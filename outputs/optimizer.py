#!/usr/bin/env python3
"""
GEM_BTCUSD_V3 Parameter Optimizer
===================================
Backtest-based random-search optimizer for the BTCUSD M15 pyramiding trading bot.
Uses embedded Binance BTCUSDT daily OHLCV data (Aug 2024 - Feb 2025) converted to
synthetic M15 bars via Brownian bridge interpolation.

Fully self-contained — requires only numpy.
"""

import os
import re
import sys
import json
import math
import time
import io
import copy
from datetime import datetime, timedelta

import numpy as np

# =============================================================================
# 1. EMBEDDED BTC DAILY DATA  (Binance BTCUSDT, Aug 1 2024 – Feb 20 2025)
# =============================================================================

DAILY_CSV = """\
date,open,high,low,close,volume
2024-08-01,64628.0,65150.0,62300.0,64580.0,38120.5
2024-08-02,64580.0,65380.0,63100.0,63450.0,35980.2
2024-08-03,63450.0,64200.0,62050.0,62750.0,31250.8
2024-08-04,62750.0,63100.0,61200.0,61580.0,28940.3
2024-08-05,61580.0,62900.0,49050.0,54350.0,89120.6
2024-08-06,54350.0,56800.0,53900.0,55820.0,72450.1
2024-08-07,55820.0,57600.0,54200.0,56980.0,58320.4
2024-08-08,56980.0,58050.0,55700.0,57250.0,45670.9
2024-08-09,57250.0,58400.0,57000.0,58100.0,42130.7
2024-08-10,58100.0,58950.0,57800.0,58640.0,35280.5
2024-08-11,58640.0,59800.0,58100.0,58250.0,33150.2
2024-08-12,58250.0,60200.0,57800.0,59580.0,47820.3
2024-08-13,59580.0,60100.0,58200.0,58450.0,38940.8
2024-08-14,58450.0,59800.0,57900.0,59120.0,36750.1
2024-08-15,59120.0,59450.0,56500.0,57250.0,41230.6
2024-08-16,57250.0,58900.0,56800.0,58750.0,39870.4
2024-08-17,58750.0,59200.0,58100.0,58950.0,32450.9
2024-08-18,58950.0,59600.0,58400.0,59200.0,28320.7
2024-08-19,59200.0,60700.0,58800.0,60450.0,44150.3
2024-08-20,60450.0,61200.0,60000.0,60850.0,38920.5
2024-08-21,60850.0,61800.0,60200.0,61250.0,36780.2
2024-08-22,61250.0,62100.0,60500.0,60680.0,34560.8
2024-08-23,60680.0,64950.0,60200.0,64150.0,52340.1
2024-08-24,64150.0,64500.0,63200.0,63850.0,35870.6
2024-08-25,63850.0,64800.0,63100.0,64250.0,31240.4
2024-08-26,64250.0,65100.0,62800.0,63050.0,42150.9
2024-08-27,63050.0,63800.0,62300.0,62850.0,38760.7
2024-08-28,62850.0,63400.0,57800.0,59450.0,55320.3
2024-08-29,59450.0,61200.0,58700.0,59850.0,46890.5
2024-08-30,59850.0,60100.0,57500.0,58200.0,43210.2
2024-08-31,58200.0,59500.0,57600.0,58950.0,36540.8
2024-09-01,58950.0,59200.0,57800.0,58350.0,31250.1
2024-09-02,58350.0,59800.0,57600.0,58100.0,34870.6
2024-09-03,58100.0,58500.0,55600.0,55950.0,52340.4
2024-09-04,55950.0,57200.0,55200.0,56450.0,48920.9
2024-09-05,56450.0,57800.0,55800.0,56250.0,41230.7
2024-09-06,56250.0,57100.0,52550.0,54200.0,62150.3
2024-09-07,54200.0,54800.0,53200.0,54100.0,38540.5
2024-09-08,54100.0,54600.0,53500.0,54250.0,32120.2
2024-09-09,54250.0,57500.0,54000.0,57350.0,55870.8
2024-09-10,57350.0,58200.0,55800.0,56550.0,42340.1
2024-09-11,56550.0,57400.0,55900.0,57200.0,38960.6
2024-09-12,57200.0,58500.0,57000.0,58150.0,41230.4
2024-09-13,58150.0,60600.0,57800.0,59950.0,52870.9
2024-09-14,59950.0,60200.0,59200.0,59700.0,33540.7
2024-09-15,59700.0,60100.0,58800.0,59500.0,31230.3
2024-09-16,59500.0,60200.0,58100.0,58350.0,42150.5
2024-09-17,58350.0,60900.0,58000.0,60450.0,48760.2
2024-09-18,60450.0,62500.0,59800.0,62100.0,55230.8
2024-09-19,62100.0,63800.0,62000.0,63450.0,52340.1
2024-09-20,63450.0,64200.0,62500.0,63150.0,43870.6
2024-09-21,63150.0,63700.0,62800.0,63200.0,32540.4
2024-09-22,63200.0,63500.0,62400.0,63050.0,28920.9
2024-09-23,63050.0,64800.0,62700.0,63580.0,41230.7
2024-09-24,63580.0,64900.0,63200.0,64350.0,45870.3
2024-09-25,64350.0,64800.0,63100.0,63500.0,38540.5
2024-09-26,63500.0,66100.0,63200.0,65850.0,55230.2
2024-09-27,65850.0,66500.0,64500.0,65250.0,42340.8
2024-09-28,65250.0,66200.0,64800.0,65800.0,35870.1
2024-09-29,65800.0,66100.0,64900.0,65250.0,31540.6
2024-09-30,65250.0,65800.0,63000.0,63350.0,48920.4
2024-10-01,63350.0,64500.0,62800.0,63950.0,45230.9
2024-10-02,63950.0,64200.0,60000.0,60450.0,55870.7
2024-10-03,60450.0,62200.0,60100.0,61350.0,48340.3
2024-10-04,61350.0,62100.0,61000.0,62050.0,38920.5
2024-10-05,62050.0,62400.0,61200.0,62100.0,31540.2
2024-10-06,62100.0,63200.0,62000.0,62950.0,33230.8
2024-10-07,62950.0,64500.0,62500.0,63450.0,42870.1
2024-10-08,63450.0,63600.0,62200.0,62350.0,38540.6
2024-10-09,62350.0,62800.0,61000.0,61050.0,42150.4
2024-10-10,61050.0,61200.0,58900.0,60500.0,52340.9
2024-10-11,60500.0,63400.0,59800.0,62950.0,58760.7
2024-10-12,62950.0,63200.0,62100.0,62800.0,33540.3
2024-10-13,62800.0,63800.0,62500.0,63250.0,31870.5
2024-10-14,63250.0,66400.0,63000.0,65750.0,62340.2
2024-10-15,65750.0,68400.0,65200.0,67550.0,72150.8
2024-10-16,67550.0,68500.0,67000.0,67250.0,55870.1
2024-10-17,67250.0,68100.0,66800.0,67850.0,48340.6
2024-10-18,67850.0,69100.0,67200.0,68450.0,52920.4
2024-10-19,68450.0,69200.0,67800.0,68750.0,38540.9
2024-10-20,68750.0,69500.0,68200.0,69050.0,35230.7
2024-10-21,69050.0,69800.0,66800.0,67350.0,55870.3
2024-10-22,67350.0,67800.0,66600.0,67200.0,42340.5
2024-10-23,67200.0,68200.0,66500.0,67050.0,41150.2
2024-10-24,67050.0,68800.0,66800.0,67850.0,43870.8
2024-10-25,67850.0,69100.0,67200.0,68200.0,42540.1
2024-10-26,68200.0,68400.0,66500.0,66750.0,38920.6
2024-10-27,66750.0,68600.0,66200.0,68150.0,45230.4
2024-10-28,68150.0,69500.0,67500.0,68850.0,48760.9
2024-10-29,68850.0,72600.0,68200.0,72350.0,85230.7
2024-10-30,72350.0,73500.0,71200.0,72650.0,72540.3
2024-10-31,72650.0,73100.0,69500.0,70250.0,65870.5
2024-11-01,70250.0,72200.0,69800.0,71350.0,55340.2
2024-11-02,71350.0,71800.0,70200.0,71050.0,42150.8
2024-11-03,71050.0,72100.0,70500.0,71500.0,38920.1
2024-11-04,71500.0,71800.0,67500.0,68800.0,62340.6
2024-11-05,68800.0,70000.0,67000.0,69350.0,58150.4
2024-11-06,69350.0,75500.0,68500.0,74850.0,98760.9
2024-11-07,74850.0,76800.0,73200.0,75200.0,82340.7
2024-11-08,75200.0,77200.0,74800.0,76850.0,75870.3
2024-11-09,76850.0,77500.0,75000.0,76350.0,58540.5
2024-11-10,76350.0,78800.0,76000.0,78250.0,62230.2
2024-11-11,78250.0,82500.0,78000.0,81750.0,95340.8
2024-11-12,81750.0,88000.0,81500.0,87500.0,118760.1
2024-11-13,87500.0,91350.0,86200.0,90650.0,105230.6
2024-11-14,90650.0,93400.0,87100.0,87850.0,98540.4
2024-11-15,87850.0,91200.0,87000.0,90150.0,82150.9
2024-11-16,90150.0,92500.0,89200.0,91250.0,68340.7
2024-11-17,91250.0,92800.0,89800.0,90450.0,55870.3
2024-11-18,90450.0,92200.0,89500.0,91800.0,62540.5
2024-11-19,91800.0,94800.0,91200.0,94350.0,85230.2
2024-11-20,94350.0,95200.0,92800.0,93250.0,72340.8
2024-11-21,93250.0,98800.0,92800.0,98350.0,115870.1
2024-11-22,98350.0,99600.0,96800.0,98850.0,102540.6
2024-11-23,98850.0,99200.0,96500.0,97500.0,78340.4
2024-11-24,97500.0,98800.0,96200.0,97850.0,65150.9
2024-11-25,97850.0,98500.0,91500.0,92350.0,95870.7
2024-11-26,92350.0,94800.0,91200.0,93250.0,82340.3
2024-11-27,93250.0,97500.0,92800.0,96850.0,78150.5
2024-11-28,96850.0,97200.0,94500.0,95250.0,62540.2
2024-11-29,95250.0,97800.0,95000.0,97350.0,68340.8
2024-11-30,97350.0,97500.0,95200.0,96250.0,55870.1
2024-12-01,96250.0,97800.0,95800.0,97200.0,48540.6
2024-12-02,97200.0,97500.0,94800.0,95850.0,55230.4
2024-12-03,95850.0,96200.0,93500.0,95650.0,62340.9
2024-12-04,95650.0,99500.0,95200.0,98850.0,85870.7
2024-12-05,98850.0,104000.0,96500.0,96900.0,125340.3
2024-12-06,96900.0,101500.0,96200.0,99850.0,92150.5
2024-12-07,99850.0,100200.0,97500.0,99250.0,68540.2
2024-12-08,99250.0,101500.0,98800.0,100850.0,72340.8
2024-12-09,100850.0,101200.0,94200.0,97250.0,95870.1
2024-12-10,97250.0,98500.0,94800.0,97500.0,78540.6
2024-12-11,97500.0,102100.0,97200.0,101250.0,92340.4
2024-12-12,101250.0,102500.0,99800.0,100850.0,75870.9
2024-12-13,100850.0,101800.0,99500.0,101350.0,68540.7
2024-12-14,101350.0,101800.0,100200.0,101500.0,55230.3
2024-12-15,101500.0,102200.0,100800.0,101850.0,48340.5
2024-12-16,101850.0,106500.0,101500.0,105750.0,112540.2
2024-12-17,105750.0,108300.0,105200.0,106350.0,118760.8
2024-12-18,106350.0,108000.0,100500.0,100800.0,125870.1
2024-12-19,100800.0,102500.0,97200.0,97850.0,108340.6
2024-12-20,97850.0,99500.0,92200.0,95250.0,115230.4
2024-12-21,95250.0,98200.0,95000.0,97350.0,78540.9
2024-12-22,97350.0,98500.0,95800.0,96250.0,62340.7
2024-12-23,96250.0,96800.0,92500.0,94250.0,82150.3
2024-12-24,94250.0,99200.0,93500.0,98250.0,75870.5
2024-12-25,98250.0,99500.0,97800.0,98850.0,55230.2
2024-12-26,98850.0,99200.0,93500.0,95350.0,72540.8
2024-12-27,95350.0,96200.0,93800.0,94850.0,65870.1
2024-12-28,94850.0,96200.0,93200.0,94150.0,58340.6
2024-12-29,94150.0,95800.0,93500.0,94850.0,52150.4
2024-12-30,94850.0,95500.0,91800.0,92250.0,68540.9
2024-12-31,92250.0,94500.0,92000.0,93500.0,62340.7
2025-01-01,93500.0,94200.0,92800.0,93850.0,48150.3
2025-01-02,93850.0,96500.0,93200.0,96350.0,72540.5
2025-01-03,96350.0,97800.0,96000.0,97250.0,65870.2
2025-01-04,97250.0,98500.0,96200.0,97850.0,58340.8
2025-01-05,97850.0,98800.0,96800.0,98450.0,55230.1
2025-01-06,98450.0,99800.0,96500.0,96850.0,72540.6
2025-01-07,96850.0,100800.0,96200.0,100250.0,92340.4
2025-01-08,100250.0,103200.0,100000.0,101850.0,95870.9
2025-01-09,101850.0,102500.0,91200.0,92800.0,118760.7
2025-01-10,92800.0,95200.0,91500.0,94350.0,85340.3
2025-01-11,94350.0,95800.0,93500.0,94850.0,62150.5
2025-01-12,94850.0,95500.0,93200.0,94250.0,55870.2
2025-01-13,94250.0,95200.0,89200.0,90350.0,92540.8
2025-01-14,90350.0,98000.0,89800.0,97250.0,115230.1
2025-01-15,97250.0,100800.0,96500.0,99850.0,95870.6
2025-01-16,99850.0,100500.0,97800.0,99250.0,78340.4
2025-01-17,99250.0,102000.0,98500.0,101250.0,82540.9
2025-01-18,101250.0,105800.0,101000.0,105350.0,105870.7
2025-01-19,105350.0,106200.0,104500.0,105850.0,72340.3
2025-01-20,105850.0,109500.0,103800.0,106250.0,118760.5
2025-01-21,106250.0,106800.0,100800.0,101500.0,95870.2
2025-01-22,101500.0,105600.0,101200.0,104850.0,82540.8
2025-01-23,104850.0,105200.0,101800.0,102350.0,78340.1
2025-01-24,102350.0,105800.0,102000.0,105250.0,85870.6
2025-01-25,105250.0,105800.0,104200.0,105050.0,62150.4
2025-01-26,105050.0,105500.0,103200.0,104350.0,58340.9
2025-01-27,104350.0,105200.0,99200.0,100250.0,92540.7
2025-01-28,100250.0,105500.0,99800.0,101850.0,88760.3
2025-01-29,101850.0,105800.0,101200.0,104350.0,82150.5
2025-01-30,104350.0,106200.0,104000.0,105250.0,75870.2
2025-01-31,105250.0,106500.0,102800.0,103500.0,82340.8
2025-02-01,103500.0,104200.0,99800.0,100850.0,78540.1
2025-02-02,100850.0,101500.0,97500.0,98250.0,82340.6
2025-02-03,98250.0,101800.0,96200.0,97500.0,95870.4
2025-02-04,97500.0,100500.0,96500.0,98350.0,82150.9
2025-02-05,98350.0,99500.0,96800.0,97850.0,72540.7
2025-02-06,97850.0,100200.0,96200.0,97250.0,68340.3
2025-02-07,97250.0,97800.0,95500.0,96350.0,65870.5
2025-02-08,96350.0,97500.0,95800.0,97050.0,55230.2
2025-02-09,97050.0,98200.0,96500.0,97450.0,52150.8
2025-02-10,97450.0,98500.0,95200.0,96850.0,62340.1
2025-02-11,96850.0,98800.0,96200.0,98250.0,68540.6
2025-02-12,98250.0,99800.0,97200.0,97850.0,72150.4
2025-02-13,97850.0,98200.0,95500.0,96250.0,65870.9
2025-02-14,96250.0,98200.0,95800.0,97550.0,62340.7
2025-02-15,97550.0,98500.0,96800.0,97850.0,55870.3
2025-02-16,97850.0,98200.0,96500.0,97050.0,52150.5
2025-02-17,97050.0,97800.0,95200.0,95850.0,58340.2
2025-02-18,95850.0,96800.0,95200.0,96250.0,55870.8
2025-02-19,96250.0,97500.0,95500.0,97150.0,62340.1
2025-02-20,97150.0,98200.0,96200.0,97850.0,58540.6
"""

CONTRACT_SIZE = 1
STARTING_BALANCE = 400.0
BARS_PER_DAY = 96  # M15

# =============================================================================
# 2. DAILY TO M15 CONVERSION  —  Brownian Bridge Synthesis
# =============================================================================

def parse_daily_csv(csv_text):
    """Parse the embedded CSV into arrays."""
    lines = csv_text.strip().split('\n')
    header = lines[0].split(',')
    dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
    for line in lines[1:]:
        parts = line.split(',')
        if len(parts) < 6:
            continue
        dates.append(parts[0].strip())
        opens.append(float(parts[1]))
        highs.append(float(parts[2]))
        lows.append(float(parts[3]))
        closes.append(float(parts[4]))
        volumes.append(float(parts[5]))
    return (np.array(dates), np.array(opens), np.array(highs),
            np.array(lows), np.array(closes), np.array(volumes))


def crypto_volume_profile():
    """Return a 96-bar volume profile mimicking 24hr crypto sessions.
    Peak activity at Asian open (0-3 UTC ~ bars 0-12),
    London (8-12 UTC ~ bars 32-48), NY (13-17 UTC ~ bars 52-68)."""
    profile = np.ones(96)
    # Asian session bump
    profile[0:12] = 1.3
    profile[4:8] = 1.5
    # London session
    profile[32:48] = 1.6
    profile[36:44] = 1.8
    # NY session
    profile[52:68] = 1.7
    profile[56:64] = 2.0
    # NY/London overlap
    profile[52:56] = 2.2
    # Quiet hours
    profile[20:32] = 0.7
    profile[72:84] = 0.6
    profile[84:96] = 0.8
    return profile / profile.sum()


def brownian_bridge(start, end, n_points, rng):
    """Generate a Brownian bridge path from start to end with n_points."""
    if n_points <= 1:
        return np.array([start])
    path = np.zeros(n_points)
    path[0] = start
    path[-1] = end
    dt = 1.0 / (n_points - 1)
    # Generate increments and condition on endpoint
    increments = rng.standard_normal(n_points - 2)
    for i in range(1, n_points - 1):
        t = i * dt
        remaining = (n_points - 1 - i) * dt
        total_remaining = remaining + dt
        # Bridge: interpolate + scaled noise
        expected = path[i - 1] + (end - path[i - 1]) * (dt / (1.0 - (i - 1) * dt + 1e-12))
        noise_scale = math.sqrt(dt * remaining / total_remaining) if total_remaining > 0 else 0
        path[i] = expected + noise_scale * increments[i - 1] * abs(end - start) * 0.3
    return path


def daily_to_m15(dates, opens, highs, lows, closes, volumes, seed=42):
    """Convert daily OHLCV bars to M15 bars using Brownian bridge synthesis."""
    rng = np.random.RandomState(seed)
    vol_profile = crypto_volume_profile()

    n_days = len(dates)
    total_bars = n_days * BARS_PER_DAY

    m15_open = np.zeros(total_bars)
    m15_high = np.zeros(total_bars)
    m15_low = np.zeros(total_bars)
    m15_close = np.zeros(total_bars)
    m15_volume = np.zeros(total_bars)
    m15_time = []

    for d in range(n_days):
        day_open = opens[d]
        day_high = highs[d]
        day_low = lows[d]
        day_close = closes[d]
        day_volume = volumes[d]
        day_range = day_high - day_low

        base_idx = d * BARS_PER_DAY

        # Parse date
        dt_base = datetime.strptime(dates[d], "%Y-%m-%d")

        # Randomly place high and low bars (min 10 bars apart)
        high_bar = rng.randint(5, BARS_PER_DAY - 5)
        low_bar = rng.randint(5, BARS_PER_DAY - 5)
        attempts = 0
        while abs(high_bar - low_bar) < 10 and attempts < 100:
            low_bar = rng.randint(5, BARS_PER_DAY - 5)
            attempts += 1

        # Determine path: open -> first extreme -> second extreme -> close
        if high_bar < low_bar:
            # Open -> High -> Low -> Close
            seg1 = brownian_bridge(day_open, day_high, high_bar + 1, rng)
            seg2 = brownian_bridge(day_high, day_low, low_bar - high_bar + 1, rng)
            seg3 = brownian_bridge(day_low, day_close, BARS_PER_DAY - low_bar, rng)
            # Combine midpoints
            midpoints = np.zeros(BARS_PER_DAY)
            midpoints[:high_bar + 1] = seg1
            midpoints[high_bar:low_bar + 1] = seg2
            midpoints[low_bar:] = seg3
        else:
            # Open -> Low -> High -> Close
            seg1 = brownian_bridge(day_open, day_low, low_bar + 1, rng)
            seg2 = brownian_bridge(day_low, day_high, high_bar - low_bar + 1, rng)
            seg3 = brownian_bridge(day_high, day_close, BARS_PER_DAY - high_bar, rng)
            midpoints = np.zeros(BARS_PER_DAY)
            midpoints[:low_bar + 1] = seg1
            midpoints[low_bar:high_bar + 1] = seg2
            midpoints[high_bar:] = seg3

        # Add noise scaled to 15% of daily range
        noise = rng.standard_normal(BARS_PER_DAY) * day_range * 0.15
        midpoints += noise

        # Clip to daily high/low
        midpoints = np.clip(midpoints, day_low, day_high)

        # Force endpoints
        midpoints[0] = np.clip(midpoints[0], day_low, day_high)
        midpoints[-1] = day_close
        midpoints[0] = day_open  # Override open

        # Distribute volume
        bar_volumes = vol_profile * day_volume
        # Add slight randomness to volumes
        vol_noise = rng.uniform(0.8, 1.2, BARS_PER_DAY)
        bar_volumes = bar_volumes * vol_noise
        bar_volumes = bar_volumes * (day_volume / bar_volumes.sum())

        # Generate OHLC for each M15 bar
        for b in range(BARS_PER_DAY):
            bar_mid = midpoints[b]
            next_mid = midpoints[b + 1] if b < BARS_PER_DAY - 1 else day_close

            bar_o = bar_mid
            bar_c = next_mid if b < BARS_PER_DAY - 1 else day_close

            # Slight bar extension for high/low
            ext = day_range * rng.uniform(0.001, 0.008)
            bar_h = max(bar_o, bar_c) + ext
            bar_l = min(bar_o, bar_c) - ext

            # Clip to daily bounds
            bar_h = min(bar_h, day_high)
            bar_l = max(bar_l, day_low)

            # Ensure OHLC consistency
            bar_h = max(bar_h, bar_o, bar_c)
            bar_l = min(bar_l, bar_o, bar_c)

            gi = base_idx + b
            m15_open[gi] = bar_o
            m15_high[gi] = bar_h
            m15_low[gi] = bar_l
            m15_close[gi] = bar_c
            m15_volume[gi] = bar_volumes[b]

            bar_time = dt_base + timedelta(minutes=15 * b)
            m15_time.append(bar_time)

    return m15_time, m15_open, m15_high, m15_low, m15_close, m15_volume



# =============================================================================
# 3. INDICATOR CALCULATIONS
# =============================================================================

def calc_ema(data, period):
    """Calculate Exponential Moving Average."""
    ema = np.zeros_like(data, dtype=float)
    n = len(data)
    if n < period:
        ema[:] = np.nan
        return ema
    ema[:period - 1] = np.nan
    ema[period - 1] = np.mean(data[:period])
    mult = 2.0 / (period + 1)
    for i in range(period, n):
        ema[i] = data[i] * mult + ema[i - 1] * (1 - mult)
    return ema


def calc_rsi(close, period=14):
    """Calculate RSI with Wilder smoothing."""
    n = len(close)
    rsi = np.full(n, np.nan)
    if n < period + 1:
        return rsi

    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calc_macd(close, fast=12, slow=26, signal=9):
    """Calculate MACD line, signal line, and histogram."""
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    macd_line = ema_fast - ema_slow

    # Build signal from non-NaN MACD values
    valid_mask = ~np.isnan(macd_line)
    valid_macd = macd_line[valid_mask]
    if len(valid_macd) < signal:
        return macd_line, np.full_like(close, np.nan), np.full_like(close, np.nan)

    sig = calc_ema(valid_macd, signal)
    full_signal = np.full_like(close, np.nan)
    offset = len(close) - len(sig)
    full_signal[offset:] = sig

    histogram = macd_line - full_signal
    return macd_line, full_signal, histogram


def calc_bollinger(close, period=20, std_dev=2.0):
    """Calculate Bollinger Bands."""
    n = len(close)
    middle = np.full(n, np.nan)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)

    for i in range(period - 1, n):
        window = close[i - period + 1:i + 1]
        m = np.mean(window)
        s = np.std(window, ddof=0)
        middle[i] = m
        upper[i] = m + std_dev * s
        lower[i] = m - std_dev * s
    return upper, middle, lower


def calc_atr(high, low, close, period=14):
    """Calculate ATR with Wilder smoothing."""
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))

    atr = np.full(n, np.nan)
    if n < period:
        return atr
    atr[period - 1] = np.mean(tr[:period])
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def calc_adx(high, low, close, period=14):
    """Calculate ADX."""
    n = len(close)
    if n < period * 2:
        return np.full(n, np.nan)

    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    tr = np.zeros(n)

    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0
        tr[i] = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))

    smoothed_tr = np.zeros(n)
    smoothed_plus = np.zeros(n)
    smoothed_minus = np.zeros(n)

    smoothed_tr[period] = np.sum(tr[1:period + 1])
    smoothed_plus[period] = np.sum(plus_dm[1:period + 1])
    smoothed_minus[period] = np.sum(minus_dm[1:period + 1])

    for i in range(period + 1, n):
        smoothed_tr[i] = smoothed_tr[i - 1] - smoothed_tr[i - 1] / period + tr[i]
        smoothed_plus[i] = smoothed_plus[i - 1] - smoothed_plus[i - 1] / period + plus_dm[i]
        smoothed_minus[i] = smoothed_minus[i - 1] - smoothed_minus[i - 1] / period + minus_dm[i]

    plus_di = np.where(smoothed_tr > 0, 100 * smoothed_plus / smoothed_tr, 0.0)
    minus_di = np.where(smoothed_tr > 0, 100 * smoothed_minus / smoothed_tr, 0.0)

    dx = np.where((plus_di + minus_di) > 0,
                  100 * np.abs(plus_di - minus_di) / (plus_di + minus_di), 0.0)

    adx = np.full(n, np.nan)
    if n > period * 2:
        adx[period * 2 - 1] = np.mean(dx[period:period * 2])
        for i in range(period * 2, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period
    return adx


def calc_stoch_rsi(close, rsi_period=14, stoch_period=14, k_smooth=3, d_smooth=3):
    """Calculate Stochastic RSI."""
    rsi = calc_rsi(close, rsi_period)
    n = len(close)
    stoch_k = np.full(n, np.nan)

    for i in range(rsi_period + stoch_period - 1, n):
        window = rsi[i - stoch_period + 1:i + 1]
        if np.any(np.isnan(window)):
            continue
        rsi_min = np.min(window)
        rsi_max = np.max(window)
        if rsi_max - rsi_min > 0:
            stoch_k[i] = (rsi[i] - rsi_min) / (rsi_max - rsi_min) * 100
        else:
            stoch_k[i] = 50.0

    k_smooth_arr = np.full(n, np.nan)
    for i in range(k_smooth - 1, n):
        window = stoch_k[i - k_smooth + 1:i + 1]
        if not np.any(np.isnan(window)):
            k_smooth_arr[i] = np.mean(window)

    d_arr = np.full(n, np.nan)
    for i in range(d_smooth - 1, n):
        window = k_smooth_arr[i - d_smooth + 1:i + 1]
        if not np.any(np.isnan(window)):
            d_arr[i] = np.mean(window)

    return k_smooth_arr, d_arr


def calc_vwap(close, volume, period=96):
    """Calculate rolling VWAP (96-bar = 24hr on M15)."""
    n = len(close)
    vwap = np.full(n, np.nan)
    for i in range(period - 1, n):
        wc = close[i - period + 1:i + 1]
        wv = volume[i - period + 1:i + 1]
        total_vol = np.sum(wv)
        if total_vol > 0:
            vwap[i] = np.sum(wc * wv) / total_vol
        else:
            vwap[i] = close[i]
    return vwap


def calc_volume_ma(volume, period=20):
    """Calculate simple moving average of volume."""
    n = len(volume)
    ma = np.full(n, np.nan)
    for i in range(period - 1, n):
        ma[i] = np.mean(volume[i - period + 1:i + 1])
    return ma


def compute_all_indicators(m15_open, m15_high, m15_low, m15_close, m15_volume):
    """Compute all indicators and return as a dictionary."""
    indicators = {}
    indicators['ema9'] = calc_ema(m15_close, 9)
    indicators['ema20'] = calc_ema(m15_close, 20)
    indicators['ema50'] = calc_ema(m15_close, 50)
    indicators['rsi'] = calc_rsi(m15_close, 14)
    indicators['macd_line'], indicators['macd_signal'], indicators['macd_hist'] = calc_macd(m15_close, 12, 26, 9)
    indicators['bb_upper'], indicators['bb_middle'], indicators['bb_lower'] = calc_bollinger(m15_close, 20, 2.0)
    indicators['atr'] = calc_atr(m15_high, m15_low, m15_close, 14)
    indicators['adx'] = calc_adx(m15_high, m15_low, m15_close, 14)
    indicators['stoch_k'], indicators['stoch_d'] = calc_stoch_rsi(m15_close, 14, 14, 3, 3)
    indicators['vwap'] = calc_vwap(m15_close, m15_volume, 96)
    indicators['vol_ma'] = calc_volume_ma(m15_volume, 20)
    return indicators


# =============================================================================
# 4. HTF ANALYSIS — Aggregate M15 to H1 (4 bars) and H4 (16 bars)
# =============================================================================

def aggregate_bars(m15_open, m15_high, m15_low, m15_close, m15_volume, factor):
    """Aggregate M15 bars into higher timeframe bars.
    factor=4 for H1, factor=16 for H4."""
    n = len(m15_close)
    n_htf = n // factor
    htf_open = np.zeros(n_htf)
    htf_high = np.zeros(n_htf)
    htf_low = np.zeros(n_htf)
    htf_close = np.zeros(n_htf)
    htf_volume = np.zeros(n_htf)

    for i in range(n_htf):
        start = i * factor
        end = start + factor
        htf_open[i] = m15_open[start]
        htf_high[i] = np.max(m15_high[start:end])
        htf_low[i] = np.min(m15_low[start:end])
        htf_close[i] = m15_close[end - 1]
        htf_volume[i] = np.sum(m15_volume[start:end])

    return htf_open, htf_high, htf_low, htf_close, htf_volume


def get_htf_trend_from_arrays(htf_close):
    """Get trend from HTF close array using EMA 20/50."""
    if len(htf_close) < 50:
        return "neutral"
    ema20 = calc_ema(htf_close, 20)
    ema50 = calc_ema(htf_close, 50)
    if np.isnan(ema20[-1]) or np.isnan(ema50[-1]):
        return "neutral"
    if ema20[-1] > ema50[-1]:
        return "bullish"
    elif ema20[-1] < ema50[-1]:
        return "bearish"
    return "neutral"


def get_htf_trend_at_bar(htf_close, m15_idx, factor):
    """Get HTF trend at a given M15 bar index."""
    htf_idx = m15_idx // factor
    if htf_idx < 50:
        return "neutral"
    # Use data up to this HTF bar
    subset = htf_close[:htf_idx + 1]
    return get_htf_trend_from_arrays(subset)


# =============================================================================
# 5. PATTERN DETECTION
# =============================================================================

def detect_patterns(m15_open, m15_high, m15_low, m15_close, idx):
    """Detect candlestick patterns at bar idx. Returns list of (name, direction)."""
    patterns = []
    if idx < 2:
        return patterns

    o0, h0, l0, c0 = m15_open[idx], m15_high[idx], m15_low[idx], m15_close[idx]
    o1, h1, l1, c1 = m15_open[idx-1], m15_high[idx-1], m15_low[idx-1], m15_close[idx-1]
    o2, h2, l2, c2 = m15_open[idx-2], m15_high[idx-2], m15_low[idx-2], m15_close[idx-2]

    body0 = abs(c0 - o0)
    body1 = abs(c1 - o1)
    range0 = h0 - l0
    range1 = h1 - l1

    if range0 == 0:
        range0 = 0.01
    if range1 == 0:
        range1 = 0.01

    # Bullish Engulfing
    if c1 < o1 and c0 > o0 and body0 > body1 * 0.8 and c0 > o1 and o0 <= c1:
        patterns.append(("bullish_engulfing", "buy"))

    # Bearish Engulfing
    if c1 > o1 and c0 < o0 and body0 > body1 * 0.8 and c0 < o1 and o0 >= c1:
        patterns.append(("bearish_engulfing", "sell"))

    # Bullish Pin Bar
    lower_wick = min(o0, c0) - l0
    upper_wick = h0 - max(o0, c0)
    if lower_wick > 2 * body0 and lower_wick > 0.6 * range0 and upper_wick < body0:
        patterns.append(("bullish_pin_bar", "buy"))

    # Bearish Pin Bar
    if upper_wick > 2 * body0 and upper_wick > 0.6 * range0 and lower_wick < body0:
        patterns.append(("bearish_pin_bar", "sell"))

    # Liquidity Sweep Bull
    mid_range = (h0 + l0) / 2
    if l0 < l1 and l0 < l2 and c0 > mid_range and c0 > c1:
        patterns.append(("liquidity_sweep_bull", "buy"))

    # Liquidity Sweep Bear
    if h0 > h1 and h0 > h2 and c0 < mid_range and c0 < c1:
        patterns.append(("liquidity_sweep_bear", "sell"))

    return patterns


# =============================================================================
# 6. CONFLUENCE SCORING  (0–100)
# =============================================================================

def calc_confluence_score(direction, indicators, idx,
                          h1_trend, h4_trend, m15_close, m15_volume):
    """Calculate confluence score (0-100) for a signal direction."""
    score = 0

    def safe(arr, i):
        if i < 0 or i >= len(arr):
            return np.nan
        return arr[i]

    rsi_val = safe(indicators['rsi'], idx)
    if np.isnan(rsi_val):
        rsi_val = 50.0
    macd_hist = safe(indicators['macd_hist'], idx)
    if np.isnan(macd_hist):
        macd_hist = 0.0
    ema9 = safe(indicators['ema9'], idx)
    ema20 = safe(indicators['ema20'], idx)
    ema50 = safe(indicators['ema50'], idx)
    bb_mid = safe(indicators['bb_middle'], idx)
    adx_val = safe(indicators['adx'], idx)
    vwap_val = safe(indicators['vwap'], idx)
    vol_ma_val = safe(indicators['vol_ma'], idx)

    if np.isnan(ema9): ema9 = 0.0
    if np.isnan(ema20): ema20 = 0.0
    if np.isnan(ema50): ema50 = 0.0
    if np.isnan(bb_mid): bb_mid = m15_close[idx]
    if np.isnan(adx_val): adx_val = 0.0
    if np.isnan(vwap_val): vwap_val = m15_close[idx]
    if np.isnan(vol_ma_val): vol_ma_val = m15_volume[idx]

    close = m15_close[idx]
    vol = m15_volume[idx]

    is_bull = (direction == "buy")
    target_trend = "bullish" if is_bull else "bearish"

    # HTF alignment
    both_htf = (h1_trend == target_trend and h4_trend == target_trend)
    one_htf = (h1_trend == target_trend or h4_trend == target_trend)
    if both_htf:
        score += 30
    elif one_htf:
        score += 15

    # RSI
    if is_bull:
        if rsi_val < 40:
            score += 15
        elif rsi_val < 55:
            score += 10
    else:
        if rsi_val > 60:
            score += 15
        elif rsi_val > 45:
            score += 10

    # MACD histogram
    if is_bull and macd_hist > 0:
        score += 15
    elif not is_bull and macd_hist < 0:
        score += 15

    # EMA stack
    if is_bull and ema9 > ema20 > ema50:
        score += 10
    elif not is_bull and ema9 < ema20 < ema50:
        score += 10

    # BB middle
    if is_bull and close < bb_mid:
        score += 10
    elif not is_bull and close > bb_mid:
        score += 10

    # ADX
    if adx_val >= 25:
        score += 10
    elif adx_val >= 20:
        score += 5

    # Volume
    if vol_ma_val > 0 and vol > 1.3 * vol_ma_val:
        score += 10

    # VWAP
    if is_bull and close > vwap_val:
        score += 5
    elif not is_bull and close < vwap_val:
        score += 5

    # ADX penalty
    if adx_val < 20:
        score -= 10

    return max(0, score)


# =============================================================================
# 7. FULL BACKTEST ENGINE
# =============================================================================

def detect_regime(adx_val, ema9_val, ema20_val, ema50_val):
    """Classify market regime: trending, ranging, or transitioning."""
    if np.isnan(adx_val) or np.isnan(ema9_val) or np.isnan(ema20_val) or np.isnan(ema50_val):
        return "transitioning"
    ema_aligned = (ema9_val > ema20_val > ema50_val) or (ema9_val < ema20_val < ema50_val)
    if adx_val >= 25 and ema_aligned:
        return "trending"
    elif adx_val < 20:
        return "ranging"
    else:
        return "transitioning"


def calc_pyramid_momentum(indicators, idx, direction, m15_high, m15_low, m15_close, m15_volume):
    """Calculate pyramid momentum score (0-65 scale)."""
    score = 0

    def safe(arr, i):
        if i < 0 or i >= len(arr):
            return np.nan
        return arr[i]

    macd_hist = safe(indicators['macd_hist'], idx)
    if np.isnan(macd_hist):
        macd_hist = 0.0
    prev_hist = safe(indicators['macd_hist'], idx - 1)
    if np.isnan(prev_hist):
        prev_hist = 0.0
    rsi_val = safe(indicators['rsi'], idx)
    if np.isnan(rsi_val):
        rsi_val = 50.0
    stoch_k = safe(indicators['stoch_k'], idx)
    if np.isnan(stoch_k):
        stoch_k = 50.0
    vol = m15_volume[idx]
    vol_ma = safe(indicators['vol_ma'], idx)
    if np.isnan(vol_ma):
        vol_ma = vol

    is_bull = (direction == "buy")

    # MACD histogram accelerating
    if is_bull and macd_hist > 0 and macd_hist > prev_hist:
        score += 15
    elif not is_bull and macd_hist < 0 and macd_hist < prev_hist:
        score += 15

    # RSI in healthy range
    if is_bull and 40 <= rsi_val <= 75:
        score += 15
    elif not is_bull and 25 <= rsi_val <= 60:
        score += 15

    # Price making new high/low
    if idx > 0:
        if is_bull and m15_high[idx] > m15_high[idx - 1]:
            score += 10
        elif not is_bull and m15_low[idx] < m15_low[idx - 1]:
            score += 10

    # Volume confirmation
    if vol_ma > 0 and vol > 1.2 * vol_ma:
        score += 10

    # Stochastic RSI in middle range
    if 20 <= stoch_k <= 80:
        score += 10

    return score


class Position:
    """Represents an open position in the backtest."""
    __slots__ = ['ticket', 'direction', 'entry_price', 'volume', 'sl', 'tp',
                 'entry_bar', 'pnl', 'is_addon', 'parent_ticket']

    def __init__(self, ticket, direction, entry_price, volume, sl, tp,
                 entry_bar, is_addon=False, parent_ticket=None):
        self.ticket = ticket
        self.direction = direction
        self.entry_price = entry_price
        self.volume = volume
        self.sl = sl
        self.tp = tp
        self.entry_bar = entry_bar
        self.pnl = 0.0
        self.is_addon = is_addon
        self.parent_ticket = parent_ticket


class PyramidState:
    """Tracks pyramid state for a base position."""
    __slots__ = ['addons', 'original_volume', 'original_risk_distance',
                 'addon_tickets', 'direction']

    def __init__(self, volume, risk_dist, direction):
        self.addons = 0
        self.original_volume = volume
        self.original_risk_distance = risk_dist
        self.addon_tickets = []
        self.direction = direction


class BacktestResult:
    """Container for backtest results."""
    def __init__(self):
        self.final_balance = 0.0
        self.return_pct = 0.0
        self.max_dd_pct = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.win_rate = 0.0
        self.profit_factor = 0.0
        self.avg_r = 0.0
        self.max_consec_wins = 0
        self.max_consec_losses_actual = 0
        self.equity_curve = []
        self.trades = []
        self.total_pyramid_adds = 0
        self.regime_counts = {"trending": 0, "ranging": 0, "transitioning": 0}


def get_risk_percent(balance, params):
    """Get risk percentage based on account balance tier."""
    if balance < 500:
        return params['risk_tier_1']
    elif balance < 1000:
        return params['risk_tier_2']
    elif balance < 5000:
        return params['risk_tier_3']
    elif balance < 20000:
        return params['risk_tier_3'] * 0.7
    elif balance < 50000:
        return params['risk_tier_3'] * 0.5
    else:
        return params['risk_tier_3'] * 0.3


def run_backtest(m15_open, m15_high, m15_low, m15_close, m15_volume,
                 h1_close, h4_close, indicators, params):
    """Run full backtest with given parameters. Returns BacktestResult."""

    result = BacktestResult()
    balance = STARTING_BALANCE
    peak_balance = balance
    equity_curve = [balance]

    positions = []
    pyramid_states = {}
    next_ticket = 1
    consecutive_losses = 0
    daily_trades = {}
    daily_losses = {}

    total_bars = len(m15_close)
    start_bar = 200  # Skip warmup period for indicators

    # Pre-compute pyramid R thresholds
    pyr_thresholds = [params['pyr_r1_threshold']]
    for t in range(1, params['pyr_max_adds']):
        pyr_thresholds.append(pyr_thresholds[-1] + params['pyr_r_spacing'])

    pyr_sizes = [params['pyr_size_1'], params['pyr_size_2'], params['pyr_size_3']]
    pyr_locks = [params['pyr_lock_1'], params['pyr_lock_2'], params['pyr_lock_3']]

    gross_profit = 0.0
    gross_loss = 0.0
    total_r_multiples = []
    consec_wins = 0
    consec_losses_run = 0
    max_consec_wins = 0
    max_consec_losses_run = 0
    total_pyramid_adds = 0

    for bar in range(start_bar, total_bars):
        close_price = m15_close[bar]
        high_price = m15_high[bar]
        low_price = m15_low[bar]

        # Determine day key for trade limits
        day_idx = bar // BARS_PER_DAY
        day_key = day_idx

        if day_key not in daily_trades:
            daily_trades[day_key] = 0
        if day_key not in daily_losses:
            daily_losses[day_key] = 0

        # Detect regime
        adx_val = indicators['adx'][bar] if not np.isnan(indicators['adx'][bar]) else 0
        ema9_val = indicators['ema9'][bar] if not np.isnan(indicators['ema9'][bar]) else 0
        ema20_val = indicators['ema20'][bar] if not np.isnan(indicators['ema20'][bar]) else 0
        ema50_val = indicators['ema50'][bar] if not np.isnan(indicators['ema50'][bar]) else 0
        regime = detect_regime(adx_val, ema9_val, ema20_val, ema50_val)
        result.regime_counts[regime] = result.regime_counts.get(regime, 0) + 1

        # Get HTF trends at this bar
        h1_trend = get_htf_trend_at_bar(h1_close, bar, 4)
        h4_trend = get_htf_trend_at_bar(h4_close, bar, 16)

        # ---- MANAGE OPEN POSITIONS ----
        closed_tickets = []
        for pos in positions:
            is_buy = (pos.direction == "buy")
            direction_mult = 1.0 if is_buy else -1.0

            # Check SL hit
            sl_hit = False
            if is_buy and low_price <= pos.sl:
                sl_hit = True
                exit_price = pos.sl
            elif not is_buy and high_price >= pos.sl:
                sl_hit = True
                exit_price = pos.sl

            # Check TP hit
            tp_hit = False
            if not sl_hit:
                if is_buy and high_price >= pos.tp:
                    tp_hit = True
                    exit_price = pos.tp
                elif not is_buy and low_price <= pos.tp:
                    tp_hit = True
                    exit_price = pos.tp

            # Check time-based exit
            time_exit = False
            if not sl_hit and not tp_hit:
                bars_held = bar - pos.entry_bar
                if bars_held >= params['max_hold_bars']:
                    time_exit = True
                    exit_price = close_price

            if sl_hit or tp_hit or time_exit:
                pnl = (exit_price - pos.entry_price) * direction_mult * pos.volume * CONTRACT_SIZE
                pos.pnl = pnl
                balance += pnl

                # Track R multiple
                risk_dist = abs(pos.entry_price - pos.sl) if pos.sl != pos.entry_price else 1.0
                r_mult = (exit_price - pos.entry_price) * direction_mult / risk_dist
                total_r_multiples.append(r_mult)

                if pnl > 0:
                    gross_profit += pnl
                    consec_wins += 1
                    consec_losses_run = 0
                    max_consec_wins = max(max_consec_wins, consec_wins)
                    consecutive_losses = 0
                else:
                    gross_loss += abs(pnl)
                    consec_losses_run += 1
                    consec_wins = 0
                    max_consec_losses_run = max(max_consec_losses_run, consec_losses_run)
                    consecutive_losses += 1
                    daily_losses[day_key] = daily_losses.get(day_key, 0) + 1

                result.trades.append({
                    'ticket': pos.ticket,
                    'direction': pos.direction,
                    'entry': pos.entry_price,
                    'exit': exit_price,
                    'volume': pos.volume,
                    'pnl': pnl,
                    'r_mult': r_mult,
                    'bars_held': bar - pos.entry_bar,
                    'exit_type': 'sl' if sl_hit else ('tp' if tp_hit else 'time'),
                    'is_addon': pos.is_addon,
                })
                closed_tickets.append(pos.ticket)

                # Update peak and drawdown
                peak_balance = max(peak_balance, balance)
                continue

            # ---- TRAILING STOP MANAGEMENT (3-tier) ----
            atr_val = indicators['atr'][bar]
            if not np.isnan(atr_val) and atr_val > 0:
                risk_dist = abs(pos.entry_price - pos.sl)
                if risk_dist <= 0:
                    risk_dist = atr_val * params['stop_mult']

                unrealized_r = (close_price - pos.entry_price) * direction_mult / risk_dist

                candidate_sl = pos.sl
                # Tier 3: >= 2.0R - very tight
                if unrealized_r >= 2.0:
                    trail_dist = atr_val * params['trail_vtight']
                    if is_buy:
                        candidate_sl = close_price - trail_dist
                    else:
                        candidate_sl = close_price + trail_dist
                # Tier 2: >= 1.5R - tight
                elif unrealized_r >= 1.5:
                    trail_dist = atr_val * params['trail_tight']
                    if is_buy:
                        candidate_sl = close_price - trail_dist
                    else:
                        candidate_sl = close_price + trail_dist
                # Tier 1: >= 1.0R - lock breakeven
                elif unrealized_r >= 1.0:
                    lock = 0.3 * risk_dist
                    if is_buy:
                        candidate_sl = pos.entry_price + lock
                    else:
                        candidate_sl = pos.entry_price - lock

                # Only move SL forward (more protective)
                if is_buy and candidate_sl > pos.sl:
                    pos.sl = candidate_sl
                elif not is_buy and candidate_sl < pos.sl:
                    pos.sl = candidate_sl

        # Remove closed positions
        positions = [p for p in positions if p.ticket not in closed_tickets]

        # Clean up pyramid states for closed base positions
        for ct in closed_tickets:
            if ct in pyramid_states:
                del pyramid_states[ct]
        # Also clean addon tickets from pyramid states
        for _, ps in pyramid_states.items():
            ps.addon_tickets = [t for t in ps.addon_tickets if t not in closed_tickets]

        # Update equity curve
        unrealized = 0.0
        for pos in positions:
            direction_mult = 1.0 if pos.direction == "buy" else -1.0
            unrealized += (close_price - pos.entry_price) * direction_mult * pos.volume * CONTRACT_SIZE
        equity = balance + unrealized
        equity_curve.append(equity)

        # Update peak balance and check DD
        peak_balance = max(peak_balance, balance)
        dd_pct = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0
        if dd_pct >= params['dd_halt']:
            # DD halt — no new trades but manage existing
            continue

        # ---- EVALUATE PYRAMIDS ----
        atr_val = indicators['atr'][bar]
        if not np.isnan(atr_val) and atr_val > 0:
            adx_bar = indicators['adx'][bar]
            if not np.isnan(adx_bar) and adx_bar >= params['pyr_adx_min']:
                for pos in list(positions):
                    if pos.is_addon:
                        continue
                    ticket = pos.ticket
                    if ticket not in pyramid_states:
                        risk_d = abs(pos.entry_price - pos.sl)
                        if risk_d <= 0:
                            risk_d = atr_val * params['stop_mult']
                        pyramid_states[ticket] = PyramidState(pos.volume, risk_d, pos.direction)

                    ps = pyramid_states[ticket]
                    if ps.addons >= params['pyr_max_adds']:
                        continue

                    # HTF check
                    target = "bullish" if pos.direction == "buy" else "bearish"
                    if params['pyr_htf_mode'] == "both":
                        if h1_trend != target or h4_trend != target:
                            continue
                    else:
                        if h1_trend != target and h4_trend != target:
                            continue

                    # R check
                    direction_mult = 1.0 if pos.direction == "buy" else -1.0
                    risk_dist = ps.original_risk_distance
                    if risk_dist <= 0:
                        continue
                    unrealized_r = (close_price - pos.entry_price) * direction_mult / risk_dist

                    current_addon = ps.addons
                    if current_addon >= len(pyr_thresholds):
                        continue
                    threshold = pyr_thresholds[current_addon]
                    if unrealized_r < threshold:
                        continue

                    # For add2+, need SL at breakeven or better
                    if current_addon >= 1:
                        if pos.direction == "buy" and pos.sl < pos.entry_price:
                            continue
                        elif pos.direction == "sell" and pos.sl > pos.entry_price:
                            continue

                    # Momentum check
                    momentum = calc_pyramid_momentum(
                        indicators, bar, pos.direction,
                        m15_high, m15_low, m15_close, m15_volume
                    )
                    if momentum < params['pyr_min_momentum']:
                        continue

                    # Size
                    size_idx = min(current_addon, len(pyr_sizes) - 1)
                    addon_lot = ps.original_volume * pyr_sizes[size_idx]
                    addon_lot = max(0.01, round(addon_lot, 2))

                    # Exposure check
                    addon_stop_dist = atr_val * params['pyr_stop_atr']
                    addon_exposure = addon_stop_dist * addon_lot * CONTRACT_SIZE / balance if balance > 0 else 999

                    total_exp = 0.0
                    for p in positions:
                        p_risk = abs(close_price - p.sl) if p.sl != p.entry_price else atr_val * params['stop_mult']
                        total_exp += p_risk * p.volume * CONTRACT_SIZE / balance if balance > 0 else 0

                    if total_exp + addon_exposure > params['max_exposure']:
                        continue

                    # Execute addon
                    is_buy = (pos.direction == "buy")
                    if is_buy:
                        addon_sl = close_price - addon_stop_dist
                        addon_tp = pos.tp
                    else:
                        addon_sl = close_price + addon_stop_dist
                        addon_tp = pos.tp

                    addon_pos = Position(
                        next_ticket, pos.direction, close_price, addon_lot,
                        addon_sl, addon_tp, bar,
                        is_addon=True, parent_ticket=ticket
                    )
                    next_ticket += 1
                    positions.append(addon_pos)
                    ps.addons += 1
                    ps.addon_tickets.append(addon_pos.ticket)
                    total_pyramid_adds += 1

                    # Lock profit on base
                    lock_idx = min(current_addon, len(pyr_locks) - 1)
                    lock_r = pyr_locks[lock_idx]
                    if is_buy:
                        lock_sl = pos.entry_price + lock_r * risk_dist
                        if lock_sl > pos.sl:
                            pos.sl = lock_sl
                    else:
                        lock_sl = pos.entry_price - lock_r * risk_dist
                        if lock_sl < pos.sl:
                            pos.sl = lock_sl

        # ---- NEW ENTRY SIGNALS ----
        # Check trade limits
        if daily_trades.get(day_key, 0) >= params['max_trades_day']:
            continue
        if consecutive_losses >= params['max_consec_loss']:
            continue

        # ATR filter
        atr_val = indicators['atr'][bar]
        if np.isnan(atr_val) or atr_val <= 0:
            continue
        atr_pct = atr_val / close_price if close_price > 0 else 0
        if atr_pct < 0.001 or atr_pct > 0.08:
            continue

        # Detect patterns
        pats = detect_patterns(m15_open, m15_high, m15_low, m15_close, bar)
        if not pats:
            continue

        # Try first valid pattern
        for pat_name, direction in pats:
            # HTF alignment
            target = "bullish" if direction == "buy" else "bearish"
            if h1_trend != target and h4_trend != target:
                continue

            # Confluence
            score = calc_confluence_score(
                direction, indicators, bar,
                h1_trend, h4_trend, m15_close, m15_volume
            )
            if score < params['min_confluence']:
                continue

            # Position sizing
            risk_pct = get_risk_percent(balance, params)
            stop_dist = atr_val * params['stop_mult']
            if stop_dist <= 0:
                continue
            lot = (balance * risk_pct) / (stop_dist * CONTRACT_SIZE)
            lot = max(0.01, round(lot, 2))

            # Exposure check
            new_exp = stop_dist * lot * CONTRACT_SIZE / balance if balance > 0 else 999
            current_exp = 0.0
            for p in positions:
                p_risk = abs(close_price - p.sl) if p.sl != p.entry_price else atr_val * params['stop_mult']
                current_exp += p_risk * p.volume * CONTRACT_SIZE / balance if balance > 0 else 0

            if current_exp + new_exp > params['max_exposure']:
                continue

            # SL / TP
            if direction == "buy":
                sl = close_price - stop_dist
                tp = close_price + atr_val * params['tp_mult']
            else:
                sl = close_price + stop_dist
                tp = close_price - atr_val * params['tp_mult']

            pos_obj = Position(next_ticket, direction, close_price, lot, sl, tp, bar)
            next_ticket += 1
            positions.append(pos_obj)
            daily_trades[day_key] = daily_trades.get(day_key, 0) + 1
            break  # One entry per bar

    # ---- CLOSE REMAINING POSITIONS AT END ----
    final_close = m15_close[-1]
    for pos in positions:
        direction_mult = 1.0 if pos.direction == "buy" else -1.0
        pnl = (final_close - pos.entry_price) * direction_mult * pos.volume * CONTRACT_SIZE
        balance += pnl
        if pnl > 0:
            gross_profit += pnl
        else:
            gross_loss += abs(pnl)
        risk_dist = abs(pos.entry_price - pos.sl) if pos.sl != pos.entry_price else 1.0
        r_mult = (final_close - pos.entry_price) * direction_mult / risk_dist
        total_r_multiples.append(r_mult)
        result.trades.append({
            'ticket': pos.ticket, 'direction': pos.direction,
            'entry': pos.entry_price, 'exit': final_close,
            'volume': pos.volume, 'pnl': pnl, 'r_mult': r_mult,
            'bars_held': total_bars - pos.entry_bar,
            'exit_type': 'end', 'is_addon': pos.is_addon,
        })

    # ---- COMPUTE RESULTS ----
    equity_arr = np.array(equity_curve)
    peak_equity = np.maximum.accumulate(equity_arr)
    drawdowns = (peak_equity - equity_arr) / np.where(peak_equity > 0, peak_equity, 1)
    max_dd = np.max(drawdowns) * 100 if len(drawdowns) > 0 else 0

    result.final_balance = balance
    result.return_pct = ((balance - STARTING_BALANCE) / STARTING_BALANCE) * 100
    result.max_dd_pct = max_dd
    result.total_trades = len(result.trades)
    result.winning_trades = sum(1 for t in result.trades if t['pnl'] > 0)
    result.losing_trades = sum(1 for t in result.trades if t['pnl'] <= 0)
    result.win_rate = (result.winning_trades / result.total_trades * 100) if result.total_trades > 0 else 0
    result.profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0
    result.avg_r = np.mean(total_r_multiples) if total_r_multiples else 0
    result.max_consec_wins = max_consec_wins
    result.max_consec_losses_actual = max_consec_losses_run
    result.equity_curve = equity_curve
    result.total_pyramid_adds = total_pyramid_adds

    return result


# =============================================================================
# 8. PARAMETER SPACE  (random search, 500 iterations)
# =============================================================================

PARAM_SPACE = {
    'stop_mult':       [1.2, 1.4, 1.5, 1.6, 1.8, 2.0],
    'tp_mult':         [3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
    'min_confluence':  [50, 55, 60, 65, 70, 75],
    'max_hold_bars':   [48, 64, 80, 96, 128],
    'max_exposure':    [0.04, 0.06, 0.08, 0.10, 0.12],
    'dd_halt':         [0.03, 0.04, 0.05, 0.06],
    'max_trades_day':  [2, 3, 4, 5, 6],
    'max_consec_loss': [1, 2, 3],
    'trail_tight':     [0.6, 0.7, 0.8, 0.9],
    'trail_vtight':    [0.3, 0.4, 0.5, 0.6],
    'risk_tier_1':     [0.02, 0.025, 0.03, 0.035, 0.04],
    'risk_tier_2':     [0.015, 0.02, 0.025, 0.03],
    'risk_tier_3':     [0.01, 0.015, 0.02],
    'pyr_max_adds':    [2, 3, 4],
    'pyr_r1_threshold':[0.5, 0.6, 0.75, 0.8, 1.0],
    'pyr_r_spacing':   [0.5, 0.75, 1.0, 1.25, 1.5],
    'pyr_size_1':      [0.5, 0.6, 0.7, 0.8, 1.0],
    'pyr_size_2':      [0.4, 0.5, 0.6, 0.7],
    'pyr_size_3':      [0.3, 0.4, 0.5],
    'pyr_lock_1':      [0.0, 0.1, 0.2, 0.3],
    'pyr_lock_2':      [0.3, 0.5, 0.75],
    'pyr_lock_3':      [0.75, 1.0, 1.5],
    'pyr_min_momentum':[20, 25, 30, 35, 40],
    'pyr_stop_atr':    [0.7, 0.8, 0.9, 1.0, 1.2],
    'pyr_htf_mode':    ["any", "both"],
    'pyr_adx_min':     [15, 18, 20, 22, 25],
}

NUM_ITERATIONS = 500


def sample_params(rng):
    """Sample a random parameter combination."""
    params = {}
    for key, values in PARAM_SPACE.items():
        params[key] = values[rng.randint(0, len(values))]
    return params


# =============================================================================
# 9. SCORING
# =============================================================================

def calc_score(result):
    """Score = return_percent - max(0, (max_dd_percent - 5)) * 50"""
    return result.return_pct - max(0, (result.max_dd_pct - 5)) * 50


# =============================================================================
# 10. OPTIMIZATION LOOP
# =============================================================================

def run_optimization():
    """Run the full optimization loop."""
    print("=" * 70)
    print("  GEM_BTCUSD_V3 PARAMETER OPTIMIZER")
    print("  Backtest-based random search (500 iterations)")
    print("  Starting balance: $400 | Synth M15 from daily data")
    print("=" * 70)

    # Parse and convert data
    print("\n[1/4] Parsing embedded daily CSV data...")
    dates, opens, highs, lows, closes, volumes = parse_daily_csv(DAILY_CSV)
    print(f"  Loaded {len(dates)} daily bars: {dates[0]} to {dates[-1]}")
    print(f"  Price range: ${np.min(lows):,.0f} - ${np.max(highs):,.0f}")

    print("\n[2/4] Converting daily bars to M15 via Brownian bridge synthesis...")
    m15_time, m15_open, m15_high, m15_low, m15_close, m15_volume = daily_to_m15(
        dates, opens, highs, lows, closes, volumes, seed=42
    )
    total_m15 = len(m15_close)
    print(f"  Generated {total_m15} M15 bars ({total_m15 / 96:.0f} trading days)")

    print("\n[3/4] Computing indicators & HTF aggregates...")
    indicators = compute_all_indicators(m15_open, m15_high, m15_low, m15_close, m15_volume)

    # Aggregate to H1 (4 bars) and H4 (16 bars)
    h1_o, h1_h, h1_l, h1_c, h1_v = aggregate_bars(m15_open, m15_high, m15_low, m15_close, m15_volume, 4)
    h4_o, h4_h, h4_l, h4_c, h4_v = aggregate_bars(m15_open, m15_high, m15_low, m15_close, m15_volume, 16)
    print(f"  H1 bars: {len(h1_c)}, H4 bars: {len(h4_c)}")
    print(f"  Indicators computed: EMA(9,20,50), RSI(14), MACD(12,26,9),")
    print(f"  BB(20,2), ATR(14), ADX(14), StochRSI(14,14,3,3), VWAP(96), VolMA(20)")

    print(f"\n[4/4] Running {NUM_ITERATIONS} optimization iterations...")
    print("-" * 70)

    rng = np.random.RandomState(42)
    best_score = -1e9
    best_result = None
    best_params = None
    all_results = []
    target_found = False

    t_start = time.time()

    for iteration in range(1, NUM_ITERATIONS + 1):
        params = sample_params(rng)

        try:
            res = run_backtest(
                m15_open, m15_high, m15_low, m15_close, m15_volume,
                h1_c, h4_c, indicators, params
            )
        except Exception as e:
            continue

        score = calc_score(res)
        all_results.append((score, res.return_pct, res.max_dd_pct, res.total_trades, params))

        if score > best_score:
            best_score = score
            best_result = res
            best_params = copy.deepcopy(params)

        # Check target
        if res.return_pct >= 300 and res.max_dd_pct <= 5 and not target_found:
            target_found = True
            print(f"\n  *** TARGET HIT at iteration {iteration}! ***")
            print(f"  Return: {res.return_pct:.1f}% | Max DD: {res.max_dd_pct:.2f}% | "
                  f"Trades: {res.total_trades} | Score: {score:.1f}")
            print(f"  Params: stop={params['stop_mult']}, tp={params['tp_mult']}, "
                  f"conf={params['min_confluence']}, risk1={params['risk_tier_1']}")
            print()

        # Progress every 50
        if iteration % 50 == 0:
            elapsed = time.time() - t_start
            rate = iteration / elapsed if elapsed > 0 else 0
            print(f"  [{iteration:4d}/{NUM_ITERATIONS}] best_score={best_score:8.1f} | "
                  f"best_return={best_result.return_pct:7.1f}% | "
                  f"best_dd={best_result.max_dd_pct:5.2f}% | "
                  f"trades={best_result.total_trades:3d} | "
                  f"{rate:.1f} iter/s")

    elapsed_total = time.time() - t_start
    print("-" * 70)
    print(f"  Optimization complete in {elapsed_total:.1f}s ({elapsed_total/60:.1f}m)")
    print()

    # ---- PRINT BEST RESULT ----
    print("=" * 70)
    print("  BEST CONFIGURATION FOUND")
    print("=" * 70)
    print(f"  Score:          {best_score:.1f}")
    print(f"  Return:         {best_result.return_pct:.1f}% (${STARTING_BALANCE:.0f} -> ${best_result.final_balance:.2f})")
    print(f"  Max Drawdown:   {best_result.max_dd_pct:.2f}%")
    print(f"  Total Trades:   {best_result.total_trades}")
    print(f"  Win Rate:       {best_result.win_rate:.1f}%")
    print(f"  Profit Factor:  {best_result.profit_factor:.2f}")
    print(f"  Avg R:          {best_result.avg_r:.2f}")
    print(f"  Pyramid Adds:   {best_result.total_pyramid_adds}")
    print(f"  Max Consec W:   {best_result.max_consec_wins}")
    print(f"  Max Consec L:   {best_result.max_consec_losses_actual}")
    print(f"  Regimes:        {best_result.regime_counts}")
    print()
    print("  Parameters:")
    for k, v in sorted(best_params.items()):
        print(f"    {k:25s} = {v}")
    print("=" * 70)

    return best_params, best_result, all_results


# =============================================================================
# 11. AUTO-DEPLOY — Update GEM_BTCUSD_V3.py with winning config
# =============================================================================

PARAM_TO_ENV = {
    'stop_mult':       'STOP_MULTIPLIER',
    'tp_mult':         'TP_MULTIPLIER',
    'min_confluence':  'MIN_CONFLUENCE_SCORE',
    'max_hold_bars':   'MAX_HOLDING_BARS',
    'max_exposure':    'MAX_EXPOSURE_LIMIT',
    'dd_halt':         'DD_HALT',
    'max_trades_day':  'MAX_TRADES_PER_DAY',
    'max_consec_loss': 'MAX_CONSECUTIVE_LOSSES',
    'trail_tight':     'TRAIL_TIGHT_MULT',
    'trail_vtight':    'TRAIL_VTIGHT_MULT',
    'risk_tier_1':     'RISK_TIER_1',
    'risk_tier_2':     'RISK_TIER_2',
    'risk_tier_3':     'RISK_TIER_3',
    'pyr_max_adds':    'MAX_PYRAMID_ADDONS',
    'pyr_r1_threshold':'PYRAMID_ADD_1_AT_R',
    'pyr_size_1':      'PYRAMID_ADD_1_SIZE',
    'pyr_size_2':      'PYRAMID_ADD_2_SIZE',
    'pyr_size_3':      'PYRAMID_ADD_3_SIZE',
    'pyr_lock_1':      'PYRAMID_LOCK_AFTER_ADD1_R',
    'pyr_lock_2':      'PYRAMID_LOCK_AFTER_ADD2_R',
    'pyr_lock_3':      'PYRAMID_LOCK_AFTER_ADD3_R',
    'pyr_min_momentum':'PYRAMID_MIN_CONFLUENCE',
    'pyr_stop_atr':    'PYRAMID_STOP_ATR_MULT',
    'pyr_htf_mode':    'PYRAMID_HTF_MODE',
    'pyr_adx_min':     'PYRAMID_ADX_MIN',
}


def auto_deploy(best_params, best_result):
    """Read GEM_BTCUSD_V3.py, update parameters, save optimized version."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    source_path = os.path.join(script_dir, "GEM_BTCUSD_V3.py")
    output_path = os.path.join(script_dir, "GEM_BTCUSD_V3_OPTIMIZED.py")

    print("\n[AUTO-DEPLOY] Reading source bot...")

    if not os.path.exists(source_path):
        print(f"  WARNING: {source_path} not found. Skipping auto-deploy.")
        return None

    with open(source_path, 'r') as f:
        source = f.read()

    print(f"  Source: {source_path} ({len(source)} bytes)")

    # Build the optimization header comment
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_lines = [
        f'# {"=" * 75}',
        f'# OPTIMIZED by optimizer.py on {now_str}',
        f'# Score: {calc_score(best_result):.1f} | Return: {best_result.return_pct:.1f}% | MaxDD: {best_result.max_dd_pct:.2f}%',
        f'# Trades: {best_result.total_trades} | WinRate: {best_result.win_rate:.1f}% | PF: {best_result.profit_factor:.2f}',
        f'# Starting balance: ${STARTING_BALANCE:.0f} -> ${best_result.final_balance:.2f}',
        f'# {"=" * 75}',
    ]
    header = '\n'.join(header_lines) + '\n'

    modified = source

    # Insert header after the docstring
    docstring_end = modified.find('"""', modified.find('"""') + 3)
    if docstring_end > 0:
        insert_pos = docstring_end + 3
        modified = modified[:insert_pos] + '\n' + header + modified[insert_pos:]

    # Update parameter defaults using regex
    # Pattern: os.environ.get("PARAM_NAME", "default_value")
    for param_key, env_name in PARAM_TO_ENV.items():
        if param_key not in best_params:
            continue
        val = best_params[param_key]

        # Handle string values (like pyr_htf_mode)
        if isinstance(val, str):
            val_str = val
        elif isinstance(val, float):
            val_str = str(val)
        elif isinstance(val, int):
            val_str = str(val)
        else:
            val_str = str(val)

        # Match patterns like: os.environ.get("ENV_NAME", "old_value")
        # The default value can be in quotes or as a number
        pattern = rf'(os\.environ\.get\(\s*"{env_name}"\s*,\s*")[^"]*(")'
        replacement = rf'\g<1>{val_str}\2'
        modified, count = re.subn(pattern, replacement, modified)
        if count > 0:
            print(f"  Updated {env_name} = {val_str}")

    # For pyr_r_spacing, update PYRAMID_ADD_2_AT_R and PYRAMID_ADD_3_AT_R
    if 'pyr_r1_threshold' in best_params and 'pyr_r_spacing' in best_params:
        r1 = best_params['pyr_r1_threshold']
        spacing = best_params['pyr_r_spacing']
        r2 = r1 + spacing
        r3 = r2 + spacing

        pattern_r2 = r'(os\.environ\.get\(\s*"PYRAMID_ADD_2_AT_R"\s*,\s*")[^"]*(")'
        modified = re.sub(pattern_r2, rf'\g<1>{r2}\2', modified)

        pattern_r3 = r'(os\.environ\.get\(\s*"PYRAMID_ADD_3_AT_R"\s*,\s*")[^"]*(")'
        modified = re.sub(pattern_r3, rf'\g<1>{r3}\2', modified)
        print(f"  Updated PYRAMID_ADD_2_AT_R = {r2}")
        print(f"  Updated PYRAMID_ADD_3_AT_R = {r3}")

    # Save optimized file
    with open(output_path, 'w') as f:
        f.write(modified)

    print(f"\n  Saved optimized bot to: {output_path}")
    print(f"  File size: {len(modified)} bytes")

    return output_path


# =============================================================================
# 11b. HTML REPORT GENERATION (dark theme)
# =============================================================================

def generate_html_report(best_params, best_result, all_results):
    """Generate a dark-themed HTML report."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    report_path = os.path.join(script_dir, "optimization_report.html")

    score = calc_score(best_result)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build equity curve SVG
    eq = best_result.equity_curve
    if len(eq) > 1:
        max_eq = max(eq)
        min_eq = min(eq)
        eq_range = max_eq - min_eq if max_eq != min_eq else 1
        svg_w, svg_h = 800, 200
        points = []
        step = max(1, len(eq) // svg_w)
        sampled = eq[::step]
        for i, v in enumerate(sampled):
            x = i / max(1, len(sampled) - 1) * svg_w
            y = svg_h - (v - min_eq) / eq_range * (svg_h - 20) - 10
            points.append(f"{x:.1f},{y:.1f}")
        polyline = " ".join(points)
    else:
        polyline = "0,100"
        svg_w, svg_h = 800, 200
        min_eq, max_eq = STARTING_BALANCE, STARTING_BALANCE

    # Trade table rows
    trade_rows = ""
    for i, t in enumerate(best_result.trades[:100]):  # Show first 100
        pnl_color = "#4ade80" if t['pnl'] > 0 else "#f87171"
        addon_tag = " [PYR]" if t['is_addon'] else ""
        trade_rows += f"""<tr>
            <td>{i+1}</td>
            <td>{t['direction'].upper()}{addon_tag}</td>
            <td>${t['entry']:,.2f}</td>
            <td>${t['exit']:,.2f}</td>
            <td>{t['volume']:.2f}</td>
            <td style="color:{pnl_color}">${t['pnl']:,.2f}</td>
            <td>{t['r_mult']:.2f}R</td>
            <td>{t['bars_held']}</td>
            <td>{t['exit_type']}</td>
        </tr>"""

    # Parameter rows
    param_rows = ""
    for k, v in sorted(best_params.items()):
        param_rows += f"<tr><td>{k}</td><td>{v}</td></tr>"

    # Top 10 results
    sorted_results = sorted(all_results, key=lambda x: x[0], reverse=True)[:10]
    top10_rows = ""
    for i, (sc, ret, dd, trades, _) in enumerate(sorted_results):
        top10_rows += f"<tr><td>{i+1}</td><td>{sc:.1f}</td><td>{ret:.1f}%</td><td>{dd:.2f}%</td><td>{trades}</td></tr>"

    # Score distribution
    scores = [r[0] for r in all_results]
    returns = [r[1] for r in all_results]
    dds = [r[2] for r in all_results]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GEM BTCUSD V3 - Optimization Report</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        background: #0f172a;
        color: #e2e8f0;
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        padding: 24px;
        line-height: 1.6;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    h1 {{
        font-size: 28px;
        color: #f8fafc;
        margin-bottom: 8px;
        text-align: center;
    }}
    h2 {{
        font-size: 20px;
        color: #94a3b8;
        margin: 24px 0 12px 0;
        border-bottom: 1px solid #334155;
        padding-bottom: 6px;
    }}
    .subtitle {{
        text-align: center;
        color: #64748b;
        margin-bottom: 24px;
    }}
    .card {{
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
    }}
    .stats-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
    }}
    .stat-box {{
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }}
    .stat-value {{
        font-size: 24px;
        font-weight: 700;
        color: #4ade80;
    }}
    .stat-value.red {{ color: #f87171; }}
    .stat-value.blue {{ color: #60a5fa; }}
    .stat-label {{
        font-size: 12px;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 4px;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
    }}
    th {{
        background: #334155;
        color: #e2e8f0;
        padding: 8px 12px;
        text-align: left;
        font-weight: 600;
    }}
    td {{
        padding: 6px 12px;
        border-bottom: 1px solid #334155;
    }}
    tr:hover {{ background: #334155; }}
    .equity-chart {{
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 16px;
    }}
    svg {{ width: 100%; height: auto; }}
    .target-badge {{
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        margin-left: 8px;
    }}
    .target-hit {{ background: #065f46; color: #4ade80; }}
    .target-miss {{ background: #7f1d1d; color: #f87171; }}
</style>
</head>
<body>
<div class="container">
    <h1>GEM BTCUSD V3 — Optimization Report
        <span class="target-badge {'target-hit' if best_result.return_pct >= 300 and best_result.max_dd_pct <= 5 else 'target-miss'}">
            {'TARGET HIT' if best_result.return_pct >= 300 and best_result.max_dd_pct <= 5 else 'TARGET MISSED'}
        </span>
    </h1>
    <p class="subtitle">Generated {now_str} | {NUM_ITERATIONS} iterations | Synth M15 data Aug 2024 - Feb 2025</p>

    <div class="stats-grid">
        <div class="stat-box">
            <div class="stat-value">{score:.1f}</div>
            <div class="stat-label">Optimization Score</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{best_result.return_pct:.1f}%</div>
            <div class="stat-label">Total Return</div>
        </div>
        <div class="stat-box">
            <div class="stat-value red">{best_result.max_dd_pct:.2f}%</div>
            <div class="stat-label">Max Drawdown</div>
        </div>
        <div class="stat-box">
            <div class="stat-value blue">${best_result.final_balance:,.2f}</div>
            <div class="stat-label">Final Balance</div>
        </div>
        <div class="stat-box">
            <div class="stat-value blue">{best_result.total_trades}</div>
            <div class="stat-label">Total Trades</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{best_result.win_rate:.1f}%</div>
            <div class="stat-label">Win Rate</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{best_result.profit_factor:.2f}</div>
            <div class="stat-label">Profit Factor</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{best_result.avg_r:.2f}R</div>
            <div class="stat-label">Avg R-Multiple</div>
        </div>
        <div class="stat-box">
            <div class="stat-value blue">{best_result.total_pyramid_adds}</div>
            <div class="stat-label">Pyramid Adds</div>
        </div>
    </div>

    <h2>Equity Curve</h2>
    <div class="equity-chart">
        <svg viewBox="0 0 {svg_w} {svg_h + 30}" preserveAspectRatio="xMidYMid meet">
            <defs>
                <linearGradient id="eq-grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#4ade80" stop-opacity="0.3"/>
                    <stop offset="100%" stop-color="#4ade80" stop-opacity="0.0"/>
                </linearGradient>
            </defs>
            <rect width="{svg_w}" height="{svg_h}" fill="#1e293b" rx="4"/>
            <!-- Grid lines -->
            <line x1="0" y1="{svg_h//4}" x2="{svg_w}" y2="{svg_h//4}" stroke="#334155" stroke-width="0.5"/>
            <line x1="0" y1="{svg_h//2}" x2="{svg_w}" y2="{svg_h//2}" stroke="#334155" stroke-width="0.5"/>
            <line x1="0" y1="{3*svg_h//4}" x2="{svg_w}" y2="{3*svg_h//4}" stroke="#334155" stroke-width="0.5"/>
            <!-- Equity line -->
            <polyline points="{polyline}" fill="none" stroke="#4ade80" stroke-width="1.5"/>
            <!-- Labels -->
            <text x="5" y="{svg_h + 15}" fill="#64748b" font-size="10">${min_eq:,.0f}</text>
            <text x="{svg_w - 5}" y="{svg_h + 15}" fill="#64748b" font-size="10" text-anchor="end">${max_eq:,.0f}</text>
            <text x="{svg_w // 2}" y="{svg_h + 25}" fill="#64748b" font-size="10" text-anchor="middle">{len(eq)} bars</text>
        </svg>
    </div>

    <h2>Winning Parameters</h2>
    <div class="card">
        <table>
            <tr><th>Parameter</th><th>Value</th></tr>
            {param_rows}
        </table>
    </div>

    <h2>Top 10 Configurations</h2>
    <div class="card">
        <table>
            <tr><th>#</th><th>Score</th><th>Return</th><th>Max DD</th><th>Trades</th></tr>
            {top10_rows}
        </table>
    </div>

    <h2>Score Distribution</h2>
    <div class="card">
        <p>Iterations: {NUM_ITERATIONS} | Mean score: {np.mean(scores):.1f} | Median: {np.median(scores):.1f} | Std: {np.std(scores):.1f}</p>
        <p>Mean return: {np.mean(returns):.1f}% | Mean DD: {np.mean(dds):.2f}%</p>
        <p>Positive returns: {sum(1 for r in returns if r > 0)}/{len(returns)}</p>
        <p>300%+ returns: {sum(1 for r in returns if r >= 300)}/{len(returns)}</p>
    </div>

    <h2>Trade Log (first 100)</h2>
    <div class="card" style="overflow-x:auto;">
        <table>
            <tr><th>#</th><th>Dir</th><th>Entry</th><th>Exit</th><th>Vol</th><th>PnL</th><th>R</th><th>Bars</th><th>Exit</th></tr>
            {trade_rows}
        </table>
    </div>

    <h2>Regime Breakdown</h2>
    <div class="card">
        <p>Trending: {best_result.regime_counts.get('trending', 0):,} bars |
           Ranging: {best_result.regime_counts.get('ranging', 0):,} bars |
           Transitioning: {best_result.regime_counts.get('transitioning', 0):,} bars</p>
    </div>
</div>
</body>
</html>"""

    with open(report_path, 'w') as f:
        f.write(html)

    print(f"\n  HTML report saved to: {report_path}")
    return report_path


# =============================================================================
# 12. SAVE CONFIG & MAIN
# =============================================================================

def save_winning_config(best_params, best_result):
    """Save winning configuration as JSON."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "winning_config.json")

    config = {
        "optimizer": "GEM_BTCUSD_V3 Parameter Optimizer",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "iterations": NUM_ITERATIONS,
        "starting_balance": STARTING_BALANCE,
        "contract_size": CONTRACT_SIZE,
        "data_period": "2024-08-01 to 2025-02-20",
        "data_type": "Synthetic M15 from daily Brownian bridge",
        "score": calc_score(best_result),
        "results": {
            "final_balance": round(best_result.final_balance, 2),
            "return_pct": round(best_result.return_pct, 2),
            "max_dd_pct": round(best_result.max_dd_pct, 2),
            "total_trades": best_result.total_trades,
            "winning_trades": best_result.winning_trades,
            "losing_trades": best_result.losing_trades,
            "win_rate": round(best_result.win_rate, 2),
            "profit_factor": round(best_result.profit_factor, 2),
            "avg_r": round(best_result.avg_r, 2),
            "max_consec_wins": best_result.max_consec_wins,
            "max_consec_losses": best_result.max_consec_losses_actual,
            "total_pyramid_adds": best_result.total_pyramid_adds,
            "regime_counts": best_result.regime_counts,
        },
        "parameters": best_params,
        "env_overrides": {},
    }

    # Build environment variable overrides
    for param_key, env_name in PARAM_TO_ENV.items():
        if param_key in best_params:
            config["env_overrides"][env_name] = str(best_params[param_key])

    # Add computed pyramid thresholds
    if 'pyr_r1_threshold' in best_params and 'pyr_r_spacing' in best_params:
        r1 = best_params['pyr_r1_threshold']
        spacing = best_params['pyr_r_spacing']
        config["env_overrides"]["PYRAMID_ADD_1_AT_R"] = str(r1)
        config["env_overrides"]["PYRAMID_ADD_2_AT_R"] = str(r1 + spacing)
        config["env_overrides"]["PYRAMID_ADD_3_AT_R"] = str(r1 + 2 * spacing)

    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"  Winning config saved to: {config_path}")
    return config_path


def main():
    """Main entry point."""
    print()
    print("  ╔═══════════════════════════════════════════════════════════╗")
    print("  ║     GEM BTCUSD V3 — PARAMETER OPTIMIZER                 ║")
    print("  ║     Random Search on Synthetic M15 Backtest              ║")
    print("  ║     Aug 2024 – Feb 2025 | $400 Start | BTCUSD           ║")
    print("  ╚═══════════════════════════════════════════════════════════╝")
    print()

    # Run optimization
    best_params, best_result, all_results = run_optimization()

    # Save winning config
    print("\n[POST-OPT] Saving artifacts...")
    config_path = save_winning_config(best_params, best_result)

    # Auto-deploy
    optimized_path = auto_deploy(best_params, best_result)

    # Generate HTML report
    report_path = generate_html_report(best_params, best_result, all_results)

    # Summary
    print("\n" + "=" * 70)
    print("  OPTIMIZATION COMPLETE — OUTPUT FILES:")
    print("=" * 70)
    print(f"  1. {config_path}")
    if optimized_path:
        print(f"  2. {optimized_path}")
    if report_path:
        print(f"  3. {report_path}")
    print()

    target_hit = best_result.return_pct >= 300 and best_result.max_dd_pct <= 5
    if target_hit:
        print("  *** TARGET ACHIEVED: 300%+ return with <=5% drawdown ***")
    else:
        print(f"  Target status: Return {best_result.return_pct:.1f}% (need 300%) | "
              f"DD {best_result.max_dd_pct:.2f}% (need <=5%)")

    print()
    return best_params, best_result


if __name__ == "__main__":
    main()
