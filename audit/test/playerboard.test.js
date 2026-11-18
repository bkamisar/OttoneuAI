const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { loadEngine } = require('../lib/engine');

function withBoard() {
  const e = loadEngine();
  e.get(fs.readFileSync(path.join(__dirname, '..', '..', 'playerboard.js'), 'utf8'));
  return e;
}

const P = (name, team, positions, type, salary) => ({ name, rawName: name, fgId: name, team, positions, type, salary });
const teams = {
  Mine: [P('Zach Neto', 'Mine', ['ss'], 'H', 11)],
  Them: [P('Pedro Ramírez', 'Them', ['2b', '3b'], 'H', 5), P('Ace', 'Them', ['sp'], 'P', 30)],
  'Free Agent': [P('Nobody', 'Free Agent', ['of'], 'H', 0)],
};
const dyn = {
  'Zach Neto': { projectedValue: 26, dynastyValue: 143, dynastySurplus: 77, holdHorizon: 5 },
  'Pedro Ramírez': { projectedValue: null, dynastyValue: 21, dynastySurplus: 3, holdHorizon: 2 },
  Ace: { projectedValue: 40, dynastyValue: 40, dynastySurplus: null, holdHorizon: 0 },
};
const opts = { myTeam: 'Mine', ages: {}, prospects: { 'Pedro Ramírez': { fv: 50 } }, season: 2027, market: () => null };

test('pbBuildRows lists rostered players only, marks mine, computes trade value', () => {
  const e = withBoard();
  const rows = e.call('pbBuildRows', teams, dyn, opts);
  assert.deepStrictEqual(Array.from(rows, r => r.name).sort(), ['Ace', 'Pedro Ramírez', 'Zach Neto']);
  const neto = rows.find(r => r.name === 'Zach Neto');
  assert.strictEqual(neto.mine, true);
  assert.strictEqual(neto.pos, 'SS');
  // cost = 143 - 77 = 66; tv = 143 - 0.25*66 = 126.5
  assert.ok(Math.abs(neto.tv - 126.5) < 1e-9);
  const ram = rows.find(r => r.name === 'Pedro Ramírez');
  assert.strictEqual(ram.fv, 50);
  assert.strictEqual(ram.prospect, true);
  assert.strictEqual(ram.pos, '2B/3B');
  // market blend raises tv by 0.25 * sample * (actual - proj)
  const withMkt = e.call('pbBuildRows', teams, dyn, Object.assign({}, opts, { market: p => p.name === 'Zach Neto' ? { actual: 30, sample: 1 } : null }));
  assert.ok(withMkt.find(r => r.name === 'Zach Neto').tv > neto.tv);
});

test('pbFilter matches multi-position, accent-insensitive search, hide mine, prospects only', () => {
  const e = withBoard();
  const rows = e.call('pbBuildRows', teams, dyn, opts);
  const names = f => Array.from(e.call('pbFilter', rows, f), r => r.name).sort();
  assert.deepStrictEqual(names({ pos: '2B' }), ['Pedro Ramírez']);
  assert.deepStrictEqual(names({ search: 'ramirez' }), ['Pedro Ramírez']);
  assert.deepStrictEqual(names({ hideMine: true }), ['Ace', 'Pedro Ramírez']);
  assert.deepStrictEqual(names({ prospectsOnly: true }), ['Pedro Ramírez']);
  assert.deepStrictEqual(names({ type: 'P' }), ['Ace']);
  assert.deepStrictEqual(names({ team: 'Mine' }), ['Zach Neto']);
  assert.deepStrictEqual(names({}), ['Ace', 'Pedro Ramírez', 'Zach Neto']);
});

test('pbSort puts nulls last in both directions and sorts strings', () => {
  const e = withBoard();
  const rows = e.call('pbBuildRows', teams, dyn, opts);
  assert.deepStrictEqual(Array.from(e.call('pbSort', rows, 'surplus', 'desc'), r => r.name), ['Zach Neto', 'Pedro Ramírez', 'Ace']);
  assert.deepStrictEqual(Array.from(e.call('pbSort', rows, 'surplus', 'asc'), r => r.name), ['Pedro Ramírez', 'Zach Neto', 'Ace']);
  assert.deepStrictEqual(Array.from(e.call('pbSort', rows, 'y0', 'asc'), r => r.name), ['Zach Neto', 'Ace', 'Pedro Ramírez']);
  assert.deepStrictEqual(Array.from(e.call('pbSort', rows, 'name', 'asc'), r => r.name), ['Ace', 'Pedro Ramírez', 'Zach Neto']);
});
