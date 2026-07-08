"""T-205 (SPEC-205): subscription tier definitions + the pure invoice-computation
function AC2's golden-total test asserts against.

No pricing figures exist anywhere in this repo's docs — the three tiers below
(`free`/`starter`/`team`) are explicit **placeholders** pending a real business
decision, chosen so the *mechanism* (plan storage, SPEC-201 quota mapping, metered
overage math, idempotent Razorpay reporting) is fully real and correct. Swap the
numbers here later; nothing downstream needs to change.

Prices are in INR (Razorpay's primary settlement currency, matching this session's
Stripe -> Razorpay vendor swap — see docs/06-tech-stack.md's Billing row).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanDefinition:
    key: str
    name: str
    monthly_price_inr: float
    # Informational only — no SPEC-205 acceptance criterion tests seat-capacity
    # enforcement, so this is stored but not enforced (disclosed non-goal).
    seats_included: int
    # Maps straight onto `orgs.max_parallel_tickets` (T-201's one real, enforced
    # quota) via billing_service.set_plan.
    max_parallel_tickets: int
    included_agent_run_minutes: float
    included_sandbox_minutes: float
    included_active_tickets: float
    # None on `free`: the free tier hard-caps instead of billing overage (see
    # ticket_service._org_over_usage_cap) — there is nothing to charge per-minute for.
    agent_run_minute_rate_inr: float | None
    sandbox_minute_rate_inr: float | None
    active_ticket_rate_inr: float | None
    requires_card: bool


PLANS: dict[str, PlanDefinition] = {
    "free": PlanDefinition(
        key="free",
        name="Free (beta)",
        monthly_price_inr=0,
        seats_included=1,
        max_parallel_tickets=1,
        included_agent_run_minutes=300,
        included_sandbox_minutes=300,
        included_active_tickets=5,
        agent_run_minute_rate_inr=None,
        sandbox_minute_rate_inr=None,
        active_ticket_rate_inr=None,
        requires_card=False,
    ),
    "starter": PlanDefinition(
        key="starter",
        name="Starter",
        monthly_price_inr=4_999,
        seats_included=3,
        max_parallel_tickets=3,
        included_agent_run_minutes=3_000,
        included_sandbox_minutes=3_000,
        included_active_tickets=20,
        agent_run_minute_rate_inr=2.0,
        sandbox_minute_rate_inr=1.0,
        active_ticket_rate_inr=50.0,
        requires_card=True,
    ),
    "team": PlanDefinition(
        key="team",
        name="Team",
        monthly_price_inr=14_999,
        seats_included=10,
        max_parallel_tickets=8,
        included_agent_run_minutes=10_000,
        included_sandbox_minutes=10_000,
        included_active_tickets=60,
        agent_run_minute_rate_inr=1.5,
        sandbox_minute_rate_inr=0.75,
        active_ticket_rate_inr=40.0,
        requires_card=True,
    ),
}

@dataclass(frozen=True)
class UsageTotals:
    agent_run_minutes: float
    sandbox_minutes: float
    active_tickets: float


@dataclass(frozen=True)
class InvoiceLineItem:
    kind: str
    included: float
    used: float
    overage: float
    rate_inr: float | None
    amount_inr: float


@dataclass(frozen=True)
class InvoiceBreakdown:
    plan_key: str
    base_fee_inr: float
    line_items: list[InvoiceLineItem]
    total_inr: float


def _line_item(kind: str, included: float, used: float, rate: float | None) -> InvoiceLineItem:
    overage = max(0.0, used - included)
    amount = overage * rate if rate is not None else 0.0
    return InvoiceLineItem(
        kind=kind, included=included, used=used, overage=overage, rate_inr=rate, amount_inr=amount
    )


def compute_invoice(plan: PlanDefinition, usage: UsageTotals) -> InvoiceBreakdown:
    """Pure function: base fee + max(0, used - included) * rate per metered item.

    No I/O — this is exactly what AC2's golden-total test seeds fixtures for and
    asserts against, independent of whether a real Razorpay call ever happens.
    """
    line_items = [
        _line_item(
            "agent_run_minutes",
            plan.included_agent_run_minutes,
            usage.agent_run_minutes,
            plan.agent_run_minute_rate_inr,
        ),
        _line_item(
            "sandbox_minutes",
            plan.included_sandbox_minutes,
            usage.sandbox_minutes,
            plan.sandbox_minute_rate_inr,
        ),
        _line_item(
            "active_tickets",
            plan.included_active_tickets,
            usage.active_tickets,
            plan.active_ticket_rate_inr,
        ),
    ]
    total = plan.monthly_price_inr + sum(item.amount_inr for item in line_items)
    return InvoiceBreakdown(
        plan_key=plan.key,
        base_fee_inr=plan.monthly_price_inr,
        line_items=line_items,
        total_inr=total,
    )
