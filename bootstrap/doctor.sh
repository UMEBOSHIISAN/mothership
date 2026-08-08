#!/bin/sh
# Resolve this non-symlink wrapper, then hand its original arguments to the package CLI.

case "$0" in
  *'
'*) exit 2 ;;
esac

case "$0" in
  */*) wrapper=$0 ;;
  *) wrapper=$(command -v "$0") || exit 2 ;;
esac

case "$wrapper" in
  *'
'*) exit 2 ;;
  /*) ;;
  *) wrapper=$(pwd -P)/$wrapper ;;
esac

[ -L "$wrapper" ] && exit 2
[ -f "$wrapper" ] && [ -x "$wrapper" ] || exit 2
wrapper_dir=$(CDPATH= cd -P "$(dirname "$wrapper")" && pwd -P) || exit 2
doctor=$wrapper_dir/../orchestration/bin/llm-doctor

[ -L "$doctor" ] && exit 2
[ -f "$doctor" ] && [ -x "$doctor" ] || exit 2
exec "$doctor" "$@"
