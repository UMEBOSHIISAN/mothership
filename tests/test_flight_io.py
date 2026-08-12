from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from orchestration.lib.canonical import canonical_json_bytes, canonical_json_sha256


REGISTRY_SHA256 = "cb5000ca90a1395c5efdf7362b5d9928fea70915a96af3c3b10542a7abbf0a14"
REQUIRED_STAGES = (
    "intent",
    "scope",
    "decision",
    "approval",
    "execution",
    "result",
    "verification",
    "persistence",
)
DIGEST = "a" * 64


def event(stage: str, number: int, *, schema_version: str = "mothership.flight-event.v1") -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "event_id": f"event-{stage}",
        "run_id": "run-safe-001",
        "event_type": "record_recorded",
        "stage": stage,
        "occurred_at": f"2026-08-12T00:00:0{number}Z",
        "producer_class": "synthetic",
        "tool_id": None,
        "predecessor_event_ids": [] if number == 0 else [f"event-{REQUIRED_STAGES[number - 1]}"],
        "subject": {
            "storage": "external",
            "protocol_kind": "frontdoor-task",
            "schema_version": "intake.v0",
            "location": f"refs/{stage}.json",
            "sha256": DIGEST,
        },
        "scope_sha256": None,
        "action_class": "none",
        "authority_effect": False,
        "execution_effect": False,
        "outcome_status": "recorded",
        "redaction": {"profile": "metadata-only", "removed_fields": 0},
        "extension": None,
    }


def index_for(events: list[dict[str, object]], *, privacy_profile: str = "metadata-only") -> dict[str, object]:
    return {
        "schema_version": "mothership.flight-index.v1",
        "run_id": "run-safe-001",
        "created_at": events[0]["occurred_at"],
        "producer_class": "synthetic",
        "event_ids": [item["event_id"] for item in events],
        "required_stages": list(REQUIRED_STAGES),
        "protocol_registry_sha256": REGISTRY_SHA256,
        "privacy_profile": privacy_profile,
        "bundle_sha256": None,
        "declared_verdict": None,
    }


def expected_digest(index: dict[str, object], events_bytes: bytes, artifacts: tuple[tuple[str, int, str], ...]) -> str:
    digest_index = copy.deepcopy(index)
    digest_index["bundle_sha256"] = None
    digest_index["declared_verdict"] = None
    return canonical_json_sha256(
        {
            "index": digest_index,
            "events_sha256": hashlib.sha256(events_bytes).hexdigest(),
            "artifacts": [
                {"path": path, "size": size, "sha256": digest}
                for path, size, digest in sorted(artifacts)
            ],
        }
    )


class FlightIoTests(unittest.TestCase):
    def setUp(self) -> None:
        from mothership.flight_contracts import FlightError
        from mothership.flight_io import FlightBundle, bundle_digest, import_generic_jsonl, load_flight_bundle

        self.FlightError = FlightError
        self.FlightBundle = FlightBundle
        self.bundle_digest = bundle_digest
        self.import_generic_jsonl = import_generic_jsonl
        self.load_flight_bundle = load_flight_bundle

    def assert_flight_error(self, rule_id: str, callback: object) -> None:
        with self.assertRaises(self.FlightError) as raised:
            callback()  # type: ignore[operator]
        self.assertEqual("INVALID", raised.exception.verdict)
        self.assertEqual(rule_id, raised.exception.rule_id)

    def write_bundle(
        self,
        root: Path,
        events: list[dict[str, object]] | None = None,
        *,
        index: dict[str, object] | None = None,
        artifacts: dict[str, bytes] | None = None,
    ) -> tuple[dict[str, object], bytes]:
        events = events or [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
        events_bytes = b"".join(canonical_json_bytes(item) + b"\n" for item in events)
        artifact_rows = tuple(
            (f"artifacts/{path}", len(raw), hashlib.sha256(raw).hexdigest())
            for path, raw in (artifacts or {}).items()
        )
        index = copy.deepcopy(index or index_for(events))
        index["bundle_sha256"] = expected_digest(index, events_bytes, artifact_rows)
        root.mkdir()
        (root / "artifacts").mkdir()
        (root / "flight.json").write_bytes(canonical_json_bytes(index))
        (root / "events.jsonl").write_bytes(events_bytes)
        for relative, raw in (artifacts or {}).items():
            artifact_path = root / "artifacts" / relative
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(raw)
        return index, events_bytes

    def test_load_preserves_jsonl_order_bytes_and_deeply_detaches_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            index, events_bytes = self.write_bundle(root)
            bundle = self.load_flight_bundle(root)

        self.assertIsInstance(bundle, self.FlightBundle)
        self.assertEqual(index, bundle.index)
        self.assertEqual(events_bytes, bundle.events_bytes)
        self.assertEqual([f"event-{stage}" for stage in REQUIRED_STAGES], [item["event_id"] for item in bundle.events])
        bundle.index["event_ids"].append("event-changed")  # type: ignore[index,union-attr]
        bundle.events[0]["subject"]["location"] = "refs/changed.json"  # type: ignore[index]
        self.assertEqual([f"event-{stage}" for stage in REQUIRED_STAGES], index["event_ids"])
        self.assertEqual("refs/intent.json", event("intent", 0)["subject"]["location"])

    def test_bundle_digest_is_non_self_referential_and_sorts_artifacts(self) -> None:
        events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
        index = index_for(events)
        event_bytes = b"".join(canonical_json_bytes(item) + b"\n" for item in events)
        artifacts = (("artifacts/z.json", 1, "b" * 64), ("artifacts/a.json", 2, "c" * 64))
        expected = expected_digest(index, event_bytes, artifacts)
        index["bundle_sha256"] = "d" * 64
        index["declared_verdict"] = "COMPLETE"
        self.assertEqual(expected, self.bundle_digest(index, event_bytes, tuple(reversed(artifacts))))

    def test_load_checks_digest_before_identity_and_classifies_identity_relationships(self) -> None:
        cases: list[tuple[str, list[dict[str, object]], dict[str, object], str]] = []

        order_mismatch_events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
        order_mismatch_index = index_for(order_mismatch_events)
        order_mismatch_index["event_ids"] = list(reversed(order_mismatch_index["event_ids"]))  # type: ignore[arg-type]
        cases.append(("event order", order_mismatch_events, order_mismatch_index, "FLIGHT.INVALID.IDENTITY"))

        run_mismatch_events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
        run_mismatch_events[-1]["run_id"] = "run-other-001"
        cases.append(("run identifier", run_mismatch_events, index_for(run_mismatch_events), "FLIGHT.INVALID.IDENTITY"))

        combined_events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
        combined_index = index_for(combined_events)
        combined_index["event_ids"] = list(reversed(combined_index["event_ids"]))  # type: ignore[arg-type]
        cases.append(("identity and digest", combined_events, combined_index, "FLIGHT.INVALID.DIGEST"))

        for name, events, index, rule_id in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(os.path.realpath(temporary)) / "bundle"
                written_index, _events_bytes = self.write_bundle(root, events, index=index)
                if name == "identity and digest":
                    written_index["bundle_sha256"] = "f" * 64
                    (root / "flight.json").write_bytes(canonical_json_bytes(written_index))
                self.assert_flight_error(rule_id, lambda: self.load_flight_bundle(root))

    def test_load_rejects_invalid_jsonl_structure_and_never_echoes_sensitive_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            index, _ = self.write_bundle(root)
            (root / "events.jsonl").write_bytes(b'{"secret":"do-not-echo"}')
            index["bundle_sha256"] = "a" * 64
            (root / "flight.json").write_bytes(canonical_json_bytes(index))
            with self.assertRaises(self.FlightError) as raised:
                self.load_flight_bundle(root)

        self.assertEqual("FLIGHT.INVALID.FILE", raised.exception.rule_id)
        self.assertNotIn("do-not-echo", str(raised.exception))

    def test_load_rejects_duplicate_keys_nonfinite_and_more_than_256_events(self) -> None:
        cases = (
            b'{"schema_version":"mothership.flight-event.v1","schema_version":"mothership.flight-event.v1"}\n',
            b'{"value":NaN}\n',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(os.path.realpath(temporary)) / "bundle"
                    self.write_bundle(root)
                    (root / "events.jsonl").write_bytes(raw)
                    self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.load_flight_bundle(root))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            events = []
            for number in range(257):
                item = event("intent", 0)
                item["event_id"] = f"event-{number}"
                events.append(item)
            self.write_bundle(root, events)
            self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.load_flight_bundle(root))

    def test_load_rejects_oversized_nonregular_and_symlinked_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            self.write_bundle(root)
            (root / "flight.json").write_bytes(b" " * 1_048_577)
            self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.load_flight_bundle(root))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            self.write_bundle(root)
            (root / "events.jsonl").unlink()
            os.mkfifo(root / "events.jsonl")
            self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.load_flight_bundle(root))

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(os.path.realpath(temporary))
            root = base / "bundle"
            self.write_bundle(root)
            (base / "link").symlink_to(root, target_is_directory=True)
            self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.load_flight_bundle(base / "link"))

    def test_public_paths_must_be_lexically_normalized_and_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(os.path.realpath(temporary))
            root = base / "bundle"
            self.write_bundle(root)
            source = base / "generic.jsonl"
            generic_events = [
                event(stage, number, schema_version="mothership.generic-event.v1")
                for number, stage in enumerate(REQUIRED_STAGES)
            ]
            source.write_bytes(b"".join(canonical_json_bytes(item) + b"\n" for item in generic_events))

            relative_root = Path(os.path.relpath(root, Path.cwd()))
            nonnormalized_root = Path(f"{base}/../{base.name}/bundle")
            relative_source = Path(os.path.relpath(source, Path.cwd()))
            nonnormalized_source = Path(f"{base}/../{base.name}/generic.jsonl")
            for invalid in (relative_root, nonnormalized_root):
                with self.subTest(bundle=invalid):
                    self.assert_flight_error("FLIGHT.INVALID.FILE", lambda invalid=invalid: self.load_flight_bundle(invalid))
            for invalid in (relative_source, nonnormalized_source):
                with self.subTest(source=invalid):
                    output = base / f"output-source-{len(str(invalid))}"
                    self.assert_flight_error(
                        "FLIGHT.INVALID.FILE",
                        lambda invalid=invalid, output=output: self.import_generic_jsonl(invalid, output),
                    )
                    self.assertFalse(output.exists())
            for invalid in (Path("relative-output"), Path(f"{base}/../{base.name}/output")):
                with self.subTest(output=invalid):
                    self.assert_flight_error(
                        "FLIGHT.INVALID.FILE",
                        lambda invalid=invalid: self.import_generic_jsonl(source, invalid),
                    )
            self.assertFalse(Path("relative-output").exists())
            self.assertFalse((base / "output").exists())

    def test_load_allows_only_report_md_as_untrusted_derived_root_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            self.write_bundle(root)
            (root / "report.md").write_text("derived report", encoding="utf-8")
            self.load_flight_bundle(root)
            (root / "unexpected.txt").write_text("not allowed", encoding="utf-8")
            self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.load_flight_bundle(root))

    def test_load_checks_registry_digest_bundle_digest_and_artifact_profile_relationships(self) -> None:
        payload = canonical_json_bytes({"kind": "safe", "value": 1})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
            events[0]["subject"] = dict(events[0]["subject"], storage="bundled", location="artifacts/proof.json", sha256=hashlib.sha256(payload).hexdigest())  # type: ignore[arg-type]
            events[0]["redaction"] = {"profile": "portable-evidence", "removed_fields": 0}
            index = index_for(events, privacy_profile="portable-evidence")
            self.write_bundle(root, events, index=index, artifacts={"proof.json": payload})
            bundle = self.load_flight_bundle(root)
            self.assertEqual((("artifacts/proof.json", len(payload), hashlib.sha256(payload).hexdigest()),), bundle.artifacts)

            index["protocol_registry_sha256"] = "a" * 64
            (root / "flight.json").write_bytes(canonical_json_bytes(index))
            self.assert_flight_error("FLIGHT.INVALID.REGISTRY", lambda: self.load_flight_bundle(root))

            index["protocol_registry_sha256"] = REGISTRY_SHA256
            index["bundle_sha256"] = "a" * 64
            (root / "flight.json").write_bytes(canonical_json_bytes(index))
            self.assert_flight_error("FLIGHT.INVALID.DIGEST", lambda: self.load_flight_bundle(root))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
            events[0]["subject"] = dict(events[0]["subject"], storage="bundled", location="artifacts/proof.json")  # type: ignore[arg-type]
            self.write_bundle(root, events, artifacts={"proof.json": payload})
            self.assert_flight_error("FLIGHT.INVALID.PRIVACY", lambda: self.load_flight_bundle(root))

    def test_load_rejects_artifacts_with_local_file_uris_unc_or_embedded_absolute_paths(self) -> None:
        for private_reference in (
            "file:///Users/alice/.env",
            r"\\server\share\proof.json",
            "artifact stored at /Users/alice/proof.json",
        ):
            with self.subTest(private_reference=private_reference), tempfile.TemporaryDirectory() as temporary:
                root = Path(os.path.realpath(temporary)) / "bundle"
                payload = canonical_json_bytes({"reference": private_reference})
                events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
                events[0]["subject"] = dict(
                    events[0]["subject"],  # type: ignore[arg-type]
                    storage="bundled",
                    location="artifacts/proof.json",
                    sha256=hashlib.sha256(payload).hexdigest(),
                )
                events[0]["redaction"] = {"profile": "portable-evidence", "removed_fields": 0}
                index = index_for(events, privacy_profile="portable-evidence")
                self.write_bundle(root, events, index=index, artifacts={"proof.json": payload})

                with self.assertRaises(self.FlightError) as raised:
                    self.load_flight_bundle(root)
                self.assertEqual("FLIGHT.INVALID.PRIVACY", raised.exception.rule_id)
                self.assertNotIn(private_reference, str(raised.exception))

    def test_load_rejects_backtick_delimited_private_paths_in_portable_artifacts(self) -> None:
        for private_reference in (
            "`/Users/alice/proof.json`",
            r"`C:\Users\alice\proof.json`",
            r"`\\server\share\proof.json`",
        ):
            with self.subTest(private_reference=private_reference), tempfile.TemporaryDirectory() as temporary:
                root = Path(os.path.realpath(temporary)) / "bundle"
                payload = canonical_json_bytes({"reference": private_reference})
                events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
                events[0]["subject"] = dict(
                    events[0]["subject"],  # type: ignore[arg-type]
                    storage="bundled",
                    location="artifacts/proof.json",
                    sha256=hashlib.sha256(payload).hexdigest(),
                )
                events[0]["redaction"] = {"profile": "portable-evidence", "removed_fields": 0}
                index = index_for(events, privacy_profile="portable-evidence")
                self.write_bundle(root, events, index=index, artifacts={"proof.json": payload})

                with self.assertRaises(self.FlightError) as raised:
                    self.load_flight_bundle(root)
                self.assertEqual("FLIGHT.INVALID.PRIVACY", raised.exception.rule_id)
                self.assertNotIn(private_reference, str(raised.exception))

    def test_load_rejects_unreferenced_or_wrong_artifacts_and_artifact_symlinks(self) -> None:
        payload = canonical_json_bytes({"kind": "safe"})
        events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
        events[0]["subject"] = dict(events[0]["subject"], storage="bundled", location="artifacts/proof.json", sha256=hashlib.sha256(payload).hexdigest())  # type: ignore[arg-type]
        events[0]["redaction"] = {"profile": "portable-evidence", "removed_fields": 0}
        index = index_for(events, privacy_profile="portable-evidence")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            self.write_bundle(root, events, index=index, artifacts={"proof.json": payload, "unused.json": payload})
            self.assert_flight_error("FLIGHT.INVALID.PRIVACY", lambda: self.load_flight_bundle(root))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            self.write_bundle(root, events, index=index, artifacts={"proof.json": payload})
            (root / "artifacts" / "proof.json").unlink()
            (root / "artifacts" / "proof.json").symlink_to(root / "flight.json")
            self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.load_flight_bundle(root))

    def test_load_sorts_artifacts_and_rejects_bundled_locations_outside_artifacts(self) -> None:
        first = canonical_json_bytes({"kind": "first"})
        second = canonical_json_bytes({"kind": "second"})
        events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
        events[0]["subject"] = dict(events[0]["subject"], storage="bundled", location="artifacts/z.json", sha256=hashlib.sha256(first).hexdigest())  # type: ignore[arg-type]
        events[1]["subject"] = dict(events[1]["subject"], storage="bundled", location="artifacts/a.json", sha256=hashlib.sha256(second).hexdigest())  # type: ignore[arg-type]
        index = index_for(events, privacy_profile="portable-evidence")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            self.write_bundle(root, events, index=index, artifacts={"z.json": first, "a.json": second})
            bundle = self.load_flight_bundle(root)
            self.assertEqual(["artifacts/a.json", "artifacts/z.json"], [path for path, _size, _digest in bundle.artifacts])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            invalid_events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
            invalid_events[0]["subject"] = dict(invalid_events[0]["subject"], storage="bundled", location="refs/proof.json")  # type: ignore[arg-type]
            invalid_index = index_for(invalid_events, privacy_profile="portable-evidence")
            self.write_bundle(root, invalid_events, index=invalid_index)
            self.assert_flight_error("FLIGHT.INVALID.SCHEMA", lambda: self.load_flight_bundle(root))

    def test_metadata_only_requires_a_literally_empty_artifacts_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.path.realpath(temporary)) / "bundle"
            self.write_bundle(root)
            (root / "artifacts" / "nested").mkdir()
            self.assert_flight_error("FLIGHT.INVALID.PRIVACY", lambda: self.load_flight_bundle(root))

    def test_root_membership_add_remove_and_replace_races_fail_closed(self) -> None:
        import mothership.flight_io as flight_io

        for mutation in ("add", "remove", "replace"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(os.path.realpath(temporary)) / "bundle"
                self.write_bundle(root)
                changed = False

                def mutate(label: str) -> None:
                    nonlocal changed
                    if label != "root" or changed:
                        return
                    changed = True
                    if mutation == "add":
                        (root / "unexpected.json").write_bytes(b"{}")
                    elif mutation == "remove":
                        (root / "events.jsonl").unlink()
                    else:
                        original = (root / "events.jsonl").read_bytes()
                        (root / "events.jsonl").rename(root.parent / "events.original")
                        (root / "events.jsonl").write_bytes(original)

                with mock.patch.object(flight_io, "_MEMBERSHIP_VERIFY_HOOK", mutate, create=True):
                    self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.load_flight_bundle(root))
                self.assertTrue(changed)

    def test_artifact_membership_add_remove_and_replace_races_fail_closed(self) -> None:
        import mothership.flight_io as flight_io

        payload = canonical_json_bytes({"kind": "safe"})
        for mutation in ("add", "remove", "replace"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(os.path.realpath(temporary)) / "bundle"
                events = [event(stage, number) for number, stage in enumerate(REQUIRED_STAGES)]
                events[0]["subject"] = dict(
                    events[0]["subject"],  # type: ignore[arg-type]
                    storage="bundled",
                    location="artifacts/proof.json",
                    sha256=hashlib.sha256(payload).hexdigest(),
                )
                index = index_for(events, privacy_profile="portable-evidence")
                self.write_bundle(root, events, index=index, artifacts={"proof.json": payload})
                changed = False

                def mutate(label: str) -> None:
                    nonlocal changed
                    if label != "artifacts" or changed:
                        return
                    changed = True
                    proof = root / "artifacts" / "proof.json"
                    if mutation == "add":
                        (root / "artifacts" / "added.json").write_bytes(b"{}")
                    elif mutation == "remove":
                        proof.unlink()
                    else:
                        proof.rename(root.parent / "proof.original")
                        proof.write_bytes(payload)

                with mock.patch.object(flight_io, "_MEMBERSHIP_VERIFY_HOOK", mutate, create=True):
                    self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.load_flight_bundle(root))
                self.assertTrue(changed)

    def test_traversed_directory_component_swap_to_symlink_fails_closed(self) -> None:
        import mothership.flight_io as flight_io

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(os.path.realpath(temporary))
            component = base / "traversed-component"
            component.mkdir()
            root = component / "bundle"
            self.write_bundle(root)
            outside = base / "outside"
            outside.mkdir()
            marker = outside / "marker"
            marker.write_bytes(b"unchanged")
            changed = False

            def swap(name: str) -> None:
                nonlocal changed
                if name != component.name or changed:
                    return
                changed = True
                component.rename(base / "moved-component")
                component.symlink_to(outside, target_is_directory=True)

            with mock.patch.object(flight_io, "_COMPONENT_OPEN_HOOK", swap, create=True):
                self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.load_flight_bundle(root))
            self.assertTrue(changed)
            self.assertEqual(b"unchanged", marker.read_bytes())
            self.assertEqual({"marker"}, {item.name for item in outside.iterdir()})

    def test_loader_blocks_leaf_swap_without_ambient_capabilities(self) -> None:
        import mothership.flight_io as flight_io

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(os.path.realpath(temporary))
            root = base / "bundle"
            self.write_bundle(root)
            actual_open = flight_io.os.open
            replaced = False

            def race_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
                nonlocal replaced
                if path == "events.jsonl" and not replaced:
                    replaced = True
                    (root / "events.jsonl").unlink()
                    (root / "events.jsonl").symlink_to(root / "flight.json")
                return actual_open(path, flags, *args, **kwargs)

            forbidden = mock.Mock(side_effect=AssertionError("ambient capability used"))
            with (
                mock.patch.object(flight_io.os, "open", side_effect=race_open),
                mock.patch("subprocess.run", forbidden),
                mock.patch("socket.socket", forbidden),
                mock.patch.object(Path, "home", forbidden),
                mock.patch.object(flight_io.os, "environ", forbidden),
            ):
                self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.load_flight_bundle(root))

    def test_import_generic_jsonl_prevalidates_then_creates_deterministic_metadata_only_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(os.path.realpath(temporary))
            source = temporary_path / "generic.jsonl"
            generic_events = [event(stage, number, schema_version="mothership.generic-event.v1") for number, stage in enumerate(REQUIRED_STAGES)]
            source_bytes = b"".join(canonical_json_bytes(item) + b"\n" for item in generic_events)
            source.write_bytes(source_bytes)
            before = source.read_bytes()
            output = temporary_path / "OUTPUT"
            outside = temporary_path / "outside-target.txt"
            outside.write_bytes(b"unchanged")

            bundle = self.import_generic_jsonl(source, output)

            self.assertEqual(before, source.read_bytes())
            self.assertEqual(b"unchanged", outside.read_bytes())
            self.assertEqual({"flight.json", "events.jsonl", "artifacts"}, {item.name for item in output.iterdir()})
            self.assertEqual(0o700, stat.S_IMODE(output.stat().st_mode))
            self.assertEqual(0o700, stat.S_IMODE((output / "artifacts").stat().st_mode))
            self.assertEqual(0o600, stat.S_IMODE((output / "flight.json").stat().st_mode))
            self.assertEqual(0o600, stat.S_IMODE((output / "events.jsonl").stat().st_mode))
            self.assertEqual("importer", bundle.index["producer_class"])
            self.assertEqual(REGISTRY_SHA256, bundle.index["protocol_registry_sha256"])
            self.assertEqual("metadata-only", bundle.index["privacy_profile"])
            self.assertEqual(list(REQUIRED_STAGES), bundle.index["required_stages"])
            self.assertEqual((), bundle.artifacts)
            self.assertEqual([item["event_id"] for item in generic_events], [item["event_id"] for item in bundle.events])
            self.assertEqual(
                b"".join(canonical_json_bytes(dict(item, schema_version="mothership.flight-event.v1")) + b"\n" for item in generic_events),
                bundle.events_bytes,
            )
            loaded = self.load_flight_bundle(output)
            self.assertEqual(bundle.index, loaded.index)
            self.assertEqual(bundle.events_bytes, loaded.events_bytes)

    def test_import_refuses_existing_target_and_mixed_or_invalid_input_without_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(os.path.realpath(temporary))
            source = temporary_path / "generic.jsonl"
            generic_events = [event(stage, number, schema_version="mothership.generic-event.v1") for number, stage in enumerate(REQUIRED_STAGES)]
            generic_events[1]["run_id"] = "run-other"
            source.write_bytes(b"".join(canonical_json_bytes(item) + b"\n" for item in generic_events))
            output = temporary_path / "OUTPUT"
            self.assert_flight_error("FLIGHT.INVALID.SCHEMA", lambda: self.import_generic_jsonl(source, output))
            self.assertFalse(output.exists())

            source.write_bytes(b'{"value":NaN}\n')
            self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.import_generic_jsonl(source, output))
            self.assertFalse(output.exists())

            output.mkdir()
            self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.import_generic_jsonl(source, output))

    def test_import_symlinked_parent_cannot_create_in_its_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(os.path.realpath(temporary))
            source = base / "generic.jsonl"
            generic_events = [
                event(stage, number, schema_version="mothership.generic-event.v1")
                for number, stage in enumerate(REQUIRED_STAGES)
            ]
            source.write_bytes(b"".join(canonical_json_bytes(item) + b"\n" for item in generic_events))
            destination = base / "destination"
            destination.mkdir()
            marker = destination / "marker"
            marker.write_bytes(b"unchanged")
            linked_parent = base / "linked-parent"
            linked_parent.symlink_to(destination, target_is_directory=True)

            self.assert_flight_error(
                "FLIGHT.INVALID.FILE",
                lambda: self.import_generic_jsonl(source, linked_parent / "OUTPUT"),
            )
            self.assertEqual(b"unchanged", marker.read_bytes())
            self.assertEqual({"marker"}, {item.name for item in destination.iterdir()})

    def test_import_target_swap_cannot_redirect_writes(self) -> None:
        import mothership.flight_io as flight_io

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(os.path.realpath(temporary))
            source = base / "generic.jsonl"
            generic_events = [
                event(stage, number, schema_version="mothership.generic-event.v1")
                for number, stage in enumerate(REQUIRED_STAGES)
            ]
            source.write_bytes(b"".join(canonical_json_bytes(item) + b"\n" for item in generic_events))
            output = base / "OUTPUT"
            outside = base / "outside"
            outside.mkdir(0o700)
            marker = outside / "marker"
            marker.write_bytes(b"unchanged")
            changed = False

            def swap(name: str) -> None:
                nonlocal changed
                if name != output.name or changed or not output.exists():
                    return
                changed = True
                output.rename(base / "moved-created-output")
                outside.rename(output)

            with mock.patch.object(flight_io, "_COMPONENT_OPEN_HOOK", swap, create=True):
                self.assert_flight_error("FLIGHT.INVALID.FILE", lambda: self.import_generic_jsonl(source, output))
            self.assertTrue(changed)
            self.assertEqual(b"unchanged", (output / "marker").read_bytes())
            self.assertEqual({"marker"}, {item.name for item in output.iterdir()})

    def test_import_keeps_all_required_stages_and_rejects_bundled_subjects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(os.path.realpath(temporary))
            source = temporary_path / "generic.jsonl"
            generic_events = [event(stage, number, schema_version="mothership.generic-event.v1") for number, stage in enumerate(REQUIRED_STAGES[:-1])]
            source.write_bytes(b"".join(canonical_json_bytes(item) + b"\n" for item in generic_events))
            output = temporary_path / "OUTPUT"
            bundle = self.import_generic_jsonl(source, output)
            self.assertEqual(list(REQUIRED_STAGES), bundle.index["required_stages"])

        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(os.path.realpath(temporary))
            source = temporary_path / "generic.jsonl"
            generic_events = [event(stage, number, schema_version="mothership.generic-event.v1") for number, stage in enumerate(REQUIRED_STAGES)]
            generic_events[0]["subject"] = dict(generic_events[0]["subject"], storage="bundled", location="artifacts/proof.json")  # type: ignore[arg-type]
            source.write_bytes(b"".join(canonical_json_bytes(item) + b"\n" for item in generic_events))
            output = temporary_path / "OUTPUT"
            self.assert_flight_error("FLIGHT.INVALID.PRIVACY", lambda: self.import_generic_jsonl(source, output))
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
