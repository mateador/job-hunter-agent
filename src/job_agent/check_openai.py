import os

from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel


console = Console()


def main() -> None:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        console.print(
            Panel(
                "Missing OPENAI_API_KEY.\n\n"
                "Fix:\n"
                "1. Copy .env.example to .env\n"
                "2. Add your OpenAI API key\n"
                "3. Re-run this check",
                title="OpenAI Check Failed",
                border_style="red",
            )
        )
        raise SystemExit(1)

    client = OpenAI(api_key=api_key)

    console.print(
        Panel(
            f"Checking OpenAI access...\nModel: {model}",
            title="OpenAI Check",
            border_style="cyan",
        )
    )

    try:
        # Cheap and fast sanity check.
        client.models.list()
        console.print("[green]✓ API key accepted by OpenAI models.list().[/green]")
    except Exception as exc:
        console.print(
            Panel(
                f"Failed to list models.\n\nError:\n{exc}",
                title="OpenAI Check Failed",
                border_style="red",
            )
        )
        raise SystemExit(1)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": "Reply with ok.",
                }
            ],
            temperature=0,
            max_tokens=5,
        )

        content = response.choices[0].message.content

        console.print(
            Panel(
                f"Chat completion succeeded.\nModel replied: {content!r}",
                title="OpenAI Check Passed",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(
            Panel(
                f"API key works for models.list, but chat completion failed.\n\nError:\n{exc}",
                title="OpenAI Check Failed",
                border_style="red",
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()