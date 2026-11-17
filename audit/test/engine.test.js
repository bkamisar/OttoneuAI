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
  // A half-season sample gets half the say: Judge raked in 285 PA.
  assert.strictEqual(v(59, 62, 0.25, { actual: 41, sample: 0.5, proj: 59 }), 59 + 0.25 * 0.5 * (41 - 59) - 15.5);
  e.localStorage.setItem('ottoneu_market_2026', JSON.stringify([{ Name: 'Shohei Ohtani', Type: 'H', Value2026: '52', Sample: '1.00' }, { Name: 'Shohei Ohtani', Type: 'P', Value2026: '20', Sample: '0.50' }]));
  const op = e.call('marketValueFor', { name: 'shohei ohtani', type: 'P' });
  assert.deepStrictEqual([op.actual, op.sample], [20, 0.5]);
  assert.strictEqual(e.call('marketValueFor', { name: 'shohei ohtani', type: 'H' }).actual, 52);
  assert.strictEqual(e.call('marketValueFor', { name: 'nobody', type: 'H' }), null);
});

test('SGP_DENOMS match the real final standings (rerun tools/build_sgp_denoms.js when a season is added)', () => {
  const e = loadEngine();
  const { denoms } = require('../../tools/build_sgp_denoms').computeDenoms();
  assert.deepStrictEqual({ ...e.get('SGP_DENOMS') }, denoms);
});

test('leagueSGPDenoms scales only the counting stats by the share of season left', () => {
  const e = loadEngine();
  const full = e.call('leagueSGPDenoms', 1), half = e.call('leagueSGPDenoms', 0.5);
  for (const k of ['R', 'HR', 'SO']) assert.ok(Math.abs(half[k] - full[k] / 2) < 1e-9, k);
  for (const k of ['OBP', 'SLG', 'ERA', 'WHIP', 'HR9']) assert.strictEqual(half[k], full[k], k);
  assert.strictEqual(e.call('leagueSGPDenoms', 0).SO, full.SO * 0.1);   // floor, never divide by 0
});

test('blendProjections: 50/50 playing time and rates, skips placeholders, fills, duplicate names; idempotent', () => {
  const e = loadEngine();
  const P = (name, ip, so, era, extra) => ({ name, type: 'P', proj: { ip, so, era, whip: 1.2, hr9: 1, hr: ip / 9, h: ip, bb: ip / 3, er: era * ip / 9 }, ...extra });
  const steamer = [P('ace', 180, 220, 3.0), P('placeholder', 1, 1, 4), P('filled', 120, 100, 4, { filled: true }), P('twin', 100, 90, 4), P('twin', 60, 50, 5), P('no zips', 150, 150, 4)];
  const zips = [P('ace', 120, 120, 3.6), P('placeholder', 150, 150, 3.5), P('filled', 60, 60, 3), P('twin', 80, 80, 3)];
  const out = e.call('blendProjections', steamer, zips, 'P');
  const ace = out[0].proj;
  assert.strictEqual(ace.ip, 150);
  assert.ok(Math.abs(ace.era - 3.3) < 1e-9);
  assert.ok(Math.abs(ace.so - (220 / 180 + 120 / 120) / 2 * 150) < 1e-9);   // blended K rate x blended innings
  assert.ok(Math.abs(ace.er - 3.3 * 150 / 9) < 1e-9);
  assert.strictEqual(out[0].blended, true);
  for (const i of [1, 2, 3, 4, 5]) assert.strictEqual(out[i], steamer[i], steamer[i].name + ' untouched');
  const again = e.call('blendProjections', out, zips, 'P');
  assert.strictEqual(again[0].proj.ip, 150);
  const H = (name, pa, hr, obp) => ({ name, type: 'H', proj: { pa, ab: pa * 0.9, h: pa * 0.25, bb: pa * 0.08, hbp: 0, hr, r: pa / 8, obp, slg: 0.45 } });
  const h = e.call('blendProjections', [H('bat', 600, 30, 0.36)], [H('bat', 400, 16, 0.34)], 'H')[0].proj;
  assert.strictEqual(h.pa, 500);
  assert.ok(Math.abs(h.hr - (30 / 600 + 16 / 400) / 2 * 500) < 1e-9);
  assert.ok(Math.abs(h.obp - 0.35) < 1e-9);
});

test('offseason: hitter replacement is the post-auction boundary, not a cut star waiting for the auction', () => {
  const e = loadEngine();
  const H = (name, obp) => ({ name, fgId: '', type: 'H', proj: { pa: 600, hr: 20, r: 80, obp, slg: obp + 0.1 } });
  const P = (name, era) => ({ name, fgId: '', type: 'P', proj: { ip: 150, so: 140, era, whip: 1.2, hr9: 1 } });
  // 20 hitters best to worst; the best one ("star") is unrostered, #2-#11 are rostered.
  const hit = Array.from({ length: 20 }, (_, i) => H(i === 0 ? 'star' : 'h' + i, 0.40 - i * 0.005));
  const pit = Array.from({ length: 14 }, (_, i) => P('p' + i, 3 + i * 0.1));
  const roster = hit.slice(1, 11).map(p => ({ ...p, positions: ['of'], salary: 5, team: 't' }));
  e.setDate('2026-11-15');
  e.call('matchPlayers', roster, hit, pit);
  const off = e.get('FA_BASELINES').proj.H.obp;
  e.setDate('2026-06-27');
  e.call('matchPlayers', roster, hit, pit);
  const inSeason = e.get('FA_BASELINES').proj.H.obp;
  const avg = a => a.reduce((s, p) => s + p.proj.obp, 0) / a.length;
  assert.ok(Math.abs(off - avg(hit.slice(10, 18))) < 1e-9, 'offseason: the 8 bats after the 10 the league rosters (star gets bought)');
  const fa = hit.filter(p => !roster.some(r => r.name === p.name));
  assert.ok(Math.abs(inSeason - avg(fa.slice(0, 8))) < 1e-9, 'in season: the best actual free agents, star included');
  assert.ok(off < inSeason);
});

test('prospect timing: FV+ soon tier overrides ETA, each year away costs PROSPECT_YEAR_DISCOUNT', () => {
  const e = loadEngine();
  e.setDate('2026-11-17');                       // offseason: prospects are measured against 2027
  assert.strictEqual(e.call('prospectSeason'), 2027);
  e.setDate('2026-06-01');
  assert.strictEqual(e.call('prospectSeason'), 2026);
  e.setDate('2026-11-17');
  const pr = { fv: 55, rank: 15, eta: '2029', pos: 'SS', risk: 'Med' };
  const yrs = t => e.call('prospectYearsAway', pr, t);
  assert.strictEqual(yrs(undefined), 2);         // ETA fallback
  assert.strictEqual(yrs(0), 2);                 // modeled but not near: ETA stands
  assert.strictEqual(yrs(25), 1);                // top-25% soon: at most a year away
  assert.strictEqual(yrs(10), 0);
  assert.strictEqual(yrs(5), 0);
  assert.strictEqual(e.call('prospectYearsAway', { ...pr, eta: '2026' }, undefined), 0);   // already due
  const d = e.get('PROSPECT_YEAR_DISCOUNT');
  const now = e.call('prospectDynastyValue', pr, 5), far = e.call('prospectDynastyValue', pr, undefined);
  assert.ok(Math.abs(far - now * d * d) < 1e-9);
});

test('parseProspectSoon keeps only the tier map, keyed by normalized name and org', () => {
  const e = loadEngine();
  const text = JSON.stringify({ fvplus: { H: { 'José Pérez|CLE': { rank: 3, tier: 5 } }, P: { 'Sam Arm|NYY': { rank: 300, tier: 0 } } }, graded: [{}] });
  const m = e.call('parseProspectSoon', text);
  assert.deepStrictEqual({ ...m }, { 'jose perez|CLE': 5, 'sam arm|NYY': 0 });
});
