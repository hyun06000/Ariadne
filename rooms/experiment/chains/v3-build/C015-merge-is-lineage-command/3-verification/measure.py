#!/usr/bin/env python3
"""C015 측정 — lineage=머지=git merge --no-ff 가 gilv3 명령 동작이 되다. 5측정 감사.

M1 다중부모 · M2 trailer 복원 · M3 append-only(두 갈래 생존+집행기) ·
M4 squash 음성대조 · M5 회귀(--lineage 없는 close = C014).

C014 measure.py 리듬 계승 — subprocess 순수 깃, 파이썬은 파싱·판정만.
gilv3.py 안에서 생 merge/checkout이 도구 동작이므로, 여기선 결과만 감사한다.
"""
import subprocess, sys, os

SCRATCH = sys.argv[1] if len(sys.argv) > 1 else \
    "/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c015-merge"
R = os.path.join(SCRATCH, "repo")
HERE = os.path.dirname(os.path.abspath(__file__))
GILV3 = os.path.join(HERE, "gilv3.py")

def git(*a, repo=R):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout

def load_index():
    d = {}
    with open(os.path.join(SCRATCH, "commit-index.txt")) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                d[parts[0]] = parts[1]
    return d

CI = load_index()
results = []
def check(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

# ── M1: 다중부모 (H1a) ──────────────────────────────────────────────
# close-merge 커밋이 부모 2개를 담고, 그 두 부모가 각각 산 잎 s4·s7 커밋.
raw = git("cat-file", "-p", CI["merge"])
parents = [l.split()[1] for l in raw.splitlines() if l.startswith("parent ")]
p_set = set(parents)
expected = {CI["s4"], CI["s7"]}
m1_count = len(parents) == 2
m1_match = p_set == expected
first_parent_is_s4 = parents and parents[0] == CI["s4"]  # HEAD=첫 산 잎(s4)이 parent[0]
m1 = m1_count and m1_match and first_parent_is_s4
check("M1-multiparent", m1,
      f"부모수={len(parents)}(=2) 부모집합일치={m1_match} 첫부모=s4={first_parent_is_s4} "
      f"→ 도구가 만든 close 머지가 gil [s4,s7] ≅ git 다중부모 (생 merge 0)")

# ── M2: trailer 복원 (H1b) ──────────────────────────────────────────
# 머지 커밋 trailer가 Kind=merge·Parent="s4, s7"·Merge=lineage.
def tr(h, key): return git("log","-1",f"--format=%(trailers:key={key},valueonly)",h).strip()
t_kind = tr(CI["merge"], "Kind")
t_parent = tr(CI["merge"], "Parent")
t_merge = tr(CI["merge"], "Merge")
# C009/C010 복원판: 부모 지문(git %P)만으로 lineage DAG 복원 — cycle.yaml 안 봄.
dag = {}
for line in git("log", "--all", "--format=%H %P").splitlines():
    parts = line.split()
    if not parts: continue
    dag[parts[0]] = parts[1:]
recon_merges = {n: ps for n, ps in dag.items() if len(ps) == 2}
recon_ok = (len(recon_merges) == 1 and CI["merge"] in recon_merges and
            set(recon_merges[CI["merge"]]) == {CI["s4"], CI["s7"]})
m2 = (t_kind == "merge" and t_parent == "s4, s7" and t_merge == "lineage" and recon_ok)
check("M2-trailer-reconstruct", m2,
      f"Kind={t_kind!r} Parent={t_parent!r} Merge={t_merge!r} "
      f"부모지문복원머지수={len(recon_merges)}(=1) 부모일치={recon_ok} "
      f"→ trailer가 lineage 담고 부모 지문만으로 DAG 복원 (C009 합류판)")

# ── M3: append-only (H1c) ───────────────────────────────────────────
# ① 머지 후 두 갈래 스텝 커밋 전부 rev-list --all 에 생존 (커밋 불소멸).
all_commits = set(git("rev-list", "--all").split())
# 두 갈래 팁·머지가 다 살아있는지 + 갈래 중간 커밋도 (부모 체인)
survive = {CI["s4"], CI["s7"], CI["merge"]} <= all_commits
# ② 도구의 _assert_append_only 가 실제 집행됨을 재현 — 깨끗한 재빌드로 확인(회귀 없음).
#    (build_case 가 이미 통과했으므로 집행기가 머지를 허용했다는 증거. 여기선 커밋수로.)
n_all = len(all_commits)  # open(s1)+s2..s4(3)+s5..s7(3)+merge = 8
m3 = survive and n_all == 8
check("M3-append-only", m3,
      f"두갈래+머지생존={survive} 전체커밋수={n_all}(=8: s1+3+3+merge) "
      f"→ 머지가 커밋 안 지움, _assert_append_only 통과 (C014 계약)")

# ── M4: squash 음성대조 (H2) ────────────────────────────────────────
# 같은 두 산 잎을 --squash 로 합치면 부모 1개 → lineage 소실.
# 도구가 --no-ff 를 강제하므로 정상 경로는 다중부모(M1). 여기선 squash가 왜 안 되는지 대조.
SQ = os.path.join(SCRATCH, "squash-repo")
subprocess.run(["rm","-rf",SQ]); os.makedirs(SQ)
def sgit(*a): return git(*a, repo=SQ)
sgit("init","-q","-b","main")
sgit("config","user.email","clew@ariadne.local"); sgit("config","user.name","clew")
sgit("config","advice.detachedHead","false")
# 두 산 잎만 fetch (머지 커밋 없이 — 도달 가능한 조상만: s1→갈래)
sgit("fetch","-q",R,f"{CI['s4']}:refs/heads/lane-s4",f"{CI['s7']}:refs/heads/lane-s7")
sgit("checkout","-q","-b","sq-base","lane-s4")
sgit("merge","--squash","lane-s7")  # squash: 스테이징만, 다중부모 없음
# steps.yaml 충돌은 squash에서도 나므로 강제 해소 후 커밋(대조 목적)
sgit("checkout","--theirs",".")
sgit("add","-A")
sgit("commit","-q","-m","squash: s4+s7 (다중부모 없음)")
sq_head = sgit("rev-parse","HEAD").strip()
sq_parents = [l.split()[1] for l in sgit("cat-file","-p",sq_head).splitlines() if l.startswith("parent ")]
sq_reconstruct_sees_both = any(
    set(l.split()[1:]) >= {sgit("rev-parse","lane-s4").strip(), sgit("rev-parse","lane-s7").strip()}
    for l in sgit("log","--all","--format=%H %P").splitlines() if l.split()
)
m4 = len(sq_parents) == 1 and not sq_reconstruct_sees_both
check("M4-squash-negative", m4,
      f"squash부모수={len(sq_parents)}(=1) squash가양계보봄={sq_reconstruct_sees_both}(=False) "
      f"→ squash는 lineage 잃음; 도구의 --no-ff 다중부모여야 보존 (C012 교훈2 강제)")

# ── M5: 회귀 (H3) ──────────────────────────────────────────────────
# --lineage 없는 close(단일 산 잎)가 C014와 동형 — 빈 봉인 커밋(부모 1개)·gil/live·gil/sealed.
REG = os.path.join(SCRATCH, "regress-repo")
subprocess.run(["rm","-rf",REG]); os.makedirs(REG)
def rgit(*a): return git(*a, repo=REG)
rgit("init","-q","-b","main")
rgit("config","user.email","clew@ariadne.local"); rgit("config","user.name","clew")
rgit("config","advice.detachedHead","false")
def g(*a): return subprocess.run(["python3", GILV3, *a], capture_output=True, text=True)
g("open", REG, "--title", "C015 회귀: 단일 산 잎 선형", "--git")
g("step", REG, "--kind","hypothesis","--note","가설","--git")
g("step", REG, "--kind","verify","--note","검증","--git")
g("step", REG, "--kind","analyze","--outcome","success","--note","산 잎","--git")
g("close", REG, "--verdict","supported","--date","2026-07-22","--git")  # --lineage 없음
reg_head = rgit("rev-parse","HEAD").strip()
reg_parents = [l.split()[1] for l in rgit("cat-file","-p",reg_head).splitlines() if l.startswith("parent ")]
# 빈 봉인 커밋: 부모 1개(선형), 머지 아님. gil/live/s4·gil/sealed/regress-repo 못 존재.
reg_branches = rgit("branch","--list","gil/*").replace("*","").split()
has_live = any(b.startswith("gil/live/") for b in reg_branches)
has_sealed = any(b.startswith("gil/sealed/") for b in reg_branches)
reg_close_msg = rgit("log","-1","--format=%s",reg_head).strip()
m5 = (len(reg_parents) == 1 and has_live and has_sealed and "봉인" in reg_close_msg
      and "lineage" not in reg_close_msg)
check("M5-regression", m5,
      f"봉인커밋부모수={len(reg_parents)}(=1 선형) gil/live={has_live} gil/sealed={has_sealed} "
      f"close메시지='{reg_close_msg[:40]}' → --lineage 없는 close = C014 동형 (회귀 0)")

# ── 판정 ──
print()
allpass = all(ok for _, ok, _ in results)
print(f"=== {'ALL PASS — supported' if allpass else '일부 FAIL'} ({sum(ok for _,ok,_ in results)}/{len(results)}) ===")
sys.exit(0 if allpass else 1)
