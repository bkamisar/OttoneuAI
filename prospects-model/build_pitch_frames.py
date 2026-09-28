"""Per level-season pitch frames for the pitch-level stuff model (P-E): one .npz per
season x level under cache/pitch_frames/ (gitignored), from the game records on disk.

Checkpointed: a finished level-season is skipped unless --force. An MLB season whose
download looks incomplete is refused, so a partial season can't be baked in.

Usage:  python build_pitch_frames.py [--force]
Reads only local game records. No network.
"""
import argparse
import os
import time

import numpy as np

from psmodel import pitchlevel as PL
from psmodel import tracking

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "cache", "pitch_frames")
JOBS = [(s, 1) for s in range(2020, 2027)] + [(s, 11) for s in range(2022, 2027)]
MIN_GAMES = {(2020, 1): 890, (2022, 11): 700}      # MLB 2020 = 60 games; AAA 2022 = PCL only
FULL_MLB, FULL_AAA = 2400, 2200


def frame_path(season, sport):
    return os.path.join(OUT_DIR, f"{season}_{sport}.npz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    for season, sport in JOBS:
        name = f"{season} {'MLB' if sport == 1 else 'AAA'}"
        path = frame_path(season, sport)
        if os.path.exists(path) and not args.force:
            print(f"[{name}] done -- skipping", flush=True)
            continue
        games = len(tracking.season_games(season, sport))
        need = MIN_GAMES.get((season, sport), FULL_MLB if sport == 1 else FULL_AAA)
        if games < need:
            print(f"[{name}] only {games} games on disk (need {need}) -- NOT built; finish the download", flush=True)
            continue
        t0 = time.time()
        fr = PL.season_frame(tracking.season_pitch_events(season, sport))
        tmp = path + ".tmp.npz"
        np.savez_compressed(tmp, **fr)
        os.replace(tmp, path)
        sw = fr["swing"]
        print(f"[{name}] {games} games, {len(fr['fam'])} pitches (FB {np.mean(fr['fam'] == 0):.0%}), "
              f"swing {sw.mean():.1%}, whiff|swing {fr['whiff'][sw].mean():.1%}, in play {int(fr['bip'].sum())}, "
              f"extension present {np.mean(np.isfinite(fr['X'][:, 4])):.0%} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
