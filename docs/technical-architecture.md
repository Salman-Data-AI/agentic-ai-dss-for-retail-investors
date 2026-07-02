# Technical Architecture

## Overview

Agentic DSS for Retail Investors is a Python-based decision support system that evaluates stocks against investor-defined BUY and SELL rules. It combines deterministic application flow with an LLM-powered agent that decides which market-data tools are required for each rule evaluation.

The system has four main layers:

- Input and configuration: plain-English investment rules plus CSV watchlist and portfolio files.
- Agent orchestration: Anthropic Claude evaluates one ticker at a time and calls tools only for required metrics.
- Market data tools: FMP-backed functions fetch quote, technical, fundamental, profile, performance, analyst, and earnings data.
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
- `.env`: local Anthropic and FMP API keys, not committed.

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
- `get_key_metrics`: existing PE ratio and trailing EPS contract.
- `get_valuation_ratios`: P/E, P/B, P/S, PEG, debt-to-equity, liquidity ratios, interest coverage, and margins.
- `get_financial_health`: ROE, ROA, ROIC, EV/EBITDA, free-cash-flow yield, earnings yield, net debt/EBITDA, and Graham number.
- `get_income_statement`: latest annual revenue, gross profit, EBITDA, operating income, net income, EPS, diluted EPS, and fiscal year.
- `get_balance_sheet`: latest annual assets, liabilities, debt, cash and short-term investments, and inventory.
- `get_cash_flow`: latest annual operating cash flow, capital expenditures, dividends, buybacks, and net change in cash.
- `get_performance`: trailing 1D, 5D, 1M, 3M, 6M, year-to-date, 1Y, 3Y, and 5Y returns.
- `get_profile`: beta, sector, industry, exchange, market cap, average volume, ETF/fund/ADR flags, IPO date, and last dividend.
- `get_technical_indicator`: latest EMA, ADX, Williams %R, or standard deviation value.
- `get_price_target`: analyst high, low, consensus, and median price targets.
- `get_analyst_rating`: analyst rating snapshot and component scores.
- `get_analyst_estimates`: annual revenue, EPS, EBITDA estimates, and EPS analyst count.
- `get_earnings`: past and upcoming earnings rows with EPS and revenue estimates/actuals.

Tool descriptions are important because Claude uses them to decide which tool is relevant to the user's rules.

### Market Data Tools: `src/agent/tools.py`

The market data layer uses Financial Modeling Prep (FMP) stable API endpoints and `requests`.

Design:

- `_fmp_get(path, params)`: thin shared FMP client used by all public tools.
- Each public data tool makes one stable API request for one FMP endpoint, except cached repeat calls, which do not re-hit FMP.
- A module-level in-memory cache is keyed by endpoint, ticker, and request params. Its lifetime is the current Python process only.
- The persisted daily FMP usage counter and in-process request counter increment only for real outbound FMP requests.
- Existing public contracts for `get_quote`, `get_rsi`, `get_sma`, and `get_key_metrics` are preserved.
- Fundamentals use `period=annual`; quarterly fundamentals are intentionally not requested because free-tier endpoints can return HTTP 402.
- RSI, SMA, and the generic technical indicators are fetched from FMP's server-side technical-indicator endpoints.
- Bundle tools return curated dictionaries rather than entire FMP payloads to keep agent context and stored `data_fetched` compact.

Each public tool catches exceptions and returns an error dictionary instead of raising. This allows the agent to receive tool failures as data and still produce a structured result.

The FMP client maps common failures to clear messages, including plan/permission errors such as HTTP 402/403, bad paths or tickers such as HTTP 404, rate limits such as HTTP 429, invalid JSON, empty responses, and network errors.

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

`data_fetched` is JSON-serialized as text. Nested dictionaries and lists from bundle tools are preserved on write and restored on read; no schema change is required for nested tool outputs.

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
- Data used is shown in a separate expander. Flat scalar values render as compact metric columns; nested bundle values render as JSON for readability.

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
tools.py fetches FMP stable data, using per-run cache for duplicate endpoint/ticker/params calls
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
FMP_API_KEY=your_fmp_key_here
```

The key is loaded from `.env` using `load_dotenv()`.

## Error Handling

The system handles errors at several levels:

- Market data functions return `{"error": "..."}` on fetch, permission, rate-limit, empty-response, invalid-response, or network failure.
- The agent returns an `ERROR` signal if Claude output cannot be parsed as JSON.
- The dashboard reports subprocess failure and displays stderr.
- SQLite table initialization runs before reads and writes, so a missing database file is created automatically.

## Extension Points

Many metrics can now be added to rules without code changes if they are already returned by an existing bundle tool. For example, once `get_valuation_ratios` exists, rules can reference P/B, PEG, debt-to-equity, current ratio, quick ratio, or margins and Claude can select the same bundle.

To add a metric that is not covered by an existing bundle:

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
- Market data comes from Financial Modeling Prep stable endpoints; availability and freshness depend on that source and the configured API plan.
- The intended scope is US equities on the FMP free tier.
- The FMP free tier is constrained by daily request limits; the app tracks daily usage locally and uses per-run caching to avoid duplicate calls.
- Fundamentals are annual only. Quarterly fundamentals are not requested because the free tier can return plan-gating errors.
- The LLM interprets user rules, so ambiguous rules can produce inconsistent evaluations.
- The current database stores an audit log of generated signals but does not store raw historical market data.
- The current agent processes tickers sequentially, one Claude conversation per stock.
- The dashboard displays the latest run only.

