const test = require('node:test');
const assert = require('node:assert');
const { buildIdentity } = require('../lib/identity');

const days = [{
  h: [[1, 'Will Smith', 500, 0, 0, 0, 0, 0, 0, 0, 0], [3, 'José Ramírez', 600, 0, 0, 0, 0, 0, 0, 0, 0]],
  p: [[2, 'Will Smith', 180, 0, 0, 0, 0, 0, 60, 0]],
}];

test('unique names match regardless of accents', () => {
  const r = buildIdentity(days, [{ ottoneuId: 'a', player: 'Jose Ramirez' }]);
  assert.deepStrictEqual(r.map.get('a'), { mlbId: 3, group: 'h' });
});

test('same name in both groups: hint wins, and the case is reported', () => {
  const r = buildIdentity(days, [{ ottoneuId: 'p', player: 'Will Smith', hint: 'P' }, { ottoneuId: 'h', player: 'Will Smith', hint: 'H' }]);
  assert.strictEqual(r.map.get('p').mlbId, 2);
  assert.strictEqual(r.map.get('h').mlbId, 1);
  assert.strictEqual(r.ambiguous.length, 2);
});

test('no MLB stats -> unmatched (a legit zero line for prospects), never a crash', () => {
  const r = buildIdentity(days, [{ ottoneuId: 'z', player: 'Unknown Prospect' }]);
  assert.strictEqual(r.map.has('z'), false);
  assert.deepStrictEqual(r.unmatched.map(u => u.ottoneuId), ['z']);
});

test('fallback ignores middle initials and Jr/II/III suffixes', () => {
  const d = [{ h: [[5, 'Jose F Miranda', 300, 0, 0, 0, 0, 0, 0, 0, 0], [6, 'James Tibbs', 50, 0, 0, 0, 0, 0, 0, 0, 0]], p: [] }];
  const r = buildIdentity(d, [{ ottoneuId: 'm', player: 'Jose Miranda' }, { ottoneuId: 't', player: 'James Tibbs III' }]);
  assert.strictEqual(r.map.get('m').mlbId, 5);
  assert.strictEqual(r.map.get('t').mlbId, 6);
});
