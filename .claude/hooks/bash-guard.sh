#!/bin/bash
# Bash Guard Hook — PreToolUse[Bash]
# 되돌릴 수 없는 명령을 차단한다. 훅 입력은 stdin JSON(.tool_input.command)으로 들어오고,
# PreToolUse에서 실제로 막으려면 exit 2여야 한다(exit 1은 비차단 에러로 실행이 계속된다).

COMMAND=$(jq -r '.tool_input.command // empty')

if echo "$COMMAND" | grep -qE 'rm\s+-(rf|fr)|git\s+push\s+(.*\s)?(--force|-f)(\s|$)|git\s+reset\s+--hard|DROP\s+TABLE'; then
  echo "BLOCKED: 위험한 명령어가 감지되었습니다: $COMMAND" >&2
  exit 2
fi

exit 0
