"""Loads evals/thresholds.yaml and the per-set case YAML files (SPEC-101)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from schemas import AcceptanceCriterion, Complexity, TaskSpec

# apps/orchestrator/src/orchestrator/evals/loader.py -> repo root is 5 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[5]
EVALS_ROOT = _REPO_ROOT / "evals"

SET_NAMES = ("dev", "distiller", "planner", "review")


@dataclass(frozen=True)
class SetThreshold:
    set_name: str
    floor: float | None
    not_yet_enforced: bool
    updated_by: str
    rationale: str


def load_thresholds(evals_root: Path = EVALS_ROOT) -> dict[str, SetThreshold]:
    raw = yaml.safe_load((evals_root / "thresholds.yaml").read_text(encoding="utf-8"))
    return {
        name: SetThreshold(
            set_name=name,
            floor=entry.get("floor"),
            not_yet_enforced=bool(entry.get("not_yet_enforced", False)),
            updated_by=str(entry.get("updated_by", "")),
            rationale=str(entry.get("rationale", "")),
        )
        for name, entry in raw.items()
        if name in SET_NAMES
    }


@dataclass(frozen=True)
class DevVerification:
    mode: str  # "pytest" | "manual"
    test_command: str | None = None
    working_dir: str | None = None
    allowed_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class DevCase:
    case_id: str
    title: str
    source: str  # "real" | "synthetic"
    starter_kind: str  # "repo_snapshot" | "standalone"
    starter_ref: str | None  # git SHA, for repo_snapshot
    starter_dir: Path | None  # directory of embedded files, for standalone
    task_spec: TaskSpec
    verification: DevVerification
    reference_patch: str
    rubric_weights: dict[str, float]
    case_dir: Path


def _load_task_spec(raw: dict[str, Any]) -> TaskSpec:
    return TaskSpec(
        id=raw["id"],
        title=raw["title"],
        context=raw["context"],
        constraints=raw.get("constraints", []),
        acceptance_criteria=[
            AcceptanceCriterion(
                id=c["id"], description=c["description"], verification=c["verification"]
            )
            for c in raw["acceptance_criteria"]
        ],
        complexity=Complexity(raw["complexity"]),
        budget_usd=float(raw["budget_usd"]),
    )


def load_dev_cases(evals_root: Path = EVALS_ROOT) -> list[DevCase]:
    cases_dir = evals_root / "dev" / "cases"
    if not cases_dir.exists():
        return []

    cases = []
    for case_dir in sorted(p for p in cases_dir.iterdir() if p.is_dir()):
        raw = yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))
        starter = raw["starter"]
        verification_raw = raw["verification"]
        cases.append(
            DevCase(
                case_id=raw["case_id"],
                title=raw["title"],
                source=raw["source"],
                starter_kind=starter["kind"],
                starter_ref=starter.get("ref"),
                starter_dir=(case_dir / starter["dir"]) if "dir" in starter else None,
                task_spec=_load_task_spec(raw["task_spec"]),
                verification=DevVerification(
                    mode=verification_raw["mode"],
                    test_command=verification_raw.get("test_command"),
                    working_dir=verification_raw.get("working_dir"),
                    allowed_paths=tuple(verification_raw.get("allowed_paths", [])),
                ),
                reference_patch=(case_dir / raw["reference_diff_file"]).read_text(
                    encoding="utf-8"
                ),
                rubric_weights=dict(raw["rubric_weights"]),
                case_dir=case_dir,
            )
        )
    return cases


@dataclass(frozen=True)
class DistillerReference:
    failing_suite: str
    failing_tests: tuple[str, ...]
    expected_vs_actual: str
    suspect_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class DistillerCase:
    case_id: str
    title: str
    ticket_id: str
    suite: str
    attempt_no: int
    raw_log: str
    reference: DistillerReference
    rubric_weights: dict[str, float]


def load_distiller_cases(evals_root: Path = EVALS_ROOT) -> list[DistillerCase]:
    cases_dir = evals_root / "distiller" / "cases"
    if not cases_dir.exists():
        return []

    cases = []
    for case_file in sorted(cases_dir.glob("*.yaml")):
        raw = yaml.safe_load(case_file.read_text(encoding="utf-8"))
        input_meta = raw["input_meta"]
        reference_raw = raw["reference"]
        cases.append(
            DistillerCase(
                case_id=raw["case_id"],
                title=raw["title"],
                ticket_id=input_meta["ticket_id"],
                suite=input_meta["suite"],
                attempt_no=int(input_meta["attempt_no"]),
                raw_log=raw["raw_log"],
                reference=DistillerReference(
                    failing_suite=reference_raw["failing_suite"],
                    failing_tests=tuple(reference_raw["failing_tests"]),
                    expected_vs_actual=reference_raw["expected_vs_actual"],
                    suspect_files=tuple(reference_raw.get("suspect_files", [])),
                ),
                rubric_weights=dict(raw["rubric_weights"]),
            )
        )
    return cases
