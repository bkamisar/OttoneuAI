"""Whiff-family test: does minor-league whiff rate / CSW predict MLB value in
this league's 4x4 beyond K% and BB%?

Usage:  python whiff_test.py     (needs cache/labels.csv -- python build_labels.py)
Writes: cache/whiff_test_report.txt
"""
import os
import statistics

from psmodel import dataset, evaluate, milb
from psmodel import features as F

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = os.path.join(HERE, "cache", "labels.csv")
REPORT = os.path.join(HERE, "cache", "whiff_test_report.txt")
SEASONS = (2016, 2017, 2018, 2019)       # most complete MLB outcomes by 2026
LEVELS = (12, 11)                        # AA, affiliated AAA
MAX_PA, MAX_IP = 800, 250                # one level-season can't exceed these


def gather(group):
    rows = []
    for s in SEASONS:
        for lvl in LEVELS:
            rows += milb.season_rows(s, lvl, group)
    # Guard: if StatsAPI returned a combined split alongside per-team splits,
    # combining would double-count and volumes would blow past a real season.
    bad = [r for r in rows if r.get("pa", 0) > MAX_PA or r.get("ip", 0) > MAX_IP]
    if bad:
        raise SystemExit(f"{len(bad)} rows exceed one-level volume limits "
                         f"(double-counted splits?) e.g. {bad[0]['name']}")
    return rows


def interaction_table(rows, a, b, lines):
    """Starter-quality rate split at the medians of two traits -- the direct,
    eyeball check on 'whiffs a lot but has real power'. Counts rows, so a
    prospect with an AA and an AAA season appears twice."""
    ma = statistics.median(r["f"][a] for r in rows)
    mb = statistics.median(r["f"][b] for r in rows)
    lines.append(f"  Became starter-quality, by {a} x {b} (split at medians):")
    for hi_a in (False, True):
        cells = []
        for hi_b in (False, True):
            cell = [r for r in rows if (r["f"][a] > ma) == hi_a and (r["f"][b] > mb) == hi_b]
            rate = sum(r["useful"] for r in cell) / len(cell) if cell else 0.0
            cells.append(f"{b} {'high' if hi_b else 'low '} {rate:5.1%} (n={len(cell)})")
        lines.append(f"    {a} {'high' if hi_a else 'low '} | " + " | ".join(cells))


def run(typ, group, base, family, labels, lines):
    thr = dataset.useful_threshold(labels, typ)
    rows = dataset.build(gather(group), typ, labels, thr)
    F.standardize_within(rows, base + family)
    rows = dataset.complete_cases(rows, base + family)
    players = {r["player_id"] for r in rows}
    useful = {r["player_id"] for r in rows if r["useful"]}
    lines.append(f"\n=== {'HITTERS' if typ == 'H' else 'PITCHERS'}: {len(rows)} rows, "
                 f"{len(players)} players, {len(useful)} became starter-quality "
                 f"(peak >= {thr:.2f} SGP) ===")
    adopted_by = []
    for kind in evaluate.KINDS:
        res = evaluate.compare(rows, base, family, kind=kind)
        lines.append(f"  [{kind}]")
        for key, label in (("rho", "rank accuracy (Spearman)"), ("top", "top-50 hit rate")):
            b = [r[key + "_base"] for r in res]
            f = [r[key + "_fam"] for r in res]
            lines.append(f"    {label:26} baseline {statistics.mean(b):.3f} +/- {statistics.pstdev(b):.3f}"
                         f"   with whiff family {statistics.mean(f):.3f} +/- {statistics.pstdev(f):.3f}")
        ok, wins = evaluate.adopt(res)
        lines.append(f"    {wins}/10 shuffles improved rank accuracy without hurting top-50 (needs 8)")
        if ok:
            adopted_by.append(kind)
    verdict = ("ADOPTED (via " + ", ".join(adopted_by) + ")") if adopted_by else "NOT adopted"
    lines.append(f"  VERDICT: whiff family {verdict}"
                 "  -- a screen, not a final cut: 3c's tree models re-test everything jointly")
    if typ == "H":
        interaction_table(rows, "whiff", "iso", lines)
    lines.append("  Traits by weight (standardized ridge coefficient; + means more MLB value):")
    for k, c in evaluate.trait_ranking(rows, base + family):
        lines.append(f"    {k:8} {c:+.3f}")


def main():
    labels = dataset.load_labels(LABELS)
    lines = ["Whiff-family test -- AA + affiliated AAA, 2016-2019 seasons; MLB outcomes through 2026"]
    run("H", "hitting", F.BASE_H, F.FAMILY_H, labels, lines)
    run("P", "pitching", F.BASE_P, F.FAMILY_P, labels, lines)
    text = "\n".join(lines)
    print(text)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"\nreport -> {REPORT}")


if __name__ == "__main__":
    main()
