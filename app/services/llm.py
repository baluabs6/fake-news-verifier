from contextvars import ContextVar
from functools import lru_cache

from anthropic import AsyncAnthropic

from app.config import get_settings


USAGE: ContextVar[dict | None] = ContextVar("llm_usage", default=None)


def start_usage() -> dict:
    """Begin counting tokens for the current task tree; the returned dict is updated in place."""
    d = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    USAGE.set(d)
    return d


class LLMNotConfigured(RuntimeError):
    pass


@lru_cache
def _make_client(key: str) -> AsyncAnthropic:
    return AsyncAnthropic(api_key=key, timeout=60.0, max_retries=2)


def _client() -> AsyncAnthropic:
    key = get_settings().anthropic_api_key
    if not key:
        raise LLMNotConfigured("ANTHROPIC_API_KEY is not set")
    return _make_client(key)


async def structured_call(system: str, user: str, tool_name: str, description: str, schema: dict) -> dict:
    """Force Claude to answer through a tool so the output is always schema-shaped JSON."""
    resp = await _client().messages.create(
        model=get_settings().anthropic_model,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[{"name": tool_name, "description": description, "input_schema": schema}],
        tool_choice={"type": "tool", "name": tool_name},
    )
    u = USAGE.get()
    if u is not None:
        u["calls"] += 1
        u["input_tokens"] += resp.usage.input_tokens
        u["output_tokens"] += resp.usage.output_tokens
    for block in resp.content:
        if block.type == "tool_use" and block.name == tool_name:
            return dict(block.input)
    raise RuntimeError("Model returned no structured output")
