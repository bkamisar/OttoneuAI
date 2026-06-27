# Ottoneu Tool Suite — Plan A: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `shared.js` (all core logic), `index.html` (data hub), and `standings.html` (standings projector) — producing a fully working standings tool and the foundation every other tool builds on.

**Architecture:** All shared logic lives in `shared.js` (loaded via `<script src="shared.js">` by every tool). Data enters through `index.html` and is stored in `localStorage`. `standings.html` reads from `localStorage` and renders the league standings using the scoring engine. A `test.html` file runs the shared.js logic in the browser for verification.

**Tech Stack:** Vanilla JS (ES5/ES6, no modules), HTML/CSS, no build tools, no external libraries. localStorage as the data bus. Runs from local filesystem (file:// protocol).

**Security note:** All user-supplied strings (player names, team names) must be escaped with `esc()` before inserting into HTML via innerHTML. `esc()` is defined in shared.js and used throughout every tool.

---

## ⚠️ Pre-Flight: Verify CSV Column Names

**Do this before writing any parser code.** Open each CSV in a text editor and record the exact first-row headers. Then update the `*_COLS` constant objects in Tasks 3–5 to match.

Files to check:
1. **Ottoneu roster CSV** — download from your Ottoneu league page
2. **FanGraphs hitting projections CSV** — from FanGraphs projections page
3. **FanGraphs pitching projections CSV** — same source, pitching tab
4. **FanGraphs current hitting stats CSV** — from FanGraphs leaderboards (batting)
5. **FanGraphs current pitching stats CSV** — from FanGraphs leaderboards (pitching)

The column name constants in Tasks 3–5 use best-guess names. **Update them to match your actual CSVs before running.**

---

## File Map

| File | Role |
|------|------|
| `shared.js` | All core logic: parsing, blending, lineup optimizer, scoring, valuation |
| `index.html` | Data hub: CSV uploads, IL management, team selector |
| `standings.html` | Full league standings projector |
| `test.html` | Browser-based test runner for shared.js |

---

## Task 1: Project Scaffold

**Files:**
- Create: `shared.js`
- Create: `test.html`

- [ ] **Step 1: Initialize git**

```bash
cd "C:/Users/bkami/Documents/OttoneuAI"
git init
```

- [ ] **Step 2: Create `shared.js` skeleton**

```javascript
// shared.js — Ottoneu 4x4 Tool Suite core logic
// Load via <script src="shared.js"> in every tool page.

// ── CONSTANTS ────────────────────────────────────────────────────────────────
const CATS         = ["OBP","SLG","HR","R","ERA","WHIP","HR9","SO"];
const LOWER_BETTER = new Set(["ERA","WHIP","HR9"]);
const NUM_TEAMS    = 12;
const SALARY_POOL  = 4800;    // $400 × 12 teams
const OF_GAME_CAP  = 810;     // 5 OF × 162 games
const SLOT_CAP     = 162;
const IP_MAX       = 1500;
const IP_MIN       = 1250;
const IL_15_MISS   = 20;      // assumed games missed on 15-day IL
const IL_60_MISS   = 80;      // assumed games missed on 60-day IL

// ── SECURITY HELPER ──────────────────────────────────────────────────────────
// Escape user-supplied strings before inserting into innerHTML.
function esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── PLACEHOLDER SECTIONS (filled in subsequent tasks) ───────────────────────
// localStorage  → Task 2
// CSV parsing   → Task 2
// Roster parser → Task 3
// Proj parsers  → Task 4
// Stats parsers → Task 5
// Player match  → Task 5
// Blended stats → Task 6
// IL pro-rating → Task 6
// Lineup optim  → Task 7
// Scoring engine→ Task 8
// Valuation     → Task 9
```

- [ ] **Step 3: Create `test.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Ottoneu Shared.js Tests</title>
  <style>
    body { font-family: monospace; padding: 20px; background: #1a1a1a; color: #ccc; }
    .pass { color: #4caf50; }
    .fail { color: #f44336; font-weight: bold; }
    .section { margin-top: 20px; color: #90caf9; font-size: 1.1em; }
    #summary { margin-top: 20px; font-size: 1.2em; }
  </style>
</head>
<body>
  <h2>shared.js Test Suite</h2>
  <div id="output"></div>
  <div id="summary"></div>
  <script src="shared.js"></script>
  <script>
    let passed = 0, failed = 0;
    const out = document.getElementById('output');

    function section(name) {
      const d = document.createElement('div');
      d.className = 'section';
      d.textContent = '── ' + name + ' ──';
      out.appendChild(d);
    }

    function assert(condition, name, detail) {
      const d = document.createElement('div');
      if (condition) {
        passed++;
        d.className = 'pass';
        d.textContent = '✓ ' + name;
      } else {
        failed++;
        d.className = 'fail';
        d.textContent = '✗ ' + name + (detail ? ': ' + detail : '');
      }
      out.appendChild(d);
    }

    function assertEqual(actual, expected, name) {
      const ok = JSON.stringify(actual) === JSON.stringify(expected);
      assert(ok, name, ok ? '' : 'got ' + JSON.stringify(actual) + ', want ' + JSON.stringify(expected));
    }

    // ── Tests ────────────────────────────────────────────────────────────────
    section('Scaffold');
    assert(typeof CATS !== 'undefined', 'CATS constant defined');
    assert(CATS.length === 8, 'CATS has 8 categories');
    assert(LOWER_BETTER.has('ERA'), 'ERA is lower-better');
    assert(!LOWER_BETTER.has('HR'), 'HR is not lower-better');

    section('esc()');
    assertEqual(esc('<script>'), '&lt;script&gt;', 'esc: escapes angle brackets');
    assertEqual(esc('"hello"'), '&quot;hello&quot;', 'esc: escapes quotes');
    assertEqual(esc(null), '', 'esc: handles null');

    // ── Summary ──────────────────────────────────────────────────────────────
    const sumEl = document.getElementById('summary');
    sumEl.textContent = passed + ' passed, ' + failed + ' failed';
    sumEl.style.color = failed === 0 ? '#4caf50' : '#f44336';
  </script>
</body>
</html>
```

- [ ] **Step 4: Open `test.html` in browser and confirm 7 tests pass**

Open `test.html` from the file system (drag into Chrome/Firefox or File → Open). Expected: "7 passed, 0 failed".

- [ ] **Step 5: Commit**

```bash
git add shared.js test.html
git commit -m "feat: project scaffold with constants, esc() helper, and test runner"
```

---

## Task 2: localStorage Interface + CSV Parser

**Files:**
- Modify: `shared.js`
- Modify: `test.html`

- [ ] **Step 1: Add localStorage interface to `shared.js`** (replace `// localStorage → Task 2`)

```javascript
// ── LOCAL STORAGE ────────────────────────────────────────────────────────────
function saveData(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function loadData(key) {
  const raw = localStorage.getItem(key);
  return raw ? JSON.parse(raw) : null;
}

function clearAllData() {
  [
    'ottoneu_roster', 'ottoneu_proj_hitting', 'ottoneu_proj_pitching',
    'ottoneu_stats_hitting', 'ottoneu_stats_pitching',
    'ottoneu_my_team', 'ottoneu_il'
  ].forEach(k => localStorage.removeItem(k));
}
```

- [ ] **Step 2: Add CSV parser to `shared.js`** (replace `// CSV parsing → Task 2`)

```javascript
// ── CSV PARSING ──────────────────────────────────────────────────────────────
function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const headers = parseCSVLine(lines[0]).map(h => h.trim().replace(/^"|"$/g, ''));
  return lines.slice(1)
    .filter(l => l.trim())
    .map(line => {
      const values = parseCSVLine(line);
      const obj = {};
      headers.forEach((h, i) => { obj[h] = (values[i] || '').trim().replace(/^"|"$/g, ''); });
      return obj;
    });
}

function parseCSVLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') { current += '"'; i++; }
      else inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      result.push(current); current = '';
    } else {
      current += ch;
    }
  }
  result.push(current);
  return result;
}
```

- [ ] **Step 3: Add tests to `test.html`** (add after the `esc()` section, before the Summary block)

```javascript
section('CSV Parser');
const csvSample = 'Name,HR,OBP\n"Judge, Aaron",62,0.400\nTrout,40,0.390';
const csvRows = parseCSV(csvSample);
assertEqual(csvRows.length, 2, 'parseCSV: correct row count');
assertEqual(csvRows[0]['Name'], 'Judge, Aaron', 'parseCSV: handles quoted commas');
assertEqual(csvRows[0]['HR'], '62', 'parseCSV: reads numeric field as string');
assertEqual(csvRows[1]['OBP'], '0.390', 'parseCSV: reads last field');

section('localStorage');
saveData('_test_key', { x: 42 });
assertEqual(loadData('_test_key'), { x: 42 }, 'saveData/loadData roundtrip');
localStorage.removeItem('_test_key');
assertEqual(loadData('_test_key'), null, 'loadData returns null for missing key');
```

- [ ] **Step 4: Reload `test.html` — confirm all tests pass**

- [ ] **Step 5: Commit**

```bash
git add shared.js test.html
git commit -m "feat: localStorage interface and CSV parser"
```

---

## Task 3: Roster CSV Parser

**Files:**
- Modify: `shared.js`
- Modify: `test.html`

> ⚠️ **Verify column names first.** Open your Ottoneu roster CSV and check the actual header row. Update `ROSTER_COLS` below to match.

- [ ] **Step 1: Add roster parser to `shared.js`** (replace `// Roster parser → Task 3`)

```javascript
// ── ROSTER PARSER ────────────────────────────────────────────────────────────
// ⚠️ Verify these against your actual Ottoneu roster CSV export headers
const ROSTER_COLS = {
  fgId:      'fg_id',    // FanGraphs player ID — primary match key
  name:      'Name',
  positions: 'Pos',      // e.g. "SS/2B" or "OF" or "SP"
  salary:    'Salary',   // e.g. "$10" or "10"
  team:      'Team',     // fantasy team name; blank = free agent
};

function parseRosterCSV(text) {
  return parseCSV(text).map(row => ({
    fgId:      (row[ROSTER_COLS.fgId]      || '').trim(),
    name:      normalizeName(row[ROSTER_COLS.name] || ''),
    rawName:   (row[ROSTER_COLS.name]      || '').trim(),
    positions: parsePositions(row[ROSTER_COLS.positions] || ''),
    salary:    parseSalary(row[ROSTER_COLS.salary]  || '0'),
    team:      (row[ROSTER_COLS.team]      || '').trim() || 'Free Agent',
    type:      inferPlayerType(row[ROSTER_COLS.positions] || ''),
  }));
}

function normalizeName(name) {
  return String(name).toLowerCase()
    .replace(/[àáâãäå]/g, 'a').replace(/[èéêë]/g, 'e')
    .replace(/[ìíîï]/g, 'i').replace(/[òóôõö]/g, 'o')
    .replace(/[ùúûü]/g, 'u').replace(/ñ/g, 'n')
    .replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
}

function parsePositions(posStr) {
  return String(posStr).toLowerCase().split(/[/,]/).map(p => p.trim()).filter(Boolean);
}

function parseSalary(str) {
  return parseFloat(String(str).replace(/[$,\s]/g, '')) || 0;
}

function inferPlayerType(posStr) {
  const pos = String(posStr).toLowerCase();
  return (pos.includes('sp') || pos.includes('rp') || pos === 'p') ? 'P' : 'H';
}
```

- [ ] **Step 2: Add tests to `test.html`** (add after the localStorage section)

```javascript
section('Roster Parser');
const rosterCSV =
  'fg_id,Name,Pos,Salary,Team\n' +
  '12345,Aaron Judge,OF,$36,My Team\n' +
  '67890,Shohei Ohtani,DH/OF,$75,Other Team\n' +
  '11111,Gerrit Cole,SP,$40,My Team\n' +
  ',Unknown Player,1B,$1,';

const roster = parseRosterCSV(rosterCSV);
assertEqual(roster.length, 4, 'parseRosterCSV: row count');
assertEqual(roster[0].fgId, '12345', 'parseRosterCSV: fgId');
assertEqual(roster[0].salary, 36, 'parseRosterCSV: strips $ from salary');
assertEqual(roster[0].type, 'H', 'parseRosterCSV: hitter type');
assertEqual(roster[2].type, 'P', 'parseRosterCSV: pitcher type');
assertEqual(roster[1].positions, ['dh','of'], 'parseRosterCSV: splits positions');
assertEqual(roster[3].team, 'Free Agent', 'parseRosterCSV: blank team → Free Agent');
assertEqual(normalizeName('José Ramírez'), 'jose ramirez', 'normalizeName: strips accents');
```

- [ ] **Step 3: Reload `test.html` — confirm all tests pass**

- [ ] **Step 4: Commit**

```bash
git add shared.js test.html
git commit -m "feat: roster CSV parser with position and salary parsing"
```

---

## Task 4: Projection CSV Parsers

**Files:**
- Modify: `shared.js`
- Modify: `test.html`

> ⚠️ **Verify column names first.** Open your FanGraphs hitting and pitching projection CSVs. Update `HITTING_PROJ_COLS` and `PITCHING_PROJ_COLS` to match.

- [ ] **Step 1: Add projection parsers to `shared.js`** (replace `// Proj parsers → Task 4`)

```javascript
// ── PROJECTION PARSERS ───────────────────────────────────────────────────────
// ⚠️ Verify these against your actual FanGraphs projection CSV headers
const HITTING_PROJ_COLS = {
  fgId: 'playerid', name: 'Name', team: 'Team',
  pa: 'PA', ab: 'AB', h: 'H', bb: 'BB', hbp: 'HBP',
  hr: 'HR', r: 'R', obp: 'OBP', slg: 'SLG',
};

const PITCHING_PROJ_COLS = {
  fgId: 'playerid', name: 'Name', team: 'Team',
  ip: 'IP', h: 'H', bb: 'BB', hr: 'HR', so: 'SO',
  era: 'ERA', whip: 'WHIP', hr9: 'HR/9',
};

function parseHittingProjections(text) {
  return parseCSV(text)
    .filter(row => parseFloat(row[HITTING_PROJ_COLS.pa]) > 0)
    .map(row => {
      const n = k => parseFloat(row[HITTING_PROJ_COLS[k]]) || 0;
      return {
        fgId:    (row[HITTING_PROJ_COLS.fgId] || '').trim(),
        name:    normalizeName(row[HITTING_PROJ_COLS.name] || ''),
        rawName: (row[HITTING_PROJ_COLS.name] || '').trim(),
        type:    'H',
        proj: {
          pa: n('pa'), ab: n('ab'), h: n('h'),
          bb: n('bb'), hbp: n('hbp'),
          hr: n('hr'), r: n('r'),
          obp: n('obp'), slg: n('slg'),
        },
      };
    });
}

function parsePitchingProjections(text) {
  return parseCSV(text)
    .filter(row => parseFloat(row[PITCHING_PROJ_COLS.ip]) > 0)
    .map(row => {
      const n   = k => parseFloat(row[PITCHING_PROJ_COLS[k]]) || 0;
      const ip  = n('ip');
      const era = n('era');
      const hr  = n('hr');
      const hr9col = parseFloat(row[PITCHING_PROJ_COLS.hr9]) || 0;
      const hr9 = hr9col > 0 ? hr9col : (ip > 0 ? hr * 9 / ip : 0);
      return {
        fgId:    (row[PITCHING_PROJ_COLS.fgId] || '').trim(),
        name:    normalizeName(row[PITCHING_PROJ_COLS.name] || ''),
        rawName: (row[PITCHING_PROJ_COLS.name] || '').trim(),
        type:    'P',
        proj: {
          ip, hr, hr9,
          h:    n('h'),
          bb:   n('bb'),
          so:   n('so'),
          era,
          whip: n('whip'),
          er:   ip > 0 ? era * ip / 9 : 0,
        },
      };
    });
}
```

- [ ] **Step 2: Add tests to `test.html`**

```javascript
section('Projection Parsers');
const hitProjCSV =
  'playerid,Name,Team,PA,AB,H,BB,HBP,HR,R,OBP,SLG\n' +
  '12345,Aaron Judge,NYY,600,520,150,90,5,55,110,0.400,0.580\n' +
  '00000,Zero PA Guy,AAA,0,0,0,0,0,0,0,0,0';

const hitProj = parseHittingProjections(hitProjCSV);
assertEqual(hitProj.length, 1, 'parseHittingProjections: filters zero-PA rows');
assertEqual(hitProj[0].proj.hr, 55, 'parseHittingProjections: HR');
assertEqual(hitProj[0].proj.obp, 0.400, 'parseHittingProjections: OBP');
assertEqual(hitProj[0].type, 'H', 'parseHittingProjections: type is H');

const pitProjCSV =
  'playerid,Name,Team,IP,H,BB,HR,SO,ERA,WHIP,HR/9\n' +
  '99999,Gerrit Cole,NYY,200,160,40,20,240,3.00,1.00,0.90';

const pitProj = parsePitchingProjections(pitProjCSV);
assertEqual(pitProj.length, 1, 'parsePitchingProjections: row count');
assertEqual(pitProj[0].proj.ip, 200, 'parsePitchingProjections: IP');
assertEqual(pitProj[0].proj.so, 240, 'parsePitchingProjections: SO');
assert(Math.abs(pitProj[0].proj.er - 200 * 3.00 / 9) < 0.01,
  'parsePitchingProjections: derived ER');

const pitProjNoHR9CSV =
  'playerid,Name,Team,IP,H,BB,HR,SO,ERA,WHIP,HR/9\n' +
  '88888,No HR9 Pitcher,NYY,180,160,50,18,200,3.50,1.10,0';
const pitProjNoHR9 = parsePitchingProjections(pitProjNoHR9CSV);
assert(Math.abs(pitProjNoHR9[0].proj.hr9 - (18 * 9 / 180)) < 0.001,
  'parsePitchingProjections: derives HR/9 when column is zero');
```

- [ ] **Step 3: Reload `test.html` — confirm all tests pass**

- [ ] **Step 4: Commit**

```bash
git add shared.js test.html
git commit -m "feat: hitting and pitching projection CSV parsers"
```

---

## Task 5: Current Stats Parsers + Player Matching

**Files:**
- Modify: `shared.js`
- Modify: `test.html`

> ⚠️ **Verify column names.** FanGraphs current stats CSVs often use identical column names to projections — confirm this. The key difference is a `G` (games) column for hitters.

- [ ] **Step 1: Add current stats parsers to `shared.js`** (replace `// Stats parsers → Task 5`)

```javascript
// ── CURRENT STATS PARSERS ────────────────────────────────────────────────────
// ⚠️ Verify these against your FanGraphs leaderboard CSV exports
const HITTING_STATS_COLS = {
  fgId: 'playerid', name: 'Name', team: 'Team',
  g: 'G', pa: 'PA', ab: 'AB', h: 'H', bb: 'BB', hbp: 'HBP',
  hr: 'HR', r: 'R', obp: 'OBP', slg: 'SLG',
};

const PITCHING_STATS_COLS = {
  fgId: 'playerid', name: 'Name', team: 'Team',
  ip: 'IP', h: 'H', bb: 'BB', hr: 'HR', so: 'SO',
  era: 'ERA', whip: 'WHIP', hr9: 'HR/9',
};

function parseHittingStats(text) {
  return parseCSV(text)
    .filter(row => parseFloat(row[HITTING_STATS_COLS.pa]) > 0)
    .map(row => {
      const n = k => parseFloat(row[HITTING_STATS_COLS[k]]) || 0;
      return {
        fgId:    (row[HITTING_STATS_COLS.fgId] || '').trim(),
        name:    normalizeName(row[HITTING_STATS_COLS.name] || ''),
        rawName: (row[HITTING_STATS_COLS.name] || '').trim(),
        type:    'H',
        stats: {
          g: n('g'), pa: n('pa'), ab: n('ab'), h: n('h'),
          bb: n('bb'), hbp: n('hbp'),
          hr: n('hr'), r: n('r'),
          obp: n('obp'), slg: n('slg'),
        },
      };
    });
}

function parsePitchingStats(text) {
  return parseCSV(text)
    .filter(row => parseFloat(row[PITCHING_STATS_COLS.ip]) > 0)
    .map(row => {
      const n   = k => parseFloat(row[PITCHING_STATS_COLS[k]]) || 0;
      const ip  = n('ip');
      const era = n('era');
      const hr  = n('hr');
      const hr9col = parseFloat(row[PITCHING_STATS_COLS.hr9]) || 0;
      const hr9 = hr9col > 0 ? hr9col : (ip > 0 ? hr * 9 / ip : 0);
      return {
        fgId:    (row[PITCHING_STATS_COLS.fgId] || '').trim(),
        name:    normalizeName(row[PITCHING_STATS_COLS.name] || ''),
        rawName: (row[PITCHING_STATS_COLS.name] || '').trim(),
        type:    'P',
        stats: {
          ip, hr, hr9, era,
          h:    n('h'), bb: n('bb'), so: n('so'),
          whip: n('whip'),
          er:   ip > 0 ? era * ip / 9 : 0,
        },
      };
    });
}
```

- [ ] **Step 2: Add player matching to `shared.js`** (replace `// Player match → Task 5`)

```javascript
// ── PLAYER MATCHING ──────────────────────────────────────────────────────────
// Merges roster players with their projections and current stats.
// Match priority: FanGraphs ID → normalized name.
function matchPlayers(rosterPlayers, hittingProj, pitchingProj, hittingStats, pitchingStats) {
  const projById   = {};
  const projByName = {};
  [...(hittingProj || []), ...(pitchingProj || [])].forEach(p => {
    if (p.fgId)  projById[p.fgId]   = p;
    if (p.name)  projByName[p.name] = p;
  });

  const statsById   = {};
  const statsByName = {};
  [...(hittingStats || []), ...(pitchingStats || [])].forEach(p => {
    if (p.fgId)  statsById[p.fgId]   = p;
    if (p.name)  statsByName[p.name] = p;
  });

  return rosterPlayers.map(rp => {
    const projMatch  = projById[rp.fgId]   || projByName[rp.name]  || null;
    const statsMatch = statsById[rp.fgId]  || statsByName[rp.name] || null;
    return {
      ...rp,
      proj:  projMatch  ? projMatch.proj   : null,
      stats: statsMatch ? statsMatch.stats : null,
    };
  });
}

// Players in projection CSVs not assigned to any rostered team = free agents.
function getFreeAgents(hittingProj, pitchingProj, rosterPlayers) {
  const rosteredIds   = new Set(rosterPlayers.map(p => p.fgId).filter(Boolean));
  const rosteredNames = new Set(rosterPlayers.map(p => p.name));
  return [...(hittingProj || []), ...(pitchingProj || [])].filter(p =>
    !rosteredIds.has(p.fgId) && !rosteredNames.has(p.name)
  ).map(p => ({
    ...p,
    positions: [],
    salary:    0,
    team:      'Free Agent',
    stats:     null,
  }));
}
```

- [ ] **Step 3: Add tests to `test.html`**

```javascript
section('Player Matching');
const rPlayers = [
  { fgId: '111', name: 'mike trout',    rawName: 'Mike Trout',    type: 'H', positions: ['of'], salary: 30, team: 'My Team' },
  { fgId: '',    name: 'nolan arenado', rawName: 'Nolan Arenado', type: 'H', positions: ['3b'], salary: 20, team: 'Other'   },
];
const hProj = [
  { fgId: '111', name: 'mike trout',    type: 'H', proj: { pa:550, ab:490, h:140, bb:85, hbp:5, hr:35, r:100, obp:0.420, slg:0.580 } },
  { fgId: '222', name: 'nolan arenado', type: 'H', proj: { pa:580, ab:530, h:160, bb:45, hbp:3, hr:28, r:85,  obp:0.350, slg:0.510 } },
];
const matched = matchPlayers(rPlayers, hProj, [], null, null);
assertEqual(matched[0].proj.hr, 35, 'matchPlayers: matches by fgId');
assertEqual(matched[1].proj.hr, 28, 'matchPlayers: falls back to name match');
assertEqual(matched[0].team, 'My Team', 'matchPlayers: preserves roster fields');
assertEqual(matched[0].salary, 30, 'matchPlayers: preserves salary');
```

- [ ] **Step 4: Reload `test.html` — confirm all tests pass**

- [ ] **Step 5: Commit**

```bash
git add shared.js test.html
git commit -m "feat: current stats parsers and player matching"
```

---

## Task 6: Blended Stats + IL Pro-Rating

**Files:**
- Modify: `shared.js`
- Modify: `test.html`

- [ ] **Step 1: Add blended stats and IL logic to `shared.js`** (replace `// Blended stats → Task 6` and `// IL pro-rating → Task 6`)

```javascript
// ── BLENDED STATS + IL PRO-RATING ────────────────────────────────────────────
// Returns a full projected season stats object, blending actual YTD stats with
// remaining projected stats. ilDesignations: [{ fgId, name, type: '15day'|'60day' }]
function getBlendedStats(player, ilDesignations) {
  const proj  = player.proj;
  const stats = player.stats;
  if (!proj) return null;

  const il = (ilDesignations || []).find(d =>
    (d.fgId && d.fgId === player.fgId) || d.name === player.name
  );
  const missedGames = il ? (il.type === '15day' ? IL_15_MISS : IL_60_MISS) : 0;
  const ilScale     = (162 - missedGames) / 162;

  if (!stats) return scaleStats(proj, ilScale, player.type);

  const fraction = player.type === 'H'
    ? Math.min((stats.pa || 0) / Math.max(proj.pa, 1), 1)
    : Math.min((stats.ip || 0) / IP_MAX, 1);

  return blendStats(stats, proj, fraction, Math.max(0, 1 - fraction) * ilScale, player.type);
}

function scaleStats(proj, scale, type) {
  if (type === 'H') {
    return {
      pa:  proj.pa  * scale, ab:  proj.ab  * scale,
      h:   proj.h   * scale, bb:  proj.bb  * scale, hbp: proj.hbp * scale,
      hr:  proj.hr  * scale, r:   proj.r   * scale,
      obp: proj.obp, slg: proj.slg,   // rate stats unchanged by uniform scaling
    };
  }
  const ip = proj.ip * scale;
  return {
    ip, hr: proj.hr * scale, so: proj.so * scale,
    h:  proj.h  * scale, bb: proj.bb * scale, er: proj.er * scale,
    era: proj.era, whip: proj.whip, hr9: proj.hr9,
  };
}

function blendStats(stats, proj, fraction, remainingScale, type) {
  if (type === 'H') {
    const actPA = stats.pa || 0, actAB = stats.ab || 0;
    const remPA = proj.pa * remainingScale, remAB = proj.ab * remainingScale;
    const totPA = actPA + remPA, totAB = actAB + remAB;
    return {
      pa:  totPA, ab:  totAB,
      h:   (stats.h   || 0) + proj.h   * remainingScale,
      bb:  (stats.bb  || 0) + proj.bb  * remainingScale,
      hbp: (stats.hbp || 0) + proj.hbp * remainingScale,
      hr:  (stats.hr  || 0) + proj.hr  * remainingScale,
      r:   (stats.r   || 0) + proj.r   * remainingScale,
      obp: totPA > 0 ? (actPA * (stats.obp || 0) + remPA * (proj.obp || 0)) / totPA : 0,
      slg: totAB > 0 ? (actAB * (stats.slg || 0) + remAB * (proj.slg || 0)) / totAB : 0,
    };
  }
  const actIP = stats.ip || 0, remIP = proj.ip * remainingScale;
  const totIP = actIP + remIP;
  const erNum   = actIP * (stats.era  || 0) / 9 + remIP * (proj.era  || 0) / 9;
  const whipNum = actIP * (stats.whip || 0)     + remIP * (proj.whip || 0);
  const hr9Num  = actIP * (stats.hr9  || 0) / 9 + remIP * (proj.hr9  || 0) / 9;
  return {
    ip:   totIP,
    hr:   (stats.hr || 0) + proj.hr * remainingScale,
    so:   (stats.so || 0) + proj.so * remainingScale,
    h:    (stats.h  || 0) + proj.h  * remainingScale,
    bb:   (stats.bb || 0) + proj.bb * remainingScale,
    er:   erNum,
    era:  totIP > 0 ? erNum  * 9 / totIP : 0,
    whip: totIP > 0 ? whipNum  / totIP   : 0,
    hr9:  totIP > 0 ? hr9Num  * 9 / totIP : 0,
  };
}
```

- [ ] **Step 2: Add tests to `test.html`**

```javascript
section('Blended Stats');
const hNoStats = {
  fgId: '1', name: 'test', type: 'H', stats: null,
  proj: { pa:600, ab:540, h:162, bb:70, hbp:5, hr:40, r:100, obp:0.380, slg:0.550 },
};
const pure = getBlendedStats(hNoStats, []);
assertEqual(pure.hr, 40, 'blended: pure projection when no stats');

const hIL15 = { ...hNoStats, fgId: '2', name: 'il15' };
const il15  = getBlendedStats(hIL15, [{ fgId: '2', name: 'il15', type: '15day' }]);
assert(Math.abs(il15.hr - 40 * (162 - IL_15_MISS) / 162) < 0.01, 'blended: 15-day IL scales HR');

const hIL60 = { ...hNoStats, fgId: '3', name: 'il60' };
const il60  = getBlendedStats(hIL60, [{ fgId: '3', name: 'il60', type: '60day' }]);
assert(Math.abs(il60.hr - 40 * (162 - IL_60_MISS) / 162) < 0.01, 'blended: 60-day IL scales HR');

const hMid = {
  fgId: '4', name: 'mid', type: 'H',
  proj:  { pa:600, ab:540, h:162, bb:70, hbp:5, hr:40, r:100, obp:0.380, slg:0.550 },
  stats: { pa:300, ab:270, h:81,  bb:35, hbp:2, hr:25, r:55,  obp:0.410, slg:0.600, g:82 },
};
const blended = getBlendedStats(hMid, []);
assert(blended.hr > 40 && blended.hr < 50, 'blended: mid-season blend HR in range');
assert(blended.pa > 550 && blended.pa < 650, 'blended: mid-season blend PA in range');
```

- [ ] **Step 3: Reload `test.html` — confirm all tests pass**

- [ ] **Step 4: Commit**

```bash
git add shared.js test.html
git commit -m "feat: blended stats model and IL pro-rating"
```

---

## Task 7: Lineup Optimizer

**Files:**
- Modify: `shared.js`
- Modify: `test.html`

The greedy approach (most-constrained slot first) is value-optimal for this lineup structure: the UTIL catch-all slot guarantees the top N hitters always start regardless of which slot a dual-position player occupies. Slot priority is used only for tiebreaking and to prevent leaving valid slots empty.

- [ ] **Step 1: Add lineup optimizer to `shared.js`** (replace `// Lineup optim → Task 7`)

```javascript
// ── LINEUP OPTIMIZER ────────────────────────────────────────────────────────
const HITTER_SLOTS = [
  { id: 'C',    eligible: p => p.positions.includes('c') },
  { id: '1B',   eligible: p => p.positions.includes('1b') },
  { id: '2B',   eligible: p => p.positions.includes('2b') },
  { id: 'SS',   eligible: p => p.positions.includes('ss') },
  { id: '3B',   eligible: p => p.positions.includes('3b') },
  { id: 'MI',   eligible: p => p.positions.some(pos => pos === '2b' || pos === 'ss') },
  { id: 'OF1',  eligible: p => p.positions.includes('of') },
  { id: 'OF2',  eligible: p => p.positions.includes('of') },
  { id: 'OF3',  eligible: p => p.positions.includes('of') },
  { id: 'OF4',  eligible: p => p.positions.includes('of') },
  { id: 'OF5',  eligible: p => p.positions.includes('of') },
  { id: 'UTIL', eligible: p => p.type === 'H' },
];

// Assigns hitters to slots. Returns { slotId: player } map.
function optimizeHitterLineup(hitters, ilDesignations) {
  const scored = hitters
    .filter(p => p.type === 'H')
    .map(p => {
      const b = getBlendedStats(p, ilDesignations) || {};
      return { ...p, _blended: b, _value: (b.pa || 0) * ((b.obp || 0) + (b.slg || 0)) };
    })
    .sort((a, b) => b._value - a._value);

  // Sort slots most-constrained first to prevent leaving valid slots empty
  const slots = [...HITTER_SLOTS].sort((a, b) =>
    scored.filter(p => a.eligible(p)).length - scored.filter(p => b.eligible(p)).length
  );

  const assignment = {};
  const used = new Set();
  for (const slot of slots) {
    const best = scored.find(p => slot.eligible(p) && !used.has(p.fgId || p.name));
    if (best) {
      assignment[slot.id] = best;
      used.add(best.fgId || best.name);
    }
  }
  return assignment;
}

// Selects pitchers ranked by value up to IP_MAX. Returns [] if projected IP < IP_MIN.
function selectPitchers(pitchers, ilDesignations) {
  const scored = pitchers
    .filter(p => p.type === 'P')
    .map(p => {
      const b        = getBlendedStats(p, ilDesignations) || {};
      const safeERA  = (b.era  || 0) > 0 ? b.era  : 99;
      const safeWHIP = (b.whip || 0) > 0 ? b.whip : 9;
      return { ...p, _blended: b, _value: (b.ip || 0) * (1 / safeERA + 1 / safeWHIP + (b.so || 0) / 100) };
    })
    .sort((a, b) => b._value - a._value);

  const selected = [];
  let totalIP = 0;
  for (const p of scored) {
    const ip = (p._blended && p._blended.ip) || 0;
    if (totalIP + ip <= IP_MAX) { selected.push(p); totalIP += ip; }
  }
  return totalIP >= IP_MIN ? selected : [];
}
```

- [ ] **Step 2: Add tests to `test.html`**

```javascript
section('Lineup Optimizer');
function mkH(name, positions, pa, obp, slg) {
  const proj = { pa, ab: pa*0.88, h: pa*0.25, bb: pa*0.10, hbp: pa*0.01, hr: pa*0.05, r: pa*0.14, obp, slg };
  return { fgId: name, name, rawName: name, type: 'H', positions, proj, stats: null, salary: 10, team: 'T' };
}
const testHitters = [
  mkH('catcher',  ['c'],       400, 0.330, 0.460),
  mkH('firstbase',['1b'],      550, 0.360, 0.520),
  mkH('second',   ['2b'],      520, 0.340, 0.470),
  mkH('short',    ['ss'],      510, 0.345, 0.465),
  mkH('third',    ['3b'],      540, 0.350, 0.500),
  mkH('midual',   ['2b','ss'], 580, 0.370, 0.530),
  mkH('of1',      ['of'],      600, 0.400, 0.600),
  mkH('of2',      ['of'],      590, 0.390, 0.580),
  mkH('of3',      ['of'],      570, 0.380, 0.560),
  mkH('of4',      ['of'],      560, 0.375, 0.550),
  mkH('of5',      ['of'],      550, 0.365, 0.540),
  mkH('dh',       ['dh'],      530, 0.355, 0.495),
];
const lu = optimizeHitterLineup(testHitters, []);
assert(lu['C']  && lu['C'].name  === 'catcher',   'optimizer: C assigned to catcher');
assert(lu['1B'] && lu['1B'].name === 'firstbase',  'optimizer: 1B assigned');
assert(lu['MI'] !== undefined,                     'optimizer: MI slot filled');
assert(lu['MI'].positions.includes('2b') || lu['MI'].positions.includes('ss'),
  'optimizer: MI player is MI-eligible');
assert(['OF1','OF2','OF3','OF4','OF5'].every(s => lu[s]), 'optimizer: all 5 OF slots filled');
assert(lu['UTIL'] !== undefined, 'optimizer: UTIL filled');
const names = Object.values(lu).map(p => p.name);
assertEqual(names.length, new Set(names).size, 'optimizer: no duplicate assignments');
```

- [ ] **Step 3: Reload `test.html` — confirm all tests pass**

- [ ] **Step 4: Commit**

```bash
git add shared.js test.html
git commit -m "feat: lineup optimizer for hitters and pitcher selection"
```

---

## Task 8: Scoring Engine

**Files:**
- Modify: `shared.js`
- Modify: `test.html`

- [ ] **Step 1: Add scoring engine to `shared.js`** (replace `// Scoring engine → Task 8`)

```javascript
// ── SCORING ENGINE ───────────────────────────────────────────────────────────
// Computes 8 category totals for one team from their lineup and pitcher pool.
function computeTeamStats(hitterAssignment, selectedPitchers, ilDesignations) {
  const hitters  = Object.values(hitterAssignment || {}).filter(Boolean);
  const pitchers = selectedPitchers || [];

  let totPA = 0, totAB = 0, totOBPNum = 0, totSLGNum = 0, totHR = 0, totR = 0;
  for (const p of hitters) {
    const b = p._blended || getBlendedStats(p, ilDesignations) || {};
    totPA     += b.pa  || 0;
    totAB     += b.ab  || 0;
    totOBPNum += (b.pa || 0) * (b.obp || 0);
    totSLGNum += (b.ab || 0) * (b.slg || 0);
    totHR     += b.hr  || 0;
    totR      += b.r   || 0;
  }

  let totIP = 0, totERNum = 0, totWHIPNum = 0, totHR9Num = 0, totSO = 0;
  for (const p of pitchers) {
    const b = p._blended || getBlendedStats(p, ilDesignations) || {};
    const ip = b.ip || 0;
    totIP      += ip;
    totERNum   += ip * (b.era  || 0) / 9;
    totWHIPNum += ip * (b.whip || 0);
    totHR9Num  += ip * (b.hr9  || 0) / 9;
    totSO      += b.so || 0;
  }

  const pitOk = totIP >= IP_MIN;
  return {
    OBP:  totPA > 0 ? totOBPNum / totPA  : 0,
    SLG:  totAB > 0 ? totSLGNum / totAB  : 0,
    HR:   totHR,
    R:    totR,
    ERA:  pitOk && totIP > 0 ? totERNum  * 9 / totIP : 0,
    WHIP: pitOk && totIP > 0 ? totWHIPNum  / totIP   : 0,
    HR9:  pitOk && totIP > 0 ? totHR9Num * 9 / totIP : 0,
    SO:   pitOk ? totSO : 0,
    _ip:  totIP,
    _pitchingValid: pitOk,
  };
}

// Ranks 12 teams 12→1 per category. Returns teams sorted by total points desc.
function buildStandings(teams) {
  const n      = teams.length;
  const ranked = teams.map(t => ({ ...t, points: 0, ranks: {} }));
  for (const cat of CATS) {
    const sorted = [...ranked].sort((a, b) => {
      const av = a.stats[cat] || 0, bv = b.stats[cat] || 0;
      return LOWER_BETTER.has(cat) ? av - bv : bv - av;
    });
    sorted.forEach((team, idx) => {
      const pts       = n - idx;
      team.ranks[cat] = pts;
      team.points    += pts;
    });
  }
  return ranked.sort((a, b) => b.points - a.points);
}
```

- [ ] **Step 2: Add tests to `test.html`**

```javascript
section('Scoring Engine');
function mkSH(name, pa, obp, slg, hr, r) {
  const b = { pa, ab: pa*0.88, obp, slg, hr, r };
  return { fgId: name, name, type: 'H', positions: ['of'], _blended: b, proj: null, stats: null, salary: 0, team: 'T' };
}
function mkSP(name, ip, era, whip, hr9, so) {
  const b = { ip, era, whip, hr9, so };
  return { fgId: name, name, type: 'P', positions: ['sp'], _blended: b, proj: null, stats: null, salary: 0, team: 'T' };
}
const testLineup   = { OF1: mkSH('h1',600,0.380,0.540,35,95), OF2: mkSH('h2',550,0.360,0.500,25,80) };
const testPitchers = [ mkSP('p1',800,3.20,1.10,1.00,220), mkSP('p2',700,3.80,1.20,1.20,180) ];
const ts = computeTeamStats(testLineup, testPitchers, []);
assert(ts._pitchingValid, 'scoring: pitching valid when IP >= 1250');
assertEqual(ts.HR, 60, 'scoring: HR sums correctly');
assertEqual(ts.R,  175, 'scoring: R sums correctly');
assert(ts.OBP > 0.36 && ts.OBP < 0.38, 'scoring: OBP is weighted average');

const teams2 = [
  { name: 'A', stats: { OBP:0.380, SLG:0.540, HR:200, R:900, ERA:3.50, WHIP:1.20, HR9:1.10, SO:1400 } },
  { name: 'B', stats: { OBP:0.360, SLG:0.510, HR:180, R:850, ERA:4.00, WHIP:1.30, HR9:1.30, SO:1300 } },
];
const standings = buildStandings(teams2);
assertEqual(standings[0].name, 'A', 'standings: better team ranks first');
assert(standings[0].ranks['ERA'] > standings[1].ranks['ERA'],
  'standings: lower ERA gets higher points');
```

- [ ] **Step 3: Reload `test.html` — confirm all tests pass**

- [ ] **Step 4: Commit**

```bash
git add shared.js test.html
git commit -m "feat: scoring engine and standings builder"
```

---

## Task 9: Valuation Model

**Files:**
- Modify: `shared.js`
- Modify: `test.html`

- [ ] **Step 1: Add valuation model to `shared.js`** (replace `// Valuation → Task 9`)

```javascript
// ── VALUATION MODEL ──────────────────────────────────────────────────────────
// Calculates dollar value per player using position-specific replacement level
// and SGP (standings gain points) denominators derived from projected standings.
//
// allTeamRosters: array of 12 arrays of matched player objects
// ilDesignations: array of { fgId, name, type }
// Returns: object keyed by player fgId-or-name →
//   { projectedValue, actualSalary, surplus, sgp }

function calculateAllValues(allTeamRosters, ilDesignations) {
  const il = ilDesignations || [];

  // 1. Optimize lineup for each team; attach blended stats
  const teamLineups = allTeamRosters.map(roster => {
    const hitters = roster.filter(p => p.type === 'H');
    const pitchers= roster.filter(p => p.type === 'P');
    const lineup  = optimizeHitterLineup(hitters, il);
    const pitPool = selectPitchers(pitchers, il);
    const stats   = computeTeamStats(lineup, pitPool, il);
    return { lineup, pitPool, stats, roster };
  });

  // 2. SGP denominators from stdev of each category across all teams
  const sgpDenom = calcSGPDenoms(teamLineups.map(t => t.stats));

  // 3. Track which players are starters
  const startingH = new Set();
  const startingP = new Set();
  teamLineups.forEach(t => {
    Object.values(t.lineup).filter(Boolean).forEach(p => startingH.add(p.fgId || p.name));
    t.pitPool.forEach(p => startingP.add(p.fgId || p.name));
  });

  // Average team PA and IP (for rate-stat normalization)
  const avgPA = teamLineups.reduce((s, t) =>
    s + Object.values(t.lineup).filter(Boolean)
      .reduce((sp, p) => sp + ((p._blended && p._blended.pa) || 0), 0), 0) / NUM_TEAMS;
  const avgIP = teamLineups.reduce((s, t) =>
    s + t.pitPool.reduce((sp, p) => sp + ((p._blended && p._blended.ip) || 0), 0), 0) / NUM_TEAMS;

  // 4. Position-specific replacement level
  const replLevels = calcReplacementLevels(allTeamRosters, il, startingH, startingP);

  // 5. SGP per player
  const valueMap = {};
  let totalSGP = 0;
  const posSGPs = [];

  allTeamRosters.flat().forEach(player => {
    const key = player.fgId || player.name;
    if (valueMap[key]) return;
    const b       = getBlendedStats(player, il);
    const replKey = getReplacementKey(player);
    const repl    = replLevels[replKey];
    if (!b || !repl) {
      valueMap[key] = { sgp: 0, projectedValue: 0, actualSalary: player.salary || 0, surplus: -(player.salary || 0) };
      return;
    }
    const sgp = calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP);
    valueMap[key] = { sgp, actualSalary: player.salary || 0 };
    if (sgp > 0) { totalSGP += sgp; posSGPs.push({ key, sgp }); }
  });

  // 6. Normalize to $4,800
  posSGPs.forEach(({ key, sgp }) => {
    const val = totalSGP > 0 ? (sgp / totalSGP) * SALARY_POOL : 0;
    valueMap[key].projectedValue = Math.max(0, val);
    valueMap[key].surplus = valueMap[key].projectedValue - (valueMap[key].actualSalary || 0);
  });

  return valueMap;
}

function calcSGPDenoms(teamStatsArr) {
  const result = {};
  CATS.forEach(cat => {
    const vals = teamStatsArr.map(s => s[cat] || 0).filter(v => v > 0);
    result[cat] = vals.length > 1 ? stdev(vals) : 1;
  });
  return result;
}

function stdev(values) {
  const mean = values.reduce((s, v) => s + v, 0) / values.length;
  return Math.sqrt(values.reduce((s, v) => s + Math.pow(v - mean, 2), 0) / values.length) || 1;
}

function getReplacementKey(player) {
  if (player.type === 'P') return 'P';
  const pos = player.positions || [];
  if (pos.includes('c'))  return 'C';
  if (pos.includes('ss')) return 'SS';
  if (pos.includes('2b')) return '2B';
  if (pos.includes('3b')) return '3B';
  if (pos.includes('1b')) return '1B';
  if (pos.includes('of')) return 'OF';
  return 'UTIL';
}

function calcReplacementLevels(allTeamRosters, il, startingH, startingP) {
  const groups = { C:[], SS:[], '2B':[], '3B':[], '1B':[], OF:[], UTIL:[], P:[] };
  allTeamRosters.flat().forEach(p => {
    const b   = getBlendedStats(p, il);
    if (!b) return;
    const pk  = getReplacementKey(p);
    const key = p.fgId || p.name;
    const isStart = p.type === 'H' ? startingH.has(key) : startingP.has(key);
    groups[pk].push({ b, isStart, v: valProxy(p, b) });
  });
  const result = {};
  Object.entries(groups).forEach(([pos, players]) => {
    const sorted = [...players].sort((a, b) => b.v - a.v);
    const bench  = sorted.find(p => !p.isStart);
    result[pos]  = bench ? bench.b : (sorted[sorted.length - 1] || { b: null }).b;
  });
  return result;
}

function valProxy(player, b) {
  if (!b) return 0;
  if (player.type === 'H') return (b.pa || 0) * ((b.obp || 0) + (b.slg || 0));
  const safeERA = (b.era || 0) > 0 ? b.era : 99;
  return (b.ip || 0) * (1 / safeERA + (b.so || 0) / 1000);
}

function calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP) {
  let sgp = 0;
  if (player.type === 'H') {
    sgp += ((b.hr  || 0) - (repl.hr  || 0)) / (sgpDenom['HR']  || 1);
    sgp += ((b.r   || 0) - (repl.r   || 0)) / (sgpDenom['R']   || 1);
    const pa = b.pa || 0;
    sgp += ((b.obp || 0) - (repl.obp || 0)) * pa / (avgPA || 1) / (sgpDenom['OBP'] || 1);
    sgp += ((b.slg || 0) - (repl.slg || 0)) * pa / (avgPA || 1) / (sgpDenom['SLG'] || 1);
  } else {
    sgp += ((b.so   || 0) - (repl.so   || 0)) / (sgpDenom['SO']   || 1);
    const ip = b.ip || 0;
    sgp += ((repl.era  || 0) - (b.era  || 0)) * ip / (avgIP || 1) / (sgpDenom['ERA']  || 1);
    sgp += ((repl.whip || 0) - (b.whip || 0)) * ip / (avgIP || 1) / (sgpDenom['WHIP'] || 1);
    sgp += ((repl.hr9  || 0) - (b.hr9  || 0)) * ip / (avgIP || 1) / (sgpDenom['HR9']  || 1);
  }
  return sgp;
}
```

- [ ] **Step 2: Add tests to `test.html`**

```javascript
section('Valuation Model');
function mkFull(id, name, type, pos, proj, salary, team) {
  return { fgId: id, name, rawName: name, type, positions: pos, salary, team, proj, stats: null };
}
function padPitchers(arr, teamName) {
  for (let i = arr.length; i < 10; i++)
    arr.push(mkFull(teamName+'p'+i, teamName+'p'+i, 'P', ['sp'],
      { ip:100, h:95, bb:35, hr:10, so:110, era:3.60, whip:1.30, hr9:0.90, er:40 }, 4, teamName));
}
const t1 = [
  mkFull('s1','star','H',['of'],{ pa:600,ab:540,h:162,bb:70,hbp:5,hr:45,r:110,obp:0.420,slg:0.600 },30,'T1'),
  mkFull('w1','weak','H',['ss'],{ pa:460,ab:415,h:110,bb:35,hbp:2,hr:10,r:55, obp:0.310,slg:0.400 },5, 'T1'),
  mkFull('p1','ace', 'P',['sp'],{ ip:220,h:170,bb:45,hr:18,so:260,era:2.90,whip:0.98,hr9:0.74,er:71 },30,'T1'),
];
const t2 = [
  mkFull('s2','avg', 'H',['of'],{ pa:500,ab:450,h:125,bb:45,hbp:4,hr:18,r:65, obp:0.340,slg:0.450 },8, 'T2'),
  mkFull('w2','poor','H',['c'], { pa:350,ab:315,h:80, bb:25,hbp:2,hr:8, r:35, obp:0.290,slg:0.370 },4, 'T2'),
  mkFull('p2','mid', 'P',['sp'],{ ip:160,h:170,bb:60,hr:25,so:155,era:4.20,whip:1.44,hr9:1.41,er:75 },10,'T2'),
];
padPitchers(t1, 'T1');
padPitchers(t2, 'T2');

const vm = calculateAllValues([t1, t2], []);
assert(vm['s1'] !== undefined, 'valuation: star hitter has entry');
assert((vm['s1'].projectedValue || 0) > (vm['w2'].projectedValue || 0),
  'valuation: star hitter valued above poor hitter');
assert(vm['s1'].surplus < vm['s1'].projectedValue, 'valuation: surplus = value - salary');
```

- [ ] **Step 3: Reload `test.html` — confirm all tests pass**

- [ ] **Step 4: Commit**

```bash
git add shared.js test.html
git commit -m "feat: SGP-based valuation model with position-specific replacement level"
```

---

## Task 10: index.html — Data Hub

**Files:**
- Create: `index.html`

- [ ] **Step 1: Create `index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Ottoneu Tools — Data Hub</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; color: #222; }
    h1 { font-size: 1.4rem; margin-bottom: 4px; }
    .subtitle { color: #666; font-size: 0.9rem; margin-bottom: 24px; }
    .nav { display: flex; gap: 12px; margin-bottom: 28px; flex-wrap: wrap; }
    .nav a { padding: 8px 16px; background: #1a73e8; color: #fff; border-radius: 6px; text-decoration: none; font-size: 0.9rem; }
    .nav a:hover { background: #1557b0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
    .card { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
    .card h2 { font-size: 1rem; margin: 0 0 4px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; margin-bottom: 12px; }
    .badge.loaded   { background: #e6f4ea; color: #1e7e34; }
    .badge.missing  { background: #fce8e6; color: #c62828; }
    .badge.optional { background: #e8f0fe; color: #1a73e8; }
    .card label { display: block; font-size: 0.85rem; color: #555; margin-bottom: 6px; }
    .card input[type=file] { width: 100%; font-size: 0.85rem; }
    .meta { font-size: 0.78rem; color: #888; margin-top: 6px; min-height: 18px; }
    .section-title { font-size: 1rem; font-weight: 600; margin: 28px 0 12px; }
    .il-add { display: flex; gap: 8px; margin-bottom: 8px; }
    .il-add input  { flex: 1; padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85rem; }
    .il-add select { padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.85rem; }
    .il-add button { background: #1a73e8; color: #fff; border: none; border-radius: 4px; padding: 6px 14px; cursor: pointer; font-size: 0.85rem; }
    .il-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
    .il-row .il-name { flex: 1; font-size: 0.9rem; }
    .il-row .il-type { font-size: 0.82rem; color: #555; }
    .il-row button { background: #f44336; color: #fff; border: none; border-radius: 4px; padding: 4px 10px; cursor: pointer; font-size: 0.82rem; }
    .il-empty { color: #999; font-size: 0.85rem; }
    .team-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
    .team-row select { padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.9rem; }
    .clear-btn { margin-top: 28px; padding: 8px 18px; background: #f5f5f5; border: 1px solid #ccc; border-radius: 6px; cursor: pointer; font-size: 0.85rem; color: #555; }
    .clear-btn:hover { background: #ffe0e0; border-color: #f44336; color: #f44336; }
    .toast { position: fixed; bottom: 24px; right: 24px; background: #333; color: #fff; padding: 10px 18px; border-radius: 8px; font-size: 0.9rem; opacity: 0; transition: opacity 0.3s; pointer-events: none; }
    .toast.show { opacity: 1; }
  </style>
</head>
<body>
  <h1>Ottoneu 4×4 Tools</h1>
  <p class="subtitle">Upload your data once — all tools share it automatically.</p>

  <nav class="nav">
    <a href="standings.html">Standings</a>
    <a href="roster.html">Roster Analysis</a>
    <a href="trade.html">Trade Evaluator</a>
    <a href="fa.html">FA Finder</a>
  </nav>

  <div class="section-title">My Team</div>
  <div class="team-row">
    <label for="teamSelect" style="font-size:0.9rem">Your team:</label>
    <select id="teamSelect"><option value="">— load roster CSV first —</option></select>
  </div>

  <div class="section-title">Data Files</div>
  <div class="grid" id="csvGrid"></div>

  <div class="section-title">Injured List (your team only)</div>
  <div class="il-add">
    <input  id="ilName" type="text" placeholder="Player name (as in roster)" autocomplete="off">
    <select id="ilType">
      <option value="15day">15-day IL</option>
      <option value="60day">60-day IL</option>
    </select>
    <button onclick="addIL()">Add</button>
  </div>
  <div id="ilList"></div>

  <button class="clear-btn" onclick="clearAll()">Clear all data</button>
  <div class="toast" id="toast"></div>

  <script src="shared.js"></script>
  <script>
    const CSV_CONFIGS = [
      { key: 'ottoneu_roster',        label: 'Ottoneu Roster',        required: true,  parse: parseRosterCSV },
      { key: 'ottoneu_proj_hitting',  label: 'Hitting Projections',   required: true,  parse: parseHittingProjections },
      { key: 'ottoneu_proj_pitching', label: 'Pitching Projections',  required: true,  parse: parsePitchingProjections },
      { key: 'ottoneu_stats_hitting', label: 'Current Hitting Stats', required: false, parse: parseHittingStats },
      { key: 'ottoneu_stats_pitching',label: 'Current Pitching Stats',required: false, parse: parsePitchingStats },
    ];

    function buildGrid() {
      const grid = document.getElementById('csvGrid');
      // Clear existing content safely
      while (grid.firstChild) grid.removeChild(grid.firstChild);

      CSV_CONFIGS.forEach((cfg, idx) => {
        const stored    = loadData(cfg.key);
        const count     = stored ? stored.length : 0;
        const statusCls = stored ? 'loaded' : (cfg.required ? 'missing' : 'optional');
        const statusTxt = stored ? '\u2713 ' + count + ' players' : (cfg.required ? 'Required' : 'Optional');
        const ts        = loadData(cfg.key + '_ts');
        const metaTxt   = stored && ts
          ? 'Loaded ' + new Date(ts).toLocaleString()
          : (stored ? 'Loaded' : 'Not loaded');

        const card = document.createElement('div');
        card.className = 'card';

        const h2 = document.createElement('h2');
        h2.textContent = cfg.label;

        const badge = document.createElement('span');
        badge.className = 'badge ' + statusCls;
        badge.textContent = statusTxt;

        const lbl = document.createElement('label');
        lbl.textContent = 'Upload CSV:';

        const input = document.createElement('input');
        input.type   = 'file';
        input.accept = '.csv';
        input.addEventListener('change', function(e) { handleFile(e, cfg.key, idx); });

        const meta = document.createElement('div');
        meta.className = 'meta';
        meta.id        = 'meta_' + cfg.key;
        meta.textContent = metaTxt;

        card.appendChild(h2);
        card.appendChild(badge);
        card.appendChild(lbl);
        card.appendChild(input);
        card.appendChild(meta);
        grid.appendChild(card);
      });
    }

    function handleFile(event, key, cfgIdx) {
      const file = event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function(e) {
        try {
          const parsed = CSV_CONFIGS[cfgIdx].parse(e.target.result);
          saveData(key, parsed);
          saveData(key + '_ts', Date.now());
          showToast('Loaded ' + parsed.length + ' rows from ' + file.name);
          buildGrid();
          if (key === 'ottoneu_roster') rebuildTeamDropdown(parsed);
        } catch (err) {
          showToast('Error parsing file: ' + err.message);
        }
      };
      reader.readAsText(file);
    }

    function rebuildTeamDropdown(rosterPlayers) {
      const teams  = Array.from(new Set(
        rosterPlayers.map(function(p) { return p.team; })
          .filter(function(t) { return t && t !== 'Free Agent'; })
      )).sort();
      const sel    = document.getElementById('teamSelect');
      const saved  = loadData('ottoneu_my_team') || '';
      while (sel.firstChild) sel.removeChild(sel.firstChild);
      const def = document.createElement('option');
      def.value       = '';
      def.textContent = '— select your team —';
      sel.appendChild(def);
      teams.forEach(function(t) {
        const opt = document.createElement('option');
        opt.value       = t;
        opt.textContent = t;
        if (t === saved) opt.selected = true;
        sel.appendChild(opt);
      });
    }

    document.getElementById('teamSelect').addEventListener('change', function() {
      saveData('ottoneu_my_team', this.value);
      showToast('My team set to: ' + this.value);
    });

    function renderIL() {
      const il   = loadData('ottoneu_il') || [];
      const list = document.getElementById('ilList');
      while (list.firstChild) list.removeChild(list.firstChild);

      if (il.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'il-empty';
        empty.textContent = 'No players on IL';
        list.appendChild(empty);
        return;
      }

      il.forEach(function(d, i) {
        const row = document.createElement('div');
        row.className = 'il-row';

        const nameSpan = document.createElement('span');
        nameSpan.className   = 'il-name';
        nameSpan.textContent = d.rawName || d.name;

        const typeSpan = document.createElement('span');
        typeSpan.className   = 'il-type';
        typeSpan.textContent = d.type === '15day' ? '15-day IL' : '60-day IL';

        const btn = document.createElement('button');
        btn.textContent = 'Remove';
        btn.addEventListener('click', function() { removeIL(i); });

        row.appendChild(nameSpan);
        row.appendChild(typeSpan);
        row.appendChild(btn);
        list.appendChild(row);
      });
    }

    function addIL() {
      const rawName = document.getElementById('ilName').value.trim();
      if (!rawName) return;
      const il = loadData('ottoneu_il') || [];
      il.push({ rawName, name: normalizeName(rawName), fgId: '', type: document.getElementById('ilType').value });
      saveData('ottoneu_il', il);
      document.getElementById('ilName').value = '';
      renderIL();
      showToast(rawName + ' added to IL');
    }

    function removeIL(idx) {
      const il = loadData('ottoneu_il') || [];
      il.splice(idx, 1);
      saveData('ottoneu_il', il);
      renderIL();
    }

    function clearAll() {
      if (!confirm('Clear all loaded data?')) return;
      clearAllData();
      buildGrid();
      const sel = document.getElementById('teamSelect');
      while (sel.firstChild) sel.removeChild(sel.firstChild);
      const def = document.createElement('option');
      def.value       = '';
      def.textContent = '— load roster CSV first —';
      sel.appendChild(def);
      renderIL();
      showToast('All data cleared');
    }

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.add('show');
      setTimeout(function() { t.classList.remove('show'); }, 2800);
    }

    buildGrid();
    const savedRoster = loadData('ottoneu_roster');
    if (savedRoster) rebuildTeamDropdown(savedRoster);
    renderIL();
  </script>
</body>
</html>
```

- [ ] **Step 2: Open `index.html` in browser and verify**
  - 5 CSV upload cards appear (3 required, 2 optional)
  - Upload Ottoneu roster CSV → team dropdown populates
  - Select your team → toast confirms save; reopen page → selection persists
  - Upload hitting projections → row count appears in card
  - Add a player to IL, reload page → player persists in IL list
  - DevTools Console → no errors

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat: data hub with CSV uploads, IL management, and team selector"
```

---

## Task 11: standings.html

**Files:**
- Create: `standings.html`

- [ ] **Step 1: Create `standings.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Ottoneu Tools — Standings</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; color: #222; }
    h1 { font-size: 1.3rem; margin-bottom: 4px; }
    .nav { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
    .nav a { padding: 7px 14px; background: #1a73e8; color: #fff; border-radius: 6px; text-decoration: none; font-size: 0.88rem; }
    .nav a.active { background: #1557b0; }
    .controls { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
    .mode-label { font-size: 0.88rem; color: #555; }
    .toggle-btn { padding: 6px 14px; border: 1px solid #1a73e8; color: #1a73e8; background: #fff; border-radius: 6px; cursor: pointer; font-size: 0.85rem; }
    .toggle-btn.on { background: #1a73e8; color: #fff; }
    .error { background: #fce8e6; border-left: 4px solid #c62828; padding: 12px 16px; border-radius: 4px; margin-bottom: 16px; }
    .error a { color: #c62828; }
    .tbl-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.1); font-size: 0.88rem; min-width: 700px; }
    th { background: #1a73e8; color: #fff; padding: 10px 8px; text-align: right; font-weight: 600; white-space: nowrap; }
    th:first-child, th:nth-child(2) { text-align: left; }
    td { padding: 8px 8px; text-align: right; border-bottom: 1px solid #f0f0f0; }
    td:first-child, td:nth-child(2) { text-align: left; }
    tr.mine td { background: #e8f0fe; font-weight: 600; }
    tr:hover td { background: #f8f8f8; }
    tr.mine:hover td { background: #d2e3fc; }
    .rank { font-weight: 700; color: #555; }
    .pts  { font-weight: 700; color: #1a73e8; }
    .low  { color: #c62828; }
    .cat-pts { font-size: 0.75rem; color: #aaa; display: block; }
  </style>
</head>
<body>
  <h1>Standings Projector</h1>
  <nav class="nav">
    <a href="index.html">Data Hub</a>
    <a href="standings.html" class="active">Standings</a>
    <a href="roster.html">Roster Analysis</a>
    <a href="trade.html">Trade Evaluator</a>
    <a href="fa.html">FA Finder</a>
  </nav>

  <div class="controls">
    <span class="mode-label" id="modeLabel"></span>
    <button class="toggle-btn" id="blendBtn" style="display:none" onclick="toggleBlend()">
      Switch to Blended Stats
    </button>
  </div>

  <div id="error"></div>
  <div class="tbl-wrap" id="tblWrap"></div>

  <script src="shared.js"></script>
  <script>
    var useBlend = false;

    function toggleBlend() {
      useBlend = !useBlend;
      var btn = document.getElementById('blendBtn');
      btn.textContent = useBlend ? 'Switch to Projections Only' : 'Switch to Blended Stats';
      btn.classList.toggle('on', useBlend);
      render();
    }

    function render() {
      var errEl  = document.getElementById('error');
      var tblWrap = document.getElementById('tblWrap');
      errEl.textContent = '';
      while (tblWrap.firstChild) tblWrap.removeChild(tblWrap.firstChild);

      var roster     = loadData('ottoneu_roster');
      var projHit    = loadData('ottoneu_proj_hitting');
      var projPitch  = loadData('ottoneu_proj_pitching');
      var myTeam     = loadData('ottoneu_my_team') || '';
      var il         = loadData('ottoneu_il') || [];
      var hasHitStats = !!loadData('ottoneu_stats_hitting');
      var hasPitStats = !!loadData('ottoneu_stats_pitching');
      var blendAvail  = hasHitStats || hasPitStats;

      if (!roster || !projHit || !projPitch) {
        var errDiv = document.createElement('div');
        errDiv.className = 'error';
        errDiv.textContent = 'Missing data \u2014 please upload the roster and both projection CSVs on the ';
        var link = document.createElement('a');
        link.href        = 'index.html';
        link.textContent = 'Data Hub';
        errDiv.appendChild(link);
        errDiv.appendChild(document.createTextNode('.'));
        errEl.appendChild(errDiv);
        return;
      }

      // Mode label and toggle
      var modeLabel = document.getElementById('modeLabel');
      var blendBtn  = document.getElementById('blendBtn');
      if (blendAvail) {
        blendBtn.style.display = '';
        modeLabel.textContent  = useBlend ? 'Mode: Projections + Current Stats' : 'Mode: Projections Only';
      } else {
        blendBtn.style.display = 'none';
        modeLabel.textContent  = 'Mode: Projections Only (upload current stats to enable blending)';
      }

      var statsHit   = useBlend ? loadData('ottoneu_stats_hitting')  : null;
      var statsPitch = useBlend ? loadData('ottoneu_stats_pitching') : null;

      // Build per-team player maps
      var teamMap = {};
      var merged  = matchPlayers(roster, projHit, projPitch, statsHit, statsPitch);
      merged.forEach(function(p) {
        if (!teamMap[p.team]) teamMap[p.team] = [];
        teamMap[p.team].push(p);
      });

      var teamNames = Object.keys(teamMap).filter(function(t) { return t !== 'Free Agent'; });

      var teamStatsArr = teamNames.map(function(name) {
        var players  = teamMap[name];
        var hitters  = players.filter(function(p) { return p.type === 'H'; });
        var pitchers = players.filter(function(p) { return p.type === 'P'; });
        var teamIL   = name === myTeam ? il : [];
        var lineup   = optimizeHitterLineup(hitters, teamIL);
        var pitPool  = selectPitchers(pitchers, teamIL);
        var stats    = computeTeamStats(lineup, pitPool, teamIL);
        return { name: name, stats: stats };
      });

      var standings = buildStandings(teamStatsArr);

      // Build table via DOM
      var table = document.createElement('table');

      // Header
      var thead = document.createElement('thead');
      var hrow  = document.createElement('tr');
      ['#','Team','Pts'].concat(CATS).forEach(function(h) {
        var th = document.createElement('th');
        th.textContent = h;
        hrow.appendChild(th);
      });
      thead.appendChild(hrow);
      table.appendChild(thead);

      // Body
      var tbody = document.createElement('tbody');
      standings.forEach(function(team, idx) {
        var tr = document.createElement('tr');
        if (team.name === myTeam) tr.className = 'mine';

        function td(text, cls) {
          var cell = document.createElement('td');
          cell.textContent = text;
          if (cls) cell.className = cls;
          return cell;
        }

        tr.appendChild(td(String(idx + 1), 'rank'));
        tr.appendChild(td(team.name));
        tr.appendChild(td(String(team.points), 'pts'));

        CATS.forEach(function(cat) {
          var pts = team.ranks[cat] || 0;
          var val = team.stats[cat] || 0;
          var isRate = cat === 'OBP' || cat === 'SLG' || cat === 'ERA' || cat === 'WHIP' || cat === 'HR9';
          var cell  = document.createElement('td');
          if (pts <= 4) cell.className = 'low';

          var valText = document.createTextNode(isRate ? val.toFixed(3) : Math.round(val));
          var ptsSpan = document.createElement('span');
          ptsSpan.className   = 'cat-pts';
          ptsSpan.textContent = pts + 'pts';

          cell.appendChild(valText);
          cell.appendChild(ptsSpan);
          tr.appendChild(cell);
        });

        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      tblWrap.appendChild(table);
    }

    render();
  </script>
</body>
</html>
```

- [ ] **Step 2: Open `standings.html` in browser and verify end-to-end**
  - Table renders with all 12 teams (or however many are in your league)
  - Your team row is highlighted in blue
  - Category values look plausible: OBP ~0.320–0.380, HR ~150–270, ERA ~3.2–5.5
  - Bottom-ranked categories show in red
  - "Switch to Blended Stats" button appears only when current stats are loaded
  - No console errors

- [ ] **Step 3: Commit**

```bash
git add standings.html
git commit -m "feat: standings projector with blended stats toggle"
```

---

## Final Verification Checklist

- [ ] Open `test.html` → 0 failures
- [ ] Open `index.html` → upload all 5 CSVs without errors; IL add/remove persists on reload
- [ ] Open `standings.html` → full league standings render; your team highlighted
- [ ] Open `standings.html` with current stats loaded → blended toggle works
- [ ] DevTools Console → no errors on any page
- [ ] FanGraphs column names were verified against actual CSVs before running parsers
