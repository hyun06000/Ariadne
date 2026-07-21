#!/usr/bin/env python3
"""C012 측정 — 머지 = lineage = 지식 통합. 순수 깃 감사.

M1 다중부모 담김 · M2 그래프가 합류로 그림 · M3 부모 지문만으로 lineage 재구성 ·
M4 실제 통합(공통조상·두 기여·진짜 머지·음성대조 squash).

C011 measure.py의 리듬 계승 — subprocess로 순수 깃만, 파이썬은 파싱·판정만.
"""
import subprocess, sys, os

SCRATCH = sys.argv[1] if len(sys.argv) > 1 else \
    "/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/bb9fdd96-c034-4239-a589-5d66caf9e63b/scratchpad/c012-merge"
R = os.path.join(SCRATCH, "repo")

def git(*a):
    return subprocess.run(["git", "-C", R, *a], capture_output=True, text=True).stdout

def load_index():
    d = {}
    with open(os.path.join(SCRATCH, "commit-index.txt")) as f:
        for line in f:
            k, v = line.split()
            d[k] = v
    return d

CI = load_index()
results = []
def check(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

# ── M1: 다중부모 담김 ──────────────────────────────────────────────
# 머지 커밋이 부모 2개를 담고, 그 두 부모가 각각 C016·C020 갈래 팁.
raw = git("cat-file", "-p", CI["c036_merge"])
parents = [l.split()[1] for l in raw.splitlines() if l.startswith("parent ")]
p_set = set(parents)
expected = {CI["lane_C020"], CI["lane_C016"]}  # C020 위에서 C016 머지 → 부모: [C020, C016]
m1_count = len(parents) == 2
m1_match = p_set == expected
# trailer의 Parent 순서가 gil [C020, C016]이고 git 첫 부모=C020(HEAD)인지
trailer = git("log", "-1", "--format=%(trailers:key=Parent,valueonly)", CI["c036_merge"]).strip()
first_parent_is_C020 = parents and parents[0] == CI["lane_C020"]
m1 = m1_count and m1_match and trailer == "C020, C016" and first_parent_is_C020
check("M1-multiparent", m1,
      f"부모수={len(parents)}(=2 기대) 부모집합일치={m1_match} "
      f"trailer='{trailer}'(='C020, C016') 첫부모=C020={first_parent_is_C020} "
      f"→ gil [C020,C016] ≅ git parents")

# ── M2: 그래프가 합류로 그림 ─────────────────────────────────────────
# git log --all --graph에서 머지 커밋이 두 입력 엣지를 합친다.
# 머지 커밋의 부모가 2 → 위상상 in-degree 2 (병합 노드). gil log '◀ 병합:'과 동형.
short_merge = git("rev-parse", "--short", CI["c036_merge"]).strip()
# rev-list --parents로 위상 확인: 머지 커밋 줄에 해시 3개(자기+부모2)
rl = git("rev-list", "--parents", "--all").splitlines()
merge_line = [l for l in rl if l.split() and l.split()[0].startswith(CI["c036_merge"][:12])]
m2_indeg = merge_line and len(merge_line[0].split()) == 3  # 자기 + 부모 2
# 다른 커밋들은 부모 0~1 (선형/루트) — 머지만 부모 2
merge_nodes = [l for l in rl if len(l.split()) == 3]
m2 = m2_indeg and len(merge_nodes) == 1
check("M2-graph-confluence", m2,
      f"머지노드 in-degree=2={bool(m2_indeg)} 전체머지노드수={len(merge_nodes)}(=1 기대) "
      f"→ git log --graph가 병합 노드로 그림 (뷰어 재구현 0)")

# ── M3: 부모 지문만으로 lineage 재구성 (cycle.yaml 안 봄) ──────────────
# git log --format=%H %P (부모 해시)만 읽어 DAG 복원 → C036이 C016·C020 두 부모.
# 정적 감사: 이 측정이 부르는 git 하위명령이 log(부모)뿐 — cat-file/show/cycle.yaml 0.
dag = {}
for line in git("log", "--all", "--format=%H %P").splitlines():
    parts = line.split()
    if not parts: continue
    node, pars = parts[0], parts[1:]
    dag[node] = pars
# 재구성된 머지 노드: 부모 2개인 노드
reconstructed_merges = {n: ps for n, ps in dag.items() if len(ps) == 2}
r_ok = (len(reconstructed_merges) == 1 and
        CI["c036_merge"] in reconstructed_merges and
        set(reconstructed_merges[CI["c036_merge"]]) == {CI["lane_C020"], CI["lane_C016"]})
# 재구성이 gil 논리 id로 라벨되는지 — 각 부모 커밋의 trailer Cycle 읽어 위상 라벨
def cycle_of(h): return git("log","-1","--format=%(trailers:key=Cycle,valueonly)",h).strip()
merge_cycle = cycle_of(CI["c036_merge"])
par_cycles = sorted(cycle_of(p) for p in reconstructed_merges.get(CI["c036_merge"], []))
m3 = r_ok and merge_cycle == "C036" and par_cycles == ["C016", "C020"]
check("M3-reconstruct-from-parents", m3,
      f"부모지문만복원 머지노드={len(reconstructed_merges)}(=1) "
      f"머지사이클={merge_cycle} 부모사이클={par_cycles}(=['C016','C020']) "
      f"→ cycle.yaml 안 보고 lineage DAG 복원 (C009 합류판)")

# ── M4: 실제 통합 (이름뿐 아님) ──────────────────────────────────────
# ① merge-base가 공통 조상(s0/사이클 루트) 찾는다.
mb = git("merge-base", CI["lane_C016"], CI["lane_C020"]).strip()
m4_base = mb == CI["s0"]
# ② 머지 이후(산 잎)에 두 갈래 코드 기여가 모두 존재.
files_at_leaf = set(git("ls-tree", "-r", "--name-only", CI["c036_leaf"]).split())
m4_both = {"ledger.py", "web.py", "integrated.py"} <= files_at_leaf
# ③ 진짜 머지 커밋(fast-forward 아님) — 부모 2개 (M1에서 확인, 재확인)
m4_real = len(git("cat-file","-p",CI["c036_merge"]).splitlines()) and \
          len([l for l in git("cat-file","-p",CI["c036_merge"]).splitlines() if l.startswith("parent ")]) == 2
# ④ 음성 대조: --squash 머지는 다중부모를 안 만든다 → lineage 소실.
#    깨끗한 새 저장소에 두 갈래 팁만 fetch(원본 머지 커밋은 안 가져옴)하고 squash 머지 →
#    부모 지문 재구성이 합류를 놓침을 보인다. (cp -r는 원본 머지 커밋을 딸려와 대조 오염 — 계측기 결함 수리)
SQ = os.path.join(SCRATCH, "squash-repo")
subprocess.run(["rm","-rf",SQ]); os.makedirs(SQ)
def sgit(*a): return subprocess.run(["git","-C",SQ,*a],capture_output=True,text=True).stdout
sgit("init","-q","-b","main")
sgit("config","user.email","clew@ariadne.local"); sgit("config","user.name","clew")
sgit("config","advice.detachedHead","false")
# 두 갈래 팁만 가져온다 — 머지 커밋 없이 (fetch는 도달 가능한 조상만: s0→갈래 스텝들)
sgit("fetch","-q",R,f"{CI['lane_C020']}:refs/heads/lane-C020",f"{CI['lane_C016']}:refs/heads/lane-C016")
sgit("checkout","-q","-b","sq-base","lane-C020")
sgit("merge","--squash","lane-C016")
sgit("commit","-q","-m","squash: C020+C016 (다중부모 없음)")
sq_head = sgit("rev-parse","HEAD").strip()
sq_parents = [l.split()[1] for l in sgit("cat-file","-p",sq_head).splitlines() if l.startswith("parent ")]
# squash 커밋은 부모 1개 → C016 계보가 부모 지문에서 사라짐 → lineage 재구성이 합류 놓침
sq_reconstruct_sees_C016 = any(
    set(l.split()[1:]) >= {CI["lane_C020"], CI["lane_C016"]}
    for l in sgit("log","--all","--format=%H %P").splitlines() if l.split()
)
m4_squash_loses = len(sq_parents) == 1 and not sq_reconstruct_sees_C016
m4 = m4_base and m4_both and m4_real and m4_squash_loses
check("M4-real-integration", m4,
      f"공통조상=s0={m4_base} 두기여모두존재={m4_both} 진짜머지(부모2)={m4_real} "
      f"음성대조:squash가lineage잃음={m4_squash_loses}(부모수={len(sq_parents)}) "
      f"→ 다중부모여야 지식통합 보존")

# ── 판정 ──
print()
allpass = all(ok for _, ok, _ in results)
print(f"=== {'ALL PASS — supported' if allpass else '일부 FAIL'} ({sum(ok for _,ok,_ in results)}/{len(results)}) ===")
sys.exit(0 if allpass else 1)
