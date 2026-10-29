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
from mothership_adapters.evidence import EvidenceError, MAX_ENCODED_BYTES
from mothership_adapters.saved_result import inspect_saved_result, summarize_saved_result
from mothership.contracts import canonical_json_sha256
from mothership_github import public_observation
from orchestration.lib.action_authority import action_sha256


_SAVED_RESULT_SCHEMA = "mothership.reference-result.v1"


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
    def v1_rows(rows):
        rows = copy.deepcopy(rows)
        frozen = rows[0]
        for row in rows:
            row["saved_result_schema"] = _SAVED_RESULT_SCHEMA
            if row["event"] != "frozen_action":
                row["action_id"] = frozen["action"]["action_id"]
                row["action_sha256"] = frozen["action_sha256"]
        return rows

    @staticmethod
    def encode_rows(rows):
        return b"".join((json.dumps(row, ensure_ascii=True) + "\n").encode() for row in rows)

    def run_saved(self, raw, *, human=True, output=None, expected_action_sha256=None, extra_args=()):
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
        stdout = io.StringIO() if output is None else output
        stderr = io.StringIO()
        argv = ["inspect-result", *extra_args]
        if expected_action_sha256 is not None:
            argv.extend(["--expect-action-sha256", expected_action_sha256])
        if human:
            argv.append("--human")
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
            try:
                code = evidence_cli_main(argv)
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
                    code, projection, error = self.run_saved(
                        raw_cases[name],
                        human=False,
                        expected_action_sha256=self.request["action_sha256"],
                    )
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

    def test_v1_clean_prefixes_keep_unknown_status_and_structural_binding_only(self):
        rows = self.v1_rows(self.saved_rows())
        for length in (1, 2, 3):
            with self.subTest(length=length):
                code, text, error = self.run_saved(self.encode_rows(rows[:length]))
                self.assertEqual(0, code, error)
                self.assertIn("outcome unknown" if length < 3 else "independent observation recorded", text)
                expected = (
                    "not supplied"
                    if length == 1
                    else "action ID and digest match (structural only; source-unverified)"
                )
                self.assertIn("execution linkage: " + expected, text)

                code, projection, error = self.run_saved(
                    self.encode_rows(rows[:length]), human=False
                )
                self.assertEqual(0, code, error)
                view = json.loads(projection)
                self.assertEqual(
                    "not supplied"
                    if length == 1
                    else "action ID and digest match (structural only; source-unverified)",
                    view["execution_summary_binding"],
                )

    def test_v1_requires_closed_version_and_complete_identity_fields(self):
        valid = self.v1_rows(self.saved_rows())
        foreign_action = copy.deepcopy(valid[0]["action"])
        foreign_action["action_id"] = "act-foreign-identical-target"
        foreign_digest = action_sha256(foreign_action)
        cases = {
            "unknown_first_marker": lambda rows: rows[0].update(
                saved_result_schema="mothership.reference-result.v2"
            ),
            "unknown_later_marker": lambda rows: rows[1].update(
                saved_result_schema="mothership.reference-result.v2"
            ),
            "missing_first_marker": lambda rows: rows[0].pop("saved_result_schema"),
            "missing_later_marker": lambda rows: rows[1].pop("saved_result_schema"),
            "missing_action_id": lambda rows: rows[1].pop("action_id"),
            "missing_action_digest": lambda rows: rows[2].pop("action_sha256"),
            "typed_action_id": lambda rows: rows[1].update(action_id=123),
            "typed_action_digest": lambda rows: rows[2].update(action_sha256=True),
            "partial_identity": lambda rows: rows[1].update(action_id=foreign_action["action_id"]),
            "wrong_digest_only": lambda rows: rows[1].update(action_sha256=foreign_digest),
            "extra_first_field": lambda rows: rows[0].update(extra="reject"),
            "extra_later_field": lambda rows: rows[1].update(extra="reject"),
            "mixed_legacy_first": lambda rows: rows[0].pop("saved_result_schema"),
            "mixed_legacy_later": lambda rows: rows[2].pop("saved_result_schema"),
            "wrong_action_identity": lambda rows: rows[1].update(
                action_id=foreign_action["action_id"], action_sha256=foreign_digest
            ),
            "torn_final_line": lambda rows: None,
            "reordered_rows": lambda rows: rows.reverse(),
            "extra_row": lambda rows: rows.append(copy.deepcopy(rows[-1])),
        }
        for name, corrupt in cases.items():
            with self.subTest(case=name):
                rows = copy.deepcopy(valid)
                raw = self.encode_rows(rows)
                if name == "torn_final_line":
                    raw = raw[:-1] + b"{"  # complete rows plus a torn final write
                else:
                    corrupt(rows)
                    raw = self.encode_rows(rows)
                code, text, error = self.run_saved(raw)
                self.assertEqual((2, ""), (code, text))
                self.assertEqual("invalid bounded evidence input\n", error)

    def test_v1_rejects_cross_action_execution_and_verification_swaps(self):
        valid = self.v1_rows(self.saved_rows())
        foreign_action = copy.deepcopy(valid[0]["action"])
        foreign_action["action_id"] = "act-foreign-identical-target"
        foreign_digest = action_sha256(foreign_action)
        self.assertEqual(
            valid[0]["action"]["execution_parameters"],
            foreign_action["execution_parameters"],
        )
        self.assertEqual(valid[1]["paths"], valid[2]["paths"])

        for index in (1, 2):
            rows = copy.deepcopy(valid)
            rows[index].update(
                action_id=foreign_action["action_id"], action_sha256=foreign_digest
            )
            code, text, error = self.run_saved(self.encode_rows(rows))
            with self.subTest(variant="complete", row=index):
                self.assertEqual((2, ""), (code, text))
                self.assertEqual("invalid bounded evidence input\n", error)

        for reason in ("receipt_unavailable", "verification_unavailable"):
            rows = copy.deepcopy(valid)
            if reason == "receipt_unavailable":
                rows[2].update(
                    status="unavailable", reason=reason, source_pair=None,
                    receipt=None, verification=None, evidence=None,
                )
            else:
                rows[2].update(
                    status="unavailable", reason=reason, verification=None, evidence=None,
                )
            rows = self.v1_rows(rows)
            rows[2].update(
                action_id=foreign_action["action_id"], action_sha256=foreign_digest
            )
            code, text, error = self.run_saved(self.encode_rows(rows))
            with self.subTest(variant=reason):
                self.assertEqual((2, ""), (code, text))
                self.assertEqual("invalid bounded evidence input\n", error)

    def test_v1_reader_is_offline_repeatable_and_does_not_consume_opaque_paths(self):
        rows = self.v1_rows(self.saved_rows(status="UNKNOWN"))
        raw = self.encode_rows(rows)
        before = bytes(raw)
        with mock.patch("socket.socket", side_effect=AssertionError("network forbidden")), \
             mock.patch("orchestration.lib.action_authority.freeze_action", side_effect=AssertionError("issuance forbidden")), \
             mock.patch("orchestration.lib.action_authority_ledger.consume_action", side_effect=AssertionError("consume forbidden")), \
             mock.patch("mothership_github.executor.execute_action_merge_pr", side_effect=AssertionError("execution forbidden")):
            first = self.run_saved(raw)
            self.run_saved(b"broken\n")
            second = self.run_saved(raw)
            projection = self.run_saved(raw, human=False)
        self.assertEqual(first, second)
        self.assertEqual(before, raw)
        self.assertEqual(0, projection[0], projection[2])
        view = json.loads(projection[1])
        self.assertEqual("UNKNOWN", view["verification_status"])
        self.assertFalse(view["source_authenticated"])
        self.assertFalse(view["external_effect_verified"])
        self.assertNotIn("/not-to-open", first[1])

    def test_v1_output_failure_does_not_leak_into_repeated_inspection(self):
        good = self.encode_rows(self.v1_rows(self.saved_rows()))
        partial = self.encode_rows(self.v1_rows(self.saved_rows()[:1]))
        first = self.run_saved(good)
        expected_partial = self.run_saved(partial)

        class BrokenWriter(io.StringIO):
            def write(self, text):
                return super().write(text[:5])

        self.assertEqual(2, self.run_saved(good, output=BrokenWriter())[0])
        self.assertEqual(first, self.run_saved(good))
        self.assertEqual(expected_partial, self.run_saved(partial))
        self.assertNotIn("CONFIRMED", expected_partial[1])

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
        before_raw = bytes(raw)
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
            code, text, error = self.run_saved(
                raw, expected_action_sha256=self.request["action_sha256"]
            )
        self.assertEqual(0, code, error)
        self.assertEqual(before_raw, raw)
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

    def test_expected_action_digest_preserves_legacy_and_v1_outputs_for_nonempty_prefixes(self):
        expected = self.request["action_sha256"]
        variants = (
            ("legacy", self.saved_rows()),
            ("v1", self.v1_rows(self.saved_rows())),
        )
        for version, rows in variants:
            for length in (1, 2, 3):
                raw = self.encode_rows(rows[:length])
                with self.subTest(version=version, length=length, human=True):
                    self.assertEqual(
                        self.run_saved(raw),
                        self.run_saved(raw, expected_action_sha256=expected),
                    )
                with self.subTest(version=version, length=length, human=False):
                    self.assertEqual(
                        self.run_saved(raw, human=False),
                        self.run_saved(raw, human=False, expected_action_sha256=expected),
                    )

    def test_expected_action_digest_preserves_all_public_saved_case_outputs(self):
        root = pathlib.Path(__file__).resolve().parents[3] / "examples" / "saved-results"
        expected = self.request["action_sha256"]
        for path in sorted(root.glob("case-*.jsonl")):
            raw = path.read_bytes()
            with self.subTest(case=path.name, human=True):
                self.assertEqual(
                    self.run_saved(raw),
                    self.run_saved(raw, expected_action_sha256=expected),
                )
            with self.subTest(case=path.name, human=False):
                self.assertEqual(
                    self.run_saved(raw, human=False),
                    self.run_saved(raw, human=False, expected_action_sha256=expected),
                )

    def test_expected_action_digest_rejects_empty_wrong_and_coherent_alternate_actions(self):
        expected = self.request["action_sha256"]
        wrong = "0" * 64 if expected != "0" * 64 else "1" * 64
        valid_legacy = self.encode_rows(self.saved_rows())
        valid_v1 = self.encode_rows(self.v1_rows(self.saved_rows()))

        alternate = copy.deepcopy(self.saved_rows()[0])
        alternate["action"]["action_id"] = "act-evidence-alternate"
        alternate["action_sha256"] = action_sha256(alternate["action"])
        alternate_legacy = self.encode_rows([alternate])
        alternate_v1 = self.encode_rows(self.v1_rows([alternate]))
        self.assertEqual(
            alternate["action"]["execution_parameters"],
            self.saved_rows()[0]["action"]["execution_parameters"],
        )
        for raw in (alternate_legacy, alternate_v1):
            for human in (True, False):
                with self.subTest(variant="alternate", raw=raw, human=human):
                    self.assertEqual(0, self.run_saved(raw, human=human)[0])

        for raw, supplied in (
            (b"", expected),
            (valid_legacy, wrong),
            (valid_v1, wrong),
            (alternate_legacy, expected),
            (alternate_v1, expected),
        ):
            for human in (True, False):
                with self.subTest(raw=raw[:20], supplied=supplied, human=human):
                    code, output, error = self.run_saved(
                        raw, human=human, expected_action_sha256=supplied
                    )
                    self.assertEqual((2, ""), (code, output))
                    self.assertEqual("invalid bounded evidence input\n", error)

    def test_expected_action_digest_does_not_bypass_existing_full_validation(self):
        rows = self.saved_rows()
        rows[1].update(status="success", merged=False)
        code, output, error = self.run_saved(
            self.encode_rows(rows), expected_action_sha256=self.request["action_sha256"]
        )
        self.assertEqual((2, ""), (code, output))
        self.assertEqual("invalid bounded evidence input\n", error)

    def test_saved_result_api_requires_strict_keyword_only_expected_digest(self):
        rows = self.saved_rows()
        raw = self.encode_rows(rows)
        expected = self.request["action_sha256"]
        self.assertEqual(
            inspect_saved_result(raw),
            inspect_saved_result(raw, expected_action_sha256=None),
        )
        self.assertEqual(
            summarize_saved_result(raw),
            summarize_saved_result(raw, expected_action_sha256=None),
        )
        with self.assertRaises(TypeError):
            inspect_saved_result(raw, expected)  # type: ignore[call-arg]

        malformed = ("", "A" * 64, "0" * 63 + "g", expected[:-1], True, 0, b"0" * 64)
        for value in malformed:
            with self.subTest(value=repr(value)):
                with self.assertRaises(EvidenceError):
                    inspect_saved_result(raw, expected_action_sha256=value)
                with self.assertRaises(EvidenceError):
                    summarize_saved_result(raw, expected_action_sha256=value)

    def test_expected_action_option_rejects_before_stdin_and_keeps_fixed_diagnostics(self):
        expected = self.request["action_sha256"]
        cases = (
            ["inspect-result", "--expect-action-sha256", "not-a-digest"],
            ["inspect-result", "--expect-action-sha256", ""],
            [
                "inspect-result",
                "--expect-action-sha256",
                expected,
                "--expect-action-sha256",
                expected,
            ],
            ["inspect-result", "--expect-action-sha256"],
            ["inspect-result", "--expect-action-sha256", "--human"],
        )
        for argv in cases:
            source = io.BytesIO(b"PRIVATE_STDIN_SENTINEL")
            stdin = io.TextIOWrapper(source, encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(argv=argv), mock.patch("sys.stdin", stdin), mock.patch(
                "sys.stdout", stdout
            ), mock.patch("sys.stderr", stderr):
                try:
                    code = evidence_cli_main(argv)
                except SystemExit as exc:
                    code = int(exc.code)
            self.assertEqual(2, code)
            self.assertEqual(0, source.tell())
            self.assertEqual("", stdout.getvalue())
            self.assertEqual("invalid bounded evidence input\n", stderr.getvalue())

    def test_expected_action_digest_keeps_output_failure_and_repeatability_behavior(self):
        raw = self.encode_rows(self.saved_rows())
        expected = self.request["action_sha256"]
        first = self.run_saved(raw, expected_action_sha256=expected)

        class BrokenWriter(io.StringIO):
            def write(self, text):
                return super().write(text[:5])

        self.assertEqual(2, self.run_saved(
            raw, expected_action_sha256=expected, output=BrokenWriter()
        )[0])
        self.assertEqual(first, self.run_saved(raw, expected_action_sha256=expected))

    def assert_saved_rejection(self, result, code, next_check, *, partial_output=False):
        status, output, error = result
        self.assertEqual(2, status)
        if not partial_output:
            self.assertEqual("", output)
        diagnostic = json.loads(error)
        self.assertEqual({
            "schema", "code", "next_read_only_check", "accepted_result", "authority",
            "source_authenticated", "external_effect_verified", "recovery",
        }, set(diagnostic))
        self.assertEqual("mothership.saved-result-rejection.v0", diagnostic["schema"])
        self.assertEqual(code, diagnostic["code"])
        self.assertIn(next_check, diagnostic["next_read_only_check"])
        for field in ("accepted_result", "authority", "source_authenticated", "external_effect_verified"):
            self.assertIs(False, diagnostic[field])
        self.assertEqual("no re-execution; no reconsume", diagnostic["recovery"])
        self.assertEqual(1, error.count("\n"))
        self.assertLess(len(error), 2048)
        self.assertNotIn("PRIVATE", error)
        self.assertNotIn("/not-to-open", error)
        self.assertNotIn(self.request["action"]["action_id"], error)
        self.assertNotIn(self.request["action_sha256"], error)

    def test_explained_mismatch_requires_valid_legacy_or_v1_evidence(self):
        # A digest comparison before full validation would misclassify bad evidence.
        for rows in (self.saved_rows(), self.v1_rows(self.saved_rows())):
            for length in (1, 2, 3):
                for human in (True, False):
                    with self.subTest(version=rows[0].get("saved_result_schema"), length=length, human=human):
                        self.assert_saved_rejection(self.run_saved(
                            self.encode_rows(rows[:length]), human=human,
                            expected_action_sha256="0" * 64, extra_args=("--explain-error",),
                        ), "expected_action_mismatch", "separately retained")
            rows[1].update(status="success", merged=False)
            self.assert_saved_rejection(self.run_saved(
                self.encode_rows(rows), expected_action_sha256="0" * 64,
                extra_args=("--explain-error",),
            ), "invalid_saved_result", "original")

    def test_explained_invalid_evidence_is_not_an_accepted_target(self):
        good = self.encode_rows(self.saved_rows())
        mixed = self.v1_rows(self.saved_rows())
        mixed[1].pop("saved_result_schema")
        altered = self.saved_rows()
        altered[0]["action"]["action_id"] = "PRIVATE_UNTRUSTED_ACTION\u001b[31m"
        for raw in (good[:-1], b"PRIVATE_NOT_JSON\n", b"\xff\n",
                    self.encode_rows(mixed), self.encode_rows(altered)):
            for human in (True, False):
                with self.subTest(raw=raw[:20], human=human):
                    self.assert_saved_rejection(self.run_saved(
                        raw, human=human, extra_args=("--explain-error",),
                    ), "invalid_saved_result", "original")

    def test_explained_missing_action_is_unavailable_not_a_mismatch(self):
        for human in (True, False):
            self.assert_saved_rejection(self.run_saved(
                b"", human=human, expected_action_sha256=self.request["action_sha256"],
                extra_args=("--explain-error",),
            ), "expected_action_unavailable", "original")

    def test_explain_error_preserves_accepted_default_outputs_and_formats(self):
        # The option must not add metadata/diagnostics to accepted results.
        for rows in (self.saved_rows(), self.v1_rows(self.saved_rows())):
            for length in (0, 1, 2, 3):
                raw = self.encode_rows(rows[:length])
                for human in (True, False):
                    for expected in (None, self.request["action_sha256"] if length else None):
                        with self.subTest(length=length, human=human, expected=expected):
                            self.assertEqual(self.run_saved(raw, human=human, expected_action_sha256=expected),
                                             self.run_saved(raw, human=human, expected_action_sha256=expected,
                                                            extra_args=("--explain-error",)))

    def test_explained_bad_expectation_still_rejects_before_reading_stdin(self):
        expected = self.request["action_sha256"]
        options = (
            ("--expect-action-sha256", "PRIVATE_BAD_DIGEST"),
            ("--expect-action-sha256", ""),
            ("--expect-action-sha256", "A" * 64),
            ("--expect-action-sha256",),
            ("--expect-action-sha256", expected, "--expect-action-sha256", expected),
        )
        for args in options:
            source = io.BytesIO(b"PRIVATE_STDIN_SENTINEL")
            stdin = io.TextIOWrapper(source, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(args=args), mock.patch("sys.stdin", stdin), \
                 mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
                code = evidence_cli_main(["inspect-result", "--explain-error", *args])
            self.assert_saved_rejection((code, out.getvalue(), err.getvalue()),
                                        "invalid_expectation", "separately retained")
            self.assertEqual(0, source.tell())

    def test_explained_input_failure_does_not_claim_corrupt_evidence(self):
        class UnreadableInput:
            @property
            def buffer(self):
                raise OSError("PRIVATE_INPUT_FAILURE")

        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdin", UnreadableInput()), mock.patch("sys.stdout", out), \
             mock.patch("sys.stderr", err):
            code = evidence_cli_main(["inspect-result", "--explain-error"])
        self.assert_saved_rejection((code, out.getvalue(), err.getvalue()),
                                    "input_unavailable", "input")

    def test_explained_runtime_and_import_failures_remain_unclassified(self):
        raw = self.encode_rows(self.saved_rows())
        real_import = __import__

        def failed_import(name, *args, **kwargs):
            if name.endswith("saved_result"):
                raise ImportError("PRIVATE_IMPORT_FAILURE")
            return real_import(name, *args, **kwargs)

        with mock.patch("mothership_adapters.saved_result.inspect_saved_result",
                        side_effect=RuntimeError("PRIVATE_RUNTIME_FAILURE")):
            self.assert_saved_rejection(self.run_saved(raw, human=False, extra_args=("--explain-error",)),
                                        "inspection_unavailable", "environment")
            with self.assertRaisesRegex(RuntimeError, "PRIVATE_RUNTIME_FAILURE"):
                self.run_saved(raw, human=False)
        with mock.patch("builtins.__import__", side_effect=failed_import):
            self.assert_saved_rejection(self.run_saved(raw, extra_args=("--explain-error",)),
                                        "inspection_unavailable", "environment")

    def test_explained_serialization_failure_is_not_a_stdout_failure(self):
        raw = self.encode_rows(self.saved_rows())
        real_dumps = json.dumps

        def fail_result_serialization(value, *args, **kwargs):
            if type(value) is dict and value.get("format") == "reference-result-jsonl":
                raise ValueError("PRIVATE_SERIALIZATION_FAILURE")
            return real_dumps(value, *args, **kwargs)

        with mock.patch("mothership_adapters.cli.json.dumps", side_effect=fail_result_serialization):
            self.assert_saved_rejection(self.run_saved(raw, human=False, extra_args=("--explain-error",)),
                                        "inspection_unavailable", "environment")

    def test_explained_output_failure_does_not_persist_into_next_call(self):
        raw = self.encode_rows(self.saved_rows())
        first = self.run_saved(raw)

        class BrokenOutput(io.StringIO):
            def __init__(self, failure):
                super().__init__()
                self.failure = failure

            def write(self, text):
                if self.failure == "write":
                    super().write(text[:5])
                    raise OSError("PRIVATE_OUTPUT_FAILURE")
                return super().write(text[:5] if self.failure == "short" else text)

            def flush(self):
                if self.failure == "flush":
                    raise OSError("PRIVATE_FLUSH_FAILURE")
                super().flush()

        for human in (True, False):
            for failure in ("write", "short", "flush"):
                self.assert_saved_rejection(self.run_saved(
                    raw, human=human, output=BrokenOutput(failure), extra_args=("--explain-error",),
                ), "output_incomplete", "discard", partial_output=True)
                self.assertEqual(first, self.run_saved(raw))
        rejected = self.run_saved(b"PRIVATE_BAD_INPUT\n", extra_args=("--explain-error",))
        self.run_saved(raw)
        self.assertEqual(rejected, self.run_saved(b"PRIVATE_BAD_INPUT\n", extra_args=("--explain-error",)))
        self.assertEqual((2, "", "invalid bounded evidence input\n"), self.run_saved(b"bad\n"))

    def test_diagnostic_sink_failure_never_triggers_a_second_write(self):
        class BrokenDiagnostic(io.StringIO):
            def __init__(self, failure):
                super().__init__()
                self.failure, self.writes = failure, 0

            def write(self, text):
                self.writes += 1
                if self.failure == "write":
                    raise OSError("PRIVATE_DIAGNOSTIC_FAILURE")
                return super().write(text[:3] if self.failure == "short" else text)

            def flush(self):
                if self.failure == "flush":
                    raise OSError("PRIVATE_DIAGNOSTIC_FLUSH_FAILURE")
                super().flush()

        for failure in ("write", "short", "flush"):
            source = io.TextIOWrapper(io.BytesIO(b"bad\n"), encoding="utf-8")
            out, err = io.StringIO(), BrokenDiagnostic(failure)
            with mock.patch("sys.stdin", source), mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
                self.assertEqual(2, evidence_cli_main(["inspect-result", "--explain-error"]))
            self.assertEqual("", out.getvalue())
            self.assertEqual(1, err.writes)
            self.assertNotIn("PRIVATE", err.getvalue())

    def test_explained_rejections_are_offline_and_preserve_retained_records(self):
        raw = self.encode_rows(self.v1_rows(self.saved_rows()))
        before = [p.read_bytes() for p in (self.authority_path, self.receipt_path)]
        forbidden = {str(self.authority_path), str(self.receipt_path),
                     "/not-to-open/authority.jsonl", "/not-to-open/attempts.jsonl"}
        real_open, real_io_open, real_os_open = open, io.open, os.open

        def guarded_file_opener(opener):
            def read_only(path, mode="r", *args, **kwargs):
                self.assertNotIn(str(path), forbidden)
                self.assertNotIn("+", mode)
                self.assertTrue(mode.startswith("r"))
                return opener(path, mode, *args, **kwargs)
            return read_only

        def read_only_os_open(path, flags, *args, **kwargs):
            self.assertNotIn(str(path), forbidden)
            self.assertEqual(0, flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            return real_os_open(path, flags, *args, **kwargs)

        with mock.patch("socket.socket", side_effect=AssertionError("network forbidden")), \
             mock.patch("builtins.open", side_effect=guarded_file_opener(real_open)), \
             mock.patch("io.open", side_effect=guarded_file_opener(real_io_open)), \
             mock.patch("os.open", side_effect=read_only_os_open), \
             mock.patch("orchestration.lib.action_authority.freeze_action", side_effect=AssertionError("issuance forbidden")), \
             mock.patch("orchestration.lib.action_authority_ledger.consume_action", side_effect=AssertionError("consume forbidden")), \
             mock.patch("mothership_github.executor.execute_action_merge_pr", side_effect=AssertionError("execution forbidden")):
            for candidate, expected, code in ((raw, "0" * 64, "expected_action_mismatch"),
                                              (raw[:-1], "0" * 64, "invalid_saved_result"),
                                              (b"", "0" * 64, "expected_action_unavailable")):
                self.assert_saved_rejection(self.run_saved(candidate, expected_action_sha256=expected,
                                                          extra_args=("--explain-error",)), code, "original")
        self.assertEqual(before, [p.read_bytes() for p in (self.authority_path, self.receipt_path)])


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


class HarnessLiveCLITests(unittest.TestCase):
    """Exercise the real entry/owner/transport, doubling only terminal and HTTP."""

    def setUp(self):
        import test_harness_handoff as fixtures
        self.fixtures = fixtures
        self.fixture = fixtures.HandoffOwnerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.serial = 0
        self.harness = self.root / "harness"
        payload = json.dumps(fixtures.preview(), ensure_ascii=True)
        self.harness.write_text("#!/bin/sh\nprintf '%s\\n' '" + payload + "'\n")
        self.harness.chmod(0o700)
        for name, value in (("interpretation", fixtures.INTERPRETATION),
                            ("parameters", self.fixture.parameters), ("context", fixtures.CONTEXT)):
            (self.root / (name + ".json")).write_text(json.dumps(value))

    def run_handoff(self, *, live=True, decision="approve", login="Operator",
                    permission=True, verification="CONFIRMED", token_error=None,
                    non_tty=False, put_error=False, context_changes=None, context_drift=False,
                    extra_args=()):
        import getpass
        from mothership_adapters.harness_handoff_cli import main
        fixtures = self.fixtures
        self.serial += 1
        run = self.root / ("run-" + str(self.serial))
        stderr, stdout, calls = fixtures.Terminal(), io.StringIO(), []
        fixed = datetime.datetime(2026, 10, 25, tzinfo=datetime.UTC)
        state = {"put": False}
        if context_changes is not None:
            (self.root / "context.json").write_text(json.dumps({**fixtures.CONTEXT, **context_changes}))

        class Input(fixtures.Terminal):
            def isatty(self):
                return not non_tty

            def readline(self, limit=-1):
                if decision == "cancel":
                    return "cancel\n"
                shown, _ = json.JSONDecoder().raw_decode(stderr.getvalue())
                request = shown.get("review_request", shown)
                if context_drift:
                    (self_root / "context.json").write_text(json.dumps({**fixtures.CONTEXT, "runtime_generation": "changed"}))
                request_id = "wrong" if decision == "wrong" else request["request_id"]
                return ("reject" if decision == "reject" else "approve") + " " + request_id + " " + request["request_sha256"] + "\n"

        def http(_opener, request, *args, **kwargs):
            method, url = request.get_method(), request.full_url
            calls.append((method, url, request.get_header("Authorization")))
            if url == "https://api.github.com/user":
                payload = {"login": login}
            elif url == "https://api.github.com/repos/example/repo":
                payload = {"full_name": "example/repo", "permissions": {"push": permission}}
            elif method == "PUT":
                state["put"] = True
                if put_error:
                    raise TimeoutError("private failure")
                payload = {"merged": True, "sha": "b" * 40}
            elif url.endswith("/pulls/7"):
                stamp = fixed + datetime.timedelta(seconds=0 if verification == "UNKNOWN" else 5)
                head = "a" * 40 if state["put"] and verification == "MISMATCH" else self.fixture.parameters["expected_head_sha"]
                payload = dict(url=url, number=7, title="synthetic canary", draft=False,
                               updated_at="2026-10-25T00:00:06Z", state="closed" if state["put"] else "open",
                               merged=state["put"], merged_at=stamp.strftime("%Y-%m-%dT%H:%M:%SZ") if state["put"] else None,
                               head={"sha": head}, base={"ref": "canary-base", "repo": {"full_name": "example/repo"}},
                               merge_commit_sha="b" * 40 if state["put"] else None)
            elif url.endswith("/git/commits/" + "b" * 40):
                payload = {"sha": "b" * 40, "parents": [{"sha": "c" * 40}, {"sha": self.fixture.parameters["expected_head_sha"]}]}
            else:
                raise AssertionError("unexpected network path")
            response = io.BytesIO(json.dumps(payload).encode())
            response.status, response.headers, response.url = 200, {}, url
            response.geturl = lambda: url
            return response

        self_root = self.root
        argv = ["--harness-cli", str(self.harness), "--request", fixtures.REQUEST,
                "--interpretation-file", str(self.root / "interpretation.json"),
                "--parameters", str(self.root / "parameters.json"), "--host-context", str(self.root / "context.json"),
                "--worktree", str(self.fixture.worktree), "--run-directory", str(run), "--json"]
        if live:
            argv += ["--live-github", "--expected-login", "Operator"]
        argv += list(extra_args)
        secret = "synthetic-" + "credential-sentinel"
        def prompt(*args, **kwargs):
            if token_error == "warning":
                import warnings
                warnings.warn("hidden input unavailable", getpass.GetPassWarning)
            if token_error == "interrupt":
                raise KeyboardInterrupt()
            return secret
        with mock.patch("sys.stdin", Input()), mock.patch("sys.stderr", stderr), mock.patch("sys.stdout", stdout), \
             mock.patch("getpass.getpass", side_effect=prompt) as hidden, \
             mock.patch("urllib.request.OpenerDirector.open", new=http), \
             mock.patch("orchestration.lib.action_authority._utc_now", return_value=fixed), \
             mock.patch("orchestration.lib.action_authority_ledger._utc_now", return_value=fixed), \
             mock.patch("mothership_github.receipts._utc_now", side_effect=[fixed, fixed + datetime.timedelta(seconds=1)]), \
             mock.patch("mothership_github.verification._utc_now", return_value=fixed + datetime.timedelta(seconds=10)):
            try:
                code = main(argv)
            except SystemExit as error:
                code = int(error.code)
        self.assertNotIn(secret, stdout.getvalue() + stderr.getvalue())
        if run.exists():
            for path in run.iterdir():
                if path.is_file():
                    self.assertNotIn(secret.encode(), path.read_bytes())
        return code, run, calls, hidden.call_count, stderr.getvalue()

    def test_harness_live_entry_uses_one_put_and_independent_default_readback(self):
        code, run, calls, hidden, shown = self.run_handoff()
        self.assertEqual(0, code, shown)
        result = json.loads((run / "result.json").read_bytes())
        self.assertEqual("thin-harness-handoff-result.v1", result["schema_version"])
        self.assertEqual("github_live", result["execution_mode"])
        self.assertFalse(result["local_only"])
        self.assertEqual("CONFIRMED", result["inspection"]["verification_status"])
        self.assertFalse(result["inspection"]["external_effect_verified"])
        self.assertEqual(1, hidden)
        self.assertEqual(1, sum(method == "PUT" for method, _, _ in calls))
        self.assertLessEqual(len(calls), 6)
        self.assertTrue(all(auth is None for _, _, auth in calls[-2:]))
        self.assertIn("LIVE GITHUB", shown)
        self.assertIsNone(json.loads((run / "original.json").read_bytes())["verification"])
        self.assertEqual("default_tokenless", json.loads((run / "readback-evidence.json").read_bytes())["transport"])

    def test_explicit_gh_auth_uses_same_transport_without_hidden_prompt(self):
        with mock.patch("mothership_adapters.gh_auth.load_secrets", return_value=("synthetic-credential-sentinel", "2.103.3")):
            code, run, calls, hidden, shown = self.run_handoff(extra_args=["--gh-auth"])
        self.assertEqual(0, code, shown)
        self.assertEqual(0, hidden)
        self.assertEqual(1, sum(method == "PUT" for method, _, _ in calls))
        self.assertEqual("CONFIRMED", json.loads((run / "result.json").read_bytes())["inspection"]["verification_status"])
        self.assertTrue(all(auth is None for _, _, auth in calls[-2:]))
        meta = json.loads((run / "credential-source.json").read_bytes())
        self.assertEqual({"source": "gh", "version": "2.103.3", "host_id": "synthetic", "expected_login": "Operator"}, meta)

    def test_gh_auth_failure_never_falls_back_or_executes(self):
        from mothership_adapters.gh_auth import GhAuthError
        with mock.patch("mothership_adapters.gh_auth.load_secrets", side_effect=GhAuthError("unavailable")):
            code, run, calls, hidden, shown = self.run_handoff(extra_args=["--gh-auth"])
        self.assertEqual(2, code, shown)
        self.assertEqual(0, hidden)
        self.assertEqual([], calls)
        self.assertFalse(run.exists())

    def test_gh_auth_flag_is_rejected_in_synthetic_mode(self):
        code, run, calls, hidden, shown = self.run_handoff(live=False, extra_args=["--gh-auth"])
        self.assertEqual(2, code, shown)
        self.assertEqual([], calls)
        self.assertEqual(0, hidden)
        self.assertFalse(run.exists())

    def test_gh_auth_wrong_identity_or_permission_stops_before_authority(self):
        for change in ({"login": "Other"}, {"permission": False}):
            with self.subTest(change=change), mock.patch(
                "mothership_adapters.gh_auth.load_secrets", return_value=("synthetic-credential-sentinel", "2.103.3")
            ):
                code, run, calls, hidden, shown = self.run_handoff(extra_args=["--gh-auth"], **change)
                self.assertEqual(2, code, shown)
                self.assertEqual(0, hidden)
                self.assertFalse(any(method == "PUT" for method, _, _ in calls))
                self.assertFalse(run.exists())

    def test_gh_auth_context_failure_precedes_credential_acquisition(self):
        with mock.patch("mothership_adapters.gh_auth.load_secrets") as load:
            code, run, calls, hidden, shown = self.run_handoff(
                context_changes={"host_id": None}, extra_args=["--gh-auth"])
        self.assertEqual(2, code, shown)
        self.assertEqual(0, load.call_count)
        self.assertEqual(0, hidden)
        self.assertEqual([], calls)
        self.assertFalse(run.exists())

    def test_gh_auth_ambiguous_put_does_not_retry(self):
        with mock.patch("mothership_adapters.gh_auth.load_secrets", return_value=("synthetic-credential-sentinel", "2.103.3")):
            code, run, calls, hidden, shown = self.run_handoff(put_error=True, extra_args=["--gh-auth"])
        self.assertEqual(2, code, shown)
        self.assertEqual(0, hidden)
        self.assertEqual(1, sum(method == "PUT" for method, _, _ in calls))
        self.assertEqual("UNKNOWN", json.loads((run / "result.json").read_bytes())["inspection"]["receipt_status"])

    def test_harness_live_unknown_or_mismatch_stops_without_reexecution(self):
        for status in ("UNKNOWN", "MISMATCH"):
            with self.subTest(status=status):
                code, run, calls, _, shown = self.run_handoff(verification=status)
                self.assertEqual(2, code, shown)
                self.assertTrue(run.is_dir(), "a partial live result must retain its run directory")
                self.assertEqual(status, json.loads((run / "result.json").read_bytes())["inspection"]["verification_status"])
                self.assertEqual(1, sum(method == "PUT" for method, _, _ in calls))

    def test_harness_live_reject_cancel_and_wrong_request_do_not_attempt(self):
        for decision in ("reject", "cancel", "wrong"):
            with self.subTest(decision=decision):
                code, run, calls, _, shown = self.run_handoff(decision=decision)
                self.assertEqual(2 if decision == "wrong" else 0, code, shown)
                self.assertFalse(any(method == "PUT" for method, _, _ in calls))
                self.assertFalse((run / "attempts.jsonl").exists())

    def test_harness_live_wrong_identity_or_permission_stops_before_authority(self):
        for changes in ({"login": "Other"}, {"permission": False}):
            with self.subTest(changes=changes):
                code, run, calls, _, shown = self.run_handoff(**changes)
                self.assertEqual(2, code, shown)
                self.assertFalse(run.exists())
                self.assertFalse(any(method == "PUT" for method, _, _ in calls))

    def test_harness_live_hidden_input_failure_and_non_tty_have_no_effect(self):
        for changes in ({"token_error": "warning"}, {"token_error": "interrupt"}, {"non_tty": True}):
            with self.subTest(changes=changes):
                code, run, calls, _, shown = self.run_handoff(**changes)
                self.assertEqual(2, code, shown)
                self.assertEqual([], calls)
                self.assertFalse(run.exists())

    def test_harness_live_ambiguous_put_is_not_retried(self):
        code, run, calls, _, shown = self.run_handoff(put_error=True)
        self.assertEqual(2, code, shown)
        self.assertEqual(1, sum(method == "PUT" for method, _, _ in calls))
        self.assertTrue((run / "attempts.jsonl").exists())
        # The remote may commit before its response is lost. Keep the UNKNOWN
        # executor report even when the independent readback confirms the merge.
        inspection = json.loads((run / "result.json").read_bytes())["inspection"]
        self.assertEqual("UNKNOWN", inspection["receipt_status"])
        self.assertEqual("CONFIRMED", inspection["verification_status"])

    def test_harness_live_context_validation_precedes_credential_input(self):
        code, run, calls, hidden, shown = self.run_handoff(context_changes={"host_id": None})
        self.assertEqual(2, code, shown)
        self.assertEqual(0, hidden)
        self.assertEqual([], calls)
        self.assertFalse(run.exists())

    def test_harness_live_flags_cannot_be_silently_ignored_by_synthetic_mode(self):
        code, run, calls, hidden, shown = self.run_handoff(live=False, extra_args=["--expected-login", ""])
        self.assertEqual(2, code, shown)
        self.assertEqual([], calls)
        self.assertEqual(0, hidden)
        self.assertFalse(run.exists())

    def test_harness_live_context_drift_stops_before_decision_and_attempt(self):
        code, run, calls, _, shown = self.run_handoff(context_drift=True)
        self.assertEqual(2, code, shown)
        self.assertFalse(any(method == "PUT" for method, _, _ in calls))
        self.assertFalse((run / "authority.jsonl").exists())
        self.assertFalse((run / "attempts.jsonl").exists())

    def test_harness_synthetic_default_never_reads_credentials_or_network(self):
        code, run, calls, hidden, shown = self.run_handoff(live=False)
        self.assertEqual(0, code, shown)
        self.assertEqual([], calls)
        self.assertEqual(0, hidden)
        result = json.loads((run / "result.json").read_bytes())
        self.assertEqual("thin-harness-handoff-result.v0", result["schema_version"])
        self.assertTrue(result["local_only"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
