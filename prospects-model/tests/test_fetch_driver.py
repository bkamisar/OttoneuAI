import json, os, tempfile, unittest
import fetch_pbp
from psmodel import pbp


class TestPhaseCheckpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._dir = pbp.PBP_DIR
        pbp.PBP_DIR = self.tmp.name

    def tearDown(self):
        pbp.PBP_DIR = self._dir
        self.tmp.cleanup()

    def write_manifest(self, season, sport, **kw):
        p = fetch_pbp.manifest_path(season, sport)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        m = {"complete": True, "failed": 0, "leagues": None}
        m.update(kw)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(m, fh)

    def test_complete_phase_is_skipped(self):
        self.write_manifest(2023, 11)
        self.assertTrue(fetch_pbp.phase_done(2023, 11, None))

    def test_a_league_filtered_run_does_not_mark_the_whole_level_done(self):
        """Finishing '2022 AAA, PCL only' must not make a later full-AAA run
        skip 2022 -- the IL games were never fetched."""
        self.write_manifest(2022, 11, leagues=[112])
        self.assertTrue(fetch_pbp.phase_done(2022, 11, {112}))
        self.assertFalse(fetch_pbp.phase_done(2022, 11, None))
        self.assertFalse(fetch_pbp.phase_done(2022, 11, {112, 117}))

    def test_failures_mean_not_done(self):
        self.write_manifest(2023, 11, failed=3)
        self.assertFalse(fetch_pbp.phase_done(2023, 11, None))

    def test_the_current_season_is_never_marked_complete(self):
        """Games still finishing after tonight must be picked up by a rerun."""
        self.assertFalse(fetch_pbp.season_is_final(fetch_pbp.CURRENT_YEAR))
        self.assertTrue(fetch_pbp.season_is_final(fetch_pbp.CURRENT_YEAR - 1))


class TestSkipSeason(unittest.TestCase):
    def test_2020_skipped_only_in_the_minors(self):
        """MLB played a 60-game 2020 season; the minors didn't play."""
        self.assertTrue(fetch_pbp.skip_season(2020, 11))
        self.assertTrue(fetch_pbp.skip_season(2020, 14))
        self.assertFalse(fetch_pbp.skip_season(2020, 1))
        self.assertFalse(fetch_pbp.skip_season(2021, 11))


if __name__ == "__main__":
    unittest.main()
