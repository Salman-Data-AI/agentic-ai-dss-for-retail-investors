"""
Streamlit dashboard — Agentic DSS for Retail Investors.
Tab 1: Latest run with progressive disclosure cards.
Tab 2: History — filtered table, requires at least one filter before loading data.
Tab 3: Metrics Reference - static help for writing plain-English rules.
Tab 4: Settings - editable provider, rules, keys, watchlist, and portfolio.
Run: streamlit run dashboard/app.py  (from inside src/)
"""

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from main import run_analysis
from dashboard.logic import build_history_rows, split_signal_groups
from agent.tools import get_fmp_request_count
from settings import (
    PORTFOLIO_COLUMNS,
    WATCHLIST_COLUMNS,
    clean_portfolio_frame,
    clean_watchlist_frame,
    load_settings,
    read_env_values,
    save_api_keys,
    save_settings,
    user_csv_path,
    validate_portfolio_columns,
)
from paths import user_data_dir
from database import (
    read_latest_signals,
    read_filtered_signals,
    read_run_dates,
    read_tickers,
)

_METRIC_REFERENCE = [
    {
        "category": "Technical indicators",
        "metric": "RSI",
        "source_tool": "get_rsi",
        "measures": "Momentum oscillator on a 0-100 scale.",
        "rule_phrasing": '"RSI below 35" / "RSI above 70"',
        "interpretation": "Commonly used bands: below 30 is oversold; above 70 is overbought.",
        "snapshot_value": "AAPL snapshot: RSI 60.26 as of 2026-07-02",
    },
    {
        "category": "Technical indicators",
        "metric": "SMA",
        "source_tool": "get_sma",
        "measures": "Simple moving average of price for trend context.",
        "rule_phrasing": '"price above its 50-day SMA"',
        "interpretation": "Price above the SMA can indicate an uptrend context.",
        "snapshot_value": "AAPL snapshot: SMA 293.52 vs price 308.63",
    },
    {
        "category": "Technical indicators",
        "metric": "EMA",
        "source_tool": "get_technical_indicator",
        "measures": "Exponential moving average that weights recent prices more heavily.",
        "rule_phrasing": '"price above its 20-day EMA"',
        "interpretation": "Reacts faster than SMA to recent moves.",
        "snapshot_value": "AAPL snapshot: EMA 294.42 as of 2026-07-02",
    },
    {
        "category": "Technical indicators",
        "metric": "ADX",
        "source_tool": "get_technical_indicator",
        "measures": "Trend strength on a 0-100 scale.",
        "rule_phrasing": '"ADX above 25"',
        "interpretation": "Commonly used band: above 25 can indicate a strong trend.",
        "snapshot_value": "AAPL snapshot: ADX 23.74 as of 2026-07-02",
    },
    {
        "category": "Technical indicators",
        "metric": "Williams %R",
        "source_tool": "get_technical_indicator",
        "measures": "Momentum oscillator on a -100 to 0 scale.",
        "rule_phrasing": '"Williams %R below -80"',
        "interpretation": "Commonly used bands: below -80 is oversold; above -20 is overbought.",
        "snapshot_value": "AAPL snapshot: -2.21 as of 2026-07-02",
    },
    {
        "category": "Technical indicators",
        "metric": "Standard deviation",
        "source_tool": "get_technical_indicator",
        "measures": "Price volatility over the selected lookback period.",
        "rule_phrasing": '"standard deviation is elevated"',
        "interpretation": "Higher values suggest more volatile price movement.",
        "snapshot_value": "AAPL snapshot: 7.99 as of 2026-07-02",
    },
    {
        "category": "Price & quote",
        "metric": "Current price",
        "source_tool": "get_quote",
        "measures": "Latest quoted stock price.",
        "rule_phrasing": '"price near the 52-week low"',
        "interpretation": "Useful for price-level and distance-from-range rules.",
        "snapshot_value": "AAPL snapshot: 308.63",
    },
    {
        "category": "Price & quote",
        "metric": "Day change %",
        "source_tool": "get_quote",
        "measures": "Percent change on the day.",
        "rule_phrasing": '"price dropped more than 3% today"',
        "interpretation": "Shows same-day movement, not a longer-term trend.",
        "snapshot_value": "AAPL snapshot: +4.84%",
    },
    {
        "category": "Price & quote",
        "metric": "52-week high",
        "source_tool": "get_quote",
        "measures": "Highest price in the past year.",
        "rule_phrasing": '"price within 5% of its 52-week high"',
        "interpretation": "Useful for breakout, momentum, or overextension rules.",
        "snapshot_value": "AAPL snapshot: 317.40",
    },
    {
        "category": "Price & quote",
        "metric": "52-week low",
        "source_tool": "get_quote",
        "measures": "Lowest price in the past year.",
        "rule_phrasing": '"price near its 52-week low"',
        "interpretation": "Useful for value, drawdown, or mean-reversion rules.",
        "snapshot_value": "AAPL snapshot: 201.50",
    },
    {
        "category": "Price & quote",
        "metric": "Volume",
        "source_tool": "get_quote",
        "measures": "Shares traded.",
        "rule_phrasing": '"volume above average"',
        "interpretation": "Can indicate trading activity or liquidity.",
        "snapshot_value": "AAPL snapshot: 71,897,697",
    },
    {
        "category": "Price & quote",
        "metric": "Market cap",
        "source_tool": "get_quote",
        "measures": "Company size by market value.",
        "rule_phrasing": '"market cap above 10 billion"',
        "interpretation": "Useful for size filters such as large-cap only.",
        "snapshot_value": "AAPL snapshot: 4.53T",
    },
    {
        "category": "Price & quote",
        "metric": "Company name",
        "source_tool": "get_quote",
        "measures": "Display name for the ticker.",
        "rule_phrasing": "(context only)",
        "interpretation": "Used for display context rather than threshold rules.",
        "snapshot_value": "AAPL snapshot: Apple Inc.",
    },
    {
        "category": "Valuation",
        "metric": "PE ratio",
        "source_tool": "get_key_metrics / get_valuation_ratios",
        "measures": "Price relative to earnings.",
        "rule_phrasing": '"PE below 25"',
        "interpretation": "Lower can mean cheaper, depending on business context.",
        "snapshot_value": "AAPL snapshot: 37.23",
    },
    {
        "category": "Valuation",
        "metric": "EPS (trailing)",
        "source_tool": "get_key_metrics",
        "measures": "Earnings per share.",
        "rule_phrasing": '"positive EPS"',
        "interpretation": "Positive EPS means the company is profitable on this measure.",
        "snapshot_value": "AAPL snapshot: 8.33",
    },
    {
        "category": "Valuation",
        "metric": "P/B",
        "source_tool": "get_valuation_ratios",
        "measures": "Price to book value.",
        "rule_phrasing": '"P/B below 3"',
        "interpretation": "Lower can mean cheaper relative to assets.",
        "snapshot_value": "AAPL snapshot: 42.63",
    },
    {
        "category": "Valuation",
        "metric": "P/S",
        "source_tool": "get_valuation_ratios",
        "measures": "Price to sales.",
        "rule_phrasing": '"P/S below 5"',
        "interpretation": "Lower can mean cheaper relative to revenue.",
        "snapshot_value": "AAPL snapshot: 10.04",
    },
    {
        "category": "Valuation",
        "metric": "PEG",
        "source_tool": "get_valuation_ratios",
        "measures": "PE ratio adjusted for growth.",
        "rule_phrasing": '"PEG below 1.5"',
        "interpretation": "Near or below 1 is often viewed as reasonable.",
        "snapshot_value": "AAPL snapshot: 1.29",
    },
    {
        "category": "Valuation",
        "metric": "Debt-to-equity",
        "source_tool": "get_valuation_ratios",
        "measures": "Leverage compared with equity.",
        "rule_phrasing": '"debt-to-equity below 1"',
        "interpretation": "Lower values usually indicate less leverage.",
        "snapshot_value": "AAPL snapshot: 0.80",
    },
    {
        "category": "Valuation",
        "metric": "Current ratio",
        "source_tool": "get_valuation_ratios",
        "measures": "Short-term liquidity.",
        "rule_phrasing": '"current ratio above 1.5"',
        "interpretation": "Above 1 suggests current assets cover current liabilities.",
        "snapshot_value": "AAPL snapshot: 1.07",
    },
    {
        "category": "Valuation",
        "metric": "Quick ratio",
        "source_tool": "get_valuation_ratios",
        "measures": "Liquidity excluding inventory.",
        "rule_phrasing": '"quick ratio above 1"',
        "interpretation": "A stricter short-term liquidity test.",
        "snapshot_value": "AAPL snapshot: 1.02",
    },
    {
        "category": "Valuation",
        "metric": "Interest coverage",
        "source_tool": "get_valuation_ratios",
        "measures": "Ability to pay interest expense.",
        "rule_phrasing": '"interest coverage above 3"',
        "interpretation": "Higher values suggest safer debt servicing.",
        "snapshot_value": "AAPL snapshot: 0.00",
    },
    {
        "category": "Valuation",
        "metric": "Margins",
        "source_tool": "get_valuation_ratios",
        "measures": "Profitability margins such as gross, operating, and net margin.",
        "rule_phrasing": '"gross margin above 40%"',
        "interpretation": "Higher margins mean more profit retained per sale.",
        "snapshot_value": "AAPL snapshot: gross 47.86%, operating 32.64%, net 27.15%",
    },
    {
        "category": "Financial health / quality",
        "metric": "ROE",
        "source_tool": "get_financial_health",
        "measures": "Return on equity.",
        "rule_phrasing": '"ROE above 15%"',
        "interpretation": "Higher values can indicate efficient use of shareholder equity.",
        "snapshot_value": "AAPL snapshot: 146.69%",
    },
    {
        "category": "Financial health / quality",
        "metric": "ROA",
        "source_tool": "get_financial_health",
        "measures": "Return on assets.",
        "rule_phrasing": '"ROA above 8%"',
        "interpretation": "Higher values can indicate efficient use of assets.",
        "snapshot_value": "AAPL snapshot: 33.03%",
    },
    {
        "category": "Financial health / quality",
        "metric": "ROIC",
        "source_tool": "get_financial_health",
        "measures": "Return on invested capital.",
        "rule_phrasing": '"ROIC above 10%"',
        "interpretation": "Higher values can indicate strong capital efficiency.",
        "snapshot_value": "AAPL snapshot: 49.57%",
    },
    {
        "category": "Financial health / quality",
        "metric": "EV/EBITDA",
        "source_tool": "get_financial_health",
        "measures": "Enterprise value compared with EBITDA.",
        "rule_phrasing": '"EV/EBITDA below 15"',
        "interpretation": "Lower values can indicate cheaper enterprise valuation.",
        "snapshot_value": "AAPL snapshot: 28.57",
    },
    {
        "category": "Financial health / quality",
        "metric": "Free-cash-flow yield",
        "source_tool": "get_financial_health",
        "measures": "Free cash flow relative to value.",
        "rule_phrasing": '"FCF yield above 4%"',
        "interpretation": "Higher values can indicate stronger cash generation relative to price.",
        "snapshot_value": "AAPL snapshot: 2.85%",
    },
    {
        "category": "Financial health / quality",
        "metric": "Earnings yield",
        "source_tool": "get_financial_health",
        "measures": "Earnings relative to price.",
        "rule_phrasing": '"earnings yield above 5%"',
        "interpretation": "Higher values can indicate more earnings per dollar of price.",
        "snapshot_value": "AAPL snapshot: 2.70%",
    },
    {
        "category": "Financial health / quality",
        "metric": "Net debt/EBITDA",
        "source_tool": "get_financial_health",
        "measures": "Leverage compared with earnings.",
        "rule_phrasing": '"net debt/EBITDA below 3"',
        "interpretation": "Lower values suggest lower debt burden.",
        "snapshot_value": "AAPL snapshot: 0.30",
    },
    {
        "category": "Financial health / quality",
        "metric": "Graham number",
        "source_tool": "get_financial_health",
        "measures": "Value-investing benchmark price.",
        "rule_phrasing": '"price below the Graham number"',
        "interpretation": "Used as a conservative value reference, not a guaranteed fair value.",
        "snapshot_value": "AAPL snapshot: 36.84",
    },
    {
        "category": "Annual financial statements",
        "metric": "Revenue, gross profit, EBITDA, operating income, net income, EPS, diluted EPS, fiscal year",
        "source_tool": "get_income_statement",
        "measures": "Latest annual income statement values.",
        "rule_phrasing": '"annual revenue is growing" / "positive annual net income"',
        "interpretation": "Annual fundamentals only; quarterly fundamentals are intentionally unsupported.",
        "snapshot_value": "AAPL snapshot: FY 2025; revenue 416.16B; net income 112.01B; EPS 7.49",
    },
    {
        "category": "Annual financial statements",
        "metric": "Total assets, current assets, current liabilities, long-term debt, short-term debt, cash and short-term investments, inventory",
        "source_tool": "get_balance_sheet",
        "measures": "Latest annual balance sheet values.",
        "rule_phrasing": '"cash is greater than short-term debt"',
        "interpretation": "Annual fundamentals only; quarterly fundamentals are intentionally unsupported.",
        "snapshot_value": "AAPL snapshot: assets 359.24B; current liabilities 165.63B; cash/ST investments 54.70B",
    },
    {
        "category": "Annual financial statements",
        "metric": "Operating cash flow, capex, dividends, buybacks, net change in cash",
        "source_tool": "get_cash_flow",
        "measures": "Latest annual cash-flow values.",
        "rule_phrasing": '"positive operating cash flow" / "buybacks are positive"',
        "interpretation": "Annual fundamentals only; quarterly fundamentals are intentionally unsupported.",
        "snapshot_value": "AAPL snapshot: operating cash flow 111.48B; capex -12.72B; buybacks -90.71B",
    },
    {
        "category": "Performance (trailing returns)",
        "metric": "1D, 5D, 1M, 3M, 6M, YTD, 1Y, 3Y, 5Y returns",
        "source_tool": "get_performance",
        "measures": "Trailing return over each horizon.",
        "rule_phrasing": '"up more than 20% year-to-date" / "1Y return is negative"',
        "interpretation": "Useful for momentum, relative-strength, rebound, or underperformance rules.",
        "snapshot_value": "AAPL snapshot: 1D 4.84%; 5D 7.64%; YTD 13.53%; 1Y 47.00%",
    },
    {
        "category": "Company profile",
        "metric": "Beta",
        "source_tool": "get_profile",
        "measures": "Volatility compared with the market.",
        "rule_phrasing": '"beta below 1.2"',
        "interpretation": "Beta above 1 is typically more volatile than the market.",
        "snapshot_value": "AAPL snapshot: 1.097",
    },
    {
        "category": "Company profile",
        "metric": "Sector / industry",
        "source_tool": "get_profile",
        "measures": "Company classification.",
        "rule_phrasing": '"only technology-sector stocks"',
        "interpretation": "Useful for inclusion or exclusion filters.",
        "snapshot_value": "AAPL snapshot: Technology / Consumer Electronics",
    },
    {
        "category": "Company profile",
        "metric": "Exchange",
        "source_tool": "get_profile",
        "measures": "Listing venue.",
        "rule_phrasing": "(context)",
        "interpretation": "Useful for display or exchange-specific filters.",
        "snapshot_value": "AAPL snapshot: NASDAQ",
    },
    {
        "category": "Company profile",
        "metric": "Market cap",
        "source_tool": "get_profile",
        "measures": "Company size by market value.",
        "rule_phrasing": '"large-cap only"',
        "interpretation": "Useful for size filters.",
        "snapshot_value": "AAPL snapshot: 4.53T",
    },
    {
        "category": "Company profile",
        "metric": "Average volume",
        "source_tool": "get_profile",
        "measures": "Typical trading liquidity.",
        "rule_phrasing": '"average volume above 1 million"',
        "interpretation": "Higher average volume can indicate better liquidity.",
        "snapshot_value": "AAPL snapshot: 53,938,116",
    },
    {
        "category": "Company profile",
        "metric": "ETF / fund / ADR flags",
        "source_tool": "get_profile",
        "measures": "Instrument type flags.",
        "rule_phrasing": '"exclude ETFs"',
        "interpretation": "Useful for filtering instrument types.",
        "snapshot_value": "AAPL snapshot: ETF false; fund false; ADR false",
    },
    {
        "category": "Company profile",
        "metric": "IPO date",
        "source_tool": "get_profile",
        "measures": "Listing date.",
        "rule_phrasing": "(context)",
        "interpretation": "Useful for company-age or listing-history context.",
        "snapshot_value": "AAPL snapshot: 1980-12-12",
    },
    {
        "category": "Company profile",
        "metric": "Last dividend",
        "source_tool": "get_profile",
        "measures": "Most recent dividend value.",
        "rule_phrasing": '"pays a dividend"',
        "interpretation": "Useful for income-oriented filters.",
        "snapshot_value": "AAPL snapshot: 1.05",
    },
    {
        "category": "Analyst & estimates",
        "metric": "Price target: high / low / consensus / median",
        "source_tool": "get_price_target",
        "measures": "Analyst price targets.",
        "rule_phrasing": '"price below the consensus target"',
        "interpretation": "Useful for analyst upside/downside context.",
        "snapshot_value": "AAPL snapshot: high 400; low 253; consensus 327; median 325",
    },
    {
        "category": "Analyst & estimates",
        "metric": "Analyst rating snapshot + component scores",
        "source_tool": "get_analyst_rating",
        "measures": "Aggregate analyst view and related score components.",
        "rule_phrasing": '"analyst rating is favourable"',
        "interpretation": "Useful as a supporting view, not a standalone guarantee.",
        "snapshot_value": "AAPL snapshot: rating B; overall score 3",
    },
    {
        "category": "Analyst & estimates",
        "metric": "Annual revenue / EPS / EBITDA estimates, EPS analyst count",
        "source_tool": "get_analyst_estimates",
        "measures": "Forward annual estimates.",
        "rule_phrasing": '"forecast EPS growth is positive"',
        "interpretation": "Useful for forward-looking growth expectations.",
        "snapshot_value": "AAPL snapshot: date 2030-09-27; EPS avg 12.82; revenue avg 662.33B",
    },
    {
        "category": "Earnings",
        "metric": "Past and upcoming earnings rows: EPS and revenue estimates/actuals, earnings dates",
        "source_tool": "get_earnings",
        "measures": "Earnings history and schedule.",
        "rule_phrasing": '"avoid buying within 5 days of earnings"',
        "interpretation": "Useful for event-risk, surprise, and schedule rules.",
        "snapshot_value": "AAPL snapshot: next 2026-07-30 EPS est 1.88; prior 2026-04-30 EPS actual 2.01",
    },
]


def _render_metrics_reference() -> None:
    st.subheader("Metrics Reference")
    st.write(
        "These are the market-data metrics the artefact can fetch. Rules are written "
        "in plain English in `src/config.py` as `BUY_RULES` and `SELL_RULES`; the "
        "agent reads the rule wording and fetches only the metrics the rule mentions. "
        "Mentioning one metric from a bundle makes the related bundle available in "
        "one request, which helps conserve the FMP free-tier request limit."
    )
    st.info(
        "Snapshot values below are real AAPL values fetched once from FMP on "
        "2026-07-05 at 16:05 UTC. They are static reference examples, not live "
        "or automatically refreshed data."
    )
    st.caption(
        "`get_technical_indicator` supports `ema`, `adx`, `williams`, and "
        "`standarddeviation`. Annual statement tools request annual fundamentals "
        "only; quarterly fundamentals are intentionally not fetched."
    )

    columns = {
        "metric": "Metric",
        "source_tool": "Source tool",
        "measures": "What it measures",
        "rule_phrasing": "How to phrase it in a rule",
        "interpretation": "Typical interpretation",
        "snapshot_value": "AAPL snapshot value",
    }
    for category in dict.fromkeys(row["category"] for row in _METRIC_REFERENCE):
        st.markdown(f"#### {category}")
        rows = [
            {columns[key]: row[key] for key in columns}
            for row in _METRIC_REFERENCE
            if row["category"] == category
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ----------------------------------------------------------- card renderer
def _render_card(s: dict) -> None:
    _SIGNAL_COLORS = {
        "BUY":   ":green",
        "SKIP":  ":gray",
        "SELL":  ":red",
        "HOLD":  ":orange",
        "ERROR": ":gray",
    }
    signal = s.get("signal", "ERROR")
    color  = _SIGNAL_COLORS.get(signal, ":gray")
    name   = s.get("data_fetched", {}).get("name") or s.get("ticker")
    ticker = s.get("ticker", "")
    provider = s.get("provider") or "unknown"
    model = s.get("model")

    with st.container(border=True):
        st.markdown(
            f"**{name}** &nbsp; `{ticker}` &nbsp;&nbsp; {color}[**{signal}**]"
        )
        caption = f"via `{provider}`"
        if model:
            caption += f" · `{model}`"
        st.caption(caption)
        with st.expander("Why this signal?"):
            st.write(s.get("rationale") or "No rationale available.")

        data = {
            k: v for k, v in s.get("data_fetched", {}).items()
            if k not in ("ticker", "name")
        }
        if data:
            with st.expander("Data used"):
                has_nested_values = any(isinstance(v, (dict, list)) for v in data.values())
                if has_nested_values:
                    st.json(data)
                else:
                    cols = st.columns(len(data))
                    for col, (k, v) in zip(cols, data.items()):
                        col.metric(
                            label=k.replace("_", " ").title(),
                            value=str(v) if v is not None else "-",
                        )


# ------------------------------------------------------------------ page setup
st.set_page_config(
    page_title="Agentic DSS for Retail Investors",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("Agentic DSS for Retail Investors")
current_settings = load_settings()
st.caption(f"Provider: `{current_settings['provider']}` · Model: `{current_settings['model']}`")
st.metric("FMP requests today", get_fmp_request_count())

if st.button("Run Analysis", type="primary"):
    with st.spinner("Agent evaluating your stocks — this takes ~10-20 seconds..."):
        try:
            run_analysis()
        except Exception as exc:
            st.error("Agent run failed.")
            st.code(str(exc), language="text")
        else:
            st.success("Analysis complete.")
            st.rerun()

st.divider()

# ------------------------------------------------------------------- tabs
tab_latest, tab_history, tab_metrics, tab_settings = st.tabs([
    "Latest Run",
    "History",
    "Metrics Reference",
    "Settings",
])


# ---------------------------------------------------------- Tab 1: Latest
with tab_latest:
    signals = read_latest_signals()

    if not signals:
        st.info("No signals yet. Click **Run Analysis** to evaluate your stocks.")
    else:
        latest_provider = signals[0].get("provider") or "unknown"
        latest_model = signals[0].get("model")
        latest_caption = f"Last run: {signals[0]['run_date']} · via `{latest_provider}`"
        if latest_model:
            latest_caption += f" · `{latest_model}`"
        st.caption(latest_caption)

        buy_signals, sell_signals = split_signal_groups(signals)

        col_buy, col_sell = st.columns(2)

        with col_buy:
            st.subheader("Watchlist — BUY / SKIP evaluation")
            if buy_signals:
                for s in buy_signals:
                    _render_card(s)
            else:
                st.caption("No watchlist results.")

        with col_sell:
            st.subheader("Portfolio — SELL / HOLD evaluation")
            if sell_signals:
                for s in sell_signals:
                    _render_card(s)
            else:
                st.caption("No portfolio results.")


# --------------------------------------------------------- Tab 2: History
with tab_history:
    st.caption("Select at least one filter to load results.")

    run_dates   = read_run_dates()
    all_tickers = read_tickers()

    col1, col2, col3 = st.columns(3)

    with col1:
        selected_date = st.selectbox(
            "Run date",
            options=["— select —"] + run_dates,
            index=0,
        )
    with col2:
        selected_type = st.selectbox(
            "Signal type",
            options=["— select —", "BUY_EVAL", "SELL_EVAL"],
            index=0,
        )
    with col3:
        selected_ticker = st.selectbox(
            "Ticker",
            options=["— select —"] + all_tickers,
            index=0,
        )

    # Resolve filter values — treat placeholder as None
    f_date   = selected_date   if selected_date   != "— select —" else None
    f_type   = selected_type   if selected_type   != "— select —" else None
    f_ticker = selected_ticker if selected_ticker != "— select —" else None

    if not any([f_date, f_type, f_ticker]):
        st.info("Choose a run date, signal type, or ticker above to view history.")
    else:
        results = read_filtered_signals(
            run_date=f_date,
            signal_type=f_type,
            ticker=f_ticker,
        )

        if not results:
            st.caption("No records match the selected filters.")
        else:
            df = pd.DataFrame(build_history_rows(results))

            def _colour_signal(val):
                return {
                    "BUY":   "color: green; font-weight: bold",
                    "SKIP":  "color: gray; font-weight: bold",
                    "SELL":  "color: red; font-weight: bold",
                    "HOLD":  "color: orange; font-weight: bold",
                    "ERROR": "color: grey",
                }.get(val, "")

            st.dataframe(
                df.style.map(_colour_signal, subset=["Signal"]),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Rationale": st.column_config.TextColumn(width="large"),
                    "Run date":  st.column_config.TextColumn(width="medium"),
                },
            )
            st.caption(f"{len(df)} records")


# -------------------------------------------------- Tab 3: Metrics Reference
with tab_metrics:
    _render_metrics_reference()


# -------------------------------------------------------- Tab 4: Settings
with tab_settings:
    settings = load_settings()
    env_values = read_env_values()
    st.caption(f"Settings folder: `{user_data_dir()}`")
    provider_options = list(config.PROVIDER_SETTINGS)
    selected_provider = st.selectbox(
        "LLM provider",
        options=provider_options,
        index=provider_options.index(settings["provider"])
        if settings["provider"] in provider_options
        else 0,
    )
    model = st.text_input(
        "Model",
        value=settings["model"] if selected_provider == settings["provider"] else config.PROVIDER_DEFAULT_MODELS[selected_provider],
        disabled=True,
        help="Automatically selected low-cost model for the chosen provider.",
    )

    provider_key_env = config.PROVIDER_SETTINGS[selected_provider]["api_key_env"]
    fmp_label = "FMP API key"
    if env_values.get("FMP_API_KEY"):
        fmp_label += " (saved)"
    provider_label = provider_key_env
    if env_values.get(provider_key_env):
        provider_label += " (saved)"

    fmp_api_key = st.text_input(fmp_label, type="password", value="")
    provider_api_key = st.text_input(provider_label, type="password", value="")

    buy_rules = st.text_area("Buy rules", value=settings["buy_rules"], height=180)
    sell_rules = st.text_area("Sell rules", value=settings["sell_rules"], height=220)

    watchlist_path = user_csv_path("watchlist.csv")
    portfolio_path = user_csv_path("portfolio.csv")
    watchlist_df = pd.read_csv(watchlist_path)
    portfolio_df = pd.read_csv(portfolio_path)

    watchlist_editor = st.data_editor(
        watchlist_df,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_order=WATCHLIST_COLUMNS,
        key="watchlist_editor",
    )
    portfolio_editor = st.data_editor(
        portfolio_df,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_order=PORTFOLIO_COLUMNS,
        key="portfolio_editor",
    )

    if st.button("Save settings", type="primary"):
        valid_portfolio, message = validate_portfolio_columns(portfolio_editor.columns)
        valid_watchlist = "ticker" in watchlist_editor.columns
        if not valid_watchlist:
            st.error("Watchlist must include a ticker column.")
        elif not valid_portfolio:
            st.error(message)
        else:
            try:
                save_settings({
                    "provider": selected_provider,
                    "model": model,
                    "buy_rules": buy_rules,
                    "sell_rules": sell_rules,
                })
                save_api_keys(
                    provider=selected_provider,
                    fmp_api_key=fmp_api_key.strip() or None,
                    provider_api_key=provider_api_key.strip() or None,
                )
                clean_watchlist_frame(watchlist_editor).to_csv(watchlist_path, index=False)
                clean_portfolio_frame(portfolio_editor).to_csv(portfolio_path, index=False)
            except OSError as exc:
                st.error("Settings could not be saved because the app-data folder is not writable.")
                st.code(str(exc), language="text")
            else:
                st.success("Settings saved.")
