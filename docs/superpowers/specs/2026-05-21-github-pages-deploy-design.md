# GitHub Pages Deployment Design Spec
**Date:** 2026-05-21  
**Scope:** Host the Ottoneu league analysis tool on GitHub Pages so it is accessible from any device, with CSV data stored in the repo and auto-loaded on every page load.

---

## Goal

The app is currently local-only (file:// + localStorage). This change makes it accessible at a permanent URL from any browser, with all data files (roster, projections) stored in the GitHub repo. Updating data = dragging a new file onto GitHub.com. No re-uploading in the app unless testing new files locally.

---

## Architecture

**Hosting:** GitHub Pages serving static files from the `main` branch root. No build step — the existing vanilla JS/HTML stack requires none.

**Data storage:** A `data/` folder in the repo holds all CSV files at fixed, known names. The app fetches these files by relative URL (`./data/roster.csv`) on every page load.

**State flow:**
1. Page loads → `autoLoadFromRepo()` fetches all data files from `./data/`
2. Each successful fetch is parsed and written into localStorage under the existing keys
3. Each failed fetch leaves localStorage untouched (manual upload data persists)
4. The rest of the app reads from localStorage as it does today — no other changes

Manual uploads remain fully functional and override repo data for the current session. This preserves local development and allows testing new projections before committing.

---

## File Structure

```
OttoneuAI/
├── index.html
├── roster.html
├── fa.html
├── trade.html
├── shared.js
├── test.html
└── data/                          ← new folder
    ├── roster.csv                 ← Ottoneu roster export
    ├── proj_hitting.csv           ← BatX hitting projections (Y0)
    ├── proj_pitching.csv          ← BatX pitching projections (Y0)
    ├── proj_hitting_y1.csv        ← (optional) Y+1 hitting
    ├── proj_pitching_y1.csv       ← (optional) Y+1 pitching
    ├── proj_hitting_y2.csv        ← (optional) Y+2 hitting
    └── proj_pitching_y2.csv       ← (optional) Y+2 pitching
```

Y1/Y2 files are optional — their absence is not an error. If missing, dynasty features are simply unavailable (same behavior as today when those files are not uploaded).

---

## New Shared Utility: `autoLoadFromRepo()`

Added to `shared.js`. Called by every page on load before rendering.

```js
// Maps repo filenames to localStorage keys and parser functions.
// Matches the keys used by CSV_CONFIGS in index.html.
const REPO_FILES = [
  { file: 'roster.csv',          key: 'ottoneu_roster',           parse: parseRosterCSV },
  { file: 'proj_hitting.csv',    key: 'ottoneu_proj_hitting',     parse: parseHittingProjections },
  { file: 'proj_pitching.csv',   key: 'ottoneu_proj_pitching',    parse: parsePitchingProjections },
  { file: 'proj_hitting_y1.csv', key: 'ottoneu_proj_hitting_y1',  parse: parseHittingProjections },
  { file: 'proj_pitching_y1.csv',key: 'ottoneu_proj_pitching_y1', parse: parsePitchingProjections },
  { file: 'proj_hitting_y2.csv', key: 'ottoneu_proj_hitting_y2',  parse: parseHittingProjections },
  { file: 'proj_pitching_y2.csv',key: 'ottoneu_proj_pitching_y2', parse: parsePitchingProjections },
];

async function autoLoadFromRepo() {
  // Only runs when served over HTTP(S) — skips silently on file:// protocol.
  if (window.location.protocol === 'file:') return {};

  const status = {};   // filename → true (loaded) | false (missing/failed)
  const fetches = REPO_FILES.map(async ({ file, key, parse }) => {
    try {
      const res = await fetch('./data/' + file);
      if (!res.ok) { status[file] = false; return; }   // 404 = optional file missing
      const text = await res.text();
      saveData(key, parse(text));             // overwrites localStorage with fresh data
      status[file] = true;
    } catch (_) {
      status[file] = false;  // Network error or parse failure
    }
  });

  await Promise.all(fetches);
  return status;
}
```

**Key properties:**
- Runs only on HTTP/HTTPS (skips on `file://` so local dev is unaffected)
- Optional files (Y1/Y2) silently ignored when absent (404 is not an error)
- Parse failures silently ignored — old localStorage data remains
- All fetches run in parallel; total load time = slowest single file
- Returns a Promise resolving to a `status` map (`filename → boolean`) so callers know what loaded

---

## Data Status Display (index.html)

`index.html` uses the returned status map to render a **Data Status checklist** — a persistent section showing exactly which files are present in the repo and which are not. This replaces silent failure with visible feedback.

**Display format (one row per file):**

| Status | Filename | Label |
|--------|----------|-------|
| ✅ | `roster.csv` | LOADED |
| ✅ | `proj_hitting.csv` | LOADED |
| ⚠️ | `proj_hitting_y1.csv` | NOT DETECTED |

Required files (`roster.csv`, `proj_hitting.csv`, `proj_pitching.csv`) show in red/warning when missing. Optional Y1/Y2 files show as neutral grey when absent — missing them is expected if dynasty mode isn't set up.

The checklist also serves as a **filename reference** — the user can always look here to get the exact names needed when uploading to GitHub.

---

## Per-Page Changes

Each of the four tool pages (`index.html`, `roster.html`, `fa.html`, `trade.html`) gets the same small addition at the top of its initialization script:

1. Show a brief loading message ("Loading league data…")
2. `await autoLoadFromRepo()`
3. Hide loading message
4. Proceed with existing initialization (read from localStorage, render)

No other changes to page logic. The existing localStorage read path is unchanged.

`index.html` additionally shows a "Data loaded from repo" notice when auto-load succeeds, so the user knows they don't need to upload anything manually.

---

## GitHub Setup (One-Time, Manual)

These steps are performed by the user on GitHub.com, not automated:

1. **Make repo public:** Settings → General → Change visibility → Public
2. **Enable GitHub Pages:** Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder: `/ (root)` → Save
3. **Create `data/` folder and upload initial files:** In the repo, navigate to "Add file" → "Upload files", upload all CSVs into a `data/` subfolder, commit to `main`

App is then live at: `https://[github-username].github.io/OttoneuAI/`

---

## Day-to-Day Update Workflow

| Action | Steps |
|--------|-------|
| New roster export | Go to `github.com/[you]/OttoneuAI/data/` → click `roster.csv` → edit/upload → commit |
| New BatX projections | Same, for `proj_hitting.csv` and `proj_pitching.csv` |
| Test projections before committing | Use the existing upload UI in the app — overrides repo data for that session |

GitHub Pages CDN propagates changes in ~1 minute. Next page load picks up new data.

---

## What Is Not Changing

- No build step, bundler, or deployment pipeline — it's a static site
- No backend, database, or authentication
- All existing features work identically
- Local development (`file://`) continues to use the localStorage/upload flow unchanged
- The manual upload UI stays in all pages as a fallback and for local testing
