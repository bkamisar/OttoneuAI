"""As-of targets: what a hitter produced after a snapshot season, and when that
answer became known. A backtest at vantage V may train only on cohorts whose
answer was known by V -- the NFLU rule.
"""
from . import dataset, targets

RATING_YEARS = 4
SOON_YEARS = 2
FIRST_LABEL = 2013


def rating_target(mlb, cohort):
    """Best season value in cohort+1..cohort+4 with >=100 PA, floored at 0."""
    vals = [r["value"] for r in mlb
            if cohort < r["season"] <= cohort + RATING_YEARS and (r.get("pa") or 0) >= targets.MIN_PA]
    return max(0.0, max(vals)) if vals else 0.0


def soon_target(mlb, cohort, bar):
    """A starter-quality season (total value >= bar) in cohort+1..cohort+2."""
    return any(r["value"] >= bar for r in mlb if cohort < r["season"] <= cohort + SOON_YEARS)


def rating_known(cohort, v):
    return cohort + RATING_YEARS <= v


def soon_known(cohort, v):
    return cohort + SOON_YEARS <= v


def useful_bar(labels, v):
    """The starter-quality bar from MLB seasons through v only."""
    return dataset.useful_threshold(labels, "H", first=FIRST_LABEL, last=v)
