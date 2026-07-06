from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

SCHEMA_VERSION: Literal["1.0"] = "1.0"

# T-104 (SPEC-103): single-repo system today (no GitHub-connect/multi-repo yet, see
# T-201/T-203) — matches apps/orchestrator/scripts/run_pilot.py's own hardcoded repo.
DEFAULT_REPO = "git@github.com:Deexit1/agent-factory.git"


class Complexity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AcceptanceCriterion(BaseModel):
    """A single machine-checkable acceptance criterion for a TaskSpec."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: str
    description: str
    verification: str = Field(description="Test name/pattern that proves this criterion")


class TaskSpec(BaseModel):
    """Product Planner -> Dev agent hand-off contract."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: str
    title: str
    context: str
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion]
    complexity: Complexity
    budget_usd: float = Field(gt=0)
    depends_on: list[str] = Field(
        default_factory=list, description="Sibling task ids this task depends on"
    )
    estimate_days: float | None = Field(
        default=None, gt=0, description="Planner's estimate; >1 is a non-blocking review flag"
    )
    epic_id: str | None = Field(default=None, description="Parent epic id, set by the Planner")
    repo: str = Field(default=DEFAULT_REPO, description="Git repo this task's work lands in")
    required_skills: list[str] = Field(
        default_factory=list,
        description="Domain tags (e.g. frontend/backend/devops) the Delivery Manager "
        "matches against capability_registry.yaml profiles; empty matches any profile",
    )


class Epic(BaseModel):
    """A Planner-produced grouping of TaskSpecs under an approved idea."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: str
    title: str
    description: str
    budget_usd: float = Field(gt=0)


class PlannerPlan(BaseModel):
    """Planner -> human review hand-off: a full decomposition of an approved idea."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    epics: list[Epic]
    tasks: list[TaskSpec]


class PlannerQuestions(BaseModel):
    """Planner output when the idea is under-specified; ticket -> escalated."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    questions: list[str] = Field(min_length=1)


class FailureReport(BaseModel):
    """Failure distiller -> Dev agent hand-off contract, attached on bounce."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    ticket_id: str
    failing_suite: str
    failing_tests: list[str]
    expected_vs_actual: str
    suspect_files: list[str] = Field(default_factory=list)
    attempt_no: int = Field(ge=1, le=3, description="Bounce attempt number; max 3 then escalated")


class MarketEvidence(BaseModel):
    """A single cited claim backing a BusinessCase."""

    claim: str
    source_url: HttpUrl


class BusinessCase(BaseModel):
    """Exec panel -> human approval gate hand-off contract."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    idea_id: str
    opportunity: str
    market_evidence: list[MarketEvidence] = Field(default_factory=list)
    cost_estimate: float = Field(ge=0)
    risks: list[str] = Field(default_factory=list)
    recommendation: str
