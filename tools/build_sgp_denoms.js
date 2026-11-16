#!/usr/bin/env node
// tools/build_sgp_denoms.js — the league's real SGP denominators.
//   node tools/build_sgp_denoms.js
// Prints the SGP_DENOMS line for shared.js: the stdev of each category across the
// teams that reached the 1,250 IP minimum, averaged over every
// data/standings-final-YYYY.csv. Paste it into shared.js when a new season's file
// lands (audit/test/engine.test.js fails until the two agree).
const fs = require('fs');
const path = require('path');
const DATA = path.join(__dirname, '..', 'data');
const COLS = { R: 'R', HR: 'HR', OBP: 'OBP', SLG: 'SLG', SO: 'K', HR9: 'HR/9', ERA: 'ERA', WHIP: 'WHIP' };
const IP_MIN = 1250;

const stdev = a => { const m = a.reduce((s, x) => s + x, 0) / a.length; return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / a.length); };
const sig3 = x => +x.toPrecision(3);

function computeDenoms() {
  const files = fs.readdirSync(DATA).filter(f => /^standings-final-\d{4}\.csv$/.test(f)).sort();
  const perSeason = files.map(f => {
    const lines = fs.readFileSync(path.join(DATA, f), 'utf8').trim().split(/\r?\n/);
    const head = lines[0].split(',');
    const rows = lines.slice(1).map(l => l.match(/("[^"]*"|[^,]+)/g)).filter(r => +r[head.indexOf('IP')] >= IP_MIN);
    return Object.fromEntries(Object.entries(COLS).map(([k, col]) => [k, stdev(rows.map(r => +r[head.indexOf(col)]))]));
  });
  const denoms = Object.fromEntries(Object.keys(COLS).map(k => [k, sig3(perSeason.reduce((s, d) => s + d[k], 0) / perSeason.length)]));
  return { denoms, seasons: files.map(f => f.slice(16, 20)) };
}

module.exports = { computeDenoms };
if (require.main === module) {
  const { denoms, seasons } = computeDenoms();
  console.log('seasons: ' + seasons.join(', '));
  console.log('const SGP_DENOMS = { ' + Object.entries(denoms).map(([k, v]) => k + ': ' + v).join(', ') + ' };');
}
