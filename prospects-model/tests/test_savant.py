import unittest
from psmodel import http, savant


def custom_csv(year, rows):
    head = '"last_name, first_name",player_id,year,' + ",".join(savant.CUSTOM_FIELDS)
    lines = [head]
    for pid, vals in rows:
        lines.append(f'"X, Y",{pid},{year},' + ",".join(vals.get(f, "") for f in savant.CUSTOM_FIELDS))
    return "\n".join(lines) + "\n"


def ev_csv(rows):
    head = "last_name,first_name,player_id,attempts,max_hit_speed,avg_distance"
    return "\n".join([head] + [f"X,Y,{pid},{a},{m},{d}" for pid, a, m, d in rows]) + "\n"


class Base(unittest.TestCase):
    def setUp(self):
        self._orig = http.fetch_text
        self.pages = {}
        http.fetch_text = lambda url, suffix=".txt": self.pages["custom" if "custom" in url else "ev"](url)

    def tearDown(self):
        http.fetch_text = self._orig


class TestSeason(Base):
    def test_parses_and_merges(self):
        self.pages["custom"] = lambda url: custom_csv(2024, [(10, {"exit_velocity_avg": "91.2", "whiff_percent": "",
                                                                  "pull_percent": "40.5"})])
        self.pages["ev"] = lambda url: ev_csv([(10, 300, 115.1, 180.5)])
        got = savant.hitter_season(2024)
        self.assertAlmostEqual(got[10]["exit_velocity_avg"], 91.2)
        self.assertIsNone(got[10]["whiff_percent"])
        self.assertAlmostEqual(got[10]["max_hit_speed"], 115.1)
        self.assertAlmostEqual(got[10]["avg_distance"], 180.5)
        self.assertAlmostEqual(got[10]["pull_percent"], 40.5)
        self.assertEqual(got[10]["bbe"], 300.0)

    def test_custom_only_player_has_no_bbe(self):
        self.pages["custom"] = lambda url: custom_csv(2024, [(10, {}), (11, {})])
        self.pages["ev"] = lambda url: ev_csv([(10, 5, 100, 100)])
        self.assertIsNone(savant.hitter_season(2024)[11]["bbe"])

    def test_wrong_year_in_payload_is_an_error(self):
        """Savant has silently ignored parameters before; the payload must
        reflect the request."""
        self.pages["custom"] = lambda url: custom_csv(2023, [(10, {})])
        self.pages["ev"] = lambda url: ev_csv([(10, 1, 100, 100)])
        with self.assertRaises(http.DataError):
            savant.hitter_season(2024)


class TestHistory(Base):
    def test_identical_seasons_are_an_error(self):
        """The exit-velocity board has no year column, so an ignored year
        parameter would return the same file every season. Catch that."""
        self.pages["custom"] = lambda url: custom_csv(int(url.split("year=")[1][:4]), [(10, {})])
        self.pages["ev"] = lambda url: ev_csv([(10, 1, 100, 100)])
        with self.assertRaises(http.DataError):
            savant.hitter_history(2023, 2024)


def pitcher_csv(year, rows):
    head = '"last_name, first_name",player_id,year,' + ",".join(savant.PITCHER_FIELDS)
    lines = [head] + [f'"X, Y",{pid},{year},' + ",".join(vals.get(f, "") for f in savant.PITCHER_FIELDS)
                      for pid, vals in rows]
    return "\n".join(lines) + "\n"


class TestPitcherSeason(Base):
    def test_primary_fastball_and_magnitude(self):
        self.pages["custom"] = lambda url: pitcher_csv(2024, [
            (5, {"n_ff_formatted": "20.0", "n_si_formatted": "45.0", "si_avg_speed": "94.5", "si_avg_spin": "2150",
                 "si_avg_break_x": "-14.2", "si_avg_break_z_induced": "7.1", "ff_avg_speed": "96.0",
                 "breaking_avg_speed": "84.0", "breaking_avg_spin": "2450", "whiff_percent": "27.5",
                 "p_formatted_ip": "62.2", "pitch_count": "1010"}),
            (6, {"whiff_percent": "20.0"})])
        out = savant.pitcher_season(2024)
        self.assertEqual((out[5]["fb_speed"], out[5]["fb_hb"], out[5]["fb_ivb"], out[5]["pitches"]),
                         (94.5, 14.2, 7.1, 1010.0))
        self.assertAlmostEqual(out[5]["ip"], 62 + 2 / 3)
        self.assertIsNone(out[6]["fb_speed"])
        self.assertIsNone(out[6]["ip"])
        self.assertEqual(out[6]["whiff_percent"], 20.0)

    def test_year_guard(self):
        self.pages["custom"] = lambda url: pitcher_csv(2023, [(5, {"whiff_percent": "20.0"})])
        with self.assertRaises(http.DataError):
            savant.pitcher_season(2024)


if __name__ == "__main__":
    unittest.main()
