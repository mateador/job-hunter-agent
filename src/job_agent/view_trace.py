"""
Day 14: Audit trail viewer with recovery narrative mode.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()


def load_trace(trace_file: Path) -> list[dict]:
    """Load all events from a trace file."""
    events = []
    with open(trace_file, "r") as f:
        for line in f:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def show_trace(trace_file: Path):
    """Display trace events in a table."""
    events = load_trace(trace_file)

    table = Table(title=f"Audit Trail: {trace_file.name}")
    table.add_column("Timestamp", style="dim", width=19)
    table.add_column("Event Type", style="cyan")
    table.add_column("Details", style="white")

    for event in events:
        timestamp = event.get("timestamp", "")[:19]
        event_type = event.get("event_type", "unknown")

        # Build details string
        details_parts = []
        for key, value in event.items():
            if key not in ("timestamp", "event_type"):
                if isinstance(value, dict):
                    details_parts.append(f"{key}={len(value)} items")
                elif isinstance(value, list):
                    details_parts.append(f"{key}={len(value)} items")
                else:
                    details_parts.append(f"{key}={value}")

        details = ", ".join(details_parts)
        table.add_row(timestamp, event_type, details[:80])

    console.print(table)


def show_narrative(trace_file: Path, run_id: str):
    """
    Display a human-readable narrative of the agent run,
    highlighting recovery events.
    """
    events = load_trace(trace_file)

    console.print(Panel(
        f"[bold]Recovery Narrative for Run: {run_id}[/bold]\n"
        f"Total events: {len(events)}",
        title="Audit Trail Analysis"
    ))
    console.print()

    # Group events by phase
    resume_events = [e for e in events if e.get("event_type") == "resume"]
    job_processed = [e for e in events if e.get("event_type") == "job_processed"]
    job_failed = [e for e in events if e.get("event_type") == "job_failed"]
    attempts = [e for e in events if e.get("event_type") == "attempt"]

    # Show recovery events
    if resume_events:
        console.print("[bold green]🔄 RECOVERY EVENTS[/bold green]")
        for event in resume_events:
            checkpoint_id = event.get("checkpoint_id", "?")
            already_processed = event.get("jobs_already_processed", 0)
            remaining = event.get("jobs_remaining", 0)
            console.print(
                f"  • Resumed from checkpoint {checkpoint_id}\n"
                f"    - {already_processed} jobs already processed\n"
                f"    - {remaining} jobs remaining"
            )
        console.print()

    # Show job processing
    if job_processed:
        console.print("[bold cyan]✅ SUCCESSFULLY PROCESSED JOBS[/bold cyan]")
        for event in job_processed:
            job_id = event.get("job_id", "?")
            progress = event.get("progress", "?")
            console.print(f"  • {job_id} ({progress})")
        console.print()

    # Show failures
    if job_failed:
        console.print("[bold red]❌ FAILED JOBS[/bold red]")
        for event in job_failed:
            job_id = event.get("job_id", "?")
            error = event.get("error", "Unknown error")
            category = event.get("error_category", "UNKNOWN")
            console.print(f"  • {job_id}: {error[:60]}... [{category}]")
        console.print()

    # Show retry activity
    retry_attempts = [a for a in attempts if a.get("attempt_number", 1) > 1]
    if retry_attempts:
        console.print("[bold yellow]🔁 RETRY ACTIVITY[/bold yellow]")
        for event in retry_attempts:
            tool = event.get("tool", "?")
            attempt = event.get("attempt_number", "?")
            status = event.get("status", "?")
            console.print(f"  • {tool}: attempt {attempt} ({status})")
        console.print()

    # Summary
    console.print(Panel(
        f"[bold]Summary[/bold]\n"
        f"  Jobs processed: {len(job_processed)}\n"
        f"  Jobs failed: {len(job_failed)}\n"
        f"  Recovery events: {len(resume_events)}\n"
        f"  Retry attempts: {len(retry_attempts)}",
        title="Run Summary"
    ))


def find_trace_for_run(run_id: str, trace_dir: str = "traces") -> Path:
    """Find the trace file for a specific run."""
    trace_path = Path(trace_dir)
    if not trace_path.exists():
        raise FileNotFoundError(f"Trace directory not found: {trace_dir}")

    # Look for trace files (we don't embed run_id in trace files yet,
    # so we'll use the most recent one or let user specify)
    trace_files = sorted(trace_path.glob("trace_*.jsonl"))
    if not trace_files:
        raise FileNotFoundError(f"No trace files found in {trace_dir}")

    # Return the most recent trace file
    return trace_files[-1]


def main():
    parser = argparse.ArgumentParser(description="View audit trail")
    parser.add_argument("--run-id", help="Run ID to display")
    parser.add_argument("--trace-file", help="Specific trace file to view")
    parser.add_argument("--narrative", action="store_true",
                        help="Show human-readable narrative instead of raw events")
    parser.add_argument("--trace-dir", default="traces",
                        help="Directory containing trace files")

    args = parser.parse_args()

    if args.trace_file:
        trace_file = Path(args.trace_file)
    elif args.run_id:
        try:
            trace_file = find_trace_for_run(args.run_id, args.trace_dir)
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            return
    else:
        # Use most recent trace file
        trace_path = Path(args.trace_dir)
        if not trace_path.exists():
            console.print(f"[red]Trace directory not found: {args.trace_dir}[/red]")
            return
        trace_files = sorted(trace_path.glob("trace_*.jsonl"))
        if not trace_files:
            console.print("[red]No trace files found[/red]")
            return
        trace_file = trace_files[-1]

    if args.narrative:
        show_narrative(trace_file, args.run_id or "unknown")
    else:
        show_trace(trace_file)


if __name__ == "__main__":
    main()