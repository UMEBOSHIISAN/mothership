from __future__ import annotations

import copy
from importlib import resources
import inspect
import unittest


DIGEST = "a" * 64
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
VERDICTS = ("COMPLETE", "INCOMPLETE", "DRIFTED", "INVALID")
ACTION_CLASSES = (
    "none",
    "read_only",
    "file_write",
    "process_execute",
    "network_access",
    "credential_access",
    "deploy",
    "scheduler_change",
    "infrastructure_change",
)
OUTCOMES = (
    "recorded",
    "proposed",
    "approved",
    "started",
    "succeeded",
    "failed",
    "verified",
    "persisted",
    "observed",
)
PRIVACY_PROFILES = ("metadata-only", "portable-evidence")


INDEX_KEYS = {
    "schema_version",
    "run_id",
    "created_at",
    "producer_class",
    "event_ids",
    "required_stages",
    "protocol_registry_sha256",
    "privacy_profile",
    "bundle_sha256",
    "declared_verdict",
}
EVENT_KEYS = {
    "schema_version",
    "event_id",
    "run_id",
    "event_type",
    "stage",
    "occurred_at",
    "producer_class",
    "tool_id",
    "predecessor_event_ids",
    "subject",
    "scope_sha256",
    "action_class",
    "authority_effect",
    "execution_effect",
    "outcome_status",
    "redaction",
    "extension",
}


def flight_index() -> dict[str, object]:
    return {
        "schema_version": "mothership.flight-index.v1",
        "run_id": "run-safe-001",
        "created_at": "2026-08-12T00:00:00Z",
        "producer_class": "synthetic",
        "event_ids": ["event-intent", "event-scope"],
        "required_stages": list(REQUIRED_STAGES),
        "protocol_registry_sha256": DIGEST,
        "privacy_profile": "metadata-only",
        "bundle_sha256": None,
        "declared_verdict": None,
    }


def flight_event(schema_version: str = "mothership.flight-event.v1") -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "event_id": "event-intent",
        "run_id": "run-safe-001",
        "event_type": "request_recorded",
        "stage": "intent",
        "occurred_at": "2026-08-12T00:00:00Z",
        "producer_class": "synthetic",
        "tool_id": None,
        "predecessor_event_ids": [],
        "subject": {
            "storage": "external",
            "protocol_kind": "frontdoor-task",
            "schema_version": "intake.v0",
            "location": "refs/intent.json",
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


class FlightContractTests(unittest.TestCase):
    def setUp(self) -> None:
        from mothership.flight_contracts import (
            FlightError,
            validate_flight_event,
            validate_flight_index,
            validate_generic_event,
            validate_safe_metadata,
        )

        self.FlightError = FlightError
        self.validate_flight_event = validate_flight_event
        self.validate_flight_index = validate_flight_index
        self.validate_generic_event = validate_generic_event
        self.validate_safe_metadata = validate_safe_metadata

    def assert_invalid(self, validator: object, value: object, rule_id: str = "FLIGHT.INVALID.SCHEMA") -> None:
        with self.assertRaises(self.FlightError) as raised:
            validator(value)  # type: ignore[operator]
        self.assertEqual("INVALID", raised.exception.verdict)
        self.assertEqual(rule_id, raised.exception.rule_id)

    def test_public_contract_surface_and_exact_constants(self) -> None:
        import mothership.flight_contracts as contracts

        self.assertEqual(REQUIRED_STAGES, contracts.REQUIRED_STAGES)
        self.assertEqual(VERDICTS, contracts.VERDICTS)
        self.assertEqual(ACTION_CLASSES, contracts.ACTION_CLASSES)
        self.assertEqual(
            ("value",),
            tuple(inspect.signature(contracts.validate_safe_metadata).parameters),
        )
        for validator in (
            contracts.validate_flight_index,
            contracts.validate_flight_event,
            contracts.validate_generic_event,
        ):
            with self.subTest(validator=validator.__name__):
                self.assertEqual(("value",), tuple(inspect.signature(validator).parameters))

        error = contracts.FlightError("INVALID", "FLIGHT.INVALID.SCHEMA")
        self.assertEqual("INVALID", error.verdict)
        self.assertEqual("FLIGHT.INVALID.SCHEMA", error.rule_id)
        self.assertEqual("FLIGHT.INVALID.SCHEMA", str(error))

    def test_flight_index_accepts_only_the_exact_closed_shape_and_returns_a_detached_copy(self) -> None:
        value = flight_index()
        validated = self.validate_flight_index(value)
        self.assertEqual(value, validated)
        self.assertIsNot(value, validated)
        validated["event_ids"].append("event-result")  # type: ignore[index,union-attr]
        self.assertEqual(["event-intent", "event-scope"], value["event_ids"])
        for field in INDEX_KEYS:
            with self.subTest(missing=field):
                invalid = flight_index()
                del invalid[field]
                self.assert_invalid(self.validate_flight_index, invalid)
        self.assert_invalid(self.validate_flight_index, dict(flight_index(), unknown=True))

    def test_flight_index_rejects_noncanonical_stage_identifier_digest_privacy_and_verdict_values(self) -> None:
        invalid_values = (
            dict(flight_index(), run_id=""),
            dict(flight_index(), created_at="2026-08-12T00:00:00+00:00"),
            dict(flight_index(), producer_class="operator"),
            dict(flight_index(), event_ids=[]),
            dict(flight_index(), event_ids=["event-intent", "event-intent"]),
            dict(flight_index(), required_stages=list(REQUIRED_STAGES[:-1])),
            dict(flight_index(), protocol_registry_sha256="A" * 64),
            dict(flight_index(), privacy_profile="private"),
            dict(flight_index(), bundle_sha256="g" * 64),
            dict(flight_index(), declared_verdict="PASSED"),
        )
        for value in invalid_values:
            with self.subTest(value=value):
                self.assert_invalid(self.validate_flight_index, value)

    def test_flight_event_accepts_the_exact_closed_shape_and_detaches_nested_data(self) -> None:
        value = flight_event()
        validated = self.validate_flight_event(value)
        self.assertEqual(value, validated)
        self.assertIsNot(value, validated)
        validated["subject"]["location"] = "refs/changed.json"  # type: ignore[index]
        self.assertEqual("refs/intent.json", value["subject"]["location"])  # type: ignore[index]
        for field in EVENT_KEYS:
            with self.subTest(missing=field):
                invalid = flight_event()
                del invalid[field]
                self.assert_invalid(self.validate_flight_event, invalid)
        self.assert_invalid(self.validate_flight_event, dict(flight_event(), unknown=True))

    def test_flight_event_rejects_invalid_nested_shapes_enums_timestamps_and_boolean_integers(self) -> None:
        invalid_values = (
            dict(flight_event(), event_id="!event"),
            dict(flight_event(), stage="handoff"),
            dict(flight_event(), occurred_at="2026-08-12T00:00:00.000Z"),
            dict(flight_event(), tool_id=""),
            dict(flight_event(), predecessor_event_ids=["event-one", "event-one"]),
            dict(flight_event(), scope_sha256="A" * 64),
            dict(flight_event(), action_class="retry"),
            dict(flight_event(), authority_effect="false"),
            dict(flight_event(), execution_effect=0),
            dict(flight_event(), outcome_status="complete"),
            dict(flight_event(), redaction={"profile": "unknown", "removed_fields": 0}),
            dict(flight_event(), redaction={"profile": "metadata-only", "removed_fields": True}),
            dict(flight_event(), subject={"storage": "external"}),
        )
        for value in invalid_values:
            with self.subTest(value=value):
                self.assert_invalid(self.validate_flight_event, value)

    def test_flight_event_accepts_integral_json_numbers_but_not_booleans_for_removed_fields(self) -> None:
        value = flight_event()
        value["redaction"] = {"profile": "metadata-only", "removed_fields": 0.0}
        self.assertEqual(value, self.validate_flight_event(value))
        value["redaction"] = {"profile": "metadata-only", "removed_fields": True}
        self.assert_invalid(self.validate_flight_event, value)

    def test_flight_event_accepts_only_reference_extensions(self) -> None:
        value = flight_event()
        value["extension"] = {
            "namespace": "org.example.runtime",
            "schema_version": "1.0",
            "location": "artifacts/runtime-event.json",
            "content_sha256": DIGEST,
        }
        self.assertEqual(value, self.validate_flight_event(value))
        for extension in (
            {"namespace": "org.example.runtime"},
            dict(value["extension"], extra=True),  # type: ignore[arg-type]
            dict(value["extension"], location="../runtime-event.json"),  # type: ignore[arg-type]
            dict(value["extension"], content_sha256="A" * 64),  # type: ignore[arg-type]
        ):
            with self.subTest(extension=extension):
                invalid = flight_event()
                invalid["extension"] = extension
                self.assert_invalid(self.validate_flight_event, invalid)

    def test_subject_storage_is_data_only_and_never_performs_an_ambient_lookup(self) -> None:
        bundled = flight_event()
        bundled["subject"] = dict(bundled["subject"], storage="bundled", location="artifacts/missing.json")  # type: ignore[arg-type]
        self.assertEqual(bundled, self.validate_flight_event(bundled))
        external = flight_event()
        external["subject"] = dict(external["subject"], location="refs/not-present-anywhere.json")  # type: ignore[arg-type]
        self.assertEqual(external, self.validate_flight_event(external))
        for storage, location, rule_id in (
            ("bundled", "refs/intent.json", "FLIGHT.INVALID.SCHEMA"),
            ("bundled", "artifacts/../secret.json", "FLIGHT.INVALID.SCHEMA"),
            ("external", "/" + "private/intent.json", "FLIGHT.INVALID.PRIVACY"),
            ("external", "../intent.json", "FLIGHT.INVALID.SCHEMA"),
            ("external", "C:\\intent.json", "FLIGHT.INVALID.PRIVACY"),
        ):
            with self.subTest(storage=storage, location=location):
                invalid = flight_event()
                invalid["subject"] = dict(invalid["subject"], storage=storage, location=location)  # type: ignore[arg-type]
                self.assert_invalid(self.validate_flight_event, invalid, rule_id)

    def test_safe_metadata_rejects_raw_content_secret_like_keys_and_private_locations_at_any_depth(self) -> None:
        safe = {"summary": ["recorded", {"reference": "refs/intent.json"}]}
        validated = self.validate_safe_metadata(safe)
        self.assertEqual(safe, validated)
        self.assertIsNot(safe, validated)
        for invalid in (
            {"prompt": "do work"},
            {"nested": {"model_output": "raw"}},
            {"credential": "x"},
            {"token": "x"},
            {"secret": "x"},
            {"environment": "x"},
            {"api_key": "x"},
            {"nested": ["~/" + "private/file"]},
            {"nested": {"reference": "/" + "private/file"}},
            {"nested": "C:\\private\\file"},
        ):
            with self.subTest(invalid=invalid):
                self.assert_invalid(self.validate_safe_metadata, invalid, "FLIGHT.INVALID.PRIVACY")

    def test_safe_metadata_scans_containers_canonical_json_can_serialize(self) -> None:
        class MetadataDict(dict[str, object]):
            pass

        for invalid in (
            ({"token": "x"},),
            MetadataDict({"secret": "x"}),
        ):
            with self.subTest(invalid=invalid):
                self.assert_invalid(self.validate_safe_metadata, invalid, "FLIGHT.INVALID.PRIVACY")

    def test_deep_unknown_metadata_fails_closed_with_flight_error_not_recursion_error(self) -> None:
        nested: dict[str, object] = {}
        cursor = nested
        for _ in range(1_200):
            child: dict[str, object] = {}
            cursor["x"] = child
            cursor = child
        invalid = flight_event()
        invalid["unknown"] = nested
        self.assert_invalid(self.validate_flight_event, invalid)

    def test_raw_content_or_secret_like_metadata_is_rejected_from_every_event_depth(self) -> None:
        for value in (
            dict(flight_event(), subject=dict(flight_event()["subject"], token="x")),  # type: ignore[arg-type]
            dict(flight_event(), extension={"namespace": "org.example", "schema_version": "1", "location": "artifacts/x", "content_sha256": DIGEST, "secret": "x"}),
        ):
            with self.subTest(value=value):
                self.assert_invalid(self.validate_flight_event, value, "FLIGHT.INVALID.PRIVACY")

    def test_generic_event_uses_the_same_closed_shape_and_normalizes_to_flight_event_version(self) -> None:
        generic = flight_event("mothership.generic-event.v1")
        expected = copy.deepcopy(generic)
        expected["schema_version"] = "mothership.flight-event.v1"
        self.assertEqual(expected, self.validate_generic_event(generic))
        self.assert_invalid(self.validate_generic_event, flight_event())
        self.assert_invalid(self.validate_generic_event, dict(generic, unknown=True))

    def test_frozen_schemas_are_closed_and_match_the_python_contract_constants(self) -> None:
        from mothership.flight_contracts import ACTION_CLASSES as python_actions
        from mothership.flight_contracts import REQUIRED_STAGES as python_stages
        from mothership.flight_contracts import VERDICTS as python_verdicts
        from mothership.contracts import loads_strict

        expected = {
            "flight-index.v1.schema.json": ("mothership.flight-index.v1", INDEX_KEYS),
            "flight-event.v1.schema.json": ("mothership.flight-event.v1", EVENT_KEYS),
            "generic-event.v1.schema.json": ("mothership.generic-event.v1", EVENT_KEYS),
        }
        schema_root = resources.files("mothership.resources").joinpath("flight/schemas")
        for filename, (identifier, required) in expected.items():
            with self.subTest(filename=filename):
                schema = loads_strict(schema_root.joinpath(filename).read_bytes())
                self.assertEqual(identifier, schema["$id"])
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
                self.assertEqual(required, set(schema["required"]))
                self.assertIs(False, schema["additionalProperties"])
                timestamp_name = "created_at" if filename == "flight-index.v1.schema.json" else "occurred_at"
                self.assertEqual("date-time", schema["properties"][timestamp_name]["format"])
                self.assertEqual(list(python_stages), schema["properties"]["required_stages"]["const"] if filename == "flight-index.v1.schema.json" else schema["properties"]["stage"]["enum"])
                if filename != "flight-index.v1.schema.json":
                    self.assertEqual(list(python_actions), schema["properties"]["action_class"]["enum"])
                    self.assertEqual(list(OUTCOMES), schema["properties"]["outcome_status"]["enum"])
                    for nested in ("subject", "redaction"):
                        self.assertIs(False, schema["properties"][nested]["additionalProperties"])
                else:
                    self.assertEqual(list(python_verdicts), schema["properties"]["declared_verdict"]["anyOf"][1]["enum"])
