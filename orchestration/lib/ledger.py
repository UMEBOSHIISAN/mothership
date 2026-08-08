"""Append-only, single-use approval ledger for Friend Mothership Core."""

from __future__ import annotations

import contextlib
import dataclasses
import datetime
import fcntl
import os
import pathlib
import re
import secrets
import stat
import typing

from . import canonical, contracts, jsonio
from .errors import ContractError


_READ_CHUNK_SIZE = 64 * 1024
_SCHEMA_VERSION = "0.1.0"
_ALIASES = frozenset({"claude-code-agent", "codex-cli", "ollama-local"})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_INVOCATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_EVENT_ID_RE = re.compile(r"^event-[0-9a-f]{32}$")
_TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

_COMMON_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "event_type",
        "alias",
        "invocation_id",
        "registry_sha256",
        "task_sha256",
        "prompt_sha256",
        "scope_sha256",
        "invocation_sha256",
        "recorded_at",
        "expires_at",
    }
)
_TYPE_FIELDS = {
    "confirmation_failed": frozenset({"confirmation_result"}),
    "approval_granted": frozenset(),
    "attempt_started": frozenset({"approval_event_id", "approval_sha256"}),
    "attempt_finished": frozenset(
        {"attempt_started_event_id", "exit_class", "exit_code"}
    ),
}
_CONFIRMATION_RESULTS = frozenset(
    {"input-not-tty", "output-not-tty", "mismatch", "eof"}
)
_EXIT_CLASSES = frozenset(
    {"success", "nonzero-exit", "launch-error", "timeout", "output-limit-exceeded"}
)


class LedgerError(ContractError):
    """Base class for closed, static ledger failures."""


class EventValidationError(LedgerError):
    """An event or relationship violates the closed ledger contract."""


class MalformedLedgerEntryError(LedgerError):
    """The complete JSONL ledger cannot be accepted."""


class LedgerIOError(LedgerError):
    """The ledger path, descriptor, lock, read, or durable write failed."""


class CeremonyIOError(LedgerError):
    """The interactive ceremony failed before a durable outcome existed."""


class NaiveDatetimeError(EventValidationError):
    """A caller supplied a datetime outside the exact UTC contract."""


class AbsentApprovalError(LedgerError):
    """No approval exists for the invocation."""


class WrongAliasError(LedgerError):
    """An approval alias differs from the requested binding."""


class StaleRegistryDigestError(LedgerError):
    """An approval carries another registry digest."""


class StaleTaskDigestError(LedgerError):
    """An approval carries another task digest."""


class StalePromptDigestError(LedgerError):
    """An approval carries another prompt digest."""


class StaleScopeDigestError(LedgerError):
    """An approval carries another scope digest."""


class StaleInvocationDigestError(LedgerError):
    """An approval carries another combined invocation digest."""


class FutureIssuedApprovalError(LedgerError):
    """Only future-issued matching approvals exist."""


class ExpiredApprovalError(LedgerError):
    """Only expired matching approvals exist."""


class ReplayedInvocationError(LedgerError):
    """The invocation already has a durable attempt start."""


class FinishAttemptError(LedgerError):
    """The requested finish cannot be related to one unfinished start."""


@dataclasses.dataclass(frozen=True)
class InvocationBinding:
    alias: str
    invocation_id: str
    registry_sha256: str
    task_sha256: str
    prompt_sha256: str
    scope_sha256: str
    invocation_sha256: str


def _require_text(value: object, label: str) -> str:
    if type(value) is not str:
        raise EventValidationError(f"{label} must be text")
    return value


def _require_digest(value: object, label: str) -> str:
    text = _require_text(value, label)
    if _DIGEST_RE.fullmatch(text) is None:
        raise EventValidationError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _binding_digest(
    registry_sha256: str,
    task_sha256: str,
    prompt_sha256: str,
    scope_sha256: str,
    invocation_id: str,
) -> str:
    raw = (
        f"registry_sha256={registry_sha256}\n"
        f"task_sha256={task_sha256}\n"
        f"prompt_sha256={prompt_sha256}\n"
        f"scope_sha256={scope_sha256}\n"
        f"invocation_id={invocation_id}\n"
    ).encode("utf-8")
    return canonical.sha256_bytes(raw)


def make_binding(
    alias: str,
    invocation_id: str,
    registry_sha256: str,
    task_sha256: str,
    prompt_sha256: str,
    scope_sha256: str,
) -> InvocationBinding:
    """Validate exact binding inputs and compute the five-line digest."""

    alias_text = _require_text(alias, "alias")
    invocation_text = _require_text(invocation_id, "invocation_id")
    if alias_text not in _ALIASES:
        raise EventValidationError("alias is not supported")
    if _INVOCATION_ID_RE.fullmatch(invocation_text) is None:
        raise EventValidationError("invocation_id is invalid")
    registry = _require_digest(registry_sha256, "registry_sha256")
    task = _require_digest(task_sha256, "task_sha256")
    prompt = _require_digest(prompt_sha256, "prompt_sha256")
    scope = _require_digest(scope_sha256, "scope_sha256")
    return InvocationBinding(
        alias=alias_text,
        invocation_id=invocation_text,
        registry_sha256=registry,
        task_sha256=task,
        prompt_sha256=prompt,
        scope_sha256=scope,
        invocation_sha256=_binding_digest(
            registry, task, prompt, scope, invocation_text
        ),
    )


def _require_binding(value: object) -> InvocationBinding:
    if type(value) is not InvocationBinding:
        raise EventValidationError("binding must be an InvocationBinding")
    expected = make_binding(
        value.alias,
        value.invocation_id,
        value.registry_sha256,
        value.task_sha256,
        value.prompt_sha256,
        value.scope_sha256,
    )
    if value.invocation_sha256 != expected.invocation_sha256:
        raise EventValidationError("binding invocation digest is invalid")
    return value


def _parse_time(value: object) -> datetime.datetime:
    text = _require_text(value, "timestamp")
    if _TIME_RE.fullmatch(text) is None:
        raise EventValidationError("timestamp is not canonical UTC")
    try:
        parsed = datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise EventValidationError("timestamp is not canonical UTC") from None
    return parsed.replace(tzinfo=datetime.UTC)


def _require_now(value: object) -> datetime.datetime:
    if type(value) is not datetime.datetime:
        raise NaiveDatetimeError("now must be a UTC datetime")
    if value.tzinfo != datetime.UTC or value.microsecond != 0:
        raise NaiveDatetimeError("now must be canonical whole-second UTC")
    return value


def _format_time(value: datetime.datetime) -> str:
    checked = _require_now(value)
    return checked.strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0)


def _new_event_id() -> str:
    return "event-" + secrets.token_hex(16)


def _binding_fields(binding: InvocationBinding) -> dict[str, str]:
    return {
        "alias": binding.alias,
        "invocation_id": binding.invocation_id,
        "registry_sha256": binding.registry_sha256,
        "task_sha256": binding.task_sha256,
        "prompt_sha256": binding.prompt_sha256,
        "scope_sha256": binding.scope_sha256,
        "invocation_sha256": binding.invocation_sha256,
    }


def _event_binding(event: dict[str, object]) -> tuple[object, ...]:
    return tuple(
        event[name]
        for name in (
            "alias",
            "invocation_id",
            "registry_sha256",
            "task_sha256",
            "prompt_sha256",
            "scope_sha256",
            "invocation_sha256",
        )
    )


def _binding_tuple(binding: InvocationBinding) -> tuple[str, ...]:
    fields = _binding_fields(binding)
    return tuple(fields[name] for name in fields)


def _validate_exit(exit_class: object, exit_code: object) -> None:
    if type(exit_class) is not str or exit_class not in _EXIT_CLASSES:
        raise EventValidationError("exit_class is invalid")
    if exit_class == "success":
        valid = type(exit_code) is int and exit_code == 0
    elif exit_class == "nonzero-exit":
        valid = type(exit_code) is int and exit_code != 0
    else:
        valid = exit_code is None
    if not valid:
        raise EventValidationError("exit_code does not match exit_class")


def validate_event(event: object) -> dict[str, object]:
    """Validate one closed event without reading external state."""

    if type(event) is not dict:
        raise EventValidationError("event must be an object")
    try:
        checked = contracts.validate_contract("approval-event", event)
    except ContractError:
        raise EventValidationError("event does not match approval-event schema") from None
    event_type = checked.get("event_type")
    if type(event_type) is not str or event_type not in _TYPE_FIELDS:
        raise EventValidationError("event_type is invalid")
    if set(checked) != _COMMON_FIELDS | _TYPE_FIELDS[event_type]:
        raise EventValidationError("event fields do not match event_type")

    expected_digest = _binding_digest(
        typing.cast(str, checked["registry_sha256"]),
        typing.cast(str, checked["task_sha256"]),
        typing.cast(str, checked["prompt_sha256"]),
        typing.cast(str, checked["scope_sha256"]),
        typing.cast(str, checked["invocation_id"]),
    )
    if checked["invocation_sha256"] != expected_digest:
        raise EventValidationError("event invocation digest is invalid")

    recorded = _parse_time(checked["recorded_at"])
    expires = _parse_time(checked["expires_at"])
    if event_type in {"confirmation_failed", "approval_granted", "attempt_started"}:
        if recorded >= expires:
            raise EventValidationError("event must be recorded before expiry")
    if event_type == "confirmation_failed":
        if checked["confirmation_result"] not in _CONFIRMATION_RESULTS:
            raise EventValidationError("confirmation_result is invalid")
    if event_type == "attempt_finished":
        _validate_exit(checked["exit_class"], checked["exit_code"])
    return dict(checked)


def _validate_ledger_events(events: list[dict[str, object]]) -> None:
    identifiers: set[str] = set()
    approvals: dict[str, dict[str, object]] = {}
    starts: dict[str, dict[str, object]] = {}
    started_invocations: set[str] = set()
    finished_starts: set[str] = set()

    for raw in events:
        event = validate_event(raw)
        event_id = typing.cast(str, event["event_id"])
        if event_id in identifiers:
            raise EventValidationError("ledger contains a duplicate event id")
        identifiers.add(event_id)
        event_type = event["event_type"]

        if event_type == "approval_granted":
            approvals[event_id] = event
            continue

        if event_type == "attempt_started":
            invocation_id = typing.cast(str, event["invocation_id"])
            if invocation_id in started_invocations:
                raise EventValidationError("invocation has more than one start")
            approval_id = typing.cast(str, event["approval_event_id"])
            approval = approvals.get(approval_id)
            if approval is None:
                raise EventValidationError("attempt start references no earlier approval")
            if _event_binding(event) != _event_binding(approval):
                raise EventValidationError("attempt start binding differs from approval")
            if event["expires_at"] != approval["expires_at"]:
                raise EventValidationError("attempt start expiry differs from approval")
            if event["approval_sha256"] != canonical.canonical_json_sha256(approval):
                raise EventValidationError("attempt start approval hash is invalid")
            if _parse_time(event["recorded_at"]) < _parse_time(approval["recorded_at"]):
                raise EventValidationError("attempt start predates approval")
            started_invocations.add(invocation_id)
            starts[event_id] = event
            continue

        if event_type == "attempt_finished":
            start_id = typing.cast(str, event["attempt_started_event_id"])
            start = starts.get(start_id)
            if start is None:
                raise EventValidationError("finish references no earlier start")
            if start_id in finished_starts:
                raise EventValidationError("attempt start has more than one finish")
            if _event_binding(event) != _event_binding(start):
                raise EventValidationError("finish binding differs from start")
            if event["expires_at"] != start["expires_at"]:
                raise EventValidationError("finish expiry differs from start")
            if _parse_time(event["recorded_at"]) < _parse_time(start["recorded_at"]):
                raise EventValidationError("finish predates start")
            finished_starts.add(start_id)


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


@contextlib.contextmanager
def _locked_ledger(path: pathlib.Path):
    checked_path = _require_ledger_path(path)
    descriptor: int | None = None
    handle: typing.BinaryIO | None = None
    locked = False
    try:
        descriptor = os.open(checked_path, _open_flags(), 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LedgerIOError("ledger target must be a regular file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise LedgerIOError("ledger mode must be 0600")
        _flock(descriptor, fcntl.LOCK_EX)
        locked = True
        handle = os.fdopen(descriptor, "r+b", buffering=0, closefd=False)
        yield descriptor, handle
    except LedgerError:
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
        raise MalformedLedgerEntryError("ledger must end with LF")
    lines = raw[:-1].split(b"\n")
    if any(not line for line in lines):
        raise MalformedLedgerEntryError("ledger contains an empty line")
    events: list[dict[str, object]] = []
    for line in lines:
        try:
            value = contracts.validate_contract("approval-event", jsonio.loads_strict(line))
        except ContractError:
            raise MalformedLedgerEntryError("ledger contains an invalid event") from None
        events.append(value)
    try:
        _validate_ledger_events(events)
    except EventValidationError:
        raise MalformedLedgerEntryError("ledger event relationships are invalid") from None
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
) -> str:
    checked = validate_event(event)
    _validate_ledger_events([*prior_events, checked])
    raw = canonical.canonical_json_bytes(checked) + b"\n"
    _write_all(handle, raw)
    try:
        _flush(handle)
        _fsync(descriptor)
    except OSError:
        raise LedgerIOError("ledger durability step failed") from None
    return typing.cast(str, checked["event_id"])


def append_event(ledger_path: pathlib.Path, event: dict[str, object]) -> str:
    """Append one validated event while holding one exclusive descriptor."""

    checked = validate_event(event)
    with _locked_ledger(ledger_path) as (descriptor, handle):
        events = _read_locked(descriptor)
        return _append_on_locked_fd(descriptor, handle, events, checked)


def _common_event(
    event_type: str,
    binding: InvocationBinding,
    event_id: str,
    recorded_at: datetime.datetime,
    expires_at: str,
) -> dict[str, object]:
    if _EVENT_ID_RE.fullmatch(event_id) is None:
        raise EventValidationError("generated event id is invalid")
    event: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "event_id": event_id,
        "event_type": event_type,
        **_binding_fields(binding),
        "recorded_at": _format_time(recorded_at),
        "expires_at": expires_at,
    }
    return event


def approve_interactively(
    binding: InvocationBinding,
    expires_at: str,
    ledger_path: pathlib.Path,
    input_stream: typing.TextIO,
    output_stream: typing.TextIO,
) -> dict[str, object]:
    """Run one visible typed-confirmation ceremony and persist its outcome."""

    checked_binding = _require_binding(binding)
    now = _require_now(_utc_now())
    expiry = _parse_time(expires_at)
    if expiry <= now:
        raise EventValidationError("approval expiry must be in the future")
    try:
        input_is_tty = bool(input_stream.isatty())
        output_is_tty = bool(output_stream.isatty()) if input_is_tty else False
    except Exception:
        raise CeremonyIOError("approval ceremony stream inspection failed") from None

    if not input_is_tty:
        confirmation_result = "input-not-tty"
    elif not output_is_tty:
        confirmation_result = "output-not-tty"
    else:
        try:
            output_stream.write(
                f"Type exactly: approve {checked_binding.alias} "
                f"{checked_binding.invocation_id}\n> "
            )
            output_stream.flush()
            raw_line = input_stream.readline()
        except Exception:
            raise CeremonyIOError("approval ceremony I/O failed") from None
        if type(raw_line) is not str:
            raise CeremonyIOError("approval ceremony I/O failed")
        if raw_line == "":
            confirmation_result = "eof"
        else:
            candidate = raw_line
            if candidate.endswith("\n"):
                candidate = candidate[:-1]
                if candidate.endswith("\r"):
                    candidate = candidate[:-1]
            expected = (
                f"approve {checked_binding.alias} {checked_binding.invocation_id}"
            )
            confirmation_result = "match" if candidate == expected else "mismatch"

    event_type = (
        "approval_granted" if confirmation_result == "match" else "confirmation_failed"
    )
    event = _common_event(
        event_type,
        checked_binding,
        _new_event_id(),
        now,
        _format_time(expiry),
    )
    if event_type == "confirmation_failed":
        event["confirmation_result"] = confirmation_result
    append_event(ledger_path, event)
    return dict(event)


def _raise_binding_mismatch(
    event: dict[str, object], binding: InvocationBinding
) -> typing.NoReturn:
    if event["alias"] != binding.alias:
        raise WrongAliasError("approval alias does not match")
    if event["registry_sha256"] != binding.registry_sha256:
        raise StaleRegistryDigestError("approval registry digest does not match")
    if event["task_sha256"] != binding.task_sha256:
        raise StaleTaskDigestError("approval task digest does not match")
    if event["prompt_sha256"] != binding.prompt_sha256:
        raise StalePromptDigestError("approval prompt digest does not match")
    if event["scope_sha256"] != binding.scope_sha256:
        raise StaleScopeDigestError("approval scope digest does not match")
    raise StaleInvocationDigestError("approval invocation digest does not match")


def consume_approval_and_start(
    ledger_path: pathlib.Path,
    binding: InvocationBinding,
    now: datetime.datetime,
) -> dict[str, object]:
    """Consume one current exact approval and durably append one start."""

    checked_binding = _require_binding(binding)
    checked_now = _require_now(now)
    with _locked_ledger(ledger_path) as (descriptor, handle):
        events = _read_locked(descriptor)
        if any(
            event["event_type"] == "attempt_started"
            and event["invocation_id"] == checked_binding.invocation_id
            for event in events
        ):
            raise ReplayedInvocationError("invocation already has an attempt start")
        grants = [
            event
            for event in events
            if event["event_type"] == "approval_granted"
            and event["invocation_id"] == checked_binding.invocation_id
        ]
        if not grants:
            raise AbsentApprovalError("no approval exists for invocation")
        exact = [
            event
            for event in grants
            if _event_binding(event) == _binding_tuple(checked_binding)
        ]
        if not exact:
            _raise_binding_mismatch(grants[-1], checked_binding)
        eligible = [
            event
            for event in exact
            if _parse_time(event["recorded_at"]) <= checked_now
            < _parse_time(event["expires_at"])
        ]
        if not eligible:
            last = exact[-1]
            if _parse_time(last["recorded_at"]) > checked_now:
                raise FutureIssuedApprovalError("approval is future-issued")
            raise ExpiredApprovalError("approval is expired")
        approval = eligible[-1]
        event = _common_event(
            "attempt_started",
            checked_binding,
            _new_event_id(),
            checked_now,
            typing.cast(str, approval["expires_at"]),
        )
        event["approval_event_id"] = approval["event_id"]
        event["approval_sha256"] = canonical.canonical_json_sha256(approval)
        event_id = _append_on_locked_fd(descriptor, handle, events, event)
        return {
            "approval_event_id": typing.cast(str, approval["event_id"]),
            "approval_sha256": typing.cast(str, event["approval_sha256"]),
            "attempt_started_event_id": event_id,
            "expires_at": typing.cast(str, approval["expires_at"]),
        }


def finish_attempt(
    ledger_path: pathlib.Path,
    binding: InvocationBinding,
    attempt_started_event_id: str,
    exit_class: str,
    exit_code: int | None,
    now: datetime.datetime,
) -> dict[str, object]:
    """Durably finish one earlier start at most once on the same locked FD."""

    checked_binding = _require_binding(binding)
    start_id = _require_text(attempt_started_event_id, "attempt_started_event_id")
    if _EVENT_ID_RE.fullmatch(start_id) is None:
        raise FinishAttemptError("attempt start id is invalid")
    _validate_exit(exit_class, exit_code)
    checked_now = _require_now(now)
    with _locked_ledger(ledger_path) as (descriptor, handle):
        events = _read_locked(descriptor)
        start = next(
            (
                event
                for event in events
                if event["event_type"] == "attempt_started"
                and event["event_id"] == start_id
            ),
            None,
        )
        if start is None:
            raise FinishAttemptError("attempt start does not exist")
        if _event_binding(start) != _binding_tuple(checked_binding):
            raise FinishAttemptError("attempt start binding does not match")
        if any(
            event["event_type"] == "attempt_finished"
            and event["attempt_started_event_id"] == start_id
            for event in events
        ):
            raise FinishAttemptError("attempt start is already finished")
        if checked_now < _parse_time(start["recorded_at"]):
            raise FinishAttemptError("finish time predates attempt start")
        event = _common_event(
            "attempt_finished",
            checked_binding,
            _new_event_id(),
            checked_now,
            typing.cast(str, start["expires_at"]),
        )
        event.update(
            {
                "attempt_started_event_id": start_id,
                "exit_class": exit_class,
                "exit_code": exit_code,
            }
        )
        event_id = _append_on_locked_fd(descriptor, handle, events, event)
        return {
            "attempt_finished_event_id": event_id,
            "attempt_started_event_id": start_id,
            "recorded_at": typing.cast(str, event["recorded_at"]),
        }
