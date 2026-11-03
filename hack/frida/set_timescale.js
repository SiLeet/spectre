// set_timescale.js — set Unity Time.timeScale in the running game (T63, risk L3).
//
// Nothing happens without an explicit value:
//   python hack/frida/attach.py attach hack/frida/set_timescale.js --params '{"scale": 1.5}'
//   optional "repeat_ms": 1000  -> re-apply when the game resets it (battle start, pause)
// Interactive (frida REPL): rpc.exports.get() / rpc.exports.set(2.0)
// The value lives only in the process (gone after an app restart). Measure
// the effect against the wall-time baseline (.spectre/metrics, T61) before
// using it anywhere else. Range is clamped to (0, 4].
'use strict';

const IL2CPP = 'libil2cpp.so';
const GETTER = ['UnityEngine.Time::get_timeScale()', 'UnityEngine.Time::get_timeScale'];
const SETTER = ['UnityEngine.Time::set_timeScale(System.Single)', 'UnityEngine.Time::set_timeScale'];
const MAX_SCALE = 4.0;

function log(msg) { console.log('[timescale] ' + msg); }

function findExport(lib, sym) {
  let m = null;
  try { m = Process.findModuleByName(lib); } catch (e) { m = null; }
  if (m !== null && typeof m.findExportByName === 'function') {       // Frida 17 style
    try { const p = m.findExportByName(sym); if (p) return p; } catch (e) { /* fall through */ }
  }
  if (typeof Module.findExportByName === 'function') {               // Frida <= 16
    try { return Module.findExportByName(lib, sym); } catch (e) { /* none */ }
  }
  return null;
}

function resolveIcall(names) {
  const p = findExport(IL2CPP, 'il2cpp_resolve_icall');
  if (p === null) return null;
  const resolve = new NativeFunction(p, 'pointer', ['pointer']);
  for (const n of names) {
    const r = resolve(Memory.allocUtf8String(n));
    if (!r.isNull()) return r;
  }
  return null;
}

let getFn = null;
let setFn = null;

function ready() {
  if (getFn === null || setFn === null) {
    const g = resolveIcall(GETTER);
    const s = resolveIcall(SETTER);
    if (g === null || s === null) {
      log('Time.get/set_timeScale icall not resolved (il2cpp not loaded or under ARM translation?)');
      return false;
    }
    getFn = new NativeFunction(g, 'float', []);
    setFn = new NativeFunction(s, 'void', ['float']);
  }
  return true;
}

function get() { return ready() ? getFn() : null; }

function set(value) {
  const v = Number(value);
  if (!(v > 0 && v <= MAX_SCALE)) { log('refused: scale must be in (0, ' + MAX_SCALE + '], got ' + value); return null; }
  if (!ready()) return null;
  const before = getFn();
  setFn(v);
  const after = getFn();
  log('timeScale ' + before + ' -> ' + after);
  return after;
}

rpc.exports = {
  init(stage, parameters) {
    const p = parameters || {};
    if (p.scale === undefined) { log('no "scale" parameter - nothing set (use --params \'{"scale": 1.5}\')'); return; }
    set(p.scale);
    const every = Number(p.repeat_ms || 0);
    if (every > 0) {
      setInterval(() => {
        const cur = get();
        if (cur !== null && Math.abs(cur - p.scale) > 1e-3) { log('game reset it to ' + cur + ', re-applying'); set(p.scale); }
      }, Math.max(every, 100));
    }
  },
  get,
  set,
};
