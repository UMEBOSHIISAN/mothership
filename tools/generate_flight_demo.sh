#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
owned_tmp="$(mktemp -d "${TMPDIR:-/tmp}/mothership-flight-demo.XXXXXX")"
trap 'rm -rf -- "$owned_tmp"' EXIT

python_bin="${PYTHON:-python3}"
safe_output="$owned_tmp/safe.json"
drift_output="$owned_tmp/drift.json"
safe_frame_text="$owned_tmp/safe-frame.txt"
drift_frame_text="$owned_tmp/drift-frame.txt"
safe_frame="$owned_tmp/safe.png"
drift_frame="$owned_tmp/drift.png"
transcript="$repo_root/docs/generated/flight-demo-transcript.txt"
gif="$repo_root/assets/flight-demo.gif"

cd "$repo_root"

"$python_bin" -m mothership demo safe >"$safe_output"

set +e
"$python_bin" -m mothership demo drift >"$drift_output"
drift_status=$?
set -e
if [[ "$drift_status" -ne 21 ]]; then
    echo "expected drift demo exit 21, received $drift_status" >&2
    exit 1
fi

cmp -s "$safe_output" docs/generated/flight-safe-output.json || {
    echo "safe demo output drifted from checked-in evidence" >&2
    exit 1
}
cmp -s "$drift_output" docs/generated/flight-drift-output.json || {
    echo "drift demo output drifted from checked-in evidence" >&2
    exit 1
}

{
    printf '$ mothership demo safe\n'
    cat "$safe_output"
    printf '[exit 0]\n\n$ mothership demo drift\n'
    cat "$drift_output"
    printf '[exit 21]\n'
} >"$owned_tmp/transcript.txt"
cp "$owned_tmp/transcript.txt" "$transcript"

{
    printf '$ mothership demo safe\n'
    cat "$safe_output"
    printf '[exit 0]\n'
} >"$safe_frame_text"
{
    printf '$ mothership demo drift\n'
    cat "$drift_output"
    printf '[exit 21]\n'
} >"$drift_frame_text"

/usr/bin/swift tools/render_terminal_frame.swift safe \
    'Mothership Flight Recorder / safe path' "$safe_frame_text" "$safe_frame"
/usr/bin/swift tools/render_terminal_frame.swift drift \
    'Mothership Flight Recorder / scope drift' "$drift_frame_text" "$drift_frame"

ffmpeg -hide_banner -loglevel error -y \
    -loop 1 -t 3 -i "$safe_frame" \
    -loop 1 -t 4 -i "$drift_frame" \
    -filter_complex \
    '[0:v][1:v]concat=n=2:v=1:a=0,fps=8,split[frames][palette_input];[palette_input]palettegen=stats_mode=diff[palette];[frames][palette]paletteuse=dither=bayer:bayer_scale=3' \
    -loop 0 "$gif"

printf 'wrote %s\nwrote %s\n' "$transcript" "$gif"
