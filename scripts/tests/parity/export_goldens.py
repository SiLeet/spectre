#!/usr/bin/env python3
"""E0b (T115, rust-port-plan §E0b/§4): export the Python goldens.

Runs the existing suite unchanged (in-process, cwd = the checkout that holds
.spectre) with recorders installed after discovery and writes:

  goldens/flows/<test_module>.jsonl   per test: one record per FakeDevice (+ one for I/O outside
                                      any device): ordered event stream (§4.1), overrides, stdout
  goldens/calls/<bot_module>.jsonl    outermost pure calls on frames / OCR lines / tuples, deduplicated
  goldens/tests.json                  per test id: outcome + record counts (ledger seed), run summary
  goldens/synthetic.json              frames built by the tests (stored in $SPECTRE_PARITY_DIR/synthetic)

Every file starts with the header {v, py_tree, git_head, python, pillow,
windows_build, ocr_ps1_sha}. py_tree pins the Python behaviour: sha16 over
`git ls-tree -r HEAD -- scripts templates` without scripts/tests/parity/ (the
tooling itself). A dirty scripts/ or templates/ refuses the export.

Event schema (one dict per event, key "ev" = type):
  shot {name, frame}   tap {x, y, mode, wait}   seq {steps: [[x, y, w], ...]}
  key {code, w}        hold {x, y, ms, wait}    swipe {args, kwargs}
  sleep {s}            now {src, val}           ocr {fn, name, box?, out}
  adb {argv, rc}       run {argv, rc}           ret {fn, argv, rc, raise?}
  io {fn, args, kwargs, out}    other bot I/O a test replaced (power, idle_seconds, ...)
  stub {fn, args, kwargs, out}  a bot function a test replaced (sub-flow stubbed out)
Events raised by the callee carry "raise": <exception type>. Frames are sha16
keys (freeze_corpus.frame_key): corpus frames resolve via parity/frames.json,
test-built frames via goldens/synthetic.json.

How events are caught: FakeDevice methods (class level, every subclass), and a
hook on unittest.mock patches: whatever a test patches onto a bot module, onto
FakeDevice or onto time.sleep/monotonic/time/perf_counter is wrapped in a
transparent recording proxy (assert_called... etc. still reach the mock).

  export: python scripts/tests/parity/export_goldens.py export --repo C:/Users/Sigi/spectre --out DIR
  check:  python scripts/tests/parity/export_goldens.py check  --repo C:/Users/Sigi/spectre
          (two exports into temp dirs, compare; only an identical, green pair replaces parity/goldens)
  py-tree: python scripts/tests/parity/export_goldens.py py-tree --repo C:/Users/Sigi/spectre
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freeze_corpus import OUT, OWN_REPO, PARITY_DIR, frame_key, guard_spectre  # noqa: E402

GOLDENS = OUT / 'goldens'
# lum(colour) and avg(img, xy) left out: primitives called at top level in scan loops (avg alone
# 268k distinct records / 58 MB); E2's corpus-wide differential run covers them (plan §E2)
CALL_NAME = re.compile(r'^(classify\w*|is_\w+|find_\w+|read_\w+|parse_\w+)$')
PARITY_PREFIX = 'scripts/tests/parity/'
# E1 infra (rust-port-plan §E1): the test's direct calls into these are recorded with their I/O
INFRA = {'afk_claim_vision': ('adb', '_env_tap_mode', 'parse_getevent', 'sendevent_cmds', 'sendevent_device',
                              '_tap_cmd', '_press', 'tap', 'tap_retry', 'tap_result', '_run_seq', 'tap_seq',
                              'key_seq', 'back', 'tap_hold', 'swipe', '_raw_to_image', 'shot'),
         '_bot_lock': ('acquire', 'release', 'describe')}
TAP_LIKE = {'tap', 'seq_step', 'key', 'hold', 'swipe'}
OCR_NAMES = {'ocr_lines', 'ocr_boxes', 'ocr_region', 'ocr_text', 'ocr_png', 'ocr_scaled', '_ocr_crop'}
CLOCK_NAMES = {'monotonic', 'time', 'perf_counter'}
# shortcut: no virtual clock yet (§E0b) -> wall-clock stamps in stdout are masked so two
# exports compare; replace with the virtual clock + `now` events in E0b-2
CLOCK = [(re.compile(r'\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?'), '<DATETIME>'),
         (re.compile(r'\b\d{4}-\d{2}-\d{2}\b'), '<DATE>'),
         (re.compile(r'\b\d{2}:\d{2}:\d{2}\b'), '<TIME>'),
         # battle metrics measured with the real clock: "wall=0.1s", "wall mean 0.1s (min 0.1s, max 0.1s)"
         (re.compile(r'\b(wall=|wall mean |min |max )\d+(\.\d+)?s\b'), r'\1<DUR>s')]


def mask_clock(text: str) -> str:
    for pat, sub in CLOCK:
        text = pat.sub(sub, text)
    return mask_tmp(text)


_TMP_ROOT = tempfile.gettempdir()
# tempfile.mkdtemp names (tmpab12cd, parity-shots-xyz) differ per run: one placeholder for all
TMP_PAT = re.compile('(' + '|'.join(re.escape(v) for v in sorted({_TMP_ROOT, _TMP_ROOT.replace(os.sep, '/')}))
                     + r''')[\\/][^\\/\s'"]+''', re.IGNORECASE)


def mask_tmp(text: str) -> str:
    return TMP_PAT.sub('<TMP>', text)


BLOB_MIN = 4096


# ---------------------------------------------------------------- header / pinning

def _git(repo: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True,
                          timeout=60, check=True).stdout


def py_tree(repo: Path) -> str:
    lines = [ln for ln in _git(repo, 'ls-tree', '-r', 'HEAD', '--', 'scripts', 'templates').splitlines()
             if not ln.split('\t', 1)[-1].startswith(PARITY_PREFIX)]
    return hashlib.sha256('\n'.join(lines).encode()).hexdigest()[:16]


def dirty(repo: Path) -> list[str]:
    out = _git(repo, 'status', '--porcelain', '--', 'scripts', 'templates').splitlines()
    return [ln for ln in out if not ln[3:].startswith(PARITY_PREFIX)]


def header(repo: Path) -> dict:
    import PIL
    ps1 = repo / 'templates' / 'ocr.ps1'
    return {'v': 1, 'py_tree': py_tree(repo), 'git_head': _git(repo, 'rev-parse', 'HEAD').strip(),
            'python': platform.python_version(), 'pillow': PIL.__version__,
            'windows_build': platform.version(),
            'ocr_ps1_sha': hashlib.sha256(ps1.read_bytes()).hexdigest()[:16] if ps1.is_file() else None}


# ---------------------------------------------------------------- frame keys

class Frames:
    """sha16 per image object; test-built images are stored once under synthetic/."""

    def __init__(self, corpus: set[str], rgb_alias: dict[str, str] | None = None):
        self.corpus = corpus
        self.rgb_alias = rgb_alias or {}        # key of convert('RGB') -> corpus key (not stored twice)
        self.memo: dict[int, tuple[object, str]] = {}   # id -> (img ref keeps id alive, key)
        self.synthetic: dict[str, dict] = {}
        self.dir = PARITY_DIR / 'synthetic'
        self.dir.mkdir(parents=True, exist_ok=True)

    def forget(self, img) -> None:
        self.memo.pop(id(img), None)

    def key(self, img) -> str:
        hit = self.memo.get(id(img))
        if hit is not None and hit[0] is img:
            return hit[1]
        k = frame_key(img)
        self.memo[id(img)] = (img, k)
        if k in self.rgb_alias and k not in self.synthetic:
            self.synthetic[k] = {'w': img.size[0], 'h': img.size[1], 'mode': img.mode,
                                 'alias_of': self.rgb_alias[k], 'op': "convert('RGB')"}
        if k not in self.corpus and k not in self.synthetic:
            self.synthetic[k] = {'w': img.size[0], 'h': img.size[1], 'mode': img.mode}
            dst = self.dir / f'{k}.png'
            if not dst.exists():
                tmp = dst.with_suffix(f'.{os.getpid()}.tmp')
                try:
                    img.save(tmp, 'PNG')
                    os.replace(tmp, dst)
                    os.chmod(dst, stat.S_IREAD)
                except (OSError, ValueError, KeyError) as exc:   # mode 'F' etc.; or a parallel export won
                    tmp.unlink(missing_ok=True)
                    if not dst.exists():
                        self.synthetic[k]['unsaved'] = type(exc).__name__
        return k


# ---------------------------------------------------------------- recording proxy

class Proxy:
    """Transparent stand-in for a patched callable: records, then defers to it.

    Attribute reads/writes go to the wrapped object, so tests can keep using
    m.assert_called_once_with(...), m.side_effect = ..., m.return_value etc."""

    def __init__(self, inner, on_call):
        object.__setattr__(self, '_parity', (inner, on_call))

    def __call__(self, *a, **k):
        inner, on_call = object.__getattribute__(self, '_parity')
        return on_call(inner, a, k)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_parity')[0], name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, '_parity')[0], name, value)

    def __repr__(self):
        return f'<parity proxy {object.__getattribute__(self, "_parity")[0]!r}>'


class _Tee(io.TextIOBase):
    """Writes through to the current sys.stdout (often a test's mock) and keeps a copy."""

    def __init__(self, inner):
        self.inner = inner
        self.captured = io.StringIO()

    def write(self, text):
        self.captured.write(text)
        return self.inner.write(text)

    def flush(self):
        flush = getattr(self.inner, 'flush', None)
        if flush:
            flush()


class _Pseudo:
    """Event sink for I/O that happens while no FakeDevice exists (dev: null record)."""


# ---------------------------------------------------------------- recorder

class Recorder:
    def __init__(self, repo: Path, frames: Frames):
        self.repo = repo
        self.scripts = (repo / 'scripts').resolve()
        self.frames = frames
        self.test_id = '?'
        self.devices: list = []                 # FakeDevices of the running test
        self.pseudo = None
        self.overrides: list = []
        self.flows: dict[str, list] = {}        # test module -> records
        self.calls: dict[str, dict] = {}        # bot module -> {input json: record}
        self.conflicts: list[dict] = []
        self.counts = {'calls_recorded': 0, 'calls_impure': 0, 'calls_mutating': 0,
                       'calls_opaque': 0, 'events_opaque': 0, 'patches_wrapped': 0}
        self.per_test: dict[str, dict] = {}
        self.depth = 0
        self.dev_events = 0                     # bumps on every event (impurity probe)
        self.Image = None
        self.fv = None
        self.dev_makers: dict = {}
        self.blobs: dict[str, int] = {}
        self.infra: dict[str, dict] = {}         # module -> {record json: record}
        self.infra_depth = 0

    # -- module classification
    def is_bot(self, mod) -> bool:
        f = getattr(mod, '__file__', None)
        return isinstance(mod, types.ModuleType) and bool(f) and Path(f).resolve().parent == self.scripts

    def bot_modules(self) -> list:
        """sys.modules + modules held by any loaded module (spec_from_file_location loads)."""
        seen, out = set(), []
        for m in list(sys.modules.values()):
            for cand in [m, *(x for x in list(vars(m).values()) if isinstance(x, types.ModuleType))]:
                if id(cand) not in seen and self.is_bot(cand):
                    seen.add(id(cand))
                    out.append(cand)
        return out

    # -- encoding
    def enc(self, x, opaque: list | None = None):
        opaque = [] if opaque is None else opaque
        if self.Image is not None and isinstance(x, self.Image.Image):
            return {'img': self.frames.key(x)}
        if isinstance(x, str):
            return mask_tmp(x)
        if x is None or isinstance(x, (bool, int)):
            return x
        if isinstance(x, float):
            return x if x == x and x not in (float('inf'), float('-inf')) else {'float': repr(x)}
        if isinstance(x, (list, tuple)):
            return [self.enc(i, opaque) for i in x]
        if isinstance(x, dict) and all(isinstance(k, str) for k in x):
            return {k: self.enc(v, opaque) for k, v in x.items()}
        if isinstance(x, (set, frozenset)):
            return {'set': sorted((self.enc(i, opaque) for i in x), key=repr)}
        if isinstance(x, subprocess.CompletedProcess):
            return {'rc': x.returncode, 'stdout': self.enc(x.stdout, opaque),
                    'stderr': self.enc(x.stderr, opaque)}
        if isinstance(x, (bytes, bytearray)):
            if len(x) < BLOB_MIN:
                return {'bytes': bytes(x).hex()}
            return {'blob': self.blob(bytes(x)), 'len': len(x)}
        if isinstance(x, Path):
            return {'path': mask_tmp(x.as_posix())}
        opaque.append(type(x).__name__)
        return {'repr': type(x).__name__}

    def blob(self, data: bytes) -> str:
        """Large byte payloads (fake screencaps) -> $SPECTRE_PARITY_DIR/blobs/<sha16>.bin."""
        k = hashlib.sha256(data).hexdigest()[:16]
        if k not in self.blobs:
            self.blobs[k] = len(data)
            d = PARITY_DIR / 'blobs'
            d.mkdir(parents=True, exist_ok=True)
            dst = d / f'{k}.bin'
            if not dst.exists():
                tmp = dst.with_suffix(f'.{os.getpid()}.tmp')
                tmp.write_bytes(data)
                try:
                    os.replace(tmp, dst)
                except OSError:               # a parallel export stored it first
                    tmp.unlink(missing_ok=True)
        return k

    def event(self, dev, ev: dict) -> dict:
        self.dev_events += 1
        dev.__dict__.setdefault('_parity_events', []).append(ev)
        return ev

    def current(self):
        if self.devices:
            return self.devices[-1]
        if self.pseudo is None:
            self.pseudo = _Pseudo()
        return self.pseudo

    # -- I/O through a patched callable
    def io_event(self, mod_name: str, name: str, a: tuple, k: dict) -> dict:
        def arg(i, key, default=None):
            return k.get(key, a[i] if len(a) > i else default)
        if name in ('shot',):
            return {'ev': 'shot', 'name': self.enc(arg(0, 'name'))}
        if name == 'tap':
            xy = arg(0, 'xy', (None, None))
            # mode = the mode used (only known when the patched tap returns it), mode_arg = passed
            return {'ev': 'tap', 'x': self.enc(xy[0]), 'y': self.enc(xy[1]), 'mode': None,
                    'mode_arg': self.enc(arg(2, 'mode')), 'wait': self.enc(arg(1, 'wait', 1.0))}
        if name in ('tap_seq',):
            return {'ev': 'seq', 'steps': self.enc(arg(0, 'steps', [])),
                    'tolerate': self.enc(arg(1, 'tolerate', True)), 'dry': self.enc(arg(2, 'dry', False))}
        if name == 'key':
            return {'ev': 'key', 'code': self.enc(arg(0, 'code')), 'w': self.enc(arg(1, 'wait'))}
        if name == 'tap_hold':
            xy = arg(0, 'xy', (None, None))
            return {'ev': 'hold', 'x': self.enc(xy[0]), 'y': self.enc(xy[1]),
                    'ms': self.enc(arg(1, 'ms', 120)), 'wait': self.enc(arg(2, 'wait', 1.0))}
        if name == 'swipe':
            return {'ev': 'swipe', 'args': self.enc(list(a)), 'kwargs': self.enc(k)}
        if name == 'sleep':
            return {'ev': 'sleep', 's': self.enc(arg(0, 's'))}
        if name in CLOCK_NAMES:
            return {'ev': 'now', 'src': f'{mod_name}.{name}'}
        if name in OCR_NAMES:
            ev = {'ev': 'ocr', 'fn': name, 'name': self.enc(arg(0, 'name'))}
            if len(a) > 1 or k:
                ev['args'] = self.enc(list(a[1:]))
                if k:
                    ev['kwargs'] = self.enc(k)
            return ev
        if name in ('adb', 'adb_exec_dump'):
            return {'ev': 'adb', 'fn': name, 'argv': self.enc(list(a)), 'kwargs': self.enc(k)}
        if name == 'run':
            return {'ev': 'run', 'argv': self.enc(arg(0, 'args')), 'kwargs': self.enc(
                {x: y for x, y in k.items() if x not in ('capture_output', 'text', 'cwd', 'env')})}
        return {'ev': 'stub', 'fn': f'{mod_name}.{name}', 'args': self.enc(list(a)), 'kwargs': self.enc(k)}

    def on_io(self, mod_name: str, name: str):
        rec = self

        def call(inner, a, k):
            ev = rec.event(rec.current(), rec.io_event(mod_name, name, a, k))   # before: keeps order
            try:
                out = inner(*a, **k)
            except BaseException as e:
                ev['raise'] = type(e).__name__
                raise
            opaque: list = []
            if ev['ev'] == 'shot':
                ev['frame'] = rec.enc(out, opaque)['img'] if rec.Image and isinstance(
                    out, rec.Image.Image) else rec.enc(out, opaque)
            elif ev['ev'] == 'now':
                ev['val'] = rec.enc(out, opaque)
            elif ev['ev'] == 'tap' and isinstance(out, str):
                ev['mode'] = out                # the patched tap reports the mode it used
            elif ev['ev'] in ('adb', 'run') and isinstance(out, subprocess.CompletedProcess):
                ev['rc'] = out.returncode
                ev['out'] = rec.enc(out, opaque)
                fh = k.get('stdout')
                if hasattr(fh, 'name') and hasattr(fh, 'flush'):   # shot(): `screencap -p` into a file
                    fh.flush()
                    ev['stdout_file'] = rec.enc(Path(fh.name).read_bytes(), opaque)
            elif ev['ev'] not in ('sleep', 'key', 'hold', 'swipe', 'seq'):
                ev['out'] = rec.enc(out, opaque)
            if opaque:
                rec.counts['events_opaque'] += 1
            return out
        return call

    # -- calls
    def wrap_call(self, mod_name: str, fn):
        rec = self

        @functools.wraps(fn)
        def w(*args, **kwargs):
            if rec.depth:
                return fn(*args, **kwargs)
            vals = (*args, *kwargs.values())
            if not (fn.__name__.startswith('parse_') or any(
                    isinstance(x, (rec.Image.Image, list, tuple)) for x in vals)):
                return fn(*args, **kwargs)      # pid/str readers: not a pure frame function
            opaque: list = []
            before = json.dumps([rec.enc(list(args), opaque), rec.enc(kwargs, opaque)], sort_keys=True)
            ev0 = rec.dev_events
            rec.depth += 1
            try:
                out = fn(*args, **kwargs)
            finally:
                rec.depth -= 1
            if rec.dev_events != ev0:
                rec.counts['calls_impure'] += 1
                return out
            # shortcut: in-place edits are seen only via ImageDraw/paste/putpixel (they drop the
            # memoised key); raw pixel-access writes inside a vision fn would go unnoticed
            after = json.dumps([rec.enc(list(args), opaque), rec.enc(kwargs, opaque)], sort_keys=True)
            if after != before:
                rec.counts['calls_mutating'] += 1
                return out
            o = rec.enc(out, opaque)
            if opaque:
                rec.counts['calls_opaque'] += 1
                return out
            key = f'{mod_name}.{fn.__qualname__}|{before}'
            shard = rec.calls.setdefault(mod_name, {})
            hit = shard.get(key)
            if hit is None:
                a, k = json.loads(before)
                shard[key] = {'fn': f'{mod_name}.{fn.__qualname__}', 'args': a, 'kwargs': k,
                              'out': o, 'test': rec.test_id, 'n': 1}
                rec.counts['calls_recorded'] += 1
                t = rec.per_test.setdefault(rec.test_id, {})
                t['calls'] = t.get('calls', 0) + 1
            else:
                hit['n'] += 1
                if hit['out'] != o:
                    rec.conflicts.append({'fn': hit['fn'], 'test': rec.test_id, 'args': hit['args'],
                                          'first_test': hit['test'], 'out': o, 'first_out': hit['out']})
            return out
        w.__parity_call__ = True
        return w

    def install_calls(self) -> int:
        wrapped = {}
        for mod in self.bot_modules():
            for attr, val in vars(mod).items():
                if (isinstance(val, types.FunctionType) and CALL_NAME.match(attr)
                        and val.__module__ == mod.__name__ and id(val) not in wrapped):
                    wrapped[id(val)] = self.wrap_call(mod.__name__, val)
        n = 0
        for mod in list(sys.modules.values()) + self.bot_modules():   # incl. `from x import f`
            f = getattr(mod, '__file__', None)
            if not f or not Path(f).resolve().is_relative_to(self.scripts):
                continue
            for attr, val in list(vars(mod).items()):
                if id(val) in wrapped:
                    setattr(mod, attr, wrapped[id(val)])
                    n += 1
        return n

    # -- devices
    def install_devices(self) -> int:
        import fake_vision as fv
        self.fv = fv
        rec = self

        def mk(build):
            def make(d, a, k, r, exc):
                evs = build(d, a, k, r)
                for ev in evs:
                    if exc is not None:
                        ev['raise'] = type(exc).__name__
                return evs
            return make

        def arg(a, k, i, key, default=None):
            return k.get(key, a[i] if len(a) > i else default)

        self.dev_makers = {
            '_shot': mk(lambda d, a, k, r: [{'ev': 'shot', 'name': rec.enc(arg(a, k, 0, 'name')),
                                            'frame': rec.frames.key(r) if rec.Image and isinstance(
                                                r, rec.Image.Image) else rec.enc(r)}]),
            '_tap': mk(lambda d, a, k, r: [{'ev': 'tap', 'x': rec.enc(arg(a, k, 0, 'xy')[0]),
                                           'y': rec.enc(arg(a, k, 0, 'xy')[1]),
                                           'mode': r if isinstance(r, str) else
                                           rec.enc(arg(a, k, 2, 'mode') or fv.v.TAP_MODE),
                                           'mode_arg': rec.enc(arg(a, k, 2, 'mode')),
                                           'wait': rec.enc(arg(a, k, 1, 'wait', 1.0))}]),
            '_tap_seq': mk(lambda d, a, k, r: [{'ev': 'seq', 'steps': rec.enc(arg(a, k, 0, 'steps', [])),
                                               'tolerate': rec.enc(arg(a, k, 1, 'tolerate', True)),
                                               'dry': rec.enc(arg(a, k, 2, 'dry', False))}]),
            '_key_seq': mk(lambda d, a, k, r: [{'ev': 'key', 'code': rec.enc(c), 'w': rec.enc(w),
                                                'tolerate': rec.enc(arg(a, k, 1, 'tolerate', True)),
                                                'dry': rec.enc(arg(a, k, 2, 'dry', False))}
                                               for c, w in arg(a, k, 0, 'steps', [])]),
            '_tap_hold': mk(lambda d, a, k, r: [{'ev': 'hold', 'x': rec.enc(arg(a, k, 0, 'xy')[0]),
                                                'y': rec.enc(arg(a, k, 0, 'xy')[1]),
                                                'ms': rec.enc(arg(a, k, 1, 'ms', 120)),
                                                'wait': rec.enc(arg(a, k, 2, 'wait', 1.0))}]),
            '_swipe': mk(lambda d, a, k, r: [{'ev': 'swipe', 'args': rec.enc(list(a)), 'kwargs': rec.enc(k)}]),
            '_ocr': mk(lambda d, a, k, r: [{'ev': 'ocr', 'fn': 'ocr_lines', 'name': rec.enc(arg(a, k, 0, 'name')),
                                           'out': rec.enc(r)}]),
            '_no_adb': mk(lambda d, a, k, r: [{'ev': 'adb', 'fn': 'adb', 'argv': rec.enc(list(a)),
                                              'kwargs': rec.enc(k),
                                              'rc': getattr(r, 'returncode', None)}]),
        }

        def classes(c):
            yield c
            for s in c.__subclasses__():
                yield from classes(s)

        n = 0
        for cls in classes(fv.FakeDevice):
            for name in self.dev_makers:
                if name in cls.__dict__:
                    self.wrap_method(cls, name)
                    n += 1

        orig_init = fv.FakeDevice.__init__

        def init(self, test, *a, **k):
            orig_init(self, test, *a, **k)
            if self.__dict__.get('_parity_init'):
                return
            self.__dict__['_parity_init'] = True
            self.__dict__.setdefault('_parity_events', [])
            rec.devices.append(self)
        fv.FakeDevice.__init__ = init
        return n

    def wrap_method(self, cls, name):
        orig = cls.__dict__[name]
        if getattr(orig, '__parity_dev__', False):
            return
        make = self.dev_makers[name]

        rec = self
        @functools.wraps(orig)
        def w(dev, *a, **k):
            # a device method called by the SAME device (super() chains, GatedDevice._tap_hold ->
            # self._tap) is the fake's internals, not bot behaviour: only the outer call records.
            # Device I/O reached through bot code still records (real_seq: the fake's _tap_seq ->
            # the real tap_seq -> v.adb = dev._no_adb; that caller frame is afk_claim_vision).
            caller = sys._getframe(1)
            internal = caller.f_locals.get('self') is dev or caller.f_locals.get('dev') is dev
            d = 1 if internal else 0
            events = dev.__dict__.setdefault('_parity_events', [])
            at = len(events)                    # the call's event goes BEFORE what happens inside
            r, exc = None, None
            try:
                r = orig(dev, *a, **k)
                return r
            except BaseException as e:
                exc = e                         # incl. AssertionError: a fired test guard is part
                raise                           # of the stream (`raise` field), replayed as such
            finally:
                if d == 0:
                    evs = make(dev, a, k, r, exc)
                    events[at:at] = evs
                    rec.dev_events += len(evs)
        w.__parity_dev__ = True
        setattr(cls, name, w)

    # -- mock patches: wrap what tests put in place of bot I/O
    def install_patch_hook(self) -> None:
        rec = self
        orig_enter = mock._patch.__enter__

        def enter(p):
            result = orig_enter(p)
            try:
                rec.after_patch(p)
            except Exception as exc:          # recording must never break a test
                rec.per_test.setdefault(rec.test_id, {}).setdefault('hook_errors', []).append(repr(exc))
            return result
        mock._patch.__enter__ = enter

    def after_patch(self, p) -> None:
        if getattr(p, 'attribute_name', None) is not None or getattr(p, 'attribute', None) is None:
            return
        target, attr = p.getter(), p.attribute
        new = getattr(target, attr, None)
        fv = self.fv
        if isinstance(target, type) and fv is not None and issubclass(target, fv.FakeDevice):
            if attr in self.dev_makers and attr in target.__dict__:
                self.wrap_method(target, attr)
                self.counts['patches_wrapped'] += 1
            return
        if target is time:
            if attr == 'sleep' or attr in CLOCK_NAMES:
                setattr(target, attr, Proxy(new, self.on_io('time', attr)))
                self.counts['patches_wrapped'] += 1
            return
        if target is subprocess and attr == 'run':
            setattr(target, attr, Proxy(new, self.on_io('subprocess', 'run')))
            self.counts['patches_wrapped'] += 1
            return
        if not self.is_bot(target) and not (isinstance(target, types.ModuleType)
                                            and getattr(target, '__name__', '') == 'subprocess'):
            return
        if attr.startswith('__'):
            return
        if callable(new) and not isinstance(new, type):
            if getattr(getattr(new, '__func__', None), '__parity_dev__', False) or isinstance(new, Proxy):
                return                        # FakeDevice method: recorded at class level
            setattr(target, attr, Proxy(new, self.on_io(target.__name__, attr)))
            self.counts['patches_wrapped'] += 1
            self.overrides.append({'mod': target.__name__, 'attr': attr, 'stub': True})
        else:
            self.overrides.append({'mod': target.__name__, 'attr': attr, 'value': self.enc(new)})

    # -- entries
    def install_entries(self) -> int:
        rec = self
        n = 0
        for mod in self.bot_modules():
            fn = getattr(mod, 'main', None)
            if not isinstance(fn, types.FunctionType) or fn.__module__ != mod.__name__:
                continue

            def w(*a, _fn=fn, _name=f'{mod.__name__}.main', **k):
                given = a[0] if a else k.get('argv')
                argv = list(given) if isinstance(given, (list, tuple)) else list(sys.argv[1:])
                ev = {'ev': 'ret', 'fn': _name, 'argv': rec.enc(argv)}
                if a or k:
                    ev['call'] = rec.enc([list(a), k])
                try:
                    rc = _fn(*a, **k)
                except SystemExit as e:
                    ev.update(rc=rec.enc(e.code), exit=True)
                    rec.event(rec.current(), ev)
                    raise
                except BaseException as e:
                    ev.update(rc=1, **{'raise': type(e).__name__})
                    rec.event(rec.current(), ev)
                    raise
                ev['rc'] = rec.enc(rc)
                rec.event(rec.current(), ev)
                return rc
            w.__parity_entry__ = True
            mod.main = w
            n += 1
        return n

    # -- infra calls (E1): the test's direct calls into the adb/tap/screencap/lock layer
    def enc_infra(self, x):
        if self.Image is not None and isinstance(x, self.Image.Image):
            rgb = x if x.mode == 'RGB' else x.convert('RGB')
            return {'img': self.frames.key(x), 'w': x.size[0], 'h': x.size[1], 'mode': x.mode,
                    'crc32': zlib.crc32(rgb.tobytes())}
        if isinstance(x, (list, tuple)):
            return [self.enc_infra(i) for i in x]
        if isinstance(x, dict) and all(isinstance(k, str) for k in x):
            return {k: self.enc_infra(v) for k, v in x.items()}
        return self.enc(x)

    def infra_state(self, mod, name: str, a: tuple, k: dict) -> dict:
        if mod.__name__ == '_bot_lock':
            lock = a[0] if a else k.get('lock')
            lock = Path(lock) if lock is not None else mod._default_lock()
            env = a[1] if len(a) > 1 else k.get('env')
            env = os.environ if env is None else env
            now = a[3] if len(a) > 3 else k.get('now')
            st = {'lock': self.enc(Path(lock)), 'env': {e: env.get(e) for e in
                                                         ('AFK_BOT_LOCK_HELD', 'AFK_LOCK_STALE')}}
            try:
                text = Path(lock).read_text(encoding='ascii', errors='replace')
                age = (time.time() if now is None else now) - Path(lock).stat().st_mtime
                st.update(exists=True, text='<PID>' if text.strip() == str(os.getpid()) else text,
                          age=int(age))
            except FileNotFoundError:
                st['exists'] = False
            return st
        st = {'TAP_MODE': mod.TAP_MODE, 'TAP_DEAD': sorted(mod._TAP_DEAD),
              'SENDEVENT': self.enc(mod._SENDEVENT), 'env': {'AFK_TAP_MODE': os.environ.get('AFK_TAP_MODE')},
              # patched -> every host sleep is an event; unpatched -> Python really slept, none recorded
              'sleep_patched': isinstance(time.sleep, Proxy)}
        if name == 'shot':                      # the persisted TMP/<name>.png (OCR reads it)
            nm = a[0] if a else k.get('name')
            f = Path(mod.TMP) / f'{nm}.png'
            try:
                data = f.read_bytes()
                st['file'] = {'exists': True, 'len': len(data), 'sha16': hashlib.sha256(data).hexdigest()[:16]}
            except OSError:
                st['file'] = {'exists': False}
        return st

    def wrap_infra(self, mod, fn):
        rec = self
        name = fn.__name__.removeprefix('_real_') if fn.__name__.startswith('_real_') else fn.__name__

        @functools.wraps(fn)
        def w(*a, **k):
            if rec.infra_depth:
                return fn(*a, **k)
            sink = rec.current()
            evs = sink.__dict__.setdefault('_parity_events', [])
            n0 = len(evs)
            before = rec.infra_state(mod, name, a, k)
            rec.infra_depth += 1
            out, exc = None, None
            tee = _Tee(sys.stdout)              # the lines the call prints (informative diff)
            sys.stdout = tee
            try:
                out = fn(*a, **k)
                return out
            except BaseException as e:
                exc = e
                raise
            finally:
                if sys.stdout is tee:
                    sys.stdout = tee.inner
                rec.infra_depth -= 1
                r = {'fn': f'{mod.__name__}.{name}', 'args': rec.enc_infra(list(a)),
                     'kwargs': rec.enc_infra(k), 'before': before, 'events': evs[n0:],
                     'after': rec.infra_state(mod, name, a, k), 'stdout': mask_clock(tee.captured.getvalue())}
                if exc is not None:
                    r['raise'] = type(exc).__name__
                else:
                    o = rec.enc_infra(out)
                    if mod.__name__ == '_bot_lock' and isinstance(o, str):
                        o = o.replace(f'pid {os.getpid()},', 'pid <PID>,')
                    r['out'] = o
                key = json.dumps(r, sort_keys=True, default=_default)
                shard = rec.infra.setdefault(mod.__name__, {})
                if key in shard:
                    shard[key]['n'] += 1
                    if rec.test_id not in shard[key]['tests']:   # identical call from another test:
                        shard[key]['tests'].append(rec.test_id)  # keep every test it specifies
                        t = rec.per_test.setdefault(rec.test_id, {})
                        t['infra'] = t.get('infra', 0) + 1
                else:
                    shard[key] = dict(r, test=rec.test_id, tests=[rec.test_id], n=1)
                    t = rec.per_test.setdefault(rec.test_id, {})
                    t['infra'] = t.get('infra', 0) + 1
        w.__parity_infra__ = True
        return w

    def install_infra(self) -> int:
        wrapped = {}
        for mod in self.bot_modules():
            for name in INFRA.get(mod.__name__, ()):
                fn = vars(mod).get(name)
                # only the module's own functions: fake_vision's lock-stub lambdas stay unwrapped
                if (isinstance(fn, types.FunctionType) and fn.__module__ == mod.__name__
                        and id(fn) not in wrapped):
                    wrapped[id(fn)] = self.wrap_infra(mod, fn)
        # fake_vision stubs _bot_lock.acquire/release/describe at import and keeps the originals
        # as _real_*; test_bot_lock binds those at import -> wrap them so lock semantics are recorded
        lock_mod = sys.modules.get('_bot_lock')
        for real in ('_real_acquire', '_real_release', '_real_describe'):
            fn = getattr(lock_mod, real, None)
            if isinstance(fn, types.FunctionType) and id(fn) not in wrapped:
                wrapped[id(fn)] = self.wrap_infra(lock_mod, fn)
        n = 0
        for mod in list(sys.modules.values()) + self.bot_modules():   # incl. `from x import f`
            f = getattr(mod, '__file__', None)
            if not f or not Path(f).resolve().is_relative_to(self.scripts):
                continue
            for attr, val in list(vars(mod).items()):
                if id(val) in wrapped:
                    setattr(mod, attr, wrapped[id(val)])
                    n += 1
        return n

    # -- per test
    def start(self, test_id: str) -> None:
        self.test_id = test_id
        self.devices, self.pseudo, self.overrides = [], None, []
        self.depth = self.infra_depth = 0
        self.frames.memo.clear()                # bounded memory: keys live for one test

    def stop(self, outcome: str) -> None:
        mod = self.test_id.split('.')[0]
        recs = self.flows.setdefault(mod, [])
        sinks = [(i, d) for i, d in enumerate(self.devices)]
        if self.pseudo is not None and self.pseudo.__dict__.get('_parity_events'):
            sinks.append((len(sinks), self.pseudo))
        incomplete = 0
        for i, dev in sinks:
            events = dev.__dict__.get('_parity_events', [])
            out = dev.__dict__.get('out')
            r = {'test': self.test_id, 'dev': None if isinstance(dev, _Pseudo) else type(dev).__name__,
                 'i': i, 'outcome': outcome, 'events': events, 'overrides': self.overrides,
                 'stdout': mask_clock(out.getvalue()) if isinstance(out, io.StringIO) else None}
            taps = dev.__dict__.get('taps')
            if isinstance(taps, list):
                n_ev = sum(len(e['steps']) if e['ev'] == 'seq' and isinstance(e.get('steps'), list)
                           else 1 for e in events if e['ev'] in TAP_LIKE | {'seq'})
                # heuristic: dev.taps vs tap-like events; differs when a test appends to dev.taps
                # itself, or when real_seq sends a batch through adb (seq event, no dev.taps entry)
                if n_ev != len(taps):
                    r['taps_mismatch'] = {'dev_taps': len(taps), 'events': n_ev}
                    incomplete += 1
            recs.append(r)
        t = self.per_test.setdefault(self.test_id, {})
        t['outcome'] = outcome
        t['flows'] = len(sinks)
        if incomplete:
            t['taps_mismatch_flows'] = incomplete
        self.devices, self.pseudo = [], None


class _Result(unittest.TextTestResult):
    rec: Recorder = None

    def startTest(self, test):
        self.rec.start(test.id())
        self._outcome = 'ok'
        super().startTest(test)

    def addFailure(self, test, err):
        self._outcome = 'fail'
        super().addFailure(test, err)

    def addError(self, test, err):
        self._outcome = 'error'
        super().addError(test, err)

    def addSkip(self, test, reason):
        self._outcome = 'skip'
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self._outcome = 'fail'
        super().addSubTest(test, subtest, err)

    def stopTest(self, test):
        super().stopTest(test)
        self.rec.stop(self._outcome)


# ---------------------------------------------------------------- .spectre write guard



# ---------------------------------------------------------------- export

def _default(o):
    return {'repr': type(o).__name__}


def _jsonl(path: Path, head: dict, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps({'header': head}, sort_keys=True) + '\n')
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False, default=_default) + '\n')


def install_overlay(repo: Path, frames_json: Path) -> dict:
    """*.png under <repo>/.spectre resolve ONLY against the frozen corpus (E0a).

    The live lane prunes/moves shot dirs while the suite runs (F16 -> .spectre/trash), so
    reading live frames makes two exports differ. A referenced path from frames.json is
    served from $SPECTRE_PARITY_DIR/frames/<sha16>.png (original bytes); any other .png
    there looks missing. Other .spectre files pass through and are listed."""
    import builtins
    import errno
    root = os.path.normcase(os.path.abspath(repo / '.spectre'))
    vmap = {}
    for e in json.loads(frames_json.read_text(encoding='utf-8'))['frames']:
        f = str(PARITY_DIR / 'frames' / f'{e["sha16"]}.png')
        for s in e['src']:
            vmap[os.path.normcase(os.path.abspath(repo / s['path']))] = f
    stats = {'mapped': len(vmap), 'served': set(), 'hidden': set(), 'live_other': set()}

    def resolve(p):
        """None = not ours, '' = hidden, else the corpus file."""
        if isinstance(p, int):
            return None
        try:
            s = os.fsdecode(os.fspath(p))
        except TypeError:
            return None
        a = os.path.normcase(os.path.abspath(s))
        if not a.startswith(root + os.sep):
            return None
        r = a[len(root) + 1:].replace(os.sep, '/')
        if not a.endswith('.png'):
            stats['live_other'].add(r)
            return None
        hit = vmap.get(a)
        (stats['served'] if hit else stats['hidden']).add(r)
        return hit or ''

    def missing(p):
        return FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), os.fsdecode(os.fspath(p)))

    real_open, real_stat = builtins.open, os.stat
    real_exists, real_isfile, real_getsize = os.path.exists, os.path.isfile, os.path.getsize

    def open_(file, mode='r', *a, **k):
        t = resolve(file)
        if t is None or any(c in mode for c in 'wax+'):
            return real_open(file, mode, *a, **k)
        if not t:
            raise missing(file)
        return real_open(t, mode, *a, **k)

    def stat_(path, *a, **k):
        t = resolve(path)
        if t is None:
            return real_stat(path, *a, **k)
        if not t:
            raise missing(path)
        return real_stat(t, *a, **k)

    def exists_(path):
        t = resolve(path)
        return real_exists(path) if t is None else bool(t)

    def isfile_(path):
        t = resolve(path)
        return real_isfile(path) if t is None else bool(t)

    def getsize_(path):
        t = resolve(path)
        if t is None:
            return real_getsize(path)
        if not t:
            raise missing(path)
        return real_getsize(t)
    builtins.open = io.open = open_
    os.stat = stat_
    os.path.exists, os.path.isfile, os.path.getsize = exists_, isfile_, getsize_
    return stats


def export(repo: Path, out: Path, pattern: str, allow_dirty: bool) -> int:
    d = dirty(repo)
    if d and not allow_dirty:
        print('REFUSED: scripts/ or templates/ dirty in', repo, *d, sep='\n  ')
        return 3
    head = header(repo)
    if d:
        head['dirty'] = d
    sys.path.insert(0, str(repo / 'scripts'))
    sys.path.insert(0, str(repo / 'scripts' / 'tests'))
    os.chdir(repo)
    sys.argv = ['export_goldens']             # main() falling back to sys.argv sees a stable argv
    fj = OUT / 'frames.json'
    overlay = install_overlay(repo, fj) if fj.is_file() else None
    from PIL import Image, ImageDraw
    import afk_claim_vision as v               # per-run shot dir would be .spectre/shots-<pid>
    v.TMP = Path(tempfile.mkdtemp(prefix='parity-shots-'))
    blocked: list = []
    corpus, rgb_alias = set(), {}
    if fj.is_file():
        fr = json.loads(fj.read_text(encoding='utf-8'))['frames']
        corpus = {e['sha16'] for e in fr}
        rgb_alias = {e['rgb_sha16']: e['sha16'] for e in fr if e.get('rgb_sha16')}
    frames = Frames(corpus, rgb_alias)
    rec = Recorder(repo, frames)
    rec.Image = Image

    orig_draw = ImageDraw.Draw            # in-place edits drop the memoised key
    orig_paste, orig_put = Image.Image.paste, Image.Image.putpixel

    def draw(im, *a, **k):
        frames.forget(im)
        return orig_draw(im, *a, **k)

    def paste(self, *a, **k):
        frames.forget(self)
        return orig_paste(self, *a, **k)

    def putpixel(self, *a, **k):
        frames.forget(self)
        return orig_put(self, *a, **k)
    ImageDraw.Draw, Image.Image.paste, Image.Image.putpixel = draw, paste, putpixel

    t0 = time.time()
    suite = unittest.defaultTestLoader.discover(str(repo / 'scripts' / 'tests'), pattern=pattern)
    installed = {'devices': rec.install_devices(), 'calls': rec.install_calls(),
                 'entries': rec.install_entries(), 'infra': rec.install_infra(),
                 'bot_modules': len(rec.bot_modules())}
    rec.install_patch_hook()
    _Result.rec = rec
    guard_spectre(repo, blocked, lambda: rec.test_id)
    res = unittest.TextTestRunner(resultclass=_Result, verbosity=0, stream=sys.stderr).run(suite)

    stage = out.with_name(out.name + '.partial')
    if stage.exists():
        shutil.rmtree(stage)
    for mod, rows in sorted(rec.flows.items()):
        if rows:
            _jsonl(stage / 'flows' / f'{mod}.jsonl', head, rows)
    for mod, shard in sorted(rec.calls.items()):
        _jsonl(stage / 'calls' / f'{mod}.jsonl', head, sorted(shard.values(),
               key=lambda r: json.dumps([r['fn'], r['args'], r['kwargs']], sort_keys=True)))
    for mod, shard in sorted(rec.infra.items()):
        _jsonl(stage / 'infra' / f'{mod}.jsonl', head, sorted(
            shard.values(), key=lambda r: (r['fn'], json.dumps(r, sort_keys=True, default=_default))))
    flow_rows = [x for r in rec.flows.values() for x in r]
    summary = {'infra_records': {m: len(s) for m, s in sorted(rec.infra.items())},
               'header': head, 'suite': {'tests_run': res.testsRun, 'failures': len(res.failures),
               'errors': len(res.errors), 'skipped': len(res.skipped)},
               'installed': installed, 'counts': rec.counts,
               'flow_records': len(flow_rows), 'flow_records_without_device': sum(
                   x['dev'] is None for x in flow_rows),
               'flow_records_taps_mismatch': sum('taps_mismatch' in x for x in flow_rows),
               'flow_events': sum(len(x['events']) for x in flow_rows),
               'conflicts': rec.conflicts, 'spectre_writes_blocked': blocked,
               'overlay': None if overlay is None else {
                   'mapped': overlay['mapped'], 'served': len(overlay['served']),
                   'hidden': sorted(overlay['hidden']), 'live_other': sorted(overlay['live_other'])},
               'tests': dict(sorted(rec.per_test.items()))}
    (stage / 'tests.json').write_text(json.dumps(summary, indent=1, sort_keys=True, default=_default),
                                      encoding='utf-8')
    (stage / 'synthetic.json').write_text(json.dumps({'header': head, 'dir': 'synthetic',
                                                      'frames': dict(sorted(frames.synthetic.items())),
                                                      'blobs': dict(sorted(rec.blobs.items()))},
                                                     indent=1, sort_keys=True), encoding='utf-8')
    if out.exists():
        shutil.rmtree(out)
    os.replace(stage, out)
    print(f'export: {res.testsRun} tests ({len(res.failures)} fail, {len(res.errors)} err, '
          f'{len(res.skipped)} skip) in {time.time() - t0:.0f}s; {summary["flow_records"]} flows / '
          f'{summary["flow_events"]} events ({summary["flow_records_taps_mismatch"]} taps mismatch), '
          f'{rec.counts["calls_recorded"]} calls, {len(frames.synthetic)} synthetic frames, '
          f'{len(rec.conflicts)} conflicts, {len(blocked)} .spectre writes blocked -> {out}')
    return 0 if res.wasSuccessful() and not blocked else 1


def _ident(line: str) -> str:
    try:
        r = json.loads(line)
    except ValueError:
        return line[:80]
    if 'header' in r:
        return 'header'
    if 'test' in r and 'i' in r:
        return f'{r["test"]}#{r["i"]}'
    return f'{r.get("fn")}({json.dumps(r.get("args"))[:80]})'


def compare(a: Path, b: Path) -> list[dict]:
    diffs = []
    fa = {p.relative_to(a).as_posix() for p in a.rglob('*') if p.is_file()}
    fb = {p.relative_to(b).as_posix() for p in b.rglob('*') if p.is_file()}
    for f in sorted(fa ^ fb):
        diffs.append({'file': f, 'only_in_one_run': True})
    for f in sorted(fa & fb):
        la = (a / f).read_text(encoding='utf-8').splitlines()
        lb = (b / f).read_text(encoding='utf-8').splitlines()
        if la != lb:
            if f.endswith('.jsonl'):
                sa, sb = set(la), set(lb)
                recs = sorted({_ident(x) for x in sa ^ sb})
            else:
                recs = []
            diffs.append({'file': f, 'records': recs[:200], 'n_records': len(recs)})
    return diffs


def check(repo: Path, pattern: str, allow_dirty: bool, keep: Path | None, force: bool) -> int:
    tmp = Path(tempfile.mkdtemp(prefix='parity-goldens-'))
    runs, rcs = [], []
    for i in (1, 2):
        out = tmp / f'run{i}'
        cmd = [sys.executable, str(Path(__file__).resolve()), 'export', '--repo', str(repo),
               '--out', str(out), '--pattern', pattern] + (['--allow-dirty'] if allow_dirty else [])
        p = subprocess.run(cmd, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        print(f'run {i}: rc {p.returncode}')
        if p.returncode not in (0, 1):
            return p.returncode
        runs.append(out)
        rcs.append(p.returncode)
    diffs = compare(*runs)
    report = {'deterministic': not diffs, 'run_rc': rcs, 'diffs': diffs}
    (runs[0] / 'determinism.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    for dd in diffs:
        print('DIFF', dd['file'], dd.get('n_records', ''), *dd.get('records', [])[:5])
    dst = keep or GOLDENS
    ok = not diffs and rcs == [0, 0]
    if ok or force:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(runs[0], dst)
        print(f'check: {"deterministic + green" if ok else "FORCED"}; goldens -> {dst}')
    else:
        print(f'check: NOT copied ({len(diffs)} files differ, run rc {rcs}); runs kept in {tmp}')
    return 0 if ok else 4


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('cmd', choices=('export', 'check', 'py-tree'))
    ap.add_argument('--repo', type=Path, default=OWN_REPO)
    ap.add_argument('--out', type=Path, default=None)
    ap.add_argument('--pattern', default='test*.py')
    ap.add_argument('--allow-dirty', action='store_true')
    ap.add_argument('--force', action='store_true', help='check: copy run 1 even if not identical/green')
    a = ap.parse_args(argv)
    repo = a.repo.resolve()
    if a.cmd == 'py-tree':
        print(py_tree(repo) + (' dirty' if dirty(repo) else ''))
        return 0
    if a.cmd == 'export':
        return export(repo, (a.out or GOLDENS).resolve(), a.pattern, a.allow_dirty)
    return check(repo, a.pattern, a.allow_dirty, a.out.resolve() if a.out else None, a.force)


if __name__ == '__main__':
    sys.exit(main())
