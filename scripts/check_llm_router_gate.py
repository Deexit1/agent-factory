#!/usr/bin/env python3
"""T-102 SaaS-readiness rule 2 (docs/00-vision.md): every LLM call goes through
`packages/llm_router` — no provider SDK imported anywhere else. Fails non-zero and
lists offenders if any tracked *.py file outside packages/llm_router imports
anthropic/openai directly.

Does NOT and cannot catch apps/orchestrator/src/orchestrator/claude_runner.py's
CLI-subprocess invocation of the `claude` binary — that path has no SDK import to grep
for. See tasks/CHANGELOG.md (T-102) for why that's a disclosed, known gap left for
T-202 (BYOK) to close.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_PREFIX = "packages/llm_router/"
_IMPORT_RE = re.compile(r"^\s*(import|from)\s+(anthropic|openai)\b")


def _tracked_python_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def find_violations() -> list[str]:
    violations = []
    for rel_path in _tracked_python_files():
        if rel_path.startswith(ALLOWED_PREFIX):
            continue
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _IMPORT_RE.match(line):
                violations.append(f"{rel_path}:{line_no}: {line.strip()}")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("llm_router gate FAILED - direct provider SDK import(s) found outside "
              f"{ALLOWED_PREFIX}:")
        for v in violations:
            print(f"  {v}")
        return 1

    print(f"llm_router gate passed - no provider SDK imports outside {ALLOWED_PREFIX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
