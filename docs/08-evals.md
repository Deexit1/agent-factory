# 08 — Evals (the quality ratchet)

Prompts and model routing are code. Like code, they regress silently — the eval harness
is the test suite that stops that. `make eval` is a blocking CI check on any diff
touching `prompts/**` or model routing config.

## Golden sets
| Set | Contents | Judged on |
|---|---|---|
| `evals/planner/` | 15–25 real ideas (incl. Phase-1 pilot retros) with reference decompositions | task independence, criteria verifiability, dependency correctness, right-sizing |
| `evals/dev/` | 10+ solved tickets: real Phase-1 pilot PRs (repo snapshot pinned to the pre-PR SHA + TaskSpec + the real diff) plus hand-authored synthetic cases sized like real tickets — the pilot was descoped to 3 real tickets (`tasks/PILOT-REPORT.md`), so "20-30 pilot tickets" wasn't achievable; see T-101 changelog | tests pass, criteria→test mapping complete, no out-of-scope edits |
| `evals/review/` | PRs with planted defects (bugs, secrets, style, scope creep) + clean PRs | catch rate vs false-block rate |
| `evals/distiller/` | raw CI logs + hand-written reference FailureReports | field accuracy, suspect-file hit rate |

## Scoring
- Deterministic checks first (schema validity, tests pass, forbidden-file edits).
- Model-graded rubric second (haiku-class judge with a fixed rubric prompt, temperature 0),
  spot-audited by humans weekly.
- Each set has a floor score in `evals/thresholds.yaml`. Below floor = red CI.

## Rules
- New failure in production → add a case to the relevant golden set in the fix PR
  (regression test culture, applied to prompts).
- Golden sets are versioned data; changing a case or threshold requires human approval.
- Nightly full-eval run posts a trend dashboard; a >5% week-over-week drop pages the
  platform lead even if still above floor.
