# Claw Claw

Claw Claw is a safety-first, multi-bot BTCUSD trading framework for MetaTrader 5 (Deriv). It runs locally, connects to a logged-in MT5 terminal, and evaluates strategies on closed M5 candles. Only the centralized trade controller can execute orders, and every trade is gated by risk checks.

## Key Features

- **Hub-and-spoke architecture**: bots only propose trades; the execution engine is centralized.
- **Risk Gate** with strict controls: one-trade-at-a-time, max trades/day, cooldowns, max spread, daily loss limit, consecutive-loss breaker, exposure caps, slippage controls, and stake-based loss cuts.
- **Deriv symbol resolver** to handle suffix variations like `BTCUSD.` or `BTCUSDm`.
- **Paper/Demo/Live modes** with an explicit unlock phrase for demo/live.
- **Kill switch** file to halt trading immediately.
- **Rotating logs** with redaction and a local SQLite audit store.

## Project Structure

```
claw_claw/
  main.py
  config.json
  mt5_connector.py
  symbol_resolver.py
  data_feed.py
  bots/
    __init__.py
    init.py
    base.py
    trend_bot.py
    mean_reversion_bot.py
    arbiter.py
  risk_manager.py
  execution.py
  trade_monitor.py
  state.py
  audit_db.py
  logger.py
  utils.py
requirements.txt
README.md
```

## Setup (PyCharm on Windows)

**Easiest option (automatic setup):**
1. Double-click `setup_pycharm_windows.bat`.
2. Wait for it to finish installing everything.
3. Open the project in PyCharm and select the `.venv` interpreter it created.
4. Run:
   - `claw_claw_full.py` (single-file option), or
   - `claw_claw/main.py` (modular package).

**Manual option (if you prefer):**
1. **Clone the repository** and open it in PyCharm.
2. **Create a virtual environment** (Python 3.9):
   - PyCharm: *File → Settings → Project → Python Interpreter → Add Interpreter*.
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Open MT5 and log in to Deriv**. Ensure the terminal is connected.
5. **Run the bot**:
   - In PyCharm, run `claw_claw/main.py`.
   - Single-file option: run `claw_claw_full.py` from the repository root.

> **Important:** The system uses `mt5.initialize()` without credentials by default. Do **not** store credentials in files. If you want to enable auto-login, set environment variables (`MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`) and set `auto_login` to `true` in `config.json`.

## Operating Modes

- **paper** (default): no orders are sent; logs decisions only.
- **demo/live**: orders are allowed only if you type the exact unlock phrase on startup.

Unlock phrase default: `I UNDERSTAND LIVE RISK` (configurable in `config.json`).

## Kill Switch

Create a file named `KILL_SWITCH` in the project root to block new trades. If `flatten_on_kill_switch` is `true`, the system will also close any open position.

## Symbol Safety

Deriv may use suffixes for BTCUSD. The resolver tries the configured symbol first and then searches Market Watch symbols containing `BTC` and `USD`. The resolved symbol is locked for all trades.

## Logs and Audit Database

- **Logs**: `logs/trading.log` and `logs/audit.log`
- **SQLite DB**: `clawclaw.db`

The logs are redacted to avoid leaking sensitive information. The database stores decisions, orders, trades, equity snapshots, and errors.

## Strategy Bots

Two example bots are included:

- **TrendBot**: simple moving average bias.
- **MeanReversionBot**: price deviation from a mean.

To add your own bot, subclass `BaseBot` and add it to the list in `main.py`.

## Safety Warnings

- **Use demo first.** BTC is highly volatile and spreads can widen rapidly.
- **Execution is not guaranteed** during spikes or disconnections.
- **Do not run live** without understanding the risks and verifying all settings.

## Dry-Run Simulation

A helper `dry_run_simulation()` function is included in `main.py` to validate proposal selection without sending orders.

## Running Tests

Run unit tests with:

```bash
python -m unittest
```
