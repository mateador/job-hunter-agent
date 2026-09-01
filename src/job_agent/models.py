from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_STEPS_REACHED = "max_steps_reached"


class AgentFinalAnswer(BaseModel):
    """
    Day 1 final answer.

    This is intentionally lightweight.
    Later in the week, this will become a richer job application schema.
    """

    summary: str = Field(
        description="Short summary of what the agent understood from the CV and keywords."
    )
    recommended_next_steps: list[str] = Field(
        default_factory=list,
        description="Concrete next steps for the job search workflow.",
    )


class AgentDecision(BaseModel):
    """
    Structured response expected from the model on every loop iteration.

    Day 1 supports:
    - continue
    - final_answer
    """

    reasoning_summary: str = Field(
        description="Short explanation of what the agent is doing. Do not include hidden chain-of-thought."
    )
    next_action: Literal["continue", "final_answer"] = Field(
        description="Whether the agent should continue the loop or provide the final answer."
    )
    message_to_user: str = Field(
        description="Brief user-facing message for this step."
    )
    final_answer: AgentFinalAnswer | None = Field(
        default=None,
        description="Required only when next_action is final_answer."
    )

    @model_validator(mode="after")
    def validate_action(self) -> "AgentDecision":
        if self.next_action == "final_answer" and self.final_answer is None:
            raise ValueError("final_answer is required when next_action is final_answer.")

        if self.next_action == "continue" and self.final_answer is not None:
            # Keep the state clean and predictable.
            self.final_answer = None

        return self


class AgentState(BaseModel):
    run_id: str
    cv_text: str
    keywords: list[str]
    max_steps: int = 5
    steps_taken: int = 0
    status: RunStatus = RunStatus.RUNNING
    messages: list[dict[str, Any]] = Field(default_factory=list)
    final_answer: AgentFinalAnswer | None = None
    error: str | None = None