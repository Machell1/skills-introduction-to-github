#!/usr/bin/env python3
"""
CLAWBOT Backtest Analyzer
==========================
Parses EA audit CSV reports, evaluates against the 80 % win-rate gate,
and produces pass / weakness reports.
"""

import sys
from pathlib import Path
from datetime import datetime


class BacktestAnalyzer:
    def __init__(self, threshold: float = 55.0):
        self.threshold = threshold
        self.stats: dict = {}
        self.strategies: dict = {}
        self.sessions: dict = {}
        self.days: dict = {}
        self.hours: dict = {}
        self.weaknesses: list = []

    # ── loading ──────────────────────────────────────────────────────
    def load_report(self, filepath=None, report_dir=None) -> bool:
        """Load audit CSV.  Accepts a direct path *or* a directory to search."""
        path = None
        if filepath:
            path = Path(filepath) if not isinstance(filepath, Path) else filepath
        elif report_dir:
            path = Path(report_dir) / "CLAWBOT_Backtest_Report.csv"
        else:
            path = self._auto_find()

        if not path or not path.exists():
            print(f"  [ERROR] Report not found: {path}")
            return False

        print(f"  Loading: {path}")
        content = path.read_text()
        for section in content.split("\n\n"):
            lines = section.strip().splitlines()
            if not lines:
                continue
            hdr = lines[0].upper()
            if "OVERALL PERFORMANCE" in hdr:
                self._kv(lines[1:])
            elif "STRATEGY BREAKDOWN" in hdr:
                self._table(lines[1:], self.strategies)
            elif "SESSION BREAKDOWN" in hdr:
                self._table(lines[1:], self.sessions)
            elif "DAY OF WEEK" in hdr:
                self._table(lines[1:], self.days)
            elif "HOURLY BREAKDOWN" in hdr:
                self._table(lines[1:], self.hours)
        return True

    def _auto_find(self) -> Path:
        home = Path.home()
        appdata = home / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
        if appdata.exists():
            for d in sorted(appdata.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                f = d / "MQL5" / "Files" / "CLAWBOT_Reports" / "CLAWBOT_Backtest_Report.csv"
                if f.exists():
                    return f
        return None

    def _kv(self, lines):
        for line in lines:
            parts = line.strip().split(",", 1)
            if len(parts) == 2:
                try:
                    self.stats[parts[0].strip()] = float(
                        parts[1].strip().replace("$", "").replace("%", ""))
                except ValueError:
                    self.stats[parts[0].strip()] = parts[1].strip()

    def _table(self, lines, dest):
        for line in lines[1:]:  # skip header row
            p = line.strip().split(",")
            if len(p) >= 4:
                dest[p[0].strip()] = {
                    "trades": int(float(p[1])),
                    "wins": int(float(p[2])),
                    "win_rate": float(p[3]),
                    "profit": float(p[4]) if len(p) > 4 else 0,
                }

    # ── evaluation ───────────────────────────────────────────────────
    def evaluate(self) -> bool:
        wr = self.stats.get("Win Rate (%)", 0)
        pf = self.stats.get("Profit Factor", 0)
        dd = self.stats.get("Max Drawdown (%)", 100)
        exp = self.stats.get("Expectancy ($)", 0)
        trades = self.stats.get("Total Trades", 0)

        checks = {
            "Win Rate":      (wr >= self.threshold,   f"{wr:.1f}%", f">={self.threshold}%"),
            "Profit Factor": (pf >= 1.5,              f"{pf:.2f}",  ">=1.5"),
            "Max Drawdown":  (dd <= 15,               f"{dd:.1f}%", "<=15%"),
            "Expectancy":    (exp > 0,                f"${exp:.2f}", ">$0"),
            "Total Trades":  (trades >= 50,           f"{trades:.0f}", ">=50"),
        }

        print("\n" + "=" * 55)
        print("  BACKTEST EVALUATION")
        print("=" * 55)
        for name, (ok, val, target) in checks.items():
            tag = "PASS" if ok else "FAIL"
            print(f"  {name:18s} {val:>10s}  {tag}  (target {target})")

        secondary = sum(v[0] for k, v in checks.items() if k != "Win Rate")
        passed = checks["Win Rate"][0] and secondary >= 2
        print(f"\n  Secondary: {secondary}/4 (need >=2)")
        print(f"  Result:    {'*** PASSED ***' if passed else '*** FAILED ***'}")
        print("=" * 55)
        return passed

    # ── weakness analysis ────────────────────────────────────────────
    def identify_weaknesses(self):
        w = []
        wr  = self.stats.get("Win Rate (%)", 0)
        pf  = self.stats.get("Profit Factor", 0)
        dd  = self.stats.get("Max Drawdown (%)", 0)
        exp = self.stats.get("Expectancy ($)", 0)
        n   = self.stats.get("Total Trades", 0)
        cl  = self.stats.get("Max Consecutive Losses", 0)

        if wr < self.threshold:
            w.append(("CRITICAL", "WIN_RATE", f"Win rate {wr:.1f}% below {self.threshold}%",
                       "Tighten entry filters or adjust indicators"))
        if pf < 1.5:
            w.append(("CRITICAL" if pf < 1 else "HIGH", "PROFIT_FACTOR",
                       f"PF {pf:.2f}", "Widen TP or tighten SL"))
        if dd > 15:
            w.append(("CRITICAL" if dd > 25 else "HIGH", "DRAWDOWN",
                       f"DD {dd:.1f}%", "Reduce risk per trade"))
        if exp <= 0:
            w.append(("CRITICAL", "EXPECTANCY", f"${exp:.2f}", "No edge – review strategy"))
        if n < 50:
            w.append(("HIGH", "SAMPLE", f"{n:.0f} trades", "Extend test or loosen filters"))
        if cl > 6:
            w.append(("HIGH", "CONSEC_LOSS", f"{cl:.0f} in a row", "Add cooldown / reduce size"))

        for name, d in self.strategies.items():
            if d["trades"] >= 10 and d["win_rate"] < 40:
                w.append(("HIGH", f"STRAT_{name}", f"{d['win_rate']:.1f}% WR", f"Recalibrate {name}"))
        for name, d in self.sessions.items():
            if d["trades"] >= 5 and d["win_rate"] < 35:
                w.append(("MEDIUM", f"SESSION_{name}", f"{d['win_rate']:.1f}% WR", f"Avoid {name}"))
        for name, d in self.days.items():
            if d["trades"] >= 5 and d["win_rate"] < 35:
                w.append(("LOW", f"DAY_{name}", f"{d['win_rate']:.1f}% WR", f"Skip {name}"))

        self.weaknesses = w
        return w

    # ── report generators ────────────────────────────────────────────
    def generate_pass_report(self) -> str:
        lines = [
            "=" * 65,
            "  CLAWBOT BACKTEST PASSED – READY FOR LIVE",
            f"  {datetime.now():%Y-%m-%d %H:%M}",
            "=" * 65, "",
        ]
        for k, v in self.stats.items():
            lines.append(f"  {k}: {v:.2f}" if isinstance(v, float) else f"  {k}: {v}")
        lines += ["", "  Next: enter your Deriv credentials to launch live trading."]
        return "\n".join(lines)

    def generate_weakness_report(self) -> str:
        self.identify_weaknesses()
        lines = [
            "=" * 65,
            "  CLAWBOT WEAKNESS REPORT",
            f"  {datetime.now():%Y-%m-%d %H:%M}",
            "=" * 65, "",
        ]
        for k, v in self.stats.items():
            lines.append(f"  {k}: {v:.2f}" if isinstance(v, float) else f"  {k}: {v}")
        lines.append(f"\n  Issues found: {len(self.weaknesses)}\n")
        for prio in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            items = [w for w in self.weaknesses if w[0] == prio]
            if items:
                lines.append(f"  [{prio}]")
                for _, cat, desc, fix in items:
                    lines.append(f"    {cat}: {desc}")
                    lines.append(f"      -> {fix}")
                lines.append("")
        lines.append("  Upload this report to Claude for optimization suggestions.")
        return "\n".join(lines)
