#!/usr/bin/env node
// tools/build_ages.js — writes data/ages.csv (Name,BirthDate) for the dynasty aging curve.
//   node tools/build_ages.js
// Source: the MLB Stats API game records the prospects-model already downloaded
// (prospects-model/cache/pbp_live/<season>/<sportId>/*.json.gz; gameData.players carries
// every player's birth date). MLB and AAA, the two most recent seasons on disk. No network.
// Names that map to two different birth dates are left out (the engine then treats the
// player's age as unknown), so a name collision can never age the wrong player.
// Re-run after a season's game records are added (new call-ups).
const fs = require('fs'), path = require('path'), zlib = require('zlib');
const ROOT = path.join(__dirname, '..');
const BASE = path.join(ROOT, 'prospects-model', 'cache', 'pbp_live');
const LEVELS = ['1', '11'];   // MLB, AAA

if (!fs.existsSync(BASE)) throw new Error('No game records at ' + BASE + ' (prospects-model cache)');
const seasons = fs.readdirSync(BASE).filter(s => /^\d{4}$/.test(s)).sort().slice(-2);
const dates = new Map(), clash = new Set();
let games = 0;
for (const s of seasons) for (const lv of LEVELS) {
  const dir = path.join(BASE, s, lv); if (!fs.existsSync(dir)) continue;
  for (const f of fs.readdirSync(dir).filter(x => x.endsWith('.json.gz'))) {
    let j; try { j = JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(dir, f)))); } catch (e) { continue; }
    games++;
    for (const p of Object.values((j.gameData && j.gameData.players) || {})) {
      if (!p.fullName || !p.birthDate) continue;
      const seen = dates.get(p.fullName);
      if (seen && seen.d !== p.birthDate && seen.id !== p.id) clash.add(p.fullName);
      if (!seen) dates.set(p.fullName, { d: p.birthDate, id: p.id });
    }
  }
}
const q = v => /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
const rows = [...dates].filter(([n]) => !clash.has(n)).sort((a, b) => a[0].localeCompare(b[0])).map(([n, x]) => q(n) + ',' + x.d);
fs.writeFileSync(path.join(ROOT, 'data', 'ages.csv'), 'Name,BirthDate\n' + rows.join('\n') + '\n');
console.log(`ages.csv: ${rows.length} players from ${games} games (${seasons.join(', ')}), ${clash.size} name collisions left out`);
