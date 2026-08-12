"""Closed, metadata-only contracts for portable Flight Recorder records."""

from __future__ import annotations

from datetime import datetime
import math
from pathlib import PurePosixPath
import re

from orchestration.lib.canonical import canonical_json_bytes
from orchestration.lib.jsonio import loads_strict


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

_PRODUCER_CLASSES = ("human", "agent", "tool", "importer", "synthetic")
_PRIVACY_PROFILES = ("metadata-only", "portable-evidence")
_OUTCOME_STATUSES = (
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
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_WINDOWS_DRIVE = re.compile(r"[A-Za-z]:")
_LOCAL_FILE_URI = re.compile(r'''(?:^|[\s"'(<\[{=])file:(?:/{1,3}|\\+)''', re.IGNORECASE)
_EMBEDDED_ABSOLUTE_PATH = re.compile(
    r'''(?:^|[\s"'(<\[{=`])(?:~[/\\]|//|/(?!/)|[A-Za-z]:[/\\]|\\\\)[A-Za-z0-9._~-]'''
)
_LOCATION = re.compile(
    r"(?![A-Za-z]:)(?!\.\.?$)(?!\.\.?/)(?!.*?/\.\.?/)(?!.*?/\.\.?$)[A-Za-z0-9._:-]+(?:/[A-Za-z0-9._:-]+)*"
)
_FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "prompt",
        "completion",
        "modeloutput",
        "credential",
        "credentials",
        "token",
        "tokens",
        "secret",
        "secrets",
        "environment",
        "env",
        "apikey",
        "authorization",
        "password",
        "privatekey",
        "clientsecret",
        "accesstoken",
        "refreshtoken",
    }
)


class FlightError(ValueError):
    def __init__(self, verdict: str, rule_id: str):
        self.verdict = verdict
        self.rule_id = rule_id
        super().__init__(rule_id)


def _schema_error() -> None:
    raise FlightError("INVALID", "FLIGHT.INVALID.SCHEMA")


def _privacy_error() -> None:
    raise FlightError("INVALID", "FLIGHT.INVALID.PRIVACY")


def _normalized_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isascii() and character.isalnum())


def _is_private_location(value: str) -> bool:
    return (
        value.startswith(("/", "~/"))
        or _WINDOWS_DRIVE.match(value) is not None
        or _LOCAL_FILE_URI.search(value) is not None
        or _EMBEDDED_ABSOLUTE_PATH.search(value) is not None
    )


def _validate_metadata(value: object) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                if type(key) is not str or _normalized_key(key) in _FORBIDDEN_METADATA_KEYS:
                    _privacy_error()
                pending.append(item)
        elif isinstance(current, (list, tuple)):
            pending.extend(current)
        elif type(current) is str and _is_private_location(current):
            _privacy_error()


def _detached_json(value: object) -> object:
    try:
        return loads_strict(canonical_json_bytes(value))
    except (RecursionError, TypeError, ValueError):
        _privacy_error()
    raise AssertionError("unreachable")


def validate_safe_metadata(value: object) -> object:
    """Return detached JSON-safe metadata while rejecting raw or private content."""

    _validate_metadata(value)
    return _detached_json(value)


def _object(value: object, keys: frozenset[str]) -> dict[str, object]:
    _validate_metadata(value)
    if type(value) is not dict or set(value) != keys:
        _schema_error()
    try:
        safe = _detached_json(value)
    except FlightError:
        _schema_error()
    if type(safe) is not dict:
        _schema_error()
    return safe


def _identifier(value: object) -> None:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        _schema_error()


def _digest(value: object, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        _schema_error()


def _location(value: object) -> None:
    if type(value) is not str or _is_private_location(value) or _LOCATION.fullmatch(value) is None:
        _schema_error()
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or parsed.as_posix() != value
        or any(part in ("", ".", "..") for part in parsed.parts)
    ):
        _schema_error()


def _timestamp(value: object) -> None:
    if type(value) is not str or _TIMESTAMP.fullmatch(value) is None:
        _schema_error()
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _schema_error()


def _unique_identifiers(value: object, *, nonempty: bool = False) -> None:
    if type(value) is not list or (nonempty and not value):
        _schema_error()
    for item in value:
        _identifier(item)
    if len(value) != len(set(value)):
        _schema_error()


def _enum(value: object, allowed: tuple[str, ...]) -> None:
    if type(value) is not str or value not in allowed:
        _schema_error()


def _boolean(value: object) -> None:
    if type(value) is not bool:
        _schema_error()


def _subject(value: object) -> None:
    subject = _object(
        value,
        frozenset({"storage", "protocol_kind", "schema_version", "location", "sha256"}),
    )
    _enum(subject["storage"], ("external", "bundled"))
    _identifier(subject["protocol_kind"])
    _identifier(subject["schema_version"])
    _location(subject["location"])
    _digest(subject["sha256"])
    if subject["storage"] == "bundled" and not subject["location"].startswith("artifacts/"):
        _schema_error()


def _redaction(value: object) -> None:
    redaction = _object(value, frozenset({"profile", "removed_fields"}))
    _enum(redaction["profile"], _PRIVACY_PROFILES)
    if not (
        type(redaction["removed_fields"]) is int
        or (
            type(redaction["removed_fields"]) is float
            and math.isfinite(redaction["removed_fields"])
            and redaction["removed_fields"].is_integer()
        )
    ) or redaction["removed_fields"] < 0:
        _schema_error()


def _extension(value: object) -> None:
    if value is None:
        return
    extension = _object(value, frozenset({"namespace", "schema_version", "location", "content_sha256"}))
    _identifier(extension["namespace"])
    _identifier(extension["schema_version"])
    _location(extension["location"])
    _digest(extension["content_sha256"])


def validate_flight_index(value: object) -> dict[str, object]:
    """Validate and detach the exact first-slice Flight Index record."""

    index = _object(
        value,
        frozenset(
            {
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
        ),
    )
    if index["schema_version"] != "mothership.flight-index.v1":
        _schema_error()
    _identifier(index["run_id"])
    _timestamp(index["created_at"])
    _enum(index["producer_class"], _PRODUCER_CLASSES)
    _unique_identifiers(index["event_ids"], nonempty=True)
    if index["required_stages"] != list(REQUIRED_STAGES):
        _schema_error()
    _digest(index["protocol_registry_sha256"])
    _enum(index["privacy_profile"], _PRIVACY_PROFILES)
    _digest(index["bundle_sha256"], nullable=True)
    if index["declared_verdict"] is not None:
        _enum(index["declared_verdict"], VERDICTS)
    return index


def _validate_event(value: object, schema_version: str) -> dict[str, object]:
    event = _object(
        value,
        frozenset(
            {
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
        ),
    )
    if event["schema_version"] != schema_version:
        _schema_error()
    _identifier(event["event_id"])
    _identifier(event["run_id"])
    _identifier(event["event_type"])
    _enum(event["stage"], REQUIRED_STAGES)
    _timestamp(event["occurred_at"])
    _enum(event["producer_class"], _PRODUCER_CLASSES)
    if event["tool_id"] is not None:
        _identifier(event["tool_id"])
    _unique_identifiers(event["predecessor_event_ids"])
    _subject(event["subject"])
    _digest(event["scope_sha256"], nullable=True)
    _enum(event["action_class"], ACTION_CLASSES)
    _boolean(event["authority_effect"])
    _boolean(event["execution_effect"])
    _enum(event["outcome_status"], _OUTCOME_STATUSES)
    _redaction(event["redaction"])
    _extension(event["extension"])
    return event


def validate_flight_event(value: object) -> dict[str, object]:
    """Validate and detach one closed Flight Event record."""

    return _validate_event(value, "mothership.flight-event.v1")


def validate_generic_event(value: object) -> dict[str, object]:
    """Validate Generic Event input and normalize it to the Flight Event form."""

    event = _validate_event(value, "mothership.generic-event.v1")
    event["schema_version"] = "mothership.flight-event.v1"
    return event


__all__ = (
    "ACTION_CLASSES",
    "FlightError",
    "REQUIRED_STAGES",
    "VERDICTS",
    "validate_flight_event",
    "validate_flight_index",
    "validate_generic_event",
    "validate_safe_metadata",
)
