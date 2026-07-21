#!/usr/bin/env python3
"""C017 측정 — v3의 눈이 지문 없는 v2 유령을 건너뛴다 (읽기호환). 4측정.

M1 무해한 유령(안 죽고 v3 트리 온전) · M2 경계 보존(유령 생존·그래프 불변) ·
M3 순수 v3 무회귀(유령 0 == C010 rebuild_trailer) · M4 유령 가시성(수 보고).

C009~C016 measure 리듬 계승 — subprocess 순수 깃, 파이썬은 판정만.
"""
import subprocess, sys, os

SCRATCH = sys.argv[1] if len(sys.argv) > 1 else \
    "/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c017-migrate"
RMIX = os.path.join(SCRATCH, "mix")    # pre-gil 유령 3 + v3 트리
RPURE = os.path.join(SCRATCH, "pure")  # 유령 0(+close), v3 트리
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rebuild_migrate as RM

# C010 원본 재구성기(회귀 대조 기준)
C010 = os.path.normpath(os.path.join(HERE, "..", "..",
        "C010-commit-message-as-contract", "3-verification"))
sys.path.insert(0, C010)
import rebuild_trailer as RT

def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout

results = []
def check(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

PRE_GIL_GHOSTS = 3  # build_case가 쌓은 pre-gil 일반 커밋 수

# ── M1: 무해한 유령 (H1a) — 혼합 원장에서 안 죽고 v3 트리 온전 ──────────
mix_nodes, mix_ghosts = RM.rebuild(RMIX, report=True)
pure_nodes, pure_ghosts = RM.rebuild(RPURE, report=True)
# 혼합 원장 v3 트리가 순수 원장 v3 트리와 동형(유령이 트리 안 오염)
mix_yaml = RM.serialize(mix_nodes)
pure_yaml = RM.serialize(pure_nodes)
m1 = (len(mix_nodes) == 4 and mix_yaml == pure_yaml)
check("M1-ghost-harmless", m1,
      f"혼합원장 v3스텝수={len(mix_nodes)}(=4) 혼합트리==순수트리={mix_yaml==pure_yaml} "
      f"→ 유령 섞여도 안 죽고 v3 트리 온전 (유령이 트리 안 오염)")

# ── M2: 경계 보존 (H1b) — 유령 생존, 그래프 불변 (읽기 전용) ───────────
# 재구성 전후 rev-list --all 이 동일(재구성기가 아무것도 안 지움).
before = git(RMIX, "rev-list", "--all")
RM.rebuild(RMIX, report=True)  # 재구성 실행
after = git(RMIX, "rev-list", "--all")
# pre-gil 유령 3개가 여전히 원장에 (첫 3커밋)
first3 = git(RMIX, "log", "--oneline", "--reverse").splitlines()[:3]
ghosts_alive = all("gilv3" not in l for l in first3) and len(first3) == 3
m2 = (before == after and ghosts_alive)
check("M2-boundary-preserved", m2,
      f"재구성전후 rev-list동일={before==after} pre-gil유령3개생존={ghosts_alive} "
      f"→ 유령 삭제·변조 0, 그래프 불변 (재구성기 읽기 전용)")

# ── M3: 순수 v3 무회귀 (H1c) — 유령 0 == C010 rebuild_trailer ──────────
# rebuild_migrate 의 v3 트리 == C010 rebuild_trailer 의 트리 (스킵 로직이 순수 경로 안 건드림)
mig_pure = RM.serialize(RM.rebuild(RPURE))
c010_pure = RT.serialize(RT.rebuild(RPURE))
m3 = (mig_pure == c010_pure)
check("M3-pure-no-regression", m3,
      f"rebuild_migrate == C010 rebuild_trailer (순수 원장)={m3} "
      f"→ 유령 스킵이 C010 복원 안 깸 (회귀 0)")

# ── M4: 유령 가시성 (H1d) — 유령 수 정확 보고 ──────────────────────────
# MIX 유령 = pre-gil 3 + close 1 = 4. PURE 유령 = close 1.
mix_ghost_n = len(mix_ghosts)
pure_ghost_n = len(pure_ghosts)
# pre-gil 순수 유령 = MIX - PURE (close는 양쪽 공통 1개)
pre_gil_isolated = mix_ghost_n - pure_ghost_n
# --report stderr 출력도 확인
r = subprocess.run(["python3", os.path.join(HERE,"rebuild_migrate.py"), RMIX, "--report"],
                   capture_output=True, text=True)
report_says_4 = "유령(지문 없음) 4개" in r.stderr
m4 = (mix_ghost_n == 4 and pure_ghost_n == 1 and pre_gil_isolated == PRE_GIL_GHOSTS
      and report_says_4)
check("M4-ghost-visible", m4,
      f"MIX유령={mix_ghost_n}(=4) PURE유령={pure_ghost_n}(=1) pre-gil격리={pre_gil_isolated}(=3) "
      f"report='유령 4개'={report_says_4} → 침묵 아닌 가시적 스킵 (사용자가 규모 앎)")

# ── 판정 ──
print()
allpass = all(ok for _, ok, _ in results)
print(f"=== {'ALL PASS — supported' if allpass else '일부 FAIL'} ({sum(ok for _,ok,_ in results)}/{len(results)}) ===")
sys.exit(0 if allpass else 1)
