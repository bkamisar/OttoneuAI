# GitHub Pages Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Host the Ottoneu tool on GitHub Pages with CSV data stored in `data/` and auto-loaded on every page visit, so the user can access the tool from any device and update data by uploading to GitHub.

**Architecture:** `autoLoadFromRepo()` is added to `shared.js` — it fetches each CSV from `./data/`, parses it, and writes to localStorage under the same keys the existing app already reads. Every page wraps its init in an async IIFE that awaits `autoLoadFromRepo()` before rendering. `index.html` additionally renders a Data Status checklist from the returned status map. On `file://` protocol the function returns immediately with an empty object so local dev is unaffected.

**Tech Stack:** Vanilla JS, `fetch()`, `async/await`, GitHub Pages (static hosting, no build step)

---

## File Map

| File | Change |
|------|--------|
| `shared.js` | Add `REPO_FILES` array + `autoLoadFromRepo()` function after the PRORATION section |
| `test.html` | Add `autoLoadFromRepo` structure tests in a new "Repo Auto-Load" section |
| `index.html` | Add CSS for status list; add loading div + `#repoStatusSection` HTML; add `renderDataStatus()` function; convert bottom init to async IIFE |
| `roster.html` | Add loading div to HTML; convert `render()` call at bottom to async IIFE |
| `fa.html` | Add loading div to HTML; convert existing IIFE to async |
| `trade.html` | Add loading div to HTML; convert existing IIFE to async |
| `data/README.md` | New file — exact filenames + instructions for updating data |

---

## Task 1: Add `autoLoadFromRepo()` to shared.js

**Files:**
- Modify: `shared.js` (after line 48, between PRORATION and SECURITY HELPER sections)

- [ ] **Step 1: Add the REPO_FILES array and autoLoadFromRepo() to shared.js**

Insert this block between the closing `}` of `rosProrationFactor()` (line 48) and the `// ── SECURITY HELPER` comment (line 50):

```js
// ── REPO AUTO-LOAD ───────────────────────────────────────────────────────────
// Maps data/ filenames to localStorage keys and parser functions.
// Matches the keys the rest of the app reads from localStorage.
const REPO_FILES = [
  { file: 'roster.csv',           key: 'ottoneu_roster',            parse: parseRosterCSV },
  { file: 'proj_hitting.csv',     key: 'ottoneu_proj_hitting',      parse: parseHittingProjections },
  { file: 'proj_pitching.csv',    key: 'ottoneu_proj_pitching',     parse: parsePitchingProjections },
  { file: 'proj_hitting_y1.csv',  key: 'ottoneu_proj_hitting_y1',   parse: parseHittingProjections },
  { file: 'proj_pitching_y1.csv', key: 'ottoneu_proj_pitching_y1',  parse: parsePitchingProjections },
  { file: 'proj_hitting_y2.csv',  key: 'ottoneu_proj_hitting_y2',   parse: parseHittingProjections },
  { file: 'proj_pitching_y2.csv', key: 'ottoneu_proj_pitching_y2',  parse: parsePitchingProjections },
];

// Fetches all data/ CSVs from the repo, parses them, and writes to localStorage.
// Returns a status map: { 'roster.csv': true, 'proj_hitting.csv': false, ... }
// Returns {} immediately on file:// so local dev is unaffected.
async function autoLoadFromRepo() {
  if (window.location.protocol === 'file:') return {};
  const status = {};
  await Promise.all(REPO_FILES.map(async function({ file, key, parse }) {
    try {
      const res = await fetch('./data/' + file);
      if (!res.ok) { status[file] = false; return; }
      const text = await res.text();
      saveData(key, parse(text));
      status[file] = true;
    } catch (_) {
      status[file] = false;
    }
  }));
  return status;
}
```

- [ ] **Step 2: Verify shared.js loads without errors**

Open `test.html` in a browser (via `file://`). The existing 55 tests should all still pass. A broken import in shared.js would cause all tests to fail at once.

Expected: 55 passed, 0 failed (same as before this change).

---

## Task 2: Add tests to test.html

**Files:**
- Modify: `test.html` (add a new section before the `#summary` div, after the last existing section)

- [ ] **Step 1: Add the "Repo Auto-Load" test section**

Find the last `section(...)` block in test.html (the Proration section). After it, append:

```js
    section('Repo Auto-Load');
    assert(typeof REPO_FILES !== 'undefined', 'REPO_FILES: defined');
    assert(Array.isArray(REPO_FILES), 'REPO_FILES: is an array');
    assert(REPO_FILES.length === 7, 'REPO_FILES: has 7 entries');
    REPO_FILES.forEach(function(entry, i) {
      assert(typeof entry.file  === 'string',   'REPO_FILES[' + i + ']: has file string');
      assert(typeof entry.key   === 'string',   'REPO_FILES[' + i + ']: has key string');
      assert(typeof entry.parse === 'function', 'REPO_FILES[' + i + ']: has parse function');
    });
    assert(typeof autoLoadFromRepo === 'function', 'autoLoadFromRepo: defined as function');
    var p = autoLoadFromRepo();
    assert(p instanceof Promise, 'autoLoadFromRepo: returns a Promise');
    assert(REPO_FILES[0].file === 'roster.csv',          'REPO_FILES[0]: roster.csv');
    assert(REPO_FILES[1].file === 'proj_hitting.csv',    'REPO_FILES[1]: proj_hitting.csv');
    assert(REPO_FILES[2].file === 'proj_pitching.csv',   'REPO_FILES[2]: proj_pitching.csv');
    assert(REPO_FILES[3].file === 'proj_hitting_y1.csv', 'REPO_FILES[3]: proj_hitting_y1.csv');
```

- [ ] **Step 2: Run tests and verify new tests pass**

Open `test.html` in a browser. On `file://`, `autoLoadFromRepo()` returns `{}` immediately (a resolved Promise), so the Promise check works.

Expected: 55 + 12 = 67 passed, 0 failed.

- [ ] **Step 3: Commit**

```bash
git add shared.js test.html
git commit -m "feat: add autoLoadFromRepo() to shared.js with REPO_FILES map"
```

---

## Task 3: Update index.html — async init + Data Status section

**Files:**
- Modify: `index.html`

This task has three parts: CSS, HTML structure, JS. All in one file.

- [ ] **Step 1: Add Data Status CSS to the `<style>` block**

In `index.html`, inside the `<style>` block, add these rules before the closing `</style>` tag:

```css
    .status-list { background:#fff; border-radius:8px; padding:12px 16px; box-shadow:0 1px 4px rgba(0,0,0,.1); display:flex; flex-direction:column; gap:8px; }
    .status-row  { display:flex; align-items:center; gap:12px; font-size:.88rem; }
    .status-fname { font-family:monospace; color:#333; min-width:210px; display:inline-block; }
    .status-badge-ok  { background:#e6f4ea; color:#1e7e34; padding:2px 8px; border-radius:12px; font-size:.75rem; font-weight:600; }
    .status-badge-err { background:#fce8e6; color:#c62828; padding:2px 8px; border-radius:12px; font-size:.75rem; font-weight:600; }
    .status-badge-opt { background:#f5f5f5; color:#999;    padding:2px 8px; border-radius:12px; font-size:.75rem; font-weight:600; }
```

- [ ] **Step 2: Add loading div and status section HTML**

In the `<body>`, insert a loading div directly before `<div class="section-title">My Team</div>` (line 62):

```html
  <div id="repoLoading" style="display:none;color:#666;font-size:.88rem;padding:4px 0 12px">Loading league data from repo…</div>
```

Then insert the status section directly after `<div class="grid" id="csvGrid"></div>` (line 69), before the Current Standings section:

```html
  <div id="repoStatusSection" style="display:none">
    <div class="section-title">Repo Data Status <span style="font-weight:400;color:#888;font-size:.85rem">— files loaded automatically from GitHub</span></div>
    <div id="repoStatusList" class="status-list"></div>
  </div>
```

- [ ] **Step 3: Add renderDataStatus() function to the `<script>` block**

In `index.html`'s `<script>`, add `renderDataStatus` before the `buildGrid` function:

```js
    var STATUS_FILES = [
      { file: 'roster.csv',           label: 'roster.csv',           required: true  },
      { file: 'proj_hitting.csv',     label: 'proj_hitting.csv',     required: true  },
      { file: 'proj_pitching.csv',    label: 'proj_pitching.csv',    required: true  },
      { file: 'proj_hitting_y1.csv',  label: 'proj_hitting_y1.csv',  required: false },
      { file: 'proj_pitching_y1.csv', label: 'proj_pitching_y1.csv', required: false },
      { file: 'proj_hitting_y2.csv',  label: 'proj_hitting_y2.csv',  required: false },
      { file: 'proj_pitching_y2.csv', label: 'proj_pitching_y2.csv', required: false },
    ];

    function renderDataStatus(status) {
      if (!status || Object.keys(status).length === 0) return; // file:// or no data
      var section = document.getElementById('repoStatusSection');
      var list    = document.getElementById('repoStatusList');
      section.style.display = '';
      while (list.firstChild) list.removeChild(list.firstChild);

      STATUS_FILES.forEach(function(f) {
        var loaded = status[f.file];
        var row    = document.createElement('div');
        row.className = 'status-row';

        var icon = document.createElement('span');
        icon.textContent = loaded ? '✅' : (f.required ? '⚠️' : '○');
        icon.style.minWidth = '24px';

        var fname = document.createElement('code');
        fname.className   = 'status-fname';
        fname.textContent = f.file;

        var badge = document.createElement('span');
        badge.className   = loaded ? 'status-badge-ok' : (f.required ? 'status-badge-err' : 'status-badge-opt');
        badge.textContent = loaded ? 'LOADED' : 'NOT DETECTED';

        row.appendChild(icon);
        row.appendChild(fname);
        row.appendChild(badge);
        list.appendChild(row);
      });
    }
```

- [ ] **Step 4: Convert bottom init to async IIFE**

Replace the current last three lines of the `<script>` block:

```js
    buildGrid();
    const savedRoster = loadData('ottoneu_roster');
    if (savedRoster) rebuildTeamDropdown(savedRoster);
```

With:

```js
    (async function() {
      document.getElementById('repoLoading').style.display = '';
      var status = await autoLoadFromRepo();
      document.getElementById('repoLoading').style.display = 'none';
      buildGrid();
      var savedRoster = loadData('ottoneu_roster');
      if (savedRoster) rebuildTeamDropdown(savedRoster);
      renderDataStatus(status);
    })();
```

- [ ] **Step 5: Verify in browser**

Open `index.html` via `file://`. The Data Status section should NOT appear (because `autoLoadFromRepo` returns `{}` on file://, and `renderDataStatus` skips when the status object is empty). All existing functionality (grid, team dropdown, weights) should work identically to before.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat: add async init and Data Status checklist to index.html"
```

---

## Task 4: Update roster.html — async init

**Files:**
- Modify: `roster.html`

- [ ] **Step 1: Add loading div to HTML**

In `roster.html`, find `<div id="error"></div>` and insert the loading div directly before it:

```html
  <div id="loading" style="display:none;color:#666;font-size:.88rem;padding:8px 0">Loading league data…</div>
```

- [ ] **Step 2: Convert bottom init to async IIFE**

Find the last line of the `<script>` block (currently just `render();` at line 272). Replace it with:

```js
    (async function() {
      document.getElementById('loading').style.display = '';
      await autoLoadFromRepo();
      document.getElementById('loading').style.display = 'none';
      render();
    })();
```

- [ ] **Step 3: Verify in browser**

Open `roster.html` via `file://` with data already in localStorage. Page should render identically — the loading div appears and disappears instantly (file:// returns immediately), then `render()` runs as before.

- [ ] **Step 4: Commit**

```bash
git add roster.html
git commit -m "feat: async init in roster.html — awaits autoLoadFromRepo before render"
```

---

## Task 5: Update fa.html — async init

**Files:**
- Modify: `fa.html`

- [ ] **Step 1: Add loading div to HTML**

In `fa.html`, find `<div id="error"></div>` and insert before it:

```html
  <div id="loading" style="display:none;color:#666;font-size:.88rem;padding:8px 0">Loading league data…</div>
```

- [ ] **Step 2: Convert IIFE to async**

Find the opening of the IIFE (line 148):

```js
  (function () {
```

Replace with:

```js
  (async function () {
    document.getElementById('loading').style.display = '';
    await autoLoadFromRepo();
    document.getElementById('loading').style.display = 'none';
```

The rest of the IIFE body is unchanged — the `var roster = loadData(...)` calls immediately follow and now read the freshly hydrated localStorage.

- [ ] **Step 3: Verify in browser**

Open `fa.html` via `file://` with data in localStorage. Page renders as before, no visible change in behavior.

- [ ] **Step 4: Commit**

```bash
git add fa.html
git commit -m "feat: async init in fa.html — awaits autoLoadFromRepo before render"
```

---

## Task 6: Update trade.html — async init

**Files:**
- Modify: `trade.html`

- [ ] **Step 1: Add loading div to HTML**

In `trade.html`, find `<div id="error"></div>` and insert before it:

```html
  <div id="loading" style="display:none;color:#666;font-size:.88rem;padding:8px 0">Loading league data…</div>
```

- [ ] **Step 2: Convert IIFE to async**

Find the opening of the IIFE (line 126 of trade.html):

```js
  (function () {
```

Replace with:

```js
  (async function () {
    document.getElementById('loading').style.display = '';
    await autoLoadFromRepo();
    document.getElementById('loading').style.display = 'none';
```

The rest of the IIFE body is unchanged.

- [ ] **Step 3: Verify in browser**

Open `trade.html` via `file://` with data in localStorage. Page renders as before.

- [ ] **Step 4: Commit**

```bash
git add trade.html
git commit -m "feat: async init in trade.html — awaits autoLoadFromRepo before render"
```

---

## Task 7: Create data/ folder with README

**Files:**
- Create: `data/README.md`

- [ ] **Step 1: Create the data/ folder and README**

Create `data/README.md` with the following content:

```markdown
# data/

CSV files in this folder are fetched automatically by the app on every page load.
Filenames must match exactly (case-sensitive).

## Required files

| Filename | Contents |
|----------|----------|
| `roster.csv` | Ottoneu roster export (all 12 teams) |
| `proj_hitting.csv` | BatX hitting projections (current year) |
| `proj_pitching.csv` | BatX pitching projections (current year) |

## Optional files (dynasty mode)

| Filename | Contents |
|----------|----------|
| `proj_hitting_y1.csv` | BatX hitting projections (Y+1) |
| `proj_pitching_y1.csv` | BatX pitching projections (Y+1) |
| `proj_hitting_y2.csv` | BatX hitting projections (Y+2) |
| `proj_pitching_y2.csv` | BatX pitching projections (Y+2) |

## Updating data

1. Go to `github.com/[your-username]/OttoneuAI/tree/main/data`
2. Click the file you want to replace
3. Click the pencil icon → "Upload file" (or drag the new file)
4. Commit to `main`

GitHub Pages propagates changes in ~1 minute. The next page load picks up the new data automatically.

## Testing locally

The app skips auto-loading when run via `file://` protocol, so local testing
always uses whatever is in localStorage. Use the upload UI on the Data Hub to
load files locally without committing them.
```

- [ ] **Step 2: Commit**

```bash
git add data/README.md
git commit -m "feat: add data/ folder with filename reference and update instructions"
```

---

## Task 8: Manual end-to-end verification (GitHub Pages)

These steps must be done by the user after pushing to GitHub and enabling Pages. They are not automated.

- [ ] **Step 1: Push all commits to GitHub**

```bash
git push origin main
```

- [ ] **Step 2: Enable GitHub Pages**

On GitHub.com:
- Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder: `/ (root)` → Save

- [ ] **Step 3: Upload initial data files**

Navigate to `github.com/[you]/OttoneuAI/data/` → "Add file" → "Upload files" → upload all CSVs with the exact names listed in `data/README.md` → Commit to `main`.

- [ ] **Step 4: Wait ~1 minute, then open the live URL**

`https://[github-username].github.io/OttoneuAI/`

- [ ] **Step 5: Verify Data Status checklist on index.html**

Required files (roster, proj_hitting, proj_pitching) should show **✅ LOADED**.  
Y1/Y2 files show **○ NOT DETECTED** if not uploaded (expected).

- [ ] **Step 6: Verify other pages load data**

Open roster.html, trade.html, fa.html. Each should show "Loading league data…" briefly then render with the repo data, without requiring any manual upload.
