# Daily Briefing setup

`scripts/briefing.gs` publishes `data/briefing.json` once a day; `briefing.html`
renders it. No email — it lives in the tool site.

1. Open your existing Apps Script project (the one with `updateRoster` /
   `updateStandings` and the `GITHUB_TOKEN` script property).
2. **File → New → Script**, name it `briefing`, and paste all of
   `scripts/briefing.gs` into it. (It reuses that project's `pushFile` helper —
   don't paste it into a fresh project.)
3. In `BRIEFING_CONFIG` at the top, set **`MY_TEAM_ID`** to your Ottoneu TeamID:
   open `data/roster.csv`, find any of your players, copy the value in the first
   column (`TeamID`). Team *names* change; the ID doesn't.
4. Select **`briefingTest`** in the function dropdown and **Run**. Approve the
   auth prompt (external requests + this project's existing scopes). Check the
   Execution log for "Briefing pushed", then open the **Daily Briefing** page and
   refresh — your first briefing should appear. Any unresolved team abbreviations
   are logged (tell the dev if a player's matchup is missing).
5. Add a daily trigger: **Triggers (clock icon) → Add Trigger →** function
   `dailyBriefing`, time-driven, daily, **7–8am ET** (late west-coast finals are
   in by then).

Sources are all free (MLB StatsAPI, Google News RSS, ESPN). Every section fails
independently — a dead source degrades that section, never the whole briefing —
and a full off-day still publishes, so a stale "generated N hours ago" always
means the script itself stopped.
