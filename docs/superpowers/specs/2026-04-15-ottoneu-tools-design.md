# Ottoneu 4x4 Fantasy Baseball Tool Suite — Design Spec
*Date: 2026-04-15*

## Overview

A suite of standalone, browser-based HTML tools for managing and analyzing an Ottoneu 4x4 fantasy baseball league. No server, no Python, no build step — runs from a local folder in any modern browser. Data is imported via CSV uploads and shared across tools via localStorage.

---

## League Context

- **Format**: Ottoneu 4x4 roto
- **Scoring categories**: OBP, SLG, HR, R (hitting) / ERA, WHIP, HR9, K (pitching)
- **Lower is better**: ERA, WHIP, HR9
- **Teams**: 12
- **Roster size**: 40 players; anyone can be active; 60-day IL grants a temporary extra roster spot
- **Salary cap**: $400 per team ($4,800 total league pool)
- **Roto scoring**: 12→1 points per category per team

---

## Architecture

### File Structure

```
OttoneuAI/
├── index.html          ← Data hub: import CSVs, IL designations, stored to localStorage
├── standings.html      ← Full league standings projector
├── roster.html         ← Your team: performance, categories, salary value
├── trade.html          ← Model trades, see standings impact
├── fa.html             ← Find free agents by category need
└── shared.js           ← All core logic: scoring, valuation, player matching
```

### Data Flow

1. User opens `index.html`, uploads CSVs and sets IL designations → data written to localStorage
2. All tool pages load `shared.js` and read from localStorage on open
3. No re-importing required between tools in the same session
4. To refresh data: re-upload updated CSVs on `index.html`

### localStorage Keys

| Key | Contents |
|-----|----------|
| `ottoneu_roster` | Full league roster: players, teams, salaries, positions |
| `ottoneu_proj_hitting` | Parsed FanGraphs hitting projections CSV |
| `ottoneu_proj_pitching` | Parsed FanGraphs pitching projections CSV |
| `ottoneu_stats_hitting` | Parsed FanGraphs current hitting stats CSV (optional) |
| `ottoneu_stats_pitching` | Parsed FanGraphs current pitching stats CSV (optional) |
| `ottoneu_my_team` | User's team name (set once on data hub) |
| `ottoneu_il` | Manual IL designations for user's team |

---

## Data Sources

| Source | Format | When to Update |
|--------|--------|----------------|
| Ottoneu league roster export | CSV | After transactions (drops/adds) |
| FanGraphs hitting projections | CSV | Start of season; re-download periodically |
| FanGraphs pitching projections | CSV | Start of season; re-download periodically |
| FanGraphs current hitting stats | CSV (optional) | Whenever you want in-season blending |
| FanGraphs current pitching stats | CSV (optional) | Whenever you want in-season blending |

**Notes:**
- The data hub shows which file is currently loaded and when it was uploaded, so swapping projection systems is obvious
- Only one projection system is supported at a time; to compare systems, re-upload a different CSV
- Position eligibility (C, 1B, OF, etc.) is sourced directly from the Ottoneu roster CSV — no derivation needed

### Free Agent Derivation

Free agents are not a separate upload. They are derived automatically:

> **Free agents = players present in the projection CSVs who are not assigned to any team in the roster CSV**

**Known limitation**: Newly called-up rookies without FanGraphs projections will not appear in the FA pool. This is an accepted trade-off.

### Minor League Players

If a rostered minor leaguer has FanGraphs projections, those projections are used. If no projections exist, the player contributes zero stats to the lineup optimizer.

---

## Shared Core (`shared.js`)

All logic shared across tools. Each HTML file loads this with a single `<script src="shared.js">` tag.

### Data Parsing

- Parse Ottoneu roster CSV → players with team, salary, position eligibility, FanGraphs ID
- Parse FanGraphs hitting/pitching projection CSVs → projected counting stats per player
- Parse FanGraphs hitting/pitching current stats CSVs → YTD stats, games played, IP
- Player matching: FanGraphs ID primary, normalized name fallback
- Ohtani split: separate bat (H) and arm (P) entries handled as distinct players

### Blended Stats Model

When current stats are loaded:
```
blended_stat = (actual_stat * games_played + projected_stat * (162 - games_played)) / 162
```
Falls back to pure projections if no current stats are uploaded. All tools call a single `getBlendedStats(player)` function — blending logic is not duplicated anywhere.

### IL Pro-Rating

Manual IL designations apply to the user's team only. When a player is designated IL, their stats are scaled before entering the lineup optimizer:

| IL Type | Assumed missed games | Stat multiplier |
|---------|---------------------|-----------------|
| 15-day IL | 20 games | (162 − 20) / 162 ≈ 88% |
| 60-day IL | 80 games | (162 − 80) / 162 ≈ 51% |

When current stats are loaded, only projected remaining games are scaled (actual games already played are locked in).

### Lineup Optimizer

Assigns players to lineup slots and computes team category totals. Each player fills exactly one slot.

**Slot definitions:**

| Slot | Eligibility | Game cap |
|------|-------------|----------|
| C | Catcher eligible | 162G |
| 1B | 1B eligible | 162G |
| 2B | 2B eligible | 162G |
| SS | SS eligible | 162G |
| 3B | 3B eligible | 162G |
| MI | 2B or SS eligible | 162G |
| OF (5 slots) | OF eligible | 810G total |
| UTIL | Any hitter | 162G |

**Assignment approach — value maximization:**
The optimizer finds the assignment of players to slots that maximizes total team value, rather than filling slots in a fixed priority order. This correctly handles dual-position players: a player eligible at 2B and OF will be assigned wherever they produce the most net value for the team, not simply to whichever slot comes first.

For a 40-man roster filling ~12 slots, the solution space is small enough to evaluate exhaustively in the browser with no performance concern.

**Slot priority order** is used only as a tiebreaker when two assignments produce equal total value: C → 1B → 2B → SS → 3B → MI → OF → UTIL. Each player fills exactly one slot.

**Pitching pool:**
- Rank pitchers by calculated value (highest first)
- Fill until 1500 IP cap is reached; remaining pitchers are excluded
- If projected total IP < 1250: team scores **0 points** in all 4 pitching categories
- IP minimum/maximum applies to the pool total, not individual pitchers

> **IMPORTANT — Pre-implementation gate**: Walk through exact slot rules, position eligibility edge cases (e.g., players eligible at multiple positions, Ohtani bat/arm split), and the value ranking used to select within slots with the user before implementing.

### Scoring Engine

- Computes 8-category totals from a set of players
- Ranks all 12 teams 12→1 per category (reversed for ERA, WHIP, HR9)
- Sums category ranks to total roto points
- `buildStandings(teamsWithStats)` returns full ranked standings

### Valuation Model

Calculates each player's dollar value using position-specific replacement level and standings gain points (SGP). Recalculated fresh every time from the current projected/blended standings, so values stay calibrated to the league's actual competitive state.

**Step 1 — Project all 12 teams**
Run the lineup optimizer for all 12 teams to get projected category totals.

**Step 2 — Calculate SGP denominators (one per category)**
For each of the 8 categories, compute the average gap between adjacent teams in the projected standings. This gap = 1 standings point. It represents how many stat units it takes to move up one spot in that category.

```
SGP_denominator[category] = stdev(all 12 teams' projected totals in that category)
```

For LOWER_BETTER categories (ERA, WHIP, HR9), a lower stat is better — value is calculated inversely.

**Step 3 — Calculate each player's SGP contribution**
For each player, divide their projected contribution to each category by that category's SGP denominator. Sum across all 8 categories:

```
player_sgp = Σ (player_category_contribution / SGP_denominator[category])
```

For LOWER_BETTER categories: contribution = replacement_level_stat − player_stat (positive = better than replacement).

**Step 4 — Subtract position-specific replacement level**
Replacement level = the best projected player at each position who did not earn a starting lineup slot across all 12 teams (e.g., the 13th-best catcher leaguewide). Subtract that player's SGP from each starter's SGP. Players at or below replacement = $0 value.

**Step 5 — Convert SGP to dollars**
```
total_sgp = sum of all starters' SGP above replacement
player_value = (player_sgp_above_replacement / total_sgp) × $4,800
```

**Output per player**: `{ projectedValue, actualSalary, surplus }`
Surplus = projectedValue − actualSalary. Positive = bargain, negative = overpaid.

### localStorage Interface

- `saveData(key, value)` — serializes and stores
- `loadData(key)` — retrieves and deserializes; returns null if not found

---

## Tools

### Data Hub (`index.html`)

**Purpose**: Single entry point for all data imports and IL management.

**CSV upload slots** (each shows filename + upload timestamp when loaded):
- Ottoneu roster
- FanGraphs hitting projections
- FanGraphs pitching projections
- FanGraphs current hitting stats *(optional)*
- FanGraphs current pitching stats *(optional)*

**IL management** (user's team only):
- Search and add players by name
- Select IL type: 15-day or 60-day
- Remove players from IL list
- Applied automatically to all tools via localStorage

**Other controls:**
- Dropdown to select "my team" from teams detected in roster CSV
- "Clear all data" button

---

### Standings (`standings.html`)

**Purpose**: Project full league standings across all 8 categories.

**UI**:
- Rankings table: teams × categories, with roto points per category and total points
- User's team highlighted
- Toggle: projections only vs. blended (shown only if current stats are loaded)

**Carries over** logic from existing OttoneuProjector tool.

---

### Roster Analysis (`roster.html`)

**Purpose**: Deep look at the user's team across three dimensions.

**Panel 1 — Performance Tracker**
- Player-by-player: projected stats vs. blended actual stats
- Flagged as overperforming / on-track / underperforming
- Sorted by deviation from projection

**Panel 2 — Category Dashboard**
- User's team rank (out of 12) in each of the 8 categories
- Signal: strong (top 4) / borderline (5–8) / weak (9–12)
- Identifies which categories to target in trades or FA adds

**Panel 3 — Salary & Value**
- Each player: calculated value vs. actual salary vs. surplus
- Sorted by surplus (best bargains at top, worst overpays at bottom)
- Surfaces: untouchables (high surplus), trade candidates (low surplus), cut candidates (large negative surplus)

---

### Trade Evaluator (`trade.html`)

**Purpose**: Model a proposed trade and see the standings impact for both teams.

**UI**:
- Two columns: "You give" and "You receive" (searchable player pickers)
- Trade partner selector
- "Evaluate" button

**Output**:
- Before/after roto points for your team and trade partner
- Before/after rank in each of the 8 categories for both teams
- Net summary: categories you gain, categories you lose, net points delta
- **Disclaimer shown in output**: *"Standings impact is approximate — other teams' category ranks are not recalculated."*

---

### FA Finder (`fa.html`)

**Purpose**: Identify the best available free agents based on your team's category needs.

**UI**:
- Filter by position
- Sort by: overall value, or specific category contribution
- Your category weakness summary shown at top (from Roster Analysis logic)

**Output per FA**:
- Name, positions
- Projected stats in each category
- Calculated value and estimated salary range (derived from comparable rostered players' salary/value ratios)
- Which of your weak categories they help

**Free agent pool**: Players in projection CSVs not assigned to any team in roster CSV.

---

## Known Limitations

| Limitation | Impact |
|------------|--------|
| Rookie callups without FanGraphs projections won't appear in FA pool | Minor; these players rarely have meaningful projection data |
| IL tracking is manual and for user's team only | Other teams' IL players may cause standings projections to be slightly optimistic for those teams |
| Trade evaluator does not re-rank all 12 teams | Standings point changes are approximations; noted explicitly in trade output |
| One projection system at a time | Swap CSVs on data hub to compare systems |

---

## Pre-Implementation Gates

Before writing any code, the following must be resolved in conversation:

1. **Lineup optimizer edge cases** — walk through position eligibility details, slot priority tiebreakers, and Ohtani handling with the user
2. **FanGraphs CSV column names** — verify exact column headers for hitting/pitching projections and current stats exports
3. **Ottoneu roster CSV format** — verify column names for salary, team, position eligibility, and FanGraphs ID
