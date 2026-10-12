// audit/lib/identity.js
// Ottoneu player -> MLB player id, by normalized name. Same-name collisions are
// resolved by hint (H/P from roster positions) then by playing volume, and are
// always reported. No MLB stats at all = unmatched (a real zero for prospects).
const norm = s => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  .replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();

function buildIdentity(dayFiles, players) {
  const idx = new Map();   // normName -> Map(mlbId|group -> {mlbId, group, vol})
  for (const d of dayFiles) for (const group of ['h', 'p']) for (const row of d[group]) {
    const k = norm(row[1]); if (!idx.has(k)) idx.set(k, new Map());
    const key = row[0] + '|' + group; const m = idx.get(k);
    const cur = m.get(key) || { mlbId: row[0], group, vol: 0 };
    cur.vol += row[2]; m.set(key, cur);
  }
  const map = new Map(), ambiguous = [], unmatched = [];
  for (const p of players) {
    const cands = [...(idx.get(norm(p.player))?.values() || [])];
    if (!cands.length) { unmatched.push(p); continue; }
    let pick = cands;
    if (cands.length > 1) {
      ambiguous.push({ ...p, candidates: cands.map(c => c.mlbId + c.group) });
      const want = p.hint === 'P' ? 'p' : p.hint === 'H' ? 'h' : null;
      if (want && cands.some(c => c.group === want)) pick = cands.filter(c => c.group === want);
    }
    const best = [...pick].sort((a, b) => b.vol - a.vol)[0];
    map.set(p.ottoneuId, { mlbId: best.mlbId, group: best.group });
  }
  return { map, ambiguous, unmatched };
}

module.exports = { buildIdentity, norm };
