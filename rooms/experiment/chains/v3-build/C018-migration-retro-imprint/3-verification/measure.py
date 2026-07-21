#!/usr/bin/env python3
"""C018 측정 — git notes 소급각인 (커밋 불변). 4측정.

M1 커밋 불변(notes 각인 전후 원장 SHA 동일) · M2 notes=trailer(소급 유령이 노드) ·
M3 유령 감소(소급 후 유령 수 = 원래 − pre-gil) · M4 pre-gil/close 구분.

C009~C017 measure 리듬 계승 — subprocess 순수 깃, 파이썬은 판정만.
"""
import subprocess, sys, os

SCRATCH = sys.argv[1] if len(sys.argv) > 1 else \
    "/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c018-retro"
R = os.path.join(SCRATCH, "repo")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rebuild_migrate as RM
import retro_imprint as RI

def git(*a):
    return subprocess.run(["git", "-C", R, *a], capture_output=True, text=True).stdout

def load_index():
    d = {}
    with open(os.path.join(SCRATCH, "commit-index.txt")) as f:
        for line in f:
            p = line.split()
            if len(p) == 2: d[p[0]] = p[1]
    return d
CI = load_index()

results = []
def check(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

# build_case가 이미 소급각인을 실행한 상태. 여기선 결과를 감사 + M1은 깨끗한 재현.

# ── M1: 커밋 불변 (H1a) — 소급각인이 원장 SHA를 안 바꾼다 ─────────────
# 깨끗한 재현: 새 저장소에 유령 하나 만들고 notes 각인 전후 원장 SHA 대조.
PROBE = os.path.join(SCRATCH, "probe")
subprocess.run(["rm","-rf",PROBE]); os.makedirs(PROBE)
def pgit(*a): return subprocess.run(["git","-C",PROBE,*a],capture_output=True,text=True).stdout
pgit("init","-q","-b","main"); pgit("config","user.email","t@t"); pgit("config","user.name","t")
open(os.path.join(PROBE,"a"),"w").write("x"); pgit("add","a"); pgit("commit","-q","-m","ghost")
before = RI._commit_shas(PROBE)
ghost = pgit("rev-parse","HEAD").strip()
RI.retro_imprint(PROBE, ghost, [("Step-Id","L1"),("Kind","define"),("Parent","null")])
after = RI._commit_shas(PROBE)
ghost_after = pgit("rev-parse","HEAD").strip()
m1 = (before == after and ghost == ghost_after)
check("M1-commit-immutable", m1,
      f"원장SHA 각인전후동일={before==after} 유령커밋SHA불변={ghost==ghost_after} "
      f"→ git notes가 커밋 안 바꿈 (append-only 준수, amend/rebase 아님)")

# ── M2: notes=trailer 동등 (H1b) — 소급 유령이 노드로 복원 ────────────
nodes = RM.rebuild(R)
node_ids = {n["id"] for n in nodes}
# L1·L2·L3(소급된 유령)가 노드로 + 지문 값이 notes와 일치
l_present = {"L1","L2","L3"} <= node_ids
byid = {n["id"]: n for n in nodes}
l_correct = (byid.get("L1",{}).get("kind")=="define" and byid.get("L1",{}).get("parent") is None and
             byid.get("L2",{}).get("kind")=="hypothesis" and byid.get("L2",{}).get("parent")=="L1" and
             byid.get("L3",{}).get("kind")=="verify" and byid.get("L3",{}).get("parent")=="L2")
m2 = l_present and l_correct
check("M2-notes-equals-trailer", m2,
      f"L1·L2·L3 노드편입={l_present} 지문값정확={l_correct} "
      f"→ notes를 trailer와 동등하게 읽음 (같은 파서, 재구현 0)")

# ── M3: 유령 감소 (H1c) — 소급 후 유령 = 원래 − pre-gil ──────────────
_, ghosts = RM.rebuild(R, report=True)
# 원래 유령 4(pre-gil 3 + close 1) → 소급 후 1(close만)
m3 = len(ghosts) == 1 and CI["CLOSE"][:12] in [g[:12] for g in ghosts]
check("M3-ghost-reduced", m3,
      f"소급후유령수={len(ghosts)}(=1, close만) close가그유령={CI['CLOSE'][:12] in [g[:12] for g in ghosts]} "
      f"→ pre-gil 3개 소급되어 유령 4→1 (전부 소급하면 close만 남음)")

# ── M4: pre-gil/close 구분 (H1d) — 소급은 pre-gil만, close 안 건드림 ──
def has_notes(commit):
    r = subprocess.run(["git","-C",R,"notes","show",commit],
                       capture_output=True,text=True)
    return r.returncode == 0
pre_gil_noted = all(has_notes(CI[g]) for g in ["G1","G2","G3"])
close_not_noted = not has_notes(CI["CLOSE"])
m4 = pre_gil_noted and close_not_noted
check("M4-pregil-close-split", m4,
      f"pre-gil3개notes有={pre_gil_noted} close커밋notes無={close_not_noted} "
      f"→ 소급각인이 pre-gil만 대상, close(이미 v3) 안 건드림")

# ── 판정 ──
print()
allpass = all(ok for _, ok, _ in results)
print(f"=== {'ALL PASS — supported' if allpass else '일부 FAIL'} ({sum(ok for _,ok,_ in results)}/{len(results)}) ===")
sys.exit(0 if allpass else 1)
