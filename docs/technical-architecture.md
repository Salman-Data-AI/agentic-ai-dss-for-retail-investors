# Technical Architecture

## Overview

Agentic DSS for Retail Investors is a Python-based decision support system that evaluates stocks against investor-defined BUY and SELL rules. It combines deterministic rule-level tool planning, an approved compiled rule set, code-owned signal evaluation, and an LLM rationale step over prefetched market data.

The system has four main layers:

- Input and configuration: plain-English investment rules plus CSV watchlist and portfolio files.
- Agent orchestration: the app compiles and approves rule text, plans required tools once per rule set, fetches those metrics for each ticker, evaluates signals in code, and asks the selected LLM for rationale text.
- Market data tools: FMP-backed functions fetch quote, technical, fundamental, profile, performance, analyst, and earnings data.
- Persistence and presentation: SQLite stores each run, and Streamlit displays the latest results.

## Repository Structure

```text
src/
|-- agent/
|   |-- agent.py          # Signal evaluation from prefetched market data
|   |-- deterministic_evaluator.py # Code-owned signal evaluation
|   |-- rule_approval.py  # Compiled-rule approval state machine
|   |-- metric_registry.py # Canonical metric contract for compile/runtime
|   |-- rule_compiler.py  # Hybrid deterministic/LLM compile step for rule text
|   |-- rule_fingerprint.py # Compile/approval fingerprinting
|   |-- rule_sets.py      # Pure compiled-rule validation
|   |-- tool_planner.py   # Rule-level fixed tool planning
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
- Prepare the compiled rule set before fetching data; unapproved, invalidated, or unbindable rules block the run with a structured summary.
- Plan the required BUY and SELL tools once per run.
- Print a console warning if a rule set maps only to the quote fallback.
- Fetch the planned metrics for each ticker.
- Fetch ticker data in parallel using a small worker pool.
- Call `evaluate_signals_from_data_batch()` once for the BUY group and once for the SELL group, passing the approved compiled rule set.
- Add metadata such as `signal_type`, `run_date`, provider, model, optional temperature, rule text, company name, and entry price.
- Persist all signals through `write_signals()`.

The pipeline produces two categories of output:

- `BUY_EVAL`: generated from watchlist tickers and `BUY_RULES`; valid successful signals are `BUY` and `SKIP`.
- `SELL_EVAL`: generated from portfolio holdings and `SELL_RULES`; valid successful signals are `SELL` and `HOLD`.

For SELL evaluations, `main.py` includes holding-specific context in the per-ticker fetched-data payload, including entry price, quantity, and entry date. This lets the evaluator apply take-profit and stop-loss rules that depend on the investor's purchase price while still using one SELL batch call.

### Configuration: `src/config.py`

`config.py` is the primary customization surface.

It defines:

- `PROVIDER`: selected LLM provider.
- `MODEL`: model name used by the agent.
- `TEMPERATURE`: optional sampling temperature. `None` sends no temperature parameter; a float requests reduced variation without guaranteeing identical outputs.
- `BUY_RULES`: plain-English entry criteria.
- `SELL_RULES`: plain-English exit criteria.

The rules are intentionally written as natural language so the user can change strategy criteria without editing application logic.

### Rule Compile, Approval, And Evaluation

`src/agent/rule_compiler.py` turns the current BUY and SELL rule text into the Chunk 1 compiled rule-set shape validated by `src/agent/rule_sets.py`. The compiler is hybrid: it first applies deterministic pattern bindings for common supported rules such as RSI thresholds, PE thresholds, positive EPS, distance from the 52-week low/high, and entry-price gain/loss. Only clauses that remain ambiguous are sent to the selected provider through `create_llm_client(...)` with no tools exposed. Because the current provider adapters expose text responses rather than a guaranteed native JSON mode for every provider, the LLM fallback contract is prompt-enforced JSON followed by strict parsing and validation.

The closed metric menu is defined in `src/agent/metric_registry.py` and re-exported as `SUPPORTED_METRIC_KEYS` for validation. The registry records canonical metric keys, aliases, valid evaluation types, source tools/fields, units, and examples for the main metrics used by the compiler. `TOOL_SCHEMA_VERSION` and `COMPILE_PROMPT_VERSION` version the metric/prompt contract. The approval fingerprint is computed by `fingerprint_rule_inputs(rule_text, tool_schema_version, prompt_version)`. Provider and model are deliberately excluded because deterministic patterns plus registry-guided fallback are intended to produce provider-independent bindings; if future compile output carries model-specific behavior, this assumption should be revisited.

Compile is fail-closed. If any clause cannot be bound to one supported numeric metric comparison, the compiler returns a structured block with `unbound_clauses` and does not silently drop the clause. `src/main.py::run_analysis()` calls `prepare_rule_set()` before fetch and evaluation. A rule set that is not approved cannot run analysis, so the pipeline blocks before making FMP requests.

`src/settings.py` persists `compiled_rule_set`, `compiled_rule_fingerprint`, and `rule_approval_state`. Legacy `settings.json` files load as `unvalidated`, which forces compile and approval before the next analysis can run. The approval states are `unvalidated`, `compiled`, `approved`, and `invalidated`. Raw BUY/SELL rule text edits take precedence over a stale approval lock because a changed fingerprint invalidates the old lock and forces recompile plus re-approval.

Until the Chunk 3 dashboard UI exists, `src/approve_rules.py` is the temporary non-UI trigger:

```powershell
python src/approve_rules.py compile
python src/approve_rules.py approve
```

`approve` compiles first if needed, then marks the current compiled rule set as approved.

Automated tests mock provider clients for compile, state-machine, gate, and deterministic-signal checks so the suite is deterministic and does not spend real LLM calls. Real-provider structured-output smoke tests are intentionally kept outside the default offline suite because they require live credentials, network access, and provider-specific account availability.

`src/agent/tool_planner.py::plan_tools_for_rules(rules)` converts each rule string into a fixed tool plan for that run. The BUY plan is reused for every watchlist ticker, and the SELL plan is reused for every portfolio holding. `plan_tools_with_diagnostics(rules)` returns the same plan plus a flag for the silent quote-fallback case, so `main.py` can warn when a rule set did not map to any specific data tool.

`src/agent/agent.py::evaluate_signals_from_data_batch(items, rules, model, evaluation_type, compiled_rule_set=...)` evaluates a group of prefetched ticker payloads in one provider call for rationale only when a compiled rule set is supplied. The deterministic evaluator owns `signal` and `triggering_rule`; the model cannot override them.

The flow:

1. Flattens the fetched market-data payload into numeric metrics, including derived metrics such as `gain_loss_pct`, `price_above_52_week_low_pct`, and `price_below_52_week_high_pct`.
2. Applies `deterministic_evaluator.evaluate_rule_set()` with the approved compiled rule set.
3. Calls the selected provider with no tools exposed for rationale text only.
4. Parses the final JSON array and maps each rationale back to its input ticker.

The batch evaluator is instructed to return one object per ticker with exactly this shape:

```json
{
  "ticker": "AAPL",
  "signal": "Code-decided BUY | SKIP for BUY_EVAL, or SELL | HOLD for SELL_EVAL",
  "triggering_rule": "Code-derived governing rule summary",
  "rationale": "Plain-English explanation",
  "data_fetched": {
    "metric_name": "metric value"
  }
}
```

The `evaluation_type` argument selects the deterministic signal contract. `BUY_EVAL` yields only `BUY` or `SKIP`; `SELL_EVAL` yields only `SELL` or `HOLD`. `triggering_rule` remains a single text value because the database column is still `TEXT`; the deterministic evaluator also keeps clause outcomes in memory for rationale generation and future UI work. Temperature now affects rationale wording only, not signal selection. If the rationale call fails, the deterministic signal remains in place with an error-style rationale. The legacy model-decided parser is still present for callers that omit `compiled_rule_set`, but `run_analysis()` uses the approved deterministic path.

### Tool Schemas: `src/agent/tool_schemas.py`

`TOOL_SCHEMAS` defines the callable tools exposed to Claude. Each schema includes a name, description, input schema, and required fields. `TOOL_SCHEMA_VERSION` lives beside those tool schemas, while `SUPPORTED_METRIC_KEYS` is sourced from `metric_registry.py`, the closed metric menu used by rule compile and validation.

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

Tool descriptions document the data surface and are still used by adapter tests and lower-level provider support. The main analysis path uses `tool_planner.py` to select tools before the LLM call.

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
    entry_price  REAL,
    provider     TEXT,
    model        TEXT,
    rules_applied TEXT,
    triggering_rule TEXT,
    temperature  REAL,
    run_elapsed_seconds REAL
)
```

Key functions:

- `write_signals(signals)`: initializes the database if needed and inserts a batch of signal records.
- `read_latest_signals()`: reads all signals from the most recent run date, ordered by signal type and ticker.

The agent does not read from the database. The database exists for persistence, auditability, and dashboard display.

`data_fetched` is JSON-serialized as text. Nested dictionaries and lists from bundle tools are preserved on write and restored on read; no schema change is required for nested tool outputs.

`rules_applied` stores the exact BUY or SELL rule block used for that signal row, so later rule edits do not change the audit context for old rows. `triggering_rule` stores the model-reported governing rule and is validated for presence only. `temperature` is nullable because the default configuration omits the parameter and lets the provider use its default.

### Dashboard: `src/dashboard/app.py`

The dashboard is a Streamlit interface for running and reviewing analyses.

Responsibilities:

- Display the selected provider and model.
- Provide a `Run Analysis` button.
- Call `run_analysis()` in process.
- Read the latest signals from SQLite.
- Split results into watchlist BUY evaluations and portfolio SELL evaluations.
- Normalize legacy stored signal labels for display.
- Render each result as a card with signal, rationale, and underlying data.
- Render a static Metrics Reference tab from hardcoded reference rows and a one-time AAPL FMP snapshot.
- Provide a Settings tab for provider/rule/API-key/CSV editing.

The dashboard uses progressive disclosure:

- Signal and ticker are visible immediately.
- Rationale is shown in an expander.
- Data used is shown in a separate expander. Flat scalar values render as compact metric columns; nested bundle values render as JSON for readability.

Dashboard tabs:

- `Latest Run`: reads and renders the newest stored analysis results.
- `History`: requires at least one filter before reading matching audit rows.
- `Metrics Reference`: static educational content for rule writing. It does not call FMP, contact an LLM, run analysis, or read/write SQLite at dashboard render time. Its hardcoded AAPL values were fetched once from FMP on 2026-07-05 at 16:05 UTC with `python scripts/fetch_metrics_snapshot.py AAPL`.
- `Settings`: edits provider, optional temperature, rules, API keys, watchlist, and portfolio inputs.

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
plan_tools_for_rules(buy_rules / sell_rules)
      |
      v
tools.py fetches the planned FMP stable data for each ticker, using per-run cache for duplicate endpoint/ticker/params calls
      |
      v
evaluate_signals_from_data_batch(items, rules, evaluation_type)
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
Streamlit calls run_analysis() in process
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

Valid successful watchlist signals are:

- `BUY`: the ticker meets the user's entry criteria now.
- `SKIP`: the ticker does not meet the user's entry criteria now.

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

Valid successful portfolio signals are:

- `SELL`: the holding meets the user's exit criteria now.
- `HOLD`: the holding does not meet the user's exit criteria now.

## Outputs

Each evaluated ticker produces:

- `ticker`: stock symbol.
- `signal`: `BUY` or `SKIP` for watchlist evaluations; `SELL` or `HOLD` for portfolio evaluations; `ERROR` for failures.
- `signal_type`: `BUY_EVAL` or `SELL_EVAL`.
- `triggering_rule`: model-reported governing rule; presence is validated, correctness is not independently verified.
- `rationale`: plain-English explanation.
- `data_fetched`: JSON-serialized dictionary of metrics used.
- `entry_price`: included for portfolio evaluations.
- `run_date`: timestamp for grouping each batch run.
- `provider`: provider selected for the run.
- `model`: model selected for the run.
- `rules_applied`: exact BUY or SELL rule block used for that row.
- `temperature`: optional sampling temperature used for the run, or `NULL` when omitted.
- `run_elapsed_seconds`: total wall-clock time for the batch run, repeated on each row so History can display run duration.

### Legacy Signal Display

Older database rows may contain labels that are no longer valid for a given evaluation type, such as `SELL` on a `BUY_EVAL` watchlist row. The dashboard does not rewrite those audit rows. Instead, `dashboard.logic.normalize_signal_for_display()` maps legacy labels into the current display vocabulary:

- `BUY_EVAL` rows display `SELL` or `HOLD` as `SKIP`.
- `SELL_EVAL` rows display `BUY` or `SKIP` as `HOLD`.
- Unknown labels display as `ERROR`.

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
- The dashboard catches analysis failures and displays the exception text.
- SQLite table initialization runs before reads and writes, so a missing database file is created automatically.

## Extension Points

Many metrics can now be added to rules without code changes if `tool_planner.py` can map the wording to an existing bundle tool. For example, once `get_valuation_ratios` exists, rules can reference P/B, PEG, debt-to-equity, current ratio, quick ratio, or margins and the planner can select the same bundle.

To add a metric that is not covered by an existing bundle:

1. Add a new function in `src/agent/tools.py`.
2. Add a matching schema in `src/agent/tool_schemas.py` if the provider adapter/tool schema surface should expose it.
3. Add the function to `_TOOL_DISPATCH` in `src/agent/agent.py`.
4. Add matching keyword logic in `src/agent/tool_planner.py`.
5. Reference the new metric in `BUY_RULES` or `SELL_RULES`.

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
- The planner maps user-rule wording to fixed tool sets, so ambiguous or novel wording may require planner updates.
- The current database stores an audit log of generated signals and the rule text used for each signal, but it does not store raw historical market data beyond the compact `data_fetched` payload returned by the model.
- Lower temperature can reduce variation, but it does not make LLM outputs deterministic or prove signal correctness.
- The current analysis path evaluates tickers in parallel with `MAX_WORKERS = 3`.
- The dashboard displays the latest run only.

