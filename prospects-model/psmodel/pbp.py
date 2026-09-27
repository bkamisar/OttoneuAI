"""Minor-league play-by-play fetcher -- source of the pitch-result family.

Every pitch at every level back to 2016 carries a result description
("Swinging Strike", "Called Strike", "Foul", ...), which gives whiff, swing,
contact and CSW rates without tracking hardware. AAA from 2023 and the Florida
State League from 2021 also carry exit velocity, launch angle and pitch tracking.

One request per game. The first slice (AA + affiliated AAA, 2016-2019) is
~17,600 games, ~5 hours at the shared 1 req/s throttle, so EVERY GAME IS ITS OWN
CHECKPOINT: a game whose file exists is never refetched unless force=True, and
files are written atomically so a killed run can never leave a half-written file
that looks complete.

Storage: the ?fields= filter cuts payloads 5.5x (591 KB -> 108 KB, identical
content) and gzip compresses the rest, so raw data survives for re-extraction
without mirroring tens of gigabytes. Lives under cache/ (gitignored).
"""
import gzip
import json
import os
import time
import urllib.request

from . import http

PBP_DIR = os.path.join(http.CACHE_DIR, "pbp_live")   # complete game records; old trimmed files stay in cache/pbp
MEXICAN_LEAGUE_ID = 125     # classified AAA until 2021; not a prospect population
SCHEDULE = ("https://statsapi.mlb.com/api/v1/schedule?sportId={sport}&season={season}"
            "&gameType=R&hydrate=team(league)"
            "&fields=dates,games,gamePk,status,abstractGameState,teams,home,team,league,id")
FEED = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"   # the complete record: pitches, tracking, movement, location, spray, counts, results, weather, venue


def list_games(season, sport_id, include_leagues=None):
    """Final regular-season games for one level-season, Mexican League excluded.

    Excluded by league id rather than an allowlist, because every affiliated
    league was renamed and several changed levels in 2021. `include_leagues`
    optionally narrows to a set of home-league ids -- ball tracking in 2022 AAA
    exists only in the Pacific Coast League (112). The Mexican League stays out
    even if listed.
    """
    d = http.fetch_json(SCHEDULE.format(sport=sport_id, season=season))
    seen, out = set(), []
    for day in d.get("dates") or []:
        for g in day.get("games") or []:
            pk = g.get("gamePk")
            if pk in seen or (g.get("status") or {}).get("abstractGameState") != "Final":
                continue
            league = ((((g.get("teams") or {}).get("home") or {}).get("team") or {})
                      .get("league") or {}).get("id")
            if league == MEXICAN_LEAGUE_ID:
                continue
            if include_leagues is not None and league not in include_leagues:
                continue
            seen.add(pk)
            out.append({"game_pk": pk, "home_league_id": league})
    http.require_rows(out, f"schedule {season}/sport{sport_id}")
    return out


def game_path(season, sport_id, game_pk):
    """Every path component is forced to an integer. game_pk comes from MLB's
    response, so a tampered value like '../../x' must never reach the filesystem
    as a path -- int() raises on it instead."""
    return os.path.join(PBP_DIR, str(int(season)), str(int(sport_id)), f"{int(game_pk)}.json.gz")


def validate(text):
    """Parse and assert this is a real game record, not a challenge page."""
    try:
        d = json.loads(text)
    except (TypeError, ValueError):
        raise http.DataError(f"game feed is not JSON: {str(text)[:80]!r}")
    plays = (((d or {}).get("liveData") or {}).get("plays") or {}).get("allPlays") if isinstance(d, dict) else None
    if not isinstance(plays, list):
        raise http.DataError("game feed has no liveData.plays.allPlays list")
    return d


def _download(url):
    """Network call, isolated so tests can replace it."""
    last = None
    for i in range(3):
        try:
            http._throttle()
            req = urllib.request.Request(url, headers={"User-Agent": http.USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8-sig", errors="replace")
        except Exception as exc:        # noqa: BLE001 - retry any transport error
            last = exc
            time.sleep(1.5 * (i + 1))
    raise http.DataError(f"download failed after 3 attempts: {url} ({last})")


def fetch_game(season, sport_id, game_pk, force=False):
    """Fetch one game to disk. Returns 'skipped' or 'fetched'.

    Validates BEFORE writing and writes atomically (temp file, then rename), so
    an invalid payload or a killed process never leaves a file behind.
    """
    path = game_path(season, sport_id, game_pk)
    if os.path.exists(path) and not force:
        return "skipped"
    text = _download(FEED.format(pk=game_pk))
    validate(text)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return "fetched"


def load_game(season, sport_id, game_pk):
    with gzip.open(game_path(season, sport_id, game_pk), "rt", encoding="utf-8") as fh:
        return json.load(fh)
