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
