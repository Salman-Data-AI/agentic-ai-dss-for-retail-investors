from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import agent.agent as agent_module
from agent.llm import AnthropicAdapter, LLMResponse, OpenAICompatibleAdapter, ToolCall


def text_block(text):
    return SimpleNamespace(text=text)


def anthropic_tool_block(name, input_, id_="tool-1"):
    return SimpleNamespace(type="tool_use", name=name, input=input_, id=id_)


def openai_tool_call(name, arguments='{"ticker":"AAPL"}', id_="call-1"):
    return SimpleNamespace(
        id=id_,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class FakeNormalizedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.appended_results = []

    def next_step(self):
        return self.responses.pop(0)

    def append_tool_results(self, results):
        self.appended_results.append(results)


def test_run_agent_dispatches_tool_and_returns_final_json(monkeypatch):
    quote_tool = Mock(return_value={"ticker": "AAPL", "price": 195.0})
    fake_client = FakeNormalizedClient([
        LLMResponse(tool_calls=[ToolCall(id="tool-1", name="get_quote", arguments={"ticker": "AAPL"})]),
        LLMResponse(final_text='{"signal":"BUY","rationale":"ok","data_fetched":{"price":195.0}}'),
    ])
    create_client = Mock(return_value=fake_client)

    monkeypatch.setitem(agent_module._TOOL_DISPATCH, "get_quote", quote_tool)
    monkeypatch.setattr(agent_module, "create_llm_client", create_client)
    monkeypatch.setattr(agent_module.config, "PROVIDER", "anthropic")
    monkeypatch.setattr(agent_module.config, "PROVIDER_SETTINGS", {
        "anthropic": {"api_key_env": "ANTHROPIC_API_KEY", "base_url": None}
    })

    result = agent_module.run_agent("AAPL", "use price", model="test-model")

    quote_tool.assert_called_once_with(ticker="AAPL")
    assert result == {
        "ticker": "AAPL",
        "signal": "BUY",
        "rationale": "ok",
        "data_fetched": {"price": 195.0},
    }
    assert fake_client.appended_results == [[
        {"id": "tool-1", "result": {"ticker": "AAPL", "price": 195.0}}
    ]]
    assert create_client.call_args.kwargs["provider"] == "anthropic"


def test_run_agent_uses_watchlist_buy_skip_contract(monkeypatch):
    fake_client = FakeNormalizedClient([
        LLMResponse(final_text='{"signal":"SKIP","rationale":"ok","data_fetched":{}}'),
    ])
    create_client = Mock(return_value=fake_client)

    monkeypatch.setattr(agent_module, "create_llm_client", create_client)
    monkeypatch.setattr(agent_module.config, "PROVIDER", "anthropic")
    monkeypatch.setattr(agent_module.config, "PROVIDER_SETTINGS", {
        "anthropic": {"api_key_env": "ANTHROPIC_API_KEY", "base_url": None}
    })

    result = agent_module.run_agent(
        "AAPL",
        "use price",
        model="test-model",
        evaluation_type="BUY_EVAL",
    )

    system = create_client.call_args.kwargs["system"]
    assert '"signal": "<BUY | SKIP>"' in system
    assert "SKIP : the stock does not meet the user's entry criteria now; skip for now" in system
    assert "Use only one of these signal values: BUY | SKIP." in system
    assert result["signal"] == "SKIP"


def test_run_agent_rejects_signal_outside_evaluation_contract(monkeypatch):
    fake_client = FakeNormalizedClient([
        LLMResponse(final_text='{"signal":"SELL","rationale":"ok","data_fetched":{}}'),
    ])

    monkeypatch.setattr(agent_module, "create_llm_client", Mock(return_value=fake_client))
    monkeypatch.setattr(agent_module.config, "PROVIDER", "anthropic")
    monkeypatch.setattr(agent_module.config, "PROVIDER_SETTINGS", {
        "anthropic": {"api_key_env": "ANTHROPIC_API_KEY", "base_url": None}
    })

    result = agent_module.run_agent(
        "AAPL",
        "use price",
        model="test-model",
        evaluation_type="BUY_EVAL",
    )

    assert result["ticker"] == "AAPL"
    assert result["signal"] == "ERROR"
    assert "invalid signal 'SELL' for BUY_EVAL" in result["rationale"]


def test_run_agent_openai_compatible_tool_flow_and_malformed_output(monkeypatch):
    quote_tool = Mock(return_value={"ticker": "AAPL", "price": 195.0})
    openai_client = OpenAICompatibleAdapter(
        model="test-model",
        system="system",
        user_content="Evaluate stock: AAPL",
        api_key="test-key",
        base_url="https://example.test/v1",
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(side_effect=[
            SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[openai_tool_call("get_quote")],
                ),
            )]),
            SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content='{"signal":"BUY","rationale":"ok","data_fetched":{"price":195.0}}',
                    tool_calls=None,
                ),
            )]),
        ])))),
    )
    malformed_client = FakeNormalizedClient([LLMResponse(final_text="{bad json}")])

    monkeypatch.setitem(agent_module._TOOL_DISPATCH, "get_quote", quote_tool)
    monkeypatch.setattr(agent_module.config, "PROVIDER", "openai")
    monkeypatch.setattr(agent_module.config, "PROVIDER_SETTINGS", {
        "openai": {"api_key_env": "OPENAI_API_KEY", "base_url": "https://api.openai.com/v1"}
    })
    monkeypatch.setattr(agent_module, "create_llm_client", Mock(side_effect=[openai_client, malformed_client]))

    result = agent_module.run_agent("AAPL", "use price", model="test-model")
    bad_json = agent_module.run_agent("MSFT", "rules", model="test-model")

    quote_tool.assert_called_once_with(ticker="AAPL")
    assert result["signal"] == "BUY"
    assert result["data_fetched"] == {"price": 195.0}
    assert bad_json["signal"] == "ERROR"
    assert "Could not parse agent response" in bad_json["rationale"]


def test_run_agent_returns_error_for_unparseable_final_output(monkeypatch):
    fake_client = FakeNormalizedClient([LLMResponse(final_text="not json")])
    monkeypatch.setattr(agent_module, "create_llm_client", Mock(return_value=fake_client))
    monkeypatch.setattr(agent_module.config, "PROVIDER", "anthropic")
    monkeypatch.setattr(agent_module.config, "PROVIDER_SETTINGS", {
        "anthropic": {"api_key_env": "ANTHROPIC_API_KEY", "base_url": None}
    })

    result = agent_module.run_agent("MSFT", "rules")

    assert result["ticker"] == "MSFT"
    assert result["signal"] == "ERROR"
    assert result["data_fetched"] == {}
    assert "Agent returned no text content" in result["rationale"]


def test_run_agent_returns_error_for_client_error_and_unknown_provider(monkeypatch):
    fake_client = FakeNormalizedClient([LLMResponse(error="Unexpected stop reason: max_tokens")])
    monkeypatch.setattr(agent_module, "create_llm_client", Mock(return_value=fake_client))
    monkeypatch.setattr(agent_module.config, "PROVIDER", "anthropic")
    monkeypatch.setattr(agent_module.config, "PROVIDER_SETTINGS", {
        "anthropic": {"api_key_env": "ANTHROPIC_API_KEY", "base_url": None}
    })

    unexpected = agent_module.run_agent("MSFT", "rules")

    assert unexpected == agent_module._error("MSFT", "Unexpected stop reason: max_tokens")

    monkeypatch.setattr(agent_module.config, "PROVIDER", "nope")
    monkeypatch.setattr(agent_module.config, "PROVIDER_SETTINGS", {})
    unsupported = agent_module.run_agent("MSFT", "rules")

    assert unsupported["signal"] == "ERROR"
    assert "Unsupported PROVIDER" in unsupported["rationale"]


def test_anthropic_adapter_preserves_tool_use_message_flow():
    fake_messages = SimpleNamespace(create=Mock(side_effect=[
        SimpleNamespace(
            stop_reason="tool_use",
            content=[anthropic_tool_block("get_quote", {"ticker": "AAPL"})],
        ),
        SimpleNamespace(
            stop_reason="end_turn",
            content=[text_block('{"signal":"HOLD","rationale":"ok","data_fetched":{}}')],
        ),
    ]))
    adapter = AnthropicAdapter(
        model="test-model",
        system="system",
        user_content="Evaluate stock: AAPL",
        api_key="test-key",
        client=SimpleNamespace(messages=fake_messages),
    )

    first = adapter.next_step()
    adapter.append_tool_results([{"id": "tool-1", "result": {"price": 195.0}}])
    second = adapter.next_step()

    assert first.tool_calls == [ToolCall(id="tool-1", name="get_quote", arguments={"ticker": "AAPL"})]
    assert adapter.messages[-1]["role"] == "user"
    assert adapter.messages[-1]["content"][0]["type"] == "tool_result"
    assert adapter.messages[-1]["content"][0]["tool_use_id"] == "tool-1"
    assert second.final_text == '{"signal":"HOLD","rationale":"ok","data_fetched":{}}'


def test_openai_adapter_renders_tools_and_appends_tool_results():
    fake_create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="tool_calls",
        message=SimpleNamespace(
            content=None,
            tool_calls=[openai_tool_call("get_quote", '{"ticker":"AAPL"}')],
        ),
    )]))
    adapter = OpenAICompatibleAdapter(
        model="test-model",
        system="system",
        user_content="Evaluate stock: AAPL",
        api_key="test-key",
        base_url="https://example.test/v1",
        provider="groq",
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )

    response = adapter.next_step()
    adapter.append_tool_results([{"id": "call-1", "result": {"price": 195.0}}])

    assert response.tool_calls == [ToolCall(id="call-1", name="get_quote", arguments={"ticker": "AAPL"})]
    sent_tools = fake_create.call_args.kwargs["tools"]
    assert fake_create.call_args.kwargs["max_tokens"] == 1024
    assert "max_completion_tokens" not in fake_create.call_args.kwargs
    assert sent_tools[0]["type"] == "function"
    assert sent_tools[0]["function"]["parameters"]["type"] == "object"
    assert adapter.messages[-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '{"price": 195.0}',
    }


def test_openai_adapter_uses_max_completion_tokens_for_openai_models():
    fake_create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop",
        message=SimpleNamespace(
            content='{"signal":"HOLD","rationale":"ok","data_fetched":{}}',
            tool_calls=None,
        ),
    )]))
    adapter = OpenAICompatibleAdapter(
        model="gpt-5.4-nano",
        system="system",
        user_content="Evaluate stock: AAPL",
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        provider="openai",
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )

    response = adapter.next_step()

    assert response.final_text == '{"signal":"HOLD","rationale":"ok","data_fetched":{}}'
    assert fake_create.call_args.kwargs["max_completion_tokens"] == 1024
    assert "max_tokens" not in fake_create.call_args.kwargs


def test_error_contract():
    assert agent_module._error("TSLA", "boom") == {
        "ticker": "TSLA",
        "signal": "ERROR",
        "rationale": "boom",
        "data_fetched": {},
    }
