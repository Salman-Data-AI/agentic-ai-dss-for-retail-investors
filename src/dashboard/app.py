"""
Streamlit dashboard — Agentic DSS for Retail Investors.
Tab 1: Latest run with progressive disclosure cards.
Tab 2: History — filtered table, requires at least one filter before loading data.
Run: streamlit run dashboard/app.py  (from inside src/)
"""

import os
import sys
import subprocess

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
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

    with st.container(border=True):
        st.markdown(
            f"**{name}** &nbsp; `{ticker}` &nbsp;&nbsp; {color}[**{signal}**]"
        )
        with st.expander("Why this signal?"):
            st.write(s.get("rationale") or "No rationale available.")

        data = {
            k: v for k, v in s.get("data_fetched", {}).items()
            if k not in ("ticker", "name")
        }
        if data:
            with st.expander("Data used"):
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
st.caption(f"Model: `{config.MODEL}`")

if st.button("Run Analysis", type="primary"):
    with st.spinner("Agent evaluating your stocks — this takes ~10-20 seconds..."):
        proc = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "..", "main.py")],
            capture_output=True,
            text=True,
        )
    if proc.returncode == 0:
        st.success("Analysis complete.")
        st.rerun()
    else:
        st.error("Agent run failed.")
        st.code(proc.stderr, language="text")

st.divider()

# ------------------------------------------------------------------- tabs
tab_latest, tab_history = st.tabs(["Latest Run", "History"])


# ---------------------------------------------------------- Tab 1: Latest
with tab_latest:
    signals = read_latest_signals()

    if not signals:
        st.info("No signals yet. Click **Run Analysis** to evaluate your stocks.")
    else:
        st.caption(f"Last run: {signals[0]['run_date']}")

        buy_signals  = [s for s in signals if s["signal_type"] == "BUY_EVAL"]
        sell_signals = [s for s in signals if s["signal_type"] == "SELL_EVAL"]

        col_buy, col_sell = st.columns(2)

        with col_buy:
            st.subheader("Watchlist — BUY evaluation")
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
            rows = []
            for s in results:
                name = s.get("data_fetched", {}).get("name") or s["ticker"]
                rows.append({
                    "Run date":  s["run_date"],
                    "Ticker":    s["ticker"],
                    "Company":   name,
                    "Type":      "BUY eval" if s["signal_type"] == "BUY_EVAL" else "SELL eval",
                    "Signal":    s["signal"],
                    "Rationale": s.get("rationale") or "",
                })

            df = pd.DataFrame(rows)

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
