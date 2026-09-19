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
