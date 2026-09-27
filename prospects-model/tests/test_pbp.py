import gzip, json, os, tempfile, unittest
from psmodel import http, pbp

VALID = json.dumps({"allPlays": [{"matchup": {"batter": {"id": 1}, "pitcher": {"id": 2}},
                                  "playEvents": [{"isPitch": True,
                                                  "details": {"description": "Ball"}}]}]})
CLOUDFLARE = "<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>"


def schedule(*games):
    return {"dates": [{"games": list(games)}]}


def game(pk, league_id, state="Final"):
    return {"gamePk": pk, "status": {"abstractGameState": state},
            "teams": {"home": {"team": {"league": {"id": league_id}}}}}


class TestListGames(unittest.TestCase):
    def setUp(self):
        self._orig = http.fetch_json

    def tearDown(self):
        http.fetch_json = self._orig

    def test_excludes_mexican_league_and_unfinished_and_dupes(self):
        """The Mexican League was 32% of qualified 'AAA' hitters in 2019, median
        age 29 vs 26. It is excluded by league id so no allowlist has to track
        the 2021 league renames."""
        http.fetch_json = lambda url: schedule(
            game(1, 112), game(2, 117), game(3, pbp.MEXICAN_LEAGUE_ID),
            game(4, 117, state="Preview"), game(2, 117))          # 2 again: resumed game
        self.assertEqual([g["game_pk"] for g in pbp.list_games(2019, 11)], [1, 2])

    def test_include_leagues_keeps_only_those(self):
        """Tracking in 2022 AAA exists only in the Pacific Coast League (112)."""
        http.fetch_json = lambda url: schedule(game(1, 112), game(2, 117), game(3, 112))
        self.assertEqual([g["game_pk"] for g in pbp.list_games(2022, 11, include_leagues={112})], [1, 3])

    def test_include_leagues_never_readmits_the_mexican_league(self):
        http.fetch_json = lambda url: schedule(game(1, 112), game(2, pbp.MEXICAN_LEAGUE_ID))
        got = pbp.list_games(2019, 11, include_leagues={112, pbp.MEXICAN_LEAGUE_ID})
        self.assertEqual([g["game_pk"] for g in got], [1])

    def test_empty_schedule_is_an_error_not_an_empty_season(self):
        http.fetch_json = lambda url: {"dates": []}
        with self.assertRaises(http.DataError):
            pbp.list_games(2019, 11)


class TestValidate(unittest.TestCase):
    def test_rejects_cloudflare_challenge(self):
        with self.assertRaises(http.DataError):
            pbp.validate(CLOUDFLARE)

    def test_rejects_json_without_plays(self):
        with self.assertRaises(http.DataError):
            pbp.validate(json.dumps({"copyright": "x"}))

    def test_accepts_valid(self):
        self.assertIn("allPlays", pbp.validate(VALID))


class TestFetchGame(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._dir, self._dl = pbp.PBP_DIR, pbp._download
        pbp.PBP_DIR = self.tmp.name
        self.calls = []

        def fake(url):
            self.calls.append(url)
            return VALID
        pbp._download = fake

    def tearDown(self):
        pbp.PBP_DIR, pbp._download = self._dir, self._dl
        self.tmp.cleanup()

    def test_path_layout(self):
        self.assertEqual(pbp.game_path(2019, 12, 555),
                         os.path.join(self.tmp.name, "2019", "12", "555.json.gz"))

    def test_tampered_game_id_cannot_escape_the_cache(self):
        """game_pk comes from a network response; a path-traversal value must
        raise rather than become a file path outside the cache."""
        for bad in ("../../evil", "555/../../x", "..\\evil", "", None):
            with self.assertRaises((ValueError, TypeError)):
                pbp.game_path(2019, 12, bad)

    def test_fetch_then_checkpoint_skip(self):
        self.assertEqual(pbp.fetch_game(2019, 12, 555), "fetched")
        self.assertEqual(pbp.fetch_game(2019, 12, 555), "skipped")
        self.assertEqual(len(self.calls), 1, "an existing file must never be refetched")

    def test_force_refetches(self):
        pbp.fetch_game(2019, 12, 555)
        self.assertEqual(pbp.fetch_game(2019, 12, 555, force=True), "fetched")
        self.assertEqual(len(self.calls), 2)

    def test_uses_the_fields_filter(self):
        pbp.fetch_game(2019, 12, 555)
        self.assertIn("fields=", self.calls[0])
        self.assertIn("/game/555/playByPlay", self.calls[0])

    def test_round_trip(self):
        pbp.fetch_game(2019, 12, 555)
        self.assertEqual(pbp.load_game(2019, 12, 555)["allPlays"][0]["matchup"]["batter"]["id"], 1)
        with gzip.open(pbp.game_path(2019, 12, 555), "rt", encoding="utf-8") as fh:
            json.load(fh)

    def test_invalid_payload_leaves_no_file(self):
        """A Cloudflare page or truncated body must never be written, or the
        checkpoint would treat a broken game as done forever."""
        pbp._download = lambda url: CLOUDFLARE
        with self.assertRaises(http.DataError):
            pbp.fetch_game(2019, 12, 777)
        self.assertFalse(os.path.exists(pbp.game_path(2019, 12, 777)))
        leftovers = [f for _, _, fs in os.walk(self.tmp.name) for f in fs]
        self.assertEqual(leftovers, [], "no temp file may survive a failed write")


if __name__ == "__main__":
    unittest.main()
