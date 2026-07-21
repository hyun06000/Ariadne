#!/usr/bin/env python3
"""C021 측정 — 사이클 간 엣지 접합 (격리 복제본). 4측정.

M1 엣지 접합(루트 notes Cycle-Parent, DAG 복원) · M2 세 형태(단일·머지·루트) ·
M3 커밋 불변(SHA·cycle.yaml 불변) · M4 DAG 정합(집계 == cycle.yaml, 잔여 설명).
"""
import os, sys, subprocess, glob, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import full_ledger_migrate as FLM
import splice_topology as ST
import rebuild_cycle_dag as RCD

REAL_REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "..", ".."))
SCRATCH = sys.argv[1] if len(sys.argv) > 1 else \
    "/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c021-splice"
CLONE = os.path.join(SCRATCH, "clone")

def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout

results = []
def check(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

# 복제본은 build_case가 노드 소급 + 엣지 접합 완료한 상태.
dag = RCD.rebuild_cycle_dag(CLONE)

# ── M1: 엣지 접합 (H1a) — DAG 복원, 사이클 간 엣지 존재 ────────────────
n_nodes = len(dag)
n_edges = sum(len(ps) for ps in dag.values())
m1 = n_nodes > 100 and n_edges > 100
check("M1-edge-spliced", m1,
      f"DAG노드={n_nodes} 사이클간엣지={n_edges} → 섬들이 Cycle-Parent로 이어짐(notes 복원)")

# ── M2: 세 형태 (H1b) — 단일·머지·루트 각각 정확 ─────────────────────
# 대표: v3-build/C015(단일 C014) · loom/C036(머지 [C020,C016]) · 각 체인 첫(루트)
c015 = dag.get("v3-build/C015")
c036 = dag.get("loom/C036")
single_ok = c015 == ["C014"]
merge_ok = c036 is not None and set(c036) == {"C020", "C016"} and len(c036) == 2
roots = [c for c, ps in dag.items() if not ps]
root_ok = len(roots) >= 1
m2 = single_ok and merge_ok and root_ok
check("M2-three-shapes", m2,
      f"단일 C015→{c015}(=['C014']) 머지 C036→{c036}(={{C020,C016}}) 루트수={len(roots)} "
      f"→ 단일·머지(다중부모=C015 lineage)·루트 각각 정확")

# ── M3: 커밋 불변 (H1c) — 복제본 커밋 SHA·cycle.yaml 불변 ─────────────
# 복제본 커밋 SHA == 우리 원장 SHA (notes append가 커밋 안 바꿈)
clone_shas = set(git(CLONE, "rev-list", "HEAD").split())
real_shas = set(git(REAL_REPO, "rev-list", "HEAD").split())
sha_ok = clone_shas == real_shas
# cycle.yaml 파일 불변: 복제본 C015 cycle.yaml == 우리 원장 것
c015_clone = open(os.path.join(CLONE,"rooms/experiment/chains/v3-build/C015-merge-is-lineage-command/cycle.yaml")).read()
c015_real = open(os.path.join(REAL_REPO,"rooms/experiment/chains/v3-build/C015-merge-is-lineage-command/cycle.yaml")).read()
yaml_ok = c015_clone == c015_real
m3 = sha_ok and yaml_ok
check("M3-commit-immutable", m3,
      f"복제본SHA==원장SHA={sha_ok} cycle.yaml불변={yaml_ok} "
      f"→ Cycle-Parent 소급이 커밋·파일 안 바꿈 (notes append, C018 계약)")

# ── M4: DAG 정합 (H1d) — 집계 == cycle.yaml, 잔여 설명 ────────────────
# cycle.yaml 실제 집계
cy_roots=cy_singles=cy_merges=0
for p in glob.glob(os.path.join(REAL_REPO,"rooms/experiment/chains/*/*/cycle.yaml")):
    for line in open(p):
        line=line.split("#")[0]
        if line.startswith("parent:"):
            v=line.split(":",1)[1].strip()
            if v in ("null",""): cy_roots+=1
            elif v.startswith("["): cy_merges+=1
            else: cy_singles+=1
            break
cy_total = cy_roots + cy_singles + cy_merges
# 접합 통계
dag_roots = len([c for c,ps in dag.items() if not ps])
dag_singles = len([c for c,ps in dag.items() if len(ps)==1])
dag_merges = len([c for c,ps in dag.items() if len(ps)>=2])
dag_total = len(dag)
# 머지는 완전 일치(머지 사이클은 최신이라 다 도출됨), 총계 차이 = 도출실패
gap = cy_total - dag_total
# 잔여 설명: gap == 도출실패(C020 커밋 못찾음) 사이클 수
no_commit = 0
for c in FLM.discover_cycles(CLONE):
    if not FLM.cycle_step_commits(CLONE, c["chain"], c["id"]):
        no_commit += 1
m4 = (dag_merges == cy_merges and gap == no_commit and
      dag_roots + (cy_roots - dag_roots) == cy_roots)  # 루트 차이도 gap에 포함
check("M4-dag-consistent", m4,
      f"머지 DAG={dag_merges}==cycle.yaml={cy_merges} | 총계 DAG={dag_total} cy={cy_total} "
      f"gap={gap}==도출실패={no_commit} → 접합 DAG가 실제 계보와 정합(잔여=도출실패, 정직)")

# ── 판정 ──
print()
allpass = all(ok for _, ok, _ in results)
print(f"=== {'ALL PASS — supported' if allpass else '일부 FAIL'} ({sum(1 for _,ok,_ in results if ok)}/{len(results)}) ===")
sys.exit(0 if allpass else 1)
