"""Public Luna Standard API estimates, kept separate from provider billing."""

PRICING = {
    "model": "gpt-6-luna",
    "tier": "Standard",
    "currency": "USD",
    "checked_on": "2026-10-27",
    "source": "https://developers.openai.com/api/docs/models/gpt-6-luna",
    "rates_per_million": {
        "input": 0.10, "cache_read": 0.01,
        "cache_write_30m": 0.125, "cache_write_12h": 0.25, "output": 0.50,
    },
}


def estimate_cost(usage: dict | None, pricing_model: str = "gpt-6-luna") -> dict:
    """Cache reads/writes are subsets of input; reasoning is part of output."""
    unavailable = {"status": "unavailable", "total_usd": None, "pricing": PRICING}
    if pricing_model != PRICING["model"]:
        return {**unavailable, "pricing": None, "reason": f"No public rates configured for {pricing_model}."}
    usage = usage or {}
    details = usage.get("input_tokens_details") or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    cached = details.get("cached_tokens")
    written = details.get("cache_write_tokens")
    if not all(_count(n) for n in (input_tokens, output_tokens, cached, written)):
        return {**unavailable, "reason": "Input, output, cache-read or cache-write usage was not reported."}
    if cached + written > input_tokens:
        return {**unavailable, "reason": "Cache usage exceeds the reported input tokens."}

    note = None
    writes = details.get("cache_write_tokens_details")
    if writes is not None:
        short = writes.get("ttl_30m_tokens")
        long = writes.get("ttl_12h_tokens")
        if not all(_count(n) for n in (short, long)) or short + long != written:
            return {**unavailable, "reason": "Cache-write lifetime counts are missing or inconsistent."}
    else:
        short, long = written, 0
        if written:
            note = "Cache-write lifetime was not reported; estimated at the default 30-minute rate."

    long_context = input_tokens > 272_000
    counts = {"input": input_tokens - cached - written, "cache_read": cached,
              "cache_write_30m": short, "cache_write_12h": long, "output": output_tokens}
    components = []
    for kind, tokens in counts.items():
        multiplier = (1.5 if kind == "output" else 2) if long_context else 1
        rate = PRICING["rates_per_million"][kind] * multiplier
        components.append({"kind": kind, "tokens": tokens, "rate_per_million": rate,
                           "cost_usd": tokens * rate / 1_000_000})
    return {"status": "estimated", "pricing": PRICING, "components": components,
            "total_usd": sum(c["cost_usd"] for c in components),
            "long_context": long_context, "note": note}


def _count(value) -> bool:
    return type(value) is int and value >= 0
