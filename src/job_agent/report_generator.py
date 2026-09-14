"""
Day 13: Markdown report generator with partial completion support.
"""
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from rich.console import Console

console = Console()


def generate_report(result: Dict[str, Any]) -> str:
    """
    Generate a Markdown report from agent results.

    Args:
        result: Dictionary from AgentRunner.run()

    Returns:
        Path to the generated report file
    """
    query = result["query"]
    jobs_found = result["jobs_found"]
    applications = result["applications"]
    failed_jobs = result.get("failed_jobs", [])
    status = result.get("status", "unknown")
    checkpoint_file = result["checkpoint_file"]

    # Create reports directory
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"report_{timestamp}.md"

    # Build report
    lines = []
    lines.append(f"# Job Search Report: {query}")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Status:** {status.upper()}")
    lines.append(f"**Jobs Found:** {len(jobs_found)}")
    lines.append(f"**Applications Generated:** {len(applications)}")
    if failed_jobs:
        lines.append(f"**Failed Jobs:** {len(failed_jobs)}")
    lines.append(f"**Checkpoint File:** `{checkpoint_file}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Applications section
    if applications:
        lines.append("## Generated Applications")
        lines.append("")
        for app in applications:
            job = next((j for j in jobs_found if j.id == app.job_id), None)
            if job:
                lines.append(f"### {job.title} at {job.company}")
                lines.append("")
                lines.append(f"**Location:** {job.location or 'Not specified'}")
                lines.append(f"**Job ID:** {job.id}")
                if job.url:
                    lines.append(f"**URL:** {job.url}")
                lines.append("")
                lines.append("#### Cover Letter")
                lines.append("")
                lines.append(app.cover_letter)
                lines.append("")
                lines.append("#### Tailored CV Bullets")
                lines.append("")
                for bullet in app.cv_bullets:
                    lines.append(f"- {bullet}")
                lines.append("")
                lines.append("---")
                lines.append("")

    # Failed jobs section
    if failed_jobs:
        lines.append("## Failed Jobs")
        lines.append("")
        lines.append("The following jobs could not be processed:")
        lines.append("")
        for fj in failed_jobs:
            lines.append(f"### {fj.job_title}")
            lines.append("")
            lines.append(f"- **Job ID:** {fj.job_id}")
            lines.append(f"- **Error Category:** {fj.error_category or 'UNKNOWN'}")
            lines.append(f"- **Error:** {fj.error}")
            lines.append("")
        lines.append("---")
        lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    if status == "completed":
        lines.append("✅ All jobs processed successfully.")
    elif status == "partial":
        lines.append(f"⚠️  Partial completion: {len(applications)}/{len(jobs_found)} jobs processed.")
        lines.append(f"   {len(failed_jobs)} job(s) failed. Check the Failed Jobs section above.")
    else:
        lines.append("❌ No jobs were successfully processed.")
    lines.append("")

    # Write report
    with open(report_file, "w") as f:
        f.write("\n".join(lines))

    console.print(f"[bold green]Report generated: {report_file}[/bold green]")
    return str(report_file)