import json
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.job_agent.llm_client import LLMClient
from src.job_agent.models import AgentDecision, AgentState, RunStatus
from src.job_agent.prompts import (
    SYSTEM_PROMPT,
    build_initial_user_prompt,
    build_json_repair_prompt,
)


console = Console()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_json_text(raw: str) -> str:
    """
    Defensive helper.

    Even with JSON mode, some models occasionally wrap output in code fences.
    We strip those before parsing.
    """

    text = raw.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines)

    return text.strip()


def create_initial_state(
    cv_text: str,
    keywords: list[str],
    max_steps: int = 5,
) -> AgentState:
    return AgentState(
        run_id=str(uuid4()),
        cv_text=cv_text,
        keywords=keywords,
        max_steps=max_steps,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": build_initial_user_prompt(cv_text=cv_text, keywords=keywords),
            },
        ],
    )


def parse_agent_decision(raw_response: str) -> AgentDecision:
    """
    Parse the model response into our strict Day 1 schema.
    """

    text = normalize_json_text(raw_response)
    data = json.loads(text)
    return AgentDecision.model_validate(data)


def print_step_header(state: AgentState) -> None:
    console.rule(
        f"[bold cyan]Run {state.run_id} | Step {state.steps_taken + 1}/{state.max_steps}"
    )


def print_decision(decision: AgentDecision) -> None:
    table = Table(title="Agent Decision")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Reasoning Summary", decision.reasoning_summary)
    table.add_row("Next Action", decision.next_action)
    table.add_row("Message", decision.message_to_user)

    console.print(table)

    if decision.final_answer:
        console.print(
            Panel(
                decision.final_answer.model_dump_json(indent=2),
                title="Final Answer",
                border_style="green",
            )
        )


def validate_initial_inputs(cv_text: str, keywords: list[str]) -> None:
    """
    Lightweight Day 1 validation.

    More formal guardrails arrive on Day 3, but we still avoid obviously bad runs.
    """

    if not cv_text or not cv_text.strip():
        raise ValueError("CV text cannot be empty.")

    if len(cv_text) < 100:
        raise ValueError("CV text is too short. Provide a more complete CV.")

    if not keywords:
        raise ValueError("Keywords list cannot be empty.")

    if not all(isinstance(keyword, str) and keyword.strip() for keyword in keywords):
        raise ValueError("Every keyword must be a non-empty string.")


def run_agent(
    cv_text: str,
    keywords: list[str],
    max_steps: int = 5,
) -> AgentState:
    """
    Day 1 agent loop.

    Loop shape:
    - prompt
    - model
    - structured response
    - next step
    - stop on final answer or max steps
    """

    validate_initial_inputs(cv_text=cv_text, keywords=keywords)

    llm = LLMClient()
    state = create_initial_state(
        cv_text=cv_text,
        keywords=keywords,
        max_steps=max_steps,
    )

    console.print(
        Panel(
            f"Started run at {utc_now_iso()}\nRun ID: {state.run_id}",
            title="Job Hunter Agent — Day 1",
            border_style="cyan",
        )
    )

    while state.status == RunStatus.RUNNING:
        if state.steps_taken >= state.max_steps:
            state.status = RunStatus.MAX_STEPS_REACHED
            state.error = f"Stopped after reaching max_steps={state.max_steps}."
            break

        print_step_header(state)

        try:
            raw_response = llm.complete(state.messages)

            console.print(
                Panel(
                    raw_response,
                    title="Raw Model Response",
                    border_style="dim",
                )
            )

            try:
                decision = parse_agent_decision(raw_response)

            except (json.JSONDecodeError, ValidationError) as parse_error:
                console.print(
                    Panel(
                        str(parse_error),
                        title="JSON Parse/Validation Error",
                        border_style="red",
                    )
                )

                state.messages.append(
                    {
                        "role": "assistant",
                        "content": raw_response,
                    }
                )
                state.messages.append(
                    {
                        "role": "user",
                        "content": build_json_repair_prompt(
                            raw_response=raw_response,
                            error=str(parse_error),
                        ),
                    }
                )

                state.steps_taken += 1
                continue

            state.messages.append(
                {
                    "role": "assistant",
                    "content": raw_response,
                }
            )

            print_decision(decision)

            if decision.next_action == "final_answer":
                state.final_answer = decision.final_answer
                state.status = RunStatus.COMPLETED
                break

            if decision.next_action == "continue":
                state.messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Continue. If you now have enough information, return "
                            "next_action as final_answer."
                        ),
                    }
                )
                state.steps_taken += 1
                continue

        except Exception as exc:
            state.status = RunStatus.FAILED
            state.error = str(exc)
            break

    console.rule("[bold cyan]Run Complete")

    if state.status == RunStatus.COMPLETED:
        console.print(
            Panel(
                "Agent completed successfully.",
                title="Status",
                border_style="green",
            )
        )
    elif state.status == RunStatus.MAX_STEPS_REACHED:
        console.print(
            Panel(
                state.error or "Max steps reached.",
                title="Status",
                border_style="yellow",
            )
        )
    else:
        console.print(
            Panel(
                state.error or "Unknown failure.",
                title="Status",
                border_style="red",
            )
        )

    return state