"""League denominators, replacement levels, and per-team averages.

DENOMINATORS come from the league's real cross-team spread in standings.csv.
They were first drafted as a simulated league (deal the top 144 hitters and the
league's innings across 12 synthetic teams). Measured 2026-09-26 against the
real spread, that was wrong either way it was built:

    cat   real league   snake/real   random/real
    HR       30.2         0.54         0.93
    R        77.2         0.44         0.73
    SO      184.3         0.45         0.64
    ERA      0.302        0.66         0.75

(real = standings.csv at its 153 estimated games, scaled to 162.)
Snaking under-estimates by roughly half; random assignment by 7-36%. A real
league is more spread out than any mechanical draw -- managers punt categories,
build lopsided rosters and absorb injuries -- so no simulated league is worth
trusting. The real spread is a league property, which is what the design spec
asked for ("held fixed at this league's current values").

Denominators are then held FIXED across all label years, while replacement level
is recomputed PER SEASON. Fixed denominators plus per-season replacement is what
makes 2019 and 2024 comparable: era inflation is absorbed into replacement
instead of making old seasons look better.

Why not read the constants from the live JS tool: measured 2026-09-26, its
rest-of-season projections were nearly exhausted, so every pitching denominator
fell back to 1.0 and hitter replacement collapsed to 2.2 PA.
"""
import statistics

NUM_TEAMS = 12
FULL_SEASON_GAMES = 162
HITTER_SLOTS = 12            # C,1B,2B,SS,3B,MI,OF1-5,UTIL (shared.js HITTER_SLOTS)
STARTING_HITTERS = NUM_TEAMS * HITTER_SLOTS          # 144 -- used for synthetic teams
TEAM_IP_BUDGET = 1500                                # shared.js IP_MAX
LEAGUE_IP_BUDGET = NUM_TEAMS * TEAM_IP_BUDGET        # 18000

# Replacement level mirrors the FUTURE-YEAR branch of computeFABaselines in
# shared.js, which is the case that matches ours: it abandons "who is actually a
# free agent" (undefined for a historical season) and instead skips the top N
# the league rosters, taking the cohort at the boundary of what remains. Its
# comment: "the roster boundary dissolves each October ... the league re-rosters
# the best available."
#
# Constants are shared.js's, not invented here:
FA_COHORT_H = 8              # hitters averaged into the baseline
FA_COHORT_P = 10             # pitchers averaged into the baseline
FA_MIN_PA = 100              # role floor: excludes stashed prospects / injured
FA_MIN_IP = 30               # excludes elite rates on no playing time
# Rostered counts measured from this league's roster.csv on 2026-09-26 (526
# players across 12 teams). Skipping only the 144 STARTING slots would set
# replacement far too high -- teams roster ~25 hitters each, and the genuinely
# free alternative sits past all of them.
ROSTERED_H = 295
ROSTERED_P = 231

# What a 12-slot team's starters typically total in PA over a full season
# (2015-2019, measured: 7,106-7,376). Fixed rather than data-derived -- see
# league_averages.
TEAM_PA = 7200.0

# Seasons shorter than 162 games. 2020 was 60 games; every counting stat and
# every volume floor scales with it.
SEASON_GAMES = {2020: 60}


def season_fraction(season):
    return SEASON_GAMES.get(season, FULL_SEASON_GAMES) / float(FULL_SEASON_GAMES)


def _hitter_rank(row):
    """Crude quality proxy for ordering only: volume x rate."""
    return row["pa"] * (row["obp"] + row["slg"])


def _pitcher_rank(row):
    era = row["era"] if row["era"] > 0 else 99.0
    return row["ip"] * (1.0 / era + row["so"] / 1000.0)


_COUNTING = {"HR": "HR", "R": "R", "SO": "K"}            # our name -> standings column
_RATES = {"OBP": "OBP", "SLG": "SLG", "ERA": "ERA", "WHIP": "WHIP", "HR9": "HR/9"}


def denominators_from_standings(rows, games=None):
    """Cross-team stdev of each category from standings.csv-shaped rows.

    Counting stats (HR, R, SO) are scaled to a full 162-game season, because the
    standings are a partial season; rate stats are not scaled. `games` overrides
    the file's Games column, which is calendar-ESTIMATED and uniform across teams
    (MODEL.md section 1) -- pass it when the true count is known, e.g. 162 once
    the season is over.

    Sampling caveat: this is a stdev over 12 teams, so it carries roughly +-20%
    relative error. It moves the WEIGHT of a category, not the ordering of
    players within it.
    """
    if len(rows) < 2:
        raise ValueError("need at least 2 teams to measure spread")
    g = float(games) if games else float(rows[0]["Games"])
    if g <= 0:
        raise ValueError(f"games must be positive, got {g!r}")
    scale = FULL_SEASON_GAMES / g

    def spread(col):
        try:
            vals = [float(r[col]) for r in rows]
        except KeyError:
            raise ValueError(f"standings rows are missing column {col!r}")
        return statistics.pstdev(vals)

    out = {}
    for name, col in _COUNTING.items():
        out[name] = spread(col) * scale
    for name, col in _RATES.items():
        out[name] = spread(col)
    for name, sd in out.items():
        if not sd or sd != sd:
            raise ValueError(f"{name}: degenerate denominator {sd!r} (no spread between teams)")
    return out


def load_league_denominators(path, games=None):
    """Read a standings.csv from disk and derive denominators."""
    import csv
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return denominators_from_standings(list(csv.DictReader(fh)), games=games)


def hitter_replacement(hitter_rows, season_fraction=1.0):
    """Average of the cohort just past what the league rosters.

    Mirrors computeFABaselines' future-year branch: apply the volume floor, rank,
    skip ROSTERED_H, average the next FA_COHORT_H. The floor prorates with the
    season length, so a 60-game season is not asked for 100 PA.
    """
    floor = FA_MIN_PA * season_fraction
    pool = [r for r in hitter_rows if (r.get("pa") or 0) >= floor]
    ranked = sorted(pool, key=_hitter_rank, reverse=True)
    need = ROSTERED_H + FA_COHORT_H
    if len(ranked) < need:
        raise ValueError(f"need >= {need} hitters over {floor:g} PA, got {len(ranked)}")
    cohort = ranked[ROSTERED_H:need]
    n = len(cohort)
    return {k: sum(r[k] for r in cohort) / n for k in ("pa", "ab", "hr", "r", "obp", "slg")}


def league_averages():
    """avgPA / avgIP as calcPlayerSGP means them: per-TEAM totals for the players
    who actually start -- NOT league-wide totals, which are roughly double and
    would halve the weight of OBP and SLG against HR and R.

    Both are FIXED constants rather than derived from the season's data. A
    data-derived avg_pa is ~37% in the 60-game 2020 season, which cancels out of
    the rate terms ((obp - repl) x pa/avgPA) while the counting terms stay 37%:
    a hitter's OBP/SLG contribution would be full-sized and his HR/R 37%-sized.
    Fixed constants make a shortened season uniformly worth ~37% of a full one.
    avg_ip was already fixed at the 1,500 IP cap.
    """
    return TEAM_PA, float(TEAM_IP_BUDGET)


def pitcher_replacement(pitcher_rows, season_fraction=1.0):
    """Same construction as hitters, with the pitcher floor, count and cohort."""
    floor = FA_MIN_IP * season_fraction
    pool = [r for r in pitcher_rows if (r.get("ip") or 0.0) >= floor]
    ranked = sorted(pool, key=_pitcher_rank, reverse=True)
    need = ROSTERED_P + FA_COHORT_P
    if len(ranked) < need:
        raise ValueError(f"need >= {need} pitchers over {floor:g} IP, got {len(ranked)}")
    cohort = ranked[ROSTERED_P:need]
    n = len(cohort)
    return {k: sum(r[k] for r in cohort) / n for k in ("ip", "so", "era", "whip", "hr9")}
