"""T80b: daily charge timing — bounded wait for the detail, re-reads of None/stale levels."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_hero_level as hl  # noqa: E402
import test_daily_leveling as tdl  # noqa: E402  (module import: no re-collected tests)

detail = tdl.detail

SCAN = {'hl_scan_710': detail(80), 'hl_scan_840': detail(78)}   # lowest: 840 @ 78
PRE_SHOTS = ['hl_entry', 'hl_scan_710', 'hl_scan_hall_840', 'hl_scan_840', 'hl_daily_hall0']


class DetailWait(unittest.TestCase):
    run_level = tdl.DailyCharge.run_level

    def test_first_unknown_then_detail(self):
        dev, rc, _ = self.run_level({**SCAN, 'hl_daily_pre0_w2': detail(78),
                                     'hl_daily_post0': ['Lvl. 79']}, frames=['UNKNOWN'] * 9)
        self.assertEqual(rc, 0)
        self.assertEqual(dev.shots[5:], ['hl_daily_pre0', 'hl_daily_pre0_w1', 'hl_daily_pre0_w2',
                                         'hl_daily_post0'])
        self.assertIn('charged: hand 840 level 78 -> 79', dev.out.getvalue())

    def test_detail_at_once_costs_no_extra_shot(self):
        dev, rc, _ = self.run_level({**SCAN, 'hl_daily_pre0': detail(78),
                                     'hl_daily_post0': ['Lvl. 79']}, frames=['UNKNOWN'] * 7)
        self.assertEqual((rc, dev.shots[:5]), (0, PRE_SHOTS))
        self.assertEqual(dev.shots[5:], ['hl_daily_pre0', 'hl_daily_post0'])

    def test_stale_previous_level_is_reread(self):
        """Live 2026-11-04: the pre read showed the PREVIOUS hand's level -> false 'no effect'."""
        dev, rc, _ = self.run_level({**SCAN, 'hl_daily_pre0': detail(80),
                                     'hl_daily_pre0_rr1': detail(78),
                                     'hl_daily_post0': ['Lvl. 79']}, frames=['UNKNOWN'] * 8)
        self.assertEqual(rc, 0)
        self.assertIn('hl_daily_pre0_rr1', dev.shots)
        self.assertIn('level 78 -> 79', dev.out.getvalue())

    def test_unreadable_post_gets_two_rereads(self):
        dev, rc, _ = self.run_level({**SCAN, 'hl_daily_pre0': detail(78),
                                     'hl_daily_post0_rr2': ['Lvl. 79']}, frames=['UNKNOWN'] * 9)
        self.assertEqual(rc, 0)
        self.assertEqual(dev.shots[-3:], ['hl_daily_post0', 'hl_daily_post0_rr1', 'hl_daily_post0_rr2'])

    def test_rereads_are_bounded(self):
        dev, rc, _ = self.run_level({**SCAN, 'hl_daily_pre0': detail(78)}, frames=['UNKNOWN'] * 9)
        self.assertEqual(rc, 1)                      # post never readable: not 'charged'
        self.assertEqual(sum(s.startswith('hl_daily_post0') for s in dev.shots), 1 + hl.SLOT_REREADS)

    def test_poll_bound_is_about_eight_seconds(self):
        self.assertAlmostEqual(hl.DETAIL_POLLS * hl.DETAIL_POLL_WAIT, 8.0)
        self.assertEqual(hl.SLOT_REREADS, 2)


if __name__ == '__main__':
    unittest.main()
