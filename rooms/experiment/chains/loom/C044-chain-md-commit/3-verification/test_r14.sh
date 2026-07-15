#!/usr/bin/env bash
# C044 T2 — fsck R14: 체인의 chain.md가 없으면 위반(exit 1)인가.
# 사용: test_r14.sh "<gil 호출>"
set -uo pipefail
GIL="$1"
WORK="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
git init -q; git config user.email t@example.com; git config user.name tester
ROOT="$WORK/rooms/experiment/chains"; mkdir -p "$ROOT"
$GIL open demo first --new-chain --title t --author me --root "$ROOT" --git >/dev/null

echo "--- (a) 정상: chain.md 있음 → 위반 0, exit 0 ---"
$GIL fsck "$ROOT" >/dev/null 2>&1; echo "exit=$?"

echo "--- (b) chain.md 삭제 → R14 위반, exit 1 ---"
rm "$ROOT/demo/chain.md"
OUT="$($GIL fsck "$ROOT" 2>/dev/null)"; RC=$?
echo "exit=$RC"
echo "$OUT" | grep -q '^R14' && echo "R14 검출: OK" || echo "R14 미검출: FAIL"
echo "$OUT" | grep '^R14' || true
