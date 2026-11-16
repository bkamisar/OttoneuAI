const test = require('node:test');
const assert = require('node:assert');
const { loadEngine } = require('../lib/engine');

test('engine exposes shared.js constants and functions', () => {
  const e = loadEngine();
  assert.strictEqual(e.get('IP_MAX'), 1500);
  assert.strictEqual(e.call('normalizeName', 'José Ramírez'), 'jose ramirez');
});

test('setDate drives rosProrationFactor', () => {
  const e = loadEngine();
  e.setDate('2026-03-01'); assert.strictEqual(e.call('rosProrationFactor'), 1);
  // Offseason: the whole NEXT season lies ahead (was 0, which shrank every budget to 10%).
  e.setDate('2026-10-01'); assert.strictEqual(e.call('rosProrationFactor'), 1);
  e.setDate('2026-11-15'); assert.strictEqual(e.call('rosProrationFactor'), 1);
  e.setDate('2026-06-27');
  const f = e.call('rosProrationFactor');
  assert.ok(f > 0.45 && f < 0.55, `mid-season factor ${f}`);
});

test('hotboard.js is loaded too', () => {
  const e = loadEngine();
  assert.strictEqual(e.call('hotClassifyRole', 10, 10), 'SP');
});

test('buildStandings ranks a toy league', () => {
  const e = loadEngine();
  const mk = (name, x) => ({ name, stats: { OBP: x, SLG: x, HR: x, R: x, ERA: 5 - x, WHIP: 5 - x, HR9: 5 - x, SO: x } });
  const s = e.call('buildStandings', [mk('a', 1), mk('b', 3), mk('c', 2)]);
  assert.deepStrictEqual(s.map(t => t.name), ['b', 'c', 'a']);
});

test('offseason: isOffseason(), and loadCurrStandings() ignores the finished season', () => {
  const e = loadEngine();
  for (const [d, off] of [['2026-11-15', true], ['2027-02-01', true], ['2026-06-01', false], ['2026-09-28', false], ['2026-09-29', true]]) {
    e.setDate(d); assert.strictEqual(e.call('isOffseason'), off, d);
  }
  e.localStorage.setItem('ottoneu_curr_standings', JSON.stringify([{ name: 'A', games: 162 }]));
  e.setDate('2026-11-15'); assert.strictEqual(e.call('loadCurrStandings'), null);
  e.setDate('2026-06-01'); assert.deepStrictEqual(e.call('loadCurrStandings'), [{ name: 'A', games: 162 }]);
});

test('projection fills replace Steamer placeholders only while the placeholder remains', () => {
  const e = loadEngine();
  const ph = e.call('parseHittingProjections', 'Name,Team,PA,AB,H,HR,R,BB,HBP,OBP,SLG\nJose Ramirez,CLE,1,1,0,0,0,0,0,0,0\nSteady Bat,NYY,600,540,150,25,90,55,5,.340,.480');
  const fill = e.call('parseHittingProjections', 'Name,Team,PA,AB,H,HR,R,BB,HBP,OBP,SLG\nJose Ramirez,CLE,600,531,141,23,81,59,4,.340,.461');
  const out = e.call('applyProjectionFills', ph, fill, 'H');
  assert.strictEqual(out.find(p => p.rawName === 'Jose Ramirez').proj.pa, 600);
  assert.strictEqual(out.find(p => p.rawName === 'Jose Ramirez').filled, true);
  assert.strictEqual(out.find(p => p.rawName === 'Steady Bat').proj.pa, 600);
  // Steamer later projects him properly -> its line wins
  const real = e.call('parseHittingProjections', 'Name,Team,PA,AB,H,HR,R,BB,HBP,OBP,SLG\nJose Ramirez,CLE,620,560,150,28,90,55,5,.345,.480');
  assert.strictEqual(e.call('applyProjectionFills', real, fill, 'H')[0].proj.pa, 620);
});

test('projFlagFor finds a flag by name; label says what to check', () => {
  const e = loadEngine();
  e.localStorage.setItem('ottoneu_proj_flags', JSON.stringify([
    { Name: 'Jacob Misiorowski', Type: 'P', Kind: 'workload', Unit: 'IP', Steamer: '183', Zips: '116' },
    { Name: 'José Ramírez', Type: 'H', Kind: 'zips-fill', Unit: 'PA', Steamer: '1', Zips: '600' }]));
  const m = e.call('projFlagFor', { name: 'jacob misiorowski', rawName: 'Jacob Misiorowski' });
  assert.strictEqual(m.Kind, 'workload');
  assert.strictEqual(e.call('projFlagFor', { name: 'jose ramirez' }).Kind, 'zips-fill');
  assert.strictEqual(e.call('projFlagFor', { name: 'tarik skubal' }), null);
  const lab = e.call('projFlagLabel', m);
  assert.ok(lab.text.length <= 8 && /183 IP/.test(lab.title) && /116 IP/.test(lab.title));
  assert.ok(/ZiPS/.test(e.call('projFlagLabel', e.call('projFlagFor', { name: 'jose ramirez' })).title));
});

test('UTIL floor: a 1B-only bat never grades below a UTIL-only bat with the same line', () => {
  const e = loadEngine();
  const b = { pa: 590, hr: 18, r: 75, obp: 0.355, slg: 0.443 };
  const repl = { pa: 550, hr: 15, r: 65, obp: 0.320, slg: 0.410 };
  const offs = { '1b': { obp: 0.015, slg: 0.027, hrRate: 0.005, rRate: 0.005 } };
  const denom = { HR: 10, R: 25, OBP: 0.005, SLG: 0.009 };
  const util = e.call('hitterSGP', { type: 'H', positions: [] }, b, repl, offs, denom, 550, 150);
  const first = e.call('hitterSGP', { type: 'H', positions: ['1b'] }, b, repl, offs, denom, 550, 150);
  assert.ok(first >= util, `1B ${first} < UTIL ${util}`);
});

test('offseason economics: bad contracts are $0, cap room is worth the auction rate, more when forced to cut', () => {
  const e = loadEngine();
  assert.strictEqual(e.call('offseasonValue', -19), 0);
  assert.strictEqual(e.call('offseasonValue', 12), 12);
  const base = e.get('CAP_DOLLAR_BASE');
  assert.ok(Math.abs(base - 0.25) < 1e-9);
  // Over $400 only because of a bad contract: nothing good must go, room is worth the base rate.
  const a = e.call('teamCapPlan', [{ salary: 300, surplus: 40 }, { salary: 150, surplus: -20 }]);
  assert.deepStrictEqual([a.payroll, a.over, a.keptPay, a.need], [450, 50, 300, 0]);
  assert.strictEqual(a.rate, base);
  // Good players alone exceed $400: the lowest surplus-per-dollar one goes, and its ratio is added.
  const b = e.call('teamCapPlan', [{ salary: 300, surplus: 60 }, { salary: 120, surplus: 12 }, { salary: 30, surplus: 30 }]);
  assert.strictEqual(b.need, 50);
  assert.strictEqual(b.cuts.length, 1);
  assert.ok(Math.abs(b.rate - (base + 0.1)) < 1e-9);
});

test('offseason trade value charges salary once at the cap rate, floors at $0, and blends 25% of 2026 for partners', () => {
  const e = loadEngine();
  const v = (val, cost, c, m) => e.call('offseasonTradeValue', val, cost, c, m);
  assert.strictEqual(v(59, 62, 0.25), 59 - 15.5);                 // Judge: a fair-priced star is worth real value
  assert.strictEqual(v(14, 35, 1), 0);                            // a bad contract is $0, never negative
  assert.strictEqual(v(36, 57, 0.25, { actual: 44, proj: 36 }), 36 + 2 - 14.25);
  e.localStorage.setItem('ottoneu_market_2026', JSON.stringify([{ Name: 'Shohei Ohtani', Type: 'H', Value2026: '52' }, { Name: 'Shohei Ohtani', Type: 'P', Value2026: '20' }]));
  assert.strictEqual(e.call('marketValueFor', { name: 'shohei ohtani', type: 'P' }), 20);
  assert.strictEqual(e.call('marketValueFor', { name: 'shohei ohtani', type: 'H' }), 52);
  assert.strictEqual(e.call('marketValueFor', { name: 'nobody', type: 'H' }), null);
});
