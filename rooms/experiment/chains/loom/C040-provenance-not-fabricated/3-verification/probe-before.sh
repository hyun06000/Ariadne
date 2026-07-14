#!/usr/bin/env bash
# C040 사전 프로브 — 이슈 #17을 두 구현에서 재현한다 (수정 전 상태의 증거).
#
# 사용법:
#   bash probe-before.sh <저장소루트> <작업디렉토리>
# 예:
#   bash probe-before.sh /path/to/Ariadne /tmp/probe
#
# 관측 대상:
#   1) open이 --author 없이 무엇을 박는가        → author: clew (내 이름)
#   2) open이 --parent 없이 무엇을 박는가         → parent: null (두 번째 루트)
#   3) fsck는 다중 루트를 판정하는가              → "위반 0건"
#   4) log는 다중 루트를 보고 있는가              → "root: C001-…, C002-…"
set -u
REPO="${1:?저장소 루트를 인자로 달라}"
WORK="${2:?작업 디렉토리를 인자로 달라}"
SPEC="$REPO/rooms/deployment/ariadne-spec"

py()  { python3 "$SPEC/gil.py" "$@"; }
gob() { "$WORK/gil-bin" "$@"; }

rm -rf "$WORK" && mkdir -p "$WORK"
go build -o "$WORK/gil-bin" "$SPEC/go/main.go" || exit 1
cd "$WORK" || exit 1
git init -q -b main . && git config user.email t@t && git config user.name T

echo "=== 1) 참조 구현: 빈 체인의 첫 사이클, --author 미지정 ==="
py open eda first --title "첫" --new-chain
grep -E '^(author|parent):' rooms/experiment/chains/eda/C001-first/cycle.yaml

echo "=== 2) Go: 비어있지 않은 체인, --author·--parent 미지정 (maru의 상황) ==="
gob open eda second --title "둘"
grep -E '^(author|parent):' rooms/experiment/chains/eda/C002-second/cycle.yaml

echo "=== 3) fsck — 한 체인에 루트가 둘인데? ==="
py  fsck; echo "  참조 exit=$?"
gob fsck; echo "  Go   exit=$?"

echo "=== 4) log — 도구는 보고 있는가? ==="
py log | grep -E '^root:'
