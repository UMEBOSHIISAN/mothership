"""Optional GitHub observation CLI; no mutation command or credential discovery."""
from __future__ import annotations
import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {'github-decision-card', 'github-candidate-window'}:
        from mothership.cli import main as core_main
        return core_main(arguments)
    parser = argparse.ArgumentParser(prog='mothership-github',
        description='Read-only GitHub observation; also supports github-decision-card and github-candidate-window')
    commands = parser.add_subparsers(dest='command')
    observe = commands.add_parser('observe-pr', help='Observe one public PR without ambient credentials')
    observe.add_argument('--repo', required=True)
    observe.add_argument('--pr', type=int, required=True)
    args = parser.parse_args(arguments)
    if args.command is None:
        parser.print_help()
        return 1
    from .observation import GitHubObservationAdapter
    try:
        snapshot = GitHubObservationAdapter().observe_candidate_pr(args.repo, args.pr)
        sys.stdout.write(json.dumps(snapshot, indent=2) + '\n')
    except (ValueError, OSError, UnicodeError):
        try:
            sys.stderr.write('observe-pr: unable to obtain observation\n')
        except (OSError, UnicodeError):
            pass
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
