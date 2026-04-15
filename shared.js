// shared.js — Ottoneu 4x4 Tool Suite core logic
// Load via <script src="shared.js"> in every tool page.

// ── CONSTANTS ────────────────────────────────────────────────────────────────
const CATS         = ["OBP","SLG","HR","R","ERA","WHIP","HR9","SO"];
const LOWER_BETTER = new Set(["ERA","WHIP","HR9"]);
const NUM_TEAMS    = 12;
const SALARY_POOL  = 4800;    // $400 × 12 teams
const OF_GAME_CAP  = 810;     // 5 OF × 162 games
const SLOT_CAP     = 162;
const IP_MAX       = 1500;
const IP_MIN       = 1250;
const IL_15_MISS   = 20;      // assumed games missed on 15-day IL
const IL_60_MISS   = 80;      // assumed games missed on 60-day IL

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
    'ottoneu_roster', 'ottoneu_proj_hitting', 'ottoneu_proj_pitching',
    'ottoneu_stats_hitting', 'ottoneu_stats_pitching',
    'ottoneu_my_team', 'ottoneu_il'
  ].forEach(k => localStorage.removeItem(k));
}

// ── CSV PARSING ──────────────────────────────────────────────────────────────
function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const headers = parseCSVLine(lines[0]).map(h => h.trim().replace(/^"|"$/g, ''));
  return lines.slice(1)
    .filter(l => l.trim())
    .map(line => {
      const values = parseCSVLine(line);
      const obj = {};
      headers.forEach((h, i) => { obj[h] = (values[i] || '').trim().replace(/^"|"$/g, ''); });
      return obj;
    });
}

function parseCSVLine(line) {
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
  fgId:      'fg_id',    // FanGraphs player ID — primary match key
  name:      'Name',
  positions: 'Pos',      // e.g. "SS/2B" or "OF" or "SP"
  salary:    'Salary',   // e.g. "$10" or "10"
  team:      'Team',     // fantasy team name; blank = free agent
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
const HITTING_PROJ_COLS = {
  fgId: 'playerid', name: 'Name', team: 'Team',
  pa: 'PA', ab: 'AB', h: 'H', bb: 'BB', hbp: 'HBP',
  hr: 'HR', r: 'R', obp: 'OBP', slg: 'SLG',
};

const PITCHING_PROJ_COLS = {
  fgId: 'playerid', name: 'Name', team: 'Team',
  ip: 'IP', h: 'H', bb: 'BB', hr: 'HR', so: 'SO',
  era: 'ERA', whip: 'WHIP', hr9: 'HR/9',
};

function parseHittingProjections(text) {
  return parseCSV(text)
    .filter(row => parseFloat(row[HITTING_PROJ_COLS.pa]) > 0)
    .map(row => {
      const n = k => parseFloat(row[HITTING_PROJ_COLS[k]]) || 0;
      return {
        fgId:    (row[HITTING_PROJ_COLS.fgId] || '').trim(),
        name:    normalizeName(row[HITTING_PROJ_COLS.name] || ''),
        rawName: (row[HITTING_PROJ_COLS.name] || '').trim(),
        type:    'H',
        proj: {
          pa: n('pa'), ab: n('ab'), h: n('h'),
          bb: n('bb'), hbp: n('hbp'),
          hr: n('hr'), r: n('r'),
          obp: n('obp'), slg: n('slg'),
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
      const era = n('era');
      const hr  = n('hr');
      const hr9col = parseFloat(row[PITCHING_PROJ_COLS.hr9]) || 0;
      const hr9 = hr9col > 0 ? hr9col : (ip > 0 ? hr * 9 / ip : 0);
      return {
        fgId:    (row[PITCHING_PROJ_COLS.fgId] || '').trim(),
        name:    normalizeName(row[PITCHING_PROJ_COLS.name] || ''),
        rawName: (row[PITCHING_PROJ_COLS.name] || '').trim(),
        type:    'P',
        proj: {
          ip, hr, hr9,
          h:    n('h'),
          bb:   n('bb'),
          so:   n('so'),
          era,
          whip: n('whip'),
          er:   ip > 0 ? era * ip / 9 : 0,
        },
      };
    });
}

// ── CURRENT STATS PARSERS ────────────────────────────────────────────────────
// ⚠️ Verify these against your FanGraphs leaderboard CSV exports
const HITTING_STATS_COLS = {
  fgId: 'playerid', name: 'Name', team: 'Team',
  g: 'G', pa: 'PA', ab: 'AB', h: 'H', bb: 'BB', hbp: 'HBP',
  hr: 'HR', r: 'R', obp: 'OBP', slg: 'SLG',
};

const PITCHING_STATS_COLS = {
  fgId: 'playerid', name: 'Name', team: 'Team',
  ip: 'IP', h: 'H', bb: 'BB', hr: 'HR', so: 'SO',
  era: 'ERA', whip: 'WHIP', hr9: 'HR/9',
};

function parseHittingStats(text) {
  return parseCSV(text)
    .filter(row => parseFloat(row[HITTING_STATS_COLS.pa]) > 0)
    .map(row => {
      const n = k => parseFloat(row[HITTING_STATS_COLS[k]]) || 0;
      return {
        fgId:    (row[HITTING_STATS_COLS.fgId] || '').trim(),
        name:    normalizeName(row[HITTING_STATS_COLS.name] || ''),
        rawName: (row[HITTING_STATS_COLS.name] || '').trim(),
        type:    'H',
        stats: {
          g: n('g'), pa: n('pa'), ab: n('ab'), h: n('h'),
          bb: n('bb'), hbp: n('hbp'),
          hr: n('hr'), r: n('r'),
          obp: n('obp'), slg: n('slg'),
        },
      };
    });
}

function parsePitchingStats(text) {
  return parseCSV(text)
    .filter(row => parseFloat(row[PITCHING_STATS_COLS.ip]) > 0)
    .map(row => {
      const n   = k => parseFloat(row[PITCHING_STATS_COLS[k]]) || 0;
      const ip  = n('ip');
      const era = n('era');
      const hr  = n('hr');
      const hr9col = parseFloat(row[PITCHING_STATS_COLS.hr9]) || 0;
      const hr9 = hr9col > 0 ? hr9col : (ip > 0 ? hr * 9 / ip : 0);
      return {
        fgId:    (row[PITCHING_STATS_COLS.fgId] || '').trim(),
        name:    normalizeName(row[PITCHING_STATS_COLS.name] || ''),
        rawName: (row[PITCHING_STATS_COLS.name] || '').trim(),
        type:    'P',
        stats: {
          ip, hr, hr9, era,
          h:    n('h'), bb: n('bb'), so: n('so'),
          whip: n('whip'),
          er:   ip > 0 ? era * ip / 9 : 0,
        },
      };
    });
}

// ── PLAYER MATCHING ──────────────────────────────────────────────────────────
// Merges roster players with their projections and current stats.
// Match priority: FanGraphs ID → normalized name.
function matchPlayers(rosterPlayers, hittingProj, pitchingProj, hittingStats, pitchingStats) {
  const projById   = {};
  const projByName = {};
  [...(hittingProj || []), ...(pitchingProj || [])].forEach(p => {
    if (p.fgId)  projById[p.fgId]   = p;
    if (p.name)  projByName[p.name] = p;
  });

  const statsById   = {};
  const statsByName = {};
  [...(hittingStats || []), ...(pitchingStats || [])].forEach(p => {
    if (p.fgId)  statsById[p.fgId]   = p;
    if (p.name)  statsByName[p.name] = p;
  });

  return rosterPlayers.map(rp => {
    const projMatch  = projById[rp.fgId]  || projByName[rp.name]  || null;
    const statsMatch = statsById[rp.fgId] || statsByName[rp.name] || null;
    return {
      ...rp,
      proj:  projMatch  ? projMatch.proj   : null,
      stats: statsMatch ? statsMatch.stats : null,
    };
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

// ── BLENDED STATS + IL PRO-RATING ────────────────────────────────────────────
// Returns a full projected season stats object, blending actual YTD stats with
// remaining projected stats. ilDesignations: [{ fgId, name, type: '15day'|'60day' }]
function getBlendedStats(player, ilDesignations) {
  const proj  = player.proj;
  const stats = player.stats;
  if (!proj) return null;

  const il = (ilDesignations || []).find(d =>
    (d.fgId && d.fgId === player.fgId) || d.name === player.name
  );
  const missedGames = il ? (il.type === '15day' ? IL_15_MISS : IL_60_MISS) : 0;
  const ilScale     = (162 - missedGames) / 162;

  if (!stats) return scaleStats(proj, ilScale, player.type);

  const fraction = player.type === 'H'
    ? Math.min((stats.pa || 0) / Math.max(proj.pa, 1), 1)
    : Math.min((stats.ip || 0) / IP_MAX, 1);

  return blendStats(stats, proj, fraction, Math.max(0, 1 - fraction) * ilScale, player.type);
}

function scaleStats(proj, scale, type) {
  if (type === 'H') {
    return {
      pa:  proj.pa  * scale, ab:  proj.ab  * scale,
      h:   proj.h   * scale, bb:  proj.bb  * scale, hbp: proj.hbp * scale,
      hr:  proj.hr  * scale, r:   proj.r   * scale,
      obp: proj.obp, slg: proj.slg,
    };
  }
  const ip = proj.ip * scale;
  return {
    ip, hr: proj.hr * scale, so: proj.so * scale,
    h:  proj.h  * scale, bb: proj.bb * scale, er: proj.er * scale,
    era: proj.era, whip: proj.whip, hr9: proj.hr9,
  };
}

function blendStats(stats, proj, fraction, remainingScale, type) {
  if (type === 'H') {
    const actPA = stats.pa || 0, actAB = stats.ab || 0;
    const remPA = proj.pa * remainingScale, remAB = proj.ab * remainingScale;
    const totPA = actPA + remPA, totAB = actAB + remAB;
    return {
      pa:  totPA, ab:  totAB,
      h:   (stats.h   || 0) + proj.h   * remainingScale,
      bb:  (stats.bb  || 0) + proj.bb  * remainingScale,
      hbp: (stats.hbp || 0) + proj.hbp * remainingScale,
      hr:  (stats.hr  || 0) + proj.hr  * remainingScale,
      r:   (stats.r   || 0) + proj.r   * remainingScale,
      obp: totPA > 0 ? (actPA * (stats.obp || 0) + remPA * (proj.obp || 0)) / totPA : 0,
      slg: totAB > 0 ? (actAB * (stats.slg || 0) + remAB * (proj.slg || 0)) / totAB : 0,
    };
  }
  const actIP = stats.ip || 0, remIP = proj.ip * remainingScale;
  const totIP = actIP + remIP;
  const erNum   = actIP * (stats.era  || 0) / 9 + remIP * (proj.era  || 0) / 9;
  const whipNum = actIP * (stats.whip || 0)     + remIP * (proj.whip || 0);
  const hr9Num  = actIP * (stats.hr9  || 0) / 9 + remIP * (proj.hr9  || 0) / 9;
  return {
    ip:   totIP,
    hr:   (stats.hr || 0) + proj.hr * remainingScale,
    so:   (stats.so || 0) + proj.so * remainingScale,
    h:    (stats.h  || 0) + proj.h  * remainingScale,
    bb:   (stats.bb || 0) + proj.bb * remainingScale,
    er:   erNum,
    era:  totIP > 0 ? erNum  * 9 / totIP : 0,
    whip: totIP > 0 ? whipNum  / totIP   : 0,
    hr9:  totIP > 0 ? hr9Num  * 9 / totIP : 0,
  };
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
function optimizeHitterLineup(hitters, ilDesignations) {
  const scored = hitters
    .filter(p => p.type === 'H')
    .map(p => {
      const b = getBlendedStats(p, ilDesignations) || {};
      return { ...p, _blended: b, _value: (b.pa || 0) * ((b.obp || 0) + (b.slg || 0)) };
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
function selectPitchers(pitchers, ilDesignations) {
  const scored = pitchers
    .filter(p => p.type === 'P')
    .map(p => {
      const b        = getBlendedStats(p, ilDesignations) || {};
      const safeERA  = (b.era  || 0) > 0 ? b.era  : 99;
      const safeWHIP = (b.whip || 0) > 0 ? b.whip : 9;
      return { ...p, _blended: b, _value: (b.ip || 0) * (1 / safeERA + 1 / safeWHIP + (b.so || 0) / 100) };
    })
    .sort((a, b) => b._value - a._value);

  const selected = [];
  let totalIP = 0;
  for (const p of scored) {
    const ip = (p._blended && p._blended.ip) || 0;
    if (totalIP + ip <= IP_MAX) { selected.push(p); totalIP += ip; }
  }
  return totalIP >= IP_MIN ? selected : [];
}

// ── SCORING ENGINE ───────────────────────────────────────────────────────────
// Computes 8 category totals for one team from their lineup and pitcher pool.
function computeTeamStats(hitterAssignment, selectedPitchers, ilDesignations) {
  const hitters  = Object.values(hitterAssignment || {}).filter(Boolean);
  const pitchers = selectedPitchers || [];

  let totPA = 0, totAB = 0, totOBPNum = 0, totSLGNum = 0, totHR = 0, totR = 0;
  for (const p of hitters) {
    const b = p._blended || getBlendedStats(p, ilDesignations) || {};
    totPA     += b.pa  || 0;
    totAB     += b.ab  || 0;
    totOBPNum += (b.pa || 0) * (b.obp || 0);
    totSLGNum += (b.ab || 0) * (b.slg || 0);
    totHR     += b.hr  || 0;
    totR      += b.r   || 0;
  }

  let totIP = 0, totERNum = 0, totWHIPNum = 0, totHR9Num = 0, totSO = 0;
  for (const p of pitchers) {
    const b = p._blended || getBlendedStats(p, ilDesignations) || {};
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
    _ip:  totIP,
    _pitchingValid: pitOk,
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

// ── PLACEHOLDER SECTIONS (filled in subsequent tasks) ───────────────────────
// Valuation     → Task 9
