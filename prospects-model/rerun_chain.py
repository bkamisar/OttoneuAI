"""FV+ Phase 1: rerun the whole prospect chain after the league-season fix.

Usage:  python rerun_chain.py [--force]
Runs each step as its own process, in order. Finished steps are recorded in
cache/rerun_chain_state.json, so a relaunch skips them (--force redoes all).
Stops at the first failing step. Every step's output goes to
cache/rerun_chain_log.txt.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "cache", "rerun_chain_state.json")
LOG = os.path.join(HERE, "cache", "rerun_chain_log.txt")
STEPS = [
    ("hitter base", ["model3c_base.py"]),
    ("hitter final", ["model3c_final.py"]),
    ("pitcher base", ["model_p_base.py"]),
    ("pitcher final", ["model_p_final.py"]),
    ("hitter consensus", ["consensus_gate.py"]),
    ("pitcher consensus", ["consensus_gate.py", "--pitchers"]),
    ("fvplus scores", ["build_fvplus_scores.py"]),
    ("shopping list", ["build_shopping_list.py"]),
    ("audit", ["audit_pipeline.py"]),
]


def load_state():
    if not os.path.exists(STATE):
        return {}
    with open(STATE, encoding="utf-8") as fh:
        return json.load(fh)


def save_state(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, STATE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="redo every step")
    state = {} if ap.parse_args().force else load_state()
    for name, cmd in STEPS:
        if state.get(name) == "done":
            print(f"skip  {name} (done)", flush=True)
            continue
        print(f"run   {name}: {' '.join(cmd)}", flush=True)
        t0 = time.time()
        with open(LOG, "a", encoding="utf-8") as log:
            log.write(f"\n===== {name}: {' '.join(cmd)}  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            log.flush()
            rc = subprocess.run([sys.executable, *cmd], cwd=HERE, stdout=log, stderr=subprocess.STDOUT).returncode
        if rc != 0:
            raise SystemExit(f"FAILED {name} (exit {rc}) after {time.time() - t0:.0f}s -- see {LOG}")
        state[name] = "done"
        save_state(state)
        print(f"done  {name} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
