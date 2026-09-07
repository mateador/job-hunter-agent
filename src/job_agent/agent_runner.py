import json
from datetime import datetime, timezone
from uuid import uuid4

import tiktoken
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from job_agent.audit_logger import AuditLogger
from job_agent.llm_client import LLMClient
from job_agent.models import AgentDecision, AgentState, RunStatus
from job_agent.prompts import (
    SYSTEM_PROMPT,
    build_initial_user_prompt,
    build_json_repair_prompt,
    build_tool_result_prompt,
)
from job_agent.tools import execute_tool

console = Console()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_json_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"): lines = lines[1:]
        if lines and lines[-1].strip() == "```": lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def count_tokens(messages: list[dict], model: str = "gpt-4o-mini") -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = 0
    for message in messages:
        num_tokens += 4
        for key, value in message.items():
            num_tokens += len(encoding.encode(str(value)))
    return num_tokens


def prune_context_if_needed(state: AgentState, audit: AuditLogger, max_tokens: int = 30000) -> None:
    current_tokens = count_tokens(state.messages)
    if current_tokens < max_tokens or len(state.messages) <= 6:
        return

    console.print(f"[yellow]⚠️ Context Pruner: {current_tokens} tokens detected. Compressing history...[/yellow]")

    system_msg = state.messages[0]
    initial_prompt = state.messages[1]
    recent_msgs = state.messages[-4:]
    middle_msgs = state.messages[2:-4]
    summary_text = (
        f"[SYSTEM NOTE: The agent previously executed {len(middle_msgs) // 2} tool calls. "
        "The results have been compressed to save context space. "
        "Rely on the most recent tool results and your initial instructions for your final answer.]"
    )

    state.messages = [system_msg, initial_prompt, {"role": "system", "content": summary_text}, *recent_msgs]

    new_tokens = count_tokens(state.messages)
    audit.log("context_pruned", {
        "tokens_before": current_tokens,
        "tokens_after": new_tokens,
        "messages_removed": len(middle_msgs),
    })


def create_initial_state(cv_text: str, keywords: list[str], max_steps: int = 8) -> AgentState:
    return AgentState(
        run_id=str(uuid4()),
        cv_text=cv_text,
        keywords=keywords,
        max_steps=max_steps,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_initial_user_prompt(cv_text=cv_text, keywords=keywords)},
        ],
    )


def parse_agent_decision(raw_response: str) -> AgentDecision:
    text = normalize_json_text(raw_response)
    data = json.loads(text)

    tool_args = data.get("tool_arguments")
    if isinstance(tool_args, list) and len(tool_args) == 1 and isinstance(tool_args[0], dict):
        data["tool_arguments"] = tool_args[0]

    return AgentDecision.model_validate(data)


def print_step_header(state: AgentState) -> None:
    console.rule(f"[bold cyan]Run {state.run_id} | Step {state.steps_taken + 1}/{state.max_steps}")


def print_decision(decision: AgentDecision) -> None:
    table = Table(title="Agent Decision")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_row("Reasoning Summary", decision.reasoning_summary)
    table.add_row("Next Action", decision.next_action)
    table.add_row("Message", decision.message_to_user)
    if decision.tool_name:
        table.add_row("Tool", decision.tool_name)
    if decision.tool_arguments:
        table.add_row("Tool Arguments", json.dumps(decision.tool_arguments, ensure_ascii=False, indent=2))
    console.print(table)
    if decision.final_answer:
        console.print(Panel(decision.final_answer.model_dump_json(indent=2), title="Final Answer", border_style="green"))


def validate_initial_inputs(cv_text: str, keywords: list[str]) -> None:
    if not cv_text or not cv_text.strip(): raise ValueError("CV text cannot be empty.")
    if len(cv_text) < 100: raise ValueError("CV text is too short.")
    if not keywords: raise ValueError("Keywords list cannot be empty.")


def run_agent(cv_text: str, keywords: list[str], max_steps: int = 8) -> AgentState:
    validate_initial_inputs(cv_text=cv_text, keywords=keywords)

    llm = LLMClient()
    state = create_initial_state(cv_text=cv_text, keywords=keywords, max_steps=max_steps)
    audit = AuditLogger(run_id=state.run_id)

    # --- AUDIT: Run Started ---
    audit.log("run_started", {
        "cv_length_chars": len(cv_text),
        "keywords": keywords,
        "max_steps": max_steps,
        "model": llm.model,
    })

    console.print(Panel(
        f"Started run at {utc_now_iso()}\nRun ID: {state.run_id}\nAudit Log: {audit.file_path}",
        title="Job Hunter Agent — Day 5",
        border_style="cyan",
    ))

    while state.status == RunStatus.RUNNING:
        if state.steps_taken >= state.max_steps:
            state.status = RunStatus.MAX_STEPS_REACHED
            state.error = f"Stopped after reaching max_steps={state.max_steps}."
            audit.log("run_failed", {"reason": "max_steps_reached", "steps_taken": state.steps_taken})
            break

        print_step_header(state)
        audit.increment_step()

        try:
            prune_context_if_needed(state, audit)

            # --- AUDIT: LLM Request ---
            token_estimate = count_tokens(state.messages)
            audit.log("llm_request", {
                "message_count": len(state.messages),
                "estimated_tokens": token_estimate,
            })

            raw_response = llm.complete(state.messages)
            console.print(Panel(raw_response, title="Raw Model Response", border_style="dim"))

            try:
                decision = parse_agent_decision(raw_response)
            except (json.JSONDecodeError, ValidationError) as parse_error:
                console.print(Panel(str(parse_error), title="JSON Parse Error", border_style="red"))

                # --- AUDIT: Parse Error ---
                audit.log("json_parse_error", {
                    "error": str(parse_error),
                    "raw_response": raw_response[:2000],
                })

                state.messages.append({"role": "assistant", "content": raw_response})
                state.messages.append({"role": "user", "content": build_json_repair_prompt(raw_response, str(parse_error))})
                state.steps_taken += 1
                continue

            # --- AUDIT: LLM Response ---
            audit.log("llm_response", {
                "next_action": decision.next_action,
                "tool_name": decision.tool_name,
                "reasoning_summary": decision.reasoning_summary,
            })

            state.messages.append({"role": "assistant", "content": raw_response})
            print_decision(decision)

            if decision.next_action == "tool_call":

                # --- DAY 3 GUARDRAIL: Budget Limit ---
                current_research_count = state.tool_call_counts.get("research_company", 0)
                if decision.tool_name == "research_company" and current_research_count >= 2:
                    console.print("[yellow]⚠️ Guardrail: Max company research limit (2) reached. Forcing final answer.[/yellow]")

                    audit.log("guardrail_triggered", {
                        "guardrail": "max_research_budget",
                        "action": "forced_final_answer",
                        "research_count": current_research_count,
                    })

                    state.messages.append({
                        "role": "user",
                        "content": "SYSTEM GUARDRAIL: You have reached the maximum limit of company research calls (2). You must now immediately return next_action as 'final_answer' using the information you already have."
                    })
                    state.steps_taken += 1
                    continue

                console.print(f"[magenta]Executing tool: {decision.tool_name}...[/magenta]")

                # --- AUDIT: Tool Call ---
                audit.log("tool_call", {
                    "tool_name": decision.tool_name,
                    "tool_arguments": decision.tool_arguments,
                })

                tool_result = execute_tool(
                    tool_name=decision.tool_name,
                    tool_arguments=decision.tool_arguments or {},
                )

                state.tool_call_counts[decision.tool_name] = (
                    current_research_count + 1 if decision.tool_name == "research_company"
                    else state.tool_call_counts.get(decision.tool_name, 0) + 1
                )

                # --- AUDIT: Tool Result ---
                audit.log("tool_result", {
                    "tool_name": decision.tool_name,
                    "status": tool_result.get("status", "unknown"),
                    "result_summary": str(tool_result)[:1000],
                })

                tool_result_text = json.dumps(tool_result, ensure_ascii=False, indent=2)
                console.print(Panel(tool_result_text[:2000] + ("..." if len(tool_result_text) > 2000 else ""), title=f"Tool Result: {decision.tool_name}", border_style="magenta"))

                state.messages.append({
                    "role": "user",
                    "content": build_tool_result_prompt(
                        tool_name=decision.tool_name,
                        tool_arguments=decision.tool_arguments or {},
                        tool_result=tool_result,
                    ),
                })
                state.steps_taken += 1
                continue

            if decision.next_action == "final_answer":
                state.final_answer = decision.final_answer
                state.status = RunStatus.COMPLETED

                # --- AUDIT: Run Completed ---
                audit.log("run_completed", {
                    "steps_taken": state.steps_taken,
                    "jobs_reviewed": decision.final_answer.jobs_reviewed if decision.final_answer else 0,
                    "selected_companies": [j.company for j in decision.final_answer.selected_jobs] if decision.final_answer else [],
                })
                break

        except Exception as exc:
            state.status = RunStatus.FAILED
            state.error = str(exc)
            audit.log("run_failed", {"error": str(exc), "steps_taken": state.steps_taken})
            break

    console.rule("[bold cyan]Run Complete")
    if state.status == RunStatus.COMPLETED:
        console.print(Panel("Agent completed successfully.", title="Status", border_style="green"))
    elif state.status == RunStatus.MAX_STEPS_REACHED:
        console.print(Panel(state.error or "Max steps reached.", title="Status", border_style="yellow"))
    else:
        console.print(Panel(state.error or "Unknown failure.", title="Status", border_style="red"))

    console.print(f"\n[dim]Audit trail saved to: {audit.file_path}[/dim]")
    console.print(f"[dim]View it with: python -m job_agent.view_trace --file {audit.file_path}[/dim]")

    return state