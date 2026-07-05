from __future__ import annotations

from agent.tool_planner import PlannedTool, plan_tools_for_rules


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
