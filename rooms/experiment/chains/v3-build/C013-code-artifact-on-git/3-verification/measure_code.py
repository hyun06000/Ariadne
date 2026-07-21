#!/usr/bin/env python3
"""C013 측정 — 실제 코드 아티팩트(다중 파일 calc/)가 공유 경로 한 벌 위에서
스텝별 트레이싱·롤백·죽은가지 생존·같은파일 독립분기 보존되는가.

부모 C011의 measure.py 계승. C011은 artifact.py 한 파일이었고, 여기선 calc/ 다중 파일 +
세 가지가 같은 core.py를 다르게 고치는 시나리오(H4). 순수 깃 명령만 사용.

6측정:
  M1 (H1) 증분 diff 트레이싱: 각 스텝 커밋 diff의 변경 파일 집합 = 의도한 집합.
  M2 (H1) 1스텝=1커밋, 머지 0.
  M3 (H2) git show 롤백(죽은 가지 포함) + 워킹트리/HEAD/인덱스 무손상.
  M4 (H3) 죽은 가지 태그 생존 + 음성대조(태그 지우면 --all 소멸, 되박으면 부활).
  M5 (H4) 같은 파일 core.py 세 버전(s4·s7·s10)이 pairwise 상이 + 각 가지 서명 포함.
  M6 (H4) 공유 한 벌: 물리 core.py 1개인데 그래프에 3버전 공존, 각 git show 접근 가능.

사용법: python3 measure_code.py <repo> <commit-index.txt>
"""
import sys
import subprocess


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.stdout.decode()


def tr(repo, commit, key):
    return git(repo, "log", "-1",
               "--format=%(trailers:key=" + key + ",valueonly)", commit).strip()


def all_step_commits(repo):
    out = []
    for h in git(repo, "log", "--all", "--format=%H").split():
        sid = tr(repo, h, "Step-Id")
        if sid:
            out.append((h, sid))
    return out


def changed_files(repo, commit):
    """이 커밋이 부모 대비 바꾼 파일 집합 (git show --name-only)."""
    out = git(repo, "show", "--name-only", "--format=", commit)
    return set(f for f in out.split("\n") if f.strip())


def m1_incremental_diff(repo, index):
    """각 스텝 커밋 diff의 변경 파일 집합이 의도한 집합과 일치하는가.
    의도(빌드 설계): s2 core만, s3 core만, s4 core만, s5 core만, s6 core만,
    s7 core만, s8 core만, s9 core+util, s10 __init__만. s1은 core+util 도입."""
    expect = {
        "s1": {"calc/util.py", "calc/core.py"},
        "s2": {"calc/core.py"},
        "s3": {"calc/core.py"},
        "s4": {"calc/core.py"},
        "s5": {"calc/core.py"},
        "s6": {"calc/core.py"},
        "s7": {"calc/core.py"},
        "s8": {"calc/core.py"},
        "s9": {"calc/core.py", "calc/util.py"},
        "s10": {"calc/__init__.py"},
    }
    mism = []
    for sid, exp in expect.items():
        got = changed_files(repo, index[sid])
        if got != exp:
            mism.append((sid, sorted(got), sorted(exp)))
    ok = not mism
    print("  M1 증분 diff — 검사 스텝 %d개, 불일치=%s"
          % (len(expect), mism or "없음"))
    if ok:
        print("     예: s9 변경파일 = %s (core+util 다중파일 증분)"
              % sorted(changed_files(repo, index["s9"])))
    return ok, "K1", "증분 diff 트레이싱 (스텝 커밋 = 그 스텝 코드 변경분, 다중파일)"


def m2_one_step_one_commit(repo):
    commits = all_step_commits(repo)
    sids = [sid for _, sid in commits]
    uniq = set(sids)
    one_each = len(sids) == len(uniq)
    merges = git(repo, "log", "--all", "--merges", "--format=%H").split()
    ok = one_each and len(uniq) == 11 and len(merges) == 0
    print("  M2 스텝커밋 %d, 고유 %d, 1스텝=1커밋=%s, 머지=%d(detached라 0)"
          % (len(sids), len(uniq), one_each, len(merges)))
    return ok, "K2", "1스텝=1커밋"


def m3_rollback_worktree_intact(repo, index):
    """죽은 잎 s4·s7의 core.py를 git show로 꺼냄 + 조회 전후 워킹트리 무손상."""
    s4, s7 = index["s4"], index["s7"]
    head_before = git(repo, "rev-parse", "HEAD").strip()
    status_before = git(repo, "status", "--porcelain")
    idx_before = git(repo, "diff", "--cached", "--stat")
    disk_before = open(repo + "/calc/core.py").read()

    s4_code = git(repo, "show", s4 + ":calc/core.py")
    s7_code = git(repo, "show", s7 + ":calc/core.py")
    rolled = ("BRANCH-A-SIGNATURE" in s4_code and "s4 branch-A 죽음" in s4_code
              and "BRANCH-B-SIGNATURE" in s7_code and "s7 branch-B 죽음" in s7_code)

    head_after = git(repo, "rev-parse", "HEAD").strip()
    status_after = git(repo, "status", "--porcelain")
    idx_after = git(repo, "diff", "--cached", "--stat")
    disk_after = open(repo + "/calc/core.py").read()
    intact = (head_before == head_after and status_before == status_after
              and idx_before == idx_after and disk_before == disk_after)
    # 작업트리의 실제 core.py는 산 잎(BRANCH-C)이어야 함 — git show가 안 건드림
    worktree_is_live = "BRANCH-C-SIGNATURE" in disk_after
    ok = rolled and intact and worktree_is_live
    print("  M3 죽은가지 git show 롤백=%s, HEAD/status/인덱스/디스크 무손상=%s, "
          "작업트리=산잎(C)=%s" % (rolled, intact, worktree_is_live))
    return ok, "K3", "git show로 죽은가지 코드 롤백 + 워킹트리 무손상"


def m4_dead_tag_survival(repo, index):
    """태그 있으면 --all에 보임 → s7 태그 삭제 → 사라짐 → 되박음 → 부활."""
    s4, s7 = index["s4"], index["s7"]
    all_h = set(git(repo, "log", "--all", "--format=%H").split())
    visible = s4 in all_h and s7 in all_h
    short7 = git(repo, "rev-parse", "--short", s7).strip()
    git(repo, "tag", "-d", "gil/leaf/" + short7)
    after_del = set(git(repo, "log", "--all", "--format=%H").split())
    vanished = s7 not in after_del
    git(repo, "tag", "gil/leaf/" + short7, s7)
    restored = s7 in set(git(repo, "log", "--all", "--format=%H").split())
    ok = visible and vanished and restored
    print("  M4 태그로 죽은가지 보임=%s, 태그삭제하면 --all서 사라짐=%s, 되박으면 부활=%s"
          % (visible, vanished, restored))
    return ok, "K4", "죽은가지 코드 태그(못)로 영구생존 + 음성대조"


def m5_same_file_independent(repo, index):
    """세 가지가 같은 core.py를 다르게 고침 — 세 버전 pairwise 상이 + 각 서명 포함."""
    s4 = git(repo, "show", index["s4"] + ":calc/core.py")
    s7 = git(repo, "show", index["s7"] + ":calc/core.py")
    s10 = git(repo, "show", index["s10"] + ":calc/core.py")
    distinct = (s4 != s7) and (s7 != s10) and (s4 != s10)
    sigs = ("BRANCH-A-SIGNATURE" in s4 and "BRANCH-B-SIGNATURE" in s7
            and "BRANCH-C-SIGNATURE" in s10)
    # 오염 없음: A 버전에 B/C 서명 없고, 등등
    no_cross = ("BRANCH-B" not in s4 and "BRANCH-C" not in s4
                and "BRANCH-A" not in s7 and "BRANCH-C" not in s7
                and "BRANCH-A" not in s10 and "BRANCH-B" not in s10)
    ok = distinct and sigs and no_cross
    print("  M5 같은파일 core.py 세 버전: pairwise 상이=%s, 각 가지 서명 있음=%s, 오염없음=%s"
          % (distinct, sigs, no_cross))
    return ok, "K5", "같은 파일 독립 분기 보존 (디렉토리 복사가 못 하는 것)"


def m6_shared_single_tree(repo, index):
    """공유 한 벌: 물리 core.py 1개인데 그래프에 3버전 공존, 각 git show 접근 가능."""
    import os
    # 작업트리의 core.py 물리 파일은 정확히 하나의 경로
    tracked = git(repo, "ls-files").split("\n")
    core_paths = [p for p in tracked if p == "calc/core.py"]
    physical_one = core_paths == ["calc/core.py"] and os.path.exists(repo + "/calc/core.py")
    # 그래프상 core.py를 만진 커밋(= 여러 버전)
    touched = git(repo, "log", "--all", "--format=%H", "--", "calc/core.py").split()
    many_versions = len(touched) >= 3
    # 세 잎 버전 모두 git show로 접근 가능
    accessible = all("def add" in git(repo, "show", index[s] + ":calc/core.py")
                     for s in ("s4", "s7", "s10"))
    ok = physical_one and many_versions and accessible
    print("  M6 물리 core.py 경로 1개=%s, core.py 손댄 커밋수=%d(≥3), 세 잎버전 접근가능=%s"
          % (physical_one, len(touched), accessible))
    print("     ∴ 사이클 디렉토리 복사 없이 공유 한 벌 위에서 전 버전 생존")
    return ok, "K6", "공유 한 벌(복사 0) 위 전 버전 생존"


def load_index(path):
    idx = {}
    for line in open(path):
        p = line.split()
        if len(p) == 2:
            idx[p[0]] = p[1]
    return idx


def main():
    if len(sys.argv) < 3:
        sys.exit("사용법: measure_code.py <repo> <commit-index.txt>")
    repo, index_path = sys.argv[1], sys.argv[2]
    index = load_index(index_path)
    print("=== C013 측정 — 실제 코드 아티팩트(다중파일 calc/)를 깃 그래프에 실음 ===")
    results = []
    for fn, args in [(m1_incremental_diff, (repo, index)),
                     (m2_one_step_one_commit, (repo,)),
                     (m3_rollback_worktree_intact, (repo, index)),
                     (m4_dead_tag_survival, (repo, index)),
                     (m5_same_file_independent, (repo, index)),
                     (m6_shared_single_tree, (repo, index))]:
        ok, kill, desc = fn(*args)
        print("%s M%d — %s [%s]\n"
              % ("PASS" if ok else "FAIL", len(results) + 1, desc, kill))
        results.append(ok)
    allok = all(results)
    print("=== %s (%d/%d) ===" % ("ALL PASS -> supported" if allok else "실패 있음",
                                  sum(results), len(results)))
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
