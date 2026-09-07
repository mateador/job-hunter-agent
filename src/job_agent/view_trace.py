import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

console = Console()

EVENT_COLORS = {
    "run_started": "cyan",
    "llm_request": "dim",
    "llm_response": "white",
    "tool_call": "magenta",
    "tool_result": "magenta",
    "guardrail_triggered": "yellow",
    "json_parse_error": "red",
    "context_pruned": "yellow",
    "run_completed": "green",
    "run_failed": "red",
}


def list_runs(logs_dir: str = "logs") -> None:
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        console.print("[yellow]No logs directory found. Run the agent first.[/yellow]")
        return

    files = sorted(logs_path.glob("run_*.jsonl"), reverse=True)

    if not files:
        console.print("[yellow]No audit logs found.[/yellow]")
        return

    table = Table(title="Available Agent Runs")
    table.add_column("#", style="cyan")
    table.add_column("File", style="white")
    table.add_column("Size", style="dim")

    for i, f in enumerate(files, 1):
        size_kb = f.stat().st_size / 1024
        table.add_row(str(i), f.name, f"{size_kb:.1f} KB")

    console.print(table)
    console.print(f"\n[dim]View a run with: python -m job_agent.view_trace --file logs/<filename>[/dim]")


def view_run(file_path: str) -> None:
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        sys.exit(1)

    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    if not events:
        console.print("[yellow]No events found in this log file.[/yellow]")
        return

    run_id = events[0].get("run_id", "unknown")
    console.print(Panel(f"Audit Trail — Run {run_id}", border_style="cyan"))

    for event in events:
        etype = event.get("event_type", "unknown")
        step = event.get("step", "?")
        ts = event.get("timestamp", "")
        data = event.get("data", {})
        color = EVENT_COLORS.get(etype, "white")

        header = f"[{color}]Step {step} | {etype} | {ts}[/{color}]"
        body = json.dumps(data, ensure_ascii=False, indent=2, default=str)

        # Truncate very long bodies for readability
        if len(body) > 3000:
            body = body[:3000] + "\n... (truncated)"

        console.print(header)
        console.print(Panel(body, border_style=color, expand=False))
        console.print()

    # Summary
    total_steps = max(e.get("step", 0) for e in events)
    tool_calls = sum(1 for e in events if e["event_type"] == "tool_call")
    errors = sum(1 for e in events if e["event_type"] in ("json_parse_error", "run_failed"))
    guardrails = sum(1 for e in events if e["event_type"] == "guardrail_triggered")

    summary_table = Table(title="Run Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="white")
    summary_table.add_row("Total Steps", str(total_steps))
    summary_table.add_row("Total Events", str(len(events)))
    summary_table.add_row("Tool Calls", str(tool_calls))
    summary_table.add_row("Guardrails Triggered", str(guardrails))
    summary_table.add_row("Errors", str(errors))
    summary_table.add_row("Log File", str(path))

    console.print(summary_table)


def main() -> None:
    parser = argparse.ArgumentParser(description="View agent audit trails.")
    parser.add_argument("--list", action="store_true", help="List all available runs.")
    parser.add_argument("--file", type=str, help="Path to a specific JSONL log file to view.")

    args = parser.parse_args()

    if args.file:
        view_run(args.file)
    else:
        list_runs()


if __name__ == "__main__":
    main()