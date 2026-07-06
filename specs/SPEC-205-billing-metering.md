# SPEC-205 — Billing & Metering

## Goal
Charge for platform usage (tokens are the customer's BYOK cost): subscription tiers +
metered units, driven by data we already record.

## In scope
- Stripe integration: products/tiers (seats, parallel-ticket limits), metered items
  (agent-run minutes, sandbox minutes, active tickets); customer portal for invoices
  and payment methods.
- Nightly metering job: cost_ledger + runner metrics → Stripe usage records; idempotent
  and replayable.
- Plan enforcement: tier limits map to SPEC-201 quotas automatically.
- Dunning: failed payment → grace period → org paused (tickets `blocked`, data retained).
- Free tier for the beta: hard caps, no card required.

## Acceptance criteria
1. Metering job is idempotent: re-running a day produces zero duplicate usage records.
2. Seeded month of fixtures produces a Stripe test-mode invoice matching a golden total.
3. Downgrading a plan tightens quotas at period end, not immediately (test both sides).
4. Payment failure walks the dunning path and pauses the org; payment fix unpauses.
5. Usage shown in the org dashboard equals what Stripe was told (reconciliation test).
