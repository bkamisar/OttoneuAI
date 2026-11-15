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
  // Offseason: the whole NEXT season lies ahead (was 0, which shrank every budget to 10%).
  e.setDate('2026-10-01'); assert.strictEqual(e.call('rosProrationFactor'), 1);
  e.setDate('2026-11-15'); assert.strictEqual(e.call('rosProrationFactor'), 1);
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

test('offseason: isOffseason(), and loadCurrStandings() ignores the finished season', () => {
  const e = loadEngine();
  for (const [d, off] of [['2026-11-15', true], ['2027-02-01', true], ['2026-06-01', false], ['2026-09-28', false], ['2026-09-29', true]]) {
    e.setDate(d); assert.strictEqual(e.call('isOffseason'), off, d);
  }
  e.localStorage.setItem('ottoneu_curr_standings', JSON.stringify([{ name: 'A', games: 162 }]));
  e.setDate('2026-11-15'); assert.strictEqual(e.call('loadCurrStandings'), null);
  e.setDate('2026-06-01'); assert.deepStrictEqual(e.call('loadCurrStandings'), [{ name: 'A', games: 162 }]);
});
