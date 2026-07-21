#!/usr/bin/env bash
# C012→C013→C014 스텝 트리를 gilv3 명령만으로 처음부터 짓는다.
# 트리: s1(define) 아래 세 형제 가지 — C012(s2-4 죽음)·C013(s5-7 죽음)·C014(s8-10 산).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
G="python3 $HERE/gilv3.py"
OUT="$HERE/built-case"
rm -rf "$OUT"; mkdir -p "$OUT"

# 루트 문제정의 P0
$G open "$OUT" --title "카드가 폴링마다 닫힌다 — 무엇이 열린 상태를 파괴하나"

# 가지 1 — C012 (상호작용/detKey 가설, 죽은 잎)
$G step "$OUT" --kind hypothesis --note "상호작용·아코디언·detKey 차이가 원인"
$G step "$OUT" --kind verify     --note "헤드리스 CDP 재현 시도"
$G step "$OUT" --kind analyze --outcome backtrack --to s1 --note "재현 실패 — 환경 의존, 세 길 배제. 되돌아감."

# 가지 2 — C013 (폴링 이분, 죽은 잎)  ← s1으로 되돌아가 난 형제
$G step "$OUT" --kind hypothesis --to s1 --note "폴링 이분: --refresh 0이면 안 닫히나"
$G step "$OUT" --kind verify     --note "실판정이 실브라우저(내 손 밖 계측기) 필요"
$G step "$OUT" --kind analyze --outcome backtrack --to s1 --note "검증자가 판정 불가 — 되돌아감."

# 가지 3 — C014 (노드 정체성, 산 잎)  ← s1으로 되돌아가 난 형제
$G step "$OUT" --kind hypothesis --to s1 --note "swapRegions 통스왑이 열린 노드를 학살"
$G step "$OUT" --kind verify     --note "hasOpenDetails 가드 + JS 마커 헤드리스 관찰"
$G step "$OUT" --kind analyze --outcome success --note "노드 정체성 보존 — 채택. 산 잎."

$G close "$OUT"
echo "=== built tree ==="
$G status "$OUT"
echo "$OUT"
