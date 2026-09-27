import unittest
from psmodel import targets

CURRENT = 2026


def season(year, value, pa=500, ip=0.0):
    return {"season": year, "value": value, "pa": pa, "ip": ip}


class TestWindow(unittest.TestCase):
    def test_peak_is_max_within_four_seasons_of_debut(self):
        rows = [season(2019, 5.0), season(2020, 12.0), season(2021, 30.0),
                season(2022, 18.0), season(2023, 99.0)]   # year 5 must be ignored
        t = targets.build_target(rows, current_season=CURRENT)
        self.assertEqual(t["debut_season"], 2019)
        self.assertAlmostEqual(t["peak_value"], 30.0)
        self.assertEqual(t["peak_season"], 2021)

    def test_cameo_cannot_be_the_peak(self):
        rows = [season(2022, 40.0, pa=40), season(2023, 9.0, pa=500)]
        t = targets.build_target(rows, current_season=CURRENT)
        self.assertAlmostEqual(t["peak_value"], 9.0)
        self.assertEqual(t["peak_season"], 2023)

    def test_no_eligible_season_is_zero_not_none(self):
        t = targets.build_target([season(2024, 3.0, pa=30)], current_season=CURRENT)
        self.assertEqual(t["peak_value"], 0.0)

    def test_pitcher_volume_uses_innings(self):
        """A pitcher has no PA; eligibility must come from IP, not be zero."""
        rows = [season(2022, 20.0, pa=0, ip=150.0)]
        t = targets.build_target(rows, current_season=CURRENT)
        self.assertAlmostEqual(t["peak_value"], 20.0)


class TestCompleteness(unittest.TestCase):
    def test_complete_window_weighs_one(self):
        rows = [season(2019, 10.0)]
        self.assertAlmostEqual(targets.build_target(rows, CURRENT)["completeness"], 1.0)

    def test_partial_window_is_downweighted(self):
        rows = [season(2025, 10.0)]        # 2025,2026 observed of 2025-2028
        self.assertAlmostEqual(targets.build_target(rows, CURRENT)["completeness"], 0.5)

    def test_weight_floors_at_quarter(self):
        rows = [season(2026, 10.0)]
        self.assertAlmostEqual(targets.build_target(rows, CURRENT)["completeness"], 0.25)


class TestTimeToContribution(unittest.TestCase):
    def test_seasons_from_snapshot_to_first_eligible_season(self):
        rows = [season(2022, 2.0, pa=60), season(2023, 14.0, pa=520)]
        t = targets.build_target(rows, CURRENT, snapshot_season=2021)
        self.assertEqual(t["years_to_contribute"], 2)   # 2021 -> 2023

    def test_none_when_never_contributed(self):
        t = targets.build_target([season(2024, 1.0, pa=20)], CURRENT, snapshot_season=2023)
        self.assertIsNone(t["years_to_contribute"])


class TestNonArrival(unittest.TestCase):
    """'Hasn't yet' must never be confused with 'never will'."""

    def test_long_gone_prospect_is_a_labeled_zero(self):
        t = targets.build_target([], CURRENT, snapshot_season=2018)
        self.assertTrue(t["labeled"])
        self.assertEqual(t["peak_value"], 0.0)

    def test_recent_prospect_without_a_debut_is_unlabeled(self):
        t = targets.build_target([], CURRENT, snapshot_season=2024)
        self.assertFalse(t["labeled"])

    def test_the_boundary_is_exactly_five_seasons(self):
        self.assertFalse(targets.build_target([], CURRENT, snapshot_season=2022)["labeled"])  # 4 elapsed
        self.assertTrue(targets.build_target([], CURRENT, snapshot_season=2021)["labeled"])   # 5 elapsed


if __name__ == "__main__":
    unittest.main()
