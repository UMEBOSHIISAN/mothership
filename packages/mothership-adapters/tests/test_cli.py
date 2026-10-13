"""Bounded evidence adapter CLI tests."""

from __future__ import annotations

import io
import json
import copy
import datetime
import os
import pathlib
import unittest
from unittest import mock

from test_evidence import EvidenceFixture

from mothership_adapters.cli import main as evidence_cli_main
from mothership_adapters.evidence import MAX_ENCODED_BYTES
from mothership.contracts import canonical_json_sha256
from mothership_github import public_observation


class AdapterEvidenceCLITests(EvidenceFixture):
    def _run_inspect_with_sidecar(
        self, bundle: dict[str, object], sidecar_path: pathlib.Path, *extra: str
    ) -> tuple[int, str, str]:
        raw = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode()
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = ["inspect", "--human", "--readback-evidence", str(sidecar_path), *extra]
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch(
            "sys.stderr", stderr
        ):
            try:
                code = evidence_cli_main(argv)
            except SystemExit as exc:
                code = int(exc.code)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_inspect_human_reads_one_bounded_regular_sidecar_file(self) -> None:
        bundle, sidecar = self._readback_artifacts()
        path = pathlib.Path(self.temp.name) / "readback.json"
        path.write_bytes(json.dumps(sidecar, separators=(",", ":")).encode())

        code, output, error = self._run_inspect_with_sidecar(bundle, path)

        self.assertEqual(0, code, error)
        self.assertEqual("", error)
        self.assertIn("readback evidence hash binding: match (structural)", output)
        self.assertIn("readback reason (caller-reported): unmerged_pr", output)
        self.assertIn(
            "next read-only check: inspect retained state/merged/merged_at; no automatic retry/re-execution/reconsume",
            output,
        )
        self.assertNotIn("structured reason: unavailable in bundle", output)
        self.assertNotIn(
            "compare the referenced evidence's canonical hash with verification.evidence_refs",
            output,
        )

    def test_readback_evidence_requires_human_before_consuming_stdin(self) -> None:
        bundle, sidecar = self._readback_artifacts()
        path = pathlib.Path(self.temp.name) / "readback.json"
        path.write_bytes(json.dumps(sidecar, separators=(",", ":")).encode())
        raw = json.dumps(bundle, separators=(",", ":")).encode()

        class ExplodingBuffer(io.BytesIO):
            def read(self, *_args, **_kwargs):
                raise AssertionError("stdin must not be consumed")

        stdin = io.TextIOWrapper(ExplodingBuffer(raw), encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch(
            "sys.stderr", stderr
        ):
            try:
                code = evidence_cli_main(
                    ["inspect", "--readback-evidence", str(path)]
                )
            except SystemExit as exc:
                code = int(exc.code)

        self.assertEqual(2, code)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual("invalid bounded evidence input\n", stderr.getvalue())

    def test_readback_evidence_rejects_duplicate_option_before_file_access(self) -> None:
        bundle, sidecar = self._readback_artifacts()
        path = pathlib.Path(self.temp.name) / "readback.json"
        path.write_bytes(json.dumps(sidecar, separators=(",", ":")).encode())
        raw = json.dumps(bundle, separators=(",", ":")).encode()
        source = io.BytesIO(raw)
        stdin = io.TextIOWrapper(source, encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch(
            "sys.stderr", stderr
        ), mock.patch("os.open", side_effect=AssertionError("sidecar must not open")):
            try:
                code = evidence_cli_main(
                    [
                        "inspect",
                        "--human",
                        "--readback-evidence",
                        str(path),
                        "--readback-evidence",
                        str(path),
                    ]
                )
            except SystemExit as exc:
                code = int(exc.code)

        self.assertEqual(2, code)
        self.assertEqual(0, source.tell())
        self.assertEqual("", stdout.getvalue())
        self.assertEqual("invalid bounded evidence input\n", stderr.getvalue())

    def test_readback_evidence_rejects_symlink_fifo_and_oversized_files_without_blocking(
        self,
    ) -> None:
        bundle, sidecar = self._readback_artifacts()
        target = pathlib.Path(self.temp.name) / "target.json"
        target.write_bytes(json.dumps(sidecar, separators=(",", ":")).encode())
        symlink = pathlib.Path(self.temp.name) / "sidecar-link.json"
        os.symlink(target, symlink)
        fifo = pathlib.Path(self.temp.name) / "sidecar.pipe"
        os.mkfifo(fifo)
        directory = pathlib.Path(self.temp.name) / "sidecar-dir"
        directory.mkdir()
        oversized = pathlib.Path(self.temp.name) / "sidecar-big.json"
        oversized.write_bytes(b"{" + b"x" * (MAX_ENCODED_BYTES + 1))

        for path in (symlink, fifo, directory, pathlib.Path(os.devnull), oversized):
            with self.subTest(path=path.name):
                code, output, error = self._run_inspect_with_sidecar(bundle, path)
                self.assertEqual(2, code)
                self.assertEqual("", output)
                self.assertEqual("invalid bounded evidence input\n", error)

    def test_readback_evidence_rejects_duplicate_and_nonfinite_sidecar(self) -> None:
        bundle, _sidecar = self._readback_artifacts()
        malformed = {
            "duplicate": b'{"version":"github-merge-readback.v0","version":"github-merge-readback.v0"}',
            "nonfinite": b"{\"version\":NaN}",
        }
        for name, raw in malformed.items():
            with self.subTest(name=name):
                path = pathlib.Path(self.temp.name) / (name + ".json")
                path.write_bytes(raw)
                code, output, error = self._run_inspect_with_sidecar(bundle, path)
                self.assertEqual(2, code)
                self.assertEqual("", output)
                self.assertEqual("invalid bounded evidence input\n", error)

    def _run(self, argv: list[str], payload: object) -> tuple[int, str, str]:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch(
            "sys.stderr", stderr
        ):
            try:
                code = evidence_cli_main(argv)
            except SystemExit as exc:
                code = int(exc.code)
        return code, stdout.getvalue(), stderr.getvalue()

    def _readback_opener(self, bundle, *, kind="confirmed"):
        parameters = bundle["request"]["action"]["execution_parameters"]
        started = datetime.datetime.strptime(bundle["receipt"]["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
        merged_at = started + datetime.timedelta(seconds=1)
        repository = parameters["repository"]
        pr_url = f"https://api.github.com/repos/{repository}/pulls/{parameters['pull_request']}"
        pr = {
            "url": pr_url, "number": parameters["pull_request"], "title": "PRIVATE_REMOTE_PROSE",
            "state": "closed", "merged": True, "merged_at": merged_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "updated_at": merged_at.strftime("%Y-%m-%dT%H:%M:%SZ"), "draft": False,
            "head": {"sha": parameters["expected_head_sha"], "ref": "feature"},
            "base": {"ref": parameters["expected_base"], "repo": {"full_name": repository}},
            "merge_commit_sha": "c" * 40,
        }
        if kind == "unknown":
            pr.update(state="open", merged=False, merged_at=None, merge_commit_sha=None)
        if kind == "same_second":
            pr["merged_at"] = bundle["receipt"]["started_at"]
        if kind == "mismatch":
            pr["head"]["sha"] = "d" * 40
        commit = {"sha": "c" * 40, "parents": [{"sha": "f" * 40}, {"sha": parameters["expected_head_sha"]}]}
        payloads = [pr, commit]
        requests = []

        def opener(request, *, timeout):
            requests.append(request)
            self.assertEqual("GET", request.get_method())
            self.assertFalse(request.has_header("Authorization"))
            if kind == "network_failure":
                raise OSError("PRIVATE_EXCEPTION")
            self.assertLessEqual(len(requests), 2)
            result = io.BytesIO(json.dumps(payloads.pop(0)).encode())
            result.status = 200
            result.headers = {}
            result.geturl = lambda: request.full_url
            return result

        return opener, requests, merged_at + datetime.timedelta(seconds=10)

    def test_readback_then_offline_human_inspect_keeps_receipt_and_reason(self):
        # Catches a missing producer connection, wrong action/Receipt binding,
        # lost reason, overwritten source rows, or hidden inspection networking.
        bundle = self.full()
        original = copy.deepcopy(bundle)
        ledgers = (self.authority_path.read_bytes(), self.receipt_path.read_bytes())
        opener, requests, observed = self._readback_opener(bundle)
        with mock.patch.object(public_observation, "_default_open", opener), mock.patch(
            "mothership_github.verification._utc_now", return_value=observed
        ):
            code, output, error = self._run(["readback"], bundle)
        self.assertEqual(0, code, error)
        verified = json.loads(output)
        sidecar = json.loads(error)
        self.assertEqual("CONFIRMED", verified["verification"]["status"])
        self.assertEqual(bundle["receipt"], verified["receipt"])
        self.assertEqual([], verified["missing"])
        self.assertEqual("merge_confirmed", sidecar["reason"])
        self.assertEqual(canonical_json_sha256(sidecar), verified["verification"]["evidence_refs"][0]["sha256"])
        self.assertEqual(2, len(requests))
        self.assertEqual(original, bundle)
        self.assertEqual(ledgers, (self.authority_path.read_bytes(), self.receipt_path.read_bytes()))
        self.assertNotIn("PRIVATE_REMOTE_PROSE", output + error)
        with mock.patch.object(public_observation, "_default_open", side_effect=AssertionError("offline")):
            code, human, error = self._run(["inspect", "--human"], verified)
        self.assertEqual((0, ""), (code, error))
        self.assertIn("verification: CONFIRMED", human)
        self.assertIn("merge_confirmed", human)
        self.assertIn("source: source-unverified", human)
        self.assertIn("external effect verified: false", human)
        self.assertIn("no re-execution; no reconsume", human)

    def test_readback_unknown_mismatch_and_network_failure_are_not_success(self):
        for kind, status, reason, gets in (
            ("unknown", "UNKNOWN", "unmerged_pr", 1),
            ("same_second", "UNKNOWN", "ambiguous_merge_time", 1),
            ("mismatch", "MISMATCH", "head_or_base_mismatch", 1),
            ("network_failure", "UNKNOWN", "invalid_pr_observation", 1),
        ):
            with self.subTest(kind=kind):
                bundle = self.full()
                opener, requests, observed = self._readback_opener(bundle, kind=kind)
                with mock.patch.object(public_observation, "_default_open", opener), mock.patch(
                    "mothership_github.verification._utc_now", return_value=observed
                ):
                    code, output, error = self._run(["readback"], bundle)
                self.assertEqual(0, code, error)
                verified = json.loads(output)
                self.assertEqual("SUCCESS", verified["receipt"]["status"])
                self.assertEqual(status, verified["verification"]["status"])
                self.assertEqual(reason, json.loads(error)["reason"])
                self.assertEqual(gets, len(requests))
                code, human, error = self._run(["inspect", "--human"], verified)
                self.assertEqual((0, ""), (code, error))
                self.assertIn(reason, human)
                self.assertNotIn("PRIVATE_EXCEPTION", human)

    def test_readback_rejects_incomplete_foreign_and_existing_verification_before_network(self):
        changed = self.full()
        changed["receipt"]["action_id"] = "act-foreign"
        changed["bundle_sha256"] = canonical_json_sha256({key: value for key, value in changed.items() if key != "bundle_sha256"})
        cases = [
            {"invalid": True}, self.full(finished=None),
            self.full(response=None, decision=None, consume=None, started=None, finished=None), changed,
            self.full(verification=self.verification(status="UNKNOWN", summary="caller-reported unknown")),
        ]
        with mock.patch.object(public_observation, "_default_open", side_effect=AssertionError("must reject before GET")) as network:
            for bundle in cases:
                with self.subTest(bundle=bundle):
                    code, output, error = self._run(["readback"], bundle)
                    self.assertEqual(2, code)
                    self.assertEqual("", output)
                    self.assertEqual("invalid bounded evidence input\n", error)
            self.assertEqual(0, network.call_count)

    def test_readback_streams_once_and_output_failure_never_repeats_observation(self):
        class Writer(io.StringIO):
            def __init__(self, failure=None):
                super().__init__()
                self.failure, self.writes, self.flushes = failure, 0, 0

            def write(self, text):
                self.writes += 1
                if self.failure == "short":
                    super().write(text[:-1])
                    return len(text) - 1
                return super().write(text)

            def flush(self):
                self.flushes += 1
                if self.failure == "flush":
                    raise OSError("PRIVATE_SINK_FAILURE")
                super().flush()

        # A failed sidecar must prevent stdout entirely. A failed stdout must
        # return nonzero after just one sidecar; neither failure may replay GET.
        for sink, failure in ((None, None), ("stderr", "short"), ("stderr", "flush"), ("stdout", "short"), ("stdout", "flush")):
            with self.subTest(sink=sink, failure=failure):
                bundle = self.full()
                opener, requests, observed = self._readback_opener(bundle)
                stdout = Writer(failure if sink == "stdout" else None)
                stderr = Writer(failure if sink == "stderr" else None)
                stdin = io.TextIOWrapper(io.BytesIO(json.dumps(bundle).encode()), encoding="utf-8")
                with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr), mock.patch.object(
                    public_observation, "_default_open", opener
                ), mock.patch("mothership_github.verification._utc_now", return_value=observed):
                    try:
                        code = evidence_cli_main(["readback"])
                    except SystemExit as exc:
                        code = int(exc.code)
                self.assertEqual(0 if sink is None else 2, code)
                self.assertEqual(2, len(requests))
                self.assertEqual(0 if sink == "stderr" else 1, stdout.writes)
                self.assertEqual(2 if sink == "stdout" else 1, stderr.writes)
                self.assertEqual(0 if sink == "stderr" and failure == "short" else 1, stderr.flushes)
                self.assertNotIn("PRIVATE_SINK_FAILURE", stdout.getvalue() + stderr.getvalue())

    def test_export_envelope_and_inspect_summary(self) -> None:
        envelope = {
            "request": self.request,
            "export": {
                "response": self.response,
                "decision": self.decision,
                "consume": self.consume,
                "started": self.started,
                "finished": self.finished,
                "executor_ref": {"ref_id": "executor:synthetic", "sha256": "b" * 64},
            },
        }
        code, output, error = self._run(["export"], envelope)
        self.assertEqual(0, code)
        self.assertEqual("", error)
        bundle = json.loads(output)
        self.assertEqual("host-evidence-bundle.v0", bundle["schema_version"])

        code, output, error = self._run(["inspect"], bundle)
        self.assertEqual(0, code)
        self.assertEqual("", error)
        summary = json.loads(output)
        self.assertEqual("caller-attested", summary["provenance"])
        self.assertEqual("source-unverified", summary["source_status"])
        self.assertFalse(summary["authority"])
        self.assertFalse(summary["source_authenticated"])
        self.assertFalse(summary["external_effect_verified"])
        self.assertEqual("SUCCESS", summary["receipt_status"])

    def test_json_export_and_inspection_require_complete_output_without_retry(self) -> None:
        bundle = self.full()
        envelope = {
            "request": bundle["request"],
            "export": {key: bundle[key] for key in (
                "response", "decision", "consume", "started", "finished",
                "executor_ref", "verification",
            )},
        }

        class Writer(io.StringIO):
            def __init__(self, failure):
                super().__init__()
                self.failure, self.writes, self.flushes = failure, 0, 0

            def write(self, text):
                self.writes += 1
                if self.failure == "raise":
                    raise OSError("PRIVATE_OUTPUT_FAILURE")
                if self.failure == "short":
                    super().write(text[:-1])
                    return len(text) - 1
                super().write(text)
                if self.failure == "none":
                    return None
                if self.failure == "bool":
                    return True
                if self.failure == "overlong":
                    return len(text) + 1
                return len(text)

            def flush(self):
                self.flushes += 1
                if self.failure == "flush":
                    raise OSError("PRIVATE_OUTPUT_FAILURE")
                super().flush()

        for command, payload in (("inspect", bundle), ("export", envelope)):
            expected_code, expected_output, expected_error = self._run([command], payload)
            self.assertEqual((0, ""), (expected_code, expected_error))
            for failure in (None, "short", "none", "bool", "overlong", "raise", "flush"):
                with self.subTest(command=command, failure=failure):
                    stdout, stderr = Writer(failure), io.StringIO()
                    stdin = io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode()), encoding="utf-8")
                    with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr), mock.patch.object(
                        public_observation, "_default_open", side_effect=AssertionError("offline")
                    ) as network:
                        code = evidence_cli_main([command])
                    self.assertEqual(0 if failure is None else 2, code)
                    self.assertEqual(1, stdout.writes)
                    self.assertEqual(1 if failure in (None, "flush") else 0, stdout.flushes)
                    self.assertEqual(0, network.call_count)
                    self.assertEqual("" if failure is None else "invalid bounded evidence input\n", stderr.getvalue())
                    self.assertNotIn("PRIVATE_OUTPUT_FAILURE", stdout.getvalue() + stderr.getvalue())
                    if failure is None:
                        self.assertEqual(expected_output, stdout.getvalue())
                        self.assertEqual(json.loads(expected_output), json.loads(stdout.getvalue()))

    def test_unknown_envelope_field_and_oversized_input_fail_closed(self) -> None:
        envelope = {
            "request": self.request,
            "export": {"executor_ref": {"ref_id": "executor:synthetic", "sha256": "b" * 64}},
            "path": "/tmp/forbidden",
        }
        code, output, error = self._run(["export"], envelope)
        self.assertEqual(2, code)
        self.assertEqual("", output)
        self.assertEqual("invalid bounded evidence input\n", error)

        oversized = b"{" + b'\"x\":\"' + b"x" * MAX_ENCODED_BYTES + b'\"}'
        stdin = io.TextIOWrapper(io.BytesIO(oversized), encoding="utf-8")
        stderr = io.StringIO()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stderr", stderr):
            code = evidence_cli_main(["inspect"])
        self.assertEqual(2, code)
        self.assertEqual("invalid bounded evidence input\n", stderr.getvalue())

    def test_inspect_human_is_bounded_text_and_default_json_remains_json(self) -> None:
        bundle = self.full()
        code, output, error = self._run(["inspect", "--human"], bundle)
        self.assertEqual(0, code)
        self.assertEqual("", error)
        self.assertIn("approval: recorded", output)
        self.assertIn("receipt: SUCCESS", output)
        self.assertIn("verification: missing", output)
        self.assertIn("next read-only check:", output)
        self.assertIn("no re-execution", output)
        self.assertIn("no reconsume", output)
        self.assertIn(
            "target: action_id=act-evidence-test; operation=github.merge_pr; repository=UMEBOSHIISAN/mothership; pull_request=5",
            output,
        )
        self.assertNotIn('"schema_version"', output)

        code, output, error = self._run(["inspect"], bundle)
        self.assertEqual(0, code)
        self.assertEqual("", error)
        self.assertEqual("host-evidence-inspection.v0", json.loads(output)["schema_version"])

    def test_inspect_human_rejects_invalid_input_without_side_effects(self) -> None:
        code, output, error = self._run(["inspect", "--human"], {"invalid": True})
        self.assertEqual(2, code)
        self.assertEqual("", output)
        self.assertEqual("invalid bounded evidence input\n", error)

    def test_inspect_human_short_write_fails_without_retry(self) -> None:
        bundle = self.full()
        raw = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode()
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
        stderr = io.StringIO()

        class ShortWriter:
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.flush_calls = 0

            def write(self, text: str) -> int:
                self.calls.append(text)
                return len(text) - 1

            def flush(self) -> None:
                self.flush_calls += 1

        stdout = ShortWriter()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch(
            "sys.stderr", stderr
        ):
            code = evidence_cli_main(["inspect", "--human"])

        self.assertEqual(2, code)
        self.assertEqual(1, len(stdout.calls))
        self.assertEqual(0, stdout.flush_calls)
        self.assertEqual("invalid bounded evidence input\n", stderr.getvalue())

    def test_inspect_human_flush_failure_is_invalid_without_retry(self) -> None:
        bundle = self.full()
        raw = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode()
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
        stderr = io.StringIO()

        class FlushFailureWriter:
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.flush_calls = 0

            def write(self, text: str) -> int:
                self.calls.append(text)
                return len(text)

            def flush(self) -> None:
                self.flush_calls += 1
                raise OSError("flush failed")

        stdout = FlushFailureWriter()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch(
            "sys.stderr", stderr
        ):
            code = evidence_cli_main(["inspect", "--human"])

        self.assertEqual(2, code)
        self.assertEqual(1, len(stdout.calls))
        self.assertEqual(1, stdout.flush_calls)
        self.assertEqual("invalid bounded evidence input\n", stderr.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
