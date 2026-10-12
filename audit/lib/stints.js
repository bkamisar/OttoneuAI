// audit/lib/stints.js
// Replays every transaction since the league's first auction to rebuild who
// owned whom, when, at what salary. Ownership intervals are "stints".
function replayRosters(txs) {
  const open = new Map();            // ottoneuId -> open stint
  const stints = [];
  const events = [];                 // [ts, ottoneuId, teamId|null, salary]
  const close = (id, date) => { const s = open.get(id); if (s) { s.end = date; open.delete(id); } };
  const openStint = (t, teamId, salary) => {
    const s = { ottoneuId: t.ottoneuId, player: t.player, teamId, salary, start: t.date, end: null };
    open.set(t.ottoneuId, s); stints.push(s);
  };
  for (const t of txs) {
    if (t.type === 'add' || t.type === 'move') {
      close(t.ottoneuId, t.date); openStint(t, t.teamId, t.salary); events.push([t.ts, t.ottoneuId, t.teamId, t.salary]);
    } else if (t.type === 'cut') {
      close(t.ottoneuId, t.date); events.push([t.ts, t.ottoneuId, null, 0]);
    } else if (t.type === 'increase') {
      const cur = open.get(t.ottoneuId);
      const teamId = cur ? cur.teamId : t.teamId;
      close(t.ottoneuId, t.date); openStint(t, teamId, t.salary); events.push([t.ts, t.ottoneuId, teamId, t.salary]);
    }
  }
  function rosterAt(ts) {
    const m = new Map();
    for (const [ets, id, teamId, salary] of events) {
      if (ets > ts) break;
      if (teamId === null) m.delete(id); else m.set(id, { teamId, salary });
    }
    return m;
  }
  return { stints, rosterAt };
}

function diffAgainstSnapshot(rosterMap, snapshotRows) {
  const snap = new Map(snapshotRows.map(r => [String(r.ottoneuId), String(r.teamId)]));
  const missing = [...snap.keys()].filter(id => !rosterMap.has(id));
  const extra = [...rosterMap.keys()].filter(id => !snap.has(id));
  const wrongTeam = [...snap.entries()]
    .filter(([id, team]) => rosterMap.has(id) && rosterMap.get(id).teamId !== team)
    .map(([ottoneuId, expected]) => ({ ottoneuId, expected, got: rosterMap.get(ottoneuId).teamId }));
  return { missing, extra, wrongTeam };
}

// When did this team's ownership of the player (that covers `date`) end?
// Salary increases split one tenure into several stints, so follow the chain of
// same-team stints that start where the previous one ended. `seen` guards
// zero-length stints (start === end), which would otherwise match themselves.
function makeTenureEnd(stints) {
  const byPlayer = new Map();
  stints.forEach(s => { if (!byPlayer.has(s.ottoneuId)) byPlayer.set(s.ottoneuId, []); byPlayer.get(s.ottoneuId).push(s); });
  return (id, teamId, date) => {
    const all = byPlayer.get(String(id)) || [];
    let cur = all.find(s => s.teamId === teamId && s.start <= date && (!s.end || s.end > date));
    if (!cur) return null;
    const seen = new Set([cur]);
    for (;;) {
      const next = all.find(s => !seen.has(s) && s.teamId === teamId && cur.end && s.start === cur.end);
      if (!next) break;
      seen.add(next); cur = next;
    }
    return cur.end;
  };
}

// How many separate tenures a team had with a player during a season (Mar 28 - Sep 28).
// Same-day add/drops don't count; stints split by a salary increase are one tenure.
function countTenures(stints, id, teamId, season) {
  const a = `${season}-03-28`, b = `${season}-09-28`;
  const mine = stints.filter(s => s.ottoneuId === String(id) && s.teamId === teamId && s.start !== s.end
    && s.start < b && (!s.end || s.end > a)).sort((x, y) => (x.start < y.start ? -1 : 1));
  return mine.filter((s, i) => i === 0 || s.start !== mine[i - 1].end).length;
}

module.exports = { replayRosters, diffAgainstSnapshot, makeTenureEnd, countTenures };
