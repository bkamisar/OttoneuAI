import os
import tempfile
import unittest

from psmodel import http, statsapi


class TestInvalidate(unittest.TestCase):
    def test_moves_every_cached_page_aside(self):
        with tempfile.TemporaryDirectory() as d:
            old = http.CACHE_DIR
            try:
                http.CACHE_DIR = d
                for off in (0, statsapi.PAGE):
                    p = http.cache_path(statsapi.season_url(2026, "hitting", statsapi.MLB, off), ".json")
                    with open(p, "w", encoding="utf-8") as fh:
                        fh.write("{}")
                self.assertEqual(statsapi.invalidate_season(2026, "hitting", statsapi.MLB), 2)
                self.assertEqual(statsapi.invalidate_season(2026, "hitting", statsapi.MLB), 0)
                self.assertEqual(len([f for f in os.listdir(d) if f.endswith(".stale")]), 2)
            finally:
                http.CACHE_DIR = old


if __name__ == "__main__":
    unittest.main()
