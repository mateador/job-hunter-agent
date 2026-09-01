import os

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI


class LLMClient:
    """
    Centralized OpenAI wrapper.

    Field note:
    Keep all model calls behind this class. Later, when you add retries,
    cost tracking, timeouts, and model switching, you only change this file.
    """

    def __init__(self) -> None:
        load_dotenv()

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing OPENAI_API_KEY. Copy .env.example to .env and set your key."
            )

        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = OpenAI(api_key=api_key)

    def complete(self, messages: list[dict]) -> str:
        """
        Call OpenAI and return the text content.

        We try JSON mode first because Day 1 relies on structured output.
        If the selected model does not support response_format, we fall back.
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
        except BadRequestError as exc:
            if "response_format" in str(exc).lower():
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=1500,
                )
            else:
                raise

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError("LLM returned an empty response.")

        return content