"""T-205 (SPEC-205 AC3): "Downgrading a plan tightens quotas at period end, not
immediately (test both sides)." Real Postgres — org.max_parallel_tickets is T-201's
one actually-enforced quota field, so this test proves set_plan's effect on the exact
mechanism that matters."""

from datetime import timedelta

from sqlalchemy.orm import Session

from api.billing_plans import PLANS
from api.db.models import Org
from api.repositories import org_repository
from api.services import billing_service


def test_upgrade_applies_immediately(db_session: Session) -> None:
    org = org_repository.create_org(db_session, name="Upgrade Org")
    db_session.commit()
    assert org.plan == "free"
    # T-201's own precedent (test_org_quota.py::test_org_with_no_quota_configured_is_
    # unaffected): a freshly created org is unlimited until a plan is actually applied
    # via set_plan — `plan="free"` here is bookkeeping only, not auto-enforcement.
    assert org.max_parallel_tickets is None

    billing_service.set_plan(db_session, org.id, "team")
    db_session.commit()

    refreshed = db_session.get(Org, org.id)
    assert refreshed is not None
    assert refreshed.plan == "team"
    assert refreshed.max_parallel_tickets == PLANS["team"].max_parallel_tickets
    assert refreshed.pending_plan is None


def test_downgrade_does_not_tighten_the_quota_immediately(db_session: Session) -> None:
    org = org_repository.create_org(db_session, name="Downgrade Org")
    billing_service.set_plan(db_session, org.id, "team")
    db_session.commit()

    billing_service.set_plan(db_session, org.id, "starter")
    db_session.commit()

    refreshed = db_session.get(Org, org.id)
    assert refreshed is not None
    # AC3 side 1: still on the old (looser) plan/quota right after the request.
    assert refreshed.plan == "team"
    assert refreshed.max_parallel_tickets == PLANS["team"].max_parallel_tickets
    assert refreshed.pending_plan == "starter"
    assert refreshed.pending_plan_effective_at == refreshed.current_period_end


def test_downgrade_tightens_the_quota_once_the_period_sweep_runs_past_period_end(
    db_session: Session,
) -> None:
    org = org_repository.create_org(db_session, name="Sweep Org")
    billing_service.set_plan(db_session, org.id, "team")
    db_session.commit()
    billing_service.set_plan(db_session, org.id, "starter")
    db_session.commit()

    stored = db_session.get(Org, org.id)
    assert stored is not None
    assert stored.current_period_end is not None
    # Simulate time passing rather than mutating current_period_end directly — the
    # sweep's own trigger IS "now >= current_period_end", so passing a future `now`
    # exercises the exact real code path instead of hand-crafting inconsistent state.
    future_now = stored.current_period_end + timedelta(hours=1)

    applied = billing_service.apply_pending_plan_sweep(db_session, now=future_now)
    db_session.commit()

    assert [o.id for o in applied] == [org.id]
    refreshed = db_session.get(Org, org.id)
    assert refreshed is not None
    # AC3 side 2: the quota is tightened for real now that the period has ended.
    assert refreshed.plan == "starter"
    assert refreshed.max_parallel_tickets == PLANS["starter"].max_parallel_tickets
    assert refreshed.pending_plan is None
    assert refreshed.pending_plan_effective_at is None
    # The billing period rolled forward past the simulated "now" — not stuck in the past.
    assert refreshed.current_period_end is not None
    assert refreshed.current_period_end > future_now
