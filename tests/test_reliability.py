import unittest, tempfile, json, datetime
from pathlib import Path
from unittest.mock import patch, Mock
from time_utils import parse_timestamp, last_completed_scan
from safe_state import atomic_json

class CommonTests(unittest.TestCase):
    def test_eastern_offsets(self):
        self.assertEqual(parse_timestamp("2026-01-15 10:00 ET").hour, 15)
        self.assertEqual(parse_timestamp("2026-07-15 10:00 ET").hour, 14)
        self.assertEqual(parse_timestamp("2026-07-15T10:00:00-04:00").hour, 14)
    def test_no_scan_from_failure_or_start(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"bot.log"
            p.write_text("[2026-07-15 10:00 ET] Starting scan\n[2026-07-15 10:01 ET] scan failed\n")
            self.assertIsNone(last_completed_scan(p))
            p.write_text("[2026-07-15 10:02 ET] Scan complete\n")
            self.assertEqual(parse_timestamp(last_completed_scan(p)).hour,14)
    def test_failed_json_write_preserves_state(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"state.json";atomic_json(p,{"valid":1})
            with self.assertRaises(ValueError):atomic_json(p,{"bad":float("nan")})
            self.assertEqual(json.loads(p.read_text()),{"valid":1})

import bankroll, config, kalshi_api, generate_data
class SafetyTests(unittest.TestCase):
    def test_zero_balance_triggers_stop(self):
        state={"live":{"peak":100,"balance":0},"live_stopped":False}
        with patch.object(bankroll,"load_bankroll",return_value=state),patch.object(bankroll,"save_bankroll"),patch.object(bankroll,"log"),patch.dict('sys.modules',{'auto_bettor':Mock()}):
            self.assertTrue(bankroll.check_drawdown_stop())
            self.assertTrue(state["live_stopped"])
    def test_corrupt_bankroll_does_not_reset(self):
        with tempfile.TemporaryDirectory() as d,patch.object(config,"DATA_DIR",Path(d)),patch.object(config,"BANKROLL_JSON",Path(d)/"bankroll.json"):
            config.BANKROLL_JSON.write_text("broken")
            with self.assertRaises(ValueError):bankroll.load_bankroll()
    def test_unavailable_cash_prevents_sync(self):
        api=Mock();api.get_account_balance.return_value=None;api.get_portfolio_total_value.return_value=50
        with patch.object(bankroll,"save_bankroll") as save,patch.object(bankroll,"log"):
            self.assertIsNone(bankroll.sync_live_balance(api));save.assert_not_called()
    def test_dry_run_blocks_http_post(self):
        api=kalshi_api.KalshiAPI()
        with patch.object(config,"DRY_RUN",True),patch.object(api._session,"post") as post:
            with self.assertRaises(RuntimeError):api._post("/portfolio/orders",{})
            post.assert_not_called()
    def test_missing_auth_blocks_http_post(self):
        api=kalshi_api.KalshiAPI()
        with patch.object(config,"DRY_RUN",False),patch.object(api,"_sign_request",return_value={}),patch.object(api._session,"post") as post:
            with self.assertRaises(RuntimeError):api._post("/portfolio/orders",{})
            post.assert_not_called()
