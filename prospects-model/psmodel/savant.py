"""Baseball Savant season leaderboards (MLB) for the bridge's MLB history.

Content guards, because Savant has silently ignored parameters before
(minors=true; and StatsAPI's metricAverages ignored sportId): the custom board's
'year' column must equal the request, and no two seasons may come back
byte-identical (the exit-velocity board has no year column to check).
"""
import csv
import hashlib
import io

from . import http, statsapi
from .metrics import HITTER_METRICS

EV_FIELDS = ("max_hit_speed", "avg_distance")
# Savant's spray comes from tracked launch direction: usable for MLB history, but
# our AAA game records can't reproduce it (plan A parity), so these are MLB-only.
SPRAY_FIELDS = ["pull_percent", "straightaway_percent", "opposite_percent"]
CUSTOM_FIELDS = [m for m in HITTER_METRICS if m not in EV_FIELDS] + SPRAY_FIELDS + ["pa"]
CUSTOM_URL = ("https://baseballsavant.mlb.com/leaderboard/custom?year={year}&type=batter&min=1"
              "&selections={sel}&csv=true")
EV_URL = ("https://baseballsavant.mlb.com/leaderboard/statcast?type=batter&year={year}"
          "&position=&team=&min=1&csv=true")


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def hitter_season(year, _seen=None):
    """{player_id: {field: value}} for one MLB season (CUSTOM_FIELDS + EV_FIELDS)."""
    ctext = http.fetch_text(CUSTOM_URL.format(year=year, sel=",".join(CUSTOM_FIELDS)), ".csv")
    etext = http.fetch_text(EV_URL.format(year=year), ".csv")
    if _seen is not None:
        for tag, text in (("custom", ctext), ("exit-velocity", etext)):
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if (tag, digest) in _seen:
                raise http.DataError(f"Savant {tag} leaderboard for {year} is identical to "
                                     f"{_seen[(tag, digest)]} -- year parameter ignored?")
            _seen[(tag, digest)] = year
    crows, erows = _rows(ctext), _rows(etext)
    http.require_rows(crows, f"savant custom {year}")
    http.require_rows(erows, f"savant exit-velocity {year}")
    out = {}
    for r in crows:
        http.require_value(r.get("year"), year, f"savant custom {year}")
        out[int(r["player_id"])] = {f: _num(r.get(f)) for f in CUSTOM_FIELDS}
    for r in erows:
        d = out.setdefault(int(r["player_id"]), {f: None for f in CUSTOM_FIELDS})
        d.update({f: _num(r.get(f)) for f in EV_FIELDS})
        d["bbe"] = _num(r.get("attempts"))
    for d in out.values():
        for f in EV_FIELDS + ("bbe",):
            d.setdefault(f, None)
    return out


def hitter_history(first, last):
    seen = {}
    return {y: hitter_season(y, seen) for y in range(first, last + 1)}


FB_TYPES = ("ff", "si", "fc")
PITCHER_FIELDS = ([f"n_{t}_formatted" for t in FB_TYPES]
                  + [f"{t}_avg_{m}" for t in FB_TYPES for m in ("speed", "spin", "break_x", "break_z_induced")]
                  + ["breaking_avg_speed", "breaking_avg_spin", "whiff_percent", "p_formatted_ip", "pitch_count"])
PITCHER_URL = ("https://baseballsavant.mlb.com/leaderboard/custom?year={year}&type=pitcher&min=1"
               "&selections={sel}&csv=true")


def pitcher_row(r):
    """One Savant pitcher row -> pitch_metrics' fields, on the most-thrown fastball
    (same rule as pitch_metrics); horizontal break as a magnitude."""
    shares = {t: _num(r.get(f"n_{t}_formatted")) or 0.0 for t in FB_TYPES}
    t = max(FB_TYPES, key=lambda k: shares[k])
    has_fb = shares[t] > 0
    hb = _num(r.get(f"{t}_avg_break_x")) if has_fb else None
    return {
        "fb_speed": _num(r.get(f"{t}_avg_speed")) if has_fb else None,
        "fb_spin": _num(r.get(f"{t}_avg_spin")) if has_fb else None,
        "fb_ivb": _num(r.get(f"{t}_avg_break_z_induced")) if has_fb else None,
        "fb_hb": abs(hb) if hb is not None else None,
        "breaking_speed": _num(r.get("breaking_avg_speed")),
        "breaking_spin": _num(r.get("breaking_avg_spin")),
        "whiff_percent": _num(r.get("whiff_percent")),
        "pitches": _num(r.get("pitch_count")),
        "ip": statsapi.parse_innings(r["p_formatted_ip"]) if r.get("p_formatted_ip") else None,
    }


def pitcher_season(year, _seen=None):
    """{player_id: pitcher_row(...)} for one MLB season, with the year guard."""
    text = http.fetch_text(PITCHER_URL.format(year=year, sel=",".join(PITCHER_FIELDS)), ".csv")
    if _seen is not None:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in _seen:
            raise http.DataError(f"Savant pitcher leaderboard for {year} is identical to "
                                 f"{_seen[digest]} -- year parameter ignored?")
        _seen[digest] = year
    rows = _rows(text)
    http.require_rows(rows, f"savant pitcher {year}")
    http.require_keys(rows, ["player_id", "year"] + PITCHER_FIELDS, f"savant pitcher {year}")
    out = {}
    for r in rows:
        http.require_value(r.get("year"), year, f"savant pitcher {year}")
        out[int(r["player_id"])] = pitcher_row(r)
    return out


def pitcher_history(first, last):
    seen = {}
    return {y: pitcher_season(y, seen) for y in range(first, last + 1)}
