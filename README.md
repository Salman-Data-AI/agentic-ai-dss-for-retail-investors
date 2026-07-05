# Agentic DSS for Retail Investors

A rule-based, AI-powered Decision Support System that evaluates stocks against your personal investment rules and generates plain-language buy/sell signals. Built as part of a Doctorate in Business Administration (DBA) dissertation at Golden Gate University.

---

## What it does

- Evaluates stocks on your **watchlist** against your BUY rules
- Evaluates stocks in your **portfolio** against your SELL rules
- Generates **BUY / SKIP** signals for watchlist stocks and **SELL / HOLD** signals for portfolio stocks
- Explains *why* each signal was generated in plain English
- Shows the underlying data behind every recommendation

All logic is driven by rules you write yourself in plain English. No coding required to customise the system.

---

## Prerequisites

- Python 3.10 or higher
- An LLM provider API key. Anthropic is the default; OpenAI, xAI Grok, Groq, and DeepSeek are also supported.
- A Financial Modeling Prep API key - sign up at [financialmodelingprep.com](https://financialmodelingprep.com)

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Salman-Data-AI/agentic-ai-dss-for-retail-investors.git
cd agentic-ai-dss-for-retail-investors
```

### 2. Create and activate a virtual environment

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**Mac / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add your API key

Create a file named `.env` in the project root with the following content:

```
ANTHROPIC_API_KEY=your_key_here
FMP_API_KEY=your_fmp_key_here
```

Replace the placeholders with your actual Anthropic and FMP API keys. This file is gitignored and will never be committed to version control.

If you choose a different provider in `src/config.py`, set the matching key instead:

```
OPENAI_API_KEY=your_openai_key_here
XAI_API_KEY=your_xai_key_here
GROQ_API_KEY=your_groq_key_here
DEEPSEEK_API_KEY=your_deepseek_key_here
GEMINI_API_KEY=your_gemini_key_here
CEREBRAS_API_KEY=your_cerebras_key_here
```

---

## Configuration

Open `src/config.py`. This is the **only file you need to edit**.

### Choose your LLM provider

Set `PROVIDER` to one of `"anthropic"`, `"openai"`, `"grok"`, `"groq"`, `"deepseek"`, `"gemini"`, or `"cerebras"`, then set `MODEL` to an exact current model ID from that provider's docs:

```python
PROVIDER = "anthropic"
MODEL = "claude-sonnet-4-6"
```

Use a model that supports tool calling. OpenAI-compatible providers use the configured base URLs in `PROVIDER_SETTINGS`; update those values in `config.py` if a provider changes its endpoint.

### Set your BUY rules

Write your entry criteria in plain English inside the `BUY_RULES` string:

```python
BUY_RULES = """
Consider buying a stock if ALL of the following are true:
- RSI (14-day) is below 35, suggesting the stock is oversold
- The current price is within 15% above the 52-week low
- PE ratio is below 25
"""
```

You can reference any of the following in your rules:
`RSI`, `current price`, `52-week high`, `52-week low`, `PE ratio`, `EPS`, `SMA (50-day or 200-day)`, `volume`, `market cap`, valuation ratios, profitability margins, liquidity ratios, debt ratios, ROE, ROA, ROIC, EV/EBITDA, free-cash-flow yield, annual income statement values, annual balance sheet values, annual cash-flow values, trailing performance, beta, sector, industry, analyst price targets, analyst ratings, annual analyst estimates, earnings dates, EMA, ADX, Williams %R, and standard deviation.

### Set your SELL rules

Write your exit criteria in the `SELL_RULES` string. You can reference your entry price — the system reads it automatically from `portfolio.csv`:

```python
SELL_RULES = """
Consider selling a stock if ANY of the following are true:
- RSI (14-day) is above 70, suggesting the stock is overbought
- The current price is more than 25% above my entry price (take profit)
- The current price is more than 15% below my entry price (stop loss)
- PE ratio has expanded above 40
"""
```

---

## Add your stocks

### Watchlist — BUY evaluation

Edit `src/data/watchlist.csv`. One ticker per row:

```
ticker
AAPL
MSFT
GOOGL
```

Watchlist tickers are entry candidates. They are evaluated only against your BUY rules and return either:

- `BUY`: the stock meets your entry criteria now.
- `SKIP`: the stock does not meet your entry criteria now; skip it for now.

### Portfolio — SELL evaluation

Edit `src/data/portfolio.csv`. One holding per row:

```
ticker,qty,entry_price,entry_date
JPM,10,195.50,2024-11-15
META,5,520.00,2024-10-03
```

Use the date format `YYYY-MM-DD`.

Portfolio holdings are current positions. They are evaluated only against your SELL rules and return either:

- `SELL`: the holding meets your exit criteria now.
- `HOLD`: the holding does not meet your exit criteria now.

---

## Running the system

### Option A — Dashboard (recommended)

Launch the dashboard from inside the `src/` directory:

```bash
cd src
streamlit run dashboard/app.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`). Click **Run Analysis** to evaluate your stocks. Results appear on screen with expandable explanations and data.

The dashboard also includes a **Metrics Reference** tab. It is static help content: it does not fetch live data, read the database, or run analysis. Use it to see which metrics the agent can fetch, which source tool provides each metric family, and how to phrase metrics in plain-English BUY or SELL rules. The sample values shown there are a real AAPL snapshot fetched once from FMP on 2026-07-05 at 16:05 UTC; they are static examples and are not automatically refreshed.

### Option B — Terminal only

```bash
python src/main.py
```

Results are printed to the terminal and saved to the database. You can launch the dashboard afterwards to view them.

### Packaged app self-test

After building the Windows onedir app, run `dist\AgenticDSS\AgenticDSS.exe --selftest` to check live FMP and LLM connectivity from inside the frozen executable without launching the UI.

---

## Running tests

Install the runtime and test dependencies, then run pytest from the repository root:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

The tests use dummy API keys and monkeypatch all external boundaries, so they do not call Financial Modeling Prep, Anthropic, the real `signals.db`, or the real FMP usage tally file.

---

## CI/CD and Windows builds

GitHub Actions runs three automated paths:

- **Tests** runs the offline pytest suite on pull requests and on pushes to `main`.
- **Build Check** runs on pull requests targeting `main` and on pushes to `main`. It builds the Windows installer without publishing a release, then uploads a temporary workflow artifact named `AgenticDSS-Setup`.
- **Release** runs only when a version tag such as `v1.0.0` is pushed. It builds the same installer and publishes it as a GitHub Release asset.

To download a build-check installer, open the completed **Build Check** workflow run in GitHub Actions, go to the run summary, and download the `AgenticDSS-Setup` artifact. GitHub downloads artifacts as a `.zip`; extract it to get `AgenticDSS-Setup.exe`.

To publish a release build, create and push a version tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Release downloads appear under the repository's **Releases** page. Build-check artifacts are temporary and intended for manual testing before release.

The CI build starts from a clean checkout with no local `.env` file. The shared installer build also runs a key-leak guard that fails if a bundled `.env` file or secret-looking API key appears in the build output.

---

## How it works

1. The agent reads your rules from `config.py`
2. For each stock, it identifies which data points your rules reference
3. It fetches only those data points from Financial Modeling Prep
4. It evaluates the data against your rules and decides the signal: `BUY` or `SKIP` for watchlist stocks, `SELL` or `HOLD` for portfolio holdings
5. It writes a plain-language explanation of the signal
6. Results are saved locally to `db/signals.db` and displayed in the dashboard

Every run is logged to the database for auditability, including the provider and model that produced each signal. The dashboard always shows the most recent run.

### Market data tools

The agent fetches data through Financial Modeling Prep stable API endpoints. To stay friendly to the FMP free tier, related metrics are grouped into single-call bundle tools:

- `get_quote`: current price, daily change, 52-week range, volume, market cap, company name
- `get_rsi`: latest RSI for a selected period
- `get_sma`: latest simple moving average for a selected period
- `get_key_metrics`: existing PE ratio and EPS TTM contract
- `get_valuation_ratios`: P/E, P/B, P/S, PEG, debt-to-equity, current/quick ratio, interest coverage, margins
- `get_financial_health`: ROE, ROA, ROIC, EV/EBITDA, free-cash-flow yield, earnings yield, net debt/EBITDA, Graham number
- `get_income_statement`: latest annual revenue, gross profit, EBITDA, operating income, net income, EPS, diluted EPS
- `get_balance_sheet`: latest annual assets, liabilities, debt, cash and short-term investments, inventory
- `get_cash_flow`: latest annual operating cash flow, capex, dividends, buybacks, net change in cash
- `get_performance`: trailing 1D, 5D, 1M, 3M, 6M, YTD, 1Y, 3Y, and 5Y returns
- `get_profile`: beta, sector, industry, exchange, market cap, average volume, ETF/fund/ADR flags, IPO date, last dividend
- `get_technical_indicator`: latest EMA, ADX, Williams %R, or standard deviation
- `get_price_target`: analyst high, low, consensus, and median targets
- `get_analyst_rating`: analyst rating and component scores
- `get_analyst_estimates`: annual revenue, EPS, EBITDA estimates and EPS analyst count
- `get_earnings`: past and upcoming earnings dates with EPS/revenue estimates and actuals

FMP free-tier constraints matter: the free plan is limited to 250 requests per day, legacy `/api/v3` paths are not used, and fundamentals request annual data only. Quarterly fundamentals can return HTTP 402 on the free tier; the app treats plan, permission, rate-limit, empty-response, and network failures as tool-level error dictionaries so an analysis run can degrade gracefully instead of crashing.

The dashboard's **Metrics Reference** tab mirrors these tool families in plain English so users can write clearer rules without looking at Python source code. Its AAPL snapshot values were generated with `python scripts/fetch_metrics_snapshot.py AAPL`, which used 18 FMP requests in that run.

---

## Project structure

```
src/
├── agent/
│   ├── agent.py          # Provider-agnostic agent loop, one call per stock
│   ├── llm.py            # Anthropic and OpenAI-compatible LLM adapters
│   ├── tools.py          # Financial Modeling Prep data wrappers
│   └── tool_schemas.py   # Tool definitions for the Claude API
├── data/
│   ├── watchlist.csv     # Your BUY watchlist
│   └── portfolio.csv     # Your current holdings
├── database/
│   └── store.py          # SQLite audit log
├── dashboard/
│   └── app.py            # Streamlit dashboard
├── config.py             # Your rules and settings — edit this
├── main.py               # Entry point
└── requirements.txt      # Python dependencies
```

---

## Limitations

- Designed for **end-of-day analysis** of S&P 500 stocks. Not suitable for intraday trading.
- Recommendations are based on the rules you define. The system does not predict market movements.
- Data is sourced from Financial Modeling Prep. Free-plan request limits may apply.
- The selected LLM interprets your rules; write them clearly for best results.
- Changing providers or models can change agent behavior, so runs from different providers are not directly comparable in research analysis.

---

## Extending the system

To add a new data point (e.g. dividend yield, debt-to-equity):

1. Add a function to `src/agent/tools.py`
2. Add the corresponding tool schema to `src/agent/tool_schemas.py`
3. Reference the new metric in your rules in `config.py`

No other files need to change.

---

## License

MIT License. Free to use, modify, and distribute.
