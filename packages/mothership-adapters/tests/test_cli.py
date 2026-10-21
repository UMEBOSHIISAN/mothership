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


class SavedResultCLITests(EvidenceFixture):
    """Read existing consumer records; never synthesize authority for a reader."""

    def saved_rows(self, *, status="CONFIRMED"):
        state = {"pull_request": {
            "repository": "UMEBOSHIISAN/mothership", "number": 5,
            "state": "closed", "merged": True,
            "merged_at": self.finished["recorded_at"],
            "head_sha": self.request["action"]["execution_parameters"]["expected_head_sha"],
            "base_ref": "main", "merge_commit_sha": "c" * 40,
        }, "commit": {"sha": "c" * 40, "parents": ["d" * 40,
            self.request["action"]["execution_parameters"]["expected_head_sha"]]}}
        bundle, sidecar = self._readback_artifacts(
            status=status, reason="merge_confirmed" if status == "CONFIRMED" else "ambiguous_merge_time",
            state=state,
        )
        paths = {"authority": "/not-to-open/authority.jsonl", "attempts": "/not-to-open/attempts.jsonl"}
        return [
            {"event": "frozen_action", "action": copy.deepcopy(self.request["action"]),
             "action_sha256": self.request["action_sha256"], "expires_at": self.request["expires_at"]},
            {"event": "execution_result", "status": "success", "mutation_attempted": True,
             **self.finished["observation"], "paths": paths},
            {"event": "verification_result", "execution_status": "success", "status": status,
             "source_pair": {"started": copy.deepcopy(self.started), "finished": copy.deepcopy(self.finished)},
             "receipt": bundle["receipt"], "verification": bundle["verification"],
             "evidence": sidecar, "paths": copy.deepcopy(paths)},
        ]

    @staticmethod
    def encode_rows(rows):
        return b"".join((json.dumps(row, ensure_ascii=True) + "\n").encode() for row in rows)

    def run_saved(self, raw, *, human=True, output=None):
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
        stdout = io.StringIO() if output is None else output
        stderr = io.StringIO()
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
            try:
                code = evidence_cli_main(["inspect-result", *(["--human"] if human else [])])
            except SystemExit as error:
                code = int(error.code)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_saved_confirmed_records_separate_report_observation_and_missing_authority(self):
        raw = self.encode_rows(self.saved_rows())
        code, text, error = self.run_saved(raw)
        self.assertEqual(0, code, error)
        for expected in ("consumer execution report: success", "receipt: SUCCESS",
                         "verification: CONFIRMED", "approval: not supplied",
                         "authority use: not supplied", "source-unverified",
                         "external effect verified: false", "no re-execution; no reconsume"):
            self.assertIn(expected, text)
        self.assertNotIn("/not-to-open", text)
        self.assertIn("unlabelled execution summary", text)

    def test_public_saved_cases_keep_their_meanings_without_effects_or_changes(self):
        # Catch a reader which promotes an incomplete case, accepts a mixed
        # action, or starts using input paths/effects while reading public data.
        root = pathlib.Path(__file__).resolve().parents[3] / "examples" / "saved-results"
        self.assertTrue(root.is_dir(), "public handoff inputs are not retained")
        names = [f"case-{number:02d}.jsonl" for number in range(1, 7)]
        self.assertEqual(set(names), {path.name for path in root.glob("case-*.jsonl")})
        raw_cases = {name: (root / name).read_bytes() for name in names}
        ledgers_before = [path.read_bytes() for path in (self.authority_path, self.receipt_path)]
        expected = (
            ("success", "SUCCESS", "CONFIRMED"),
            ("success", None, None),
            ("success", "SUCCESS", "UNKNOWN"),
            (None, None, None),
            ("reconciliation_required", None, None),
        )
        with mock.patch("socket.socket", side_effect=AssertionError("network forbidden")), \
             mock.patch("orchestration.lib.action_authority.freeze_action", side_effect=AssertionError("issuance forbidden")), \
             mock.patch("orchestration.lib.action_authority_ledger.consume_action", side_effect=AssertionError("consume forbidden")), \
             mock.patch("mothership_github.executor.execute_action_merge_pr", side_effect=AssertionError("execution forbidden")):
            for name, statuses in zip(names, expected):
                with self.subTest(case=name):
                    code, text, error = self.run_saved(raw_cases[name])
                    self.assertEqual(0, code, error)
                    for field, status in zip(("consumer execution report", "receipt", "verification"), statuses):
                        self.assertIn(f"{field}: {status or 'not supplied'}", text)
                    self.assertIn("approval: not supplied", text)
                    self.assertIn("source-unverified", text)
                    self.assertIn("external effect verified: false", text)
                    self.assertIn("next read-only check:", text)
                    self.assertIn("no re-execution; no reconsume", text)
                    self.assertNotIn("/not-to-open", text)
                    code, projection, error = self.run_saved(raw_cases[name], human=False)
                    self.assertEqual(0, code, error)
                    view = json.loads(projection)
                    self.assertEqual(statuses, tuple(view[key] for key in
                        ("execution_status", "receipt_status", "verification_status")))
                    self.assertTrue({"review_request", "decision", "consume"} <= set(view["missing"]))
                    self.assertFalse(view["authority"])
            code, text, error = self.run_saved(raw_cases[names[-1]])
            self.assertEqual((2, ""), (code, text))
            self.assertEqual("invalid bounded evidence input\n", error)
            # A rejected case cannot contaminate the next incomplete reading.
            code, text, error = self.run_saved(raw_cases[names[3]])
            self.assertEqual(0, code, error)
            self.assertIn("outcome unknown", text)
            self.assertNotIn("verification: CONFIRMED", text)
        self.assertEqual(raw_cases, {name: (root / name).read_bytes() for name in names})
        self.assertEqual(ledgers_before,
                         [path.read_bytes() for path in (self.authority_path, self.receipt_path)])

    def test_real_consumer_saved_file_round_trip_is_offline_and_unchanged(self):
        from examples.reference_result_handoff import synthetic_saved_result

        with mock.patch("socket.socket", side_effect=AssertionError("network forbidden")):
            raw = synthetic_saved_result()
            before = bytes(raw)
            code, text, error = self.run_saved(raw)
        self.assertEqual(0, code, error)
        self.assertEqual(before, raw)
        self.assertIn("repository=example/repo; pull_request=7", text)
        self.assertIn("consumer execution report: success", text)
        self.assertIn("receipt: SUCCESS", text)
        self.assertIn("verification: UNKNOWN", text)
        self.assertIn("unmerged_pr", text)

    def test_failed_receipt_and_confirmed_observation_are_independent(self):
        from mothership_github.external_action import build_external_action_receipt

        rows = self.saved_rows()
        finished = rows[2]["source_pair"]["finished"]
        finished["outcome"] = "failure"
        finished["observation"] = {"http_status": 409, "merged": False, "merge_commit_sha": None}
        rows[1].update(status="failure", **finished["observation"])
        receipt = build_external_action_receipt(
            rows[2]["source_pair"]["started"], finished,
            expected_action_id=rows[0]["action"]["action_id"],
            expected_action_sha256=rows[0]["action_sha256"],
            expected_consume_event_id=self.consume["event_id"],
            executor_ref=rows[2]["receipt"]["executor_ref"],
        )
        rows[2].update(execution_status="failure", receipt=receipt)
        rows[2]["verification"]["receipt_ref"]["sha256"] = canonical_json_sha256(receipt)
        code, text, error = self.run_saved(self.encode_rows(rows))
        self.assertEqual(0, code, error)
        self.assertIn("consumer execution report: failure", text)
        self.assertIn("receipt: FAILED", text)
        self.assertIn("verification: CONFIRMED", text)
        self.assertNotIn("execution succeeded", text)

    def test_actual_missing_finish_save_remains_unknown_without_reading_ledger(self):
        from examples import reference_result_handoff as example

        root = pathlib.Path(self.temp.name).resolve() / "consumer"
        root.mkdir(mode=0o700)
        output = example._Terminal()
        with mock.patch("mothership_github.receipts.record_attempt_finished", side_effect=OSError("fixture finish save")), \
             mock.patch("socket.socket", side_effect=AssertionError("network forbidden")):
            code = example.reference.main(
                ["--repo", "example/repo", "--pr", "7", "--ledger-dir", str(root),
                 "--verify-result", "--save-result"],
                transport=example._SyntheticTransport(), input_stream=example._FixtureApproval(output),
                output_stream=output, readback_opener=example._synthetic_readback,
            )
        self.assertEqual(1, code)
        before = {p.name: p.read_bytes() for p in root.iterdir()}
        code, text, error = self.run_saved(before["result.jsonl"])
        self.assertEqual(0, code, error)
        self.assertIn("consumer execution report: reconciliation_required", text)
        self.assertIn("receipt: not supplied", text)
        self.assertIn("verification: not supplied", text)
        self.assertIn("outcome unknown", text)
        self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_old_record_dates_are_read_without_becoming_current_authority_or_truth(self):
        rows = self.saved_rows()
        rows[0]["expires_at"] = "2001-01-01T00:00:00Z"
        code, text, error = self.run_saved(self.encode_rows(rows))
        self.assertEqual(0, code, error)
        self.assertIn("do not establish successful process exit or record freshness", text)
        self.assertIn("authority: false", text)
        self.assertIn("not proof of this attempt's causation or current state", text)

    def test_closed_shapes_scalars_and_contradictory_facts_reject(self):
        corruptions = [
            lambda r: r[0].update(extra="private sentinel"),
            lambda r: r[0].update(expires_at="not-UTC"),
            lambda r: r[1].update(http_status=True),
            lambda r: r[1].update(merged=1),
            lambda r: r[1].update(status="success", merged=False),
            lambda r: r[1].update(status="failure"),
            lambda r: r[1].update(mutation_attempted="unknown"),
            lambda r: r[1]["paths"].update(other="not a supported field"),
            lambda r: r[2].update(reason="not supported with complete records"),
            lambda r: r[2].update(source_pair=None),
            lambda r: r[2].update(receipt=None),
            lambda r: r[2]["verification"].update(status="UNKNOWN"),
        ]
        for corrupt in corruptions:
            rows = self.saved_rows()
            corrupt(rows)
            code, text, error = self.run_saved(self.encode_rows(rows))
            self.assertEqual((2, ""), (code, text))
            self.assertEqual("invalid bounded evidence input\n", error)

    def test_clean_prefixes_leave_outcomes_unknown_and_do_not_invent_records(self):
        rows = self.saved_rows()
        for length in (0, 1, 2):
            with self.subTest(length=length):
                code, text, error = self.run_saved(self.encode_rows(rows[:length]))
                self.assertEqual(0, code, error)
                self.assertIn("verification: not supplied", text)
                self.assertIn("receipt: not supplied", text)
                self.assertIn("outcome unknown", text)
                self.assertNotIn("cancelled", text)
                self.assertNotIn("no operation occurred", text)
        code, text, error = self.run_saved(self.encode_rows(rows[:2]))
        self.assertIn("consumer execution report: success", text)
        self.assertIn("not a bound completion record", text)

    def test_receipt_unavailable_does_not_reconstruct_missing_finish_or_receipt(self):
        rows = self.saved_rows()
        rows[2].update(status="unavailable", reason="receipt_unavailable",
                       source_pair=None, receipt=None, verification=None, evidence=None)
        code, text, error = self.run_saved(self.encode_rows(rows))
        self.assertEqual(0, code, error)
        self.assertIn("receipt: not supplied", text)
        self.assertIn("receipt_unavailable", text)
        self.assertIn("existing authority and attempt records", text)
        self.assertIn("outcome unknown", text)

    def test_unknown_and_verification_unavailable_stay_unconfirmed(self):
        rows = self.saved_rows(status="UNKNOWN")
        code, text, error = self.run_saved(self.encode_rows(rows))
        self.assertEqual(0, code, error)
        self.assertIn("verification: UNKNOWN", text)
        self.assertIn("ambiguous_merge_time", text)
        rows[2].update(status="unavailable", reason="verification_unavailable", verification=None, evidence=None)
        code, text, error = self.run_saved(self.encode_rows(rows))
        self.assertEqual(0, code, error)
        self.assertIn("receipt: SUCCESS", text)
        self.assertIn("verification: not supplied", text)

    def test_invalid_or_torn_jsonl_has_no_operation_summary(self):
        rows = self.saved_rows()
        valid = self.encode_rows(rows)
        malformed = [valid[:-1], valid + b"garbage\n", valid + b"\n", b" \n", b"\xff\n",
                     valid + b"{}\n", self.encode_rows(rows[::-1]),
                     self.encode_rows([rows[0], rows[1], rows[1]]),
                     b'{"event":"frozen_action","event":"frozen_action"}\n',
                     b'{"event":"frozen_action","private":NaN}\n', b"x" * (MAX_ENCODED_BYTES + 1)]
        for raw in malformed:
            with self.subTest(raw=raw[:50]):
                code, text, error = self.run_saved(raw)
                self.assertEqual((2, ""), (code, text))
                self.assertEqual("invalid bounded evidence input\n", error)

    def test_hash_action_and_cross_record_tampering_reject_before_summary(self):
        for corrupt in ("digest", "action", "receipt", "sidecar", "state", "status", "paths", "pair", "observation"):
            rows = self.saved_rows()
            if corrupt == "digest": rows[0]["action_sha256"] = "0" * 64
            if corrupt == "action": rows[0]["action"]["action_id"] = "act-other-run"
            if corrupt == "receipt": rows[2]["receipt"]["action_id"] = "act-other-run"
            if corrupt == "sidecar": rows[2]["evidence"]["reason"] = "unmerged_pr"
            if corrupt == "state": rows[2]["evidence"]["state"]["commit"]["parents"] = []
            if corrupt == "status": rows[2]["execution_status"] = "failure"
            if corrupt == "paths": rows[2]["paths"]["attempts"] = "/other-run/attempts.jsonl"
            if corrupt == "pair": rows[2]["source_pair"]["started"]["action_id"] = "act-other-run"
            if corrupt == "observation": rows[1]["merge_commit_sha"] = "a" * 40
            with self.subTest(corrupt=corrupt):
                code, text, error = self.run_saved(self.encode_rows(rows))
                self.assertEqual((2, ""), (code, text))
                self.assertEqual("invalid bounded evidence input\n", error)

    def test_no_implicit_paths_authority_network_or_input_mutation(self):
        raw = self.encode_rows(self.saved_rows())
        paths = (self.authority_path, self.receipt_path)
        before = [p.read_bytes() for p in paths]
        real_open = os.open
        schema_root = pathlib.Path(__file__).resolve().parents[3] / "evidence" / "contracts"

        def resource_read_only(path, flags, *args, **kwargs):
            target = pathlib.Path(path).resolve()
            self.assertTrue(target.is_relative_to(schema_root), "only bundled schema reads are allowed")
            self.assertEqual(0, flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            return real_open(path, flags, *args, **kwargs)

        with mock.patch("socket.socket", side_effect=AssertionError("network forbidden")), \
             mock.patch("os.open", side_effect=resource_read_only), \
             mock.patch("orchestration.lib.action_authority.freeze_action", side_effect=AssertionError("issuance forbidden")), \
             mock.patch("orchestration.lib.action_authority_ledger.consume_action", side_effect=AssertionError("consume forbidden")), \
             mock.patch("mothership_github.executor.execute_action_merge_pr", side_effect=AssertionError("execution forbidden")):
            code, text, error = self.run_saved(raw)
        self.assertEqual(0, code, error)
        self.assertEqual(before, [p.read_bytes() for p in paths])
        self.assertIn("verification: CONFIRMED", text)

    def test_repeated_reordered_and_failed_outputs_do_not_leak_state(self):
        good = self.encode_rows(self.saved_rows())
        partial = self.encode_rows(self.saved_rows()[:1])
        first = self.run_saved(good)
        self.run_saved(b"broken\n")
        expected_partial = self.run_saved(partial)

        class BrokenWriter(io.StringIO):
            def write(self, text):
                return super().write(text[:5])

        self.assertEqual(2, self.run_saved(good, output=BrokenWriter())[0])
        self.assertEqual(first, self.run_saved(good))
        self.assertEqual(expected_partial, self.run_saved(partial))
        self.assertNotIn("CONFIRMED", expected_partial[1])
        code, text, error = self.run_saved(good, human=False)
        self.assertEqual(0, code, error)
        view = json.loads(text)
        self.assertFalse(view["authority"])
        self.assertFalse(view["external_effect_verified"])
        self.assertNotIn("request", view)


class AdapterEvidenceCLITests(EvidenceFixture):
    def test_output_failure_does_not_leak_a_success_into_the_next_inspection(self) -> None:
        complete = self.full()
        incomplete = self.full(finished=None)
        before_files = (self.authority_path.read_bytes(), self.receipt_path.read_bytes())

        class FailingWriter(io.StringIO):
            def __init__(self, failure):
                super().__init__()
                self.failure = failure

            def write(self, text):
                if self.failure == "write":
                    super().write(text[:8])
                    raise OSError("PRIVATE_SYNTHETIC_SAVE_FAILURE")
                if self.failure == "short":
                    return super().write(text[:-1])
                return super().write(text)

            def flush(self):
                if self.failure == "flush":
                    raise OSError("PRIVATE_SYNTHETIC_SAVE_FAILURE")
                super().flush()

        for argv in (["inspect"], ["inspect", "--human"]):
            for failure in ("write", "short", "flush"):
                with self.subTest(argv=argv, failure=failure):
                    stdin = io.TextIOWrapper(io.BytesIO(json.dumps(complete).encode()), encoding="utf-8")
                    stdout, stderr = FailingWriter(failure), io.StringIO()
                    with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                        self.assertEqual(2, evidence_cli_main(argv))
                    self.assertNotIn("PRIVATE_SYNTHETIC_SAVE_FAILURE", stdout.getvalue() + stderr.getvalue())
                    code, output, error = self._run(argv, incomplete)
                    self.assertEqual((0, ""), (code, error))
                    if "--human" in argv:
                        self.assertIn("receipt: missing", output)
                        self.assertIn("verification: missing", output)
                    else:
                        result = json.loads(output)
                        self.assertIsNone(result["receipt_status"])
                        self.assertIsNone(result["verification_status"])
                        self.assertEqual(["finished", "verification"], result["missing"])
                        self.assertIs(False, result["external_effect_verified"])
        self.assertEqual(before_files, (self.authority_path.read_bytes(), self.receipt_path.read_bytes()))

    def test_missing_original_sidecar_is_not_replaced_by_a_previous_trial(self) -> None:
        bundle, sidecar = self._readback_artifacts()
        root = pathlib.Path(self.temp.name)
        path = root / "readback.json"
        path.write_bytes(json.dumps(sidecar).encode())
        before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(0, self._run_inspect_with_sidecar(bundle, path)[0])
        code, output, error = self._run_inspect_with_sidecar(bundle, root / "absent.json")
        self.assertEqual(2, code)
        self.assertEqual("", output)
        self.assertEqual("invalid bounded evidence input\n", error)
        code, output, error = self._run(["inspect"], bundle)
        self.assertEqual((0, ""), (code, error))
        result = json.loads(output)
        self.assertEqual("UNKNOWN", result["verification_status"])
        self.assertEqual("source-unverified", result["source_status"])
        self.assertIs(False, result["external_effect_verified"])
        self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()})

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

    def test_inspect_human_rejects_noncanonical_sidecar_timestamp(self) -> None:
        bundle, sidecar = self._readback_artifacts(
            observations=[
                {
                    "endpoint": "pull_request",
                    "started_at": "2026-10-13T02:54:00Z",
                    "finished_at": "2026-10-13T02:54:01Z",
                }
            ]
        )
        sidecar["observations"][0]["started_at"] = "2026-10-13T02:54:00z"
        bundle, sidecar = self._rebind_readback_sidecar(bundle, sidecar)
        path = pathlib.Path(self.temp.name) / "readback-invalid-timestamp.json"
        path.write_bytes(json.dumps(sidecar, separators=(",", ":")).encode())

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
