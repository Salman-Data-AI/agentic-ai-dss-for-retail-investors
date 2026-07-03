from __future__ import annotations

from pathlib import Path

import main as pipeline


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
    written = []

    def fake_run_agent(ticker, rules, model):
        calls.append({"ticker": ticker, "rules": rules, "model": model})
        return {
            "ticker": ticker,
            "signal": "HOLD",
            "rationale": f"{ticker} rationale",
            "data_fetched": {},
        }

    monkeypatch.setattr(pipeline, "_DATA_DIR", str(data_dir))
    monkeypatch.setattr(pipeline, "datetime", FixedDateTime)
    monkeypatch.setattr(pipeline, "run_agent", fake_run_agent)
    monkeypatch.setattr(pipeline, "write_signals", lambda signals: written.extend(signals))
    monkeypatch.setattr(pipeline, "get_quote", lambda ticker: {"name": f"{ticker} Corp"})
    monkeypatch.setattr(pipeline, "get_fmp_run_request_count", lambda: 0)
    monkeypatch.setattr(pipeline, "get_fmp_request_count", lambda: 0)
    monkeypatch.setattr(pipeline.config, "BUY_RULES", "buy rules")
    monkeypatch.setattr(pipeline.config, "SELL_RULES", "sell rules")
    monkeypatch.setattr(pipeline.config, "MODEL", "test-model")
    monkeypatch.setattr(pipeline.config, "PROVIDER", "openai")

    pipeline.main()

    assert [call["ticker"] for call in calls] == ["AAPL", "MSFT", "JPM"]
    assert calls[0] == {"ticker": "AAPL", "rules": "buy rules", "model": "test-model"}
    assert calls[1] == {"ticker": "MSFT", "rules": "buy rules", "model": "test-model"}
    assert "My entry price for JPM is $195.5." in calls[2]["rules"]
    assert "I bought 10 shares on 2024-11-15." in calls[2]["rules"]
    assert calls[2]["rules"].endswith("sell rules")

    assert len(written) == 3
    assert [record["signal_type"] for record in written] == ["BUY_EVAL", "BUY_EVAL", "SELL_EVAL"]
    assert {record["run_date"] for record in written} == {"2026-07-02 12:34:56"}
    assert {record["provider"] for record in written} == {"openai"}
    assert {record["model"] for record in written} == {"test-model"}
    assert written[0]["data_fetched"]["name"] == "AAPL Corp"
    assert written[1]["data_fetched"]["name"] == "MSFT Corp"
    assert written[2]["data_fetched"]["name"] == "JPM Corp"
    assert written[2]["entry_price"] == 195.5
