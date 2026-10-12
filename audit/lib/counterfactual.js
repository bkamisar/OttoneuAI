// audit/lib/counterfactual.js
// Replay final standings with one move undone. Each move is evaluated alone
// against what actually happened (moves interact, so these never sum).
const IP_MAX = 1500;

function applyDelta(stats, ip, delta, teamPA) {
  const s = { ...stats }; let tip = ip;
  for (const { line, sign } of delta.H) {
    if (!line) continue;
    const pa = line.pa || 0;
    s.HR += sign * (line.hr || 0); s.R += sign * (line.r || 0);
    // Team PA held fixed: the player's PA displace (or are displaced by) team-average PA.
    s.OBP += sign * ((line.obp || 0) - stats.OBP) * pa / teamPA;
    s.SLG += sign * ((line.slg || 0) - stats.SLG) * pa / teamPA;
  }
  for (const { line, sign } of delta.P) {
    if (!line) continue;
    const lip = line.ip || 0; const newIp = tip + sign * lip;
    if (newIp <= 0) continue;
    for (const [k, f] of [['ERA', 'era'], ['WHIP', 'whip'], ['HR9', 'hr9']]) s[k] = (s[k] * tip + sign * (line[f] || 0) * lip) / newIp;
    s.SO += sign * (line.so || 0); tip = newIp;
  }
  if (tip > IP_MAX) { s.SO *= IP_MAX / tip; tip = IP_MAX; }
  return { stats: s, ip: tip };
}

const scaleRepl = (repl, type, line) => {
  if (!repl || !line) return null;
  const k = type === 'H' ? 'pa' : 'ip';
  const f = (repl[k] || 0) > 0 ? (line[k] || 0) / repl[k] : 0;
  return type === 'H'
    ? { pa: line.pa, hr: repl.hr * f, r: repl.r * f, obp: repl.obp, slg: repl.slg }
    : { ip: line.ip, so: repl.so * f, era: repl.era, whip: repl.whip, hr9: repl.hr9 };
};

const order = st => st.map(t => t.teamId);

function undoMove(engine, ctx, final, move, lookup, opts = {}) {
  const end = move.season + '-09-28';
  const deltas = new Map(final.map(t => [t.teamId, { H: [], P: [] }]));
  const push = (teamId, type, line, sign) => { if (deltas.has(teamId) && line) deltas.get(teamId)[type].push({ line, sign }); };
  const repl = (type, line) => (opts.replacementLine ? opts.replacementLine(type, line) : scaleRepl(ctx.repl[type], type, line));
  const winEnd = p => (opts.moveEnd && opts.moveEnd(p.ottoneuId)) || end;

  if (move.kind === 'trade') {
    for (const p of move.in) {
      const x = lookup(p.ottoneuId, move.date, winEnd(p));
      push(move.teamId, x.type, x.line, -1);
      push(move.counterTeamId, x.type, lookup(p.ottoneuId, move.date, end).line, +1);
    }
    for (const p of move.out) { const x = lookup(p.ottoneuId, move.date, end); push(move.teamId, x.type, x.line, +1); }
  } else {
    for (const p of move.in) {
      const x = lookup(p.ottoneuId, move.date, winEnd(p)); push(move.teamId, x.type, x.line, -1);
      if (move.kind !== 'swap') push(move.teamId, x.type, repl(x.type, x.line), +1);
    }
    for (const p of move.out) {
      const x = lookup(p.ottoneuId, move.date, move.kind === 'swap' ? winEnd(move.in[0]) : end);
      push(move.teamId, x.type, x.line, +1);
    }
  }

  const actual = engine.call('buildStandings', final.map(t => ({ teamId: t.teamId, stats: t.stats })));
  const cf = engine.call('buildStandings', final.map(t => ({ teamId: t.teamId, stats: applyDelta(t.stats, t.ip, deltas.get(t.teamId), ctx.avgPA).stats })));
  const pos = st => new Map(st.map((t, i) => [t.teamId, { pts: t.points, rank: i + 1 }]));
  const a = pos(actual), c = pos(cf);
  const out = new Map();
  for (const t of final) out.set(t.teamId, { dPts: a.get(t.teamId).pts - c.get(t.teamId).pts, dRank: c.get(t.teamId).rank - a.get(t.teamId).rank });
  out.decisive = isDecisive(order(actual), order(cf));
  return out;
}

function isDecisive(actualOrder, cfOrder) {
  if (actualOrder[0] !== cfOrder[0]) return true;
  const top3 = o => new Set(o.slice(0, 3));
  const a = top3(actualOrder), c = top3(cfOrder);
  return [...a].some(x => !c.has(x));
}

module.exports = { applyDelta, undoMove, isDecisive };
