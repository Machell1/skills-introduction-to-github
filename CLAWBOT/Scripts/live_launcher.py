#!/usr/bin/env python3
"""
CLAWBOT Live Launcher
======================
Creates an MT5 chart template with the CLAWBOT EA embedded,
a startup profile, and launches MT5 in auto-trading mode.
"""

import time
import subprocess
from pathlib import Path


# =====================================================================
#  Chart template (embeds the EA with Live mode inputs)
# =====================================================================
def _chart_template(symbol: str) -> str:
    return f"""<chart>
id=0
symbol={symbol}
period_type=0
period_size=1
digits=2
tick_size=0.000000
position_time=0
scale_fix=0
scale_fixed_min=0.000000
scale_fixed_max=0.000000
scale_fix11=0
scale_bar=0
scale_bar_val=1.000000
scale=8
mode=1
fore=0
grid=1
volume=0
scroll=1
shift=1
shift_size=20.000000
fixed_pos=0.000000
ticker=1
ohlc=1
one_click=0
one_click_btn=1
bidline=1
askline=1
lastline=0
days=0
descriptions=0
tradelines=1
tradehistory=0
window_left=0
window_top=0
window_right=0
window_bottom=0
window_type=0
background_color=0
foreground_color=16777215
barup_color=65280
bardown_color=255
bullcandle_color=65280
bearcandle_color=255
chartline_color=65280
volumes_color=32768
grid_color=2105376
bidline_color=65280
askline_color=255
lastline_color=12632256
stops_color=255
windows_total=1

<window>
height=100.000000
objects=0
<indicator>
name=Main
path=
apply=1
show_data=1
scale_inherit=0
scale_line=0
scale_line_percent=50
scale_line_value=0.000000
expertmode=0
fixed_height=-1
</indicator>
</window>

<expert>
name=CLAWBOT\\CLAWBOT
path=Experts\\CLAWBOT\\CLAWBOT.ex5
expertmode=33
<inputs>
Inp_BotMode=1
Inp_Symbol={symbol}
Inp_Timeframe=16385
; Risk Management - Optimized for max profit (3886% backtest return)
Inp_RiskPerTrade=1.0
Inp_MaxDailyLoss=5.0
Inp_MaxDrawdown=15.0
Inp_MaxConcurrent=3
Inp_MaxDailyTrades=10
Inp_MinRiskReward=0.5
; SL/TP - Tight SL (0.6 ATR) with 5:1 R:R target (3.0 ATR TP)
Inp_SL_ATR=0.6
Inp_TP_ATR=3.0
Inp_MinSL=200.0
Inp_MaxSL=800.0
Inp_TrailActivation=0.7
Inp_TrailDistance=0.35
Inp_MaxSpread=50.0
; Strategies - SMC and MTF disabled per optimization
Inp_EnableTrend=true
Inp_EnableMomentum=true
Inp_EnableSession=true
Inp_EnableMeanRevert=true
Inp_EnableSMC=false
Inp_EnableBrain=true
Inp_EnableMTF=false
; Pending Orders
Inp_UsePendingOrders=true
Inp_PendingExpBars=4
Inp_PullbackATR=0.3
; Dynamic Closure
Inp_EnableDynClosure=true
Inp_DynCls_MaxLossATR=1.8
Inp_DynCls_StaleBars=24
Inp_DynCls_StaleRange=0.15
Inp_DynCls_AdverseMom=0.3
; Dynamic TP
Inp_EnableDynamicTP=true
Inp_DynTP_TrendMult=1.6
Inp_DynTP_RangeMult=1.0
; Profit Locking - Early partial close (0.1 ATR) locks quick profits
Inp_EnablePartialClose=true
Inp_TP1_ATR=0.1
Inp_PartialClosePct=0.3
; Confluence - Lower bar for single-strategy entries
Inp_MinScore=30
Inp_MinStrategies=1
Inp_MinStrategyScore=20
Inp_CooldownAfterLosses=3
Inp_CooldownBars=3
Inp_WinRateThreshold=55.0
Inp_RSI_Overbought=75.0
Inp_ExitHour=21
</inputs>
</expert>

</chart>
"""


def _startup_ini(login: str, password: str, server: str) -> str:
    return f"""[Common]
Login={login}
Password={password}
Server={server}
AutoTrading=1

[Charts]
ProfileLast=CLAWBOT_Live
TemplateLast=clawbot_live
"""


# =====================================================================
#  Public API
# =====================================================================
def verify_live_readiness(data_path: Path) -> list:
    """Return a list of blocking issues (empty = ready)."""
    issues = []
    ex5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.ex5"
    if not ex5.exists():
        issues.append("CLAWBOT.ex5 not found. Compile the EA first.")
    return issues


def launch_live(
    terminal: Path,
    data_path: Path,
    login: str,
    password: str,
    server: str,
    symbol: str = "XAUUSD",
) -> bool:
    """Write template + profile + config, then launch MT5."""

    # 1. Chart template
    tpl_dir = data_path / "MQL5" / "Profiles" / "Templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    tpl = tpl_dir / "clawbot_live.tpl"
    tpl.write_text(_chart_template(symbol))
    print(f"  [OK] Template: {tpl}")

    # 2. Profile
    prof = data_path / "MQL5" / "Profiles" / "Charts" / "CLAWBOT_Live"
    prof.mkdir(parents=True, exist_ok=True)
    (prof / "chart01.chr").write_text(_chart_template(symbol))
    print(f"  [OK] Profile:  {prof}")

    # 3. Startup INI
    cfg_dir = data_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "clawbot_live.ini"
    cfg.write_text(_startup_ini(login, password, server))
    print(f"  [OK] Config:   {cfg}")

    # 4. Launch
    print("  Starting MT5 ...")
    try:
        proc = subprocess.Popen(
            [str(terminal), f"/config:{cfg}"],
            cwd=str(terminal.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"  [OK] MT5 launched (PID {proc.pid})")
        time.sleep(5)
        return True
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False
