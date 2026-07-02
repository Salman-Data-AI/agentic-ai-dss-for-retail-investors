# Technical Architecture

## Overview

Agentic DSS for Retail Investors is a Python-based decision support system that evaluates stocks against investor-defined BUY and SELL rules. It combines deterministic application flow with an LLM-powered agent that decides which market-data tools are required for each rule evaluation.

The system has four main layers:

- Input and configuration: plain-English investment rules plus CSV watchlist and portfolio files.
- Agent orchestration: Anthropic Claude evaluates one ticker at a time and calls tools only for required metrics.
- Market data tools: FMP-backed functions fetch quote, technical, and fundamental data.
- Persistence and presentation: SQLite stores each run, and Streamlit displays the latest results.

## Repository Structure

```text
src/
|-- agent/
|   |-- agent.py          # Core Anthropic tool-use loop
|   |-- tools.py          # Market data and indicator functions
|   `-- tool_schemas.py   # Tool definitions exposed to Claude
|-- dashboard/
|   `-- app.py            # Streamlit dashboard
|-- data/
|   |-- portfolio.csv     # Current holdings for SELL evaluation
|   `-- watchlist.csv     # Candidate stocks for BUY evaluation
|-- database/
|   |-- __init__.py       # Database exports
|   |-- signals.db        # Local SQLite signal database
|   `-- store.py          # SQLite read/write functions
|-- config.py             # Model choice and user investment rules
`-- main.py               # Batch pipeline entry point
```

Project-level files:

- `README.md`: setup and user guide.
- `requirements.txt`: Python dependencies.
- `.env`: local Anthropic API key, not committed.

## Runtime Components

### Entry Point: `src/main.py`

`main.py` coordinates a full analysis run.

Responsibilities:

- Load environment variables with `python-dotenv`.
- Add `src/` to `sys.path` so modules can be imported from either the project root or `src/`.
- Read `src/data/watchlist.csv` for BUY evaluations.
- Read `src/data/portfolio.csv` for SELL evaluations.
- Call `run_agent()` once per ticker.
- Add metadata such as `signal_type`, `run_date`, company name, and entry price.
- Persist all signals through `write_signals()`.

The pipeline produces two categories of output:

- `BUY_EVAL`: generated from watchlist tickers and `BUY_RULES`.
- `SELL_EVAL`: generated from portfolio holdings and `SELL_RULES`.

For SELL evaluations, `main.py` injects holding-specific context into the rules, including entry price, quantity, and entry date. This lets the agent evaluate take-profit and stop-loss rules that depend on the investor's purchase price.

### Configuration: `src/config.py`

`config.py` is the primary customization surface.

It defines:

- `MODEL`: Anthropic model name used by the agent.
- `BUY_RULES`: plain-English entry criteria.
- `SELL_RULES`: plain-English exit criteria.

The rules are intentionally written as natural language so the user can change strategy criteria without editing application logic.

### Agent Loop: `src/agent/agent.py`

`run_agent(ticker, rules, model)` is the core agent function.

The function:

1. Builds a system prompt containing the investor's rules.
2. Sends the ticker to Anthropic Claude.
3. Allows Claude to request market-data tools using the schemas in `tool_schemas.py`.
4. Dispatches requested tools to local Python functions in `tools.py`.
5. Sends tool results back to Claude.
6. Repeats until Claude returns a final JSON object.
7. Parses the JSON and appends the ticker.

The agent is instructed to return exactly this shape:

```json
{
  "signal": "BUY | SELL | HOLD",
  "rationale": "Plain-English explanation",
  "data_fetched": {
    "metric_name": "metric value"
  }
}
```

If parsing fails or the agent returns an unexpected stop reason, `_error()` returns a structured `ERROR` signal. This keeps downstream storage and dashboard rendering consistent.

### Tool Schemas: `src/agent/tool_schemas.py`

`TOOL_SCHEMAS` defines the callable tools exposed to Claude. Each schema includes a name, description, input schema, and required fields.

Available tools:

- `get_quote`: current price, day change percentage, 52-week high/low, volume, market cap, and company name.
- `get_rsi`: Relative Strength Index for overbought/oversold analysis.
- `get_sma`: simple moving average for trend analysis.
- `get_key_metrics`: PE ratio and trailing EPS.

Tool descriptions are important because Claude uses them to decide which tool is relevant to the user's rules.

### Market Data Tools: `src/agent/tools.py`

The market data layer uses Financial Modeling Prep (FMP) and `requests`.

Functions:

- `_history(ticker, period)`: fetches historical daily prices.
- `get_quote(ticker)`: fetches current quote and company-level market data.
- `get_rsi(ticker, period=14)`: calculates RSI using Wilder-style exponential smoothing.
- `get_sma(ticker, period=50)`: calculates a rolling simple moving average.
- `get_key_metrics(ticker)`: fetches trailing PE ratio and EPS.

Each public tool catches exceptions and returns an error dictionary instead of raising. This allows the agent to receive tool failures as data and still produce a structured result.

### Database Layer: `src/database/store.py`

The application uses SQLite as a local audit log.

Database path:

```text
src/database/signals.db
```

Table:

```sql
CREATE TABLE IF NOT EXISTS signals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date     TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    signal_type  TEXT NOT NULL,
    signal       TEXT NOT NULL,
    rationale    TEXT,
    data_fetched TEXT,
    entry_price  REAL
)
```

Key functions:

- `write_signals(signals)`: initializes the database if needed and inserts a batch of signal records.
- `read_latest_signals()`: reads all signals from the most recent run date, ordered by signal type and ticker.

The agent does not read from the database. The database exists for persistence, auditability, and dashboard display.

### Dashboard: `src/dashboard/app.py`

The dashboard is a Streamlit interface for running and reviewing analyses.

Responsibilities:

- Display the selected Anthropic model.
- Provide a `Run Analysis` button.
- Execute `src/main.py` as a subprocess.
- Read the latest signals from SQLite.
- Split results into watchlist BUY evaluations and portfolio SELL evaluations.
- Render each result as a card with signal, rationale, and underlying data.

The dashboard uses progressive disclosure:

- Signal and ticker are visible immediately.
- Rationale is shown in an expander.
- Data used is shown in a separate expander.

## Data Flow

### Batch Analysis Flow

```text
config.py rules
      |
      v
watchlist.csv / portfolio.csv
      |
      v
src/main.py
      |
      v
run_agent(ticker, rules)
      |
      v
Claude selects required tools
      |
      v
tools.py fetches FMP data, including server-side technical indicators
      |
      v
Claude returns signal JSON
      |
      v
write_signals()
      |
      v
src/database/signals.db
```

### Dashboard Flow

```text
User clicks Run Analysis
      |
      v
Streamlit subprocess runs src/main.py
      |
      v
Signals are written to SQLite
      |
      v
Dashboard reloads latest run
      |
      v
Cards display signal, rationale, and data used
```

## Inputs

### Watchlist

Path:

```text
src/data/watchlist.csv
```

Expected columns:

```csv
ticker
AAPL
MSFT
GOOGL
```

Each ticker is evaluated against `BUY_RULES`.

### Portfolio

Path:

```text
src/data/portfolio.csv
```

Expected columns:

```csv
ticker,qty,entry_price,entry_date
JPM,10,195.50,2024-11-15
META,5,520.00,2024-10-03
```

Each holding is evaluated against `SELL_RULES`. The entry price, quantity, and date are included in the prompt context.

## Outputs

Each evaluated ticker produces:

- `ticker`: stock symbol.
- `signal`: `BUY`, `SELL`, `HOLD`, or `ERROR`.
- `signal_type`: `BUY_EVAL` or `SELL_EVAL`.
- `rationale`: plain-English explanation.
- `data_fetched`: JSON-serialized dictionary of metrics used.
- `entry_price`: included for portfolio evaluations.
- `run_date`: timestamp for grouping each batch run.

## Dependencies

Defined in `requirements.txt`:

- `anthropic`: Claude API client.
- `requests`: Financial Modeling Prep market data access.
- `streamlit`: dashboard UI.
- `python-dotenv`: local environment variable loading.
- `pandas`: CSV handling and dashboard table preparation.

## Environment Variables

The application expects:

```text
ANTHROPIC_API_KEY=your_key_here
```

The key is loaded from `.env` using `load_dotenv()`.

## Error Handling

The system handles errors at several levels:

- Market data functions return `{"error": "..."}` on fetch or calculation failure.
- The agent returns an `ERROR` signal if Claude output cannot be parsed as JSON.
- The dashboard reports subprocess failure and displays stderr.
- SQLite table initialization runs before reads and writes, so a missing database file is created automatically.

## Extension Points

To add a new metric:

1. Add a new function in `src/agent/tools.py`.
2. Add a matching schema in `src/agent/tool_schemas.py`.
3. Add the function to `_TOOL_DISPATCH` in `src/agent/agent.py`.
4. Reference the new metric in `BUY_RULES` or `SELL_RULES`.

To change the investment strategy:

1. Edit `BUY_RULES` and `SELL_RULES` in `src/config.py`.
2. Keep wording clear and specific so the agent can identify the required metrics.

To change the UI:

1. Edit `src/dashboard/app.py`.
2. Preserve `read_latest_signals()` as the data source unless adding new dashboard views.

## Technical Constraints and Assumptions

- The system is designed for end-of-day decision support, not intraday trading.
- Market data comes from Financial Modeling Prep; availability and freshness depend on that source and the configured API plan.
- The LLM interprets user rules, so ambiguous rules can produce inconsistent evaluations.
- The current database stores an audit log of generated signals but does not store raw historical market data.
- The current agent processes tickers sequentially, one Claude conversation per stock.
- The dashboard displays the latest run only.

