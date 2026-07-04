from __future__ import annotations

import json
import os
from pathlib import Path

import config
import settings


def test_load_settings_merges_defaults_and_handles_missing_or_corrupt_file():
    assert settings.load_settings() == {
        "provider": config.PROVIDER,
        "model": config.PROVIDER_DEFAULT_MODELS[config.PROVIDER],
        "buy_rules": config.BUY_RULES,
        "sell_rules": config.SELL_RULES,
    }

    path = Path(settings.settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"provider":"openai","model":"custom-model"}', encoding="utf-8")

    loaded = settings.load_settings()

    assert loaded["provider"] == "openai"
    assert loaded["model"] == config.PROVIDER_DEFAULT_MODELS["openai"]
    assert loaded["buy_rules"] == config.BUY_RULES
    assert loaded["sell_rules"] == config.SELL_RULES

    path.write_text("{not json", encoding="utf-8")

    assert settings.load_settings()["provider"] == config.PROVIDER


def test_save_settings_round_trip_and_keeps_keys_out_of_json():
    settings.save_settings({
        "provider": "groq",
        "model": "ignored-model",
        "buy_rules": "buy from ui",
        "sell_rules": "sell from ui",
        "FMP_API_KEY": "must-not-be-saved",
    })

    assert settings.load_settings() == {
        "provider": "groq",
        "model": config.PROVIDER_DEFAULT_MODELS["groq"],
        "buy_rules": "buy from ui",
        "sell_rules": "sell from ui",
    }
    raw = json.loads(Path(settings.settings_path()).read_text(encoding="utf-8"))
    assert "FMP_API_KEY" not in raw


def test_save_settings_ignores_blocked_legacy_tmp_filename():
    path = Path(settings.settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "settings.json.tmp").mkdir()

    settings.save_settings({
        "provider": "openai",
        "model": "fresh-temp-model",
        "buy_rules": "buy",
        "sell_rules": "sell",
    })

    assert settings.load_settings()["model"] == config.PROVIDER_DEFAULT_MODELS["openai"]
    assert (path.parent / "settings.json.tmp").is_dir()


def test_model_is_derived_from_provider_to_avoid_stale_cross_provider_values():
    path = Path(settings.settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"provider":"deepseek","model":"claude-sonnet-4-6","buy_rules":"buy","sell_rules":"sell"}',
        encoding="utf-8",
    )

    loaded = settings.load_settings()

    assert loaded["provider"] == "deepseek"
    assert loaded["model"] == config.PROVIDER_DEFAULT_MODELS["deepseek"]


def test_save_api_keys_updates_env_without_clobbering_unrelated_lines(monkeypatch):
    env_path = Path(settings.user_env_path())
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(
        "# keep me\nOTHER=value\nFMP_API_KEY=old-fmp\nOPENAI_API_KEY=old-openai\n",
        encoding="utf-8",
    )

    settings.save_api_keys(
        provider="openai",
        fmp_api_key="new-fmp",
        provider_api_key="new-openai",
    )

    text = env_path.read_text(encoding="utf-8")
    assert "# keep me" in text
    assert "OTHER=value" in text
    assert "FMP_API_KEY=new-fmp" in text
    assert "OPENAI_API_KEY=new-openai" in text
    assert os.getenv("FMP_API_KEY") == "new-fmp"
    assert os.getenv("OPENAI_API_KEY") == "new-openai"


def test_validate_portfolio_columns_rejects_missing_required_columns():
    valid, message = settings.validate_portfolio_columns(["ticker", "qty"])

    assert not valid
    assert "ticker, qty, entry_price, entry_date" in message

    assert settings.validate_portfolio_columns(settings.PORTFOLIO_COLUMNS) == (True, "")
