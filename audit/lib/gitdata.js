// audit/lib/gitdata.js
// Read dated snapshots of data/*.csv out of git history (Apps Script commits daily).
const { execFileSync } = require('child_process');
const path = require('path');
const ROOT = path.join(__dirname, '..', '..');
const git = args => execFileSync('git', ['-C', ROOT, ...args], { encoding: 'utf8', maxBuffer: 1 << 28 });

function fileHistory(relPath) {
  const out = git(['log', '--reverse', '--format=%H %ad', '--date=short', '--', relPath]).trim();
  const byDate = new Map();
  for (const line of out.split('\n').filter(Boolean)) {
    const [sha, date] = line.split(' ');
    byDate.set(date, sha);        // later commit the same day wins
  }
  return [...byDate.entries()].map(([date, sha]) => ({ sha, date }));
}

function fileAt(sha, relPath) { return git(['show', `${sha}:${relPath}`]); }

function latestOnOrBefore(history, date) {
  let best = null;
  for (const h of history) { if (h.date <= date) best = h; else break; }
  return best;
}

module.exports = { fileHistory, fileAt, latestOnOrBefore };
