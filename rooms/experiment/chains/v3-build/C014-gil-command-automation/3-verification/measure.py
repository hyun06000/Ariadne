#!/usr/bin/env python3
"""C014 측정 — 백트래킹=checkout이 gilv3.py 명령 동작이 됐는가. 순수 깃 감사.

M1 깃 그래프 분기 · M2 steps.yaml↔깃 그래프 동형 · M3 trailer 복원 무손상 ·
M4 append-only 보존 + 정정 집행(음성대조) · M5 회귀 0.
"""
import sys, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = sys.argv[1] if len(sys.argv) > 1 else \
    "/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/bb9fdd96-c034-4949/scratchpad/c014-auto"
if not os.path.isdir(os.path.join(SCRATCH, "repo")):
    SCRATCH = "/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/bb9fdd96-c034-4a97/scratchpad/c014-auto"
# 실제 경로는 build_case가 찍은 것 — 인자로 받는 게 원칙
R = os.path.join(SCRATCH, "repo")
GILV3 = os.path.join(HERE, "gilv3.py")

def git(*a, repo=None):
    return subprocess.run(["git", "-C", repo or R, *a],
                          capture_output=True, text=True).stdout

results = []
def check(name, ok, detail):
    results.append((name, ok, detail)); print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

# ── M1: 깃 그래프 분기 (선형 아님) ──────────────────────────────────
# 도구가 만든 저장소에서 여러 갈래가 s1에서 갈라진다. 판정: s1(루트 define) 커밋이
# 자식을 3개 갖는다(세 형제 가지의 첫 커밋 각각). 선형이면 자식 1개.
def sid_commit(sid):
    fmt = "%H\x1f%(trailers:key=Step-Id,valueonly)"
    for line in git("log", "--all", "--format=" + fmt).splitlines():
        if "\x1f" in line:
            h, t = line.split("\x1f", 1)
            if t.strip() == sid: return h.strip()
    return None
s1 = sid_commit("s1")
# s1을 부모로 갖는 커밋들(--all): rev-list --all --children 로 자식 조회
children = {}
for line in git("rev-list", "--all", "--children").splitlines():
    parts = line.split()
    if parts: children[parts[0]] = parts[1:]
s1_children = children.get(s1, [])
m1 = len(s1_children) == 3
check("M1-graph-branches", m1,
      f"루트 s1 커밋의 자식 수={len(s1_children)}(=3 기대: 세 형제 가지) "
      f"→ 도구가 선형 아닌 실제 분기 생성 (C011 build_branches.sh 위상)")

# ── M2: steps.yaml ↔ 깃 그래프 동형 ──────────────────────────────────
# steps.yaml 논리 트리(parent/backtrack)와 깃 커밋 부모 그래프가 일치.
# 각 스텝 커밋의 깃 부모의 Step-Id == steps.yaml parent (백트래킹 노드는 checkout으로
# 깃 부모가 backtrack 대상이 됨).
def load_steps():
    nodes, cur = [], None
    for raw in open(os.path.join(R, "steps.yaml"), encoding="utf-8"):
        st = raw.strip()
        if not st or st.startswith("#"): continue
        if st.startswith("- "):
            if cur: nodes.append(cur)
            cur = {}; st = st[2:]
        if ":" in st:
            k, _, v = st.partition(":"); cur[k.strip()] = (None if v.strip()=="null" else v.strip())
    if cur: nodes.append(cur)
    return nodes
steps = load_steps()
by_id = {n["id"]: n for n in steps}
# 깃에서 각 스텝 커밋의 부모 Step-Id
def parent_sid_in_git(sid):
    h = sid_commit(sid)
    if not h: return "?"
    ph = git("rev-list", "--parents", "-n", "1", h).split()
    if len(ph) < 2: return None  # 루트(부모 없음)
    par = ph[1]
    # 부모 커밋의 Step-Id
    t = git("log", "-1", "--format=%(trailers:key=Step-Id,valueonly)", par).strip()
    return t or None
mismatches = []
for n in steps:
    sid = n["id"]
    git_par = parent_sid_in_git(sid)
    # 논리 트리에서 이 노드의 '깃 부모여야 할 것':
    #  - 백트래킹 새 가지(첫 hypothesis, parent=조상 define): checkout으로 깃 부모=그 조상
    #  - 그 외: steps.yaml parent
    logical = n["parent"]
    if git_par != logical:
        mismatches.append((sid, f"git부모={git_par} steps={logical}"))
m2 = not mismatches
check("M2-yaml-git-isomorphic", m2,
      f"불일치 {len(mismatches)}건 {mismatches if mismatches else ''} "
      f"→ steps.yaml parent/backtrack 포인터 == 깃 커밋 부모 그래프")

# ── M3: trailer 복원 무손상 (checkout이 C010 복원을 안 깸) ─────────────
# C010 rebuild_trailer는 `git log --reverse`(--all 없음)로 읽어 선형 전제였다 —
# HEAD에서 도달 가능한 한 가지만 본다. C011 분기 후엔 --all이 필요하다. C010 원본은
# 불변(닫힌 사이클)이므로, C014는 그 rebuild 로직을 --all로 재호출한다. 이는
# C011·C012가 예고한 '재구성기를 git log --all 기반으로 재배선' 이월의 국소 적용 —
# 여기선 trailer 자기완결성이 분기(--all)에서도 성립함을 측정으로 보인다.
sys.path.insert(0, os.path.normpath(os.path.join(
    HERE, "..", "..", "C010-commit-message-as-contract", "3-verification")))
import rebuild_trailer

def rebuild_all(repo):
    """rebuild_trailer.rebuild의 --all 판. C010 파서(_FMT)를 그대로 재사용,
    log에 --all만 더한다 — 분기 저장소의 모든 가지 커밋을 시간순으로 읽는다."""
    out = subprocess.run(
        ["git", "-C", repo, "log", "--all", "--reverse",
         "--format=" + rebuild_trailer._FMT],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
    nodes, KEYS = [], rebuild_trailer.KEYS
    for rec in out.split(rebuild_trailer.SEP):
        rec = rec.strip("\n")
        if not rec: continue
        vals = [v.strip() for v in rec.split(rebuild_trailer.FSEP)]
        d = dict(zip(KEYS, vals))
        sid = d.get("Step-Id", "")
        if not sid: continue
        nodes.append({"id": sid, "kind": d["Kind"],
                      "parent": None if d["Parent"] in ("", "null") else d["Parent"],
                      "outcome": d["Outcome"] or None,
                      "backtrack": d["Backtrack-To"] or None,
                      "body": "steps/%s.md" % sid})
    return nodes

rebuilt = rebuild_all(R)
# 복원된 노드(시간순)를 id로 비교 — steps.yaml과 동일 집합·동일 parent/backtrack
rb_by = {n["id"]: n for n in rebuilt}
r_ok = set(rb_by) == set(by_id)
field_ok = all(
    rb_by[i]["parent"] == by_id[i]["parent"] and
    rb_by[i].get("backtrack") == by_id[i].get("backtrack") and
    rb_by[i].get("outcome") == by_id[i].get("outcome")
    for i in by_id) if r_ok else False
m3 = r_ok and field_ok
check("M3-trailer-rebuild-intact", m3,
      f"복원노드집합일치={r_ok} parent/backtrack/outcome일치={field_ok} "
      f"→ checkout 도입이 C010 trailer 복원을 안 깸 (자기완결 trailer)")

# ── M4: append-only 보존 + 정정 집행 (음성대조) ───────────────────────
# ① 죽은 가지 커밋이 살아있다(gil/dead/* 못 덕에 --all에 보임).
dead_tips = [sid_commit("s4"), sid_commit("s7")]
all_commits = set(git("rev-list", "--all").split())
m4_dead_alive = all(c in all_commits for c in dead_tips if c)
# ② 음성대조: 정정된 _assert_append_only가 진짜 위반(reset --hard로 커밋 삭제)을 잡나.
#    저장소 R을 건드리지 않도록 깨끗한 복제본(cp -r)에서 파괴 실험을 한다.
sys.path.insert(0, HERE)
import importlib.util
spec = importlib.util.spec_from_file_location("gilv3", GILV3)
gilv3 = importlib.util.module_from_spec(spec); spec.loader.exec_module(gilv3)

M4R = os.path.join(SCRATCH, "m4-clone")
subprocess.run(["rm", "-rf", M4R]); subprocess.run(["cp", "-r", R, M4R])
def m4git(*a): return subprocess.run(["git","-C",M4R,*a],capture_output=True,text=True).stdout
# (a) checkout(HEAD 뒤로)은 통과해야: 못이 다 있으니 커밋 집합 불변.
before_set = gilv3._all_commits(M4R)
m4git("checkout", "-q", s1)  # HEAD를 조상으로 (뒤로 이동, 그러나 커밋 안 지움)
try:
    gilv3._assert_append_only(M4R, before_set)  # 커밋 안 사라졌으니 통과해야
    m4_checkout_ok = True
except SystemExit:
    m4_checkout_ok = False
# (b) 진짜 위반: 새 커밋 만들고 reset --hard로 지운 뒤 집행 → 거부해야.
m4git("checkout", "-q", "-b", "tmp-violate", s1)
open(os.path.join(M4R, "x.tmp"), "w").write("x")
m4git("add", "."); m4git("commit", "-q", "-m", "tmp")
viol_before = gilv3._all_commits(M4R)
m4git("reset", "-q", "--hard", "HEAD~1")  # 방금 커밋 삭제 = 히스토리 재작성
m4git("branch", "-q", "-D", "tmp-violate")  # 브랜치 ref도 제거해 커밋을 진짜 dangling
try:
    gilv3._assert_append_only(M4R, viol_before)
    m4_reset_caught = False  # 안 잡음 = 나쁨
except SystemExit:
    m4_reset_caught = True   # 잡음 = 좋음
m4 = m4_dead_alive and m4_checkout_ok and m4_reset_caught
check("M4-append-only", m4,
      f"죽은가지생존(못)={m4_dead_alive} checkout통과={m4_checkout_ok} "
      f"reset거부(음성대조)={m4_reset_caught} "
      f"→ append-only 진짜계약=커밋불소멸. checkout 허용, 재작성 거부")

# ── M5: 회귀 0 — 선형 사이클 (백트래킹 없이) ─────────────────────────
LIN = os.path.join(SCRATCH, "linear")
subprocess.run(["rm", "-rf", LIN]); os.makedirs(LIN)
git("init", "-q", "-b", "main", repo=LIN)
git("config", "user.email", "c@a.local", repo=LIN); git("config", "user.name", "c", repo=LIN)
def grun(*a): return subprocess.run(["python3", GILV3, *a], capture_output=True, text=True)
grun("open", LIN, "--title", "선형", "--git")
grun("step", LIN, "--kind", "hypothesis", "--git")
grun("step", LIN, "--kind", "verify", "--git")
r5 = grun("step", LIN, "--kind", "analyze", "--outcome", "success", "--git")
c5 = grun("close", LIN, "--verdict", "supported", "--date", "2026-07-22", "--git")
# 선형이면 분기 0: 모든 커밋이 부모 ≤1, 그래프 한 갈래
lin_commits = git("rev-list", "--all", repo=LIN).split()
lin_branchy = any(len(git("rev-list","--parents","-n","1",c,repo=LIN).split())>2 for c in lin_commits)
lin_trailer = "s1" in git("log","--all","--format=%(trailers:key=Step-Id,valueonly)",repo=LIN)
m5 = (r5.returncode==0 and c5.returncode==0 and not lin_branchy and lin_trailer
      and os.path.exists(os.path.join(LIN,"cycle.yaml")))
check("M5-no-regression", m5,
      f"선형 open→step→close rc0={r5.returncode==0 and c5.returncode==0} "
      f"분기없음={not lin_branchy} trailer각인={lin_trailer} cycle.yaml봉인={os.path.exists(os.path.join(LIN,'cycle.yaml'))} "
      f"→ 기존 C010 동작 회귀 0")

print()
allpass = all(ok for _, ok, _ in results)
print(f"=== {'ALL PASS — supported' if allpass else '일부 FAIL'} ({sum(ok for _,ok,_ in results)}/{len(results)}) ===")
sys.exit(0 if allpass else 1)
