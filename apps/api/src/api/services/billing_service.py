"""T-205 (SPEC-205): subscription plan changes, the nightly usage-metering job, and the
Razorpay-driven dunning path. Mirrors github_repo_service.py's shape (real vendor client
+ repository rows + a force-block reuse of ticket_service.request_transition) and
provider_health_service.py's own disclosed standing: no scheduler daemon exists
anywhere in this repo, so run_metering_for_all_orgs/apply_pending_plan_sweep/
expire_grace_periods are meant to be called by scripts/run_billing_metering.py, an
externally-triggered ops entrypoint — nothing here assumes a cron exists.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from api import razorpay_client
from api.billing_plans import PLANS, InvoiceBreakdown, UsageTotals, compute_invoice
from api.db.models import Org, Ticket, TicketState
from api.repositories import billing_repository as billing_repo
from api.repositories import ticket_repository
from api.services import ticket_service

BILLING_SYSTEM_ACTOR = "system:billing"
GRACE_PERIOD = timedelta(days=7)
_BILLING_PERIOD = timedelta(days=30)

_USAGE_KINDS = ("agent_run_minutes", "sandbox_minutes", "active_tickets")


class BillingServiceError(Exception):
    pass


class OrgNotFound(BillingServiceError):
    def __init__(self, org_id: str) -> None:
        self.org_id = org_id
        super().__init__(f"org {org_id} not found")


class UnknownPlan(BillingServiceError):
    def __init__(self, plan_key: str) -> None:
        self.plan_key = plan_key
        super().__init__(f"unknown plan {plan_key!r}")


def _get_org(session: Session, org_id: str) -> Org:
    org = session.get(Org, org_id)
    if org is None:
        raise OrgNotFound(org_id)
    return org


def _ensure_billing_period(org: Org) -> None:
    """Lazily initializes current_period_end for orgs created before this column
    existed — avoids a migration-time backfill sweep."""
    if org.current_period_end is None:
        org.current_period_end = datetime.now(UTC) + _BILLING_PERIOD


def get_org_billing(session: Session, org_id: str) -> Org:
    """Read-only accessor for routers/billing.py's `GET .../billing` status route."""
    return _get_org(session, org_id)


def set_plan(session: Session, org_id: str, new_plan_key: str) -> Org:
    """AC3: upgrade (new plan's max_parallel_tickets >= current) applies immediately;
    downgrade is deferred to `org.current_period_end` and only takes effect once
    apply_pending_plan_sweep runs past it."""
    if new_plan_key not in PLANS:
        raise UnknownPlan(new_plan_key)
    org = _get_org(session, org_id)
    _ensure_billing_period(org)

    current_plan = PLANS.get(org.plan, PLANS["free"])
    new_plan = PLANS[new_plan_key]

    if new_plan.max_parallel_tickets >= current_plan.max_parallel_tickets:
        org.plan = new_plan_key
        org.max_parallel_tickets = new_plan.max_parallel_tickets
        org.pending_plan = None
        org.pending_plan_effective_at = None
    else:
        org.pending_plan = new_plan_key
        org.pending_plan_effective_at = org.current_period_end

    session.flush()
    return org


def _bill_elapsed_period(
    session: Session, org: Org, *, period_start: date, period_end: date
) -> None:
    """Real overage billing: one Razorpay addon per metered line item with overage,
    computed once from the whole elapsed period's recorded usage — not prorated
    day-by-day, so it agrees exactly with compute_invoice_for_period's own math (and
    therefore with AC2's golden-total test)."""
    if org.razorpay_subscription_id is None:
        return
    invoice = compute_invoice_for_period(
        session, org_id=org.id, start_date=period_start, end_date=period_end
    )
    for item in invoice.line_items:
        if item.overage > 0 and item.amount_inr > 0:
            razorpay_client.create_addon(
                subscription_id=org.razorpay_subscription_id,
                name=f"{item.kind} overage ({period_start.isoformat()}..{period_end.isoformat()})",
                amount_inr=item.amount_inr,
            )


def apply_pending_plan_sweep(session: Session, *, now: datetime | None = None) -> list[Org]:
    """Applies any org whose deferred downgrade has reached its period end — the other
    half of AC3's "tightens at period end, not immediately". Also bills the elapsed
    period's overage (see _bill_elapsed_period) and rolls current_period_end forward a
    month — this is this repo's only "billing period rollover" mechanism, since no
    scheduler exists to do it separately."""
    now = now or datetime.now(UTC)
    applied: list[Org] = []
    for org_id in billing_repo.list_all_org_ids(session):
        org = _get_org(session, org_id)
        _ensure_billing_period(org)
        assert org.current_period_end is not None
        if org.current_period_end > now:
            continue

        period_start = (org.current_period_end - _BILLING_PERIOD).date()
        period_end = org.current_period_end.date()
        _bill_elapsed_period(session, org, period_start=period_start, period_end=period_end)

        if org.pending_plan is not None and org.pending_plan_effective_at is not None:
            if org.pending_plan_effective_at <= now:
                new_plan = PLANS[org.pending_plan]
                org.plan = org.pending_plan
                org.max_parallel_tickets = new_plan.max_parallel_tickets
                org.pending_plan = None
                org.pending_plan_effective_at = None
                applied.append(org)
        org.current_period_end = org.current_period_end + _BILLING_PERIOD
    session.flush()
    return applied


def compute_org_usage_for_period(
    session: Session, *, org_id: str, start: datetime, end: datetime
) -> UsageTotals:
    return UsageTotals(
        agent_run_minutes=billing_repo.sum_agent_run_minutes(
            session, org_id=org_id, start=start, end=end
        ),
        sandbox_minutes=billing_repo.sum_usage_events(
            session, org_id=org_id, kind="sandbox_minutes", start=start, end=end
        ),
        active_tickets=billing_repo.count_active_tickets(
            session, org_id=org_id, start=start, end=end
        ),
    )


def run_metering_for_day(session: Session, *, org_id: str, report_date: date) -> list[str]:
    """AC1: idempotent — for each of the 3 metered kinds, upserts-if-absent against
    billing_usage_reports; a second call for the same (org_id, report_date) makes zero
    new rows. Records raw usage only — pricing/overage is computed once per elapsed
    billing period (see _bill_elapsed_period), not prorated day-by-day, so it agrees
    exactly with compute_invoice_for_period's math. Returns the kinds actually reported
    this call (empty on a repeat run)."""
    _get_org(session, org_id)  # raises OrgNotFound rather than silently reporting zeros
    start = datetime.combine(report_date, datetime.min.time(), tzinfo=UTC)
    end = start + timedelta(days=1)
    usage = compute_org_usage_for_period(session, org_id=org_id, start=start, end=end)
    usage_by_kind = {
        "agent_run_minutes": usage.agent_run_minutes,
        "sandbox_minutes": usage.sandbox_minutes,
        "active_tickets": usage.active_tickets,
    }

    reported: list[str] = []
    for kind in _USAGE_KINDS:
        already_reported = billing_repo.get_usage_report(
            session, org_id=org_id, report_date=report_date, kind=kind
        )
        if already_reported:
            continue  # AC1: already reported for this day — no-op

        billing_repo.record_usage_report(
            session,
            org_id=org_id,
            report_date=report_date,
            kind=kind,
            quantity=usage_by_kind[kind],
            razorpay_addon_id=None,
            created_at=datetime.now(UTC),
        )
        reported.append(kind)

    session.flush()
    return reported


def run_metering_for_all_orgs(session: Session, *, report_date: date) -> dict[str, list[str]]:
    return {
        org_id: run_metering_for_day(session, org_id=org_id, report_date=report_date)
        for org_id in billing_repo.list_all_org_ids(session)
    }


def compute_invoice_for_period(
    session: Session, *, org_id: str, start_date: date, end_date: date
) -> InvoiceBreakdown:
    """AC2: sums the raw usage run_metering_for_day already recorded for the period and
    feeds it through the same pure compute_invoice used by the golden-total unit test —
    also what _bill_elapsed_period uses to decide real Razorpay addon amounts, so the
    two always agree exactly."""
    org = _get_org(session, org_id)
    plan = PLANS.get(org.plan, PLANS["free"])
    usage = UsageTotals(
        agent_run_minutes=billing_repo.sum_usage_reports(
            session,
            org_id=org_id,
            kind="agent_run_minutes",
            start_date=start_date,
            end_date=end_date,
        ),
        sandbox_minutes=billing_repo.sum_usage_reports(
            session, org_id=org_id, kind="sandbox_minutes", start_date=start_date, end_date=end_date
        ),
        active_tickets=billing_repo.sum_usage_reports(
            session, org_id=org_id, kind="active_tickets", start_date=start_date, end_date=end_date
        ),
    )
    return compute_invoice(plan, usage)


def compute_live_invoice_for_period(
    session: Session, *, org_id: str, start_date: date, end_date: date
) -> InvoiceBreakdown:
    """AC5: computed directly from usage_events/agent_runs/ticket_events (the same raw
    source data run_metering_for_day itself reads), independent of billing_usage_reports
    — what the org dashboard (routers/billing.py's GET .../usage) shows. The
    reconciliation test checks this against compute_invoice_for_period's ledger-based
    total for the same period, proving the two independently-derived numbers agree."""
    org = _get_org(session, org_id)
    plan = PLANS.get(org.plan, PLANS["free"])
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(end_date, datetime.min.time(), tzinfo=UTC)
    usage = compute_org_usage_for_period(session, org_id=org_id, start=start, end=end)
    return compute_invoice(plan, usage)


def pause_org_for_nonpayment(
    session: Session, *, org_id: str, actor: str = BILLING_SYSTEM_ACTOR
) -> list[Ticket]:
    """AC4: `github_repo_service.disconnect_repo`'s force-block loop verbatim, keyed off
    org instead of repo. "Data retained" is satisfied by construction — nothing here
    deletes anything."""
    org = _get_org(session, org_id)
    org.billing_status = "paused"
    in_flight = ticket_repository.list_in_flight_by_org(session, org_id=org_id)
    blocked: list[Ticket] = []
    for ticket in in_flight:
        updated = ticket_service.request_transition(
            session,
            ticket.id,
            TicketState.BLOCKED,
            actor,
            org_id=org_id,
            reason="org paused for nonpayment",
        )
        blocked.append(updated)
    session.flush()
    return blocked


def handle_payment_failed(session: Session, *, razorpay_subscription_id: str) -> Org | None:
    """AC4 step 1: grace period starts — the org is NOT touched otherwise yet."""
    org = billing_repo.get_org_by_razorpay_subscription_id(session, razorpay_subscription_id)
    if org is None:
        return None
    org.billing_status = "past_due"
    org.dunning_grace_until = datetime.now(UTC) + GRACE_PERIOD
    session.flush()
    return org


def handle_payment_succeeded(session: Session, *, razorpay_subscription_id: str) -> Org | None:
    """AC4 step 3: "payment fix unpauses" — clears billing_status/grace. Already-BLOCKED
    tickets are NOT auto-unblocked (BLOCKED has no whitelisted exit in state_machine.py
    at all today — a pre-existing gap since T-203, not created or closed here)."""
    org = billing_repo.get_org_by_razorpay_subscription_id(session, razorpay_subscription_id)
    if org is None:
        return None
    org.billing_status = "active"
    org.dunning_grace_until = None
    session.flush()
    return org


def expire_grace_periods(session: Session, *, now: datetime | None = None) -> list[Org]:
    """AC4 step 2: grace period -> org paused. Part of the nightly job, run alongside
    apply_pending_plan_sweep for the same reason (no scheduler daemon exists)."""
    now = now or datetime.now(UTC)
    paused: list[Org] = []
    for org_id in billing_repo.list_all_org_ids(session):
        org = _get_org(session, org_id)
        if org.billing_status != "past_due" or org.dunning_grace_until is None:
            continue
        if org.dunning_grace_until <= now:
            pause_org_for_nonpayment(session, org_id=org_id)
            paused.append(org)
    return paused


def subscribe(session: Session, *, org_id: str, plan_key: str, email: str) -> str:
    """Creates the Razorpay customer+subscription for a free -> paid upgrade and
    returns the hosted checkout short_url. Free-plan orgs never call this — they stay
    card-free by construction (AC's "Free tier for the beta: hard caps, no card
    required")."""
    if plan_key not in PLANS:
        raise UnknownPlan(plan_key)
    org = _get_org(session, org_id)
    if org.razorpay_customer_id is None:
        customer = razorpay_client.create_customer(name=org.name, email=email)
        org.razorpay_customer_id = customer.id
    subscription = razorpay_client.create_subscription(
        plan_key=plan_key, customer_id=org.razorpay_customer_id
    )
    org.razorpay_subscription_id = subscription.id
    session.flush()
    set_plan(session, org_id, plan_key)
    return subscription.short_url


def portal_link(session: Session, *, org_id: str) -> str:
    org = _get_org(session, org_id)
    if org.razorpay_subscription_id is None:
        raise BillingServiceError(f"org {org_id} has no active Razorpay subscription")
    subscription = razorpay_client.fetch_subscription(subscription_id=org.razorpay_subscription_id)
    return subscription.short_url
