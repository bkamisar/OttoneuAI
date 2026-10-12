// audit/lib/engine.js
// Loads the suite's browser scripts (shared.js, hotboard.js) into a Node vm
// context so the audit uses the exact same valuation code as the pages.
// Shims: localStorage (in-memory), window/document stubs, quiet console, and a
// Date whose "now" is settable so rosProrationFactor() can replay any day.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..', '..');
const SCRIPTS = ['shared.js', 'hotboard.js'];

function loadEngine() {
  let nowMs = Date.now();
  const RealDate = Date;
  class FixedDate extends RealDate {
    constructor(...a) { if (a.length === 0) super(nowMs); else super(...a); }
    static now() { return nowMs; }
  }
  const store = new Map();
  const ctx = {
    Date: FixedDate, Math, JSON, Set, Map, Object, Array, Number, String, parseFloat, parseInt, isNaN,
    console: { log() {}, warn() {}, error: console.error },
    localStorage: {
      getItem: k => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: k => store.delete(k),
    },
    window: { location: { hostname: '', pathname: '', protocol: 'file:' } },
    document: { getElementById: () => null },
    fetch: () => Promise.reject(new Error('fetch disabled in audit engine')),
  };
  vm.createContext(ctx);
  for (const f of SCRIPTS) {
    vm.runInContext(fs.readFileSync(path.join(ROOT, f), 'utf8'), ctx, { filename: f });
  }
  const get = name => vm.runInContext(name, ctx);
  return {
    setDate(iso) { nowMs = new RealDate(iso + 'T12:00:00').getTime(); },
    get,
    call(name, ...args) { return get(name)(...args); },
    localStorage: ctx.localStorage,
  };
}

module.exports = { loadEngine };
