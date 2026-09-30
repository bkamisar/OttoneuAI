"""FV+ Phase 1: old vs new after the league-season fix.

Usage:  python phase1_compare.py
Reads cache/phase1_before/ (the snapshot) and the current cache outputs; writes
cache/phase1_compare.txt (gitignored) and prints it.
"""
import csv
import difflib
import json
import os

from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
BEFORE = os.path.join(CACHE, "phase1_before")
DATA = os.path.join(os.path.dirname(HERE), "data")
OUT = os.path.join(CACHE, "phase1_compare.txt")
VERDICT_FIELDS = ("verdict", "verdict_graded", "verdict_restored", "unstable", "show_model_for_ungraded")
REPORTS = ("model3c_base_report.txt", "model3c_final_report.txt", "model_p_base_report.txt",
           "model_p_final_report.txt", "consensus_report.txt", "consensus_p_report.txt")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def ratings(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["player_id"]: r for r in csv.DictReader(fh)}


def text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def main():
    L = ["FV+ PHASE 1 -- old (level-season) vs new (level-season-league) normalization", ""]
    L.append("1. Adopted groups (vantage decisions, unchanged rules):")
    for name in ("model3c_choice.json", "model_p_choice.json"):
        old, new = load(os.path.join(BEFORE, name)), load(os.path.join(CACHE, name))
        for t in ("rating", "soon"):
            o, n = old[t], new[t]
            L.append(f"  {name:22} {t:6} {o['kind']} {o['adopted']} -> {n['kind']} {n['adopted']}"
                     + ("" if (o["kind"], o["adopted"]) == (n["kind"], n["adopted"]) else "   CHANGED"))
    L += ["", "2. Consensus verdicts:"]
    for name in ("consensus_verdict.json", "consensus_p_verdict.json"):
        old, new = load(os.path.join(BEFORE, name)), load(os.path.join(CACHE, name))
        for t in ("rating", "soon"):
            o, n = old[t], new[t]
            changed = any(o[f] != n[f] for f in VERDICT_FIELDS)
            L.append(f"  {name:24} {t:6} " + ", ".join(f"{f} {o[f]} -> {n[f]}" for f in VERDICT_FIELDS)
                     + ("   CHANGED" if changed else ""))
    L += ["", "3. Production ratings, old vs new:"]
    for name in ("hitter_ratings.csv", "pitcher_ratings.csv"):
        old, new = ratings(os.path.join(BEFORE, name)), ratings(os.path.join(CACHE, name))
        common = sorted(set(old) & set(new))
        for col in ("rating_percentile", "p_useful_within_2"):
            a = [float(old[p][col]) for p in common]
            b = [float(new[p][col]) for p in common]
            top_o = set(sorted(common, key=lambda p: -float(old[p][col]))[:50])
            top_n = set(sorted(common, key=lambda p: -float(new[p][col]))[:50])
            L.append(f"  {name:20} {col:18} Spearman {spearmanr(a, b).statistic:.3f} over {len(common)}; "
                     f"top-50 overlap {len(top_o & top_n)}/50")
        L.append(f"  {name:20} players only in old {len(set(old) - set(new))}, only in new {len(set(new) - set(old))}")
    old, new = load(os.path.join(BEFORE, "prospect_model.json")), load(os.path.join(DATA, "prospect_model.json"))
    L += ["", "4. Shopping list counts:",
          f"  hitters  {old['counts']} -> {new['counts']}",
          f"  pitchers {old['pitchers']['counts']} -> {new['pitchers']['counts']}", ""]
    for name in REPORTS:
        diff = list(difflib.unified_diff(text(os.path.join(BEFORE, name)), text(os.path.join(CACHE, name)),
                                         "old/" + name, "new/" + name, lineterm="", n=0))
        L += [f"=== diff {name} ({'no change' if not diff else f'{len(diff)} lines'})"] + diff + [""]
    out = "\n".join(L)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(out)
    print(out)


if __name__ == "__main__":
    main()
