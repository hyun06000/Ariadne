#!/usr/bin/env python3
"""C024 derive_precise — 재번호 매핑으로 도출기 정밀화.

기존 cycle_step_commits가 새 id로 커밋을 못 찾으면, 재번호 매핑에서 옛 id를 조회해
옛 id로 재시도한다. 회수한 커밋으로 v3 지문을 도출(C019 규칙 그대로).
"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import full_ledger_migrate as FLM
import derive_fingerprint as DF
import renumber_map as RM


def precise_step_commits(repo, chain, cid, rmap):
    """새 id 실패 시 재번호 매핑의 옛 id로 재시도."""
    commits = FLM.cycle_step_commits(repo, chain, cid)
    if commits:
        return commits, cid  # 정상 도출
    key = "%s/%s" % (chain, cid)
    if key in rmap:
        old_num = rmap[key]
        # ⭐ 재번호는 번호만 바꾸고 slug은 유지 → 옛 full id = C<old_num>-<현재 slug>.
        #    번호만으로 매칭하면 같은 번호의 다른 사이클을 긁는 오염 발생(C003 두 사이클).
        slug = cid.split("-", 1)[1] if "-" in cid else ""
        old_id = "C%03d-%s" % (old_num, slug)
        return FLM.cycle_step_commits(repo, chain, old_id), old_id
    return [], cid


def measure_recovery(repo):
    """도출실패 사이클에 정밀화 적용 → 회수 통계."""
    cycles = FLM.discover_cycles(repo)
    failed_dirs = [c["dir"] for c in cycles
                   if not FLM.cycle_step_commits(repo, c.get("chain", ""), c.get("id", ""))]
    rmap = RM.build_map(repo, failed_dirs)
    recovered, still_failed = [], []
    for c in cycles:
        chain, cid = c.get("chain", ""), c.get("id", "")
        base = FLM.cycle_step_commits(repo, chain, cid)
        if base:
            continue  # 원래 성공
        commits, used_id = precise_step_commits(repo, chain, cid, rmap)
        if commits:
            recovered.append((chain, cid, used_id, len(commits)))
        else:
            still_failed.append((chain, cid))
    return {"recovered": recovered, "still_failed": still_failed, "rmap": rmap}


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    r = measure_recovery(repo)
    print("=== 정밀화 회수 결과 ===")
    print("회수 %d건:" % len(r["recovered"]))
    for chain, cid, old, n in sorted(r["recovered"]):
        print("  %s/%s ← %s (%d 스텝 커밋)" % (chain, cid, old, n))
    print("여전히 도출실패 %d건:" % len(r["still_failed"]))
    for chain, cid in sorted(r["still_failed"]):
        print("  %s/%s" % (chain, cid))
