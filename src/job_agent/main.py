import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from src.job_agent.agent_runner import run_agent


console = Console()


def load_cv(path: str) -> str:
    cv_path = Path(path)

    if not cv_path.exists():
        raise FileNotFoundError(f"CV file not found: {path}")

    return cv_path.read_text(encoding="utf-8")


def load_keywords(path: str) -> list[str]:
    keywords_path = Path(path)

    if not keywords_path.exists():
        raise FileNotFoundError(f"Keywords file not found: {path}")

    data = json.loads(keywords_path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise ValueError("Keywords file must contain a JSON list of strings.")

    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Day 1 Job Hunter Agent runner."
    )

    parser.add_argument(
        "--cv",
        required=True,
        help="Path to a Markdown or text CV file.",
    )

    parser.add_argument(
        "--keywords",
        required=True,
        help="Path to a JSON file containing a list of job search keywords.",
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=5,
        help="Maximum number of agent loop steps before stopping.",
    )

    args = parser.parse_args()

    try:
        cv_text = load_cv(args.cv)
        keywords = load_keywords(args.keywords)

        final_state = run_agent(
            cv_text=cv_text,
            keywords=keywords,
            max_steps=args.max_steps,
        )

        if final_state.final_answer:
            console.print(
                Panel(
                    final_state.final_answer.model_dump_json(indent=2),
                    title="Day 1 Final Output",
                    border_style="green",
                )
            )

    except Exception as exc:
        console.print(
            Panel(
                str(exc),
                title="Fatal Error",
                border_style="red",
            )
        )
        raise


if __name__ == "__main__":
    main()