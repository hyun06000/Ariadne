#!/usr/bin/env bash
# C021 검증 — cycle.yaml parent를 사이클 간 v3 엣지로 접합 (격리 복제본).
#
# 흐름: 우리 저장소 clone → C020 노드 소급 → C021 엣지 접합 → 사이클 DAG 재구성.
# ⭐ 격리 철칙: 우리 실제 저장소는 절대 안 건드린다.
set -e
SCRATCH="${1:-/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c021-splice}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REAL_REPO="$(cd "$HERE/../../../../../.." && pwd)"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
CLONE="$SCRATCH/clone"

echo "=== 격리 복제본 clone 중... ==="
git clone -q "$REAL_REPO" "$CLONE"
git -C "$CLONE" config user.email "clew@ariadne.local"
git -C "$CLONE" config user.name "clew"

echo ""
echo "=== 1단계: C020 노드 소급 (사이클 내부) ==="
python3 "$HERE/full_ledger_migrate.py" "$CLONE" --apply | head -4

echo ""
echo "=== 2단계: C021 엣지 접합 (사이클 간) ==="
python3 "$HERE/splice_topology.py" "$CLONE"

echo ""
echo "=== 3단계: 사이클 DAG 재구성 (notes만으로) ==="
python3 "$HERE/rebuild_cycle_dag.py" "$CLONE"

echo ""
echo "=== cycle.yaml 실제 집계 (대조 기준) ==="
python3 - "$REAL_REPO" <<'PY'
import sys, glob, os, re
repo = sys.argv[1]
roots=singles=merges=0
for p in glob.glob(os.path.join(repo,"rooms/experiment/chains/*/*/cycle.yaml")):
    for line in open(p):
        line=line.split("#")[0]
        if line.startswith("parent:"):
            v=line.split(":",1)[1].strip()
            if v in ("null",""): roots+=1
            elif v.startswith("["): merges+=1
            else: singles+=1
            break
print(f"cycle.yaml 집계: 루트 {roots} · 선형 {singles} · 머지 {merges} (총 {roots+singles+merges})")
PY

echo ""
echo "SCRATCH=$SCRATCH"
echo "CLONE=$CLONE"
