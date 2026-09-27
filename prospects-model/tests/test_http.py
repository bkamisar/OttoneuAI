import json, os, tempfile, unittest
from psmodel import http


class TestCacheKey(unittest.TestCase):
    def test_distinct_urls_get_distinct_paths(self):
        a = http.cache_path("https://x/y?a=1", ".json")
        b = http.cache_path("https://x/y?a=2", ".json")
        self.assertNotEqual(a, b)

    def test_same_url_is_stable(self):
        a = http.cache_path("https://x/y?a=1", ".json")
        b = http.cache_path("https://x/y?a=1", ".json")
        self.assertEqual(a, b)


class TestAssertions(unittest.TestCase):
    """The rule earned the hard way: assert on CONTENT, not HTTP status.
    Four endpoints in this project returned 200 with wrong or empty data."""

    def test_require_rows_rejects_empty(self):
        with self.assertRaises(http.DataError):
            http.require_rows([], "empty-case")

    def test_require_keys_rejects_missing(self):
        with self.assertRaises(http.DataError):
            http.require_keys([{"a": 1}], ["a", "b"], "missing-case")

    def test_require_keys_accepts_present(self):
        http.require_keys([{"a": 1, "b": 2}], ["a", "b"], "ok-case")


class TestCacheRoundTrip(unittest.TestCase):
    def test_write_then_read(self):
        with tempfile.TemporaryDirectory() as d:
            old = http.CACHE_DIR
            try:
                http.CACHE_DIR = d
                p = http.cache_path("https://example/test", ".json")
                http.cache_write(p, json.dumps({"hello": "world"}))
                self.assertEqual(json.loads(http.cache_read(p))["hello"], "world")
                self.assertIsNone(http.cache_read(os.path.join(d, "nope.json")))
            finally:
                http.CACHE_DIR = old


if __name__ == "__main__":
    unittest.main()
