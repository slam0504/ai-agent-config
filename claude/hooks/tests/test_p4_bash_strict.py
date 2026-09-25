"""P4: RL_STRICT=1 must propagate the wrapped python script's real exit code;
without RL_STRICT the wrapper must still swallow failures and exit 0."""
import os
import shutil
import subprocess
import tempfile
import unittest

HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WRAPPERS = {
    "review-loop-stop.sh": "stop_enqueue.py",
    "review-loop-consume.sh": "consume_feedback.py",
    "review-loop-status.sh": "sessionstart_status.py",
}

STUB = "#!/usr/bin/env python3\nimport sys\nsys.exit(7)\n"


class TestWrapperStrictMode(unittest.TestCase):
    def _run_wrapper(self, wrapper_name, script_name, strict):
        with tempfile.TemporaryDirectory() as tmp:
            wrapper_path = os.path.join(tmp, wrapper_name)
            shutil.copy(os.path.join(HOOKS_DIR, wrapper_name), wrapper_path)
            with open(os.path.join(tmp, script_name), "w") as f:
                f.write(STUB)

            env = dict(os.environ)
            if strict:
                env["RL_STRICT"] = "1"
            else:
                env.pop("RL_STRICT", None)

            result = subprocess.run(
                ["bash", wrapper_path], capture_output=True, text=True, env=env,
            )
            return result.returncode

    def test_strict_mode_propagates_python_exit_code(self):
        for wrapper, script in WRAPPERS.items():
            with self.subTest(wrapper=wrapper):
                rc = self._run_wrapper(wrapper, script, strict=True)
                self.assertEqual(
                    rc, 7,
                    f"{wrapper} should propagate the python script's exit code under RL_STRICT=1",
                )

    def test_non_strict_mode_still_exits_zero(self):
        for wrapper, script in WRAPPERS.items():
            with self.subTest(wrapper=wrapper):
                rc = self._run_wrapper(wrapper, script, strict=False)
                self.assertEqual(
                    rc, 0,
                    f"{wrapper} should swallow failures and exit 0 when RL_STRICT is unset",
                )


if __name__ == "__main__":
    unittest.main()
