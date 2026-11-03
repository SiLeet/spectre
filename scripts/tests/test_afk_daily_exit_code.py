"""Integration tests for afk-bot-watch.sh scheduled Daily phase handling."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOCK_KEEPER = '( while [ -e "$LOCK" ]; do sleep 240; touch "$LOCK" 2>/dev/null || true; done ) &'


def bash_path(path: Path | str) -> str:
    value = str(path)
    if os.name == "nt":
        return subprocess.check_output(["cygpath", "-u", value], text=True).strip()
    return value


class DailyWrapperExitCode(unittest.TestCase):
    def _run_wrapper(self, **fake_results: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        with tempfile.TemporaryDirectory(prefix="afk-daily-wrapper-") as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "examples").mkdir()
            (root / "examples" / "bot-config-afk-live.yaml").write_text(
                (REPO / "examples" / "bot-config-afk-live.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "target" / "release").mkdir(parents=True)
            (root / "bin").mkdir()
            wrapper_path = root / "scripts" / "afk-bot-watch.sh"
            wrapper = (REPO / "scripts" / "afk-bot-watch.sh").read_text(encoding="utf-8")
            if LOCK_KEEPER not in wrapper:
                raise AssertionError("lock keeper command changed; update this integration test")
            wrapper_path.write_text(wrapper.replace(LOCK_KEEPER, "( true ) &"), encoding="utf-8")
            wrapper_path.chmod(0o755)

            fake_spectre = root / "target" / "release" / "spectre.exe"
            fake_spectre.write_text(
                "#!/usr/bin/env bash\n"
                "case \"$1\" in\n"
                "  find) printf '4392 com.farlightgames.igame.gp\\n' ;;\n"
                "  regions) printf '%s\\n' '[{\"start\":\"0x724dd0000000\",\"end\":\"0x724de0000000\",\"perms\":\"rw-p\",\"path\":\"\"}]' ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            fake_spectre.chmod(0o755)

            fake_python = root / "bin" / "python"
            fake_python.write_text(
                """#!/usr/bin/env bash
if [ "${1:-}" = "-c" ]; then exit 0; fi
if [ "${1:-}" = "-" ]; then echo 0x724DD0000000; exit 0; fi
script="$1"
printf '%s\\n' "$script" >> "$FAKE_CALLS"
case "$script" in
  *afk_normalize.py) exit "${FAKE_NORMALIZE_RC:-0}" ;;
  *afk_arena.py) exit "${FAKE_ARENA_RC:-0}" ;;
  *afk_dream_realm.py) exit "${FAKE_DREAM_RC:-0}" ;;
  *afk_stage_push.py) exit "${FAKE_STAGE_RC:-0}" ;;
  *) exit 0 ;;
esac
""",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            env = os.environ.copy()
            original_path = env.get("PATH", "")
            if os.name == "nt":
                original_path = subprocess.check_output(
                    ["cygpath", "-p", "-u", original_path], text=True
                ).strip()
                env["REAL_PYTHON"] = bash_path(sys.executable)
            else:
                env["REAL_PYTHON"] = sys.executable
            env["PATH"] = f"{bash_path(root / 'bin')}:{original_path}"
            env["AFK_PYTHON"] = bash_path(fake_python)
            env["AFK_MIN_IDLE"] = "180"
            calls_file = root / "calls.txt"
            env["FAKE_CALLS"] = bash_path(calls_file)
            env.update(fake_results)

            result = subprocess.run(
                [shutil.which("bash") or "bash", bash_path(wrapper_path), "--scheduled"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            calls = calls_file.read_text(encoding="utf-8").splitlines() if calls_file.exists() else []
            return result, calls

    def test_normalizer_failure_aborts_gameplay_and_reaches_task_scheduler(self):
        result, calls = self._run_wrapper(FAKE_NORMALIZE_RC="1")

        self.assertEqual(
            result.returncode,
            1,
            f"failed normalizer should fail the scheduled task; output:\n{result.stdout}\n{result.stderr}",
        )
        self.assertTrue(any("afk_normalize.py" in call for call in calls), calls)
        self.assertFalse(any("afk_arena.py" in call for call in calls), calls)
        self.assertFalse(any("afk_dream_realm.py" in call for call in calls), calls)
        self.assertFalse(any("afk_stage_push.py" in call for call in calls), calls)

    def test_later_gameplay_failure_is_reported_while_remaining_phases_run(self):
        result, calls = self._run_wrapper(FAKE_ARENA_RC="7")

        self.assertEqual(
            result.returncode,
            7,
            f"failed gameplay phase should reach Task Scheduler; output:\n{result.stdout}\n{result.stderr}",
        )
        self.assertTrue(any("afk_dream_realm.py" in call for call in calls), calls)
        self.assertTrue(any("afk_stage_push.py" in call for call in calls), calls)


if __name__ == "__main__":
    unittest.main()
