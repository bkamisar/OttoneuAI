import unittest
from psmodel import context


def hitters(n, base_hr=20):
    """n synthetic hitters, DESCENDING quality (player 1 is best)."""
    return [{"player_id": i, "pa": 600, "ab": 540, "hr": base_hr + (n - i) // 3,
             "r": 70 + (n - i) // 3, "obp": 0.400 - i * 0.0003,
             "slg": 0.560 - i * 0.0005} for i in range(1, n + 1)]


def pitchers(n):
    return [{"player_id": i, "ip": 180.0, "so": 220 - i // 2, "bb": 50, "hr": 18,
             "era": 3.0 + i * 0.008, "whip": 1.05 + i * 0.0015,
             "hr9": 0.9 + i * 0.0015} for i in range(1, n + 1)]


class TestDenominators(unittest.TestCase):
    """Denominators are the real league's cross-team spread from standings.csv,
    NOT a simulated league. Measured 2026-09-26 against the real spread: snaking
    starters across synthetic teams under-estimated it by roughly half (0.44-0.68x)
    and random assignment by 7-36%. A real league is more spread out than any
    mechanical draw (managers punt categories, build lopsided rosters, absorb
    injuries), so there is no version of 'simulate a league' worth trusting."""

    ROWS = [
        {"Team": "A", "Games": "81", "R": "400", "HR": "100", "OBP": "0.320", "SLG": "0.400",
         "K": "600", "HR/9": "1.00", "ERA": "3.80", "WHIP": "1.20"},
        {"Team": "B", "Games": "81", "R": "440", "HR": "140", "OBP": "0.340", "SLG": "0.440",
         "K": "700", "HR/9": "1.20", "ERA": "4.20", "WHIP": "1.30"},
    ]

    def test_counting_stats_scale_to_a_full_season(self):
        """Half a season observed: a stdev of 20 HR becomes 40 over 162 games."""
        d = context.denominators_from_standings(self.ROWS)
        self.assertAlmostEqual(d["HR"], 20 * 2, places=9)
        self.assertAlmostEqual(d["R"], 20 * 2, places=9)
        self.assertAlmostEqual(d["SO"], 50 * 2, places=9)

    def test_rate_stats_are_not_scaled(self):
        d = context.denominators_from_standings(self.ROWS)
        self.assertAlmostEqual(d["OBP"], 0.010, places=9)
        self.assertAlmostEqual(d["SLG"], 0.020, places=9)
        self.assertAlmostEqual(d["ERA"], 0.200, places=9)
        self.assertAlmostEqual(d["WHIP"], 0.050, places=9)
        self.assertAlmostEqual(d["HR9"], 0.100, places=9)

    def test_full_season_needs_no_scaling(self):
        rows = [dict(r, Games="162") for r in self.ROWS]
        d = context.denominators_from_standings(rows)
        self.assertAlmostEqual(d["HR"], 20.0, places=9)

    def test_explicit_games_overrides_the_file(self):
        """standings.csv Games is calendar-ESTIMATED and uniform across teams,
        so the caller may know better."""
        d = context.denominators_from_standings(self.ROWS, games=162)
        self.assertAlmostEqual(d["HR"], 20.0, places=9)

    def test_too_few_teams_raises(self):
        with self.assertRaises(ValueError):
            context.denominators_from_standings(self.ROWS[:1])

    def test_zero_spread_raises(self):
        """A denominator of 0 would divide every label by zero."""
        rows = [dict(self.ROWS[0]), dict(self.ROWS[0], Team="B")]
        with self.assertRaises(ValueError):
            context.denominators_from_standings(rows)

    def test_missing_column_raises_instead_of_defaulting(self):
        rows = [{k: v for k, v in r.items() if k != "HR"} for r in self.ROWS]
        with self.assertRaises(ValueError):
            context.denominators_from_standings(rows)


class TestReplacement(unittest.TestCase):
    def test_hitter_replacement_is_a_real_regular(self):
        """Must look like an actual player -- not the 2.2 PA the live tool
        produced from exhausted September projections."""
        repl = context.hitter_replacement(hitters(400))
        self.assertGreater(repl["pa"], 100)
        self.assertGreater(repl["obp"], 0.200)
        self.assertLess(repl["obp"], 0.400)

    def test_replacement_sits_past_everyone_rostered(self):
        """Mirrors computeFABaselines' future branch: skip ROSTERED_H, then take
        the next FA_COHORT_H. Skipping only the 144 starting slots would set
        replacement far too high."""
        pool = hitters(400)
        repl = context.hitter_replacement(pool)
        ranked = sorted(pool, key=lambda r: r["pa"] * (r["obp"] + r["slg"]), reverse=True)
        expected = ranked[context.ROSTERED_H:context.ROSTERED_H + context.FA_COHORT_H]
        self.assertAlmostEqual(repl["obp"],
                               sum(r["obp"] for r in expected) / len(expected), places=9)
        # and it is worse than the starters
        starters = ranked[:context.STARTING_HITTERS]
        self.assertLess(repl["obp"] + repl["slg"],
                        sum(r["obp"] + r["slg"] for r in starters) / len(starters))

    def test_volume_floor_excludes_tiny_samples(self):
        """FA_MIN_PA keeps a 12-PA hot streak out of the replacement cohort."""
        pool = hitters(400)
        pool.append({"player_id": 9999, "pa": 12, "ab": 10, "hr": 4, "r": 6,
                     "obp": 0.900, "slg": 1.800})
        repl = context.hitter_replacement(pool)
        self.assertLess(repl["obp"], 0.500)

    def test_pitcher_replacement_uses_rostered_count_and_floor(self):
        repl = context.pitcher_replacement(pitchers(300))
        self.assertGreaterEqual(repl["ip"], context.FA_MIN_IP)
        self.assertGreater(repl["era"], 0.0)

    def test_too_small_a_pool_raises(self):
        with self.assertRaises(ValueError):
            context.hitter_replacement(hitters(10))


class TestLeagueAverages(unittest.TestCase):
    def test_avg_pa_is_per_team_starters_not_league_wide(self):
        """144 starters at 600 PA is 86,400 league PA; per team that is 7,200.
        League-wide/12 over a 300-player pool would give 15,000 -- roughly
        double -- and would halve the weight of OBP and SLG."""
        avg_pa, avg_ip = context.league_averages(hitters(300), pitchers(250))
        self.assertAlmostEqual(avg_pa, 144 * 600 / 12, places=6)
        self.assertAlmostEqual(avg_ip, 1500.0, places=6)


if __name__ == "__main__":
    unittest.main()
