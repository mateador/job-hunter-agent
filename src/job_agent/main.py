"""
Day 11: CLI entrypoint with resume capability.
"""
import argparse
import logging
from datetime import datetime

from rich.console import Console
from rich.logging import RichHandler

from .agent_runner import AgentRunner
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

def main():
    parser = argparse.ArgumentParser(description="AI Job Hunting Agent")
    parser.add_argument("query", help="Job search query")
    parser.add_argument("--max-jobs", type=int, default=10, help="Maximum jobs to process")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model to use")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--run-id", help="Run ID for checkpoint (auto-generated if not provided)")
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    # Initialize managers
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    audit_logger = AuditLogger()
    checkpoint_manager = CheckpointManager(run_id=run_id)
    
    # Initialize and run agent
    agent = AgentRunner(
        audit_logger=audit_logger,
        checkpoint_manager=checkpoint_manager,
        model=args.model,
        max_jobs=args.max_jobs
    )
    
    console.print(f"[bold green]Starting agent run: {run_id}[/bold green]")
    
    try:
        result = agent.run(query=args.query, resume=args.resume)
        
        # Generate report
        report_file = generate_report(result)
        console.print(f"[bold green]Report generated: {report_file}[/bold green]")
        console.print(f"[bold]Checkpoint file: {result['checkpoint_file']}[/bold]")
        
    except KeyboardInterrupt:
        console.print("[bold yellow]Interrupted by user. State saved to checkpoint.[/bold yellow]")
        console.print(f"[bold]Resume with: python -m src.job_agent.main '{args.query}' --resume --run-id {run_id}[/bold]")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        console.print(f"[bold]Resume with: python -m src.job_agent.main '{args.query}' --resume --run-id {run_id}[/bold]")
        raise

if __name__ == "__main__":
    main()