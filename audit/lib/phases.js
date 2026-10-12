// audit/lib/phases.js
// Checkpointed phases: each result is saved with a hash of its inputs, so a
// killed run resumes and a changed input (e.g. a fresh transactions.csv) reruns.
const fs = require('fs'); const path = require('path');

async function runPhases(phases, { cacheDir, force = null }) {
  fs.mkdirSync(cacheDir, { recursive: true });
  const results = {}; let forcing = force === true;
  for (const ph of phases) {
    if (force === ph.name) forcing = true;
    const file = path.join(cacheDir, ph.name + '.json');
    const hash = ph.inputsHash();
    if (!forcing && fs.existsSync(file)) {
      const saved = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (saved.inputsHash === hash) { results[ph.name] = saved.value; console.log(`[skip] ${ph.name}`); continue; }
    }
    console.log(`[run ] ${ph.name}`);
    const value = await ph.run(results);
    fs.writeFileSync(file, JSON.stringify({ inputsHash: hash, value }));
    results[ph.name] = value;
    forcing = true;   // a phase actually ran, so every later phase reruns too (skips `continue` above)
  }
  return results;
}

module.exports = { runPhases };
