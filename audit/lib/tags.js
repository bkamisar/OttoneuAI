// audit/lib/tags.js
// Automatic "why" labels from what was true on the move date.
const { sumWindow } = require('./stats');

function tagMove(move, env) {
  const tags = new Set();
  for (const p of move.in) {
    const h = env.hotPctl(p.ottoneuId, move.date);
    if (h !== null && h >= 0.75) tags.add('hot');
    if (env.isProspect(p.ottoneuId, move.date)) tags.add('prospect');
    const need = env.weakestCatGroup(move.teamId, move.date);
    if (need && env.typeOf(p.ottoneuId) === need) tags.add('need');
  }
  if (move.kind === 'trade') {
    if (move.date.slice(5, 7) === '08') tags.add('deadline');
    const net = move.out.reduce((s, p) => s + p.salary, 0) - move.in.reduce((s, p) => s + p.salary, 0);
    if (net >= 10) tags.add('salary-dump');
    const few = Math.min(move.in.length, move.out.length), many = Math.max(move.in.length, move.out.length);
    if (few >= 1 && many >= 2 && few !== many) tags.add('consolidation');
  }
  const rank = env.rankAt(move.teamId, move.date);
  if (rank !== null) { if (rank <= 4) tags.add('contender'); else if (rank >= 9) tags.add('rebuilder'); }
  return [...tags];
}

// L15 HotScore percentile, same scoring as hot.html, pool = same-kind qualified players.
function makeHotPercentile(engine, days, identity) {
  const dates = [...days.keys()].sort();
  const cache = new Map();
  function pool(date) {
    if (cache.has(date)) return cache.get(date);
    const win = dates.filter(d => d < date).slice(-15).map(d => days.get(d));
    if (win.length < 10) { cache.set(date, null); return null; }
    const ids = { h: new Set(), p: new Set() };
    win.forEach(d => { d.h.forEach(r => ids.h.add(r[0])); d.p.forEach(r => ids.p.add(r[0])); });
    const kinds = { H: [], SP: [], RP: [] };
    ids.h.forEach(id => { const l = sumWindow(win, id, 'h'); if (engine.call('hotMeetsThreshold', 'H', 15, l)) kinds.H.push([id, l]); });
    ids.p.forEach(id => {
      const l = sumWindow(win, id, 'p'); const k = engine.call('hotClassifyRole', l.g, l.gs);
      if (engine.call('hotMeetsThreshold', k, 15, l)) kinds[k].push([id, l]);
    });
    const scored = new Map();
    for (const [kind, rows] of Object.entries(kinds)) {
      const k = kind === 'H' ? 'H' : 'P';
      const cats = engine.get('HOT_CATS')[k].map(c => c.k);
      const ps = engine.call('hotPoolStats', rows.map(r => r[1]), cats);
      const sc = rows.map(([id, l]) => [id, engine.call('hotScoreFor', l, ps, k)]).sort((a, b) => a[1] - b[1]);
      sc.forEach(([id], i) => scored.set(id, sc.length > 1 ? i / (sc.length - 1) : 0.5));
    }
    cache.set(date, scored); return scored;
  }
  return (ottoneuId, date) => {
    const who = identity.get(String(ottoneuId)); if (!who) return null;
    const s = pool(date); return s && s.has(who.mlbId) ? s.get(who.mlbId) : null;
  };
}

module.exports = { tagMove, makeHotPercentile };
