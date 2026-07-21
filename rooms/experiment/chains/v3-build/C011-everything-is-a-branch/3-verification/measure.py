#!/usr/bin/env python3
"""C011 측정 — 백트래킹=checkout+detached, 위계=커밋 지문, 이름=체인/사이클 의미+스텝 해시.

상현님 모델(이 사이클 대화로 확정):
  - 백트래킹은 새 브랜치가 아니라 git checkout <조상> + detached HEAD 커밋.
  - 위계 지문은 커밋 메시지 trailer에 (Chain·Cycle·Step-Id·Parent·Backtrack-To).
  - 뷰어 = git 그래프 전체 + 커밋 메시지.
  - 이름: 체인·사이클 분기=의미 이름, 스텝 분기=구분용 해시 ref면 충분.

4측정:
  M1 위계 지문 완전성        (K1): 모든 스텝 커밋이 Chain·Cycle·Step-Id·Parent 지문
  M2 1스텝 = 1커밋          (K2)
  M3 죽은 가지 생존 + 롤백    (K3): 해시 ref로 그래프 생존 + git show 롤백(워킹트리 무손상)
                                   + 음성 대조(ref 없으면 --all이 못 봄)
  M4 위계 복원              (K4): 커밋 지문만으로 체인⊃사이클⊃스텝·죽은/산 잎 복원

사용법: python3 measure.py <repo> <commit-index.txt>
"""
import sys, subprocess


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE
                          ).stdout.decode()


def tr(repo, commit, key):
    return git(repo, "log", "-1",
               "--format=%(trailers:key=" + key + ",valueonly)", commit).strip()


def all_step_commits(repo):
    """--all 이 보는 커밋 중 Step-Id 지문 있는 것 (시간순 무관, 집합)."""
    out = []
    for h in git(repo, "log", "--all", "--format=%H").split():
        sid = tr(repo, h, "Step-Id")
        if sid:
            out.append((h, sid))
    return out


def m1_fingerprint(repo):
    """모든 스텝 커밋(root 포함)이 위계 지문을 완전히 담는가."""
    commits = all_step_commits(repo)
    missing = []
    for h, sid in commits:
        for key in ("Kind", "Parent", "Chain", "Cycle"):
            if not tr(repo, h, key) and not (sid == "s0" and key == "Cycle"):
                missing.append((sid, key))
    # 백트래킹 커밋은 Backtrack-To 지문 필수
    bt_ok = True
    for h, sid in commits:
        if tr(repo, h, "Outcome") == "backtrack" and not tr(repo, h, "Backtrack-To"):
            bt_ok = False
    ok = not missing and bt_ok
    print("  M1 스텝커밋 %d개, 지문누락=%s, 백트래킹 Backtrack-To=%s"
          % (len(commits), missing or "없음", "완전" if bt_ok else "누락"))
    return ok, "K1", "위계 지문 완전 (Chain·Cycle·Step-Id·Parent·Backtrack-To)"


def m2_one_step_one_commit(repo):
    commits = all_step_commits(repo)
    sids = [sid for _, sid in commits]
    uniq = set(sids)
    one_each = len(sids) == len(uniq)
    # 머지·태그는 스텝 아님. 여기선 머지 커밋 0 (detached 모델은 머지 없이 분기).
    merges = git(repo, "log", "--all", "--merges", "--format=%H").split()
    ok = one_each and len(uniq) == 11 and len(merges) == 0
    print("  M2 스텝커밋 %d, 고유 %d, 1스텝=1커밋=%s, 머지커밋=%d(detached라 0)"
          % (len(sids), len(uniq), one_each, len(merges)))
    return ok, "K2", "1스텝=1커밋 (0/2커밋 스텝 0)"


def m3_dead_survival_rollback(repo, index):
    """죽은 가지 생존(해시 ref로 그래프에 뜸) + git show 롤백(워킹트리 무손상)
    + 음성 대조(ref 없으면 --all이 못 본다)."""
    s4 = index["s4"]; s7 = index["s7"]
    # (a) 해시 ref로 죽은 잎이 --all 그래프에 보이는가
    all_hashes = set(git(repo, "log", "--all", "--format=%H").split())
    dead_visible = (s4 in all_hashes) and (s7 in all_hashes)
    # (b) git show 로컬 롤백 — 워킹트리 안 깨고 죽은 잎 코드 꺼냄
    head_before = git(repo, "rev-parse", "HEAD").strip()
    status_before = git(repo, "status", "--porcelain")
    s4_code = git(repo, "show", s4 + ":artifact.py")
    s7_code = git(repo, "show", s7 + ":artifact.py")
    rolled = ("s4 죽음" in s4_code) and ("s7 죽음" in s7_code)
    worktree_intact = (head_before == git(repo, "rev-parse", "HEAD").strip()
                       and status_before == git(repo, "status", "--porcelain"))
    # (c) 음성 대조: 해시 태그를 지우면 --all이 죽은 잎을 못 본다 (ref 필요성 증명)
    #     s7의 태그를 임시 삭제 → --all 재조회 → 복원. (태그=불변 못, push되어 공유)
    short7 = git(repo, "rev-parse", "--short", s7).strip()
    git(repo, "tag", "-d", "gil/leaf/" + short7)
    after_del = set(git(repo, "log", "--all", "--format=%H").split())
    vanished = s7 not in after_del      # 태그 지우니 그래프에서 사라짐
    git(repo, "tag", "gil/leaf/" + short7, s7)  # 복원
    restored = s7 in set(git(repo, "log", "--all", "--format=%H").split())
    ok = dead_visible and rolled and worktree_intact and vanished and restored
    print("  M3 죽은잎 그래프생존(해시ref)=%s, git show 롤백=%s, 워킹트리무손상=%s"
          % (dead_visible, rolled, worktree_intact))
    print("     음성대조: ref 지우면 사라짐=%s, 복원하면 다시 보임=%s (∴ref 필요)"
          % (vanished, restored))
    print("     s4 죽은잎 코드: %s" % s4_code.strip())
    return ok, "K3", "죽은가지 생존(해시ref)+git show 롤백(워킹트리무손상), ref 필요성 실증"


def m4_hierarchy_from_fingerprint(repo):
    """커밋 지문(trailer)만으로 위계 복원 — 브랜치·태그 안 보고 Chain·Cycle·Parent로.
    이것이 상현님 '커밋 메시지에 위계 지문' 모델의 핵심 검증."""
    commits = all_step_commits(repo)
    by_sid = {}
    for h, sid in commits:
        by_sid[sid] = {
            "hash": h,
            "chain": tr(repo, h, "Chain"),
            "cycle": tr(repo, h, "Cycle"),
            "parent": tr(repo, h, "Parent"),
            "kind": tr(repo, h, "Kind"),
            "outcome": tr(repo, h, "Outcome"),
            "backtrack": tr(repo, h, "Backtrack-To"),
        }
    # 위계: 모든 스텝이 같은 체인 v3-demo, s1~s10이 사이클 C-demo
    chains = {v["chain"] for v in by_sid.values()}
    cycles = {v["cycle"] for v in by_sid.values() if v["cycle"] not in (None, "null", "")}
    one_chain = chains == {"v3-demo"}
    one_cycle = cycles == {"C-demo"}
    # 트리: parent 링크로 세 형제 가지 (s2·s5·s8 부모가 s1)
    s1_children = sorted(sid for sid, v in by_sid.items() if v["parent"] == "s1")
    tree_ok = s1_children == ["s2", "s5", "s8"]
    # 죽은/산 잎: outcome으로 (backtrack=죽음, success=산)
    dead = sorted(sid for sid, v in by_sid.items() if v["outcome"] == "backtrack")
    live = sorted(sid for sid, v in by_sid.items() if v["outcome"] == "success")
    leaf_ok = dead == ["s4", "s7"] and live == ["s10"]
    ok = one_chain and one_cycle and tree_ok and leaf_ok
    print("  M4 체인=%s, 사이클=%s, s1의 세 자식=%s, 죽은잎=%s, 산잎=%s"
          % (chains, cycles, s1_children, dead, live))
    return ok, "K4", "커밋 지문만으로 위계 복원 (체인⊃사이클⊃스텝, 죽은/산 잎)"


def load_index(path):
    idx = {}
    for line in open(path):
        parts = line.split()
        if len(parts) == 2:
            idx[parts[0]] = parts[1]
    return idx


def main():
    if len(sys.argv) < 3:
        sys.exit("사용법: measure.py <repo> <commit-index.txt>")
    repo, index_path = sys.argv[1], sys.argv[2]
    index = load_index(index_path)
    print("=== C011 측정 — 백트래킹=checkout, 위계=커밋 지문 ===")
    results = []
    for fn, args in [(m1_fingerprint, (repo,)),
                     (m2_one_step_one_commit, (repo,)),
                     (m3_dead_survival_rollback, (repo, index)),
                     (m4_hierarchy_from_fingerprint, (repo,))]:
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
