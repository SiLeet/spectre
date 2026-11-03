// probe_timescale.js — LOG-ONLY probe for Unity time / frame-rate controls (T63).
//
// Reads (never writes): Time.timeScale, Time.fixedDeltaTime,
// Application.targetFrameRate, QualitySettings.vSyncCount, resolved through
// IL2CPP's own icall resolver (il2cpp_resolve_icall). Also logs every call of
// Time.set_timeScale (who changes it, how often) without touching the value.
//
// Run:  python hack/frida/attach.py attach hack/frida/probe_timescale.js
// Tolerant to Frida 16 vs 17 module APIs. If the game's native code runs
// under ARM translation (libhoudini / libndk_translation on x86 BlueStacks),
// an x86 frida-server cannot see libil2cpp.so — the probe says so.
'use strict';

const IL2CPP = 'libil2cpp.so';
const TRANSLATORS = ['libhoudini.so', 'libndk_translation.so'];
const READS = [
  ['Time.timeScale', 'float', ['UnityEngine.Time::get_timeScale()', 'UnityEngine.Time::get_timeScale']],
  ['Time.fixedDeltaTime', 'float', ['UnityEngine.Time::get_fixedDeltaTime()', 'UnityEngine.Time::get_fixedDeltaTime']],
  ['Application.targetFrameRate', 'int', ['UnityEngine.Application::get_targetFrameRate()', 'UnityEngine.Application::get_targetFrameRate']],
  ['QualitySettings.vSyncCount', 'int', ['UnityEngine.QualitySettings::get_vSyncCount()', 'UnityEngine.QualitySettings::get_vSyncCount']],
];
const SETTER = ['UnityEngine.Time::set_timeScale(System.Single)', 'UnityEngine.Time::set_timeScale'];

function log(msg) { console.log('[probe] ' + msg); }

function findModule(name) {
  try { return Process.findModuleByName(name); } catch (e) { return null; }
}

function findExport(lib, sym) {
  const m = findModule(lib);
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
    if (!r.isNull()) return { name: n, ptr: r };
  }
  return null;
}

function probe() {
  log('arch=' + Process.arch + ' platform=' + Process.platform + ' pid=' + Process.id);
  for (const t of TRANSLATORS) {
    if (findModule(t) !== null) log('ARM translation layer loaded: ' + t + ' (il2cpp may be invisible to this frida-server)');
  }
  const il2cpp = findModule(IL2CPP);
  log(IL2CPP + ': ' + (il2cpp ? il2cpp.base + ' size=' + il2cpp.size : 'NOT FOUND'));
  if (il2cpp === null) return;
  for (const [label, ret, names] of READS) {
    const hit = resolveIcall(names);
    if (hit === null) { log(label + ': icall not resolved'); continue; }
    let value = '?';
    try { value = new NativeFunction(hit.ptr, ret, [])(); } catch (e) { value = 'call failed: ' + e; }
    log(label + ' = ' + value + '  (' + hit.name + ' @ ' + hit.ptr + ')');
  }
  const setter = resolveIcall(SETTER);
  if (setter === null) { log('set_timeScale: icall not resolved'); return; }
  log('set_timeScale @ ' + setter.ptr + ' — logging calls (value untouched)');
  let calls = 0;
  Interceptor.attach(setter.ptr, {
    onEnter() {
      calls += 1;
      if (calls <= 20 || calls % 100 === 0) log('set_timeScale called (#' + calls + ')');
    },
  });
}

// libil2cpp.so may load after attach: poll up to 60 s
let waited = 0;
const timer = setInterval(() => {
  if (findModule(IL2CPP) !== null || waited >= 60000) {
    clearInterval(timer);
    probe();
  }
  waited += 500;
}, 500);
