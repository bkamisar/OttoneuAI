// scripts/updaters.gs — the main Apps Script file (roster, standings, projections, prospects).
// Paste the WHOLE file over the project's main script file. briefing.gs and hotstats.gs
// are separate files in the same project and reuse pushFile() from here.
//
// ── Configuration ──────────────────────────────────────────────────────────
// Store your GitHub token in: Project Settings → Script properties
// Key: GITHUB_TOKEN   Value: your token. Never paste the token into this file.
//
// Changes 2026-11-15 (offseason fix):
//   - Never push a file with too few rows (FanGraphs returns empty arrays out of season;
//     on Nov 1 and Nov 4 2026 that blanked every projection file).
//   - Offseason (Sep 29 → Mar 27): "this season" = NEXT season's preseason Steamer
//     (type=steamer). In season: rest-of-season Steamer (type=steamerr), as before.
//   - Standings are not re-pushed in the offseason (last season's final stays in place).
//   - Y1/Y2 labels follow the season the tools are valuing.

var GITHUB_OWNER = "bkamisar";
var GITHUB_REPO  = "OttoneuAI";
var FG_BASE      = "https://www.fangraphs.com/api/projections";

var MIN_HITTERS  = 1000;   // a real projection set has ~4,000+ hitters / 5,000+ pitchers
var MIN_PITCHERS = 1000;
var MIN_FUTURE   = 500;    // ZiPS multi-year sets are smaller (~1,800 each)
var MIN_PROSPECTS = 300;

var FG_OPTS = {
  method: "get",
  headers: {
    "User-Agent":        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":            "application/json, text/javascript, */*; q=0.01",
    "Referer":           "https://www.fangraphs.com/projections.aspx",
    "X-Requested-With":  "XMLHttpRequest"
  },
  muteHttpExceptions: true
};

// ── Season clock (matches shared.js: season = Mar 28 → Sep 28) ──────────────
function isOffseason(now) {
  now = now || new Date();
  var m = now.getMonth() + 1, d = now.getDate();
  return (m > 9) || (m === 9 && d > 28) || (m < 3) || (m === 3 && d < 28);
}

// The season the tools are valuing: next year once this one has ended.
function seasonYear(now) {
  now = now || new Date();
  var m = now.getMonth() + 1;
  return (isOffseason(now) && m >= 9) ? now.getFullYear() + 1 : now.getFullYear();
}

// Push only when the data looks real; otherwise keep the file already in the repo.
function checkedPush(token, path, rows, cols, message, minRows) {
  if (rows.length < minRows) {
    Logger.log("✗ NOT pushing " + path + ": only " + rows.length + " rows (need " + minRows +
               "). The repo copy is left as it was.");
    return false;
  }
  pushFile(token, path, toCsv(rows, cols), message);
  return true;
}

// ── Fetch FanGraphs ─────────────────────────────────────────────────────────
// Offseason: next season's preseason Steamer. In season: rest-of-season Steamer.
function fetchFG(stats) {
  var type = isOffseason() ? "steamer" : "steamerr";
  var url  = FG_BASE + "?type=" + type + "&stats=" + stats + "&pos=all&team=0&players=0&lg=all";
  var resp = UrlFetchApp.fetch(url, FG_OPTS);
  if (resp.getResponseCode() !== 200)
    throw new Error("FanGraphs " + resp.getResponseCode() + " for type=" + type + " stats=" + stats);
  Logger.log("Projection type: " + type);
  return JSON.parse(resp.getContentText());
}

// ── CSV builder ─────────────────────────────────────────────────────────────
function toCsv(rows, cols) {
  var lines = [cols.join(",")];
  rows.forEach(function(row) {
    var vals = cols.map(function(col) {
      var v = (row[col] === null || row[col] === undefined) ? "" : String(row[col]);
      return (v.indexOf(",") >= 0 || v.indexOf('"') >= 0)
        ? '"' + v.replace(/"/g, '""') + '"' : v;
    });
    lines.push(vals.join(","));
  });
  return lines.join("\n");
}

// ── GitHub push ─────────────────────────────────────────────────────────────
function getFileSha(token, path) {
  var url  = "https://api.github.com/repos/" + GITHUB_OWNER + "/" + GITHUB_REPO + "/contents/" + path;
  var resp = UrlFetchApp.fetch(url, {
    method: "get",
    headers: { "Authorization": "token " + token },
    muteHttpExceptions: true
  });
  return resp.getResponseCode() === 200 ? JSON.parse(resp.getContentText()).sha : null;
}

function pushFile(token, path, csvContent, message) {
  var sha     = getFileSha(token, path);
  var payload = {
    message:   message,
    content:   Utilities.base64Encode(csvContent, Utilities.Charset.UTF_8),
    committer: { name: "Apps Script Bot", email: "bot@example.com" }
  };
  if (sha) payload.sha = sha;

  var resp = UrlFetchApp.fetch(
    "https://api.github.com/repos/" + GITHUB_OWNER + "/" + GITHUB_REPO + "/contents/" + path,
    {
      method:  "put",
      headers: { "Authorization": "token " + token, "Content-Type": "application/json" },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    }
  );
  var code = resp.getResponseCode();
  if (code !== 200 && code !== 201)
    throw new Error("GitHub push failed (" + code + "): " + resp.getContentText().substring(0, 300));
  Logger.log("✓ " + path + " pushed (HTTP " + code + ")");
}

var HIT_COLS = ["Name","Team","PA","AB","H","HR","R","BB","HBP","OBP","SLG"];
var PIT_COLS = ["Name","Team","GS","G","IP","HR","SO","BB","HR/9","WHIP","ERA"];
function hitRow(r) {
  return { Name:r.PlayerName, Team:r.Team, PA:r.PA, AB:r.AB, H:r.H,
           HR:r.HR, R:r.R, BB:r.BB, HBP:r.HBP, OBP:r.OBP, SLG:r.SLG };
}
function pitRow(r) {
  return { Name:r.PlayerName, Team:r.Team, GS:r.GS, G:r.G, IP:r.IP,
           HR:r.HR, SO:r.SO, BB:r.BB, "HR/9":r["HR/9"], WHIP:r.WHIP, ERA:r.ERA };
}

// ── Update projections ("this season") ──────────────────────────────────────
function updateProjections() {
  var token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  if (!token) throw new Error("GITHUB_TOKEN not set — see Project Settings → Script properties");

  var today = new Date().toISOString().split("T")[0];
  var tag = (isOffseason() ? seasonYear() + " preseason" : "rest-of-season");

  Logger.log("Fetching hitting projections (" + tag + ")...");
  var hitRows = fetchFG("bat").filter(function(r) { return r.PlayerName; }).map(hitRow);
  Logger.log(hitRows.length + " hitters");
  checkedPush(token, "data/proj_hitting.csv", hitRows, HIT_COLS,
              "Auto-update hitting projections (" + tag + ") " + today, MIN_HITTERS);

  Logger.log("Fetching pitching projections (" + tag + ")...");
  var pitRows = fetchFG("pit").filter(function(r) { return r.PlayerName; }).map(pitRow);
  Logger.log(pitRows.length + " pitchers");
  checkedPush(token, "data/proj_pitching.csv", pitRows, PIT_COLS,
              "Auto-update pitching projections (" + tag + ") " + today, MIN_PITCHERS);

  Logger.log("Done! " + hitRows.length + " hitters, " + pitRows.length + " pitchers.");
}

// ── Update standings ────────────────────────────────────────────────────────
function updateStandings() {
  if (isOffseason()) {
    Logger.log("Offseason: standings not updated (last season's final stays in data/standings.csv).");
    return;
  }
  var LEAGUE_ID = "1648";
  var token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  if (!token) throw new Error("GITHUB_TOKEN not set — see Project Settings → Script properties");

  // ── 1. Build TeamID → name from roster.csv already in the repo ───────────
  var rosterUrl = "https://raw.githubusercontent.com/" + GITHUB_OWNER + "/" + GITHUB_REPO + "/main/data/roster.csv";
  var rosterText = UrlFetchApp.fetch(rosterUrl, {
    headers: { "User-Agent": "Mozilla/5.0" },
    muteHttpExceptions: true
  }).getContentText();

  var rosterLines = rosterText.trim().split("\n");
  var rosterHeader = parseCsvLine(rosterLines[0]);
  var tidIdx  = rosterHeader.indexOf("TeamID");
  var nameIdx = rosterHeader.indexOf("Team Name");
  var teamMap = {};
  for (var i = 1; i < rosterLines.length; i++) {
    var cols = parseCsvLine(rosterLines[i]);
    var tid  = (cols[tidIdx]  || '').trim();
    var name = (cols[nameIdx] || '').trim();
    if (tid && name && !teamMap[tid]) teamMap[tid] = name;
  }
  Logger.log("Teams mapped: " + Object.keys(teamMap).length);

  // ── 2. Fetch standingsMeter for category stats ────────────────────────────
  var today = new Date().toISOString().slice(0, 10);
  var meterResp = UrlFetchApp.fetch(
    "https://ottoneu.fangraphs.com/" + LEAGUE_ID + "/ajax/standingsMeter?date=" + today,
    { headers: { "User-Agent": "Mozilla/5.0" }, muteHttpExceptions: true }
  );
  Logger.log("Meter status: " + meterResp.getResponseCode());
  Logger.log("Meter response: " + meterResp.getContentText().substring(0, 500));
  var meter = JSON.parse(meterResp.getContentText());
  Logger.log("TOPKEYS: " + JSON.stringify(Object.keys(meter)));
  Logger.log("STATSET: " + JSON.stringify(meter.leagueStatSet));

  // Map statID → stat name from leagueStatSet
  var statNames = {};
  ["batting", "pitching"].forEach(function(side) {
    (meter.leagueStatSet[side] || []).forEach(function(s) {
      statNames[s.ID] = s.StatName;
    });
  });

  // Build teamStats: { teamId: { R: "397", HR: "114", ... } }
  var teamStats = {};
  Object.keys(meter.stats).forEach(function(statId) {
    var statName = statNames[statId];
    if (!statName) return;
    meter.stats[statId].teams.forEach(function(t) {
      if (!teamStats[t.TeamID]) teamStats[t.TeamID] = {};
      teamStats[t.TeamID][statName] = t.Value;
    });
  });

  // ── 3. Estimate games / IP from today's date ──────────────────────────────
  var now   = new Date();
  var year  = now.getFullYear();
  var start = new Date(year + "-04-01");
  var end   = new Date(year + "-10-01");
  var frac  = Math.min(1, Math.max(0, (now - start) / (end - start)));
  var games = Math.round(frac * 162);
  var ip    = Math.round(frac * 1400);
  Logger.log("Season fraction: " + frac.toFixed(3) + " → games=" + games + " ip=" + ip);

  // ── 4. Build CSV rows ─────────────────────────────────────────────────────
  var header = ["Team","Games","R","HR","OBP","SLG","IP","K","HR/9","ERA","WHIP"];
  var rows = [header.join(",")];

  Object.keys(teamStats).forEach(function(tid) {
    var name = teamMap[tid];
    if (!name) { Logger.log("No name for TeamID " + tid); return; }
    var s = teamStats[tid];
    var row = [
      '"' + name.replace(/"/g, '""') + '"',
      games,
      s["R"]    || 0,
      s["HR"]   || 0,
      s["OBP"]  || 0,
      s["SLG"]  || 0,
      ip,
      s["K"]    || 0,
      s["HR9"]  || 0,
      s["ERA"]  || 0,
      s["WHIP"] || 0
    ];
    rows.push(row.join(","));
  });

  Logger.log("Rows built: " + (rows.length - 1) + " teams");
  if (rows.length - 1 < 10) {
    Logger.log("✗ NOT pushing standings: only " + (rows.length - 1) + " teams.");
    return;
  }

  // ── 5. Push to GitHub ─────────────────────────────────────────────────────
  var csv = rows.join("\n");
  pushFile(token, "data/standings.csv", csv, "Auto-update standings " + now.toISOString().slice(0,10));
  Logger.log("standings.csv pushed.");
}

// ── CSV line parser (handles quoted fields) ─────────────────────────────────
function parseCsvLine(line) {
  var result = [], cur = '', inQ = false;
  for (var i = 0; i < line.length; i++) {
    var c = line[i];
    if (c === '"') { inQ = !inQ; }
    else if (c === ',' && !inQ) { result.push(cur); cur = ''; }
    else { cur += c; }
  }
  result.push(cur);
  return result;
}

// ── Update roster ───────────────────────────────────────────────────────────
function updateRoster() {
  var LEAGUE_ID = "1648";
  var token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  if (!token) throw new Error("GITHUB_TOKEN not set — see Project Settings → Script properties");

  var url  = "https://ottoneu.fangraphs.com/" + LEAGUE_ID + "/rosterexport?csv=1";
  var resp = UrlFetchApp.fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0" },
    muteHttpExceptions: true
  });
  var code = resp.getResponseCode();
  var csv  = resp.getContentText();
  Logger.log("Roster export status: " + code);
  Logger.log("First line: " + (csv.split("\n")[0] || "").slice(0, 120));

  // Safety guard: only push if this really is the roster CSV. If Ottoneu returned
  // a Cloudflare challenge or login page, csv is HTML — pushing it would corrupt
  // data/roster.csv and break every tool.
  var header = csv.split("\n")[0] || "";
  var looksValid = code === 200
    && header.indexOf("TeamID") !== -1
    && header.indexOf("Salary") !== -1
    && header.indexOf("<") === -1;
  if (!looksValid) {
    throw new Error("Roster export did not return expected CSV (HTTP " + code +
      "). NOT pushing — repo roster.csv left untouched. First 200 chars: " +
      csv.slice(0, 200));
  }

  var rowCount = csv.trim().split("\n").length - 1;
  Logger.log("Roster rows: " + rowCount);
  pushFile(token, "data/roster.csv", csv, "Auto-update roster " + new Date().toISOString().slice(0, 10));
  Logger.log("roster.csv pushed.");
}

// ── Probe future-year projection types ──────────────────────────────────────
function probeFutureProjections() {
  var candidates = [
    { label: 'zips2027 (literal type)',      url: FG_BASE + '?type=zips2027&stats=bat&pos=all&team=0&players=0' },
    { label: 'zips + season=2027',           url: FG_BASE + '?type=zips&season=2027&stats=bat&pos=all&team=0&players=0' },
    { label: 'zips2028 (literal type)',      url: FG_BASE + '?type=zips2028&stats=bat&pos=all&team=0&players=0' },
    { label: 'zips + season=2028',           url: FG_BASE + '?type=zips&season=2028&stats=bat&pos=all&team=0&players=0' },
  ];

  candidates.forEach(function(c) {
    Logger.log('── ' + c.label + ' ──');
    Logger.log('URL: ' + c.url);
    try {
      var resp = UrlFetchApp.fetch(c.url, FG_OPTS);
      var code = resp.getResponseCode();
      Logger.log('HTTP ' + code);
      if (code !== 200) { Logger.log('Body: ' + resp.getContentText().slice(0, 200)); return; }
      var data = JSON.parse(resp.getContentText());
      Logger.log('Row count: ' + data.length);
      if (data.length) {
        var r = data[0];
        Logger.log('Sample: ' + r.PlayerName + ' | PA=' + r.PA + ' | HR=' + r.HR + ' | Season=' + r.Season);
        Logger.log('Keys: ' + Object.keys(r).join(', '));
      }
    } catch (e) {
      Logger.log('ERROR: ' + e);
    }
    Logger.log('');
  });
}
function probeZipsFuture() {
  var candidates = [
    { label: 'zipsp1', url: FG_BASE + '?type=zipsp1&stats=bat&pos=all&team=0&players=0&lg=all' },
    { label: 'zipsp2', url: FG_BASE + '?type=zipsp2&stats=bat&pos=all&team=0&players=0&lg=all' },
    { label: 'zips (this season)', url: FG_BASE + '?type=zips&stats=bat&pos=all&team=0&players=0&lg=all' },
  ];
  candidates.forEach(function(c) {
    Logger.log('── ' + c.label + ' ──');
    try {
      var resp = UrlFetchApp.fetch(c.url, FG_OPTS);  // same FG_OPTS as fetchFG — NO cookies
      var code = resp.getResponseCode();
      Logger.log('HTTP ' + code);
      if (code !== 200) { Logger.log('Body: ' + resp.getContentText().slice(0, 300)); return; }
      var data = JSON.parse(resp.getContentText());
      Logger.log('Row count: ' + data.length);
      var judge = data.filter(function(r) { return r.PlayerName === 'Aaron Judge'; })[0];
      Logger.log('Judge: PA=' + (judge && judge.PA) + ' HR=' + (judge && judge.HR));
    } catch (e) { Logger.log('ERROR: ' + e); }
  });
}

// ── Fetch future-year ZiPS projections ──────────────────────────────────────
function fetchFGFuture(stats, type) {
  var url  = FG_BASE + "?type=" + type + "&stats=" + stats + "&pos=all&team=0&players=0&lg=all";
  var resp = UrlFetchApp.fetch(url, FG_OPTS);
  if (resp.getResponseCode() !== 200)
    throw new Error("FanGraphs " + resp.getResponseCode() + " for type=" + type + " stats=" + stats);
  return JSON.parse(resp.getContentText());
}

// ── Update Y1/Y2 (future-year ZiPS) projections ─────────────────────────────
// zipsp1/zipsp2 = one and two years after FanGraphs' current season. They go empty when
// FanGraphs rolls over to the next season (early November) until that winter's ZiPS
// release; the row guard keeps the last good files until then.
function updateFutureProjections() {
  var token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  if (!token) throw new Error("GITHUB_TOKEN not set — see Project Settings → Script properties");

  var today = new Date().toISOString().split("T")[0];
  var base = seasonYear();
  var years = [
    { type: "zipsp1", label: "y1", tag: "Y1 (" + (base + 1) + ")" },
    { type: "zipsp2", label: "y2", tag: "Y2 (" + (base + 2) + ")" }
  ];

  years.forEach(function(y) {
    Logger.log("Fetching " + y.tag + " hitting...");
    var hitRows = fetchFGFuture("bat", y.type).filter(function(r) { return r.PlayerName; }).map(hitRow);
    Logger.log(hitRows.length + " hitters for " + y.tag);
    checkedPush(token, "data/proj_hitting_" + y.label + ".csv", hitRows, HIT_COLS,
                "Auto-update " + y.tag + " hitting projections " + today, MIN_FUTURE);

    Logger.log("Fetching " + y.tag + " pitching...");
    var pitRows = fetchFGFuture("pit", y.type).filter(function(r) { return r.PlayerName; }).map(pitRow);
    Logger.log(pitRows.length + " pitchers for " + y.tag);
    checkedPush(token, "data/proj_pitching_" + y.label + ".csv", pitRows, PIT_COLS,
                "Auto-update " + y.tag + " pitching projections " + today, MIN_FUTURE);
  });

  Logger.log("Future projections update complete.");
}

function probeBoardPublic() {
  var url = "https://www.fangraphs.com/api/prospects/board/prospects-list-combined" +
    "?pos=all&lg=2,4,5,6,7,8,9,10,11,14,12,13,15,16,17,18,30,32&stats=bat&qual=0&type=0" +
    "&team=&season=2026&seasonend=2026&draft=2026prospect&valueheader=prospect-new&quickleaderboard=2026all";
  var opts = {
    method: "get",
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept": "application/json, text/plain, */*",
      "Referer": "https://www.fangraphs.com/prospects/the-board-scouting-and-stats"
    },
    muteHttpExceptions: true
  };
  var resp = UrlFetchApp.fetch(url, opts);
  var code = resp.getResponseCode();
  var text = resp.getContentText();
  Logger.log("HTTP " + code);
  Logger.log("Length: " + text.length);
  Logger.log("First 300: " + text.slice(0, 300));
  try {
    var data = JSON.parse(text);
    var arr = Array.isArray(data) ? data : (data.data || data.prospects || data.board || null);
    if (Array.isArray(arr)) {
      Logger.log("Row count: " + arr.length);
      Logger.log("Sample keys: " + Object.keys(arr[0]).join(", "));
      Logger.log("Sample row: " + JSON.stringify(arr[0]).slice(0, 500));
    } else {
      Logger.log("Top-level keys: " + Object.keys(data).join(", "));
    }
  } catch (e) {
    Logger.log("Not JSON: " + e);
  }
}
function probeBoardShape() {
  var url = "https://www.fangraphs.com/api/prospects/board/prospects-list-combined" +
    "?pos=all&lg=2,4,5,6,7,8,9,10,11,14,12,13,15,16,17,18,30,32&stats=bat&qual=0&type=0" +
    "&team=&season=2026&seasonend=2026&draft=2026prospect&valueheader=prospect-new&quickleaderboard=2026all";
  var opts = {
    method: "get",
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept": "application/json, text/plain, */*",
      "Referer": "https://www.fangraphs.com/prospects/the-board-scouting-and-stats"
    },
    muteHttpExceptions: true
  };
  var data = JSON.parse(UrlFetchApp.fetch(url, opts).getContentText());

  Logger.log("dataScout count: " + data.dataScout.length);
  Logger.log("dataScout keys: " + Object.keys(data.dataScout[0]).join(", "));
  Logger.log("dataStats count: " + data.dataStats.length);
  Logger.log("dataStats keys: " + Object.keys(data.dataStats[0]).join(", "));

  // Griffin appears in your current manual export — use him as a known anchor.
  var griffin = data.dataScout.filter(function(r) { return r.playerName === "Konnor Griffin"; })[0];
  Logger.log("Griffin scout row: " + JSON.stringify(griffin));

  // Find a pitcher to confirm the schema covers both.
  var pitcher = data.dataScout.filter(function(r) { return /P/.test(r.positionDB) && r.positionDB !== "SS"; })[0];
  Logger.log("Sample pitcher scout row: " + JSON.stringify(pitcher));

  var statRow = data.dataStats.filter(function(r) { return r.playerName === "Konnor Griffin"; })[0];
  Logger.log("Griffin stats row: " + JSON.stringify(statRow));
}
function probeBoardPitchAndJoin() {
  var base = "https://www.fangraphs.com/api/prospects/board/prospects-list-combined" +
    "?pos=all&lg=2,4,5,6,7,8,9,10,11,14,12,13,15,16,17,18,30,32&qual=0&type=0" +
    "&team=&season=2026&seasonend=2026&draft=2026prospect&valueheader=prospect-new&quickleaderboard=2026all";
  var opts = {
    method: "get",
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept": "application/json, text/plain, */*",
      "Referer": "https://www.fangraphs.com/prospects/the-board-scouting-and-stats"
    },
    muteHttpExceptions: true
  };

  function trimScout(r) {
    return { playerName:r.playerName, UPID:r.UPID, positionDB:r.positionDB,
             mlevel:r.mlevel, llevel:r.llevel, Team:r.Team, Age:r.Age,
             cFV:r.cFV, Ovr_Rank:r.Ovr_Rank, Org_Rank:r.Org_Rank, cRisk:r.cRisk,
             ETA_Current:r.ETA_Current,
             pHit:r.pHit, fHit:r.fHit, pGame:r.pGame, fGame:r.fGame,
             pRaw:r.pRaw, fRaw:r.fRaw, pSpd:r.pSpd, fSpd:r.fSpd,
             pFld:r.pFld, fFld:r.fFld, pArm:r.pArm, fArm:r.fArm,
             pFB:r.pFB, fFB:r.fFB, pSL:r.pSL, fSL:r.fSL, pCB:r.pCB, fCB:r.fCB,
             pCH:r.pCH, fCH:r.fCH, pSPL:r.pSPL, fSPL:r.fSPL, pCT:r.pCT, fCT:r.fCT,
             pCMD:r.pCMD, fCMD:r.fCMD };
  }

  // ── BAT call: find someone STILL in the minors ──
  var batData = JSON.parse(UrlFetchApp.fetch(base + "&stats=bat", opts).getContentText());
  Logger.log("BAT dataScout count: " + batData.dataScout.length);
  var minorHitter = batData.dataScout.filter(function(r) { return r.mlevel && r.mlevel !== "MLB"; })[0];
  Logger.log("Minors hitter scout: " + JSON.stringify(trimScout(minorHitter)));
  var hitterStats = batData.dataStats.filter(function(r) { return r.UPID === minorHitter.UPID; })[0];
  Logger.log("Matched stats row (join by UPID): " + JSON.stringify(hitterStats));

  // ── PIT call ──
  var pitData = JSON.parse(UrlFetchApp.fetch(base + "&stats=pit", opts).getContentText());
  Logger.log("PIT dataScout count: " + pitData.dataScout.length);
  Logger.log("PIT dataStats count: " + pitData.dataStats.length);
  var pitcher = pitData.dataScout.filter(function(r) { return r.mlevel && r.mlevel !== "MLB"; })[0];
  Logger.log("Minors pitcher scout: " + JSON.stringify(trimScout(pitcher)));
  var pitcherStats = pitData.dataStats.filter(function(r) { return r.UPID === pitcher.UPID; })[0];
  Logger.log("Matched pitcher stats row: " + JSON.stringify(pitcherStats));
}
function fetchBoard(statsType) {
  var url = "https://www.fangraphs.com/api/prospects/board/prospects-list-combined" +
    "?pos=all&lg=2,4,5,6,7,8,9,10,11,14,12,13,15,16,17,18,30,32&stats=" + statsType +
    "&qual=0&type=0&team=&season=2026&seasonend=2026&draft=2026prospect" +
    "&valueheader=prospect-new&quickleaderboard=2026all";
  var opts = {
    method: "get",
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept": "application/json, text/plain, */*",
      "Referer": "https://www.fangraphs.com/prospects/the-board-scouting-and-stats"
    },
    muteHttpExceptions: true
  };
  var resp = UrlFetchApp.fetch(url, opts);
  if (resp.getResponseCode() !== 200)
    throw new Error("FanGraphs Board " + resp.getResponseCode() + " for stats=" + statsType);
  return JSON.parse(resp.getContentText());
}

function updateProspects() {
  var token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  if (!token) throw new Error("GITHUB_TOKEN not set — see Project Settings → Script properties");
  var today = new Date().toISOString().split("T")[0];

  Logger.log("Fetching hitter board...");
  var bat = fetchBoard("bat");
  Logger.log("Fetching pitcher board...");
  var pit = fetchBoard("pit");

  // Merge scouting rows by UPID. A true two-way player appears in both calls
  // with only half his grades populated in each — merge rather than pick one.
  var byId = {};
  function mergeScout(rows) {
    rows.forEach(function(r) {
      var id = r.UPID;
      if (!id) return;
      if (!byId[id]) byId[id] = r;
      else {
        Object.keys(r).forEach(function(k) {
          if ((byId[id][k] === null || byId[id][k] === undefined) && r[k] != null) byId[id][k] = r[k];
        });
      }
    });
  }
  mergeScout(bat.dataScout);
  mergeScout(pit.dataScout);
  var scoutRows = Object.keys(byId).map(function(id) { return byId[id]; });
  Logger.log("Merged scouting rows: " + scoutRows.length);

  // ── data/prospects.csv — same 22 columns as before, PLUS present/future
  //    tool and pitch grades appended. Column NAMES are all parseProspectsCSV
  //    needs (it looks up by header, not position), so this is backward-safe.
  var prospectCols = [
    "Top 100","Org Rk","Name","Org","Pos","Current Level","ETA","FV","Risk","Trend",
    "Age","Ht","Wt","B","T","Sign Yr","Sign Mkt","Sign Org","Bonus","Signed From","Report","Video",
    "Hit_Now","Hit_Fut","Game_Now","Game_Fut","Raw_Now","Raw_Fut","Spd_Now","Spd_Fut",
    "Fld_Now","Fld_Fut","Arm_Now","Arm_Fut",
    "FB_Now","FB_Fut","SL_Now","SL_Fut","CB_Now","CB_Fut","CH_Now","CH_Fut",
    "SPL_Now","SPL_Fut","CT_Now","CT_Fut","CMD_Now","CMD_Fut"
  ];
  var prospectRows = scoutRows
    .filter(function(r) { return r.playerName && r.FV_Current; })
    .map(function(r) {
      return {
        "Top 100": r.Ovr_Rank || "", "Org Rk": r.Org_Rank || "",
        "Name": r.playerName, "Org": r.Team || "", "Pos": r.positionDB || "",
        "Current Level": r.mlevel || "", "ETA": r.ETA_Current || "",
        "FV": r.FV_Current || "", "Risk": r.cRisk || "", "Trend": r.Trend || "",
        "Age": r.Age || "", "Ht": r.cHeight || "", "Wt": r.cWeight || "",
        "B": r.Bats || "", "T": r.Throws || "",
        "Sign Yr": r.Signed_Yr || "", "Sign Mkt": r.Signed_Mkt || "", "Sign Org": r.Signed_Org || "",
        "Bonus": r.Sign_Bonus || "", "Signed From": r.cDraftSchool || "",
        "Report": r.TLDR || "", "Video": r.YouTube || "",
        "Hit_Now": r.pHit, "Hit_Fut": r.fHit, "Game_Now": r.pGame, "Game_Fut": r.fGame,
        "Raw_Now": r.pRaw, "Raw_Fut": r.fRaw, "Spd_Now": r.pSpd, "Spd_Fut": r.fSpd,
        "Fld_Now": r.pFld, "Fld_Fut": r.fFld, "Arm_Now": r.pArm, "Arm_Fut": r.fArm,
        "FB_Now": r.pFB, "FB_Fut": r.fFB, "SL_Now": r.pSL, "SL_Fut": r.fSL,
        "CB_Now": r.pCB, "CB_Fut": r.fCB, "CH_Now": r.pCH, "CH_Fut": r.fCH,
        "SPL_Now": r.pSPL, "SPL_Fut": r.fSPL, "CT_Now": r.pCT, "CT_Fut": r.fCT,
        "CMD_Now": r.pCMD, "CMD_Fut": r.fCMD
      };
    });
  Logger.log(prospectRows.length + " prospects (with FV)");
  checkedPush(token, "data/prospects.csv", prospectRows, prospectCols,
              "Auto-update prospects " + today, MIN_PROSPECTS);

  // ── data/prospects_stats_hitting.csv ──────────────────────────────────────
  var hitStatCols = ["Name","Level","Team","Age","G","PA","AB","H","HR","R","RBI","BB","SO","SB",
                      "AVG","OBP","SLG","wOBA","wRC+","BB%","K%","ISO"];
  var hitStatRows = bat.dataStats
    .filter(function(r) { return r.PlayerName; })
    .map(function(r) {
      return { Name:r.PlayerName, Level:r.level, Team:r.AffAbbName, Age:r.Age,
               G:r.G, PA:r.PA, AB:r.AB, H:r.H, HR:r.HR, R:r.R, RBI:r.RBI, BB:r.BB, SO:r.SO, SB:r.SB,
               AVG:r.AVG, OBP:r.OBP, SLG:r.SLG, "wOBA":r.wOBA, "wRC+":r["wRC+"],
               "BB%":r["BB%"], "K%":r["K%"], ISO:r.ISO };
    });
  Logger.log(hitStatRows.length + " hitter stat lines");
  checkedPush(token, "data/prospects_stats_hitting.csv", hitStatRows, hitStatCols,
              "Auto-update prospect hitting stats " + today, MIN_PROSPECTS);

  // ── data/prospects_stats_pitching.csv ─────────────────────────────────────
  var pitStatCols = ["Name","Level","Team","Age","G","GS","IP","ERA","FIP","WHIP","SO","BB",
                      "K/9","BB/9","K%","BB%","HR"];
  var pitStatRows = pit.dataStats
    .filter(function(r) { return r.PlayerName; })
    .map(function(r) {
      return { Name:r.PlayerName, Level:r.level, Team:r.AffAbbName, Age:r.Age,
               G:r.G, GS:r.GS, IP:r.IP, ERA:r.ERA, FIP:r.FIP, WHIP:r.WHIP, SO:r.SO, BB:r.BB,
               "K/9":r["K/9"], "BB/9":r["BB/9"], "K%":r["K%"], "BB%":r["BB%"], HR:r.HR };
    });
  Logger.log(pitStatRows.length + " pitcher stat lines");
  checkedPush(token, "data/prospects_stats_pitching.csv", pitStatRows, pitStatCols,
              "Auto-update prospect pitching stats " + today, MIN_PROSPECTS);

  Logger.log("Done: " + prospectRows.length + " scouting rows, " +
             hitStatRows.length + " hitter lines, " + pitStatRows.length + " pitcher lines.");
}
function probeBoardSeasons() {
  var opts = {
    method: "get",
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept": "application/json, text/plain, */*",
      "Referer": "https://www.fangraphs.com/prospects/the-board-scouting-and-stats"
    },
    muteHttpExceptions: true
  };

  [2026, 2025, 2022, 2019].forEach(function (yr) {
    var url = "https://www.fangraphs.com/api/prospects/board/prospects-list-combined" +
      "?pos=all&lg=2,4,5,6,7,8,9,10,11,14,12,13,15,16,17,18,30,32&stats=bat" +
      "&qual=0&type=0&team=&season=" + yr + "&seasonend=" + yr +
      "&draft=" + yr + "prospect&valueheader=prospect-new&quickleaderboard=" + yr + "all";
    Logger.log("---- season " + yr + " ----");
    try {
      var resp = UrlFetchApp.fetch(url, opts);
      var code = resp.getResponseCode();
      var text = resp.getContentText();
      Logger.log("HTTP " + code + " | length " + text.length);
      if (text.charAt(0) !== "{" && text.charAt(0) !== "[") {
        Logger.log("NOT JSON. First 200: " + text.slice(0, 200).replace(/\s+/g, " "));
        return;
      }
      var data = JSON.parse(text);
      var scout = data.dataScout || [];
      Logger.log("dataScout rows: " + scout.length);
      if (scout.length) {
        var r = scout[0];
        Logger.log("top player: " + r.playerName + " | FV " + r.FV_Current + " | Age " + r.Age);
        var idKeys = Object.keys(r).filter(function (k) {
          return /mlb|mlbam|upid|playerid|prospectid/i.test(k);
        });
        Logger.log("ID-ish keys: " + JSON.stringify(idKeys.map(function (k) { return k + "=" + r[k]; })));
      }
    } catch (e) {
      Logger.log("ERROR: " + e);
    }
  });
}
