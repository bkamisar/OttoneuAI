#!/usr/bin/env node
// tools/build_market_2026.js -- writes data/market_2026.csv (Name, Type, Value2026).
//   node tools/build_market_2026.js
// What each rostered player's ACTUAL 2026 season was worth, valued by the same
// engine as the projections (offseason date, today's rosters, actual lines in
// place of projections). The trade finder blends 25% of it into the values it
// uses to guess what trade PARTNERS will accept: managers price on what they
// watched, not on Steamer. Your own valuations stay projection-only.
//
// Source: the audit's daily MLB Stats API cache (audit/cache/stats, first-party).
// Run `node audit/run.js` first if it is missing.
const fs = require('fs');
const path = require('path');
const { loadEngine } = require('../audit/lib/engine');

const ROOT = path.join(__dirname, '..');
const SEASON = '2026';
const MIN = { pa: 100, ip: 30 };   // less than this = no real 2026 season, no market blend

const e = loadEngine();
e.setDate('2026-11-15');
const norm = s => e.call('normalizeName', s);

// Sum the season's daily lines per player.
const dir = path.join(ROOT, 'audit', 'cache', 'stats');
if (!fs.existsSync(dir)) throw new Error('audit/cache/stats missing: run `node audit/run.js` first');
const H = new Map(), P = new Map();
for (const f of fs.readdirSync(dir).filter(f => f.startsWith(SEASON))) {
  const day = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
  for (const r of day.h) {   // id, name, PA, AB, H, BB, HBP, SF, HR, R, TB
    const x = H.get(r[0]) || { name: r[1], pa: 0, ab: 0, h: 0, bb: 0, hbp: 0, sf: 0, hr: 0, r: 0, tb: 0 };
    x.pa += r[2]; x.ab += r[3]; x.h += r[4]; x.bb += r[5]; x.hbp += r[6]; x.sf += r[7]; x.hr += r[8]; x.r += r[9]; x.tb += r[10];
    H.set(r[0], x);
  }
  for (const r of day.p) {   // id, name, outs, SO, ER, BB, H, HR, G, GS
    const x = P.get(r[0]) || { name: r[1], outs: 0, so: 0, er: 0, bb: 0, h: 0, hr: 0, g: 0, gs: 0 };
    x.outs += r[2]; x.so += r[3]; x.er += r[4]; x.bb += r[5]; x.h += r[6]; x.hr += r[7]; x.g += r[8]; x.gs += r[9];
    P.set(r[0], x);
  }
}

const q = v => /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v);
const hitCSV = ['Name,Team,PA,AB,H,HR,R,BB,HBP,OBP,SLG'].concat([...H.values()].filter(x => x.pa >= MIN.pa).map(x => {
  const obpDen = x.ab + x.bb + x.hbp + x.sf;
  return [q(x.name), '', x.pa, x.ab, x.h, x.hr, x.r, x.bb, x.hbp,
    (obpDen ? (x.h + x.bb + x.hbp) / obpDen : 0).toFixed(4), (x.ab ? x.tb / x.ab : 0).toFixed(4)].join(',');
})).join('\n');
const pitCSV = ['Name,Team,GS,G,IP,HR,SO,BB,HR/9,WHIP,ERA'].concat([...P.values()].filter(x => x.outs / 3 >= MIN.ip).map(x => {
  const ip = x.outs / 3;
  return [q(x.name), '', x.gs, x.g, ip.toFixed(1), x.hr, x.so, x.bb,
    (x.hr * 9 / ip).toFixed(3), ((x.bb + x.h) / ip).toFixed(3), (x.er * 9 / ip).toFixed(3)].join(',');
})).join('\n');

// Value the actual lines exactly as the pages value projections.
const hp = e.call('parseHittingProjections', hitCSV);
const pp = e.call('parsePitchingProjections', pitCSV);
const rc = fs.readFileSync(path.join(ROOT, 'data', 'roster.csv'), 'utf8');
const roster = e.call('parseRosterCSV', rc);
const rows = e.call('parseCSV', rc);
roster.forEach((p, i) => { p.teamId = rows[i]['TeamID']; });
const m = e.call('matchPlayers', roster, hp, pp);
const byT = {};
m.forEach(p => (byT[p.teamId] = byT[p.teamId] || []).push(p));
const vm = e.call('calculateAllValues', Object.values(byT), null, true);

const out = ['Name,Type,Value2026'];
let n = 0;
for (const p of m) {
  if (!p.proj) continue;                       // no real 2026 season -> no market blend
  const v = vm[p.fgId || p.name];
  if (!v) continue;
  out.push([q(p.rawName), p.type, Math.round(v.projectedValue || 0)].join(','));
  n++;
}
fs.writeFileSync(path.join(ROOT, 'data', 'market_2026.csv'), out.join('\n') + '\n');
console.log(`market_2026.csv: ${n} rostered players with a real 2026 season (of ${m.length})`);
