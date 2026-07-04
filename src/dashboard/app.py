"""
Streamlit dashboard — Agentic DSS for Retail Investors.
Tab 1: Latest run with progressive disclosure cards.
Tab 2: History — filtered table, requires at least one filter before loading data.
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


# ----------------------------------------------------------- card renderer
def _render_card(s: dict) -> None:
    _SIGNAL_COLORS = {
        "BUY":   ":green",
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
tab_latest, tab_history, tab_settings = st.tabs(["Latest Run", "History", "Settings"])


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
            st.subheader("Watchlist — BUY / HOLD evaluation")
            if buy_signals:
                for s in buy_signals:
                    _render_card(s)
            else:
                st.caption("No watchlist results.")

        with col_sell:
            st.subheader("Portfolio — SELL evaluation")
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


# -------------------------------------------------------- Tab 3: Settings
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
