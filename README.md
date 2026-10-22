# Trading 212 Intraday Agent

An automated intraday trading agent for a Trading 212 **Invest** or **Stocks ISA**
account. The Trading 212 Public API does not support CFD accounts. The agent buys
on intraday momentum signals, manages each trade with a stop loss and a take profit,
and sells everything it opened before the market closes.

> ⚠️ **Risk warning.** This is example software, not financial advice. Intraday
> trading loses money for most people. The strategy has **not** been backtested on
> your instruments. Run it on the **demo (paper) account** for a while before you
> think about live money, and never trade money you can't afford to lose.

## How it works

| Part | File | What it does |
|---|---|---|
| API client | `t212_agent/t212_client.py` | Calls Trading 212 API v0: cash, positions, market orders. Retries on rate limits. |
| Market data | `t212_agent/data.py` | Gets 5-minute bars from Yahoo Finance, because the T212 API has no price history. |
| Strategy | `t212_agent/strategy.py` | **Buys** when the 9-EMA crosses above the 21-EMA while price is above the day's VWAP. **Sells** on the opposite cross or when price falls back below VWAP. Long only. |
| Risk | `t212_agent/risk.py` | Sizes each trade so hitting the stop costs about 0.5% of the account. Limits: 20% of the account per position, 3 open positions, 10 trades a day, and a 2% daily loss limit that stops trading for the day. |
| Agent loop | `t212_agent/agent.py` | Checks the market every 60 s. Skips the first 15 min after the open, opens no new trades in the last 30 min, and sells everything 10 min before the close. |

**Your existing holdings are safe.** The agent only manages positions it opened
itself. It records them in `agent_state.json`, so it never sells shares you
already held. Every trade is written to `trades.jsonl`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then edit .env
```

1. In the Trading 212 app, switch to **Practice** mode and go to
   **Settings → API (Beta)**. Generate a key with permissions for account data,
   portfolio, and orders (execute).
2. Copy the API key and secret into `.env`. The secret is shown only once.
3. Check the connection:

   ```bash
   python -m t212_agent --check
   ```

## Running

The safety settings unlock in stages:

| Stage | `.env` settings | What happens |
|---|---|---|
| 1. Dry run (default) | `T212_ENV=demo`, `DRY_RUN=true` | Reads your account and logs the trades it *would* make. |
| 2. Paper trading | `T212_ENV=demo`, `DRY_RUN=false` | Places real orders on the practice account. |
| 3. Live | `T212_ENV=live`, `DRY_RUN=false`, `I_UNDERSTAND_THIS_TRADES_REAL_MONEY=yes` | Real money. Live keys come from the app in real-money mode. |

```bash
python -m t212_agent            # run the loop (Ctrl+C sells managed positions and exits)
python -m t212_agent --flatten  # sell everything the agent opened, now
```

Leave it running during market hours, for example in `tmux`, on a small VPS, or
under `systemd`. If you restart it, it picks up its positions from
`agent_state.json`.

## Configuration

Set any of these in `.env` (defaults shown):

```
SYMBOLS=AAPL_US_EQ:AAPL,MSFT_US_EQ:MSFT,NVDA_US_EQ:NVDA   # T212 ticker:Yahoo symbol
TIMEZONE=America/New_York  SESSION_OPEN=09:30  SESSION_CLOSE=16:00
BAR_INTERVAL=5m  FAST_EMA=9  SLOW_EMA=21  ATR_PERIOD=14
STOP_ATR_MULT=1.5  TARGET_ATR_MULT=3.0  POLL_SECONDS=60
RISK_PER_TRADE_PCT=0.5  MAX_POSITION_PCT=20  MAX_OPEN_POSITIONS=3
MAX_DAILY_LOSS_PCT=2  MAX_TRADES_PER_DAY=10
```

To trade UK shares, use LSE tickers and London hours, for example
`SYMBOLS=VODl_EQ:VOD.L`, `TIMEZONE=Europe/London`, `SESSION_OPEN=08:00`,
`SESSION_CLOSE=16:30`. You can look up exact T212 tickers through the
`/equity/metadata/instruments` endpoint.

## Known limitations

- **Delayed data.** Yahoo intraday data can lag by a few minutes, and Yahoo is
  unofficial and rate-limited. For serious use, replace `data.get_bars` with a
  real-time feed such as Polygon, Alpaca data, or Finnhub. The function's return
  shape stays the same.
- **The agent handles stops itself.** Stops and targets are checked every
  `POLL_SECONDS`, not held at the broker. If the agent goes offline, open trades
  have no protection.
- **No market holidays.** The agent only knows about weekends and session times,
  so on a holiday or an early close it may keep trying.
- **Market orders only.** Expect some slippage. Instruments priced in a foreign
  currency also pay T212's FX fee on every trade, which matters a lot intraday.
- **API in beta.** The Trading 212 API is in beta and only executes orders in
  the account's primary currency.

## Tests

```bash
pip install pytest && pytest -q
```
