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


def _patch_provider(monkeypatch, provider="anthropic"):
    monkeypatch.setattr(agent_module.config, "PROVIDER", provider)
    monkeypatch.setattr(agent_module.config, "PROVIDER_SETTINGS", {
        provider: {"api_key_env": "ANTHROPIC_API_KEY", "base_url": None}
    })


def test_evaluate_signals_from_data_batch_uses_one_no_tool_client(monkeypatch):
    fake_client = FakeNormalizedClient([
        LLMResponse(final_text=(
            '['
            '{"ticker":"AAPL","signal":"BUY","rationale":"ok","data_fetched":{"price":200}},'
            '{"ticker":"MSFT","signal":"SKIP","rationale":"steady","data_fetched":{"price":300}}'
            ']'
        )),
    ])
    create_client = Mock(return_value=fake_client)

    monkeypatch.setattr(agent_module, "create_llm_client", create_client)
    _patch_provider(monkeypatch)

    result = agent_module.evaluate_signals_from_data_batch(
        [
            {"ticker": "AAPL", "fetched_data": {"get_quote": {"price": 200}}},
            {"ticker": "MSFT", "fetched_data": {"get_quote": {"price": 300}}},
        ],
        "use price",
        model="test-model",
        evaluation_type="BUY_EVAL",
    )

    assert [row["ticker"] for row in result] == ["AAPL", "MSFT"]
    assert [row["signal"] for row in result] == ["BUY", "SKIP"]
    assert create_client.call_count == 1
    assert create_client.call_args.kwargs["tool_schemas"] == []
    assert create_client.call_args.kwargs["max_tokens"] == 8192
    assert "JSON array" in create_client.call_args.kwargs["system"]
    assert "Three to four plain-English sentences" in create_client.call_args.kwargs["system"]


def test_evaluate_signals_from_data_batch_handles_bad_rows(monkeypatch):
    fake_client = FakeNormalizedClient([
        LLMResponse(final_text='[{"ticker":"AAPL","signal":"SELL","rationale":"bad","data_fetched":{}}]'),
    ])

    monkeypatch.setattr(agent_module, "create_llm_client", Mock(return_value=fake_client))
    _patch_provider(monkeypatch)

    result = agent_module.evaluate_signals_from_data_batch(
        [
            {"ticker": "AAPL", "fetched_data": {}},
            {"ticker": "MSFT", "fetched_data": {}},
        ],
        "rules",
        evaluation_type="BUY_EVAL",
    )

    assert result[0]["signal"] == "ERROR"
    assert "invalid signal 'SELL'" in result[0]["rationale"]
    assert result[1]["signal"] == "ERROR"
    assert "omitted this ticker" in result[1]["rationale"]


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


def test_openai_adapter_omits_tools_when_no_tool_schemas_are_provided():
    fake_create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop",
        message=SimpleNamespace(
            content='{"signal":"HOLD","rationale":"ok","data_fetched":{}}',
            tool_calls=None,
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
        tool_schemas=[],
    )

    response = adapter.next_step()

    assert response.final_text == '{"signal":"HOLD","rationale":"ok","data_fetched":{}}'
    assert "tools" not in fake_create.call_args.kwargs
    assert "tool_choice" not in fake_create.call_args.kwargs


def test_error_contract():
    assert agent_module._error("TSLA", "boom") == {
        "ticker": "TSLA",
        "signal": "ERROR",
        "rationale": "boom",
        "data_fetched": {},
    }
