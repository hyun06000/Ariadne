#!/usr/bin/env python3
"""gilv3 splice-topology (C021) — cycle.yaml parent를 사이클 간 v3 엣지로 소급.

C020이 532 스텝을 각 사이클 안에서 노드로 편입했으나, 150개 분리된 섬이었다.
이 접합기는 cycle.yaml parent를 각 사이클 루트 지문에 Cycle-Parent notes로 소급해
섬들을 한 v3 체인 DAG로 잇는다.

⭐ C015 lineage=머지의 마이그레이션 판: cycle.yaml parent:[A,B]는 다중부모 계보(C012).
  살아있는 v3 사이클은 close --lineage로 머지 커밋(C015), 죽은 v2 사이클은 notes
  Cycle-Parent로 계보를 담는다 — 같은 lineage 개념, 다른 각인 수단.

⭐ 커밋 불변(C018): git notes append로 루트 지문에 Cycle-Parent 한 줄 덧붙임.
  cycle.yaml 파일도, 커밋 SHA도 안 바꾼다.
"""
import os, sys, subprocess, glob
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import full_ledger_migrate as FLM


def parse_parent(raw):
    """cycle.yaml parent 값 → 부모 사이클 id 리스트 (짧은 id로 정규화).
    'C014-gil-command-automation' → ['C014']  (숫자 id만, 슬러그 제거)
    '[C020-go-web-port, C016-number-ledger]' → ['C020','C016']
    'null' → []."""
    raw = raw.strip()
    if raw in ("null", ""):
        return []
    raw = raw.strip("[]")
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        # C014-slug → C014 (숫자 id만)
        import re
        m = re.match(r"(C\d+)", part)
        ids.append(m.group(1) if m else part)
    return ids


def short_id(full_id):
    """C015-merge-is-lineage-command → C015."""
    import re
    m = re.match(r"(C\d+)", full_id)
    return m.group(1) if m else full_id


def splice_cycle(repo, cycle_meta):
    """사이클 루트 지문에 Cycle-Parent 엣지를 notes로 append (커밋 불변).
    루트 = 그 사이클의 가장 이른 도출 노드 커밋(N 최소 — s1이든 s2든).
    반환: (루트_해시, 부모_id_리스트) 또는 None(도출 커밋 없음)."""
    chain, cid = cycle_meta["chain"], cycle_meta["id"]
    commits = FLM.cycle_step_commits(repo, chain, cid)
    if not commits:
        return None  # C020 도출 실패 사이클 — 여전히 섬(정직)
    root = commits[0]  # N 최소 = 사이클 시작 지문 커밋 (cycle_step_commits가 정렬)
    parents = parse_parent(cycle_meta.get("parent", "null"))
    cp_val = ", ".join(parents) if parents else "null"
    subprocess.run(["git", "-C", repo, "notes", "append", "-m",
                    "Cycle-Parent: %s" % cp_val, root],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return (root, parents)


def splice_all(repo):
    """전량 접합: C020이 도출한 사이클마다 Cycle-Parent 소급.
    반환: {spliced, roots, singles, merges, no_commit}."""
    cycles = FLM.discover_cycles(repo)
    stats = {"spliced": 0, "roots": 0, "singles": 0, "merges": 0, "no_commit": 0}
    for c in cycles:
        r = splice_cycle(repo, c)
        if r is None:
            stats["no_commit"] += 1
            continue
        _, parents = r
        stats["spliced"] += 1
        if len(parents) == 0:
            stats["roots"] += 1
        elif len(parents) == 1:
            stats["singles"] += 1
        else:
            stats["merges"] += 1
    return stats


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    stats = splice_all(repo)
    print("접합된 사이클: %d" % stats["spliced"])
    print("  루트(부모 0): %d · 선형(부모 1): %d · 머지(부모 ≥2): %d"
          % (stats["roots"], stats["singles"], stats["merges"]))
    print("  접합 못함(C020 도출 커밋 없음): %d" % stats["no_commit"])


if __name__ == "__main__":
    main()
