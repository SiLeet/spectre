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


class TGold(Base):
    """T116: homestead gold = u32 (+ identical u64) at gold-region base + 0x7518C8."""
    GBASE = '0x7607b0000000'

    def setUp(self):
        super().setUp()
        self.gstate = ART / 'gold-state-afk-memory.json'
        self.gstate.unlink(missing_ok=True)
        p = mock.patch.object(am, 'GOLD_STATE', self.gstate)
        p.start()
        self.addCleanup(p.stop)
        am._gold_cache.clear()

    def test_happy_path(self):
        with self.fake_run(batch_rows(lo=654398, hi=0, ptr=0x0002_e6bd_4403)):
            self.assertEqual(am.gold(PID, self.GBASE), ('ok', 654398))
        self.assertEqual(len(self.calls), 1)          # u32 + u64 views from ONE read-batch
        cmd = self.calls[0]
        self.assertEqual(cmd[cmd.index('--base') + 1], self.GBASE)
        self.assertTrue(cmd[cmd.index('--offsets') + 1].endswith('afk_memory_slot_7518c8.yaml'))

    def test_out_of_range_or_broken_mirror_is_invalid(self):
        for lo, hi in ((1_500_000_000, 0),        # > GOLD_MAX
                       (0xFFFF_FFF0, 0),          # >= 2**31: signed u32 view != u64 view
                       (654398, 1)):              # u64 != u32: not the verified slot shape
            with self.subTest(lo=lo, hi=hi), self.fake_run(batch_rows(lo=lo, hi=hi)):
                am._snap_cache.clear()
                self.assertEqual(am.gold(PID, self.GBASE), ('invalid', None))
        self.assertEqual(am._gold_cache, {})

    def test_cache_within_ttl_then_expires(self):
        with self.fake_run(batch_rows(lo=654398)):
            with mock.patch.object(am.time, 'monotonic', return_value=200.0):
                a = am.gold(PID, self.GBASE)
                b = am.gold(PID, self.GBASE)
            self.assertEqual(len(self.calls), 1)      # second call: cache hit
            with mock.patch.object(am.time, 'monotonic', return_value=201.6):
                am.gold(PID, self.GBASE)
        self.assertEqual(a, b)
        self.assertEqual(len(self.calls), 2)

    def test_fail_not_cached_and_state_offset_used(self):
        self.gstate.write_text(json.dumps({'offset': 0x100}))
        with self.fake_run(rc=2):
            self.assertEqual(am.gold(PID, self.GBASE), ('fail', None))
        self.assertEqual(am._gold_cache, {})
        self.assertTrue(self.calls[0][self.calls[0].index('--offsets') + 1]
                        .endswith('afk_memory_slot_100.yaml'))

    def test_show_prints_gold(self):
        out = []
        with self.fake_run(batch_rows(lo=654398)),              mock.patch.object(am, 'power', return_value=('ok', 259850)),              mock.patch('builtins.print', side_effect=lambda *a, **k: out.append(' '.join(map(str, a)))):
            am.main(['--show', '--pid', PID, '--base', BASE, '--gold-base', self.GBASE])
        self.assertIn('gold: ok 654398', out)
        out.clear()
        with self.fake_run(batch_rows(lo=654398)),              mock.patch.object(am, 'power', return_value=('ok', 259850)),              mock.patch('builtins.print', side_effect=lambda *a, **k: out.append(' '.join(map(str, a)))):
            am.main(['--show', '--pid', PID, '--base', BASE])   # no state, no --gold-base
        self.assertTrue(any(l.startswith('gold: n/a') for l in out), out)

    def test_show_takes_base_from_state_only_for_same_pid(self):
        for pid, want in ((PID, 'gold: ok 654398'), ('999', 'gold: n/a')):
            self.gstate.write_text(json.dumps({'offset': '0x7518C8', 'base': self.GBASE, 'pid': pid}))
            am._snap_cache.clear()
            am._gold_cache.clear()
            out = []
            with self.subTest(pid=pid), self.fake_run(batch_rows(lo=654398)),                  mock.patch.object(am, 'power', return_value=('ok', 259850)),                  mock.patch('builtins.print', side_effect=lambda *a, **k: out.append(' '.join(map(str, a)))):
                am.main(['--show', '--pid', PID, '--base', BASE])
                self.assertTrue(any(l.startswith(want) for l in out), out)

    def test_bundled_yaml_entry(self):
        text = (Path(__file__).resolve().parents[2] / 'games' / 'afk-journey' / 'offsets.yaml').read_text(encoding='utf-8')
        self.assertIn(f'offset: {am.DEFAULT_GOLD_OFFSET:#X}'.replace('0X', '0x'), text)


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
