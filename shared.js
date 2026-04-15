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

// ── PLACEHOLDER SECTIONS (filled in subsequent tasks) ───────────────────────
// localStorage  → Task 2
// CSV parsing   → Task 2
// Roster parser → Task 3
// Proj parsers  → Task 4
// Stats parsers → Task 5
// Player match  → Task 5
// Blended stats → Task 6
// IL pro-rating → Task 6
// Lineup optim  → Task 7
// Scoring engine→ Task 8
// Valuation     → Task 9
