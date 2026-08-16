"""Compile plain-English rule text into validated deterministic rule sets."""

from __future__ import annotations

import json
import re
from typing import Any

import config

from .llm import create_llm_client
from .metric_registry import METRIC_REGISTRY, SUPPORTED_METRIC_KEYS, canonical_metric_key, metric_prompt_menu
from .rule_fingerprint import fingerprint_rule_inputs
from .rule_sets import validate_rule_set
from .tool_planner import plan_tools_for_rules
from .tool_schemas import TOOL_SCHEMA_VERSION

COMPILE_PROMPT_VERSION = "compile-prompt-v3"
_COMPILE_MAX_TOKENS = 4096

_COMPILE_SYSTEM_PROMPT = """You compile investor rule text into executable numeric metric clauses.

You are not deciding stock signals. You are only binding each user clause to one supported metric key,
one numeric comparison operator, and one numeric threshold.

Return ONLY a JSON object with exactly this shape:
{{
  "buy_clauses": [
    {{"user_phrase": "<original clause>", "bound_metric": "<metric key>",
    "operator": "<|<=|>|>=|==|!=", "threshold": 0}}
  ],
  "sell_clauses": [
    {{"user_phrase": "<original clause>", "bound_metric": "<metric key>",
    "operator": "<|<=|>|>=|==|!=", "threshold": 0}}
  ],
  "unbound_clauses": [
    {{"side": "buy|sell", "user_phrase": "<original clause>", "reason": "<why no supported metric fits>"}}
  ]
}}

Rules:
- Use only the supported metric keys described in this metric registry:
{metric_registry}
- Do not invent metric keys.
- Do not silently drop clauses.
- If a clause cannot be expressed as one supported numeric metric comparison, put it in unbound_clauses.
- Percent thresholds are numeric percentages for *_pct metrics.
- The compile step is pure closed-menu classification; provider and model are excluded from the approval fingerprint.
"""


def combined_rule_text(buy_rules: str, sell_rules: str) -> str:
    """Return the exact rule text payload used for compile fingerprinting."""
    return f"BUY_RULES:\n{buy_rules}\n\nSELL_RULES:\n{sell_rules}"


def current_rule_fingerprint(buy_rules: str, sell_rules: str) -> str:
    return fingerprint_rule_inputs(
        combined_rule_text(buy_rules, sell_rules),
        TOOL_SCHEMA_VERSION,
        COMPILE_PROMPT_VERSION,
    )


def compile_rule_text(
    *,
    buy_rules: str,
    sell_rules: str,
    provider: str,
    model: str,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Compile and validate rule text, returning either compiled data or a structured block."""
    fingerprint = current_rule_fingerprint(buy_rules, sell_rules)
    deterministic = compile_deterministic_rule_text(buy_rules=buy_rules, sell_rules=sell_rules)
    if not deterministic["remaining_buy_clauses"] and not deterministic["remaining_sell_clauses"]:
        return _validated_result(
            deterministic["rule_set"],
            fingerprint=fingerprint,
            compiler="deterministic",
            buy_rules=buy_rules,
            sell_rules=sell_rules,
        )

    provider_settings = getattr(config, "PROVIDER_SETTINGS", {}).get(provider)
    if not provider_settings:
        return _blocked(
            "unsupported_provider",
            f"Unsupported provider: {provider}",
            fingerprint=fingerprint,
        )

    system = _COMPILE_SYSTEM_PROMPT.format(metric_registry=metric_prompt_menu())
    user_content = (
        "Compile only these remaining investor clauses. Deterministic clauses have already been bound.\n\n"
        f"REMAINING BUY CLAUSES:\n{_format_remaining_clauses(deterministic['remaining_buy_clauses'])}\n\n"
        f"REMAINING SELL CLAUSES:\n{_format_remaining_clauses(deterministic['remaining_sell_clauses'])}\n"
    )

    try:
        client = create_llm_client(
            provider=provider,
            model=model,
            system=system,
            user_content=user_content,
            provider_settings=provider_settings,
            tool_schemas=[],
            max_tokens=_COMPILE_MAX_TOKENS,
            temperature=temperature,
        )
    except RuntimeError as exc:
        return _blocked("provider_error", str(exc), fingerprint=fingerprint)

    response = client.next_step()
    if response.tool_calls is not None:
        return _blocked(
            "compile_requested_tools", "Compile requested tools; expected JSON only.", fingerprint=fingerprint
        )
    if response.error:
        return _blocked("provider_error", response.error, fingerprint=fingerprint)
    if response.final_text is None:
        return _blocked("empty_response", "Compile returned no response.", fingerprint=fingerprint)

    parsed = parse_compiled_rule_response(response.final_text, fingerprint=fingerprint)
    if not parsed["ok"]:
        return parsed
    combined_rule_set = {
        "buy_clauses": deterministic["rule_set"]["buy_clauses"] + parsed["rule_set"]["buy_clauses"],
        "sell_clauses": deterministic["rule_set"]["sell_clauses"] + parsed["rule_set"]["sell_clauses"],
    }
    return _validated_result(
        combined_rule_set,
        fingerprint=fingerprint,
        compiler="hybrid",
        buy_rules=buy_rules,
        sell_rules=sell_rules,
    )


def compile_deterministic_rule_text(*, buy_rules: str, sell_rules: str) -> dict[str, Any]:
    buy_result = _compile_deterministic_clauses(buy_rules, side="buy")
    sell_result = _compile_deterministic_clauses(sell_rules, side="sell")
    return {
        "rule_set": {
            "buy_clauses": buy_result["compiled"],
            "sell_clauses": sell_result["compiled"],
        },
        "remaining_buy_clauses": buy_result["remaining"],
        "remaining_sell_clauses": sell_result["remaining"],
    }


def parse_compiled_rule_response(text: str, *, fingerprint: str) -> dict[str, Any]:
    """Strictly parse and validate a compile response."""
    try:
        candidate = _extract_json_object(text)
    except ValueError as exc:
        return _blocked("parse_error", str(exc), fingerprint=fingerprint)

    candidate = _repair_supported_unbound_clauses(candidate)
    unbound = candidate.get("unbound_clauses", [])
    if not isinstance(unbound, list):
        return _blocked("malformed_unbound_clauses", "unbound_clauses must be a list.", fingerprint=fingerprint)
    if unbound:
        return _blocked(
            "unbound_clauses",
            "One or more clauses could not be bound to supported metrics.",
            fingerprint=fingerprint,
            unbound_clauses=unbound,
        )

    rule_set = _canonicalize_rule_set(
        {
            "buy_clauses": candidate.get("buy_clauses"),
            "sell_clauses": candidate.get("sell_clauses"),
        }
    )
    return _validated_result(rule_set, fingerprint=fingerprint, compiler="llm")


def _compile_deterministic_clauses(rule_text: str, *, side: str) -> dict[str, list]:
    compiled = []
    remaining = []
    for phrase in _split_rule_clauses(rule_text):
        clause = _bind_common_clause(phrase, side=side)
        if clause is None:
            remaining.append(phrase)
        else:
            compiled.append(clause)
    return {"compiled": compiled, "remaining": remaining}


def _split_rule_clauses(rule_text: str) -> list[str]:
    clauses = []
    for raw_line in rule_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("-", "*", "•")):
            clauses.append(line.lstrip("-*•").strip())
    if clauses:
        return clauses
    stripped = rule_text.strip()
    return [stripped] if stripped else []


def _bind_common_clause(phrase: str, *, side: str) -> dict[str, Any] | None:
    normalized = phrase.lower()
    number = _comparison_number(normalized)

    special_clause = _bind_special_reference_clause(phrase, normalized)
    if special_clause is not None:
        return special_clause

    if ("rsi" in normalized or "relative strength index" in normalized) and number is not None:
        operator = _operator_from_text(normalized)
        if operator:
            return _clause(phrase, "rsi", operator, number)

    if _mentions_pe_ratio(normalized) and number is not None:
        operator = _operator_from_text(normalized)
        if operator:
            return _clause(phrase, "pe_ratio", operator, number)

    if _mentions_positive_eps(normalized):
        return _clause(phrase, "eps_ttm", ">", 0)

    if "52" in normalized and "low" in normalized and "price" in normalized and number is not None:
        if "within" in normalized or "above" in normalized or "near" in normalized:
            return _clause(phrase, "price_above_52_week_low_pct", "<=", number)

    if "52" in normalized and "high" in normalized and "price" in normalized and number is not None:
        if "within" in normalized or "below" in normalized or "near" in normalized:
            return _clause(phrase, "price_below_52_week_high_pct", "<=", number)

    if side == "sell":
        entry_price_clause = _bind_supported_unbound_clause({"side": side, "user_phrase": phrase})
        if entry_price_clause:
            return entry_price_clause

    return None


def _bind_special_reference_clause(phrase: str, normalized: str) -> dict[str, Any] | None:
    number = _comparison_number(normalized)

    if "volume" in normalized and "average" in normalized:
        if any(token in normalized for token in ("above", "greater than", "more than", "over", ">")):
            return _clause(phrase, "volume_vs_average_pct", ">", number if number is not None else 0)
        if any(token in normalized for token in ("below", "less than", "under", "<")):
            threshold = -(number if number is not None else 0)
            return _clause(phrase, "volume_vs_average_pct", "<", threshold)

    if "dropped" in normalized and "today" in normalized and number is not None:
        return _clause(phrase, "change_pct", "<", -abs(number))

    if "52" in normalized and "price" in normalized:
        return None
    if "entry price" in normalized and "current price" in normalized:
        return None

    if "positive" in normalized:
        for token, metric_key in (
            ("net income", "net_income"),
            ("operating cash flow", "operating_cash_flow"),
            ("buyback", "common_stock_repurchased"),
            ("buybacks", "common_stock_repurchased"),
        ):
            if token in normalized:
                return _clause(phrase, metric_key, ">", 0)

    metric_key = _metric_key_from_text(normalized)
    if metric_key is None:
        return None

    if "negative" in normalized:
        return _clause(phrase, metric_key, "<", 0)
    if "positive" in normalized:
        return _clause(phrase, metric_key, ">", 0)

    if number is None:
        return None

    operator = _operator_from_text(normalized)
    if operator:
        return _clause(phrase, metric_key, operator, number)
    return None


def _metric_key_from_text(text: str) -> str | None:
    bindings = (
        (("sma", "simple moving average"), "sma"),
        (("ema", "exponential moving average"), "ema"),
        (("adx",), "adx"),
        (("williams",), "williams"),
        (("standard deviation",), "standard_deviation"),
        (("current price", "price"), "price"),
        (("market cap", "market capitalization", "large-cap", "large cap"), "market_cap"),
        (("p/b", "price to book", "price-to-book"), "price_to_book_ttm"),
        (("p/s", "price to sales", "price-to-sales"), "price_to_sales_ttm"),
        (("peg",), "peg_ratio_ttm"),
        (("debt-to-equity", "debt to equity"), "debt_to_equity_ttm"),
        (("current ratio",), "current_ratio_ttm"),
        (("quick ratio",), "quick_ratio_ttm"),
        (("interest coverage",), "interest_coverage_ttm"),
        (("gross margin",), "gross_profit_margin_ttm"),
        (("operating margin",), "operating_profit_margin_ttm"),
        (("net margin",), "net_profit_margin_ttm"),
        (("roe", "return on equity"), "return_on_equity_ttm"),
        (("roa", "return on assets"), "return_on_assets_ttm"),
        (("roic", "return on invested capital"), "return_on_invested_capital_ttm"),
        (("ev/ebitda",), "ev_to_ebitda_ttm"),
        (("fcf yield", "free cash flow yield"), "free_cash_flow_yield_ttm"),
        (("earnings yield",), "earnings_yield_ttm"),
        (("net debt/ebitda", "net debt to ebitda"), "net_debt_to_ebitda_ttm"),
        (("graham",), "graham_number_ttm"),
        (("annual revenue", "revenue"), "revenue"),
        (("ebitda",), "ebitda"),
        (("operating income",), "operating_income"),
        (("net income",), "net_income"),
        (("cash and short-term investments", "cash and short term investments"), "cash_and_short_term_investments"),
        (("operating cash flow",), "operating_cash_flow"),
        (("capex", "capital expenditure"), "capital_expenditures"),
        (("beta",), "beta"),
        (("average volume",), "average_volume"),
        (("last dividend", "dividend"), "last_dividend"),
        (("consensus target",), "target_consensus"),
        (("median target",), "target_median"),
        (("analyst score", "overall score"), "overall_score"),
        (("forecast eps", "expected eps"), "eps_avg"),
        (("forecast revenue", "expected revenue"), "revenue_avg"),
    )
    for tokens, metric_key in bindings:
        if any(token in text for token in tokens):
            return metric_key

    return _return_metric_key_from_text(text)


def _return_metric_key_from_text(text: str) -> str | None:
    horizons = (
        ("1d", "return_1d"),
        ("5d", "return_5d"),
        ("1m", "return_1m"),
        ("3m", "return_3m"),
        ("6m", "return_6m"),
        ("ytd", "return_ytd"),
        ("year-to-date", "return_ytd"),
        ("1y", "return_1y"),
        ("3y", "return_3y"),
        ("5y", "return_5y"),
    )
    if "return" not in text and "up more than" not in text:
        return None
    for token, metric_key in horizons:
        if token in text:
            return metric_key
    return None


def _mentions_pe_ratio(text: str) -> bool:
    return any(token in text for token in ("pe ratio", "p/e", "price to earnings", "price-to-earnings")) or bool(
        re.search(r"\bpe\b", text)
    )


def _mentions_positive_eps(text: str) -> bool:
    return ("eps" in text or "earnings per share" in text) and any(
        token in text for token in ("positive", "above 0", "> 0", "greater than 0")
    )


def _operator_from_text(text: str) -> str | None:
    if any(token in text for token in ("below", "less than", "under", "dropped more than", "<")):
        return "<"
    if any(
        token in text for token in ("above", "greater than", "more than", "over", "expanded above", "up more than", ">")
    ):
        return ">"
    return None


def _first_number(text: str) -> float | None:
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*(billion|million|trillion|%)?", text)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit == "million":
        value *= 1_000_000
    elif unit == "billion":
        value *= 1_000_000_000
    elif unit == "trillion":
        value *= 1_000_000_000_000
    return int(value) if value.is_integer() else value


def _comparison_number(text: str) -> float | None:
    for pattern in (
        r"(?:below|less than|under|above|greater than|more than|over|expanded above|within|up more than|dropped more than)[^\d-]+(-?\d+(?:\.\d+)?)\s*(billion|million|trillion|%)?",  # noqa: E501
        r"(?:<|>)\s*(-?\d+(?:\.\d+)?)\s*(billion|million|trillion|%)?",
    ):
        match = re.search(pattern, text)
        if match:
            value = float(match.group(1))
            unit = match.group(2)
            if unit == "million":
                value *= 1_000_000
            elif unit == "billion":
                value *= 1_000_000_000
            elif unit == "trillion":
                value *= 1_000_000_000_000
            return int(value) if value.is_integer() else value
    return _first_number(text)


def _clause(phrase: str, metric_key: str, operator: str, threshold: float) -> dict[str, Any]:
    return {
        "user_phrase": phrase,
        "bound_metric": canonical_metric_key(metric_key),
        "operator": operator,
        "threshold": threshold,
    }


def _format_remaining_clauses(clauses: list[str]) -> str:
    if not clauses:
        return "(none)"
    return "\n".join(f"- {clause}" for clause in clauses)


def _validated_result(
    rule_set: dict[str, Any],
    *,
    fingerprint: str,
    compiler: str,
    buy_rules: str | None = None,
    sell_rules: str | None = None,
) -> dict[str, Any]:
    validation = validate_rule_set(rule_set, set(SUPPORTED_METRIC_KEYS))
    if not validation["valid"]:
        return _blocked(
            "validation_error",
            "Compiled rule set did not pass validation.",
            fingerprint=fingerprint,
            validation=validation,
        )
    if buy_rules is not None and sell_rules is not None:
        source_validation = _validate_rule_sources(rule_set, buy_rules=buy_rules, sell_rules=sell_rules)
        if not source_validation["valid"]:
            return _blocked(
                "source_validation_error",
                "Compiled rule set requires metrics that the current tool plan does not produce.",
                fingerprint=fingerprint,
                validation=source_validation,
            )

    return {
        "ok": True,
        "rule_set": rule_set,
        "fingerprint": fingerprint,
        "tool_schema_version": TOOL_SCHEMA_VERSION,
        "prompt_version": COMPILE_PROMPT_VERSION,
        "compiler": compiler,
        "structured_output": "prompt-enforced JSON with strict parse and validation",
    }


def _validate_rule_sources(rule_set: dict[str, Any], *, buy_rules: str, sell_rules: str) -> dict[str, Any]:
    problems = []
    plans = {
        "buy_clauses": {tool.name for tool in plan_tools_for_rules(buy_rules)},
        "sell_clauses": {tool.name for tool in plan_tools_for_rules(sell_rules)},
    }
    for list_key, planned_tools in plans.items():
        evaluation_type = "SELL_EVAL" if list_key == "sell_clauses" else "BUY_EVAL"
        for index, clause in enumerate(rule_set.get(list_key, [])):
            if not isinstance(clause, dict):
                continue
            metric_key = clause.get("bound_metric")
            metric = METRIC_REGISTRY.get(metric_key)
            if not metric:
                continue
            if evaluation_type not in metric["evaluation_types"]:
                problems.append(
                    {
                        "path": f"{list_key}[{index}].bound_metric",
                        "message": f"{metric_key} is not valid for {evaluation_type}.",
                    }
                )
            produced_by = set(metric["produced_by"]) - {"holding"}
            if metric.get("requires_all_sources") and not produced_by.issubset(planned_tools):
                problems.append(
                    {
                        "path": f"{list_key}[{index}].bound_metric",
                        "message": (
                            f"{metric_key} requires all of {sorted(produced_by)}, "
                            f"but planned tools are {sorted(planned_tools)}."
                        ),
                    }
                )
            elif produced_by and not produced_by.intersection(planned_tools):
                problems.append(
                    {
                        "path": f"{list_key}[{index}].bound_metric",
                        "message": (
                            f"{metric_key} requires one of {sorted(produced_by)}, "
                            f"but planned tools are {sorted(planned_tools)}."
                        ),
                    }
                )
    return {"valid": not problems, "problems": problems}


def _canonicalize_rule_set(rule_set: dict[str, Any]) -> dict[str, Any]:
    canonical = {"buy_clauses": [], "sell_clauses": []}
    for key in ("buy_clauses", "sell_clauses"):
        clauses = rule_set.get(key)
        if not isinstance(clauses, list):
            canonical[key] = clauses
            continue
        for clause in clauses:
            if not isinstance(clause, dict):
                canonical[key].append(clause)
                continue
            updated = dict(clause)
            metric_key = updated.get("bound_metric")
            if isinstance(metric_key, str):
                updated["bound_metric"] = canonical_metric_key(metric_key)
            canonical[key].append(updated)
    return canonical


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError("Compile returned no JSON object.")
    try:
        parsed = json.loads(stripped[start:end])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse compile JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Compile JSON must be an object.")
    return parsed


def _repair_supported_unbound_clauses(candidate: dict[str, Any]) -> dict[str, Any]:
    """Bind supported common clauses even if the model marked them unbound."""
    unbound = candidate.get("unbound_clauses", [])
    if not isinstance(unbound, list) or not unbound:
        return candidate

    repaired = dict(candidate)
    repaired_unbound = []
    sell_clauses = list(repaired.get("sell_clauses") or [])
    buy_clauses = list(repaired.get("buy_clauses") or [])

    for clause in unbound:
        bound_clause = _bind_supported_unbound_clause(clause)
        if bound_clause is None:
            repaired_unbound.append(clause)
            continue
        side = str(clause.get("side", "")).lower().strip() if isinstance(clause, dict) else ""
        if side == "sell":
            sell_clauses.append(bound_clause)
        elif side == "buy":
            buy_clauses.append(bound_clause)
        else:
            repaired_unbound.append(clause)

    repaired["buy_clauses"] = buy_clauses
    repaired["sell_clauses"] = sell_clauses
    repaired["unbound_clauses"] = repaired_unbound
    return repaired


def _bind_supported_unbound_clause(clause: Any) -> dict[str, Any] | None:
    if not isinstance(clause, dict):
        return None
    phrase = clause.get("user_phrase")
    if not isinstance(phrase, str):
        return None
    normalized = phrase.lower()
    if "entry price" not in normalized or "current price" not in normalized:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", normalized)
    if not match:
        return None
    threshold = float(match.group(1))
    if "above" in normalized or "gain" in normalized or "profit" in normalized:
        operator = ">"
    elif "below" in normalized or "loss" in normalized or "stop" in normalized:
        operator = "<"
        threshold = -threshold
    else:
        return None
    return {
        "user_phrase": phrase,
        "bound_metric": "gain_loss_pct",
        "operator": operator,
        "threshold": threshold,
    }


def _blocked(
    code: str,
    message: str,
    *,
    fingerprint: str,
    unbound_clauses: list | None = None,
    validation: dict | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "code": code,
        "message": message,
        "fingerprint": fingerprint,
        "unbound_clauses": unbound_clauses or [],
        "validation": validation,
        "metrics_reference": "Dashboard Metrics Reference tab",
    }
