from __future__ import annotations

import ast
from pathlib import Path
import re
from unittest.mock import Mock

import agent.agent as agent_module
import agent.rule_compiler as compiler
import agent.rule_approval as approval
import settings
from agent.llm import LLMResponse


class FakeClient:
    def __init__(self, text):
        self.text = text

    def next_step(self):
        return LLMResponse(final_text=self.text)

    def append_tool_results(self, results):
        raise AssertionError("compile/rationale paths should not request tools")


def _metrics_reference_rule_phrases() -> list[str]:
    app_path = Path(__file__).resolve().parents[1] / "src" / "dashboard" / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"))
    rows = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(target, "id", None) == "_METRIC_REFERENCE" for target in node.targets):
            rows = ast.literal_eval(node.value)
            break
    phrases = []
    for row in rows:
        phrases.extend(re.findall(r'"([^"]+)"', row["rule_phrasing"]))
    return phrases


def _patch_provider(module, monkeypatch):
    monkeypatch.setattr(module.config, "PROVIDER_SETTINGS", {
        "anthropic": {"api_key_env": "ANTHROPIC_API_KEY", "base_url": None}
    })


def test_compile_blocks_unbound_clause_without_dropping_it(monkeypatch):
    _patch_provider(compiler, monkeypatch)
    fake_compile = FakeClient(
        '{"buy_clauses":[],"sell_clauses":[],"unbound_clauses":['
        '{"side":"buy","user_phrase":"buy only if management is excellent","reason":"unsupported qualitative metric"}'
        ']}'
    )
    create_client = Mock(return_value=fake_compile)
    monkeypatch.setattr(compiler, "create_llm_client", create_client)

    result = compiler.compile_rule_text(
        buy_rules="buy only if management is excellent",
        sell_rules="sell if RSI above 70",
        provider="anthropic",
        model="test-model",
    )

    assert result["ok"] is False
    assert result["code"] == "unbound_clauses"
    assert result["unbound_clauses"][0]["user_phrase"] == "buy only if management is excellent"
    assert create_client.call_args.kwargs["tool_schemas"] == []
    assert "prompt-enforced" not in result["message"]


def test_compile_prompt_explains_entry_price_metric(monkeypatch):
    _patch_provider(compiler, monkeypatch)
    fake_compile = FakeClient(
        '{"buy_clauses":[{"user_phrase":"RSI below 35","bound_metric":"rsi","operator":"<","threshold":35}],'
        '"sell_clauses":[{"user_phrase":"RSI above 70","bound_metric":"rsi","operator":">","threshold":70}],'
        '"unbound_clauses":[]}'
    )
    create_client = Mock(return_value=fake_compile)
    monkeypatch.setattr(compiler, "create_llm_client", create_client)

    compiler.compile_rule_text(
        buy_rules="management is excellent",
        sell_rules="The current price is more than 25% above my entry price",
        provider="anthropic",
        model="test-model",
    )

    system_prompt = create_client.call_args.kwargs["system"]
    assert "gain_loss_pct" in system_prompt
    assert "price more than 25% above my entry price -> gain_loss_pct > 25" in system_prompt


def test_common_rules_compile_deterministically_without_llm(monkeypatch):
    create_client = Mock()
    monkeypatch.setattr(compiler, "create_llm_client", create_client)

    result = compiler.compile_rule_text(
        buy_rules="""
        Consider buying a stock if ALL of the following are true:
        - RSI (14-day) is below 35, suggesting the stock is oversold
        - The current price is within 25% above the 52-week low
        - PE ratio is below 20
        - EPS should be positive
        - Volume should be above average
        """,
        sell_rules="""
        Consider selling a stock if ANY of the following are true:
        - RSI (14-day) is above 70, suggesting the stock is overbought
        - The current price is more than 25% above my entry price (take profit)
        - The current price is more than 15% below my entry price (stop loss)
        - PE ratio has expanded above 39
        """,
        provider="anthropic",
        model="test-model",
    )

    assert result["ok"] is True
    assert result["compiler"] == "deterministic"
    assert create_client.call_count == 0
    assert result["rule_set"]["buy_clauses"] == [
        {
            "user_phrase": "RSI (14-day) is below 35, suggesting the stock is oversold",
            "bound_metric": "rsi",
            "operator": "<",
            "threshold": 35,
        },
        {
            "user_phrase": "The current price is within 25% above the 52-week low",
            "bound_metric": "price_above_52_week_low_pct",
            "operator": "<=",
            "threshold": 25,
        },
        {
            "user_phrase": "PE ratio is below 20",
            "bound_metric": "pe_ratio",
            "operator": "<",
            "threshold": 20,
        },
        {
            "user_phrase": "EPS should be positive",
            "bound_metric": "eps_ttm",
            "operator": ">",
            "threshold": 0,
        },
        {
            "user_phrase": "Volume should be above average",
            "bound_metric": "volume_vs_average_pct",
            "operator": ">",
            "threshold": 0,
        },
    ]
    assert result["rule_set"]["sell_clauses"][1]["bound_metric"] == "gain_loss_pct"
    assert result["rule_set"]["sell_clauses"][2]["threshold"] == -15.0


def test_metrics_reference_rule_phrases_compile_without_llm(monkeypatch):
    create_client = Mock()
    monkeypatch.setattr(compiler, "create_llm_client", create_client)

    failures = []
    for phrase in _metrics_reference_rule_phrases():
        result = compiler.compile_rule_text(
            buy_rules=f"- {phrase}",
            sell_rules="- RSI above 70",
            provider="anthropic",
            model="test-model",
        )
        if not result["ok"]:
            failures.append((phrase, result))

    assert failures == []
    create_client.assert_not_called()


def test_hybrid_compile_sends_only_remaining_clauses_to_llm(monkeypatch):
    _patch_provider(compiler, monkeypatch)
    fake_compile = FakeClient(
        '{"buy_clauses":[{"user_phrase":"brand strength above 4","bound_metric":"overall_score","operator":">","threshold":4}],'
        '"sell_clauses":[],"unbound_clauses":[]}'
    )
    create_client = Mock(return_value=fake_compile)
    monkeypatch.setattr(compiler, "create_llm_client", create_client)

    result = compiler.compile_rule_text(
        buy_rules="- RSI below 35\n- brand strength above 4",
        sell_rules="- RSI above 70",
        provider="anthropic",
        model="test-model",
    )

    assert result["ok"] is True
    assert result["compiler"] == "hybrid"
    assert "RSI below 35" not in create_client.call_args.kwargs["user_content"]
    assert "brand strength above 4" in create_client.call_args.kwargs["user_content"]
    assert [clause["bound_metric"] for clause in result["rule_set"]["buy_clauses"]] == [
        "rsi",
        "overall_score",
    ]


def test_compile_rejects_metric_invalid_for_evaluation_type(monkeypatch):
    _patch_provider(compiler, monkeypatch)
    fake_compile = FakeClient(
        '{"buy_clauses":[{"user_phrase":"return from entry above 10%","bound_metric":"gain_loss_pct","operator":">","threshold":10}],'
        '"sell_clauses":[],"unbound_clauses":[]}'
    )
    monkeypatch.setattr(compiler, "create_llm_client", Mock(return_value=fake_compile))

    result = compiler.compile_rule_text(
        buy_rules="- return from entry above 10%",
        sell_rules="- RSI above 70",
        provider="anthropic",
        model="test-model",
    )

    assert result["ok"] is False
    assert result["code"] == "source_validation_error"
    assert "not valid for BUY_EVAL" in result["validation"]["problems"][0]["message"]


def test_parse_repairs_supported_entry_price_unbound_clauses():
    result = compiler.parse_compiled_rule_response(
        '{"buy_clauses":[{"user_phrase":"RSI below 35","bound_metric":"rsi","operator":"<","threshold":35}],'
        '"sell_clauses":[{"user_phrase":"RSI above 70","bound_metric":"rsi","operator":">","threshold":70}],'
        '"unbound_clauses":['
        '{"side":"sell","user_phrase":"The current price is more than 25% above my entry price (take profit)","reason":"No supported metric captures price relative to the investor entry price"},'
        '{"side":"sell","user_phrase":"The current price is more than 15% below my entry price (stop loss)","reason":"No supported metric captures price relative to the investor entry price"}'
        ']}',
        fingerprint="fp",
    )

    assert result["ok"] is True
    assert result["rule_set"]["sell_clauses"][1] == {
        "user_phrase": "The current price is more than 25% above my entry price (take profit)",
        "bound_metric": "gain_loss_pct",
        "operator": ">",
        "threshold": 25.0,
    }
    assert result["rule_set"]["sell_clauses"][2] == {
        "user_phrase": "The current price is more than 15% below my entry price (stop loss)",
        "bound_metric": "gain_loss_pct",
        "operator": "<",
        "threshold": -15.0,
    }


def test_prepare_rule_set_invalidates_stale_approved_lock_and_requires_reapproval(monkeypatch):
    rule_set = {
        "buy_clauses": [{"user_phrase": "RSI below 35", "bound_metric": "rsi", "operator": "<", "threshold": 35}],
        "sell_clauses": [{"user_phrase": "RSI above 70", "bound_metric": "rsi", "operator": ">", "threshold": 70}],
    }
    settings.save_settings({
        "provider": "anthropic",
        "buy_rules": "old buy",
        "sell_rules": "old sell",
        "compiled_rule_set": rule_set,
        "compiled_rule_fingerprint": compiler.current_rule_fingerprint("old buy", "old sell"),
        "rule_approval_state": "approved",
    })
    compile_result = {
        "ok": True,
        "rule_set": rule_set,
        "fingerprint": compiler.current_rule_fingerprint("new buy", "old sell"),
    }
    monkeypatch.setattr(approval, "compile_rule_text", Mock(return_value=compile_result))

    current = settings.load_settings()
    current["buy_rules"] = "new buy"
    result = approval.prepare_rule_set(current)
    loaded = settings.load_settings()

    assert result["ok"] is False
    assert result["code"] == "approval_required"
    assert loaded["rule_approval_state"] == "compiled"
    assert loaded["compiled_rule_fingerprint"] == compiler.current_rule_fingerprint("new buy", "old sell")


def test_approve_current_rule_set_locks_unchanged_compiled_rules(monkeypatch):
    rule_set = {
        "buy_clauses": [{"user_phrase": "RSI below 35", "bound_metric": "rsi", "operator": "<", "threshold": 35}],
        "sell_clauses": [{"user_phrase": "RSI above 70", "bound_metric": "rsi", "operator": ">", "threshold": 70}],
    }
    settings.save_settings({
        "provider": "anthropic",
        "buy_rules": "buy",
        "sell_rules": "sell",
        "compiled_rule_set": rule_set,
        "compiled_rule_fingerprint": compiler.current_rule_fingerprint("buy", "sell"),
        "rule_approval_state": "compiled",
    })

    result = approval.approve_current_rule_set()

    assert result["ok"] is True
    assert settings.load_settings()["rule_approval_state"] == "approved"


def test_prepare_rule_set_does_not_recompile_unchanged_compiled_rules(monkeypatch):
    rule_set = {
        "buy_clauses": [{"user_phrase": "RSI below 35", "bound_metric": "rsi", "operator": "<", "threshold": 35}],
        "sell_clauses": [{"user_phrase": "RSI above 70", "bound_metric": "rsi", "operator": ">", "threshold": 70}],
    }
    settings.save_settings({
        "provider": "anthropic",
        "buy_rules": "buy",
        "sell_rules": "sell",
        "compiled_rule_set": rule_set,
        "compiled_rule_fingerprint": compiler.current_rule_fingerprint("buy", "sell"),
        "rule_approval_state": "compiled",
    })
    compile_mock = Mock()
    monkeypatch.setattr(approval, "compile_rule_text", compile_mock)

    result = approval.prepare_rule_set(settings.load_settings())

    assert result["ok"] is False
    assert result["code"] == "approval_required"
    compile_mock.assert_not_called()


def test_deterministic_signal_authority_ignores_model_signal(monkeypatch):
    rule_set = {
        "buy_clauses": [{"user_phrase": "RSI below 35", "bound_metric": "rsi", "operator": "<", "threshold": 35}],
        "sell_clauses": [{"user_phrase": "RSI above 70", "bound_metric": "rsi", "operator": ">", "threshold": 70}],
    }
    fake_client = FakeClient(
        '[{"ticker":"AAPL","signal":"SELL","triggering_rule":"wrong","rationale":"RSI is below the approved threshold, so the code-decided signal is BUY.","data_fetched":{"rsi":30}}]'
    )
    monkeypatch.setattr(agent_module, "create_llm_client", Mock(return_value=fake_client))
    _patch_provider(agent_module, monkeypatch)

    first = agent_module.evaluate_signals_from_data_batch(
        [{"ticker": "AAPL", "fetched_data": {"get_rsi": {"rsi": 30}}}],
        "buy when RSI below 35",
        model="test-model",
        evaluation_type="BUY_EVAL",
        compiled_rule_set=rule_set,
    )
    second = agent_module.evaluate_signals_from_data_batch(
        [{"ticker": "AAPL", "fetched_data": {"get_rsi": {"rsi": 30}}}],
        "buy when RSI below 35",
        model="test-model",
        evaluation_type="BUY_EVAL",
        compiled_rule_set=rule_set,
    )

    assert first[0]["signal"] == "BUY"
    assert first[0]["triggering_rule"] == "RSI below 35"
    assert first[0]["data_fetched"] == {"get_rsi": {"rsi": 30}}
    assert second[0]["signal"] == "BUY"


def test_deterministic_rationale_cannot_overwrite_code_fetched_data(monkeypatch):
    rule_set = {
        "buy_clauses": [{"user_phrase": "PE below 20", "bound_metric": "pe_ratio", "operator": "<", "threshold": 20}],
        "sell_clauses": [{"user_phrase": "RSI above 70", "bound_metric": "rsi", "operator": ">", "threshold": 70}],
    }
    code_fetched = {"get_key_metrics": {"pe_ratio": 18, "eps_ttm": 4.2}}
    fake_client = FakeClient(
        '[{"ticker":"AAPL","rationale":"PE is below the approved threshold.","data_fetched":{"pe_ratio":999,"source":"model"}}]'
    )
    monkeypatch.setattr(agent_module, "create_llm_client", Mock(return_value=fake_client))
    _patch_provider(agent_module, monkeypatch)

    result = agent_module.evaluate_signals_from_data_batch(
        [{"ticker": "AAPL", "fetched_data": code_fetched}],
        "buy when PE below 20",
        model="test-model",
        evaluation_type="BUY_EVAL",
        compiled_rule_set=rule_set,
    )

    assert result[0]["signal"] == "BUY"
    assert result[0]["rationale"] == "PE is below the approved threshold."
    assert result[0]["data_fetched"] == code_fetched


def test_deterministic_buy_uses_ttm_metric_aliases(monkeypatch):
    rule_set = {
        "buy_clauses": [
            {"user_phrase": "PE ratio is below 20", "bound_metric": "pe_ratio", "operator": "<", "threshold": 20},
            {"user_phrase": "EPS should be positive", "bound_metric": "eps", "operator": ">", "threshold": 0},
        ],
        "sell_clauses": [{"user_phrase": "RSI above 70", "bound_metric": "rsi", "operator": ">", "threshold": 70}],
    }
    fake_client = FakeClient(
        '[{"ticker":"BA","rationale":"BA passes the approved PE and EPS checks.","data_fetched":{"pe_ratio":18,"eps":4.2}}]'
    )
    monkeypatch.setattr(agent_module, "create_llm_client", Mock(return_value=fake_client))
    _patch_provider(agent_module, monkeypatch)

    result = agent_module.evaluate_signals_from_data_batch(
        [{"ticker": "BA", "fetched_data": {"get_key_metrics": {"pe_ratio": 18, "eps_ttm": 4.2}}}],
        "PE below 20 and EPS positive",
        model="test-model",
        evaluation_type="BUY_EVAL",
        compiled_rule_set=rule_set,
    )

    assert result[0]["signal"] == "BUY"
    assert result[0]["triggering_rule"] == "PE ratio is below 20; EPS should be positive"


def test_deterministic_error_names_missing_clause_metric():
    rule_set = {
        "buy_clauses": [{"user_phrase": "EPS should be positive", "bound_metric": "eps", "operator": ">", "threshold": 0}],
        "sell_clauses": [{"user_phrase": "RSI above 70", "bound_metric": "rsi", "operator": ">", "threshold": 70}],
    }

    result = agent_module.evaluate_signals_from_data_batch(
        [{"ticker": "BA", "fetched_data": {"get_quote": {"price": 200}}}],
        "EPS positive",
        model="test-model",
        evaluation_type="BUY_EVAL",
        compiled_rule_set=rule_set,
    )

    assert result[0]["signal"] == "ERROR"
    assert "EPS should be positive [eps]: Metric is missing." in result[0]["rationale"]
