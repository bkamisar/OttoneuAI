/**
 * hotstats.gs — Hot FA Board data pipeline.
 *
 * Paste into the SAME Apps Script project as briefing.gs / updateProjections.
 * Reuses that project's pushFile(token, path, content, message) helper and its
 * GITHUB_TOKEN script property — do NOT redefine those. Everything here is
 * namespaced hot* / HOT_* so nothing collides.
 *
 * Writes data/hot.json once a day from MLB StatsAPI byDateRange (free, first-
 * party). Run hotSpike_() once first to confirm the endpoint, then hotStatsTest(),
 * then add a daily time trigger (~8am ET) on hotStats.
 */

var HOT_WINDOWS = [7, 15, 30];
var HOT_TZ = 'America/New_York';

function hotStats()     { hotRun_(false); }
function hotStatsTest() { hotRun_(true); }

// One-time probe: confirms byDateRange returns per-player splits, whether the
// response is capped by `limit` (→ pagination needed), and whether position is
// populated (feeds the hitter position filter).
function hotSpike_() {
  var url = 'https://statsapi.mlb.com/api/v1/stats?stats=byDateRange&group=hitting' +
            '&startDate=2026-07-05&endDate=2026-07-19&sportId=1&gameType=R&limit=50&offset=0';
  var r = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  var splits = ((JSON.parse(r.getContentText()).stats || [])[0] || {}).splits || [];
  var p0 = splits[0] && splits[0].player;
  Logger.log('code=' + r.getResponseCode() + ' splits=' + splits.length +
             ' first=' + (p0 && p0.fullName) +
             ' pos=' + (p0 && p0.primaryPosition && p0.primaryPosition.abbreviation));
}

function hotRun_(isTest) {
  var tz = HOT_TZ, now = new Date();
  var end = Utilities.formatDate(new Date(now.getTime() - 24 * 3600 * 1000), tz, 'yyyy-MM-dd'); // yesterday
  var ranges = {}, hitMap = {}, pitMap = {};

  HOT_WINDOWS.forEach(function (w) {
    var start = Utilities.formatDate(new Date(now.getTime() - w * 24 * 3600 * 1000), tz, 'yyyy-MM-dd');
    ranges[w] = { start: start, end: end };
    hotFetch_('hitting',  start, end).forEach(function (s) { hotAddHit_(hitMap, w, s); });
    hotFetch_('pitching', start, end).forEach(function (s) { hotAddPit_(pitMap, w, s); });
  });

  var obj = {
    generatedAt: now.toISOString(),
    ranges: ranges,
    hitters:  Object.keys(hitMap).map(function (k) { return hitMap[k]; }),
    pitchers: Object.keys(pitMap).map(function (k) { return pitMap[k]; })
  };
  if (isTest) { Logger.log('hitters=' + obj.hitters.length + ' pitchers=' + obj.pitchers.length); return; }

  var token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) { Logger.log('No GITHUB_TOKEN — cannot push.'); return; }
  pushFile(token, 'data/hot.json', JSON.stringify(obj), 'Hot stats ' + end);
  Logger.log('Hot stats pushed for ' + end);
}

// Paginated pull of byDateRange for one group. Returns array of split objects.
function hotFetch_(group, start, end) {
  var out = [], offset = 0, page = 250;
  for (var guard = 0; guard < 20; guard++) {
    var url = 'https://statsapi.mlb.com/api/v1/stats?stats=byDateRange&group=' + group +
              '&startDate=' + start + '&endDate=' + end + '&sportId=1&gameType=R' +
              '&limit=' + page + '&offset=' + offset;
    var r = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (r.getResponseCode() !== 200) break;
    var splits = (((JSON.parse(r.getContentText()).stats || [])[0]) || {}).splits || [];
    out = out.concat(splits);
    if (splits.length < page) break;
    offset += page;
  }
  return out;
}

function hotKey_(s)  { return (s.player && s.player.id) || (s.player && s.player.fullName) || Math.random(); }
function hotTeam_(s) { return (s.team && s.team.abbreviation) || ''; }
function hotNum_(v)  { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
function hotRound_(v, d) { var p = Math.pow(10, d); return Math.round(hotNum_(v) * p) / p; }

function hotAddHit_(map, w, s) {
  var id = hotKey_(s), st = s.stat || {};
  var pos = (s.player && s.player.primaryPosition && s.player.primaryPosition.abbreviation) || '';
  var rec = map[id] || (map[id] = { id: (s.player && s.player.id) || null,
    name: (s.player && s.player.fullName) || '', team: hotTeam_(s), pos: pos, w: {} });
  rec.w[w] = {
    pa:  hotNum_(st.plateAppearances),
    hr:  hotNum_(st.homeRuns),
    r:   hotNum_(st.runs),
    obp: hotRound_(st.obp, 3),
    slg: hotRound_(st.slg, 3)
  };
}

function hotAddPit_(map, w, s) {
  var id = hotKey_(s), st = s.stat || {};
  var ip = hotNum_(st.inningsPitched);
  var g  = hotNum_(st.gamesPlayed) || hotNum_(st.gamesPitched);
  var gs = hotNum_(st.gamesStarted);
  var hr = hotNum_(st.homeRuns);
  var rec = map[id] || (map[id] = { id: (s.player && s.player.id) || null,
    name: (s.player && s.player.fullName) || '', team: hotTeam_(s), w: {} });
  rec.w[w] = {
    g: g, gs: gs, ip: hotRound_(ip, 1),
    so:   hotNum_(st.strikeOuts),
    era:  hotRound_(st.era, 2),
    whip: hotRound_(st.whip, 2),
    hr9:  ip > 0 ? hotRound_(hr * 9 / ip, 2) : 0,
    bf:   hotNum_(st.battersFaced),
    role: (gs > 0 && gs * 2 >= g) ? 'SP' : 'RP'
  };
}
