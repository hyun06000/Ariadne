#!/usr/bin/env python3
"""C009 측정 — 깃 로그로 트리 재구성. 4측정 자동 판정 (순수 stdlib).

M1 노드·parent 엣지 동형        (K1)
M2 backtrack·outcome 동형       (K2)
M3 깃 로그 단독 (정적 감사)      (K3): rebuild.py의 git 하위명령 = log만
M4 유일 결정성 + 왕복 무손실     (K4)

사용법: python3 measure.py <git_repo> <원본_steps.yaml>
"""
import sys, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rebuild as RB


def load_yaml(path):
    """steps.yaml 평면 파서 (독립 구현, gilv3.load 규칙과 동일)."""
    nodes, cur = [], None
    for raw in open(path, encoding="utf-8"):
        st = raw.strip()
        if not st or st.startswith("#"):
            continue
        if st.startswith("- "):
            if cur:
                nodes.append(cur)
            cur = {}
            st = st[2:]
        if ":" in st:
            k, _, v = st.partition(":")
            v = v.strip()
            cur[k.strip()] = None if v == "null" else v
    if cur:
        nodes.append(cur)
    return nodes


def edges_parent(nodes):
    return {(n["id"], n["parent"]) for n in nodes}


def edges_backtrack(nodes):
    return {(n["id"], n.get("backtrack")) for n in nodes if n.get("backtrack")}


def outcomes(nodes):
    return {(n["id"], n.get("outcome")) for n in nodes if n.get("outcome")}


def m1_nodes_parent(recon, orig):
    ids_r = {n["id"] for n in recon}
    ids_o = {n["id"] for n in orig}
    same_nodes = ids_r == ids_o
    same_parent = edges_parent(recon) == edges_parent(orig)
    ok = same_nodes and same_parent
    print("  M1 노드집합 동일=%s (복원 %d / 원본 %d), parent 엣지 동일=%s"
          % (same_nodes, len(ids_r), len(ids_o), same_parent))
    if not same_parent:
        print("     복원-원본 parent 차이:", edges_parent(recon) ^ edges_parent(orig))
    return ok, "K1", "노드·parent 엣지 동형"


def m2_backtrack_outcome(recon, orig):
    same_bt = edges_backtrack(recon) == edges_backtrack(orig)
    same_oc = outcomes(recon) == outcomes(orig)
    ok = same_bt and same_oc
    print("  M2 backtrack 엣지 동일=%s %s, outcome 동일=%s %s"
          % (same_bt, sorted(edges_backtrack(recon)), same_oc, sorted(outcomes(recon))))
    return ok, "K2", "backtrack·outcome 동형"


def m3_log_only():
    """rebuild.py가 호출하는 git 하위명령이 log뿐인지 정적 감사.
    주석·독스트링 제거 후 실제 subprocess git 호출만 본다."""
    raw = open(os.path.join(HERE, "rebuild.py"), encoding="utf-8").read()
    src = re.sub(r'"""[\s\S]*?"""', "", raw)
    src = re.sub(r'#.*', "", src)
    subs = re.findall(r'\["git",\s*"-C",\s*[^,]+,\s*"([a-z-]+)"', src)
    # steps.yaml·show·diff·cat-file 접근이 코드에 있는지 (log 외 데이터 소스)
    forbidden = [s for s in subs if s != "log"]
    reads_yaml = bool(re.search(r'steps\.yaml', src))  # 파일 직접 읽기
    reads_show = bool(re.search(r'"(show|diff|cat-file)"', src))
    ok = (set(subs) == {"log"} and not forbidden and not reads_yaml and not reads_show)
    print("  M3 git 하위명령(주석제외)=%s, steps.yaml 읽기=%s, show/diff=%s"
          % (sorted(set(subs)), reads_yaml, reads_show))
    return ok, "K3", "깃 로그 단독 (steps.yaml·show·diff 접근 0)"


def m4_determinism_roundtrip(repo, orig_path):
    """유일 결정성: 파서가 케이스 배타적(한 subject가 두 케이스에 안 걸림).
    왕복 무손실: 복원→serialize == 원본 파일 바이트."""
    # 배타성: 각 커밋 subject가 OPEN·STEP·CLOSE 중 정확히 하나에만 매칭
    subs = RB.git_log_subjects(repo)
    exclusive = True
    for s in subs:
        hits = sum(bool(rx.match(s)) for rx in (RB.RE_OPEN, RB.RE_STEP, RB.RE_CLOSE))
        if hits != 1:
            exclusive = False
            print("     비배타 subject (%d 매칭): %r" % (hits, s))
    # 왕복: 복원 serialize == 원본 파일
    recon = RB.rebuild(repo)
    rebuilt_text = RB.serialize(recon)
    orig_text = open(orig_path, encoding="utf-8").read()
    roundtrip = rebuilt_text == orig_text
    ok = exclusive and roundtrip
    print("  M4 파싱 배타적=%s, 왕복 무손실(복원→yaml == 원본)=%s" % (exclusive, roundtrip))
    return ok, "K4", "유일 결정성 + 왕복 무손실"


def main():
    if len(sys.argv) < 3:
        sys.exit("사용법: measure.py <git_repo> <원본_steps.yaml>")
    repo, orig_path = sys.argv[1], sys.argv[2]
    recon = RB.rebuild(repo)
    orig = load_yaml(orig_path)
    print("=== C009 측정 — 깃 로그로 트리 재구성 ===")
    results = []
    for fn, args in [(m1_nodes_parent, (recon, orig)),
                     (m2_backtrack_outcome, (recon, orig)),
                     (m3_log_only, ()),
                     (m4_determinism_roundtrip, (repo, orig_path))]:
        ok, kill, desc = fn(*args)
        print("%s M%d — %s [%s]\n" % ("✅ PASS" if ok else "❌ FAIL",
                                      len(results) + 1, desc, kill))
        results.append(ok)
    allok = all(results)
    print("=== %s (%d/%d) ===" % ("ALL PASS → supported" if allok else "실패 있음",
                                  sum(results), len(results)))
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
