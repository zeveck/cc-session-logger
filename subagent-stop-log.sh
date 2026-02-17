#!/bin/bash
# Session logger for subagents. Runs in the SubagentStop hook.
# Parallel to stop-log.sh but reads subagent-specific fields.
# Exits 0 always.

export TZ="${TZ:-__TZ__}"

INPUT=$(cat)

eval "$(echo "$INPUT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'TRANSCRIPT_PATH={chr(34)}{d.get(\"agent_transcript_path\", \"\")}{chr(34)}')
print(f'SESSION_ID={chr(34)}{d.get(\"session_id\", \"unknown\")}{chr(34)}')
print(f'AGENT_ID={chr(34)}{d.get(\"agent_id\", \"unknown\")}{chr(34)}')
print(f'AGENT_TYPE={chr(34)}{d.get(\"agent_type\", \"subagent\")}{chr(34)}')
")"

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

# Wait for transcript to finish flushing (file size stabilizes)
PREV_SIZE=-1
for _ in 1 2 3 4 5 6 7 8 9 10; do
  CURR_SIZE=$(wc -c < "$TRANSCRIPT_PATH" 2>/dev/null || echo 0)
  [ "$CURR_SIZE" = "$PREV_SIZE" ] && break
  PREV_SIZE=$CURR_SIZE
  sleep 0.2
done

# Extract start timestamp from first record that has one, convert to local time
START_TS=$(python3 -c "
import json, sys
for line in sys.stdin:
    try:
        ts = json.loads(line).get('timestamp')
        if ts:
            print(ts)
            break
    except (json.JSONDecodeError, AttributeError):
        pass
" < "$TRANSCRIPT_PATH" 2>/dev/null)
if [ -n "$START_TS" ]; then
  DATE=$(date -d "$START_TS" +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)
  TIME_PART=$(date -d "$START_TS" +%H%M 2>/dev/null || echo "0000")
  LOCAL_TS=$(date -d "$START_TS" --iso-8601=seconds 2>/dev/null || echo "$START_TS")
else
  DATE=$(date +%Y-%m-%d)
  TIME_PART="0000"
  LOCAL_TS=""
fi

mkdir -p .claude/logs

SCRIPT_DIR="$(dirname "$0")"
SHORT_SESSION=$(echo "$SESSION_ID" | cut -c1-8)
SHORT_AGENT=$(echo "$AGENT_ID" | cut -c1-8)
LOG_FILE=".claude/logs/${DATE}-${TIME_PART}-${SHORT_SESSION}-subagent-${AGENT_TYPE}-${SHORT_AGENT}.md"

python3 "${SCRIPT_DIR}/log-converter.py" \
  --transcript "$TRANSCRIPT_PATH" \
  --output "$LOG_FILE" \
  --session-id "$SESSION_ID" \
  --date "$DATE" \
  --start-time "$LOCAL_TS" \
  --agent-type "$AGENT_TYPE" \
  --agent-id "$AGENT_ID" \
  >/dev/null 2>> .claude/logs/.converter-errors.log

# Remove error log if empty — its presence is the signal
[ -f .claude/logs/.converter-errors.log ] && [ ! -s .claude/logs/.converter-errors.log ] \
  && rm .claude/logs/.converter-errors.log

exit 0
