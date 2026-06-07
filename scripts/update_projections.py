"""
update_projections.py
---------------------
Fetches Steamer rest-of-season projections from FanGraphs and writes:
  data/proj_hitting.csv
  data/proj_pitching.csv

Only these two files are touched. Y1 / Y2 files (proj_y1_*.csv,
proj_y2_*.csv) are managed manually — this script never modifies them.

Run manually:  python scripts/update_projections.py
Run via CI:    GitHub Actions (see .github/workflows/update-projections.yml)
"""

import csv
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is not installed. Run: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FANGRAPHS_URL = "https://www.fangraphs.com/api/projections"

# steamerr = Steamer rest-of-season (best for in-season decisions)
# Change to "steamer" for full-season view if preferred
PROJ_TYPE = "steamerr"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.fangraphs.com/projections.aspx",
    "X-Requested-With": "XMLHttpRequest",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_projections(stats: str) -> list[dict]:
    """Fetch projection data from FanGraphs. stats='bat' or 'pit'."""
    params = {
        "type":    PROJ_TYPE,
        "stats":   stats,
        "pos":     "all",
        "team":    "0",
        "players": "0",
    }
    print(f"  GET {FANGRAPHS_URL}?type={PROJ_TYPE}&stats={stats}&pos=all ...")
    resp = requests.get(
        FANGRAPHS_URL, params=params, headers=REQUEST_HEADERS, timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(
            f"Expected JSON list from FanGraphs, got: {type(data).__name__}"
        )
    return data


def get(row: dict, *keys, default=""):
    """Return the first non-empty value found among the given keys."""
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip() not in ("", "None", "null"):
            return v
    return default


# ---------------------------------------------------------------------------
# Hitting
# ---------------------------------------------------------------------------

HITTING_COLS = [
    "Name", "Team", "PA", "AB", "H", "HR", "R", "BB", "HBP", "OBP", "SLG"
]

def extract_hitter(row: dict) -> dict | None:
    name = str(get(row, "PlayerName", "Name", "name", default="")).strip()
    if not name:
        return None
    return {
        "Name": name,
        "Team": get(row, "Team", "team"),
        "PA":   get(row, "PA"),
        "AB":   get(row, "AB"),
        "H":    get(row, "H"),
        "HR":   get(row, "HR"),
        "R":    get(row, "R"),
        "BB":   get(row, "BB"),
        "HBP":  get(row, "HBP", default=0),
        "OBP":  get(row, "OBP"),
        "SLG":  get(row, "SLG"),
    }


# ---------------------------------------------------------------------------
# Pitching
# ---------------------------------------------------------------------------

PITCHING_COLS = [
    "Name", "Team", "GS", "G", "IP", "HR", "SO", "BB", "HR/9", "WHIP", "ERA"
]

def extract_pitcher(row: dict) -> dict | None:
    name = str(get(row, "PlayerName", "Name", "name", default="")).strip()
    if not name:
        return None
    # HR/9 field name varies across FanGraphs responses
    hr9 = get(row, "HR9", "HR/9", "hr9")
    return {
        "Name":  name,
        "Team":  get(row, "Team", "team"),
        "GS":    get(row, "GS"),
        "G":     get(row, "G"),
        "IP":    get(row, "IP"),
        "HR":    get(row, "HR"),
        "SO":    get(row, "SO"),
        "BB":    get(row, "BB"),
        "HR/9":  hr9,
        "WHIP":  get(row, "WHIP"),
        "ERA":   get(row, "ERA"),
    }


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict], cols: list[str], path: Path) -> int:
    """Write rows to a comma-separated CSV. Returns number of rows written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


# ---------------------------------------------------------------------------
# Diagnostics — print first raw row so we can see actual field names
# ---------------------------------------------------------------------------

def show_sample(label: str, raw_rows: list[dict]) -> None:
    if not raw_rows:
        return
    sample = raw_rows[0]
    print(f"  Sample {label} row keys: {list(sample.keys())[:20]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    repo_root = Path(__file__).parent.parent
    data_dir  = repo_root / "data"

    # --- Hitting ---
    print("\n[1/2] Fetching hitting projections...")
    try:
        raw_hit = fetch_projections("bat")
    except Exception as e:
        print(f"ERROR fetching hitting projections: {e}")
        sys.exit(1)

    show_sample("hitter", raw_hit)
    hitters = [r for row in raw_hit if (r := extract_hitter(row)) is not None]
    if len(hitters) == 0:
        print("ERROR: 0 hitters extracted — field names may have changed.")
        print("       First raw row:", raw_hit[0] if raw_hit else "empty")
        sys.exit(1)

    hit_path = data_dir / "proj_hitting.csv"
    n_hit = write_csv(hitters, HITTING_COLS, hit_path)
    print(f"  ✓ {n_hit} hitters → {hit_path.relative_to(repo_root)}")

    # --- Pitching ---
    print("\n[2/2] Fetching pitching projections...")
    try:
        raw_pit = fetch_projections("pit")
    except Exception as e:
        print(f"ERROR fetching pitching projections: {e}")
        sys.exit(1)

    show_sample("pitcher", raw_pit)
    pitchers = [r for row in raw_pit if (r := extract_pitcher(row)) is not None]
    if len(pitchers) == 0:
        print("ERROR: 0 pitchers extracted — field names may have changed.")
        print("       First raw row:", raw_pit[0] if raw_pit else "empty")
        sys.exit(1)

    pit_path = data_dir / "proj_pitching.csv"
    n_pit = write_csv(pitchers, PITCHING_COLS, pit_path)
    print(f"  ✓ {n_pit} pitchers → {pit_path.relative_to(repo_root)}")

    print(f"\nDone. {n_hit} hitters, {n_pit} pitchers written.")


if __name__ == "__main__":
    main()
