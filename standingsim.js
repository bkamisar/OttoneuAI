// ── STANDINGS FINISH ODDS ─────────────────────────────────────────────────────
// Monte Carlo odds of each team's final standings place, plus data-driven
// "paths" up the table. Spec: docs/superpowers/specs/2026-09-19-standings-odds-
// design.md. Model notes: MODEL.md §3b.
//
// Team-level simulation. Each run adds noise — luck plus projection error — to
// every team's projected category stats for the simulated period, then either
// blends them with current actuals through blendStats ('ros' mode) or uses them
// as the whole season ('full' mode), and ranks with buildStandings.
// Depends on shared.js: CATS, LOWER_BETTER, IP_MAX, blendStats, buildStandings.

// Luck: sampling variance over the playing time being simulated.
const SIM_LUCK = {
  D_HR: 1.0,          // team HR count variance / mean (≈ Poisson)
  D_R: 2.0,           // runs cluster within innings → overdispersed
  D_SO: 1.0,
  SLG_AB_SD: 0.88,    // SD of total bases per AB at a ~.420 SLG
  AB_PER_PA: 0.89,    // fallback when a projection carries no _totAB
  ERA_IP_SD: 0.9,     // SD of runs allowed per inning
  WHIP_IP_SD: 1.15,   // SD of baserunners per inning
};

// Projection error: a one-SD FULL-SEASON team miss. Counting categories are a
// fraction of the period's projected count; rate categories are absolute.
const SIM_PROJ_ERR = { HR: 0.10, R: 0.06, SO: 0.07, OBP: 0.008, SLG: 0.015, ERA: 0.30, WHIP: 0.035, HR9: 0.12 };
const SIM_ERR_RHO = 0.6;                          // share of a side's error that is team-wide
const SIM_ERROR_MULT = { ros: 0.75, full: 1.5 };  // RoS has absorbed 5 months of data; a full year adds injuries and churn
const SIM_DEFAULT_RUNS = 10000;
const SIM_PATH_MIN_ODDS = 0.01;   // below this, too few runs to describe a path honestly
const SIM_PATH_MIN_DELTA = 0.3;   // category-point moves smaller than this aren't reported
const SIM_HIT_CATS = { OBP: true, SLG: true, HR: true, R: true };

// Seeded RNG: mulberry32 uniforms + Box–Muller normals. The engine never uses
// Math.random, so a given seed and data set always give the same odds.
function simRng(seed) {
  let a = seed >>> 0;
  let spare = null;
  function uni() {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  function normal() {
    if (spare !== null) { const s = spare; spare = null; return s; }
    let u = 0;
    while (u === 0) u = uni();
    const v = uni();
    const r = Math.sqrt(-2 * Math.log(u));
    spare = r * Math.sin(2 * Math.PI * v);
    return r * Math.cos(2 * Math.PI * v);
  }
  return { uni: uni, normal: normal };
}

// The playing time the noise is sized on — only what actually reaches the
// final line. In 'ros' mode pitching is capped exactly as blendStats caps it
// (IP_MAX − innings already thrown), so luck is never sized on innings that
// won't count. ipScale is the fraction of projected innings that survive.
function simPeriod(curr, proj, mode) {
  const projIP = proj._ip || 0;
  const ip = (mode === 'ros' && curr)
    ? Math.min(projIP, Math.max(0, IP_MAX - (curr.ip || 0)))
    : projIP;
  const pa = proj._totPA || 0;
  return {
    pa: pa,
    ab: proj._totAB || pa * SIM_LUCK.AB_PER_PA,
    ip: ip,
    ipScale: projIP > 0 ? ip / projIP : 0,
  };
}

// Luck SD of each category's value over the period. Counting stats grow with
// volume (√count); rate stats shrink with it (1/√sample).
function simLuckSD(proj, period) {
  const L = SIM_LUCK;
  const pa = period.pa, ab = period.ab, ip = period.ip;
  const obp = Math.min(1, Math.max(0, proj.OBP || 0));
  const soEff = Math.max(0, (proj.SO || 0) * period.ipScale);
  return {
    HR:   Math.sqrt(L.D_HR * Math.max(0, proj.HR || 0)),
    R:    Math.sqrt(L.D_R  * Math.max(0, proj.R  || 0)),
    OBP:  pa > 0 ? Math.sqrt(obp * (1 - obp) / pa) : 0,
    SLG:  ab > 0 ? L.SLG_AB_SD / Math.sqrt(ab) : 0,
    SO:   Math.sqrt(L.D_SO * soEff),
    ERA:  ip > 0 ? 9 * L.ERA_IP_SD / Math.sqrt(ip) : 0,
    WHIP: ip > 0 ? L.WHIP_IP_SD / Math.sqrt(ip) : 0,
    HR9:  ip > 0 ? Math.sqrt(9 * Math.max(0, proj.HR9 || 0) / ip) : 0,
  };
}

// One simulated line for a team's period: projection + luck + projection error.
// Projection error is correlated within a side: one team-wide draw per side
// (hitting / pitching) carries SIM_ERR_RHO of the variance, signed so a
// positive draw is better in every category of that side.
function simDrawStats(proj, period, luck, errMult, luckMult, rng) {
  const out = Object.assign({}, proj);
  const E = SIM_PROJ_ERR;
  const a = Math.sqrt(SIM_ERR_RHO), b = Math.sqrt(1 - SIM_ERR_RHO);
  const zSide = { H: rng.normal(), P: rng.normal() };
  const soEff = Math.max(0, (proj.SO || 0) * period.ipScale);
  const errScale = {
    HR: E.HR * Math.max(0, proj.HR || 0),
    R:  E.R  * Math.max(0, proj.R  || 0),
    SO: E.SO * soEff,
    OBP: E.OBP, SLG: E.SLG, ERA: E.ERA, WHIP: E.WHIP, HR9: E.HR9,
  };
  CATS.forEach(cat => {
    const side = SIM_HIT_CATS[cat] ? 'H' : 'P';
    const zCat = rng.normal(), zLuck = rng.normal();   // always drawn: keeps the RNG stream aligned
    if (side === 'P' && proj._pitchingValid === false) return;
    const better = LOWER_BETTER.has(cat) ? -1 : 1;
    let delta = errMult * errScale[cat] * (a * zSide[side] + b * zCat) * better
              + luckMult * luck[cat] * zLuck;
    // blendStats multiplies the projected SO by ipScale; pre-divide so the
    // noise lands at its intended size on the innings that count.
    if (cat === 'SO') delta = period.ipScale > 0 ? delta / period.ipScale : 0;
    const v = (proj[cat] || 0) + delta;
    out[cat] = Number.isFinite(v) ? v : (proj[cat] || 0);
  });
  out.HR = Math.max(0, out.HR || 0);
  out.R  = Math.max(0, out.R  || 0);
  out.SO = Math.max(0, out.SO || 0);
  out.OBP = Math.min(1, Math.max(0, out.OBP || 0));
  out.SLG  = Math.max(0, out.SLG  || 0);
  out.ERA  = Math.max(0, out.ERA  || 0);
  out.WHIP = Math.max(0, out.WHIP || 0);
  out.HR9  = Math.max(0, out.HR9  || 0);
  return out;
}

// Finishing-place spans with ties on total points. `standings` is
// buildStandings output (sorted by points desc). A team tied across places
// lo..hi gets 1/(hi−lo+1) credit for each of them, so every team's odds and
// every place's odds still sum to 1.
function simPlaceSpans(standings) {
  const spans = {};
  let i = 0;
  while (i < standings.length) {
    let j = i;
    while (j + 1 < standings.length && standings[j + 1].points === standings[i].points) j++;
    for (let k = i; k <= j; k++) spans[standings[k].name] = { lo: i, hi: j };
    i = j + 1;
  }
  return spans;
}

function simNewAcc(names) {
  const sum = {};
  names.forEach(nm => { sum[nm] = {}; CATS.forEach(c => { sum[nm][c] = 0; }); });
  return { w: 0, sum: sum };
}

// Adds one run's category-point changes vs the baseline, for every team,
// weighted by how much credit the condition earned in this run.
function simAccumulate(acc, w, ranks, baseRanks) {
  acc.w += w;
  for (const team in acc.sum) {
    const s = acc.sum[team], r = ranks[team], r0 = baseRanks[team];
    CATS.forEach(cat => { s[cat] += w * ((r[cat] || 0) - (r0[cat] || 0)); });
  }
}

// Mean category-point moves in the runs where the condition held. null when
// the condition is too rare to average honestly.
function simPath(acc, team, rival, n) {
  if (!acc || acc.w / n < SIM_PATH_MIN_ODDS) return null;
  const mean = (t, cat) => acc.sum[t][cat] / acc.w;
  const gains = CATS.map(cat => ({ cat: cat, delta: mean(team, cat) }))
    .filter(g => g.delta >= SIM_PATH_MIN_DELTA)
    .sort((x, y) => y.delta - x.delta)
    .slice(0, 3);
  const rivals = rival
    ? CATS.map(cat => ({ team: rival, cat: cat, delta: mean(rival, cat) }))
        .filter(r => r.delta <= -SIM_PATH_MIN_DELTA)
        .sort((x, y) => x.delta - y.delta)
        .slice(0, 3)
    : [];
  return { odds: acc.w / n, gains: gains, rivals: rivals };
}

// teams: [{ name, curr (parseCurrStandings row or null), proj (computeTeamStats shape) }]
// opts:  { mode: 'ros'|'full', n, seed, errorMult, luckMult }
function simulateStandings(teams, opts) {
  opts = opts || {};
  const mode = opts.mode === 'full' ? 'full' : 'ros';
  const n = opts.n || SIM_DEFAULT_RUNS;
  const rng = simRng(opts.seed == null ? 1 : opts.seed);
  const errMult  = opts.errorMult != null ? opts.errorMult : SIM_ERROR_MULT[mode];
  const luckMult = opts.luckMult  != null ? opts.luckMult  : 1;
  const names = teams.map(t => t.name);
  const T = names.length;
  if (!T) return { n: n, mode: mode, baseline: [], teams: {} };

  function finalize(t, stats) {
    return (mode === 'ros' && t.curr) ? blendStats(t.curr, stats) : stats;
  }
  const prep = teams.map(t => {
    const period = simPeriod(t.curr, t.proj, mode);
    return { t: t, period: period, luck: simLuckSD(t.proj, period) };
  });

  // Zero-noise pass: the "most likely" standings the paths are measured from.
  const baseline = buildStandings(teams.map(t => ({ name: t.name, stats: finalize(t, t.proj) })));
  const baseRanks = {};
  baseline.forEach(t => { baseRanks[t.name] = t.ranks; });
  const leader = baseline[0].name;
  const baseTop3 = baseline.slice(0, 3).map(t => t.name);

  const place = {}, ptsSum = {}, accFirst = {}, accTop3 = {}, displaced = {};
  names.forEach(nm => {
    place[nm] = new Array(T).fill(0);
    ptsSum[nm] = 0;
    displaced[nm] = {};
    if (nm !== leader) accFirst[nm] = simNewAcc(names);
    if (baseTop3.indexOf(nm) === -1) accTop3[nm] = simNewAcc(names);
  });

  for (let run = 0; run < n; run++) {
    const st = buildStandings(prep.map(p => ({
      name: p.t.name,
      stats: finalize(p.t, simDrawStats(p.t.proj, p.period, p.luck, errMult, luckMult, rng)),
    })));
    const spans = simPlaceSpans(st);
    const ranks = {};
    st.forEach(t => { ranks[t.name] = t.ranks; ptsSum[t.name] += t.points; });

    const top3Credit = {};
    names.forEach(nm => {
      const s = spans[nm], share = 1 / (s.hi - s.lo + 1);
      for (let k = s.lo; k <= s.hi; k++) place[nm][k] += share;
      top3Credit[nm] = Math.max(0, Math.min(s.hi, 2) - s.lo + 1) * share;
    });
    names.forEach(nm => {
      const s = spans[nm];
      const wFirst = s.lo === 0 ? 1 / (s.hi - s.lo + 1) : 0;
      if (wFirst > 0 && accFirst[nm]) simAccumulate(accFirst[nm], wFirst, ranks, baseRanks);
      const w3 = top3Credit[nm];
      if (w3 > 0 && accTop3[nm]) {
        simAccumulate(accTop3[nm], w3, ranks, baseRanks);
        baseTop3.forEach(x => { displaced[nm][x] = (displaced[nm][x] || 0) + w3 * (1 - top3Credit[x]); });
      }
    });
  }

  const result = { n: n, mode: mode, baseline: baseline, teams: {} };
  names.forEach(nm => {
    const p = place[nm].map(c => c / n);
    // For the top-3 path, the rival is the baseline top-3 team this team most
    // often pushes out.
    let rival3 = null, most = 0;
    baseTop3.forEach(x => { const v = displaced[nm][x] || 0; if (v > most) { most = v; rival3 = x; } });
    result.teams[nm] = {
      place: p,
      top3: p[0] + (p[1] || 0) + (p[2] || 0),
      avgPts: ptsSum[nm] / n,
      paths: {
        first: accFirst[nm] ? simPath(accFirst[nm], nm, leader, n) : null,
        top3:  accTop3[nm]  ? simPath(accTop3[nm],  nm, rival3, n) : null,
      },
    };
  });
  return result;
}
