"""Signal evaluation from prefetched market data."""

import json

from dotenv import load_dotenv

import config
from paths import executable_env_path, user_env_path
from settings import load_settings
from .llm import create_llm_client
from .tools import (
    get_analyst_estimates,
    get_analyst_rating,
    get_balance_sheet,
    get_cash_flow,
    get_earnings,
    get_financial_health,
    get_income_statement,
    get_key_metrics,
    get_performance,
    get_price_target,
    get_profile,
    get_quote,
    get_rsi,
    get_sma,
    get_technical_indicator,
    get_valuation_ratios,
)

load_dotenv()
load_dotenv(user_env_path(), override=False)
exe_env = executable_env_path()
if exe_env:
    load_dotenv(exe_env, override=False)

_TOOL_DISPATCH = {
    "get_quote": get_quote,
    "get_rsi": get_rsi,
    "get_sma": get_sma,
    "get_key_metrics": get_key_metrics,
    "get_valuation_ratios": get_valuation_ratios,
    "get_financial_health": get_financial_health,
    "get_income_statement": get_income_statement,
    "get_balance_sheet": get_balance_sheet,
    "get_cash_flow": get_cash_flow,
    "get_performance": get_performance,
    "get_profile": get_profile,
    "get_technical_indicator": get_technical_indicator,
    "get_price_target": get_price_target,
    "get_analyst_rating": get_analyst_rating,
    "get_analyst_estimates": get_analyst_estimates,
    "get_earnings": get_earnings,
}

_SIGNAL_CONTRACTS = {
    "BUY_EVAL": {
        "allowed": ("BUY", "SKIP"),
        "rules": (
            "- BUY  : the stock meets the user's entry criteria now\n"
            "- SKIP : the stock does not meet the user's entry criteria now; skip for now"
        ),
    },
    "SELL_EVAL": {
        "allowed": ("SELL", "HOLD"),
        "rules": (
            "- SELL : the stock meets the user's exit criteria now\n"
            "- HOLD : the stock does not meet the user's exit criteria now; continue holding"
        ),
    },
    "GENERAL": {
        "allowed": ("BUY", "SELL", "HOLD"),
        "rules": (
            "- BUY  : the stock meets the entry criteria\n"
            "- SELL : the stock meets the exit criteria\n"
            "- HOLD : the stock does not clearly meet entry or exit criteria"
        ),
    },
}

_BATCH_SYSTEM_PROMPT = """You are a rule-based investment decision support system for retail investors.

Your job is to evaluate multiple stocks against the user's stated rules and return structured signals.

INSTRUCTIONS:
1. Read the user's rules carefully.
2. Use only the fetched data supplied by the application. Do not request tools or invent missing data.
3. Evaluate each ticker independently against the relevant rule.
4. Return your result as a JSON array. The array must contain exactly one object for each input ticker, using exactly these five fields:

[
  {{
    "ticker": "<ticker>",
    "signal": "<{allowed_signals}>",
    "triggering_rule": "<The single user rule, quoted or closely paraphrased, that most directly drove this signal. For SKIP/HOLD, state which criterion was closest to being met and why it was not.>",
    "rationale": "<Explain what the key metric values mean in market terms, why they are or are not significant right now, and connect them to the signal. Three to four plain-English sentences. Do not just report pass/fail; explain what the numbers are telling the investor about the stock's current condition.>",
    "data_fetched": {{ "<metric_name>": <compact value>, ... }}
  }}
]

Rules:
{signal_rules}

Use only one of these signal values: {allowed_signals}.
The rationale must name the triggering_rule in prose.
Keep data_fetched compact and include only the metrics needed for the decision.

CRITICAL: Your entire response must be ONLY the JSON array.
No preamble, no explanation, no markdown, no bullet points, no text before or after the JSON.
Start your response with [ and end with ]. Nothing else.

USER RULES:
{rules}
"""

_BATCH_MAX_TOKENS = 8192


def evaluate_signals_from_data_batch(
    items: list[dict],
    rules: str,
    model: str = "claude-sonnet-4-6",
    evaluation_type: str = "GENERAL",
) -> list[dict]:
    """Evaluate multiple tickers from already-fetched data in one LLM call."""
    if not items:
        return []
    contract = _SIGNAL_CONTRACTS.get(evaluation_type)
    if not contract:
        return [
            _error(
                item["ticker"],
                f"Unsupported evaluation_type={evaluation_type!r}. Choose one of: BUY_EVAL, SELL_EVAL, GENERAL.",
            )
            for item in items
        ]
    allowed_signals = " | ".join(contract["allowed"])
    system = _BATCH_SYSTEM_PROMPT.format(
        rules=rules,
        allowed_signals=allowed_signals,
        signal_rules=contract["rules"],
    )
    settings = load_settings()
    provider = settings.get("provider") or getattr(config, "PROVIDER", "anthropic")
    temperature = settings.get("temperature")
    if model == "claude-sonnet-4-6":
        model = settings.get("model") or model
    provider_settings = getattr(config, "PROVIDER_SETTINGS", {}).get(provider)
    if not provider_settings:
        return [
            _error(
                item["ticker"],
                f"Unsupported PROVIDER={provider!r}. Choose one of: anthropic, openai, grok, groq, deepseek, gemini, cerebras.",
            )
            for item in items
        ]

    payload = [
        {
            "ticker": item["ticker"],
            "fetched_data": item["fetched_data"],
        }
        for item in items
    ]
    user_content = (
        "Evaluate these stocks independently.\n\n"
        f"FETCHED DATA JSON:\n{json.dumps(payload, sort_keys=True)}"
    )

    try:
        client = create_llm_client(
            provider=provider,
            model=model,
            system=system,
            user_content=user_content,
            provider_settings=provider_settings,
            tool_schemas=[],
            max_tokens=_BATCH_MAX_TOKENS,
            temperature=temperature,
        )
    except RuntimeError as exc:
        return [_error(item["ticker"], str(exc)) for item in items]

    response = client.next_step()
    if response.final_text is not None:
        return _parse_signal_batch_response(
            items=items,
            text=response.final_text,
            contract=contract,
            evaluation_type=evaluation_type,
            allowed_signals=allowed_signals,
        )
    if response.tool_calls is not None:
        return [
            _error(item["ticker"], "Agent requested tools even though data was already fetched")
            for item in items
        ]
    return [_error(item["ticker"], response.error or "Agent returned no response") for item in items]


def _parse_signal_batch_response(
    *,
    items: list[dict],
    text: str,
    contract: dict,
    evaluation_type: str,
    allowed_signals: str,
) -> list[dict]:
    text = text.strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end <= start:
        return [_error(item["ticker"], "Agent returned no JSON array") for item in items]
    try:
        parsed = json.loads(text[start:end])
    except json.JSONDecodeError:
        return [_error(item["ticker"], f"Could not parse agent response: {text[:300]}") for item in items]
    if not isinstance(parsed, list):
        return [_error(item["ticker"], "Agent returned JSON but not an array") for item in items]

    by_ticker = {
        str(row.get("ticker", "")).upper().strip(): row
        for row in parsed
        if isinstance(row, dict)
    }
    results = []
    for item in items:
        ticker = item["ticker"]
        row = by_ticker.get(ticker.upper().strip())
        if not row:
            results.append(_error(ticker, "Agent omitted this ticker from the batch response"))
            continue
        if row.get("signal") not in contract["allowed"]:
            results.append(_error(
                ticker,
                (
                    f"Agent returned invalid signal {row.get('signal')!r} "
                    f"for {evaluation_type}. Allowed signals: {allowed_signals}."
                ),
            ))
            continue
        triggering_rule = row.get("triggering_rule")
        # The model reports this rule; validation checks presence, not correctness.
        if not isinstance(triggering_rule, str) or not triggering_rule.strip():
            results.append(_error(ticker, "Agent omitted non-empty triggering_rule from the response"))
            continue
        if not isinstance(row.get("data_fetched"), dict):
            row["data_fetched"] = {}
        row["ticker"] = ticker
        results.append(row)
    return results


def _error(ticker: str, msg: str) -> dict:
    return {
        "ticker": ticker,
        "signal": "ERROR",
        "triggering_rule": "",
        "rationale": msg,
        "data_fetched": {},
    }
