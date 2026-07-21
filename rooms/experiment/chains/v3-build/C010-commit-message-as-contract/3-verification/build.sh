#!/usr/bin/env bash
# C010 검증 — C012→C013→C014 트리를 gilv3 v0.5(trailer 각인) --git으로 각인한다.
# C008 build.sh와 동일 시퀀스이나 이 사이클 gilv3(trailer 계약면)를 쓴다.
# 임시 깃 저장소는 메인 레포 밖(스크래치패드) — 중첩 .git 방지 (C005 규율).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
G="python3 $HERE/gilv3.py"

SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/c0664b20-c4aa-4a97-8421-618e91963c15/scratchpad/c010-trailer}"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
git -C "$SCRATCH" init -q
git -C "$SCRATCH" config user.email "clew@ariadne.local"
git -C "$SCRATCH" config user.name "clew"
OUT="$SCRATCH/case"; mkdir -p "$OUT"

$G open "$OUT" --title "카드가 폴링마다 닫힌다 — 무엇이 열린 상태를 파괴하나" --git

$G step "$OUT" --kind hypothesis --note "상호작용·아코디언·detKey 차이가 원인" --git
$G step "$OUT" --kind verify     --note "헤드리스 CDP 재현 시도" --git
$G step "$OUT" --kind analyze --outcome backtrack --to s1 --note "재현 실패 — 환경 의존. 되돌아감." --git

$G step "$OUT" --kind hypothesis --to s1 --note "폴링 이분: --refresh 0이면 안 닫히나" --git
$G step "$OUT" --kind verify     --note "실판정이 실브라우저 필요" --git
$G step "$OUT" --kind analyze --outcome backtrack --to s1 --note "검증자가 판정 불가 — 되돌아감." --git

$G step "$OUT" --kind hypothesis --to s1 --note "swapRegions 통스왑이 열린 노드를 학살" --git
$G step "$OUT" --kind verify     --note "hasOpenDetails 가드 + JS 마커 헤드리스 관찰" --git
$G step "$OUT" --kind analyze --outcome success --note "노드 정체성 보존 — 채택. 산 잎." --git

$G close "$OUT" --git
echo "SCRATCH=$SCRATCH"
echo "OUT=$OUT"
