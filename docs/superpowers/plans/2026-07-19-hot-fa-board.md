# Hot FA Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Hot FAs" scouting page showing every player's raw last-7/15/30-day production in this league's 4×4 categories, ranked by a HotScore composite, with a breakout-vs-projection badge.

**Architecture:** A daily Apps Script (`scripts/hotstats.gs`) snapshots MLB StatsAPI `byDateRange` stats into `data/hot.json`. Pure logic lives in a new `hotboard.js` (thresholds, HotScore, role classification, breakout badge) so it's unit-testable in `test.html`. `hot.html` renders it, cross-referencing `roster.csv` (FA vs rostered) and projection CSVs (badge).

**Tech stack:** Vanilla browser JS (no build), Google Apps Script, MLB StatsAPI. Tests run in `test.html` via `assert()`/`assertEqual()`, verified by opening the page under `python -m http.server` and confirming all assertions pass (green).

**Note on commits:** All commit steps are **local only** — never `git push`. The user pushes via GitHub Desktop.

---

### Task 1: `hotboard.js` — thresholds + role classification

**Files:**
- Create: `hotboard.js`
- Modify: `test.html` (add `<script src="hotboard.js"></script>` after the shared.js tag, and a test block)

- [ ] **Step 1: Create `hotboard.js` with the config + first two functions**

```js
/* hotboard.js — pure logic for the Hot FA Board.
 * Depends on normalizeName() from shared.js (load shared.js first).
 * All thresholds here are the tunable knobs from the design spec. */

// Sample gates: minimum workload to appear in the default (non-marginal) view.
var HOT_MIN_PA = { 7: 12, 15: 25, 30: 45 };   // hitters, by window
var HOT_MIN_GS = { 7: 1,  15: 2,  30: 3  };   // starters: starts
var HOT_MIN_G  = { 7: 3,  15: 5,  30: 8  };   // relievers: appearances

// role = SP if starts are at least half of appearances (and he started at least once).
function hotClassifyRole(g, gs) {
  g = g || 0; gs = gs || 0;
  return (gs > 0 && gs * 2 >= g) ? 'SP' : 'RP';
}

// kind: 'H' (hitter), 'SP', or 'RP'. window: 7|15|30. line: a per-window stat object.
function hotMeetsThreshold(kind, window, line) {
  if (!line) return false;
  if (kind === 'H')  return (line.pa || 0) >= (HOT_MIN_PA[window] || 0);
  if (kind === 'SP') return (line.gs || 0) >= (HOT_MIN_GS[window] || 0);
  if (kind === 'RP') return (line.g  || 0) >= (HOT_MIN_G[window]  || 0);
  return false;
}
```

- [ ] **Step 2: Wire `hotboard.js` into `test.html` and add the failing tests**

In `test.html`, add `<script src="hotboard.js"></script>` immediately after `<script src="shared.js"></script>`. Then add this block inside the test `<script>` (near the end, before the summary line):

```js
    // ── hotboard: role + thresholds ──────────────────────────────────────────
    assertEqual(hotClassifyRole(4, 4), 'SP', 'hotClassifyRole: all starts → SP');
    assertEqual(hotClassifyRole(5, 2), 'RP', 'hotClassifyRole: mostly relief → RP');
    assertEqual(hotClassifyRole(4, 2), 'SP', 'hotClassifyRole: half starts → SP');
    assertEqual(hotClassifyRole(6, 0), 'RP', 'hotClassifyRole: no starts → RP');
    assert(hotMeetsThreshold('H', 15, { pa: 25 }), 'hotMeetsThreshold: hitter at PA gate passes');
    assert(!hotMeetsThreshold('H', 15, { pa: 24 }), 'hotMeetsThreshold: hitter under PA gate fails');
    assert(hotMeetsThreshold('SP', 7, { gs: 1 }), 'hotMeetsThreshold: SP at start gate passes');
    assert(!hotMeetsThreshold('RP', 30, { g: 7 }), 'hotMeetsThreshold: RP under appearance gate fails');
    assert(!hotMeetsThreshold('H', 15, null), 'hotMeetsThreshold: null line fails');
```

- [ ] **Step 3: Verify tests pass**

Run `python -m http.server` in the repo root, open `http://localhost:8000/test.html`, hard-refresh. Expected: all assertions green, including the 9 new ones; total count increased by 9.

- [ ] **Step 4: Commit (local only)**

```bash
git add hotboard.js test.html
git commit -m "feat(hot): hotboard thresholds + role classification"
```

---

### Task 2: `hotboard.js` — HotScore composite

**Files:**
- Modify: `hotboard.js`
- Modify: `test.html`

- [ ] **Step 1: Add the pool-stats + score functions to `hotboard.js`**

```js
// Which categories drive HotScore, and direction (+1 higher-better, -1 lower-better).
var HOT_CATS = {
  H: [{ k: 'obp', d: 1 }, { k: 'slg', d: 1 }, { k: 'hr', d: 1 }, { k: 'r', d: 1 }],
  P: [{ k: 'so', d: 1 }, { k: 'hr9', d: -1 }, { k: 'era', d: -1 }, { k: 'whip', d: -1 }]
};

// mean + stdev per category across a pool of stat lines. std guarded to >=... (never 0).
function hotPoolStats(lines, keys) {
  var stats = {};
  keys.forEach(function (c) {
    var vals = lines.map(function (l) { return +l[c] || 0; });
    var n = vals.length || 1;
    var mean = vals.reduce(function (a, b) { return a + b; }, 0) / n;
    var variance = vals.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / n;
    stats[c] = { mean: mean, std: Math.sqrt(variance) || 1 };
  });
  return stats;
}

// kind: 'H' for hitters, 'P' for pitchers (SP and RP each get their OWN pool passed in).
function hotScoreFor(line, poolStats, kind) {
  var cats = HOT_CATS[kind === 'H' ? 'H' : 'P'];
  var score = 0;
  cats.forEach(function (c) {
    var s = poolStats[c.k];
    if (!s) return;
    score += c.d * (((+line[c.k] || 0) - s.mean) / s.std);
  });
  return score;
}
```

- [ ] **Step 2: Add failing tests to `test.html`**

Add after the Task 1 block:

```js
    // ── hotboard: HotScore ───────────────────────────────────────────────────
    var hpool = [
      { obp: 0.330, slg: 0.430, hr: 4, r: 11 },
      { obp: 0.290, slg: 0.370, hr: 2, r: 7 },
      { obp: 0.370, slg: 0.490, hr: 6, r: 15 }
    ];
    var hstats = hotPoolStats(hpool, ['obp', 'slg', 'hr', 'r']);
    assert(Math.abs(hstats.obp.mean - 0.330) < 1e-9, 'hotPoolStats: mean OBP');
    // Hot line should score well above an average line.
    var hot = hotScoreFor({ obp: 0.400, slg: 0.620, hr: 7, r: 15 }, hstats, 'H');
    var avg = hotScoreFor({ obp: 0.330, slg: 0.430, hr: 4, r: 11 }, hstats, 'H');
    assert(hot > avg, 'hotScoreFor: hot hitter beats average hitter');
    assert(Math.abs(avg) < 0.5, 'hotScoreFor: average-ish line near zero');
    // Pitcher direction: lower ERA/WHIP/HR9 is better.
    var ppool = [
      { so: 20, hr9: 1.0, era: 3.50, whip: 1.10 },
      { so: 10, hr9: 1.5, era: 5.00, whip: 1.40 }
    ];
    var pstats = hotPoolStats(ppool, ['so', 'hr9', 'era', 'whip']);
    var goodP = hotScoreFor({ so: 20, hr9: 1.0, era: 3.50, whip: 1.10 }, pstats, 'P');
    var badP  = hotScoreFor({ so: 10, hr9: 1.5, era: 5.00, whip: 1.40 }, pstats, 'P');
    assert(goodP > badP, 'hotScoreFor: strong pitcher beats weak pitcher');
    // Zero-variance category must not divide by zero.
    var flat = hotPoolStats([{ hr: 3 }, { hr: 3 }], ['hr']);
    assert(isFinite(hotScoreFor({ hr: 3 }, flat, 'H')), 'hotScoreFor: no NaN on flat category');
```

- [ ] **Step 3: Verify tests pass**

Reload `test.html`. Expected: all green, +6 assertions.

- [ ] **Step 4: Commit (local only)**

```bash
git add hotboard.js test.html
git commit -m "feat(hot): HotScore z-score composite"
```

---

### Task 3: `hotboard.js` — breakout badge + FA matching

**Files:**
- Modify: `hotboard.js`
- Modify: `test.html`

- [ ] **Step 1: Add the functions to `hotboard.js`**

```js
var HOT_BREAKOUT_OPS  = 0.075;  // hitter recent OPS over projected OPS
var HOT_BREAKOUT_KPCT = 0.03;   // pitcher recent K% over projected K% (+3 pts)

// kind: 'H' or 'P'. recent = per-window line; proj = projection line (may be null).
function hotBreakoutBadge(kind, recent, proj) {
  if (!recent || !proj) return false;
  if (kind === 'H') {
    var recOps  = (+recent.obp || 0) + (+recent.slg || 0);
    var projOps = (+proj.obp  || 0) + (+proj.slg  || 0);
    return (recOps - projOps) >= HOT_BREAKOUT_OPS;
  }
  var eraWhipBetter = (+recent.era || 99) < (+proj.era || 0) &&
                      (+recent.whip || 99) < (+proj.whip || 0);
  var recKpct  = recent.bf ? (+recent.so || 0) / recent.bf : 0;
  var projKpct = (proj.kpct != null) ? +proj.kpct : 0;   // 0 if projection has no K%
  var kBetter  = projKpct > 0 && recKpct >= projKpct + HOT_BREAKOUT_KPCT;
  return eraWhipBetter || kBetter;
}

// Build a lookup of rostered players from parsed roster rows: normalized name -> true.
function hotRosteredSet(rosterRows) {
  var set = {};
  (rosterRows || []).forEach(function (p) {
    if (p && p.name) set[normalizeName(p.name)] = true;
  });
  return set;
}

// A StatsAPI player is a free agent if his normalized name is not in the rostered set.
function hotIsFreeAgent(name, rosteredSet) {
  return !rosteredSet[normalizeName(name || '')];
}
```

- [ ] **Step 2: Add failing tests to `test.html`**

```js
    // ── hotboard: breakout + FA matching ─────────────────────────────────────
    assert(hotBreakoutBadge('H', { obp: 0.400, slg: 0.560 }, { obp: 0.340, slg: 0.470 }),
      'hotBreakoutBadge: hitter well over proj → true');
    assert(!hotBreakoutBadge('H', { obp: 0.330, slg: 0.440 }, { obp: 0.340, slg: 0.470 }),
      'hotBreakoutBadge: hitter under proj → false');
    assert(!hotBreakoutBadge('H', { obp: 0.400, slg: 0.560 }, null),
      'hotBreakoutBadge: no projection → false');
    assert(hotBreakoutBadge('P', { era: 2.10, whip: 0.90 }, { era: 3.80, whip: 1.25 }),
      'hotBreakoutBadge: pitcher ERA+WHIP both better → true');
    assert(!hotBreakoutBadge('P', { era: 2.10, whip: 1.40 }, { era: 3.80, whip: 1.25 }),
      'hotBreakoutBadge: pitcher WHIP worse → false (ERA-only not enough)');
    var rset = hotRosteredSet([{ name: 'Aaron Judge' }, { name: 'José Ramírez' }]);
    assert(!hotIsFreeAgent('Aaron Judge', rset), 'hotIsFreeAgent: rostered → false');
    assert(hotIsFreeAgent('Some Prospect', rset), 'hotIsFreeAgent: unrostered → true');
    assert(!hotIsFreeAgent('Jose Ramirez', rset), 'hotIsFreeAgent: accent-insensitive match');
```

- [ ] **Step 3: Verify tests pass**

Reload `test.html`. Expected: all green, +8 assertions.

- [ ] **Step 4: Commit (local only)**

```bash
git add hotboard.js test.html
git commit -m "feat(hot): breakout badge + FA matching"
```

---

### Task 4: `scripts/hotstats.gs` — daily data pipeline

**Files:**
- Create: `scripts/hotstats.gs`

This runs in Apps Script, not the browser — no unit test. Verify via `Logger.log`.

- [ ] **Step 1: SPIKE — confirm the StatsAPI query returns all players**

Create `scripts/hotstats.gs` with just a probe and run it in Apps Script:

```js
function hotSpike_() {
  var url = 'https://statsapi.mlb.com/api/v1/stats?stats=byDateRange&group=hitting' +
            '&startDate=2026-07-05&endDate=2026-07-19&sportId=1&gameType=R&limit=50&offset=0';
  var r = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  var j = JSON.parse(r.getContentText());
  var splits = (j.stats && j.stats[0] && j.stats[0].splits) || [];
  var p0 = splits[0] && splits[0].player;
  Logger.log('code=' + r.getResponseCode() + ' splits=' + splits.length +
             ' first=' + (p0 && p0.fullName) +
             ' pos=' + (p0 && p0.primaryPosition && p0.primaryPosition.abbreviation));
}
```

Expected: `code=200`, `splits=50` (i.e. `limit` caps it → pagination needed). If splits are per-player with `player.fullName` and a `stat` object, proceed. Also note whether `pos=` is populated — it feeds the hitter position filter. **If position is absent**, store `pos: ''` and the position pills degrade to "All only" (documented approximation). **If the response is empty or not per-player**, switch to iterating `teams/{id}/stats?stats=byDateRange` per team (30 teams) — note this in the file and continue.

- [ ] **Step 2: Implement the full pipeline**

Replace the file with the generator. It reuses `pushFile` + `GITHUB_TOKEN` from the shared Apps Script project.

```js
/* hotstats.gs — Hot FA Board data pipeline. Paste into the SAME Apps Script
 * project as briefing.gs / updateProjections. Reuses pushFile + GITHUB_TOKEN.
 * Writes data/hot.json daily (add a time trigger on hotStats). */

var HOT_WINDOWS = [7, 15, 30];
var HOT_TZ = 'America/New_York';

function hotStats()     { hotRun_(false); }
function hotStatsTest() { hotRun_(true); }

function hotRun_(isTest) {
  var tz = HOT_TZ, now = new Date();
  var end = Utilities.formatDate(new Date(now.getTime() - 24 * 3600 * 1000), tz, 'yyyy-MM-dd'); // yesterday
  var ranges = {}, hitMap = {}, pitMap = {};

  HOT_WINDOWS.forEach(function (w) {
    var start = Utilities.formatDate(new Date(now.getTime() - w * 24 * 3600 * 1000), tz, 'yyyy-MM-dd');
    ranges[w] = { start: start, end: end };
    hotFetch_('hitting', start, end).forEach(function (s) { hotAddHit_(hitMap, w, s); });
    hotFetch_('pitching', start, end).forEach(function (s) { hotAddPit_(pitMap, w, s); });
  });

  var obj = {
    generatedAt: now.toISOString(),
    ranges: ranges,
    hitters:  Object.keys(hitMap).map(function (k) { return hitMap[k]; }),
    pitchers: Object.keys(pitMap).map(function (k) { return pitMap[k]; })
  };
  if (isTest) { Logger.log('hitters=' + obj.hitters.length + ' pitchers=' + obj.pitchers.length); return; }

  var token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) { Logger.log('No GITHUB_TOKEN — cannot push.'); return; }
  pushFile(token, 'data/hot.json', JSON.stringify(obj), 'Hot stats ' + end);
  Logger.log('Hot stats pushed for ' + end);
}

// Paginated pull of byDateRange for one group. Returns array of split objects.
function hotFetch_(group, start, end) {
  var out = [], offset = 0, page = 250;
  for (var guard = 0; guard < 20; guard++) {
    var url = 'https://statsapi.mlb.com/api/v1/stats?stats=byDateRange&group=' + group +
              '&startDate=' + start + '&endDate=' + end + '&sportId=1&gameType=R' +
              '&limit=' + page + '&offset=' + offset;
    var r = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (r.getResponseCode() !== 200) break;
    var splits = (JSON.parse(r.getContentText()).stats[0] || {}).splits || [];
    out = out.concat(splits);
    if (splits.length < page) break;
    offset += page;
  }
  return out;
}

function hotKey_(s) {
  return (s.player && s.player.id) || (s.player && s.player.fullName) || Math.random();
}
function hotTeam_(s) { return (s.team && s.team.abbreviation) || ''; }
function hotNum_(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
function hotRound_(v, d) { var p = Math.pow(10, d); return Math.round(hotNum_(v) * p) / p; }

function hotAddHit_(map, w, s) {
  var id = hotKey_(s), st = s.stat || {};
  var pos = (s.player && s.player.primaryPosition && s.player.primaryPosition.abbreviation) || '';
  var rec = map[id] || (map[id] = { id: (s.player && s.player.id) || null,
    name: (s.player && s.player.fullName) || '', team: hotTeam_(s), pos: pos, w: {} });
  rec.w[w] = {
    pa:  hotNum_(st.plateAppearances),
    hr:  hotNum_(st.homeRuns),
    r:   hotNum_(st.runs),
    obp: hotRound_(st.obp, 3),
    slg: hotRound_(st.slg, 3)
  };
}

function hotAddPit_(map, w, s) {
  var id = hotKey_(s), st = s.stat || {};
  var ip = hotNum_(st.inningsPitched);
  var g = hotNum_(st.gamesPlayed) || hotNum_(st.gamesPitched);
  var gs = hotNum_(st.gamesStarted);
  var hr = hotNum_(st.homeRuns);
  var rec = map[id] || (map[id] = { id: (s.player && s.player.id) || null,
    name: (s.player && s.player.fullName) || '', team: hotTeam_(s), w: {} });
  rec.w[w] = {
    g: g, gs: gs, ip: hotRound_(ip, 1),
    so: hotNum_(st.strikeOuts),
    era: hotRound_(st.era, 2),
    whip: hotRound_(st.whip, 2),
    hr9: ip > 0 ? hotRound_(hr * 9 / ip, 2) : 0,
    bf: hotNum_(st.battersFaced),
    role: (gs > 0 && gs * 2 >= g) ? 'SP' : 'RP'
  };
}
```

- [ ] **Step 3: Verify in Apps Script**

Run `hotStatsTest()`. Expected log: `hitters=NNN pitchers=NNN` with NNN in the hundreds. Then run `hotStats()` once and confirm `data/hot.json` appears in the repo with the shape from the spec. Add a daily time trigger (~8am ET) on `hotStats`.

- [ ] **Step 4: Commit (local only)**

```bash
git add scripts/hotstats.gs
git commit -m "feat(hot): daily byDateRange pipeline -> data/hot.json"
```

---

### Task 5: `hot.html` — the page

**Files:**
- Create: `hot.html`

- [ ] **Step 1: Create `hot.html`**

Model structure/styles on `fa.html` (nav block, `.filter-bar`, `.pos-btn`, tables). The page loads `shared.js` + `hotboard.js`, fetches `data/hot.json`, loads `roster.csv` (via the suite's existing `autoLoadFromRepo`/`parseRosterCSV`) and the projection CSVs, then:

1. Reads the selected window (default 15) and the "Free agents only" toggle (default on).
2. Builds `hotRosteredSet` from roster rows; tags each player FA/rostered via `hotIsFreeAgent`.
3. Splits into three pools for the window: hitters, SP (`w[win].role==='SP'`), RP (`role==='RP'`).
4. For each pool: filter by `hotMeetsThreshold` (unless "Show marginal" is on), compute `hotPoolStats` over the qualified pool, assign `hotScoreFor`, match to projection by `normalizeName` and set the badge via `hotBreakoutBadge` — pass the projection row's **`.proj` sub-object** (e.g. `parseHittingProjections()` returns `{name, type, proj:{obp,slg,hr,r,...}}`, so the badge gets `.proj`, not the whole row).
5. Renders three tables (Hitters, SP, RP), default-sorted by HotScore desc, all columns click-to-sort, using `textContent` only (never `innerHTML` with fetched data — match `briefing.html`'s XSS discipline).
6. Controls: window toggle, FA-only toggle, position pills (hitters), "Show marginal" toggle, name search — each re-renders from the already-fetched data (no refetch).

Reuse existing helpers from `shared.js` where present (`normalizeName`, `parseRosterCSV`, `parseHittingProjections`, `parsePitchingProjections`, `autoLoadFromRepo`). Do not duplicate CSV parsing.

- [ ] **Step 2: Verify in the browser**

With `python -m http.server` running, open `http://localhost:8000/hot.html`, hard-refresh. Confirm via preview tools:
- No console errors (`preview_console_logs` level error).
- Three tables render; default window 15; FA-only on by default.
- Toggling the window re-sorts without refetch; toggling FA-only reveals rostered players tagged with a chip; "Show marginal" adds below-threshold players.
- Clicking a column header re-sorts; the 🔥 badge appears on at least some players.
- `preview_screenshot` for a final visual check.

- [ ] **Step 3: Commit (local only)**

```bash
git add hot.html
git commit -m "feat(hot): Hot FA Board page"
```

---

### Task 6: Nav links across the suite

**Files:**
- Modify: `index.html`, `standings.html`, `roster.html`, `trade.html`, `fa.html`, `bid.html`, `briefing.html`, `prospects.html`, `targets.html` (the shared `<nav class="nav">` block in each)

- [ ] **Step 1: Add the nav link**

In each page's `<nav class="nav">`, add `<a href="hot.html">Hot FAs</a>` in a consistent position (e.g., right after the FA Finder link). In `hot.html` itself, give that link `class="active"`.

- [ ] **Step 2: Verify**

Reload two or three pages in the preview; confirm the "Hot FAs" link appears and navigates to `hot.html`, and that `hot.html`'s own nav shows it as active.

- [ ] **Step 3: Commit (local only)**

```bash
git add index.html standings.html roster.html trade.html fa.html bid.html briefing.html prospects.html targets.html
git commit -m "feat(hot): add Hot FAs to suite nav"
```

---

## Out of scope (Phase 2 — separate plan)

- `fa.html` "L15 form" column reading `hot.json`.
- Briefing "Hot on the wire" card (top FA hitter/SP/RP by 15-day HotScore).

## Definition of done

- `test.html` all green, +23 new assertions (Tasks 1–3).
- `data/hot.json` generated and pushed by `hotStats` on a daily trigger.
- `hot.html` renders three ranked tables with working window/FA/marginal/position/search controls and the breakout badge, no console errors.
- "Hot FAs" nav link on every page.
