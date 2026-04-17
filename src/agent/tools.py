"""
Market data wrapper functions using yfinance.
No API key required — yfinance pulls directly from Yahoo Finance.

RSI and SMA are calculated from historical price data using pandas.
This keeps the logic transparent and auditable.
"""

import pandas as pd
import yfinance as yf


def _history(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Fetch daily closing price history. Returns empty DataFrame on failure."""
    t = yf.Ticker(ticker)
    df = t.history(period=period, auto_adjust=True)
    return df


def get_quote(ticker: str) -> dict:
    """Current price, day change %, 52-week high/low, volume, market cap, company name."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName") or ticker,
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "change_pct": round(info.get("regularMarketChangePercent", 0), 2),
            "week_52_high": info.get("fiftyTwoWeekHigh"),
            "week_52_low": info.get("fiftyTwoWeekLow"),
            "volume": info.get("regularMarketVolume"),
            "market_cap": info.get("marketCap"),
        }
    except Exception as e:
        return {"error": f"Quote fetch failed for {ticker}: {e}"}


def get_rsi(ticker: str, period: int = 14) -> dict:
    """
    RSI calculated from daily closing prices using Wilder's smoothing method.
    Below 30 = oversold, above 70 = overbought.
    """
    try:
        df = _history(ticker, period="3mo")
        if df.empty or len(df) < period + 1:
            return {"error": f"Not enough price history to calculate RSI for {ticker}"}

        delta = df["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return {
            "ticker": ticker,
            "rsi": round(rsi.iloc[-1], 2),
            "period": period,
            "as_of": str(df.index[-1].date()),
        }
    except Exception as e:
        return {"error": f"RSI calculation failed for {ticker}: {e}"}


def get_sma(ticker: str, period: int = 50) -> dict:
    """
    Simple Moving Average calculated from daily closing prices.
    Common periods: 50-day (medium-term trend), 200-day (long-term trend).
    """
    try:
        hist_period = "1y" if period <= 50 else "2y"
        df = _history(ticker, period=hist_period)
        if df.empty or len(df) < period:
            return {"error": f"Not enough price history to calculate {period}-day SMA for {ticker}"}

        sma = df["Close"].rolling(window=period).mean().iloc[-1]
        return {
            "ticker": ticker,
            "sma": round(sma, 2),
            "period": period,
            "as_of": str(df.index[-1].date()),
        }
    except Exception as e:
        return {"error": f"SMA calculation failed for {ticker}: {e}"}


def get_key_metrics(ticker: str) -> dict:
    """PE ratio and EPS (trailing twelve months) from Yahoo Finance."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "ticker": ticker,
            "pe_ratio": round(info.get("trailingPE") or 0, 2),
            "eps_ttm": round(info.get("trailingEps") or 0, 2),
        }
    except Exception as e:
        return {"error": f"Key metrics fetch failed for {ticker}: {e}"}
