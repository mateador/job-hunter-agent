"""
Day 15: CLI entrypoint with CV + keywords support restored.
Supports both query-based and CV-based workflows.
"""
import argparse
import json
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.logging import RichHandler

from .agent_runner import AgentRunner, InvalidQueryError, ResumeError
from .audit_logger import AuditLogger
from .checkpoint import CheckpointManager
from .report_generator import generate_report

# Add these lines after the existing imports
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_file = Path(__file__).parent.parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    
console = Console()


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)]
    )


def load_cv(cv_path: str) -> str:
    """Load CV text from a markdown file."""
    path = Path(cv_path)
    if not path.exists():
        raise FileNotFoundError(f"CV file not found: {cv_path}")
    if not path.is_file():
        raise ValueError(f"CV path is not a file: {cv_path}")
    return path.read_text(encoding="utf-8")


def load_keywords(keywords_path: str) -> list[str]:
    """
    Load keywords from a JSON file.
    Supports two formats:
      - Plain list: ["query1", "query2"]
      - Object with queries key: {"queries": ["query1", "query2"]}
    """
    path = Path(keywords_path)
    if not path.exists():
        raise FileNotFoundError(f"Keywords file not found: {keywords_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        queries = data
    elif isinstance(data, dict) and "queries" in data:
        queries = data["queries"]
    else:
        raise ValueError(
            f"Invalid keywords format in {keywords_path}. "
            "Expected a JSON list or an object with a 'queries' key."
        )

    if not queries:
        raise ValueError(f"Keywords file {keywords_path} contains no queries")

    return [str(q).strip() for q in queries if str(q).strip()]


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


def main():
    parser = argparse.ArgumentParser(
        description="AI Job Hunting Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Query-based (simple)
  python -m src.job_agent.main "python engineer london" --max-jobs 5

  # CV-based (tailored to your experience)
  python -m src.job_agent.main --cv private/alexandre_cv.md \\
      --keywords examples/keywords.json --max-jobs 5

  # Resume an interrupted run
  python -m src.job_agent.main --resume --run-id <RUN_ID>
        """
    )

    # Query input (mutually exclusive modes)
    parser.add_argument("query", nargs="?", help="Job search query (optional if using --keywords)")
    parser.add_argument("--cv", help="Path to CV markdown file")
    parser.add_argument("--keywords", help="Path to JSON file with keyword queries")

    # Run configuration
    parser.add_argument("--max-jobs", type=int, default=10, help="Maximum jobs to process per query")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model to use")
    parser.add_argument("--retry-model", help="Model for grounding retries (default: same as --model)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    # Resume configuration
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

    # ── Validate query input ──
    is_resume = args.resume or args.resume_from is not None

    if not is_resume:
        if args.query and args.keywords:
            parser.error("Cannot specify both a positional query and --keywords. Use one or the other.")
        if not args.query and not args.keywords:
            parser.error("Either a positional query or --keywords is required (unless using --resume or --list-interrupted)")
        if args.query is not None and not args.query.strip():
            parser.error("The search query is empty or whitespace-only.")

    # ── Load CV if provided ──
    cv_text = None
    if args.cv:
        try:
            cv_text = load_cv(args.cv)
            console.print(f"[dim]Loaded CV from {args.cv} ({len(cv_text)} chars)[/dim]")
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[bold red]Error loading CV: {e}[/bold red]")
            sys.exit(1)

    # ── Build list of queries to run ──
    if is_resume:
        queries = [args.query or ""]  # Resume needs a query for validation
    elif args.keywords:
        try:
            queries = load_keywords(args.keywords)
            console.print(f"[dim]Loaded {len(queries)} queries from {args.keywords}[/dim]")
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
            console.print(f"[bold red]Error loading keywords: {e}[/bold red]")
            sys.exit(1)
    else:
        queries = [args.query]

    # ── Process each query ──
    results = []
    for idx, query in enumerate(queries):
        if len(queries) > 1:
            console.print(f"\n[bold cyan]━━━ Query {idx + 1}/{len(queries)}: {query} ━━━[/bold cyan]")

        # For multi-query runs, generate a unique run-id per query
        if len(queries) > 1 and not args.run_id:
            run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx + 1:02d}"
        else:
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
            retry_model=args.retry_model,
            max_jobs=args.max_jobs,
            cv_text=cv_text,
        )

        console.print(f"[bold green]Starting agent run: {run_id}[/bold green]")

        try:
            result = agent.run(
                query=query,
                resume=is_resume,
                resume_from=args.resume_from
            )

            report_file = generate_report(result)

            # Display summary
            status = result["status"]
            apps_count = len(result["applications"])
            failed_count = len(result.get("failed_jobs", []))
            total_jobs = len(result["jobs_found"])

            console.print("")
            if status == "completed":
                console.print(f"[bold green]✅ Completed: {apps_count}/{total_jobs} jobs processed[/bold green]")
            elif status == "partial":
                console.print(f"[bold yellow]⚠️  Partial: {apps_count}/{total_jobs} jobs processed, {failed_count} failed[/bold yellow]")
            else:
                console.print(f"[bold red]❌ Failed: 0/{total_jobs} jobs processed[/bold red]")

            usage = result.get("usage") or {}
            if usage.get("calls"):
                unpriced = " (some calls unpriced)" if usage.get("unpriced_calls") else ""
                console.print(f"[dim]LLM usage: {usage['calls']} calls, {usage['total_tokens']:,} tokens, "
                              f"estimated cost ${usage['cost_usd']:.4f}{unpriced} at list price[/dim]")
            flagged = sum(1 for a in result["applications"] if a.warnings)
            if flagged:
                console.print(f"[bold yellow]⚠️  {flagged} application(s) contain figures not found in your CV "
                              f"or the posting: review before sending[/bold yellow]")

            console.print(f"[bold]Report: {report_file}[/bold]")
            console.print(f"[bold]Checkpoint: {result['checkpoint_file']}[/bold]")

            results.append(result)

        except ResumeError as e:
            console.print(f"[bold red]Resume error: {e}[/bold red]")
            sys.exit(1)

        except InvalidQueryError as e:
            console.print(f"[bold red]Invalid query: {e}[/bold red]")
            sys.exit(1)

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Interrupted by user. State saved to checkpoint.[/bold yellow]")
            console.print(
                f"[bold]Resume with:[/bold] "
                f"python -m src.job_agent.main '{query}' --resume --run-id {run_id}"
            )
            sys.exit(0)

        except Exception as e:
            console.print(f"[bold red]Error: {e}[/bold red]")
            console.print(
                f"[bold]Resume with:[/bold] "
                f"python -m src.job_agent.main '{query}' --resume --run-id {run_id}"
            )
            raise

    # ── Final summary for multi-query runs ──
    if len(results) > 1:
        console.print("\n[bold cyan]━━━ Final Summary ━━━[/bold cyan]")
        total_apps = sum(len(r["applications"]) for r in results)
        total_failed = sum(len(r.get("failed_jobs", [])) for r in results)
        console.print(f"[bold]Total applications generated: {total_apps}[/bold]")
        console.print(f"[bold]Total failed jobs: {total_failed}[/bold]")


if __name__ == "__main__":
    main()