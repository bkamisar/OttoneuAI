import unittest

import probe_minors_tracking as P


def pitch(code, ev=None):
    return {"isPitch": True, "details": {"code": code}, "hitData": {"launchSpeed": ev} if ev else {}}


class TestProbe(unittest.TestCase):
    def test_spread_picks_evenly_through_the_season(self):
        self.assertEqual(P.spread(list(range(10)), 4), [1, 3, 6, 8])
        self.assertEqual(P.spread([1, 2], 4), [1, 2])

    def test_ev_share_counts_balls_in_play_only(self):
        game = {"liveData": {"plays": {"allPlays": [{"matchup": {}, "playEvents": [
            pitch("X", 95.0), pitch("D"), pitch("S"), pitch("E", 101.2), pitch("B")]}]}}}
        n, share = P.ev_share(game)
        self.assertEqual(n, 3)
        self.assertAlmostEqual(share, 2 / 3)
