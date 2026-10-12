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
