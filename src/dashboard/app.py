"""
Streamlit dashboard — Agentic DSS for Retail Investors.
Progressive disclosure: signal shown by default, rationale and metrics expand on demand.
Run: streamlit run src/dashboard/app.py
"""

import os
import sys
import subprocess

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from database import read_latest_signals


# ----------------------------------------------------------- card renderer
def _render_card(s: dict) -> None:
    """
    Render a single signal card with progressive disclosure.
    - Header: company name, ticker, signal — always visible
    - Rationale: expander, collapsed by default
    - Metrics: expander, collapsed by default
    """
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
        # Header row — always visible
        st.markdown(
            f"**{name}** &nbsp; `{ticker}` &nbsp;&nbsp; {color}[**{signal}**]"
        )

        # Rationale — expand to read the explanation
        rationale = s.get("rationale") or "No rationale available."
        with st.expander("Why this signal?"):
            st.write(rationale)

        # Metrics — expand to see the underlying data
        data = {
            k: v for k, v in s.get("data_fetched", {}).items()
            if k not in ("ticker", "name")
        }
        if data:
            with st.expander("Data used"):
                cols = st.columns(len(data))
                for col, (k, v) in zip(cols, data.items()):
                    label = k.replace("_", " ").title()
                    col.metric(label=label, value=str(v) if v is not None else "-")


# ------------------------------------------------------------------ page setup
st.set_page_config(
    page_title="Agentic DSS for Retail Investors",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("Agentic DSS for Retail Investors")
st.caption(f"Model: `{config.MODEL}`")

# --------------------------------------------------------------- run button
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

# --------------------------------------------------------------- load + display
signals = read_latest_signals()

if not signals:
    st.info("No signals yet. Click **Run Analysis** to evaluate your stocks.")
    st.stop()

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
