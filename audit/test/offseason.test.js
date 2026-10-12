const test = require('node:test');
const assert = require('node:assert');
const { auctionDays, annotateOffseason } = require('../lib/offseason');

const mv = (o) => ({ id: o.id, kind: o.kind, season: o.season, date: o.date, teamId: o.teamId || 'B', counterTeamId: null, tradeId: null, in: o.in || [], out: o.out || [] });
const moves = [
  mv({ id: 'c1', kind: 'cut', season: 2026, date: '2026-01-31', out: [{ ottoneuId: 'y', player: 'Yordan', salary: 52 }] }),
  mv({ id: 'a1', kind: 'auction', season: 2026, date: '2026-03-05', in: [{ ottoneuId: 'y', player: 'Yordan', salary: 51 }] }),
  mv({ id: 'a2', kind: 'auction', season: 2026, date: '2026-03-05', teamId: 'C', in: [{ ottoneuId: 'z', player: 'Zed', salary: 10 }] }),
  mv({ id: 'c2', kind: 'cut', season: 2026, date: '2025-11-15', out: [{ ottoneuId: 'q', player: 'Q', salary: 20 }] }),
  mv({ id: 'c3', kind: 'cut', season: 2026, date: '2026-06-01', out: [{ ottoneuId: 'r', player: 'R', salary: 4 }] }),
  mv({ id: 'c4', kind: 'cut', season: 2026, date: '2025-12-01', teamId: 'D', out: [{ ottoneuId: 'w', player: 'W', salary: 5 }] }),
  mv({ id: 'a4', kind: 'auction', season: 2026, date: '2026-03-05', teamId: 'D', in: [{ ottoneuId: 'w', player: 'W', salary: 9 }] }),
  { ...mv({ id: 't1', kind: 'trade', season: 2026, date: '2025-12-18', out: [{ ottoneuId: 'p', salary: 30 }], in: [{ ottoneuId: 'k', salary: 12 }] }), tradeId: 't', counterTeamId: 'C' },
];

test('auction day per season', () => { assert.deepStrictEqual(auctionDays(moves), { 2026: '2026-03-05' }); });

test('cut + same-team auction rebuy -> one reset move graded old - new', () => {
  const out = annotateOffseason(moves);
  const r = out.find(m => m.kind === 'reset' && m.teamId === 'B');
  assert.strictEqual(r.resetGrade, 1); assert.strictEqual(r.phase, 'offseason');
  assert.ok(!out.some(m => m.id === 'a1'));
});

test('reset that cost more is negative, not dropped', () => {
  const r = annotateOffseason(moves).find(m => m.kind === 'reset' && m.teamId === 'D');
  assert.strictEqual(r.resetGrade, -4);
});

test('phases and cap delta', () => {
  const out = annotateOffseason(moves);
  const ph = id => out.find(m => m.id === id).phase;
  assert.strictEqual(ph('c2'), 'offseason'); assert.strictEqual(ph('c3'), 'in-season'); assert.strictEqual(ph('a2'), 'offseason');
  assert.strictEqual(out.find(m => m.id === 't1').capDelta, 18);
});
