# Agentic DSS for Retail Investors

A rule-based, AI-powered Decision Support System that evaluates stocks against your personal investment rules and generates plain-language buy/sell signals. Built as part of a Doctorate in Business Administration (DBA) dissertation at Golden Gate University.

---

## What it does

- Evaluates stocks on your **watchlist** against your BUY rules
- Evaluates stocks in your **portfolio** against your SELL rules
- Generates a **BUY / SELL / HOLD** signal for each stock
- Explains *why* each signal was generated in plain English
- Shows the underlying data behind every recommendation

All logic is driven by rules you write yourself in plain English. No coding required to customise the system.

---

## Prerequisites

- Python 3.10 or higher
- An Anthropic API key — sign up at [console.anthropic.com](https://console.anthropic.com)
- No other accounts or API keys required

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
pip install -r src/requirements.txt
```

### 4. Add your API key

Create a file named `.env` in the project root with the following content:

```
ANTHROPIC_API_KEY=your_key_here
```

Replace `your_key_here` with your actual Anthropic API key. This file is gitignored and will never be committed to version control.

---

## Configuration

Open `src/config.py`. This is the **only file you need to edit**.

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
`RSI`, `current price`, `52-week high`, `52-week low`, `PE ratio`, `EPS`, `SMA (50-day or 200-day)`, `volume`, `market cap`

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

### Portfolio — SELL evaluation

Edit `src/data/portfolio.csv`. One holding per row:

```
ticker,qty,entry_price,entry_date
JPM,10,195.50,2024-11-15
META,5,520.00,2024-10-03
```

Use the date format `YYYY-MM-DD`.

---

## Running the system

### Option A — Dashboard (recommended)

Launch the dashboard from inside the `src/` directory:

```bash
cd src
streamlit run dashboard/app.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`). Click **Run Analysis** to evaluate your stocks. Results appear on screen with expandable explanations and data.

### Option B — Terminal only

```bash
python src/main.py
```

Results are printed to the terminal and saved to the database. You can launch the dashboard afterwards to view them.

---

## How it works

1. The agent reads your rules from `config.py`
2. For each stock, it identifies which data points your rules reference
3. It fetches only those data points from Yahoo Finance (no API key required)
4. It evaluates the data against your rules and decides the signal
5. It writes a plain-language explanation of the signal
6. Results are saved locally to `db/signals.db` and displayed in the dashboard

Every run is logged to the database for auditability. The dashboard always shows the most recent run.

---

## Project structure

```
src/
├── agent/
│   ├── agent.py          # AI agent loop — one call per stock
│   ├── tools.py          # Yahoo Finance data wrappers
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
- Data is sourced from Yahoo Finance via the `yfinance` library. Occasional data gaps may occur.
- The AI agent (Claude) interprets your rules — write them clearly for best results.

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
