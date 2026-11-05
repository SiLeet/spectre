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
    def _run_wrapper(
        self, runs: int = 1, args: tuple[str, ...] = ("--scheduled",), idle: list[int] | None = None,
        **fake_results: str,
    ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
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
if [ "${1:-}" = "-c" ]; then
  case "${2:-}" in *idle_seconds*)
    if [ -n "${FAKE_IDLE:-}" ] && [ -s "$FAKE_IDLE" ]; then
      head -n1 "$FAKE_IDLE"
      [ "$(wc -l < "$FAKE_IDLE")" -gt 1 ] && sed -i 1d "$FAKE_IDLE"   # last value sticks
    fi ;;
  esac
  exit 0
fi
if [ "${1:-}" = "-" ]; then echo 0x724DD0000000; exit 0; fi
script="$1"
printf '%s\\n' "$*" >> "$FAKE_CALLS"
case "$script" in
  *afk_normalize.py) exit "${FAKE_NORMALIZE_RC:-0}" ;;
  *afk_hero_level.py) exit "${FAKE_LEVEL_RC:-0}" ;;
  *afk_arena.py) exit "${FAKE_ARENA_RC:-0}" ;;
  *afk_dream_realm.py) exit "${FAKE_DREAM_RC:-0}" ;;
  *afk_stage_push.py) exit "${FAKE_STAGE_RC:-0}" ;;
  *afk_duras.py) exit "${FAKE_DURAS_RC:-0}" ;;
  *afk_homestead.py) exit "${FAKE_HOMESTEAD_RC:-0}" ;;
  *afk_homestead_upgrade.py) exit "${FAKE_UPGRADE_RC:-0}" ;;
  *afk_homestead_requests.py) exit "${FAKE_REQUESTS_RC:-0}" ;;
  *afk_guild.py) exit "${FAKE_GUILD_RC:-0}" ;;
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
            if idle is not None:   # T107: idle probe values (one per poll, last sticks) + fake sleep
                # LF only: a CR would make the probe value non-numeric ("unknown idle")
                (root / "idle.txt").write_text("".join(f"{i}\n" for i in idle), encoding="utf-8", newline="\n")
                env["FAKE_IDLE"] = bash_path(root / "idle.txt")
                fake_sleep = root / "bin" / "sleep"
                fake_sleep.write_text(
                    '#!/usr/bin/env bash\nprintf \'sleep %s\\n\' "$*" >> "$FAKE_CALLS"\n'
                    '[ -e .spectre/afk-bot.lock ] && echo LOCKED-DURING-WAIT >> "$FAKE_CALLS"\nexit 0\n',
                    encoding="utf-8"
                )
                fake_sleep.chmod(0o755)
            env.update(fake_results)

            for _ in range(runs):        # same temp root = same .spectre markers / same day
                result = subprocess.run(
                    [shutil.which("bash") or "bash", bash_path(wrapper_path), *args],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=90,   # T106 review: +1 phase, 30 s flaked under load
                )
            calls = calls_file.read_text(encoding="utf-8").splitlines() if calls_file.exists() else []
            self.markers = sorted(p.name for p in (root / ".spectre").glob("*-last.txt"))
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

    # --- T67 daily leveling (soft phase between dream realm and stage push) ---
    def _index(self, calls, needle):
        return next(i for i, call in enumerate(calls) if needle in call)

    def test_leveling_runs_once_with_level_flag_before_stage_push(self):
        result, calls = self._run_wrapper()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        level = [c for c in calls if "afk_hero_level.py" in c]
        self.assertEqual(len(level), 1, calls)
        self.assertIn("--level", level[0])
        self.assertLess(self._index(calls, "afk_dream_realm.py"), self._index(calls, "afk_hero_level.py"))
        self.assertLess(self._index(calls, "afk_hero_level.py"), self._index(calls, "afk_stage_push.py"))
        self.assertIn("level-last.txt", self.markers)

    def test_leveling_once_per_day_over_two_runs(self):
        # T70 (review gap): the level-last.txt gate across runs on the same day
        result, calls = self._run_wrapper(runs=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sum("afk_hero_level.py" in c for c in calls), 1, calls)
        self.assertEqual(sum("afk_claim_vision.py" in c for c in calls), 2, calls)   # both runs ran

    def test_resources_out_marks_the_day(self):
        result, calls = self._run_wrapper(FAKE_LEVEL_RC="4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("level-last.txt", self.markers)

    def test_leveling_failure_is_soft(self):
        result, calls = self._run_wrapper(FAKE_LEVEL_RC="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(any("afk_stage_push.py" in call for call in calls), calls)
        self.assertNotIn("level-last.txt", self.markers)
        self.assertIn("hero leveling rc=1 (soft phase", result.stdout)

    def test_leveling_switch_off(self):
        result, calls = self._run_wrapper(AFK_DAILY_LEVEL="0")
        self.assertFalse(any("afk_hero_level.py" in call for call in calls), calls)

    # --- T84 Dura's Trials (soft daily phase after the claims, before stage push) ---
    def test_duras_runs_once_after_claims_before_stage_push(self):
        result, calls = self._run_wrapper()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        duras = [c for c in calls if "afk_duras.py" in c]
        self.assertEqual(duras, ["scripts/afk_duras.py --min-idle 180"], calls)
        i = self._index(calls, "afk_duras.py")
        for claim in ("afk_claim_vision.py", "afk-daily-gift.py", "afk_dailies.py", "afk_hero_level.py"):
            self.assertLess(self._index(calls, claim), i, calls)
        self.assertIn("afk_normalize.py", calls[i - 1])               # screen normalized before
        self.assertLess(i, self._index(calls, "afk_stage_push.py"))
        self.assertIn("duras-last.txt", self.markers)

    def test_duras_once_per_day_over_two_runs(self):
        result, calls = self._run_wrapper(runs=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sum("afk_duras.py" in c for c in calls), 1, calls)
        self.assertEqual(sum("afk_claim_vision.py" in c for c in calls), 2, calls)   # both runs ran

    def test_duras_not_cleared_marks_the_day(self):
        result, calls = self._run_wrapper(FAKE_DURAS_RC="4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("duras-last.txt", self.markers)

    def test_duras_failure_is_soft(self):
        for rc in ("1", "5"):
            with self.subTest(rc=rc):
                result, calls = self._run_wrapper(runs=2, FAKE_DURAS_RC=rc)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(any("afk_stage_push.py" in call for call in calls), calls)
                self.assertNotIn("duras-last.txt", self.markers)
                self.assertIn(f"dura's trials rc={rc} (soft phase", result.stdout)
                # no marker -> the next run on the same day tries again
                self.assertEqual(sum("afk_duras.py" in c for c in calls), 2, calls)

    def test_duras_switch_off(self):
        result, calls = self._run_wrapper(AFK_DURAS="0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any("afk_duras.py" in call for call in calls), calls)
        self.assertTrue(any("afk_stage_push.py" in call for call in calls), calls)
        self.assertNotIn("duras-last.txt", self.markers)

    # --- T102 homestead build (soft daily phase after dura's, before stage push) ---
    def test_homestead_runs_once_after_duras_before_stage_push(self):
        result, calls = self._run_wrapper(runs=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        hs = [c for c in calls if "afk_homestead.py" in c]
        self.assertEqual(hs, ["scripts/afk_homestead.py --min-idle 180"], calls)
        i = self._index(calls, "afk_homestead.py")
        self.assertLess(self._index(calls, "afk_duras.py"), i, calls)
        self.assertIn("afk_normalize.py", calls[i - 1])
        self.assertLess(i, self._index(calls, "afk_stage_push.py"))
        self.assertIn("homestead-last.txt", self.markers)

    def test_homestead_nothing_to_do_marks_the_day(self):
        result, calls = self._run_wrapper(FAKE_HOMESTEAD_RC="4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("homestead-last.txt", self.markers)

    def test_homestead_failure_is_soft(self):
        result, calls = self._run_wrapper(runs=2, FAKE_HOMESTEAD_RC="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(any("afk_stage_push.py" in call for call in calls), calls)
        self.assertNotIn("homestead-last.txt", self.markers)
        self.assertIn("homestead build rc=1 (soft phase", result.stdout)
        self.assertEqual(sum("afk_homestead.py" in c for c in calls), 2, calls)

    def test_homestead_switch_off(self):
        result, calls = self._run_wrapper(AFK_HOMESTEAD="0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any("afk_homestead.py" in call for call in calls), calls)
        self.assertNotIn("homestead-last.txt", self.markers)

    # --- T103 homestead upgrade (soft daily phase right after the homestead build) ---
    def test_upgrade_runs_once_after_homestead_build(self):
        result, calls = self._run_wrapper(runs=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        hu = [c for c in calls if "afk_homestead_upgrade.py" in c]
        self.assertEqual(hu, ["scripts/afk_homestead_upgrade.py --min-idle 180"], calls)
        i = self._index(calls, "afk_homestead_upgrade.py")
        self.assertLess(self._index(calls, "afk_homestead.py"), i, calls)
        self.assertIn("afk_normalize.py", calls[i - 1])
        self.assertLess(i, self._index(calls, "afk_stage_push.py"))
        self.assertIn("homestead-upgrade-last.txt", self.markers)

    def test_upgrade_nothing_to_do_marks_the_day(self):
        result, calls = self._run_wrapper(FAKE_UPGRADE_RC="4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("homestead-upgrade-last.txt", self.markers)

    def test_upgrade_failure_is_soft(self):
        result, calls = self._run_wrapper(runs=2, FAKE_UPGRADE_RC="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(any("afk_stage_push.py" in call for call in calls), calls)
        self.assertNotIn("homestead-upgrade-last.txt", self.markers)
        self.assertIn("homestead upgrade rc=1 (soft phase", result.stdout)
        self.assertEqual(sum("afk_homestead_upgrade.py" in c for c in calls), 2, calls)

    def test_upgrade_switch_off(self):
        result, calls = self._run_wrapper(AFK_HOMESTEAD_UPGRADE="0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any("afk_homestead_upgrade.py" in call for call in calls), calls)
        self.assertTrue(any("afk_homestead.py" in call for call in calls), calls)

    # --- T104 homestead requests (soft daily phase right after the homestead upgrade) ---
    def test_requests_run_once_after_homestead_upgrade(self):
        result, calls = self._run_wrapper(runs=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rq = [c for c in calls if "afk_homestead_requests.py" in c]
        self.assertEqual(rq, ["scripts/afk_homestead_requests.py --min-idle 180"], calls)
        i = self._index(calls, "afk_homestead_requests.py")
        self.assertLess(self._index(calls, "afk_homestead_upgrade.py"), i, calls)
        self.assertIn("afk_normalize.py", calls[i - 1])
        self.assertLess(i, self._index(calls, "afk_stage_push.py"))
        self.assertIn("homestead-requests-last.txt", self.markers)

    def test_requests_nothing_to_do_marks_the_day(self):
        result, calls = self._run_wrapper(FAKE_REQUESTS_RC="4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("homestead-requests-last.txt", self.markers)

    def test_requests_failure_is_soft(self):
        result, calls = self._run_wrapper(runs=2, FAKE_REQUESTS_RC="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(any("afk_stage_push.py" in call for call in calls), calls)
        self.assertNotIn("homestead-requests-last.txt", self.markers)
        self.assertIn("homestead requests rc=1 (soft phase", result.stdout)
        self.assertEqual(sum("afk_homestead_requests.py" in c for c in calls), 2, calls)

    def test_requests_switch_off(self):
        result, calls = self._run_wrapper(AFK_HOMESTEAD_REQUESTS="0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any("afk_homestead_requests.py" in call for call in calls), calls)
        self.assertTrue(any("afk_homestead_upgrade.py" in call for call in calls), calls)


    # --- T106 guild daily (soft log-only phase right after the homestead requests) ---
    def test_guild_runs_once_after_homestead_requests(self):
        result, calls = self._run_wrapper(runs=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        gd = [c for c in calls if "afk_guild.py" in c]
        self.assertEqual(gd, ["scripts/afk_guild.py --min-idle 180"], calls)
        i = self._index(calls, "afk_guild.py")
        self.assertLess(self._index(calls, "afk_homestead_requests.py"), i, calls)
        self.assertIn("afk_normalize.py", calls[i - 1])
        self.assertLess(i, self._index(calls, "afk_stage_push.py"))
        self.assertIn("guild-last.txt", self.markers)

    def test_guild_nothing_to_do_marks_the_day(self):
        result, calls = self._run_wrapper(FAKE_GUILD_RC="4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("guild-last.txt", self.markers)

    def test_guild_failure_is_soft(self):
        result, calls = self._run_wrapper(runs=2, FAKE_GUILD_RC="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(any("afk_stage_push.py" in call for call in calls), calls)
        self.assertNotIn("guild-last.txt", self.markers)
        self.assertIn("guild rc=1 (soft phase", result.stdout)
        self.assertEqual(sum("afk_guild.py" in c for c in calls), 2, calls)

    def test_guild_switch_off(self):
        result, calls = self._run_wrapper(AFK_GUILD="0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any("afk_guild.py" in call for call in calls), calls)
        self.assertTrue(any("afk_homestead_requests.py" in call for call in calls), calls)


class ScheduledIdleWait(unittest.TestCase):
    """T107: scheduled runs wait for an idle window (fake idle probe + fake sleep, no real sleeping)."""

    _run_wrapper = DailyWrapperExitCode._run_wrapper   # reuse the harness without re-running its tests
    _index = DailyWrapperExitCode._index

    @staticmethod
    def _sleeps(calls):
        return [c for c in calls if c.startswith("sleep ")]

    def test_scheduled_waits_for_idle_then_runs(self):
        result, calls = self._run_wrapper(idle=[5, 100, 200], AFK_WAIT_POLL="90")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self._sleeps(calls), ["sleep 90", "sleep 90"], calls)
        last_sleep = max(i for i, c in enumerate(calls) if c.startswith("sleep "))
        self.assertGreater(self._index(calls, "afk_claim_vision.py"), last_sleep, calls)
        self.assertIn("idle window after 180s wait", result.stdout)
        self.assertNotIn("LOCKED-DURING-WAIT", calls)

    def test_no_idle_window_exits_5_without_any_phase(self):
        result, calls = self._run_wrapper(idle=[1], AFK_WAIT_TIMEOUT="180", AFK_WAIT_POLL="60")
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertEqual(len(self._sleeps(calls)), 3, calls)
        self.assertFalse(any(".py" in c for c in calls), calls)
        self.assertIn("no idle window", result.stderr)
        self.assertNotIn("LOCKED-DURING-WAIT", calls)

    def test_progress_mode_waits_too(self):
        result, calls = self._run_wrapper(args=("--scheduled-progress",), idle=[1, 500])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self._sleeps(calls)), 1, calls)
        self.assertTrue(any("afk_claim_vision.py" in c for c in calls), calls)
        push = [c for c in calls if "afk_stage_push.py" in c]
        self.assertEqual(len(push), 1, calls)
        self.assertIn("--min-idle 180", push[0])   # stage push re-checks idle per poll

    def test_manual_run_never_waits(self):
        result, calls = self._run_wrapper(args=(), idle=[1])
        self.assertEqual(self._sleeps(calls), [], calls)
        claim = [c for c in calls if "afk_claim_vision.py" in c]
        self.assertEqual(len(claim), 1, calls)
        self.assertIn("--min-idle 0", claim[0])

    def test_wait_timeout_flag_zero_skips_immediately(self):
        result, calls = self._run_wrapper(args=("--scheduled", "--wait-timeout", "0"), idle=[1])
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertEqual(self._sleeps(calls), [], calls)
        self.assertIn("no idle window", result.stderr)

    def test_invalid_poll_falls_back_to_60(self):
        result, calls = self._run_wrapper(idle=[1, 999], AFK_WAIT_POLL="0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self._sleeps(calls), ["sleep 60"], calls)

    def test_unknown_idle_does_not_wait(self):
        result, calls = self._run_wrapper(idle=[])   # empty probe output + recording fake sleep
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WARN idle time unavailable", result.stdout)
        self.assertEqual(self._sleeps(calls), [], calls)
    def test_leading_zero_poll_is_decimal(self):
        result, calls = self._run_wrapper(idle=[1, 999], AFK_WAIT_POLL="08")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self._sleeps(calls), ["sleep 8"], calls)

    def test_user_back_after_claims_stops_daily_gameplay(self):
        # 999 passes the wait, 1 = user back at the first normalize boundary (sticks)
        result, calls = self._run_wrapper(idle=[999, 1])
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertTrue(any("afk_claim_vision.py" in c for c in calls), calls)
        for ungated in ("afk_normalize.py", "afk_arena.py", "afk_hero_level.py", "afk_stage_push.py"):
            self.assertFalse(any(ungated in c for c in calls), (ungated, calls))
        self.assertIn("user is back", result.stderr)

    def _assert_usage_error(self, *args):
        result, calls = self._run_wrapper(args=args, idle=[1])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(calls, [], calls)
        self.assertIn("usage", result.stderr)

    def test_misplaced_wait_timeout_is_rejected_not_manual(self):
        self._assert_usage_error("--wait-timeout", "0", "--scheduled")

    def test_non_numeric_wait_timeout_is_rejected(self):
        self._assert_usage_error("--scheduled", "--wait-timeout", "0s")

    def test_unknown_argument_is_rejected(self):
        self._assert_usage_error("--schedueld")


if __name__ == "__main__":
    unittest.main()
