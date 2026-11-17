const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { loadEngine } = require('../lib/engine');

function withFinder() {
  const e = loadEngine();
  e.get(fs.readFileSync(path.join(__dirname, '..', '..', 'tradefinder.js'), 'utf8'));
  return e;
}

test('tfCapPlan keeps the best value per salary dollar under the cap and cuts the rest', () => {
  const e = withFinder();
  const P = (name, salary, dynastyValue) => ({ name, fgId: name, salary, _d: dynastyValue });
  const roster = [P('star', 68, 71), P('bargain', 16, 250), P('pricey', 57, 43), P('mid', 44, 34), P('cheap', 5, 20), P('dead', 10, 0)];
  const dm = {}; roster.forEach(p => { dm[p.fgId] = { dynastyValue: p._d }; });
  const plan = e.call('tfCapPlan', roster, dm, 150);
  assert.strictEqual(plan.payroll, 200);
  // order by value/$: bargain 15.6, cheap 4, star 1.04, mid 0.77, pricey 0.75 -> keep bargain, cheap, star (89); mid fits (133)
  assert.deepStrictEqual(Object.keys(plan.cut).sort(), ['dead', 'pricey']);
  assert.strictEqual(plan.keptPay, 133);
  assert.strictEqual(plan.room, 17);
});

test('salary dumps are offseason-only', () => {
  const e = withFinder();
  e.setDate('2026-06-15');
  const ctx = { offseason: false, rostersByTeam: { a: [], b: [] }, valueMap: {}, dynastyMap: {} };
  assert.strictEqual(e.call('tfDumpCandidates', ctx, 'a', 'b', 'contender', 'fringe').length, 0);
});
