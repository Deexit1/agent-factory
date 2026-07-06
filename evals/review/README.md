# evals/review

Scaffolded by T-101 (SPEC-101) to match the layout convention ("one folder per agent"),
but intentionally empty — the Review agent doesn't exist until T-106 (SPEC-105).

T-106 seeds this set with PRs carrying planted defects (bugs, secrets, style, scope
creep) plus clean PRs per docs/08-evals.md, and flips `review.not_yet_enforced` to
`false` in `evals/thresholds.yaml` once cases exist.
