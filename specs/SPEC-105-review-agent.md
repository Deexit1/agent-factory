# SPEC-105 — Review Agent & in_review Gate

## Goal
Automated first-pass code review between dev and QA: block obvious defects cheaply,
before CI minutes are spent. Human can always override.

## In scope
- New state `in_review` wired per docs/03-state-machine.md (shared bounce_count).
- Review agent (sonnet-class): input = PR diff, TaskSpec, style guide, Semgrep output;
  output = structured review (comments[], scope_violations[], verdict approve|block).
- Verdict handling in orchestrator: approve → `in_qa`; block → `bounced` with
  FailureReport(kind=review); 3rd total bounce → `escalated`.
- Comments posted to the GitHub PR; human override button on the board (approver role)
  records an approval row.
- Golden set `evals/review/` with planted-defect PRs.

## Acceptance criteria
1. A PR with a planted out-of-scope file edit is blocked with a scope_violation naming
   the file.
2. A clean fixture PR is approved and transitions to `in_qa` automatically.
3. Review-block then QA-fail on the same ticket yields bounce_count = 2 (shared counter).
4. Human override on a blocked PR transitions to `in_qa` and records the approval row.
5. Review set false-block rate ≤ 10% on the golden set (eval floor).
