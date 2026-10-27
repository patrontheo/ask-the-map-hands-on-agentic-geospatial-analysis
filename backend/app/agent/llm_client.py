from functools import lru_cache

from openai import OpenAI

from backend.app import config


@lru_cache(maxsize=1)
def client() -> OpenAI:
    if not (config.LLM_BASE_URL and config.LLM_API_KEY and config.LLM_MODEL):
        raise RuntimeError("Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL in .env (see .env.example).")
    return OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=config.LLM_TIMEOUT_S)


def create_response(instructions: str, items: list, tools: list[dict]):
    """One stateless Responses API call; the caller keeps the conversation items."""
    kwargs = {"tools": tools, "parallel_tool_calls": True} if tools else {}
    if config.LLM_REASONING_EFFORT:
        kwargs["reasoning"] = {"effort": config.LLM_REASONING_EFFORT}
    return client().responses.create(
        model=config.LLM_MODEL,
        instructions=instructions,
        input=items,
        store=False,
        include=["reasoning.encrypted_content"],
        **kwargs,
    )
