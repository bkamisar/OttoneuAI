// shared.js — Ottoneu 4x4 Tool Suite core logic
// Load via <script src="shared.js"> in every tool page.

// ── CONSTANTS ────────────────────────────────────────────────────────────────
const CATS         = ["OBP","SLG","HR","R","ERA","WHIP","HR9","SO"];
const LOWER_BETTER = new Set(["ERA","WHIP","HR9"]);
const NUM_TEAMS    = 12;
const SALARY_POOL  = 4800;    // $400 × 12 teams

// BatX RoS projections are already regression-adjusted from real stats-to-date.
// Setting these to 0 passes rate stats through unchanged (no double regression).
// LG_MEAN is retained for future Y1/Y2 regression use; currently inactive (REGRESS = 0).
// Values = mean team stats across 24 team-seasons (2024 + 2025, 12 teams each).
const REGRESS_PA = 0;
const REGRESS_IP = 0;
const LG_MEAN = { OBP: 0.325, SLG: 0.430, ERA: 3.735, WHIP: 1.197, HR9: 1.087 };

const OF_GAME_CAP  = 810;     // 5 OF × 162 games
const SLOT_CAP     = 162;
const IP_MAX       = 1500;
const IP_MIN       = 400;   // RoS projections have lower IP totals; 400 works year-round
const TWO_WAY_IP_MIN = 30; // Min projected IP for a hitter to count as a true two-way pitcher

// ── PRORATION ────────────────────────────────────────────────────────────────
// Returns the fraction of the MLB season remaining as of today.
// Used by FA and trade tools to show rest-of-season dollar value alongside
// full-season value. Approximates opening day as March 28, end as September 28.
function rosProrationFactor() {
  const year  = new Date().getFullYear();
  const start = new Date(year, 2, 28);  // March 28
  const end   = new Date(year, 8, 28);  // September 28
  const today = new Date();
  if (today <= start) return 1.0;
  if (today >= end)   return 0.0;
  return (end - today) / (end - start);
}

// ── REPO AUTO-LOAD ───────────────────────────────────────────────────────────
// Maps data/ filenames to localStorage keys and parser functions.
// Matches the keys the rest of the app reads from localStorage.
const REPO_FILES = [
  { file: 'roster.csv',           key: 'ottoneu_roster',            parse: parseRosterCSV },
  { file: 'proj_hitting.csv',     key: 'ottoneu_proj_hitting',      parse: parseHittingProjections },
  { file: 'proj_pitching.csv',    key: 'ottoneu_proj_pitching',     parse: parsePitchingProjections },
  { file: 'proj_hitting_y1.csv',  key: 'ottoneu_proj_hitting_y1',   parse: parseHittingProjections },
  { file: 'proj_pitching_y1.csv', key: 'ottoneu_proj_pitching_y1',  parse: parsePitchingProjections },
  { file: 'proj_hitting_y2.csv',  key: 'ottoneu_proj_hitting_y2',   parse: parseHittingProjections },
  { file: 'proj_pitching_y2.csv', key: 'ottoneu_proj_pitching_y2',  parse: parsePitchingProjections },
  { file: 'prospects.csv',        key: 'ottoneu_prospects',          parse: parseProspectsCSV },
  { file: 'standings.csv',        key: 'ottoneu_curr_standings',     parse: parseCurrStandings },
];

// Fetches all data/ CSVs from the repo, parses them, and writes to localStorage.
// Returns a status map: { 'roster.csv': true, 'proj_hitting.csv': false, ... }
// Returns {} immediately on file:// so local dev is unaffected.
// Fetch with retry on transient failures (network errors, 5xx). A 404 is a
// genuine "file absent" and returns immediately without retrying. Guards against
// dropped fetches when many files load in parallel.
async function fetchWithRetry(url, attempts) {
  attempts = attempts || 3;
  let lastErr;
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404) return res;
      lastErr = new Error('HTTP ' + res.status);
    } catch (e) {
      lastErr = e;
    }
    if (i < attempts - 1) await new Promise(r => setTimeout(r, 150 * (i + 1)));
  }
  throw lastErr;
}

// Files we show freshness stamps for — these get their real last-commit time
// from the GitHub API (see refineCommitStamps). Others just use fetch time.
const STAMPED_FILES = ['proj_hitting.csv', 'roster.csv', 'standings.csv'];

// Derive owner/repo from the GitHub Pages URL (e.g. bkamisar.github.io/OttoneuAI),
// falling back to the known repo for local dev / other hosts.
function repoSlug() {
  const host  = window.location.hostname || '';
  const parts = (window.location.pathname || '').split('/').filter(Boolean);
  if (host.endsWith('github.io') && parts.length) {
    return { owner: host.split('.')[0], repo: parts[0] };
  }
  return { owner: 'bkamisar', repo: 'OttoneuAI' };
}

// Real "last changed" time for a repo file = the date of the last commit that
// touched it (GitHub commits API). Cached ~30 min in localStorage to stay well
// under the 60/hr unauthenticated rate limit. Returns ms epoch or null.
const COMMIT_TS_TTL = 30 * 60 * 1000;
async function fetchLastCommitTs(path, key) {
  const cacheKey = key + '_commit';
  const cached = loadData(cacheKey);
  if (cached && (Date.now() - cached.checkedAt) < COMMIT_TS_TTL) return cached.ts;
  try {
    const { owner, repo } = repoSlug();
    const url = 'https://api.github.com/repos/' + owner + '/' + repo +
                '/commits?path=' + encodeURIComponent(path) + '&per_page=1';
    const res = await fetch(url, { headers: { 'Accept': 'application/vnd.github+json' } });
    if (!res.ok) return cached ? cached.ts : null;
    const arr = await res.json();
    if (!Array.isArray(arr) || !arr.length) return cached ? cached.ts : null;
    const ts = Date.parse(arr[0].commit.committer.date);
    saveData(cacheKey, { ts: ts, checkedAt: Date.now() });
    return ts;
  } catch (e) {
    return cached ? cached.ts : null;   // offline / rate-limited → keep last known
  }
}

async function autoLoadFromRepo() {
  if (window.location.protocol === 'file:') return {};
  const status = {};
  await Promise.all(REPO_FILES.map(async function({ file, key, parse }) {
    try {
      const res = await fetchWithRetry('./data/' + file);
      if (!res.ok) { console.warn('[autoLoad] 404:', file); status[file] = false; return; }
      const text = await res.text();
      const parsed = parse(text);
      console.log('[autoLoad]', file, '→', Array.isArray(parsed) ? parsed.length + ' rows' : typeof parsed);
      saveData(key, parsed);
      // Provisional freshness from the fetch (Last-Modified ≈ deploy time, else now).
      // For stamped files this is refined below to the real commit time.
      const lastMod = res.headers.get('Last-Modified');
      saveData(key + '_ts',  lastMod ? Date.parse(lastMod) : Date.now());
      saveData(key + '_src', 'repo');
      status[file] = true;
    } catch (e) {
      console.error('[autoLoad] ERROR:', file, e);
      status[file] = false;
    }
  }));

  // Refine the stamped files' timestamps to the REAL last-commit time so the UI
  // shows when the data actually changed, not when the tab loaded. Best-effort.
  await Promise.all(STAMPED_FILES.map(async function(file) {
    if (!status[file]) return;
    const entry = REPO_FILES.find(function(f) { return f.file === file; });
    if (!entry) return;
    const ts = await fetchLastCommitTs('data/' + file, entry.key);
    if (ts) saveData(entry.key + '_ts', ts);
  }));

  return status;
}

// ── DATA FRESHNESS STAMPS ────────────────────────────────────────────────────
// Returns { ts, src } for a data key, or null if no timestamp recorded.
// src is 'repo' (auto-loaded from GitHub) or 'manual' (uploaded in browser).
function getDataStamp(key) {
  const ts = loadData(key + '_ts');
  if (!ts) return null;
  return { ts: ts, src: loadData(key + '_src') || 'manual' };
}

// Human-readable relative age, e.g. "3 days ago", "just now".
function relativeAge(ts) {
  const ms = Date.now() - ts;
  if (ms < 0) return 'just now';
  const min = Math.floor(ms / 60000);
  if (min < 1)  return 'just now';
  if (min < 60) return min + (min === 1 ? ' min ago' : ' mins ago');
  const hr = Math.floor(min / 60);
  if (hr < 24)  return hr + (hr === 1 ? ' hour ago' : ' hours ago');
  const d = Math.floor(hr / 24);
  if (d < 30)   return d + (d === 1 ? ' day ago' : ' days ago');
  const mo = Math.floor(d / 30);
  return mo + (mo === 1 ? ' month ago' : ' months ago');
}

// Formats a stamp for display: "Jun 27, 2026, 4:02 AM (auto) · 3 days ago".
// Returns 'Not loaded' when no stamp exists.
function formatDataStamp(key) {
  const s = getDataStamp(key);
  if (!s) return 'Not loaded';
  const when = new Date(s.ts).toLocaleString([], {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
  const tag = s.src === 'repo' ? 'auto' : 'uploaded';
  return when + ' (' + tag + ') · ' + relativeAge(s.ts);
}

// ── PROSPECT PARSER ──────────────────────────────────────────────────────────
function parseProspectsCSV(text) {
  // Strip UTF-8 BOM and split into non-empty lines.
  var lines = text.replace(/^﻿/, '').split(/\r?\n/).filter(function(l) { return l.trim(); });

  // Find the header line by scanning for one that contains both Name and FV columns.
  // This handles FanGraphs' multi-line quoted first column header gracefully.
  var headerIdx = -1;
  for (var i = 0; i < Math.min(6, lines.length); i++) {
    if (lines[i].indexOf('Name') !== -1 && lines[i].indexOf('FV') !== -1) {
      headerIdx = i;
      break;
    }
  }
  if (headerIdx < 0) return [];

  // Detect delimiter from the first data row (not the header) so a manually
  // edited comma-separated header still works with tab-separated data rows.
  var firstData = lines[headerIdx + 1] || '';
  var delim = firstData.includes('\t') ? '\t' : ',';

  function splitLine(line) {
    return line.split(delim).map(function(c) { return c.trim().replace(/^"|"$/g, ''); });
  }

  var headers = splitLine(lines[headerIdx]);
  var idx = {};
  headers.forEach(function(h, i) { idx[h] = i; });

  if (idx['Name'] === undefined || idx['FV'] === undefined) return [];

  return lines.slice(headerIdx + 1).map(function(line) {
    var cols = splitLine(line);
    var name = cols[idx['Name']] || '';
    var fv   = parseInt(cols[idx['FV']]) || 0;
    if (!name || !fv) return null;
    var rankRaw = idx['Top 100'] !== undefined ? parseInt(cols[idx['Top 100']]) : NaN;
    return {
      name:    normalizeName(name),
      rawName: name,
      rank:    isNaN(rankRaw) ? null : rankRaw,
      orgRank: idx['Org Rk']       !== undefined ? (parseInt(cols[idx['Org Rk']])       || null) : null,
      org:     idx['Org']          !== undefined ? (cols[idx['Org']]          || '')              : '',
      pos:     idx['Pos']          !== undefined ? (cols[idx['Pos']]          || '')              : '',
      level:   idx['Current Level']!== undefined ? (cols[idx['Current Level']]|| '')              : '',
      eta:     idx['ETA']          !== undefined ? (cols[idx['ETA']]          || '')              : '',
      fv,
      risk:    idx['Risk']         !== undefined ? (cols[idx['Risk']]         || '')              : '',
      age:     idx['Age']          !== undefined ? (parseFloat(cols[idx['Age']]) || null)         : null,
    };
  }).filter(Boolean);
}

// ── SECURITY HELPER ──────────────────────────────────────────────────────────
// Escape user-supplied strings before inserting into innerHTML.
function esc(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── LOCAL STORAGE ────────────────────────────────────────────────────────────
function saveData(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function loadData(key) {
  const raw = localStorage.getItem(key);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch (e) { console.warn('loadData: bad JSON for key', key); return null; }
}

function clearAllData() {
  const dataKeys = [
    'ottoneu_roster',
    'ottoneu_proj_hitting',  'ottoneu_proj_pitching',
    'ottoneu_proj_hitting_y1', 'ottoneu_proj_pitching_y1',
    'ottoneu_proj_hitting_y2', 'ottoneu_proj_pitching_y2',
    'ottoneu_prospects',
    'ottoneu_curr_standings',
  ];
  dataKeys.forEach(k => {
    localStorage.removeItem(k);
    localStorage.removeItem(k + '_ts');
    localStorage.removeItem(k + '_src');
  });
  ['ottoneu_dynasty_weights', 'ottoneu_my_team'].forEach(k => localStorage.removeItem(k));
}

// ── CSV PARSING ──────────────────────────────────────────────────────────────
function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  // Auto-detect delimiter: tab-separated if first line contains a tab
  const delim = lines[0].includes('\t') ? '\t' : ',';
  const headers = parseCSVLine(lines[0], delim).map(h => h.trim().replace(/^"|"$/g, ''));
  return lines.slice(1)
    .filter(l => l.trim())
    .map(line => {
      const values = parseCSVLine(line, delim);
      const obj = {};
      headers.forEach((h, i) => { obj[h] = (values[i] || '').trim().replace(/^"|"$/g, ''); });
      return obj;
    });
}

function parseCSVLine(line, delim) {
  delim = delim || ',';
  // For tab-delimited files, split directly (tabs won't appear inside quoted fields in FanGraphs exports)
  if (delim === '\t') return line.split('\t');
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') { current += '"'; i++; }
      else inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      result.push(current); current = '';
    } else {
      current += ch;
    }
  }
  result.push(current);
  return result;
}

// ── ROSTER PARSER ────────────────────────────────────────────────────────────
// ⚠️ Verify these against your actual Ottoneu roster CSV export headers
const ROSTER_COLS = {
  fgId:      'FG MajorLeagueID',  // FanGraphs player ID — primary match key
  name:      'Name',
  positions: 'Position(s)',        // e.g. "SS/2B" or "OF" or "SP"
  salary:    'Salary',             // e.g. "$60"
  team:      'Team Name',          // fantasy team name
};

function parseRosterCSV(text) {
  return parseCSV(text).map(row => ({
    fgId:      (row[ROSTER_COLS.fgId]      || '').trim(),
    name:      normalizeName(row[ROSTER_COLS.name] || ''),
    rawName:   (row[ROSTER_COLS.name]      || '').trim(),
    positions: parsePositions(row[ROSTER_COLS.positions] || ''),
    salary:    parseSalary(row[ROSTER_COLS.salary]  || '0'),
    team:      (row[ROSTER_COLS.team]      || '').trim() || 'Free Agent',
    type:      inferPlayerType(row[ROSTER_COLS.positions] || ''),
  }));
}

function normalizeName(name) {
  return String(name).toLowerCase()
    .replace(/[àáâãäå]/g, 'a').replace(/[èéêë]/g, 'e')
    .replace(/[ìíîï]/g, 'i').replace(/[òóôõö]/g, 'o')
    .replace(/[ùúûü]/g, 'u').replace(/ñ/g, 'n')
    .replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
}

function parsePositions(posStr) {
  return String(posStr).toLowerCase().split(/[/,]/).map(p => p.trim()).filter(Boolean);
}

function parseSalary(str) {
  return parseFloat(String(str).replace(/[$,\s]/g, '')) || 0;
}

function inferPlayerType(posStr) {
  const tokens = String(posStr).toLowerCase().split(/[/,]/).map(p => p.trim());
  const hasPitching = tokens.some(p => p === 'sp' || p === 'rp' || p === 'p');
  const hasHitting  = tokens.some(p => ['c','1b','2b','ss','3b','of','dh','mi','ci','util'].includes(p));
  // Only classify as pitcher if there are NO hitting positions.
  // Players like "1b/of/rp" are hitters who occasionally pitch — treat as 'H'.
  return hasPitching && !hasHitting ? 'P' : 'H';
}

// ── PROJECTION PARSERS ───────────────────────────────────────────────────────
// ⚠️ Verify these against your actual FanGraphs projection CSV headers
// Actual FanGraphs projection export headers (tab-separated):
// Hitting:  #  Name  Team  G  PA  AB  H  HR  R  BB  HBP  OBP  SLG  wOBA  wRC+  ADP
// Pitching: #  Name  Team  GS  G  IP  ER  HR  SO  BB  HR/9  WHIP  ERA  ADP
const HITTING_PROJ_COLS = {
  fgId: 'fgId',
  name: 'Name', team: 'Team',
  pa: 'PA', ab: 'AB', h: 'H', bb: 'BB', hbp: 'HBP',
  hr: 'HR', r: 'R', obp: 'OBP', slg: 'SLG',
};

const PITCHING_PROJ_COLS = {
  fgId: 'fgId',
  name: 'Name', team: 'Team',
  ip: 'IP', bb: 'BB', hr: 'HR', so: 'SO',
  era: 'ERA', whip: 'WHIP', hr9: 'HR/9',
};

function parseHittingProjections(text) {
  return parseCSV(text)
    .filter(row => parseFloat(row[HITTING_PROJ_COLS.pa]) > 0)
    .map(row => {
      const n  = k => parseFloat(row[HITTING_PROJ_COLS[k]]) || 0;
      const pa = n('pa');
      const regW = pa + REGRESS_PA;
      return {
        fgId:    (row[HITTING_PROJ_COLS.fgId] || '').trim(),
        name:    normalizeName(row[HITTING_PROJ_COLS.name] || ''),
        rawName: (row[HITTING_PROJ_COLS.name] || '').trim(),
        type:    'H',
        proj: {
          pa, ab: n('ab'), h: n('h'),
          bb: n('bb'), hbp: n('hbp'),
          hr: n('hr'), r: n('r'),
          obp: (pa * n('obp') + REGRESS_PA * LG_MEAN.OBP) / regW,
          slg: (pa * n('slg') + REGRESS_PA * LG_MEAN.SLG) / regW,
        },
      };
    });
}

function parsePitchingProjections(text) {
  return parseCSV(text)
    .filter(row => parseFloat(row[PITCHING_PROJ_COLS.ip]) > 0)
    .map(row => {
      const n   = k => parseFloat(row[PITCHING_PROJ_COLS[k]]) || 0;
      const ip  = n('ip');
      const hr  = n('hr');
      const gs  = parseFloat(row['GS']) || 0;
      const g   = parseFloat(row['G'])  || 0;
      const role = (g > 0 && gs / g >= 0.4) ? 'SP' : 'RP';

      const hr9col  = parseFloat(row[PITCHING_PROJ_COLS.hr9]) || 0;
      const rawHR9  = hr9col > 0 ? hr9col : (ip > 0 ? hr * 9 / ip : 0);
      const rawERA  = n('era');
      const rawWHIP = n('whip');

      const regW = ip + REGRESS_IP;
      const era  = ip > 0 ? (ip * rawERA  + REGRESS_IP * LG_MEAN.ERA)  / regW : 0;
      const whip = ip > 0 ? (ip * rawWHIP + REGRESS_IP * LG_MEAN.WHIP) / regW : 0;
      const hr9  = ip > 0 ? (ip * rawHR9  + REGRESS_IP * LG_MEAN.HR9)  / regW : 0;

      return {
        fgId:    (row[PITCHING_PROJ_COLS.fgId] || '').trim(),
        name:    normalizeName(row[PITCHING_PROJ_COLS.name] || ''),
        rawName: (row[PITCHING_PROJ_COLS.name] || '').trim(),
        type:    'P',
        proj: {
          ip, hr, hr9, h: n('h'), bb: n('bb'), so: n('so'),
          era, whip, role,
          er: ip > 0 ? era * ip / 9 : 0,
        },
      };
    });
}

// ── PLAYER MATCHING ──────────────────────────────────────────────────────────
// Merges roster players with their projections.
// Match priority: FanGraphs ID → normalized name.
function matchPlayers(rosterPlayers, hittingProj, pitchingProj) {
  // Type-separated ID and name lookups.
  // Keeping hitting and pitching separate prevents two-way players (Ohtani) or
  // name collisions (minor-league pitcher "Juan Soto") from clobbering the wrong
  // projection when both files share the same playerid or name.
  const projByIdH = {};
  const projByIdP = {};
  const projByNameH = {};
  const projByNameP = {};
  (hittingProj  || []).forEach(p => {
    if (p.fgId) projByIdH[p.fgId] = p;
    if (p.name)  projByNameH[p.name]  = p;
  });
  (pitchingProj || []).forEach(p => {
    if (p.fgId) projByIdP[p.fgId] = p;
    if (p.name)  projByNameP[p.name]  = p;
  });

  const matched = rosterPlayers.map(rp => {
    // 1. Type-aware ID match (most reliable)
    const idLookup = rp.type === 'P' ? projByIdP : projByIdH;
    let projMatch = (rp.fgId && idLookup[rp.fgId]) || null;
    // 2. Type-aware name match fallback
    if (!projMatch) {
      projMatch = rp.type === 'P' ? projByNameP[rp.name] : projByNameH[rp.name];
    }

    // 3. Two-way check: a type='H' player with pitching eligibility (SP/RP) who
    //    also has a meaningful pitching projection is a genuine two-way player.
    //    Attach projP so the SGP loop can add their pitching value on top.
    //    TWO_WAY_IP_MIN filters out position players who pitched once in a blowout.
    let projP = null;
    if (rp.type === 'H') {
      const hasPitchPos = (rp.positions || []).some(p => p === 'sp' || p === 'rp' || p === 'p');
      if (hasPitchPos) {
        const ppMatch = (rp.fgId && projByIdP[rp.fgId]) || projByNameP[rp.name] || null;
        if (ppMatch && ppMatch.proj && (ppMatch.proj.ip || 0) >= TWO_WAY_IP_MIN) {
          projP = ppMatch.proj;
        }
      }
    }

    return { ...rp, proj: projMatch ? projMatch.proj : null, projP };
  });
  const hMatched = matched.filter(p => p.type === 'H' && p.proj).length;
  const pMatched = matched.filter(p => p.type === 'P' && p.proj).length;
  const hTotal   = matched.filter(p => p.type === 'H').length;
  const pTotal   = matched.filter(p => p.type === 'P').length;
  console.log('[matchPlayers] hitters:', hMatched + '/' + hTotal, '| pitchers:', pMatched + '/' + pTotal);
  // Snapshot rostered identity for all future baseline computations (see
  // ROSTERED_IDS comment). Captured here because matchPlayers is the one
  // place every page passes the true league roster.
  ROSTERED_IDS   = new Set(rosterPlayers.map(p => p.fgId).filter(Boolean));
  ROSTERED_NAMES = new Set(rosterPlayers.map(p => p.name));
  computeFABaselines(hittingProj, pitchingProj, rosterPlayers, 'proj');
  return matched;
}

// Players in projection CSVs not assigned to any rostered team = free agents.
function getFreeAgents(hittingProj, pitchingProj, rosterPlayers) {
  const rosteredIds   = new Set(rosterPlayers.map(p => p.fgId).filter(Boolean));
  const rosteredNames = new Set(rosterPlayers.map(p => p.name));
  return [...(hittingProj || []), ...(pitchingProj || [])].filter(p =>
    !rosteredIds.has(p.fgId) && !rosteredNames.has(p.name)
  ).map(p => ({
    ...p,
    positions: [],
    salary:    0,
    team:      'Free Agent',
    stats:     null,
  }));
}

// ── FA REPLACEMENT BASELINES ─────────────────────────────────────────────────
// Replacement level = the best freely available alternative. For each player
// type we average the stats of the top free-agent cohort (best unrostered
// players with a real projected MLB role). Stored per projection year
// ('proj', 'proj_y1', 'proj_y2') so dynasty valuations use that year's FA pool.
const FA_COHORT_H = 8;    // hitters averaged into the baseline
const FA_COHORT_P = 10;   // pitchers averaged into the baseline
const FA_MIN_PA   = 100;  // role floors: excludes stashed prospects / injured
const FA_MIN_IP   = 30;   // players with elite rates but no MLB playing time

let FA_BASELINES = {};    // { proj: {H,P}, proj_y1: {H,P}, proj_y2: {H,P} }

// Rostered-identity snapshot, captured ONCE by matchPlayers. Baselines must
// always be computed against the league's actual rosters — NOT against
// whatever array happens to be passed to attachYearProjections. Without this,
// attaching year projections to a FREE-AGENT pool (bid.html) redefined "the
// roster" as the FA pool, making the "FA baseline" the league's rostered
// stars: replacement ERA 4.12 → 3.18, which collapsed most pitchers' SGP and
// concentrated the entire Y1/Y2 pitching pool on a few elite relievers
// (Muñoz dynasty $236 instead of ~$70).
let ROSTERED_IDS   = null;   // Set of fgIds
let ROSTERED_NAMES = null;   // Set of normalized names

function computeFABaselines(hittingProj, pitchingProj, rosterPlayers, yearKey) {
  const rosteredIds   = ROSTERED_IDS   || new Set(rosterPlayers.map(p => p.fgId).filter(Boolean));
  const rosteredNames = ROSTERED_NAMES || new Set(rosterPlayers.map(p => p.name));
  const isFA = p => !(p.fgId && rosteredIds.has(p.fgId)) && !rosteredNames.has(p.name);

  const faH = (hittingProj || [])
    .filter(p => isFA(p) && p.proj && (p.proj.pa || 0) >= FA_MIN_PA)
    .sort((a, b) => valProxy({ type: 'H' }, b.proj) - valProxy({ type: 'H' }, a.proj))
    .slice(0, FA_COHORT_H);
  const faP = (pitchingProj || [])
    .filter(p => isFA(p) && p.proj && (p.proj.ip || 0) >= FA_MIN_IP)
    .sort((a, b) => valProxy({ type: 'P' }, b.proj) - valProxy({ type: 'P' }, a.proj))
    .slice(0, FA_COHORT_P);

  FA_BASELINES[yearKey] = {
    H: avgCohortStats(faH.map(p => p.proj), ['pa', 'hr', 'r', 'obp', 'slg']),
    P: avgCohortStats(faP.map(p => p.proj), ['ip', 'so', 'era', 'whip', 'hr9']),
  };
}

// Averages each stat across a cohort. Returns null if the cohort is too thin
// to be a trustworthy baseline (callers fall back to roster-based replacement).
function avgCohortStats(projs, fields) {
  if (projs.length < 3) return null;
  const out = {};
  fields.forEach(f => {
    out[f] = projs.reduce((s, b) => s + (b[f] || 0), 0) / projs.length;
  });
  return out;
}

// Attaches a future-year projection to already-matched roster players.
// projKey: 'proj_y1' or 'proj_y2'. Matched by normalized name only
// (projection CSVs have no player ID column).
function attachYearProjections(matchedPlayers, hittingProj, pitchingProj, projKey) {
  if (!hittingProj && !pitchingProj) return matchedPlayers;
  computeFABaselines(hittingProj, pitchingProj, matchedPlayers, projKey);
  // Type-separated lookups — same reason as matchPlayers: prevents Ohtani's
  // pitching projection from overwriting his hitting projection for the same name.
  const byNameH = {};
  const byNameP = {};
  (hittingProj  || []).forEach(p => { if (p.name) byNameH[p.name] = p.proj; });
  (pitchingProj || []).forEach(p => { if (p.name) byNameP[p.name] = p.proj; });

  return matchedPlayers.map(p => {
    const yearProj = p.type === 'P' ? byNameP[p.name] : byNameH[p.name];
    const result = { ...p, [projKey]: yearProj || null };
    // Two-way players: also store the year-specific pitching projection so
    // cloneForYear can set projP correctly for that year's valuation pass.
    if (p.type === 'H' && p.projP !== undefined) {
      const yearPitchProj = byNameP[p.name];
      result[projKey + '_P'] = (yearPitchProj && (yearPitchProj.ip || 0) >= TWO_WAY_IP_MIN)
        ? yearPitchProj : null;
    }
    return result;
  });
}

// Computes dynasty value by running the SGP model across up to three projection
// years and combining with weighted discounting.
// weights: { y1: 0.90, y2: 0.81 }  (defaults; pass null to use Y0 only)
// Players with no Y1/Y2 projection simply contribute 0 for that year.
function calculateDynastyValues(allRosters, weights, extraPlayers) {
  const w1 = weights ? (weights.y1 || 0) : 0;
  const w2 = weights ? (weights.y2 || 0) : 0;

  // Helper: clone rosters swapping proj → a different year's projection.
  // fbKey (optional) is a fallback year used when the primary year is missing:
  // Y2 projection files cover only ~half the league (almost no pitchers), so a
  // player with a Y1 line but no Y2 line reuses Y1 — the w2 weight already
  // discounts it. Without this, every ace contributed $0 for Y2 AND the fixed
  // pool spread over half as many players, inflating everyone who remained.
  // Also forward projP from the year-specific pitching field so two-way players
  // (Ohtani) get the correct pitching projection for each dynasty year, not Y0's.
  function yearProjP(p, yearKey, fbKey) {
    if (p[yearKey + '_P'] != null) return p[yearKey + '_P'];
    if (fbKey && p[fbKey + '_P'] != null) return p[fbKey + '_P'];
    return p[yearKey + '_P'] !== undefined ? p[yearKey + '_P'] : p.projP;
  }
  function cloneForYear(rosters, yearKey, fbKey) {
    return rosters.map(r => r.map(p => ({
      ...p,
      proj:  p[yearKey] || (fbKey ? p[fbKey] : null) || null,
      projP: yearProjP(p, yearKey, fbKey),
    })));
  }
  function cloneExtras(extras, yearKey, fbKey) {
    return extras ? extras.map(p => ({
      ...p,
      proj:  p[yearKey] || (fbKey ? p[fbKey] : null) || null,
      projP: yearProjP(p, yearKey, fbKey),
    })) : null;
  }

  // Y0 — always run
  const vmY0 = calculateAllValues(allRosters, extraPlayers);

  // Y1 — run only if any player actually has proj_y1 data.
  // Pass the year key so replacement level comes from that year's FA baseline.
  const hasY1 = w1 > 0 && allRosters.flat().some(p => p.proj_y1);
  const vmY1 = hasY1
    ? calculateAllValues(cloneForYear(allRosters, 'proj_y1'), cloneExtras(extraPlayers, 'proj_y1'), true, 'proj_y1')
    : null;

  // Y2 — runs whenever Y1 or Y2 data exists (Y1 lines back-fill missing Y2)
  const hasY2 = w2 > 0 && allRosters.flat().some(p => p.proj_y2 || p.proj_y1);
  const vmY2 = hasY2
    ? calculateAllValues(cloneForYear(allRosters, 'proj_y2', 'proj_y1'), cloneExtras(extraPlayers, 'proj_y2', 'proj_y1'), true, 'proj_y2')
    : null;

  // Dynasty salary cost: apply the same discount weights to salary as to value.
  // Salary is paid each year, so total cost in present-value terms mirrors the
  // same discount logic: cost = salary × (1 + w1 + w2).
  // This keeps surplus meaningful — a player at $10 with default weights costs
  // $27.10 in dynasty terms, not $10.
  const salaryMultiplier = 1 + w1 + w2;

  // Prospect dynasty floors. Projection systems can't see players far from the
  // majors (no Y0/Y1/Y2 lines), so without this an FV-65 teenager values at ~$3
  // and the trade finder's rebuilder lens treats him as a throw-in. The floor is
  // computed from scouting data (Top-100 rank, FV, position, risk) — see
  // prospectDynastyValue.
  const keyToProspect = {};
  const prospectList = (typeof loadData === 'function' && loadData('ottoneu_prospects')) || [];
  if (prospectList.length) {
    const prByName = {};
    prospectList.forEach(pr => { if (pr.name && pr.fv) prByName[pr.name] = pr; });
    const collect = p => {
      const pr = prByName[p.name];
      if (pr) keyToProspect[p.fgId || p.name] = pr;
    };
    allRosters.flat().forEach(collect);
    (extraPlayers || []).forEach(collect);
  }

  // Merge into a single map: all Y0 keys, enriched with dynasty values.
  const dynastyMap = {};
  Object.keys(vmY0).forEach(key => {
    const v0 = vmY0[key] || {};
    const v1 = vmY1 ? (vmY1[key] || {}) : {};
    const v2 = vmY2 ? (vmY2[key] || {}) : {};
    const currentValue = v0.projectedValue || 0;
    let dynastyValue = currentValue
      + w1 * (v1.projectedValue || 0)
      + w2 * (v2.projectedValue || 0);
    const floor = prospectDynastyValue(keyToProspect[key]);
    if (floor > dynastyValue) dynastyValue = floor;
    const s0 = Math.max(1, v0.actualSalary || 0);
    const dynastyCost = s0 + w1 * Math.max(1, s0 + 2) + w2 * Math.max(1, s0 + 4);
    dynastyMap[key] = {
      ...v0,
      dynastyValue,
      dynastySurplus: dynastyValue - dynastyCost,
    };
  });
  return dynastyMap;
}

// ── PROSPECT DYNASTY VALUATION ───────────────────────────────────────────────
// Expected dynasty $ for a prospect from scouting data, used as a floor under
// the projection-based model. Shape follows public surplus-value research
// (FanGraphs): Top-100 rank is the best granular signal (it already encodes
// proximity, upside, and risk beyond the coarse FV bucket); same-FV pitching
// prospects return ~30% less than hitters; the Risk grade tweaks expected value.
// All anchors tunable. Treat output as EV for trade math, not precision.

// Top-100 rank → $ anchors, interpolated. (#1 elite ≈ what a top rebuilder
// return actually costs; tail of the 100 ≈ solid-prospect price.)
const PROSPECT_RANK_CURVE = [[1, 62], [5, 50], [10, 44], [25, 33], [50, 24], [100, 15]];
// Unranked prospects fall back to their FV grade.
const FV_DYNASTY_FLOORS = [[45, 4], [50, 8], [55, 14], [60, 22], [65, 32], [70, 42], [80, 55]];

function interpAnchors(x, anchors) {
  if (x <= anchors[0][0]) return anchors[0][1];
  for (let i = 0; i < anchors.length - 1; i++) {
    const [x0, y0] = anchors[i], [x1, y1] = anchors[i + 1];
    if (x <= x1) return y0 + (y1 - y0) * (x - x0) / (x1 - x0);
  }
  return anchors[anchors.length - 1][1];
}

function fvDynastyFloor(fv) {
  if (!fv || fv < FV_DYNASTY_FLOORS[0][0]) return 0;
  return interpAnchors(fv, FV_DYNASTY_FLOORS);
}

function prospectDynastyValue(pr) {
  if (!pr || !pr.fv) return 0;
  // Base: Top-100 rank curve when ranked, FV grade otherwise. A ranked prospect
  // never values below his FV floor (guards against a stale rank column).
  let base = pr.rank
    ? Math.max(interpAnchors(pr.rank, PROSPECT_RANK_CURVE), fvDynastyFloor(pr.fv) * 0.85)
    : fvDynastyFloor(pr.fv);
  // Pitching prospects bust more often (TINSTAAPP): same-FV arms return less.
  // Every pitcher tag (SP, RP, SIRP, MIRP, LHP, RHP) contains 'P'; no hitter tag does.
  const pos = String(pr.pos || '').toUpperCase();
  if (pos.indexOf('P') !== -1) base *= 0.72;
  // Scout-assigned variance: high risk trims EV, low risk firms it up.
  const risk = String(pr.risk || '').toLowerCase();
  if (risk === 'high' || risk === 'extreme') base *= 0.85;
  else if (risk === 'low') base *= 1.12;
  return base;
}

// ── LINEUP OPTIMIZER ────────────────────────────────────────────────────────
const HITTER_SLOTS = [
  { id: 'C',    eligible: p => p.positions.includes('c') },
  { id: '1B',   eligible: p => p.positions.includes('1b') },
  { id: '2B',   eligible: p => p.positions.includes('2b') },
  { id: 'SS',   eligible: p => p.positions.includes('ss') },
  { id: '3B',   eligible: p => p.positions.includes('3b') },
  { id: 'MI',   eligible: p => p.positions.some(pos => pos === '2b' || pos === 'ss') },
  { id: 'OF1',  eligible: p => p.positions.includes('of') },
  { id: 'OF2',  eligible: p => p.positions.includes('of') },
  { id: 'OF3',  eligible: p => p.positions.includes('of') },
  { id: 'OF4',  eligible: p => p.positions.includes('of') },
  { id: 'OF5',  eligible: p => p.positions.includes('of') },
  { id: 'UTIL', eligible: p => p.type === 'H' },
];

// Assigns hitters to slots. Returns { slotId: player } map.
function optimizeHitterLineup(hitters) {
  const scored = hitters
    .filter(p => p.type === 'H')
    .map(p => {
      const b = p.proj || {};
      return { ...p, _proj: b, _value: (b.pa || 0) * ((b.obp || 0) + (b.slg || 0)) };
    })
    .sort((a, b) => b._value - a._value);

  const slots = [...HITTER_SLOTS].sort((a, b) =>
    scored.filter(p => a.eligible(p)).length - scored.filter(p => b.eligible(p)).length
  );

  const assignment = {};
  const used = new Set();
  for (const slot of slots) {
    const best = scored.find(p => slot.eligible(p) && !used.has(p.fgId || p.name));
    if (best) {
      assignment[slot.id] = best;
      used.add(best.fgId || best.name);
    }
  }
  return assignment;
}

// Selects pitchers ranked by value up to an innings budget (default: the full
// 1500 IP_MAX). Pass a smaller budget for rest-of-season valuation so team SO
// totals reflect the innings the league cap actually allows — otherwise teams
// hoarding arms show wildly different IP, inflating the SO stdev and making
// strikeout production look nearly worthless in SGP terms.
function selectPitchers(pitchers, ipBudget) {
  const budget = ipBudget || IP_MAX;
  const minIP  = Math.min(IP_MIN, budget * 0.5);
  const scored = pitchers
    .filter(p => p.type === 'P')
    .map(p => {
      const b        = p.proj || {};
      const safeERA  = (b.era  || 0) > 0 ? b.era  : 99;
      const safeWHIP = (b.whip || 0) > 0 ? b.whip : 9;
      return { ...p, _proj: b, _value: (b.ip || 0) * (1 / safeERA + 1 / safeWHIP + (b.so || 0) / 100) };
    })
    .sort((a, b) => b._value - a._value);

  const selected = [];
  let totalIP = 0;
  for (const p of scored) {
    const ip = (p._proj && p._proj.ip) || 0;
    if (totalIP + ip <= budget) { selected.push(p); totalIP += ip; }
  }
  return totalIP >= minIP ? selected : [];
}

// ── SCORING ENGINE ───────────────────────────────────────────────────────────
// Computes 8 category totals for one team from their lineup and pitcher pool.
// minValidIP (optional) overrides the IP_MIN validity floor — used when the
// pitcher pool was selected under a prorated rest-of-season innings budget.
function computeTeamStats(hitterAssignment, selectedPitchers, minValidIP) {
  const hitters  = Object.values(hitterAssignment || {}).filter(Boolean);
  const pitchers = selectedPitchers || [];
  const ipFloor  = minValidIP || IP_MIN;

  let totPA = 0, totAB = 0, totOBPNum = 0, totSLGNum = 0, totHR = 0, totR = 0;
  for (const p of hitters) {
    const b = p._proj || p.proj || {};
    totPA     += b.pa  || 0;
    totAB     += b.ab  || 0;
    totOBPNum += (b.pa || 0) * (b.obp || 0);
    totSLGNum += (b.ab || 0) * (b.slg || 0);
    totHR     += b.hr  || 0;
    totR      += b.r   || 0;
  }

  let totIP = 0, totERNum = 0, totWHIPNum = 0, totHR9Num = 0, totSO = 0;
  for (const p of pitchers) {
    const b = p._proj || p.proj || {};
    const ip = b.ip || 0;
    totIP      += ip;
    totERNum   += ip * (b.era  || 0) / 9;
    totWHIPNum += ip * (b.whip || 0);
    totHR9Num  += ip * (b.hr9  || 0) / 9;
    totSO      += b.so || 0;
  }

  const pitOk = totIP >= ipFloor;
  return {
    OBP:  totPA > 0 ? totOBPNum / totPA  : 0,
    SLG:  totAB > 0 ? totSLGNum / totAB  : 0,
    HR:   totHR,
    R:    totR,
    ERA:  pitOk && totIP > 0 ? totERNum  * 9 / totIP : 0,
    WHIP: pitOk && totIP > 0 ? totWHIPNum  / totIP   : 0,
    HR9:  pitOk && totIP > 0 ? totHR9Num * 9 / totIP : 0,
    SO:   pitOk ? totSO : 0,
    _ip:           totIP,
    _totPA:        totPA,
    _totAB:        totAB,
    _pitchingValid: pitOk,
  };
}

// ── CURRENT STANDINGS PARSER ─────────────────────────────────────────────────
// Parses the user's current-standings CSV (Team,Games,R,HR,OBP,SLG,IP,K,HR/9,ERA,WHIP).
// IP is in baseball ⅓-inning notation: 357.2 = 357⅔ innings.
function parseIPInnings(s) {
  const f     = parseFloat(s) || 0;
  const whole = Math.floor(f);
  const outs  = Math.round((f - whole) * 10);  // 0, 1, or 2
  return whole + outs / 3;
}

function parseCurrStandings(text) {
  return parseCSV(text).map(row => ({
    name:  (row['Team'] || '').trim(),
    games: parseFloat(row['Games']) || 0,
    r:     parseFloat(row['R'])     || 0,
    hr:    parseFloat(row['HR'])    || 0,
    obp:   parseFloat(row['OBP'])   || 0,
    slg:   parseFloat(row['SLG'])   || 0,
    ip:    parseIPInnings(row['IP']),
    k:     parseFloat(row['K'])     || 0,
    hr9:   parseFloat(row['HR/9'])  || 0,
    era:   parseFloat(row['ERA'])   || 0,
    whip:  parseFloat(row['WHIP'])  || 0,
  })).filter(r => r.name);
}

// ── REST-OF-SEASON BLENDER ────────────────────────────────────────────────────
// Combines current actual stats with projected remaining stats.
//
// curr  — one row from parseCurrStandings (season-to-date actuals)
// proj  — result of computeTeamStats over CURRENT roster
//
// IMPORTANT: projections are Steamer REST-OF-SEASON (steamerr), so proj.* already
// represents the *remaining* production, not the full season. Therefore:
//   - Counting stats (HR, R, SO): full season = current actuals + RoS projection.
//   - Rate stats (OBP, SLG, ERA, WHIP, HR9): weighted average of current and
//     remaining. (Earlier code treated proj as full-season and subtracted current
//     from it, which gutted counting stats — esp. strikeouts.)
// Pitching also respects the league innings cap: a team rosters more arms than it
// can use, so only innings up to (IP_MAX − innings already thrown) count toward
// the rest of season. Hitting has no analogous over-roster problem (one hitter
// per active slot), so its RoS projection is added directly.
function blendStats(curr, proj) {
  const f = Math.min(1, Math.max(0, (curr.games || 0) / 162));  // season elapsed
  const g = 1 - f;                                              // season remaining

  // ── Hitting: counting = actual + RoS; rates blended by season fraction ──────
  const hr  = curr.hr + proj.HR;
  const r   = curr.r  + proj.R;
  const obp = curr.obp * f + proj.OBP * g;
  const slg = curr.slg * f + proj.SLG * g;

  // ── Pitching: cap remaining innings at the league budget (IP_MAX − thrown) ──
  const currIP  = curr.ip || 0;
  const projIP  = proj._ip || 0;
  const remIP   = Math.min(projIP, Math.max(0, IP_MAX - currIP));
  const ipScale = projIP > 0 ? remIP / projIP : 0;          // throttle RoS counting
  const totalIP = currIP + remIP;
  const wCur    = totalIP > 0 ? currIP / totalIP : 0;
  const wRem    = totalIP > 0 ? remIP  / totalIP : 1;

  const so   = curr.k + proj.SO * ipScale;
  const era  = curr.era  * wCur + proj.ERA  * wRem;
  const whip = curr.whip * wCur + proj.WHIP * wRem;
  const hr9  = curr.hr9  * wCur + proj.HR9  * wRem;

  return {
    OBP: obp, SLG: slg, HR: hr, R: r,
    ERA: era, WHIP: whip, HR9: hr9, SO: so,
    _ip: totalIP,
    _totPA: (proj._totPA || 0),
    _pitchingValid: proj._pitchingValid,
  };
}

// Ranks 12 teams 12→1 per category. Returns teams sorted by total points desc.
function buildStandings(teams) {
  const n      = teams.length;
  const ranked = teams.map(t => ({ ...t, points: 0, ranks: {} }));
  for (const cat of CATS) {
    const sorted = [...ranked].sort((a, b) => {
      const av = a.stats[cat] || 0, bv = b.stats[cat] || 0;
      return LOWER_BETTER.has(cat) ? av - bv : bv - av;
    });
    sorted.forEach((team, idx) => {
      const pts       = n - idx;
      team.ranks[cat] = pts;
      team.points    += pts;
    });
  }
  return ranked.sort((a, b) => b.points - a.points);
}

// ── VALUATION MODEL ──────────────────────────────────────────────────────────
// Calculates dollar value per player using position-specific replacement level
// and SGP (standings gain points) denominators derived from projected standings.
//
// allTeamRosters: array of 12 arrays of matched player objects
// ilDesignations: array of { fgId, name, type }
// Returns: object keyed by player fgId-or-name →
//   { projectedValue, actualSalary, surplus, sgp }

// extraPlayers: optional array of FA players to value using the same rates.
// They do NOT affect replacement levels or total SGP — keeping existing values calibrated.
function calculateAllValues(allTeamRosters, extraPlayers, quiet, yearKey) {
  // Innings budget for team-stat aggregation. Y0 uses rest-of-season
  // projections, so each team can only add innings up to the league cap's
  // remaining share (calendar-prorated). Y1/Y2 files are full-season → full cap.
  const isFutureYear = yearKey && yearKey !== 'proj';
  const ipBudget = isFutureYear ? IP_MAX : IP_MAX * Math.max(rosProrationFactor(), 0.1);

  // 1. Optimize lineup for each team
  const teamLineups = allTeamRosters.map(roster => {
    const hitters  = roster.filter(p => p.type === 'H');
    const pitchers = roster.filter(p => p.type === 'P');
    const lineup   = optimizeHitterLineup(hitters);
    const pitPool  = selectPitchers(pitchers, ipBudget);
    const stats    = computeTeamStats(lineup, pitPool, Math.min(IP_MIN, ipBudget * 0.5));
    return { lineup, pitPool, stats, roster };
  });

  // 2. SGP denominators from stdev of each category across all teams
  const sgpDenom = calcSGPDenoms(teamLineups.map(t => t.stats));

  // 3. Average team PA and IP (for rate-stat normalization)
  const avgPA = teamLineups.reduce((s, t) =>
    s + Object.values(t.lineup).filter(Boolean)
      .reduce((sp, p) => sp + ((p._proj && p._proj.pa) || (p.proj && p.proj.pa) || 0), 0), 0) / NUM_TEAMS;
  const avgIP = teamLineups.reduce((s, t) =>
    s + t.pitPool.reduce((sp, p) => sp + ((p._proj && p._proj.ip) || (p.proj && p.proj.ip) || 0), 0), 0) / NUM_TEAMS;

  // 4. Replacement level = best freely available alternative (FA baseline)
  const replLevels = calcReplacementLevels(allTeamRosters, yearKey);

  // Starters: players whose production actually reaches the field (active
  // lineup slots / capped innings). The hit-vs-pitch dollar split is computed
  // from THEIR SGP only — bench bats and surplus arms are still valued at the
  // resulting rates, but they don't tilt the split, since rosters hold far more
  // pitching volume than the innings cap lets teams use.
  const starterKeys = new Set();
  teamLineups.forEach(t => {
    Object.values(t.lineup).filter(Boolean).forEach(p => starterKeys.add(p.fgId || p.name));
    t.pitPool.forEach(p => starterKeys.add(p.fgId || p.name));
  });

  // 5. SGP per player — split into hitting and pitching pools
  const valueMap = {};
  const entries  = [];   // every rostered player with a projection
  let totalHitSGP = 0;   // all positive SGP (rate denominators — conserves the pool)
  let totalPitSGP = 0;
  let starterHitSGP = 0; // starters only (drives the hit/pitch dollar split)
  let starterPitSGP = 0;

  allTeamRosters.flat().forEach(player => {
    const key = player.fgId || player.name;
    if (valueMap[key]) return;
    const b = player.proj;

    if (!b) {
      if (!quiet) console.warn('[Ottoneu] No projection matched for:', player.rawName || player.name,
        '(salary $' + (player.salary || 0) + ', pos ' + (player.positions || []).join('/') + ')');
      valueMap[key] = { sgp: 0, noProj: true, actualSalary: player.salary || 0, surplus: -(player.salary || 0) };
      return;
    }

    const repl = replLevels[player.type === 'P' ? 'P' : 'H'];
    if (!repl) {
      valueMap[key] = { sgp: 0, actualSalary: player.salary || 0, surplus: -(player.salary || 0) };
      return;
    }
    let sgp = calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP);

    // Two-way players: add pitching SGP on top of hitting SGP.
    // Since hitRate === pitRate by construction (both = distributable / totalSGP),
    // adding pitching SGP directly to the hitting pool produces the correct value.
    if (player.type === 'H' && player.projP && replLevels.P) {
      const pitSGP = calcPlayerSGP({ ...player, type: 'P' }, player.projP, replLevels.P, sgpDenom, avgPA, avgIP);
      if (pitSGP > 0) sgp += pitSGP;
    }

    valueMap[key] = { sgp, actualSalary: player.salary || 0 };
    entries.push({ key, sgp, type: player.type });
    if (sgp > 0) {
      if (player.type === 'H') totalHitSGP += sgp;
      else                     totalPitSGP += sgp;
      if (starterKeys.has(key)) {
        if (player.type === 'H') starterHitSGP += sgp;
        else                     starterPitSGP += sgp;
      }
    }
  });

  // 6. Dollar normalization. Reserve $1 per rostered player (a roster spot is
  // never worth less than the league-minimum salary), then distribute the rest
  // proportional to SGP, split between hitting/pitching pools by SGP share.
  const reserved      = entries.length;            // $1 × rostered players
  const distributable = Math.max(0, SALARY_POOL - reserved);
  const starterSGP = starterHitSGP + starterPitSGP;
  const dynamicHitShare = starterSGP > 0 ? starterHitSGP / starterSGP
    : (totalHitSGP + totalPitSGP > 0 ? totalHitSGP / (totalHitSGP + totalPitSGP) : 0.60);
  const hitDollars = distributable * dynamicHitShare;
  const pitDollars = distributable * (1 - dynamicHitShare);

  const hitRate = totalHitSGP > 0 ? hitDollars / totalHitSGP : 0;
  const pitRate = totalPitSGP > 0 ? pitDollars / totalPitSGP : 0;
  if (!quiet) console.log('[values] hitShare:', (dynamicHitShare*100).toFixed(1)+'%',
    '| hitRate: $'+hitRate.toFixed(2)+'/SGP | pitRate: $'+pitRate.toFixed(2)+'/SGP',
    '| replH PA:', Math.round(replLevels.H && replLevels.H.pa || 0),
    'HR:', Math.round(replLevels.H && replLevels.H.hr || 0),
    'OBP:', (replLevels.H && replLevels.H.obp || 0).toFixed(3),
    '| replP IP:', Math.round(replLevels.P && replLevels.P.ip || 0),
    'ERA:', (replLevels.P && replLevels.P.era || 0).toFixed(2),
    'WHIP:', (replLevels.P && replLevels.P.whip || 0).toFixed(3),
    'SO:', Math.round(replLevels.P && replLevels.P.so || 0));

  entries.forEach(({ key, sgp, type }) => {
    const rate = type === 'P' ? pitRate : hitRate;
    const val  = 1 + Math.max(0, sgp) * rate;   // $1 floor for every rostered player
    valueMap[key].projectedValue = val;
    valueMap[key].surplus = val - (valueMap[key].actualSalary || 0);
  });

  // Value extra (FA) players using the same $/SGP rates without affecting denominators.
  if (extraPlayers && extraPlayers.length) {
    extraPlayers.forEach(player => {
      const key = player.fgId || player.name;
      if (valueMap[key]) return;
      const b = player.proj;
      if (!b) {
        valueMap[key] = { noProj: true, projectedValue: 0, actualSalary: 0, surplus: 0 };
        return;
      }
      const repl = replLevels[player.type === 'P' ? 'P' : 'H'];
      if (!repl) { valueMap[key] = { projectedValue: 0, sgp: 0, actualSalary: 0, surplus: 0 }; return; }
      const sgp  = calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP);
      const rate = player.type === 'P' ? pitRate : hitRate;
      // No $1 roster floor for free agents — they don't hold a roster spot.
      const projectedValue = Math.max(0, sgp * rate);
      valueMap[key] = { sgp, projectedValue, actualSalary: 0, surplus: projectedValue };
    });
  }

  return valueMap;
}

function calcSGPDenoms(teamStatsArr) {
  const result = {};
  CATS.forEach(cat => {
    const vals = teamStatsArr.map(s => s[cat] || 0).filter(v => v > 0);
    result[cat] = vals.length > 1 ? stdev(vals) : 1;
  });
  return result;
}

function stdev(values) {
  const mean = values.reduce((s, v) => s + v, 0) / values.length;
  return Math.sqrt(values.reduce((s, v) => s + Math.pow(v - mean, 2), 0) / values.length) || 1;
}

// Returns { H, P } replacement baselines.
// Primary source: FA_BASELINES — the averaged top free-agent cohort for this
// projection year (replacement = the best freely available alternative).
// Fallback (no FA data, e.g. unit tests or missing projection files): average
// the weakest quartile of rostered players of that type.
function calcReplacementLevels(allTeamRosters, yearKey) {
  const base = FA_BASELINES[yearKey || 'proj'] || {};
  const result = { H: base.H || null, P: base.P || null };

  if (!result.H || !result.P) {
    const hitters  = [];
    const pitchers = [];
    allTeamRosters.flat().forEach(p => {
      if (!p.proj) return;
      (p.type === 'P' ? pitchers : hitters).push(p);
    });
    if (!result.H) {
      result.H = avgCohortStats(weakestQuartile(hitters), ['pa', 'hr', 'r', 'obp', 'slg'])
        || (hitters.length ? hitters[hitters.length - 1].proj : null);
    }
    if (!result.P) {
      result.P = avgCohortStats(weakestQuartile(pitchers), ['ip', 'so', 'era', 'whip', 'hr9'])
        || (pitchers.length ? pitchers[pitchers.length - 1].proj : null);
    }
  }
  return result;
}

function weakestQuartile(players) {
  const sorted = [...players].sort((a, b) => valProxy(b, b.proj) - valProxy(a, a.proj));
  return sorted.slice(Math.floor(sorted.length * 0.75)).map(p => p.proj);
}

function valProxy(player, b) {
  if (!b) return 0;
  if (player.type === 'H') return (b.pa || 0) * ((b.obp || 0) + (b.slg || 0));
  const safeERA = (b.era || 0) > 0 ? b.era : 99;
  return (b.ip || 0) * (1 / safeERA + (b.so || 0) / 1000);
}

// Marginal SGP vs a replacement (FA-baseline) player.
//
// HITTER counting stats (HR/R) pro-rate the replacement to the player's PA:
// a part-time bat's low PA is a fixed role constraint, so he shouldn't eat a
// full-time replacement's HR total as a penalty (the Will Smith fix).
//
// PITCHER strikeouts do NOT pro-rate: SO is a pure counting category, so raw
// volume is what helps your team, and a 30-inning reliever genuinely
// contributes fewer strikeouts than a full-inning replacement — he should be
// docked for it. Pro-rating the replacement down to his innings (the old
// behavior) rewarded K-*rate* and hid the volume deficit, inflating relievers
// to ~47% of all pitching value. Raw comparison drops them to a realistic
// share and correctly credits starters for their strikeout volume.
//
// Rate stats (OBP/SLG, ERA/WHIP/HR9) are already scaled by PA/IP, so a low
// innings arm's great ratio moves team stats — and earns SGP — proportionally.
function calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP) {
  let sgp = 0;
  if (player.type === 'H') {
    const pa = b.pa || 0;
    const paRatio = (repl.pa || 0) > 0 ? pa / repl.pa : 1;
    sgp += ((b.hr  || 0) - (repl.hr  || 0) * paRatio) / (sgpDenom['HR']  || 1);
    sgp += ((b.r   || 0) - (repl.r   || 0) * paRatio) / (sgpDenom['R']   || 1);
    sgp += ((b.obp || 0) - (repl.obp || 0)) * pa / (avgPA || 1) / (sgpDenom['OBP'] || 1);
    sgp += ((b.slg || 0) - (repl.slg || 0)) * pa / (avgPA || 1) / (sgpDenom['SLG'] || 1);
  } else {
    const ip = b.ip || 0;
    sgp += ((b.so   || 0) - (repl.so   || 0)) / (sgpDenom['SO']   || 1);
    sgp += ((repl.era  || 0) - (b.era  || 0)) * ip / (avgIP || 1) / (sgpDenom['ERA']  || 1);
    sgp += ((repl.whip || 0) - (b.whip || 0)) * ip / (avgIP || 1) / (sgpDenom['WHIP'] || 1);
    sgp += ((repl.hr9  || 0) - (b.hr9  || 0)) * ip / (avgIP || 1) / (sgpDenom['HR9']  || 1);
  }
  return sgp;
}
