// audit/lib/review.js
// Numbers for the league year-in-review cards. Commentary is written separately
// (data/review-commentary.json) by Claude after reading these.
function buildCards(audit, season) {
  const mv = audit.moves.filter(m => m.season === season && m.result != null);
  const name = id => audit.teams[id]?.name || id;
  const cards = [];
  const push = c => cards.push({ players: [], numbers: {}, ...c });

  // Trades: pair the two sides by tradeId.
  const trades = new Map();
  mv.filter(m => m.kind === 'trade').forEach(m => { if (!trades.has(m.tradeId)) trades.set(m.tradeId, []); trades.get(m.tradeId).push(m); });
  const tradeRows = [...trades.values()].filter(s => s.length === 2).map(([a, b]) => {
    const [w, l] = a.result >= b.result ? [a, b] : [b, a];
    return { w, l, margin: w.result - l.result, both: a.result > 0 && b.result > 0 };
  });
  const fleece = [...tradeRows].sort((x, y) => y.margin - x.margin)[0];
  if (fleece) push({ id: 'trade-of-year', title: 'Fleecing of the Year', teamId: fleece.w.teamId, team: name(fleece.w.teamId),
    numbers: { margin: Math.round(fleece.margin), winner: Math.round(fleece.w.result), loser: Math.round(fleece.l.result), victim: name(fleece.l.teamId) },
    players: fleece.w.in.map(p => p.player) });
  const winwin = tradeRows.filter(r => r.both).sort((x, y) => (y.w.result + y.l.result) - (x.w.result + x.l.result))[0];
  if (winwin) push({ id: 'win-win', title: 'Trade of the Year (everybody won)', teamId: winwin.w.teamId, team: name(winwin.w.teamId),
    numbers: { total: Math.round(winwin.w.result + winwin.l.result), partner: name(winwin.l.teamId) },
    players: [...winwin.w.in, ...winwin.l.in].map(p => p.player) });

  const adds = mv.filter(m => m.kind === 'add' || m.kind === 'swap').sort((a, b) => b.result - a.result);
  if (adds[0]) push({ id: 'pickup-of-year', title: 'Pickup of the Year', teamId: adds[0].teamId, team: name(adds[0].teamId),
    numbers: { value: Math.round(adds[0].result), salary: adds[0].in[0].salary }, players: adds[0].in.map(p => p.player) });

  const cuts = mv.filter(m => m.kind === 'cut' || m.kind === 'swap').sort((a, b) => a.result - b.result);
  if (cuts[0] && cuts[0].result < 0) push({ id: 'cut-that-haunts', title: 'The Cut That Haunts', teamId: cuts[0].teamId, team: name(cuts[0].teamId),
    numbers: { lost: Math.round(-cuts[0].result) }, players: cuts[0].out.map(p => p.player) });

  mv.filter(m => m.decisive).sort((a, b) => Math.abs(b.standings?.dPts || 0) - Math.abs(a.standings?.dPts || 0)).slice(0, 3).forEach((m, i) =>
    push({ id: i ? 'decisive-' + i : 'decisive', title: m.standings.dPts > 0 ? 'The Move That Won It' : 'The Move That Cost It', teamId: m.teamId, team: name(m.teamId),
      numbers: { dPts: m.standings.dPts, dRank: m.standings.dRank, closeCall: m.fragile === true, unchecked: m.fragile === 'unchecked' },
      players: (m.in.length ? m.in : m.out).map(p => p.player) }));

  const byTeam = new Map();
  mv.forEach(m => { const t = byTeam.get(m.teamId) || { n: 0, luck: 0, nl: 0 }; t.n++; if (m.luck != null) { t.luck += m.luck; t.nl++; } byTeam.set(m.teamId, t); });
  const active = [...byTeam.entries()].sort((a, b) => b[1].n - a[1].n);
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

  const auction = mv.filter(m => m.kind === 'auction').sort((a, b) => b.result - a.result);
  if (auction.length >= 2) {
    push({ id: 'auction-best', title: 'Best Auction Buy', teamId: auction[0].teamId, team: name(auction[0].teamId),
      numbers: { value: Math.round(auction[0].result), salary: auction[0].in[0].salary }, players: auction[0].in.map(p => p.player) });
    const worst = auction.at(-1);
    push({ id: 'auction-worst', title: 'Worst Auction Buy', teamId: worst.teamId, team: name(worst.teamId),
      numbers: { value: Math.round(worst.result), salary: worst.in[0].salary }, players: worst.in.map(p => p.player) });
  }

  // All-time trade record (every season in the file).
  const rec = new Map();
  audit.moves.filter(m => m.kind === 'trade' && m.result != null).forEach(m => {
    const r = rec.get(m.teamId) || { w: 0, l: 0, net: 0 }; m.result >= 0 ? r.w++ : r.l++; r.net += m.result; rec.set(m.teamId, r);
  });
  if (rec.size) push({ id: 'all-time-trades', title: 'All-Time Trade Record', teamId: null, team: null,
    numbers: { rows: [...rec.entries()].sort((a, b) => b[1].net - a[1].net).map(([id, r]) => ({ team: name(id), w: r.w, l: r.l, net: Math.round(r.net) })) } });
  return cards;
}

module.exports = { buildCards };
