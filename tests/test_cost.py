from copy import deepcopy

import pytest

from backend.app.agent.cost import estimate_cost


def usage(input_tokens=12_000, cached=4_000, written=7_000, output_tokens=2_000):
    return {"input_tokens": input_tokens, "output_tokens": output_tokens,
            "input_tokens_details": {"cached_tokens": cached, "cache_write_tokens": written},
            "output_tokens_details": {"reasoning_tokens": 1_000}}


def test_cache_and_reasoning_tokens_are_not_double_counted():
    data = usage()
    original = deepcopy(data)
    cost = estimate_cost(data)
    assert cost["status"] == "estimated"
    assert cost["total_usd"] == pytest.approx(0.002_015)
    assert [c["tokens"] for c in cost["components"]] == [1_000, 4_000, 7_000, 0, 2_000]
    assert "default 30-minute" in cost["note"]
    assert data == original


def test_mixed_write_lifetimes_use_separate_rates():
    data = usage()
    data["input_tokens_details"]["cache_write_tokens_details"] = {
        "ttl_30m_tokens": 3_000, "ttl_12h_tokens": 4_000}
    cost = estimate_cost(data)
    assert cost["total_usd"] == pytest.approx(0.002_515)
    assert cost["note"] is None


@pytest.mark.parametrize("input_tokens,input_rate,output_rate", [
    (272_000, 0.10, 0.50), (272_001, 0.20, 0.75),
])
def test_long_context_threshold_applies_to_whole_request(input_tokens, input_rate, output_rate):
    cost = estimate_cost(usage(input_tokens=input_tokens, cached=0, written=0, output_tokens=10))
    assert cost["components"][0]["rate_per_million"] == input_rate
    assert cost["components"][-1]["rate_per_million"] == output_rate
    assert cost["total_usd"] == pytest.approx((input_tokens * input_rate + 10 * output_rate) / 1_000_000)
    assert cost["note"] is None


def test_long_context_also_increases_cache_rates():
    cost = estimate_cost(usage(input_tokens=300_000))
    assert [c["rate_per_million"] for c in cost["components"]] == [0.2, 0.02, 0.25, 0.5, 0.75]


@pytest.mark.parametrize("data", [None, {}, {"input_tokens": 100, "output_tokens": 10},
    {"input_tokens": 100, "output_tokens": 10, "input_tokens_details": {"cached_tokens": 0}}])
def test_unreported_usage_is_unavailable_instead_of_free(data):
    cost = estimate_cost(data)
    assert cost["status"] == "unavailable"
    assert cost["total_usd"] is None


@pytest.mark.parametrize("input_tokens,cached,written,output_tokens", [
    (100, 60, 50, 1), (100, -1, 0, 1), (100, 0, 0, -1),
    (True, 0, 0, 1), (100, 0, 0, 1.5),
])
def test_invalid_usage_cannot_produce_an_estimate(input_tokens, cached, written, output_tokens):
    assert estimate_cost(usage(input_tokens, cached, written, output_tokens))["total_usd"] is None


@pytest.mark.parametrize("writes", [
    {"ttl_30m_tokens": 1, "ttl_12h_tokens": 0}, {"ttl_30m_tokens": 7_000},
])
def test_inconsistent_write_lifetimes_are_unavailable(writes):
    data = usage()
    data["input_tokens_details"]["cache_write_tokens_details"] = writes
    assert estimate_cost(data)["total_usd"] is None


def test_explicit_zero_usage_and_missing_prices_are_distinct():
    data = usage(0, 0, 0, 0)
    assert estimate_cost(data)["total_usd"] == 0
    cost = estimate_cost(data, pricing_model="another-model")
    assert cost["total_usd"] is None
    assert cost["pricing"] is None
