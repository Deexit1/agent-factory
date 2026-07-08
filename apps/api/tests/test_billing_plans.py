"""T-205 (SPEC-205 AC2): compute_invoice is a pure function — base fee + max(0, used -
included) * rate per metered item, no I/O. This is the golden-total assertion AC2
actually cares about; test_billing_metering_job.py separately proves a seeded month of
real fixtures, run through the nightly job, produces usage totals that feed this same
function to the same result."""

from api.billing_plans import PLANS, UsageTotals, compute_invoice


def test_compute_invoice_golden_total_for_starter_plan_with_overage() -> None:
    plan = PLANS["starter"]
    usage = UsageTotals(agent_run_minutes=3_500, sandbox_minutes=3_200, active_tickets=25)

    invoice = compute_invoice(plan, usage)

    assert invoice.plan_key == "starter"
    assert invoice.base_fee_inr == 4_999
    line_items_by_kind = {item.kind: item for item in invoice.line_items}
    assert line_items_by_kind["agent_run_minutes"].overage == 500
    assert line_items_by_kind["agent_run_minutes"].amount_inr == 1_000.0
    assert line_items_by_kind["sandbox_minutes"].overage == 200
    assert line_items_by_kind["sandbox_minutes"].amount_inr == 200.0
    assert line_items_by_kind["active_tickets"].overage == 5
    assert line_items_by_kind["active_tickets"].amount_inr == 250.0
    # Golden total: 4999 base + 1000 + 200 + 250 overage = 6449
    assert invoice.total_inr == 6_449.0


def test_compute_invoice_within_plan_allowance_has_no_overage() -> None:
    plan = PLANS["starter"]
    usage = UsageTotals(agent_run_minutes=100, sandbox_minutes=100, active_tickets=1)

    invoice = compute_invoice(plan, usage)

    assert invoice.total_inr == invoice.base_fee_inr
    assert all(item.overage == 0 and item.amount_inr == 0 for item in invoice.line_items)


def test_compute_invoice_free_plan_never_bills_overage() -> None:
    """Free tier hard-caps usage instead (ticket_service._org_over_usage_cap) — even
    wildly over its included amounts, compute_invoice must never charge for it since
    agent_run_minute_rate_inr etc. are None on the free plan."""
    plan = PLANS["free"]
    usage = UsageTotals(agent_run_minutes=10_000, sandbox_minutes=10_000, active_tickets=100)

    invoice = compute_invoice(plan, usage)

    assert invoice.total_inr == 0
    assert all(item.amount_inr == 0 for item in invoice.line_items)
