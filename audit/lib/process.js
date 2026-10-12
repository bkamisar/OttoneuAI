// audit/lib/process.js
// "Process" grades: was the move good given what the suite's own projections
// said the day before? Replays shared.js on that day's roster + projections.
const { latestOnOrBefore } = require('./gitdata');

const PROCESS_FROM = '2026-05-24';
const PROCESS_TO = '2026-09-28';
const DYNASTY_WEIGHTS = { y1: 0.90, y2: 0.81 };   // the suite's defaults (bid/fa/roster/trade pages)
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

    // Future value (lazy): the suite's dynasty surplus minus this season's rental part, i.e. what a
    // player is worth BEYOND this season. Never below $0 -- a bad contract can be cut free at
    // season's end. Prospects get their scouting floor (prospectDynastyValue).
    let dyn = null;
    function dynasty() {
      if (dyn) return dyn;
      const at = k => latestOnOrBefore(snapshots[k] || [], before);
      const load = (k, file, fn) => { const sn = at(k); return sn ? engine.call(fn, snapshots.read(sn.sha, file)) : null; };
      const h1 = load('hitY1', 'data/proj_hitting_y1.csv', 'parseHittingProjections');
      const p1 = load('pitY1', 'data/proj_pitching_y1.csv', 'parsePitchingProjections');
      const h2 = load('hitY2', 'data/proj_hitting_y2.csv', 'parseHittingProjections');
      const p2 = load('pitY2', 'data/proj_pitching_y2.csv', 'parsePitchingProjections');
      const pr = at('prospects');
      engine.localStorage.setItem('ottoneu_prospects', JSON.stringify(pr ? engine.call('parseProspectsCSV', snapshots.read(pr.sha, 'data/prospects.csv')) : []));
      engine.setDate(before);
      // Re-match: shared.js keeps rostered-set and FA baselines in module state, and other dates may have run since.
      let rows = engine.call('matchPlayers', players, hp, pp);
      if (h1 || p1) rows = engine.call('attachYearProjections', rows, h1, p1, 'proj_y1');
      if (h2 || p2) rows = engine.call('attachYearProjections', rows, h2, p2, 'proj_y2');
      const teams = new Map();
      rows.forEach(m => { if (!teams.has(m.teamId)) teams.set(m.teamId, []); teams.get(m.teamId).push(m); });
      dyn = engine.call('calculateDynastyValues', [...teams.values()], DYNASTY_WEIGHTS, null);
      return dyn;
    }
    function future(ottoneuId, name) {
      const d = dynasty()[keyOf(ottoneuId, name)];
      if (!d) return 0;
      const rental = (d.projectedValue || 0) - Math.max(1, d.actualSalary || 0);
      return Math.max(0, d.dynastySurplus - rental);
    }

    const out = { values: vm, keyOf, value, benchBest, future, f: engine.call('rosProrationFactor') };
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

// Future value a trade side gained: sum of future value received minus sum sent. Trades only; null
// outside the window where saved projections exist.
function moveFuture(engine, valuer, move) {
  if (move.kind !== 'trade' || move.date < PROCESS_FROM || move.date >= PROCESS_TO) return null;
  const v = valuer.valuesAsOf(move.date);
  if (!v) return null;
  return move.in.reduce((s, p) => s + v.future(p.ottoneuId, p.player), 0) - move.out.reduce((s, p) => s + v.future(p.ottoneuId, p.player), 0);
}

module.exports = { makeValuer, moveProcess, moveFuture, PROCESS_FROM, PROCESS_TO };
