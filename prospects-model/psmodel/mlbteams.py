"""MLB parent clubs: FanGraphs Board org codes -> MLB team ids, and each club's
regular-season winning percentage from MLB StatsAPI standings (first-party).

Content-asserted: a season must return exactly the 30 clubs below, and each
club's name must contain the nickname expected for its id.
"""
from . import http

URL = "https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season={season}&standingsTypes=regularSeason"
TEAMS = {
    "ARI": (109, "D-backs"), "ATL": (144, "Braves"), "BAL": (110, "Orioles"), "BOS": (111, "Red Sox"),
    "CHC": (112, "Cubs"), "CHW": (145, "White Sox"), "CIN": (113, "Reds"), "CLE": (114, "Guardians"),
    "COL": (115, "Rockies"), "DET": (116, "Tigers"), "HOU": (117, "Astros"), "KCR": (118, "Royals"),
    "LAA": (108, "Angels"), "LAD": (119, "Dodgers"), "MIA": (146, "Marlins"), "MIL": (158, "Brewers"),
    "MIN": (142, "Twins"), "NYM": (121, "Mets"), "NYY": (147, "Yankees"), "OAK": (133, "Athletics"),
    "PHI": (143, "Phillies"), "PIT": (134, "Pirates"), "SDP": (135, "Padres"), "SEA": (136, "Mariners"),
    "SFG": (137, "Giants"), "STL": (138, "Cardinals"), "TBR": (139, "Rays"), "TEX": (140, "Rangers"),
    "TOR": (141, "Blue Jays"), "WSN": (120, "Nationals"),
}
ALIASES = {"StL": "STL", "ATH": "OAK"}
# The standings feed names clubs by short nickname; Cleveland renamed for 2022.
OTHER_NAMES = {109: ("Diamondbacks",), 114: ("Indians",)}


def team_of(org):
    """(MLB team id, nickname) for a Board org code. An unknown code raises KeyError."""
    return TEAMS[ALIASES.get(org, org)]


def parse_standings(payload, season):
    """{team id: winning percentage} from a standings payload, content-checked."""
    got = {}
    for rec in payload.get("records") or []:
        for tr in rec.get("teamRecords") or []:
            t = tr.get("team") or {}
            w, l = int(tr.get("wins", 0)), int(tr.get("losses", 0))
            got[t.get("id")] = (t.get("name") or "", w / (w + l) if w + l else None)
    expected = dict(TEAMS.values())
    if set(got) != set(expected):
        raise http.DataError(f"standings {season}: clubs {sorted(set(got) ^ set(expected), key=str)} "
                             "don't match the 30 expected")
    for tid, nick in expected.items():
        if not any(n in got[tid][0] for n in (nick,) + OTHER_NAMES.get(tid, ())):
            raise http.DataError(f"standings {season}: team {tid} is {got[tid][0]!r}, expected '{nick}'")
    return {tid: pct for tid, (_, pct) in got.items()}


def win_pct(season):
    return parse_standings(http.fetch_json(URL.format(season=season)), season)
