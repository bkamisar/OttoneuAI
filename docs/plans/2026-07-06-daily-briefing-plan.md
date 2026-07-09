# Implementation Plan: Daily Email Briefing (Google Apps Script)

Execute mechanically — decisions are pre-answered. The deliverable is ONE new
file in the repo, `scripts/briefing.gs`, containing complete Apps Script code
the user pastes into their existing Apps Script project (same project that has
`updateProjections` / `updateStandings` / `updateRoster` and the `GITHUB_TOKEN`
script property). Do NOT modify shared.js or any HTML page. The implementer
cannot run Apps Script; correctness comes from careful code + the built-in
test function the user runs (verification section at bottom).

## What the email contains (sections in order)
1. **Header** — "⚾ {TEAM_NAME} Daily Briefing — {date}", record of points if
   trivially available (SKIP standings math — out of scope).
2. **Yesterday's box** — one row per MY player who appeared yesterday:
   hitters `Name — 2-4, HR, 2 RBI, R, BB` · pitchers `Name — 6.0 IP, 2 ER,
   7 K (W)`. Players who didn't play are omitted. If no games (off-day),
   section says "No games yesterday."
3. **News** — MLB transactions from the last 48h involving MY players (IL
   placement/activation, recall, option, trade, DFA). Plus OPTIONAL Rotowire
   RSS items matching my players (see Data Sources). Empty → "No roster news."
4. **Today's matchups** —
   - Hitters, grouped by MLB team: "NYY @ BOS 7:05 — vs LHP Crochet (2.95 ERA) ⚠"
     (⚠ opposing starter ERA < 3.30 · 🔥 ERA > 4.60 · nothing between;
     'TBD' when no probable listed).
   - My probable pitchers today: "Yamamoto vs SEA (home)".
5. **Footer** — link to the GitHub Pages tools.

## Architecture (all inside briefing.gs)
- `CONFIG` block at top: `MY_TEAM_ID` (Ottoneu TeamID string — the user fills
  this in ONCE; find it as the first column of their players' rows in
  data/roster.csv — team NAMES change, IDs don't), `EMAIL_TO`,
  `LEAGUE_ID='1648'`, `TIMEZONE='America/New_York'`.
- `dailyBriefing()` — main entry; user adds a daily time trigger 7–8am ET.
- `briefingTest()` — runs everything, `Logger.log`s the plain-text version,
  and emails to EMAIL_TO with subject prefixed "[TEST] ". This is the
  verification path.
- Steps in `dailyBriefing()`:
  1. `getMyPlayers_()` — fetch `https://ottoneu.fangraphs.com/{LEAGUE_ID}/rosterexport?csv=1`
     (same fetch as updateRoster, same UA header), parse CSV, filter rows
     where `TeamID === MY_TEAM_ID`. Extract `Name` + `Position(s)`; build
     `norm(name)` set. `norm()` = lowercase, strip accents
     (`.normalize('NFD').replace(/[̀-ͯ]/g,'')`), collapse spaces,
     strip periods (so "Luis L. Ortiz"/"J.T." variants match).
  2. `getYesterdayBox_(mySet)` — StatsAPI:
     `GET https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={yyyy-MM-dd}`
     (yesterday in TIMEZONE via `Utilities.formatDate`). For each game (both
     doubleheader games included): `GET /api/v1/game/{gamePk}/boxscore`; walk
     `teams.home.players` + `teams.away.players`; match `person.fullName`
     via norm() against mySet. Hitters: use `stats.batting` (ab, hits,
     homeRuns, rbi, runs, baseOnBalls, stolenBases) — include only if ab>0 or
     baseOnBalls>0. Pitchers: `stats.pitching` (inningsPitched, earnedRuns,
     strikeOuts, note W/L/SV from `stats.pitching.note` if present). A player
     can appear in 2 games (DH) — emit one line per game.
  3. `getNews_(mySet)` — StatsAPI:
     `GET /api/v1/transactions?startDate={2 days ago}&endDate={today}`;
     filter `person.fullName` via norm() ∈ mySet; use `typeDesc` +
     `description`. THEN optional Rotowire: try
     `https://www.rotowire.com/rss/news.php?sport=MLB` inside try/catch with
     `muteHttpExceptions:true`; if HTTP 200 and body contains `<item>`, parse
     titles/descriptions with regex (`<title>...<\/title>`), match my players
     by norm() substring, take ≤5. ANY failure → skip silently (comment why:
     Cloudflare/licensing makes this best-effort only).
  4. `getTodayMatchups_(myPlayers)` — StatsAPI:
     `GET /api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher`.
     Build map MLB-team-abbrev → {opp, home/away, gameTime local,
     oppProbable {name, id}}. To place MY players on MLB teams, use the
     roster CSV's `MLB Team` column (it exists — e.g. "NYY"); map Ottoneu
     abbrevs to StatsAPI team abbreviations via a small ALIAS table (fill
     with identity + known diffs: CWS/CHW, WSH/WAS, AZ/ARI, KC/KCR, SD/SDP,
     SF/SFG, TB/TBR — implementer: build the map from the schedule response's
     `teams[].team.abbreviation` and log any of my players whose abbrev
     doesn't resolve rather than throwing).
     For each opposing probable pitcher: one call
     `GET /api/v1/people/{id}/stats?stats=season&group=pitching` → ERA +
     `pitchHand` from `GET /api/v1/people/{id}` (or hydrate person). Cache in
     a map so duplicate starters cost one call. Flags: ⚠ if ERA<3.30,
     🔥 if ERA>4.60.
     My pitchers: if a probable pitcher's norm(name) ∈ mySet → "starts today
     vs X" line.
  5. `buildEmail_(sections)` — returns {plain, html}. HTML: minimal inline
     styles, tables with 1px #ddd borders, green header bar (#1a4429 / gold
     #d9b64e to match the tool theme), max-width 640px. Plain text fallback
     with simple lines.
  6. Send: `MailApp.sendEmail({to: CONFIG.EMAIL_TO, subject, htmlBody, body})`.
  7. OPTIONAL (include, cheap): push the HTML to the repo as
     `data/briefing.html` using the existing `pushFile(token, path, content,
     msg)` helper already in the user's project — wrap in try/catch so email
     still sends if push fails. Note in comments: reuses pushFile from the
     existing script file in the same project (same global namespace).

## Hard requirements / gotchas
- All UrlFetchApp calls: `muteHttpExceptions: true`, check `getResponseCode()`,
  and every section builder returns a safe fallback string on failure — a
  broken section must NEVER kill the whole email. Wrap each section in
  try/catch and put the error one-liner in the email ("Yesterday's box
  unavailable (HTTP 500)") so failures are visible, not silent.
- Dates: ALWAYS `Utilities.formatDate(d, CONFIG.TIMEZONE, 'yyyy-MM-dd')`.
  "Yesterday" = now minus 24h in ET; late-night west-coast games are why the
  trigger should run ≥ 7am ET.
- `inningsPitched` from StatsAPI is a STRING like "6.2" (= 6⅔) — display
  as-is, do not do arithmetic on it.
- Name collisions (two MLB players, same normalized name): acceptable risk;
  mitigate by also comparing MLB team abbrev when available (roster CSV has
  `MLB Team`) — if abbrevs disagree, skip the match and Logger.log it.
- Ohtani: type both ways — he may produce a batting AND a pitching line from
  the same game. That's correct; emit both.
- No games yesterday AND no news AND no games today (full off-day):
  still send ("Quiet day — no games, no news."), so the user can trust that
  no email = something broke.
- Keep total UrlFetchApp calls < ~50/run (schedule 2 + boxscores ≤16 +
  transactions 1 + probables ≤15 + rotowire 1). Consumer quota is 20k/day.

## Also produce (small, in the same PR)
- `scripts/README-briefing.md` — 10-line setup: where to paste, set
  MY_TEAM_ID + EMAIL_TO, run `briefingTest`, authorize scopes
  (Mail + external requests), add daily trigger 7–8am ET, done.

## Out of scope (do NOT build)
- Standings deltas, lineup-optimizer advice, bench/start recommendations
  beyond the ⚠/🔥 starter flags, Rotowire scraping beyond the public RSS
  attempt, ID-map files (Chadwick), and any shared.js/page changes.

## Verification checklist (implementer)
1. `scripts/briefing.gs` parses as valid JS (paste into node --check via a
   temp file, or careful read — no Apps Script runtime locally; MailApp/
   UrlFetchApp/Logger/Utilities are globals, don't shim them).
2. Every UrlFetchApp call has muteHttpExceptions + response-code check.
3. Every section has try/catch with visible fallback text.
4. norm() identical logic applied on BOTH sides of every name comparison.
5. Date handling exclusively via Utilities.formatDate with CONFIG.TIMEZONE.
6. Commit briefing.gs + README; nothing else changed (`git diff --stat`).
7. Tell the user the exact 5 setup steps and that `briefingTest()` is the
   real verification (implementer cannot run Apps Script).
