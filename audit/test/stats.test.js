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
