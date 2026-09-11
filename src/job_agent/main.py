"""
Day 12: CLI entrypoint with robust resume capability.
"""
import argparse
import logging
import sys
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.logging import RichHandler

from .agent_runner import AgentRunner, ResumeError
from .audit_logger import AuditLogger
from .checkpoint import CheckpointManager
from .report_generator import generate_report

console = Console()


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)]
    )


def show_interrupted_runs(checkpoint_dir: str = "checkpoints"):
    """Display a table of interrupted runs that can be resumed."""
    manager = CheckpointManager(checkpoint_dir=checkpoint_dir, run_id="scan")
    interrupted = manager.find_interrupted_runs()

    if not interrupted:
        console.print("[dim]No interrupted runs found.[/dim]")
        return

    table = Table(title="Interrupted Runs (available for resume)")
    table.add_column("Run ID", style="cyan")
    table.add_column("Query", style="green")
    table.add_column("Progress", style="yellow")
    table.add_column("Status", style="red")
    table.add_column("Last Checkpoint", style="magenta")
    table.add_column("Timestamp", style="dim")

    for run in interrupted:
        table.add_row(
            run["run_id"],
            run["query"][:40],
            run["progress"],
            run["status"],
            str(run["last_checkpoint_id"]),
            run["timestamp"][:19]
        )

    console.print(table)
    console.print(
        "\n[bold]Resume with:[/bold] "
        "python -m src.job_agent.main '<query>' --resume --run-id <RUN_ID>"
    )
    console.print(
        "[bold]Or from specific checkpoint:[/bold] "
        "python -m src.job_agent.main '<query>' --resume-from <ID> --run-id <RUN_ID>"
    )


def main():
    parser = argparse.ArgumentParser(description="AI Job Hunting Agent")
    parser.add_argument("query", nargs="?", help="Job search query")
    parser.add_argument("--max-jobs", type=int, default=10, help="Maximum jobs to process")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model to use")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--resume-from", type=int, metavar="ID",
                        help="Resume from a specific checkpoint ID")
    parser.add_argument("--run-id", help="Run ID for checkpoint (auto-generated if not provided)")
    parser.add_argument("--list-interrupted", action="store_true",
                        help="List interrupted runs and exit")

    args = parser.parse_args()
    setup_logging(args.verbose)

    # ── List interrupted runs mode ──
    if args.list_interrupted:
        show_interrupted_runs()
        return

    # ── Query is required unless listing ──
    if not args.query:
        parser.error("query is required (unless using --list-interrupted)")

    # ── Initialize managers ──
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    audit_logger = AuditLogger()
    checkpoint_manager = CheckpointManager(run_id=run_id)

    # ── Auto-detect interrupted runs if --resume without --run-id ──
    if args.resume and not args.run_id:
        scan_manager = CheckpointManager(run_id="scan")
        interrupted = scan_manager.find_interrupted_runs()
        if len(interrupted) == 1:
            auto_run = interrupted[0]
            console.print(
                f"[yellow]Auto-detected interrupted run: {auto_run['run_id']} "
                f"({auto_run['progress']})[/yellow]"
            )
            checkpoint_manager = CheckpointManager(run_id=auto_run["run_id"])
            run_id = auto_run["run_id"]
        elif len(interrupted) > 1:
            console.print("[yellow]Multiple interrupted runs found:[/yellow]")
            show_interrupted_runs()
            console.print("[bold red]Please specify --run-id to resume a specific run.[/bold red]")
            sys.exit(1)

    # ── Initialize and run agent ──
    agent = AgentRunner(
        audit_logger=audit_logger,
        checkpoint_manager=checkpoint_manager,
        model=args.model,
        max_jobs=args.max_jobs
    )

    console.print(f"[bold green]Starting agent run: {run_id}[/bold green]")

    try:
        result = agent.run(
            query=args.query,
            resume=args.resume or args.resume_from is not None,
            resume_from=args.resume_from
        )

        report_file = generate_report(result)
        console.print(f"[bold green]Report generated: {report_file}[/bold green]")
        console.print(f"[bold]Checkpoint file: {result['checkpoint_file']}[/bold]")

    except ResumeError as e:
        console.print(f"[bold red]Resume error: {e}[/bold red]")
        sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n[bold yellow]Interrupted by user. State saved to checkpoint.[/bold yellow]")
        console.print(
            f"[bold]Resume with:[/bold] "
            f"python -m src.job_agent.main '{args.query}' --resume --run-id {run_id}"
        )

    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        console.print(
            f"[bold]Resume with:[/bold] "
            f"python -m src.job_agent.main '{args.query}' --resume --run-id {run_id}"
        )
        raise


if __name__ == "__main__":
    main()