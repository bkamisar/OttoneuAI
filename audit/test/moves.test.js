const test = require('node:test');
const assert = require('node:assert');
const { parseTransactions, buildMoves, seasonOf } = require('../lib/moves');

const H = 'date,type,player,ottoneuId,teamId,team,fromTeamId,fromTeam,salary\n';
const row = (ts, type, player, id, team, from = '', sal = 1) =>
  `${ts},${type},${player},${id},${team},T${team},${from},${from ? 'T' + from : ''},${sal}\n`;

test('parses and sorts oldest first', () => {
  const t = parseTransactions(H + row('2026-08-15T14:26:01', 'add', 'B', 2, 1) + row('2024-03-14T19:03:07', 'add', 'A', 1, 1, '', 35));
  assert.deepStrictEqual(t.map(x => x.player), ['A', 'B']);
  assert.strictEqual(t[0].salary, 35);
  assert.strictEqual(t[0].date, '2024-03-14');
});

test('commissioner adds ("add   (C)") parse as adds, flagged', () => {
  const t = parseTransactions(H + row('2024-05-18T12:13:02', 'add                 (C)', 'Ryne Nelson', 37826, 10897));
  assert.strictEqual(t[0].type, 'add');
  assert.strictEqual(t[0].commissioner, true);
});

test('seasonOf maps offseason to the right season', () => {
  assert.strictEqual(seasonOf('2026-06-01'), 2026);
  assert.strictEqual(seasonOf('2026-10-15'), 2027);
  assert.strictEqual(seasonOf('2027-01-20'), 2027);
});

test('trade rows sharing a timestamp group into one trade, two sides', () => {
  const csv = H +
    row('2026-08-15T14:26:01', 'move', 'Trout', 10, 10759, 20, 22) +
    row('2026-08-15T14:26:01', 'move', 'Schwellenbach', 11, 20, 10759, 5) +
    row('2026-08-15T14:26:01', 'move', 'Vaughn', 12, 10759, 20, 3);
  const m = buildMoves(parseTransactions(csv));
  assert.strictEqual(m.length, 2);
  const mine = m.find(x => x.teamId === '10759');
  assert.strictEqual(mine.kind, 'trade');
  assert.deepStrictEqual(mine.in.map(p => p.player).sort(), ['Trout', 'Vaughn']);
  assert.deepStrictEqual(mine.out.map(p => p.player), ['Schwellenbach']);
  assert.strictEqual(mine.counterTeamId, '20');
  assert.strictEqual(mine.tradeId, m.find(x => x.teamId === '20').tradeId);
});

test('missing fromTeamId is filled from the from-team name (Ottoneu gives no link there)', () => {
  const csv = H +
    '2026-08-30T09:06:01,move,Pallante,1,10899,Prospects R Us,,Bryce K,1\n' +
    '2026-08-30T09:06:01,move,Peters,2,10925,Bryce K,,Prospects R Us,3\n';
  const t = parseTransactions(csv);
  assert.deepStrictEqual(t.map(x => x.fromTeamId).sort(), ['10899', '10925']);
  const m = buildMoves(t);
  assert.strictEqual(m.length, 2);
  assert.ok(m.every(x => x.in.length === 1 && x.out.length === 1));
});

test('one trade split across timestamps a second apart is still one trade', () => {
  const csv = H +
    row('2025-06-18T11:03:01', 'move', 'Perdomo', 1, 10759, 10818) +
    row('2025-06-18T11:03:02', 'move', 'Harris', 2, 10759, 10818, 37) +
    row('2025-06-18T11:03:01', 'move', 'Riley', 3, 10818, 10759, 30);
  const m = buildMoves(parseTransactions(csv));
  assert.strictEqual(m.length, 2);
  assert.deepStrictEqual(m.find(x => x.teamId === '10759').in.map(p => p.player).sort(), ['Harris', 'Perdomo']);
});

test('two trades between the same pair 2 minutes apart stay separate', () => {
  const csv = H + row('2025-06-18T11:00:00', 'move', 'A', 1, 1, 2) + row('2025-06-18T11:02:00', 'move', 'B', 2, 1, 2);
  assert.strictEqual(new Set(buildMoves(parseTransactions(csv)).map(x => x.tradeId)).size, 2);
});

test('two trades between different pairs in the same second stay separate', () => {
  const csv = H +
    row('2026-08-01T12:00:00', 'move', 'A', 1, 1, 2) + row('2026-08-01T12:00:00', 'move', 'B', 2, 2, 1) +
    row('2026-08-01T12:00:00', 'move', 'C', 3, 3, 4) + row('2026-08-01T12:00:00', 'move', 'D', 4, 4, 3);
  const m = buildMoves(parseTransactions(csv));
  assert.strictEqual(new Set(m.map(x => x.tradeId)).size, 2);
});

test('add + cut by one team within 30 min pair into a swap', () => {
  const csv = H + row('2026-09-27T13:47:40', 'cut', 'Cortes', 5, 10759) + row('2026-09-27T14:10:00', 'add', 'Gonzalez', 6, 10759, '', 3);
  const m = buildMoves(parseTransactions(csv));
  assert.strictEqual(m.length, 1);
  assert.strictEqual(m[0].kind, 'swap');
  assert.deepStrictEqual([m[0].in[0].player, m[0].out[0].player], ['Gonzalez', 'Cortes']);
});

test('add and cut 31 min apart stay separate; other team never pairs', () => {
  const csv = H + row('2026-09-27T13:00:00', 'cut', 'X', 5, 1) + row('2026-09-27T13:31:00', 'add', 'Y', 6, 1) + row('2026-09-27T13:05:00', 'add', 'Z', 7, 2);
  const kinds = buildMoves(parseTransactions(csv)).map(x => x.kind).sort();
  assert.deepStrictEqual(kinds, ['add', 'add', 'cut']);
});

test('March adds before Opening Day are auction buys; increases make no move', () => {
  const csv = H + row('2025-03-10T19:00:00', 'add', 'Ohtani', 1, 1, '', 44) + row('2025-10-06T00:00:00', 'increase', 'Ohtani', 1, 1, '', 46);
  const m = buildMoves(parseTransactions(csv));
  assert.deepStrictEqual(m.map(x => x.kind), ['auction']);
});

test('offseason cut rows ($0 on Ottoneu) take the salary the player last carried', () => {
  const csv = H +
    row('2025-03-14T19:00:00', 'add', 'Yordan', 1, 10925, '', 40) +
    row('2025-10-06T00:00:00', 'increase', 'Yordan', 1, 10925, '', 42) +
    row('2026-01-31T12:00:00', 'cut', 'Yordan', 1, 10925, '', 0);
  const cut = parseTransactions(csv).find(t => t.type === 'cut');
  assert.strictEqual(cut.salary, 42);
});
