const test = require('node:test');
const assert = require('node:assert');
const { buildCards } = require('../lib/review');

const mv = (o) => ({ season: 2026, kind: 'add', in: [], out: [], tags: [], process: null, standings: { dPts: 0, dRank: 0 }, decisive: false, fragile: null, ...o });
const audit = {
  myTeamId: '1', teams: { 1: { name: 'Me' }, 2: { name: 'You' } },
  moves: [
    mv({ id: 'a', teamId: '1', kind: 'trade', tradeId: 't1', counterTeamId: '2', result: 30, in: [{ player: 'Trout', salary: 22 }], out: [{ player: 'X', salary: 5 }] }),
    mv({ id: 'b', teamId: '2', kind: 'trade', tradeId: 't1', counterTeamId: '1', result: -30, in: [{ player: 'X', salary: 5 }], out: [{ player: 'Trout', salary: 22 }] }),
    mv({ id: 'c', teamId: '2', result: 25, in: [{ player: 'Gem', salary: 1 }] }),
    mv({ id: 'd', teamId: '1', kind: 'cut', result: -18, out: [{ player: 'Ghost', salary: 1 }] }),
    mv({ id: 'e', teamId: '1', result: 2, process: -5, decisive: true, fragile: false, standings: { dPts: 4, dRank: 1 }, in: [{ player: 'Clutch', salary: 1 }] }),
  ],
};

test('cards pick the right moves', () => {
  const c = Object.fromEntries(buildCards(audit, 2026).map(x => [x.id, x]));
  assert.strictEqual(c['trade-of-year'].numbers.margin, 60);
  assert.strictEqual(c['pickup-of-year'].players[0], 'Gem');
  assert.strictEqual(c['cut-that-haunts'].players[0], 'Ghost');
  assert.strictEqual(c['decisive'].players[0], 'Clutch');
  assert.strictEqual(c['most-active'].teamId, '1');
});

test('no qualifying move -> card omitted, not empty', () => {
  const ids = buildCards({ ...audit, moves: audit.moves.filter(m => m.kind !== 'trade') }, 2026).map(x => x.id);
  assert.ok(!ids.includes('trade-of-year'));
});

test('trade cards show what the winner sent as well as received', () => {
  const c = Object.fromEntries(buildCards(audit, 2026).map(x => [x.id, x]));
  assert.deepStrictEqual(c['trade-of-year'].sent, ['X']);
});

test('decisive cards: only teams whose own finish changed, one card per trade', () => {
  const both = { ...audit, moves: audit.moves.concat([
    mv({ id: 'w', teamId: '1', kind: 'trade', tradeId: 't9', counterTeamId: '2', result: 5, decisive: true, standings: { dPts: 6, dRank: 1 }, in: [{ player: 'Raleigh', salary: 20 }] }),
    mv({ id: 'l', teamId: '2', kind: 'trade', tradeId: 't9', counterTeamId: '1', result: -5, decisive: true, standings: { dPts: -7, dRank: 0 }, in: [{ player: 'Ward', salary: 10 }] }),
  ]) };
  const dec = buildCards(both, 2026).filter(c => c.id.startsWith('decisive'));
  assert.ok(dec.some(c => c.players.includes('Raleigh')));
  assert.ok(!dec.some(c => c.players.includes('Ward')));
});
