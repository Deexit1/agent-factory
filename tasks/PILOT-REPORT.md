# Pilot Report — T-009

**Date:** 2026-07-05
**Scope actually run:** 3 real tickets (T-001, T-002, T-003), not the 20-30 specified in
the task — reduced by explicit human decision after the validation ticket (see "What
happened" below) to keep the pilot's cost/time proportionate to what it needed to prove.
All 3 numbers below are real: real Claude Code runs, real PRs, real GitHub Actions CI,
real webhook-driven state transitions. Nothing in this report is simulated or fixture-based.

## What happened

The very first real run of this pipeline (T-001 through T-008 had each been built with
Claude Code, `gh pr create`, and the CI gate implemented for real but deliberately never
exercised against live services — see each task's CHANGELOG entry) surfaced four real,
previously-latent bugs, none of them specific to the pilot itself:

1. **`agent-pr-gate.yml`'s semgrep and dependency-audit gates were whole-repo, not
   diff-based** — 32 pre-existing semgrep findings (unpinned GitHub Actions, missing
   Dockerfile `USER`) and a dev-only npm vulnerability set would have failed *every* PR
   forever, regardless of what it changed. Fixed: pinned actions to commit SHAs, added
   non-root `USER` to both Dockerfiles, scoped `npm audit` to production dependencies.
2. **`SubprocessClaudeCodeRunner` had never been run against a real `claude` CLI** since
   T-006 wrote it: `--output-format stream-json` needs `--verbose` or the CLI errors
   before emitting anything (silent zero-event failure), and tool calls arrive nested
   inside assistant/user turns rather than as their own event type, so every tool call
   was being recorded as a generic "message" instead of "tool_call".
3. Added a small bounded retry for transient first-turn API errors (defensive; see below,
   it wasn't the actual fix for what triggered writing it).
4. **The real root cause of most of the debugging time**: the npm-installed `claude` CLI
   was outdated (2.1.50) and has a genuine bug constructing requests for `claude-sonnet-5`
   specifically when authenticated via `ANTHROPIC_API_KEY` (vs. an interactive account
   session) — it sends a `thinking` config the API rejects. `claude update` (→ 2.1.201)
   fixed it outright. This is not pilot-specific: **any real deployment of this
   orchestrator always uses `ANTHROPIC_API_KEY`** (there's no human session to fall back
   on), so this would have affected production too. Worth a standing reminder to keep the
   `claude` CLI current.

Also found and fixed before any ticket ran: a real Anthropic API key had been pasted into
`.env.example` (a git-tracked file) rather than `.env` — caught before it was ever
committed, moved to `.env`, `.env.example` reverted to a placeholder.

Once the CLI was updated, all three tickets that were run (T-001, T-002, T-003) succeeded
on the first attempt with no further intervention.

## Known scope limitations (disclosed, not silent)

- **No sandbox/Docker isolation.** `apps/orchestrator` was never wired to `apps/sandbox`'s
  container isolation (separate integration project, out of scope here — see the T-009
  plan). Each ticket ran in a fresh, disposable `git clone` instead. The human explicitly
  accepted running without GitHub branch protection on `main` for this pilot.
- **3 tickets, not 20-30.** Reduced by explicit human decision. The four metrics below are
  real but from a small sample — treat the percentages as directional, not statistically
  powered.
- All 3 tickets happened to be genuinely small, low-risk chores (2 docs updates, 1 test
  addition) by deliberate selection (safest-first ordering) — the sample doesn't cover
  larger or more ambiguous chores.

## The four metrics vs. `docs/00-vision.md` thresholds

| Metric | Threshold | Result | Status |
|---|---|---|---|
| First-pass QA rate | ≥ 50% (closed with ≤ 1 bounce) | **100%** (3/3, all zero bounces) | ✅ Pass |
| Median cost per closed ticket | < 1 loaded engineer-hour | **$0.60** | ✅ Pass |
| Security incidents (egress violations, credential leaks, unauthorized pushes) | Zero | **Zero** during ticket execution | ✅ Pass, with a caveat below |
| Escaped defects within 2 weeks of ticket close | Zero | **Not yet measurable** | ⏳ N/A — all 3 tickets closed within this session; 2 weeks hasn't elapsed |

**Security caveat**: zero incidents were caused by the *agent's* work (no unauthorized
pushes — `git_ops.push` only ever constructs `agent/<ticket_id>` branches; no egress
violations — irrelevant without sandbox isolation; no credential leaks by any agent). The
one real credential-handling incident this session (the `.env.example` key, see above) was
a human/setup-phase issue caught and fixed *before* any pilot ticket ran, not something an
agent did — but it's exactly the kind of near-miss `docs/05-security.md`'s gates exist to
catch, so it's reported here rather than omitted.

## Raw data

`GET /dashboard/metrics` and `GET /dashboard/export.csv` (T-008), captured 2026-07-05:

```
ticket_id,state,bounce_count,created_at,done_at,cycle_time_hours,cost_usd,escaped_defects
T-001,done,0,2026-07-04T22:52:56Z,2026-07-04T23:00:58Z,0.134,0.5549,0
T-002,done,0,2026-07-04T23:05:56Z,2026-07-04T23:14:11Z,0.137,0.5968,0
T-003,done,0,2026-07-04T23:14:37Z,2026-07-04T23:24:49Z,0.170,1.0121,0
```

- Median cycle time (ready → done, includes real CI wait): **8.2 minutes**
- Total real spend: **$2.16** across 3 tickets
- PRs: [#3](https://github.com/Deexit1/agent-factory/pull/3),
  [#4](https://github.com/Deexit1/agent-factory/pull/4),
  [#5](https://github.com/Deexit1/agent-factory/pull/5)

## Recommendation

The loop works end-to-end for real, for small well-scoped chores, once the CLI-version and
CI-gate bugs above are fixed (now merged to `main`). Before trusting this for a larger or
less-curated batch: (1) wire real sandbox isolation before running agents against a repo
that doesn't have branch protection, (2) re-run with a larger, less hand-picked ticket set
to get a statistically meaningful first-pass QA rate, (3) pin or monitor the `claude` CLI
version given finding #4 above.
