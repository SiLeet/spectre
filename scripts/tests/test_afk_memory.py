"""T78: afk_memory — read-batch snapshot, cache, power() through the ONE guard."""
from __future__ import annotations

import contextlib
import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import afk_claim_vision as v  # noqa: E402
import afk_memory as am  # noqa: E402
import afk_dailies as dl  # noqa: E402

ART = Path(__file__).resolve().parent / '.artifacts'
PID, BASE, OFF = '1', '0x7964E0000000', 0xA578


def batch_rows(lo=259850, hi=0, ptr=0x7964_E123_4560, valid=True):
    return [{'name': f'Slot.{n}', 'address': '0x0', 'value': val, 'fmt': 'U32', 'valid': valid}
            for n, val in (('lo', lo), ('hi', hi), ('ptr', ptr))]


class Base(unittest.TestCase):
    def setUp(self):
        am._snap_cache.clear()
        am._power_cache.clear()
        ART.mkdir(exist_ok=True)
        self.state = ART / 'power-state-afk-memory.json'
        self.state.unlink(missing_ok=True)
        patches = [mock.patch.object(v, 'POWER_STATE', self.state),
                   mock.patch.object(v, 'TMP', ART / 'afk_memory_tmp')]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.calls = []

    def fake_run(self, rows=None, rc=0, stdout=None, exc=None):
        def run(cmd, **kw):
            self.calls.append(cmd)
            if exc:
                raise exc
            out = stdout if stdout is not None else json.dumps(rows)
            return subprocess.CompletedProcess(cmd, rc, out, '')
        return mock.patch.object(am.subprocess, 'run', side_effect=run)


class TSnapshot(Base):
    def test_one_call_cached_then_expires(self):
        y = am.slot_yaml(OFF)
        with self.fake_run(batch_rows()):
            with mock.patch.object(am.time, 'monotonic', return_value=100.0):
                a = am.snapshot(PID, BASE, y)
                b = am.snapshot(PID, BASE, y)
            with mock.patch.object(am.time, 'monotonic', return_value=101.6):
                am.snapshot(PID, BASE, y)
        self.assertEqual(a['Slot.lo']['value'], 259850)
        self.assertIs(a, b)
        self.assertEqual(len(self.calls), 2)          # cache hit, then TTL expiry
        cmd = self.calls[0]
        self.assertEqual(cmd[1:3], ['read-batch', '--offsets'])
        self.assertIn('--json', cmd)
        self.assertIn('--adb', cmd)

    def test_failures_return_empty_and_are_not_cached(self):
        y = am.slot_yaml(OFF)
        for kw in ({'rc': 1}, {'stdout': 'not json'},
                   {'exc': subprocess.TimeoutExpired('x', 30)}, {'exc': FileNotFoundError()}):
            with self.subTest(kw=kw), self.fake_run(**kw):
                self.assertEqual(am.snapshot(PID, BASE, y), {})
        self.assertEqual(am._snap_cache, {})

    def test_slot_yaml_offsets(self):
        text = am.slot_yaml(0xA578).read_text()
        for needle in ('offset: 0xa578', 'offset: 0xa57c', 'offset: 0xa580', 'U64'):
            self.assertIn(needle, text)


class TPower(Base):
    def seed(self, **kw):
        st = {'offset': OFF, 'width': 8, 'power': 259850, 'pid': PID, 'base': BASE}
        st.update(kw)
        v.save_power_state(st)

    def test_u32_entry_ok_in_one_process_run(self):
        self.seed(width=4)
        with self.fake_run(batch_rows()):
            status, val = am.power(PID, BASE)
            am.power(PID, BASE)                        # cached
        self.assertEqual((status, val), ('ok', 259850))
        self.assertEqual(len(self.calls), 1)

    def test_same_verdict_as_classic_reads(self):
        """Guard verdicts must match v.memory_preflight with the dump backend."""
        cases = [  # (state width, lo, hi, ptr, last)
            (4, 259850, 0x1234, 0x7964_E000_0010, 259850),      # u32 map entry ok
            (4, 108449240, 0, 0x7964_E000_0010, 259850),        # drift -> disabled
            (8, 259900, 0, 0x10, 259850),                       # u64 field, no ptr -> ok
            (8, 259850, 0x55, 0x7964_E000_0010, 259850),        # u64 aliasing a map entry -> disabled
        ]
        for width, lo, hi, ptr, last in cases:
            with self.subTest(width=width, lo=lo, hi=hi):
                raw = lo.to_bytes(4, 'little') + hi.to_bytes(4, 'little') + ptr.to_bytes(8, 'little')

                def dump(pid, addr, out, size='8', raw=raw):
                    Path(out).write_bytes(raw[:int(size)])
                    return True
                self.seed(width=width, power=last)
                with mock.patch.object(v, 'adb_exec_dump', side_effect=dump), \
                     mock.patch.object(v, 'revalidate_power_offset', return_value=None):
                    classic = v.memory_preflight(PID, BASE)
                self.seed(width=width, power=last)
                am._snap_cache.clear()
                am._power_cache.clear()
                with self.fake_run(batch_rows(lo, hi, ptr)), \
                     mock.patch.object(v, 'revalidate_power_offset', return_value=None):
                    fast = am.power(PID, BASE)
                self.assertEqual(fast, classic)

    def test_no_read_batch_falls_back_to_classic_dumps(self):
        self.seed(width=4)
        with self.fake_run(rc=2), \
             mock.patch.object(v, 'read_power', return_value=259850) as rp, \
             mock.patch.object(v, 'read_power_entry_valid', return_value=True):
            self.assertEqual(am.power(PID, BASE), ('ok', 259850))
        rp.assert_called_once()

    def test_fail_not_cached(self):
        self.seed(width=4)
        with self.fake_run(rc=2), mock.patch.object(v, 'read_power', return_value=None):
            self.assertEqual(am.power(PID, BASE), ('fail', None))
        self.assertEqual(am._power_cache, {})

    def test_drift_window_single_rule(self):
        self.assertEqual(v.drift_window(259850), 25985)
        self.assertEqual(v.drift_window(1000), 2000)


class TConsumer(unittest.TestCase):
    def test_dailies_power_gate_uses_afk_memory(self):
        with mock.patch.object(dl.v, 'idle_seconds', return_value=None), \
             mock.patch.object(dl.afk_memory, 'power', return_value=('fail', None)) as pw, \
             mock.patch.object(dl.v, 'memory_preflight') as classic, \
             mock.patch('sys.stdout'):
            self.assertEqual(dl.run_dailies(0, '1', '0x7964E0000000'), 2)
        pw.assert_called_once_with('1', '0x7964E0000000')
        classic.assert_not_called()


def _load_daily_gift():
    spec = importlib.util.spec_from_file_location(
        'afk_daily_gift', Path(__file__).resolve().parents[1] / 'afk-daily-gift.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TRollout(unittest.TestCase):
    """T81: every bot runtime power read goes through afk_memory.power."""
    ARGS = ['--pid', PID, '--base', BASE]

    def assert_wired(self, main, extra_patches=()):
        with contextlib.ExitStack() as stack:
            pw = stack.enter_context(mock.patch.object(am, 'power', return_value=('fail', None)))
            classic = stack.enter_context(mock.patch.object(v, 'memory_preflight'))
            stack.enter_context(mock.patch.object(v, 'prune_shot_dirs', return_value=0))
            stack.enter_context(mock.patch.object(sys, 'argv', ['x'] + self.ARGS))
            stack.enter_context(mock.patch('sys.stdout'))
            for p in extra_patches:
                stack.enter_context(p)
            self.assertEqual(main(), 2)   # 'fail' branch unchanged: ERROR + exit 2
        pw.assert_called_once_with(PID, BASE)
        classic.assert_not_called()

    def lock_patches(self, mod):
        return [mock.patch.object(mod._bot_lock, 'acquire', return_value=True),
                mock.patch.object(mod._bot_lock, 'release_at_exit')]

    def test_consumers_call_afk_memory_power(self):
        import afk_dream_realm as dr
        import afk_stage_push as sp
        for name, main, extra in (
                ('afk_claim_vision', v.main, ()),
                ('afk-daily-gift', _load_daily_gift().main, ()),
                ('afk_dream_realm', dr.main, self.lock_patches(dr)),
                ('afk_stage_push', sp.main, self.lock_patches(sp))):
            with self.subTest(name):
                self.assert_wired(main, extra)

    def test_no_script_reads_power_offsets_directly(self):
        """grep-assert: only the guard definition + afk_memory touch the raw readers."""
        pat = re.compile(r'\b(memory_preflight|read_power|read_power_entry_valid|'
                         r'revalidate_power_offset|adb_exec_dump)\(')
        # direct spectre value reads (subcommand literal on a line naming the binary)
        spectre_read = re.compile(r'''['"](dump|read|read-batch)['"]''')
        allowed = {'afk_memory.py', 'afk_claim_vision.py'}
        # wallet-hunt-all.py: research whole-region heap dump hunt, not a runtime value reader
        allowed_spectre = allowed | {'wallet-hunt-all.py'}
        hits = [f'{f.name}:{n}' for f in sorted(Path(__file__).resolve().parents[1].glob('*.py'))
                for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1)
                if (f.name not in allowed and pat.search(line))
                or (f.name not in allowed_spectre and 'spectre' in line.lower()
                    and spectre_read.search(line))]
        self.assertEqual(hits, [], 'use afk_memory.power instead of the raw readers')


if __name__ == '__main__':
    unittest.main()
