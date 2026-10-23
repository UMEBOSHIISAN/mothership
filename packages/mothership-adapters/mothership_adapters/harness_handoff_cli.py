"""Explicit local synthetic handoff. No live option or credential reader."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from .harness_handoff import (
    MAX_INPUT, HandoffError, ThinHarnessOwner, collect_response,
    decode_handoff_json, read_regular, validate_preview, write_complete,
)


class _SyntheticTransport:
    def __init__(self, parameters):
        self.parameters = parameters

    def get_pull_request(self, repository, pull_request):
        if (repository, pull_request) != (self.parameters["repository"], self.parameters["pull_request"]):
            raise ValueError("synthetic target differs")
        return dict(http_status=200, state="open", merged=False,
                    head_sha=self.parameters["expected_head_sha"], base_ref=self.parameters["expected_base"])

    def merge_pull_request(self, **parameters):
        expected = {k: self.parameters[k] for k in (
            "repository", "pull_request", "expected_head_sha", "merge_method")}
        if parameters != expected:
            raise ValueError("synthetic target differs")
        return dict(http_status=200, merged=True, merge_commit_sha="b" * 40)


def _unavailable_observation(request, *, timeout):
    # Deliberately exercise UNKNOWN; no fabricated real completion or clock.
    raise OSError("synthetic readback unavailable")


def main(argv=None):
    parser = argparse.ArgumentParser(description=(
        "Local synthetic Harness preview → Mothership Session → saved evidence. No GitHub or model access."))
    for name in ("harness-cli", "request", "interpretation-file", "parameters", "worktree",
                 "run-directory", "host-context"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--json", action="store_true", help="print the same structured result as result.json")
    args = parser.parse_args(argv)
    owner, failed = None, False
    try:
        # All parsing precedes the one explicitly selected Harness subprocess.
        interpretation_raw = read_regular(args.interpretation_file)
        interpretation = decode_handoff_json(interpretation_raw)
        parameters = decode_handoff_json(read_regular(args.parameters))
        context = decode_handoff_json(read_regular(args.host_context))
        harness = Path(args.harness_cli).absolute()
        harness_bytes = read_regular(harness, 1_048_576)
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise HandoffError("foreground terminal required")
        preview_process = subprocess.run(
            [str(harness), "--handoff-json",
             "--request", args.request, "--llm-output-file", str(Path(args.interpretation_file).absolute())],
            capture_output=True, timeout=15,
            env={"PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath,
                 "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if preview_process.returncode not in (0, 2) or len(preview_process.stdout) > MAX_INPUT:
            raise HandoffError("Harness preview held")
        preview = validate_preview(decode_handoff_json(preview_process.stdout), args.request, interpretation)
        if read_regular(harness, 1_048_576) != harness_bytes:
            raise HandoffError("Harness executable changed")
        executor_ref = dict(ref_id="executor:thin-handoff-synthetic-v0",
                            sha256=hashlib.sha256(read_regular(__file__, 1_048_576)).hexdigest())
        owner = ThinHarnessOwner(
            parameters, preview=preview, raw_request=args.request, interpretation=interpretation,
            interpretation_bytes=interpretation_raw, worktree=args.worktree,
            run_directory=args.run_directory, host_context_provider=lambda: context,
            transport=_SyntheticTransport(parameters), executor_ref=executor_ref)
        owner._write("harness-entry.json", json.dumps(dict(
            path=str(harness), sha256=hashlib.sha256(harness_bytes).hexdigest(),
            source="explicit_offline_entry", authenticated=False), sort_keys=True).encode())
        answer = collect_response(owner.request, sys.stdin, sys.stderr)
        if answer is None:
            owner.cancel()
        elif owner.review(answer) == "approve":
            owner.execute(parameters)
            if owner.export()["missing"] == ["verification"]:
                owner.readback(opener=_unavailable_observation)
    except (Exception, KeyboardInterrupt):
        failed = True
        if owner is not None:
            owner.cancel()
    try:
        if owner is None:
            raise HandoffError("input unavailable")
        outcome = owner.save()
        text = (json.dumps(outcome, ensure_ascii=True, sort_keys=True) if args.json else
                "LOCAL SYNTHETIC RUN — no real GitHub operation\n" + outcome["human"] +
                "\nSaved evidence: " + json.dumps(str(owner.root))) + "\n"
        write_complete(sys.stdout, text)
    except (Exception, KeyboardInterrupt):
        failed = True
    if failed:
        try:
            write_complete(sys.stderr, "Handoff stopped. Existing records remain at " +
                           json.dumps(str(Path(args.run_directory).absolute())) +
                           "; inspect retained records; no retry or action reissue.\n")
        except Exception:
            pass
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
