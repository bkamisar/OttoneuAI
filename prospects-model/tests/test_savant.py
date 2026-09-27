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
        self.pages["custom"] = lambda url: custom_csv(2024, [(10, {"exit_velocity_avg": "91.2", "whiff_percent": ""})])
        self.pages["ev"] = lambda url: ev_csv([(10, 300, 115.1, 180.5)])
        got = savant.hitter_season(2024)
        self.assertAlmostEqual(got[10]["exit_velocity_avg"], 91.2)
        self.assertIsNone(got[10]["whiff_percent"])
        self.assertAlmostEqual(got[10]["max_hit_speed"], 115.1)
        self.assertAlmostEqual(got[10]["avg_distance"], 180.5)

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


if __name__ == "__main__":
    unittest.main()
