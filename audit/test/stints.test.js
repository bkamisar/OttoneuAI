const test = require('node:test');
const assert = require('node:assert');
const { replayRosters, diffAgainstSnapshot } = require('../lib/stints');
const { latestOnOrBefore } = require('../lib/gitdata');

const tx = (ts, type, id, teamId, fromTeamId = '', salary = 1) =>
  ({ ts, date: ts.slice(0, 10), type, player: 'P' + id, ottoneuId: String(id), teamId: String(teamId), fromTeamId: String(fromTeamId), salary });

test('add -> trade -> cut produces two stints', () => {
  const { stints } = replayRosters([
    tx('2026-04-01T10:00:00', 'add', 1, 'A', '', 5),
    tx('2026-06-01T10:00:00', 'move', 1, 'B', 'A', 5),
    tx('2026-07-01T10:00:00', 'cut', 1, 'B', '', 5),
  ]);
  assert.deepStrictEqual(stints.map(s => [s.teamId, s.start, s.end]), [['A', '2026-04-01', '2026-06-01'], ['B', '2026-06-01', '2026-07-01']]);
});

test('increase splits a stint at the new salary', () => {
  const { stints } = replayRosters([tx('2025-03-14T10:00:00', 'add', 1, 'A', '', 10), tx('2025-10-06T00:00:00', 'increase', 1, 'A', '', 12)]);
  assert.deepStrictEqual(stints.map(s => [s.salary, s.end]), [[10, '2025-10-06'], [12, null]]);
});

test('rosterAt reflects state at a timestamp', () => {
  const r = replayRosters([tx('2026-04-01T10:00:00', 'add', 1, 'A'), tx('2026-05-01T10:00:00', 'cut', 1, 'A')]);
  assert.strictEqual(r.rosterAt('2026-04-15T00:00:00').get('1').teamId, 'A');
  assert.strictEqual(r.rosterAt('2026-05-02T00:00:00').has('1'), false);
});

test('diffAgainstSnapshot finds missing, extra, wrong team', () => {
  const m = new Map([['1', { teamId: 'A' }], ['2', { teamId: 'B' }]]);
  const d = diffAgainstSnapshot(m, [{ ottoneuId: '1', teamId: 'A' }, { ottoneuId: '2', teamId: 'C' }, { ottoneuId: '3', teamId: 'A' }]);
  assert.deepStrictEqual([d.missing, d.extra, d.wrongTeam.map(x => x.ottoneuId)], [['3'], [], ['2']]);
});

test('latestOnOrBefore never looks forward', () => {
  const h = [{ sha: 'a', date: '2026-06-01' }, { sha: 'b', date: '2026-06-03' }];
  assert.strictEqual(latestOnOrBefore(h, '2026-06-02').sha, 'a');
  assert.strictEqual(latestOnOrBefore(h, '2026-05-31'), null);
});
