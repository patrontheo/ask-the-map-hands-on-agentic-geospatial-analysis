from types import SimpleNamespace

import pytest

from backend.app.agent import llm_client


@pytest.mark.parametrize("effort", ["low", "medium", ""])
def test_response_request_uses_configured_effort_and_parallel_tools(monkeypatch, effort):
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return "response"

    monkeypatch.setattr(llm_client, "client", lambda: SimpleNamespace(responses=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_client.config, "LLM_MODEL", "test-model")
    monkeypatch.setattr(llm_client.config, "LLM_REASONING_EFFORT", effort)
    items = [{"role": "user", "content": "Show sites."}]
    tools = [{"type": "function", "name": "show_layer"}]

    assert llm_client.create_response("instructions", items, tools) == "response"
    request = requests[0]
    assert request["input"] == items and request["tools"] == tools
    assert request["parallel_tool_calls"] is True
    assert request["store"] is False
    if effort:
        assert request["reasoning"] == {"effort": effort}
    else:
        assert "reasoning" not in request
