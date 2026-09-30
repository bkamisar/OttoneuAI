"""MLB StatsAPI season stats — the canonical source for counting and rate stats.

sportId: 1 = MLB, 11 = AAA, 12 = AA, 13 = High-A, 14 = Single-A.
The player id is the SAME across levels, so MiLB->MLB is an exact join. This
matters: a name-substring search for "Witt" during design matched Jantzen
Witte, a 31-year-old in Tacoma, not Bobby Witt Jr.
"""
import os

from . import http

BASE = "https://statsapi.mlb.com/api/v1/stats"
PAGE = 1000

MLB, AAA, AA, HIGH_A, SINGLE_A = 1, 11, 12, 13, 14
MILB_SPORT_IDS = (AAA, AA, HIGH_A, SINGLE_A)


def num(v) -> float:
    """StatsAPI rate stats arrive as strings, sometimes leading-dot ('.369')."""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_innings(v) -> float:
    """'62.2' is 62 and 2/3 innings. Mirrors parseIPInnings in shared.js."""
    f = num(v)
    whole = int(f)
    outs = round((f - whole) * 10)
    return whole + outs / 3.0


def _common(split, season, sport_id):
    player = split.get("player", {}) or {}
    return {
        "player_id": player.get("id"),
        "name": player.get("fullName"),
        "season": season,
        "sport_id": sport_id,
        "team": (split.get("team") or {}).get("name"),
        "league": (split.get("league") or {}).get("name"),
        "age": split.get("stat", {}).get("age"),
    }


def normalize_hitter(split, season, sport_id):
    st = split.get("stat", {}) or {}
    row = _common(split, season, sport_id)
    row.update({
        "g": int(num(st.get("gamesPlayed"))),
        "pa": int(num(st.get("plateAppearances"))),
        "ab": int(num(st.get("atBats"))),
        "h": int(num(st.get("hits"))),
        "hr": int(num(st.get("homeRuns"))),
        "r": int(num(st.get("runs"))),
        "bb": int(num(st.get("baseOnBalls"))),
        "so": int(num(st.get("strikeOuts"))),
        "sb": int(num(st.get("stolenBases"))),
        "obp": num(st.get("obp")),
        "slg": num(st.get("slg")),
        "np": int(num(st.get("numberOfPitches"))),
    })
    return row


def normalize_pitcher(split, season, sport_id):
    st = split.get("stat", {}) or {}
    ip = parse_innings(st.get("inningsPitched"))
    hr = int(num(st.get("homeRuns")))
    row = _common(split, season, sport_id)
    row.update({
        "g": int(num(st.get("gamesPlayed"))),
        "gs": int(num(st.get("gamesStarted"))),
        "ip": ip,
        "so": int(num(st.get("strikeOuts"))),
        "bb": int(num(st.get("baseOnBalls"))),
        "hr": hr,
        "era": num(st.get("era")),
        "whip": num(st.get("whip")),
        # HR/9 is a scored category but not served; derive it.
        "hr9": (hr * 9.0 / ip) if ip > 0 else 0.0,
        "np": int(num(st.get("numberOfPitches"))),
        "strikes": int(num(st.get("strikes"))),
        "bf": int(num(st.get("battersFaced"))),
        "go": int(num(st.get("groundOuts"))),
        "ao": int(num(st.get("airOuts"))),
    })
    return row


def season_url(season, group, sport_id, offset):
    return (f"{BASE}?stats=season&season={season}&group={group}"
            f"&sportId={sport_id}&limit={PAGE}&offset={offset}&playerPool=all")


def season_stats(season: int, group: str, sport_id: int):
    """All player-seasons for one season/group/level. group is 'hitting'|'pitching'."""
    normalize = normalize_hitter if group == "hitting" else normalize_pitcher
    out, offset = [], 0
    while True:
        url = season_url(season, group, sport_id, offset)
        payload = http.fetch_json(url)
        stats = payload.get("stats") or []
        if not stats:
            break
        splits = stats[0].get("splits") or []
        if offset == 0:
            http.require_rows(splits, f"statsapi {season}/{group}/sport{sport_id}")
            http.require_keys(splits, ["player", "stat"],
                              f"statsapi {season}/{group}/sport{sport_id}")
        for s in splits:
            row = normalize(s, season, sport_id)
            if row["player_id"] is not None:
                out.append(row)
        if len(splits) < PAGE:
            break
        offset += PAGE
    return out


def invalidate_season(season, group, sport_id):
    """Move this season's cached pages aside (renamed *.stale) so the next call
    refetches -- for a season that was still in progress when first cached.
    Returns the number of pages moved."""
    moved, offset = 0, 0
    while True:
        path = http.cache_path(season_url(season, group, sport_id, offset), ".json")
        if not os.path.exists(path):
            return moved
        os.replace(path, path + ".stale")
        moved += 1
        offset += PAGE


def season_advanced(season: int, group: str, sport_id: int):
    """{player_id: {"swings", "whiffs"}} from stats=seasonAdvanced, summed
    across team splits. Validated: MLB 2024 whiff rate from this endpoint vs
    Savant's whiff_percent, r = 0.9997 over 397 hitters."""
    out, offset = {}, 0
    while True:
        url = (f"{BASE}?stats=seasonAdvanced&season={season}&group={group}"
               f"&sportId={sport_id}&limit={PAGE}&offset={offset}&playerPool=all")
        stats = http.fetch_json(url).get("stats") or []
        splits = (stats[0].get("splits") if stats else None) or []
        if offset == 0:
            http.require_rows(splits, f"seasonAdvanced {season}/{group}/sport{sport_id}")
        for s in splits:
            pid = (s.get("player") or {}).get("id")
            if pid is None:
                continue
            st = s.get("stat") or {}
            cur = out.setdefault(pid, {"swings": 0, "whiffs": 0})
            cur["swings"] += int(num(st.get("totalSwings")))
            cur["whiffs"] += int(num(st.get("swingAndMisses")))
        if len(splits) < PAGE:
            break
        offset += PAGE
    return out
