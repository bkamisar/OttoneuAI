/**
 * briefing.gs — Daily Briefing generator for the Ottoneu tools.
 *
 * Paste this into the SAME Apps Script project that already holds
 * updateProjections / updateStandings / updateRoster. It REUSES that project's
 * `pushFile(token, path, content, message)` helper and its `GITHUB_TOKEN`
 * script property — do NOT redefine those. Everything here is namespaced
 * `bf*` / `BRIEFING_*` so nothing collides in the shared global scope.
 *
 * It fetches, once a day, from free sources (MLB StatsAPI, Google News RSS,
 * ESPN) and pushes data/briefing.json to the repo; briefing.html renders it.
 * NO EMAIL. Set MY_TEAM_ID below, run briefingTest(), then add a daily
 * time trigger (7–8am ET) on dailyBriefing.
 */

var BRIEFING_CONFIG = {
  MY_TEAM_ID: '',                    // <-- SET THIS: first column (TeamID) of your rows in data/roster.csv
  LEAGUE_ID:  '1648',
  TIMEZONE:   'America/New_York'
};

// Ottoneu -> MLB StatsAPI team abbreviations (only the ones that differ).
// Verified against /api/v1/teams: Arizona is AZ (not ARI), etc.
var BF_TEAM_ALIAS = { ARI: 'AZ', CHW: 'CWS', KCR: 'KC', SDP: 'SD', SFG: 'SF', TBR: 'TB', WSN: 'WSH' };
var BF_UA = { 'User-Agent': 'Mozilla/5.0' };
var BF_NEWS_PER_PLAYER        = 4;   // headlines kept per flagged player
var BF_NEWS_ROSTER_PER_PLAYER = 2;   // headlines kept per other rostered player
var BF_NEWS_MAX_AGE_DAYS      = 5;   // drop headlines/articles older than this

function dailyBriefing() { bfRun_(false); }
function briefingTest()  { bfRun_(true); }

function bfRun_(isTest) {
  var errors = [];
  var tz  = BRIEFING_CONFIG.TIMEZONE;
  var now = new Date();
  var today     = Utilities.formatDate(now, tz, 'yyyy-MM-dd');
  var yesterday = Utilities.formatDate(new Date(now.getTime() - 24 * 3600 * 1000), tz, 'yyyy-MM-dd');
  var dateLabel = Utilities.formatDate(now, tz, 'EEEE, MMMM d');

  var my = null;
  try { my = bfGetMyPlayers_(); }
  catch (e) { errors.push('Roster fetch failed: ' + e); }
  if (!my) { my = { list: [], byNorm: {} }; errors.push('No roster — set MY_TEAM_ID and check the export.'); }

  var yObj = { note: '', hitters: [], pitchers: [] };
  var box  = { appeared: {}, gamePksWithMine: {}, teamsPlayed: {} };
  try { box = bfGetYesterdayBox_(my, yesterday, yObj); }
  catch (e) { errors.push('Yesterday box failed: ' + e); yObj.note = 'Yesterday’s box unavailable.'; }

  var news = { transactions: [], flagged: [], league: [] };
  try { bfGetNews_(my, box, yObj, news, today, tz, now); }
  catch (e) { errors.push('News failed: ' + e); }

  var matchups = { hitters: [], myStarters: [], note: '' };
  try { bfGetMatchups_(my, today, tz, matchups); }
  catch (e) { errors.push('Matchups failed: ' + e); matchups.note = 'Matchups unavailable.'; }

  // Strip the internal `norm` keys before publishing.
  yObj.hitters.forEach(function (h) { delete h.norm; });
  yObj.pitchers.forEach(function (p) { delete p.norm; });

  var obj = {
    generatedAt: now.toISOString(),
    dateLabel:   dateLabel,
    teamId:      BRIEFING_CONFIG.MY_TEAM_ID,
    yesterday:   yObj,
    news:        news,
    matchups:    matchups,
    errors:      errors
  };

  if (isTest) Logger.log(JSON.stringify(obj, null, 2));

  var token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) { Logger.log('No GITHUB_TOKEN script property — cannot push.'); return; }
  pushFile(token, 'data/briefing.json', JSON.stringify(obj, null, 1), 'Daily briefing ' + today);
  Logger.log('Briefing pushed for ' + today + (errors.length ? (' with ' + errors.length + ' error(s)') : ''));
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function bfNorm_(s) {
  return String(s || '').toLowerCase()
    .normalize('NFD').replace(/[̀-ͯ]/g, '')   // strip accents
    .replace(/\./g, '')                                 // strip periods (J.T., Luis L.)
    .replace(/\s+/g, ' ').trim();
}

function bfAlias_(o) { return BF_TEAM_ALIAS[o] || o; }

// Canonical MLB team map (fetched once). The schedule endpoint's team objects
// only carry {id, name, link} — NOT abbreviation — so all team matching is done
// by ID. This maps StatsAPI abbreviation <-> team id.
var BF_TEAMS_CACHE = null;
function bfTeams_() {
  if (BF_TEAMS_CACHE) return BF_TEAMS_CACHE;
  var idByAbbr = {}, abbrById = {};
  var r = bfGet_('https://statsapi.mlb.com/api/v1/teams?sportId=1');
  if (r.code === 200) {
    (JSON.parse(r.text).teams || []).forEach(function (t) {
      if (!t.abbreviation || !t.id) return;
      idByAbbr[t.abbreviation] = t.id;
      abbrById[t.id] = t.abbreviation;
    });
  }
  BF_TEAMS_CACHE = { idByAbbr: idByAbbr, abbrById: abbrById };
  return BF_TEAMS_CACHE;
}
// Ottoneu roster abbrev -> StatsAPI team id (null if unresolved).
function bfTeamId_(ottoneuAbbr) {
  return bfTeams_().idByAbbr[bfAlias_(ottoneuAbbr)] || null;
}

function bfParseCsvLine_(line) {
  var out = [], cur = '', q = false;
  for (var i = 0; i < line.length; i++) {
    var c = line[i];
    if (c === '"') { q = !q; }
    else if (c === ',' && !q) { out.push(cur); cur = ''; }
    else { cur += c; }
  }
  out.push(cur);
  return out;
}

function bfGet_(url, opts) {
  var resp = UrlFetchApp.fetch(url, opts || { muteHttpExceptions: true });
  return { code: resp.getResponseCode(), text: resp.getContentText() };
}

function bfGetMyPlayers_() {
  var url = 'https://ottoneu.fangraphs.com/' + BRIEFING_CONFIG.LEAGUE_ID + '/rosterexport?csv=1';
  var r = bfGet_(url, { headers: BF_UA, muteHttpExceptions: true });
  if (r.code !== 200) throw new Error('roster HTTP ' + r.code);
  var lines = r.text.trim().split('\n');
  var header = bfParseCsvLine_(lines[0]);
  var iTid = header.indexOf('TeamID'), iName = header.indexOf('Name'),
      iMlb = header.indexOf('MLB Team'), iPos = header.indexOf('Position(s)');
  var list = [], byNorm = {};
  for (var i = 1; i < lines.length; i++) {
    if (!lines[i].trim()) continue;
    var c = bfParseCsvLine_(lines[i]);
    if ((c[iTid] || '').trim() !== BRIEFING_CONFIG.MY_TEAM_ID) continue;
    var name = (c[iName] || '').trim();
    if (!name) continue;
    var mlb = (c[iMlb] || '').trim();
    var p = {
      name: name,
      mlb: mlb,
      mlbBase: mlb.split(' ')[0],            // "NYY AAA" -> "NYY"; MLB-level rows have no space
      pos: (c[iPos] || '').trim(),
      norm: bfNorm_(name)
    };
    list.push(p);
    byNorm[p.norm] = p;
  }
  if (!list.length) throw new Error('No players found for TeamID "' + BRIEFING_CONFIG.MY_TEAM_ID + '"');
  return { list: list, byNorm: byNorm };
}

function bfScheduleGames_(url) {
  var r = bfGet_(url);
  if (r.code !== 200) throw new Error('schedule HTTP ' + r.code);
  var sched = JSON.parse(r.text);
  var games = [];
  (sched.dates || []).forEach(function (d) { (d.games || []).forEach(function (g) { games.push(g); }); });
  return games;
}

function bfGetYesterdayBox_(my, yesterday, out) {
  var box = { appeared: {}, gamePksWithMine: {}, teamsPlayed: {} };
  var games = bfScheduleGames_('https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=' + yesterday);
  if (!games.length) { out.note = 'No games yesterday.'; return box; }

  games.forEach(function (g) {
    try {
      box.teamsPlayed[g.teams.home.team.id] = 1;   // keyed by team ID (schedule has no abbrev)
      box.teamsPlayed[g.teams.away.team.id] = 1;
    } catch (e) {}
  });

  games.forEach(function (g) {
    var r = bfGet_('https://statsapi.mlb.com/api/v1/game/' + g.gamePk + '/boxscore');
    if (r.code !== 200) return;
    var bx = JSON.parse(r.text);
    ['home', 'away'].forEach(function (side) {
      var tm = bx.teams && bx.teams[side];
      if (!tm || !tm.players) return;
      var abbr   = (tm.team && tm.team.abbreviation) || '';
      var teamId = (tm.team && tm.team.id) || null;
      Object.keys(tm.players).forEach(function (pid) {
        var pl = tm.players[pid];
        var full = pl.person && pl.person.fullName;
        if (!full) return;
        var nm = bfNorm_(full);
        var mine = my.byNorm[nm];
        if (!mine) return;
        // Collision guard by team ID: same normalized name, different team → not mine.
        var myId = bfTeamId_(mine.mlbBase);
        if (myId && teamId && myId !== teamId) {
          Logger.log('Name/team mismatch, skipped: ' + full + ' (box team ' + teamId + ' vs roster ' + mine.mlbBase + ')');
          return;
        }
        box.appeared[nm] = 1;
        box.gamePksWithMine[g.gamePk] = 1;
        var st = pl.stats || {};
        if (st.batting && ((st.batting.atBats || 0) > 0 || (st.batting.baseOnBalls || 0) > 0)) {
          out.hitters.push({ name: mine.name, mlb: abbr, line: bfHitLine_(st.batting), blurb: '', norm: nm });
        }
        if (st.pitching && st.pitching.inningsPitched && st.pitching.inningsPitched !== '0.0') {
          out.pitchers.push({ name: mine.name, mlb: abbr, line: bfPitLine_(st.pitching), blurb: '', norm: nm });
        }
      });
    });
  });
  return box;
}

function bfHitLine_(b) {
  var parts = [(b.hits || 0) + '-' + (b.atBats || 0)];
  if (b.homeRuns)     parts.push(b.homeRuns + ' HR');
  if (b.rbi)          parts.push(b.rbi + ' RBI');
  if (b.runs)         parts.push(b.runs + ' R');
  if (b.baseOnBalls)  parts.push(b.baseOnBalls + ' BB');
  if (b.stolenBases)  parts.push(b.stolenBases + ' SB');
  return parts.join(', ');
}

function bfPitLine_(p) {
  var line = [(p.inningsPitched || '0.0') + ' IP', (p.earnedRuns || 0) + ' ER', (p.strikeOuts || 0) + ' K'].join(', ');
  if (p.note) line += ' ' + p.note;   // note already looks like "(W, 8-3)"
  return line;
}

function bfGetNews_(my, box, yObj, news, today, tz, now) {
  var start = Utilities.formatDate(new Date(now.getTime() - 2 * 24 * 3600 * 1000), tz, 'yyyy-MM-dd');
  var flagged = {};   // norm -> reason

  // (a) Official transactions
  try {
    var r = bfGet_('https://statsapi.mlb.com/api/v1/transactions?startDate=' + start + '&endDate=' + today);
    if (r.code !== 200) throw new Error('HTTP ' + r.code);
    var tj = JSON.parse(r.text);
    (tj.transactions || []).forEach(function (tx) {
      var full = tx.person && tx.person.fullName;
      if (!full) return;
      var nm = bfNorm_(full);
      if (!my.byNorm[nm]) return;
      var d = (tx.date || '').slice(5).replace(/-/g, '/');   // MM/DD
      news.transactions.push(d + ' — ' + (tx.description || tx.typeDesc || 'transaction'));
      flagged[nm] = 'transaction';
    });
  } catch (e) { news.transactions.push('(transactions unavailable: ' + e + ')'); }

  // Monster lines from yesterday's box
  yObj.hitters.forEach(function (h) {
    var hr = h.line.match(/(\d+) HR/), rbi = h.line.match(/(\d+) RBI/);
    if ((hr && +hr[1] >= 2) || (rbi && +rbi[1] >= 5)) flagged[h.norm] = flagged[h.norm] || 'monster game';
  });
  yObj.pitchers.forEach(function (p) {
    var k = p.line.match(/(\d+) K/);
    if (k && +k[1] >= 10) flagged[p.norm] = flagged[p.norm] || 'monster game';
  });

  // Absence: MLB HITTER whose team played yesterday but who never appeared.
  // Pitchers are excluded — a starter is "absent" from the box on ~4 of every
  // 5 days by design, and an injured pitcher trips this EVERY day, which is how
  // weeks-old IL coverage kept resurfacing for the same arms (Pivetta, etc.).
  my.list.forEach(function (p) {
    if (p.mlb.indexOf(' ') !== -1) return;   // minor leaguer
    if (bfIsPitcherOnly_(p.pos)) return;     // pitcher absence from a daily box is meaningless
    var id = bfTeamId_(p.mlbBase);
    if (id && box.teamsPlayed[id] && !box.appeared[p.norm]) {
      flagged[p.norm] = flagged[p.norm] || 'absent from box';
    }
  });

  // (b) Per-player Google News. Flagged players (transaction / monster game /
  // hitter absence) come first, keep their reason badge, and get a full set of
  // headlines. Every other rostered player follows with a smaller cap so there's
  // always more to read — but only when they actually have recent headlines.
  var cutoff = now.getTime() - BF_NEWS_MAX_AGE_DAYS * 24 * 3600 * 1000;
  var ordered = [], seenNorm = {}, seenTitle = {};
  Object.keys(flagged).forEach(function (nm) { if (!seenNorm[nm]) { seenNorm[nm] = 1; ordered.push(nm); } });
  my.list.forEach(function (p) { if (!seenNorm[p.norm]) { seenNorm[p.norm] = 1; ordered.push(p.norm); } });

  ordered.forEach(function (nm) {
    var p = my.byNorm[nm];
    if (!p) return;
    var reason = flagged[nm] || '';
    var cap = reason ? BF_NEWS_PER_PLAYER : BF_NEWS_ROSTER_PER_PLAYER;
    var items = [];
    try {
      var q = encodeURIComponent('"' + p.name + '" mlb');
      var gr = bfGet_('https://news.google.com/rss/search?q=' + q + '&hl=en-US&gl=US&ceid=US:en',
                      { headers: BF_UA, muteHttpExceptions: true });
      if (gr.code === 200) items = bfParseRss_(gr.text, cap, cutoff);
    } catch (e) {}
    // Drop any headline already shown under an earlier (higher-priority) player.
    items = items.filter(function (it) {
      var key = bfNorm_(it.title);
      if (!key || seenTitle[key]) return false;
      seenTitle[key] = 1;
      return true;
    });
    // Flagged players always appear (the reason is the point); other players
    // only when they have recent headlines worth reading.
    if (!reason && !items.length) return;
    news.flagged.push({ name: p.name, reason: reason, items: items });
  });

  // (c) ESPN league-wide catch-all (recent only)
  try {
    var cut = now.getTime() - BF_NEWS_MAX_AGE_DAYS * 24 * 3600 * 1000;
    var er = bfGet_('https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/news?limit=25');
    if (er.code === 200) {
      var ej = JSON.parse(er.text);
      var seen = {};
      (ej.articles || []).forEach(function (a) {
        var pub = Date.parse(a.published || '');
        if (!isNaN(pub) && pub < cut) return;                 // older than the window
        var hay = bfNorm_((a.headline || '') + ' ' + (a.description || ''));
        if (!my.list.some(function (p) { return hay.indexOf(p.norm) !== -1; })) return;
        if (seen[a.headline]) return;
        seen[a.headline] = 1;
        var link = (a.links && a.links.web && a.links.web.href) || '';
        news.league.push({ title: a.headline || '', link: link });
      });
    }
  } catch (e) {}
}

// Extract up to n recent <item> title/link pairs from an RSS feed. Skips items
// whose <pubDate> is older than cutoffMs (kept if pubDate is missing/unparseable).
// Uses split+match (no RegExp.exec) so it stays a plain string parse.
function bfParseRss_(xml, n, cutoffMs) {
  var items = [];
  var chunks = String(xml).split('<item>').slice(1);
  for (var i = 0; i < chunks.length && items.length < n; i++) {
    var d = chunks[i].match(/<pubDate>([\s\S]*?)<\/pubDate>/);
    if (cutoffMs && d) { var ts = Date.parse(d[1].trim()); if (!isNaN(ts) && ts < cutoffMs) continue; }
    var t = chunks[i].match(/<title>([\s\S]*?)<\/title>/);
    var l = chunks[i].match(/<link>([\s\S]*?)<\/link>/);
    var title = t ? bfDecode_(t[1].replace(/<!\[CDATA\[|\]\]>/g, '')).trim() : '';
    var link  = l ? l[1].replace(/<!\[CDATA\[|\]\]>/g, '').trim() : '';
    if (title) items.push({ title: title, link: link });
  }
  return items;
}

function bfDecode_(s) {
  return String(s).replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&#39;/g, "'").replace(/&apos;/g, "'").replace(/&quot;/g, '"');
}

function bfIsPitcherOnly_(pos) {
  var toks = String(pos || '').toLowerCase().split(/[\/,]/).map(function (s) { return s.trim(); });
  var hasHit = toks.some(function (t) { return ['c', '1b', '2b', 'ss', '3b', 'of', 'dh', 'mi', 'ci', 'util'].indexOf(t) >= 0; });
  var hasPit = toks.some(function (t) { return t === 'sp' || t === 'rp' || t === 'p'; });
  return hasPit && !hasHit;
}

function bfGameTime_(g, tz) {
  try { return Utilities.formatDate(new Date(g.gameDate), tz, 'h:mm a'); } catch (e) { return ''; }
}

function bfPitcherInfo_(id) {
  var out = { era: null, hand: '', name: '' };
  try {
    var r = bfGet_('https://statsapi.mlb.com/api/v1/people/' + id + '?hydrate=stats(group=[pitching],type=[season])');
    if (r.code !== 200) return out;
    var per = (JSON.parse(r.text).people || [])[0] || {};
    out.name = per.fullName || '';
    out.hand = (per.pitchHand && per.pitchHand.code) || '';
    try {
      var splits = per.stats[0].splits;
      var era = splits[splits.length - 1].stat.era;
      if (era !== undefined && era !== '-.--') out.era = parseFloat(era);
    } catch (e) {}
  } catch (e) {}
  return out;
}

// Season team-offense ranks (1 = best offense), one API call, cached. Used to
// judge whether starting one of my pitchers is favorable (weak opposing bats).
var BF_OFFENSE_CACHE = null;
function bfTeamOffense_() {
  if (BF_OFFENSE_CACHE) return BF_OFFENSE_CACHE;
  var rankById = {}, opsById = {};
  try {
    var yr = Utilities.formatDate(new Date(), BRIEFING_CONFIG.TIMEZONE, 'yyyy');
    var r = bfGet_('https://statsapi.mlb.com/api/v1/teams/stats?season=' + yr + '&sportIds=1&group=hitting&stats=season');
    if (r.code === 200) {
      var splits = ((JSON.parse(r.text).stats || [])[0] || {}).splits || [];
      splits.map(function (s) { return { id: s.team && s.team.id, ops: parseFloat(s.stat && s.stat.ops) || 0 }; })
        .filter(function (x) { return x.id; })
        .sort(function (a, b) { return b.ops - a.ops; })
        .forEach(function (x, i) { rankById[x.id] = i + 1; opsById[x.id] = x.ops; });
    }
  } catch (e) {}
  BF_OFFENSE_CACHE = { rankById: rankById, opsById: opsById, count: Object.keys(rankById).length };
  return BF_OFFENSE_CACHE;
}

function bfGetMatchups_(my, today, tz, out) {
  var games = bfScheduleGames_('https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=' + today + '&hydrate=probablePitcher');
  if (!games.length) { out.note = 'No games today.'; return; }

  // Schedule team objects only have ids — resolve abbrevs from the canonical map.
  var abbrById = bfTeams_().abbrById;
  var off = bfTeamOffense_();
  var pitcherCache = {};
  var byTeamId = {};   // team id -> game context
  games.forEach(function (g) {
    var home = g.teams.home, away = g.teams.away;
    var hId = home.team.id, aId = away.team.id;
    var hAbbr = abbrById[hId] || home.team.name || ('#' + hId);
    var aAbbr = abbrById[aId] || away.team.name || ('#' + aId);
    var time = bfGameTime_(g, tz);
    byTeamId[hId] = { oppProbable: away.probablePitcher || null, gameStr: hAbbr + ' vs ' + aAbbr + (time ? ' ' + time : '') };
    byTeamId[aId] = { oppProbable: home.probablePitcher || null, gameStr: aAbbr + ' @ ' + hAbbr + (time ? ' ' + time : '') };
    // My probable starters today — with own ERA and opposing-offense strength
    [{ pp: home.probablePitcher, team: hAbbr, opp: aAbbr, oppId: aId, home: true },
     { pp: away.probablePitcher, team: aAbbr, opp: hAbbr, oppId: hId, home: false }].forEach(function (x) {
      if (!x.pp || !x.pp.fullName) return;
      var mine = my.byNorm[bfNorm_(x.pp.fullName)];
      if (!mine) return;
      var info = pitcherCache[x.pp.id] || (pitcherCache[x.pp.id] = bfPitcherInfo_(x.pp.id));
      var oppRank = off.rankById[x.oppId] || null;   // 1 = strongest offense
      var total = off.count || 30;
      var flag = '';
      if (oppRank) flag = oppRank >= total - 9 ? 'good' : (oppRank <= 10 ? 'tough' : '');
      out.myStarters.push({
        name: mine.name,
        era: info.era,
        game: x.team + (x.home ? ' vs ' : ' @ ') + x.opp + ' (' + (x.home ? 'home' : 'away') + ')',
        oppTeam: x.opp,
        oppOffRank: oppRank,
        oppOffTotal: total,
        flag: flag
      });
    });
  });

  // Group my hitters by their game (by team id)
  var groups = {};
  my.list.forEach(function (p) {
    if (p.mlb.indexOf(' ') !== -1) return;        // minor leaguer
    if (bfIsPitcherOnly_(p.pos)) return;          // pitchers handled via myStarters
    var id = bfTeamId_(p.mlbBase);
    if (!id) { Logger.log('Unresolved team abbrev: ' + p.name + ' (' + p.mlb + ')'); return; }
    var ctx = byTeamId[id];
    if (!ctx) return;                             // team is simply off today — normal, no log spam
    if (!groups[id]) groups[id] = { abbr: abbrById[id] || p.mlbBase, players: [], ctx: ctx };
    groups[id].players.push(p.name);
  });

  Object.keys(groups).forEach(function (id) {
    var grp = groups[id], ctx = grp.ctx, pp = ctx.oppProbable;
    var oppName = 'TBD', era = null, flag = '';
    if (pp && pp.id) {
      var info = pitcherCache[pp.id] || (pitcherCache[pp.id] = bfPitcherInfo_(pp.id));
      oppName = (info.hand ? info.hand + 'P ' : '') + (pp.fullName || info.name || '?');
      era = info.era;
      if (era !== null) flag = era < 3.30 ? 'tough' : (era > 4.60 ? 'target' : '');
    }
    out.hitters.push({ mlb: grp.abbr, players: grp.players, game: ctx.gameStr, opp: 'vs ' + oppName, era: era, flag: flag });
  });
}
