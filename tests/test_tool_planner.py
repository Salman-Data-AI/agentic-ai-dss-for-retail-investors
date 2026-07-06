from __future__ import annotations

import config
from agent.tool_planner import PlannedTool, plan_tools_for_rules, plan_tools_with_diagnostics


def test_plan_tools_for_default_buy_rules():
    plan = plan_tools_for_rules("""
    Consider buying when RSI (14-day) is below 35, current price is within
    15% above the 52-week low, and PE ratio is below 25.
    """)

    assert plan == [
        PlannedTool("get_quote"),
        PlannedTool("get_rsi", {"period": 14}),
        PlannedTool("get_key_metrics"),
    ]


def test_plan_tools_falls_back_to_quote_for_unknown_rules():
    assert plan_tools_for_rules("avoid anything too weird") == [PlannedTool("get_quote")]


def test_plan_tools_with_diagnostics_flags_fallback_only():
    diagnostics = plan_tools_with_diagnostics("buy if the vibes are good")

    assert diagnostics.tools == [PlannedTool("get_quote")]
    assert diagnostics.fallback_only is True


def test_plan_tools_with_diagnostics_default_buy_rules_are_specific():
    diagnostics = plan_tools_with_diagnostics(config.BUY_RULES)

    assert diagnostics.fallback_only is False
    assert diagnostics.tools == [
        PlannedTool("get_quote"),
        PlannedTool("get_rsi", {"period": 14}),
        PlannedTool("get_key_metrics"),
    ]
