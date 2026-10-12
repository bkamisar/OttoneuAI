// audit/lib/offseason.js
// October -> auction moves are cap moves. A cut that the same team buys back at
// the auction is a salary reset, graded on the salary change alone.
function auctionDays(moves) {
  const out = {};
  moves.filter(m => m.kind === 'auction').forEach(m => { if (!out[m.season] || m.date < out[m.season]) out[m.season] = m.date; });
  return out;
}

function annotateOffseason(moves) {
  const days = auctionDays(moves);
  // Auction buys are always offseason (an auction can span several days).
  const isOff = m => m.kind === 'auction' || (m.date >= `${m.season - 1}-10-01` && (!days[m.season] || m.date < days[m.season]));
  const consumed = new Set();
  const resets = new Map();   // cut id -> reset move
  for (const cut of moves.filter(m => m.kind === 'cut' && isOff(m))) {
    const p = cut.out[0];
    const buy = moves.find(a => a.kind === 'auction' && a.season === cut.season && a.teamId === cut.teamId && !consumed.has(a.id)
      && a.in.some(q => q.ottoneuId === p.ottoneuId));
    if (!buy) continue;
    consumed.add(buy.id);
    const np = buy.in.find(q => q.ottoneuId === p.ottoneuId);
    resets.set(cut.id, { ...cut, kind: 'reset', in: [np], out: [p], resetGrade: p.salary - np.salary });
  }
  return moves.filter(m => !consumed.has(m.id)).map(m => {
    const x = { ...(resets.get(m.id) || m), phase: isOff(m) ? 'offseason' : 'in-season' };
    if (x.kind === 'trade') x.capDelta = x.out.reduce((s, p) => s + p.salary, 0) - x.in.reduce((s, p) => s + p.salary, 0);
    return x;
  });
}

module.exports = { auctionDays, annotateOffseason };
