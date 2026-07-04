"""Runtime-editable settings and app-data file helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

import config
from paths import seed_user_csv_defaults, user_data_file, user_env_path


SETTINGS_FILENAME = "settings.json"
SETTINGS_KEYS = ("provider", "model", "buy_rules", "sell_rules")
PORTFOLIO_COLUMNS = ["ticker", "qty", "entry_price", "entry_date"]
WATCHLIST_COLUMNS = ["ticker"]


def default_settings() -> dict:
    provider = config.PROVIDER
    return {
        "provider": provider,
        "model": default_model_for_provider(provider),
        "buy_rules": config.BUY_RULES,
        "sell_rules": config.SELL_RULES,
    }


def default_model_for_provider(provider: str) -> str:
    return config.PROVIDER_DEFAULT_MODELS.get(provider, config.MODEL)


def settings_path() -> str:
    return user_data_file(SETTINGS_FILENAME)


def load_settings() -> dict:
    """Read settings.json and merge it over config.py defaults."""
    settings = default_settings()
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return settings

    if not isinstance(data, dict):
        return settings

    for key in SETTINGS_KEYS:
        if key == "model":
            continue
        if key in data and isinstance(data[key], str):
            settings[key] = data[key]

    if settings["provider"] not in config.PROVIDER_SETTINGS:
        settings["provider"] = config.PROVIDER
    settings["model"] = default_model_for_provider(settings["provider"])
    return settings


def save_settings(values: dict) -> None:
    """Write non-secret settings to settings.json."""
    current = load_settings()
    provider = str(values.get("provider", current["provider"]))
    payload = {
        key: str(values.get(key, current[key]))
        for key in SETTINGS_KEYS
    }
    payload["provider"] = provider
    payload["model"] = default_model_for_provider(provider)
    if payload["provider"] not in config.PROVIDER_SETTINGS:
        raise ValueError(f"Unsupported provider: {payload['provider']}")

    path = Path(settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_env_values() -> dict[str, str]:
    """Read simple KEY=VALUE pairs from the app-data .env file."""
    values: dict[str, str] = {}
    try:
        lines = Path(user_env_path()).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values
    except OSError:
        return values

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def save_api_keys(
    *,
    provider: str,
    fmp_api_key: str | None = None,
    provider_api_key: str | None = None,
) -> None:
    """Update app-data .env keys without clobbering unrelated lines."""
    provider_settings = config.PROVIDER_SETTINGS.get(provider)
    if not provider_settings:
        raise ValueError(f"Unsupported provider: {provider}")

    updates: dict[str, str] = {}
    if fmp_api_key:
        updates["FMP_API_KEY"] = fmp_api_key
    if provider_api_key:
        updates[provider_settings["api_key_env"]] = provider_api_key

    if not updates:
        return

    path = Path(user_env_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []

    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key, _value = line.split("=", 1)
        key = key.strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)

    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")

    path.write_text("\n".join(output) + "\n", encoding="utf-8")
    load_dotenv(user_env_path(), override=True)


def user_csv_path(filename: str) -> str:
    seed_user_csv_defaults()
    return user_data_file(filename)


def _clean_ticker_column(column):
    return column.fillna("").astype(str).str.upper().str.strip()


def clean_watchlist_frame(df):
    """Return watchlist rows with usable tickers only."""
    cleaned = df[WATCHLIST_COLUMNS].copy()
    cleaned["ticker"] = _clean_ticker_column(cleaned["ticker"])
    return cleaned[cleaned["ticker"] != ""].reset_index(drop=True)


def clean_portfolio_frame(df):
    """Return portfolio rows with usable tickers only."""
    cleaned = df[PORTFOLIO_COLUMNS].copy()
    cleaned["ticker"] = _clean_ticker_column(cleaned["ticker"])
    return cleaned[cleaned["ticker"] != ""].reset_index(drop=True)


def validate_portfolio_columns(columns) -> tuple[bool, str]:
    missing = [column for column in PORTFOLIO_COLUMNS if column not in list(columns)]
    if missing:
        return False, f"Portfolio must include columns: {', '.join(PORTFOLIO_COLUMNS)}"
    return True, ""
