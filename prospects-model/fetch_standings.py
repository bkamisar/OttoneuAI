"""FV+ Phase 2: pull MLB regular-season standings (first-party StatsAPI) for the
seasons the FV+ classes need, and check them. Responses are cached under cache/
(gitignored); a rerun reads the cache and makes no requests.

Usage:  python fetch_standings.py
Network: statsapi.mlb.com only, stdlib urllib over HTTPS, no credentials.
"""
from psmodel import mlbteams

SEASONS = [s for s in range(2016, 2027) if s != 2020]
KNOWN_BEST = {2016: "CHC", 2018: "BOS", 2019: "HOU", 2022: "LAD"}   # public record, as a content check


def main():
    code_of = {tid: code for code, (tid, _) in mlbteams.TEAMS.items()}
    seen = {}
    for s in SEASONS:
        pct = mlbteams.win_pct(s)
        best, worst = max(pct, key=pct.get), min(pct, key=pct.get)
        print(f"{s}: 30 clubs; best {code_of[best]} {pct[best]:.3f}, worst {code_of[worst]} {pct[worst]:.3f}")
        if s in KNOWN_BEST and code_of[best] != KNOWN_BEST[s]:
            raise SystemExit(f"{s}: best record should be {KNOWN_BEST[s]}, got {code_of[best]}")
        seen[s] = tuple(sorted(pct.items()))
    if len(set(seen.values())) != len(seen):
        raise SystemExit("two seasons returned identical standings -- the season parameter may be ignored")
    print("standings OK")


if __name__ == "__main__":
    main()
