#!/usr/bin/env python3
"""C010 측정 — 커밋 메시지를 계약면으로 (git trailer). 4측정 자동 판정.

M1 trailer 복원 동형 + 왕복      (K1)
M2 subject 무오염                (K2)
M3 견고성 대조 (서술 변조)        (K3): 자연어 rebuild 깨지고 trailer rebuild 불변
M4 append-only 유지              (K4)

사용법: python3 measure.py <trailer_repo> <원본_steps.yaml> <c009_rebuild.py>
"""
import sys, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rebuild_trailer as RT


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE
                          ).stdout.decode()


def load_yaml(path):
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


def edges_parent(ns):
    return {(n["id"], n["parent"]) for n in ns}


def edges_bt(ns):
    return {(n["id"], n.get("backtrack")) for n in ns if n.get("backtrack")}


def outc(ns):
    return {(n["id"], n.get("outcome")) for n in ns if n.get("outcome")}


def m1_isomorph(repo, orig_path):
    recon = RT.rebuild(repo)
    orig = load_yaml(orig_path)
    same_nodes = {n["id"] for n in recon} == {n["id"] for n in orig}
    same_p = edges_parent(recon) == edges_parent(orig)
    same_bt = edges_bt(recon) == edges_bt(orig)
    same_oc = outc(recon) == outc(orig)
    roundtrip = RT.serialize(recon) == open(orig_path, encoding="utf-8").read()
    ok = same_nodes and same_p and same_bt and same_oc and roundtrip
    print("  M1 노드=%s parent=%s backtrack=%s outcome=%s 왕복=%s"
          % (same_nodes, same_p, same_bt, same_oc, roundtrip))
    return ok, "K1", "trailer 복원 동형 + 왕복 무손실"


def m2_subject_clean(repo):
    """subject(%s)에 trailer가 안 새고, 사람용 서술이 온전한가."""
    subs = git(repo, "log", "--reverse", "--format=%s").strip().splitlines()
    # trailer 키가 subject에 새면 오염
    leaked = any(re.search(r"(Step-Id|Kind|Parent|Outcome|Backtrack-To):", s)
                 for s in subs)
    # 사람용 서술 온전 — open/step/close 형태 유지
    shape = (subs[0].startswith("gilv3 open") and subs[-1].startswith("gilv3 close")
             and all(s.startswith("gilv3 ") for s in subs))
    # 백트래킹 서술이 subject에 여전히 있는가 (사람용으로 유지 — C008 정신)
    has_human = any("backtrack to" in s for s in subs)
    ok = (not leaked) and shape and has_human
    print("  M2 trailer 누출=%s, subject 형태온전=%s, 사람용 서술 유지=%s"
          % (leaked, shape, has_human))
    return ok, "K2", "subject 무오염 (trailer 미누출, 사람 서술 온전)"


def m3_robustness(repo, orig_path, c009_rebuild_path):
    """견고성 대조: subject 자연어를 망가뜨린 저장소를 만들어 —
    ① C009 자연어 rebuild는 깨지고 ② trailer rebuild는 불변임을 대조.
    변조 저장소: 원본을 복제 후, gil v3.5의 --scramble-subject로 subject의
    자연어 백트래킹 마커를 제거해 재각인 (trailer는 유지). 여기선 재각인 대신
    filter로 만들 수 없으니, gilv3.py를 --scramble 모드로 다시 빌드한다."""
    scratch = os.path.dirname(repo)
    scrambled = os.path.join(scratch, "case-scrambled")
    # gil v3.5 build를 scramble 모드로 재실행
    env = dict(os.environ, GILV3_SCRAMBLE_SUBJECT="1")
    subprocess.run(["bash", os.path.join(HERE, "build.sh"),
                    os.path.join(scratch, "scrambled-root")],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    scrambled = os.path.join(scratch, "scrambled-root", "case")
    orig = load_yaml(orig_path)

    # ① trailer rebuild: 변조 저장소에서도 원본과 동형이어야 (불변)
    recon_tr = RT.rebuild(scrambled)
    tr_invariant = (edges_parent(recon_tr) == edges_parent(orig)
                    and edges_bt(recon_tr) == edges_bt(orig))

    # ② C009 자연어 rebuild: 변조 저장소에서 깨져야 (트리 붕괴 or 복원 실패)
    r = subprocess.run(
        ["python3", c009_rebuild_path, scrambled, "--yaml"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        nat_broken = True   # 복원 실패 (해석 불가 커밋 등)
    else:
        nat_nodes = load_yaml_text(r.stdout.decode())
        # 자연어 rebuild가 백트래킹 착지(s5·s8 parent=s1)를 잃으면 붕괴
        nat_broken = edges_parent(nat_nodes) != edges_parent(orig)

    ok = tr_invariant and nat_broken
    print("  M3 변조 subject에서 — trailer 복원 불변=%s, 자연어 복원 깨짐=%s"
          % (tr_invariant, nat_broken))
    if not nat_broken:
        print("     (자연어 복원이 안 깨졌다 — 변조가 충분히 자연어 마커를 안 건드림)")
    return ok, "K3", "견고성: 서술 변조에도 trailer 불변, 자연어는 붕괴"


def load_yaml_text(text):
    nodes, cur = [], None
    for raw in text.splitlines():
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


def m4_append_only():
    """trailer 각인 경로도 add·commit만인가 (C008 계약 유지)."""
    raw = open(os.path.join(HERE, "gilv3.py"), encoding="utf-8").read()
    src = re.sub(r'"""[\s\S]*?"""', "", raw)
    src = re.sub(r'#.*', "", src)
    subs = re.findall(r'\["git",\s*"-C",\s*[^,]+,\s*"([a-z-]+)"', src)
    forbidden = [s for s in subs if s in
                 ("reset", "checkout", "revert", "rebase", "cherry-pick")]
    flag = bool(re.search(r'"git"[\s\S]{0,200}?(--amend|--force)', src))
    ok = not forbidden and not flag
    print("  M4 git 하위명령=%s, 금지=%s, amend/force=%s"
          % (sorted(set(subs)), forbidden or "없음", flag))
    return ok, "K4", "append-only 유지 (add·commit만)"


def main():
    if len(sys.argv) < 4:
        sys.exit("사용법: measure.py <trailer_repo> <원본_steps.yaml> <c009_rebuild.py>")
    repo, orig_path, c009 = sys.argv[1], sys.argv[2], sys.argv[3]
    print("=== C010 측정 — 커밋 메시지를 계약면으로 (git trailer) ===")
    results = []
    for fn, args in [(m1_isomorph, (repo, orig_path)),
                     (m2_subject_clean, (repo,)),
                     (m3_robustness, (repo, orig_path, c009)),
                     (m4_append_only, ())]:
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
