#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-/dev/cu.usbserial-0001}"
OUT="tools/terminal/transcripts/milestone-b-acceptance.txt"

now_utc() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

branch="$(git branch --show-current 2>/dev/null || echo unknown)"
commit="$(git rev-parse HEAD 2>/dev/null || echo unknown)"

mkdir -p "$(dirname "$OUT")"

{
  printf "# Milestone B Acceptance Transcript\n"
  printf "# Date: %s\n" "$(now_utc)"
  printf "# Branch: %s\n" "$branch"
  printf "# Commit: %s\n" "$commit"
  printf "# Port: %s\n" "$PORT"
  printf "\n## Setup\n"
  printf "%s\n" "- Starts by loading \`firmware/esp32/codignity.fs\` (muted; waits for \`ok\` per line)."
  printf "%s\n" "- Then runs protocol commands (each ends with \`! end\`)."
} >"$OUT"

tmp="$(mktemp -t codignity-milestone-b.XXXXXX)"
trap 'rm -f "$tmp"' EXIT
cat >"$tmp" <<'EOF'
# mute on
# until ok
# include firmware/esp32/codignity.fs
# mute off
# until end
meta id node1
meta role gateway
define : foo 123 ;
define : foo 456 ;
source
history
validate
safe-save
restart
# sleep 10
meta id
explain
?
source
history
EOF

{
  printf "\n## Commands + Output\n"
  .venv/bin/python tools/terminal/codignity_serial.py \
    --port "$PORT" \
    --until ok \
    --timeout 12 \
    --settle 4 \
    --echo-sent \
    --file "$tmp"
} | sed 's/\r$//' >>"$OUT"

printf "\nWrote %s\n" "$OUT" 1>&2
