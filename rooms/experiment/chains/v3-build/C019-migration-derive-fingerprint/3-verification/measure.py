#!/usr/bin/env python3
"""C019 측정 — v2 메타 → v3 지문 자동 도출. 4측정.

M1 결정성(같은 입력 같은 출력) · M2 파싱 정확(실제 원장 분류·N/5) ·
M3 C018 통합(도출→retro_imprint→rebuild 노드) · M4 근사 명시.

실제 v2 원장의 C015 사이클을 표적(읽기만). 소급각인 실측은 격리 저장소에서.
"""
import subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import derive_fingerprint as DF
import retro_imprint as RI
import rebuild_migrate as RM

# 실제 Ariadne 원장 루트 (이 파일에서 상위로 — 읽기만)
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "..", ".."))
TARGET = "v3-build/C015-merge-is-lineage-command"
SCRATCH = sys.argv[1] if len(sys.argv) > 1 else \
    "/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c019-derive"

def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout

results = []
def check(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

# 실제 원장에서 C015 사이클 커밋 수집
def collect(target):
    out = git(REPO, "log", "--reverse", "--format=%H\x1f%s")
    commits = []
    for line in out.splitlines():
        if "\x1f" not in line: continue
        h, subj = line.split("\x1f", 1)
        _, cyc, _, _ = DF.classify(subj)
        if cyc == target:
            commits.append((h, subj))
    return commits
commits = collect(TARGET)

# ── M1: 결정성 (H1a) ────────────────────────────────────────────────
d1 = DF.derive_cycle(commits, "supported")
d2 = DF.derive_cycle(commits, "supported")
m1 = (d1 == d2 and len(d1) == 5)
check("M1-deterministic", m1,
      f"2회도출동일={d1==d2} 노드수={len(d1)}(=5) → 순수 함수(같은 입력 같은 지문)")

# ── M2: 파싱 정확 (H1b) ─────────────────────────────────────────────
# 실제 C015 커밋: open 1 + step 5 + close 1 = 7. 분류가 정확한가.
all_out = git(REPO, "log", "--reverse", "--format=%H\x1f%s")
cyc_all = []
for line in all_out.splitlines():
    if "\x1f" not in line: continue
    h, subj = line.split("\x1f", 1)
    k, cyc, n, nm = DF.classify(subj)
    if cyc == TARGET:
        cyc_all.append((k, n, nm))
n_open = sum(1 for k,_,_ in cyc_all if k=="open")
n_step = sum(1 for k,_,_ in cyc_all if k=="step")
n_close = sum(1 for k,_,_ in cyc_all if k=="close")
# step N 번호가 1..5 정확
step_ns = sorted(n for k,n,_ in cyc_all if k=="step")
m2 = (n_open==1 and n_step==5 and n_close==1 and step_ns==[1,2,3,4,5])
check("M2-parse-accurate", m2,
      f"open={n_open}(=1) step={n_step}(=5) close={n_close}(=1) step번호={step_ns}(=1..5) "
      f"→ 실제 원장 subject 분류·N/5 추출 정확")

# ── M3: C018 통합 (H1c) — 도출 지문 → retro_imprint → rebuild 노드 ───
# 격리 저장소에 C015 커밋들을 v2 스타일로 재현(subject만) → 도출 → 각인 → 복원.
R = os.path.join(SCRATCH, "repo")
subprocess.run(["rm","-rf",SCRATCH]); os.makedirs(R)
def rg(*a): return git(R, *a)
rg("init","-q","-b","main"); rg("config","user.email","t@t"); rg("config","user.name","t")
# 실제 C015 step 커밋 subject 5개를 순서대로 커밋(v2 유령 재현)
step_subjects = [git(REPO,"log","-1","--format=%s",h).strip() for h,_ in commits]
for i, subj in enumerate(step_subjects):
    open(os.path.join(R,"f%d"%i),"w").write("x")
    rg("add","-A"); rg("commit","-q","-m",subj)
# 재현 커밋 리스트 수집 (시간순)
repro = [(h, git(R,"log","-1","--format=%s",h).strip())
         for h in git(R,"log","--reverse","--format=%H").split()]
derived = DF.derive_cycle(repro, "supported")
# 각 도출 지문을 retro_imprint로 각인
for h, trailers, ap in derived:
    RI.retro_imprint(R, h, trailers)
# rebuild가 s1~s5를 노드로 복원
nodes = RM.rebuild(R)
node_ids = {n["id"] for n in nodes}
m3 = ({"s1","s2","s3","s4","s5"} <= node_ids and len(nodes) == 5)
check("M3-c018-integration", m3,
      f"복원노드={sorted(node_ids)} (s1~s5 편입={ {'s1','s2','s3','s4','s5'} <= node_ids }) "
      f"→ 도출 지문 → retro_imprint → rebuild 왕복 (C018 재사용)")

# ── M4: 근사 명시 (H4d) ─────────────────────────────────────────────
# V2_STEP_TO_KIND 테이블 존재 + 근사 스텝 표기.
has_table = hasattr(DF, "V2_STEP_TO_KIND") and hasattr(DF, "V2_APPROXIMATE_STEPS")
approx_marked = sum(1 for _,_,ap in derived if ap) == 3  # 2·4·5 근사
m4 = has_table and approx_marked
check("M4-approximation-honest", m4,
      f"매핑테이블존재={has_table} 근사스텝표기={approx_marked}(=3: 2·4·5) "
      f"→ v2 5스텝→v3 4kind 근사 명시(무손실 주장 안 함)")

# ── 판정 ──
print()
allpass = all(ok for _, ok, _ in results)
print(f"=== {'ALL PASS — supported' if allpass else '일부 FAIL'} ({sum(ok for _,ok,_ in results)}/{len(results)}) ===")
sys.exit(0 if allpass else 1)
