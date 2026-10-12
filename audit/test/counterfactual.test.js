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

const { scoreStandings } = require('../lib/counterfactual');
const fs = require('fs'); const path = require('path');

test('teams under 1250 IP get zero pitching points; others unchanged (Ottoneu rule)', () => {
  const t = (id, ip, x) => ({ teamId: id, ip, stats: { ...base, ERA: 3 + x, SO: 1500 - x * 100, HR: 200 + x } });
  const s = scoreStandings(e, [t('A', 1400, 0), t('B', 1100, 1), t('C', 1400, 2)]);
  const pts = Object.fromEntries(s.map(x => [x.teamId, x.points]));
  // OBP/SLG/R are tied (input order: A3 B2 C1); HR: C3 B2 A1. B keeps hitting only: 2+2+2+2.
  assert.strictEqual(pts.B, 8);
  // A: hitting 3+3+3+1 = 10, pitching untouched (best ERA, SO; ties input order) = 12.
  assert.strictEqual(pts.A, 22);
});

test('reproduces real Ottoneu final points for 2024-2026', () => {
  const { parseCSVLine } = require('../lib/moves');
  for (const y of [2024, 2025, 2026]) {
    const L = fs.readFileSync(path.join(__dirname, '..', '..', `data/standings-final-${y}.csv`), 'utf8').replace(/\r/g, '').trim().split('\n');
    const H = parseCSVLine(L[0]);
    const teams = L.slice(1).map(l => { const v = parseCSVLine(l); const o = {}; H.forEach((h, i) => { o[h] = v[i]; });
      return { teamId: o.TeamID, real: +o.Points, ip: e.call('parseIPInnings', o.IP),
        stats: { R: +o.R, HR: +o.HR, OBP: +o.OBP, SLG: +o.SLG, SO: +o.K, HR9: +o['HR/9'], ERA: +o.ERA, WHIP: +o.WHIP } }; });
    const s = scoreStandings(e, teams);
    const err = teams.reduce((acc, t) => acc + Math.abs(s.find(x => x.teamId === t.teamId).points - t.real), 0);
    assert.ok(err <= 2, `${y} total abs error ${err}`);   // Ottoneu splits ties (.5); buildStandings doesn't
  }
});
