"""4x4 SGP above replacement -- a mirror of calcPlayerSGP in shared.js.

Any change here must keep parity/compare.py passing. The JS engine is the
reference implementation; this is a port, not a redesign.

Known simplification: uses the general replacement baseline, not hitterSGP's
positional offsets. Those need full-league position data per season and
redistribute value among hitters rather than changing the total.
"""


def hitter_sgp(row, repl, den, avg_pa):
    pa = row["pa"] or 0
    pa_ratio = (pa / repl["pa"]) if repl.get("pa") else 1.0
    sgp = (row["hr"] - repl["hr"] * pa_ratio) / den["HR"]
    sgp += (row["r"] - repl["r"] * pa_ratio) / den["R"]
    sgp += (row["obp"] - repl["obp"]) * pa / (avg_pa or 1) / den["OBP"]
    sgp += (row["slg"] - repl["slg"]) * pa / (avg_pa or 1) / den["SLG"]
    return sgp


def pitcher_sgp(row, repl, den, avg_ip):
    ip = row["ip"] or 0.0
    # max(1, ...) never scales DOWN: a low-inning reliever faces the full
    # replacement K total and stays docked for volume (shared.js invariant #3).
    ip_scale = max(1.0, ip / repl["ip"]) if repl.get("ip") else 1.0
    sgp = (row["so"] - repl["so"] * ip_scale) / den["SO"]
    sgp += (repl["era"] - row["era"]) * ip / (avg_ip or 1) / den["ERA"]
    sgp += (repl["whip"] - row["whip"]) * ip / (avg_ip or 1) / den["WHIP"]
    sgp += (repl["hr9"] - row["hr9"]) * ip / (avg_ip or 1) / den["HR9"]
    return sgp
