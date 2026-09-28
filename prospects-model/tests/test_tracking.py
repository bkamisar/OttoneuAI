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


class TestIterPitches(unittest.TestCase):
    def test_pitch_tracking_fields(self):
        game = {"liveData": {"plays": {"allPlays": [{"matchup": {"pitcher": {"id": 7}}, "playEvents": [
            {"isPitch": True, "details": {"code": "S", "type": {"code": "FF"}},
             "pitchData": {"startSpeed": 96.1,
                           "breaks": {"spinRate": 2400, "breakVerticalInduced": 17.0, "breakHorizontal": -6.5},
                           "coordinates": {"pfxX": -5.9, "pfxZ": 11.2}}},
            {"isPitch": False, "details": {"code": "X"}}]}]}}}
        self.assertEqual(list(tracking.iter_pitches(game)), [
            {"pitcher": 7, "type": "FF", "code": "S", "speed": 96.1, "spin": 2400, "ivb": 17.0, "hb": -6.5,
             "pfx_x": -5.9, "pfx_z": 11.2}])


class TestIterPitchEvents(unittest.TestCase):
    def test_fields_and_the_play_result_on_the_in_play_pitch(self):
        game = {"liveData": {"plays": {"allPlays": [{
            "matchup": {"pitcher": {"id": 7}, "batter": {"id": 9}, "pitchHand": {"code": "L"}, "batSide": {"code": "R"}},
            "result": {"eventType": "double"},
            "playEvents": [
                {"isPitch": True, "details": {"code": "S", "type": {"code": "SL"}},
                 "pitchData": {"startSpeed": 85.0, "extension": 6.4,
                               "breaks": {"spinRate": 2500, "breakVerticalInduced": 2.0, "breakHorizontal": 5.0},
                               "coordinates": {"x0": 1.8, "z0": 5.9}}},
                {"isPitch": True, "details": {"code": "X", "type": {"code": "FF"}},
                 "pitchData": {"startSpeed": 94.0, "extension": 6.5,
                               "breaks": {"spinRate": 2300, "breakVerticalInduced": 16.0, "breakHorizontal": -8.0},
                               "coordinates": {"x0": 1.9, "z0": 6.0}},
                 "hitData": {"launchSpeed": 101.0, "launchAngle": 18.0}}]}]}}}
        ps = list(tracking.iter_pitch_events(game))
        self.assertEqual(len(ps), 2)
        self.assertEqual((ps[0]["pitcher"], ps[0]["p_hand"], ps[0]["b_side"], ps[0]["type"], ps[0]["ext"]),
                         (7, "L", "R", "SL", 6.4))
        self.assertEqual((ps[0]["ev"], ps[0]["event"]), (None, None))       # not the in-play pitch
        self.assertEqual((ps[1]["ev"], ps[1]["la"], ps[1]["event"], ps[1]["x0"], ps[1]["z0"]),
                         (101.0, 18.0, "double", 1.9, 6.0))


if __name__ == "__main__":
    unittest.main()
