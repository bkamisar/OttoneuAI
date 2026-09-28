import unittest

from psmodel import stuff_layer as SL

KEYS = ["age", "fb_speed"]


def stat(pid, age=24):
    return {"player_id": pid, "sport_id": 11, "age": age, "ip": 60.0, "so": 60, "bb": 20, "bf": 250,
            "hr9": 1.0, "era": 3.5, "whip": 1.2, "np": 960, "strikes": 600}


class Fixed:
    def predict(self, X):
        return [row[1] for row in X]           # score = translated fb_speed


class TestScores(unittest.TestCase):
    def test_aaa_scores_translate_and_need_volume_stats_and_the_season(self):
        table = {(1, 2022): {"pitches": 400, "fb_speed": 93.0}, (2, 2022): {"pitches": 200, "fb_speed": 99.0},
                 (3, 2023): {"pitches": 400, "fb_speed": 95.0}, (4, 2022): {"pitches": 400, "fb_speed": 90.0}}
        stats = {(1, 2022): stat(1), (2, 2022): stat(2), (3, 2023): stat(3)}      # 4 has no stat row
        got = SL.aaa_scores(table, stats, Fixed(), {"fb_speed": {"offset": 1.5}}, KEYS, {2022})
        self.assertEqual(got, {(1, 2022): 94.5})

    def test_offsets_and_mapping_rows_respect_the_vantage(self):
        aaa = {(1, 2022): {"pitches": 300, "fb_speed": 93.0}, (1, 2024): {"pitches": 300, "fb_speed": 80.0}}
        mlb = {(1, 2022): {"pitches": 300, "fb_speed": 94.0}, (1, 2024): {"pitches": 300, "fb_speed": 99.0}}
        self.assertAlmostEqual(SL.offsets(2023, aaa, mlb, ["fb_speed"])["fb_speed"]["offset"], 1.0)
        self.assertEqual(SL.mapping_table(mlb, 2023), {(1, 2022): mlb[(1, 2022)]})    # t <= v - 1


if __name__ == "__main__":
    unittest.main()
