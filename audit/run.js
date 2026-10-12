#!/usr/bin/env node
// audit/run.js — Decision audit pipeline.
//   node audit/run.js [--force | --force=<phase>]
// Phases checkpoint to audit/cache/. See docs/superpowers/specs/2026-10-11-decision-audit-design.md
const fs = require('fs'); const path = require('path'); const crypto = require('crypto');
const { loadEngine } = require('./lib/engine');
const { parseTransactions, buildMoves, parseCSVLine } = require('./lib/moves');
const { replayRosters, diffAgainstSnapshot, makeTenureEnd: makeStintEnd } = require('./lib/stints');
const g = require('./lib/gitdata');
const { fetchDay, seasonDays, sumWindow } = require('./lib/stats');
const { buildIdentity } = require('./lib/identity');
const { seasonContext, moveResult, inSeason } = require('./lib/result');
const { makeValuer, moveProcess } = require('./lib/process');
const { undoMove } = require('./lib/counterfactual');
const { tagMove, makeHotPercentile } = require('./lib/tags');
const { buildCards } = require('./lib/review');
const { runPhases } = require('./lib/phases');

const ROOT = path.join(__dirname, '..');
const CACHE = path.join(__dirname, 'cache');
const MY_TEAM = '10759';
const arg = process.argv.find(a => a.startsWith('--force'));
const force = !arg ? null : arg === '--force' ? true : arg.split('=')[1];
const read = p => fs.readFileSync(path.join(ROOT, p), 'utf8');
const hashOf = (...parts) => crypto.createHash('sha1').update(parts.join('\u0000')).digest('hex');
const headSha = p => (g.fileHistory(p).at(-1) || {}).sha || '';

function csvRows(text) {
  const L = text.replace(/\r/g, '').trim().split('\n'); const H = parseCSVLine(L[0]);
  return L.slice(1).map(l => { const v = parseCSVLine(l); const r = {}; H.forEach((h, i) => { r[h] = v[i]; }); return r; });
}

const standingsStats = r => ({ R: +r.R, HR: +r.HR, OBP: +r.OBP, SLG: +r.SLG, SO: +r.K, HR9: +(r['HR/9'] ?? r.HR9), ERA: +r.ERA, WHIP: +r.WHIP });

// Final standings per season from data/standings-final-<season>.csv (TeamIDs included).
function finalStandings(engine, season) {
  const f = `data/standings-final-${season}.csv`;
  if (!fs.existsSync(path.join(ROOT, f))) return null;
  return csvRows(read(f)).map(r => ({ teamId: r.TeamID, team: r.Team, ip: engine.call('parseIPInnings', r.IP) || 1500, stats: standingsStats(r) }));
}

// Per-player daily rows, so any window is a quick filter + sumWindow.
function makeStatsIndex(seasons) {
  const byPlayer = new Map();   // 'h|id' -> [[date, row]]
  const seasonIds = {};         // season -> {h:Set, p:Set}
  for (const s of seasons) {
    seasonIds[s] = { h: new Set(), p: new Set() };
    for (const d of seasonDays(s)) {
      const f = path.join(CACHE, 'stats', d + '.json');
      if (!fs.existsSync(f)) continue;
      const day = JSON.parse(fs.readFileSync(f, 'utf8'));
      for (const grp of ['h', 'p']) for (const row of day[grp]) {
        const k = grp + '|' + row[0];
        if (!byPlayer.has(k)) byPlayer.set(k, []);
        byPlayer.get(k).push([d, row]);
        seasonIds[s][grp].add(row[0]);
      }
    }
  }
  const window = (mlbId, grp, a, b) => {
    const rows = (byPlayer.get(grp + '|' + mlbId) || []).filter(([d]) => d >= a && d < b).map(([, row]) => ({ [grp]: [row] }));
    return rows.length ? sumWindow(rows.map(r => ({ h: r.h || [], p: r.p || [] })), mlbId, grp) : null;
  };
  const dayFiles = () => {   // reconstruct day files (identity building)
    const byDate = new Map();
    for (const [k, rows] of byPlayer) { const grp = k[0]; for (const [d, row] of rows) { if (!byDate.has(d)) byDate.set(d, { h: [], p: [] }); byDate.get(d)[grp].push(row); } }
    return byDate;
  };
  return { window, seasonIds, dayFiles };
}

function makeLookup(stats, ident, hint) {
  return (id, a, b) => {
    const who = ident.get(String(id));
    if (!who) return { type: hint[id] || 'H', line: null };
    return { type: who.group === 'p' ? 'P' : 'H', line: stats.window(who.mlbId, who.group, a, b) };
  };
}

(async () => {
  const engine = loadEngine();
  const txText = read('data/transactions.csv');
  const txs = parseTransactions(txText);
  const seasons = [...new Set(buildMoves(txs).map(m => m.season))].filter(s => s <= 2026).sort();
  let statsIdx = null;
  const stats = () => (statsIdx = statsIdx || makeStatsIndex(seasons));

  const phases = [
    { name: 'snapshots', inputsHash: () => hashOf(headSha('data/roster.csv'), headSha('data/proj_hitting.csv'), headSha('data/standings.csv')),
      run: async () => ({ roster: g.fileHistory('data/roster.csv'), hit: g.fileHistory('data/proj_hitting.csv'), pit: g.fileHistory('data/proj_pitching.csv'), standings: g.fileHistory('data/standings.csv') }) },

    { name: 'moves', inputsHash: () => hashOf(txText),
      run: async (r) => {
        const { stints, rosterAt } = replayRosters(txs);
        const diffs = r.snapshots.roster.filter((_, i, a) => i % 30 === 0 || i === a.length - 1).map(s => {
          const rows = csvRows(g.fileAt(s.sha, 'data/roster.csv')).map(x => ({ ottoneuId: x['ottoneu ID'], teamId: x.TeamID }));
          const d = diffAgainstSnapshot(rosterAt(s.date + 'T23:59:59'), rows);
          return { date: s.date, missing: d.missing.length, extra: d.extra.length, wrongTeam: d.wrongTeam.length };
        });
        const teams = {}; txs.forEach(t => { teams[t.teamId] = { name: t.team }; });
        return { moves: buildMoves(txs), stints, teams, snapshotDiffs: diffs };
      } },

    { name: 'stats', inputsHash: () => hashOf(seasons.join(',')),
      run: async () => {
        let n = 0;
        for (const s of seasons) for (const d of seasonDays(s)) { await fetchDay(d, CACHE); if (++n % 50 === 0) console.log(`  stats ${d}`); }
        return { days: n };
      } },

    { name: 'grade', inputsHash: () => hashOf(txText, headSha('data/roster.csv'), headSha('data/proj_hitting.csv'), read('shared.js'), 'v1'),
      run: async (r) => {
        const { moves, stints } = r.moves;
        const st = stats();
        // Position hints from roster snapshots (P if no hitting position).
        const hint = {};
        r.snapshots.roster.filter((_, i, a) => i % 20 === 0 || i === a.length - 1).forEach(s =>
          csvRows(g.fileAt(s.sha, 'data/roster.csv')).forEach(x => { hint[x['ottoneu ID']] = engine.call('inferPlayerType', x['Position(s)']); }));
        const players = [...new Map(stints.map(s => [s.ottoneuId, { ottoneuId: s.ottoneuId, player: s.player, hint: hint[s.ottoneuId] }])).values()];
        const ident = buildIdentity([...st.dayFiles().values()], players);
        const lookup = makeLookup(st, ident.map, hint);
        const stintEnd = makeStintEnd(stints);
        const valuer = makeValuer(engine, { ...r.snapshots, read: g.fileAt });

        const ctxBySeason = {};
        for (const s of seasons) {
          const final = finalStandings(engine, s);
          if (!final) continue;
          const a = `${s}-03-28`, b = `${s}-09-28`;
          const sStints = stints.filter(x => x.start < b && (!x.end || x.end > a));
          const stintLines = sStints.map(x => lookup(x.ottoneuId, x.start < a ? a : x.start, x.end && x.end < b ? x.end : b)).filter(x => x.line);
          const rosteredMlb = new Set(sStints.map(x => ident.map.get(x.ottoneuId)?.mlbId).filter(Boolean));
          const fa = [];
          for (const grp of ['h', 'p']) st.seasonIds[s][grp].forEach(id => {
            if (!rosteredMlb.has(id)) fa.push({ type: grp === 'p' ? 'P' : 'H', line: st.window(id, grp, a, b) });
          });
          ctxBySeason[s] = seasonContext(engine, { finalTeams: final, stintLines, freeAgentLines: fa });
        }
        const graded = moves.map(m => {
          const ctx = ctxBySeason[m.season];
          const result = ctx ? moveResult(engine, ctx, m, lookup, id => stintEnd(id, m.teamId, m.date)) : null;
          const proc = moveProcess(engine, valuer, m);
          return { ...m, process: proc, result, luck: proc === null || result === null ? null : result - proc };
        });
        return { graded, ctxBySeason, hint, identity: [...ident.map.entries()],
          report: { unmatched: ident.unmatched.map(u => u.player), ambiguous: ident.ambiguous.map(x => x.player) } };
      } },

    { name: 'standings', inputsHash: () => hashOf(txText, 'v1'),
      run: async (r) => {
        const st = stats();
        const ident = new Map(r.grade.identity);
        const lookup = makeLookup(st, ident, r.grade.hint);
        const stintEnd = makeStintEnd(r.moves.stints);
        const valuer = makeValuer(engine, { ...r.snapshots, read: g.fileAt });
        const byMove = {}; const jointCuts = {};
        for (const s of seasons) {
          const final = finalStandings(engine, s); const ctx = r.grade.ctxBySeason[s];
          if (!final || !ctx) continue;
          const seasonMoves = r.grade.graded.filter(x => x.season === s && x.kind !== 'auction' && inSeason(x.date));
          for (const m of seasonMoves) {
            const moveEnd = id => stintEnd(id, m.teamId, m.date);
            const d = undoMove(engine, ctx, final, m, lookup, { moveEnd });
            let fragile = null;
            if (d.decisive) {
              fragile = 'unchecked';
              const p0 = m.in[0] || m.out[0];
              const v = s === 2026 && p0 ? valuer.valuesAsOf(m.date) : null;
              const benchId = v ? v.benchBest(m.teamId, lookup(p0.ottoneuId, m.date, m.date).type, p0.ottoneuId) : null;
              if (benchId) {
                const tough = undoMove(engine, ctx, final, m, lookup, { moveEnd, replacementLine: () => lookup(benchId, m.date, `${s}-09-28`).line });
                fragile = !tough.decisive;
              }
            }
            byMove[m.id] = { standings: d.get(m.teamId) || null, decisive: d.decisive, fragile };
          }
          // Joint: all of a team's in-season cuts undone together.
          jointCuts[s] = {};
          for (const teamId of final.map(t => t.teamId)) {
            const cuts = seasonMoves.filter(x => x.teamId === teamId && x.kind === 'cut');
            if (!cuts.length) continue;
            const cutDate = new Map(); cuts.forEach(c => c.out.forEach(p => cutDate.set(p.ottoneuId, c.date)));
            const combined = { kind: 'cut', season: s, date: cuts[0].date, teamId, in: [], out: cuts.flatMap(c => c.out) };
            jointCuts[s][teamId] = undoMove(engine, ctx, final, combined, (id, a, b) => lookup(id, cutDate.get(id) || a, b)).get(teamId);
          }
        }
        return { byMove, jointCuts, seasonsWithoutStandings: seasons.filter(s => !finalStandings(engine, s)) };
      } },

    { name: 'tags', inputsHash: () => hashOf(txText, headSha('data/standings.csv'), 'v1'),
      run: async (r) => {
        const st = stats();
        const ident = new Map(r.grade.identity); const hint = r.grade.hint;
        const hotPctl = makeHotPercentile(engine, st.dayFiles(), ident);
        const prospects = new Set(csvRows(read('data/prospects.csv')).map(x => engine.call('normalizeName', x.Name || '')));
        const nameOf = {}; r.moves.stints.forEach(s => { nameOf[s.ottoneuId] = s.player; });
        const nameToId = {}; Object.entries(r.moves.teams).forEach(([id, t]) => { nameToId[t.name] = id; });
        const rankCache = new Map();
        const ranked = date => {
          if (rankCache.has(date)) return rankCache.get(date);
          const snap = g.latestOnOrBefore(r.snapshots.standings, date);
          const out = snap ? engine.call('buildStandings', csvRows(g.fileAt(snap.sha, 'data/standings.csv'))
            .map(x => ({ teamId: nameToId[x.Team] || x.Team, stats: standingsStats(x) }))) : null;
          rankCache.set(date, out); return out;
        };
        const env = {
          hotPctl,
          isProspect: id => prospects.has(engine.call('normalizeName', nameOf[id] || '')) && !ident.has(String(id)),
          typeOf: id => (ident.get(String(id))?.group === 'p' ? 'P' : hint[id] || 'H'),
          rankAt: (teamId, date) => { const s = ranked(date); if (!s) return null; const i = s.findIndex(t => t.teamId === teamId); return i < 0 ? null : i + 1; },
          weakestCatGroup: (teamId, date) => {
            const s = ranked(date); const t = s && s.find(x => x.teamId === teamId); if (!t) return null;
            const worst = Object.entries(t.ranks).sort((a, b) => a[1] - b[1])[0][0];
            return ['OBP', 'SLG', 'HR', 'R'].includes(worst) ? 'H' : 'P';
          },
        };
        return Object.fromEntries(r.grade.graded.map(m => [m.id, tagMove(m, env)]));
      } },

    { name: 'write', inputsHash: () => hashOf(String(Date.now())),   // always rewrite outputs
      run: async (r) => {
        const moves = r.grade.graded.map(m => ({ ...m, tags: r.tags[m.id] || [], ...(r.standings.byMove[m.id] || { standings: null, decisive: false, fragile: null }) }));
        const audit = {
          generated: new Date().toISOString(), myTeamId: MY_TEAM, seasons, teams: r.moves.teams, moves,
          jointCuts: r.standings.jointCuts,
          approximations: [
            'Stats count while a player is rostered — Ottoneu lineups are not in the data, so bench players are overstated.',
            'Each move is measured alone against what actually happened; moves interact, so individual impacts never add up.',
            'Replacement for an undone pickup is the averaged top free-agent production that season; an add paired with a cut restores the cut player instead.',
            'Process grades exist only from 2026-05-24 (first saved projections) to the end of the 2026 season.',
          ],
          report: { moves: moves.length, unmatched: r.grade.report.unmatched, ambiguous: r.grade.report.ambiguous,
            snapshotDiffs: r.moves.snapshotDiffs, seasonsWithoutStandings: r.standings.seasonsWithoutStandings },
        };
        fs.writeFileSync(path.join(ROOT, 'data/audit.json'), JSON.stringify(audit));
        const season = Math.max(...seasons);
        fs.writeFileSync(path.join(ROOT, 'data/review.json'), JSON.stringify({ season, generated: audit.generated, cards: buildCards(audit, season) }));
        return { ok: true };
      } },
  ];

  await runPhases(phases, { cacheDir: CACHE, force });
  const rep = JSON.parse(read('data/audit.json')).report;
  console.log(`\nmoves ${rep.moves} · unmatched ${rep.unmatched.length} · ambiguous ${rep.ambiguous.length} · seasons without standings: ${rep.seasonsWithoutStandings.join(',') || 'none'}`);
  console.log('snapshot cross-check:', rep.snapshotDiffs.map(d => `${d.date} m${d.missing}/x${d.extra}/w${d.wrongTeam}`).join(' '));
  if (rep.unmatched.length) console.log('unmatched (first 30):', rep.unmatched.slice(0, 30).join(', '));
})().catch(e => { console.error(e); process.exit(1); });
