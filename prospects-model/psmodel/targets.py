"""Turns a player's MLB season labels into a training target.

Peak value over the first 4 seasons from debut. The window is short on purpose:
the planning horizon is not 5-10 years, so producing well AND soon is the goal,
and a short window also leaves more cohorts with complete outcomes.
"""
WINDOW = 4
MIN_PA = 100          # peak-eligibility floor; low volume already self-penalizes
MIN_IP = 25
NON_ARRIVAL_YEARS = 5  # seasons after the snapshot before a no-show counts as a zero
MIN_WEIGHT = 0.25


def _eligible(row):
    return (row.get("pa") or 0) >= MIN_PA or (row.get("ip") or 0.0) >= MIN_IP


def build_target(mlb_seasons, current_season, snapshot_season=None):
    """mlb_seasons: [{season, value, pa, ip}] for ONE player (may be empty)."""
    rows = sorted(mlb_seasons, key=lambda r: r["season"])
    if not rows:
        elapsed = (current_season - snapshot_season) if snapshot_season is not None else 0
        labeled = snapshot_season is not None and elapsed >= NON_ARRIVAL_YEARS
        return {"debut_season": None, "peak_value": 0.0, "peak_season": None,
                "completeness": 1.0 if labeled else 0.0,
                "years_to_contribute": None, "labeled": labeled}

    debut = rows[0]["season"]
    window = [r for r in rows if debut <= r["season"] <= debut + WINDOW - 1]
    eligible = [r for r in window if _eligible(r)]

    peak = max(eligible, key=lambda r: r["value"]) if eligible else None
    observed = min(WINDOW, max(0, current_season - debut + 1))
    first = next((r for r in rows if _eligible(r)), None)

    return {
        "debut_season": debut,
        # Floored at 0 like shared.js (Math.max(0, sgp)): a below-replacement
        # debut must not rank under a labeled non-arrival.
        "peak_value": max(0.0, peak["value"]) if peak else 0.0,
        "peak_season": peak["season"] if peak else None,
        "completeness": max(MIN_WEIGHT, observed / WINDOW),
        "years_to_contribute": (first["season"] - snapshot_season)
                               if (first and snapshot_season is not None) else None,
        "labeled": True,
    }
