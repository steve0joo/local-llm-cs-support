#!/bin/bash
# TDD Guard Hook — PreToolUse[Edit|Write]
# 구현 코드를 작성하려 할 때, 해당 모듈의 테스트 파일이 먼저 존재하는지 체크.
# 테스트 없이 구현 코드를 작성하려 하면 차단.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# 파일 경로가 없으면 통과
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# 패턴은 repo 기준 상대 경로로 매칭한다. 절대 경로로 매칭하면 repo가 이름에 "test"가 든
# 디렉터리 아래 있을 때 모든 파일이 테스트로 오인돼 가드가 꺼진다.
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
REL_PATH="/${FILE_PATH#"$PROJECT_ROOT"/}"
BASE_NAME=$(basename "$FILE_PATH")

# 테스트 파일 자체를 수정하는 건 허용 (파일명 또는 테스트 디렉터리 기준)
case "$BASE_NAME" in
  test_*|*_test.*|*.test.*|*.spec.*)
    exit 0
    ;;
esac
case "$REL_PATH" in
  */tests/*|*/test/*|*/__tests__/*|*/spec/*)
    exit 0
    ;;
esac

# 설정/타입/스타일 파일은 테스트 불필요 — 허용
case "$REL_PATH" in
  *.json|*.jsonl|*.css|*.scss|*.md|*.yml|*.yaml|*.toml|*.txt|*.sh|*.env*|*.config.*|*tailwind*|*postcss*|*next.config*|*tsconfig*)
    exit 0
    ;;
esac

# Python 설정·패키지 보일러플레이트는 테스트 불필요 — 허용
case "$REL_PATH" in
  */__init__.py|*/conftest.py|*/config.py|*/settings.py|*/setup.py)
    exit 0
    ;;
esac

# types/ 폴더는 테스트 불필요 — 허용
case "$REL_PATH" in
  */types/*|*/types.ts|*/types.d.ts)
    exit 0
    ;;
esac

# Next.js 프레임워크 파일은 허용 (layout, page, loading, error, not-found, global styles)
case "$REL_PATH" in
  */layout.tsx|*/layout.ts|*/page.tsx|*/page.ts|*/loading.tsx|*/error.tsx|*/not-found.tsx|*/globals.css)
    exit 0
    ;;
esac

# lib/ 또는 소스 파일이면 테스트 파일 존재 여부 확인
case "$REL_PATH" in
  *.ts|*.tsx|*.js|*.jsx)
    # 파일명 추출
    DIR=$(dirname "$FILE_PATH")
    BASENAME=$(basename "$FILE_PATH" | sed -E 's/\.(ts|tsx|js|jsx)$//')

    # 테스트 파일 후보 경로들
    TEST_FOUND=false

    # 같은 폴더에 .test 파일
    for EXT in ts tsx js jsx; do
      if [ -f "${DIR}/${BASENAME}.test.${EXT}" ] || [ -f "${DIR}/${BASENAME}.spec.${EXT}" ]; then
        TEST_FOUND=true
        break
      fi
    done

    # __tests__ 폴더
    if [ "$TEST_FOUND" = false ]; then
      PARENT=$(dirname "$DIR")
      for EXT in ts tsx js jsx; do
        if [ -f "${PARENT}/__tests__/${BASENAME}.test.${EXT}" ] || [ -f "${DIR}/__tests__/${BASENAME}.test.${EXT}" ]; then
          TEST_FOUND=true
          break
        fi
      done
    fi

    # src/__tests__/ 루트 테스트 폴더
    if [ "$TEST_FOUND" = false ]; then
      for EXT in ts tsx js jsx; do
        if [ -f "${PROJECT_ROOT}/src/__tests__/${BASENAME}.test.${EXT}" ]; then
          TEST_FOUND=true
          break
        fi
      done
    fi

    if [ "$TEST_FOUND" = false ]; then
      cat << EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "TDD GUARD: '${BASENAME}'에 대한 테스트 파일이 존재하지 않습니다. 구현 코드를 작성하기 전에 테스트를 먼저 작성하세요. (테스트 파일 예: ${BASENAME}.test.ts)"
  }
}
EOF
    fi
    ;;

  *.py)
    # 테스트 파일 후보: test_<모듈>.py · test_<모듈>_*.py · <모듈>_test.py (repo 어디든, 가상환경 제외)
    BASENAME=$(basename "$FILE_PATH" .py)
    MATCH=$(find "$PROJECT_ROOT" \( -name .git -o -name node_modules -o -name .venv -o -name venv -o -name __pycache__ \) -prune -o \
      -type f \( -name "test_${BASENAME}.py" -o -name "test_${BASENAME}_*.py" -o -name "${BASENAME}_test.py" \) -print 2>/dev/null | head -1)

    if [ -z "$MATCH" ]; then
      cat << EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "TDD GUARD: '${BASENAME}'에 대한 테스트 파일이 존재하지 않습니다. 구현 코드를 작성하기 전에 테스트를 먼저 작성하세요. (테스트 파일 예: tests/test_${BASENAME}.py)"
  }
}
EOF
    fi
    ;;
esac

exit 0
