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

// ── PA-BUDGET LINEUP ────────────────────────────────────────────────────────
// A lineup slot's hard capacity is SLOT_CAP games — one player can never exceed
// it, so primaries are never capped. PA_PER_SLOT is the EXPECTED full-season PA
// of a full-timer: below it, the slot has leftover days a bench bat would cover.
const PA_PER_SLOT = 650;
// Full-season thresholds; scaled to the active budget inside optimizeHitterLineup.
// Scaling matters: fixed thresholds invert in September, when every RoS
// projection is tiny and a fixed ramp would re-introduce volume bias.
const PA_FULL_RATE_FULL = 150;  // below (scaled) this, rate is ramped down as a partial sample
const PA_MIN_SHARE_FULL = 100;  // don't supplement (or accept a backup) below this (scaled)
// Hitter ranking weights: per-rate-unit z-value of filling one slot, derived
// from the Aug 2026 SGP denominators (D_OBP .0083, D_SLG .0094, D_HR 8.39,
// D_R 17.84; avg lineup PA 2355 / AB 2082), normalized to OBP = 1:
//   w_obp = 1/(T_PA·D_OBP)   w_slg = 0.9/(T_AB·D_SLG)   w_hr = 1/D_HR   w_r = 1/D_R
// OPS alone misranks: it overweights empty OBP/AVG and ignores HR/R (~24% of a
// starter's rank score); 380 rostered pairs flip order vs this key.
const HIT_RANK_W = { obp: 1.0, slg: 0.905, hrPerPA: 2.34, rPerPA: 1.10 };
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
      // no-store: these CSVs are auto-updated in the repo throughout the day,
      // and the browser's default HTTP cache has silently served stale copies
      // of individual files before (e.g. proj_hitting.csv) while everything
      // else on the page refreshed fine — surfacing as unmatched/"No Proj"
      // players with no visible error.
      const res = await fetch(url, { cache: 'no-store' });
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

  // Reuses the same quote-aware tokenizer parseCSV() uses elsewhere. The naive
  // line.split(delim) this used to do breaks on any comma inside a quoted
  // field — which the Report/TLDR scouting blurb reliably contains (ordinary
  // English sentences have commas), silently shifting every column after it
  // (Age, ETA, FV, and now the grade columns) for most prospects.
  function splitLine(line) {
    return parseCSVLine(line, delim).map(function(c) { return c.trim().replace(/^"|"$/g, ''); });
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
      // Present/future scouting grades (20-80 scale). Optional — older-format
      // prospects.csv files without these columns simply parse to null, same
      // graceful-degradation pattern as risk/age above.
      hitNow:  gradeCol(idx, cols, 'Hit_Now'),  hitFut:  gradeCol(idx, cols, 'Hit_Fut'),
      gameNow: gradeCol(idx, cols, 'Game_Now'), gameFut: gradeCol(idx, cols, 'Game_Fut'),
      rawNow:  gradeCol(idx, cols, 'Raw_Now'),  rawFut:  gradeCol(idx, cols, 'Raw_Fut'),
      spdNow:  gradeCol(idx, cols, 'Spd_Now'),  spdFut:  gradeCol(idx, cols, 'Spd_Fut'),
      fldNow:  gradeCol(idx, cols, 'Fld_Now'),  fldFut:  gradeCol(idx, cols, 'Fld_Fut'),
      armNow:  gradeCol(idx, cols, 'Arm_Now'),  armFut:  gradeCol(idx, cols, 'Arm_Fut'),
      fbNow:   gradeCol(idx, cols, 'FB_Now'),   fbFut:   gradeCol(idx, cols, 'FB_Fut'),
      slNow:   gradeCol(idx, cols, 'SL_Now'),   slFut:   gradeCol(idx, cols, 'SL_Fut'),
      cbNow:   gradeCol(idx, cols, 'CB_Now'),   cbFut:   gradeCol(idx, cols, 'CB_Fut'),
      chNow:   gradeCol(idx, cols, 'CH_Now'),   chFut:   gradeCol(idx, cols, 'CH_Fut'),
      splNow:  gradeCol(idx, cols, 'SPL_Now'),  splFut:  gradeCol(idx, cols, 'SPL_Fut'),
      ctNow:   gradeCol(idx, cols, 'CT_Now'),   ctFut:   gradeCol(idx, cols, 'CT_Fut'),
      cmdNow:  gradeCol(idx, cols, 'CMD_Now'),  cmdFut:  gradeCol(idx, cols, 'CMD_Fut'),
    };
  }).filter(Boolean);
}

function gradeCol(idx, cols, header) {
  if (idx[header] === undefined) return null;
  var n = parseInt(cols[idx[header]]);
  return isNaN(n) ? null : n;
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
  ROSTERED_COUNTS = {
    H: rosterPlayers.filter(p => p.type === 'H').length,
    P: rosterPlayers.filter(p => p.type === 'P').length,
  };
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
// How many players of each type the league actually rosters. Used by future-year
// replacement: the offseason reshuffle re-rosters roughly this many, so the
// replacement cohort sits at the boundary of what is left over.
let ROSTERED_COUNTS = null;  // { H, P }

function computeFABaselines(hittingProj, pitchingProj, rosterPlayers, yearKey) {
  const rosteredIds   = ROSTERED_IDS   || new Set(rosterPlayers.map(p => p.fgId).filter(Boolean));
  const rosteredNames = ROSTERED_NAMES || new Set(rosterPlayers.map(p => p.name));
  const isFA = p => !(p.fgId && rosteredIds.has(p.fgId)) && !rosteredNames.has(p.name);

  // Ranked pools (role floors applied first — same floors as before).
  const hPool = (hittingProj || [])
    .filter(p => p.proj && (p.proj.pa || 0) >= FA_MIN_PA)
    .sort((a, b) => valProxy({ type: 'H' }, b.proj) - valProxy({ type: 'H' }, a.proj));
  const pPool = (pitchingProj || [])
    .filter(p => p.proj && (p.proj.ip || 0) >= FA_MIN_IP)
    .sort((a, b) => valProxy({ type: 'P' }, b.proj) - valProxy({ type: 'P' }, a.proj));

  const future = yearKey && yearKey !== 'proj';
  let faH, faP;
  if (future) {
    // FUTURE YEARS: "unrostered today" is NOT "freely available next season."
    // The roster boundary dissolves each October — cutting is free and ~60% of
    // contracts resolve to the rental horizon (§4) — so the league re-rosters
    // the best available. Assume it re-rosters the top N of each type by THIS
    // year's value (N = what it rosters today) and take replacement from the
    // boundary of what remains. Without this, mid-season churn leaves regulars
    // (Duran/Naylor/McLain class) unrostered, putting Y1 hitter replacement at
    // league average — which drops half the league's bats below replacement.
    const counts = ROSTERED_COUNTS || {
      H: rosterPlayers.filter(p => p.type === 'H').length,
      P: rosterPlayers.filter(p => p.type === 'P').length,
    };
    faH = hPool.slice(counts.H, counts.H + FA_COHORT_H);
    faP = pPool.slice(counts.P, counts.P + FA_COHORT_P);
  } else {
    // Y0: today's rosters ARE current reality — the best actual free agents are
    // genuinely the freely available alternative right now.
    faH = hPool.filter(isFA).slice(0, FA_COHORT_H);
    faP = pPool.filter(isFA).slice(0, FA_COHORT_P);
  }

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

// ── CONTRACT HORIZONS ────────────────────────────────────────────────────────
// A dynasty contract is an OPTION, not an obligation: cutting is free at
// season's end, so nobody is forced to carry an escalating salary for three
// years. Evaluate each holding horizon and return the best one:
//   H0 "rental" — keep through this season only, then cut
//   H1          — keep one additional year  (+$2 escalation)
//   H2 "keeper" — keep two additional years (+$2 / +$4)
// Do NOT prorate the year-0 salary. Y0 *stat lines* are rest-of-season, but Y0
// *dollar values* are normalized to the full $4,800 pool regardless of how much
// season remains — a player's Y0 value is his share of that full pool. Salary
// and value are therefore already on the same scale. (Invariant #1 governs
// projection stat lines, not pool-normalized dollars; prorating cost against
// unprorated value inflates every surplus and makes H0 win spuriously.)
// Value and cost ALWAYS describe the same horizon; reporting a 3-year value
// against a 1-year cost would credit production that was never paid for.
function computeContractHorizon(y0, y1, y2, s0, w1, w2, floor) {
  const salary = Math.max(1, s0 || 0);
  const base0  = salary;                // full season-long cap commitment
  const esc1   = Math.max(1, salary + 2);
  const esc2   = Math.max(1, salary + 4);

  const v0 = y0;
  const v1 = y0 + w1 * y1;
  // The prospect floor is long-horizon by nature — it represents what a
  // prospect is worth if you hold him. Apply it to H2 only, as max() never
  // additive (invariant #6).
  let   v2 = y0 + w1 * y1 + w2 * y2;
  if (floor > v2) v2 = floor;

  const c0 = base0;
  const c1 = base0 + w1 * esc1;
  const c2 = base0 + w1 * esc1 + w2 * esc2;

  const options = [
    { holdHorizon: 0, dynastyValue: v0, dynastyCost: c0, dynastySurplus: v0 - c0 },
    { holdHorizon: 1, dynastyValue: v1, dynastyCost: c1, dynastySurplus: v1 - c1 },
    { holdHorizon: 2, dynastyValue: v2, dynastyCost: c2, dynastySurplus: v2 - c2 },
  ];
  return options.reduce((best, o) => (o.dynastySurplus > best.dynastySurplus ? o : best));
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
    const h = computeContractHorizon(
      v0.projectedValue || 0,
      v1.projectedValue || 0,
      v2.projectedValue || 0,
      v0.actualSalary   || 0,
      w1, w2,
      prospectDynastyValue(keyToProspect[key])
    );
    dynastyMap[key] = {
      ...v0,
      dynastyValue:   h.dynastyValue,
      dynastyCost:    h.dynastyCost,
      dynastySurplus: h.dynastySurplus,
      holdHorizon:    h.holdHorizon,
    };
  });

  // Diagnostic: the option effect is the whole change — how much surplus the
  // best horizon recovers versus the old forced-3-year hold. Zero for every
  // player where H2 already won, so the pool mean is modest by construction.
  try {
    let nH0 = 0, nH1 = 0, nH2 = 0, optionGain = 0, maxGain = 0, maxName = '', n = 0;
    Object.keys(dynastyMap).forEach(k => {
      const d = dynastyMap[k];
      if (d.holdHorizon === 0) nH0++; else if (d.holdHorizon === 1) nH1++; else nH2++;
      const v0 = vmY0[k] || {}, v1 = vmY1 ? (vmY1[k] || {}) : {}, v2 = vmY2 ? (vmY2[k] || {}) : {};
      const s0 = Math.max(1, v0.actualSalary || 0);
      let val2 = (v0.projectedValue || 0) + w1 * (v1.projectedValue || 0) + w2 * (v2.projectedValue || 0);
      const fl = prospectDynastyValue(keyToProspect[k]);
      if (fl > val2) val2 = fl;
      const forcedH2 = val2 - (s0 + w1 * Math.max(1, s0 + 2) + w2 * Math.max(1, s0 + 4));
      const gain = d.dynastySurplus - forcedH2;
      optionGain += gain;
      if (gain > maxGain) { maxGain = gain; maxName = k; }
      n++;
    });
    console.log('[dynasty] horizons H0/H1/H2 = ' + nH0 + '/' + nH1 + '/' + nH2 +
      ' | mean option gain $' + (optionGain / (n || 1)).toFixed(2) +
      ' | max $' + maxGain.toFixed(1) + ' (' + maxName + ')');
  } catch (e) { /* diagnostic only — never break valuation */ }

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

// RoS plate appearances a single lineup slot is expected to absorb.
// NOTE: this is the ONLY date-dependent entry point. The ramp and min-share
// thresholds are derived from the budget inside optimizeHitterLineup, so the
// optimizer itself is a pure function of (hitters, budget) — deterministic in
// tests and correct in September, when fixed thresholds would exceed every
// projection and silently re-introduce volume bias.
function paSlotBudget() { return PA_PER_SLOT * Math.max(rosProrationFactor(), 0.1); }

// Ranking key for lineup selection: rate quality weighted by what this league
// scores (HIT_RANK_W), NOT raw volume and NOT raw OPS. Volume is handled by the
// slot budget — a short-PA player simply leaves room for a backup. The ramp only
// suppresses genuinely tiny samples. rampPA is overridable for deterministic tests.
function hitterRateValue(p, rampPA) {
  const b = p._proj || p.proj || {};
  const pa = b.pa || 0;
  const rate = (b.obp || 0) * HIT_RANK_W.obp
             + (b.slg || 0) * HIT_RANK_W.slg
             + (pa > 0 ? (b.hr || 0) / pa : 0) * HIT_RANK_W.hrPerPA
             + (pa > 0 ? (b.r  || 0) / pa : 0) * HIT_RANK_W.rPerPA;
  const ramp = Math.min(1, pa / (rampPA || PA_FULL_RATE_FULL * Math.max(rosProrationFactor(), 0.1)));
  return rate * ramp;
}

// A player contributing only part of a slot: rate stats unchanged, counting
// stats scaled to the fraction of his projection actually used.
function scaleHitterUsage(p, usedPA) {
  const b = p._proj || p.proj || {};
  const full = b.pa || 0;
  if (!full || usedPA >= full) return p;
  const f = usedPA / full;
  return Object.assign({}, p, { _proj: Object.assign({}, b, {
    pa: usedPA,
    ab: (b.ab || 0) * f,
    hr: (b.hr || 0) * f,
    r:  (b.r  || 0) * f,
  }) });
}

// Assigns hitters to slots under a PA budget. Returns { slotId: player } map;
// derived keys (OF1_2, C_3, …) are scaled backup contributions for slots whose
// primary cannot fill the budget. paBudget overridable: future-year valuation
// passes full-season PA_PER_SLOT; tests pass explicit budgets.
function optimizeHitterLineup(hitters, paBudget) {
  const budget = paBudget || paSlotBudget();
  // Thresholds scale with the budget, keeping this a pure function of its
  // arguments: a September budget shrinks the ramp and min-share with it.
  const rampPA   = budget * PA_FULL_RATE_FULL / PA_PER_SLOT;   // ≈ 0.23 × budget
  const minShare = budget * PA_MIN_SHARE_FULL / PA_PER_SLOT;   // ≈ 0.15 × budget
  const scored = hitters
    .filter(p => p.type === 'H')
    .map(p => {
      const b = p.proj || {};
      return { ...p, _proj: b, _value: hitterRateValue(p, rampPA) };
    })
    .sort((a, b) => b._value - a._value);

  const slots = [...HITTER_SLOTS].sort((a, b) =>
    scored.filter(p => a.eligible(p)).length - scored.filter(p => b.eligible(p)).length
  );

  const assignment = {};
  const used = new Set();

  // Phase 1 — primaries only. No player may be consumed as a backup before
  // every slot has its best available starter (a lone backup catcher must not
  // be eaten by an OF slot's supplementation).
  for (const slot of slots) {
    const best = scored.find(p => slot.eligible(p) && !used.has(p.fgId || p.name));
    if (best) { assignment[slot.id] = best; used.add(best.fgId || best.name); }
  }

  // Phase 2 — supplementation. The primary always contributes his FULL
  // projection (one player cannot exceed the slot's SLOT_CAP-game capacity, so
  // he is never capped). When injury or part-time usage leaves the slot short
  // of the budget, bench bats absorb the remainder as scaled clones — the slot
  // is shared, as it would be in a real daily lineup.
  for (const slot of slots) {
    const primary = assignment[slot.id];
    if (!primary) continue;
    let shortfall = budget - ((primary._proj && primary._proj.pa) || 0);
    let n = 2;
    while (shortfall >= minShare && n <= 3) {
      const backup = scored.find(p => slot.eligible(p) && !used.has(p.fgId || p.name)
        && ((p._proj && p._proj.pa) || 0) >= minShare);
      if (!backup) break;
      const give = Math.min(shortfall, backup._proj.pa);
      assignment[slot.id + '_' + n] = scaleHitterUsage(backup, give);
      used.add(backup.fgId || backup.name);
      shortfall -= give;
      n++;
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
  // Guard against the (rosters, extras, 'proj_y1') call shape — yearKey passed
  // in the quiet slot silently ran a Y0-baseline, prorated-budget pass over
  // full-season stats and reported plausible-looking garbage with no error.
  if (typeof quiet === 'string') { yearKey = quiet; quiet = true; }
  // Innings budget for team-stat aggregation. Y0 uses rest-of-season
  // projections, so each team can only add innings up to the league cap's
  // remaining share (calendar-prorated). Y1/Y2 files are full-season → full cap.
  const isFutureYear = yearKey && yearKey !== 'proj';
  const ipBudget = isFutureYear ? IP_MAX : IP_MAX * Math.max(rosProrationFactor(), 0.1);
  // Y1/Y2 projections are FULL-SEASON (invariant #1), so those passes get the
  // unprorated slot budget — mirroring ipBudget above. Passing the prorated Y0
  // budget here would treat a full-season line as if it overflowed the slot.
  const paBudget = isFutureYear ? PA_PER_SLOT : paSlotBudget();

  // 1. Optimize lineup for each team
  const teamLineups = allTeamRosters.map(roster => {
    const hitters  = roster.filter(p => p.type === 'H');
    const pitchers = roster.filter(p => p.type === 'P');
    const lineup   = optimizeHitterLineup(hitters, paBudget);
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

  // 4. Replacement level = best freely available alternative (FA baseline),
  //    plus per-position scarcity offsets for hitters.
  const replLevels = calcReplacementLevels(allTeamRosters, yearKey);
  const posOffsets = computePositionalOffsets(allTeamRosters);

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
    let sgp = player.type === 'P'
      ? calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP)
      : hitterSGP(player, b, repl, posOffsets, sgpDenom, avgPA, avgIP);

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
      const sgp  = player.type === 'P'
        ? calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP)
        : hitterSGP(player, b, repl, posOffsets, sgpDenom, avgPA, avgIP);
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

// ── POSITIONAL SCARCITY ──────────────────────────────────────────────────────
// The single hitter FA baseline ignores that power is scarce at C/2B/SS and
// deep at 1B/corner OF, so scarce-position bats are undervalued and corner
// sluggers overvalued (on HR/SLG especially). For each position we take the
// replacement-level cohort of ROSTERED players eligible there — cohort-averaged
// to avoid the single-player coupling that sank the old depth buckets — and
// express it as an OFFSET from the slot-weighted average position. Offsets net
// ~0 across the league, so this redistributes value among hitters by position
// WITHOUT shifting the hit/pitch pool. (Free agents carry no position data, so
// they fall back to the general baseline — see hitterSGP.)
const HIT_POS_DEPTH = { c: 12, '1b': 12, '2b': 16, ss: 16, '3b': 12, of: 60 };
function computePositionalOffsets(allTeamRosters) {
  const hitters = allTeamRosters.flat().filter(p => p.type === 'H' && p.proj && (p.proj.pa || 0) > 50);
  const raw = {};
  Object.keys(HIT_POS_DEPTH).forEach(pos => {
    const elig = hitters.filter(p => (p.positions || []).includes(pos))
      .sort((a, b) => valProxy(b, b.proj) - valProxy(a, a.proj));
    const d = HIT_POS_DEPTH[pos];
    let cohort = elig.slice(d, d + 8);
    if (cohort.length < 3) cohort = elig.slice(-6);   // thin position fallback
    raw[pos] = avgCohortStats(cohort.map(p => p.proj), ['obp', 'slg', 'hr', 'r']);
  });
  const present = Object.keys(raw).filter(p => raw[p]);
  if (!present.length) return {};
  const totW = present.reduce((s, p) => s + HIT_POS_DEPTH[p], 0);
  const avg = {};
  ['obp', 'slg', 'hr', 'r'].forEach(k => {
    avg[k] = present.reduce((s, p) => s + raw[p][k] * HIT_POS_DEPTH[p], 0) / totW;
  });
  const offsets = {};
  present.forEach(p => {
    offsets[p] = {};
    ['obp', 'slg', 'hr', 'r'].forEach(k => { offsets[p][k] = raw[p][k] - avg[k]; });
  });
  return offsets;
}

// Best hitter SGP across eligible positions, grading against the general FA
// baseline shifted by each position's scarcity offset. A player is valued at
// his most favorable (scarcest) eligible position — this is what rewards
// positional flexibility and restores the catcher/middle-infield premium.
// No mapped position (DH/UTIL-only, or FAs) → general baseline.
function hitterSGP(player, b, replH, posOffsets, sgpDenom, avgPA, avgIP) {
  const positions = (player.positions || []).filter(pos => posOffsets && posOffsets[pos]);
  if (!positions.length) return calcPlayerSGP(player, b, replH, sgpDenom, avgPA, avgIP);
  let best = -Infinity;
  for (const pos of positions) {
    const o = posOffsets[pos];
    const adj = { ...replH, obp: replH.obp + o.obp, slg: replH.slg + o.slg, hr: replH.hr + o.hr, r: replH.r + o.r };
    const s = calcPlayerSGP(player, b, adj, sgpDenom, avgPA, avgIP);
    if (s > best) best = s;
  }
  return best;
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
    // Innings-cap awareness. A pitcher who throws MORE innings than replacement
    // does not get those extra strikeouts for free: under the league IP cap they
    // displace another arm who would have produced K of his own. Charge him by
    // scaling the replacement's K to his workload.
    // max(1, …) is LOAD-BEARING — it never scales DOWN, so a low-inning reliever
    // still faces the full replacement K total and stays correctly docked
    // (invariant #3; naive two-way pro-rating once inflated relievers to ~47% of
    // pitching value — this clamp is what prevents that).
    const ipScale = (repl.ip || 0) > 0 ? Math.max(1, ip / (repl.ip || 1)) : 1;
    sgp += ((b.so   || 0) - (repl.so   || 0) * ipScale) / (sgpDenom['SO']   || 1);
    sgp += ((repl.era  || 0) - (b.era  || 0)) * ip / (avgIP || 1) / (sgpDenom['ERA']  || 1);
    sgp += ((repl.whip || 0) - (b.whip || 0)) * ip / (avgIP || 1) / (sgpDenom['WHIP'] || 1);
    sgp += ((repl.hr9  || 0) - (b.hr9  || 0)) * ip / (avgIP || 1) / (sgpDenom['HR9']  || 1);
  }
  return sgp;
}
