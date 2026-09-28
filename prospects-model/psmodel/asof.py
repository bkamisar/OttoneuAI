"""As-of targets: what a hitter produced after a snapshot season, and when that
answer became known. A backtest at vantage V may train only on cohorts whose
answer was known by V -- the NFLU rule.

Targets are RANK-based within each MLB season (plan B review): the SGP spread
between stars and replacement swings from year to year (the 144th-best hitter was
worth 0.93 SGP in 2013, 0.16 in 2014, 0.23 in 2026), so a fixed SGP bar made
"starter-quality" mean different things in different years.
"""
import numpy as np

from . import targets

RATING_YEARS = 4
SOON_YEARS = 2
FIRST_LABEL = 2013
STARTERS = 144          # 12 teams x 12 lineup slots


def attach_ranks(labels):
    """Adds 'rank' (1 = best that year, by total SGP) to every hitter-season, in place."""
    by = {}
    for (pid, typ), rows in labels.items():
        if typ == "H":
            for r in rows:
                by.setdefault(r["season"], []).append(r)
    for recs in by.values():
        for i, r in enumerate(sorted(recs, key=lambda r: -r["value"]), 1):
            r["rank"] = i
    return labels


def ref_curve(labels, v):
    """Typical SGP of the season ranked r (index r-1): the median across seasons
    FIRST_LABEL..v, 2020 excluded. Ranks are valued on this common scale."""
    by = {}
    for (pid, typ), rows in labels.items():
        if typ == "H":
            for r in rows:
                if FIRST_LABEL <= r["season"] <= v and r["season"] != 2020:
                    by.setdefault(r["season"], []).append(r["value"])
    n = min(len(x) for x in by.values())
    cols = [sorted(x, reverse=True)[:n] for x in by.values()]
    return [float(np.median(c)) for c in zip(*cols)]


def useful_value(curve):
    """The typical value of the 144th-best season: the starter line for top-N."""
    return curve[STARTERS - 1]


def rating_target(mlb, cohort, curve):
    """Best season in cohort+1..cohort+4 with >=100 PA, valued at the typical value
    of its rank, floored at 0."""
    vals = [curve[min(r["rank"], len(curve)) - 1] for r in mlb
            if cohort < r["season"] <= cohort + RATING_YEARS and (r.get("pa") or 0) >= targets.MIN_PA]
    return max(0.0, max(vals)) if vals else 0.0


def soon_target(mlb, cohort):
    """A top-144 season (starter-quality in that year) in cohort+1..cohort+2."""
    return any(r["rank"] <= STARTERS for r in mlb if cohort < r["season"] <= cohort + SOON_YEARS)


def rating_known(cohort, v):
    return cohort + RATING_YEARS <= v


def soon_known(cohort, v):
    return cohort + SOON_YEARS <= v
