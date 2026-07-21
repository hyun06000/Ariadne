#!/usr/bin/env python3
"""C024 measure — 재번호 provenance 정밀화의 4측정.

M1 매핑 수집 · M2 커밋 회수(정합) · M3 도출 감소(20→16) · M4 오염 없음.
격리 없이 우리 원장에서 조회만(읽기 전용).
"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import full_ledger_migrate as FLM
import renumber_map as RM
import derive_precise as DP

EXPECTED_RENUMBER = {
    "loom/C083-warp-selfupdate": 82,
    "loom/C106-go-deploy-panel-render": 105,
    "v3-build/C004-v3-viewer-step-tree": 3,
    "v3-build/C007-viewer-node-body-interaction": 6,
}


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    cycles = FLM.discover_cycles(repo)
    failed_dirs = [c["dir"] for c in cycles
                   if not FLM.cycle_step_commits(repo, c.get("chain", ""), c.get("id", ""))]
    n_failed_before = len(failed_dirs)
    rmap = RM.build_map(repo, failed_dirs)
    rec = DP.measure_recovery(repo)

    results = []

    # M1: 매핑 수집 — 기대 4건 정확
    m1 = (rmap == EXPECTED_RENUMBER)
    results.append(("M1 매핑 수집",
                    "재번호 매핑 %d건 == 기대 %d건 %s"
                    % (len(rmap), len(EXPECTED_RENUMBER), "정확" if m1 else "불일치"), m1))

    # M2: 커밋 회수 — 4건 모두 회수, used_id가 slug 포함 옛 id(오염 없음)
    recovered = {"%s/%s" % (c, i): (old, n) for c, i, old, n in rec["recovered"]}
    m2 = (len(recovered) == 4
          and all("-" in old for old, n in recovered.values())  # slug 포함 = 정확 매칭
          and all(n >= 4 for old, n in recovered.values()))     # 각 4스텝 이상
    results.append(("M2 커밋 회수 (정합)",
                    "회수 %d건, 전부 slug 포함 옛 id·4스텝↑ (오염 0)" % len(recovered), m2))

    # M3: 도출 감소 — 20 → 16 (회수 4)
    n_after = len(rec["still_failed"])
    m3 = (n_failed_before == 20 and len(rec["recovered"]) == 4 and n_after == 16)
    results.append(("M3 도출 감소",
                    "도출실패 %d→%d (회수 %d)" % (n_failed_before, n_after, len(rec["recovered"])), m3))

    # M4: 오염 없음 — 잔여 16이 전부 초기 관습(genesis/loom C001~C012/tapestry), 재번호 아님
    still = set("%s/%s" % (c, i) for c, i in rec["still_failed"])
    early_ok = all(
        s.startswith("genesis/") or s.startswith("tapestry/")
        or (s.startswith("loom/") and int(s.split("/C")[1][:3]) <= 12)
        for s in still)
    m4 = (len(still) == 16 and early_ok and not (set(EXPECTED_RENUMBER) & still))
    results.append(("M4 오염 없음",
                    "잔여 %d 전부 초기 관습(재번호 아님), 재번호 4건 안 남음" % len(still), m4))

    print("=== C024 measure — 재번호 provenance 정밀화 ===\n")
    allpass = True
    for name, detail, ok in results:
        print("[%s] %s\n      %s" % ("PASS" if ok else "FAIL", name, detail))
        allpass = allpass and ok
    print("\n=== %s ===" % ("ALL PASS → supported" if allpass else "일부 FAIL → 조사"))
    sys.exit(0 if allpass else 1)


if __name__ == "__main__":
    main()
