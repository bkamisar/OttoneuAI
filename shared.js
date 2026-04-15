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

// ── PLACEHOLDER SECTIONS (filled in subsequent tasks) ───────────────────────
// Proj parsers  → Task 4
// Stats parsers → Task 5
// Player match  → Task 5
// Blended stats → Task 6
// IL pro-rating → Task 6
// Lineup optim  → Task 7
// Scoring engine→ Task 8
// Valuation     → Task 9
