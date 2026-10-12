const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs'); const os = require('os'); const path = require('path');
const { runPhases } = require('../lib/phases');

test('skips cached phases, reruns on input change and on --force=<name>', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-'));
  let runs = []; let input = 'v1';
  const phases = ['a', 'b', 'c'].map(name => ({ name, inputsHash: () => input, run: async () => { runs.push(name); return name; } }));
  await runPhases(phases, { cacheDir: dir }); assert.deepStrictEqual(runs, ['a', 'b', 'c']);
  runs = []; await runPhases(phases, { cacheDir: dir }); assert.deepStrictEqual(runs, []);
  runs = []; await runPhases(phases, { cacheDir: dir, force: 'b' }); assert.deepStrictEqual(runs, ['b', 'c']);
  runs = []; input = 'v2'; await runPhases(phases, { cacheDir: dir }); assert.deepStrictEqual(runs, ['a', 'b', 'c']);
});
