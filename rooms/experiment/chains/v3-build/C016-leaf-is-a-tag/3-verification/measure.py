#!/usr/bin/env python3
"""C016 측정 — 잎 못=태그 정식화. 5측정 감사.

M1 잎=태그(브랜치 못 0) · M2 종결=태그 · M3 dangling 방지(잎·머지·close 생존) ·
M4 불변성(태그가 잎 커밋에 고정) · M5 회귀(C015 lineage + C014 백트래킹 불변).

C014·C015 measure 리듬 계승 — subprocess 순수 깃, 파이썬은 파싱·판정만.
"""
import subprocess, sys, os

SCRATCH = sys.argv[1] if len(sys.argv) > 1 else \
    "/private/tmp/claude-501/-Users-davi-Desktop-code-my-project-Ariadne/930cf6a0-6608-412b-9001-1786d9caf97a/scratchpad/c016-leaf-tag"
RM = os.path.join(SCRATCH, "merge")      # caseM: lineage 머지 (C015 표적)
RB = os.path.join(SCRATCH, "backtrack")  # caseB: 3층 분기 (C014 표적)

def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout

results = []
def check(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

def tags(repo):     return set(git(repo, "tag", "-l").split())
def gil_branches(repo):
    return [b.strip().lstrip("* ") for b in git(repo, "branch", "--list", "gil/*").splitlines() if b.strip()]
def sid_commit(repo, sid):
    fmt = "%H\x1f%(trailers:key=Step-Id,valueonly)"
    for line in git(repo, "log", "--all", "--format="+fmt).splitlines():
        if "\x1f" in line:
            h, tid = line.split("\x1f", 1)
            if tid.strip() == sid:
                return h.strip()
    return None
def short(repo, h): return git(repo, "rev-parse", "--short", h).strip()

# ── M1: 잎=태그, 브랜치 못 0 ────────────────────────────────────────
# caseM: 산 잎 s4·s7 이 gil/leaf/<short> 태그. caseB: 죽은 잎 s4·s7 + 산 잎 s10.
def leaf_tagged(repo, leaf_sids):
    tg = tags(repo)
    all_ok = True
    for s in leaf_sids:
        c = sid_commit(repo, s)
        want = "gil/leaf/%s" % short(repo, c)
        if want not in tg:
            all_ok = False
    return all_ok
m_leaves = leaf_tagged(RM, ["s4", "s7"])       # 두 산 잎
b_leaves = leaf_tagged(RB, ["s4", "s7", "s10"]) # 죽은 잎 2 + 산 잎 1
no_branch_m = len(gil_branches(RM)) == 0
no_branch_b = len(gil_branches(RB)) == 0
m1 = m_leaves and b_leaves and no_branch_m and no_branch_b
check("M1-leaf-is-tag", m1,
      f"caseM 산잎2태그={m_leaves} caseB 잎3태그={b_leaves} "
      f"브랜치못 M={len(gil_branches(RM))} B={len(gil_branches(RB))}(둘다=0) "
      f"→ 모든 잎이 gil/leaf/<hash> 태그, 브랜치 못 0 (C011 결론)")

# ── M2: 종결=태그 ──────────────────────────────────────────────────
# cycle/<name>/solved 태그가 close 커밋에.
m2_m = "cycle/merge/solved" in tags(RM)
m2_b = "cycle/backtrack/solved" in tags(RB)
# solved 태그가 실제 close(봉인) 커밋을 가리키는지
def close_commit(repo):
    for line in git(repo, "log", "--all", "--format=%H %s").splitlines():
        if "봉인" in line:
            return line.split()[0]
    return None
solved_m = git(RM, "rev-parse", "cycle/merge/solved").strip()
cc_m = close_commit(RM)
m2_points = solved_m == cc_m
m2 = m2_m and m2_b and m2_points
check("M2-sealed-is-tag", m2,
      f"caseM종결태그={m2_m} caseB종결태그={m2_b} solved→봉인커밋일치={m2_points} "
      f"→ cycle/<name>/solved 태그가 close 커밋에 (C011·gil v2 규율)")

# ── M3: dangling 방지 (잎·머지·close 생존) ──────────────────────────
# 태그도 ref라 rev-list --all 이 잎·머지·close 를 도달가능으로 봄.
def all_commits(repo): return set(git(repo, "rev-list", "--all").split())
# caseM: 두 산 잎 + 머지 커밋 생존
m_all = all_commits(RM)
merge_c = None
for line in git(RM, "log", "--all", "--format=%H %P").splitlines():
    if len(line.split()) == 3:  # 다중부모 = 머지
        merge_c = line.split()[0]
m3_m = {sid_commit(RM,"s4"), sid_commit(RM,"s7"), merge_c} <= m_all
# caseB: 죽은 잎 2 + 산 잎 1 + close 생존
b_all = all_commits(RB)
m3_b = {sid_commit(RB,"s4"), sid_commit(RB,"s7"), sid_commit(RB,"s10"), close_commit(RB)} <= b_all
m3 = m3_m and m3_b
check("M3-dangling-prevented", m3,
      f"caseM 두산잎+머지생존={m3_m} caseB 죽은2+산1+close생존={m3_b} "
      f"→ 태그 ref가 dangling 방지 (브랜치와 등가, 더 정확)")

# ── M4: 불변성 (태그가 잎 커밋에 고정) ──────────────────────────────
# 태그는 브랜치와 달리 후속 커밋에 안 옮긴다. gil/leaf/<short> == 해당 잎 커밋.
def tag_points_correct(repo, sid):
    c = sid_commit(repo, sid)
    tag = "gil/leaf/%s" % short(repo, c)
    return git(repo, "rev-parse", tag).strip() == c
m4 = all(tag_points_correct(RM, s) for s in ["s4","s7"]) and \
     all(tag_points_correct(RB, s) for s in ["s4","s7","s10"])
# 추가: 태그 타입이 실제 태그인지 (브랜치 아님) — for-each-ref
tag_refs = git(RM, "for-each-ref", "--format=%(refname)", "refs/tags/gil/leaf").split()
m4_istag = len(tag_refs) == 2  # caseM 잎 2개가 refs/tags 아래
m4 = m4 and m4_istag
check("M4-immutable", m4,
      f"태그→잎커밋정확={all(tag_points_correct(RM,s) for s in ['s4','s7'])}(caseM) "
      f"refs/tags/gil/leaf수={len(tag_refs)}(=2) → 태그가 잎에 고정, 브랜치 아님 (불변)")

# ── M5: 회귀 (C015 lineage + C014 백트래킹 불변) ────────────────────
# caseM 머지 커밋이 여전히 다중부모·trailer(Merge=lineage). caseB 3층 분기 위상 불변.
raw = git(RM, "cat-file", "-p", merge_c)
parents = [l.split()[1] for l in raw.splitlines() if l.startswith("parent ")]
m5_multiparent = len(parents) == 2 and set(parents) == {sid_commit(RM,"s4"), sid_commit(RM,"s7")}
m5_trailer = git(RM,"log","-1","--format=%(trailers:key=Merge,valueonly)",merge_c).strip() == "lineage"
# caseB: s1 이 자식 3개(세 형제 가지) — C014 M1 위상
children = 0
for line in git(RB,"log","--all","--format=%H %P").splitlines():
    parts = line.split()
    if len(parts) >= 2 and sid_commit(RB,"s1") in parts[1:]:
        children += 1
m5_branch = children == 3  # 세 형제 가지
m5 = m5_multiparent and m5_trailer and m5_branch
check("M5-regression", m5,
      f"caseM 다중부모={m5_multiparent} Merge=lineage={m5_trailer} "
      f"caseB s1자식수={children}(=3 세형제) → 태그 전환이 C015 lineage·C014 분기 안 깸")

# ── 판정 ──
print()
allpass = all(ok for _, ok, _ in results)
print(f"=== {'ALL PASS — supported' if allpass else '일부 FAIL'} ({sum(ok for _,ok,_ in results)}/{len(results)}) ===")
sys.exit(0 if allpass else 1)
