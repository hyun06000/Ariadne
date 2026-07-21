#!/usr/bin/env python3
"""C022 measure — 실제 원장 마이그레이션 적용의 5측정 감사.

격리 복제본에서 왕복(백업→적용→되돌림→재적용)을 처음부터 재현해 5측정을 판정한다.
⭐ 감사는 격리 복제본에서 한다 — 실제 원장은 이미 적용됐고, 이 측정은 그 절차가
   안전함(불변·되돌림)을 독립 재현으로 증명한다.

M1 커밋 불변 · M2 트리·cycle.yaml 불변 · M3 실제 재구성(C021 대조) ·
M4 되돌림 완전성 · M5 되돌림 후 원장 무손상.
"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import snapshot as SNAP

BACKUP_REF = "refs/notes-backup/pre-c022"
NOTES_REF = "refs/notes/commits"


def sh(cmd, repo=None, capture=True):
    args = ["git", "-C", repo] + cmd if repo else ["git"] + cmd
    r = subprocess.run(args, stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE)
    return r.stdout.decode().strip() if capture else None


def rev(repo, ref):
    r = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q", ref],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.stdout.decode().strip() or None


def dag_stats(repo):
    r = subprocess.run([sys.executable, os.path.join(HERE, "rebuild_cycle_dag.py"), repo],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = r.stdout.decode()
    import re
    nodes = int(re.search(r"복원: (\d+) 노드", out).group(1)) if "노드" in out else 0
    m = re.search(r"루트: (\d+) · 머지 노드: (\d+) · 총 엣지: (\d+)", out)
    roots, merges, edges = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (0, 0, 0)
    return {"nodes": nodes, "roots": roots, "merges": merges, "edges": edges}


def main():
    real_repo = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    scratch = sys.argv[2] if len(sys.argv) > 2 else "/tmp/c022-measure"
    clone = os.path.join(scratch, "clone")

    print("=== C022 measure — 격리 복제본 독립 재현 감사 ===")
    subprocess.run(["rm", "-rf", scratch]); os.makedirs(scratch, exist_ok=True)
    sh(["clone", "-q", real_repo, clone])
    sh(["config", "user.email", "clew@ariadne.local"], repo=clone)
    sh(["config", "user.name", "clew"], repo=clone)

    results = []

    # 기준 스냅샷 (적용 전)
    before = SNAP.snapshot(clone)

    # 국면 A+B: 백업 + 적용
    cur = rev(clone, NOTES_REF)
    if cur:
        sh(["update-ref", BACKUP_REF, cur], repo=clone)
    subprocess.run([sys.executable, os.path.join(HERE, "full_ledger_migrate.py"),
                    clone, "--apply"], stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, os.path.join(HERE, "splice_topology.py"), clone],
                   stdout=subprocess.DEVNULL)
    after = SNAP.snapshot(clone)

    # M1: 커밋 불변
    m1 = before["commit_shas"] == after["commit_shas"]
    results.append(("M1 커밋 불변",
                    "적용 전후 커밋 SHA %d==%d" % (before["commit_count"], after["commit_count"]),
                    m1))

    # M2: 트리·cycle.yaml 불변
    m2 = (before["worktree_status"] == after["worktree_status"]
          and before["cycle_yaml_hash"] == after["cycle_yaml_hash"])
    results.append(("M2 트리·cycle.yaml 불변",
                    "트리·cycle.yaml 해시 동일" if m2 else "변화 감지", m2))

    # M3: 실제 재구성 — C021 격리(131노드·130엣지·머지4) 대조
    dag = dag_stats(clone)
    m3 = dag["merges"] == 4 and dag["nodes"] >= 131 and dag["edges"] >= 130
    results.append(("M3 실제 재구성",
                    "DAG %d노드·%d엣지·머지%d (C021 131·130·4 이상, 머지 완전일치)"
                    % (dag["nodes"], dag["edges"], dag["merges"]), m3))

    # M4: 되돌림 완전성 — 백업(부재)로 되돌림 → notes 제거
    backup = rev(clone, BACKUP_REF)
    if backup:
        sh(["update-ref", NOTES_REF, backup], repo=clone)
    else:
        if rev(clone, NOTES_REF):
            sh(["update-ref", "-d", NOTES_REF], repo=clone)
    rolled = SNAP.snapshot(clone)
    m4 = (rolled["notes_ref"] == before["notes_ref"])  # 적용 전 상태 복귀
    results.append(("M4 되돌림 완전성",
                    "되돌림 후 notes_ref=%s (적용 전=%s)"
                    % (rolled["notes_ref"], before["notes_ref"]), m4))

    # M5: 되돌림 후 원장 무손상 — 커밋·cycle.yaml 불변, 재적용도 무손상
    m5a = (rolled["commit_shas"] == before["commit_shas"]
           and rolled["cycle_yaml_hash"] == before["cycle_yaml_hash"])
    # 재적용
    subprocess.run([sys.executable, os.path.join(HERE, "full_ledger_migrate.py"),
                    clone, "--apply"], stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, os.path.join(HERE, "splice_topology.py"), clone],
                   stdout=subprocess.DEVNULL)
    reapplied = SNAP.snapshot(clone)
    m5b = (reapplied["commit_shas"] == before["commit_shas"]
           and reapplied["cycle_yaml_hash"] == before["cycle_yaml_hash"])
    dag2 = dag_stats(clone)
    m5c = dag2["nodes"] == dag["nodes"] and dag2["edges"] == dag["edges"]
    m5 = m5a and m5b and m5c
    results.append(("M5 되돌림 후 원장 무손상",
                    "되돌림·재적용 거쳐도 커밋·cycle.yaml 불변, 재적용 DAG %d노드 동일"
                    % dag2["nodes"], m5))

    print()
    allpass = True
    for name, detail, ok in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
        print("      %s" % detail)
        allpass = allpass and ok
    print()
    print("=== %s ===" % ("ALL PASS → supported" if allpass else "일부 FAIL → 조사"))
    sys.exit(0 if allpass else 1)


if __name__ == "__main__":
    main()
