// audit/lib/moves.js
// Ottoneu transaction rows -> decisions ("moves"). One Move per team per
// decision: a trade produces one Move for each side, sharing tradeId.
const SWAP_WINDOW_MS = 30 * 60 * 1000;
const TRADE_GAP_MS = 60 * 1000;
const OPENING_DAY_MMDD = '03-28';

function parseCSVLine(line) {
  const out = []; let cur = ''; let q = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (q) { if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') q = false; else cur += c; }
    else if (c === '"') q = true; else if (c === ',') { out.push(cur); cur = ''; } else cur += c;
  }
  out.push(cur); return out;
}

function parseTransactions(text) {
  const lines = text.replace(/\r/g, '').trim().split('\n');
  const head = parseCSVLine(lines[0]);
  const txs = lines.slice(1).map(l => {
    const v = parseCSVLine(l); const r = {}; head.forEach((h, i) => { r[h] = v[i] ?? ''; });
    return {
      // Commissioner actions arrive as e.g. "add      (C)" -- same move, flagged.
      ts: r.date, date: r.date.slice(0, 10), type: r.type.trim().split(/\s+/)[0], commissioner: /\(C\)/.test(r.type), player: r.player,
      ottoneuId: String(r.ottoneuId), teamId: String(r.teamId), team: r.team,
      fromTeamId: r.fromTeamId ? String(r.fromTeamId) : '', fromTeam: r.fromTeam,
      salary: parseInt(String(r.salary).replace(/[$,]/g, ''), 10) || 0,
    };
  });
  // Ottoneu links the receiving team but not the from-team, so fill fromTeamId
  // from names (it shows current names everywhere, so names map 1:1 to ids).
  const idByName = new Map(txs.filter(t => t.teamId).map(t => [t.team, t.teamId]));
  txs.forEach(t => { if (!t.fromTeamId && t.fromTeam) t.fromTeamId = idByName.get(t.fromTeam) || ''; });
  return txs.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
}

// Offseason moves count toward the next season: Oct-Dec Y -> Y+1.
function seasonOf(date) {
  const y = +date.slice(0, 4), m = +date.slice(5, 7);
  return m >= 10 ? y + 1 : y;
}

const P = t => ({ player: t.player, ottoneuId: t.ottoneuId, salary: t.salary });
const ms = ts => new Date(ts + 'Z').getTime();

function buildMoves(txs) {
  const moves = []; let n = 0;
  const base = (t, kind, teamId) => ({
    id: 'm' + (++n), kind, season: seasonOf(t.date), ts: t.ts, date: t.date,
    teamId, counterTeamId: null, tradeId: null, in: [], out: [],
  });

  // Trades: 'move' rows between the same two teams, clustered when each row is
  // within TRADE_GAP_MS of the previous one (Ottoneu stamps one trade's rows a
  // second or two apart).
  const tradeGroups = [];
  const lastByPair = new Map();   // pair -> open group
  for (const t of txs.filter(x => x.type === 'move')) {
    const pair = [t.teamId, t.fromTeamId].sort().join('-');
    const g = lastByPair.get(pair);
    if (g && ms(t.ts) - ms(g[g.length - 1].ts) <= TRADE_GAP_MS) { g.push(t); continue; }
    const ng = [t]; tradeGroups.push(ng); lastByPair.set(pair, ng);
  }
  let tn = 0;
  for (const rows of tradeGroups) {
    const tradeId = 't' + (++tn);
    const [a, b] = [rows[0].teamId, rows[0].fromTeamId].sort();
    for (const [me, them] of [[a, b], [b, a]]) {
      const m = base(rows[0], 'trade', me);
      m.counterTeamId = them; m.tradeId = tradeId;
      m.in = rows.filter(r => r.teamId === me).map(P);
      m.out = rows.filter(r => r.fromTeamId === me).map(P);
      moves.push(m);
    }
  }

  // Adds / cuts, pairing same-team add+cut within the swap window (timestamp order).
  const addsCuts = txs.filter(x => x.type === 'add' || x.type === 'cut');
  const used = new Set();
  for (let i = 0; i < addsCuts.length; i++) {
    if (used.has(i)) continue;
    const t = addsCuts[i];
    let j = -1;
    for (let k = i + 1; k < addsCuts.length && ms(addsCuts[k].ts) - ms(t.ts) <= SWAP_WINDOW_MS; k++) {
      const u = addsCuts[k];
      if (!used.has(k) && u.teamId === t.teamId && u.type !== t.type) { j = k; break; }
    }
    used.add(i);
    if (j >= 0) {
      used.add(j);
      const add = t.type === 'add' ? t : addsCuts[j];
      const cut = t.type === 'cut' ? t : addsCuts[j];
      const m = base(t, 'swap', t.teamId); m.in = [P(add)]; m.out = [P(cut)];
      moves.push(m); continue;
    }
    const isAuction = t.type === 'add' && +t.date.slice(5, 7) === 3 && t.date.slice(5) < OPENING_DAY_MMDD;
    const m = base(t, t.type === 'cut' ? 'cut' : (isAuction ? 'auction' : 'add'), t.teamId);
    (t.type === 'add' ? m.in : m.out).push(P(t));
    moves.push(m);
  }
  return moves.sort((x, y) => (x.ts < y.ts ? -1 : x.ts > y.ts ? 1 : 0));
}

module.exports = { parseTransactions, buildMoves, seasonOf, parseCSVLine };
