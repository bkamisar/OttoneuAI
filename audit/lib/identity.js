// audit/lib/identity.js
// Ottoneu player -> MLB player id, by normalized name. Same-name collisions are
// resolved by hint (H/P from roster positions) then by playing volume, and are
// always reported. No MLB stats at all = unmatched (a real zero for prospects).
const norm = s => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  .replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();

// Looser key for a second pass: drop single-letter middle initials and Jr/Sr/II-V suffixes
// ("Jose F Miranda" = "Jose Miranda", "James Tibbs III" = "James Tibbs").
const loose = s => norm(s).split(' ').filter((w, i, a) => !(i > 0 && i < a.length - 1 && w.length === 1))
  .filter(w => !/^(jr|sr|ii|iii|iv|v)$/.test(w)).join(' ');

function buildIdentity(dayFiles, players) {
  const idx = new Map();   // name key -> Map(mlbId|group -> {mlbId, group, vol})
  const looseIdx = new Map();
  const add = (index, k, row, group) => {
    if (!index.has(k)) index.set(k, new Map());
    const key = row[0] + '|' + group; const m = index.get(k);
    const cur = m.get(key) || { mlbId: row[0], group, vol: 0 };
    cur.vol += row[2]; m.set(key, cur);
  };
  for (const d of dayFiles) for (const group of ['h', 'p']) for (const row of d[group]) {
    add(idx, norm(row[1]), row, group); add(looseIdx, loose(row[1]), row, group);
  }
  const map = new Map(), ambiguous = [], unmatched = [];
  for (const p of players) {
    let cands = [...(idx.get(norm(p.player))?.values() || [])];
    if (!cands.length) cands = [...(looseIdx.get(loose(p.player))?.values() || [])];
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
