"""Baseball Savant season leaderboards (MLB) for the bridge's MLB history.

Content guards, because Savant has silently ignored parameters before
(minors=true; and StatsAPI's metricAverages ignored sportId): the custom board's
'year' column must equal the request, and no two seasons may come back
byte-identical (the exit-velocity board has no year column to check).
"""
import csv
import hashlib
import io

from . import http
from .metrics import HITTER_METRICS

EV_FIELDS = ("max_hit_speed", "avg_distance")
CUSTOM_FIELDS = [m for m in HITTER_METRICS if m not in EV_FIELDS] + ["pa"]
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
    for d in out.values():
        for f in EV_FIELDS:
            d.setdefault(f, None)
    return out


def hitter_history(first, last):
    seen = {}
    return {y: hitter_season(y, seen) for y in range(first, last + 1)}
