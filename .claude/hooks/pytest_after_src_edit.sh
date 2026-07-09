#!/bin/bash
# PostToolUse hook: run the fast pytest suite after any edit under src/.
# Deterministic feedback loop — failures surface immediately, not at phase end.

INPUT=$(cat)
FILE=$(printf '%s' "$INPUT" | /usr/bin/python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

case "$FILE" in
  */src/sideout/*) ;;
  *) exit 0 ;;
esac

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR" 2>/dev/null || exit 0

# No tests yet? Nothing to run.
ls tests/test_*.py >/dev/null 2>&1 || exit 0

export PATH="$HOME/.local/bin:$PATH"
OUT=$(uv run pytest -x -q tests/ 2>&1)
STATUS=$?
if [ $STATUS -ne 0 ]; then
  echo "pytest FAILED after edit to $FILE:" >&2
  echo "$OUT" | tail -20 >&2
  exit 2   # feed failure back to Claude
fi
exit 0
