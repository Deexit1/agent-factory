#!/usr/bin/env python3
"""T-201 (SPEC-201 AC2): every repository-layer function that touches the database
must be tenant-scoped. Real AST walk (not a text/regex scan like
check_llm_router_gate.py, which this repo's own T-102 comments describe as
"AST-based" but is actually a regex line-scan over import statements) — for every
top-level function in apps/api/src/api/repositories/*.py whose body calls
`session.execute(...)`, `session.get(...)`, or `session.query(...)`, verifies the
name `org_id` appears somewhere in that function (a parameter or a reference).

This is a real but simple heuristic, not full data-flow analysis: it can't prove the
org_id reference is actually used to filter the query in question, only that the
function never mentions org_id at all despite hitting the database — which is exactly
the class of bug T-107 found for real in `count_in_progress_by_repo` (a JSONB
COALESCE bug, not a missing-org_id bug, but the same "nobody double-checked this
function's tenant scoping" root cause).
"""

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES_DIR = REPO_ROOT / "apps" / "api" / "src" / "api" / "repositories"
_DB_CALL_ATTRS = {"execute", "get", "query"}

# Sequence/ID generators with no tenant data to scope — the only functions allowed to
# touch the database without ever mentioning org_id. Keep this list short and explain
# each entry inline; it is not a place to silence real gaps.
_ALLOWLIST = {
    "next_ticket_id",  # a global ticket_seq nextval() — no org-scoped row involved
    "get_user",  # user_repository.py: `users` is a global identity table (T-201) —
    # org-scoping lives on `org_members`, whose own queries DO reference org_id
    "list_orgs_for_user",  # org_repository.py: deliberately cross-org — "every org
    # this user belongs to" has no single org_id to scope by
    "get_invite_by_token",  # org_repository.py: looked up by the invite's own unique
    # token (the acceptance credential) — org_id isn't known until after this returns
    "list_by_installation",  # repo_repository.py: T-203 — a GitHub webhook delivery
    # only ever gives us an installation_id, never an org_id; the caller resolves
    # org_id per returned Repo row before doing anything tenant-scoped with it
}


def _tracked_repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "apps/api/src/api/repositories/*.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def _calls_the_database(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in _DB_CALL_ATTRS
        ):
            return True
    return False


def _references_org_id(node: ast.FunctionDef) -> bool:
    arg_names = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
    if "org_id" in arg_names:
        return True
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "org_id":
            return True
    return False


def find_violations() -> list[str]:
    violations = []
    for path in _tracked_repository_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name in _ALLOWLIST:
                continue
            if _calls_the_database(node) and not _references_org_id(node):
                rel_path = path.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}:{node.lineno}: {node.name} queries the database but "
                    "never references org_id"
                )
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("tenant-scope gate FAILED - repository function(s) missing org_id scope:")
        for v in violations:
            print(f"  {v}")
        return 1

    print("tenant-scope gate passed - every repository query references org_id")
    return 0


if __name__ == "__main__":
    sys.exit(main())
