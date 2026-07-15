#!/usr/bin/env bash
# C044 결함 재현/회귀 스크립트 — open --new-chain --git이 chain.md를 커밋하는가.
# 사용: repro.sh "<gil 호출>"   예) repro.sh "python3 /abs/gil.py"  또는  repro.sh /tmp/gil-go
# 수정 전: chain.md가 untracked로 남는다(결함).  수정 후: HEAD 커밋에 포함, 트리 깨끗.
set -euo pipefail
GIL="$1"
WORK="$(cd "$(mktemp -d)" && pwd -P)"   # pwd -P: /var→/private/var 심링크 정규화 (파이썬 relpath 대비)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
git init -q
git config user.email t@example.com
git config user.name tester
ROOT="$WORK/rooms/experiment/chains"
mkdir -p "$ROOT"

$GIL open demo first-step --new-chain --title "재현" --author me --root "$ROOT" --git >/dev/null

echo "=== git status --porcelain (수정 후엔 비어 있어야) ==="
git status --porcelain
echo "=== chain.md가 추적되는가 (수정 후엔 경로 출력) ==="
git ls-files rooms/experiment/chains/demo/chain.md
echo "=== chain.md가 HEAD 커밋에 있는가 (수정 후엔 경로 출력) ==="
git show --name-only --format= HEAD | grep 'demo/chain.md' || echo "(HEAD에 chain.md 없음 — 결함)"
