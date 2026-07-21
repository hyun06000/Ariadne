#!/usr/bin/env python3
"""C008 측정 — 백트래킹=새 커밋. 네 측정을 순수 stdlib로 자동 판정.

M1 append-only 코드 감사    (K1): 각인 경로 git 하위명령 = add·commit만
M2 전진 단조성 실측         (K2·K4): reflog 뒤로간 HEAD 0, 커밋 11개 시간순
M3 벽의 지도 보존           (K2): 죽은 가지 커밋·body 생존
M4 역할 분리               (K3): 깃 그래프 선형(분기0), steps.yaml 트리

사용법: python3 measure.py <scratch_repo> <case_dir>
"""
import sys, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE
                          ).stdout.decode()


def load_steps(case):
    """steps.yaml을 평면 노드 리스트로 (gilv3.load 규칙과 동일, 독립 파서)."""
    nodes, cur = [], None
    for raw in open(os.path.join(case, "steps.yaml"), encoding="utf-8"):
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


# ---- M1: append-only 코드 감사 ----
FORBIDDEN = ["reset", "checkout", "revert", "amend", "rebase", "cherry-pick",
             "--force", "-f "]


def _strip_comments_strings(src):
    """정적 감사는 실제 코드 호출만 봐야 한다 — 주석·독스트링·문자열 리터럴 안의
    금지 토큰(계약을 서술하는 텍스트)은 오탐이므로 제거한다. 단 실제 git 호출
    리스트 `["git", "-C", ..., "<sub>"]`는 코드이므로 남겨야 한다.
    간단·보수적으로: `#` 주석 제거 + 삼중따옴표 독스트링 제거."""
    src = re.sub(r'"""[\s\S]*?"""', "", src)   # 독스트링/삼중따옴표 문자열
    src = re.sub(r'#.*', "", src)               # 라인 주석
    return src


def m1_code_audit():
    """gilv3.py의 각인 경로(git_imprint + 그 헬퍼)가 호출하는 git 하위명령을
    정적 수집. 금지 명령이 0이어야 PASS. 우리는 subprocess.run(["git", ...])
    형태만 쓰므로 소스에서 git 인자 리스트를 스캔한다.
    주석·독스트링은 제거하고 본다 (계약 서술 텍스트가 오탐이 되지 않게)."""
    raw = open(os.path.join(HERE, "gilv3.py"), encoding="utf-8").read()
    src = _strip_comments_strings(raw)
    # subprocess.run(["git", "-C", dir_, <SUB>, ...]) 의 <SUB> 토큰 수집
    calls = re.findall(r'\["git",\s*"-C",\s*[^,]+,\s*"([a-z-]+)"', src)
    forbidden_hits = []
    # 실제 호출된 하위명령 중 금지 목록
    for sub in calls:
        if sub in ("reset", "checkout", "revert", "rebase", "cherry-pick"):
            forbidden_hits.append(sub)
    # git 명령 리스트 안에 --amend/--force 플래그가 실제로 등장하는지 (주석 제거된 src)
    if re.search(r'"git"[\s\S]{0,200}?(--amend|--force|force-with-lease)', src):
        forbidden_hits.append("amend/force-flag")
    ok = len(forbidden_hits) == 0
    print("  M1 각인 경로 git 하위명령(주석제외): %s" % sorted(set(calls)))
    print("  M1 금지 명령 히트: %s" % (forbidden_hits or "없음"))
    return ok, "K1", "각인 경로 git 하위명령이 add·commit만 (reset/checkout/revert/amend/force/rebase=0)"


# ---- M2: 전진 단조성 실측 ----
def m2_forward(repo):
    # 커밋 수
    n = int(git(repo, "rev-list", "--count", "HEAD").strip())
    # 커밋 메시지 순서 (오래된→최신) — s1..s10 + close
    log = git(repo, "log", "--reverse", "--format=%s").strip().splitlines()
    order_ok = (log[0].startswith("gilv3 open") and log[-1].startswith("gilv3 close"))
    # s번호가 시간순 단조 증가하는지 — step 커밋의 스텝 id만 뽑는다.
    # (close 줄의 "산 잎 s10"은 스텝 id가 아니므로 제외; "gilv3 step: sN" 형태만)
    sids = []
    for line in log:
        m = re.match(r"gilv3 step: (s\d+)\b", line)
        if m:
            sids.append(int(m.group(1)[1:]))
    # step 커밋은 s2..s10 (9개). 시간순 == id순 == 연속 증가여야 한다.
    monotone = (sids == sorted(sids) and len(sids) == 9
                and sids == list(range(sids[0], sids[0] + 9)))
    # reflog에 뒤로 간 HEAD가 있는지 — 부모체인이 선형 전진인지로 판정.
    # 각 커밋 i의 부모가 커밋 i-1인지 (선형 append-only)
    # %H|%P 를 한 줄로 — 첫 커밋의 빈 %P 가 splitlines에서 사라지는 걸 방지
    rows = [ln.split("|", 1) for ln in
            git(repo, "log", "--reverse", "--format=%H|%P").strip().splitlines()]
    hashes = [r[0] for r in rows]
    parents = [r[1].strip() if len(r) > 1 else "" for r in rows]
    linear_forward = True
    for i in range(1, len(hashes)):
        # 커밋 i의 부모 == 커밋 i-1 (선형, 뒤로 안 감)
        if parents[i] != hashes[i - 1]:
            linear_forward = False
    # reflog 명령 중 되돌림 흔적(reset/checkout/rebase moving HEAD) 검사
    reflog = git(repo, "reflog", "--format=%gs")
    rewind = bool(re.search(r"reset:|checkout:|rebase", reflog))
    ok = (n == 11 and order_ok and monotone and linear_forward and not rewind)
    print("  M2 커밋 수=%d (기대 11), open/close 경계=%s, s번호 단조=%s"
          % (n, order_ok, monotone))
    print("  M2 부모체인 선형전진=%s, reflog 되돌림흔적=%s" % (linear_forward, rewind))
    return ok, "K2·K4", "전진 단조: 11커밋 시간순, 부모체인 선형, HEAD 되돌림 0"


# ---- M3: 벽의 지도 보존 (죽은 가지 커밋·body 생존) ----
def m3_wall_map(repo, case):
    log = git(repo, "log", "--format=%s")
    # 죽은 잎 s4·s7의 backtrack 커밋이 히스토리에 살아있는가
    dead_commits = ["s4 analyze/backtrack" in log, "s7 analyze/backtrack" in log]
    # 죽은 가지의 다른 스텝(s2·s3·s5·s6)도 생존
    dead_branch = all(("%s " % s) in log for s in ["s2", "s3", "s5", "s6"])
    # 죽은 잎 body 파일이 워킹트리에 그대로
    bodies = all(os.path.exists(os.path.join(case, "steps", "%s.md" % s))
                 for s in ["s4", "s7", "s2", "s5"])
    ok = all(dead_commits) and dead_branch and bodies
    print("  M3 죽은 잎 커밋 s4·s7 생존=%s, 죽은 가지 스텝 생존=%s, body 생존=%s"
          % (all(dead_commits), dead_branch, bodies))
    return ok, "K2", "벽의 지도: 죽은 가지 커밋·body 전부 히스토리에 보존"


# ---- M4: 역할 분리 (깃 선형 vs steps.yaml 트리) ----
def m4_roles(repo, case):
    # 깃 그래프에 머지/분기가 없는가 — 모든 커밋의 부모가 정확히 1개(첫 커밋만 0).
    # 머지커밋은 %P에 공백구분 부모가 2개 — 라인이 splitlines에서 사라져도(빈 첫줄)
    # 머지 검사엔 무해(빈줄엔 부모0<2).
    parents = git(repo, "log", "--format=%P").splitlines()
    branchy = any(len(p.split()) > 1 for p in parents)  # 머지커밋
    multi_child = False  # 선형이면 각 커밋 자식 1 (rev-list로 이미 선형 확인됨)
    git_linear = not branchy
    # steps.yaml은 트리인가 — s1이 세 자식(parent=s1)을 가짐
    nodes = load_steps(case)
    by_parent = {}
    for nd in nodes:
        by_parent.setdefault(nd.get("parent"), []).append(nd["id"])
    s1_children = by_parent.get("s1", [])
    is_tree = len(s1_children) >= 3  # 세 형제 가지
    # 되돌아감 목적지가 steps.yaml backtrack에만 있는가 (깃엔 구조로 없음)
    backtracks = [(nd["id"], nd.get("backtrack")) for nd in nodes
                  if nd.get("backtrack")]
    bt_in_data = backtracks == [("s4", "s1"), ("s7", "s1")]
    ok = git_linear and is_tree and bt_in_data
    print("  M4 깃 선형(머지0)=%s, steps.yaml s1 자식=%s (트리=%s)"
          % (git_linear, s1_children, is_tree))
    print("  M4 backtrack 포인터(steps.yaml에만)=%s" % backtracks)
    return ok, "K3", "역할분리: 깃 선형(분기0)인데 steps.yaml은 트리(형제3+backtrack2)"


# ---- M5: 음성 대조 — 가드가 진짜 작동하나 (뒤로 간 HEAD를 잡는가) ----
def m5_guard_control(case):
    """전진 단조성 가드(_assert_forward_only)가 무의미한 통과가 아님을 증명한다.
    HEAD를 인위적으로 뒤로 옮긴 뒤 가드를 호출해 거부되는지 확인하고 복원한다.
    이 대조가 없으면 M2 PASS는 '애초에 뒤로 갈 일이 없어서'일 수도 있다."""
    sys.path.insert(0, HERE)
    import gilv3
    head = gilv3._head(case)
    parent = subprocess.run(["git", "-C", case, "rev-parse", "HEAD~1"],
                            stdout=subprocess.PIPE).stdout.decode().strip()
    subprocess.run(["git", "-C", case, "reset", "-q", "--hard", parent],
                   stdout=subprocess.DEVNULL)
    caught = False
    try:
        gilv3._assert_forward_only(case, head)
    except SystemExit:
        caught = True
    subprocess.run(["git", "-C", case, "reset", "-q", "--hard", head],
                   stdout=subprocess.DEVNULL)  # 원상복원
    restored = gilv3._head(case) == head
    ok = caught and restored
    print("  M5 가드가 뒤로간 HEAD 거부=%s, 복원=%s" % (caught, restored))
    return ok, "(가드 유효성)", "가드가 무의미한 통과 아님: 뒤로 간 HEAD를 실제로 거부"


def main():
    if len(sys.argv) < 3:
        sys.exit("사용법: measure.py <scratch_repo> <case_dir>")
    repo, case = sys.argv[1], sys.argv[2]
    print("=== C008 측정 — 백트래킹=새 커밋 ===")
    results = []
    for fn, args in [(m1_code_audit, ()), (m2_forward, (repo,)),
                     (m3_wall_map, (repo, case)), (m4_roles, (repo, case)),
                     (m5_guard_control, (case,))]:
        ok, kill, desc = fn(*args)
        tag = "M%d" % (len(results) + 1)
        print("%s %s — %s [%s]" % ("✅ PASS" if ok else "❌ FAIL", tag, desc, kill))
        print()
        results.append(ok)
    allok = all(results)
    n = len(results)
    print("=== %s (%d/%d) ===" % ("ALL PASS → supported" if allok else "실패 있음",
                                  sum(results), n))
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
