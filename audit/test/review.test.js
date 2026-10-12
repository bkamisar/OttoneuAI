const test = require('node:test');
const assert = require('node:assert');
const { buildCards } = require('../lib/review');

const mv = (o) => ({ season: 2026, kind: 'add', in: [], out: [], tags: [], process: null, ptsContributed: 0, titleDeciding: null, ...o });
const audit = {
  myTeamId: '1', teams: { 1: { name: 'Me' }, 2: { name: 'You' } },
  moves: [
    mv({ id: 'a', teamId: '1', kind: 'trade', tradeId: 't1', counterTeamId: '2', result: 30, in: [{ player: 'Trout', salary: 22 }], out: [{ player: 'X', salary: 5 }] }),
    mv({ id: 'b', teamId: '2', kind: 'trade', tradeId: 't1', counterTeamId: '1', result: -30, in: [{ player: 'X', salary: 5 }], out: [{ player: 'Trout', salary: 22 }] }),
    mv({ id: 'c', teamId: '2', result: 25, in: [{ player: 'Gem', salary: 1 }] }),
    mv({ id: 'd', teamId: '1', kind: 'cut', result: -18, out: [{ player: 'Ghost', salary: 1 }] }),
    mv({ id: 'e', teamId: '1', result: 2, process: -5, titleDeciding: 'won-title', ptsContributed: 4, in: [{ player: 'Clutch', salary: 1 }] }),
  ],
};

test('cards pick the right moves', () => {
  const c = Object.fromEntries(buildCards(audit, 2026).map(x => [x.id, x]));
  assert.strictEqual(c['trade-of-year'].numbers.margin, 60);
  assert.strictEqual(c['pickup-of-year'].players[0], 'Gem');
  assert.strictEqual(c['cut-that-haunts'].players[0], 'Ghost');
  assert.strictEqual(c['title-1'].players[0], 'Clutch');
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

test('title cards: one per trade, only moves that decided a place; winter card from winters', () => {
  const both = { ...audit, winters: { 2026: { 1: { freed: 30, resetSavings: 1, tradeSalary: 0, auctionSpend: 60, auctionReturn: 25 }, 2: { freed: 10, resetSavings: 0, tradeSalary: 0, auctionSpend: 40, auctionReturn: -5 } } },
    moves: audit.moves.concat([
      mv({ id: 'w', teamId: '1', kind: 'trade', tradeId: 't9', counterTeamId: '2', result: 5, titleDeciding: 'won-title', ptsContributed: 6, in: [{ player: 'Raleigh', salary: 20 }] }),
      mv({ id: 'l', teamId: '2', kind: 'trade', tradeId: 't9', counterTeamId: '1', result: -5, titleDeciding: null, ptsContributed: -6, in: [{ player: 'Ward', salary: 10 }] }),
      mv({ id: 'r', teamId: '2', kind: 'reset', result: 1, out: [{ player: 'Yordan', salary: 52 }] }),
    ]) };
  const c = buildCards(both, 2026);
  const titles = c.filter(x => x.id.startsWith('title-'));
  assert.ok(titles.some(x => x.players.includes('Raleigh')) && !titles.some(x => x.players.includes('Ward')));
  assert.notStrictEqual(c.find(x => x.id === 'cut-that-haunts').players[0], 'Yordan');
  assert.strictEqual(c.find(x => x.id === 'winter-of-year').teamId, '1');
});

test('all-time trade record splits a team that changed managers', () => {
  const t = { myTeamId: '1', teams: { 10899: { name: 'Prospects R Us' }, 1: { name: 'Me' } }, moves: [
    mv({ id: 'p1', season: 2025, date: '2025-06-01', teamId: '10899', kind: 'trade', tradeId: 'x1', counterTeamId: '1', result: 10, in: [{ player: 'A', salary: 1 }], out: [{ player: 'B', salary: 1 }] }),
    mv({ id: 'p2', season: 2026, date: '2026-06-01', teamId: '10899', kind: 'trade', tradeId: 'x2', counterTeamId: '1', result: -4, in: [{ player: 'C', salary: 1 }], out: [{ player: 'D', salary: 1 }] }),
  ] };
  const rows = buildCards(t, 2026).find(c => c.id === 'all-time-trades').numbers.rows.map(r => r.team);
  assert.ok(rows.includes('Prospects R Us (2024–25)') && rows.includes('Prospects R Us (2026)'));
});

test('season cards count a mid-season manager change as two managers', () => {
  const t = { myTeamId: '1', teams: { 10758: { name: 'Misiorowski Index' }, 1: { name: 'Me' } }, moves: [
    ...[1, 2, 3].map(i => mv({ id: 'o' + i, date: '2026-05-0' + i, teamId: '10758', result: 1, in: [{ player: 'O' + i, salary: 1 }] })),
    ...[1, 2, 3].map(i => mv({ id: 'n' + i, date: '2026-08-2' + i, teamId: '10758', result: 1, in: [{ player: 'N' + i, salary: 1 }] })),
    ...[1, 2, 3, 4].map(i => mv({ id: 'm' + i, date: '2026-06-0' + i, teamId: '1', result: 1, in: [{ player: 'M' + i, salary: 1 }] })),
  ] };
  const c = Object.fromEntries(buildCards(t, 2026).map(x => [x.id, x]));
  assert.strictEqual(c['most-active'].team, 'Me');
  assert.strictEqual(c['most-active'].numbers.moves, 4);
});

test('a partial-season manager is not "most patient"', () => {
  const t = { myTeamId: '1', teams: { 10758: { name: 'Misiorowski Index' }, 1: { name: 'Me' }, 2: { name: 'You' } }, moves: [
    mv({ id: 'n1', date: '2026-08-21', teamId: '10758', result: 1, in: [{ player: 'N', salary: 1 }] }),
    ...[1, 2].map(i => mv({ id: 'y' + i, date: '2026-06-0' + i, teamId: '2', result: 1, in: [{ player: 'Y' + i, salary: 1 }] })),
    ...[1, 2, 3].map(i => mv({ id: 'm' + i, date: '2026-06-0' + i, teamId: '1', result: 1, in: [{ player: 'M' + i, salary: 1 }] })),
  ] };
  assert.strictEqual(buildCards(t, 2026).find(c => c.id === 'most-patient').team, 'You');
});

test('trade cards and the all-time record carry production (before salary) next to the result', () => {
  const t = { myTeamId: '1', teams: { 1: { name: 'Me' }, 2: { name: 'You' } }, moves: [
    mv({ id: 'a', teamId: '1', kind: 'trade', tradeId: 't1', counterTeamId: '2', result: 40, production: 15, in: [{ player: 'Big', salary: 52 }], out: [{ player: 'Y', salary: 1 }] }),
    mv({ id: 'b', teamId: '2', kind: 'trade', tradeId: 't1', counterTeamId: '1', result: -40, production: -15, in: [{ player: 'Y', salary: 1 }], out: [{ player: 'Big', salary: 52 }] }),
  ] };
  const c = Object.fromEntries(buildCards(t, 2026).map(x => [x.id, x]));
  assert.strictEqual(c['trade-of-year'].numbers.winnerProduction, 15);
  assert.strictEqual(c['trade-of-year'].numbers.loserProduction, -15);
  const row = c['all-time-trades'].numbers.rows.find(r => r.team === 'Me');
  assert.strictEqual(row.net, 40); assert.strictEqual(row.prod, 15);
});

test('title cards carry the close-call flag', () => {
  const t = { myTeamId: '1', teams: { 1: { name: 'Me' } }, moves: [
    mv({ id: 'c', teamId: '1', result: 1, titleDeciding: 'cost-podium', ptsContributed: -11, closeCall: true, in: [{ player: 'Jump', salary: 3 }] }),
  ] };
  assert.strictEqual(buildCards(t, 2026).find(c => c.id === 'title-1').numbers.closeCall, true);
});

test('cards rank by grade (production), with after-salary carried as information', () => {
  const t = { myTeamId: '1', teams: { 1: { name: 'Me' }, 2: { name: 'You' }, 3: { name: 'Them' }, 4: { name: 'Us' } }, moves: [
    // salary-dump trade: big after-salary swing, small production swing
    mv({ id: 'a', teamId: '1', kind: 'trade', tradeId: 't1', counterTeamId: '2', result: 60, production: 5, grade: 5, in: [{ player: 'Kid', salary: 1 }], out: [{ player: 'Contract', salary: 50 }] }),
    mv({ id: 'b', teamId: '2', kind: 'trade', tradeId: 't1', counterTeamId: '1', result: -60, production: -5, grade: -5, in: [{ player: 'Contract', salary: 50 }], out: [{ player: 'Kid', salary: 1 }] }),
    // production trade: modest after-salary, big production
    mv({ id: 'c', teamId: '3', kind: 'trade', tradeId: 't2', counterTeamId: '4', result: 10, production: 30, grade: 30, in: [{ player: 'Star', salary: 40 }], out: [{ player: 'Kid2', salary: 2 }] }),
    mv({ id: 'd', teamId: '4', kind: 'trade', tradeId: 't2', counterTeamId: '3', result: -10, production: -30, grade: -30, in: [{ player: 'Kid2', salary: 2 }], out: [{ player: 'Star', salary: 40 }] }),
  ] };
  const c = Object.fromEntries(buildCards(t, 2026).map(x => [x.id, x]));
  assert.strictEqual(c['trade-of-year'].team, 'Them');
  assert.strictEqual(c['trade-of-year'].numbers.winner, 30);
  assert.strictEqual(c['trade-of-year'].numbers.winnerAfterSalary, 10);
  const me = c['all-time-trades'].numbers.rows.find(r => r.team === 'Me');
  assert.strictEqual(me.net, 5); assert.strictEqual(me.afterSalary, 60);
});

test('all-time record: trades graded within $1 of zero are pushes, not wins', () => {
  const t = { myTeamId: '1', teams: { 1: { name: 'Me' }, 2: { name: 'You' } }, moves: [
    mv({ id: 'w', teamId: '1', kind: 'trade', tradeId: 'a', counterTeamId: '2', result: 9, grade: 9, in: [{ player: 'A', salary: 1 }], out: [{ player: 'B', salary: 1 }] }),
    mv({ id: 'z', teamId: '1', kind: 'trade', tradeId: 'b', counterTeamId: '2', result: 0, grade: 0.4, in: [], out: [{ player: 'C', salary: 1 }] }),
    mv({ id: 'l', teamId: '1', kind: 'trade', tradeId: 'c', counterTeamId: '2', result: -3, grade: -3, in: [{ player: 'D', salary: 1 }], out: [{ player: 'E', salary: 1 }] }),
  ] };
  const me = buildCards(t, 2026).find(c => c.id === 'all-time-trades').numbers.rows.find(r => r.team === 'Me');
  assert.deepStrictEqual([me.w, me.l, me.t], [1, 1, 1]);
});
