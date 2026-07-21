#!/usr/bin/env bash
# verify.sh (C025) — 통합 계보 뷰어 재현 절차.
#
# 순수 git notes에서 두 층(사이클 간 DAG + 사이클 내 스텝 트리)을 재구성해
# 자기완결 드릴다운 HTML을 내고, 4측정(M1~M4)을 실측한다.
#
# 사용법:  bash verify.sh [<repo>]
#   <repo> 기본 = 이 저장소 루트(살아있는 원장, C022 마이그레이션 notes 적용됨).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="${1:-$(git -C "$HERE" rev-parse --show-toplevel)}"

echo "== 원장: $REPO =="

# 원장에 마이그레이션 notes가 없으면 먼저 migrate (클린 환경 재현).
NOTE_CNT=$(git -C "$REPO" notes list 2>/dev/null | wc -l | tr -d ' ')
if [ "$NOTE_CNT" -eq 0 ]; then
  echo "notes 부재 → gilv3 migrate 먼저 (재현)"
  python3 "$HERE/gilv3.py" migrate "$REPO"
fi

# 뷰어 생성
OUT="$(mktemp -d)/gilv3-web.html"
python3 "$HERE/gilv3.py" web "$REPO" -o "$OUT"
echo "생성: $OUT"

# 4측정
python3 "$HERE/measure.py" "$REPO"
