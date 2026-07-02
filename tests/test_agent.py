from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import agent.agent as agent_module


class FakeMessages:
    def __init__(self, responses):
        self.create = Mock(side_effect=responses)


def text_block(text):
    return SimpleNamespace(text=text)


def tool_block(name, input_, id_="tool-1"):
    return SimpleNamespace(type="tool_use", name=name, input=input_, id=id_)


def test_run_agent_dispatches_tool_and_returns_final_json(monkeypatch):
    quote_tool = Mock(return_value={"ticker": "AAPL", "price": 195.0})
    monkeypatch.setitem(agent_module._TOOL_DISPATCH, "get_quote", quote_tool)
    fake_client = SimpleNamespace(messages=FakeMessages([
        SimpleNamespace(
            stop_reason="tool_use",
            content=[tool_block("get_quote", {"ticker": "AAPL"})],
        ),
        SimpleNamespace(
            stop_reason="end_turn",
            content=[text_block('{"signal":"BUY","rationale":"ok","data_fetched":{"price":195.0}}')],
        ),
    ]))
    monkeypatch.setattr(agent_module, "_client", fake_client)

    result = agent_module.run_agent("AAPL", "use price", model="test-model")

    quote_tool.assert_called_once_with(ticker="AAPL")
    assert result == {
        "ticker": "AAPL",
        "signal": "BUY",
        "rationale": "ok",
        "data_fetched": {"price": 195.0},
    }
    assert fake_client.messages.create.call_count == 2
    second_messages = fake_client.messages.create.call_args_list[1].kwargs["messages"]
    assert second_messages[-1]["content"][0]["type"] == "tool_result"
    assert second_messages[-1]["content"][0]["tool_use_id"] == "tool-1"


def test_run_agent_returns_error_for_unparseable_final_output(monkeypatch):
    fake_client = SimpleNamespace(messages=FakeMessages([
        SimpleNamespace(stop_reason="end_turn", content=[text_block("not json")]),
    ]))
    monkeypatch.setattr(agent_module, "_client", fake_client)

    result = agent_module.run_agent("MSFT", "rules")

    assert result["ticker"] == "MSFT"
    assert result["signal"] == "ERROR"
    assert result["data_fetched"] == {}
    assert "Agent returned no text content" in result["rationale"]


def test_run_agent_returns_error_for_bad_json_and_unexpected_stop_reason(monkeypatch):
    bad_json_client = SimpleNamespace(messages=FakeMessages([
        SimpleNamespace(stop_reason="end_turn", content=[text_block("{bad json}")]),
    ]))
    monkeypatch.setattr(agent_module, "_client", bad_json_client)

    bad_json = agent_module.run_agent("MSFT", "rules")

    assert bad_json["signal"] == "ERROR"
    assert "Could not parse agent response" in bad_json["rationale"]

    unexpected_client = SimpleNamespace(messages=FakeMessages([
        SimpleNamespace(stop_reason="max_tokens", content=[]),
    ]))
    monkeypatch.setattr(agent_module, "_client", unexpected_client)

    unexpected = agent_module.run_agent("MSFT", "rules")

    assert unexpected == agent_module._error("MSFT", "Unexpected stop reason: max_tokens")


def test_error_contract():
    assert agent_module._error("TSLA", "boom") == {
        "ticker": "TSLA",
        "signal": "ERROR",
        "rationale": "boom",
        "data_fetched": {},
    }
