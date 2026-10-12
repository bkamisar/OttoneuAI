// audit/lib/process.js
// "Process" grades: was the move good given what the suite's own projections
// said the day before? Replays shared.js on that day's roster + projections.
const { latestOnOrBefore } = require('./gitdata');

const PROCESS_FROM = '2026-05-24';
const PROCESS_TO = '2026-09-28';
const prevDay = d => { const x = new Date(d + 'T00:00:00Z'); x.setUTCDate(x.getUTCDate() - 1); return x.toISOString().slice(0, 10); };

function makeValuer(engine, snapshots) {
  const cache = new Map();
  function valuesAsOf(date) {
    const before = prevDay(date);
    const r = latestOnOrBefore(snapshots.roster, before);
    const h = latestOnOrBefore(snapshots.hit, before);
    const p = latestOnOrBefore(snapshots.pit, before);
    if (!r || !h || !p) return null;
    const key = [r.sha, h.sha, p.sha, before].join('|');
    if (cache.has(key)) return cache.get(key);

    engine.setDate(before);
    const rosterText = snapshots.read(r.sha, 'data/roster.csv');
    const rosterRows = engine.call('parseCSV', rosterText);
    const players = engine.call('parseRosterCSV', rosterText);
    players.forEach((pl, i) => { pl.ottoneuId = String(rosterRows[i]['ottoneu ID'] || ''); pl.teamId = String(rosterRows[i]['TeamID'] || ''); });
    const hp = engine.call('parseHittingProjections', snapshots.read(h.sha, 'data/proj_hitting.csv'));
    const pp = engine.call('parsePitchingProjections', snapshots.read(p.sha, 'data/proj_pitching.csv'));
    const matched = engine.call('matchPlayers', players, hp, pp);
    const byTeam = new Map();
    matched.forEach(m => { if (!byTeam.has(m.teamId)) byTeam.set(m.teamId, []); byTeam.get(m.teamId).push(m); });
    const fas = engine.call('getFreeAgents', hp, pp, players);
    const vm = engine.call('calculateAllValues', [...byTeam.values()], fas, true);

    const byOttoneu = new Map(matched.map(m => [m.ottoneuId, m.fgId || m.name]));
    const norm = s => engine.call('normalizeName', s);
    const faByName = new Map(fas.map(f => [f.name, f.fgId || f.name]));
    const keyOf = (ottoneuId, name) => byOttoneu.get(String(ottoneuId)) || faByName.get(norm(name)) || null;
    const value = k => (k && vm[k] ? vm[k].projectedValue || 0 : 0);

    // Best bench player of a type on a team (robustness check): highest value
    // among players NOT in the optimal lineup / capped pitcher pool.
    function benchBest(teamId, type, excludeOttoneuId) {
      const roster = (byTeam.get(String(teamId)) || []).filter(m => m.ottoneuId !== String(excludeOttoneuId) && m.proj);
      const starters = new Set();
      if (type === 'H') {
        const lu = engine.call('optimizeHitterLineup', roster.filter(m => m.type === 'H'), engine.call('paSlotBudget'));
        Object.values(lu).filter(Boolean).forEach(m => starters.add(m.ottoneuId));
      } else {
        const ipB = engine.get('IP_MAX') * Math.max(engine.call('rosProrationFactor'), 0.1);
        engine.call('selectPitchers', roster.filter(m => m.type === 'P'), ipB).forEach(m => starters.add(m.ottoneuId));
      }
      const bench = roster.filter(m => m.type === type && !starters.has(m.ottoneuId))
        .sort((a, b) => value(b.fgId || b.name) - value(a.fgId || a.name));
      return bench.length ? bench[0].ottoneuId : null;
    }

    const out = { values: vm, keyOf, value, benchBest, f: engine.call('rosProrationFactor') };
    cache.set(key, out);
    return out;
  }
  return { valuesAsOf };
}

function moveProcess(engine, valuer, move) {
  if (move.date < PROCESS_FROM || move.date >= PROCESS_TO) return null;
  const v = valuer.valuesAsOf(move.date);
  if (!v) return null;
  const surplus = p => v.value(v.keyOf(p.ottoneuId, p.player)) - p.salary;
  let total = 0;
  for (const p of move.in) total += surplus(p);
  for (const p of move.out) {
    if (move.kind === 'trade') total -= surplus(p);
    else total += p.salary * 0.5 - v.value(v.keyOf(p.ottoneuId, p.player));
  }
  return total * v.f;
}

module.exports = { makeValuer, moveProcess, PROCESS_FROM, PROCESS_TO };
