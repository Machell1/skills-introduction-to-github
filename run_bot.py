#!/usr/bin/env python3
"""
Smart Money Concepts (SMC) Trading Bot Launcher

Multi-Pair | 1H Timeframe | MT5 Platform | Deriv Broker

Supported pairs: XAUUSD, EURUSD, GBPUSD, USDJPY, GBPJPY, EURJPY
Each pair auto-loads an ICT/SMC-tuned profile (kill zones, displacement, spreads).

Usage:
    python run_bot.py                              # All 6 pairs (auto multi-pair)
    python run_bot.py --live                       # All 6 pairs, live trading
    python run_bot.py --symbol EURUSD              # Trade EURUSD only with auto-tuned profile
    python run_bot.py --config my_config.json      # Custom config, all pairs
    python run_bot.py --symbol XAUUSD --paper      # Single pair, paper mode

PyCharm Run Configuration:
    Script path:  run_bot.py
    Parameters:   --config smart_money_bot/settings.json --symbol EURUSD
    Working dir:  <project root>
    Python:       Python 3.9+ with MetaTrader5 package

Before running live:
    1. Install MT5 terminal and log in to your Deriv account
    2. Update settings.json with your MT5 login, password, server
    3. Set paper_trading to false (or use --live flag)
    4. Ensure your chosen symbol is visible in MT5 Market Watch
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for PyCharm compatibility
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from smart_money_bot.config import BotConfig
from smart_money_bot.bot import SMCBot


def setup_logging(log_level: str = "INFO", log_file: str = "smc_bot.log", symbol: str = ""):
    """Configure logging to both console and file."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create logs directory if needed
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    symbol_tag = f"_{symbol}" if symbol else ""
    log_path = log_dir / f"{datetime.utcnow().strftime('%Y%m%d')}{symbol_tag}_{log_file}"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # Always log everything to file
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console)
    root_logger.addHandler(file_handler)

    logging.getLogger("smart_money_bot").setLevel(level)


def load_config(config_path: str) -> BotConfig:
    """Load configuration from JSON file."""
    path = Path(config_path)
    if not path.exists():
        print(f"Config file not found: {config_path}")
        print("Creating default settings.json...")
        # Use default config
        return BotConfig()

    with open(path, "r") as f:
        data = json.load(f)

    return BotConfig.from_dict(data)


def load_config_with_symbol(config_path: str, symbol: str) -> BotConfig:
    """Load config and override the symbol before profile application.

    This ensures the symbol profile for *symbol* is applied during
    ``from_dict()``, not the profile for whatever symbol was in settings.json.
    """
    path = Path(config_path)
    if not path.exists():
        data = {}
    else:
        with open(path, "r") as f:
            data = json.load(f)

    # Inject symbol so from_dict() sees it during profile resolution
    data.setdefault("mt5", {})["symbol"] = symbol
    return BotConfig.from_dict(data)


def print_banner(symbol: str = "XAU/USD"):
    """Print startup banner."""
    sym_display = symbol if symbol else "XAU/USD"
    banner = f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║         SMART MONEY CONCEPTS (SMC) TRADING BOT             ║
    ║                                                            ║
    ║  {sym_display:^8s}  |  1H Timeframe  |  MT5  |  Deriv Broker        ║
    ║                                                            ║
    ║  Templates: Reversal (Sweep->MSS->OB) + Continuation (BOS)║
    ║  Risk: Fractional sizing, drawdown brakes, exposure caps   ║
    ╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_config_summary(config: BotConfig):
    """Print a summary of the active configuration."""
    print("\n── Configuration Summary ──")
    print(f"  Symbol:           {config.mt5.symbol}")
    print(f"  Server:           {config.mt5.server}")
    print(f"  Magic Number:     {config.mt5.magic_number}")
    print(f"  Paper Trading:    {config.execution.paper_trading}")
    print(f"  Templates:        {[t.value for t in config.active_templates]}")
    print(f"  Risk/Trade:       {config.risk.risk_per_trade_pct}%")
    print(f"  Max Positions:    {config.risk.max_positions}")
    print(f"  Daily Loss Limit: {config.risk.daily_loss_limit_pct}%")
    print(f"  Swing Length:     {config.swing.swing_length}")
    print(f"  Displacement k:   {config.displacement.body_atr_multiplier}")
    print(f"  OB Entry f:       {config.order_block.entry_fraction}")
    print(f"  Stop Buffer b:    {config.stop.atr_buffer_multiplier} ATR")
    print(f"  Target Mode:      {config.target.mode.value}")
    if config.target.mode.value == "fixed_r":
        print(f"  Target R:         {config.target.fixed_r_multiple}")
    else:
        print(f"  Target R Range:   {config.target.liquidity_min_r}-{config.target.liquidity_max_r}")
    print(f"  Break-even:       {'Enabled' if config.trade_mgmt.breakeven_enabled else 'Disabled'}")
    print(f"  Max Hold:         {config.trade_mgmt.max_hold_candles} candles ({config.trade_mgmt.max_hold_candles}h)")
    print(f"  Bias Filter:      {'EMA' + str(config.bias_filter.ema_period) if config.bias_filter.enabled else 'Disabled'}")
    print(f"  Check Interval:   {config.execution.check_interval_seconds}s")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="SMC Trading Bot — Multi-Pair on MT5 (Deriv)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_bot.py                              # All 6 pairs (auto multi-pair)
  python run_bot.py --live                       # All 6 pairs, live trading
  python run_bot.py --symbol EURUSD              # Trade EURUSD only
  python run_bot.py --symbol GBPJPY --paper      # GBPJPY in paper mode
  python run_bot.py --config my_settings.json    # Custom config, all pairs
  python run_bot.py --paper --log-level DEBUG    # Verbose paper mode
        """,
    )
    parser.add_argument(
        "--config", "-c",
        default=str(project_root / "smart_money_bot" / "settings.json"),
        help="Path to JSON configuration file (default: smart_money_bot/settings.json)",
    )
    parser.add_argument(
        "--symbol", "-s",
        default=None,
        help="Trading symbol (overrides config). Auto-applies symbol profile.",
    )
    parser.add_argument(
        "--paper",
        action="store_true",
        help="Force paper trading mode (overrides config)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Force live trading mode (overrides config)",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override log level from config",
    )
    parser.add_argument(
        "--login",
        type=int,
        default=None,
        help="MT5 login (overrides config)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="MT5 password (overrides config)",
    )
    parser.add_argument(
        "--server",
        default=None,
        help="MT5 server (overrides config)",
    )

    args = parser.parse_args()

    # No --symbol specified → launch all 6 pairs via run_multi.py
    if not args.symbol:
        import subprocess as _sp
        multi_cmd = [sys.executable, str(project_root / "run_multi.py"),
                     "--config", args.config]
        if args.paper:
            multi_cmd.append("--paper")
        elif args.live:
            multi_cmd.append("--live")
        if args.log_level:
            multi_cmd.extend(["--log-level", args.log_level])
        print("  No --symbol specified — launching all 6 pairs automatically.")
        sys.exit(_sp.call(multi_cmd, cwd=str(project_root)))

    config = load_config_with_symbol(args.config, args.symbol)

    print_banner(config.mt5.symbol)

    # Apply CLI overrides
    if args.paper:
        config.execution.paper_trading = True
    elif args.live:
        config.execution.paper_trading = False

    if args.log_level:
        config.execution.log_level = args.log_level
    if args.login:
        config.mt5.login = args.login
    if args.password:
        config.mt5.password = args.password
    if args.server:
        config.mt5.server = args.server

    # Per-symbol trade journal
    if config.mt5.symbol != "XAUUSD":
        config.execution.trade_journal_path = f"trade_journal_{config.mt5.symbol}.csv"

    # Setup logging (per-symbol log file)
    setup_logging(config.execution.log_level, config.execution.log_file, config.mt5.symbol)

    # Print config
    print_config_summary(config)

    # Validate MT5 credentials for live mode
    if not config.execution.paper_trading:
        if config.mt5.login == 0 or not config.mt5.password:
            print("ERROR: Live trading requires MT5 login credentials.")
            print("Set them in settings.json or via --login and --password flags.")
            sys.exit(1)

    # Create and start bot
    bot = SMCBot(config)

    try:
        bot.start()
    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
        bot.stop()
    except Exception as e:
        logging.exception("Fatal error: %s", e)
        bot.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
