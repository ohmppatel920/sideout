#!/bin/bash
# PreToolUse hook: block any git add/commit that would introduce video files
# outside the allowed paths. Deterministic guard for the sideOut rule:
# raw video is NEVER committed. Two exceptions are allowed:
#   - samples/demo.mp4|mov       the single raw sample clip
#   - demo/assets/*.mp4          the DERIVED, web-encoded overlay for the
#                                published demo (a rendered artifact, not raw
#                                footage) — approved for GitHub Pages hosting.
# Exit 2 blocks the tool call; exit 0 allows.

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | /usr/bin/python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)

# Only inspect git add / git commit commands.
case "$CMD" in
  *"git add"*|*"git commit"*) ;;
  *) exit 0 ;;
esac

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR" 2>/dev/null || exit 0

# Check staged files (covers `git add -A` followed by commit, and adds already made).
BAD=$(git diff --cached --name-only 2>/dev/null | grep -iE '\.(mp4|mov|avi|mkv|m4v|webm)$' | grep -vE '^(samples/demo\.(mp4|mov)|demo/assets/.*\.mp4)$')
if [ -n "$BAD" ]; then
  echo "BLOCKED: video staged outside samples/demo.*: $BAD — sideOut never commits raw video (SPEC.md)." >&2
  exit 2
fi

# For `git add`, also check paths named directly in the command.
if printf '%s' "$CMD" | grep -q "git add"; then
  for TOKEN in $CMD; do
    case "$TOKEN" in
      samples/demo.mp4|samples/demo.mov) ;;
      demo/assets/*.mp4) ;;
      *.mp4|*.mov|*.avi|*.mkv|*.m4v|*.webm)
        echo "BLOCKED: git add of video '$TOKEN' — sideOut never commits raw video (SPEC.md)." >&2
        exit 2
        ;;
    esac
  done
fi

exit 0
