# SPEC-206 — Onboarding & Abuse Controls

## Goal
A stranger can sign up and reach their first agent-built PR in under 15 minutes —
and abusers get stopped at intake.

## In scope
- Self-serve signup (email + OAuth), org creation wizard: add LLM key → connect repo
  (or provision) → create first idea → guided first ticket.
- Idea/task intake screening: automated content check for prohibited use (malware,
  credential attacks, scraping farms, spam infra) → reject with reason + audit event;
  borderline → platform-staff review queue.
- Acceptable-use policy + ToS acceptance recorded; per-org strike/appeal handling.
- Product telemetry for the funnel (signup → key added → repo connected → first PR),
  privacy-respecting, org-level.
- In-app docs: BYOK setup guides per provider, checkpoint explainer.

## Acceptance criteria
1. E2E test: fresh signup to merged first PR on a fixture repo, fully self-serve.
2. Seeded prohibited-use fixtures are rejected at intake with an audit trail; seeded
   borderline fixtures land in the review queue.
3. ToS acceptance is recorded with version + timestamp and re-prompted on ToS change.
4. Funnel dashboard reproduces a seeded fixture cohort exactly.
5. A struck org's tickets are `blocked`, not deleted; appeal flow reactivates them.
