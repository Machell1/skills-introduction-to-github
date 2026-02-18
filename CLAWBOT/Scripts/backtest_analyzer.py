#!/usr/bin/env python3
"""
CLAWBOT Backtest Analyzer
==========================
Analyzes MT5 Strategy Tester results and the CLAWBOT audit reports.
Determines if the bot meets the 80% win rate threshold.
Generates actionable reports for optimization.

Usage:
  python backtest_analyzer.py [--report-path PATH] [--threshold 80]
"""

import os
import sys
import csv
import argparse
from pathlib import Path
from datetime import datetime


class BacktestAnalyzer:
    """Analyzes CLAWBOT backtest results from CSV reports."""

    def __init__(self, report_path: str = None, threshold: float = 80.0):
        self.threshold = threshold
        self.report_path = self._find_report_path(report_path)
        self.stats = {}
        self.weaknesses = []
        self.strategies = {}
        self.sessions = {}
        self.days = {}
        self.hours = {}

    def _find_report_path(self, custom_path: str = None) -> Path:
        """Find the CLAWBOT report directory."""
        search_paths = []

        if custom_path:
            search_paths.append(Path(custom_path))

        # Standard locations
        script_dir = Path(__file__).parent.resolve()
        search_paths.extend([
            script_dir.parent / "Reports",
            script_dir.parent / "MQL5" / "Files" / "CLAWBOT_Reports",
        ])

        # MT5 data directories
        home = Path.home()
        mt5_base = home / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
        if mt5_base.exists():
            for terminal_dir in mt5_base.iterdir():
                if terminal_dir.is_dir():
                    files_dir = terminal_dir / "MQL5" / "Files" / "CLAWBOT_Reports"
                    search_paths.append(files_dir)

        for path in search_paths:
            if path.exists():
                return path

        return search_paths[0]  # Default to first option

    def load_report(self, filename: str = "CLAWBOT_Backtest_Report.csv") -> bool:
        """Load and parse the backtest report CSV."""
        filepath = self.report_path / filename
        if not filepath.exists():
            print(f"[ERROR] Report file not found: {filepath}")
            print(f"Searched in: {self.report_path}")
            return False

        print(f"[OK] Loading report: {filepath}")

        with open(filepath, 'r') as f:
            content = f.read()

        # Parse sections
        sections = content.split("\n\n")
        for section in sections:
            lines = section.strip().split("\n")
            if not lines:
                continue

            header = lines[0].strip()

            if "OVERALL PERFORMANCE" in header:
                self._parse_performance(lines[1:])
            elif "STRATEGY BREAKDOWN" in header:
                self._parse_strategies(lines[1:])
            elif "SESSION BREAKDOWN" in header:
                self._parse_sessions(lines[1:])
            elif "DAY OF WEEK" in header:
                self._parse_days(lines[1:])
            elif "HOURLY BREAKDOWN" in header:
                self._parse_hours(lines[1:])

        return True

    def _parse_performance(self, lines):
        """Parse overall performance metrics."""
        for line in lines:
            parts = line.strip().split(",")
            if len(parts) == 2:
                key = parts[0].strip()
                try:
                    value = float(parts[1].strip().replace("$", "").replace("%", ""))
                except ValueError:
                    value = parts[1].strip()
                self.stats[key] = value

    def _parse_strategies(self, lines):
        """Parse strategy breakdown."""
        for line in lines[1:]:  # Skip header
            parts = line.strip().split(",")
            if len(parts) >= 5:
                name = parts[0].strip()
                self.strategies[name] = {
                    "trades": int(float(parts[1])),
                    "wins": int(float(parts[2])),
                    "win_rate": float(parts[3]),
                    "profit": float(parts[4])
                }

    def _parse_sessions(self, lines):
        """Parse session breakdown."""
        for line in lines[1:]:
            parts = line.strip().split(",")
            if len(parts) >= 4:
                name = parts[0].strip()
                self.sessions[name] = {
                    "trades": int(float(parts[1])),
                    "wins": int(float(parts[2])),
                    "win_rate": float(parts[3])
                }

    def _parse_days(self, lines):
        """Parse day of week breakdown."""
        for line in lines[1:]:
            parts = line.strip().split(",")
            if len(parts) >= 4:
                name = parts[0].strip()
                self.days[name] = {
                    "trades": int(float(parts[1])),
                    "wins": int(float(parts[2])),
                    "win_rate": float(parts[3])
                }

    def _parse_hours(self, lines):
        """Parse hourly breakdown."""
        for line in lines[1:]:
            parts = line.strip().split(",")
            if len(parts) >= 4:
                hour = parts[0].strip()
                self.hours[hour] = {
                    "trades": int(float(parts[1])),
                    "wins": int(float(parts[2])),
                    "win_rate": float(parts[3])
                }

    def evaluate(self) -> bool:
        """Evaluate if backtest meets the threshold."""
        win_rate = self.stats.get("Win Rate (%)", 0)
        profit_factor = self.stats.get("Profit Factor", 0)
        max_dd = self.stats.get("Max Drawdown (%)", 100)
        expectancy = self.stats.get("Expectancy ($)", 0)
        total_trades = self.stats.get("Total Trades", 0)

        print("\n" + "=" * 60)
        print("  CLAWBOT BACKTEST EVALUATION")
        print("=" * 60)

        # Primary check
        wr_pass = win_rate >= self.threshold
        print(f"\n  Win Rate:       {win_rate:.1f}% {'PASS' if wr_pass else 'FAIL'} (target: >={self.threshold}%)")

        # Secondary checks
        pf_pass = profit_factor >= 1.5
        dd_pass = max_dd <= 15.0
        exp_pass = expectancy > 0
        trades_pass = total_trades >= 50

        print(f"  Profit Factor:  {profit_factor:.2f}   {'PASS' if pf_pass else 'FAIL'} (target: >=1.5)")
        print(f"  Max Drawdown:   {max_dd:.1f}%  {'PASS' if dd_pass else 'FAIL'} (target: <=15%)")
        print(f"  Expectancy:     ${expectancy:.2f}  {'PASS' if exp_pass else 'FAIL'} (target: >$0)")
        print(f"  Total Trades:   {total_trades:.0f}     {'PASS' if trades_pass else 'FAIL'} (target: >=50)")

        secondary_passed = sum([pf_pass, dd_pass, exp_pass, trades_pass])
        overall_pass = wr_pass and secondary_passed >= 2

        print(f"\n  Secondary criteria passed: {secondary_passed}/4 (need >=2)")
        print(f"\n  {'=' * 40}")
        print(f"  OVERALL RESULT: {'*** PASSED ***' if overall_pass else '*** FAILED ***'}")
        print(f"  {'=' * 40}")

        return overall_pass

    def identify_weaknesses(self) -> list:
        """Identify all weaknesses in the backtest results."""
        self.weaknesses = []

        win_rate = self.stats.get("Win Rate (%)", 0)
        pf = self.stats.get("Profit Factor", 0)
        dd = self.stats.get("Max Drawdown (%)", 0)
        expectancy = self.stats.get("Expectancy ($)", 0)
        trades = self.stats.get("Total Trades", 0)
        sharpe = self.stats.get("Sharpe Ratio", 0)
        consec_losses = self.stats.get("Max Consecutive Losses", 0)

        # Core metrics
        if win_rate < self.threshold:
            self.weaknesses.append({
                "priority": "CRITICAL",
                "category": "WIN_RATE",
                "description": f"Win rate {win_rate:.1f}% is below {self.threshold}% target",
                "recommendation": "Tighten entry filters, increase confluence requirements, or adjust indicator parameters"
            })

        if pf < 1.5:
            level = "CRITICAL" if pf < 1.0 else "HIGH"
            self.weaknesses.append({
                "priority": level,
                "category": "PROFIT_FACTOR",
                "description": f"Profit factor {pf:.2f} is {'negative' if pf < 1 else 'low'}",
                "recommendation": "Widen TP targets, tighten SL, or improve entry timing"
            })

        if dd > 15:
            level = "CRITICAL" if dd > 25 else "HIGH"
            self.weaknesses.append({
                "priority": level,
                "category": "DRAWDOWN",
                "description": f"Max drawdown {dd:.1f}% exceeds 15% target",
                "recommendation": "Reduce position size, lower risk per trade, or add drawdown circuit breaker"
            })

        if expectancy <= 0:
            self.weaknesses.append({
                "priority": "CRITICAL",
                "category": "EXPECTANCY",
                "description": f"Negative expectancy ${expectancy:.2f} per trade",
                "recommendation": "Strategy has no statistical edge. Fundamental review required."
            })

        if trades < 50:
            self.weaknesses.append({
                "priority": "HIGH",
                "category": "SAMPLE_SIZE",
                "description": f"Only {trades:.0f} trades. Insufficient for statistical confidence.",
                "recommendation": "Extend backtest period or loosen entry criteria for more trades"
            })

        if sharpe < 1.0:
            self.weaknesses.append({
                "priority": "MEDIUM",
                "category": "SHARPE_RATIO",
                "description": f"Sharpe ratio {sharpe:.2f} indicates poor risk-adjusted returns",
                "recommendation": "Reduce volatility of returns by improving consistency"
            })

        if consec_losses > 6:
            self.weaknesses.append({
                "priority": "HIGH",
                "category": "CONSECUTIVE_LOSSES",
                "description": f"{consec_losses:.0f} max consecutive losses",
                "recommendation": "Add cooldown period after consecutive losses or reduce position sizing"
            })

        # Strategy-level weaknesses
        for name, data in self.strategies.items():
            if data["trades"] >= 10:
                if data["win_rate"] < 40:
                    self.weaknesses.append({
                        "priority": "HIGH",
                        "category": f"STRATEGY_{name}",
                        "description": f"{name} strategy has only {data['win_rate']:.1f}% win rate",
                        "recommendation": f"Recalibrate or disable {name} strategy"
                    })
                if data["profit"] < 0:
                    self.weaknesses.append({
                        "priority": "HIGH",
                        "category": f"STRATEGY_{name}_LOSS",
                        "description": f"{name} strategy net loss: ${abs(data['profit']):.2f}",
                        "recommendation": f"The {name} strategy is dragging performance. Consider disabling."
                    })

        # Session weaknesses
        for name, data in self.sessions.items():
            if data["trades"] >= 5 and data["win_rate"] < 35:
                self.weaknesses.append({
                    "priority": "MEDIUM",
                    "category": f"SESSION_{name}",
                    "description": f"{name} session has {data['win_rate']:.1f}% win rate",
                    "recommendation": f"Consider avoiding trades during {name} session"
                })

        # Day weaknesses
        for name, data in self.days.items():
            if data["trades"] >= 5 and data["win_rate"] < 35:
                self.weaknesses.append({
                    "priority": "LOW",
                    "category": f"DAY_{name}",
                    "description": f"{name} has {data['win_rate']:.1f}% win rate",
                    "recommendation": f"Consider not trading on {name}"
                })

        return self.weaknesses

    def generate_weakness_report(self) -> str:
        """Generate a formatted weakness report for upload to Claude."""
        self.identify_weaknesses()

        report = []
        report.append("=" * 70)
        report.append("  CLAWBOT WEAKNESS ANALYSIS REPORT")
        report.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 70)

        report.append(f"\nBacktest did NOT meet the {self.threshold}% win rate threshold.\n")

        # Summary
        report.append("--- PERFORMANCE SUMMARY ---")
        for key, value in self.stats.items():
            if isinstance(value, float):
                report.append(f"  {key}: {value:.2f}")
            else:
                report.append(f"  {key}: {value}")

        # Weaknesses by priority
        report.append(f"\n--- IDENTIFIED WEAKNESSES ({len(self.weaknesses)}) ---\n")

        for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            priority_items = [w for w in self.weaknesses if w["priority"] == priority]
            if priority_items:
                report.append(f"[{priority}]")
                for w in priority_items:
                    report.append(f"  * {w['category']}: {w['description']}")
                    report.append(f"    -> {w['recommendation']}")
                report.append("")

        # Strategy breakdown
        report.append("--- STRATEGY PERFORMANCE ---")
        for name, data in self.strategies.items():
            report.append(f"  {name}: {data['trades']} trades, {data['win_rate']:.1f}% WR, ${data['profit']:.2f} net")

        # Recommendations
        report.append("\n--- RECOMMENDED ACTIONS ---")
        report.append("  1. Address CRITICAL weaknesses first")
        report.append("  2. Upload this report to Claude for optimization suggestions")
        report.append("  3. Adjust parameters in CLAWBOT EA inputs")
        report.append("  4. Re-run backtest to verify improvement")
        report.append("  5. Iterate until >=80% win rate is achieved")

        return "\n".join(report)

    def generate_pass_report(self) -> str:
        """Generate a pass report with deployment instructions."""
        report = []
        report.append("=" * 70)
        report.append("  CLAWBOT BACKTEST PASSED - READY FOR LIVE DEPLOYMENT")
        report.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 70)

        report.append(f"\nWin Rate: {self.stats.get('Win Rate (%)', 0):.1f}% >= {self.threshold}%\n")

        report.append("--- PERFORMANCE SUMMARY ---")
        for key, value in self.stats.items():
            if isinstance(value, float):
                report.append(f"  {key}: {value:.2f}")
            else:
                report.append(f"  {key}: {value}")

        report.append("\n--- DEPLOYMENT INSTRUCTIONS ---")
        report.append("  1. Run credential_manager.py to enter your Deriv MT5 credentials")
        report.append("  2. Open your Deriv MT5 terminal")
        report.append("  3. Load CLAWBOT EA on XAUUSD H1 chart")
        report.append("  4. Change Bot Mode input to 'Live'")
        report.append("  5. Enable AutoTrading")
        report.append("  6. Start with MINIMUM lot sizes for first 2 weeks")
        report.append("  7. Monitor daily and compare with backtest metrics")

        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="CLAWBOT Backtest Analyzer")
    parser.add_argument("--report-path", type=str, help="Path to CLAWBOT report directory")
    parser.add_argument("--threshold", type=float, default=80.0, help="Win rate threshold (default: 80)")
    parser.add_argument("--output", type=str, help="Output file for analysis report")
    args = parser.parse_args()

    analyzer = BacktestAnalyzer(args.report_path, args.threshold)

    if not analyzer.load_report():
        print("\n[INFO] No backtest report found yet.")
        print("Run the CLAWBOT EA in MT5 Strategy Tester first to generate results.")
        sys.exit(1)

    passed = analyzer.evaluate()

    if passed:
        report = analyzer.generate_pass_report()
        print("\n" + report)

        output_file = args.output or str(analyzer.report_path / "CLAWBOT_Analysis_PASS.txt")
        with open(output_file, 'w') as f:
            f.write(report)
        print(f"\n[OK] Pass report saved to: {output_file}")
        print("\n*** Next step: Run credential_manager.py to set up live trading ***")
    else:
        report = analyzer.generate_weakness_report()
        print("\n" + report)

        output_file = args.output or str(analyzer.report_path / "CLAWBOT_Analysis_WEAKNESSES.txt")
        with open(output_file, 'w') as f:
            f.write(report)
        print(f"\n[OK] Weakness report saved to: {output_file}")
        print("\n*** Upload this report to Claude for optimization assistance ***")


if __name__ == "__main__":
    main()
