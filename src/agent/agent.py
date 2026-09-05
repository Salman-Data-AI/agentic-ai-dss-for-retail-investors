"""Signal evaluation from prefetched market data."""

import json

from dotenv import load_dotenv

import config
from paths import executable_env_path, user_env_path
from settings import load_settings

from .deterministic_evaluator import BUY_EVALUATION, SELL_EVALUATION, evaluate_rule_set
from .llm import create_llm_client
from .metric_registry import METRIC_ALIASES
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

_BATCH_MAX_TOKENS = 8192

_RATIONALE_SYSTEM_PROMPT = """You are an investment decision support explainer for retail investors.

The application has already decided each signal deterministically from approved rules. Your job is rationale only.

Return your result as a JSON array with exactly one object per input ticker:
[
  {{
    "ticker": "<ticker>",
    "rationale": "<Three to four plain-English sentences explaining the deterministic signal
        using the supplied fetched data and triggering rule.>",
    "data_fetched": {{ "<metric_name>": <compact value>, ... }}
  }}
]

Do not change, reinterpret, or contradict the supplied signal or triggering_rule.
Temperature can affect wording only; it does not affect the signal.
Keep data_fetched compact and include only values relevant to the supplied decision.
Return ONLY the JSON array.
"""


def evaluate_signals_from_data_batch(
    items: list[dict],
    rules: str,
    compiled_rule_set: dict,
    model: str = "claude-sonnet-4-6",
    evaluation_type: str = "GENERAL",
    *,
    explanation_mode: bool = True,
) -> list[dict]:
    """Evaluate multiple tickers from already-fetched data with deterministic signals."""
    if not items:
        return []
    return _evaluate_with_deterministic_signals(
        items=items,
        model=model,
        evaluation_type=evaluation_type,
        compiled_rule_set=compiled_rule_set,
        explanation_mode=explanation_mode,
    )


def _evaluate_with_deterministic_signals(
    *,
    items: list[dict],
    model: str,
    evaluation_type: str,
    compiled_rule_set: dict,
    explanation_mode: bool,
) -> list[dict]:
    deterministic_type = {
        "BUY_EVAL": BUY_EVALUATION,
        "SELL_EVAL": SELL_EVALUATION,
    }.get(evaluation_type)
    if deterministic_type is None:
        return [
            _error(item["ticker"], f"Deterministic evaluation does not support evaluation_type={evaluation_type!r}.")
            for item in items
        ]

    deterministic_rows = []
    for item in items:
        evaluation = evaluate_rule_set(
            compiled_rule_set, _flatten_metrics(item.get("fetched_data", {})), deterministic_type
        )
        deterministic_rows.append(
            {
                "ticker": item["ticker"],
                "signal": evaluation["signal"],
                "triggering_rule": evaluation["triggering_rule"],
                "rationale": _format_deterministic_error(evaluation) if evaluation["error"] else "",
                "data_fetched": item.get("fetched_data", {}),
                "triggering_clauses": evaluation["triggering_clauses"],
                "clause_outcomes": evaluation["clause_outcomes"],
            }
        )

    if all(row["signal"] == "ERROR" for row in deterministic_rows):
        return deterministic_rows

    if not explanation_mode:
        return [
            {
                **row,
                "rationale": row["rationale"] if row["signal"] == "ERROR" else None,
            }
            for row in deterministic_rows
        ]

    settings = load_settings()
    provider = settings.get("provider") or getattr(config, "PROVIDER", "anthropic")
    temperature = settings.get("temperature")
    if model == "claude-sonnet-4-6":
        model = settings.get("model") or model
    provider_settings = getattr(config, "PROVIDER_SETTINGS", {}).get(provider)
    if not provider_settings:
        message = f"Unsupported PROVIDER={provider!r}. Choose one of: anthropic, openai, grok, groq, deepseek, gemini, cerebras."  # noqa: E501
        return [_merge_rationale_error(row, message) for row in deterministic_rows]

    payload = [
        {
            "ticker": row["ticker"],
            "signal": row["signal"],
            "triggering_rule": row["triggering_rule"],
            "fetched_data": row["data_fetched"],
            "clause_outcomes": row["clause_outcomes"],
        }
        for row in deterministic_rows
    ]
    user_content = (
        "Explain these deterministic rule decisions. Do not alter the supplied signal.\n\n"
        f"DECISIONS JSON:\n{json.dumps(payload, sort_keys=True)}"
    )
    try:
        client = create_llm_client(
            provider=provider,
            model=model,
            system=_RATIONALE_SYSTEM_PROMPT,
            user_content=user_content,
            provider_settings=provider_settings,
            tool_schemas=[],
            max_tokens=_BATCH_MAX_TOKENS,
            temperature=temperature,
        )
    except RuntimeError as exc:
        return [_merge_rationale_error(row, str(exc)) for row in deterministic_rows]

    response = client.next_step()
    if response.final_text is not None:
        return _parse_rationale_batch_response(deterministic_rows, response.final_text)
    if response.tool_calls is not None:
        return [
            _merge_rationale_error(row, "Agent requested tools even though data was already fetched")
            for row in deterministic_rows
        ]
    return [_merge_rationale_error(row, response.error or "Agent returned no response") for row in deterministic_rows]


def _parse_rationale_batch_response(deterministic_rows: list[dict], text: str) -> list[dict]:
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end <= start:
        return [_merge_rationale_error(row, "Agent returned no JSON array") for row in deterministic_rows]
    try:
        parsed = json.loads(text[start:end])
    except json.JSONDecodeError:
        return [
            _merge_rationale_error(row, f"Could not parse agent response: {text[:300]}") for row in deterministic_rows
        ]
    if not isinstance(parsed, list):
        return [_merge_rationale_error(row, "Agent returned JSON but not an array") for row in deterministic_rows]

    by_ticker = {str(row.get("ticker", "")).upper().strip(): row for row in parsed if isinstance(row, dict)}
    results = []
    for deterministic_row in deterministic_rows:
        row = by_ticker.get(deterministic_row["ticker"].upper().strip())
        if not row:
            results.append(
                _merge_rationale_error(deterministic_row, "Agent omitted this ticker from the batch response")
            )
            continue
        rationale = row.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            results.append(
                _merge_rationale_error(deterministic_row, "Agent omitted non-empty rationale from the response")
            )
            continue
        results.append(
            {
                **deterministic_row,
                "rationale": rationale,
                "data_fetched": deterministic_row["data_fetched"],
            }
        )
    return results


def _merge_rationale_error(row: dict, message: str) -> dict:
    if row["signal"] == "ERROR":
        return row
    return {
        **row,
        "rationale": f"{message} Deterministic signal remains {row['signal']}.",
    }


def _error(ticker: str, msg: str) -> dict:
    return {
        "ticker": ticker,
        "signal": "ERROR",
        "triggering_rule": "",
        "rationale": msg,
        "data_fetched": {},
    }


def _flatten_metrics(fetched_data: dict) -> dict:
    metrics = {}
    if not isinstance(fetched_data, dict):
        return metrics
    for value in fetched_data.values():
        if isinstance(value, dict):
            indicator = value.get("indicator")
            if indicator and "value" in value:
                key = "standard_deviation" if indicator == "standarddeviation" else str(indicator)
                metrics[key] = value["value"]
            _collect_metric_values(value, metrics)
    quote = fetched_data.get("get_quote") if isinstance(fetched_data.get("get_quote"), dict) else {}
    holding = fetched_data.get("holding") if isinstance(fetched_data.get("holding"), dict) else {}
    price = quote.get("price")
    entry_price = holding.get("entry_price")
    if _is_number(price) and _is_number(entry_price) and entry_price:
        metrics["gain_loss_pct"] = round(((price - entry_price) / entry_price) * 100, 4)
    week_52_low = quote.get("week_52_low")
    if _is_number(price) and _is_number(week_52_low) and week_52_low:
        metrics["price_above_52_week_low_pct"] = round(((price - week_52_low) / week_52_low) * 100, 4)
    week_52_high = quote.get("week_52_high")
    if _is_number(price) and _is_number(week_52_high) and week_52_high:
        metrics["price_below_52_week_high_pct"] = round(((week_52_high - price) / week_52_high) * 100, 4)
    profile = fetched_data.get("get_profile") if isinstance(fetched_data.get("get_profile"), dict) else {}
    volume = quote.get("volume")
    average_volume = profile.get("average_volume")
    if _is_number(volume) and _is_number(average_volume) and average_volume:
        metrics["volume_vs_average_pct"] = round(((volume - average_volume) / average_volume) * 100, 4)
    _add_metric_aliases(metrics)
    return metrics


def _add_metric_aliases(metrics: dict) -> None:
    for alias, canonical in METRIC_ALIASES.items():
        if alias not in metrics and canonical in metrics:
            metrics[alias] = metrics[canonical]
        if canonical not in metrics and alias in metrics:
            metrics[canonical] = metrics[alias]
    if "pe_ratio" not in metrics and "pe_ratio_ttm" in metrics:
        metrics["pe_ratio"] = metrics["pe_ratio_ttm"]
    if "pe_ratio_ttm" not in metrics and "pe_ratio" in metrics:
        metrics["pe_ratio_ttm"] = metrics["pe_ratio"]


def _collect_metric_values(value, metrics: dict) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if _is_number(nested):
                metrics[key] = nested
            elif isinstance(nested, dict):
                _collect_metric_values(nested, metrics)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_deterministic_error(evaluation: dict) -> str:
    details = []
    for outcome in evaluation.get("clause_outcomes", []):
        if outcome.get("status") != "error":
            continue
        phrase = outcome.get("user_phrase") or f"Clause {outcome.get('index')}"
        metric = outcome.get("bound_metric") or "unknown metric"
        reason = outcome.get("reason") or "could not be evaluated"
        details.append(f"{phrase} [{metric}]: {reason}")
    if not details:
        return evaluation.get("error") or "One or more clauses could not be evaluated."
    return f"{evaluation.get('error')} " + " ".join(details)
