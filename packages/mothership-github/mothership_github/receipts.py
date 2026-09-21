"""Closed, append-only GitHub execution-attempt receipts.

The authority ledger remains the source of truth for approval and consumption.
This module only records the bounded attempt that follows a real consume event.
Its parser and append/rollback path are deliberately separate from the
authority-ledger event validators.
"""

from __future__ import annotations

from collections.abc import Mapping
import copy
import datetime
import os
import pathlib
import re
import stat
import typing
import uuid

from orchestration.lib import action_authority, action_authority_ledger, canonical, jsonio
from orchestration.lib.errors import ContractError


_SCHEMA_VERSION = "github-execution-attempt.v1"
_UTC_TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"
_EVENT_ID = re.compile(r"event-[0-9a-f]{32}\Z")
_ACTION_ID = re.compile(r"act-[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MERGE_SHA = re.compile(r"[0-9a-f]{40}\Z")
_READ_CHUNK_SIZE = 64 * 1024
_START_KEYS = frozenset(
    {
        "schema_version",
        "event_type",
        "event_id",
        "action_id",
        "action_sha256",
        "consume_event_id",
        "recorded_at",
    }
)
_FINISH_KEYS = frozenset(
    {
        "schema_version",
        "event_type",
        "event_id",
        "attempt_started_event_id",
        "action_id",
        "action_sha256",
        "consume_event_id",
        "outcome",
        "observation",
        "recorded_at",
    }
)
_OBSERVATION_KEYS = frozenset({"http_status", "merged", "merge_commit_sha"})
_OUTCOMES = frozenset({"success", "failure", "reconciliation_required"})


class ReceiptError(Exception):
    """Base class for receipt-ledger failures."""


class ReceiptPathError(ReceiptError):
    """A receipt path is unsafe or aliases the authority ledger."""


class ReceiptBindingError(ReceiptError):
    """A receipt input does not bind to the durable authority or start row."""


class ReceiptValidationError(ReceiptError):
    """A generated or supplied receipt violates the closed receipt contract."""


class MalformedReceiptError(ReceiptValidationError):
    """The complete receipt history is malformed or has broken relationships."""


class ReceiptReplayError(ReceiptBindingError):
    """The one-shot consume or attempt already has a receipt."""


class ReceiptIOError(ReceiptError):
    """A receipt append, flush, fsync, rollback, or quarantine failed."""


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0)


def _format_utc(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).strftime(_UTC_TIMESTAMP)


def _parse_utc(value: object, *, error: type[ReceiptError] = MalformedReceiptError) -> datetime.datetime:
    if type(value) is not str:
        raise error("timestamp is invalid")
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
        raise error("timestamp is invalid")
    try:
        return datetime.datetime.strptime(value, _UTC_TIMESTAMP).replace(tzinfo=datetime.UTC)
    except ValueError:
        raise error("timestamp is invalid") from None


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _same_json(left: object, right: object) -> bool:
    try:
        return canonical.canonical_json_bytes(_plain(left)) == canonical.canonical_json_bytes(_plain(right))
    except Exception:
        return False


def _require_path(value: object, label: str) -> pathlib.Path:
    if not isinstance(value, pathlib.Path):
        raise ReceiptPathError(f"{label} must be a pathlib.Path")
    text = os.fspath(value)
    if (
        not value.is_absolute()
        or text == os.path.sep
        or os.path.normpath(text) != text
        or "\x00" in text
    ):
        raise ReceiptPathError(f"{label} must be normalized and absolute")
    return value


def _require_distinct_paths(receipt_path: pathlib.Path, authority_path: pathlib.Path) -> None:
    if receipt_path == authority_path:
        raise ReceiptPathError("receipt and authority paths must be distinct")


def _read_chunk(descriptor: int, size: int) -> bytes:
    return action_authority_ledger._read_chunk(descriptor, size)


def _flush(handle: typing.BinaryIO) -> None:
    action_authority_ledger._flush(handle)


def _fsync(descriptor: int) -> None:
    action_authority_ledger._fsync(descriptor)


def _ftruncate(descriptor: int, size: int) -> None:
    os.ftruncate(descriptor, size)


def _fchmod(descriptor: int, mode: int) -> None:
    os.fchmod(descriptor, mode)


def _read_raw_locked(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        while True:
            block = _read_chunk(descriptor, _READ_CHUNK_SIZE)
            if not block:
                return b"".join(chunks)
            chunks.append(block)
    except OSError:
        raise ReceiptIOError("receipt ledger could not be read") from None


def _validate_observation(value: object) -> dict[str, object]:
    if type(value) is not dict and not isinstance(value, Mapping):
        raise ReceiptValidationError("observation must be a mapping")
    observation = dict(value)
    if set(observation) != _OBSERVATION_KEYS:
        raise ReceiptValidationError("observation contains unknown or missing fields")
    http_status = observation["http_status"]
    if type(http_status) is not int or http_status != 0 and not 100 <= http_status <= 599:
        raise ReceiptValidationError("observation http_status is invalid")
    merged = observation["merged"]
    if merged is not None and type(merged) is not bool:
        raise ReceiptValidationError("observation merged is invalid")
    merge_commit_sha = observation["merge_commit_sha"]
    if merge_commit_sha is not None:
        if type(merge_commit_sha) is not str or _MERGE_SHA.fullmatch(merge_commit_sha) is None:
            raise ReceiptValidationError("observation merge_commit_sha is invalid")
    return {
        "http_status": http_status,
        "merged": merged,
        "merge_commit_sha": merge_commit_sha,
    }


def _validate_event(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise MalformedReceiptError("receipt row is not an object")
    event_type = value.get("event_type")
    expected = _START_KEYS if event_type == "attempt_started" else _FINISH_KEYS if event_type == "attempt_finished" else None
    if expected is None or value.get("schema_version") != _SCHEMA_VERSION or set(value) != expected:
        raise MalformedReceiptError("receipt row has an invalid closed shape")
    event_id = value.get("event_id")
    if type(event_id) is not str or _EVENT_ID.fullmatch(event_id) is None:
        raise MalformedReceiptError("receipt event id is invalid")
    action_id = value.get("action_id")
    if type(action_id) is not str or _ACTION_ID.fullmatch(action_id) is None:
        raise MalformedReceiptError("receipt action id is invalid")
    digest = value.get("action_sha256")
    if type(digest) is not str or _DIGEST.fullmatch(digest) is None:
        raise MalformedReceiptError("receipt action digest is invalid")
    _parse_utc(value.get("recorded_at"))
    consume_id = value.get("consume_event_id")
    if type(consume_id) is not str or _EVENT_ID.fullmatch(consume_id) is None:
        raise MalformedReceiptError("receipt consume event id is invalid")
    if event_type == "attempt_started":
        return copy.deepcopy(value)
    start_id = value.get("attempt_started_event_id")
    if type(start_id) is not str or _EVENT_ID.fullmatch(start_id) is None:
        raise MalformedReceiptError("receipt start event id is invalid")
    outcome = value.get("outcome")
    if type(outcome) is not str or outcome not in _OUTCOMES:
        raise MalformedReceiptError("receipt outcome is invalid")
    observation = _validate_observation(value.get("observation"))
    result = copy.deepcopy(value)
    result["observation"] = observation
    if outcome == "success":
        if not (
            observation["http_status"] == 200
            and observation["merged"] is True
            and type(observation["merge_commit_sha"]) is str
            and _MERGE_SHA.fullmatch(observation["merge_commit_sha"]) is not None
        ):
            raise MalformedReceiptError("success lacks strong normalized observation")
    if outcome == "failure" and (
        observation["merged"] is True or observation["merge_commit_sha"] is not None
    ):
        raise MalformedReceiptError("failure contains positive merge observation")
    return result


def _validate_history(events: list[dict[str, object]]) -> None:
    seen_ids: set[str] = set()
    starts_by_id: dict[str, dict[str, object]] = {}
    starts_by_consume: set[str] = set()
    starts_by_action: set[str] = set()
    finished_for_start: set[str] = set()
    for event in events:
        checked = _validate_event(event)
        event_id = typing.cast(str, checked["event_id"])
        if event_id in seen_ids:
            raise MalformedReceiptError("receipt history contains a duplicate event id")
        seen_ids.add(event_id)
        if checked["event_type"] == "attempt_started":
            consume_id = typing.cast(str, checked["consume_event_id"])
            action_id = typing.cast(str, checked["action_id"])
            if consume_id in starts_by_consume or action_id in starts_by_action:
                raise MalformedReceiptError("receipt history contains a duplicate start")
            starts_by_consume.add(consume_id)
            starts_by_action.add(action_id)
            starts_by_id[event_id] = checked
            continue
        start_id = typing.cast(str, checked["attempt_started_event_id"])
        start = starts_by_id.get(start_id)
        if start is None:
            raise MalformedReceiptError("receipt finish is orphaned or out of order")
        if start_id in finished_for_start:
            raise MalformedReceiptError("receipt start has more than one finish")
        if any(checked[key] != start[key] for key in ("action_id", "action_sha256", "consume_event_id")):
            raise MalformedReceiptError("receipt finish is rebound to another start")
        start_time = _parse_utc(start["recorded_at"])
        finish_time = _parse_utc(checked["recorded_at"])
        if finish_time < start_time:
            raise MalformedReceiptError("receipt finish precedes its start")
        finished_for_start.add(start_id)


def _read_history_locked(descriptor: int) -> tuple[list[dict[str, object]], bytes]:
    raw = _read_raw_locked(descriptor)
    if not raw:
        return [], raw
    if not raw.endswith(b"\n"):
        raise MalformedReceiptError("receipt ledger must end with LF")
    lines = raw[:-1].split(b"\n")
    if any(not line for line in lines):
        raise MalformedReceiptError("receipt ledger contains an empty line")
    events: list[dict[str, object]] = []
    try:
        for line in lines:
            events.append(_validate_event(jsonio.loads_strict(line)))
        _validate_history(events)
    except (ContractError, ReceiptValidationError, TypeError, ValueError):
        raise MalformedReceiptError("receipt ledger contains invalid history") from None
    return events, raw


def _write_all(handle: typing.BinaryIO, raw: bytes) -> None:
    try:
        action_authority_ledger._write_all(handle, raw)
    except action_authority_ledger.LedgerIOError:
        raise ReceiptIOError("receipt append failed") from None


def _quarantine_unconfirmed(
    descriptor: int, preappend: bytes, receipt_path: pathlib.Path
) -> None:
    # Mode quarantine is the preferred receipt-specific fail-closed state.
    try:
        _fchmod(descriptor, 0o000)
        descriptor_info = os.fstat(descriptor)
        path_info = os.lstat(receipt_path)
        if (
            stat.S_ISREG(descriptor_info.st_mode)
            and stat.S_IMODE(descriptor_info.st_mode) == 0
            and stat.S_ISREG(path_info.st_mode)
            and (path_info.st_dev, path_info.st_ino) == (descriptor_info.st_dev, descriptor_info.st_ino)
            and stat.S_IMODE(path_info.st_mode) == 0
        ):
            return
    except (OSError, TypeError, ValueError):
        pass

    # If mode changes are unavailable, poison the exact open inode.  A NUL
    # appended after a valid JSONL document is necessarily malformed history.
    try:
        # The descriptor is opened with O_APPEND.  Truncate to the exact
        # preappend boundary, then one append produces precisely one poison
        # byte (and cannot leave an unverified zero plus a second byte).
        _ftruncate(descriptor, len(preappend))
        os.lseek(descriptor, len(preappend), os.SEEK_SET)
        if os.write(descriptor, b"\x00") != 1:
            raise OSError("receipt poison write failed")
        if _read_raw_locked(descriptor) != preappend + b"\x00":
            raise OSError("receipt poison verification failed")
        try:
            _read_history_locked(descriptor)
        except MalformedReceiptError:
            return
        raise OSError("receipt poison remained parseable")
    except (ReceiptError, OSError, TypeError, ValueError):
        pass

    try:
        descriptor_info = os.fstat(descriptor)
        path_info = os.lstat(receipt_path)
        identity = (descriptor_info.st_dev, descriptor_info.st_ino)
        if not stat.S_ISREG(path_info.st_mode) or (path_info.st_dev, path_info.st_ino) != identity:
            raise OSError("receipt path identity changed")
        os.chmod(receipt_path, 0o000, follow_symlinks=False)
        after = os.fstat(descriptor)
        path_after = os.lstat(receipt_path)
        if (
            stat.S_IMODE(after.st_mode) != 0
            or stat.S_IMODE(path_after.st_mode) != 0
            or (after.st_dev, after.st_ino) != identity
            or (path_after.st_dev, path_after.st_ino) != identity
        ):
            raise OSError("receipt mode quarantine could not be confirmed")
    except (OSError, TypeError, ValueError, NotImplementedError):
        raise ReceiptIOError("receipt quarantine could not be confirmed") from None


def _restore_preappend_state(
    descriptor: int,
    handle: typing.BinaryIO,
    preappend: bytes,
    receipt_path: pathlib.Path,
) -> bool:
    try:
        _ftruncate(descriptor, len(preappend))
        if os.fstat(descriptor).st_size != len(preappend):
            raise OSError("receipt rollback size mismatch")
        _flush(handle)
        _fsync(descriptor)
        if _read_raw_locked(descriptor) != preappend:
            raise OSError("receipt rollback bytes mismatch")
        return True
    except (ReceiptError, OSError, TypeError, ValueError):
        _quarantine_unconfirmed(descriptor, preappend, receipt_path)
        return False


def _append_receipt_locked(
    descriptor: int,
    handle: typing.BinaryIO,
    prior_events: list[dict[str, object]],
    prior_raw: bytes,
    event: dict[str, object],
    receipt_path: pathlib.Path,
) -> dict[str, object]:
    _validate_history([*prior_events, event])
    raw = canonical.canonical_json_bytes(event) + b"\n"
    try:
        if os.fstat(descriptor).st_size != len(prior_raw):
            raise ReceiptIOError("receipt ledger changed while locked")
        _write_all(handle, raw)
        _flush(handle)
        _fsync(descriptor)
    except (ReceiptError, OSError):
        if _restore_preappend_state(descriptor, handle, prior_raw, receipt_path):
            raise ReceiptIOError("receipt append failed and was rolled back") from None
        raise ReceiptIOError("receipt append failed and rollback was quarantined") from None
    return copy.deepcopy(event)


def _capture_authority_fact(
    authority_path: pathlib.Path, consume_event: object, action: object
) -> tuple[
    tuple[int, int],
    dict[str, object],
    dict[str, object],
    dict[str, tuple[dict[str, object], dict[str, object]]],
]:
    supplied_consume = dict(consume_event) if isinstance(consume_event, Mapping) else None
    if supplied_consume is None:
        raise ReceiptBindingError("consume event must be a mapping")
    supplied_id = supplied_consume.get("event_id")
    if type(supplied_id) is not str or _EVENT_ID.fullmatch(supplied_id) is None:
        raise ReceiptBindingError("consume event id is invalid")
    try:
        with action_authority_ledger._locked_ledger(authority_path) as (descriptor, _handle):
            info = os.fstat(descriptor)
            events = action_authority_ledger._read_locked(descriptor)
            durable = next((row for row in events if row.get("event_id") == supplied_id), None)
            if durable is None or durable.get("event_type") != "authority_action_consume":
                raise ReceiptBindingError("consume event does not exist in authority history")
            if not _same_json(supplied_consume, durable):
                raise ReceiptBindingError("consume event differs from authority history")
            approval_id = durable.get("approval_event_id")
            consume_index = events.index(durable)
            approval = next(
                (
                    row
                    for row in events[:consume_index]
                    if row.get("event_type") == "authority_action_approval"
                    and row.get("event_id") == approval_id
                ),
                None,
            )
            if approval is None or approval.get("decision") != "approve":
                raise ReceiptBindingError("consume event lacks its earlier approval")
            approval_action = typing.cast(dict[str, object], approval["action"])
            try:
                if action_authority.action_sha256(copy.deepcopy(approval_action)) != approval["action_sha256"]:
                    raise ReceiptBindingError("authority approval action digest is invalid")
            except action_authority.ActionAuthorityError:
                raise ReceiptBindingError("authority approval action is invalid") from None
            supplied_action = _plain(action)
            if not isinstance(supplied_action, dict) or not _same_json(supplied_action, approval_action):
                raise ReceiptBindingError("action differs from consumed authority")
            if (
                durable.get("action_id") != approval_action.get("action_id")
                or durable.get("action_sha256") != approval.get("action_sha256")
            ):
                raise ReceiptBindingError("consume event action binding is invalid")
            authority_facts: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
            approvals = {
                typing.cast(str, row["event_id"]): row
                for row in events
                if row.get("event_type") == "authority_action_approval"
            }
            for row in events:
                if row.get("event_type") != "authority_action_consume":
                    continue
                row_approval = approvals.get(typing.cast(str, row["approval_event_id"]))
                if row_approval is None:
                    raise ReceiptBindingError("authority consume lacks its approval snapshot")
                authority_facts[typing.cast(str, row["event_id"])] = (
                    copy.deepcopy(row),
                    copy.deepcopy(typing.cast(dict[str, object], row_approval["action"])),
                )
            return (
                (info.st_dev, info.st_ino),
                copy.deepcopy(durable),
                copy.deepcopy(approval_action),
                authority_facts,
            )
    except ReceiptError:
        raise
    except action_authority_ledger.MalformedLedgerStateError:
        raise ReceiptBindingError("authority history is malformed") from None
    except action_authority_ledger.LedgerIOError:
        raise ReceiptIOError("authority history could not be read") from None


def _new_event_id(existing: set[str]) -> str:
    candidate = "event-" + uuid.uuid4().hex
    if candidate in existing:
        raise ReceiptIOError("receipt event id collision")
    return candidate


def record_attempt_started(
    receipt_path: pathlib.Path,
    authority_path: pathlib.Path,
    consume_event: Mapping[str, object],
    action: Mapping[str, object],
) -> dict[str, object]:
    """Persist one attempt start bound to an actually consumed authority row."""

    checked_receipt = _require_path(receipt_path, "receipt path")
    checked_authority = _require_path(authority_path, "authority path")
    _require_distinct_paths(checked_receipt, checked_authority)
    authority_identity, durable_consume, durable_action, authority_facts = _capture_authority_fact(
        checked_authority, consume_event, action
    )
    consumed_at = _parse_utc(durable_consume.get("consumed_at"), error=ReceiptBindingError)
    try:
        with action_authority_ledger._locked_ledger(checked_receipt) as (descriptor, handle):
            receipt_info = os.fstat(descriptor)
            if (receipt_info.st_dev, receipt_info.st_ino) == authority_identity:
                raise ReceiptPathError("receipt and authority paths alias the same inode")
            prior_events, prior_raw = _read_history_locked(descriptor)
            for prior in prior_events:
                if prior["event_type"] != "attempt_started":
                    continue
                prior_consume_id = typing.cast(str, prior["consume_event_id"])
                authority_fact = authority_facts.get(prior_consume_id)
                if authority_fact is None:
                    raise ReceiptBindingError("existing receipt start lacks an authority consume")
                authoritative_consume, authoritative_action = authority_fact
                if (
                    prior["action_id"] != authoritative_consume["action_id"]
                    or prior["action_sha256"] != authoritative_consume["action_sha256"]
                    or authoritative_consume["action_sha256"] != action_authority.action_sha256(
                        copy.deepcopy(authoritative_action)
                    )
                    or _parse_utc(prior["recorded_at"]) < _parse_utc(
                        authoritative_consume["consumed_at"]
                    )
                ):
                    raise ReceiptBindingError("existing receipt start is not bound to authority")
            consume_id = typing.cast(str, durable_consume["event_id"])
            action_id = typing.cast(str, durable_action["action_id"])
            digest = typing.cast(str, durable_consume["action_sha256"])
            now = _utc_now()
            if now < consumed_at:
                raise ReceiptValidationError("attempt start precedes authority consume")
            if any(
                row["event_type"] == "attempt_started"
                and (row["consume_event_id"] == consume_id or row["action_id"] == action_id)
                for row in prior_events
            ):
                raise ReceiptReplayError("consume event or action already has an attempt start")
            event = {
                "schema_version": _SCHEMA_VERSION,
                "event_type": "attempt_started",
                "event_id": _new_event_id({typing.cast(str, row["event_id"]) for row in prior_events}),
                "action_id": action_id,
                "action_sha256": digest,
                "consume_event_id": consume_id,
                "recorded_at": _format_utc(now),
            }
            return _append_receipt_locked(
                descriptor, handle, prior_events, prior_raw, event, checked_receipt
            )
    except ReceiptError:
        raise
    except action_authority_ledger.LedgerIOError:
        raise ReceiptIOError("receipt ledger could not be opened or locked") from None


def record_attempt_finished(
    receipt_path: pathlib.Path,
    started: Mapping[str, object],
    outcome: str,
    observation: Mapping[str, object],
) -> dict[str, object]:
    """Persist one terminal attempt row after validating the stored start byte-for-byte."""

    checked_receipt = _require_path(receipt_path, "receipt path")
    if not isinstance(started, Mapping):
        raise ReceiptBindingError("started receipt must be a mapping")
    supplied_started = dict(started)
    start_id = supplied_started.get("event_id")
    if type(start_id) is not str or _EVENT_ID.fullmatch(start_id) is None:
        raise ReceiptBindingError("started receipt event id is invalid")
    if type(outcome) is not str or outcome not in _OUTCOMES:
        raise ReceiptValidationError("outcome is invalid")
    normalized_observation = _validate_observation(observation)
    with action_authority_ledger._locked_ledger(checked_receipt) as (descriptor, handle):
        receipt_info = os.fstat(descriptor)
        if not stat.S_ISREG(receipt_info.st_mode) or stat.S_IMODE(receipt_info.st_mode) != 0o600:
            raise ReceiptPathError("receipt ledger must be a regular 0600 file")
        prior_events, prior_raw = _read_history_locked(descriptor)
        stored = next(
            (
                row
                for row in prior_events
                if row["event_type"] == "attempt_started" and row["event_id"] == start_id
            ),
            None,
        )
        if stored is None or not _same_json(supplied_started, stored):
            raise ReceiptBindingError("started receipt is not the stored byte-equivalent start")
        if any(
            row["event_type"] == "attempt_finished"
            and row["attempt_started_event_id"] == start_id
            for row in prior_events
        ):
            raise ReceiptReplayError("attempt already has a terminal receipt")
        now = _utc_now()
        if now < _parse_utc(stored["recorded_at"]):
            raise ReceiptValidationError("attempt finish precedes start")
        event = {
            "schema_version": _SCHEMA_VERSION,
            "event_type": "attempt_finished",
            "event_id": _new_event_id({typing.cast(str, row["event_id"]) for row in prior_events}),
            "attempt_started_event_id": start_id,
            "action_id": stored["action_id"],
            "action_sha256": stored["action_sha256"],
            "consume_event_id": stored["consume_event_id"],
            "outcome": outcome,
            "observation": normalized_observation,
            "recorded_at": _format_utc(now),
        }
        return _append_receipt_locked(
            descriptor, handle, prior_events, prior_raw, event, checked_receipt
        )


__all__ = [
    "MalformedReceiptError",
    "ReceiptBindingError",
    "ReceiptError",
    "ReceiptIOError",
    "ReceiptPathError",
    "ReceiptReplayError",
    "ReceiptValidationError",
    "record_attempt_finished",
    "record_attempt_started",
]
