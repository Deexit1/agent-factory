"""SPEC-101 AC3: fail CI if evals/thresholds.yaml LOWERS a floor without an approving
review from a CODEOWNERS login already on the PR.

Standalone (not part of the orchestrator package) since it only runs inside
.github/workflows/eval-gate.yml's threshold-governance job, via `python3
apps/orchestrator/scripts/check_threshold_governance.py`. Reads BASE_REF, GH_TOKEN,
PR_NUMBER, REPO from the environment (set by that workflow step).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _lowered_sets(old: dict[str, object], new: dict[str, object]) -> list[str]:
    lowered = []
    for name, entry in new.items():
        if not isinstance(entry, dict):
            continue
        old_entry = old.get(name)
        old_floor = old_entry.get("floor") if isinstance(old_entry, dict) else None
        new_floor = entry.get("floor")
        if isinstance(old_floor, int | float) and isinstance(new_floor, int | float):
            if new_floor < old_floor:
                lowered.append(name)
    return lowered


def _codeowners_logins() -> set[str]:
    codeowners_path = _REPO_ROOT / "CODEOWNERS"
    logins = set()
    for line in codeowners_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "evals/thresholds.yaml" not in line:
            continue
        for token in line.split()[1:]:
            if token.startswith("@"):
                logins.add(token.removeprefix("@"))
    return logins


def _has_codeowner_approval(repo: str, pr_number: str, owners: set[str]) -> bool:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls/{pr_number}/reviews"],
        capture_output=True,
        text=True,
        check=True,
    )
    reviews = json.loads(result.stdout)
    return any(
        review.get("state") == "APPROVED" and review.get("user", {}).get("login") in owners
        for review in reviews
    )


def main() -> int:
    base_ref = os.environ["BASE_REF"]
    pr_number = os.environ["PR_NUMBER"]
    repo = os.environ["REPO"]

    old_text = subprocess.run(
        ["git", "show", f"origin/{base_ref}:evals/thresholds.yaml"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    old = yaml.safe_load(old_text) or {}
    new = yaml.safe_load((_REPO_ROOT / "evals" / "thresholds.yaml").read_text()) or {}

    lowered = _lowered_sets(old, new)
    if not lowered:
        print("No floors lowered in evals/thresholds.yaml; nothing to gate.")
        return 0

    owners = _codeowners_logins()
    if _has_codeowner_approval(repo, pr_number, owners):
        print(f"Floors lowered for {lowered}, but a CODEOWNERS approval is present. OK.")
        return 0

    print(
        f"evals/thresholds.yaml lowers a floor for {lowered} without an approving "
        f"review from a CODEOWNERS login ({sorted(owners)}). Get that approval, then "
        "re-run this check."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
