from __future__ import annotations

import os
import subprocess
import sys
import unittest

from orchestration.lib.canonical import canonical_json_bytes


class FlightDemoTests(unittest.TestCase):
    def setUp(self) -> None:
        from mothership.flight_contracts import FlightError
        from mothership.flight_demo import run_flight_demo

        self.FlightError = FlightError
        self.run_flight_demo = run_flight_demo

    def test_packaged_safe_and_drift_records_project_their_evaluations(self) -> None:
        """Catches a projection that bypasses bundle evaluation or reports the wrong finding."""

        safe = self.run_flight_demo("safe")
        drift = self.run_flight_demo("drift")

        self.assertEqual("mothership.flight-demo.v1", safe["schema_version"])
        self.assertEqual("safe", safe["scenario"])
        self.assertEqual("COMPLETE", safe["verdict"])
        self.assertEqual(8, safe["verified_stages"])
        self.assertEqual([], safe["rule_ids"])
        self.assertEqual("mothership.flight-demo.v1", drift["schema_version"])
        self.assertEqual("drift", drift["scenario"])
        self.assertEqual("DRIFTED", drift["verdict"])
        self.assertEqual(8, drift["verified_stages"])
        self.assertEqual(["FLIGHT.DRIFT.ACTION_CLASS"], drift["rule_ids"])
        for result in (safe, drift):
            with self.subTest(scenario=result["scenario"]):
                self.assertEqual(8, result["required_stages"])
                self.assertIs(False, result["authority_effect"])
                self.assertIs(False, result["execution_effect"])
                self.assertEqual("supplied-records-only", result["claim"])

    def test_unknown_demo_name_is_a_closed_flight_error(self) -> None:
        """Catches accepting an unrecognized resource path or fallback scenario."""

        with self.assertRaises(self.FlightError) as raised:
            self.run_flight_demo("unknown")

        self.assertEqual("INVALID", raised.exception.verdict)
        self.assertEqual("FLIGHT.INVALID.DEMO", raised.exception.rule_id)

    def test_packaged_demo_bytes_do_not_depend_on_process_environment(self) -> None:
        """Catches ambient environment values leaking into the public demo projection."""

        script = (
            "from mothership.flight_demo import run_flight_demo\n"
            "from orchestration.lib.canonical import canonical_json_bytes\n"
            "import sys\n"
            "sys.stdout.buffer.write(canonical_json_bytes(run_flight_demo(sys.argv[1])))\n"
        )
        outputs: list[bytes] = []
        for environment in (
            {"LANG": "C", "LC_ALL": "C", "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            {"LANG": "ja_JP.UTF-8", "LC_ALL": "C", "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        ):
            for name in ("safe", "drift"):
                completed = subprocess.run(
                    [sys.executable, "-c", script, name],
                    cwd=os.getcwd(),
                    env=environment,
                    input=b"",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8", "replace"))
                outputs.append(completed.stdout)

        self.assertEqual(outputs[0], outputs[2])
        self.assertEqual(outputs[1], outputs[3])


if __name__ == "__main__":
    unittest.main()
