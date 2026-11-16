// tools/projflags.js
// Compare "this season" Steamer projections with ZiPS for the same season and
// mark players whose values are shaky. Established MLB players only (200+ PA or
// 50+ IP in their best season of the last three): ZiPS gives prospects full-season lines and Steamer
// rightly does not, so prospects would swamp every list.
//   zips-fill: Steamer has a placeholder (~0 playing time) while ZiPS has a real
//              season -> use the ZiPS line (shared.js applies it while Steamer
//              still shows the placeholder) and flag it. Rostered players only;
//   steamer-zero: the same case for an unrostered player -- flagged, not filled.
//   workload:  both are real projections but disagree on playing time.
const RULES = {
  established: { pa: 200, ip: 50 },
  placeholder: { pa: 10, ip: 5 },     // Steamer at or below this = not really projected
  realSeason:  { pa: 200, ip: 40 },   // ZiPS at or above this = a real season to fill with
  workload:    { pa: 250, ip: 60 },   // disagreement big enough to flag (~36 rostered players at launch)
};

function compare(steamer, zips, unit, kind, usage, norm, out, fills, fillOnly) {
  const key = unit === 'PA' ? 'pa' : 'ip';
  const zi = new Map(zips.map(r => [norm(r.Name), r]));
  for (const s of steamer) {
    const k = norm(s.Name);
    const z = zi.get(k);
    const used = usage.get(k);
    if (!z || !used || (used[key] || 0) < RULES.established[key]) continue;
    const sv = +s[unit] || 0, zv = +z[unit] || 0;
    const row = { Name: s.Name, Type: kind, Unit: unit, Steamer: String(Math.round(sv)), Zips: String(Math.round(zv)) };
    if (sv <= RULES.placeholder[key] && zv >= RULES.realSeason[key]) {
      // Fill rostered players only: unrostered veterans at ~0 (unsigned free agents,
      // retirees) would otherwise join the free-agent pool and raise replacement level.
      if (!fillOnly || fillOnly.has(k)) { out.push({ ...row, Kind: 'zips-fill' }); fills.push(z); }
      else out.push({ ...row, Kind: 'steamer-zero' });
    } else if (Math.abs(sv - zv) >= RULES.workload[key]) {
      out.push({ ...row, Kind: 'workload' });
    }
  }
}

// fillOnly: optional Set of normalized names allowed a fill (the rostered players).
function computeFlags({ steamerH, steamerP, zipsH, zipsP, usage, norm, fillOnly }) {
  const flags = [], fillsH = [], fillsP = [];
  compare(steamerH, zipsH, 'PA', 'H', usage, norm, flags, fillsH, fillOnly);
  compare(steamerP, zipsP, 'IP', 'P', usage, norm, flags, fillsP, fillOnly);
  return { flags, fillsH, fillsP };
}

module.exports = { computeFlags, RULES };
