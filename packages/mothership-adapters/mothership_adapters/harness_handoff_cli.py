"""Explicit handoff; synthetic by default, live only by foreground selection."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import warnings

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


def _manual_live_transport(repository, expected_login):
    # Same hidden, explicit input boundary as the reference consumer. Never
    # discover credentials or fall back to visible input or another account.
    import getpass
    from mothership_github.transport import GitHubRestTransport
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        token = getpass.getpass("GitHub token (hidden input; not stored): ", stream=sys.stderr)
    transport = GitHubRestTransport(token)
    return transport, transport.get_execution_access(repository, expected_login)


def main(argv=None):
    parser = argparse.ArgumentParser(description=(
        "Harness preview → retained Mothership Session → saved evidence. Synthetic by default; no model access."))
    for name in ("harness-cli", "request", "interpretation-file", "parameters", "worktree",
                 "run-directory", "host-context"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--json", action="store_true", help="print the same structured result as result.json")
    parser.add_argument("--live-github", action="store_true", help="explicit foreground GitHub operation; never retries")
    parser.add_argument("--expected-login", help="required selected account for --live-github")
    parser.add_argument("--gh-auth", action="store_true", help="explicitly use the selected GitHub CLI account")
    args = parser.parse_args(argv)
    if ((args.live_github and not args.expected_login)
            or (not args.live_github and (args.expected_login is not None or args.gh_auth))):
        parser.error("--live-github requires --expected-login; synthetic mode accepts neither")
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
        transport, access, credential_source = _SyntheticTransport(parameters), None, None
        if args.live_github:
            import re
            from orchestration.lib.action_authority import _validated_parameters
            from orchestration.lib.contracts import _SCHEMAS, _validate_schema
            from mothership.contracts import load_strict
            from .worktree_observer import GitWorktreeObserver
            parameters = _validated_parameters(parameters)
            # Reuse the bundled context contract without issuing a second
            # action/Session just to validate input before hidden token access.
            schema = load_strict(_SCHEMAS["authority-action-review-request"])
            _validate_schema(context, schema["properties"]["host_context"])
            if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", args.expected_login) is None:
                raise HandoffError("invalid selected account")
            observation = GitWorktreeObserver(args.worktree, parameters["repository"]).observe()
            run = Path(args.run_directory).absolute()
            if (not observation["clean"] or observation["head_sha"] != parameters["expected_head_sha"]
                    or run.resolve() != run or run.exists() or run.is_symlink()
                    or not run.parent.is_dir() or run.is_relative_to(Path(observation["worktree_realpath"]))
                    or type(context) is not dict or type(context.get("scope")) is not list
                    or "github.merge_pr" not in context["scope"]):
                raise HandoffError("live inputs unavailable")
            if args.gh_auth:
                from .gh_auth import load_secrets
                from mothership_github.transport import GitHubRestTransport
                token, gh_version = load_secrets("github", args.expected_login)
                transport = GitHubRestTransport(token)
                access = transport.get_execution_access(parameters["repository"], args.expected_login)
                credential_source = dict(source="gh", version=gh_version,
                                         host_id=context["host_id"], expected_login=args.expected_login)
            else:
                transport, access = _manual_live_transport(parameters["repository"], args.expected_login)
        executor_ref = dict(ref_id="executor:thin-handoff-live-v1" if args.live_github else "executor:thin-handoff-synthetic-v0",
                            sha256=hashlib.sha256(read_regular(__file__, 1_048_576)).hexdigest())
        owner = ThinHarnessOwner(
            parameters, preview=preview, raw_request=args.request, interpretation=interpretation,
            interpretation_bytes=interpretation_raw, worktree=args.worktree,
            run_directory=args.run_directory,
            host_context_provider=(lambda: decode_handoff_json(read_regular(args.host_context))) if args.live_github else (lambda: context),
            transport=transport, executor_ref=executor_ref,
            execution_mode="github_live" if args.live_github else "synthetic", execution_access=access)
        owner._write("harness-entry.json", json.dumps(dict(
            path=str(harness), sha256=hashlib.sha256(harness_bytes).hexdigest(),
            source="explicit_offline_entry", authenticated=False), sort_keys=True).encode())
        if credential_source is not None:
            owner._write("credential-source.json", json.dumps(credential_source, sort_keys=True).encode())
        answer = collect_response(owner.request, sys.stdin, sys.stderr, execution_access=access)
        if answer is None:
            owner.cancel()
        elif owner.review(answer) == "approve":
            owner.execute(parameters)
            if owner.export()["missing"] == ["verification"]:
                if args.live_github:
                    owner.readback_github()
                else:
                    owner.readback(opener=_unavailable_observation)
    except (Exception, KeyboardInterrupt):
        failed = True
        if owner is not None:
            owner.cancel()
    try:
        if owner is None:
            raise HandoffError("input unavailable")
        outcome = owner.save()
        if args.live_github and outcome["session_state"] == "finished":
            failed = failed or (outcome["inspection"]["receipt_status"] != "SUCCESS"
                                or outcome["inspection"]["verification_status"] != "CONFIRMED")
        text = (json.dumps(outcome, ensure_ascii=True, sort_keys=True) if args.json else
                ("EXPLICIT GITHUB MODE — inspect execution and independent observation separately\n" if args.live_github else
                 "LOCAL SYNTHETIC RUN — no real GitHub operation\n") + outcome["human"] +
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
