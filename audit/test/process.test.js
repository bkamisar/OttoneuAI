const test = require('node:test');
const assert = require('node:assert');
const { loadEngine } = require('../lib/engine');
const { makeValuer, moveProcess } = require('../lib/process');

const ROSTER_H = 'TeamID,"Team Name","ottoneu ID","FG MajorLeagueID","FG MinorLeagueID",Name,"MLB Team",Position(s),Salary\n';
const rosterRows = [];
for (let t = 0; t < 12; t++) for (let i = 0; i < 4; i++) {
  rosterRows.push(`${100 + t},"T${t}",${t * 10 + i},${t * 10 + i},,"H${t}_${i}",NYY,OF,$${5 + i}`);
  rosterRows.push(`${100 + t},"T${t}",${500 + t * 10 + i},${500 + t * 10 + i},,"P${t}_${i}",NYY,SP,$${5 + i}`);
}
const roster = ROSTER_H + rosterRows.join('\n');
const hit = 'Name,Team,PA,AB,H,HR,R,BB,HBP,OBP,SLG,fgId\n' +
  rosterRows.filter(r => r.includes('"H')).map((r, k) => { const id = r.split(',')[2]; return `"H${Math.floor(id / 10)}_${id % 10}",NYY,${300 + k},${270 + k},70,${10 + k % 20},${40 + k % 30},25,3,.330,.430,${id}`; }).join('\n') +
  '\n"FA Bat",NYY,400,360,90,25,60,30,3,.360,.520,9999\n"FA Scrub",NYY,200,180,40,3,20,15,1,.290,.350,9998';
const pit = 'Name,Team,GS,G,IP,ER,HR,SO,BB,HR/9,WHIP,ERA,fgId\n' +
  rosterRows.filter(r => r.includes('"P')).map((r, k) => { const id = r.split(',')[2]; return `"P${Math.floor((id - 500) / 10)}_${(id - 500) % 10}",NYY,15,15,${80 + k},35,10,${80 + k},25,1.1,1.2,${3.5 + (k % 10) / 10},${id}`; }).join('\n');

const snap = (date) => [{ sha: 's', date }];
const snapshots = { roster: snap('2026-06-01'), hit: snap('2026-06-01'), pit: snap('2026-06-01'),
  read: (sha, p) => (p.endsWith('roster.csv') ? roster : p.endsWith('hitting.csv') ? hit : pit) };

test('add of a strong FA has positive process; scrub negative-ish', () => {
  const e = loadEngine(); const v = makeValuer(e, snapshots);
  const good = moveProcess(e, v, { kind: 'add', date: '2026-06-10', in: [{ ottoneuId: 'x', player: 'FA Bat', salary: 1 }], out: [] });
  const bad = moveProcess(e, v, { kind: 'add', date: '2026-06-10', in: [{ ottoneuId: 'y', player: 'FA Scrub', salary: 10 }], out: [] });
  assert.ok(good > bad, `${good} vs ${bad}`);
  assert.ok(bad < 0);
});

test('no snapshot strictly before the move -> null; outside window -> null', () => {
  const e = loadEngine(); const v = makeValuer(e, snapshots);
  assert.strictEqual(moveProcess(e, v, { kind: 'add', date: '2026-06-01', in: [{ ottoneuId: 'x', player: 'FA Bat', salary: 1 }], out: [] }), null);
  assert.strictEqual(moveProcess(e, v, { kind: 'add', date: '2025-06-10', in: [], out: [] }), null);
});

const { moveFuture } = require('../lib/process');
// A ranked prospect (#10, FV 60) on a $2 contract with no projections, plus Y1 projection files.
const prospectsCsv = 'Top 100,Name,FV,Risk\n10,Kid Prospect,60,Medium\n';
const roster2 = roster + '\n100,"T0",9001,9001,,"Kid Prospect",NYY,OF,$2';
const snaps2 = { roster: snap('2026-06-01'), hit: snap('2026-06-01'), pit: snap('2026-06-01'),
  hitY1: snap('2026-06-01'), pitY1: snap('2026-06-01'), hitY2: [], pitY2: [], prospects: snap('2026-06-01'),
  read: (sha, p) => (p.endsWith('roster.csv') ? roster2 : p.endsWith('prospects.csv') ? prospectsCsv : p.includes('hitting') ? hit : pit) };

test('future value: a ranked prospect carries dynasty value; nobody is below $0', () => {
  const e = loadEngine(); const v = makeValuer(e, snaps2).valuesAsOf('2026-06-10');
  assert.ok(v.future('9001', 'Kid Prospect') > 25, `prospect future ${v.future('9001', 'Kid Prospect')}`);
  for (const id of ['10', '11', '500', '511']) assert.ok(v.future(id, '') >= 0, id);
});

test('moveFuture: trading a veteran for a top prospect gains future value; outside the window -> null', () => {
  const e = loadEngine(); const v = makeValuer(e, snaps2);
  const move = { kind: 'trade', date: '2026-06-10', teamId: '101', counterTeamId: '100',
    in: [{ ottoneuId: '9001', player: 'Kid Prospect', salary: 2 }], out: [{ ottoneuId: '10', player: 'H1_0', salary: 5 }] };
  assert.ok(moveFuture(e, v, move) > 20);
  assert.strictEqual(moveFuture(e, v, { ...move, date: '2026-04-01' }), null);
});
