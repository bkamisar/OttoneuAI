const test = require('node:test');
const assert = require('node:assert');
const { loadEngine } = require('../lib/engine');
const { seasonContext, lineValue, fracOfSeason, moveResult } = require('../lib/result');

const e = loadEngine();
const team = (x) => ({ teamId: 't' + x, ip: 1400, stats: { OBP: .32 + x / 1000, SLG: .42 + x / 500, HR: 200 + x * 5, R: 800 + x * 10, ERA: 4 - x / 20, WHIP: 1.25 - x / 200, HR9: 1.2 - x / 100, SO: 1300 + x * 10 } });
const H = (pa, hr, r, obp, slg) => ({ type: 'H', line: { pa, hr, r, obp, slg } });
const P = (ip, so, era, whip, hr9) => ({ type: 'P', line: { ip, so, era, whip, hr9 } });
const ctx = seasonContext(e, {
  finalTeams: Array.from({ length: 12 }, (_, i) => team(i)),
  stintLines: [H(600, 35, 100, .37, .55), H(550, 20, 80, .33, .44), P(180, 200, 3.2, 1.1, 1.0), P(60, 70, 3.0, 1.1, .9)],
  freeAgentLines: [H(300, 8, 35, .30, .38), H(250, 6, 30, .30, .37), P(80, 70, 4.4, 1.3, 1.3), P(50, 45, 4.5, 1.35, 1.4)],
});

test('context: positive rate, replacement from free agents', () => {
  assert.ok(ctx.rate > 0);
  assert.ok(ctx.repl.H.obp < .32);
});

test('a star line is worth more than a scrub line; null is 0; scrub can be negative', () => {
  const star = lineValue(e, ctx, 'H', H(600, 35, 100, .37, .55).line);
  const scrub = lineValue(e, ctx, 'H', H(200, 2, 15, .26, .30).line);
  assert.ok(star > 10 && star > scrub);
  assert.ok(scrub < 0);
  assert.strictEqual(lineValue(e, ctx, 'H', null), 0);
});

test('zero-PA line is finite', () => {
  assert.ok(Number.isFinite(lineValue(e, ctx, 'H', { pa: 0, hr: 0, r: 0, obp: 0, slg: 0 })));
});

test('fracOfSeason', () => {
  assert.strictEqual(fracOfSeason(2026, '2026-01-01', null), 1);
  const half = fracOfSeason(2026, '2026-06-27', null);
  assert.ok(half > .45 && half < .55);
  assert.strictEqual(fracOfSeason(2026, '2026-10-01', null), 0);
});

test('cut result: freed salary minus what the player did afterward', () => {
  const move = { kind: 'cut', season: 2026, date: '2026-06-27', in: [], out: [{ ottoneuId: 'x', salary: 20 }] };
  const look = () => ({ type: 'H', line: { pa: 0, hr: 0, r: 0, obp: 0, slg: 0 } });
  const r = moveResult(e, ctx, move, look);
  assert.ok(r > 0 && r < 20);
});

const { countedResult } = require('../lib/result');
const look = map => (id, team) => map[id + '|' + team] || { type: null, line: null };
const hitL = (pa, hr, r, obp, slg) => ({ type: 'H', line: { pa, hr, r, obp, slg } });
const opts = (map, teams = {}, stints = {}) => ({
  counted: look(map), teamsWith: (id) => teams[id] || [], tenureEnd: () => null, stintCount: (id, t) => stints[id + '|' + t] || 1,
});

test('trade: received player counted almost nothing -> that side loses', () => {
  const move = { kind: 'trade', season: 2026, date: '2026-05-13', teamId: 'BUR', counterTeamId: 'ME', phase: 'in-season',
    in: [{ ottoneuId: 'don', salary: 7 }], out: [{ ottoneuId: 'lugo', salary: 3 }] };
  const map = { 'don|BUR': hitL(17, 0, 2, .333, .533), 'lugo|ME': { type: 'P', line: { ip: 90, so: 85, era: 3.4, whip: 1.15, hr9: 1.0 } } };
  const r = countedResult(e, ctx, move, opts(map));
  assert.ok(r.result < 0, `Bureau side ${r.result}`);
});

test('traded-away player with no production row counts zero; trade still grades', () => {
  const move = { kind: 'trade', season: 2026, date: '2026-07-01', teamId: 'A', counterTeamId: 'B', phase: 'in-season',
    in: [{ ottoneuId: 'star', salary: 10 }], out: [{ ottoneuId: 'prospect', salary: 1 }] };
  const r = countedResult(e, ctx, move, opts({ 'star|A': hitL(250, 15, 40, .36, .52) }));
  assert.ok(Number.isFinite(r.result) && r.result > 0);
});

test('offseason cut frees full salary; production only from later teams', () => {
  const move = { kind: 'cut', season: 2026, date: '2025-11-15', teamId: 'A', phase: 'offseason', in: [], out: [{ ottoneuId: 'q', salary: 20 }] };
  const r = countedResult(e, ctx, move, opts({}, { q: [] }));
  assert.ok(Math.abs(r.result - 20) < 1e-9);
});

test('reset returns its salary grade', () => {
  const r = countedResult(e, ctx, { kind: 'reset', resetGrade: 1, season: 2026, date: '2026-01-31', in: [], out: [] }, opts({}));
  assert.strictEqual(r.result, 1);
});

test('player with two stints on the same team in a season is flagged combinedStints', () => {
  const move = { kind: 'add', season: 2026, date: '2026-07-01', teamId: 'A', phase: 'in-season', in: [{ ottoneuId: 'x', salary: 1 }], out: [] };
  const r = countedResult(e, ctx, move, opts({ 'x|A': hitL(100, 3, 12, .31, .40) }, {}, { 'x|A': 2 }));
  assert.strictEqual(r.combinedStints, true);
});

test('short-stint pitcher is not docked strikeouts as if full-time; full-time pitchers unchanged', () => {
  const direct = line => e.call('calcPlayerSGP', { type: 'P' }, line, ctx.repl.P, ctx.sgpDenom, ctx.avgPA, ctx.avgIP) * ctx.rate;
  const reliever = { ip: 20, so: 25, era: 3.0, whip: 1.1, hr9: 0.9 };    // good K rate, few innings
  assert.ok(direct(reliever) < 0, 'precondition: the old formula docks this reliever below zero');
  assert.ok(lineValue(e, ctx, 'P', reliever) > 0, 'prorated strikeouts: a good short stint is worth something');
  const starter = { ip: 180, so: 200, era: 3.2, whip: 1.1, hr9: 1.0 };
  assert.ok(Math.abs(lineValue(e, ctx, 'P', starter) - direct(starter)) < 1e-9);
  const tiny = { ip: 3.3, so: 3, era: 10.8, whip: 2.1, hr9: 0 };            // Rico Garcia: three innings
  // The only change is the strikeout term: the replacement's K is cut to the innings actually thrown.
  const expectedGain = ctx.repl.P.so * (1 - tiny.ip / ctx.repl.P.ip) / ctx.sgpDenom.SO * ctx.rate;
  assert.ok(Math.abs((lineValue(e, ctx, 'P', tiny) - direct(tiny)) - expectedGain) < 1e-9);
});

test('countedResult also reports production alone; result - production is the salary effect', () => {
  const move = { kind: 'trade', season: 2026, date: '2026-06-23', teamId: 'BUR', counterTeamId: 'ME', phase: 'in-season',
    in: [{ ottoneuId: 'don', salary: 7 }], out: [{ ottoneuId: 'lugo', salary: 3 }] };
  const map = { 'don|BUR': hitL(250, 12, 40, .35, .50), 'lugo|ME': { type: 'P', line: { ip: 90, so: 85, era: 3.4, whip: 1.15, hr9: 1.0 } } };
  const r = countedResult(e, ctx, move, opts(map));
  const frac = fracOfSeason(2026, '2026-06-23', null);
  assert.ok(Math.abs(r.production - (lineValue(e, ctx, 'H', map['don|BUR'].line) - lineValue(e, ctx, 'P', map['lugo|ME'].line))) < 1e-9);
  assert.ok(Math.abs((r.result - r.production) - (-7 * frac + 3 * frac)) < 1e-9);
});

test('production is 0 for a reset and for an offseason cut nobody picked up', () => {
  assert.strictEqual(countedResult(e, ctx, { kind: 'reset', resetGrade: 1, season: 2026, date: '2026-01-31', in: [], out: [] }, opts({})).production, 0);
  const cut = { kind: 'cut', season: 2026, date: '2025-11-15', teamId: 'A', phase: 'offseason', in: [], out: [{ ottoneuId: 'q', salary: 20 }] };
  const r = countedResult(e, ctx, cut, opts({}, { q: [] }));
  assert.strictEqual(r.production, 0); assert.ok(Math.abs(r.result - 20) < 1e-9);
});
