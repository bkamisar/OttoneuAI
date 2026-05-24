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

// Active lineup slots per position across the 12-team league.
// Replacement = the (N+1)th best rostered player at that position —
// represents who you'd realistically plug in from active rosters, not the
// 40-man bench (too high a bar) and not the waiver wire (too low).
const REPL_DEPTH = {
  C:    12,   // 1 per team
  '1B': 12,
  '2B': 16,   // 12 dedicated + ~4 for MI slot sharing with SS
  'SS': 16,   // 12 dedicated + ~4 for MI slot sharing with 2B
  '3B': 12,
  OF:   60,   // 5 per team
  UTIL: 12,   // fallback; not used in eligible-key evaluation
};
const OF_GAME_CAP  = 810;     // 5 OF × 162 games
const SLOT_CAP     = 162;
const IP_MAX       = 1500;
const IP_MIN       = 1250;

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
];

// Fetches all data/ CSVs from the repo, parses them, and writes to localStorage.
// Returns a status map: { 'roster.csv': true, 'proj_hitting.csv': false, ... }
// Returns {} immediately on file:// so local dev is unaffected.
async function autoLoadFromRepo() {
  if (window.location.protocol === 'file:') return {};
  const status = {};
  await Promise.all(REPO_FILES.map(async function({ file, key, parse }) {
    try {
      const res = await fetch('./data/' + file);
      if (!res.ok) { status[file] = false; return; }
      const text = await res.text();
      saveData(key, parse(text));
      status[file] = true;
    } catch (_) {
      status[file] = false;
    }
  }));
  return status;
}

// ── PROSPECT PARSER ──────────────────────────────────────────────────────────
function parseProspectsCSV(text) {
  return parseCSV(text).map(function(row) {
    const fv  = parseInt(row['FV'])      || 0;
    const name = (row['Name'] || '').trim();
    if (!name || !fv) return null;
    const rankRaw = parseInt(row['Top 100']);
    return {
      name:    normalizeName(name),
      rawName: name,
      rank:    isNaN(rankRaw) ? null : rankRaw,
      orgRank: parseInt(row['Org Rk']) || null,
      org:     (row['Org']           || '').trim(),
      pos:     (row['Pos']           || '').trim(),
      level:   (row['Current Level'] || '').trim(),
      eta:     (row['ETA']           || '').trim(),
      fv,
      age:     parseFloat(row['Age']) || null,
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
  [
    'ottoneu_roster',
    'ottoneu_proj_hitting',  'ottoneu_proj_pitching',
    'ottoneu_proj_hitting_y1', 'ottoneu_proj_pitching_y1',
    'ottoneu_proj_hitting_y2', 'ottoneu_proj_pitching_y2',
    'ottoneu_dynasty_weights',
    'ottoneu_my_team',
    'ottoneu_curr_standings', 'ottoneu_curr_standings_ts',
  ].forEach(k => localStorage.removeItem(k));
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
  return tokens.some(p => p === 'sp' || p === 'rp' || p === 'p') ? 'P' : 'H';
}

// ── PROJECTION PARSERS ───────────────────────────────────────────────────────
// ⚠️ Verify these against your actual FanGraphs projection CSV headers
// Actual FanGraphs projection export headers (tab-separated):
// Hitting:  #  Name  Team  G  PA  AB  H  HR  R  BB  HBP  OBP  SLG  wOBA  wRC+  ADP
// Pitching: #  Name  Team  GS  G  IP  ER  HR  SO  BB  HR/9  WHIP  ERA  ADP
const HITTING_PROJ_COLS = {
  name: 'Name', team: 'Team',
  pa: 'PA', ab: 'AB', h: 'H', bb: 'BB', hbp: 'HBP',
  hr: 'HR', r: 'R', obp: 'OBP', slg: 'SLG',
};

const PITCHING_PROJ_COLS = {
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
        fgId:    '',
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
        fgId:    '',
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
  const projById   = {};
  const projByName = {};
  [...(hittingProj || []), ...(pitchingProj || [])].forEach(p => {
    if (p.fgId) projById[p.fgId]   = p;
    if (p.name) projByName[p.name] = p;
  });

  return rosterPlayers.map(rp => {
    const projMatch = projById[rp.fgId] || projByName[rp.name] || null;
    return { ...rp, proj: projMatch ? projMatch.proj : null };
  });
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

// Attaches a future-year projection to already-matched roster players.
// projKey: 'proj_y1' or 'proj_y2'. Matched by normalized name only
// (projection CSVs have no player ID column).
function attachYearProjections(matchedPlayers, hittingProj, pitchingProj, projKey) {
  if (!hittingProj && !pitchingProj) return matchedPlayers;
  const byName = {};
  [...(hittingProj || []), ...(pitchingProj || [])].forEach(p => {
    if (p.name) byName[p.name] = p.proj;
  });
  return matchedPlayers.map(p => ({ ...p, [projKey]: byName[p.name] || null }));
}

// Computes dynasty value by running the SGP model across up to three projection
// years and combining with weighted discounting.
// weights: { y1: 0.90, y2: 0.81 }  (defaults; pass null to use Y0 only)
// Players with no Y1/Y2 projection simply contribute 0 for that year.
function calculateDynastyValues(allRosters, weights, extraPlayers) {
  const w1 = weights ? (weights.y1 || 0) : 0;
  const w2 = weights ? (weights.y2 || 0) : 0;

  // Helper: clone rosters swapping proj → a different year's projection.
  function cloneForYear(rosters, yearKey) {
    return rosters.map(r => r.map(p => ({ ...p, proj: p[yearKey] || null })));
  }
  function cloneExtras(extras, yearKey) {
    return extras ? extras.map(p => ({ ...p, proj: p[yearKey] || null })) : null;
  }

  // Y0 — always run
  const vmY0 = calculateAllValues(allRosters, extraPlayers);

  // Y1 — run only if any player actually has proj_y1 data
  const hasY1 = w1 > 0 && allRosters.flat().some(p => p.proj_y1);
  const vmY1 = hasY1
    ? calculateAllValues(cloneForYear(allRosters, 'proj_y1'), cloneExtras(extraPlayers, 'proj_y1'))
    : null;

  // Y2 — run only if any player actually has proj_y2 data
  const hasY2 = w2 > 0 && allRosters.flat().some(p => p.proj_y2);
  const vmY2 = hasY2
    ? calculateAllValues(cloneForYear(allRosters, 'proj_y2'), cloneExtras(extraPlayers, 'proj_y2'))
    : null;

  // Dynasty salary cost: apply the same discount weights to salary as to value.
  // Salary is paid each year, so total cost in present-value terms mirrors the
  // same discount logic: cost = salary × (1 + w1 + w2).
  // This keeps surplus meaningful — a player at $10 with default weights costs
  // $27.10 in dynasty terms, not $10.
  const salaryMultiplier = 1 + w1 + w2;

  // Merge into a single map: all Y0 keys, enriched with dynasty values.
  const dynastyMap = {};
  Object.keys(vmY0).forEach(key => {
    const v0 = vmY0[key] || {};
    const v1 = vmY1 ? (vmY1[key] || {}) : {};
    const v2 = vmY2 ? (vmY2[key] || {}) : {};
    const currentValue = v0.projectedValue || 0;
    const dynastyValue = currentValue
      + w1 * (v1.projectedValue || 0)
      + w2 * (v2.projectedValue || 0);
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

// Selects pitchers ranked by value up to IP_MAX. Returns [] if projected IP < IP_MIN.
function selectPitchers(pitchers) {
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
    if (totalIP + ip <= IP_MAX) { selected.push(p); totalIP += ip; }
  }
  return totalIP >= IP_MIN ? selected : [];
}

// ── SCORING ENGINE ───────────────────────────────────────────────────────────
// Computes 8 category totals for one team from their lineup and pitcher pool.
function computeTeamStats(hitterAssignment, selectedPitchers) {
  const hitters  = Object.values(hitterAssignment || {}).filter(Boolean);
  const pitchers = selectedPitchers || [];

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

  const pitOk = totIP >= IP_MIN;
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
// curr  — one row from parseCurrStandings
// proj  — result of computeTeamStats (full-season projection)
//
// Hitting: Games × PA_PER_GAME gives current PA proxy; remainder drawn from proj._totPA.
// Pitching: curr.ip is the exact denominator; remainder = proj._ip − curr.ip.
// Rate stats are weighted by their natural denominators (PA for hitting, IP for pitching).
const PA_PER_GAME = 4.2;

function blendStats(curr, proj) {
  // ── Hitting ───────────────────────────────────────────────────────────────
  const currPA    = curr.games * PA_PER_GAME;
  const projFullPA = proj._totPA || 1;
  const remPA     = Math.max(0, projFullPA - currPA);
  const totalPA   = currPA + remPA;
  const hitFrac   = projFullPA > 0 ? remPA / projFullPA : 0;

  const obp = totalPA > 0
    ? (curr.obp * currPA + proj.OBP * remPA) / totalPA : proj.OBP;
  const slg = totalPA > 0
    ? (curr.slg * currPA + proj.SLG * remPA) / totalPA : proj.SLG;
  const hr  = curr.hr + proj.HR * hitFrac;
  const r   = curr.r  + proj.R  * hitFrac;

  // ── Pitching ──────────────────────────────────────────────────────────────
  const currIP    = curr.ip;
  const projFullIP = proj._ip || 1;
  const remIP     = Math.max(0, projFullIP - currIP);
  const totalIP   = currIP + remIP;
  const pitFrac   = projFullIP > 0 ? remIP / projFullIP : 0;

  const era  = totalIP > 0
    ? (curr.era * currIP / 9 + proj.ERA  * remIP / 9) * 9 / totalIP : proj.ERA;
  const whip = totalIP > 0
    ? (curr.whip * currIP    + proj.WHIP * remIP)      / totalIP     : proj.WHIP;
  const hr9  = totalIP > 0
    ? (curr.hr9 * currIP / 9 + proj.HR9  * remIP / 9) * 9 / totalIP : proj.HR9;
  const so   = curr.k + proj.SO * pitFrac;

  return {
    OBP: obp, SLG: slg, HR: hr, R: r,
    ERA: era, WHIP: whip, HR9: hr9, SO: so,
    _ip: totalIP, _totPA: totalPA, _pitchingValid: proj._pitchingValid,
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
function calculateAllValues(allTeamRosters, extraPlayers) {
  // 1. Optimize lineup for each team
  const teamLineups = allTeamRosters.map(roster => {
    const hitters  = roster.filter(p => p.type === 'H');
    const pitchers = roster.filter(p => p.type === 'P');
    const lineup   = optimizeHitterLineup(hitters);
    const pitPool  = selectPitchers(pitchers);
    const stats    = computeTeamStats(lineup, pitPool);
    return { lineup, pitPool, stats, roster };
  });

  // 2. SGP denominators from stdev of each category across all teams
  const sgpDenom = calcSGPDenoms(teamLineups.map(t => t.stats));

  // 3. Track which players are starters (used for hitter replacement level only)
  const startingH = new Set();
  const startingP = new Set();
  teamLineups.forEach(t => {
    Object.values(t.lineup).filter(Boolean).forEach(p => startingH.add(p.fgId || p.name));
    t.pitPool.forEach(p => startingP.add(p.fgId || p.name));
  });

  // Average team PA and IP (for rate-stat normalization)
  const avgPA = teamLineups.reduce((s, t) =>
    s + Object.values(t.lineup).filter(Boolean)
      .reduce((sp, p) => sp + ((p._proj && p._proj.pa) || (p.proj && p.proj.pa) || 0), 0), 0) / NUM_TEAMS;
  const avgIP = teamLineups.reduce((s, t) =>
    s + t.pitPool.reduce((sp, p) => sp + ((p._proj && p._proj.ip) || (p.proj && p.proj.ip) || 0), 0), 0) / NUM_TEAMS;

  // 4. Position-specific replacement level
  const replLevels = calcReplacementLevels(allTeamRosters, startingP);

  // 5. SGP per player — split into hitting and pitching pools
  const valueMap = {};
  const hitSGPs  = [];
  const pitSGPs  = [];
  let totalHitSGP = 0;
  let totalPitSGP = 0;

  allTeamRosters.flat().forEach(player => {
    const key = player.fgId || player.name;
    if (valueMap[key]) return;
    const b = player.proj;

    if (!b) {
      console.warn('[Ottoneu] No projection matched for:', player.rawName || player.name,
        '(salary $' + (player.salary || 0) + ', pos ' + (player.positions || []).join('/') + ')');
      valueMap[key] = { sgp: 0, noProj: true, actualSalary: player.salary || 0, surplus: -(player.salary || 0) };
      return;
    }

    let sgp;
    if (player.type === 'P') {
      const repl = replLevels['P'];
      if (!repl) { valueMap[key] = { sgp: 0, actualSalary: player.salary || 0, surplus: -(player.salary || 0) }; return; }
      sgp = calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP);
    } else {
      // Try every eligible position bucket; use the one that gives the best SGP.
      // This correctly values multi-position players at their most scarce slot.
      const eligibleKeys = getEligibleReplacementKeys(player);
      let bestSGP = null;
      for (const replKey of eligibleKeys) {
        const repl = replLevels[replKey];
        if (!repl) continue;
        const s = calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP);
        if (bestSGP === null || s > bestSGP) bestSGP = s;
      }
      sgp = bestSGP !== null ? bestSGP : 0;
    }

    valueMap[key] = { sgp, actualSalary: player.salary || 0 };
    if (sgp > 0) {
      if (player.type === 'H') { totalHitSGP += sgp; hitSGPs.push({ key, sgp }); }
      else                     { totalPitSGP += sgp; pitSGPs.push({ key, sgp }); }
    }
  });

  // 6. Normalize to $4,800 with a hitting/pitching pool split derived from SGP totals.
  // Allocating dollars proportional to where scoring opportunity exists avoids
  // hardcoded assumptions and self-corrects as projections update.
  const totalSGP = totalHitSGP + totalPitSGP;
  const dynamicHitShare = totalSGP > 0 ? totalHitSGP / totalSGP : 0.60;
  const hitDollars = SALARY_POOL * dynamicHitShare;
  const pitDollars = SALARY_POOL * (1 - dynamicHitShare);

  const hitRate = totalHitSGP > 0 ? hitDollars / totalHitSGP : 0;
  const pitRate = totalPitSGP > 0 ? pitDollars / totalPitSGP : 0;

  hitSGPs.forEach(({ key, sgp }) => {
    const val = sgp * hitRate;
    valueMap[key].projectedValue = Math.max(0, val);
    valueMap[key].surplus = valueMap[key].projectedValue - (valueMap[key].actualSalary || 0);
  });
  pitSGPs.forEach(({ key, sgp }) => {
    const val = sgp * pitRate;
    valueMap[key].projectedValue = Math.max(0, val);
    valueMap[key].surplus = valueMap[key].projectedValue - (valueMap[key].actualSalary || 0);
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
      let sgp;
      if (player.type === 'P') {
        const repl = replLevels['P'];
        if (!repl) { valueMap[key] = { projectedValue: 0, sgp: 0, actualSalary: 0, surplus: 0 }; return; }
        sgp = calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP);
      } else {
        const eligibleKeys = getEligibleReplacementKeys(player);
        let bestSGP = null;
        for (const rk of eligibleKeys) {
          const repl = replLevels[rk];
          if (!repl) continue;
          const s = calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP);
          if (bestSGP === null || s > bestSGP) bestSGP = s;
        }
        sgp = bestSGP !== null ? bestSGP : 0;
      }
      const rate = player.type === 'P' ? pitRate : hitRate;
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

function getReplacementKey(player) {
  if (player.type === 'P') return 'P';
  const pos = player.positions || [];
  if (pos.includes('c'))  return 'C';
  if (pos.includes('ss')) return 'SS';
  if (pos.includes('2b')) return '2B';
  if (pos.includes('3b')) return '3B';
  if (pos.includes('1b')) return '1B';
  if (pos.includes('of')) return 'OF';
  return 'UTIL';
}

// Returns all replacement-level buckets a hitter is eligible for.
// Used to value multi-position players at their most scarce slot.
function getEligibleReplacementKeys(player) {
  if (player.type === 'P') return ['P'];
  const pos = player.positions || [];
  const keys = [];
  if (pos.includes('c'))  keys.push('C');
  if (pos.includes('ss')) keys.push('SS');
  if (pos.includes('2b')) keys.push('2B');
  if (pos.includes('3b')) keys.push('3B');
  if (pos.includes('1b')) keys.push('1B');
  if (pos.includes('of')) keys.push('OF');
  return keys.length ? keys : ['UTIL'];
}

function calcReplacementLevels(allTeamRosters, startingP) {
  const groups = { C:[], SS:[], '2B':[], '3B':[], '1B':[], OF:[], UTIL:[], P:[] };
  allTeamRosters.flat().forEach(p => {
    const b = p.proj;
    if (!b) return;
    const pk  = getReplacementKey(p);
    const key = p.fgId || p.name;
    if (p.type === 'P') {
      groups[pk].push({ b, isStart: startingP.has(key), v: valProxy(p, b) });
    } else {
      groups[pk].push({ b, v: valProxy(p, b) });
    }
  });

  const result = {};
  Object.entries(groups).forEach(([pos, players]) => {
    const sorted = [...players].sort((a, b) => b.v - a.v);

    if (pos === 'P') {
      // Simulate full-league IP budget to find true replacement pitcher.
      // Avoids the fallback-to-worst-pitcher bug when all rostered arms fit under
      // each team's individual cap but collectively exceed the league's budget.
      const leagueBudget = IP_MAX * NUM_TEAMS;
      let usedIP = 0;
      let replPitcher = null;
      for (const p of sorted) {
        const ip = p.b.ip || 0;
        if (usedIP + ip <= leagueBudget) {
          usedIP += ip;
        } else {
          replPitcher = p;
          break;
        }
      }
      result[pos] = replPitcher ? replPitcher.b : (sorted[sorted.length - 1] || { b: null }).b;
    } else {
      // Use fixed active-roster depth: the player just beyond the expected number
      // of active lineup slots league-wide. Accounts for 40-man rosters without
      // treating waiver-wire dregs as the replacement.
      const depth = REPL_DEPTH[pos] || 12;
      result[pos] = (sorted[depth] || sorted[sorted.length - 1] || { b: null }).b;
    }
  });
  return result;
}

function valProxy(player, b) {
  if (!b) return 0;
  if (player.type === 'H') return (b.pa || 0) * ((b.obp || 0) + (b.slg || 0));
  const safeERA = (b.era || 0) > 0 ? b.era : 99;
  return (b.ip || 0) * (1 / safeERA + (b.so || 0) / 1000);
}

function calcPlayerSGP(player, b, repl, sgpDenom, avgPA, avgIP) {
  let sgp = 0;
  if (player.type === 'H') {
    sgp += ((b.hr  || 0) - (repl.hr  || 0)) / (sgpDenom['HR']  || 1);
    sgp += ((b.r   || 0) - (repl.r   || 0)) / (sgpDenom['R']   || 1);
    const pa = b.pa || 0;
    sgp += ((b.obp || 0) - (repl.obp || 0)) * pa / (avgPA || 1) / (sgpDenom['OBP'] || 1);
    sgp += ((b.slg || 0) - (repl.slg || 0)) * pa / (avgPA || 1) / (sgpDenom['SLG'] || 1);
  } else {
    sgp += ((b.so   || 0) - (repl.so   || 0)) / (sgpDenom['SO']   || 1);
    const ip = b.ip || 0;
    sgp += ((repl.era  || 0) - (b.era  || 0)) * ip / (avgIP || 1) / (sgpDenom['ERA']  || 1);
    sgp += ((repl.whip || 0) - (b.whip || 0)) * ip / (avgIP || 1) / (sgpDenom['WHIP'] || 1);
    sgp += ((repl.hr9  || 0) - (b.hr9  || 0)) * ip / (avgIP || 1) / (sgpDenom['HR9']  || 1);
  }
  return sgp;
}
