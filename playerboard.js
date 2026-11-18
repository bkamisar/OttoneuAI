// Player Board helpers (players.html). Pure functions over shared.js output, so the
// audit harness can test them: rows from the dynasty map, filtering, sorting.

// teams: { teamName: [player] }; dynMap: calculateDynastyValues output keyed by fgId||name.
// opts: { myTeam, ages: {name: birthDate}, prospects: {name: {fv, age}}, season,
//         market: function (p) -> {actual, sample} | null }
function pbBuildRows(teams, dynMap, opts) {
  opts = opts || {};
  var rows = [];
  Object.keys(teams).forEach(function (team) {
    if (team === 'Free Agent') return;
    (teams[team] || []).forEach(function (p) {
      var key = p.fgId || p.name;
      var d = dynMap[key] || {};
      var dyn = d.dynastyValue == null ? null : d.dynastyValue;
      var surplus = d.dynastySurplus == null ? null : d.dynastySurplus;
      var tv = null;
      if (dyn != null) {
        var cost = surplus == null ? 0 : dyn - surplus;
        var m = opts.market ? opts.market(p) : null;
        tv = offseasonTradeValue(dyn, cost, null,
          m && m.actual != null ? { actual: m.actual, sample: m.sample, proj: d.projectedValue || 0 } : null);
      }
      var pr = (opts.prospects || {})[p.name] || null;
      var age = typeof ageInSeason === 'function' && opts.ages ? ageInSeason(opts.ages[p.name], opts.season) : null;
      if (age == null && pr && pr.age) age = Math.floor(+pr.age) + 1;
      rows.push({
        key: key, name: p.rawName || p.name, team: team, mine: team === opts.myTeam,
        pos: (p.positions || []).join('/').toUpperCase(), type: p.type,
        age: age == null ? null : age, salary: p.salary || 0,
        y0: d.projectedValue == null ? null : d.projectedValue,
        dyn: dyn, surplus: surplus, hold: d.holdHorizon == null ? null : d.holdHorizon + 1,
        tv: tv, fv: pr && pr.fv ? +pr.fv : null, prospect: !!(pr && pr.fv),
      });
    });
  });
  return rows;
}

function pbFold(s) {
  return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

// f: { search, team, pos, type ('H'|'P'), prospectsOnly, hideMine }; empty fields don't filter.
function pbFilter(rows, f) {
  f = f || {};
  var q = pbFold(f.search).trim();
  var pos = String(f.pos || '').toUpperCase();
  return rows.filter(function (r) {
    if (q && pbFold(r.name).indexOf(q) < 0) return false;
    if (f.team && r.team !== f.team) return false;
    if (pos && r.pos.split('/').indexOf(pos) < 0) return false;
    if (f.type && r.type !== f.type) return false;
    if (f.prospectsOnly && !r.prospect) return false;
    if (f.hideMine && r.mine) return false;
    return true;
  });
}

// New array sorted by key; nulls last in both directions; strings by localeCompare.
function pbSort(rows, key, dir) {
  var sign = dir === 'asc' ? 1 : -1;
  return rows.slice().sort(function (a, b) {
    var x = a[key], y = b[key];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    if (typeof x === 'string') return sign * x.localeCompare(y);
    return sign * (x - y);
  });
}
