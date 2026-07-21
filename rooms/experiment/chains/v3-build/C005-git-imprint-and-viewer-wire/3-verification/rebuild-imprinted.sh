#!/usr/bin/env bash
# G1: 각인(--git) 켠 채 C012→C014 트리를 짓고, 스텝마다 커밋이 하나씩 나는지 관찰.
# 격리 임시 깃 저장소에서 — 메인 레포 원장 오염 0.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
G="python3 $HERE/gilv3.py"
# 격리 임시 저장소는 메인 레포 밖(중첩 .git 방지). 인자로 경로 받으면 그걸 씀.
OUT="${1:-${TMPDIR:-/tmp}/gilv3-imprinted-case}"
rm -rf "$OUT"; mkdir -p "$OUT"
git -C "$OUT" init -q
git -C "$OUT" config user.email v3@ariadne.local
git -C "$OUT" config user.name gilv3

count() { git -C "$OUT" rev-list --count HEAD 2>/dev/null || echo 0; }

$G open "$OUT" --title "카드가 폴링마다 닫힌다" --git
echo "  커밋수 after open: $(count)"
$G step "$OUT" --kind hypothesis --note "상호작용·detKey" --git
$G step "$OUT" --kind verify --note "헤드리스 재현 시도" --git
$G step "$OUT" --kind analyze --outcome backtrack --to s1 --note "재현 실패, 되돌아감" --git
$G step "$OUT" --kind hypothesis --to s1 --note "폴링 이분" --git
$G step "$OUT" --kind verify --note "실브라우저 계측 필요" --git
$G step "$OUT" --kind analyze --outcome backtrack --to s1 --note "판정 불가, 되돌아감" --git
$G step "$OUT" --kind hypothesis --to s1 --note "swapRegions 통스왑 의심" --git
$G step "$OUT" --kind verify --note "hasOpenDetails 가드 + JS 마커" --git
$G step "$OUT" --kind analyze --outcome success --note "노드 정체성 보존, 채택" --git
$G close "$OUT" --git
echo "  커밋수 after close: $(count)"

echo "=== git log (스텝=커밋 순서) ==="
git -C "$OUT" log --oneline --reverse | sed 's/^/  /'
echo "$OUT"
