#!/usr/bin/env python3
"""notes_reconstruct (C025) — 순수 git notes에서 통합 뷰어의 두 데이터 층을 재구성.

상현님 결정 1(순수 v3): cycle.yaml 안 읽는다. 원장 git notes가 유일 진실원.

두 층:
  1. 사이클 간 DAG  — C021/C022 rebuild_cycle_dag 그대로 재사용 (Cycle-Parent notes 엣지).
  2. 사이클 내 스텝 트리 — 각 사이클 step 커밋의 notes 지문(Step-Id/Kind/Parent/Outcome/
     Backtrack-To)을 시퀀스로 모아 steps.yaml 등가 노드 리스트로.

⭐ 재구현 금지: 커밋 발견은 C023 full_ledger_migrate.cycle_step_commits 재사용,
   DAG는 C021 rebuild_cycle_dag 재사용. 여긴 notes 지문 → 노드 dict 파싱만 새로.
"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import full_ledger_migrate as FLM
from rebuild_cycle_dag import rebuild_cycle_dag  # 상위 DAG (C021/C022 자산)


_TRAILER_KEYS = ["Step-Id", "Kind", "Parent", "Outcome", "Backtrack-To"]


def _fingerprint_lines(repo, commit):
    """커밋의 v3 지문(Key: Value 라인)을 반환 — 두 각인 수단을 모두 지원.

    ⭐ 마이그레이션 사이클은 지문을 git notes에 담고(retro_imprint, C018), v3 네이티브
       사이클은 커밋 trailer에 담는다(gilv3 --git, C010). 통합 뷰어는 둘 다 비춰야 하므로
       notes를 먼저 읽고, 없으면 커밋 trailer로 폴백한다. 같은 파서가 둘을 읽는다
       ("notes 본문 = trailer와 동일한 Key: Value" — retro_imprint 계약)."""
    r = subprocess.run(["git", "-C", repo, "notes", "show", commit],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if r.returncode == 0 and r.stdout.decode().strip():
        return r.stdout.decode()
    # 폴백: 커밋 trailer (네이티브 v3). 각 키를 개별 조회해 Key: Value 라인 재구성.
    lines = []
    for k in _TRAILER_KEYS:
        v = subprocess.run(
            ["git", "-C", repo, "log", "-1",
             "--format=%%(trailers:key=%s,valueonly)" % k, commit],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode().strip()
        if v:
            lines.append("%s: %s" % (k, v))
    return "\n".join(lines)


def _parse_fingerprint(note_text):
    """notes 본문의 Key: Value 라인 → dict. Cycle-Parent 등 트리-무관 키는 별도.
    반환: (step_fields dict, cycle_parent_or_None)."""
    fields = {}
    cycle_parent = None
    for line in note_text.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if not k:
            continue
        if k == "Cycle-Parent":
            cycle_parent = v
        else:
            fields[k] = v
    return fields, cycle_parent


def reconstruct_step_tree(repo, chain, cid):
    """한 사이클의 step 커밋 notes 지문을 steps.yaml 등가 노드 리스트로 재구성.

    반환: [{id, kind, parent, outcome, backtrack, body}] (steptree.py가 아는 키).
    - 커밋 발견: C023 cycle_step_commits 재사용 (subject의 chain/cid 매칭, N 오름차순).
    - 각 커밋: git notes show → Step-Id/Kind/Parent/Outcome/Backtrack-To.
    - ⭐ H4 root 방어: 어떤 노드의 parent가 이 노드 집합에 없으면(마이그레이션 v2는
      s1(open)에 notes 없어 s2가 최이른), 그 parent를 None으로 정규화 → build_tree가
      root를 찾는다. notes가 담은 만큼만 비춘다(정직).
    - 지문 없는 커밋(빈 notes)은 스킵. 노드 0이면 빈 트리(섬).
    """
    commits = FLM.cycle_step_commits(repo, chain, cid)
    nodes = []
    for h in commits:
        note = _fingerprint_lines(repo, h)
        if not note.strip():
            continue
        f, _cp = _parse_fingerprint(note)
        sid = f.get("Step-Id")
        if not sid:
            continue
        parent = f.get("Parent")
        if parent in ("null", "", None):
            parent = None
        node = {
            "id": sid,
            "kind": f.get("Kind"),
            "parent": parent,
            "outcome": f.get("Outcome"),  # None if absent
            "backtrack": f.get("Backtrack-To"),
            "body": None,  # 통합 뷰어는 본문 임베드 안 함(순수 위상). C006는 단일 사이클용.
        }
        nodes.append(node)

    # H4 root 방어: parent가 노드 집합에 없으면 None으로 (root 승격).
    ids = {n["id"] for n in nodes}
    for n in nodes:
        if n["parent"] is not None and n["parent"] not in ids:
            n["parent"] = None
    return nodes


def all_cycles_with_trees(repo):
    """상위 DAG의 모든 사이클 키에 대해 스텝 트리를 재구성.

    반환: {
      'dag': {chain/short_id: [parents]},   # 상위 (rebuild_cycle_dag)
      'trees': {chain/short_id: [nodes]},   # 하위 (reconstruct_step_tree)
      'chain_of': {chain/short_id: chain},  # 라벨용
      'cid_of': {chain/short_id: cid},      # 라벨용
    }
    - DAG 키(chain/short_id)를 진실원으로. 각 키의 실제 full cid를 cycle_step_commits용으로
      복원해야 하므로, discover_cycles로 short→full 매핑을 만든다(cycle.yaml은 '어느 사이클이
      있나'의 목록으로만 쓰고 계보/스텝 데이터는 안 읽음 — 순수 notes 유지).
    """
    from splice_topology import short_id
    dag = rebuild_cycle_dag(repo)

    # short_id → full cid 매핑 (커밋 발견에 full cid 필요). cycle.yaml은 목록으로만.
    full_of = {}
    for c in FLM.discover_cycles(repo):
        key = "%s/%s" % (c["chain"], short_id(c["id"]))
        full_of[key] = c["id"]

    trees, chain_of, cid_of = {}, {}, {}
    for key in dag:
        chain, short = key.split("/", 1)
        full = full_of.get(key, short)
        trees[key] = reconstruct_step_tree(repo, chain, full)
        chain_of[key] = chain
        cid_of[key] = short
    return {"dag": dag, "trees": trees, "chain_of": chain_of, "cid_of": cid_of}


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    data = all_cycles_with_trees(repo)
    dag = data["dag"]
    n_nodes = len(dag)
    n_edges = sum(len(p) for p in dag.values())
    n_empty = sum(1 for k, t in data["trees"].items() if not t)
    n_backtrack = sum(1 for t in data["trees"].values()
                      if any(n.get("backtrack") for n in t))
    print("상위 DAG: %d 노드 · %d 엣지" % (n_nodes, n_edges))
    print("하위 스텝 트리: %d 사이클 · 빈 트리(섬) %d · backtrack 보유 %d"
          % (len(data["trees"]), n_empty, n_backtrack))
    if "--full" in sys.argv:
        for k in sorted(data["trees"]):
            t = data["trees"][k]
            print("  %s: %d노드 %s" % (k, len(t),
                  "[backtrack]" if any(n.get("backtrack") for n in t) else ""))


if __name__ == "__main__":
    main()
