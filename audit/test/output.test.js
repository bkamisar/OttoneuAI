// Checks on the committed pipeline output (data/audit.json). Re-run node audit/run.js first.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs'); const path = require('path');
const file = path.join(__dirname, '..', '..', 'data', 'audit.json');
const a = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : null;

test('offseason cuts and auction buys get a standings impact too', { skip: !a && 'no audit.json' }, () => {
  const yordan = a.moves.find(m => m.kind === 'cut' && m.date === '2026-01-31' && m.out.some(p => p.player === 'Yordan Alvarez'));
  assert.ok(yordan && yordan.standings, 'Jan 2026 Yordan cut has standings');
  assert.ok(a.moves.filter(m => m.kind === 'auction' && m.standings).length > 100, 'auction buys have standings');
});

test('every move has a numeric result and no NaN anywhere', { skip: !a && 'no audit.json' }, () => {
  for (const m of a.moves) {
    assert.ok(Number.isFinite(m.result), m.id + ' result');
    if (m.process != null) assert.ok(Number.isFinite(m.process), m.id + ' process');
  }
});
