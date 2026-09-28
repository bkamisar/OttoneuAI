# Prospect Shopping List (sub-project 4): Design

**Status:** approved 2026-09-28. Plan: `plans/2026-09-28-prospect-shopping-list.md`.

## What this is

The prospect model's user-facing surface. The goal is to use **FanGraphs and the
model together**, following what plan C proved
(`2026-09-27-3c-hitters-design.md`, "Plan C result"):

- **How good:** follow FanGraphs' order. Combining it with the model never beat
  FanGraphs alone by 1 SE.
- **Useful soon:** the average of the FV and model percentiles beat FanGraphs
  alone in 3 of 3 test years.
- **Ungraded hitters:** the model is better than chance, but true sleepers rarely
  pan out. Most ungraded hits had been on an earlier list.

The page answers two questions directly and says in words where the model
disagrees, rather than showing a grid of numbers to combine by hand.

**Supersedes** the parent spec's section 4 idea of an "edge column = model value −
FV dynasty value". Plan C found no proven ceiling edge, so a dollar "edge" would
be noise.

## Data: `build_shopping_list.py` → `data/prospect_model.json`

A local script in `prospects-model/`. It reads only local files (no network):
- `cache/hitter_ratings.csv`: the model's 2026 hitters (from `model3c_final.py`).
- `data/prospects.csv`: the site's current FanGraphs board. It's the Aug 24
  in-season board for now (the Apps Script feed is blocked by Cloudflare), and a
  manual export replaces it.
- `cache/fv/board_<year>_hitters.csv` (2017–2026): used only for the
  "was on an earlier list" flag.

**Matching** uses plan C's tested `consensus.match`: name plus a calibrated age
guard, with same-name cases never guessed. Board pitchers are skipped, since
there's no pitcher model.

**The pool** for percentiles is the board hitters that have a model read. In it:
- `fv_pct` comes from FanGraphs' order (`consensus.fv_score`), `soon_pct` from
  the model's 2-year odds, and `rating_pct` from the model's rating.
- `ready = (fv_pct + soon_pct) / 2` gives `ready_rank` (1 = closest to helping).
  This is exactly the combination plan C tested.

**Take** (one line of plain language; a disagreement means ≥ 25 percentile
points):
- `soon_pct − fv_pct` ≥ +0.25 → "Model: readier than the grade suggests"; ≤ −0.25
  → "Model: further away than the grade suggests". This is the proven one, and it
  is what moves a player in the ready ranking.
- `rating_pct − fv_pct` beyond ±0.25 → "likes the bat more/less (ceiling:
  unproven)". This is context only.
- Both can appear, joined by "; ". If neither applies → "Model agrees".

**Ungraded** (model hitters not on the board), sorted by the model's rating
percentile, each with a `listed` year and a take:
- On an earlier list → "On the <year> list, since dropped".
- Never on a list since 2017 → "Never on a FanGraphs list".
- The name matches a board prospect of a different age → "Name matches a
  FanGraphs prospect of a different age — check".
- The name is shared with a board prospect it can't be told apart from → "Name
  shared with a FanGraphs prospect — check". The board keys involved are listed
  so those board rows can say "No model read: name shared by two players".

**Odds display:** the model's 2-year probability rounded to the nearest 5%;
under 2.5% shows as "<5%". It's roughly calibrated at the top (2024: 27%
predicted vs 22% actual).

**Join key** = the board's own `Name|Org` exactly as written in
`data/prospects.csv`, which is the page's `rawName|org`. No second name
normalizer in JavaScript is needed.

**What gets committed:** model numbers, derived ranks, takes, flags and the join
key. The JSON holds no FanGraphs grades. (The board itself is already public in
`data/prospects.csv` through the site's existing pipeline; the raw Board
exports in `cache/fv/` stay gitignored.)

**Refresh:** local run plus commit, as in the parent spec.
- When the board changes: the user exports it, it replaces
  `data/prospects.csv`, the script is rerun, and both files are committed.
- The model itself changes once a season.

## Page: `prospects.html`

- **Lens toggle:**
  - **"Best prospects"** (default): sorted by FV, as now.
  - **"Closest to helping"**: hitters only, sorted by `ready_rank`.
  - Picking the Pitchers or Ungraded filter returns to "Best prospects".
- **Type filter** gains **"Ungraded (model only)"**. In that view:
  - The FV column becomes "Model" (the rating percentile) and is the default sort.
  - Board-only columns show "—"; Ottoneu team and salary still show, found by name.
  - A caveat line reads: "Model only, no scouting grade. In backtests about
    1–2.5% of never-listed hitters became starter-quality; most ungraded hits had
    been on an earlier list."
- **Two new columns:**
  - **2-yr odds** (sortable).
  - **Take**, which holds:
    - the take line for hitters with a model read;
    - "No model read: under 150 PA at a full-season level in 2026" for other
      hitters, or "name shared by two players" for ambiguous ones;
    - "FanGraphs only (no pitcher model)" for pitchers.
- **Note line** per lens:
  - "Closest to helping": "Ranked by the average of FanGraphs' order and the
    model's 2-year odds, which beat FanGraphs alone in 3 of 3 test years. N board
    hitters have no model read."
  - "Best prospects": "Sorted by FanGraphs. Take shows where the model disagrees;
    ceiling disagreements are unproven."
- **Unchanged:** FV badges, grades, Proj $ and dynasty $ (these still come from
  FanGraphs' rank and FV curve).
- **If the JSON is missing,** the model columns show "—" and the lens toggle hides.
  The page otherwise works as today.
- **Rendering:** stays `textContent`-only (the site's invariant).

## Testing

- Python unit tests for:
  - the board loader (skips pitchers and duplicates, finds the header);
  - odds rounding;
  - every take case;
  - a synthetic end-to-end build (ready ranks, listed years, ambiguous and
    different-age cases).
- Page check in the preview browser against the real JSON:
  - Known names land in the right rows.
  - The "Closest to helping" order matches `ready_rank`.
  - The Ungraded view shows listed flags and the caveat.
  - Pitchers show "FanGraphs only".
  - No console errors.

## Out of scope

Pitcher model; daily automation; dollar-value changes; the optional tool-grade
test; revisits that wait on future seasons (see the 3c spec).
