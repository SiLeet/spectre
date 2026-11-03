"""Integration test for afk-night.sh exit-code propagation through tee."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def bash_path(path: Path | str) -> str:
    value = str(path)
    if os.name == "nt":
        return subprocess.check_output(["cygpath", "-u", value], text=True).strip()
    return value


class NightWrapperExitCode(unittest.TestCase):
    def test_stage_push_failure_is_returned_to_task_launcher(self):
        scratch = Path("C:/Users/Sigi/AppData/Local/hermes/cache/scratch")
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="afk-night-wrapper-", dir=scratch) as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "target" / "release").mkdir(parents=True)
            (root / "bin").mkdir()
            wrapper_path = root / "scripts" / "afk-night.sh"
            wrapper = (REPO / "scripts" / "afk-night.sh").read_text(encoding="utf-8")
            lock_keeper = '( while [ -e "$LOCK" ]; do sleep 240; touch "$LOCK" 2>/dev/null || true; done ) &'
            self.assertIn(lock_keeper, wrapper)
            wrapper_path.write_text(wrapper.replace(lock_keeper, "( true ) &"), encoding="utf-8")
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
                "#!/usr/bin/env bash\\n"
                "if [[ \\\"${1:-}\\\" == \\\"-\\\" ]]; then printf '0x724DD0000000\\\\n'; exit 0; fi\\n"
                "exit \\\"${FAKE_PUSH_RC:-7}\\\"\\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            fake_python.write_text(
                """#!/usr/bin/env bash
if [ "${1:-}" = "-" ]; then
  echo 0x724DD0000000
  exit 0
fi
exit "${FAKE_PUSH_RC:-7}"
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
            env["FAKE_PUSH_RC"] = "7"

            result = subprocess.run(
                [shutil.which("bash") or "bash", bash_path(root / "scripts" / "afk-night.sh")],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(
            result.returncode,
            7,
            f"night wrapper should propagate stage-push rc=7; output:\n{result.stdout}\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
