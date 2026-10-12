// audit/lib/production.js
// Ottoneu "team production": the lineup-only stats each player counted for each
// team in a season (one row per player/team/season). The factual basis for v2 grades.
const { parseCSVLine } = require('./moves');

const MONTHS = { January: 1, February: 2, March: 3, April: 4, May: 5, June: 6, July: 7, August: 8, September: 9, October: 10, November: 11, December: 12 };
const isoDate = s => {
  const m = String(s).match(/^(\w+) (\d+), (\d{4})/); if (!m) return '';
  const p = n => String(n).padStart(2, '0'); return `${m[3]}-${p(MONTHS[m[1]])}-${p(m[2])}`;
};
const innings = s => { const f = parseFloat(s) || 0; const w = Math.floor(f); return w + Math.round((f - w) * 10) / 3; };

function parseProduction(text) {
  const L = text.replace(/\r/g, '').trim().split('\n');
  const rows = []; const bench = new Map();
  for (const l of L.slice(1)) {
    const [season, teamId, group, ottoneuId, player, acquired, g, c1, c2, c3, c4, c5] = parseCSVLine(l);
    const pit = { ip: innings(c1), so: +c2, hr9: +c3, era: +c4, whip: +c5 };
    if (group === 'PBENCH') { bench.set(season + '|' + teamId, pit); continue; }
    rows.push({ season: +season, teamId, group, ottoneuId, player, acquired: isoDate(acquired), g: +g,
      line: group === 'H' ? { ab: +c1, r: +c2, hr: +c3, obp: +c4, slg: +c5 } : pit });
  }
  return { rows, bench };
}

// counted(ottoneuId, teamId, season) -> { type, line } of what counted for that team.
// Hitter PA isn't on the page: estimated from AB with the player's own PA/AB ratio.
function makeCounted(rows, paRatio) {
  const idx = new Map();
  rows.forEach(r => { const k = r.season + '|' + r.teamId + '|' + r.ottoneuId; const e = idx.get(k) || {}; e[r.group] = r; idx.set(k, e); });
  return (ottoneuId, teamId, season) => {
    const e = idx.get(season + '|' + teamId + '|' + ottoneuId);
    if (!e) return { type: null, line: null };
    if (e.H) {
      const line = { ...e.H.line, pa: Math.round(e.H.line.ab * (paRatio(String(ottoneuId), season) || 1.12)) };
      if (e.P) line.pitch = { ...e.P.line };
      return { type: 'H', line };
    }
    return { type: 'P', line: { ...e.P.line } };
  };
}

function teamsWithPlayer(rows, ottoneuId, season) {
  const seen = new Map();
  rows.filter(r => r.ottoneuId === String(ottoneuId) && r.season === season).forEach(r => seen.set(r.teamId, { teamId: r.teamId, acquired: r.acquired }));
  return [...seen.values()];
}

module.exports = { parseProduction, makeCounted, teamsWithPlayer };
