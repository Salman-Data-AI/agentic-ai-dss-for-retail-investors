# Code Walkthrough

This document describes the current source code in this repository. It is documentation only: it describes what the code does now, not an intended future design.

## 1. Repo Map

Current significant files:

```text
.
|-- README.md
|-- requirements.txt
|-- requirements-dev.txt
|-- pytest.ini
|-- agentic_dss.spec
|-- packaging/
|   `-- desktop_launcher.py
|-- docs/
|   |-- artefact-summary.md
|   `-- technical-architecture.md
|-- src/
|   |-- config.py
|   |-- settings.py
|   |-- main.py
|   |-- paths.py
|   |-- selftest.py
|   |-- consistency_check.py
|   |-- agent/
|   |   |-- agent.py
|   |   |-- llm.py
|   |   |-- tool_planner.py
|   |   |-- tool_schemas.py
|   |   `-- tools.py
|   |-- dashboard/
|   |   |-- app.py
|   |   `-- logic.py
|   |-- data/
|   |   |-- portfolio.csv
|   |   `-- watchlist.csv
|   `-- database/
|       |-- __init__.py
|       |-- signals.db
|       `-- store.py
`-- tests/
    |-- conftest.py
    |-- test_agent.py
    |-- test_dashboard_logic.py
    |-- test_llm_config.py
    |-- test_main.py
    |-- test_paths.py
    |-- test_selftest.py
    |-- test_settings.py
    |-- test_store.py
    |-- test_tool_planner.py
    `-- test_tools.py
```

`docs/misc/CODE_WALKTHROUGH.md` is an ignored copy kept for local notes. The root `CODE_WALKTHROUGH.md` is the source-controlled walkthrough.

## 2. Paths And App-Data

`src/paths.py` owns frozen-aware file locations.

`is_frozen()` returns true only when `sys.frozen` is truthy and `sys._MEIPASS` exists. `bundle_dir()` returns `sys._MEIPASS` in a PyInstaller bundle and the `src/` directory in source mode.

`user_data_dir()` returns a writable per-user directory. It checks:

- `AGENTIC_DSS_USER_DATA_DIR`
- `%APPDATA%`
- `%LOCALAPPDATA%`
- `Path.home() / "AppData" / "Roaming"`
- `.app-data` under the repo root in source mode
- `tempfile.gettempdir()`

For each base path, it appends `Agentic AI DSS for Retail Investors` unless the base already has that name, creates the directory, writes and reads a small `.write-test` file, then returns the first usable path.

Derived paths:

- `signals_db_path()` -> app-data `signals.db`
- `fmp_usage_path()` -> app-data `fmp_usage.json`
- `analysis_summary_path()` -> app-data `latest_run_summary.json`
- `user_env_path()` -> app-data `.env`
- `executable_env_path()` -> executable-adjacent `.env` only when frozen

`seed_user_csv_defaults()` copies bundled `watchlist.csv` and `portfolio.csv` into app-data only when those user files do not already exist.

## 3. Configuration And Settings

`src/config.py` contains default provider/model/rule settings:

- `PROVIDER`
- `MODEL`
- `TEMPERATURE`
- `PROVIDER_DEFAULT_MODELS`
- `PROVIDER_SETTINGS`
- `BUY_RULES`
- `SELL_RULES`

`TEMPERATURE = None` means the app does not send a temperature parameter. A float such as `0.0` requests reduced variation, but it does not make the output deterministic.

`src/settings.py` is the runtime settings layer. `default_settings()` returns:

```python
{
    "provider": provider,
    "model": default_model_for_provider(provider),
    "buy_rules": config.BUY_RULES,
    "sell_rules": config.SELL_RULES,
    "temperature": parsed_temperature_or_none,
}
```

`load_settings()` reads app-data `settings.json` and merges it over `config.py` defaults. It derives the model from the provider, so a stale cross-provider model in JSON is not reused. `temperature` is parsed to `float | None`; invalid values fall back to `None`.

`save_settings()` writes non-secret settings to `settings.json`. It stores `temperature` as a string or `null`.

API keys are not stored in `settings.json`. `save_api_keys()` updates the app-data `.env` file for `FMP_API_KEY` and the selected provider key.

## 4. Environment Loading

`src/main.py`, `src/agent/agent.py`, and `src/agent/tools.py` load environment files in this order:

1. Default `python-dotenv` search.
2. App-data `.env` from `user_env_path()`.
3. Executable-adjacent `.env` from `executable_env_path()` when frozen.

`src/selftest.py` reports those same locations during the packaged self-test.

Provider keys are selected from `config.PROVIDER_SETTINGS`. Supported providers are `anthropic`, `openai`, `grok`, `groq`, `deepseek`, `gemini`, and `cerebras`.

## 5. Analysis Run Flow

The CLI entry point is:

```text
python src/main.py
```

The dashboard calls the same `run_analysis()` function in-process.

`run_analysis()` does this:

1. Loads runtime settings.
2. Creates a run timestamp.
3. Builds shared run metadata: provider, model, and temperature.
4. Plans BUY tools with `plan_tools_with_diagnostics(settings["buy_rules"])`.
5. Plans SELL tools with `plan_tools_with_diagnostics(settings["sell_rules"])`.
6. Prints a console warning if either rule set matched no specific tool and fell back to `get_quote`.
7. Reads app-data `watchlist.csv` and creates BUY jobs.
8. Reads app-data `portfolio.csv` and creates SELL jobs with holding context.
9. Fetches each ticker's planned data with a `ThreadPoolExecutor`, capped by `MAX_WORKERS = 3`.
10. Evaluates all BUY fetched jobs deterministically and requests rationale text.
11. Evaluates all SELL fetched jobs deterministically and requests rationale text.
12. Merges each job's metadata into the returned signal.
13. Adds `run_elapsed_seconds` to each signal.
14. Writes all signals through `database.write_signals()`.
15. Writes `latest_run_summary.json`.

BUY job metadata includes:

- `signal_type = "BUY_EVAL"`
- `run_date`
- `rules_applied = settings["buy_rules"]`
- `provider`
- `model`
- `temperature`

SELL job metadata adds:

- `entry_price`
- `rules_applied = settings["sell_rules"]`

`_evaluate_group()` is the join point where the evaluated signal gets the job metadata:

```python
signal.update(item["job"]["metadata"])
```

There is no second storage path for `rules_applied`.

## 6. Tool Planning

`src/agent/tool_planner.py` converts rule text into a list of `PlannedTool` objects.

`plan_tools_for_rules(rules)` preserves the original return type: `list[PlannedTool]`.

`plan_tools_with_diagnostics(rules)` returns:

```python
PlannedToolsDiagnostics(
    tools=[...],
    fallback_only=True_or_false,
)
```

`fallback_only` is true when no keyword branch matched and the planner returned `[PlannedTool("get_quote")]`. The app warns about that condition but does not reinterpret or correct the user's rules.

The planner recognizes quote terms, RSI, SMA, valuation ratios, financial health, statement terms, cash flow, performance/momentum, profile/beta terms, EMA, ADX, Williams, standard deviation, price targets, analyst ratings, analyst estimates, and earnings terms.

## 7. Market Data Tools

`src/agent/tools.py` wraps Financial Modeling Prep stable endpoints.

The main dispatch map lives in `src/agent/agent.py` as `_TOOL_DISPATCH`. `main.py` imports that map and uses it when executing a planned tool list.

Tool functions return dictionaries. On HTTP, permission, quota, empty-response, malformed-response, or network failures, tools return error dictionaries rather than raising. FMP usage is tracked in app-data `fmp_usage.json`, and an in-process cache avoids duplicate endpoint/ticker/parameter requests during one Python process.

## 8. Deterministic Signal Evaluation

`src/agent/agent.py::evaluate_signals_from_data_batch()` accepts:

- `items`: a list of `{"ticker": ..., "fetched_data": ...}` dictionaries
- `rules`
- `compiled_rule_set`
- `model`
- `evaluation_type`

`compiled_rule_set` is required. Omitting it is a `TypeError`, so callers cannot silently fall back to model-decided signals.

The active deterministic signal contract depends on `evaluation_type`:

- `BUY_EVAL`: successful signals must be `BUY` or `SKIP`.
- `SELL_EVAL`: successful signals must be `SELL` or `HOLD`.
- Other evaluation types return `ERROR`.

The deterministic evaluator owns `signal` and `triggering_rule`. The LLM rationale prompt receives the already-decided signal and requires one JSON object per input ticker with rationale-only fields:

```json
{
  "ticker": "AAPL",
  "rationale": "Plain-English explanation that names the rule.",
  "data_fetched": {
    "metric_name": "compact value"
  }
}
```

The rationale parser extracts the JSON array and maps rows back to input tickers. It does not accept signal or triggering-rule changes from the model.

If a ticker is omitted, JSON parsing fails, the provider asks for tools, or the provider returns no text, the deterministic signal remains in place and the rationale records the provider error. If a compiled metric is missing, non-numeric, or an error dict, the result for that ticker is:

```python
{
    "ticker": ticker,
    "signal": "ERROR",
    "triggering_rule": "",
    "rationale": msg,
    "data_fetched": fetched_data,
}
```

## 9. LLM Adapters

`src/agent/llm.py` provides a common `LLMClient` protocol and two adapters:

- `AnthropicAdapter` for Anthropic Messages API.
- `OpenAICompatibleAdapter` for OpenAI Chat Completions compatible providers.

`create_llm_client()` reads the selected provider key from the environment and returns the matching adapter.

Both adapters accept `temperature: float | None`. They add `temperature` to request kwargs only when it is not `None`; with `None`, no temperature key is sent. This is important because some configured model IDs may reject explicit non-default temperature values.

The OpenAI provider path uses `max_completion_tokens`; other OpenAI-compatible providers use `max_tokens`.

## 10. Database Storage

`src/database/store.py` uses SQLite as an audit log. The database path is app-data `signals.db`.

The `signals` table is created with:

- `id`
- `run_date`
- `ticker`
- `signal_type`
- `signal`
- `rationale`
- `data_fetched`
- `entry_price`
- `provider`
- `model`
- `rules_applied`
- `triggering_rule`
- `temperature`
- `run_elapsed_seconds`

`_ensure_column()` adds provider/model/runtime and hardening columns to older databases. No existing column is dropped or renamed.

`write_signals()` JSON-serializes `data_fetched`, inserts all audit fields, and commits the batch. `read_latest_signals()` and `read_filtered_signals()` select columns in the same order consumed by `_row_to_dict()`.

`rules_applied` stores the exact BUY or SELL rule block used for the row. `triggering_rule` stores the code-derived governing rule. `temperature` is nullable.

## 11. Dashboard

`src/dashboard/app.py` is the Streamlit UI.

It renders:

1. Page title.
2. Current provider/model caption from `load_settings()`.
3. FMP request count.
4. `Run Analysis` button.
5. Latest run timing caption when `latest_run_summary.json` exists.
6. Tabs: `Latest Run`, `History`, `Metrics Reference`, and `Settings`.

`Latest Run` reads `read_latest_signals()`, splits rows through `dashboard.logic.split_signal_groups()`, and renders watchlist BUY/SKIP cards and portfolio SELL/HOLD cards.

`History` requires at least one filter before calling `read_filtered_signals()`.

`Metrics Reference` is static guidance. It does not call FMP, contact an LLM provider, run analysis, or read/write SQLite at render time.

`Settings` edits:

- provider
- derived model display
- optional temperature
- FMP/provider API keys
- BUY rules
- SELL rules
- watchlist rows
- portfolio rows

Dashboard display uses `dashboard.logic.normalize_signal_for_display()` to map older rows into the current display vocabulary without rewriting stored audit rows.

## 12. Self-Test And Packaging

`packaging/desktop_launcher.py` is the PyInstaller executable entry point. It inserts bundled `src` onto `sys.path`, handles `--selftest`, then launches Streamlit.

`AgenticDSS.exe --selftest` runs `src/selftest.py`, which:

- reports environment files checked
- calls `get_quote("AAPL")` through the FMP path
- creates the configured LLM client and asks for a short response
- prints PASS/FAIL lines
- returns exit code `0` only when both checks pass

`agentic_dss.spec` builds a PyInstaller onedir app and excludes mutable runtime files such as the source `signals.db`, `fmp_usage.json`, `__pycache__`, and `.pyc` files.

## 13. Consistency Measurement

`src/consistency_check.py` is a developer/evaluation tool, not part of the normal user run path or frozen entry points.

It fetches data once for a small ticker list, calls `evaluate_signals_from_data_batch()` repeatedly against the same fetched payload and approved compiled rule set, and prints signal agreement plus disagreements. It measures signal stability only. It does not validate signal correctness.

Example:

```text
python src/consistency_check.py --runs 3 --tickers AAPL,MSFT
```

## 14. Tests

Pytest is the test runner.

`tests/conftest.py` adds `src` to `sys.path`, redirects temp directories into workspace `.pytest-tmp`, sets dummy API keys, and provides fixtures for isolated FMP usage files and temp SQLite databases.

Coverage includes:

- FMP tool shapes, errors, cache, and usage counting.
- Deterministic signal authority, rationale parsing, and adapter behavior with mocked clients.
- Provider settings and adapter routing.
- Runtime settings load/save behavior.
- `run_analysis()` orchestration.
- SQLite writes, reads, and legacy-column migration.
- Planner diagnostics and fallback detection.
- Dashboard display logic and legacy signal mapping.
- Path helpers, CSV seeding, and frozen-path behavior.
- Self-test formatting and exit-code behavior.

Tests are offline: they use fake HTTP clients, fake LLM clients, dummy keys, temp database paths, and temp FMP usage paths.

## 15. Known Boundaries

- The artefact is decision support, not automated trading.
- FMP data availability and quota depend on the configured API plan.
- `triggering_rule` is code-derived from the approved compiled rule set.
- Lower temperature can reduce rationale wording variation, but does not affect signal selection.
- The planner maps recognized wording to fixed tool sets; novel or ambiguous wording may fall back to quote-only data until planner keywords are expanded.
- The dashboard provides latest-run display and filtered history rows, not full historical analytics.
