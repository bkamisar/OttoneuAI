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
