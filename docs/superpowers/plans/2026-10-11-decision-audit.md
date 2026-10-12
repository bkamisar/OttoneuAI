# Decision Audit + Year-in-Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Node pipeline that grades every Ottoneu roster move 2024–2026 (process, result, luck, standings impact, tags) and two static pages: `audit.html` (my coaching page) and `review.html` (league year-in-review cards).

**Architecture:** `audit/run.js` runs checkpointed phases over `data/transactions.csv`, git history of the daily data files, and cached MLB Stats API daily lines. All valuation goes through the existing `shared.js` (and `hotboard.js`) loaded into a Node `vm` context with browser shims — no second copy of the model. Output is `data/audit.json` + `data/review.json`; the pages only render.

**Tech Stack:** Node 24 (built-in `fetch`, `vm`, `node:test`, `child_process`), no npm dependencies. Plain HTML/JS pages matching the suite (`theme.css`, nav).

**Spec:** `docs/superpowers/specs/2026-10-11-decision-audit-design.md`

## Global Constraints

- League 1648, 12 teams, **my TeamID = 10759**. TeamID is identity; team names are display only.
- No npm dependencies. Node built-ins only. Tests: `node --test audit/test/`.
- `shared.js` and `hotboard.js` are **not edited**; loaded via `audit/lib/engine.js` shims.
- Phases checkpoint to `audit/cache/` (gitignored); `--force` redoes all, `--force=<phase>` redoes that phase and later.
- First-party data only: Ottoneu pages (read in the built-in browser by Claude), git history, MLB Stats API.
- Never bypass Cloudflare challenges; on HTTP 429 stop and resume later.
- Manual notes/tag overrides live in browser `localStorage` only (key `audit_notes_v1`). Never committed.
- Process grades exist only for moves dated **2026-05-24 → 2026-09-28** (first projection snapshot → season end). Everything else is `process: null` ("result only").
- Swap window: add + cut by the same team within **30 minutes**.
- Patterns shown only when **n ≥ 5**; n always displayed.
- Review cards: phone width (max 420px), no URLs or tool links on cards.

### Dollar conventions (load-bearing — every grade uses these)

- `f(d)` = `rosProrationFactor()` evaluated at date `d` (fraction of season remaining; 1 before Mar 28, 0 after Sep 28).
- **Process** (as of date d): suite surplus × f(d). Add: `(projValue − salary) × f`. Cut: `(salaryFreed − projValue) × f`, `salaryFreed = salary × 0.5` in-season, `× 1` offseason. Trade side: `(Σ in surplus − Σ out surplus) × f`. Swap = add + cut.
- **Result**: `stintValue − salary × fracHeld`, where `stintValue = SGP(actual line over the window) × rate_season` (full-season-scale dollars) and `fracHeld` = share of the season's days (Mar 28–Sep 28) inside the window. Cut: `salary × salaryFactor × fracRemaining − value of the player's production from cut date to season end`. Trade side: `Σ in (value while on team − salary × frac) − Σ out (value from trade date to season end − salary × frac)`.
- **Luck** = result − process (null when process is null).

## Review Focus

1. **Transactions re-fetched with new rows on top** → pipeline must re-run cleanly (moves phase keyed on file hash, not on "already parsed"). Test in Task 9.
2. **Same-name players** (two "Will Smith"s, a hitter and a pitcher) → identity must pick by group/volume and list the case in the report, never merge two people. Test in Task 4.
3. **Player with zero MLB stats** (prospect stash) → production is a legitimate zero line, not "unmatched"; must not crash rate math (divide by zero). Test in Task 5.
4. **Move on a date with no roster/projection snapshot** (gap day) → process uses the latest snapshot *before* the date, never after. Test in Task 6.
5. **Two trades between different team pairs at the same second** → grouped as two trades, not one. Test in Task 2.

---

### Task 0: Data acquisition (Claude, interactive — not code)

**Files:**
- Create: `data/transactions.csv`
- Create: `data/standings-final-2024.csv`, `data/standings-final-2025.csv`
- Create: `audit/tools/fetch-transactions.browser.js` (the snippet, saved for re-runs)

- [ ] **Step 1:** In the built-in browser tab on `ottoneu.fangraphs.com/1648/transactions`, run the paging snippet (pages until an empty table; 6 s between pages; stop on any non-200). Rows accumulate in `localStorage.__tx_rows`.
- [ ] **Step 2:** Convert rows in the page to CSV with columns `date,type,player,ottoneuId,teamId,team,fromTeamId,fromTeam,salary` — ids parsed from hrefs `/1648/players/<id>` and `/1648/team/<id>`, date converted to `YYYY-MM-DDTHH:MM:SS` (24h, as shown, ET), salary as integer. Trigger a download (user approved: `ottoneu_1648_transactions_2024-2026.csv`), move it to `data/transactions.csv`.
- [ ] **Step 3:** Open the league standings page, find the season selector for 2024 and 2025, and save each final table as `data/standings-final-<year>.csv` with header `TeamID,Team,R,HR,OBP,SLG,IP,K,HR/9,ERA,WHIP` (TeamID from the team link). If the page has no IP column, write `1500`. If no historical standings exist, stop and tell the user (2024–25 standings impact then becomes unavailable; everything else still works).
- [ ] **Step 4:** Save the snippet as `audit/tools/fetch-transactions.browser.js` with a header comment: "Paste into the browser console on the Ottoneu transactions page. Read-only. Slow on purpose."
- [ ] **Step 5:** Sanity check: `node -e "const t=require('fs').readFileSync('data/transactions.csv','utf8').trim().split('\n');console.log(t.length-1, t[1], t.at(-1))"` → ~5,500 rows, newest first, oldest `2024-03-14...`.
- [ ] **Step 6: Commit** `git add data/transactions.csv data/standings-final-*.csv audit/tools && git commit -m "data(audit): Ottoneu transactions 2024-2026 + final standings 2024/2025"`

---

### Task 1: Engine loader

**Files:**
- Create: `audit/lib/engine.js`
- Create: `audit/test/engine.test.js`
- Modify: `.gitignore` (append `audit/cache/`)

**Interfaces:**
- Produces: `loadEngine() → engine` where `engine.setDate(isoDate)` fixes "today" for `rosProrationFactor()`, and `engine.call(name, ...args)` / `engine.get(name)` reach any top-level function or `const`/`let` in `shared.js` + `hotboard.js` (e.g. `engine.call('calculateAllValues', rosters, extras, true)`, `engine.get('IP_MAX')`).

- [ ] **Step 1: Write the failing test**

```js
// audit/test/engine.test.js
const test = require('node:test');
const assert = require('node:assert');
const { loadEngine } = require('../lib/engine');

test('engine exposes shared.js constants and functions', () => {
  const e = loadEngine();
  assert.strictEqual(e.get('IP_MAX'), 1500);
  assert.strictEqual(e.call('normalizeName', 'José Ramírez'), 'jose ramirez');
});

test('setDate drives rosProrationFactor', () => {
  const e = loadEngine();
  e.setDate('2026-03-01'); assert.strictEqual(e.call('rosProrationFactor'), 1);
  e.setDate('2026-10-01'); assert.strictEqual(e.call('rosProrationFactor'), 0);
  e.setDate('2026-06-27');
  const f = e.call('rosProrationFactor');
  assert.ok(f > 0.45 && f < 0.55, `mid-season factor ${f}`);
});

test('hotboard.js is loaded too', () => {
  const e = loadEngine();
  assert.strictEqual(e.call('hotClassifyRole', 10, 10), 'SP');
});

test('buildStandings ranks a toy league', () => {
  const e = loadEngine();
  const mk = (name, x) => ({ name, stats: { OBP: x, SLG: x, HR: x, R: x, ERA: 5 - x, WHIP: 5 - x, HR9: 5 - x, SO: x } });
  const s = e.call('buildStandings', [mk('a', 1), mk('b', 3), mk('c', 2)]);
  assert.deepStrictEqual(s.map(t => t.name), ['b', 'c', 'a']);
});
```

- [ ] **Step 2: Run it** — `node --test audit/test/engine.test.js` → FAIL (`Cannot find module '../lib/engine'`).

- [ ] **Step 3: Implement**

```js
// audit/lib/engine.js
// Loads the suite's browser scripts (shared.js, hotboard.js) into a Node vm
// context so the audit uses the exact same valuation code as the pages.
// Shims: localStorage (in-memory), window/document stubs, quiet console, and a
// Date whose "now" is settable so rosProrationFactor() can replay any day.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..', '..');
const SCRIPTS = ['shared.js', 'hotboard.js'];

function loadEngine() {
  let nowMs = Date.now();
  const RealDate = Date;
  class FixedDate extends RealDate {
    constructor(...a) { if (a.length === 0) super(nowMs); else super(...a); }
    static now() { return nowMs; }
  }
  const store = new Map();
  const ctx = {
    Date: FixedDate, Math, JSON, Set, Map, Object, Array, Number, String, parseFloat, parseInt, isNaN,
    console: { log() {}, warn() {}, error: console.error },
    localStorage: {
      getItem: k => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: k => store.delete(k),
    },
    window: { location: { hostname: '', pathname: '', protocol: 'file:' } },
    document: { getElementById: () => null },
    fetch: () => Promise.reject(new Error('fetch disabled in audit engine')),
  };
  vm.createContext(ctx);
  for (const f of SCRIPTS) {
    vm.runInContext(fs.readFileSync(path.join(ROOT, f), 'utf8'), ctx, { filename: f });
  }
  const get = name => vm.runInContext(name, ctx);
  return {
    setDate(iso) { nowMs = new RealDate(iso + 'T12:00:00').getTime(); },
    get,
    call(name, ...args) { return get(name)(...args); },
    localStorage: ctx.localStorage,
  };
}

module.exports = { loadEngine };
```

- [ ] **Step 4: Run it** — `node --test audit/test/engine.test.js` → PASS (4 tests).
- [ ] **Step 5:** Append `audit/cache/` to `.gitignore`.
- [ ] **Step 6: Commit** `git add audit/lib/engine.js audit/test/engine.test.js .gitignore && git commit -m "feat(audit): load shared.js + hotboard.js into a Node vm with date replay"`

---

### Task 2: Transactions → moves (trades, swaps)

**Files:**
- Create: `audit/lib/moves.js`
- Create: `audit/test/moves.test.js`

**Interfaces:**
- Produces:
  - `parseTransactions(csvText) → Tx[]` sorted **oldest first**; `Tx = { ts: 'YYYY-MM-DDTHH:MM:SS', date: 'YYYY-MM-DD', type: 'add'|'cut'|'move'|'increase', player, ottoneuId, teamId, team, fromTeamId, fromTeam, salary: number }`.
  - `seasonOf(date) → number` — offseason moves count toward the *next* season: Oct–Dec Y → Y+1; Jan–Sep Y → Y.
  - `buildMoves(txs) → Move[]`; `Move = { id, kind: 'add'|'auction'|'cut'|'swap'|'trade', season, ts, date, teamId, counterTeamId: string|null, tradeId: string|null, in: P[], out: P[] }`, `P = { player, ottoneuId, salary }`. **One Move per team per decision** (a trade yields two Moves sharing `tradeId`). `increase` rows produce no Move.

- [ ] **Step 1: Write the failing tests**

```js
// audit/test/moves.test.js
const test = require('node:test');
const assert = require('node:assert');
const { parseTransactions, buildMoves, seasonOf } = require('../lib/moves');

const H = 'date,type,player,ottoneuId,teamId,team,fromTeamId,fromTeam,salary\n';
const row = (ts, type, player, id, team, from = '', sal = 1) =>
  `${ts},${type},${player},${id},${team},T${team},${from},${from ? 'T' + from : ''},${sal}\n`;

test('parses and sorts oldest first', () => {
  const t = parseTransactions(H + row('2026-08-15T14:26:01', 'add', 'B', 2, 1) + row('2024-03-14T19:03:07', 'add', 'A', 1, 1, '', 35));
  assert.deepStrictEqual(t.map(x => x.player), ['A', 'B']);
  assert.strictEqual(t[0].salary, 35);
  assert.strictEqual(t[0].date, '2024-03-14');
});

test('commissioner adds ("add   (C)") parse as adds, flagged', () => {
  const t = parseTransactions(H + row('2024-05-18T12:13:02', 'add                 (C)', 'Ryne Nelson', 37826, 10897));
  assert.strictEqual(t[0].type, 'add');
  assert.strictEqual(t[0].commissioner, true);
});

test('seasonOf maps offseason to the right season', () => {
  assert.strictEqual(seasonOf('2026-06-01'), 2026);
  assert.strictEqual(seasonOf('2026-10-15'), 2027);
  assert.strictEqual(seasonOf('2027-01-20'), 2027);
});

test('trade rows sharing a timestamp group into one trade, two sides', () => {
  const csv = H +
    row('2026-08-15T14:26:01', 'move', 'Trout', 10, 10759, 20, 22) +
    row('2026-08-15T14:26:01', 'move', 'Schwellenbach', 11, 20, 10759, 5) +
    row('2026-08-15T14:26:01', 'move', 'Vaughn', 12, 10759, 20, 3);
  const m = buildMoves(parseTransactions(csv));
  assert.strictEqual(m.length, 2);
  const mine = m.find(x => x.teamId === '10759');
  assert.strictEqual(mine.kind, 'trade');
  assert.deepStrictEqual(mine.in.map(p => p.player).sort(), ['Trout', 'Vaughn']);
  assert.deepStrictEqual(mine.out.map(p => p.player), ['Schwellenbach']);
  assert.strictEqual(mine.counterTeamId, '20');
  assert.strictEqual(mine.tradeId, m.find(x => x.teamId === '20').tradeId);
});

test('two trades between different pairs in the same second stay separate', () => {
  const csv = H +
    row('2026-08-01T12:00:00', 'move', 'A', 1, 1, 2) + row('2026-08-01T12:00:00', 'move', 'B', 2, 2, 1) +
    row('2026-08-01T12:00:00', 'move', 'C', 3, 3, 4) + row('2026-08-01T12:00:00', 'move', 'D', 4, 4, 3);
  const m = buildMoves(parseTransactions(csv));
  assert.strictEqual(new Set(m.map(x => x.tradeId)).size, 2);
});

test('add + cut by one team within 30 min pair into a swap', () => {
  const csv = H + row('2026-09-27T13:47:40', 'cut', 'Cortes', 5, 10759) + row('2026-09-27T14:10:00', 'add', 'Gonzalez', 6, 10759, '', 3);
  const m = buildMoves(parseTransactions(csv));
  assert.strictEqual(m.length, 1);
  assert.strictEqual(m[0].kind, 'swap');
  assert.deepStrictEqual([m[0].in[0].player, m[0].out[0].player], ['Gonzalez', 'Cortes']);
});

test('add and cut 31 min apart stay separate; other team never pairs', () => {
  const csv = H + row('2026-09-27T13:00:00', 'cut', 'X', 5, 1) + row('2026-09-27T13:31:00', 'add', 'Y', 6, 1) + row('2026-09-27T13:05:00', 'add', 'Z', 7, 2);
  const kinds = buildMoves(parseTransactions(csv)).map(x => x.kind).sort();
  assert.deepStrictEqual(kinds, ['add', 'add', 'cut']);
});

test('March adds before Opening Day are auction buys; increases make no move', () => {
  const csv = H + row('2025-03-10T19:00:00', 'add', 'Ohtani', 1, 1, '', 44) + row('2025-10-06T00:00:00', 'increase', 'Ohtani', 1, 1, '', 46);
  const m = buildMoves(parseTransactions(csv));
  assert.deepStrictEqual(m.map(x => x.kind), ['auction']);
});
```

- [ ] **Step 2: Run** — `node --test audit/test/moves.test.js` → FAIL (module not found).

- [ ] **Step 3: Implement**

```js
// audit/lib/moves.js
// Ottoneu transaction rows -> decisions ("moves"). One Move per team per
// decision: a trade produces one Move for each side, sharing tradeId.
const SWAP_WINDOW_MS = 30 * 60 * 1000;
const OPENING_DAY_MMDD = '03-28';

function parseCSVLine(line) {
  const out = []; let cur = ''; let q = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (q) { if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') q = false; else cur += c; }
    else if (c === '"') q = true; else if (c === ',') { out.push(cur); cur = ''; } else cur += c;
  }
  out.push(cur); return out;
}

function parseTransactions(text) {
  const lines = text.replace(/\r/g, '').trim().split('\n');
  const head = parseCSVLine(lines[0]);
  return lines.slice(1).map(l => {
    const v = parseCSVLine(l); const r = {}; head.forEach((h, i) => { r[h] = v[i] ?? ''; });
    return {
      // Commissioner actions arrive as e.g. "add      (C)" -- same move, flagged.
      ts: r.date, date: r.date.slice(0, 10), type: r.type.trim().split(/\s+/)[0], commissioner: /\(C\)/.test(r.type), player: r.player,
      ottoneuId: String(r.ottoneuId), teamId: String(r.teamId), team: r.team,
      fromTeamId: r.fromTeamId ? String(r.fromTeamId) : '', fromTeam: r.fromTeam,
      salary: parseInt(String(r.salary).replace(/[$,]/g, ''), 10) || 0,
    };
  }).sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
}

function seasonOf(date) {
  const y = +date.slice(0, 4), m = +date.slice(5, 7);
  return m >= 10 ? y + 1 : y;
}

const P = t => ({ player: t.player, ottoneuId: t.ottoneuId, salary: t.salary });
const ms = ts => new Date(ts + 'Z').getTime();

function buildMoves(txs) {
  const moves = []; let n = 0;
  const base = (t, kind, teamId) => ({
    id: 'm' + (++n), kind, season: seasonOf(t.date), ts: t.ts, date: t.date,
    teamId, counterTeamId: null, tradeId: null, in: [], out: [],
  });

  // Trades: rows of type 'move' grouped by timestamp + unordered team pair.
  const tradeGroups = new Map();
  for (const t of txs.filter(x => x.type === 'move')) {
    const pair = [t.teamId, t.fromTeamId].sort().join('-');
    const key = t.ts + '|' + pair;
    if (!tradeGroups.has(key)) tradeGroups.set(key, []);
    tradeGroups.get(key).push(t);
  }
  let tn = 0;
  for (const rows of tradeGroups.values()) {
    const tradeId = 't' + (++tn);
    const [a, b] = rows[0].teamId < rows[0].fromTeamId ? [rows[0].teamId, rows[0].fromTeamId] : [rows[0].fromTeamId, rows[0].teamId];
    for (const [me, them] of [[a, b], [b, a]]) {
      const m = base(rows[0], 'trade', me);
      m.counterTeamId = them; m.tradeId = tradeId;
      m.in = rows.filter(r => r.teamId === me).map(P);
      m.out = rows.filter(r => r.fromTeamId === me).map(P);
      moves.push(m);
    }
  }

  // Adds / cuts, pairing same-team add+cut within the swap window (timestamp order).
  const addsCuts = txs.filter(x => x.type === 'add' || x.type === 'cut');
  const used = new Set();
  for (let i = 0; i < addsCuts.length; i++) {
    if (used.has(i)) continue;
    const t = addsCuts[i];
    let j = -1;
    for (let k = i + 1; k < addsCuts.length && ms(addsCuts[k].ts) - ms(t.ts) <= SWAP_WINDOW_MS; k++) {
      const u = addsCuts[k];
      if (!used.has(k) && u.teamId === t.teamId && u.type !== t.type) { j = k; break; }
    }
    if (j >= 0) {
      used.add(i); used.add(j);
      const add = t.type === 'add' ? t : addsCuts[j];
      const cut = t.type === 'cut' ? t : addsCuts[j];
      const m = base(t, 'swap', t.teamId); m.in = [P(add)]; m.out = [P(cut)];
      moves.push(m); continue;
    }
    used.add(i);
    const isAuction = t.type === 'add' && t.date.slice(5) < OPENING_DAY_MMDD && +t.date.slice(5, 7) >= 3;
    const m = base(t, t.type === 'cut' ? 'cut' : (isAuction ? 'auction' : 'add'), t.teamId);
    (t.type === 'add' ? m.in : m.out).push(P(t));
    moves.push(m);
  }
  return moves.sort((x, y) => (x.ts < y.ts ? -1 : x.ts > y.ts ? 1 : 0));
}

module.exports = { parseTransactions, buildMoves, seasonOf, parseCSVLine };
```

- [ ] **Step 4: Run** — `node --test audit/test/moves.test.js` → PASS (7 tests).
- [ ] **Step 5: Commit** `git add audit/lib/moves.js audit/test/moves.test.js && git commit -m "feat(audit): parse transactions into moves -- trades by timestamp+pair, 30-min swaps, auction"`

---

### Task 3: Roster replay + stints, checked against snapshots

**Files:**
- Create: `audit/lib/stints.js`
- Create: `audit/lib/gitdata.js`
- Create: `audit/test/stints.test.js`

**Interfaces:**
- Consumes: `Tx[]` from Task 2.
- Produces:
  - `replayRosters(txs) → { stints: Stint[], rosterAt(isoTs) → Map<ottoneuId, {teamId, salary}> }`; `Stint = { ottoneuId, player, teamId, salary, start: 'YYYY-MM-DD', end: 'YYYY-MM-DD'|null }` (end exclusive, null = still rostered). Salary changes (`increase`) close the stint and open a new one with the new salary.
  - `diffAgainstSnapshot(rosterMap, snapshotRows) → { missing: [], extra: [], wrongTeam: [] }` where `snapshotRows` = `[{ ottoneuId, teamId }]`.
  - `gitdata.js`: `fileHistory(relPath) → [{ sha, date }]` oldest first (one per date, last commit that day); `fileAt(sha, relPath) → string`; `latestOnOrBefore(history, date) → {sha,date}|null`.

- [ ] **Step 1: Write the failing tests**

```js
// audit/test/stints.test.js
const test = require('node:test');
const assert = require('node:assert');
const { replayRosters, diffAgainstSnapshot } = require('../lib/stints');
const { latestOnOrBefore } = require('../lib/gitdata');

const tx = (ts, type, id, teamId, fromTeamId = '', salary = 1) =>
  ({ ts, date: ts.slice(0, 10), type, player: 'P' + id, ottoneuId: String(id), teamId: String(teamId), fromTeamId: String(fromTeamId), salary });

test('add -> trade -> cut produces two stints', () => {
  const { stints } = replayRosters([
    tx('2026-04-01T10:00:00', 'add', 1, 'A', '', 5),
    tx('2026-06-01T10:00:00', 'move', 1, 'B', 'A', 5),
    tx('2026-07-01T10:00:00', 'cut', 1, 'B', '', 5),
  ]);
  assert.deepStrictEqual(stints.map(s => [s.teamId, s.start, s.end]), [['A', '2026-04-01', '2026-06-01'], ['B', '2026-06-01', '2026-07-01']]);
});

test('increase splits a stint at the new salary', () => {
  const { stints } = replayRosters([tx('2025-03-14T10:00:00', 'add', 1, 'A', '', 10), tx('2025-10-06T00:00:00', 'increase', 1, 'A', '', 12)]);
  assert.deepStrictEqual(stints.map(s => [s.salary, s.end]), [[10, '2025-10-06'], [12, null]]);
});

test('rosterAt reflects state at a timestamp', () => {
  const r = replayRosters([tx('2026-04-01T10:00:00', 'add', 1, 'A'), tx('2026-05-01T10:00:00', 'cut', 1, 'A')]);
  assert.strictEqual(r.rosterAt('2026-04-15T00:00:00').get('1').teamId, 'A');
  assert.strictEqual(r.rosterAt('2026-05-02T00:00:00').has('1'), false);
});

test('diffAgainstSnapshot finds missing, extra, wrong team', () => {
  const m = new Map([['1', { teamId: 'A' }], ['2', { teamId: 'B' }]]);
  const d = diffAgainstSnapshot(m, [{ ottoneuId: '1', teamId: 'A' }, { ottoneuId: '2', teamId: 'C' }, { ottoneuId: '3', teamId: 'A' }]);
  assert.deepStrictEqual([d.missing, d.extra, d.wrongTeam.map(x => x.ottoneuId)], [['3'], [], ['2']]);
});

test('latestOnOrBefore never looks forward', () => {
  const h = [{ sha: 'a', date: '2026-06-01' }, { sha: 'b', date: '2026-06-03' }];
  assert.strictEqual(latestOnOrBefore(h, '2026-06-02').sha, 'a');
  assert.strictEqual(latestOnOrBefore(h, '2026-05-31'), null);
});
```

- [ ] **Step 2: Run** — `node --test audit/test/stints.test.js` → FAIL.

- [ ] **Step 3: Implement `audit/lib/stints.js`**

```js
// audit/lib/stints.js
// Replays every transaction since the league's first auction to rebuild who
// owned whom, when, at what salary. Ownership intervals are "stints".
function replayRosters(txs) {
  const open = new Map();            // ottoneuId -> open stint
  const stints = [];
  const events = [];                 // [ts, ottoneuId, teamId|null, salary]
  const close = (id, date) => { const s = open.get(id); if (s) { s.end = date; open.delete(id); } };
  const openStint = (t, teamId, salary) => {
    const s = { ottoneuId: t.ottoneuId, player: t.player, teamId, salary, start: t.date, end: null };
    open.set(t.ottoneuId, s); stints.push(s);
  };
  for (const t of txs) {
    if (t.type === 'add') { close(t.ottoneuId, t.date); openStint(t, t.teamId, t.salary); events.push([t.ts, t.ottoneuId, t.teamId, t.salary]); }
    else if (t.type === 'cut') { close(t.ottoneuId, t.date); events.push([t.ts, t.ottoneuId, null, 0]); }
    else if (t.type === 'move') { close(t.ottoneuId, t.date); openStint(t, t.teamId, t.salary); events.push([t.ts, t.ottoneuId, t.teamId, t.salary]); }
    else if (t.type === 'increase') {
      const cur = open.get(t.ottoneuId);
      const teamId = cur ? cur.teamId : t.teamId;
      close(t.ottoneuId, t.date); openStint(t, teamId, t.salary); events.push([t.ts, t.ottoneuId, teamId, t.salary]);
    }
  }
  function rosterAt(ts) {
    const m = new Map();
    for (const [ets, id, teamId, salary] of events) {
      if (ets > ts) break;
      if (teamId === null) m.delete(id); else m.set(id, { teamId, salary });
    }
    return m;
  }
  return { stints, rosterAt };
}

function diffAgainstSnapshot(rosterMap, snapshotRows) {
  const snap = new Map(snapshotRows.map(r => [String(r.ottoneuId), String(r.teamId)]));
  const missing = [...snap.keys()].filter(id => !rosterMap.has(id));
  const extra = [...rosterMap.keys()].filter(id => !snap.has(id));
  const wrongTeam = [...snap.entries()]
    .filter(([id, team]) => rosterMap.has(id) && rosterMap.get(id).teamId !== team)
    .map(([ottoneuId, expected]) => ({ ottoneuId, expected, got: rosterMap.get(ottoneuId).teamId }));
  return { missing, extra, wrongTeam };
}

module.exports = { replayRosters, diffAgainstSnapshot };
```

- [ ] **Step 4: Implement `audit/lib/gitdata.js`**

```js
// audit/lib/gitdata.js
// Read dated snapshots of data/*.csv out of git history (Apps Script commits daily).
const { execFileSync } = require('child_process');
const path = require('path');
const ROOT = path.join(__dirname, '..', '..');
const git = args => execFileSync('git', ['-C', ROOT, ...args], { encoding: 'utf8', maxBuffer: 1 << 28 });

function fileHistory(relPath) {
  const out = git(['log', '--reverse', '--format=%H %ad', '--date=short', '--', relPath]).trim();
  const byDate = new Map();
  for (const line of out.split('\n').filter(Boolean)) {
    const [sha, date] = line.split(' ');
    byDate.set(date, sha);        // later commit the same day wins
  }
  return [...byDate.entries()].map(([date, sha]) => ({ sha, date }));
}

function fileAt(sha, relPath) { return git(['show', `${sha}:${relPath}`]); }

function latestOnOrBefore(history, date) {
  let best = null;
  for (const h of history) { if (h.date <= date) best = h; else break; }
  return best;
}

module.exports = { fileHistory, fileAt, latestOnOrBefore };
```

- [ ] **Step 5: Run** — `node --test audit/test/stints.test.js` → PASS (5 tests).
- [ ] **Step 6: Real-data check** (prints, doesn't assert):

```bash
node -e "const fs=require('fs');const {parseTransactions}=require('./audit/lib/moves');const {replayRosters,diffAgainstSnapshot}=require('./audit/lib/stints');const g=require('./audit/lib/gitdata');const {parseCSVLine}=require('./audit/lib/moves');const r=replayRosters(parseTransactions(fs.readFileSync('data/transactions.csv','utf8')));const h=g.fileHistory('data/roster.csv');for(const s of [h[0],h[Math.floor(h.length/2)],h.at(-1)]){const L=g.fileAt(s.sha,'data/roster.csv').replace(/\r/g,'').trim().split('\n');const H=parseCSVLine(L[0]);const iT=H.indexOf('TeamID'),iO=H.indexOf('ottoneu ID');const rows=L.slice(1).map(l=>{const v=parseCSVLine(l);return{ottoneuId:v[iO],teamId:v[iT]}});const d=diffAgainstSnapshot(r.rosterAt(s.date+'T23:59:59'),rows);console.log(s.date,rows.length,'missing',d.missing.length,'extra',d.extra.length,'wrongTeam',d.wrongTeam.length)}"
```

Expected: small numbers (snapshot time-of-day vs transaction time can differ by a few moves). **If any count is > 15, stop** and inspect a few ids — it means the transactions file is incomplete or the replay is wrong; report to the user before continuing.

- [ ] **Step 7: Commit** `git add audit/lib/stints.js audit/lib/gitdata.js audit/test/stints.test.js && git commit -m "feat(audit): replay rosters into stints; git snapshot readers; cross-check vs roster.csv"`

---

### Task 4: MLB daily stats cache + player identity

**Files:**
- Create: `audit/lib/stats.js`
- Create: `audit/lib/identity.js`
- Create: `audit/test/stats.test.js`
- Create: `audit/test/identity.test.js`

**Interfaces:**
- Produces:
  - `fetchDay(date, cacheDir) → Promise<DayFile>` (cached at `<cacheDir>/stats/<date>.json`; returns cached file without network if present). `DayFile = { h: [[mlbId, name, pa, ab, h, bb, hbp, sf, hr, r, tb]], p: [[mlbId, name, outs, so, er, bb, h, hr, g, gs]] }`.
  - `seasonDays(season) → string[]` — every date Mar 15 … Oct 5.
  - `sumWindow(days: DayFile[], mlbId, group: 'h'|'p') → Line|null`; `Line` hitter `{ pa, ab, h, bb, hbp, sf, hr, r, tb, obp, slg }`, pitcher `{ ip, outs, so, er, bb, h, hr, g, gs, era, whip, hr9 }`. Rates are 0 when denominators are 0 (never NaN).
  - `buildIdentity(dayFiles, players: [{ottoneuId, player, hint?: 'H'|'P'}]) → { map: Map<ottoneuId, {mlbId, group}>, ambiguous: [], unmatched: [] }`.

- [ ] **Step 1: Probe the API once** (confirms field names and whether `limit=1000` works without paging):

```bash
node -e "fetch('https://statsapi.mlb.com/api/v1/stats?stats=byDateRange&group=hitting&startDate=2026-06-10&endDate=2026-06-10&sportId=1&gameType=R&playerPool=all&limit=1000').then(r=>r.json()).then(j=>{const s=j.stats[0].splits;console.log(s.length,Object.keys(s[0].stat).join(','),s[0].player.id,s[0].player.fullName)})"
```

Expected: a few hundred splits; keys include `plateAppearances,atBats,hits,baseOnBalls,hitByPitch,sacFlies,homeRuns,runs,totalBases`. Repeat with `group=pitching` and check `outs,strikeOuts,earnedRuns,baseOnBalls,hits,homeRuns,gamesPitched,gamesStarted`. **If `splits.length` equals exactly 1000, paging is needed** — keep the `offset` loop below; otherwise it still runs once per group.

- [ ] **Step 2: Write the failing tests**

```js
// audit/test/stats.test.js
const test = require('node:test');
const assert = require('node:assert');
const { sumWindow, seasonDays } = require('../lib/stats');

const day = (pa, hr) => ({ h: [[7, 'Juan Soto', pa, pa - 1, 1, 1, 0, 0, hr, 1, 4]], p: [[9, 'Arm', 18, 7, 2, 1, 4, 1, 1, 1]] });

test('sumWindow sums counting stats and derives rates', () => {
  const l = sumWindow([day(4, 1), day(5, 0)], 7, 'h');
  assert.strictEqual(l.pa, 9); assert.strictEqual(l.hr, 1);
  assert.ok(Math.abs(l.obp - (2 + 2 + 0) / (7 + 2 + 0 + 0)) < 1e-9);
  const p = sumWindow([day(1, 0), day(1, 0)], 9, 'p');
  assert.strictEqual(p.ip, 12); assert.ok(Math.abs(p.era - 4 * 9 / 12) < 1e-9);
});

test('player with no games -> null; zero denominators -> 0 rates', () => {
  assert.strictEqual(sumWindow([day(4, 1)], 999, 'h'), null);
  const z = sumWindow([{ h: [[7, 'x', 0, 0, 0, 0, 0, 0, 0, 0, 0]], p: [] }], 7, 'h');
  assert.strictEqual(z.obp, 0); assert.strictEqual(z.slg, 0);
});

test('seasonDays spans Mar 15 to Oct 5', () => {
  const d = seasonDays(2026);
  assert.strictEqual(d[0], '2026-03-15'); assert.strictEqual(d.at(-1), '2026-10-05');
});
```

```js
// audit/test/identity.test.js
const test = require('node:test');
const assert = require('node:assert');
const { buildIdentity } = require('../lib/identity');

const days = [{
  h: [[1, 'Will Smith', 500, 0, 0, 0, 0, 0, 0, 0, 0], [3, 'José Ramírez', 600, 0, 0, 0, 0, 0, 0, 0, 0]],
  p: [[2, 'Will Smith', 180, 0, 0, 0, 0, 0, 60, 0]],
}];

test('unique names match regardless of accents', () => {
  const r = buildIdentity(days, [{ ottoneuId: 'a', player: 'Jose Ramirez' }]);
  assert.deepStrictEqual(r.map.get('a'), { mlbId: 3, group: 'h' });
});

test('same name in both groups: hint wins, and the case is reported', () => {
  const r = buildIdentity(days, [{ ottoneuId: 'p', player: 'Will Smith', hint: 'P' }, { ottoneuId: 'h', player: 'Will Smith', hint: 'H' }]);
  assert.strictEqual(r.map.get('p').mlbId, 2);
  assert.strictEqual(r.map.get('h').mlbId, 1);
  assert.strictEqual(r.ambiguous.length, 2);
});

test('no MLB stats -> unmatched (a legit zero line for prospects), never a crash', () => {
  const r = buildIdentity(days, [{ ottoneuId: 'z', player: 'Unknown Prospect' }]);
  assert.strictEqual(r.map.has('z'), false);
  assert.deepStrictEqual(r.unmatched.map(u => u.ottoneuId), ['z']);
});
```

- [ ] **Step 3: Run** — `node --test audit/test/stats.test.js audit/test/identity.test.js` → FAIL.

- [ ] **Step 4: Implement `audit/lib/stats.js`**

```js
// audit/lib/stats.js
// One compact file per day of MLB stats (all players), fetched once and cached.
// Any ownership window is then a sum over cached days.
const fs = require('fs');
const path = require('path');

const API = 'https://statsapi.mlb.com/api/v1/stats?stats=byDateRange&sportId=1&gameType=R&playerPool=all&limit=1000';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function fetchGroup(group, date) {
  let out = [];
  for (let offset = 0; offset < 10000; offset += 1000) {
    const res = await fetch(`${API}&group=${group}&startDate=${date}&endDate=${date}&offset=${offset}`);
    if (!res.ok) throw new Error(`MLB API ${res.status} for ${group} ${date}`);
    const splits = ((await res.json()).stats?.[0]?.splits) || [];
    out = out.concat(splits);
    if (splits.length < 1000) break;
    await sleep(250);
  }
  return out;
}

const n = v => +v || 0;

async function fetchDay(date, cacheDir) {
  const file = path.join(cacheDir, 'stats', date + '.json');
  if (fs.existsSync(file)) return JSON.parse(fs.readFileSync(file, 'utf8'));
  const [hs, ps] = [await fetchGroup('hitting', date), await fetchGroup('pitching', date)];
  const day = {
    h: hs.map(s => { const t = s.stat; return [s.player.id, s.player.fullName, n(t.plateAppearances), n(t.atBats), n(t.hits), n(t.baseOnBalls), n(t.hitByPitch), n(t.sacFlies), n(t.homeRuns), n(t.runs), n(t.totalBases)]; }),
    p: ps.map(s => { const t = s.stat; return [s.player.id, s.player.fullName, n(t.outs), n(t.strikeOuts), n(t.earnedRuns), n(t.baseOnBalls), n(t.hits), n(t.homeRuns), n(t.gamesPitched), n(t.gamesStarted)]; }),
  };
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(day));
  await sleep(250);
  return day;
}

function seasonDays(season) {
  const out = []; const d = new Date(Date.UTC(season, 2, 15)); const end = Date.UTC(season, 9, 5);
  while (d.getTime() <= end) { out.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() + 1); }
  return out;
}

const H_KEYS = ['pa', 'ab', 'h', 'bb', 'hbp', 'sf', 'hr', 'r', 'tb'];
const P_KEYS = ['outs', 'so', 'er', 'bb', 'h', 'hr', 'g', 'gs'];

function sumWindow(days, mlbId, group) {
  const keys = group === 'h' ? H_KEYS : P_KEYS;
  const acc = Object.fromEntries(keys.map(k => [k, 0])); let seen = false;
  for (const d of days) for (const row of d[group]) {
    if (row[0] !== mlbId) continue;
    seen = true; keys.forEach((k, i) => { acc[k] += row[i + 2]; });
  }
  if (!seen) return null;
  if (group === 'h') {
    const den = acc.ab + acc.bb + acc.hbp + acc.sf;
    acc.obp = den ? (acc.h + acc.bb + acc.hbp) / den : 0;
    acc.slg = acc.ab ? acc.tb / acc.ab : 0;
  } else {
    acc.ip = acc.outs / 3;
    acc.era = acc.ip ? acc.er * 9 / acc.ip : 0;
    acc.whip = acc.ip ? (acc.bb + acc.h) / acc.ip : 0;
    acc.hr9 = acc.ip ? acc.hr * 9 / acc.ip : 0;
  }
  return acc;
}

module.exports = { fetchDay, seasonDays, sumWindow };
```

- [ ] **Step 5: Implement `audit/lib/identity.js`**

```js
// audit/lib/identity.js
// Ottoneu player -> MLB player id, by normalized name. Same-name collisions are
// resolved by hint (H/P from roster positions) then by playing volume, and are
// always reported. No MLB stats at all = unmatched (a real zero for prospects).
const norm = s => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  .replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();

function buildIdentity(dayFiles, players) {
  const idx = new Map();   // normName -> Map(mlbId|group -> {mlbId, group, vol})
  for (const d of dayFiles) for (const group of ['h', 'p']) for (const row of d[group]) {
    const k = norm(row[1]); if (!idx.has(k)) idx.set(k, new Map());
    const key = row[0] + '|' + group; const m = idx.get(k);
    const cur = m.get(key) || { mlbId: row[0], group, vol: 0 };
    cur.vol += row[2]; m.set(key, cur);
  }
  const map = new Map(), ambiguous = [], unmatched = [];
  for (const p of players) {
    const cands = [...(idx.get(norm(p.player))?.values() || [])];
    if (!cands.length) { unmatched.push(p); continue; }
    let pick = cands;
    if (cands.length > 1) {
      ambiguous.push({ ...p, candidates: cands.map(c => c.mlbId + c.group) });
      const want = p.hint === 'P' ? 'p' : p.hint === 'H' ? 'h' : null;
      if (want && cands.some(c => c.group === want)) pick = cands.filter(c => c.group === want);
    }
    const best = pick.sort((a, b) => b.vol - a.vol)[0];
    map.set(p.ottoneuId, { mlbId: best.mlbId, group: best.group });
  }
  return { map, ambiguous, unmatched };
}

module.exports = { buildIdentity, norm };
```

Note: a two-way player (Ohtani) is matched to his higher-volume group; `result.js` (Task 5) adds his other group's line when it has ≥ `TWO_WAY_IP_MIN` innings.

- [ ] **Step 6: Run** — `node --test audit/test/stats.test.js audit/test/identity.test.js` → PASS (6 tests).
- [ ] **Step 7: Commit** `git add audit/lib/stats.js audit/lib/identity.js audit/test/stats.test.js audit/test/identity.test.js && git commit -m "feat(audit): cached MLB daily stats, window sums, name-based identity with collision report"`

---

### Task 5: Result valuation

**Files:**
- Create: `audit/lib/result.js`
- Create: `audit/test/result.test.js`

**Interfaces:**
- Consumes: `engine` (Task 1), `sumWindow` (Task 4), stints (Task 3), identity map (Task 4).
- Produces:
  - `seasonContext(engine, { finalTeams, stintLines, freeAgentLines }) → Ctx`; `finalTeams = [{ teamId, stats: {OBP,SLG,HR,R,ERA,WHIP,HR9,SO}, ip }]`, `stintLines = [{ type: 'H'|'P', line }]` (every stint in the season), `freeAgentLines` = season lines of players never rostered that season. `Ctx = { sgpDenom, avgPA, avgIP, repl: {H, P}, rate }`.
  - `lineValue(engine, ctx, type, line) → $` (`0` for null line; can be negative).
  - `fracOfSeason(season, start, end) → 0..1` — share of Mar 28–Sep 28 inside `[start, end)`.
  - `moveResult(engine, ctx, move, lookup) → number` where `lookup(ottoneuId, startDate, endDate) → { type, line }` returns the player's production in the window (null line if none).

- [ ] **Step 1: Write the failing tests**

```js
// audit/test/result.test.js
const test = require('node:test');
const assert = require('node:assert');
const { loadEngine } = require('../lib/engine');
const { seasonContext, lineValue, fracOfSeason, moveResult } = require('../lib/result');

const e = loadEngine();
const team = (x) => ({ teamId: 't' + x, ip: 1400, stats: { OBP: .32 + x / 1000, SLG: .42 + x / 500, HR: 200 + x * 5, R: 800 + x * 10, ERA: 4 - x / 20, WHIP: 1.25 - x / 200, HR9: 1.2 - x / 100, SO: 1300 + x * 10 } });
const H = (pa, hr, r, obp, slg) => ({ type: 'H', line: { pa, hr, r, obp, slg } });
const P = (ip, so, era, whip, hr9) => ({ type: 'P', line: { ip, so, era, whip, hr9 } });
const ctx = seasonContext(e, {
  finalTeams: Array.from({ length: 12 }, (_, i) => team(i)),
  stintLines: [H(600, 35, 100, .37, .55), H(550, 20, 80, .33, .44), P(180, 200, 3.2, 1.1, 1.0), P(60, 70, 3.0, 1.1, .9)],
  freeAgentLines: [H(300, 8, 35, .30, .38), H(250, 6, 30, .30, .37), P(80, 70, 4.4, 1.3, 1.3), P(50, 45, 4.5, 1.35, 1.4)],
});

test('context: positive rate, replacement from free agents', () => {
  assert.ok(ctx.rate > 0);
  assert.ok(ctx.repl.H.obp < .32);
});

test('a star line is worth more than a scrub line; null is 0; scrub can be negative', () => {
  const star = lineValue(e, ctx, 'H', H(600, 35, 100, .37, .55).line);
  const scrub = lineValue(e, ctx, 'H', H(200, 2, 15, .26, .30).line);
  assert.ok(star > 10 && star > scrub);
  assert.ok(scrub < 0);
  assert.strictEqual(lineValue(e, ctx, 'H', null), 0);
});

test('zero-PA line is finite', () => {
  assert.ok(Number.isFinite(lineValue(e, ctx, 'H', { pa: 0, hr: 0, r: 0, obp: 0, slg: 0 })));
});

test('fracOfSeason', () => {
  assert.strictEqual(fracOfSeason(2026, '2026-01-01', null), 1);
  const half = fracOfSeason(2026, '2026-06-27', null);
  assert.ok(half > .45 && half < .55);
  assert.strictEqual(fracOfSeason(2026, '2026-10-01', null), 0);
});

test('cut result: freed salary minus what the player did afterward', () => {
  const move = { kind: 'cut', season: 2026, date: '2026-06-27', in: [], out: [{ ottoneuId: 'x', salary: 20 }] };
  const look = () => ({ type: 'H', line: { pa: 0, hr: 0, r: 0, obp: 0, slg: 0 } });   // did nothing after
  const r = moveResult(e, ctx, move, look);
  assert.ok(r > 0 && r < 20);   // ~half salary × half season freed, minus ~0 lost
});
```

- [ ] **Step 2: Run** — `node --test audit/test/result.test.js` → FAIL.

- [ ] **Step 3: Implement**

```js
// audit/lib/result.js
// "Result" grades: what actually happened, in the suite's dollars.
// SGP denominators come from the real final standings; replacement is the
// averaged top free-agent cohort by actual production (same rule as shared.js
// FA baselines); $/SGP spreads the league pool over all rostered production.
const SEASON_START = '-03-28', SEASON_END = '-09-28';
const DAY = 86400000;
const t = d => new Date(d + 'T00:00:00Z').getTime();

function fracOfSeason(season, start, end) {
  const s0 = t(season + SEASON_START), s1 = t(season + SEASON_END);
  const a = Math.max(s0, t(start)), b = Math.min(s1, end ? t(end) : s1);
  return b > a ? (b - a) / (s1 - s0) : 0;
}

function sgpOf(engine, ctx, type, line) {
  if (!line) return 0;
  const repl = ctx.repl[type];
  if (!repl) return 0;
  return engine.call('calcPlayerSGP', { type }, line, repl, ctx.sgpDenom, ctx.avgPA, ctx.avgIP);
}

function seasonContext(engine, { finalTeams, stintLines, freeAgentLines }) {
  const sgpDenom = engine.call('calcSGPDenoms', finalTeams.map(x => x.stats));
  const avgPA = engine.get('PA_PER_SLOT') * engine.get('HITTER_SLOTS').length;
  const ips = finalTeams.map(x => x.ip).filter(Boolean);
  const avgIP = ips.length ? ips.reduce((a, b) => a + b, 0) / ips.length : engine.get('IP_MAX');
  const cohort = (type, minVol, size, fields) => {
    const vol = type === 'H' ? 'pa' : 'ip';
    const pool = freeAgentLines.filter(x => x.type === type && (x.line[vol] || 0) >= minVol)
      .map(x => ({ type, proj: x.line }))
      .sort((a, b) => engine.call('valProxy', b, b.proj) - engine.call('valProxy', a, a.proj))
      .slice(0, size);
    return pool.length ? engine.call('avgCohortStats', pool, fields) : null;
  };
  const repl = {
    H: cohort('H', engine.get('FA_MIN_PA'), engine.get('FA_COHORT_H'), ['pa', 'hr', 'r', 'obp', 'slg']),
    P: cohort('P', engine.get('FA_MIN_IP'), engine.get('FA_COHORT_P'), ['ip', 'so', 'era', 'whip', 'hr9']),
  };
  const ctx = { sgpDenom, avgPA, avgIP, repl, rate: 0 };
  const totalPos = stintLines.reduce((s, x) => s + Math.max(0, sgpOf(engine, ctx, x.type, x.line)), 0);
  const pool = engine.get('SALARY_POOL') - engine.get('NUM_TEAMS') * 40;   // $1 floor per roster spot
  ctx.rate = totalPos > 0 ? pool / totalPos : 0;
  return ctx;
}

function lineValue(engine, ctx, type, line) { return sgpOf(engine, ctx, type, line) * ctx.rate; }

const seasonEnd = s => s + SEASON_END;
const inSeason = d => d.slice(5) >= SEASON_START.slice(1) && d.slice(5) < SEASON_END.slice(1);

// lookup(ottoneuId, start, end) -> { type, line } for production in [start, end).
// moveEnd(ottoneuId) -> the date the player left the acquiring team (or null).
function moveResult(engine, ctx, move, lookup, moveEnd = () => null) {
  const s = move.season, d = move.date;
  const cutFactor = inSeason(d) ? 0.5 : 1;
  let total = 0;
  for (const p of move.in) {
    const end = moveEnd(p.ottoneuId) || seasonEnd(s);
    const { type, line } = lookup(p.ottoneuId, d, end);
    total += lineValue(engine, ctx, type, line) - p.salary * fracOfSeason(s, d, end);
  }
  for (const p of move.out) {
    const { type, line } = lookup(p.ottoneuId, d, seasonEnd(s));
    const lost = lineValue(engine, ctx, type, line);
    const freed = move.kind === 'trade' ? p.salary : p.salary * cutFactor;
    total += freed * fracOfSeason(s, d, null) - lost;
  }
  return total;
}

module.exports = { seasonContext, lineValue, fracOfSeason, moveResult, inSeason };
```

- [ ] **Step 4: Run** — `node --test audit/test/result.test.js` → PASS (5 tests). If `HITTER_SLOTS`, `FA_MIN_PA` etc. are not reachable via `engine.get`, they are `const` in `shared.js` — `vm.runInContext(name)` does reach top-level `const`; if a test shows `undefined`, print `engine.get('typeof HITTER_SLOTS')` to diagnose before changing anything.
- [ ] **Step 5: Commit** `git add audit/lib/result.js audit/test/result.test.js && git commit -m "feat(audit): result grades -- actual production in suite dollars vs final-standings SGP"`

---

### Task 6: Process valuation (2026 snapshots)

**Files:**
- Create: `audit/lib/process.js`
- Create: `audit/test/process.test.js`

**Interfaces:**
- Consumes: `engine`, `gitdata` (`fileHistory`, `fileAt`, `latestOnOrBefore`).
- Produces:
  - `PROCESS_FROM = '2026-05-24'`, `PROCESS_TO = '2026-09-28'`.
  - `makeValuer(engine, snapshots) → valuer`; `snapshots = { roster: History, hit: History, pit: History, read(sha, path) → text }`.
  - `valuer.valuesAsOf(date) → { values: Map<key, {projectedValue, actualSalary}>, keyOf(ottoneuId, name) → key|null, benchBest(teamId, type, excludeOttoneuId) → ottoneuId|null } | null` — uses the latest snapshot **strictly before** `date` (state before the move). Cached per date.
  - `moveProcess(engine, valuer, move) → number|null` — null outside `[PROCESS_FROM, PROCESS_TO)` or when no snapshot exists.

- [ ] **Step 1: Write the failing test** (pure logic with fake snapshots — no git)

```js
// audit/test/process.test.js
const test = require('node:test');
const assert = require('node:assert');
const { loadEngine } = require('../lib/engine');
const { makeValuer, moveProcess } = require('../lib/process');

const ROSTER_H = 'TeamID,"Team Name","ottoneu ID","FG MajorLeagueID","FG MinorLeagueID",Name,"MLB Team",Position(s),Salary\n';
const rosterRows = [];
for (let t = 0; t < 12; t++) for (let i = 0; i < 4; i++) {
  rosterRows.push(`${100 + t},"T${t}",${t * 10 + i},${t * 10 + i},,"H${t}_${i}",NYY,OF,$${5 + i}`);
  rosterRows.push(`${100 + t},"T${t}",${500 + t * 10 + i},${500 + t * 10 + i},,"P${t}_${i}",NYY,SP,$${5 + i}`);
}
const roster = ROSTER_H + rosterRows.join('\n');
const hit = 'Name,Team,PA,AB,H,HR,R,BB,HBP,OBP,SLG,fgId\n' +
  rosterRows.filter(r => r.includes('"H')).map((r, k) => { const id = r.split(',')[2]; return `"H${Math.floor(id / 10)}_${id % 10}",NYY,${300 + k},${270 + k},70,${10 + k % 20},${40 + k % 30},25,3,.330,.430,${id}`; }).join('\n') +
  '\n"FA Bat",NYY,400,360,90,25,60,30,3,.360,.520,9999\n"FA Scrub",NYY,200,180,40,3,20,15,1,.290,.350,9998';
const pit = 'Name,Team,GS,G,IP,ER,HR,SO,BB,HR/9,WHIP,ERA,fgId\n' +
  rosterRows.filter(r => r.includes('"P')).map((r, k) => { const id = r.split(',')[2]; return `"P${Math.floor((id - 500) / 10)}_${(id - 500) % 10}",NYY,15,15,${80 + k},35,10,${80 + k},25,1.1,1.2,${3.5 + (k % 10) / 10},${id}`; }).join('\n');

const snap = (date) => [{ sha: 's', date }];
const snapshots = { roster: snap('2026-06-01'), hit: snap('2026-06-01'), pit: snap('2026-06-01'),
  read: (sha, p) => (p.endsWith('roster.csv') ? roster : p.endsWith('hitting.csv') ? hit : pit) };

test('add of a strong FA has positive process; scrub negative-ish', () => {
  const e = loadEngine(); const v = makeValuer(e, snapshots);
  const good = moveProcess(e, v, { kind: 'add', date: '2026-06-10', in: [{ ottoneuId: 'x', player: 'FA Bat', salary: 1 }], out: [] });
  const bad = moveProcess(e, v, { kind: 'add', date: '2026-06-10', in: [{ ottoneuId: 'y', player: 'FA Scrub', salary: 10 }], out: [] });
  assert.ok(good > bad, `${good} vs ${bad}`);
  assert.ok(bad < 0);
});

test('no snapshot strictly before the move -> null; outside window -> null', () => {
  const e = loadEngine(); const v = makeValuer(e, snapshots);
  assert.strictEqual(moveProcess(e, v, { kind: 'add', date: '2026-06-01', in: [{ ottoneuId: 'x', player: 'FA Bat', salary: 1 }], out: [] }), null);
  assert.strictEqual(moveProcess(e, v, { kind: 'add', date: '2025-06-10', in: [], out: [] }), null);
});
```

- [ ] **Step 2: Run** — `node --test audit/test/process.test.js` → FAIL.

- [ ] **Step 3: Implement**

```js
// audit/lib/process.js
// "Process" grades: was the move good given what the suite's own projections
// said the day before? Replays shared.js on that day's roster + projections.
const { latestOnOrBefore } = require('./gitdata');

const PROCESS_FROM = '2026-05-24';
const PROCESS_TO = '2026-09-28';
const prevDay = d => { const x = new Date(d + 'T00:00:00Z'); x.setUTCDate(x.getUTCDate() - 1); return x.toISOString().slice(0, 10); };

function makeValuer(engine, snapshots) {
  const cache = new Map();
  function valuesAsOf(date) {
    const before = prevDay(date);
    const r = latestOnOrBefore(snapshots.roster, before);
    const h = latestOnOrBefore(snapshots.hit, before);
    const p = latestOnOrBefore(snapshots.pit, before);
    if (!r || !h || !p) return null;
    const key = [r.sha, h.sha, p.sha, before].join('|');
    if (cache.has(key)) return cache.get(key);

    engine.setDate(before);
    const rosterText = snapshots.read(r.sha, 'data/roster.csv');
    const rosterRows = engine.call('parseCSV', rosterText);
    const players = engine.call('parseRosterCSV', rosterText);
    players.forEach((pl, i) => { pl.ottoneuId = String(rosterRows[i]['ottoneu ID'] || ''); pl.teamId = String(rosterRows[i]['TeamID'] || ''); });
    const hp = engine.call('parseHittingProjections', snapshots.read(h.sha, 'data/proj_hitting.csv'));
    const pp = engine.call('parsePitchingProjections', snapshots.read(p.sha, 'data/proj_pitching.csv'));
    const matched = engine.call('matchPlayers', players, hp, pp);
    const byTeam = new Map();
    matched.forEach(m => { if (!byTeam.has(m.teamId)) byTeam.set(m.teamId, []); byTeam.get(m.teamId).push(m); });
    const fas = engine.call('getFreeAgents', hp, pp, players);
    const vm = engine.call('calculateAllValues', [...byTeam.values()], fas, true);

    const byOttoneu = new Map(matched.map(m => [m.ottoneuId, m.fgId || m.name]));
    const norm = s => engine.call('normalizeName', s);
    const faByName = new Map(fas.map(f => [f.name, f.fgId || f.name]));
    const keyOf = (ottoneuId, name) => byOttoneu.get(String(ottoneuId)) || faByName.get(norm(name)) || null;
    const value = k => (k && vm[k] ? vm[k].projectedValue || 0 : 0);

    // Best bench player of a type on a team (robustness check): highest value
    // among players NOT in the optimal lineup / capped pitcher pool.
    function benchBest(teamId, type, excludeOttoneuId) {
      const roster = (byTeam.get(String(teamId)) || []).filter(m => m.ottoneuId !== String(excludeOttoneuId) && m.proj);
      const starters = new Set();
      if (type === 'H') {
        const lu = engine.call('optimizeHitterLineup', roster.filter(m => m.type === 'H'), engine.call('paSlotBudget'));
        Object.values(lu).filter(Boolean).forEach(m => starters.add(m.ottoneuId));
      } else {
        const ipB = engine.get('IP_MAX') * Math.max(engine.call('rosProrationFactor'), 0.1);
        engine.call('selectPitchers', roster.filter(m => m.type === 'P'), ipB).forEach(m => starters.add(m.ottoneuId));
      }
      const bench = roster.filter(m => m.type === type && !starters.has(m.ottoneuId))
        .sort((a, b) => value(b.fgId || b.name) - value(a.fgId || a.name));
      return bench.length ? bench[0].ottoneuId : null;
    }

    const out = { values: vm, keyOf, value, benchBest, f: engine.call('rosProrationFactor') };
    cache.set(key, out);
    return out;
  }
  return { valuesAsOf };
}

function moveProcess(engine, valuer, move) {
  if (move.date < PROCESS_FROM || move.date >= PROCESS_TO) return null;
  const v = valuer.valuesAsOf(move.date);
  if (!v) return null;
  const surplus = p => v.value(v.keyOf(p.ottoneuId, p.player)) - p.salary;
  let total = 0;
  for (const p of move.in) total += surplus(p);
  for (const p of move.out) {
    if (move.kind === 'trade') total -= surplus(p);
    else total += p.salary * 0.5 - v.value(v.keyOf(p.ottoneuId, p.player));
  }
  return total * v.f;
}

module.exports = { makeValuer, moveProcess, PROCESS_FROM, PROCESS_TO };
```

- [ ] **Step 4: Run** — `node --test audit/test/process.test.js` → PASS (2 tests). If `matchPlayers` warns about unmatched fixture rows, that's fine (console is silenced).
- [ ] **Step 5: Spot-check vs the live page:** pick one 2026 date with a snapshot and print three player values:

```bash
node -e "const {loadEngine}=require('./audit/lib/engine');const g=require('./audit/lib/gitdata');const {makeValuer}=require('./audit/lib/process');const e=loadEngine();const v=makeValuer(e,{roster:g.fileHistory('data/roster.csv'),hit:g.fileHistory('data/proj_hitting.csv'),pit:g.fileHistory('data/proj_pitching.csv'),read:g.fileAt});const x=v.valuesAsOf('2026-10-10');for(const n of ['Aaron Judge','Tarik Skubal','Corey Seager'])console.log(n,Math.round(x.value(x.keyOf('',n))))"
```

Expected: values in the MODEL.md sanity ranges (top hitter ~$55–65, ace $45–70). Note: `keyOf('', name)` only finds FAs by name — for rostered players pass their ottoneu ID; if all three print 0, look up their ottoneu IDs in `data/roster.csv` and retry before concluding anything is wrong.
- [ ] **Step 6: Commit** `git add audit/lib/process.js audit/test/process.test.js && git commit -m "feat(audit): process grades -- replay shared.js on the prior day's roster + projections"`

---

### Task 7: Counterfactual standings

**Files:**
- Create: `audit/lib/counterfactual.js`
- Create: `audit/test/counterfactual.test.js`

**Interfaces:**
- Consumes: `engine.call('buildStandings')`, `IP_MAX`, ctx from Task 5 (`ctx.avgPA`, `ctx.repl`).
- Produces:
  - `applyDelta(teamStats, ip, delta, teamPA) → {stats, ip}` — `delta = { H: [{line, sign}], P: [{line, sign}] }` (sign +1 add, −1 remove); `teamPA` = `ctx.avgPA`.
  - `undoMove(engine, ctx, final, move, lookup, opts) → Map<teamId, {dPts, dRank}>` — `final = [{teamId, stats, ip}]`. Undo semantics: **add/auction** → remove the player's stint line, add `ctx.repl` scaled to his PA/IP; **cut** → add back his production from cut date to season end; **swap** → remove the added player's stint line, add the cut player's production over the same window; **trade** → both teams at once: remove received lines (on-team window), add sent players' production from trade date to season end. `opts.replacementLine(type, pa|ip)` overrides the FA replacement (robustness check).
  - Returned deltas are **actual minus counterfactual** (positive dPts = the move helped).
  - `isDecisive(actualOrder, cfOrder) → boolean` — 1st place or top-3 membership differs.

- [ ] **Step 1: Write the failing tests**

```js
// audit/test/counterfactual.test.js
const test = require('node:test');
const assert = require('node:assert');
const { loadEngine } = require('../lib/engine');
const { applyDelta, undoMove, isDecisive } = require('../lib/counterfactual');

const e = loadEngine();
const base = { OBP: .330, SLG: .430, HR: 200, R: 800, ERA: 3.9, WHIP: 1.22, HR9: 1.15, SO: 1300 };

test('applyDelta adjusts counting and rate stats', () => {
  const r = applyDelta(base, 1400, { H: [{ line: { pa: 600, hr: 40, r: 100, obp: .400, slg: .600 }, sign: -1 }], P: [] }, 7800);
  assert.strictEqual(r.stats.HR, 160);
  assert.ok(r.stats.OBP < .330);
});

test('IP cap scales strikeouts when an undo pushes a staff past 1500', () => {
  const r = applyDelta(base, 1480, { H: [], P: [{ line: { ip: 60, so: 70, era: 3, whip: 1.1, hr9: 1 }, sign: 1 }] }, 7800);
  assert.ok(r.ip <= 1500);
  assert.ok(r.stats.SO < 1370);
});

test('undoing a big add costs the adder points; toy 3-team league', () => {
  const final = [
    { teamId: 'A', ip: 1400, stats: { ...base, HR: 230 } },
    { teamId: 'B', ip: 1400, stats: { ...base, HR: 220 } },
    { teamId: 'C', ip: 1400, stats: { ...base, HR: 210 } },
  ];
  const ctx = { avgPA: 7800, repl: { H: { pa: 600, hr: 10, r: 60, obp: .300, slg: .380 }, P: null } };
  const move = { kind: 'add', season: 2026, date: '2026-06-01', teamId: 'A', in: [{ ottoneuId: 'x' }], out: [] };
  const lookup = () => ({ type: 'H', line: { pa: 400, hr: 30, r: 60, obp: .350, slg: .500 } });
  const d = undoMove(e, ctx, final, move, lookup);
  assert.ok(d.get('A').dPts > 0, 'move helped A');
});

test('isDecisive', () => {
  assert.strictEqual(isDecisive(['A', 'B', 'C', 'D'], ['B', 'A', 'C', 'D']), true);
  assert.strictEqual(isDecisive(['A', 'B', 'C', 'D'], ['A', 'B', 'D', 'C']), true);
  assert.strictEqual(isDecisive(['A', 'B', 'C', 'D', 'E'], ['A', 'B', 'C', 'E', 'D']), false);
});
```

- [ ] **Step 2: Run** — `node --test audit/test/counterfactual.test.js` → FAIL.

- [ ] **Step 3: Implement**

```js
// audit/lib/counterfactual.js
// Replay final standings with one move undone. Each move is evaluated alone
// against what actually happened (moves interact, so these never sum).
const IP_MAX = 1500;

function applyDelta(stats, ip, delta, teamPA) {
  const s = { ...stats }; let tip = ip;
  for (const { line, sign } of delta.H) {
    if (!line) continue;
    const pa = line.pa || 0;
    s.HR += sign * (line.hr || 0); s.R += sign * (line.r || 0);
    // Team PA held fixed: the player's PA displace (or are displaced by) team-average PA.
    s.OBP += sign * ((line.obp || 0) - stats.OBP) * pa / teamPA;
    s.SLG += sign * ((line.slg || 0) - stats.SLG) * pa / teamPA;
  }
  for (const { line, sign } of delta.P) {
    if (!line) continue;
    const lip = line.ip || 0; const newIp = tip + sign * lip;
    if (newIp <= 0) continue;
    for (const [k, f] of [['ERA', 'era'], ['WHIP', 'whip'], ['HR9', 'hr9']]) s[k] = (s[k] * tip + sign * (line[f] || 0) * lip) / newIp;
    s.SO += sign * (line.so || 0); tip = newIp;
  }
  if (tip > IP_MAX) { s.SO *= IP_MAX / tip; tip = IP_MAX; }
  return { stats: s, ip: tip };
}

const scaleRepl = (repl, type, line) => {
  if (!repl || !line) return null;
  const k = type === 'H' ? 'pa' : 'ip';
  const f = (repl[k] || 0) > 0 ? (line[k] || 0) / repl[k] : 0;
  return type === 'H'
    ? { pa: line.pa, hr: repl.hr * f, r: repl.r * f, obp: repl.obp, slg: repl.slg }
    : { ip: line.ip, so: repl.so * f, era: repl.era, whip: repl.whip, hr9: repl.hr9 };
};

const order = st => st.map(t => t.teamId);

function undoMove(engine, ctx, final, move, lookup, opts = {}) {
  const end = move.season + '-09-28';
  const deltas = new Map(final.map(t => [t.teamId, { H: [], P: [] }]));
  const push = (teamId, type, line, sign) => { if (deltas.has(teamId) && line) deltas.get(teamId)[type].push({ line, sign }); };
  const repl = (type, line) => (opts.replacementLine ? opts.replacementLine(type, line) : scaleRepl(ctx.repl[type], type, line));
  const winEnd = p => (opts.moveEnd && opts.moveEnd(p.ottoneuId)) || end;

  if (move.kind === 'trade') {
    for (const p of move.in) { const x = lookup(p.ottoneuId, move.date, winEnd(p)); push(move.teamId, x.type, x.line, -1); push(move.counterTeamId, x.type, lookup(p.ottoneuId, move.date, end).line, +1); }
    for (const p of move.out) { const x = lookup(p.ottoneuId, move.date, end); push(move.teamId, x.type, x.line, +1); }
  } else {
    for (const p of move.in) {
      const x = lookup(p.ottoneuId, move.date, winEnd(p)); push(move.teamId, x.type, x.line, -1);
      if (move.kind !== 'swap') push(move.teamId, x.type, repl(x.type, x.line), +1);
    }
    for (const p of move.out) {
      const x = lookup(p.ottoneuId, move.date, move.kind === 'swap' ? winEnd(move.in[0]) : end);
      push(move.teamId, x.type, x.line, +1);
    }
  }

  const actual = engine.call('buildStandings', final.map(t => ({ teamId: t.teamId, stats: t.stats })));
  const cf = engine.call('buildStandings', final.map(t => ({ teamId: t.teamId, stats: applyDelta(t.stats, t.ip, deltas.get(t.teamId), ctx.avgPA).stats })));
  const pos = st => new Map(st.map((t, i) => [t.teamId, { pts: t.points, rank: i + 1 }]));
  const a = pos(actual), c = pos(cf);
  const out = new Map();
  for (const t of final) out.set(t.teamId, { dPts: a.get(t.teamId).pts - c.get(t.teamId).pts, dRank: c.get(t.teamId).rank - a.get(t.teamId).rank });
  out.decisive = isDecisive(order(actual), order(cf));
  return out;
}

function isDecisive(actualOrder, cfOrder) {
  if (actualOrder[0] !== cfOrder[0]) return true;
  const top3 = o => new Set(o.slice(0, 3));
  const a = top3(actualOrder), c = top3(cfOrder);
  return [...a].some(x => !c.has(x));
}

module.exports = { applyDelta, undoMove, isDecisive };
```

- [ ] **Step 4: Run** — `node --test audit/test/counterfactual.test.js` → PASS (4 tests).
- [ ] **Step 5: Commit** `git add audit/lib/counterfactual.js audit/test/counterfactual.test.js && git commit -m "feat(audit): counterfactual final standings per move, IP cap, decisive flag"`

---

### Task 8: Tags

**Files:**
- Create: `audit/lib/tags.js`
- Create: `audit/test/tags.test.js`

**Interfaces:**
- Consumes: `engine` (`hotPoolStats`, `hotScoreFor`, `hotMeetsThreshold`, `hotClassifyRole`), `sumWindow`.
- Produces: `tagMove(move, env) → string[]` with `env = { hotPctl(ottoneuId, date) → 0..1|null, isProspect(ottoneuId, date) → bool, weakestCatGroup(teamId, date) → 'H'|'P'|null, typeOf(ottoneuId) → 'H'|'P'|null, rankAt(teamId, date) → 1..12|null }`. Tags: `hot`, `prospect`, `need`, `deadline`, `salary-dump`, `consolidation`, `contender`, `rebuilder`.
- Also produces `makeHotPercentile(engine, days: Map<date, DayFile>, identity) → (ottoneuId, date) → pctl|null` (L15 window ending the day before; pool = qualified players of the same kind).

- [ ] **Step 1: Write the failing test**

```js
// audit/test/tags.test.js
const test = require('node:test');
const assert = require('node:assert');
const { tagMove } = require('../lib/tags');

const env = {
  hotPctl: id => (id === 'hot' ? 0.9 : 0.3), isProspect: id => id === 'kid',
  weakestCatGroup: () => 'H', typeOf: id => (id === 'arm' ? 'P' : 'H'), rankAt: t => (t === 'top' ? 2 : 11),
};

test('add tags: hot, need, contender', () => {
  const t = tagMove({ kind: 'add', date: '2026-06-01', teamId: 'top', in: [{ ottoneuId: 'hot', salary: 1 }], out: [] }, env);
  assert.deepStrictEqual(t.sort(), ['contender', 'hot', 'need']);
});

test('prospect stash on a rebuilder; pitcher add misses a hitting need', () => {
  assert.deepStrictEqual(tagMove({ kind: 'add', date: '2026-06-01', teamId: 'bot', in: [{ ottoneuId: 'kid', salary: 1 }], out: [] }, env).sort(), ['need', 'prospect', 'rebuilder']);
  assert.ok(!tagMove({ kind: 'add', date: '2026-06-01', teamId: 'mid', in: [{ ottoneuId: 'arm', salary: 1 }], out: [] }, { ...env, rankAt: () => 6 }).includes('need'));
});

test('trade tags: deadline, salary-dump, consolidation', () => {
  const t = tagMove({ kind: 'trade', date: '2026-08-15', teamId: 'mid', in: [{ ottoneuId: 'a', salary: 22 }], out: [{ ottoneuId: 'b', salary: 5 }, { ottoneuId: 'c', salary: 3 }] }, { ...env, rankAt: () => 6 });
  assert.ok(t.includes('deadline') && t.includes('consolidation') && !t.includes('salary-dump'));
  const dump = tagMove({ kind: 'trade', date: '2026-07-01', teamId: 'mid', in: [{ ottoneuId: 'a', salary: 2 }], out: [{ ottoneuId: 'b', salary: 20 }] }, { ...env, rankAt: () => 6 });
  assert.ok(dump.includes('salary-dump'));
});
```

- [ ] **Step 2: Run** — `node --test audit/test/tags.test.js` → FAIL.

- [ ] **Step 3: Implement**

```js
// audit/lib/tags.js
// Automatic "why" labels from what was true on the move date.
const { sumWindow } = require('./stats');

function tagMove(move, env) {
  const tags = new Set();
  for (const p of move.in) {
    const h = env.hotPctl(p.ottoneuId, move.date);
    if (h !== null && h >= 0.75) tags.add('hot');
    if (env.isProspect(p.ottoneuId, move.date)) tags.add('prospect');
    const need = env.weakestCatGroup(move.teamId, move.date);
    if (need && env.typeOf(p.ottoneuId) === need) tags.add('need');
  }
  if (move.kind === 'trade') {
    if (move.date.slice(5, 7) === '08') tags.add('deadline');
    const net = move.out.reduce((s, p) => s + p.salary, 0) - move.in.reduce((s, p) => s + p.salary, 0);
    if (net >= 10) tags.add('salary-dump');
    if (move.in.length !== move.out.length && Math.min(move.in.length, move.out.length) >= 1 && Math.max(move.in.length, move.out.length) >= 2) tags.add('consolidation');
  }
  const rank = env.rankAt(move.teamId, move.date);
  if (rank !== null) { if (rank <= 4) tags.add('contender'); else if (rank >= 9) tags.add('rebuilder'); }
  return [...tags];
}

// L15 HotScore percentile, same scoring as hot.html, pool = same-kind qualified players.
function makeHotPercentile(engine, days, identity) {
  const dates = [...days.keys()].sort();
  const cache = new Map();
  function pool(date) {
    if (cache.has(date)) return cache.get(date);
    const end = dates.filter(d => d < date); const win = end.slice(-15).map(d => days.get(d));
    if (win.length < 10) { cache.set(date, null); return null; }
    const ids = { h: new Set(), p: new Set() };
    win.forEach(d => { d.h.forEach(r => ids.h.add(r[0])); d.p.forEach(r => ids.p.add(r[0])); });
    const kinds = { H: [], SP: [], RP: [] };
    ids.h.forEach(id => { const l = sumWindow(win, id, 'h'); if (engine.call('hotMeetsThreshold', 'H', 15, l)) kinds.H.push([id, l]); });
    ids.p.forEach(id => { const l = sumWindow(win, id, 'p'); const k = engine.call('hotClassifyRole', l.g, l.gs); if (engine.call('hotMeetsThreshold', k, 15, l)) kinds[k].push([id, l]); });
    const scored = new Map();
    for (const [kind, rows] of Object.entries(kinds)) {
      const cats = engine.get('HOT_CATS')[kind === 'H' ? 'H' : 'P'].map(c => c.k);
      const ps = engine.call('hotPoolStats', rows.map(r => r[1]), cats);
      const sc = rows.map(([id, l]) => [id, engine.call('hotScoreFor', l, ps, kind === 'H' ? 'H' : 'P')]).sort((a, b) => a[1] - b[1]);
      sc.forEach(([id], i) => scored.set(id, sc.length > 1 ? i / (sc.length - 1) : 0.5));
    }
    cache.set(date, scored); return scored;
  }
  return (ottoneuId, date) => {
    const who = identity.get(String(ottoneuId)); if (!who) return null;
    const s = pool(date); return s && s.has(who.mlbId) ? s.get(who.mlbId) : null;
  };
}

module.exports = { tagMove, makeHotPercentile };
```

- [ ] **Step 4: Run** — `node --test audit/test/tags.test.js` → PASS (3 tests).
- [ ] **Step 5: Commit** `git add audit/lib/tags.js audit/test/tags.test.js && git commit -m "feat(audit): auto-tags -- hot (L15 percentile), prospect, need, deadline, dump, consolidation, status"`

---

### Task 9: Runner — phases, checkpoints, outputs, run report

**Files:**
- Create: `audit/run.js`
- Create: `audit/lib/phases.js`
- Create: `audit/lib/review.js`
- Create: `audit/test/phases.test.js`
- Create: `audit/test/review.test.js`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `runPhases(phases: [{name, inputsHash() → string, run(prev) → Promise<any>}], { cacheDir, force: true|string|null }) → results` — skips a phase when `<cacheDir>/<name>.json` exists **and** its stored `inputsHash` matches and no force applies; `--force=<name>` reruns that phase and all after it.
  - `data/audit.json`:
    ```
    { generated, myTeamId: '10759', seasons: [2024,2025,2026],
      teams: { [teamId]: { name } },
      moves: [{ id, kind, season, date, teamId, counterTeamId, tradeId,
                in: [{player, ottoneuId, salary}], out: [...],
                process, result, luck, tags: [],
                standings: { dPts, dRank } | null, decisive, fragile: true|false|null|'unchecked' }],
      jointCuts: { [season]: { [teamId]: { dPts, dRank } } },
      approximations: [ '...strings shown on both pages...' ],
      report: { moves, unmatched: [...], ambiguous: [...], snapshotDiffs: [...], seasonsWithoutStandings: [] } }
    ```
  - `data/review.json`: `{ season, cards: [{ id, title, team, teamId, numbers: {...}, players: [] }] }` from `buildCards(audit, season)`.

- [ ] **Step 1: Write the failing tests**

```js
// audit/test/phases.test.js
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs'); const os = require('os'); const path = require('path');
const { runPhases } = require('../lib/phases');

test('skips cached phases, reruns on input change and on --force=<name>', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-'));
  let runs = []; let input = 'v1';
  const phases = ['a', 'b', 'c'].map(name => ({ name, inputsHash: () => input, run: async () => { runs.push(name); return name; } }));
  await runPhases(phases, { cacheDir: dir }); assert.deepStrictEqual(runs, ['a', 'b', 'c']);
  runs = []; await runPhases(phases, { cacheDir: dir }); assert.deepStrictEqual(runs, []);
  runs = []; await runPhases(phases, { cacheDir: dir, force: 'b' }); assert.deepStrictEqual(runs, ['b', 'c']);
  runs = []; input = 'v2'; await runPhases(phases, { cacheDir: dir }); assert.deepStrictEqual(runs, ['a', 'b', 'c']);
});
```

```js
// audit/test/review.test.js
const test = require('node:test');
const assert = require('node:assert');
const { buildCards } = require('../lib/review');

const mv = (o) => ({ season: 2026, kind: 'add', in: [], out: [], tags: [], process: null, standings: { dPts: 0, dRank: 0 }, decisive: false, fragile: null, ...o });
const audit = {
  myTeamId: '1', teams: { 1: { name: 'Me' }, 2: { name: 'You' } },
  moves: [
    mv({ id: 'a', teamId: '1', kind: 'trade', tradeId: 't1', counterTeamId: '2', result: 30, in: [{ player: 'Trout', salary: 22 }], out: [{ player: 'X', salary: 5 }] }),
    mv({ id: 'b', teamId: '2', kind: 'trade', tradeId: 't1', counterTeamId: '1', result: -30, in: [{ player: 'X', salary: 5 }], out: [{ player: 'Trout', salary: 22 }] }),
    mv({ id: 'c', teamId: '2', result: 25, in: [{ player: 'Gem', salary: 1 }] }),
    mv({ id: 'd', teamId: '1', kind: 'cut', result: -18, out: [{ player: 'Ghost', salary: 1 }] }),
    mv({ id: 'e', teamId: '1', result: 2, process: -5, decisive: true, fragile: false, standings: { dPts: 4, dRank: 1 }, in: [{ player: 'Clutch', salary: 1 }] }),
  ],
};

test('cards pick the right moves', () => {
  const c = Object.fromEntries(buildCards(audit, 2026).map(x => [x.id, x]));
  assert.strictEqual(c['trade-of-year'].numbers.margin, 60);
  assert.strictEqual(c['pickup-of-year'].players[0], 'Gem');
  assert.strictEqual(c['cut-that-haunts'].players[0], 'Ghost');
  assert.strictEqual(c['decisive'].players[0], 'Clutch');
  assert.strictEqual(c['most-active'].teamId, '1');
});

test('no qualifying move -> card omitted, not empty', () => {
  const ids = buildCards({ ...audit, moves: audit.moves.filter(m => m.kind !== 'trade') }, 2026).map(x => x.id);
  assert.ok(!ids.includes('trade-of-year'));
});
```

- [ ] **Step 2: Run** — `node --test audit/test/phases.test.js audit/test/review.test.js` → FAIL.

- [ ] **Step 3: Implement `audit/lib/phases.js`**

```js
// audit/lib/phases.js
// Checkpointed phases: each result is saved with a hash of its inputs, so a
// killed run resumes and a changed input (e.g. a fresh transactions.csv) reruns.
const fs = require('fs'); const path = require('path');

async function runPhases(phases, { cacheDir, force = null }) {
  fs.mkdirSync(cacheDir, { recursive: true });
  const results = {}; let forcing = force === true;
  for (const ph of phases) {
    if (force === ph.name) forcing = true;
    const file = path.join(cacheDir, ph.name + '.json');
    const hash = ph.inputsHash();
    if (!forcing && fs.existsSync(file)) {
      const saved = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (saved.inputsHash === hash) { results[ph.name] = saved.value; console.log(`[skip] ${ph.name}`); continue; }
    }
    console.log(`[run ] ${ph.name}`);
    const value = await ph.run(results);
    fs.writeFileSync(file, JSON.stringify({ inputsHash: hash, value }));
    results[ph.name] = value;
    forcing = true;   // a phase actually ran, so every later phase reruns too (skips `continue` above)
  }
  return results;
}

module.exports = { runPhases };
```

- [ ] **Step 4: Implement `audit/lib/review.js`**

```js
// audit/lib/review.js
// Numbers for the league year-in-review cards. Commentary is written separately
// (data/review-commentary.json) by Claude after reading these.
function buildCards(audit, season) {
  const mv = audit.moves.filter(m => m.season === season);
  const name = id => audit.teams[id]?.name || id;
  const cards = [];
  const push = c => cards.push({ players: [], numbers: {}, ...c });

  const trades = new Map();
  mv.filter(m => m.kind === 'trade').forEach(m => { if (!trades.has(m.tradeId)) trades.set(m.tradeId, []); trades.get(m.tradeId).push(m); });
  const tradeRows = [...trades.values()].filter(s => s.length === 2).map(([a, b]) => {
    const [w, l] = a.result >= b.result ? [a, b] : [b, a];
    return { w, l, margin: w.result - l.result, both: a.result > 0 && b.result > 0 };
  });
  const fleece = tradeRows.sort((x, y) => y.margin - x.margin)[0];
  if (fleece) push({ id: 'trade-of-year', title: 'Fleecing of the Year', teamId: fleece.w.teamId, team: name(fleece.w.teamId),
    numbers: { margin: Math.round(fleece.margin), winner: Math.round(fleece.w.result), loser: Math.round(fleece.l.result), victim: name(fleece.l.teamId) },
    players: fleece.w.in.map(p => p.player) });
  const winwin = tradeRows.filter(r => r.both).sort((x, y) => (y.w.result + y.l.result) - (x.w.result + x.l.result))[0];
  if (winwin) push({ id: 'win-win', title: 'Trade of the Year (everybody won)', teamId: winwin.w.teamId, team: name(winwin.w.teamId),
    numbers: { total: Math.round(winwin.w.result + winwin.l.result), partner: name(winwin.l.teamId) }, players: [...winwin.w.in, ...winwin.l.in].map(p => p.player) });

  const adds = mv.filter(m => m.kind === 'add' || m.kind === 'swap').sort((a, b) => b.result - a.result);
  if (adds[0]) push({ id: 'pickup-of-year', title: 'Pickup of the Year', teamId: adds[0].teamId, team: name(adds[0].teamId),
    numbers: { value: Math.round(adds[0].result), salary: adds[0].in[0].salary }, players: adds[0].in.map(p => p.player) });

  const cuts = mv.filter(m => m.kind === 'cut' || m.kind === 'swap').sort((a, b) => a.result - b.result);
  if (cuts[0] && cuts[0].result < 0) push({ id: 'cut-that-haunts', title: 'The Cut That Haunts', teamId: cuts[0].teamId, team: name(cuts[0].teamId),
    numbers: { lost: Math.round(-cuts[0].result) }, players: cuts[0].out.map(p => p.player) });

  mv.filter(m => m.decisive).sort((a, b) => (b.standings?.dPts || 0) - (a.standings?.dPts || 0)).slice(0, 3).forEach((m, i) =>
    push({ id: i ? 'decisive-' + i : 'decisive', title: m.standings.dPts > 0 ? 'The Move That Won It' : 'The Move That Cost It', teamId: m.teamId, team: name(m.teamId),
      numbers: { dPts: m.standings.dPts, dRank: m.standings.dRank, closeCall: m.fragile === true, unchecked: m.fragile === 'unchecked' },
      players: (m.in.length ? m.in : m.out).map(p => p.player) }));

  const byTeam = new Map();
  mv.forEach(m => { const t = byTeam.get(m.teamId) || { n: 0, luck: 0, nl: 0 }; t.n++; if (m.luck != null) { t.luck += m.luck; t.nl++; } byTeam.set(m.teamId, t); });
  const teamsArr = [...byTeam.entries()];
  const active = teamsArr.sort((a, b) => b[1].n - a[1].n);
  if (active.length) {
    push({ id: 'most-active', title: 'Most Active Manager', teamId: active[0][0], team: name(active[0][0]), numbers: { moves: active[0][1].n } });
    const quiet = active.at(-1); push({ id: 'most-patient', title: 'Most Patient Manager', teamId: quiet[0], team: name(quiet[0]), numbers: { moves: quiet[1].n } });
  }
  const lucky = teamsArr.filter(([, t]) => t.nl >= 5).sort((a, b) => b[1].luck - a[1].luck);
  if (lucky.length >= 2) {
    push({ id: 'luckiest', title: 'Luckiest Manager', teamId: lucky[0][0], team: name(lucky[0][0]), numbers: { luck: Math.round(lucky[0][1].luck) } });
    push({ id: 'unluckiest', title: 'Unluckiest Manager', teamId: lucky.at(-1)[0], team: name(lucky.at(-1)[0]), numbers: { luck: Math.round(lucky.at(-1)[1].luck) } });
  }

  const auction = mv.filter(m => m.kind === 'auction').sort((a, b) => b.result - a.result);
  if (auction.length >= 2) {
    push({ id: 'auction-best', title: 'Best Auction Buy', teamId: auction[0].teamId, team: name(auction[0].teamId), numbers: { value: Math.round(auction[0].result), salary: auction[0].in[0].salary }, players: auction[0].in.map(p => p.player) });
    const worst = auction.at(-1);
    push({ id: 'auction-worst', title: 'Worst Auction Buy', teamId: worst.teamId, team: name(worst.teamId), numbers: { value: Math.round(worst.result), salary: worst.in[0].salary }, players: worst.in.map(p => p.player) });
  }

  // All-time trade record (every season in the file)
  const rec = new Map();
  audit.moves.filter(m => m.kind === 'trade').forEach(m => { const r = rec.get(m.teamId) || { w: 0, l: 0, net: 0 }; m.result >= 0 ? r.w++ : r.l++; r.net += m.result; rec.set(m.teamId, r); });
  if (rec.size) push({ id: 'all-time-trades', title: 'All-Time Trade Record', teamId: null, team: null,
    numbers: { rows: [...rec.entries()].sort((a, b) => b[1].net - a[1].net).map(([id, r]) => ({ team: name(id), w: r.w, l: r.l, net: Math.round(r.net) })) } });
  return cards;
}

module.exports = { buildCards };
```

Note the test expects `trade-of-year` to be the one-sided trade. Keep the ids as written: `trade-of-year` = fleecing, `win-win` = everybody-won.

- [ ] **Step 5: Run** — `node --test audit/test/phases.test.js audit/test/review.test.js` → PASS (3 tests).

- [ ] **Step 6: Implement `audit/run.js`** — wires the phases in order: `snapshots` → `moves` → `stats` → `grade` → `standings` → `tags` → `write`.

```js
#!/usr/bin/env node
// audit/run.js — Decision audit pipeline.
//   node audit/run.js [--force | --force=<phase>]
// Phases checkpoint to audit/cache/. See docs/superpowers/specs/2026-10-11-decision-audit-design.md
const fs = require('fs'); const path = require('path'); const crypto = require('crypto');
const { loadEngine } = require('./lib/engine');
const { parseTransactions, buildMoves, parseCSVLine } = require('./lib/moves');
const { replayRosters, diffAgainstSnapshot } = require('./lib/stints');
const g = require('./lib/gitdata');
const { fetchDay, seasonDays, sumWindow } = require('./lib/stats');
const { buildIdentity } = require('./lib/identity');
const { seasonContext, moveResult, inSeason } = require('./lib/result');
const { makeValuer, moveProcess } = require('./lib/process');
const { undoMove } = require('./lib/counterfactual');
const { tagMove, makeHotPercentile } = require('./lib/tags');
const { buildCards } = require('./lib/review');
const { runPhases } = require('./lib/phases');

const ROOT = path.join(__dirname, '..');
const CACHE = path.join(__dirname, 'cache');
const MY_TEAM = '10759';
const arg = process.argv.find(a => a.startsWith('--force'));
const force = !arg ? null : arg === '--force' ? true : arg.split('=')[1];
const read = p => fs.readFileSync(path.join(ROOT, p), 'utf8');
const hashOf = (...parts) => crypto.createHash('sha1').update(parts.join('\u0000')).digest('hex');
const headSha = p => (g.fileHistory(p).at(-1) || {}).sha || '';

function csvRows(text) {
  const L = text.replace(/\r/g, '').trim().split('\n'); const H = parseCSVLine(L[0]);
  return L.slice(1).map(l => { const v = parseCSVLine(l); const r = {}; H.forEach((h, i) => { r[h] = v[i]; }); return r; });
}

function finalStandings(season) {
  let rows;
  if (season === 2026) rows = csvRows(read('data/standings.csv'));
  else if (fs.existsSync(path.join(ROOT, `data/standings-final-${season}.csv`))) rows = csvRows(read(`data/standings-final-${season}.csv`));
  else return null;
  return rows.map(r => ({ teamId: r.TeamID || r.Team, team: r.Team, ip: +r.IP || 1500,
    stats: { R: +r.R, HR: +r.HR, OBP: +r.OBP, SLG: +r.SLG, SO: +r.K, HR9: +r['HR/9'], ERA: +r.ERA, WHIP: +r.WHIP } }));
}

(async () => {
  const engine = loadEngine();
  const txText = read('data/transactions.csv');
  const txs = parseTransactions(txText);
  const seasons = [...new Set(buildMoves(txs).map(m => m.season))].filter(s => s <= 2026).sort();

  const phases = [
    { name: 'snapshots', inputsHash: () => hashOf(headSha('data/roster.csv'), headSha('data/proj_hitting.csv'), headSha('data/standings.csv')),
      run: async () => ({ roster: g.fileHistory('data/roster.csv'), hit: g.fileHistory('data/proj_hitting.csv'), pit: g.fileHistory('data/proj_pitching.csv'), standings: g.fileHistory('data/standings.csv') }) },
    { name: 'moves', inputsHash: () => hashOf(txText),
      run: async (r) => {
        const { stints, rosterAt } = replayRosters(txs);
        const diffs = r.snapshots.roster.filter((_, i, a) => i % 30 === 0 || i === a.length - 1).map(s => {
          const rows = csvRows(g.fileAt(s.sha, 'data/roster.csv')).map(x => ({ ottoneuId: x['ottoneu ID'], teamId: x.TeamID }));
          const d = diffAgainstSnapshot(rosterAt(s.date + 'T23:59:59'), rows);
          return { date: s.date, missing: d.missing.length, extra: d.extra.length, wrongTeam: d.wrongTeam.length };
        });
        const teams = {}; txs.forEach(t => { teams[t.teamId] = { name: t.team }; if (t.fromTeamId) teams[t.fromTeamId] = { name: t.fromTeam }; });
        return { moves: buildMoves(txs), stints, teams, snapshotDiffs: diffs };
      } },
    { name: 'stats', inputsHash: () => hashOf(seasons.join(',')),
      run: async () => {
        let n = 0;
        for (const s of seasons) for (const d of seasonDays(s)) { await fetchDay(d, CACHE); if (++n % 25 === 0) console.log(`  stats ${d}`); }
        return { days: n };
      } },
    { name: 'grade', inputsHash: () => hashOf(txText, headSha('data/roster.csv'), headSha('data/proj_hitting.csv'), fs.readFileSync(path.join(ROOT, 'shared.js'), 'utf8')),
      run: async (r) => {
        const { moves, stints } = r.moves;
        const dayCache = new Map();
        const day = d => { if (!dayCache.has(d)) { const f = path.join(CACHE, 'stats', d + '.json'); dayCache.set(d, fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf8')) : { h: [], p: [] }); } return dayCache.get(d); };
        const daysIn = (a, b) => seasonDays(+a.slice(0, 4)).filter(d => d >= a && d < b).map(day);
        const allDays = seasons.flatMap(s => seasonDays(s).map(day));
        // Position hints from roster snapshots (P if no hitting position).
        const hint = {};
        r.snapshots.roster.filter((_, i) => i % 20 === 0).forEach(s => csvRows(g.fileAt(s.sha, 'data/roster.csv')).forEach(x => { hint[x['ottoneu ID']] = engine.call('inferPlayerType', x['Position(s)']); }));
        const players = [...new Map(stints.map(s => [s.ottoneuId, { ottoneuId: s.ottoneuId, player: s.player, hint: hint[s.ottoneuId] }])).values()];
        const ident = buildIdentity(allDays, players);
        const lookup = (id, a, b) => {
          const who = ident.map.get(String(id));
          if (!who) return { type: hint[id] || 'H', line: null };
          const days = daysIn(a, b);
          const type = who.group === 'p' ? 'P' : 'H';
          return { type, line: sumWindow(days, who.mlbId, who.group) };
        };
        const valuer = makeValuer(engine, { ...r.snapshots, read: g.fileAt });
        const ctxBySeason = {};
        for (const s of seasons) {
          const final = finalStandings(s);
          if (!final) continue;
          const st = stints.filter(x => x.start <= `${s}-09-28` && (!x.end || x.end >= `${s}-03-28`));
          const rosteredIds = new Set(st.map(x => x.ottoneuId));
          const stintLines = st.map(x => lookup(x.ottoneuId, x.start < `${s}-03-28` ? `${s}-03-28` : x.start, x.end && x.end < `${s}-09-28` ? x.end : `${s}-09-28`)).filter(x => x.line);
          const sDays = seasonDays(s).map(day);
          const fa = [];
          for (const grp of ['h', 'p']) {
            const ids = new Set(); sDays.forEach(d => d[grp].forEach(row => ids.add(row[0])));
            const rosteredMlb = new Set([...rosteredIds].map(id => ident.map.get(id)?.mlbId).filter(Boolean));
            ids.forEach(id => { if (!rosteredMlb.has(id)) fa.push({ type: grp === 'p' ? 'P' : 'H', line: sumWindow(sDays, id, grp) }); });
          }
          ctxBySeason[s] = seasonContext(engine, { finalTeams: final, stintLines, freeAgentLines: fa });
        }
        const stintEnd = (id, teamId, date) => (stints.find(s => s.ottoneuId === String(id) && s.teamId === teamId && s.start <= date && (!s.end || s.end > date)) || {}).end || null;
        const graded = moves.map(m => {
          const ctx = ctxBySeason[m.season];
          const result = ctx ? moveResult(engine, ctx, m, lookup, id => stintEnd(id, m.teamId, m.date)) : null;
          const proc = moveProcess(engine, valuer, m);
          return { ...m, process: proc, result, luck: proc === null || result === null ? null : result - proc };
        });
        return { graded, ctxBySeason, report: { unmatched: ident.unmatched.map(u => u.player), ambiguous: ident.ambiguous.map(a => a.player) },
          identity: [...ident.map.entries()], hint };
      } },
    { name: 'standings', inputsHash: () => hashOf(txText, headSha('data/standings.csv'), 'v1'),
      run: async (r) => {
        // Re-create lookup + valuer (functions don't survive JSON checkpoints).
        const ident = new Map(r.grade.identity); const hint = r.grade.hint;
        const dayCache = new Map();
        const day = d => { if (!dayCache.has(d)) { const f = path.join(CACHE, 'stats', d + '.json'); dayCache.set(d, fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf8')) : { h: [], p: [] }); } return dayCache.get(d); };
        const lookup = (id, a, b) => { const who = ident.get(String(id)); if (!who) return { type: hint[id] || 'H', line: null };
          return { type: who.group === 'p' ? 'P' : 'H', line: sumWindow(seasonDays(+a.slice(0, 4)).filter(d => d >= a && d < b).map(day), who.mlbId, who.group) }; };
        const stints = r.moves.stints;
        const stintEnd = (id, teamId, date) => (stints.find(s => s.ottoneuId === String(id) && s.teamId === teamId && s.start <= date && (!s.end || s.end > date)) || {}).end || null;
        const valuer = makeValuer(engine, { ...r.snapshots, read: g.fileAt });
        const out = {}; const jointCuts = {};
        for (const s of seasons) {
          const final = finalStandings(s); const ctx = r.grade.ctxBySeason[s];
          if (!final || !ctx) continue;
          for (const m of r.grade.graded.filter(x => x.season === s && x.kind !== 'auction' && inSeason(x.date))) {
            const moveEnd = id => stintEnd(id, m.teamId, m.date);
            const d = undoMove(engine, ctx, final, m, lookup, { moveEnd });
            let fragile = null;
            if (d.decisive) {
              if (s !== 2026) fragile = 'unchecked';
              else {
                const v = valuer.valuesAsOf(m.date); const p0 = m.in[0] || m.out[0];
                const benchId = v && p0 ? v.benchBest(m.teamId, lookup(p0.ottoneuId, m.date, m.date).type, p0.ottoneuId) : null;
                if (!benchId) fragile = 'unchecked';
                else {
                  const tough = undoMove(engine, ctx, final, m, lookup, { moveEnd, replacementLine: (type, line) => lookup(benchId, m.date, `${s}-09-28`).line });
                  fragile = !tough.decisive;
                }
              }
            }
            out[m.id] = { standings: d.get(m.teamId), decisive: d.decisive, fragile };
          }
          // Joint: all of a team's in-season cuts undone together.
          jointCuts[s] = {};
          for (const teamId of new Set(final.map(t => t.teamId))) {
            const cuts = r.grade.graded.filter(x => x.season === s && x.teamId === teamId && x.kind === 'cut' && inSeason(x.date));
            if (!cuts.length) continue;
            const combined = { kind: 'cut', season: s, date: cuts[0].date, teamId, in: [], out: cuts.flatMap(c => c.out) };
            jointCuts[s][teamId] = undoMove(engine, ctx, final, combined, (id, a, b) => {
              const c = cuts.find(x => x.out.some(p => p.ottoneuId === id)); return lookup(id, c ? c.date : a, b);
            }).get(teamId);
          }
        }
        return { byMove: out, jointCuts, seasonsWithoutStandings: seasons.filter(s => !finalStandings(s)) };
      } },
    { name: 'tags', inputsHash: () => hashOf(txText, headSha('data/standings.csv'), 'v1'),
      run: async (r) => {
        const ident = new Map(r.grade.identity); const hint = r.grade.hint;
        const days = new Map(); seasons.forEach(s => seasonDays(s).forEach(d => { const f = path.join(CACHE, 'stats', d + '.json'); if (fs.existsSync(f)) days.set(d, JSON.parse(fs.readFileSync(f, 'utf8'))); }));
        const hotPctl = makeHotPercentile(engine, days, ident);
        const prospects = new Set(csvRows(read('data/prospects.csv')).map(x => engine.call('normalizeName', x.Name)));
        const nameOf = {}; r.moves.stints.forEach(s => { nameOf[s.ottoneuId] = s.player; });
        const standHist = r.snapshots.standings;
        const standAt = date => { const s = g.latestOnOrBefore(standHist, date); return s ? csvRows(g.fileAt(s.sha, 'data/standings.csv')) : null; };
        const rankCache = new Map();
        const ranked = date => {
          if (rankCache.has(date)) return rankCache.get(date);
          const rows = standAt(date); if (!rows) { rankCache.set(date, null); return null; }
          const teams = rows.map(x => ({ teamId: x.TeamID || x.Team, team: x.Team, stats: { R: +x.R, HR: +x.HR, OBP: +x.OBP, SLG: +x.SLG, SO: +x.K, HR9: +x['HR/9'], ERA: +x.ERA, WHIP: +x.WHIP } }));
          const st = engine.call('buildStandings', teams); rankCache.set(date, st); return st;
        };
        const nameToId = {}; Object.entries(r.moves.teams).forEach(([id, t]) => { nameToId[t.name] = id; });
        const env = {
          hotPctl,
          isProspect: (id, date) => prospects.has(engine.call('normalizeName', nameOf[id] || '')) && !ident.has(String(id)),
          typeOf: id => (ident.get(String(id))?.group === 'p' ? 'P' : hint[id] || 'H'),
          rankAt: (teamId, date) => { const st = ranked(date); if (!st) return null; const i = st.findIndex(t => (nameToId[t.team] || t.teamId) === teamId); return i < 0 ? null : i + 1; },
          weakestCatGroup: (teamId, date) => { const st = ranked(date); if (!st) return null; const t = st.find(x => (nameToId[x.team] || x.teamId) === teamId); if (!t) return null;
            const worst = Object.entries(t.ranks).sort((a, b) => a[1] - b[1])[0][0]; return ['OBP', 'SLG', 'HR', 'R'].includes(worst) ? 'H' : 'P'; },
        };
        return Object.fromEntries(r.grade.graded.map(m => [m.id, tagMove(m, env)]));
      } },
    { name: 'write', inputsHash: () => hashOf(Date.now().toString()),   // always rewrite outputs
      run: async (r) => {
        const moves = r.grade.graded.map(m => ({ ...m, tags: r.tags[m.id] || [], ...(r.standings.byMove[m.id] || { standings: null, decisive: false, fragile: null }) }));
        const audit = {
          generated: new Date().toISOString(), myTeamId: MY_TEAM, seasons, teams: r.moves.teams, moves,
          jointCuts: r.standings.jointCuts,
          approximations: [
            'Stats count while a player is rostered — Ottoneu lineups are not in the data, so bench players are overstated.',
            'Each move is measured alone against what actually happened; moves interact, so individual impacts never add up.',
            'Replacement for an undone pickup is the averaged top free-agent production that season; an add paired with a cut restores the cut player instead.',
            'Process grades exist only from 2026-05-24 (first saved projections) to the end of the 2026 season.',
          ],
          report: { moves: moves.length, unmatched: r.grade.report.unmatched, ambiguous: r.grade.report.ambiguous, snapshotDiffs: r.moves.snapshotDiffs, seasonsWithoutStandings: r.standings.seasonsWithoutStandings },
        };
        fs.writeFileSync(path.join(ROOT, 'data/audit.json'), JSON.stringify(audit));
        const season = Math.max(...seasons);
        fs.writeFileSync(path.join(ROOT, 'data/review.json'), JSON.stringify({ season, generated: audit.generated, cards: buildCards(audit, season) }));
        return { ok: true };
      } },
  ];

  const res = await runPhases(phases, { cacheDir: CACHE, force });
  const rep = JSON.parse(read('data/audit.json')).report;
  console.log(`\nmoves ${rep.moves} · unmatched ${rep.unmatched.length} · ambiguous ${rep.ambiguous.length} · seasons without standings: ${rep.seasonsWithoutStandings.join(',') || 'none'}`);
  console.log('snapshot cross-check:', rep.snapshotDiffs.map(d => `${d.date} m${d.missing}/x${d.extra}/w${d.wrongTeam}`).join(' '));
  if (rep.unmatched.length) console.log('unmatched (first 30):', rep.unmatched.slice(0, 30).join(', '));
})().catch(e => { console.error(e); process.exit(1); });
```

Note: `ctxBySeason` is checkpointed as JSON between phases — it holds only plain numbers/objects, so that's safe. Lookups and valuers are functions and are rebuilt in each phase that needs them.

- [ ] **Step 7: First real run** — `node audit/run.js`. The stats phase makes ~1,250 day fetches (~10–15 min) on the first run only. Expected output: a `[run ]` line per phase, then the report line. **Stop and report to the user if:** unmatched > 10% of distinct players who have MLB service; any snapshot cross-check count > 15; any season without standings other than one you already know is missing.
- [ ] **Step 8: Real-data spot checks:**
  - `node -e "const a=require('./data/audit.json');const t=a.moves.filter(m=>m.kind==='trade'&&m.date==='2026-08-15');console.log(t.map(m=>[a.teams[m.teamId].name,m.in.map(p=>p.player),m.out.map(p=>p.player),Math.round(m.result),m.process&&Math.round(m.process)]))"` → two sides; mine gets Trout + Vaughn for Schwellenbach.
  - Re-run `node audit/run.js` → every phase prints `[skip]` except `write`.
- [ ] **Step 9: Commit** `git add audit/run.js audit/lib/phases.js audit/lib/review.js audit/test/phases.test.js audit/test/review.test.js data/audit.json data/review.json && git commit -m "feat(audit): checkpointed runner -- grades, counterfactual standings, tags, review cards"`

---

### Task 10: `audit.html` — coaching page

**Files:**
- Create: `audit.html`
- Modify: nav block in every page that has one (`index.html`, `standings.html`, `roster.html`, `trade.html`, `fa.html`, `bid.html`, `briefing.html`, `hot.html`, `prospects.html`, `targets.html`) — add `<a href="audit.html">Audit</a>` after Trade Targets.

**Interfaces:**
- Consumes: `data/audit.json` (schema in Task 9).

- [ ] **Step 1: Build the page.** Copy the `<head>` style block, `<link rel="stylesheet" href="theme.css">` and nav from `hot.html` lines 1–57 (title "Ottoneu Tools — Decision Audit", nav `active` on Audit). Body sections, rendered by an inline script that `fetch('data/audit.json')`:
  1. **Headline** (my team, season selector defaulting to the latest): sums of my `process`, `result`, `luck` vs. league median of team sums; standings places net (sum of `standings.dRank` over my moves) with the approximation list in a `<details>`.
  2. **Patterns:** table rows = move kind (`add`, `swap`, `cut`, `trade`, `auction`) and each tag; columns = my n, my avg result, league avg result, my avg process, league avg process. Rows with my n < 5 are hidden; footnote "patterns need at least 5 moves".
  3. **Me vs. my tools** (moves with `process !== null`): "Followed the model" = process ≥ 0, "Overruled the model" = process < 0. For each group: n and avg result. One sentence: "When you overruled the model you averaged $X vs $Y when you followed it."
  4. **Standings:** my 5 most costly and 5 most valuable moves by `standings.dPts`, each with players, date, dPts, dRank, a "decisive" badge, and "close call"/"unchecked" when `fragile` is `true`/`'unchecked'`. Below: `jointCuts[season][myTeamId]` as "All your cuts undone together: ±X pts, ±Y places".
  5. **Every move:** sortable table (date, kind, in, out, process, result, luck, Δpts, tags, note). Toggle "My team / Whole league". Note cell is an inline `<input>` saving to `localStorage['audit_notes_v1']` (`{[moveId]: {note, tags}}`) wrapped in try/catch; tag overrides via a small text field (comma-separated) in the same store, shown instead of auto tags when set.
  - Money format: `+$8` / `−$4` (round), `—` for null.
- [ ] **Step 2: Verify without a server** (the preview tool hangs here per project memory): `node --check` cannot parse HTML, so extract and check the script: `node -e "const h=require('fs').readFileSync('audit.html','utf8');const s=h.split('<script>').pop().split('</script>')[0];new Function(s);console.log('ok')"` → `ok`.
- [ ] **Step 3: Data check:** `node -e "const a=require('./data/audit.json');const mine=a.moves.filter(m=>m.teamId===a.myTeamId&&m.season===2026);console.log(mine.length,'moves', Math.round(mine.reduce((s,m)=>s+(m.result||0),0)),'result')"` — the page headline must show the same total.
- [ ] **Step 4: Commit** `git add audit.html index.html standings.html roster.html trade.html fa.html bid.html briefing.html hot.html prospects.html targets.html && git commit -m "feat(audit): coaching page -- headline, patterns (n>=5), me vs model, standings impact, move table with local notes"`
- [ ] **Step 5:** Tell the user to open `audit.html` on the live site after pushing via GitHub Desktop (or locally via `file://` won't load JSON — needs the Pages site).

---

### Task 11: `review.html` — league year-in-review + commentary

**Files:**
- Create: `review.html`
- Create: `data/review-commentary.json`

**Interfaces:**
- Consumes: `data/review.json` (`{season, cards}`), `data/review-commentary.json` (`{ [cardId]: "one line" }`).

- [ ] **Step 1: Build the page.** Standalone (no nav, no links, no stamp — screenshots only). Cream background from `theme.css` palette, `Graduate` heading font like the suite. Single column, `max-width: 420px; margin: 0 auto; padding: 16px`. Each card: `<section class="card">` with title, team name, the big number (e.g. "+$38" or "+4 pts"), player names, a small grey stat line, and the commentary line in italics if present. `decisive` cards with `closeCall` show a "close call" chip; `unchecked` shows "unverified". `all-time-trades` renders as a compact table. Order: decisive cards, trade-of-year, win-win, pickup-of-year, cut-that-haunts, luckiest, unluckiest, most-active, most-patient, auction-best, auction-worst, all-time-trades. Header card: "The Peacock League · {season} Year in Review".
- [ ] **Step 2: Script check** — same `new Function` extraction as Task 10 Step 2 → `ok`.
- [ ] **Step 3: Write commentary (Claude, not code).** Read `data/review.json`; write one line per card into `data/review-commentary.json`. Rules: every claim backed by that card's numbers; light ribbing, never mean; no claims about a manager beyond the card; ≤ 140 characters each; cards marked close call/unverified get hedged wording.
- [ ] **Step 4: Show the user the commentary** in chat (card id → line) and apply their edits.
- [ ] **Step 5: Commit** `git add review.html data/review-commentary.json && git commit -m "feat(audit): league year-in-review cards with commentary"`
- [ ] **Step 6:** Remind the user: push via GitHub Desktop, open `review.html` on the site on their phone, screenshot cards.

---

### Task 12: Docs + memory

**Files:**
- Modify: `MODEL.md` (append a short "Decision audit" section: what reuses which engine function, the dollar conventions block from this plan, the approximations list)
- Modify: `README.md` (one line per new page + how to re-run: `node audit/run.js`, and re-fetching transactions via `audit/tools/fetch-transactions.browser.js`)

- [ ] **Step 1:** Write both sections.
- [ ] **Step 2: Commit** `git add MODEL.md README.md && git commit -m "docs(audit): MODEL.md conventions + README usage"`
- [ ] **Step 3:** Update project memory (`project_build_status.md`): audit pipeline exists, outputs, how to refresh.
