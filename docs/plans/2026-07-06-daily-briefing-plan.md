# Implementation Plan: Daily Briefing (Apps Script → repo JSON → briefing.html)

Execute mechanically — decisions are pre-answered. NO EMAIL — the briefing is
published to the repo and viewed in the tool site. Deliverables:

1. `scripts/briefing.gs` — complete Apps Script code the user pastes into
   their existing project (alongside updateProjections/updateStandings/
   updateRoster; `GITHUB_TOKEN` script property and the `pushFile` helper
   already exist there — briefing.gs REUSES `pushFile`, do not redefine it).
   Daily trigger fetches all data and pushes **`data/briefing.json`**.
2. `briefing.html` — new page in the suite (clone the structural skeleton of
   an existing simple page): standard nav (marked active), inline styles +
   `<link rel="stylesheet" href="theme.css">`, fetches `./data/briefing.json`
   (cache-busted: `?t=`+Date.now()) and renders it. No shared.js valuation
   calls — this page only renders the JSON (it MAY include shared.js to reuse
   `relativeAge()` for the freshness line; that's fine, autoLoad tolerates it).
3. Nav link "Daily Briefing" added to all 8 existing pages (index, standings,
   roster, trade, fa, bid, prospects, targets), after "Bid Advisor".
4. `scripts/README-briefing.md` — setup steps (≤10 lines).

Do NOT modify shared.js. The implementer cannot run Apps Script; correctness
comes from careful code + `briefingTest()` (verification section at bottom).

## briefing.json schema (script writes, page reads)
```json
{
  "generatedAt": "2026-07-06T11:05:00Z",
  "dateLabel": "Sunday, July 6",
  "teamId": "…",
  "yesterday": {
    "note": "",                     // "No games yesterday." on off-days
    "hitters": [ { "name": "Juan Soto", "mlb": "NYM",
                   "line": "2-4, HR, 3 RBI, BB",
                   "blurb": "…recap sentence(s), ≤2, may be empty…" } ],
    "pitchers": [ { "name": "Yoshinobu Yamamoto", "mlb": "LAD",
                    "line": "6.2 IP, 2 ER, 8 K (W)", "blurb": "" } ]
  },
  "news": {
    "transactions": [ "7/5 — Placed RHP X on the 15-day IL (forearm)" ],
    "flagged": [ { "name": "…", "reason": "monster game | transaction | absent from box",
                   "items": [ { "title": "…", "link": "…" } ] } ],
    "league": [ { "title": "…", "link": "…" } ]   // ESPN catch-all matching my players
  },
  "matchups": {
    "hitters": [ { "mlb": "NYM", "players": ["Juan Soto", "Pete Alonso"],
                   "game": "NYM @ ATL 7:15", "opp": "vs RHP Spencer Strider",
                   "era": 3.05, "flag": "tough" } ],   // flag: "tough" | "target" | ""
    "myStarters": [ { "name": "Yoshinobu Yamamoto", "game": "LAD vs SEA (home)" } ],
    "note": ""                      // "No games today." on off-days
  },
  "errors": [ "Yesterday's box unavailable (HTTP 500)" ]   // section-level failures, page shows them
}
```

## scripts/briefing.gs
- `CONFIG`: `MY_TEAM_ID` (Ottoneu TeamID string — user fills once; find it in
  the first column of their players' rows in data/roster.csv; team NAMES
  change, IDs don't), `LEAGUE_ID='1648'`, `TIMEZONE='America/New_York'`,
  `GITHUB_OWNER/REPO` consts matching the existing script file.
- `dailyBriefing()` — main entry; user adds a daily time trigger 7–8am ET.
  Builds the JSON object then
  `pushFile(token, 'data/briefing.json', JSON.stringify(obj, null, 1),
  'Daily briefing ' + dateStr)`.
- `briefingTest()` — same pipeline, `Logger.log(JSON.stringify(obj, null, 2))`
  AND does the push (harmless; lets the user verify end-to-end on the page).

### Pipeline steps
1. `getMyPlayers_()` — fetch
   `https://ottoneu.fangraphs.com/{LEAGUE_ID}/rosterexport?csv=1` (same UA
   header as updateRoster), parse CSV, keep rows `TeamID === MY_TEAM_ID`.
   Carry `Name`, `MLB Team` abbrev, `Position(s)`. `norm(name)` = lowercase,
   strip accents (`.normalize('NFD').replace(/[̀-ͯ]/g,'')`), strip periods,
   collapse spaces. Build Map norm→display.
2. `getYesterdayBox_(my)` — StatsAPI
   `GET https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={yesterday}`
   (dates ALWAYS via `Utilities.formatDate(d, CONFIG.TIMEZONE, 'yyyy-MM-dd')`;
   yesterday = now − 24h). For each game (doubleheaders included):
   `GET /api/v1/game/{gamePk}/boxscore`; walk both teams' `players`; match
   `person.fullName` by norm(); guard name collisions by also comparing the
   MLB team abbrev from the roster CSV when it resolves — mismatch → skip +
   log. Hitters (`stats.batting`, ab>0 or bb>0): `H-AB, HR, RBI, R, BB, SB`
   (omit zero items except H-AB). Pitchers (`stats.pitching`, ip!=='0.0'):
   `IP, ER, K` + W/L/SV from `note`. `inningsPitched` is a STRING ("6.2" =
   6⅔) — display as-is, never do arithmetic. Ohtani may emit both a hitter
   and pitcher line — correct. Record the set of gamePks + which of my
   players appeared (feeds recaps + absence detection).
3. `getRecaps_(gamePks, my)` — for each gamePk with a my-player (no cap):
   `GET /api/v1/game/{gamePk}/content`; take `editorial.recap.mlb.body`
   (fallback `.headline`); strip tags `.replace(/<[^>]+>/g,' ')`; split into
   sentences; keep sentences containing a my-player norm() name, **≤2
   sentences per player** (hard cap, user-confirmed); attach as `blurb` on
   that player's yesterday line.
4. `getNews_(my, box)` —
   (a) `GET /api/v1/transactions?startDate={2 days ago}&endDate={today}`;
   filter person by norm() ∈ my; render `date — description`.
   (b) Flagged players — **NO cap on player count** (user-confirmed):
   flags = transaction players ∪ monster lines (HR≥2 | RBI≥5 | K≥10) ∪
   "his MLB team played yesterday but he's absent from every box" (compute
   from step 2's schedule + appearances; single-day only, no streak state).
   Per flagged player: Google News RSS
   `https://news.google.com/rss/search?q="{Player Name}"+mlb&hl=en-US&gl=US&ceid=US:en`,
   regex top 2 `<item>`→title+link. (Realistic volume is <15 players/day;
   UrlFetchApp quota 20k/day makes an explicit cap unnecessary.)
   (c) ESPN catch-all: one call
   `https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/news?limit=25`,
   keep items whose headline/description matches a my-player norm() name.
5. `getTodayMatchups_(my)` — `GET /api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher`.
   Map my hitters onto games via roster `MLB Team` abbrev; resolve abbrev
   differences against the schedule's own `teams[].team.abbreviation` values
   and Logger.log any of my players whose abbrev doesn't resolve (don't
   throw). Opposing probable: fetch once per unique pitcher id —
   `GET /api/v1/people/{id}?hydrate=stats(group=[pitching],type=[season])`
   → ERA + pitchHand. flag = "tough" if ERA<3.30, "target" if ERA>4.60.
   No probable listed → opp "TBD". My starters: probable whose norm(name) ∈
   my → myStarters entry.
6. Assemble JSON per schema; every step wrapped in try/catch; a failed step
   contributes a one-liner to `errors[]` and its section renders what it has —
   a broken source must NEVER kill the push. Full off-day still pushes (notes
   filled in) so a stale `generatedAt` always means the SCRIPT broke.

## briefing.html
- Standard suite page: h1 "Daily Briefing", nav (active), theme.css link.
- Fetch `./data/briefing.json?t=`+Date.now(); if 404 → friendly "No briefing
  yet — set up scripts/briefing.gs (see scripts/README-briefing.md)".
- Header line: `dateLabel` + "generated {relativeAge(Date.parse(generatedAt))}"
  (shared.js is loaded for relativeAge; guard with a plain fallback if absent).
  If generatedAt > 30h old, show a stale warning banner (reuse .error styling).
- Sections: Yesterday (two tables: hitters/pitchers; `blurb` as an italic
  muted line under the player's row — colspan cell), News (transactions list;
  per-flagged-player headline links, `target="_blank" rel="noopener"`; league
  items), Today's Matchups (hitters grouped by MLB team with ⚠ tough /
  🔥 target flags rendered from `flag`; My Starters list), and `errors[]`
  as small warning lines at the bottom.
- ALL rendering via createElement/textContent (NO innerHTML with fetched
  strings — recap/news text is external input; links set via `href` property).

## Gotchas carried over
- Every UrlFetchApp call: `muteHttpExceptions:true` + response-code check.
- All dates via Utilities.formatDate with CONFIG.TIMEZONE; trigger ≥7am ET so
  west-coast finals are in.
- Section-level try/catch everywhere; `errors[]` makes failures visible.
- Total calls/run ≈ schedule 2 + boxscores ≤16 + content ≤16 + transactions 1
  + gnews ≤15 + espn 1 + probables ≤15 ≈ 65 — fine.

## Verification checklist (implementer)
1. `briefing.gs` and `briefing.html` are valid JS/HTML (careful read; no Apps
   Script shims — MailApp is NOT used anywhere).
2. Every UrlFetchApp call has muteHttpExceptions + code check; every section
   try/caught into `errors[]`.
3. norm() identical on both sides of every name comparison.
4. briefing.html renders a hand-written sample briefing.json correctly in the
   local preview (create a temp data/briefing.json with 2 hitters incl. a
   blurb, 1 pitcher, 1 transaction, 1 flagged player w/ 2 links, 2 matchups
   w/ both flags, 1 error line; verify layout + theme + no console errors;
   DELETE the temp file before committing — the real one comes from the bot).
5. Nav link present on all 9 pages; test.html untouched; 90/90 still passes.
6. Commit: briefing.html + scripts/briefing.gs + scripts/README-briefing.md +
   8 nav-touched pages. `git diff --stat` shows nothing else.
7. Tell the user: paste briefing.gs into the Apps Script project, set
   MY_TEAM_ID, run briefingTest() (check the execution log + the live page),
   then add the daily 7–8am ET trigger on dailyBriefing.
