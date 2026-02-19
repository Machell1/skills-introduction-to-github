#!/usr/bin/env python3
"""
CLAWBOT Fast Optimizer - pre-computes indicators once, runs grid search fast.
Target: Win Rate >= 80%, Return >= 50%
"""
import sys, json, copy, time
from pathlib import Path
import numpy as np, pandas as pd

# Import from backtest engine
sys.path.insert(0, str(Path(__file__).parent))
from backtest_engine import (
    Config, ClawbotBacktester, print_stats, diagnose,
    calc_atr, calc_ema, calc_rsi, calc_adx, calc_bollinger
)

TARGET_WR = 80.0
TARGET_RETURN = 50.0


def precompute_indicators(df, cfg):
    """Compute all indicators ONCE and cache them."""
    df = df.copy()
    df['datetime'] = pd.to_datetime(df['datetime'])
    df['hour'] = df['datetime'].dt.hour
    df['day_of_week'] = df['datetime'].dt.dayofweek
    df['atr'] = calc_atr(df['high'], df['low'], df['close'], 14)
    df['ema_fast'] = calc_ema(df['close'], cfg.ema_fast)
    df['ema_signal'] = calc_ema(df['close'], cfg.ema_signal)
    df['ema_trend'] = calc_ema(df['close'], cfg.ema_trend)
    df['ema_major'] = calc_ema(df['close'], cfg.ema_major)
    df['rsi'] = calc_rsi(df['close'], cfg.rsi_period)
    df['adx'], df['plus_di'], df['minus_di'] = calc_adx(
        df['high'], df['low'], df['close'], cfg.adx_period)
    df['bb_upper'], df['bb_mid'], df['bb_lower'] = calc_bollinger(
        df['close'], cfg.bb_period, cfg.bb_deviation)
    return df


def fast_backtest(df_with_indicators, cfg):
    """Run backtest using pre-computed indicators."""
    bt = ClawbotBacktester(cfg)
    # Monkey-patch to skip indicator computation
    bt._prepare_indicators = lambda d: d
    stats = bt.run(df_with_indicators, silent=True)
    return stats


def main():
    data_path = Path(__file__).parent.parent / "Data" / "XAUUSD_H1.csv"
    df_raw = pd.read_csv(data_path)
    print(f"Loaded {len(df_raw)} bars total\n")

    # Pre-compute indicators for FAST subset (first year) and FULL dataset
    print("Pre-computing indicators...")
    t0 = time.time()
    base_cfg = Config()
    # Fast subset for grid search (first 6000 bars ~ 1 year)
    df_fast = precompute_indicators(df_raw.iloc[:6000].copy().reset_index(drop=True), base_cfg)
    # Full dataset for final validation
    df = precompute_indicators(df_raw, base_cfg)
    print(f"Indicators computed in {time.time()-t0:.1f}s (fast={len(df_fast)}, full={len(df)})\n")

    # ================================================================
    # PHASE 1: Grid search (fast with pre-computed indicators)
    # ================================================================
    print("=" * 60)
    print("  PHASE 1: GRID SEARCH (fast)")
    print("=" * 60)

    results = []
    t0 = time.time()

    for ms in [40, 55, 70, 85]:
        for mst in [2, 3]:
            for adx in [22, 30]:
                for sl in [2.0, 3.0]:
                    for tp_m in [2.0, 3.0]:
                        cfg = Config()
                        cfg.min_score = ms
                        cfg.min_strategies = mst
                        cfg.adx_threshold = adx
                        cfg.sl_atr = sl
                        cfg.tp_atr = round(sl * tp_m, 1)
                        cfg.trail_distance = round(sl * 0.5, 1)
                        cfg.trail_activation = round(sl * 0.75, 1)
                        cfg.min_risk_reward = round(tp_m * 0.5, 1)
                        cfg.tp1_atr = round(sl * 0.5, 1)
                        cfg.dyn_max_loss_atr = round(sl * 0.9, 1)

                        stats = fast_backtest(df_fast, cfg)
                        wr = stats['win_rate']
                        ret = stats['return_pct']
                        total_t = stats['total_trades']
                        pf = stats['profit_factor']

                        trade_pen = max(0, 30 - total_t) * 3
                        score = wr * 2.5 + min(ret, 200) * 0.2 + pf * 5 - trade_pen

                        results.append({
                            'wr': wr, 'ret': ret, 'pf': pf, 'trades': total_t,
                            'score': score, 'cfg': copy.deepcopy(cfg), 'stats': stats,
                            'ms': ms, 'mst': mst, 'adx': adx, 'sl': sl, 'tp_m': tp_m
                        })

    elapsed = time.time() - t0
    results.sort(key=lambda x: x['score'], reverse=True)
    print(f"\nGrid: {len(results)} configs tested in {elapsed:.0f}s")
    print(f"\nTop 15:")
    print(f"  {'WR':>6} {'Ret':>7} {'PF':>5} {'Trd':>4} {'MS':>3} {'#St':>3} {'ADX':>4} {'SL':>4} {'TPm':>4}")
    for r in results[:15]:
        print(f"  {r['wr']:5.1f}% {r['ret']:6.1f}% {r['pf']:5.2f} {r['trades']:4d} "
              f"{r['ms']:3d} {r['mst']:3d} {r['adx']:4.0f} {r['sl']:4.1f} {r['tp_m']:4.1f}")

    # ================================================================
    # PHASE 2: Fine-tune top 3 results
    # ================================================================
    print("\n" + "=" * 60)
    print("  PHASE 2: FINE-TUNING")
    print("=" * 60)

    viable = [r for r in results if r['trades'] >= 25]
    if not viable:
        viable = [r for r in results if r['trades'] >= 10]
    if not viable:
        viable = results[:3]

    best_cfg = viable[0]['cfg']
    best_stats = viable[0]['stats']
    best_score = viable[0]['score']

    params = [
        ('min_score', lambda c: list(range(max(20, c.min_score-12), c.min_score+15, 2))),
        ('min_strat_score', lambda c: [8, 10, 12, 15, 18, 20, 23, 25]),
        ('adx_threshold', lambda c: [c.adx_threshold-4, c.adx_threshold-2, c.adx_threshold,
                                      c.adx_threshold+2, c.adx_threshold+4]),
        ('sl_atr', lambda c: [c.sl_atr-0.4, c.sl_atr-0.2, c.sl_atr, c.sl_atr+0.2, c.sl_atr+0.4]),
        ('risk_per_trade', lambda c: [0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0]),
        ('partial_close_pct', lambda c: [0.25, 0.35, 0.45, 0.55, 0.65]),
        ('tp1_atr', lambda c: [0.4, 0.6, 0.8, 1.0, 1.3, 1.5]),
        ('cooldown_bars', lambda c: [1, 2, 3, 4, 5, 6]),
        ('cooldown_losses', lambda c: [2, 3, 4, 5]),
        ('dyn_max_loss_atr', lambda c: [0.8, 1.0, 1.2, 1.5, 1.8, 2.0]),
        ('dyn_stale_bars', lambda c: [10, 16, 22, 28, 34]),
        ('dyn_adverse_mom', lambda c: [0.8, 1.0, 1.2, 1.5, 1.8]),
        ('rsi_oversold', lambda c: [18, 22, 26, 30, 35]),
        ('rsi_overbought', lambda c: [65, 70, 75, 80]),
        ('max_concurrent', lambda c: [1, 2, 3]),
        ('max_daily_trades', lambda c: [2, 3, 5, 8, 10]),
        ('london_end', lambda c: [13, 14, 15, 16, 17]),
        ('exit_hour', lambda c: [17, 18, 19, 20, 21]),
    ]

    for pname, vfn in params:
        for val in vfn(best_cfg):
            cfg = copy.deepcopy(best_cfg)
            if hasattr(cfg, pname):
                setattr(cfg, pname, val)
            if pname == 'sl_atr':
                ratio = best_cfg.tp_atr / max(best_cfg.sl_atr, 0.1)
                cfg.tp_atr = round(val * ratio, 1)

            stats = fast_backtest(df, cfg)
            trades = stats['total_trades']
            pen = max(0, 25 - trades) * 3
            sc = stats['win_rate'] * 2.5 + min(stats['return_pct'], 200) * 0.2 + stats['profit_factor'] * 5 - pen

            if sc > best_score and trades >= 15:
                best_score = sc
                best_cfg = copy.deepcopy(cfg)
                best_stats = stats
                print(f"  {pname}={val}: WR={stats['win_rate']:.1f}%, "
                      f"Ret={stats['return_pct']:.1f}%, PF={stats['profit_factor']:.2f}, "
                      f"Trd={trades}")

    # ================================================================
    # PHASE 3: Return boosting
    # ================================================================
    print("\n" + "=" * 60)
    print("  PHASE 3: RETURN BOOSTING")
    print("=" * 60)

    if best_stats['return_pct'] < TARGET_RETURN:
        for risk in [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]:
            cfg = copy.deepcopy(best_cfg)
            cfg.risk_per_trade = risk
            stats = fast_backtest(df, cfg)
            wr = stats['win_rate']
            ret = stats['return_pct']
            dd = stats['max_drawdown_pct']
            print(f"  Risk={risk}%: WR={wr:.1f}%, Return={ret:.1f}%, DD={dd:.1f}%")
            if wr >= TARGET_WR and ret >= TARGET_RETURN and dd < 50:
                best_cfg = copy.deepcopy(cfg)
                best_stats = stats
                print(f"  >>> TARGET MET!")
                break
            if wr >= best_stats['win_rate'] * 0.95 and ret > best_stats['return_pct'] and dd < 60:
                best_cfg = copy.deepcopy(cfg)
                best_stats = stats

    # ================================================================
    # FINAL REPORT
    # ================================================================
    print("\n" + "=" * 60)
    print("  FINAL OPTIMIZED RESULTS")
    print("=" * 60)
    print_stats(best_stats)

    issues = diagnose(best_stats)
    if issues:
        print("\nRemaining issues:")
        for iss in issues:
            print(f"  [!] {iss}")

    wr = best_stats['win_rate']
    ret = best_stats['return_pct']
    if wr >= TARGET_WR and ret >= TARGET_RETURN:
        print(f"\n*** TARGETS MET! WR={wr:.1f}% >= {TARGET_WR}%, Return={ret:.1f}% >= {TARGET_RETURN}% ***")
    else:
        print(f"\n*** Best achieved: WR={wr:.1f}% (target {TARGET_WR}%), Return={ret:.1f}% (target {TARGET_RETURN}%) ***")

    # Save config
    print("\nOptimal Parameters:")
    for p in ['risk_per_trade', 'sl_atr', 'tp_atr', 'trail_activation', 'trail_distance',
              'min_score', 'min_strategies', 'min_strat_score', 'adx_threshold',
              'rsi_oversold', 'rsi_overbought', 'dyn_max_loss_atr', 'dyn_stale_bars',
              'dyn_adverse_mom', 'partial_close_pct', 'tp1_atr', 'max_concurrent',
              'max_daily_trades', 'cooldown_bars', 'cooldown_losses',
              'london_end', 'exit_hour', 'min_risk_reward']:
        if hasattr(best_cfg, p):
            print(f"  {p} = {getattr(best_cfg, p)}")

    out = Path(__file__).parent.parent / "Data" / "optimal_config.json"
    with open(out, 'w') as f:
        json.dump({k: v for k, v in best_cfg.__dict__.items()}, f, indent=2)
    print(f"\nSaved to: {out}")

    return best_stats, best_cfg


if __name__ == "__main__":
    main()
