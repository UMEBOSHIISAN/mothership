"""Bounded stdin-only CLI for evidence export and inspection."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .evidence import (
    EvidenceError,
    MAX_ENCODED_BYTES,
    decode_json,
    export_evidence,
    inspect_evidence,
    summarize_evidence,
)


_EXPORT_FIELDS = frozenset(
    {"response", "decision", "consume", "started", "finished", "executor_ref", "verification"}
)


def _invalid() -> EvidenceError:
    return EvidenceError("invalid bounded CLI input")


def _read_stdin() -> object:
    try:
        raw = sys.stdin.buffer.read(MAX_ENCODED_BYTES + 1)
    except (AttributeError, OSError, ValueError):
        raise _invalid() from None
    if len(raw) > MAX_ENCODED_BYTES:
        raise _invalid()
    return decode_json(raw)


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
    sys.stdout.write(encoded)
    sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mothership-evidence",
        description="Read-only bounded Mothership evidence export and inspection",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("export", help="export a bundle from a bounded stdin envelope")
    inspect_parser = subparsers.add_parser("inspect", help="inspect a bounded bundle from stdin")
    inspect_parser.add_argument(
        "--human",
        action="store_true",
        help="render bounded human-facing text instead of the default JSON projection",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the stdin-only CLI and return a process status."""

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        payload = _read_stdin()
        if args.command == "export":
            result = _export_from_envelope(payload)
        elif args.command == "inspect":
            if args.human:
                human_text = summarize_evidence(payload)
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
        sys.stderr.write("invalid bounded evidence input\n")
        return 2
    except (OSError, TypeError, ValueError, UnicodeError, RecursionError):
        sys.stderr.write("invalid bounded evidence input\n")
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised through the entry point
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
