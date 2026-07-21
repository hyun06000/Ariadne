#!/usr/bin/env python3
"""C023 measure — gil migrate 명령을 C022 스크립트(오라클)와 대조하는 5측정.

각 측정마다 신선한 격리 복제본을 떠서(우리 원장 불변) 명령과 오라클을 대조한다.
M1 오라클 대조(적용) · M2 notes 내용 동일 · M3 안전 계약 · M4 되돌림 명령 · M5 드라이런 계약.
"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import snapshot as SNAP

NOTES_REF = "refs/notes/commits"


def sh(*args, repo=None):
    a = ["git", "-C", repo] + list(args) if repo else ["git"] + list(args)
    r = subprocess.run(a, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.stdout.decode().strip()


def rev(repo, ref):
    r = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q", ref],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.stdout.decode().strip() or None


def fresh_clone(real, dst):
    sh("clone", "-q", real, dst)
    sh("config", "user.email", "clew@ariadne.local", repo=dst)
    sh("config", "user.name", "clew", repo=dst)
    # C022로 push된 원격 notes 제거 → v2 원본 상태에서 재마이그레이션
    if rev(dst, NOTES_REF):
        sh("update-ref", "-d", NOTES_REF, repo=dst)


def dag_stats(repo):
    r = subprocess.run([sys.executable, os.path.join(HERE, "rebuild_cycle_dag.py"), repo],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = r.stdout.decode()
    import re
    nodes = int(re.search(r"복원: (\d+) 노드", out).group(1)) if "노드" in out else 0
    m = re.search(r"루트: (\d+) · 머지 노드: (\d+) · 총 엣지: (\d+)", out)
    roots, merges, edges = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (0, 0, 0)
    return {"nodes": nodes, "roots": roots, "merges": merges, "edges": edges}


def all_notes_body(repo):
    """모든 notes 본문을 (커밋→본문) 정렬 문자열로 — 내용 대조용."""
    listing = sh("notes", "list", repo=repo)
    bodies = []
    for line in sorted(listing.splitlines()):
        if not line.strip():
            continue
        note_obj, commit = line.split()
        body = sh("notes", "show", commit, repo=repo)
        bodies.append("%s\n%s" % (commit, body))
    return "\n---\n".join(bodies)


def oracle_apply(repo):
    subprocess.run([sys.executable, os.path.join(HERE, "full_ledger_migrate.py"),
                    repo, "--apply"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([sys.executable, os.path.join(HERE, "splice_topology.py"), repo],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cmd_migrate(repo, *flags):
    return subprocess.run([sys.executable, os.path.join(HERE, "gilv3.py"),
                           "migrate", repo, *flags],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main():
    real = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    scratch = sys.argv[2] if len(sys.argv) > 2 else "/tmp/c023-measure"
    subprocess.run(["rm", "-rf", scratch]); os.makedirs(scratch, exist_ok=True)
    print("=== C023 measure — gil migrate vs C022 오라클 대조 ===\n")
    results = []

    # M1+M2: 오라클(clone-A) vs 명령(clone-B) — DAG + notes 내용 대조
    A = os.path.join(scratch, "A"); B = os.path.join(scratch, "B")
    fresh_clone(real, A); fresh_clone(real, B)
    oracle_apply(A)
    cmd_migrate(B)
    da, db = dag_stats(A), dag_stats(B)
    m1 = (da == db)
    results.append(("M1 오라클 대조 (적용)",
                    "명령 DAG %s == 오라클 DAG %s" % (db, da), m1))
    na, nb = all_notes_body(A), all_notes_body(B)
    m2 = (na == nb)
    results.append(("M2 notes 내용 동일",
                    "명령·오라클 notes 본문 %s (길이 %d==%d)"
                    % ("동일" if m2 else "차이", len(na), len(nb)), m2))

    # M3: 안전 계약 — 명령 적용 후 커밋·cycle.yaml 불변
    C = os.path.join(scratch, "C"); fresh_clone(real, C)
    before = SNAP.snapshot(C)
    cmd_migrate(C)
    after = SNAP.snapshot(C)
    m3 = (before["commit_shas"] == after["commit_shas"]
          and before["cycle_yaml_hash"] == after["cycle_yaml_hash"])
    results.append(("M3 안전 계약",
                    "명령 적용 후 커밋 %d==%d·cycle.yaml %s"
                    % (before["commit_count"], after["commit_count"],
                       "동일" if before["cycle_yaml_hash"] == after["cycle_yaml_hash"] else "차이"),
                    m3))

    # M4: 되돌림 명령 — --rollback 후 notes 잔재 0
    cmd_migrate(C, "--rollback")
    m4 = (rev(C, NOTES_REF) is None)
    results.append(("M4 되돌림 명령",
                    "migrate --rollback 후 notes=%s" % (rev(C, NOTES_REF) or "없음(잔재0)"), m4))

    # M5: 드라이런 계약 — --dry가 각인 안 함
    E = os.path.join(scratch, "E"); fresh_clone(real, E)
    r = cmd_migrate(E, "--dry")
    m5 = (rev(E, NOTES_REF) is None and "도출 스텝" in r.stdout.decode())
    results.append(("M5 드라이런 계약",
                    "migrate --dry 후 notes=%s, 수 보고=%s"
                    % (rev(E, NOTES_REF) or "없음(각인0)", "있음" if "도출 스텝" in r.stdout.decode() else "없음"),
                    m5))

    print()
    allpass = True
    for name, detail, ok in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
        print("      %s" % detail)
        allpass = allpass and ok
    print("\n=== %s ===" % ("ALL PASS → supported" if allpass else "일부 FAIL → 조사"))
    sys.exit(0 if allpass else 1)


if __name__ == "__main__":
    main()
