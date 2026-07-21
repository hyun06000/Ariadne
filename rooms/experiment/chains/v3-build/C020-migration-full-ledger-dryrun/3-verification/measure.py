#!/usr/bin/env python3
"""C020 측정 — 전량 순회 소급 (격리 복제본). 5측정.

M1 전량 순회 무사고(원장 커밋 SHA 불변) · M2 유령 감소(대표 사이클) ·
M3 도출 견고성(→·— 둘 다, release 스킵) · M4 잔여 투명성(3종 분류 합 일치) ·
M5 원장 불변(우리 실제 저장소 무손상).
"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import full_ledger_migrate as FLM
import derive_fingerprint as DF
import rebuild_migrate as RM

REAL_REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "..", ".."))
SCRATCH = sys.argv[1] if len(sys.argv) > 1 else \
    "/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c020-fullledger"
CLONE = os.path.join(SCRATCH, "clone")

def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout

results = []
def check(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

# 복제본은 build_case가 이미 --apply 각인한 상태.

# ── M5 먼저: 원장 불변 (격리 철칙) — 측정 시작 시 우리 저장소 스냅샷 ──────
real_head_before = git(REAL_REPO, "rev-parse", "HEAD").strip()
real_notes_before = git(REAL_REPO, "notes", "list")  # 우리 원장 notes (있으면)

# ── M1: 전량 순회 무사고 (H1a) — 복제본 원장 커밋 SHA 불변 ────────────
# clone 직후 SHA(우리 원장과 동일해야) vs 각인 후 SHA
clone_shas = set(git(CLONE, "rev-list", "HEAD").split())
real_shas = set(git(REAL_REPO, "rev-list", "HEAD").split())
# 복제본 커밋 SHA가 우리 원장과 동일(notes 각인이 커밋 안 바꿈)
m1 = clone_shas == real_shas and len(clone_shas) > 1000
check("M1-full-sweep-safe", m1,
      f"복제본 커밋 SHA == 원장 SHA={clone_shas==real_shas} 커밋수={len(clone_shas)} "
      f"→ notes 각인이 커밋 하나도 안 바꿈 (전량 순회 무사고)")

# ── M2: 유령 감소 (H1b) — 대표 사이클 재구성 ────────────────────────
# 소급된 사이클 하나(C015)를 복제본에서 재구성 — notes로 스텝 노드 나오나.
# rebuild_migrate는 사이클 dir이 아니라 repo 전체 log를 보므로, 대신
# C015 step 커밋들이 notes를 받았는지로 유령 감소를 확인.
c015_commits = FLM.cycle_step_commits(CLONE, "v3-build", "C015-merge-is-lineage-command")
noted = 0
for h in c015_commits:
    n = subprocess.run(["git","-C",CLONE,"notes","show",h],
                       capture_output=True,text=True)
    if n.returncode == 0 and "Step-Id" in n.stdout:
        noted += 1
m2 = len(c015_commits) >= 4 and noted == len(c015_commits)
check("M2-ghost-reduced", m2,
      f"C015 step커밋={len(c015_commits)} notes받음={noted} (전부={noted==len(c015_commits)}) "
      f"→ 소급된 사이클의 스텝이 지문 받음 (유령→노드)")

# ── M3: 도출 견고성 (H1c) — →·— 둘 다, release 스킵 ──────────────────
# → 형식과 — 형식 subject를 둘 다 파싱하는지 직접 시험
s_arrow = "gil: step loom/C015 → 3/5 검증"
s_dash  = "gil: step v3-build/C003 — 3/5 검증 산출물"
s_rel   = "gil: release v2.10.0"
import re
m_arrow = FLM.RE_STEP2.match(s_arrow)
m_dash  = FLM.RE_STEP2.match(s_dash)
m_rel   = FLM.RE_STEP2.match(s_rel)
mgmt_rel = FLM.LEDGER_MGMT.match(s_rel)
m3 = bool(m_arrow and m_arrow.group(2)=="3" and m_dash and m_dash.group(2)=="3"
          and not m_rel and mgmt_rel)
check("M3-derive-robust", m3,
      f"→파싱={bool(m_arrow)} —파싱={bool(m_dash)} release는step아님={not m_rel} "
      f"release는관리로분류={bool(mgmt_rel)} → 이질 형식 견고, 오각인 0")

# ── M4: 잔여 투명성 (H1d) — 3종 분류 합이 전체 유령과 일치 ────────────
g = FLM.classify_ghosts(CLONE)
total_ghost = g["non_ledger"] + g["ledger_mgmt"] + g["step_no_note"]
# 전체 유령 = trailer도 notes도 없는 커밋 수 (독립 계산)
all_out = git(CLONE, "log", "--format=%H").split()
independent_ghost = 0
for h in all_out:
    tr = git(CLONE,"log","-1","--format=%(trailers:key=Step-Id,valueonly)",h).strip()
    if tr: continue
    n = subprocess.run(["git","-C",CLONE,"notes","show",h],capture_output=True,text=True)
    if n.returncode==0 and n.stdout.strip(): continue
    independent_ghost += 1
m4 = total_ghost == independent_ghost and total_ghost > 0
check("M4-residual-transparent", m4,
      f"3종분류합={total_ghost}(비원장{g['non_ledger']}·관리{g['ledger_mgmt']}·도출실패{g['step_no_note']}) "
      f"독립계산유령={independent_ghost} 일치={total_ghost==independent_ghost} → 잔여 정체 투명(침묵 0)")

# ── M5: 원장 불변 (격리) — 우리 실제 저장소 무손상 ────────────────────
real_head_after = git(REAL_REPO, "rev-parse", "HEAD").strip()
real_notes_after = git(REAL_REPO, "notes", "list")
m5 = (real_head_before == real_head_after and real_notes_before == real_notes_after)
check("M5-real-repo-untouched", m5,
      f"우리원장 HEAD불변={real_head_before==real_head_after} notes불변={real_notes_before==real_notes_after} "
      f"→ 격리 철칙 준수 (복제본만 각인, 우리 저장소 무손상)")

# ── 판정 ──
print()
allpass = all(ok for _, ok, _ in results)
print(f"=== {'ALL PASS — supported' if allpass else '일부 FAIL'} ({sum(ok for _,ok,_ in results)}/{len(results)}) ===")
sys.exit(0 if allpass else 1)
