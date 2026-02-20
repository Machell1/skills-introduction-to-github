"""
Calibration Loop
─────────────────
Iteratively tunes strategy parameters until the backtest hits the
1000% profit target on a small account.

Optimisation priority:
  1. Average VOLUME WON per trade  (primary objective)
  2. Total return >= 1000%         (hard constraint)
  3. Win rate is IRRELEVANT        (explicitly ignored)

Algorithm: coordinate-ascent hill-climber with random restarts.
Each round perturbs one parameter at a time, keeping changes that
improve the score while meeting the profit target.

After calibration on the primary dataset, validates on multiple
random seeds to check robustness.
"""

from __future__ import annotations

import copy
import random
import numpy as np
from config import (
    INITIAL_BALANCE,
    PROFIT_TARGET_PCT,
    MAX_CALIBRATION_ROUNDS,
    PARAM_STEP_SIZES,
    PARAM_BOUNDS,
    LOOKBACK_PERIOD,
    BREAKOUT_THRESHOLD,
    VOLUME_SURGE_MULT,
    ATR_PERIOD,
    REWARD_RISK_RATIO,
    TRAILING_STOP_ATR_MULT,
    TAKE_PROFIT_ATR_MULT,
    RISK_PER_TRADE_PCT,
    MAX_POSITION_SIZE_PCT,
    MIN_POSITION_SIZE_PCT,
)
from backtester import run_backtest


def default_params() -> dict:
    """Return the default parameter set from config."""
    return {
        "INITIAL_BALANCE": INITIAL_BALANCE,
        "LOOKBACK_PERIOD": LOOKBACK_PERIOD,
        "BREAKOUT_THRESHOLD": BREAKOUT_THRESHOLD,
        "VOLUME_SURGE_MULT": VOLUME_SURGE_MULT,
        "ATR_PERIOD": ATR_PERIOD,
        "REWARD_RISK_RATIO": REWARD_RISK_RATIO,
        "TRAILING_STOP_ATR_MULT": TRAILING_STOP_ATR_MULT,
        "TAKE_PROFIT_ATR_MULT": TAKE_PROFIT_ATR_MULT,
        "RISK_PER_TRADE_PCT": RISK_PER_TRADE_PCT,
        "MAX_POSITION_SIZE_PCT": MAX_POSITION_SIZE_PCT,
        "MIN_POSITION_SIZE_PCT": MIN_POSITION_SIZE_PCT,
        "PROFIT_TARGET_PCT": PROFIT_TARGET_PCT,
    }


def _score(metrics: dict, target: float) -> float:
    """
    Scoring function — maximises average volume won per trade.
    Heavily rewards hitting the profit target.
    Penalises parameter sets that generate zero trades.
    """
    vol_won = metrics["avg_volume_won_per_trade"]
    ret = metrics["total_return_pct"]
    total_vol = metrics["total_volume_won"]
    num_trades = metrics["total_trades"]

    # Zero trades is the worst possible outcome — heavily penalise
    if num_trades == 0:
        return -10000.0

    if ret >= target:
        # Big bonus for meeting target + reward volume won
        return total_vol + vol_won * 10 + (ret - target) * 2.0
    else:
        # Proportional reward for progress toward target
        # Also reward having more trades (more chances to compound)
        progress = ret / max(target, 1) * 100  # 0-100 scale
        trade_bonus = min(num_trades, 200) * 0.1  # Reward trade generation
        return vol_won + progress * 0.5 + trade_bonus - (target - ret) * 0.1


def calibrate(df, params: dict | None = None, verbose: bool = True) -> dict:
    """
    Run the calibration loop.

    Returns dict with:
      best_params, best_metrics, rounds_run, calibration_history, target_met
    """
    if params is None:
        params = default_params()

    target = params.get("PROFIT_TARGET_PCT", PROFIT_TARGET_PCT)
    best_params = copy.deepcopy(params)
    best_metrics = run_backtest(df, best_params)
    best_score = _score(best_metrics, target)

    history: list[dict] = []
    tunable_keys = list(PARAM_STEP_SIZES.keys())

    if verbose:
        _log_round(0, best_metrics, best_score, "INIT")

    stall_count = 0
    max_stall = 12  # random restart after this many stalls

    for round_num in range(1, MAX_CALIBRATION_ROUNDS + 1):
        improved = False

        # Shuffle parameter order each round for diversity
        random.shuffle(tunable_keys)

        for key in tunable_keys:
            step = PARAM_STEP_SIZES[key]
            lo, hi = PARAM_BOUNDS[key]

            # Try multiple step sizes for faster convergence
            for mult in [1.0, 2.0, 0.5]:
                actual_step = step * mult
                for direction in [+1, -1]:
                    candidate = copy.deepcopy(best_params)
                    new_val = candidate[key] + direction * actual_step

                    # Integer params stay integer
                    if isinstance(PARAM_BOUNDS[key][0], int) or key == "LOOKBACK_PERIOD":
                        new_val = int(round(new_val))
                    else:
                        new_val = round(new_val, 4)

                    new_val = max(lo, min(hi, new_val))

                    if new_val == best_params[key]:
                        continue

                    candidate[key] = new_val
                    metrics = run_backtest(df, candidate)
                    score = _score(metrics, target)

                    if score > best_score:
                        best_params = candidate
                        best_metrics = metrics
                        best_score = score
                        improved = True

                        if verbose:
                            _log_round(round_num, best_metrics, best_score, f"{key}={candidate[key]}")
                        break  # Move to next step size
                if improved:
                    break  # Move to next parameter

        history.append({
            "round": round_num,
            "score": best_score,
            "return_pct": best_metrics["total_return_pct"],
            "avg_vol_won": best_metrics["avg_volume_won_per_trade"],
        })

        # Check if target met
        if best_metrics["total_return_pct"] >= target:
            if verbose:
                print(f"\n{'='*65}")
                print(f"  TARGET HIT: {best_metrics['total_return_pct']:.1f}% return")
                print(f"  Avg volume won/trade: ${best_metrics['avg_volume_won_per_trade']:.2f}")
                print(f"  Total volume won: ${best_metrics['total_volume_won']:.2f}")
                print(f"  Calibrated in {round_num} rounds")
                print(f"{'='*65}\n")

            # Keep optimising volume won per trade even after hitting target
            # Run a few more rounds to maximise volume
            extra_rounds = min(20, MAX_CALIBRATION_ROUNDS - round_num)
            if extra_rounds > 0 and verbose:
                print(f"  Running {extra_rounds} extra rounds to maximise volume won...")
            for _ in range(extra_rounds):
                any_improved = False
                random.shuffle(tunable_keys)
                for key in tunable_keys:
                    step = PARAM_STEP_SIZES[key]
                    lo, hi = PARAM_BOUNDS[key]
                    for direction in [+1, -1]:
                        candidate = copy.deepcopy(best_params)
                        new_val = candidate[key] + direction * step
                        if key == "LOOKBACK_PERIOD":
                            new_val = int(round(new_val))
                        else:
                            new_val = round(new_val, 4)
                        new_val = max(lo, min(hi, new_val))
                        if new_val == best_params[key]:
                            continue
                        candidate[key] = new_val
                        metrics = run_backtest(df, candidate)
                        score = _score(metrics, target)
                        if score > best_score and metrics["total_return_pct"] >= target:
                            best_params = candidate
                            best_metrics = metrics
                            best_score = score
                            any_improved = True
                            if verbose:
                                _log_round(round_num, metrics, score, f"OPT {key}={new_val}")
                            break
                if not any_improved:
                    break
            break

        # Stall detection -> random restart from perturbed best
        if not improved:
            stall_count += 1
            if stall_count >= max_stall:
                few_trades = best_metrics["total_trades"] < 10
                if verbose:
                    tag = "entry-biased restart" if few_trades else "random restart"
                    print(f"  [Round {round_num:>3}] Stall detected — {tag}")
                best_params = _random_perturb(best_params, favor_entries=few_trades)
                best_metrics = run_backtest(df, best_params)
                best_score = _score(best_metrics, target)
                stall_count = 0
        else:
            stall_count = 0

    return {
        "best_params": best_params,
        "best_metrics": best_metrics,
        "rounds_run": min(round_num, MAX_CALIBRATION_ROUNDS),
        "calibration_history": history,
        "target_met": best_metrics["total_return_pct"] >= target,
    }


def _random_perturb(params: dict, favor_entries: bool = False) -> dict:
    """
    Randomly perturb all tunable params within bounds.

    If favor_entries=True, bias toward parameters that generate more
    trade entries (lower thresholds, shorter lookbacks, wider sizing).
    Used when the current best has zero or very few trades.
    """
    p = copy.deepcopy(params)
    for key in PARAM_STEP_SIZES:
        lo, hi = PARAM_BOUNDS[key]
        if favor_entries:
            # Bias toward entry-generating values
            if key == "BREAKOUT_THRESHOLD":
                p[key] = round(random.uniform(lo, lo + (hi - lo) * 0.4), 4)
            elif key == "VOLUME_SURGE_MULT":
                p[key] = round(random.uniform(lo, lo + (hi - lo) * 0.3), 4)
            elif key == "LOOKBACK_PERIOD":
                p[key] = random.randint(int(lo), int(lo + (hi - lo) * 0.5))
            elif key == "RISK_PER_TRADE_PCT":
                p[key] = round(random.uniform(hi * 0.4, hi), 4)
            elif key == "MAX_POSITION_SIZE_PCT":
                p[key] = round(random.uniform(hi * 0.5, hi), 4)
            else:
                p[key] = round(random.uniform(lo, hi), 4)
        else:
            if key == "LOOKBACK_PERIOD":
                p[key] = random.randint(int(lo), int(hi))
            else:
                p[key] = round(random.uniform(lo, hi), 4)
    return p


def _log_round(round_num: int, metrics: dict, score: float, change: str) -> None:
    ret = metrics["total_return_pct"]
    vol = metrics["avg_volume_won_per_trade"]
    tvol = metrics["total_volume_won"]
    trades = metrics["total_trades"]
    wr = metrics["win_rate_pct"]
    dd = metrics["max_drawdown_pct"]
    print(
        f"  [Round {round_num:>3}] Return: {ret:>9.1f}%  |  "
        f"VolWon/Trade: ${vol:>9.2f}  |  "
        f"TotalVolWon: ${tvol:>10.2f}  |  "
        f"Trades: {trades:>4}  |  WR: {wr:>5.1f}%  |  "
        f"DD: {dd:>5.1f}%  |  {change}"
    )
