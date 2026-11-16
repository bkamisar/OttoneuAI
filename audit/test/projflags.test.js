const test = require('node:test');
const assert = require('node:assert');
const { computeFlags } = require('../../tools/projflags');

const norm = s => String(s).toLowerCase();
const H = (Name, PA) => ({ Name, Team: 'X', PA: String(PA), AB: String(Math.round(PA * 0.9)), HR: '20', R: '70', OBP: '.340', SLG: '.450' });
const P = (Name, IP) => ({ Name, Team: 'X', IP: String(IP), SO: String(Math.round(IP)), ERA: '3.50', WHIP: '1.15', 'HR/9': '1.0', GS: '30', G: '30' });

const input = {
  steamerH: [H('Jose Ramirez', 1), H('Prospect Kid', 20), H('Steady Bat', 600), H('Part Timer', 260), H('Gap Of 220', 400)],
  zipsH: [H('Jose Ramirez', 600), H('Prospect Kid', 565), H('Steady Bat', 610), H('Part Timer', 520), H('Gap Of 220', 620)],
  steamerP: [P('Hunter Greene', 1), P('Jacob Misiorowski', 183), P('Tarik Skubal', 192)],
  zipsP: [P('Hunter Greene', 144), P('Jacob Misiorowski', 116), P('Tarik Skubal', 182)],
  // usage = best single season of the last three (an injured 2026 must not hide an established arm)
  usage: new Map([['jose ramirez', { pa: 650, ip: 0 }], ['steady bat', { pa: 640, ip: 0 }], ['part timer', { pa: 410, ip: 0 }], ['gap of 220', { pa: 500, ip: 0 }],
    ['hunter greene', { pa: 0, ip: 150 }], ['jacob misiorowski', { pa: 0, ip: 140 }], ['tarik skubal', { pa: 0, ip: 190 }]]),
  norm,
};

test('established player at ~0 in Steamer gets the ZiPS season as a fill, and a flag saying so', () => {
  const r = computeFlags(input);
  assert.deepStrictEqual(r.fillsH.map(x => x.Name), ['Jose Ramirez']);
  assert.strictEqual(r.fillsH[0].PA, '600');
  assert.deepStrictEqual(r.fillsP.map(x => x.Name), ['Hunter Greene']);
  const f = r.flags.find(x => x.Name === 'Jose Ramirez');
  assert.deepStrictEqual([f.Kind, f.Steamer, f.Zips, f.Unit], ['zips-fill', '1', '600', 'PA']);
});

test('big workload disagreement between two real projections is flagged, not filled', () => {
  const r = computeFlags(input);
  const m = r.flags.find(x => x.Name === 'Jacob Misiorowski');
  assert.deepStrictEqual([m.Kind, m.Steamer, m.Zips, m.Unit], ['workload', '183', '116', 'IP']);
  assert.ok(r.flags.find(x => x.Name === 'Part Timer' && x.Kind === 'workload'));       // 260 vs 520 PA (gap 260)
  assert.ok(!r.flags.find(x => x.Name === 'Gap Of 220'));                               // under the 250-PA cutoff
  assert.ok(!r.fillsP.some(x => x.Name === 'Jacob Misiorowski'));
});

test('prospects (no 2026 MLB playing time) and players the systems agree on are never flagged', () => {
  const r = computeFlags(input);
  const names = r.flags.map(x => x.Name);
  assert.ok(!names.includes('Prospect Kid'));
  assert.ok(!names.includes('Steady Bat'));
  assert.ok(!names.includes('Tarik Skubal'));                                          // 192 vs 182
});

test('only rostered players get filled; an unrostered established player at ~0 is flagged steamer-zero', () => {
  const r = computeFlags({ ...input, fillOnly: new Set(['jose ramirez']) });
  assert.deepStrictEqual(r.fillsH.map(x => x.Name), ['Jose Ramirez']);
  assert.deepStrictEqual(r.fillsP, []);
  assert.strictEqual(r.flags.find(x => x.Name === 'Hunter Greene').Kind, 'steamer-zero');
});
