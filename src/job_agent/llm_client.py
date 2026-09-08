import os
import logging
from openai import OpenAI
from .audit_logger import AuditLogger
from .retry import execute_with_retry
from .config import LLM_TIMEOUT

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, audit_logger: AuditLogger, model: str = "gpt-4o-mini"):
        self.audit_logger = audit_logger
        self.model = model
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set.")
        
        # Day 10: Enforce timeout on all LLM calls
        self.client = OpenAI(api_key=api_key, timeout=LLM_TIMEOUT)

    def chat(self, messages: list, **kwargs) -> str:
        def _call(**call_kwargs):
            msgs = call_kwargs.pop("messages")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=msgs,
                **call_kwargs
            )
            return response.choices[0].message.content

        def _modify_llm_kwargs(kwargs_dict, attempt):
            # If context overflow, truncate messages (keep system prompt + last half)
            msgs = kwargs_dict.get("messages", [])
            if len(msgs) > 2:
                kwargs_dict["messages"] = [msgs[0]] + msgs[-(len(msgs)//2):]
            return kwargs_dict

        call_kwargs = {"messages": messages, **kwargs}
        
        return execute_with_retry(
            func=_call,
            args=(),
            kwargs=call_kwargs,
            audit_logger=self.audit_logger,
            tool_name="llm_chat",
            modify_kwargs_fn=_modify_llm_kwargs
        )