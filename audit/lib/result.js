// audit/lib/result.js
// "Result" grades: what actually happened, in the suite's dollars.
// SGP denominators come from the real final standings; replacement is the
// averaged top free-agent cohort by actual production (same rule as shared.js
// FA baselines); $/SGP spreads the league pool over all rostered production.
const SEASON_START = '-03-28', SEASON_END = '-09-28';
const t = d => new Date(d + 'T00:00:00Z').getTime();

function fracOfSeason(season, start, end) {
  const s0 = t(season + SEASON_START), s1 = t(season + SEASON_END);
  const a = Math.max(s0, t(start)), b = Math.min(s1, end ? t(end) : s1);
  return b > a ? (b - a) / (s1 - s0) : 0;
}

function sgpOf(engine, ctx, type, line) {
  if (!line) return 0;
  const repl = ctx.repl[type];
  if (!repl) return 0;
  return engine.call('calcPlayerSGP', { type }, line, repl, ctx.sgpDenom, ctx.avgPA, ctx.avgIP);
}

function average(lines, fields) {
  if (!lines.length) return null;
  return Object.fromEntries(fields.map(f => [f, lines.reduce((s, l) => s + (l[f] || 0), 0) / lines.length]));
}

function seasonContext(engine, { finalTeams, stintLines, freeAgentLines }) {
  const sgpDenom = engine.call('calcSGPDenoms', finalTeams.map(x => x.stats));
  const avgPA = engine.get('PA_PER_SLOT') * engine.get('HITTER_SLOTS').length;
  const ips = finalTeams.map(x => x.ip).filter(Boolean);
  const avgIP = ips.length ? ips.reduce((a, b) => a + b, 0) / ips.length : engine.get('IP_MAX');
  // Same cohort rule as computeFABaselines: top N unrostered by valProxy, with a role floor.
  const cohort = (type, minVol, size, fields) => {
    const vol = type === 'H' ? 'pa' : 'ip';
    const pool = freeAgentLines.filter(x => x.type === type && x.line && (x.line[vol] || 0) >= minVol)
      .map(x => x.line)
      .sort((a, b) => engine.call('valProxy', { type }, b) - engine.call('valProxy', { type }, a))
      .slice(0, size);
    return average(pool, fields);
  };
  const repl = {
    H: cohort('H', engine.get('FA_MIN_PA'), engine.get('FA_COHORT_H'), ['pa', 'hr', 'r', 'obp', 'slg']),
    P: cohort('P', engine.get('FA_MIN_IP'), engine.get('FA_COHORT_P'), ['ip', 'so', 'era', 'whip', 'hr9']),
  };
  const ctx = { sgpDenom, avgPA, avgIP, repl, rate: 0 };
  const totalPos = stintLines.reduce((s, x) => s + Math.max(0, sgpOf(engine, ctx, x.type, x.line)), 0);
  const pool = engine.get('SALARY_POOL') - engine.get('NUM_TEAMS') * 40;   // $1 floor per roster spot
  ctx.rate = totalPos > 0 ? pool / totalPos : 0;
  return ctx;
}

function lineValue(engine, ctx, type, line) { return sgpOf(engine, ctx, type, line) * ctx.rate; }

const seasonEnd = s => s + SEASON_END;
const inSeason = d => d.slice(5) >= SEASON_START.slice(1) && d.slice(5) < SEASON_END.slice(1);

// lookup(ottoneuId, start, end) -> { type, line } for production in [start, end).
// moveEnd(ottoneuId) -> the date the player left the acquiring team (or null).
function moveResult(engine, ctx, move, lookup, moveEnd = () => null) {
  const s = move.season, d = move.date;
  const cutFactor = inSeason(d) ? 0.5 : 1;
  let total = 0;
  for (const p of move.in) {
    const end = moveEnd(p.ottoneuId) || seasonEnd(s);
    const { type, line } = lookup(p.ottoneuId, d, end);
    total += lineValue(engine, ctx, type, line) - p.salary * fracOfSeason(s, d, end);
  }
  for (const p of move.out) {
    const { type, line } = lookup(p.ottoneuId, d, seasonEnd(s));
    const lost = lineValue(engine, ctx, type, line);
    const freed = move.kind === 'trade' ? p.salary : p.salary * cutFactor;
    total += freed * fracOfSeason(s, d, null) - lost;
  }
  return total;
}

module.exports = { seasonContext, lineValue, fracOfSeason, moveResult, inSeason };
