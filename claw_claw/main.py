"""Claw Claw trading system entry point."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import MetaTrader5 as mt5

from claw_claw import mt5_connector
from claw_claw.audit_db import AuditDB
from claw_claw.bots.arbiter import Arbiter
from claw_claw.bots.mean_reversion_bot import MeanReversionBot
from claw_claw.bots.trend_bot import TrendBot
from claw_claw.data_feed import fetch_candles
from claw_claw.execution import ExecutionEngine
from claw_claw.logger import setup_logger
from claw_claw.risk_manager import RiskManager
from claw_claw.state import MarketContext, Proposal, TradeState
from claw_claw.symbol_resolver import ensure_symbol_enabled, resolve_symbol
from claw_claw.trade_monitor import TradeMonitor
from claw_claw.utils import kill_switch_triggered, load_config, utc_now

TIMEFRAME_MAP = {
    "M5": mt5.TIMEFRAME_M5,
}


def _prompt_unlock(config: dict) -> str:
    mode = config["mode"].lower()
    if mode in {"demo", "live"}:
        phrase = input(
            "Type the exact unlock phrase to enable demo/live mode: "
        ).strip()
        if phrase != config["unlock_phrase"]:
            print("Unlock phrase not provided. Falling back to paper mode.")
            return "paper"
    return mode


def _resolve_timeframe(config: dict) -> int:
    timeframe = config["timeframe"].upper()
    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return TIMEFRAME_MAP[timeframe]


def _collect_proposals(bots, market: MarketContext) -> List[Proposal]:
    proposals: List[Proposal] = []
    for bot in bots:
        proposal = bot.propose(market)
        if proposal is not None:
            proposals.append(proposal)
    return proposals


def _log_proposals(logger, proposals: List[Proposal]) -> None:
    for proposal in proposals:
        logger.info(
            "Proposal %s %s confidence=%.2f",
            proposal.bot_name,
            proposal.direction,
            proposal.confidence,
        )


def _update_state_on_close(state: TradeState, config: dict, audit_db: AuditDB) -> None:
    history = mt5.history_deals_get(datetime.now() - timedelta(days=1), datetime.now())
    if history is None:
        return
    relevant = [d for d in history if d.magic == config["magic"]]
    if not relevant:
        return
    last = relevant[-1]
    if last.profit < 0:
        state.consecutive_losses += 1
    else:
        state.consecutive_losses = 0
    state.realized_pnl += last.profit
    audit_db.log_trade(
        {
            "entry_time": datetime.fromtimestamp(last.time).isoformat(),
            "exit_time": datetime.fromtimestamp(last.time).isoformat(),
            "symbol": last.symbol,
            "direction": "buy" if last.type == mt5.DEAL_TYPE_BUY else "sell",
            "volume": last.volume,
            "entry_price": last.price,
            "exit_price": last.price,
            "sl": 0.0,
            "tp": 0.0,
            "pnl": last.profit,
            "pnl_pct": 0.0,
            "risk_amount": 0.0,
            "drawdown_at_entry": state.daily_drawdown_pct,
            "spread_at_entry": 0.0,
            "bot_name": "",
            "rationale": "",
        }
    )


def dry_run_simulation() -> None:
    fake_candles = [
        {"time": datetime.now(), "open": 100, "high": 105, "low": 95, "close": 100, "tick_volume": 1}
        for _ in range(40)
    ]
    market = MarketContext(
        symbol="BTCUSD",
        timeframe=mt5.TIMEFRAME_M5,
        candles=fake_candles,
        last_closed_time=datetime.now(),
        spread_points=10.0,
    )
    bots = [TrendBot(), MeanReversionBot()]
    proposals = _collect_proposals(bots, market)
    arbiter = Arbiter()
    selected = arbiter.select(proposals)
    print("Dry run selected:", selected.bot_name if selected else "None")


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    config_path = Path(__file__).resolve().parent / "config.json"
    config = load_config(config_path)

    logs_dir = project_root / "logs"
    trade_logger = setup_logger(logs_dir, "trading", "trading.log")
    audit_logger = setup_logger(logs_dir, "audit", "audit.log")

    print("Please open MetaTrader 5 and log in to Deriv. Press Enter when ready.")
    input()

    connected, message = mt5_connector.connect(
        auto_login=bool(config.get("auto_login")),
        retries=int(config.get("connection_retries", 3)),
        delay_seconds=float(config.get("connection_delay_seconds", 2.0)),
    )
    if not connected:
        print(message)
        return
    if not mt5_connector.is_ready():
        print("MT5 terminal is not ready (account info unavailable).")
        mt5_connector.shutdown()
        return

    resolved = resolve_symbol(config["symbol_preferred"])
    if resolved is None:
        print("Could not resolve BTCUSD symbol.")
        mt5_connector.shutdown()
        return

    if not ensure_symbol_enabled(resolved):
        print("Failed to enable symbol.")
        mt5_connector.shutdown()
        return

    config["resolved_symbol"] = resolved
    print(f"Resolved symbol: {resolved}")

    config["mode"] = _prompt_unlock(config)
    print(f"Mode: {config['mode']}")

    timeframe = _resolve_timeframe(config)
    bots = [TrendBot(), MeanReversionBot()]
    arbiter = Arbiter()
    risk_manager = RiskManager(config)
    execution = ExecutionEngine(config, trade_logger)
    audit_db = AuditDB(project_root / "clawclaw.db")
    monitor = TradeMonitor(config, project_root, trade_logger, audit_db)
    state = TradeState()

    while True:
        if kill_switch_triggered(project_root):
            trade_logger.info("Kill switch active: no new trades.")
            time.sleep(5)
            continue
        if not mt5_connector.is_ready():
            trade_logger.info("MT5 not ready or disconnected; waiting.")
            time.sleep(5)
            continue

        equity = mt5_connector.account_equity()
        if equity is None:
            trade_logger.info("Equity unavailable.")
            time.sleep(5)
            continue
        audit_db.log_equity(utc_now().isoformat(), equity)

        candles = fetch_candles(resolved, timeframe, 200)
        if len(candles) < 3:
            time.sleep(10)
            continue

        last_closed = candles[-2]
        last_closed_time = last_closed["time"]
        if state.last_processed_candle_time == last_closed_time:
            time.sleep(5)
            continue

        tick = mt5.symbol_info_tick(resolved)
        info = mt5.symbol_info(resolved)
        if tick is None or info is None:
            time.sleep(5)
            continue

        spread_points = (tick.ask - tick.bid) / info.point
        market = MarketContext(
            symbol=resolved,
            timeframe=timeframe,
            candles=candles[:-1],
            last_closed_time=last_closed_time,
            spread_points=spread_points,
        )

        proposals = _collect_proposals(bots, market)
        _log_proposals(audit_logger, proposals)
        selected = arbiter.select(proposals)

        audit_db.log_decision(
            {
                "timestamp": utc_now().isoformat(),
                "symbol": resolved,
                "bot_name": selected.bot_name if selected else "",
                "direction": selected.direction if selected else "",
                "confidence": selected.confidence if selected else 0.0,
                "rationale": selected.rationale if selected else "",
                "arbiter_decision": selected.bot_name if selected else "none",
                "risk_allowed": 0,
                "risk_reasons": "",
            }
        )

        if selected is None:
            state.last_processed_candle_time = last_closed_time
            time.sleep(2)
            continue

        decision = risk_manager.evaluate(selected, state, equity)
        audit_db.log_decision(
            {
                "timestamp": utc_now().isoformat(),
                "symbol": resolved,
                "bot_name": selected.bot_name,
                "direction": selected.direction,
                "confidence": selected.confidence,
                "rationale": selected.rationale,
                "arbiter_decision": selected.bot_name,
                "risk_allowed": int(decision.allowed),
                "risk_reasons": ";".join(decision.reasons),
            }
        )

        if not decision.allowed:
            trade_logger.info("Risk veto: %s", ";".join(decision.reasons))
            state.last_processed_candle_time = last_closed_time
            time.sleep(2)
            continue

        if config["mode"] == "paper":
            trade_logger.info("Paper mode: trade not sent.")
            state.last_processed_candle_time = last_closed_time
            state.trades_today += 1
            state.last_trade_time = datetime.now()
            time.sleep(2)
            continue

        ticket = execution.send_order(selected, decision.volume)
        if ticket is not None:
            state.trades_today += 1
            state.last_trade_time = datetime.now()
            state.open_position_ticket = ticket
            state.total_volume += decision.volume
            audit_db.log_order(
                {
                    "timestamp": utc_now().isoformat(),
                    "ticket": ticket,
                    "symbol": resolved,
                    "direction": selected.direction,
                    "volume": decision.volume,
                    "entry_price": tick.ask if selected.direction == "buy" else tick.bid,
                    "sl": selected.suggested_sl,
                    "tp": selected.suggested_tp,
                    "spread": spread_points,
                }
            )

            snapshot = monitor.snapshot_position(resolved, config["magic"])
            if snapshot is not None:
                info = mt5.symbol_info(resolved)
                if info is not None:
                    point_value = info.trade_tick_value / info.trade_tick_size
                    sl_distance = abs(snapshot.price_open - snapshot.sl)
                    snapshot.risk_amount = (sl_distance / info.point) * point_value * snapshot.volume
                monitor.monitor(state, snapshot)
            else:
                trade_logger.info("Position not found after execution.")
        else:
            trade_logger.info("Order failed; backing off.")
            time.sleep(5)

        _update_state_on_close(state, config, audit_db)
        print(audit_db.daily_summary())
        state.last_processed_candle_time = last_closed_time
        time.sleep(2)


if __name__ == "__main__":
    main()
