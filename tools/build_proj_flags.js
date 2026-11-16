#!/usr/bin/env node
// tools/build_proj_flags.js — writes data/proj_flags.csv and data/proj_fills_{hitting,pitching}.csv.
//   node tools/build_proj_flags.js
// Re-run whenever "this season" projections change meaningfully, and switch ZIPS_SOURCE
// to the fresh preseason ZiPS when FanGraphs releases it (Dec-Feb).
//
// Inputs:
//   - Steamer "this season": data/proj_hitting.csv / proj_pitching.csv (Apps Script, daily)
//   - ZiPS for the same season: the in-season ZiPS 2027 lines (zipsp1) as last pulled
//     before FanGraphs' November rollover, read from git history
//   - Who is "established": best MLB season of the last three, from audit/cache/stats
//     (run `node audit/run.js` once if the cache is missing)
const fs = require('fs');
const path = require('path');
const { loadEngine } = require('../audit/lib/engine');
const g = require('../audit/lib/gitdata');
const { computeFlags } = require('./projflags');

const ROOT = path.join(__dirname, '..');
const ZIPS_SOURCE = { before: '2026-11-01', hitting: 'data/proj_hitting_y1.csv', pitching: 'data/proj_pitching_y1.csv' };
const USAGE_SEASONS = [2024, 2025, 2026];

const e = loadEngine();
const parse = t => e.call('parseCSV', t);
const norm = s => e.call('normalizeName', s);

function lastGood(file) {
  const hist = g.fileHistory(file).filter(h => h.date < ZIPS_SOURCE.before).reverse();
  for (const h of hist) { const t = g.fileAt(h.sha, file); if (t.length > 10000) return { text: t, date: h.date }; }
  throw new Error('No non-empty version of ' + file + ' before ' + ZIPS_SOURCE.before);
}

// Best single season of the last three: a pitcher hurt for most of 2026 is still established.
function usage() {
  const dir = path.join(ROOT, 'audit', 'cache', 'stats');
  if (!fs.existsSync(dir)) throw new Error('audit/cache/stats missing: run `node audit/run.js` first');
  const bySeason = new Map();   // 'name|year' -> totals
  for (const f of fs.readdirSync(dir).filter(f => USAGE_SEASONS.includes(+f.slice(0, 4)))) {
    const y = f.slice(0, 4);
    const day = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
    const add = (name, pa, ip) => { const k = norm(name) + '|' + y; const x = bySeason.get(k) || { pa: 0, ip: 0 }; x.pa += pa; x.ip += ip; bySeason.set(k, x); };
    for (const r of day.h) add(r[1], r[2], 0);
    for (const r of day.p) add(r[1], 0, r[2] / 3);
  }
  const u = new Map();
  for (const [k, v] of bySeason) {
    const n = k.split('|')[0]; const x = u.get(n) || { pa: 0, ip: 0 };
    x.pa = Math.max(x.pa, v.pa); x.ip = Math.max(x.ip, v.ip); u.set(n, x);
  }
  return u;
}

const csv = (rows, cols) => [cols.join(',')].concat(rows.map(r => cols.map(c => {
  const v = r[c] == null ? '' : String(r[c]);
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
}).join(','))).join('\n') + '\n';

const zh = lastGood(ZIPS_SOURCE.hitting), zp = lastGood(ZIPS_SOURCE.pitching);
const steamerHText = fs.readFileSync(path.join(ROOT, 'data/proj_hitting.csv'), 'utf8');
const steamerPText = fs.readFileSync(path.join(ROOT, 'data/proj_pitching.csv'), 'utf8');
const r = computeFlags({ steamerH: parse(steamerHText), steamerP: parse(steamerPText),
  zipsH: parse(zh.text), zipsP: parse(zp.text), usage: usage(), norm,
  fillOnly: new Set(parse(fs.readFileSync(path.join(ROOT, 'data/roster.csv'), 'utf8')).map(x => norm(x.Name))) });

const hCols = steamerHText.split(/\r?\n/)[0].split(','), pCols = steamerPText.split(/\r?\n/)[0].split(',');
fs.writeFileSync(path.join(ROOT, 'data/proj_flags.csv'), csv(r.flags, ['Name', 'Type', 'Kind', 'Unit', 'Steamer', 'Zips']));
fs.writeFileSync(path.join(ROOT, 'data/proj_fills_hitting.csv'), csv(r.fillsH, hCols));
fs.writeFileSync(path.join(ROOT, 'data/proj_fills_pitching.csv'), csv(r.fillsP, pCols));
// The same ZiPS season, whole: shared.js blends it 50/50 into "this season" in the offseason (blendProjections).
fs.writeFileSync(path.join(ROOT, 'data/proj_zips_hitting.csv'), zh.text);
fs.writeFileSync(path.join(ROOT, 'data/proj_zips_pitching.csv'), zp.text);
console.log(`ZiPS source ${zh.date} / ${zp.date} · flags ${r.flags.length} (zips-fill ${r.flags.filter(f => f.Kind === 'zips-fill').length}, steamer-zero ${r.flags.filter(f => f.Kind === 'steamer-zero').length}, workload ${r.flags.filter(f => f.Kind === 'workload').length}) · fills ${r.fillsH.length} hitters, ${r.fillsP.length} pitchers`);
