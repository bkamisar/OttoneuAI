// audit/lib/review.js
// Numbers for the league year-in-review cards. Commentary is written separately
// (data/review-commentary.json) by Claude after reading these.
const { managerKey, managerName, coversSeason } = require('./eras');

function buildCards(audit, season) {
  const mv = audit.moves.filter(m => m.season === season && m.result != null);
  // Labels and per-team totals go through manager eras (teams that changed hands split).
  const name = key => managerName(audit.teams, key);
  const mk = m => managerKey(m.teamId, m.date || '');
  const cards = [];
  const push = c => cards.push({ players: [], numbers: {}, ...c });
  // Cards rank on the grade (production for trades/cuts/adds, value minus price for auction buys);
  // after-salary results ride along as information.
  const g = m => (m.grade != null ? m.grade : m.result);

  // Trades: pair the two sides by tradeId.
  const trades = new Map();
  mv.filter(m => m.kind === 'trade').forEach(m => { if (!trades.has(m.tradeId)) trades.set(m.tradeId, []); trades.get(m.tradeId).push(m); });
  const tradeRows = [...trades.values()].filter(s => s.length === 2).map(([a, b]) => {
    const [w, l] = g(a) >= g(b) ? [a, b] : [b, a];
    return { w, l, margin: g(w) - g(l), both: g(a) > 0 && g(b) > 0 };
  });
  const fleece = [...tradeRows].sort((x, y) => y.margin - x.margin)[0];
  if (fleece) push({ id: 'trade-of-year', title: 'Fleecing of the Year', teamId: fleece.w.teamId, team: name(mk(fleece.w)),
    numbers: { margin: Math.round(fleece.margin), winner: Math.round(g(fleece.w)), loser: Math.round(g(fleece.l)), victim: name(mk(fleece.l)),
      winnerAfterSalary: Math.round(fleece.w.result), loserAfterSalary: Math.round(fleece.l.result),
      winnerProduction: Math.round(fleece.w.production || 0), loserProduction: Math.round(fleece.l.production || 0) },
    players: fleece.w.in.map(p => p.player), sent: fleece.w.out.map(p => p.player) });
  const winwin = tradeRows.filter(r => r.both).sort((x, y) => (g(y.w) + g(y.l)) - (g(x.w) + g(x.l)))[0];
  if (winwin) push({ id: 'win-win', title: 'Trade of the Year (everybody won)', teamId: winwin.w.teamId, team: name(mk(winwin.w)),
    numbers: { total: Math.round(g(winwin.w) + g(winwin.l)), partner: name(mk(winwin.l)) },
    players: winwin.w.in.map(p => p.player), sent: winwin.w.out.map(p => p.player) });

  const adds = mv.filter(m => m.kind === 'add' || m.kind === 'swap').sort((a, b) => g(b) - g(a));
  if (adds[0]) push({ id: 'pickup-of-year', title: 'Pickup of the Year', teamId: adds[0].teamId, team: name(mk(adds[0])),
    numbers: { value: Math.round(g(adds[0])), salary: adds[0].in[0].salary }, players: adds[0].in.map(p => p.player) });

  // Plain cuts only: resets (cut + auction rebuy) and swaps have their own kinds.
  const cuts = mv.filter(m => m.kind === 'cut').sort((a, b) => g(a) - g(b));
  if (cuts[0] && g(cuts[0]) < 0) push({ id: 'cut-that-haunts', title: 'The Cut That Haunts', teamId: cuts[0].teamId, team: name(mk(cuts[0])),
    numbers: { lost: Math.round(-g(cuts[0])) }, players: cuts[0].out.map(p => p.player) });

  // Moves whose counted points decided a place (real margins); one card per trade.
  const seenTrade = new Set();
  const LABEL = { 'won-title': 'The Move That Won It', 'made-podium': 'The Move That Made the Podium', 'cost-title': 'The Move That Cost the Title', 'cost-podium': 'The Move That Cost the Podium' };
  mv.filter(m => m.titleDeciding).sort((a, b) => Math.abs(b.ptsContributed) - Math.abs(a.ptsContributed))
    .filter(m => !m.tradeId || (!seenTrade.has(m.tradeId) && seenTrade.add(m.tradeId))).slice(0, 3)
    .forEach((m, i) => push({ id: 'title-' + (i + 1), title: LABEL[m.titleDeciding], teamId: m.teamId, team: name(mk(m)),
      numbers: { pts: Math.round(m.ptsContributed * 10) / 10, kind: m.titleDeciding, closeCall: !!m.closeCall }, players: (m.in.length ? m.in : m.out).map(p => p.player) }));

  const byTeam = new Map();
  mv.forEach(m => { const t = byTeam.get(mk(m)) || { n: 0, luck: 0, nl: 0 }; t.n++; if (m.luck != null) { t.luck += m.luck; t.nl++; } byTeam.set(mk(m), t); });
  const active = [...byTeam.entries()].filter(([k]) => coversSeason(k, season)).sort((a, b) => b[1].n - a[1].n);
  if (active.length) {
    push({ id: 'most-active', title: 'Most Active Manager', teamId: active[0][0], team: name(active[0][0]), numbers: { moves: active[0][1].n } });
    const quiet = active.at(-1);
    push({ id: 'most-patient', title: 'Most Patient Manager', teamId: quiet[0], team: name(quiet[0]), numbers: { moves: quiet[1].n } });
  }
  const lucky = [...byTeam.entries()].filter(([, t]) => t.nl >= 5).sort((a, b) => b[1].luck - a[1].luck);
  if (lucky.length >= 2) {
    push({ id: 'luckiest', title: 'Luckiest Manager', teamId: lucky[0][0], team: name(lucky[0][0]), numbers: { luck: Math.round(lucky[0][1].luck) } });
    push({ id: 'unluckiest', title: 'Unluckiest Manager', teamId: lucky.at(-1)[0], team: name(lucky.at(-1)[0]), numbers: { luck: Math.round(lucky.at(-1)[1].luck) } });
  }

  const auction = mv.filter(m => m.kind === 'auction').sort((a, b) => g(b) - g(a));
  if (auction.length >= 2) {
    push({ id: 'auction-best', title: 'Best Auction Buy', teamId: auction[0].teamId, team: name(mk(auction[0])),
      numbers: { value: Math.round(g(auction[0])), salary: auction[0].in[0].salary }, players: auction[0].in.map(p => p.player) });
    const worst = auction.at(-1);
    push({ id: 'auction-worst', title: 'Worst Auction Buy', teamId: worst.teamId, team: name(mk(worst)),
      numbers: { value: Math.round(g(worst)), salary: worst.in[0].salary }, players: worst.in.map(p => p.player) });
  }

  const w = Object.entries((audit.winters || {})[season] || {}).sort((a, b) => b[1].auctionReturn - a[1].auctionReturn)[0];
  if (w) push({ id: 'winter-of-year', title: 'Winter of the Year', teamId: w[0], team: name(managerKey(w[0], `${season - 1}-11-01`)),
    numbers: { auctionReturn: Math.round(w[1].auctionReturn), auctionSpend: w[1].auctionSpend, freed: w[1].freed, resetSavings: w[1].resetSavings } });

  // All-time trade record (every season in the file).
  const rec = new Map();
  audit.moves.filter(m => m.kind === 'trade' && m.result != null).forEach(m => {
    const r = rec.get(mk(m)) || { w: 0, l: 0, net: 0, prod: 0, afterSalary: 0 }; g(m) >= 0 ? r.w++ : r.l++; r.net += g(m); r.prod += m.production || 0; r.afterSalary += m.result; rec.set(mk(m), r);
  });
  if (rec.size) push({ id: 'all-time-trades', title: 'All-Time Trade Record', teamId: null, team: null,
    numbers: { rows: [...rec.entries()].sort((a, b) => b[1].net - a[1].net).map(([id, r]) => ({ team: name(id), w: r.w, l: r.l, net: Math.round(r.net), prod: Math.round(r.prod), afterSalary: Math.round(r.afterSalary) })) } });
  return cards;
}

module.exports = { buildCards };
