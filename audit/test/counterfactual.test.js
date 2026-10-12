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
