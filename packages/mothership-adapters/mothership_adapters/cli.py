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


def _write_json(value: object) -> None:
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
    _write_once(sys.stdout, encoded + "\n")


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
            from .saved_result import inspect_saved_result, summarize_saved_result

            raw = _read_stdin_bytes()
            if args.human:
                _write_once(sys.stdout, summarize_saved_result(raw))
            else:
                _write_json(inspect_saved_result(raw))
            return 0
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
