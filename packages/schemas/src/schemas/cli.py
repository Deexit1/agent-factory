import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from schemas.models import (
    AcceptanceCriterion,
    BusinessCase,
    Epic,
    FailureReport,
    PlannerPlan,
    PlannerQuestions,
    TaskSpec,
)

MODELS: dict[str, type[BaseModel]] = {
    "task-spec": TaskSpec,
    "acceptance-criterion": AcceptanceCriterion,
    "failure-report": FailureReport,
    "business-case": BusinessCase,
    "epic": Epic,
    "planner-plan": PlannerPlan,
    "planner-questions": PlannerQuestions,
}

# packages/schemas/src/schemas/cli.py -> repo root is 4 parents up.
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUT_DIR = REPO_ROOT / "apps" / "web" / "src" / "generated" / "schemas"


def export_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in MODELS.items():
        json_schema = model.model_json_schema()
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(json_schema, indent=2) + "\n")
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="schemas")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Write JSON Schema files")
    export_parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Output directory (default: apps/web/src/generated/schemas)",
    )

    args = parser.parse_args(argv)

    if args.command == "export":
        for path in export_schemas(args.out):
            print(f"wrote {path}")


if __name__ == "__main__":
    main()
