"""Bounded evidence CLI; inspect may read one explicit sidecar file."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from collections.abc import Sequence

from .evidence import (
    EvidenceError,
    MAX_ENCODED_BYTES,
    decode_json,
    export_evidence,
    inspect_evidence,
    summarize_evidence,
    _require_digest,
    _validate_bundle_shape,
)


_EXPORT_FIELDS = frozenset(
    {"response", "decision", "consume", "started", "finished", "executor_ref", "verification"}
)


def _invalid() -> EvidenceError:
    return EvidenceError("invalid bounded CLI input")


def _read_stdin_bytes() -> bytes:
    try:
        raw = sys.stdin.buffer.read(MAX_ENCODED_BYTES + 1)
    except (AttributeError, OSError, ValueError):
        raise _invalid() from None
    if len(raw) > MAX_ENCODED_BYTES:
        raise _invalid()
    return raw


def _read_stdin() -> object:
    return decode_json(_read_stdin_bytes())


def _readback_evidence_file(path: str) -> object:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    nonblock = getattr(os, "O_NONBLOCK", None)
    cloexec = getattr(os, "O_CLOEXEC", None)
    if type(nofollow) is not int or type(nonblock) is not int or type(cloexec) is not int:
        raise _invalid()
    flags = os.O_RDONLY | nofollow | nonblock | cloexec
    try:
        descriptor = os.open(path, flags)
    except (OSError, TypeError, ValueError):
        raise _invalid() from None

    chunks: list[bytes] = []
    total = 0
    try:
        try:
            mode = os.fstat(descriptor).st_mode
        except OSError:
            raise _invalid() from None
        if not stat.S_ISREG(mode):
            raise _invalid()
        while total <= MAX_ENCODED_BYTES:
            try:
                block = os.read(
                    descriptor,
                    min(64 * 1024, MAX_ENCODED_BYTES + 1 - total),
                )
            except OSError:
                raise _invalid() from None
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > MAX_ENCODED_BYTES:
                raise _invalid()
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
    return decode_json(b"".join(chunks))


def _export_from_envelope(payload: object) -> dict[str, object]:
    if type(payload) is not dict:
        raise _invalid()
    request = payload.get("request")
    if "request" not in payload:
        raise _invalid()
    if "export" in payload:
        if set(payload) != {"request", "export"} or type(payload["export"]) is not dict:
            raise _invalid()
        kwargs = payload["export"]
    else:
        if set(payload) - ({"request"} | _EXPORT_FIELDS):
            raise _invalid()
        kwargs = {key: payload[key] for key in payload if key != "request"}
    if set(kwargs) - _EXPORT_FIELDS or "executor_ref" not in kwargs:
        raise _invalid()
    try:
        return export_evidence(request, **kwargs)
    except TypeError:
        raise _invalid() from None


def _json_line(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError):
        raise _invalid() from None
    return encoded + "\n"


def _write_json(value: object) -> None:
    _write_once(sys.stdout, _json_line(value))


def _readback_line(value: object) -> str:
    line = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False) + "\n"
    # Apply the same plain-JSON depth, node and byte bounds as stdin.
    decode_json(line)
    return line


def _write_once(stream, line: str) -> None:
    written = stream.write(line)
    if type(written) is not int or written != len(line):
        raise OSError("incomplete evidence output")
    stream.flush()


def _report_invalid() -> int:
    try:
        sys.stderr.write("invalid bounded evidence input\n")
    except (OSError, TypeError, ValueError, UnicodeError):
        pass
    return 2


_SAVED_REJECTION_CHECKS = {
    "invalid_expectation": "check the command and the original task's separately retained action digest; do not derive it from this input",
    "input_unavailable": "check access to the original input and its byte limit; preserve the original bytes",
    "invalid_saved_result": "preserve the original input; compare its separately retained checksum and original records with the sender",
    "expected_action_unavailable": "inspect the separately retained original task/action record; no action identity was supplied",
    "expected_action_mismatch": "compare the original task's separately retained action digest with the intended handoff; do not replace it from this input",
    "expected_input_mismatch": "compare the handoff against its separately retained saved-input checksum; preserve the original bytes and do not replace the expectation from this input",
    "output_incomplete": "discard partial output; check the output destination",
    "inspection_unavailable": "preserve the original input and check the reader environment; the cause is unclassified",
}


def _report_saved_rejection(code: str) -> int:
    if code not in _SAVED_REJECTION_CHECKS:
        code = "inspection_unavailable"
    diagnostic = {
        "schema": "mothership.saved-result-rejection.v0",
        "code": code, "next_read_only_check": _SAVED_REJECTION_CHECKS[code],
        "accepted_result": False, "authority": False,
        "source_authenticated": False, "external_effect_verified": False,
        "recovery": "no re-execution; no reconsume",
    }
    try:
        _write_once(sys.stderr, _json_line(diagnostic))
    except Exception:
        # An incomplete diagnostic is not data. Never retry a broken sink.
        pass
    return 2


def _inspect_saved_command(args: argparse.Namespace) -> int:
    stage = "inspection_unavailable"
    expectation_error = ()
    input_expectation_error = ()
    try:
        from .saved_result import (
            _ExpectedActionError, _ExpectedInputError, inspect_saved_result, summarize_saved_result,
        )

        expectation_error = (_ExpectedActionError,)
        input_expectation_error = (_ExpectedInputError,)
        stage = "invalid_expectation"
        expected_values = args.expect_action_sha256
        if expected_values is not None:
            if type(expected_values) is not list or len(expected_values) != 1:
                raise _invalid()
            expected_action_sha256 = _require_digest(expected_values[0])
        else:
            expected_action_sha256 = None
        expected_inputs = args.expect_input_sha256
        if expected_inputs is not None:
            if type(expected_inputs) is not list or len(expected_inputs) != 1:
                raise _invalid()
            expected_input_sha256 = _require_digest(expected_inputs[0])
        else:
            expected_input_sha256 = None
        stage = "input_unavailable"
        raw = _read_stdin_bytes()
        stage = "invalid_saved_result"
        result = (summarize_saved_result if args.human else inspect_saved_result)(
            raw, expected_action_sha256=expected_action_sha256,
            expected_input_sha256=expected_input_sha256,
        )
        stage = "inspection_unavailable"
        line = result if args.human else _json_line(result)
        stage = "output_incomplete"
        _write_once(sys.stdout, line)
        return 0
    except Exception as error:
        if not args.explain_error:
            # Retain the existing main handler's exact default error contract.
            raise
        if isinstance(error, expectation_error):
            code = "expected_action_unavailable" if error.action_unavailable else "expected_action_mismatch"
        elif isinstance(error, input_expectation_error):
            code = "expected_input_mismatch"
        elif isinstance(error, EvidenceError) or stage in {"input_unavailable", "output_incomplete"}:
            code = stage
        else:
            code = "inspection_unavailable"
        return _report_saved_rejection(code)


def _emit_readback(result: dict[str, object]) -> int:
    # Serialize both first. Successful stderr is data, not an error log.
    sidecar = _readback_line(result["evidence"])
    bundle = _readback_line(result["bundle"])
    try:
        _write_once(sys.stderr, sidecar)
    except (OSError, TypeError, ValueError, UnicodeError):
        # A broken error sink must not trigger another write to that sink.
        return 2
    try:
        _write_once(sys.stdout, bundle)
    except (OSError, TypeError, ValueError, UnicodeError):
        return _report_invalid()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mothership-evidence",
        description="Read-only bounded Mothership evidence export and inspection",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("export", help="export a bundle from a bounded stdin envelope")
    subparsers.add_parser(
        "readback",
        help="public tokenless GET read-back; new bundle on stdout, evidence JSON on stderr",
    )
    inspect_parser = subparsers.add_parser("inspect", help="inspect a bounded bundle from stdin")
    inspect_parser.add_argument(
        "--human",
        action="store_true",
        help="render bounded human-facing text instead of the default JSON projection",
    )
    inspect_parser.add_argument(
        "--readback-evidence",
        action="append",
        metavar="PATH",
        help="read one bounded regular-file read-back sidecar for --human output",
    )
    result_parser = subparsers.add_parser(
        "inspect-result", help="offline inspection of saved reference-consumer result.jsonl from stdin",
    )
    result_parser.add_argument("--human", action="store_true", help="explain supplied saved-result records")
    result_parser.add_argument(
        "--explain-error", action="store_true",
        help="on rejection, emit a bounded reason and next read-only check as JSON on stderr",
    )
    result_parser.add_argument(
        "--expect-action-sha256",
        action="append",
        nargs="?",
        metavar="DIGEST",
        help="require the supplied saved result's already-validated action digest",
    )
    result_parser.add_argument(
        "--expect-input-sha256",
        action="append",
        nargs="?",
        metavar="DIGEST",
        help="require the raw saved-input bytes to match a separately retained SHA-256",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bounded evidence CLI and return a process status."""

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        sidecar_paths = getattr(args, "readback_evidence", None)
        if sidecar_paths is not None and (
            args.command != "inspect"
            or not args.human
            or type(sidecar_paths) is not list
            or len(sidecar_paths) != 1
        ):
            raise _invalid()
        if args.command == "inspect-result":
            return _inspect_saved_command(args)
        payload = _read_stdin()
        if args.command == "export":
            result = _export_from_envelope(payload)
        elif args.command == "readback":
            from .readback import readback_evidence

            return _emit_readback(readback_evidence(payload))
        elif args.command == "inspect":
            if args.human:
                if sidecar_paths is None:
                    human_text = summarize_evidence(payload)
                else:
                    checked = _validate_bundle_shape(payload)
                    inspect_evidence(checked)
                    if checked["verification"] is None:
                        raise _invalid()
                    sidecar = _readback_evidence_file(sidecar_paths[0])
                    human_text = summarize_evidence(
                        checked, readback_evidence=sidecar
                    )
                written = sys.stdout.write(human_text)
                if type(written) is not int or written != len(human_text):
                    raise OSError("incomplete human display")
                sys.stdout.flush()
                return 0
            result = inspect_evidence(payload)
        else:
            raise _invalid()
        _write_json(result)
        return 0
    except EvidenceError:
        return _report_invalid()
    except (OSError, TypeError, ValueError, UnicodeError, RecursionError):
        return _report_invalid()


if __name__ == "__main__":  # pragma: no cover - exercised through the entry point
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
