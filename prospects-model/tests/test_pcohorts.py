import unittest

from psmodel import pcohorts


def milb_p(pid, season, sid, ip=60.0, g=20, gs=10, age=22):
    return {"player_id": pid, "name": f"P{pid}", "season": season, "sport_id": sid, "age": age,
            "g": g, "gs": gs, "ip": ip, "so": 60, "bb": 20, "hr": 5, "era": 3.5, "whip": 1.2,
            "hr9": 5 * 9.0 / ip, "np": int(ip * 16), "strikes": int(ip * 10), "bf": int(ip * 4.3),
            "swings": int(ip * 7), "whiffs": int(ip * 2)}


class TestPriorIp(unittest.TestCase):
    def test_counts_only_earlier_seasons(self):
        hist = {1: {2010: 60.0, 2011: 50.5, 2013: 20.0}}
        self.assertEqual(pcohorts.prior_mlb_ip(hist, 1, 2012), 110.5)
        self.assertEqual(pcohorts.prior_mlb_ip(hist, 2, 2012), 0)


class TestBuildRows(unittest.TestCase):
    def setUp(self):
        milb = [milb_p(1, 2019, 12, gs=20), milb_p(2, 2019, 12, gs=0),   # starter vs reliever, same level-season
                milb_p(3, 2019, 12, ip=25.0),                             # under 30 IP: dropped
                milb_p(4, 2019, 11), milb_p(1, 2021, 12)]
        hist = {4: {2017: 120.0}}                                         # 100+ prior MLB IP: dropped
        mlb = {1: [{"season": 2022, "value": 1.0, "pa": 0, "ip": 80.0}]}
        rows = pcohorts.build_rows(milb, hist, mlb)
        self.by = {(r["player_id"], r["season"], r["sport_id"]): r for r in rows}

    def test_volume_floor_and_established_cut(self):
        self.assertEqual(sorted(self.by), [(1, 2019, 12), (1, 2021, 12), (2, 2019, 12)])

    def test_role_features_rank_starter_above_reliever(self):
        self.assertGreater(self.by[(1, 2019, 12)]["f"]["gs_share"], self.by[(2, 2019, 12)]["f"]["gs_share"])

    def test_rows_are_pitchers_with_labels_flags_and_every_grouped_feature(self):
        r = self.by[(1, 2021, 12)]
        self.assertEqual((r["typ"], r["mlb"][0]["season"], r["age_raw"]), ("P", 2022, 22))
        self.assertEqual((r["f"]["repeat_level"], r["f"]["multi_level"], r["f"]["is_aa"]), (1.0, 0.0, 1.0))
        self.assertEqual({k for g in pcohorts.GROUPS.values() for k in g}, set(r["f"]))

    def test_rows_keep_the_raw_start_share(self):
        self.assertEqual((self.by[(1, 2019, 12)]["start_share"], self.by[(2, 2019, 12)]["start_share"]), (1.0, 0.0))


class TestLeads(unittest.TestCase):
    def test_leads_are_products_of_the_standardized_features(self):
        rows = [{"f": {"age": 1.5, "k": -2.0, "csw": 0.5}}, {"f": {"age": None, "k": 1.0, "csw": 1.0}}]
        pcohorts.add_products(rows)
        self.assertEqual((rows[0]["f"]["age_x_k"], rows[0]["f"]["age_x_csw"]), (-3.0, 0.75))
        self.assertIsNone(rows[1]["f"]["age_x_k"])


if __name__ == "__main__":
    unittest.main()
