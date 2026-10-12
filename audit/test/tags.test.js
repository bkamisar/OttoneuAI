const test = require('node:test');
const assert = require('node:assert');
const { tagMove } = require('../lib/tags');

const env = {
  hotPctl: id => (id === 'hot' ? 0.9 : 0.3), isProspect: id => id === 'kid',
  weakestCatGroup: () => 'H', typeOf: id => (id === 'arm' ? 'P' : 'H'), rankAt: t => (t === 'top' ? 2 : 11),
};

test('add tags: hot, need, contender', () => {
  const t = tagMove({ kind: 'add', date: '2026-06-01', teamId: 'top', in: [{ ottoneuId: 'hot', salary: 1 }], out: [] }, env);
  assert.deepStrictEqual(t.sort(), ['contender', 'hot', 'need']);
});

test('prospect stash on a rebuilder; pitcher add misses a hitting need', () => {
  assert.deepStrictEqual(tagMove({ kind: 'add', date: '2026-06-01', teamId: 'bot', in: [{ ottoneuId: 'kid', salary: 1 }], out: [] }, env).sort(), ['need', 'prospect', 'rebuilder']);
  assert.ok(!tagMove({ kind: 'add', date: '2026-06-01', teamId: 'mid', in: [{ ottoneuId: 'arm', salary: 1 }], out: [] }, { ...env, rankAt: () => 6 }).includes('need'));
});

test('trade tags: deadline, salary-dump, consolidation', () => {
  const t = tagMove({ kind: 'trade', date: '2026-08-15', teamId: 'mid', in: [{ ottoneuId: 'a', salary: 22 }], out: [{ ottoneuId: 'b', salary: 5 }, { ottoneuId: 'c', salary: 3 }] }, { ...env, rankAt: () => 6 });
  assert.ok(t.includes('deadline') && t.includes('consolidation') && !t.includes('salary-dump'));
  const dump = tagMove({ kind: 'trade', date: '2026-07-01', teamId: 'mid', in: [{ ottoneuId: 'a', salary: 2 }], out: [{ ottoneuId: 'b', salary: 20 }] }, { ...env, rankAt: () => 6 });
  assert.ok(dump.includes('salary-dump'));
});
