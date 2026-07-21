#!/usr/bin/env python3
"""gilv3 rebuild-cycle-dag (C021) — 접합된 notes에서 사이클 간 DAG 복원.

C021 splice_topology가 각 사이클 루트에 Cycle-Parent notes를 소급했다. 이 재구성기는
그것을 읽어 사이클 간 DAG를 복원한다 — 150 섬이 이어진 그래프.

오직 git notes만 읽는다(cycle.yaml·커밋 내용 안 봄). C009~C020 재구성 리듬 계승.
"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import full_ledger_migrate as FLM


def rebuild_cycle_dag(repo):
    """각 사이클 루트 notes의 Cycle-Parent를 읽어 사이클 DAG 복원.
    반환: {cycle_id(short): [parent_ids]} — 루트(빈)·선형(1)·머지(≥2).

    루트 커밋 찾기: 각 사이클의 시작 지문 커밋(C020 도출)에서 Cycle-Parent notes.
    cycle.yaml을 안 보고 notes만으로 — 진짜 복원(마이그레이션 왕복)."""
    cycles = FLM.discover_cycles(repo)
    dag = {}
    for c in cycles:
        chain, cid = c["chain"], c["id"]
        commits = FLM.cycle_step_commits(repo, chain, cid)
        if not commits:
            continue
        root = commits[0]
        note = subprocess.run(["git", "-C", repo, "notes", "show", root],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if note.returncode != 0:
            continue
        cp = None
        for line in note.stdout.decode().splitlines():
            if line.startswith("Cycle-Parent:"):
                cp = line.split(":", 1)[1].strip()
                break
        if cp is None:
            continue
        parents = [] if cp == "null" else [p.strip() for p in cp.split(",") if p.strip()]
        from splice_topology import short_id
        # ⭐ C021 함정: 키를 short_id(C001)로만 하면 체인 간 충돌(loom/C001·v3-build/C001).
        # cycle id는 체인 안에서만 유일 → 키는 chain/short_id 로 전역 유일화.
        dag["%s/%s" % (chain, short_id(cid))] = parents
    return dag


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    dag = rebuild_cycle_dag(repo)
    roots = [c for c, ps in dag.items() if not ps]
    merges = [c for c, ps in dag.items() if len(ps) >= 2]
    total_edges = sum(len(ps) for ps in dag.values())
    print("사이클 DAG 복원: %d 노드" % len(dag))
    print("  루트: %d · 머지 노드: %d · 총 엣지: %d" % (len(roots), len(merges), total_edges))
    if "--full" in sys.argv:
        for c in sorted(dag):
            print("  %s → %s" % (c, dag[c] or "(루트)"))


if __name__ == "__main__":
    main()
