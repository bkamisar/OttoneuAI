#!/usr/bin/env node
// audit/run.js — Decision audit pipeline.
//   node audit/run.js [--force | --force=<phase>]
// Phases checkpoint to audit/cache/. Specs: docs/superpowers/specs/2026-10-11-decision-audit-design.md (v1),
// 2026-10-12-decision-audit-v2-design.md (v2: counted production, offseason cap moves)
const fs = require('fs'); const path = require('path'); const crypto = require('crypto');
const { loadEngine } = require('./lib/engine');
const { parseTransactions, buildMoves, parseCSVLine } = require('./lib/moves');
const { replayRosters, diffAgainstSnapshot, makeTenureEnd: makeStintEnd, countTenures } = require('./lib/stints');
const g = require('./lib/gitdata');
const { fetchDay, seasonDays, sumWindow } = require('./lib/stats');
const { buildIdentity } = require('./lib/identity');
const { seasonContext, countedResult } = require('./lib/result');
const { makeValuer, moveProcess } = require('./lib/process');
const { parseProduction, makeCounted, teamsWithPlayer } = require('./lib/production');
const { annotateOffseason } = require('./lib/offseason');
const { ptsContributed, titleDeciding, teamTotalsFromLines, isCloseCall } = require('./lib/contributed');
const { tagMove, makeHotPercentile } = require('./lib/tags');
const { buildCards } = require('./lib/review');
const { managerKey, managerName } = require('./lib/eras');
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
  return csvRows(read(f)).map(r => ({ teamId: r.TeamID, team: r.Team, ip: engine.call('parseIPInnings', r.IP) || 1500, points: +r.Points, stats: standingsStats(r) }));
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
  const prodText = read('data/teamproduction.csv');
  const seasons = [...new Set(buildMoves(txs).map(m => m.season))].filter(s => s <= 2026).sort();
  let statsIdx = null;
  const stats = () => (statsIdx = statsIdx || makeStatsIndex(seasons));

  const phases = [
    { name: 'snapshots', inputsHash: () => hashOf(headSha('data/roster.csv'), headSha('data/proj_hitting.csv'), headSha('data/standings.csv')),
      run: async () => ({ roster: g.fileHistory('data/roster.csv'), hit: g.fileHistory('data/proj_hitting.csv'), pit: g.fileHistory('data/proj_pitching.csv'), standings: g.fileHistory('data/standings.csv') }) },

    { name: 'moves', inputsHash: () => hashOf(txText, prodText, 'v2'),
      run: async (r) => {
        const { stints, rosterAt } = replayRosters(txs);
        const diffs = r.snapshots.roster.filter((_, i, a) => i % 30 === 0 || i === a.length - 1).map(s => {
          const rows = csvRows(g.fileAt(s.sha, 'data/roster.csv')).map(x => ({ ottoneuId: x['ottoneu ID'], teamId: x.TeamID }));
          const d = diffAgainstSnapshot(rosterAt(s.date + 'T23:59:59'), rows);
          return { date: s.date, missing: d.missing.length, extra: d.extra.length, wrongTeam: d.wrongTeam.length };
        });
        const teams = {}; txs.forEach(t => { teams[t.teamId] = { name: t.team }; });
        return { moves: annotateOffseason(buildMoves(txs)), stints, teams, snapshotDiffs: diffs };
      } },

    { name: 'stats', inputsHash: () => hashOf(seasons.join(',')),
      run: async () => {
        let n = 0;
        for (const s of seasons) for (const d of seasonDays(s)) { await fetchDay(d, CACHE); if (++n % 50 === 0) console.log(`  stats ${d}`); }
        return { days: n };
      } },

    { name: 'grade', inputsHash: () => hashOf(txText, prodText, headSha('data/roster.csv'), headSha('data/proj_hitting.csv'), read('shared.js'), read('audit/lib/result.js'), 'v2'),
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
        // v2: what actually counted for each team (Ottoneu team production).
        const prod = parseProduction(prodText);
        const paRatio = (id, s) => {
          const who = ident.map.get(String(id)); if (!who || who.group !== 'h') return null;
          const l = st.window(who.mlbId, 'h', `${s}-03-01`, `${s}-10-15`); return l && l.ab ? l.pa / l.ab : null;
        };
        const counted = makeCounted(prod.rows, paRatio);
        const stintCount = (id, team, s) => countTenures(stints, id, team, s);
        const teamsWith = (id, s) => teamsWithPlayer(prod.rows, id, s);

        const ctxBySeason = {};
        for (const s of seasons) {
          const final = finalStandings(engine, s);
          if (!final) continue;
          const a = `${s}-03-28`, b = `${s}-09-28`;
          const sStints = stints.filter(x => x.start < b && (!x.end || x.end > a));
          const stintLines = prod.rows.filter(x => x.season === s).map(x => counted(x.ottoneuId, x.teamId, s)).filter(x => x.line);
          const rosteredMlb = new Set(sStints.map(x => ident.map.get(x.ottoneuId)?.mlbId).filter(Boolean));
          const fa = [];
          for (const grp of ['h', 'p']) st.seasonIds[s][grp].forEach(id => {
            if (!rosteredMlb.has(id)) fa.push({ type: grp === 'p' ? 'P' : 'H', line: st.window(id, grp, a, b) });
          });
          ctxBySeason[s] = seasonContext(engine, { finalTeams: final, stintLines, freeAgentLines: fa });
        }
        const graded = moves.map(m => {
          const ctx = ctxBySeason[m.season];
          const cr = ctx ? countedResult(engine, ctx, m, { counted, teamsWith, tenureEnd: stintEnd, stintCount }) : { result: null, production: null, combinedStints: false };
          const proc = m.kind === 'reset' ? null : moveProcess(engine, valuer, m);
          return { ...m, process: proc, result: cr.result, production: cr.production ?? null, combinedStints: cr.combinedStints,
            // Luck (result − process) is off in v2: results are lineup-only, process grades are
            // projection-based and assume every player plays, so the gap measures bench time, not luck.
            luck: null };
        });
        const paRatios = {};
        prod.rows.filter(x => x.group === 'H').forEach(x => { paRatios[x.season + '|' + x.ottoneuId] = paRatio(x.ottoneuId, x.season); });
        return { graded, ctxBySeason, hint, identity: [...ident.map.entries()], prodRows: prod.rows, paRatios,
          report: { unmatched: ident.unmatched.map(u => u.player), ambiguous: ident.ambiguous.map(x => x.player) } };
      } },

    { name: 'standings', inputsHash: () => hashOf(txText, prodText, read('audit/lib/contributed.js'), 'v4'),
      run: async (r) => {
        // v2: roto points each player's COUNTED stats were worth to the team that had them.
        const counted = makeCounted(r.grade.prodRows, (id, s) => r.grade.paRatios[s + '|' + id] || null);
        const byMove = {};
        for (const s of seasons) {
          const final = finalStandings(engine, s); if (!final) continue;
          const totals = {};
          final.forEach(t => { totals[t.teamId] = teamTotalsFromLines(r.grade.prodRows.filter(x => x.season === s && x.teamId === t.teamId).map(x => counted(x.ottoneuId, x.teamId, s))); });
          const memo = new Map();
          const pts = (id, team) => {
            const k = id + '|' + team;
            if (!memo.has(k)) memo.set(k, totals[team] ? ptsContributed(engine, final, team, counted(id, team, s), totals[team]) : 0);
            return memo.get(k);
          };
          for (const m of r.grade.graded.filter(x => x.season === s)) {
            // One signed piece per player, so a close call can be tested by dropping pieces.
            const pieces = [];
            if (m.kind === 'trade') {
              m.in.forEach(p => pieces.push(pts(p.ottoneuId, m.teamId)));
              m.out.forEach(p => pieces.push(-pts(p.ottoneuId, m.counterTeamId)));
            } else if (m.kind !== 'reset') {
              m.in.forEach(p => pieces.push(pts(p.ottoneuId, m.teamId)));
              m.out.forEach(p => teamsWithPlayer(r.grade.prodRows, p.ottoneuId, s)
                .filter(t => t.teamId !== m.teamId && t.acquired >= m.date).forEach(t => pieces.push(-pts(p.ottoneuId, t.teamId))));
            }
            const net = pieces.reduce((q, v) => q + v, 0);
            byMove[m.id] = { ptsContributed: net, titleDeciding: titleDeciding(final, m.teamId, net), closeCall: isCloseCall(final, m.teamId, pieces) };
          }
        }
        return { byMove, seasonsWithoutStandings: seasons.filter(s => !finalStandings(engine, s)) };
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
        // grade: what the move is judged on. Production for trades/cuts/adds (freed salary is only worth
        // what it later buys, and offseason cuts are free); value minus price for auction buys, where the
        // price IS the budget; 0 for salary resets (pure cap moves, judged in the winter summary).
        const gradeOf = m => (m.production == null ? null : m.kind === 'auction' ? m.result : m.kind === 'reset' ? 0 : m.production);
        // cash: one side of a trade received no players (Ottoneu's log doesn't show loans/cash).
        const moves = r.grade.graded.map(m => ({ ...m, grade: gradeOf(m), cash: m.kind === 'trade' && (!m.in.length || !m.out.length), manager: managerKey(m.teamId, m.date), tags: r.tags[m.id] || [], ...(r.standings.byMove[m.id] || { ptsContributed: null, titleDeciding: null, closeCall: false }) }));
        const managers = Object.fromEntries([...new Set(moves.map(m => m.manager))].map(k => [k, managerName(r.moves.teams, k)]));
        // Winter cap summary: what each team freed and spent between October and the auction.
        const winters = {};
        for (const m of moves) {
          const ws = (winters[m.season] = winters[m.season] || {});
          const w = (ws[m.teamId] = ws[m.teamId] || { freed: 0, resetSavings: 0, tradeSalary: 0, auctionSpend: 0, auctionReturn: 0 });
          if (m.phase !== 'offseason') continue;
          if (m.kind === 'cut') w.freed += m.out.reduce((q, p) => q + p.salary, 0);
          if (m.kind === 'reset') w.resetSavings += m.resetGrade;
          if (m.kind === 'trade') w.tradeSalary += m.capDelta || 0;
          if (m.kind === 'auction') { w.auctionSpend += m.in.reduce((q, p) => q + p.salary, 0); w.auctionReturn += m.result || 0; }
        }
        const audit = {
          generated: new Date().toISOString(), myTeamId: MY_TEAM, seasons, teams: r.moves.teams, managers, moves, winters,
          approximations: [
            'Results use what Ottoneu counted for each team (lineup-only stats), one line per player per team per season; players with two stints on a team in one season are combined and flagged.',
            'Hitter plate appearances are estimated from at-bats using the player\'s own MLB ratio that season.',
            'Points contributed = the team\'s final points minus its points with that player\'s counted stats removed. Nothing hypothetical is added back, so it measures what the stats were worth, not what a replacement would have done.',
            'Offseason (October to the auction) cuts are cap moves: full salary freed; a cut bought back by the same team at the auction is a salary reset graded on the salary change.',
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
  const out = JSON.parse(read('data/audit.json')); const rep = out.report;
  console.log('resets', out.moves.filter(m => m.kind === 'reset').length, '· title-deciding', out.moves.filter(m => m.titleDeciding).length,
    '· combined stints', out.moves.filter(m => m.combinedStints).length);
  console.log(`\nmoves ${rep.moves} · unmatched ${rep.unmatched.length} · ambiguous ${rep.ambiguous.length} · seasons without standings: ${rep.seasonsWithoutStandings.join(',') || 'none'}`);
  console.log('snapshot cross-check:', rep.snapshotDiffs.map(d => `${d.date} m${d.missing}/x${d.extra}/w${d.wrongTeam}`).join(' '));
  if (rep.unmatched.length) console.log('unmatched (first 30):', rep.unmatched.slice(0, 30).join(', '));
})().catch(e => { console.error(e); process.exit(1); });
