// audit/lib/eras.js
// Teams that changed managers: anything summed per team is split by manager.
// Eras start on a date (YYYY-MM-DD); a move belongs to the era its date falls in.
const MANAGER_ERAS = {
  // Prospects R Us: new manager from the 2026 season, its offseason included.
  10899: [{ from: '2024-01-01', label: '2024–25' }, { from: '2025-10-01', label: '2026' }],
  // Misiorowski Index: new manager mid-August 2026 (their moves resume Aug 21).
  10758: [{ from: '2024-01-01', label: 'to Aug 2026' }, { from: '2026-08-15', label: 'from Aug 2026' }],
};

function eraOf(teamId, date) {
  const eras = MANAGER_ERAS[teamId];
  if (!eras) return null;
  return [...eras].reverse().find(e => date >= e.from) || eras[0];
}

function managerKey(teamId, date) {
  const e = eraOf(teamId, date);
  return e ? `${teamId}@${e.from}` : String(teamId);
}

function managerName(teams, key) {
  const [teamId, from] = String(key).split('@');
  const base = (teams[teamId] && teams[teamId].name) || teamId;
  if (!from) return base;
  const e = (MANAGER_ERAS[teamId] || []).find(x => x.from === from);
  return e ? `${base} (${e.label})` : base;
}

// Did this manager run the team for the whole season (its offseason through Sep 28)?
// Season-long counts (most active / most patient) only compare full-season managers.
function coversSeason(key, season) {
  const [teamId, from] = String(key).split('@');
  if (!from) return true;
  const eras = MANAGER_ERAS[teamId] || [];
  const i = eras.findIndex(e => e.from === from);
  const next = eras[i + 1];
  return from <= `${season - 1}-10-01` && (!next || next.from > `${season}-09-28`);
}

module.exports = { MANAGER_ERAS, managerKey, managerName, coversSeason };
