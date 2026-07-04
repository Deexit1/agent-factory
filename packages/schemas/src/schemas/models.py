from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

SCHEMA_VERSION: Literal["1.0"] = "1.0"


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
