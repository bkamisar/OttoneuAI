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
  return raw ? JSON.parse(raw) : null;
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

// ── PLACEHOLDER SECTIONS (filled in subsequent tasks) ───────────────────────
// Roster parser → Task 3
// Proj parsers  → Task 4
// Stats parsers → Task 5
// Player match  → Task 5
// Blended stats → Task 6
// IL pro-rating → Task 6
// Lineup optim  → Task 7
// Scoring engine→ Task 8
// Valuation     → Task 9
