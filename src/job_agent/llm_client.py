"""
Day 15: OpenAI wrapper with full traceback logging for underlying causes.
"""
import os
import time
import logging
import traceback
from contextlib import contextmanager
from typing import Optional
from openai import OpenAI
from .audit_logger import AuditLogger
from .retry import execute_with_retry
from .config import get_llm_timeout
from .routing import ModelRouter, supports_reasoning_effort
from .usage import LLMUsage, UsageTracker

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, audit_logger: AuditLogger, model: str = "gpt-4o-mini",
                 router: Optional[ModelRouter] = None, reasoning_effort: Optional[str] = None):
        self.audit_logger = audit_logger
        self.model = model
        self.router = router or ModelRouter(model)
        self.reasoning_effort = reasoning_effort
        self.usage = UsageTracker()
        self._tags: dict = {}
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set.")
        
        self.client = OpenAI(api_key=api_key, timeout=get_llm_timeout(), max_retries=0)

    @contextmanager
    def tagged(self, **tags):
        """Label the calls made inside the block, e.g. tagged(job_id=..., purpose="application").

        The purpose also selects the model through the router.
        """
        previous = self._tags
        self._tags = {**previous, **tags}
        try:
            yield
        finally:
            self._tags = previous

    def _record_usage(self, response, model: str, latency_s: float) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        details = getattr(usage, "prompt_tokens_details", None)
        completion_details = getattr(usage, "completion_tokens_details", None)
        record = LLMUsage(
            model=getattr(response, "model", None) or model,
            purpose=self._tags.get("purpose", "unspecified"),
            job_id=self._tags.get("job_id"),
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cached_tokens=(getattr(details, "cached_tokens", 0) or 0) if details else 0,
            reasoning_tokens=(getattr(completion_details, "reasoning_tokens", 0) or 0) if completion_details else 0,
            latency_s=latency_s,
        )
        self.usage.record(record)
        self.audit_logger.log_event(
            event_type="llm_usage",
            model=record.model,
            purpose=record.purpose,
            job_id=record.job_id,
            prompt_tokens=record.prompt_tokens,
            completion_tokens=record.completion_tokens,
            cached_tokens=record.cached_tokens,
            reasoning_tokens=record.reasoning_tokens,
            reasoning_effort=self._effort_for(model),
            cost_usd=record.cost_usd,
            latency_s=round(latency_s, 3),
        )

    def _effort_for(self, model: str) -> Optional[str]:
        """The reasoning effort actually sent for this model (None if unset or unsupported)."""
        return self.reasoning_effort if self.reasoning_effort and supports_reasoning_effort(model) else None

    def chat(self, messages: list, **kwargs) -> str:
        model = self.router.model_for(self._tags.get("purpose"))
        effort = self._effort_for(model)
        if effort:
            kwargs["reasoning_effort"] = effort

        def _call(**call_kwargs):
            msgs = call_kwargs.pop("messages")
            started = time.perf_counter()
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    **call_kwargs
                )
                self._record_usage(response, model, time.perf_counter() - started)
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"LLM Call Failed. Type: {type(e).__name__}, Message: {e}")
                if hasattr(e, '__cause__') and e.__cause__:
                    # Print the FULL traceback of the underlying error
                    tb = "".join(traceback.format_exception(type(e.__cause__), e.__cause__, e.__cause__.__traceback__))
                    logger.error(f"Underlying Cause Full Traceback:\n{tb}")
                raise

        def _modify_llm_kwargs(kwargs_dict, attempt):
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