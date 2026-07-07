from __future__ import annotations

import main as pipeline
import settings


class FixedDateTime:
    @classmethod
    def now(cls):
        return cls()

    def strftime(self, fmt):
        assert fmt == "%Y-%m-%d %H:%M:%S"
        return "2026-07-02 12:34:56"


def test_main_orchestrates_buy_and_sell_evaluations(workspace_tmp_path, monkeypatch):
    data_dir = workspace_tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "watchlist.csv").write_text("ticker,name\naapl,Apple\nmsft,Microsoft\n", encoding="utf-8")
    (data_dir / "portfolio.csv").write_text(
        "ticker,qty,entry_price,entry_date\njpm,10,195.50,2024-11-15\n",
        encoding="utf-8",
    )

    calls = []
    fetched = []
    written = []
    summaries = []

    def fake_execute_tool_plan(ticker, plan):
        fetched.append({"ticker": ticker, "plan": plan})
        return {"get_quote": {"ticker": ticker, "name": f"{ticker} Corp"}}

    def fake_evaluate_batch(items, rules, model, evaluation_type, compiled_rule_set=None):
        calls.append({
            "items": items,
            "rules": rules,
            "model": model,
            "evaluation_type": evaluation_type,
            "compiled_rule_set": compiled_rule_set,
        })
        return [
            {
                "ticker": item["ticker"],
                "signal": "SKIP" if evaluation_type == "BUY_EVAL" else "HOLD",
                "rationale": f"{item['ticker']} rationale",
                "data_fetched": {},
            }
            for item in items
        ]

    monkeypatch.setattr(pipeline, "_DATA_DIR", str(data_dir))
    monkeypatch.setattr(pipeline, "MAX_WORKERS", 1)
    monkeypatch.setattr(pipeline, "datetime", FixedDateTime)
    monkeypatch.setattr(pipeline, "_execute_tool_plan", fake_execute_tool_plan)
    monkeypatch.setattr(pipeline, "evaluate_signals_from_data_batch", fake_evaluate_batch)
    monkeypatch.setattr(pipeline, "write_signals", lambda signals: written.extend(signals))
    monkeypatch.setattr(pipeline, "_write_run_summary", lambda summary: summaries.append(summary))
    monkeypatch.setattr(pipeline, "get_fmp_run_request_count", lambda: 0)
    monkeypatch.setattr(pipeline, "get_fmp_request_count", lambda: 0)
    monkeypatch.setattr(pipeline, "prepare_rule_set", lambda current: {
        "ok": True,
        "rule_set": {"buy_clauses": [], "sell_clauses": []},
        "fingerprint": "fp",
    })
    monkeypatch.setattr(pipeline, "load_settings", lambda: {
        "provider": "openai",
        "model": "test-model",
        "buy_rules": "buy rules",
        "sell_rules": "sell rules",
        "temperature": 0.0,
    })

    result = pipeline.run_analysis()

    assert [item["ticker"] for item in calls[0]["items"]] == ["AAPL", "MSFT"]
    assert calls[0]["rules"] == "buy rules"
    assert calls[0]["model"] == "test-model"
    assert calls[0]["evaluation_type"] == "BUY_EVAL"
    assert calls[0]["compiled_rule_set"] == {"buy_clauses": [], "sell_clauses": []}
    assert calls[0]["items"][0]["fetched_data"] == {"get_quote": {"ticker": "AAPL", "name": "AAPL Corp"}}
    assert [item["ticker"] for item in calls[1]["items"]] == ["JPM"]
    assert calls[1]["rules"] == "sell rules"
    assert calls[1]["evaluation_type"] == "SELL_EVAL"
    assert calls[1]["items"][0]["fetched_data"]["holding"] == {
        "entry_price": 195.5,
        "qty": 10,
        "entry_date": "2024-11-15",
    }
    assert len(fetched) == 3

    assert len(written) == 3
    assert [record["signal_type"] for record in written] == ["BUY_EVAL", "BUY_EVAL", "SELL_EVAL"]
    assert {record["run_date"] for record in written} == {"2026-07-02 12:34:56"}
    assert {record["provider"] for record in written} == {"openai"}
    assert {record["model"] for record in written} == {"test-model"}
    assert {record["temperature"] for record in written} == {0.0}
    assert written[0]["rules_applied"] == "buy rules"
    assert written[1]["rules_applied"] == "buy rules"
    assert written[2]["rules_applied"] == "sell rules"
    assert written[0]["data_fetched"]["name"] == "AAPL Corp"
    assert written[1]["data_fetched"]["name"] == "MSFT Corp"
    assert written[2]["data_fetched"]["name"] == "JPM Corp"
    assert written[2]["entry_price"] == 195.5
    assert all(record["run_elapsed_seconds"] == result["elapsed_seconds"] for record in written)
    assert result["run_date"] == "2026-07-02 12:34:56"
    assert result["signal_count"] == 3
    assert result["fmp_requests_this_run"] == 0
    assert result["fmp_requests_today"] == 0
    assert result["max_workers"] == 1
    assert result["ticker_timings"][0]["ticker"] == "AAPL"
    assert result["ticker_timings"][2]["signal_type"] == "SELL_EVAL"
    assert set(result["batch_timings"]) == {"BUY_EVAL", "SELL_EVAL"}
    assert summaries == [result]


def test_run_analysis_uses_settings_changed_since_import(workspace_tmp_path, monkeypatch):
    data_dir = workspace_tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "watchlist.csv").write_text("ticker\nAAPL\n", encoding="utf-8")
    (data_dir / "portfolio.csv").write_text(
        "ticker,qty,entry_price,entry_date\nMSFT,2,100.0,2025-01-02\n",
        encoding="utf-8",
    )

    settings.save_settings({
        "provider": "openai",
        "model": "runtime-model",
        "buy_rules": "runtime buy rules",
        "sell_rules": "runtime sell rules",
        "temperature": None,
    })

    calls = []
    written = []

    def fake_evaluate_batch(items, rules, model, evaluation_type, compiled_rule_set=None):
        calls.append({
            "tickers": [item["ticker"] for item in items],
            "rules": rules,
            "model": model,
            "evaluation_type": evaluation_type,
        })
        return [
            {
                "ticker": item["ticker"],
                "signal": "SKIP" if evaluation_type == "BUY_EVAL" else "HOLD",
                "rationale": "ok",
                "data_fetched": {"name": item["ticker"]},
            }
            for item in items
        ]

    monkeypatch.setattr(pipeline, "_DATA_DIR", str(data_dir))
    monkeypatch.setattr(pipeline, "MAX_WORKERS", 1)
    monkeypatch.setattr(pipeline, "datetime", FixedDateTime)
    monkeypatch.setattr(pipeline, "_execute_tool_plan", lambda ticker, plan: {"get_quote": {"name": ticker}})
    monkeypatch.setattr(pipeline, "evaluate_signals_from_data_batch", fake_evaluate_batch)
    monkeypatch.setattr(pipeline, "write_signals", lambda signals: written.extend(signals))
    monkeypatch.setattr(pipeline, "_write_run_summary", lambda summary: None)
    monkeypatch.setattr(pipeline, "get_fmp_run_request_count", lambda: 0)
    monkeypatch.setattr(pipeline, "get_fmp_request_count", lambda: 0)
    monkeypatch.setattr(pipeline, "prepare_rule_set", lambda current: {
        "ok": True,
        "rule_set": {"buy_clauses": [], "sell_clauses": []},
        "fingerprint": "fp",
    })

    pipeline.run_analysis()

    assert calls[0] == {
        "tickers": ["AAPL"],
        "rules": "runtime buy rules",
        "model": "gpt-5.4-nano",
        "evaluation_type": "BUY_EVAL",
    }
    assert calls[1] == {
        "tickers": ["MSFT"],
        "rules": "runtime sell rules",
        "model": "gpt-5.4-nano",
        "evaluation_type": "SELL_EVAL",
    }
    assert {record["provider"] for record in written} == {"openai"}
    assert {record["model"] for record in written} == {"gpt-5.4-nano"}
    assert {record["temperature"] for record in written} == {None}
    assert written[0]["rules_applied"] == "runtime buy rules"
    assert written[1]["rules_applied"] == "runtime sell rules"


def test_run_analysis_skips_blank_watchlist_and_portfolio_tickers(workspace_tmp_path, monkeypatch):
    data_dir = workspace_tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "watchlist.csv").write_text("ticker\nAAPL\n\n \nMSFT\n", encoding="utf-8")
    (data_dir / "portfolio.csv").write_text(
        "ticker,qty,entry_price,entry_date\nJPM,10,195.50,2024-11-15\n,6,111,2024-01-01\nBAC,6,111,2024-01-01\n",
        encoding="utf-8",
    )

    calls = []
    written = []

    def fake_evaluate_batch(items, rules, model, evaluation_type, compiled_rule_set=None):
        calls.extend(item["ticker"] for item in items)
        return [
            {
                "ticker": item["ticker"],
                "signal": "SKIP" if evaluation_type == "BUY_EVAL" else "HOLD",
                "rationale": "ok",
                "data_fetched": {"name": item["ticker"]},
            }
            for item in items
        ]

    monkeypatch.setattr(pipeline, "_DATA_DIR", str(data_dir))
    monkeypatch.setattr(pipeline, "MAX_WORKERS", 1)
    monkeypatch.setattr(pipeline, "datetime", FixedDateTime)
    monkeypatch.setattr(pipeline, "_execute_tool_plan", lambda ticker, plan: {"get_quote": {"name": ticker}})
    monkeypatch.setattr(pipeline, "evaluate_signals_from_data_batch", fake_evaluate_batch)
    monkeypatch.setattr(pipeline, "write_signals", lambda signals: written.extend(signals))
    monkeypatch.setattr(pipeline, "_write_run_summary", lambda summary: None)
    monkeypatch.setattr(pipeline, "get_fmp_run_request_count", lambda: 0)
    monkeypatch.setattr(pipeline, "get_fmp_request_count", lambda: 0)
    monkeypatch.setattr(pipeline, "prepare_rule_set", lambda current: {
        "ok": True,
        "rule_set": {"buy_clauses": [], "sell_clauses": []},
        "fingerprint": "fp",
    })
    monkeypatch.setattr(pipeline, "load_settings", lambda: {
        "provider": "openai",
        "model": "test-model",
        "buy_rules": "buy rules",
        "sell_rules": "sell rules",
        "temperature": None,
    })

    pipeline.run_analysis()

    assert calls == ["AAPL", "MSFT", "JPM", "BAC"]
    assert [record["ticker"] for record in written] == ["AAPL", "MSFT", "JPM", "BAC"]


def test_run_analysis_blocks_before_fetch_when_rules_are_not_approved(workspace_tmp_path, monkeypatch):
    data_dir = workspace_tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "watchlist.csv").write_text("ticker\nAAPL\n", encoding="utf-8")
    (data_dir / "portfolio.csv").write_text("ticker,qty,entry_price,entry_date\n", encoding="utf-8")

    summaries = []
    monkeypatch.setattr(pipeline, "_DATA_DIR", str(data_dir))
    monkeypatch.setattr(pipeline, "datetime", FixedDateTime)
    monkeypatch.setattr(pipeline, "_execute_tool_plan", lambda ticker, plan: (_ for _ in ()).throw(AssertionError("should not fetch")))
    monkeypatch.setattr(pipeline, "write_signals", lambda signals: (_ for _ in ()).throw(AssertionError("should not write")))
    monkeypatch.setattr(pipeline, "_write_run_summary", lambda summary: summaries.append(summary))
    monkeypatch.setattr(pipeline, "get_fmp_run_request_count", lambda: 0)
    monkeypatch.setattr(pipeline, "get_fmp_request_count", lambda: 0)
    monkeypatch.setattr(pipeline, "prepare_rule_set", lambda current: {
        "ok": False,
        "code": "approval_required",
        "message": "Rule set compiled and must be approved before analysis can run.",
        "state": "compiled",
        "fingerprint": "fp",
    })
    monkeypatch.setattr(pipeline, "load_settings", lambda: {
        "provider": "openai",
        "model": "test-model",
        "buy_rules": "buy rules",
        "sell_rules": "sell rules",
        "temperature": None,
    })

    result = pipeline.run_analysis()

    assert result["blocked"] is True
    assert result["block_code"] == "approval_required"
    assert result["signal_count"] == 0
    assert summaries == [result]
