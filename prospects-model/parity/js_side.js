// Runs shared.js calcPlayerSGP on injected inputs and prints JSON.
// Inputs are injected so the comparison isolates the FORMULA: the JS tool's
// own denominators and replacement levels depend on its seasonal state (in
// late September they collapse to 1.0 and 2.2 PA), which would make an
// end-to-end comparison fail for reasons unrelated to the math.
const fs = require('fs'), vm = require('vm'), path = require('path');
const sandbox = {
  console: { log() {}, warn() {}, error() {} },
  window: { location: { hostname: '', pathname: '' } },
  localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', '..', 'shared.js'), 'utf8'), sandbox);

const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = cases.map(c =>
  sandbox.calcPlayerSGP({ type: c.type }, c.stats, c.repl, c.den, c.avgPA, c.avgIP));
process.stdout.write(JSON.stringify(out));
