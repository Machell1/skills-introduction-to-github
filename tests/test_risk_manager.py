import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("MetaTrader5", SimpleNamespace())

from claw_claw.risk_manager import RiskManager
from claw_claw.state import Proposal, TradeState


class RiskManagerTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "resolved_symbol": "BTCUSD",
            "magic": 123,
            "cooldown_minutes": 10,
            "max_spread_points": 50.0,
            "max_daily_loss_pct": 2.0,
            "max_consecutive_losses": 3,
            "max_trades_per_day": 3,
            "one_trade_at_a_time": True,
            "min_sl_points": 10.0,
            "max_sl_points": 1000.0,
            "risk_per_trade_pct": 1.0,
            "max_volume": 2.0,
            "max_total_volume": 2.0,
            "pyramiding_enabled": True,
            "max_pyramid_entries": 1,
            "pyramid_confidence_min": 0.7,
            "pyramid_r_multiple_trigger": 1.0,
            "pyramid_volume_multiplier": 0.5,
        }
        self.state = TradeState()
        self.proposal = Proposal(
            bot_name="Test",
            symbol="BTCUSD",
            direction="buy",
            entry_type="market",
            suggested_sl=99.0,
            suggested_tp=110.0,
            confidence=0.7,
            rationale="Test",
        )

    @patch("claw_claw.risk_manager.mt5")
    def test_compute_volume(self, mock_mt5):
        info = MagicMock()
        info.point = 1.0
        info.trade_tick_value = 1.0
        info.trade_tick_size = 1.0
        info.volume_min = 0.01
        info.volume_max = 10.0
        info.volume_step = 0.01
        mock_mt5.symbol_info.return_value = info

        risk_manager = RiskManager(self.config)
        volume = risk_manager.compute_volume("BTCUSD", 1000.0, 99.0, 100.0)
        self.assertIsNotNone(volume)
        self.assertGreater(volume, 0)

    @patch("claw_claw.risk_manager.mt5")
    def test_spread_filter(self, mock_mt5):
        info = MagicMock()
        info.point = 0.01
        info.trade_tick_value = 1.0
        info.trade_tick_size = 0.01
        info.volume_min = 0.01
        info.volume_max = 10.0
        info.volume_step = 0.01
        mock_mt5.symbol_info.return_value = info
        tick = MagicMock()
        tick.ask = 100.0
        tick.bid = 99.0
        mock_mt5.symbol_info_tick.return_value = tick
        mock_mt5.positions_get.return_value = []

        risk_manager = RiskManager(self.config)
        decision = risk_manager.evaluate(self.proposal, self.state, equity=1000.0)
        self.assertFalse(decision.allowed)
        self.assertIn("Spread too high", ";".join(decision.reasons))

    @patch("claw_claw.risk_manager.mt5")
    def test_compute_volume_rejects_invalid_tick_size(self, mock_mt5):
        info = MagicMock()
        info.point = 0.01
        info.trade_tick_value = 1.0
        info.trade_tick_size = 0.0
        info.volume_min = 0.01
        info.volume_max = 10.0
        info.volume_step = 0.01
        mock_mt5.symbol_info.return_value = info

        risk_manager = RiskManager(self.config)
        volume = risk_manager.compute_volume("BTCUSD", 1000.0, 99.0, 100.0)
        self.assertIsNone(volume)

    @patch("claw_claw.risk_manager.mt5")
    def test_compute_volume_rounds_down_to_step(self, mock_mt5):
        info = MagicMock()
        info.point = 1.0
        info.trade_tick_value = 1.0
        info.trade_tick_size = 1.0
        info.volume_min = 0.1
        info.volume_max = 10.0
        info.volume_step = 0.1
        mock_mt5.symbol_info.return_value = info

        risk_manager = RiskManager(self.config)
        # Raw volume is 0.53 and should round down to the nearest 0.1 step.
        volume = risk_manager.compute_volume("BTCUSD", 53.0, 99.0, 100.0)
        self.assertEqual(volume, 0.5)

    @patch("claw_claw.risk_manager.mt5")
    def test_pyramid_rejects_when_trigger_not_reached(self, mock_mt5):
        info = MagicMock()
        info.point = 1.0
        info.trade_tick_value = 1.0
        info.trade_tick_size = 1.0
        info.volume_min = 0.1
        info.volume_max = 10.0
        info.volume_step = 0.1
        mock_mt5.symbol_info.return_value = info
        tick = MagicMock()
        tick.ask = 100.2
        tick.bid = 100.1
        mock_mt5.symbol_info_tick.return_value = tick
        base = MagicMock()
        base.type = 0
        base.price_open = 100.0
        base.sl = 99.0
        base.magic = 123
        mock_mt5.positions_get.return_value = [base]
        mock_mt5.POSITION_TYPE_BUY = 0

        risk_manager = RiskManager(self.config)
        decision = risk_manager.pyramid_allowed(self.proposal, self.state, equity=1000.0)
        self.assertFalse(decision.allowed)
        self.assertIn("Pyramid trigger not reached.", decision.reasons)


if __name__ == "__main__":
    unittest.main()
