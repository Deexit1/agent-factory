"""JUnit XML + markdown summary output for `make eval` (SPEC-101 AC5)."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
RESULTS_DIR = _REPO_ROOT / "evals" / "results"


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    title: str
    score: float
    rationale: str


@dataclass(frozen=True)
class SetReport:
    set_name: str
    floor: float | None
    scores: list[CaseScore]

    @property
    def average(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.score for s in self.scores) / len(self.scores)

    @property
    def passed(self) -> bool:
        return self.floor is None or self.average >= self.floor


def write_junit(set_reports: list[SetReport], path: Path) -> None:
    root = ET.Element("testsuites")
    for report in set_reports:
        suite = ET.SubElement(
            root,
            "testsuite",
            name=f"eval.{report.set_name}",
            tests=str(len(report.scores)),
            failures=str(sum(1 for s in report.scores if report.floor and s.score < report.floor)),
        )
        for case in report.scores:
            case_el = ET.SubElement(
                suite,
                "testcase",
                name=f"{case.case_id}: {case.title}",
                classname=f"eval.{report.set_name}",
            )
            if report.floor is not None and case.score < report.floor:
                failure = ET.SubElement(
                    case_el,
                    "failure",
                    message=f"score {case.score:.1f} below floor {report.floor}",
                )
                failure.text = case.rationale
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        ET.ElementTree(root).write(f, encoding="unicode", xml_declaration=True)


def write_markdown_summary(set_reports: list[SetReport], path: Path) -> str:
    lines = ["# Eval results (SPEC-101)", ""]
    for report in set_reports:
        status = "PASS" if report.passed else "FAIL"
        floor_text = str(report.floor) if report.floor is not None else "n/a"
        lines.append(
            f"## {report.set_name}: {status} (avg {report.average:.1f}, floor {floor_text})"
        )
        worst = sorted(report.scores, key=lambda s: s.score)[:3]
        if worst:
            lines.append("")
            lines.append("Worst 3 cases:")
            for case in worst:
                lines.append(
                    f"- `{case.case_id}` ({case.title}): {case.score:.1f} — {case.rationale}"
                )
        lines.append("")
    text = "\n".join(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text
