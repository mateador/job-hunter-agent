from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_STEPS_REACHED = "max_steps_reached"


class JobCandidate(BaseModel):
    job_id: str | None = None
    company: str = Field(min_length=1)
    position: str = Field(min_length=1)
    url: str | None = None
    location: str | None = None
    snippet: str | None = None
    match_reason: str | None = None


class CompanyResearch(BaseModel):
    company: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)


class AgentFinalAnswer(BaseModel):
    """Day 2 final answer schema."""
    summary: str = Field(description="Short summary of findings.")
    jobs_reviewed: int = Field(default=0, ge=0)
    selected_jobs: list[JobCandidate] = Field(default_factory=list)
    company_research: list[CompanyResearch] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)


class AgentDecision(BaseModel):
    """Structured response expected from the model on every loop iteration."""
    reasoning_summary: str = Field(description="Short explanation of what the agent is doing.")
    
    # Day 2: Added "tool_call"
    next_action: Literal["tool_call", "final_answer"] = Field(
        description="Whether to call a tool or provide the final answer."
    )
    message_to_user: str = Field(description="Brief user-facing message for this step.")

    # Day 2: Tool calling fields
    tool_name: Literal["search_freehire_jobs", "research_company"] | None = Field(
        default=None,
        description="Required when next_action is tool_call."
    )
    tool_arguments: dict[str, Any] | None = Field(
        default=None,
        description="Required when next_action is tool_call."
    )

    final_answer: AgentFinalAnswer | None = Field(
        default=None,
        description="Required when next_action is final_answer."
    )

    @model_validator(mode="after")
    def validate_action(self) -> "AgentDecision":
        if self.next_action == "tool_call":
            if not self.tool_name:
                raise ValueError("tool_name is required when next_action is tool_call.")
            if self.tool_arguments is None:
                self.tool_arguments = {}
            if self.final_answer is not None:
                self.final_answer = None

        if self.next_action == "final_answer":
            if self.final_answer is None:
                raise ValueError("final_answer is required when next_action is final_answer.")
            if self.tool_name is not None:
                self.tool_name = None
            if self.tool_arguments is not None:
                self.tool_arguments = None

        return self


class AgentState(BaseModel):
    run_id: str
    cv_text: str
    keywords: list[str]
    max_steps: int = 8  # Increased for Day 2 tool loops
    steps_taken: int = 0
    status: RunStatus = RunStatus.RUNNING
    messages: list[dict[str, Any]] = Field(default_factory=list)
    final_answer: AgentFinalAnswer | None = None
    error: str | None = None
