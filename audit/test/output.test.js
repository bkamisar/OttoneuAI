// Checks on the committed pipeline output (data/audit.json). Re-run node audit/run.js first.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs'); const path = require('path');
const file = path.join(__dirname, '..', '..', 'data', 'audit.json');
const a = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : null;

test('v2: Yordan 2026 cut is a +$1 reset; Donovan trade gives Bureau ~0 points', { skip: !a && 'no audit.json' }, () => {
  const y = a.moves.find(m => m.kind === 'reset' && m.season === 2026 && m.out.some(p => p.player === 'Yordan Alvarez'));
  assert.ok(y, 'reset exists'); assert.strictEqual(Math.round(y.result), 1);
  const bur = a.moves.find(m => m.kind === 'trade' && m.date === '2026-05-13' && m.teamId === '10818');
  assert.ok(bur.ptsContributed !== null && Math.abs(bur.ptsContributed) <= 2, `Bureau pts ${bur.ptsContributed}`);
  assert.ok(a.winters && a.winters['2026'] && a.winters['2026']['10925'], 'winters present');
  assert.ok(a.moves.every(m => m.phase === 'offseason' || m.phase === 'in-season'));
});

test('every move has a numeric result and no NaN anywhere', { skip: !a && 'no audit.json' }, () => {
  for (const m of a.moves) {
    assert.ok(Number.isFinite(m.result), m.id + ' result');
    if (m.process != null) assert.ok(Number.isFinite(m.process), m.id + ' process');
  }
});

test('v2: luck is not reported (process is projection-based, results are lineup-only)', { skip: !a && 'no audit.json' }, () => {
  assert.ok(a.moves.every(m => m.luck === null), 'luck must be null in v2');
});

test('grade = production for trades/cuts/adds, value-minus-price for auction buys, 0 for resets', { skip: !a && 'no audit.json' }, () => {
  for (const m of a.moves) {
    if (m.production == null) continue;
    const want = m.kind === 'auction' ? m.result : m.kind === 'reset' ? 0 : m.production;
    assert.ok(Math.abs(m.grade - want) < 1e-9, `${m.id} ${m.kind}`);
  }
  // Pressmerlyn's January blockbuster: +51 production, negative only after salary -> graded a win now.
  const mtp = a.moves.find(m => m.kind === 'trade' && m.date === '2026-01-10' && m.teamId === '10761');
  assert.ok(mtp.grade > 40 && mtp.result < 0);
});
