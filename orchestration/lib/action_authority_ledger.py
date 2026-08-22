"""Dedicated atomic JSONL ledger for one-shot authority actions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import contextlib
import copy
import datetime
import fcntl
import os
import pathlib
import re
import stat
import typing
import uuid

from . import action_authority, canonical, contracts, jsonio
from .errors import ContractError


_READ_CHUNK_SIZE = 64 * 1024
_APPROVAL_TTL = datetime.timedelta(minutes=10)
_UTC_TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"
_EVENT_ID = re.compile(r"event-[0-9a-f]{32}\Z")
_ACTION_ID = re.compile(r"act-[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class ActionAuthorityLedgerError(ContractError):
    """Base error for the closed authority-action ledger boundary."""


class ActionEventValidationError(ActionAuthorityLedgerError):
    """Raised internally when one authority-action event is malformed."""


class MalformedLedgerStateError(ActionAuthorityLedgerError):
    """The complete ledger cannot be accepted as closed authority-action state."""


class LedgerIOError(ActionAuthorityLedgerError):
    """The ledger path, lock, local file, or durable write failed."""


class MissingApprovalError(ActionAuthorityLedgerError):
    """The requested approval event does not exist."""


class RejectedApprovalError(ActionAuthorityLedgerError):
    """The requested approval event is a rejection."""


class ExpiredApprovalError(ActionAuthorityLedgerError):
    """The requested approval is expired or not yet eligible."""


class ApprovalMismatchError(ActionAuthorityLedgerError):
    """The supplied action binding differs from the durable approval."""


class ApprovalReplayError(ActionAuthorityLedgerError):
    """The approval event has already been consumed."""


class ActionReplayError(ActionAuthorityLedgerError):
    """The one-time action instance has already been consumed."""


class _EventValidationError(ActionEventValidationError):
    pass


# Stable public vocabulary used by the Mothership facade.
ActionLedgerError = ActionAuthorityLedgerError
ActionLedgerIOError = LedgerIOError
ActionMalformedLedgerError = MalformedLedgerStateError
ActionMissingApprovalError = MissingApprovalError
ActionRejectedError = RejectedApprovalError
ActionAlreadyConsumedError = ApprovalReplayError
ActionAlreadyConsumedActionError = ActionReplayError


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0)


def _format_utc(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).strftime(_UTC_TIMESTAMP)


def _parse_utc(value: object) -> datetime.datetime:
    if type(value) is not str:
        raise _EventValidationError("timestamp is not text")
    try:
        return datetime.datetime.strptime(value, _UTC_TIMESTAMP).replace(
            tzinfo=datetime.UTC
        )
    except ValueError:
        raise _EventValidationError("timestamp is invalid") from None


def _new_event_id() -> str:
    return "event-" + uuid.uuid4().hex


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_plain(item) for item in value]
    return value


def _validated_event(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise _EventValidationError("ledger row is not an object")
    schema_version = value.get("schema_version")
    event_type = value.get("event_type")
    if (
        schema_version == "authority-action-approval.v0"
        and event_type == "authority_action_approval"
    ):
        kind = "authority-action-approval"
    elif (
        schema_version == "authority-action-consume.v0"
        and event_type == "authority_action_consume"
    ):
        kind = "authority-action-consume"
    else:
        raise _EventValidationError("ledger row belongs to another event family")
    try:
        checked = contracts.validate_contract(kind, value)
    except ContractError:
        raise _EventValidationError("ledger row violates its closed contract") from None

    if kind == "authority-action-approval":
        action = typing.cast(dict[str, object], checked["action"])
        try:
            digest = action_authority.action_sha256(copy.deepcopy(action))
        except action_authority.ActionAuthorityError:
            raise _EventValidationError("approval contains a malformed action") from None
        if checked["action_sha256"] != digest:
            raise _EventValidationError("approval action digest is invalid")
        recorded_at = _parse_utc(checked["recorded_at"])
        expires_at = _parse_utc(checked["expires_at"])
        if expires_at <= recorded_at or expires_at > recorded_at + _APPROVAL_TTL:
            raise _EventValidationError("approval deadline relationship is invalid")
    else:
        _parse_utc(checked["consumed_at"])
        _parse_utc(checked["expires_at"])
    return copy.deepcopy(checked)


def _validate_ledger_events(events: list[dict[str, object]]) -> None:
    by_id: dict[str, dict[str, object]] = {}
    consumed_approvals: set[str] = set()
    consumed_actions: set[str] = set()
    for event in events:
        event_id = typing.cast(str, event["event_id"])
        if event_id in by_id:
            raise _EventValidationError("ledger contains a duplicate event id")
        if event["event_type"] == "authority_action_approval":
            by_id[event_id] = event
            continue

        approval_event_id = typing.cast(str, event["approval_event_id"])
        approval = by_id.get(approval_event_id)
        if approval is None or approval["event_type"] != "authority_action_approval":
            raise _EventValidationError("consume does not reference an earlier approval")
        if approval["decision"] != "approve":
            raise _EventValidationError("consume references a rejection")
        action = typing.cast(dict[str, object], approval["action"])
        if event["action_id"] != action["action_id"]:
            raise _EventValidationError("consume action id differs from approval")
        if event["action_sha256"] != approval["action_sha256"]:
            raise _EventValidationError("consume digest differs from approval")
        if event["expires_at"] != approval["expires_at"]:
            raise _EventValidationError("consume expiry differs from approval")
        consumed_at = _parse_utc(event["consumed_at"])
        recorded_at = _parse_utc(approval["recorded_at"])
        expires_at = _parse_utc(approval["expires_at"])
        if consumed_at < recorded_at or consumed_at >= expires_at:
            raise _EventValidationError("consume time relationship is invalid")
        if approval_event_id in consumed_approvals:
            raise _EventValidationError("approval is consumed more than once")
        action_id = typing.cast(str, event["action_id"])
        if action_id in consumed_actions:
            raise _EventValidationError("action is consumed more than once")
        consumed_approvals.add(approval_event_id)
        consumed_actions.add(action_id)
        by_id[event_id] = event


def _require_ledger_path(value: object) -> pathlib.Path:
    if not isinstance(value, pathlib.Path):
        raise LedgerIOError("ledger path must be a pathlib.Path")
    text = os.fspath(value)
    if (
        not value.is_absolute()
        or text == os.path.sep
        or os.path.normpath(text) != text
        or "\x00" in text
    ):
        raise LedgerIOError("ledger path must be normalized and absolute")
    return value


def _verify_parent_directory(path: pathlib.Path) -> None:
    try:
        metadata = os.stat(path.parent, follow_symlinks=False)
    except (OSError, TypeError, ValueError):
        raise LedgerIOError("authority-action directory could not be inspected") from None
    if not stat.S_ISDIR(metadata.st_mode):
        raise LedgerIOError("authority-action parent must be a real directory")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise LedgerIOError("authority-action directory mode must be 0700")


def _open_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise LedgerIOError("no-follow ledger access is unavailable")
    return (
        os.O_RDWR
        | os.O_APPEND
        | os.O_CREAT
        | os.O_NONBLOCK
        | nofollow
        | getattr(os, "O_CLOEXEC", 0)
    )


def _flock(descriptor: int, operation: int) -> None:
    fcntl.flock(descriptor, operation)


def _read_chunk(descriptor: int, size: int) -> bytes:
    return os.read(descriptor, size)


def _write_chunk(handle: typing.BinaryIO, raw: bytes) -> int | None:
    return handle.write(raw)


def _flush(handle: typing.BinaryIO) -> None:
    handle.flush()


def _fsync(descriptor: int) -> None:
    os.fsync(descriptor)


def _restore_preappend_state(
    descriptor: int,
    handle: typing.BinaryIO,
    preappend_size: int,
    prior_events: list[dict[str, object]],
    ledger_path: pathlib.Path,
) -> bool:
    try:
        os.ftruncate(descriptor, preappend_size)
        if os.fstat(descriptor).st_size != preappend_size:
            raise OSError("ledger rollback size mismatch")
        _flush(handle)
        _fsync(descriptor)
        if _read_locked(descriptor) != prior_events:
            raise OSError("ledger rollback state mismatch")
        return True
    except (ActionAuthorityLedgerError, OSError, TypeError, ValueError):
        _quarantine_unconfirmed_ledger(descriptor, preappend_size, ledger_path)
        return False


def _quarantine_unconfirmed_ledger(
    descriptor: int, preappend_size: int, ledger_path: pathlib.Path
) -> None:
    try:
        os.fchmod(descriptor, 0o000)
        if stat.S_IMODE(os.fstat(descriptor).st_mode) == 0o000:
            return
    except OSError:
        pass

    try:
        poison_size = preappend_size + 1
        os.ftruncate(descriptor, poison_size)
        if os.fstat(descriptor).st_size != poison_size:
            raise OSError("ledger poison size mismatch")
        os.lseek(descriptor, preappend_size, os.SEEK_SET)
        if os.read(descriptor, 1) != b"\x00":
            raise OSError("ledger poison byte mismatch")
        try:
            _read_locked(descriptor)
        except MalformedLedgerStateError:
            return
        raise OSError("ledger poison remained readable")
    except (ActionAuthorityLedgerError, OSError, TypeError, ValueError):
        pass

    try:
        descriptor_before = os.fstat(descriptor)
        path_before = os.lstat(ledger_path)
        inode = (descriptor_before.st_dev, descriptor_before.st_ino)
        if not stat.S_ISREG(path_before.st_mode) or (
            path_before.st_dev,
            path_before.st_ino,
        ) != inode:
            raise OSError("ledger quarantine path identity mismatch")
        os.chmod(ledger_path, 0o000, follow_symlinks=False)
        descriptor_after = os.fstat(descriptor)
        path_after = os.lstat(ledger_path)
        if (
            not stat.S_ISREG(path_after.st_mode)
            or (descriptor_after.st_dev, descriptor_after.st_ino) != inode
            or (path_after.st_dev, path_after.st_ino) != inode
            or stat.S_IMODE(descriptor_after.st_mode) != 0o000
            or stat.S_IMODE(path_after.st_mode) != 0o000
        ):
            raise OSError("ledger path quarantine could not be verified")
        return
    except (OSError, TypeError, ValueError, NotImplementedError):
        raise LedgerIOError("ledger quarantine could not be confirmed") from None


@contextlib.contextmanager
def _locked_ledger(path: pathlib.Path):
    checked_path = _require_ledger_path(path)
    _verify_parent_directory(checked_path)
    descriptor: int | None = None
    handle: typing.BinaryIO | None = None
    locked = False
    try:
        descriptor = os.open(checked_path, _open_flags(), 0o600)
        _flock(descriptor, fcntl.LOCK_EX)
        locked = True
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LedgerIOError("ledger target must be a regular file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise LedgerIOError("ledger mode must be 0600")
        handle = os.fdopen(descriptor, "r+b", buffering=0, closefd=False)
        yield descriptor, handle
    except (ActionAuthorityLedgerError, action_authority.ActionAuthorityError):
        raise
    except (OSError, TypeError, ValueError):
        raise LedgerIOError("ledger could not be opened or locked safely") from None
    finally:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if descriptor is not None:
            if locked:
                try:
                    _flock(descriptor, fcntl.LOCK_UN)
                except OSError:
                    pass
            try:
                os.close(descriptor)
            except OSError:
                pass


def _read_locked(descriptor: int) -> list[dict[str, object]]:
    chunks: list[bytes] = []
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        while True:
            block = _read_chunk(descriptor, _READ_CHUNK_SIZE)
            if not block:
                break
            chunks.append(block)
    except OSError:
        raise LedgerIOError("ledger could not be read") from None
    raw = b"".join(chunks)
    if not raw:
        return []
    if not raw.endswith(b"\n"):
        raise MalformedLedgerStateError("ledger must end with LF")
    lines = raw[:-1].split(b"\n")
    if any(not line for line in lines):
        raise MalformedLedgerStateError("ledger contains an empty line")
    events: list[dict[str, object]] = []
    try:
        for line in lines:
            events.append(_validated_event(jsonio.loads_strict(line)))
        _validate_ledger_events(events)
    except (ContractError, _EventValidationError):
        raise MalformedLedgerStateError("ledger contains invalid authority-action state") from None
    return events


def _write_all(handle: typing.BinaryIO, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        try:
            written = _write_chunk(handle, raw[offset:])
        except OSError:
            raise LedgerIOError("ledger append failed") from None
        if type(written) is not int or written <= 0 or written > len(raw) - offset:
            raise LedgerIOError("ledger append failed")
        offset += written


def _append_on_locked_fd(
    descriptor: int,
    handle: typing.BinaryIO,
    prior_events: list[dict[str, object]],
    event: dict[str, object],
    ledger_path: pathlib.Path,
) -> dict[str, object]:
    try:
        checked = _validated_event(event)
        _validate_ledger_events([*prior_events, checked])
    except _EventValidationError:
        raise ActionAuthorityLedgerError("generated event violates the closed ledger") from None
    raw = canonical.canonical_json_bytes(checked) + b"\n"
    try:
        preappend_size = os.fstat(descriptor).st_size
    except OSError:
        raise LedgerIOError("ledger size could not be captured") from None
    try:
        _write_all(handle, raw)
        _flush(handle)
        _fsync(descriptor)
    except (LedgerIOError, OSError):
        restored = _restore_preappend_state(
            descriptor,
            handle,
            preappend_size,
            prior_events,
            ledger_path,
        )
        if restored:
            raise LedgerIOError("ledger append failed and was rolled back") from None
        raise LedgerIOError(
            "ledger append failed and rollback could not be confirmed"
        ) from None
    return copy.deepcopy(checked)


def _require_consume_binding(
    approval_event_id: object, action_id: object, action_sha256: object
) -> None:
    if type(approval_event_id) is not str or not _EVENT_ID.fullmatch(approval_event_id):
        raise ApprovalMismatchError("approval event id is invalid")
    if type(action_id) is not str or not _ACTION_ID.fullmatch(action_id):
        raise ApprovalMismatchError("action id is invalid")
    if type(action_sha256) is not str or not _DIGEST.fullmatch(action_sha256):
        raise ApprovalMismatchError("action digest is invalid")


def record_action_decision(
    ledger_path: pathlib.Path,
    frozen_action: action_authority.FrozenAction,
    decision: object,
    action_id: object,
    action_sha256: object,
) -> dict[str, object]:
    """Durably record one action-bound human approve or reject decision."""

    with _locked_ledger(ledger_path) as (descriptor, handle):
        events = _read_locked(descriptor)
        transport = action_authority.validate_decision_transport(
            frozen_action, decision, action_id, action_sha256
        )
        action = typing.cast(dict[str, object], _plain(frozen_action.action))
        recomputed_digest = action_authority.action_sha256(copy.deepcopy(action))
        if recomputed_digest != frozen_action.action_sha256:
            raise action_authority.MalformedActionError(
                "frozen action digest is invalid"
            )
        now = _utc_now()
        try:
            expires_at = _parse_utc(frozen_action.expires_at)
        except _EventValidationError:
            raise action_authority.MalformedActionError(
                "frozen action expiry is invalid"
            ) from None
        if expires_at > now + _APPROVAL_TTL:
            raise action_authority.MalformedActionError(
                "frozen action expiry exceeds the fixed policy window"
            )
        if expires_at <= now:
            raise action_authority.ExpiredActionError("frozen action has expired")
        event = {
            "schema_version": "authority-action-approval.v0",
            "event_type": "authority_action_approval",
            "event_id": _new_event_id(),
            "decision": transport["decision"],
            "approver_class": "human",
            "action": action,
            "action_sha256": recomputed_digest,
            "recorded_at": _format_utc(now),
            "expires_at": frozen_action.expires_at,
            "max_uses": 1,
        }
        return _append_on_locked_fd(descriptor, handle, events, event, ledger_path)


def consume_action(
    ledger_path: pathlib.Path,
    approval_event_id: object,
    action_id: object,
    action_sha256: object,
) -> tuple[dict[str, object], dict[str, object]]:
    """Atomically consume one approved action and return its durable fact."""

    with _locked_ledger(ledger_path) as (descriptor, handle):
        events = _read_locked(descriptor)
        now = _utc_now()
        _require_consume_binding(approval_event_id, action_id, action_sha256)
        approval = next(
            (event for event in events if event["event_id"] == approval_event_id),
            None,
        )
        if approval is None or approval["event_type"] != "authority_action_approval":
            raise MissingApprovalError("approval event does not exist")
        if approval["decision"] != "approve":
            raise RejectedApprovalError("rejected action cannot be consumed")
        action = typing.cast(dict[str, object], approval["action"])
        if action["action_id"] != action_id or approval["action_sha256"] != action_sha256:
            raise ApprovalMismatchError("action binding differs from approval")
        expires_at = _parse_utc(approval["expires_at"])
        recorded_at = _parse_utc(approval["recorded_at"])
        if now < recorded_at or now >= expires_at:
            raise ExpiredApprovalError("approval is outside its valid time window")
        if any(
            event["event_type"] == "authority_action_consume"
            and event["approval_event_id"] == approval_event_id
            for event in events
        ):
            raise ApprovalReplayError("approval event has already been consumed")
        if any(
            event["event_type"] == "authority_action_consume"
            and event["action_id"] == action_id
            for event in events
        ):
            raise ActionReplayError("action instance has already been consumed")
        event = {
            "schema_version": "authority-action-consume.v0",
            "event_type": "authority_action_consume",
            "event_id": _new_event_id(),
            "approval_event_id": approval_event_id,
            "action_id": action_id,
            "action_sha256": action_sha256,
            "consumed_at": _format_utc(now),
            "expires_at": approval["expires_at"],
        }
        durable_event = _append_on_locked_fd(
            descriptor, handle, events, event, ledger_path
        )
        return durable_event, copy.deepcopy(action)
