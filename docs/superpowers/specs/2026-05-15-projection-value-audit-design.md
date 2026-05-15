# Projection Value Audit — Design Spec
**Date:** 2026-05-15  
**Scope:** Audit and improve accuracy of projected value and dynasty value calculations in the Ottoneu 4x4 league analysis tool.

---

## Context

The tool computes player auction values using a Standings Gain Points (SGP) model across 8 categories (HR, R, OBP, SLG / ERA, WHIP, HR9, SO). Projection input is BatX rest-of-season (RoS) projections. All 12 team rosters are loaded via CSV. The audit identified four concrete sources of error and one missing feature.

---

## Change 1 — Remove Double Regression on Y0

**File:** `shared.js`  
**Constants:** `REGRESS_PA`, `REGRESS_IP`

### Problem
The code applies Bayesian shrinkage to rate stats pulled from BatX:
```
regressed_OBP = (PA × raw_OBP + 200 × LG_MEAN.OBP) / (PA + 200)
```
BatX RoS projections already incorporate real stats-to-date and their own regression model. The code's second regression layer systematically deflates rate stats — most severely for part-timers, injured returners, and call-ups with low projected PA/IP.

### Fix
Set `REGRESS_PA = 0` and `REGRESS_IP = 0` for Y0 (current-year) projection parsing. This collapses the regression formula to a pass-through, trusting BatX's rates as-is.

Y1 and Y2 future-year projections retain their regression constants (unchanged), since those are full-season forecasts with more uncertainty than a projection system has already resolved.

---

## Change 2 — Update LG_MEAN to League Historical Means

**File:** `shared.js`  
**Constants:** `LG_MEAN` object

### Problem
`LG_MEAN` is currently hardcoded to MLB-wide averages:
```js
const LG_MEAN = { OBP: 0.318, SLG: 0.414, ERA: 4.25, WHIP: 1.28, HR9: 1.15 };
```
Ottoneu rosters are curated from the best available players — the average rostered player has meaningfully better rate stats than the average MLB player. Regressing Y1/Y2 projections toward MLB means pulls players toward a lower baseline than is realistic for this league.

### Fix
Compute mean team stats across two seasons of league history (from Ottoneu standings exports). Replace the five hardcoded constants with the computed values. Add a comment noting the source seasons so the constants are easy to update after each completed season.

**Required input:** Two seasons of league standings data (12 team-seasons × 2 years = 24 data points per category). Retrieve from Ottoneu standings exports.

---

## Change 3 — SGP-Derived Hitting/Pitching Dollar Split

**File:** `shared.js`  
**Constant:** `HIT_POOL_SHARE = 0.60`

### Problem
The 60/40 H/P dollar split is a universal rule-of-thumb, not calibrated to 4x4 scoring or this league. Because it applies a multiplicative rate to every player's value, even a few percentage points of error systematically over- or under-prices an entire side of the roster.

Using market salary data to calibrate is also incorrect — it would encode whatever biases exist in manager behavior (e.g., systematic underpayment for pitching) into the model.

### Fix
Remove the hardcoded constant. Compute the split dynamically from the SGP totals themselves each session:

```
HIT_POOL_SHARE = totalHitSGP / (totalHitSGP + totalPitSGP)
```

Where `totalHitSGP` and `totalPitSGP` are the sums of all positive player SGPs on the hitting and pitching sides respectively, computed across all rostered players on all 12 loaded team rosters. This anchors the split to the actual scoring opportunity available in the projections, not to market behavior or external assumptions. The split updates naturally as projections evolve throughout the season.

---

## Change 4 — RoS Proration in FA and Trade Tools

**Files:** `fa.html`, `trade.html`  
**New input:** Today's date (from `new Date()` in browser)

### Problem
Both tools display dollar values computed against the full $4,800 annual pool. A player acquired mid-season can only contribute for remaining games, so full-season values overstate what a player is actually worth to acquire today.

### Fix
Compute a proration factor from the current date:
```
remainingGames = 162 - gamesPlayedToDate
prorationFactor = remainingGames / 162
rosValue = projectedValue × prorationFactor
rosSurplus = rosValue - salary
```

Display both values in FA and trade tools — the existing full-season figure stays visible for apples-to-apples comparison (e.g., "is this a $30 player or a $15 player in the abstract"), and the new RoS figure shows what they're actually worth to acquire today.

**Dynasty value and dynasty surplus are never prorated.** Dynasty value spans Y0 + Y1 + Y2 where Y1 and Y2 are full future seasons — prorating Y0's contribution would incorrectly shrink the dynasty outlook based on current calendar position.

### Display columns added
| Tool | New column | Replaces |
|------|-----------|---------|
| `fa.html` | RoS Value, RoS Surplus | Nothing — added alongside existing |
| `trade.html` | RoS Value, RoS Surplus | Nothing — added alongside existing |

---

## What Is Not Changing

- **Replacement level depths** — confirmed correct for this league structure (12 teams, standard Ottoneu 4x4 roster slots)
- **Scoring categories** — HR, R, OBP, SLG / ERA, WHIP, HR9, SO confirmed correct for 4x4 format
- **Dynasty discount weights** — w1=0.90, w2=0.81 are already user-configurable; defaults are reasonable
- **SGP formula structure** — logic is sound; only the inputs and constants are changing
- **Roster analysis tool** — no proration applied; salaries are already committed, relative rankings are what matter

---

## Implementation Order

1. Remove Y0 regression (`REGRESS_PA = 0`, `REGRESS_IP = 0`)
2. Compute league historical means from standings data and update `LG_MEAN`
3. Replace `HIT_POOL_SHARE` with SGP-derived dynamic split
4. Add RoS proration columns to `fa.html` and `trade.html`

Changes 1–3 are all in `shared.js`. Change 4 touches the two tool pages. Each change is independent and can be verified in isolation.
