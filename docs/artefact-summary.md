# Artefact Summary

## What It Is

Agentic DSS for Retail Investors is an AI-assisted decision support artefact for individual investors. It helps users evaluate stocks against their own investment rules and produces plain-language BUY, SELL, or HOLD signals.

The artefact is not a trading bot and does not execute trades. It is a rule-based advisory tool that helps make investment decisions more consistent, explainable, and auditable.

## Purpose

Retail investors often rely on scattered information, manual calculations, and subjective interpretation when deciding whether to buy, sell, or hold a stock. This artefact addresses that problem by turning the investor's own strategy rules into a repeatable analysis workflow.

Its purpose is to:

- Apply investor-defined rules consistently.
- Reduce manual effort in checking market indicators.
- Explain each signal in plain English.
- Show the data used to support each recommendation.
- Keep a local record of each analysis run.

## What It Does

The system evaluates two groups of stocks:

- Watchlist stocks: potential investments evaluated against BUY rules.
- Portfolio stocks: current holdings evaluated against SELL rules.

For each stock, it returns:

- A signal: `BUY`, `SELL`, `HOLD`, or `ERROR`.
- A rationale explaining why that signal was generated.
- The specific data points used during evaluation.

Example data points include:

- Current price.
- 52-week high and low.
- RSI.
- Simple moving averages.
- PE ratio.
- EPS.
- Volume.
- Market capitalization.

## How It Works

The user defines investment rules in plain English in `src/config.py`.

Example BUY rule:

```text
Consider buying a stock if RSI is below 35, the current price is near the
52-week low, and PE ratio is below 25.
```

Example SELL rule:

```text
Consider selling a stock if RSI is above 70, the price is more than 25%
above entry price, or the price is more than 15% below entry price.
```

The system then:

1. Reads the watchlist and portfolio CSV files.
2. Sends each ticker and relevant rules to the AI agent.
3. Lets the agent identify which data points are required.
4. Fetches only those data points using local market-data tools.
5. Evaluates the stock against the user's rules.
6. Produces a structured signal and explanation.
7. Saves the result in a local SQLite database.
8. Displays the latest results in a Streamlit dashboard.

## Main Functionalities

### Rule-Based BUY Evaluation

The watchlist file contains stocks the user may want to buy. Each ticker is evaluated against `BUY_RULES`.

The output helps the user identify which watchlist stocks currently match their entry criteria.

### Rule-Based SELL Evaluation

The portfolio file contains stocks the user already owns, including quantity, entry price, and entry date. Each holding is evaluated against `SELL_RULES`.

The output helps the user identify whether an existing holding may meet exit, profit-taking, stop-loss, or risk-management criteria.

### AI-Guided Data Selection

The agent does not fetch every available metric by default. It reads the user's rules and decides which tools are needed.

For example:

- If the rule mentions RSI, the agent calls the RSI tool.
- If the rule mentions valuation or PE ratio, the agent calls the key metrics tool.
- If the rule mentions 52-week high or low, the agent calls the quote tool.

This keeps the analysis focused on the user's stated criteria.

### Market Data Retrieval

Market data is fetched through Yahoo Finance using the `yfinance` library. Technical indicators such as RSI and SMA are calculated locally using price history and pandas.

This design keeps indicator calculations transparent and inspectable in the codebase.

### Plain-Language Explanations

Each signal includes a rationale that explains the market meaning of the data, not only whether a threshold passed or failed.

The explanation is intended to help a retail investor understand why the system produced its recommendation.

### Audit Logging

Every run is written to a local SQLite database. The stored record includes the ticker, signal type, signal, rationale, data used, entry price when relevant, and run timestamp.

This makes it possible to review the latest analysis and preserve a history of generated recommendations.

### Dashboard View

The Streamlit dashboard provides an interactive interface for running the analysis and reviewing results.

It displays:

- Latest run timestamp.
- Watchlist BUY evaluations.
- Portfolio SELL evaluations.
- Signal cards for each stock.
- Expandable rationales.
- Expandable underlying data.

## Intended Users

The primary user is a retail investor who wants to apply a personal investment strategy more consistently without writing code.

The artefact is also suitable for research or demonstration contexts where explainable AI decision support is being studied, especially in relation to personal finance and retail investing.

## User Workflow

1. Add an Anthropic API key to `.env`.
2. Edit `src/config.py` to define BUY and SELL rules.
3. Add candidate stocks to `src/data/watchlist.csv`.
4. Add current holdings to `src/data/portfolio.csv`.
5. Run the dashboard with Streamlit or execute the terminal pipeline.
6. Review BUY, SELL, and HOLD signals.
7. Expand each result to inspect the rationale and data used.

## Key Design Principles

### User-Controlled Strategy

The system does not impose a fixed investment model. The user controls the decision criteria through plain-English rules.

### Explainability

Each signal includes both the recommendation and the reasoning behind it. The dashboard also exposes the underlying data used during the evaluation.

### Repeatability

The same rules can be applied repeatedly to the same watchlist and portfolio structure. This supports more consistent decision-making over time.

### Auditability

Results are stored locally in SQLite, creating a record of what the system recommended and what data supported that recommendation.

### Modularity

The system separates configuration, agent logic, tools, storage, and presentation. This makes it easier to extend the artefact with new metrics, rules, or dashboard views.

## Current Capabilities

- Evaluate watchlist tickers for potential BUY signals.
- Evaluate portfolio holdings for potential SELL signals.
- Interpret plain-English investment rules.
- Fetch quote data, technical indicators, and basic fundamentals.
- Calculate RSI and SMA locally.
- Produce plain-English rationales.
- Store signals in SQLite.
- Display latest results in a Streamlit dashboard.

## Limitations

- It is intended for decision support, not automated trading.
- It does not place orders or connect to brokerage accounts.
- It depends on Yahoo Finance data availability through `yfinance`.
- It relies on the AI model's interpretation of the user's rules.
- Ambiguous or contradictory rules can lead to weaker recommendations.
- It currently processes stocks sequentially.
- The dashboard currently displays the latest run rather than full historical analytics.

## Example Use Case

A retail investor wants to buy stocks only when they appear oversold, trade near their 52-week low, and have a reasonable PE ratio. The same investor wants to sell current holdings if they become overbought, hit a profit target, hit a stop loss, or become too expensive.

The investor writes those criteria in `config.py`, lists candidate stocks in `watchlist.csv`, and lists current holdings in `portfolio.csv`. When the analysis runs, the system checks each ticker, fetches the required metrics, generates a signal, explains the result, and displays everything in the dashboard.

## Value of the Artefact

The artefact demonstrates how an agentic AI system can support retail investment decisions while keeping the human investor in control. It combines flexible natural-language strategy definition with structured data retrieval, transparent outputs, and local audit logging.

