const test = require('node:test');
const assert = require('node:assert');
const { managerKey, managerName } = require('../lib/eras');

test('Prospects R Us splits at the 2026 offseason; Misiorowski mid-August 2026; others unchanged', () => {
  assert.strictEqual(managerKey('10899', '2025-07-01'), '10899@2024-01-01');
  assert.strictEqual(managerKey('10899', '2025-11-15'), '10899@2025-10-01');   // 2026 offseason cut
  assert.strictEqual(managerKey('10758', '2026-08-01'), '10758@2024-01-01');
  assert.strictEqual(managerKey('10758', '2026-08-21'), '10758@2026-08-15');
  assert.strictEqual(managerKey('10759', '2026-08-21'), '10759');
  const teams = { 10899: { name: 'Prospects R Us' }, 10758: { name: 'Misiorowski Index' }, 10759: { name: 'Juan Nation' } };
  assert.strictEqual(managerName(teams, '10899@2024-01-01'), 'Prospects R Us (2024–25)');
  assert.strictEqual(managerName(teams, '10899@2025-10-01'), 'Prospects R Us (2026)');
  assert.strictEqual(managerName(teams, '10758@2026-08-15'), 'Misiorowski Index (from Aug 2026)');
  assert.strictEqual(managerName(teams, '10759'), 'Juan Nation');
});

const { coversSeason } = require('../lib/eras');
test('coversSeason: only managers who ran the team all season qualify for season-long counts', () => {
  assert.strictEqual(coversSeason('10759', 2026), true);
  assert.strictEqual(coversSeason('10758@2026-08-15', 2026), false);
  assert.strictEqual(coversSeason('10758@2024-01-01', 2026), false);
  assert.strictEqual(coversSeason('10758@2024-01-01', 2025), true);
  assert.strictEqual(coversSeason('10899@2025-10-01', 2026), true);
});
