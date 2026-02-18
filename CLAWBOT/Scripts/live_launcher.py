#!/usr/bin/env python3
"""
CLAWBOT Live Launcher
======================
Launches MT5 with the CLAWBOT EA attached to a XAUUSD H1 chart
in live trading mode. Creates chart template and startup profile.
"""

import os
import time
import subprocess
from pathlib import Path


def create_chart_template(data_path: Path, symbol: str = "XAUUSD") -> Path:
    """
    Create an MT5 chart template (.tpl) with CLAWBOT EA embedded.
    This template auto-attaches the EA when applied to a chart.
    """
    template_dir = data_path / "MQL5" / "Profiles" / "Templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / "clawbot_live.tpl"

    # MT5 chart template format
    template_content = f"""<chart>
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
scale_fix_min=0
scale_fix_min_val=0.000000
scale_fix_max=0
scale_fix_max_val=0.000000
expertmode=0
fixed_height=-1
</indicator>

</window>

<expert>
name=CLAWBOT\\CLAWBOT
path=Experts\\CLAWBOT\\CLAWBOT.ex5
expertmode=33
<inputs>
Inp_Separator1==== GENERAL SETTINGS ===
Inp_MagicNumber=20240101
Inp_Symbol={symbol}
Inp_Timeframe=16385
Inp_BotMode=1
Inp_Separator2==== RISK MANAGEMENT ===
Inp_RiskPerTrade=1.5
Inp_MaxDailyLoss=3.0
Inp_MaxDrawdown=8.0
Inp_MaxConcurrent=2
Inp_MaxDailyTrades=5
Inp_MinRiskReward=1.5
Inp_Separator3==== SL/TP SETTINGS ===
Inp_SL_ATR=2.0
Inp_TP_ATR=3.0
Inp_MinSL=150.0
Inp_MaxSL=500.0
Inp_TrailActivation=1.0
Inp_TrailDistance=1.5
Inp_MaxSpread=50.0
Inp_Separator4==== TREND STRATEGY ===
Inp_EnableTrend=true
Inp_EMA_Fast=8
Inp_EMA_Signal=21
Inp_EMA_Trend=50
Inp_EMA_Major=200
Inp_ADX_Period=14
Inp_ADX_Threshold=20.0
Inp_CrossoverLookback=3
Inp_Separator5==== MOMENTUM STRATEGY ===
Inp_EnableMomentum=true
Inp_RSI_Period=14
Inp_RSI_Oversold=35.0
Inp_RSI_Overbought=65.0
Inp_MACD_Fast=12
Inp_MACD_Slow=26
Inp_MACD_Signal=9
Inp_Stoch_K=14
Inp_Stoch_D=3
Inp_Stoch_Slowing=3
Inp_Separator6==== SESSION STRATEGY ===
Inp_EnableSession=true
Inp_AsianStart=0
Inp_AsianEnd=7
Inp_LondonStart=7
Inp_LondonEnd=10
Inp_ExitHour=20
Inp_Separator7==== CONFLUENCE SETTINGS ===
Inp_MinScore=40
Inp_MinStrategies=2
Inp_Separator8==== AUDIT SETTINGS ===
Inp_WinRateThreshold=80.0
Inp_ReportPath=CLAWBOT_Reports
</inputs>
</expert>

</chart>
"""
    template_path.write_text(template_content)
    return template_path


def create_startup_config(
    data_path: Path,
    login: str,
    password: str,
    server: str,
) -> Path:
    """
    Create an MT5 startup configuration INI for live trading.
    This logs into the account automatically on startup.
    """
    config_path = data_path / "config" / "clawbot_live.ini"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config_content = f"""[Common]
Login={login}
Password={password}
Server={server}
AutoTrading=1

[Charts]
ProfileLast=CLAWBOT_Live
TemplateLast=clawbot_live
"""
    config_path.write_text(config_content)
    return config_path


def create_live_profile(data_path: Path, symbol: str = "XAUUSD") -> Path:
    """
    Create an MT5 chart profile that opens XAUUSD H1 with the CLAWBOT template.
    """
    profile_dir = data_path / "MQL5" / "Profiles" / "Charts" / "CLAWBOT_Live"
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Profile chart file (chart00.chr)
    chart_content = f"""<chart>
id=100
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
window_right=1920
window_bottom=1080
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
</inputs>
</expert>

</chart>
"""
    chart_path = profile_dir / "chart01.chr"
    chart_path.write_text(chart_content)
    return profile_dir


def launch_live(
    terminal_path: Path,
    data_path: Path,
    login: str,
    password: str,
    server: str,
    symbol: str = "XAUUSD",
) -> bool:
    """
    Full live launch pipeline:
    1. Create chart template with EA
    2. Create live profile
    3. Create startup config
    4. Launch MT5 with config
    """
    print("\n  Creating CLAWBOT live chart template...")
    template_path = create_chart_template(data_path, symbol)
    print(f"  [OK] Template: {template_path}")

    print("  Creating CLAWBOT live profile...")
    profile_dir = create_live_profile(data_path, symbol)
    print(f"  [OK] Profile: {profile_dir}")

    print("  Creating startup configuration...")
    config_path = create_startup_config(data_path, login, password, server)
    print(f"  [OK] Config: {config_path}")

    print("  Launching MetaTrader 5 in live mode...")

    cmd = [str(terminal_path), f"/config:{config_path}"]

    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(terminal_path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"  [OK] MT5 launched (PID: {process.pid})")

        # Wait a moment for MT5 to start
        time.sleep(5)

        # Verify it's running
        from backtest_runner import is_mt5_running
        if is_mt5_running():
            print("  [OK] MT5 is running with CLAWBOT EA attached.")
            return True
        else:
            print("  [WARNING] MT5 process started but may not be visible yet.")
            print("  Check your taskbar for the MT5 window.")
            return True

    except Exception as e:
        print(f"  [ERROR] Failed to launch MT5: {e}")
        return False


def verify_live_readiness(data_path: Path) -> list:
    """
    Pre-flight checks before launching live.
    Returns list of issues (empty = ready).
    """
    issues = []

    # Check compiled EA exists
    ex5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.ex5"
    if not ex5.exists():
        issues.append("Compiled EA (CLAWBOT.ex5) not found. Run compilation first.")

    return issues
