// audit/lib/stats.js
// One compact file per day of MLB stats (all players), fetched once and cached.
// Any ownership window is then a sum over cached days.
const fs = require('fs');
const path = require('path');

const API = 'https://statsapi.mlb.com/api/v1/stats?stats=byDateRange&sportId=1&gameType=R&playerPool=all&limit=1000';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function fetchGroup(group, date) {
  let out = [];
  for (let offset = 0; offset < 10000; offset += 1000) {
    const res = await fetch(`${API}&group=${group}&startDate=${date}&endDate=${date}&offset=${offset}`);
    if (!res.ok) throw new Error(`MLB API ${res.status} for ${group} ${date}`);
    const splits = ((await res.json()).stats?.[0]?.splits) || [];
    out = out.concat(splits);
    if (splits.length < 1000) break;
    await sleep(250);
  }
  return out;
}

const n = v => +v || 0;

async function fetchDay(date, cacheDir) {
  const file = path.join(cacheDir, 'stats', date + '.json');
  if (fs.existsSync(file)) return JSON.parse(fs.readFileSync(file, 'utf8'));
  const hs = await fetchGroup('hitting', date);
  const ps = await fetchGroup('pitching', date);
  const day = {
    h: hs.map(s => { const t = s.stat; return [s.player.id, s.player.fullName, n(t.plateAppearances), n(t.atBats), n(t.hits), n(t.baseOnBalls), n(t.hitByPitch), n(t.sacFlies), n(t.homeRuns), n(t.runs), n(t.totalBases)]; }),
    p: ps.map(s => { const t = s.stat; return [s.player.id, s.player.fullName, n(t.outs), n(t.strikeOuts), n(t.earnedRuns), n(t.baseOnBalls), n(t.hits), n(t.homeRuns), n(t.gamesPitched), n(t.gamesStarted)]; }),
  };
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(day));
  await sleep(250);
  return day;
}

function seasonDays(season) {
  const out = []; const d = new Date(Date.UTC(season, 2, 15)); const end = Date.UTC(season, 9, 5);
  while (d.getTime() <= end) { out.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() + 1); }
  return out;
}

const H_KEYS = ['pa', 'ab', 'h', 'bb', 'hbp', 'sf', 'hr', 'r', 'tb'];
const P_KEYS = ['outs', 'so', 'er', 'bb', 'h', 'hr', 'g', 'gs'];

function sumWindow(days, mlbId, group) {
  const keys = group === 'h' ? H_KEYS : P_KEYS;
  const acc = Object.fromEntries(keys.map(k => [k, 0])); let seen = false;
  for (const d of days) for (const row of d[group]) {
    if (row[0] !== mlbId) continue;
    seen = true; keys.forEach((k, i) => { acc[k] += row[i + 2]; });
  }
  if (!seen) return null;
  if (group === 'h') {
    const den = acc.ab + acc.bb + acc.hbp + acc.sf;
    acc.obp = den ? (acc.h + acc.bb + acc.hbp) / den : 0;
    acc.slg = acc.ab ? acc.tb / acc.ab : 0;
  } else {
    acc.ip = acc.outs / 3;
    acc.era = acc.ip ? acc.er * 9 / acc.ip : 0;
    acc.whip = acc.ip ? (acc.bb + acc.h) / acc.ip : 0;
    acc.hr9 = acc.ip ? acc.hr * 9 / acc.ip : 0;
  }
  return acc;
}

module.exports = { fetchDay, seasonDays, sumWindow };
