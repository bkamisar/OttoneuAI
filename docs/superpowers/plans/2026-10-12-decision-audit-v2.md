# Decision Audit v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-grade every move on what actually counted for each Ottoneu team (`data/teamproduction.csv`) and treat offseason cuts/trades as cap moves (salary resets, winter summaries).

**Architecture:** Two new pure modules (`production.js`, `offseason.js`), one new standings module (`contributed.js`), a counted-production result function added to `result.js`, then `run.js` rewired: the `grade` phase uses counted results, the `standings` phase computes roto points contributed, `write` adds winter summaries. Pages and cards follow.

**Tech Stack:** Node 24 built-ins only; `node --test audit/test/*.test.js`; plain HTML/JS pages.

**Spec:** `docs/superpowers/specs/2026-10-12-decision-audit-v2-design.md` (v1 spec: `2026-10-11-decision-audit-design.md`)

## Global Constraints

- TeamID is identity. My team = `10759`. Commit on `main`; never push.
- `shared.js` / `hotboard.js` unchanged; valuation via `audit/lib/engine.js`.
- Counted lines come only from `data/teamproduction.csv`; a missing row = the player counted nothing for that team (zero, not missing).
- Hitter PA ≈ AB × player's season PA/AB from MLB daily stats; fallback ratio **1.12**.
- Offseason window for season S: **Oct 1 (S−1) → S's auction day** (earliest `auction` move of S).
- Salary reset = offseason cut + the same team buys the same player at S's auction; graded `old − new salary`.
- In-season cut frees **half** salary; offseason cut frees **full** salary.
- 1,250-IP rule applies to every standings computation (`scoreStandings`).
- Title-deciding uses real Ottoneu final points (`Points` column) for margins.
- Process grades unchanged.

## Review Focus

1. **A player cut and re-added by the same team in one season** → teamproduction combines the lines; the move must be flagged `combinedStints: true`, never double-counted. Test in Task 3.
2. **A reset where the rebuy price is higher than the cut price** → negative grade (cost money), not dropped. Test in Task 2.
3. **Team with no teamproduction row for a traded-away player** (prospect never in a lineup) → contributes 0, trade still grades. Test in Task 3.
4. **Pitcher rows in baseball IP notation (`36.1`)** → 36⅓ innings, not 36.1. Test in Task 1.
5. **Removing a team's only hitter at a position / a pitcher pushing IP under 1,250** → ptsContributed reflects the IP-rule loss. Test in Task 4.

---

### Task 1: Team production parsing + counted lookup

**Files:** Create `audit/lib/production.js`, `audit/test/production.test.js`

**Interfaces:**
- Produces:
  - `parseProduction(text) → { rows: ProdRow[], bench: Map<'season|teamId', {ip, so, era, whip, hr9}> }`, `ProdRow = { season: number, teamId, group: 'H'|'P', ottoneuId, player, acquired: 'YYYY-MM-DD', g, line }`; H `line = { ab, r, hr, obp, slg }`, P `line = { ip, so, hr9, era, whip }` (ip converted from baseball notation).
  - `makeCounted(rows, paRatio) → counted(ottoneuId, teamId, season) → { type: 'H'|'P'|null, line|null }` where hitter lines gain `pa = round(ab × (paRatio(ottoneuId, season) || 1.12))`. Two-way players (H and P rows on one team) return the H row with `line.pitch` = the P line.
  - `teamsWithPlayer(rows, ottoneuId, season) → [{ teamId, acquired }]`.

- [ ] **Step 1: Write the failing test**

```js
// audit/test/production.test.js
const test = require('node:test');
const assert = require('node:assert');
const { parseProduction, makeCounted, teamsWithPlayer } = require('../lib/production');

const CSV = 'season,teamId,group,ottoneuId,player,acquired,G,c1,c2,c3,c4,c5\n' +
  '2026,10818,H,34619,Brendan Donovan,"May 13, 2026 2:49 PM",3,15,2,0,0.33333,0.53333\n' +
  '2026,10908,H,34619,Brendan Donovan,"August 15, 2026 11:25 PM",4,16,2,0,0.50000,0.43750\n' +
  '2026,10818,P,9,Seth Lugo,"March 5, 2026 8:03 PM",6,36.1,32,0.24771,3.71560,1.48624\n' +
  '2026,10818,PBENCH,,Bench,,165,429.0,410,1.00699,3.27273,1.23776\n';

test('parses hitters, pitchers (IP notation), bench and acquisition dates', () => {
  const { rows, bench } = parseProduction(CSV);
  assert.strictEqual(rows.length, 3);
  const lugo = rows.find(r => r.player === 'Seth Lugo');
  assert.ok(Math.abs(lugo.line.ip - (36 + 1 / 3)) < 1e-9);
  assert.strictEqual(lugo.line.so, 32);
  assert.strictEqual(rows[0].acquired, '2026-05-13');
  assert.ok(Math.abs(bench.get('2026|10818').ip - 429) < 1e-9);
});

test('counted lookup: PA from ratio (fallback 1.12), zero for missing rows', () => {
  const { rows } = parseProduction(CSV);
  const c = makeCounted(rows, (id) => (id === '34619' ? 1.1 : null));
  const d = c('34619', '10818', 2026);
  assert.strictEqual(d.type, 'H'); assert.strictEqual(d.line.pa, Math.round(15 * 1.1)); assert.strictEqual(d.line.hr, 0);
  assert.deepStrictEqual(c('34619', '10759', 2026), { type: null, line: null });
  const c2 = makeCounted(rows, () => null);
  assert.strictEqual(c2('34619', '10908', 2026).line.pa, Math.round(16 * 1.12));
});

test('teamsWithPlayer lists every team a player counted for that season', () => {
  const { rows } = parseProduction(CSV);
  assert.deepStrictEqual(teamsWithPlayer(rows, '34619', 2026).map(t => t.teamId).sort(), ['10818', '10908']);
});
```

- [ ] **Step 2: Run** `node --test audit/test/production.test.js` → FAIL (module not found).

- [ ] **Step 3: Implement**

```js
// audit/lib/production.js
// Ottoneu "team production": the lineup-only stats each player counted for each
// team in a season (one row per player/team/season). The factual basis for v2 grades.
const { parseCSVLine } = require('./moves');

const MONTHS = { January: 1, February: 2, March: 3, April: 4, May: 5, June: 6, July: 7, August: 8, September: 9, October: 10, November: 11, December: 12 };
const isoDate = s => { const m = String(s).match(/^(\w+) (\d+), (\d{4})/); if (!m) return ''; const p = n => String(n).padStart(2, '0'); return `${m[3]}-${p(MONTHS[m[1]])}-${p(m[2])}`; };
const innings = s => { const f = parseFloat(s) || 0; const w = Math.floor(f); return w + Math.round((f - w) * 10) / 3; };

function parseProduction(text) {
  const L = text.replace(/\r/g, '').trim().split('\n');
  const rows = []; const bench = new Map();
  for (const l of L.slice(1)) {
    const v = parseCSVLine(l);
    const [season, teamId, group, ottoneuId, player, acquired, g, c1, c2, c3, c4, c5] = v;
    const pit = { ip: innings(c1), so: +c2, hr9: +c3, era: +c4, whip: +c5 };
    if (group === 'PBENCH') { bench.set(season + '|' + teamId, pit); continue; }
    rows.push({ season: +season, teamId, group, ottoneuId, player, acquired: isoDate(acquired), g: +g,
      line: group === 'H' ? { ab: +c1, r: +c2, hr: +c3, obp: +c4, slg: +c5 } : pit });
  }
  return { rows, bench };
}

function makeCounted(rows, paRatio) {
  const idx = new Map();
  rows.forEach(r => { const k = r.season + '|' + r.teamId + '|' + r.ottoneuId; const e = idx.get(k) || {}; e[r.group] = r; idx.set(k, e); });
  return (ottoneuId, teamId, season) => {
    const e = idx.get(season + '|' + teamId + '|' + ottoneuId);
    if (!e) return { type: null, line: null };
    if (e.H) {
      const line = { ...e.H.line, pa: Math.round(e.H.line.ab * (paRatio(String(ottoneuId), season) || 1.12)) };
      if (e.P) line.pitch = { ...e.P.line };
      return { type: 'H', line };
    }
    return { type: 'P', line: { ...e.P.line } };
  };
}

function teamsWithPlayer(rows, ottoneuId, season) {
  const seen = new Map();
  rows.filter(r => r.ottoneuId === String(ottoneuId) && r.season === season).forEach(r => seen.set(r.teamId, { teamId: r.teamId, acquired: r.acquired }));
  return [...seen.values()];
}

module.exports = { parseProduction, makeCounted, teamsWithPlayer };
```

- [ ] **Step 4: Run** `node --test audit/test/production.test.js` → PASS (3). Then real data: `node -e "const {parseProduction}=require('./audit/lib/production');const p=parseProduction(require('fs').readFileSync('data/teamproduction.csv','utf8'));console.log(p.rows.length,p.bench.size,p.rows.filter(r=>!r.acquired).length)"` → `2185 36 0`.
- [ ] **Step 5: Commit** `git add audit/lib/production.js audit/test/production.test.js && git commit -m "feat(audit-v2): parse team production; counted-line lookup with PA estimate"`

---

### Task 2: Offseason phases, salary resets, cap deltas

**Files:** Create `audit/lib/offseason.js`, `audit/test/offseason.test.js`

**Interfaces:**
- Consumes: `Move` from `moves.js` (`{id, kind, season, date, teamId, in, out, tradeId, counterTeamId}`).
- Produces:
  - `auctionDays(moves) → { [season]: 'YYYY-MM-DD' }` (earliest `auction` move date per season).
  - `annotateOffseason(moves) → Move[]`: returns new moves with `phase: 'offseason'|'in-season'` (offseason = date ≥ `${S-1}-10-01` and < auction day of S); offseason cut + same-team same-player `auction` in S → the two become one move `{ kind: 'reset', in: [auction P], out: [cut P], resetGrade: out.salary − in.salary }` (id of the cut; auction move removed); trades get `capDelta = Σ out salary − Σ in salary`.

- [ ] **Step 1: Write the failing test**

```js
// audit/test/offseason.test.js
const test = require('node:test');
const assert = require('node:assert');
const { auctionDays, annotateOffseason } = require('../lib/offseason');

const mv = (o) => ({ id: o.id, kind: o.kind, season: o.season, date: o.date, teamId: o.teamId || 'B', counterTeamId: null, tradeId: null, in: o.in || [], out: o.out || [] });
const moves = [
  mv({ id: 'c1', kind: 'cut', season: 2026, date: '2026-01-31', out: [{ ottoneuId: 'y', player: 'Yordan', salary: 52 }] }),
  mv({ id: 'a1', kind: 'auction', season: 2026, date: '2026-03-05', in: [{ ottoneuId: 'y', player: 'Yordan', salary: 51 }] }),
  mv({ id: 'a2', kind: 'auction', season: 2026, date: '2026-03-05', teamId: 'C', in: [{ ottoneuId: 'z', player: 'Zed', salary: 10 }] }),
  mv({ id: 'c2', kind: 'cut', season: 2026, date: '2025-11-15', out: [{ ottoneuId: 'q', player: 'Q', salary: 20 }] }),
  mv({ id: 'c3', kind: 'cut', season: 2026, date: '2026-06-01', out: [{ ottoneuId: 'r', player: 'R', salary: 4 }] }),
  mv({ id: 'c4', kind: 'cut', season: 2026, date: '2025-12-01', teamId: 'D', out: [{ ottoneuId: 'w', player: 'W', salary: 5 }] }),
  mv({ id: 'a4', kind: 'auction', season: 2026, date: '2026-03-05', teamId: 'D', in: [{ ottoneuId: 'w', player: 'W', salary: 9 }] }),
  { ...mv({ id: 't1', kind: 'trade', season: 2026, date: '2025-12-18', out: [{ ottoneuId: 'p', salary: 30 }], in: [{ ottoneuId: 'k', salary: 12 }] }), tradeId: 't', counterTeamId: 'C' },
];

test('auction day per season', () => { assert.deepStrictEqual(auctionDays(moves), { 2026: '2026-03-05' }); });

test('cut + same-team auction rebuy -> one reset move graded old - new', () => {
  const out = annotateOffseason(moves);
  const r = out.find(m => m.kind === 'reset' && m.teamId === 'B');
  assert.strictEqual(r.resetGrade, 1); assert.strictEqual(r.phase, 'offseason');
  assert.ok(!out.some(m => m.id === 'a1'));
});

test('reset that cost more is negative, not dropped', () => {
  const r = annotateOffseason(moves).find(m => m.kind === 'reset' && m.teamId === 'D');
  assert.strictEqual(r.resetGrade, -4);
});

test('phases and cap delta', () => {
  const out = annotateOffseason(moves);
  const ph = id => out.find(m => m.id === id).phase;
  assert.strictEqual(ph('c2'), 'offseason'); assert.strictEqual(ph('c3'), 'in-season'); assert.strictEqual(ph('a2'), 'offseason');
  assert.strictEqual(out.find(m => m.id === 't1').capDelta, 18);
});
```

- [ ] **Step 2: Run** `node --test audit/test/offseason.test.js` → FAIL.

- [ ] **Step 3: Implement**

```js
// audit/lib/offseason.js
// October -> auction moves are cap moves. A cut that the same team buys back at
// the auction is a salary reset, graded on the salary change alone.
function auctionDays(moves) {
  const out = {};
  moves.filter(m => m.kind === 'auction').forEach(m => { if (!out[m.season] || m.date < out[m.season]) out[m.season] = m.date; });
  return out;
}

function annotateOffseason(moves) {
  const days = auctionDays(moves);
  // Auction buys are always offseason (an auction can span several days).
  const isOff = m => m.kind === 'auction' || (m.date >= `${m.season - 1}-10-01` && (!days[m.season] || m.date < days[m.season]));
  const consumed = new Set();
  const resets = new Map();   // cut id -> reset move
  for (const cut of moves.filter(m => m.kind === 'cut' && isOff(m))) {
    const p = cut.out[0];
    const buy = moves.find(a => a.kind === 'auction' && a.season === cut.season && a.teamId === cut.teamId && !consumed.has(a.id)
      && a.in.some(q => q.ottoneuId === p.ottoneuId));
    if (!buy) continue;
    consumed.add(buy.id);
    const np = buy.in.find(q => q.ottoneuId === p.ottoneuId);
    resets.set(cut.id, { ...cut, kind: 'reset', in: [np], out: [p], resetGrade: p.salary - np.salary });
  }
  return moves.filter(m => !consumed.has(m.id)).map(m => {
    const base = resets.get(m.id) || m;
    const x = { ...base, phase: isOff(m) ? 'offseason' : 'in-season' };
    if (x.kind === 'trade') x.capDelta = x.out.reduce((s, p) => s + p.salary, 0) - x.in.reduce((s, p) => s + p.salary, 0);
    return x;
  });
}

module.exports = { auctionDays, annotateOffseason };
```

- [ ] **Step 4: Run** → PASS (4). Real data: `node -e "const {parseTransactions,buildMoves}=require('./audit/lib/moves');const {annotateOffseason}=require('./audit/lib/offseason');const m=annotateOffseason(buildMoves(parseTransactions(require('fs').readFileSync('data/transactions.csv','utf8'))));const r=m.filter(x=>x.kind==='reset');console.log('resets',r.length,r.find(x=>x.out[0].player==='Yordan Alvarez'&&x.season===2026))"` → Yordan 2026 reset with `resetGrade: 1`.
- [ ] **Step 5: Commit** `git add audit/lib/offseason.js audit/test/offseason.test.js && git commit -m "feat(audit-v2): offseason phase, salary resets (cut + auction rebuy), trade cap delta"`

---

### Task 3: Counted-production results

**Files:** Modify `audit/lib/result.js` (add `countedResult`, export it), Test `audit/test/result.test.js` (append)

**Interfaces:**
- Consumes: `lineValue(engine, ctx, type, line)`, `fracOfSeason`, `inSeason` (result.js); `counted` from Task 1; `teamsWithPlayer` rows from Task 1; `tenureEnd(id, teamId, date)`.
- Produces: `countedValue(engine, ctx, c) → $` (adds `c.line.pitch` value for two-way); `countedResult(engine, ctx, move, { counted, teamsWith, tenureEnd, stintCount }) → { result: number, combinedStints: boolean }`:
  - `reset` → `move.resetGrade`.
  - in-player on `move.teamId`: `countedValue(counted(p, team, S)) − salary × fracOfSeason(S, date, tenureEnd)`.
  - cut / swap-out: `freed − Σ countedValue(counted(p, t, S))` over `teamsWith(p, S)` with `t ≠ move.teamId` and `acquired ≥ move.date`; `freed = salary × (phase==='offseason' ? 1 : 0.5) × fracOfSeason(S, date, null)`.
  - trade out-player: `− [countedValue(counted(p, counterTeamId, S)) − salary × fracOfSeason(S, date, tenureEnd(p, counterTeamId, date))]`.
  - `combinedStints` = any in-player has `stintCount(p, team, S) > 1`.

- [ ] **Step 1: Write the failing tests** (append to `audit/test/result.test.js`)

```js
const { countedResult } = require('../lib/result');
const look = map => (id, team) => map[id + '|' + team] || { type: null, line: null };
const hitL = (pa, hr, r, obp, slg) => ({ type: 'H', line: { pa, hr, r, obp, slg } });
const opts = (map, teams = {}, stints = {}) => ({
  counted: look(map), teamsWith: (id) => teams[id] || [], tenureEnd: () => null, stintCount: (id, t) => stints[id + '|' + t] || 1,
});

test('trade: received player counted almost nothing -> that side loses', () => {
  const move = { kind: 'trade', season: 2026, date: '2026-05-13', teamId: 'BUR', counterTeamId: 'ME', phase: 'in-season',
    in: [{ ottoneuId: 'don', salary: 7 }], out: [{ ottoneuId: 'lugo', salary: 3 }] };
  const map = { 'don|BUR': hitL(17, 0, 2, .333, .533), 'lugo|ME': { type: 'P', line: { ip: 90, so: 85, era: 3.4, whip: 1.15, hr9: 1.0 } } };
  const r = countedResult(e, ctx, move, opts(map));
  assert.ok(r.result < 0, `Bureau side ${r.result}`);
});

test('traded-away player with no production row counts zero; trade still grades', () => {
  const move = { kind: 'trade', season: 2026, date: '2026-07-01', teamId: 'A', counterTeamId: 'B', phase: 'in-season',
    in: [{ ottoneuId: 'star', salary: 10 }], out: [{ ottoneuId: 'prospect', salary: 1 }] };
  const r = countedResult(e, ctx, move, opts({ 'star|A': hitL(250, 15, 40, .36, .52) }));
  assert.ok(Number.isFinite(r.result) && r.result > 0);
});

test('offseason cut frees full salary; production only from later teams', () => {
  const move = { kind: 'cut', season: 2026, date: '2025-11-15', teamId: 'A', phase: 'offseason', in: [], out: [{ ottoneuId: 'q', salary: 20 }] };
  const r = countedResult(e, ctx, move, opts({}, { q: [] }));
  assert.ok(Math.abs(r.result - 20) < 1e-9);
});

test('reset returns its salary grade', () => {
  const r = countedResult(e, ctx, { kind: 'reset', resetGrade: 1, season: 2026, date: '2026-01-31', in: [], out: [] }, opts({}));
  assert.strictEqual(r.result, 1);
});

test('player with two stints on the same team in a season is flagged combinedStints', () => {
  const move = { kind: 'add', season: 2026, date: '2026-07-01', teamId: 'A', phase: 'in-season', in: [{ ottoneuId: 'x', salary: 1 }], out: [] };
  const r = countedResult(e, ctx, move, opts({ 'x|A': hitL(100, 3, 12, .31, .40) }, {}, { 'x|A': 2 }));
  assert.strictEqual(r.combinedStints, true);
});
```

- [ ] **Step 2: Run** `node --test audit/test/result.test.js` → 5 new FAIL (`countedResult is not a function`).

- [ ] **Step 3: Implement** (append to `audit/lib/result.js` before `module.exports`, and export `countedValue, countedResult`)

```js
// v2: grade on what actually counted for each team (Ottoneu team production).
function countedValue(engine, ctx, c) {
  if (!c || !c.line) return 0;
  let v = lineValue(engine, ctx, c.type, c.line);
  if (c.type === 'H' && c.line.pitch && (c.line.pitch.ip || 0) >= engine.get('TWO_WAY_IP_MIN')) v += lineValue(engine, ctx, 'P', c.line.pitch);
  return v;
}

function countedResult(engine, ctx, move, { counted, teamsWith, tenureEnd, stintCount }) {
  if (move.kind === 'reset') return { result: move.resetGrade, combinedStints: false };
  const S = move.season, d = move.date;
  let total = 0, combined = false;
  for (const p of move.in) {
    const end = tenureEnd(p.ottoneuId, move.teamId, d);
    total += countedValue(engine, ctx, counted(p.ottoneuId, move.teamId, S)) - p.salary * fracOfSeason(S, d, end);
    if (stintCount(p.ottoneuId, move.teamId, S) > 1) combined = true;
  }
  for (const p of move.out) {
    if (move.kind === 'trade') {
      const end = tenureEnd(p.ottoneuId, move.counterTeamId, d);
      total -= countedValue(engine, ctx, counted(p.ottoneuId, move.counterTeamId, S)) - p.salary * fracOfSeason(S, d, end);
    } else {
      const freed = p.salary * (move.phase === 'offseason' ? 1 : 0.5) * fracOfSeason(S, d, null);
      const later = teamsWith(p.ottoneuId, S).filter(t => t.teamId !== move.teamId && t.acquired >= d);
      total += freed - later.reduce((s, t) => s + countedValue(engine, ctx, counted(p.ottoneuId, t.teamId, S)), 0);
    }
  }
  return { result: total, combinedStints: combined };
}
```

- [ ] **Step 4: Run** → all result tests PASS (10).
- [ ] **Step 5: Commit** `git add audit/lib/result.js audit/test/result.test.js && git commit -m "feat(audit-v2): results from counted production; resets; offseason cuts free full salary"`

---

### Task 4: Roto points contributed + title-deciding

**Files:** Create `audit/lib/contributed.js`, `audit/test/contributed.test.js`

**Interfaces:**
- Consumes: `scoreStandings(engine, teams)` from `counterfactual.js`.
- Produces:
  - `teamTotalsFromLines(lines) → { pa, ip }` where `lines` = counted lines of one team-season.
  - `ptsContributed(engine, final, teamId, c, totals) → number` — `final = [{teamId, stats, ip}]`; removes counted line `c` from that team (counting − ; rates re-weighted over `totals.pa`/`totals.ip` minus the player's PA/IP; team IP for the 1,250 rule = `final.ip − c.line.ip`) and returns points(actual) − points(removed) for that team.
  - `titleDeciding(finalWithPoints, teamId, net) → 'won-title'|'made-podium'|'cost-title'|'cost-podium'|null` using real `points` and rank order of `finalWithPoints` (sorted desc).

- [ ] **Step 1: Write the failing test**

```js
// audit/test/contributed.test.js
const test = require('node:test');
const assert = require('node:assert');
const { loadEngine } = require('../lib/engine');
const { ptsContributed, titleDeciding, teamTotalsFromLines } = require('../lib/contributed');

const e = loadEngine();
const base = { OBP: .330, SLG: .430, HR: 200, R: 800, ERA: 3.9, WHIP: 1.22, HR9: 1.15, SO: 1300 };
const final = [
  { teamId: 'A', ip: 1400, stats: { ...base, HR: 230 } },
  { teamId: 'B', ip: 1400, stats: { ...base, HR: 220 } },
  { teamId: 'C', ip: 1400, stats: { ...base, HR: 210 } },
];

test('a 30-HR counted line is worth points; a 1-AB line is worth ~nothing', () => {
  const totals = { pa: 6000, ip: 1400 };
  assert.ok(ptsContributed(e, final, 'A', { type: 'H', line: { pa: 500, hr: 30, r: 70, obp: .35, slg: .50 } }, totals) >= 2);
  assert.strictEqual(ptsContributed(e, final, 'A', { type: 'H', line: { pa: 1, hr: 0, r: 0, obp: 0, slg: 0 } }, totals), 0);
});

test('removing innings that drop a staff under 1,250 IP costs all pitching points', () => {
  const totals = { pa: 6000, ip: 1300 };
  const f = final.map(t => (t.teamId === 'A' ? { ...t, ip: 1300 } : t));
  const pts = ptsContributed(e, f, 'A', { type: 'P', line: { ip: 60, so: 50, era: 3.9, whip: 1.22, hr9: 1.15 } }, totals);
  assert.ok(pts >= 4, `lost pitching points ${pts}`);
});

test('teamTotalsFromLines sums PA and IP', () => {
  assert.deepStrictEqual(teamTotalsFromLines([{ type: 'H', line: { pa: 10 } }, { type: 'P', line: { ip: 5 } }, { type: null, line: null }]), { pa: 10, ip: 5 });
});

test('titleDeciding uses real margins', () => {
  const pts = [{ teamId: 'BUR', points: 82 }, { teamId: 'ME', points: 79 }, { teamId: 'MTP', points: 70 }, { teamId: 'FCH', points: 61 }];
  assert.strictEqual(titleDeciding(pts, 'BUR', 3), 'won-title');
  assert.strictEqual(titleDeciding(pts, 'BUR', 2.5), null);
  assert.strictEqual(titleDeciding(pts, 'ME', -3), 'cost-title');
  assert.strictEqual(titleDeciding(pts, 'MTP', 9), 'made-podium');
  assert.strictEqual(titleDeciding(pts, 'FCH', -9), 'cost-podium');
});
```

- [ ] **Step 2: Run** `node --test audit/test/contributed.test.js` → FAIL.

- [ ] **Step 3: Implement**

```js
// audit/lib/contributed.js
// v2 standings: how many final roto points a player's COUNTED stats were worth to
// the team (team points minus points with that line removed). No invented replacement.
const { scoreStandings } = require('./counterfactual');

function teamTotalsFromLines(lines) {
  return lines.reduce((t, c) => {
    if (!c || !c.line) return t;
    if (c.type === 'H') { t.pa += c.line.pa || 0; if (c.line.pitch) t.ip += c.line.pitch.ip || 0; } else t.ip += c.line.ip || 0;
    return t;
  }, { pa: 0, ip: 0 });
}

function removeLine(stats, ip, c, totals) {
  const s = { ...stats }; let tip = ip;
  const dropH = l => {
    const pa = l.pa || 0, rest = Math.max(1, totals.pa - pa);
    s.HR -= l.hr || 0; s.R -= l.r || 0;
    s.OBP = (stats.OBP * totals.pa - (l.obp || 0) * pa) / rest;
    s.SLG = (stats.SLG * totals.pa - (l.slg || 0) * pa) / rest;
  };
  const dropP = l => {
    const lip = l.ip || 0, restIP = Math.max(1, totals.ip - lip);
    for (const [k, f] of [['ERA', 'era'], ['WHIP', 'whip'], ['HR9', 'hr9']]) s[k] = (stats[k] * totals.ip - (l[f] || 0) * lip) / restIP;
    s.SO -= l.so || 0; tip = ip - lip;
  };
  if (c.type === 'H') { dropH(c.line); if (c.line.pitch) dropP(c.line.pitch); } else if (c.type === 'P') dropP(c.line);
  return { stats: s, ip: tip };
}

function ptsContributed(engine, final, teamId, c, totals) {
  if (!c || !c.line) return 0;
  const pointsOf = teams => scoreStandings(engine, teams).find(t => t.teamId === teamId).points;
  const actual = pointsOf(final);
  const without = pointsOf(final.map(t => (t.teamId === teamId ? { teamId, ...removeLine(t.stats, t.ip, c, totals) } : t)));
  return actual - without;
}

function titleDeciding(finalWithPoints, teamId, net) {
  const s = [...finalWithPoints].sort((a, b) => b.points - a.points);
  const i = s.findIndex(t => t.teamId === teamId); if (i < 0 || !net) return null;
  const P = s[i].points;
  if (net > 0) {
    if (i === 0 && s[1] && net >= P - s[1].points) return 'won-title';
    if (i > 0 && i <= 2 && s[3] && net >= P - s[3].points) return 'made-podium';
  } else {
    if (i === 1 && -net >= s[0].points - P) return 'cost-title';
    if (i >= 3 && s[2] && -net >= s[2].points - P) return 'cost-podium';
  }
  return null;
}

module.exports = { ptsContributed, titleDeciding, teamTotalsFromLines };
```

- [ ] **Step 4: Run** → PASS (4).
- [ ] **Step 5: Commit** `git add audit/lib/contributed.js audit/test/contributed.test.js && git commit -m "feat(audit-v2): roto points contributed from counted lines; title-deciding by real margins"`

---

### Task 5: Rewire the runner (grade, standings, winters)

**Files:** Modify `audit/run.js`; Modify `audit/test/output.test.js`

**Interfaces:**
- Consumes: Tasks 1–4; existing `finalStandings`, `makeStatsIndex`, `makeLookup`, `makeStintEnd`, `buildIdentity`, `seasonContext`, `moveProcess`.
- Produces in `data/audit.json` moves: `phase`, `capDelta` (trades), `combinedStints`, `result`, `process`, `luck`, `ptsContributed` (number|null), `titleDeciding` (string|null); remove `standings`, `decisive`, `fragile`; top-level `winters` and no `jointCuts`. `finalStandings` rows gain `points: +r.Points`.

- [ ] **Step 1: Update the output tests first** (replace the first test in `audit/test/output.test.js`; keep the NaN test)

```js
test('v2: Yordan 2026 cut is a +$1 reset; Donovan trade gives Bureau ~0 points', { skip: !a && 'no audit.json' }, () => {
  const y = a.moves.find(m => m.kind === 'reset' && m.season === 2026 && m.out.some(p => p.player === 'Yordan Alvarez'));
  assert.ok(y, 'reset exists'); assert.strictEqual(Math.round(y.result), 1);
  const bur = a.moves.find(m => m.kind === 'trade' && m.date === '2026-05-13' && m.teamId === '10818');
  assert.ok(bur.ptsContributed !== null && Math.abs(bur.ptsContributed) <= 2, `Bureau pts ${bur.ptsContributed}`);
  assert.ok(a.winters && a.winters['2026'] && a.winters['2026']['10925'], 'winters present');
  assert.ok(a.moves.every(m => m.phase === 'offseason' || m.phase === 'in-season'));
});
```

- [ ] **Step 2: Run** `node --test audit/test/output.test.js` → FAIL (no reset / no winters yet).

- [ ] **Step 3: Implement in `audit/run.js`**
  1. Requires: add `const { parseProduction, makeCounted, teamsWithPlayer } = require('./lib/production');`, `const { annotateOffseason } = require('./lib/offseason');`, `const { ptsContributed, titleDeciding, teamTotalsFromLines } = require('./lib/contributed');`, and import `countedResult, countedValue` from `./lib/result`. Remove the `undoMove` import.
  2. `finalStandings`: add `points: +r.Points` to each team.
  3. `moves` phase: `moves: annotateOffseason(buildMoves(txs))`; add `read('data/teamproduction.csv')` to the moves and grade `inputsHash`.
  4. `grade` phase: after building `ident`/`st`, define
     ```js
     const prod = parseProduction(read('data/teamproduction.csv'));
     const paRatio = (id, s) => { const who = ident.map.get(String(id)); if (!who || who.group !== 'h') return null;
       const l = st.window(who.mlbId, 'h', `${s}-03-01`, `${s}-10-15`); return l && l.ab ? l.pa / l.ab : null; };
     const counted = makeCounted(prod.rows, paRatio);
     const stintCount = (id, team, s) => stints.filter(x => x.ottoneuId === String(id) && x.teamId === team && x.start < `${s}-09-28` && (!x.end || x.end > `${s}-03-28`)).length;
     const teamsWith = (id, s) => teamsWithPlayer(prod.rows, id, s);
     ```
     Season context: `stintLines` becomes every counted line of the season: `prod.rows.filter(r => r.season === s).map(r => counted(r.ottoneuId, r.teamId, s))`; `freeAgentLines` unchanged. Results: replace `moveResult(...)` with
     `const cr = ctx ? countedResult(engine, ctx, m, { counted, teamsWith, tenureEnd: (id, team, date) => stintEnd(id, team, date), stintCount }) : { result: null, combinedStints: false };`
     and spread `result: cr.result, combinedStints: cr.combinedStints` into the graded move. Return `prodRows: prod.rows` and the `paRatio` values are recomputed in later phases (functions don't checkpoint) — so also return `paRatios: Object.fromEntries(prod.rows.filter(r => r.group === 'H').map(r => [r.season + '|' + r.ottoneuId, paRatio(r.ottoneuId, r.season)]))`.
  5. Replace the whole `standings` phase body with (inputsHash `hashOf(txText, read('data/teamproduction.csv'), 'v3')`):
     ```js
     run: async (r) => {
       const counted = makeCounted(r.grade.prodRows, (id, s) => r.grade.paRatios[s + '|' + id] || null);
       const byMove = {};
       for (const s of seasons) {
         const final = finalStandings(engine, s); if (!final) continue;
         const totals = {}; final.forEach(t => { totals[t.teamId] = teamTotalsFromLines(r.grade.prodRows.filter(x => x.season === s && x.teamId === t.teamId).map(x => counted(x.ottoneuId, x.teamId, s))); });
         const memo = new Map();
         const pts = (id, team) => { const k = id + '|' + team; if (!memo.has(k)) memo.set(k, totals[team] ? ptsContributed(engine, final, team, counted(id, team, s), totals[team]) : 0); return memo.get(k); };
         for (const m of r.grade.graded.filter(x => x.season === s)) {
           let net = 0;
           if (m.kind === 'reset') net = 0;
           else if (m.kind === 'trade') net = m.in.reduce((q, p) => q + pts(p.ottoneuId, m.teamId), 0) - m.out.reduce((q, p) => q + pts(p.ottoneuId, m.counterTeamId), 0);
           else {
             net = m.in.reduce((q, p) => q + pts(p.ottoneuId, m.teamId), 0);
             m.out.forEach(p => teamsWithPlayer(r.grade.prodRows, p.ottoneuId, s).filter(t => t.teamId !== m.teamId && t.acquired >= m.date).forEach(t => { net -= pts(p.ottoneuId, t.teamId); }));
           }
           byMove[m.id] = { ptsContributed: net, titleDeciding: titleDeciding(final, m.teamId, net) };
         }
       }
       return { byMove, seasonsWithoutStandings: seasons.filter(s => !finalStandings(engine, s)) };
     }
     ```
  6. `write` phase: merge `r.standings.byMove[m.id] || { ptsContributed: null, titleDeciding: null }` instead of the v1 fields; delete `jointCuts`; add `winters`:
     ```js
     const winters = {};
     for (const m of moves) {
       const w = ((winters[m.season] = winters[m.season] || {})[m.teamId] = winters[m.season][m.teamId] || { freed: 0, resetSavings: 0, tradeSalary: 0, auctionSpend: 0, auctionReturn: 0 });
       if (m.phase !== 'offseason') continue;
       if (m.kind === 'cut') w.freed += m.out.reduce((q, p) => q + p.salary, 0);
       if (m.kind === 'reset') w.resetSavings += m.resetGrade;
       if (m.kind === 'trade') w.tradeSalary += m.capDelta || 0;
       if (m.kind === 'auction') { w.auctionSpend += m.in.reduce((q, p) => q + p.salary, 0); w.auctionReturn += m.result || 0; }
     }
     ```
     and set `audit.winters = winters`. Update `approximations` to: counted stats are Ottoneu's lineup-only numbers; per player/team/season lines (multiple stints combined, flagged); hitter PA estimated from AB; points contributed = team points minus points without that line (no replacement); process grades 2026-05-24 → season end only.
  7. Summary print: replace the snapshot line's neighbour with `console.log('resets', moves.filter(m=>m.kind==='reset').length, '· title-deciding', moves.filter(m=>m.titleDeciding).length)` — read from `data/audit.json`.
- [ ] **Step 4: Run** `node audit/run.js --force=moves` then `node --test audit/test/*.test.js` → all PASS, including the output test.
- [ ] **Step 5: Commit** `git add audit/run.js audit/test/output.test.js data/audit.json data/review.json && git commit -m "feat(audit-v2): runner grades on counted production; points contributed; winter cap summaries"`

---

### Task 6: Review cards for v2

**Files:** Modify `audit/lib/review.js`; Modify `audit/test/review.test.js`

**Interfaces:**
- Consumes: v2 move fields (`titleDeciding`, `ptsContributed`, `kind: 'reset'`, `phase`), `audit.winters`.
- Produces: cards `title-1..3` (replace `decisive*`), `cut-that-haunts` (cuts only, not resets/swaps-as-resets), new `winter-of-year` (`numbers: { auctionReturn, auctionSpend, freed, resetSavings }`), others unchanged.

- [ ] **Step 1: Update tests** — in `audit/test/review.test.js`: change the `mv()` default to `{ ..., ptsContributed: 0, titleDeciding: null }`, change move `e` to `titleDeciding: 'won-title', ptsContributed: 4`, and replace assertions on `c['decisive']` with `c['title-1']`; replace the "decisive cards" test with:

```js
test('title cards: one per trade, only moves that decided a place; winter card from winters', () => {
  const both = { ...audit, winters: { 2026: { 1: { freed: 30, resetSavings: 1, tradeSalary: 0, auctionSpend: 60, auctionReturn: 25 }, 2: { freed: 10, resetSavings: 0, tradeSalary: 0, auctionSpend: 40, auctionReturn: -5 } } },
    moves: audit.moves.concat([
      mv({ id: 'w', teamId: '1', kind: 'trade', tradeId: 't9', counterTeamId: '2', result: 5, titleDeciding: 'won-title', ptsContributed: 6, in: [{ player: 'Raleigh', salary: 20 }] }),
      mv({ id: 'l', teamId: '2', kind: 'trade', tradeId: 't9', counterTeamId: '1', result: -5, titleDeciding: null, ptsContributed: -6, in: [{ player: 'Ward', salary: 10 }] }),
      mv({ id: 'r', teamId: '2', kind: 'reset', result: 1, out: [{ player: 'Yordan', salary: 52 }] }),
    ]) };
  const c = buildCards(both, 2026);
  const titles = c.filter(x => x.id.startsWith('title-'));
  assert.ok(titles.some(x => x.players.includes('Raleigh')) && !titles.some(x => x.players.includes('Ward')));
  assert.notStrictEqual(c.find(x => x.id === 'cut-that-haunts').players[0], 'Yordan');
  assert.strictEqual(c.find(x => x.id === 'winter-of-year').teamId, '1');
});
```

- [ ] **Step 2: Run** `node --test audit/test/review.test.js` → FAIL.
- [ ] **Step 3: Implement** in `audit/lib/review.js`:
  - Replace the decisive block with:
    ```js
    const seenTrade = new Set();
    const LABEL = { 'won-title': 'The Move That Won It', 'made-podium': 'The Move That Made the Podium', 'cost-title': 'The Move That Cost the Title', 'cost-podium': 'The Move That Cost the Podium' };
    mv.filter(m => m.titleDeciding).sort((a, b) => Math.abs(b.ptsContributed) - Math.abs(a.ptsContributed))
      .filter(m => !m.tradeId || (!seenTrade.has(m.tradeId) && seenTrade.add(m.tradeId))).slice(0, 3)
      .forEach((m, i) => push({ id: 'title-' + (i + 1), title: LABEL[m.titleDeciding], teamId: m.teamId, team: name(m.teamId),
        numbers: { pts: Math.round(m.ptsContributed * 10) / 10, kind: m.titleDeciding }, players: (m.in.length ? m.in : m.out).map(p => p.player) }));
    ```
  - `cuts` filter: `m => m.kind === 'cut'` (resets have their own kind; swaps excluded).
  - Winter card (after auction cards):
    ```js
    const w = Object.entries((audit.winters || {})[season] || {}).sort((a, b) => b[1].auctionReturn - a[1].auctionReturn)[0];
    if (w) push({ id: 'winter-of-year', title: 'Winter of the Year', teamId: w[0], team: name(w[0]),
      numbers: { auctionReturn: Math.round(w[1].auctionReturn), auctionSpend: w[1].auctionSpend, freed: w[1].freed, resetSavings: w[1].resetSavings } });
    ```
- [ ] **Step 4: Run** → PASS; `node audit/run.js` (write phase only) regenerates `data/review.json`.
- [ ] **Step 5: Commit** `git add audit/lib/review.js audit/test/review.test.js data/review.json && git commit -m "feat(audit-v2): title cards from real margins, winter of the year, resets excluded from haunting cuts"`

---

### Task 7: Pages

**Files:** Modify `audit.html`, `review.html`

- [ ] **Step 1: `audit.html`**
  - Patterns: group keys become kind × phase — `[['add','in-season','Pickups'], ['swap','in-season','Swaps'], ['cut','in-season','In-season cuts'], ['cut','offseason','Offseason cuts (cap)'], ['reset','offseason','Salary resets'], ['trade','in-season','In-season trades'], ['trade','offseason','Offseason trades'], ['auction','offseason','Auction buys']]`, filter `m.kind === k && m.phase === ph`.
  - Headline tile "Roto pts from moves" sums `m.ptsContributed`; sub-label "points your moves' counted stats were worth".
  - Standings section: sort by `m.ptsContributed`; column "Pts contributed"; chip from `m.titleDeciding` (`won-title`→"won the title", `made-podium`→"made the podium", `cost-title`→"cost the title", `cost-podium`→"cost the podium"); delete the joint-cuts note.
  - New section "Your winters" after Standings: table for every season in `A.winters` row `A.winters[y][A.myTeamId]`: Season, Cap freed by cuts, Reset savings, Net trade salary, Auction spend, Auction return (money format), plus league median of auction return per season.
  - Move table: Δ pts column reads `m.ptsContributed`; add a "Phase" column after Move.
- [ ] **Step 2: `review.html`**: in `ORDER` replace `decisive, decisive-1, decisive-2` with `title-1, title-2, title-3` and add `winter-of-year` after `auction-worst`; `body()` cases: `title` → big `±N pts` + players + stat "Points these players' counted stats were worth — enough to decide the place."; `winter-of-year` → big `money(auctionReturn)` + stat `"Auction: $" + auctionSpend + " spent · cap freed $" + freed + (resetSavings ? " · resets " + money(resetSavings) : "")`. Remove the `decisive` case.
- [ ] **Step 3: Verify** with the render check (vm + fake DOM, exercises clicks) for both pages against regenerated data: no errors; `audit.html` text contains "Your winters" and "Offseason cuts (cap)"; `review.html` has a "Winter of the Year" card.
- [ ] **Step 4: Commit** `git add audit.html review.html && git commit -m "feat(audit-v2): pages -- phase split, points contributed, winters table, new cards"`

---

### Task 8: Commentary, docs, memory

- [ ] **Step 1:** Rewrite `data/review-commentary.json` for the regenerated cards (ids `title-1..3`, `winter-of-year`, and any card whose subject changed). Rules: backed by the card's numbers, light, ≤140 chars, no gendered pronouns for managers or players. Draft — user approves.
- [ ] **Step 2:** `MODEL.md` §9: replace the Result and Standings-replay paragraphs with the v2 definitions (counted production, PA estimate, points contributed, title-deciding, offseason phase/resets/winters); keep the data-quirks list and add "teamproduction: one line per player/team/season".
- [ ] **Step 3:** README decision-audit bullets: add refreshing `data/teamproduction.csv` (in-tab fetch of `/1648/teamproduction/<team>/<year>` for 12 teams, saved as CSV).
- [ ] **Step 4:** Republish the two private preview artifacts (local self-contained copies) so the user can check on a phone.
- [ ] **Step 5: Commit** `git add data/review-commentary.json MODEL.md README.md && git commit -m "docs(audit-v2): commentary draft, MODEL.md v2 conventions, README refresh steps"`; update `project_build_status.md` memory (v2 shipped; commentary pending approval).
