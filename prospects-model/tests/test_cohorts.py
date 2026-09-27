import unittest

from psmodel import cohorts


def milb_row(pid, season, sid, pa=200, age=22):
    return {"player_id": pid, "name": f"P{pid}", "season": season, "sport_id": sid, "age": age,
            "pa": pa, "ab": pa - 20, "h": 50, "hr": 5, "r": 20, "bb": 15, "so": 40, "sb": 3,
            "obp": 0.33, "slg": 0.40, "np": pa * 4, "swings": pa * 2, "whiffs": pa // 2}


class TestPriorPa(unittest.TestCase):
    def test_counts_only_earlier_seasons(self):
        hist = {1: {2010: 200, 2011: 150, 2013: 50}}
        self.assertEqual(cohorts.prior_mlb_pa(hist, 1, 2012), 350)
        self.assertEqual(cohorts.prior_mlb_pa(hist, 2, 2012), 0)


class TestBuildRows(unittest.TestCase):
    def setUp(self):
        milb = [milb_row(1, 2018, 12), milb_row(1, 2019, 12, pa=300),
                milb_row(2, 2019, 12, pa=50), milb_row(2, 2021, 12), milb_row(2, 2021, 11),
                milb_row(3, 2019, 11), milb_row(4, 2019, 13, pa=100)]
        hist = {3: {2017: 400}}
        mlb = {1: [{"season": 2020, "value": 1.0, "pa": 300, "ip": 0.0}]}
        rows = cohorts.build_rows(milb, hist, mlb)
        self.by = {(r["player_id"], r["season"], r["sport_id"]): r for r in rows}

    def test_volume_floor_and_established_cut(self):
        self.assertEqual(sorted(self.by), [(1, 2018, 12), (1, 2019, 12), (2, 2021, 11), (2, 2021, 12)])

    def test_repeat_level_bridges_2020(self):
        self.assertEqual(self.by[(1, 2019, 12)]["f"]["repeat_level"], 1.0)
        self.assertEqual(self.by[(1, 2018, 12)]["f"]["repeat_level"], 0.0)
        self.assertEqual(self.by[(2, 2021, 12)]["f"]["repeat_level"], 1.0)   # 2019 AA, even at 50 PA
        self.assertEqual(self.by[(2, 2021, 11)]["f"]["repeat_level"], 0.0)

    def test_multi_level_and_level_flags(self):
        f = self.by[(2, 2021, 11)]["f"]
        self.assertEqual((f["multi_level"], f["is_aaa"], f["is_aa"], f["is_higha"]), (1.0, 1.0, 0.0, 0.0))
        self.assertEqual(self.by[(1, 2018, 12)]["f"]["multi_level"], 0.0)

    def test_mlb_attached_and_groups_cover_every_feature(self):
        self.assertEqual(self.by[(1, 2018, 12)]["mlb"][0]["season"], 2020)
        keys = {k for g in cohorts.GROUPS.values() for k in g}
        self.assertEqual(keys, set(self.by[(1, 2018, 12)]["f"]))

    def test_raw_age_kept_beside_the_standardized_one(self):
        self.assertEqual(self.by[(1, 2018, 12)]["age_raw"], 22)

    def test_lead_products(self):
        rows = [{"f": {"age": 2.0, "slg": 1.5, "swstr": None}}]
        cohorts.add_products(rows)
        self.assertEqual(rows[0]["f"]["age_x_slg"], 3.0)
        self.assertIsNone(rows[0]["f"]["swstr_x_slg"])


if __name__ == "__main__":
    unittest.main()
