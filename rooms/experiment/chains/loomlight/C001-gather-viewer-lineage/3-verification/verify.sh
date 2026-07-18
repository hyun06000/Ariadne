#!/usr/bin/env bash
# loomlight/C001 검증 재현 스크립트.
# 실행: 워크트리(또는 레포) 루트에서  bash rooms/experiment/chains/loomlight/C001-gather-viewer-lineage/3-verification/verify.sh
# 산출물은 이 스크립트 옆(3-verification/)에 저장된다.
set -euo pipefail

GIL="python3 rooms/deployment/ariadne-spec/gil.py"
ROOT="rooms/experiment/chains"
OUT="rooms/experiment/chains/loomlight/C001-gather-viewer-lineage/3-verification"
CID="C001-gather-viewer-lineage"

# 검증 대상 10개 뷰어 사이클 (전역 표기)
LINEAGE=(
  loom/C005-web-viewer
  loom/C013-realtime-step-visibility
  loom/C015-being-work-visibility
  loom/C020-go-web-port
  loom/C028-pages-command
  loom/C031-web-lane-layout
  loom/C042-viewer-follows-ledger
  loom/C047-web-topology-layout
  loom/C048-sibling-label-spacing
  loom/C049-live-viewer-refresh
)

echo "== 절차1: fsck (규칙 준수) =="
$GIL fsck "$ROOT" > "$OUT/fsck.txt" 2>&1 || true
grep -i "loomlight" "$OUT/fsck.txt" > "$OUT/fsck-loomlight.txt" 2>&1 || true
echo "  loomlight 관련 fsck 줄 수: $(wc -l < "$OUT/fsck-loomlight.txt" | tr -d ' ')"

echo "== 절차2: gil log (교차-체인 ⇠ 엣지) =="
$GIL log --chain loomlight "$ROOT" > "$OUT/log-loomlight.txt" 2>&1
$GIL log "$ROOT" > "$OUT/log-all.txt" 2>&1

echo "== 절차3: ⇠ lineage 엣지 개수 측정 =="
# C001 행에서 "⇠ lineage:" 뒤의 콤마 구분 참조 수를 센다
LINE=$(grep "$CID" "$OUT/log-loomlight.txt" | grep "⇠ lineage:" | head -1)
REFS=$(echo "$LINE" | sed 's/.*⇠ lineage: //' | tr ',' '\n' | sed '/^[[:space:]]*$/d' | wc -l | tr -d ' ')
{
  echo "C001 log 행:"
  echo "$LINE"
  echo ""
  echo "측정된 ⇠ lineage 참조 개수: $REFS (기대: 10)"
} > "$OUT/edge-count.txt"
echo "  측정 엣지 수: $REFS"

echo "== 절차4: chain.md 링크 해소 =="
{
  RESOLVED=0
  for l in "${LINEAGE[@]}"; do
    p="rooms/experiment/chains/${l}/5-report.md"
    if [ -f "$p" ]; then echo "OK   $l -> $p"; RESOLVED=$((RESOLVED+1)); else echo "MISS $l -> $p"; fi
  done
  echo ""
  echo "해소: $RESOLVED/10"
} > "$OUT/link-resolution.txt"
echo "  링크 해소: $(grep -c '^OK' "$OUT/link-resolution.txt")/10"

echo "== 절차5: 주제 일관성 (10 사이클 title) =="
{
  echo "10개 lineage 사이클의 title (뷰어 주제 일관성 확인):"
  echo ""
  for l in "${LINEAGE[@]}"; do
    id="${l#loom/}"
    t=$(grep -E '^title:' "rooms/experiment/chains/loom/${id}/cycle.yaml" | sed 's/^title: //')
    echo "- ${id}: ${t}"
  done
} > "$OUT/theme-coherence.txt"

echo ""
echo "== 요약 =="
echo "fsck loomlight 위반 줄: $(grep -c -iE 'R[0-9]' "$OUT/fsck-loomlight.txt" 2>/dev/null | head -1)"
echo "⇠ 엣지: $REFS/10"
echo "링크 해소: $(grep -c '^OK' "$OUT/link-resolution.txt")/10"
echo "산출물: $OUT/"
