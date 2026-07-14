#!/usr/bin/env python3
"""loom/C036 검증 — 번호 원장 규율의 구현 독립 실증.

loom/C016의 tests.py(T1~T3)를 계승하되 **구현을 --gil로 주입**한다.
같은 시나리오를 두 구현(참조 gil.py · Go 바이너리)에 돌려 최종 원장 상태를 대조하기 위함이다.
판정 기준은 2-design.md에 선고정 (T1~T3).

사용:
    python3 ledger-tests.py --gil "/abs/path/to/gil"            [--dump dump-go.txt]
    python3 ledger-tests.py --gil "python3 /abs/path/to/gil.py" [--dump dump-py.txt]

--dump: 실험 종료 후 원장(bare)을 새로 클론해 상태를 정규화 덤프한다.
        두 구현의 덤프가 바이트 단위로 같으면 같은 경합에서 같은 원장에 도달한 것이다.
종료 코드: 전 항목 통과 0, 하나라도 실패 1.
"""
import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

RESULTS = []


def sh(cwd, *cli):
    return subprocess.run(list(cli), cwd=cwd, capture_output=True, text=True)


def git(repo, *cli):
    return sh(repo, "git", *cli)


def check(tid, desc, cond, detail=""):
    RESULTS.append(cond)
    print(f"{'PASS' if tid and cond else 'FAIL'} {tid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gil", required=True, help='구현 호출 명령 (예: "./gil" 또는 "python3 gil.py")')
    ap.add_argument("--dump", help="원장 최종 상태 덤프 경로 (구현 간 대조용)")
    args = ap.parse_args()
    GIL = shlex.split(args.gil)

    def gil(cwd, *cli):
        return sh(cwd, *GIL, *cli)

    tmp = tempfile.mkdtemp(prefix="gil-c036-")
    bare = os.path.join(tmp, "ledger.git")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)

    # 씨앗 저장소: 템플릿 + demo 체인(C001 닫힘) — C016과 동일한 픽스처
    seed = os.path.join(tmp, "seed")
    tpl = os.path.join(seed, "rooms", "experiment", "_template")
    os.makedirs(os.path.join(tpl, "3-verification"))
    for name, body in [("cycle.yaml", "id: C000-slug\nchain: c\nparent: null\nstatus: open\n"
                                      "opened: 2026-01-01\nclosed: null\ntitle: \"\"\n"),
                       ("1-hypothesis.md", "# 1\n"), ("2-design.md", "# 2\n"),
                       ("3-verification/README.md", "# 3\n"), ("4-analysis.md", "# 4\n"),
                       ("5-report.md", "# 5\n")]:
        with open(os.path.join(tpl, name), "w", encoding="utf-8") as f:
            f.write(body)
    demo = os.path.join(seed, "rooms", "experiment", "chains", "demo")
    os.makedirs(os.path.join(demo, "C001-seed"))
    with open(os.path.join(demo, "chain.md"), "w", encoding="utf-8") as f:
        f.write("# Chain: demo\n공유 원장 검증용.\n")
    with open(os.path.join(demo, "C001-seed", "cycle.yaml"), "w", encoding="utf-8") as f:
        f.write("id: C001-seed\nchain: demo\nparent: null\nauthor: fx\nstatus: closed\n"
                "opened: 2026-01-01\nclosed: 2026-01-02\ntitle: \"씨앗\"\n")
    git(seed, "init", "-q", "-b", "main"); git(seed, "config", "user.name", "fx")
    git(seed, "config", "user.email", "fx@t"); git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "seed"); git(seed, "remote", "add", "origin", bare)
    git(seed, "push", "-q", "origin", "main")

    def clone(name):
        d = os.path.join(tmp, name)
        subprocess.run(["git", "clone", "-q", bare, d], check=True)
        git(d, "config", "user.name", name); git(d, "config", "user.email", f"{name}@t")
        return d

    A, B = clone("beingA"), clone("beingB")

    # T2 (무경합 회귀): A가 open --git --push → C002
    rA = gil(A, "open", "demo", "alpha-path", "--title", "A의 폭", "--parent", "C001-seed",
             "--author", "a", "--date", "2026-01-03", "--git", "--push")
    check("T2", "무경합 open --git --push 정상 (A → C002)", rA.returncode == 0
          and os.path.isdir(os.path.join(A, "rooms/experiment/chains/demo/C002-alpha-path")),
          (rA.stderr or "").strip()[-150:])

    # T1 (병렬 경합): B는 fetch 없이 같은 번호로 open → 자동 재번호로 성공해야
    rB = gil(B, "open", "demo", "beta-path", "--title", "B의 폭", "--parent", "C001-seed",
             "--author", "b", "--date", "2026-01-03", "--git", "--push")
    probe = clone("probe")
    y = os.path.join(probe, "rooms/experiment/chains/demo/C003-beta-path/cycle.yaml")
    intact = os.path.isfile(y) and all(k in open(y, encoding="utf-8").read()
                                       for k in ("id: C003-beta-path", 'title: "B의 폭"', "author: b"))
    fsck = gil(probe, "fsck")
    check("T1", "병렬 경합 자동 해소 (B: C002→C003 재번호, 원장 무위반, 내용 무손상)",
          rB.returncode == 0 and "재번호" in (rB.stderr or "")
          and os.path.isdir(os.path.join(probe, "rooms/experiment/chains/demo/C002-alpha-path"))
          and not os.path.isdir(os.path.join(probe, "rooms/experiment/chains/demo/C002-beta-path"))
          and intact and fsck.returncode == 0,
          (rB.stderr or "").strip()[-200:])

    # T3 (해소 불가): C는 chain.md 충돌 커밋을 안고 open --push → 명시적 오류 + rebase abort
    git(A, "pull", "-q", "--rebase", "origin", "main")  # B의 커밋 수용 (C016의 교훈: 없으면 push가 조용히 거절됨)
    sh(A, "bash", "-c", "echo A수정 >> rooms/experiment/chains/demo/chain.md")
    git(A, "commit", "-aqm", "A: chain.md 수정")
    rpush = git(A, "push", "origin", "main")
    assert rpush.returncode == 0, rpush.stderr
    C = clone("beingC")
    git(C, "fetch", "-q", "origin")
    sh(C, "bash", "-c", "git reset -q --hard origin/main~1")  # A의 chain.md 수정 이전으로
    sh(C, "bash", "-c", "echo C수정 >> rooms/experiment/chains/demo/chain.md")
    git(C, "commit", "-aqm", "C: chain.md 충돌 수정")
    rC = gil(C, "open", "demo", "gamma-path", "--title", "C의 폭", "--parent", "C001-seed",
             "--author", "c", "--date", "2026-01-04", "--git", "--push")
    rebase_clean = not os.path.isdir(os.path.join(C, ".git", "rebase-merge"))
    check("T3", "rebase 충돌 시 명시적 오류 + abort (조용한 실패 없음)", rC.returncode != 0
          and ("rebase" in (rC.stderr or "") or "수동" in (rC.stderr or "")) and rebase_clean,
          (rC.stderr or "").strip()[-150:])

    # 상태 덤프: 원장의 진실을 제3의 클론으로 관찰해 정규화 기록한다 (구현 간 대조용).
    if args.dump:
        final = clone("final")
        fdemo = os.path.join(final, "rooms/experiment/chains/demo")
        lines = ["=== 원장 사이클 디렉토리 ==="]
        lines += sorted(e for e in os.listdir(fdemo) if os.path.isdir(os.path.join(fdemo, e)))
        lines.append("")
        for cid in sorted(e for e in os.listdir(fdemo) if os.path.isdir(os.path.join(fdemo, e))):
            lines.append(f"=== {cid}/cycle.yaml ===")
            with open(os.path.join(fdemo, cid, "cycle.yaml"), encoding="utf-8") as f:
                lines.append(f.read().rstrip("\n"))
            lines.append("")
        lines.append("=== 원장 커밋 제목 (오래된 것부터) ===")
        log = git(final, "log", "--reverse", "--format=%s")
        lines += log.stdout.strip().splitlines()
        lines.append("")
        lines.append("=== chain.md ===")
        with open(os.path.join(fdemo, "chain.md"), encoding="utf-8") as f:
            lines.append(f.read().rstrip("\n"))
        with open(args.dump, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\n덤프: {args.dump}")

    shutil.rmtree(tmp, ignore_errors=True)
    total, passed = len(RESULTS), sum(RESULTS)
    print(f"\n결과: {passed}/{total} 통과")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
