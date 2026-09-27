import gzip, json, os, tempfile, unittest
from psmodel import pbp, tracking


def pitch(code, zone, **hit):
    e = {"isPitch": True, "details": {"code": code}, "pitchData": {"zone": zone}}
    if hit:
        e["hitData"] = {"launchSpeed": hit["ev"], "launchAngle": hit["la"], "totalDistance": hit.get("dist"),
                        "trajectory": hit["traj"], "coordinates": {"coordX": hit["x"], "coordY": hit["y"]}}
    return e


GAME = {"liveData": {"plays": {"allPlays": [
    {"matchup": {"batter": {"id": 1}, "pitcher": {"id": 2}, "batSide": {"code": "R"}, "pitchHand": {"code": "L"}},
     "playEvents": [pitch("C", 5), pitch("S", 12),
                    pitch("X", 5, ev=101.2, la=27.0, dist=410.0, traj="fly_ball", x=60.0, y=100.0)]},
    {"matchup": {"batter": {"id": 3}, "pitcher": {"id": 2}, "batSide": {"code": "L"}, "pitchHand": {"code": "L"}},
     "playEvents": [{"isPitch": False, "details": {"code": "PK"}}, pitch("B", 13), pitch("F", 4)]},
]}}}


class TestIterEvents(unittest.TestCase):
    def test_one_event_per_pitch_non_pitches_skipped(self):
        ev = list(tracking.iter_events(GAME))
        self.assertEqual(len(ev), 5)
        self.assertEqual([e["code"] for e in ev], ["C", "S", "X", "B", "F"])

    def test_fields(self):
        ev = list(tracking.iter_events(GAME))
        bip = ev[2]
        self.assertEqual((bip["batter"], bip["pitcher"], bip["bat_side"], bip["pitch_hand"]), (1, 2, "R", "L"))
        self.assertEqual((bip["ev"], bip["la"], bip["dist"], bip["traj"]), (101.2, 27.0, 410.0, "fly_ball"))
        self.assertEqual((bip["hc_x"], bip["hc_y"], bip["zone"]), (60.0, 100.0, 5))
        self.assertIsNone(ev[0]["ev"])
        self.assertEqual(ev[3]["bat_side"], "L")


class TestSeasonGames(unittest.TestCase):
    def test_lists_game_files_only(self):
        with tempfile.TemporaryDirectory() as d:
            old = pbp.PBP_DIR
            try:
                pbp.PBP_DIR = d
                folder = os.path.join(d, "2024", "11")
                os.makedirs(folder)
                for name in ("9.json.gz", "10.json.gz"):
                    with gzip.open(os.path.join(folder, name), "wt", encoding="utf-8") as fh:
                        json.dump(GAME, fh)
                with open(os.path.join(folder, "_manifest.json"), "w") as fh:
                    fh.write("{}")
                self.assertEqual(tracking.season_games(2024, 11), [9, 10])
                self.assertEqual(len(list(tracking.season_events(2024, 11))), 10)
            finally:
                pbp.PBP_DIR = old


if __name__ == "__main__":
    unittest.main()
