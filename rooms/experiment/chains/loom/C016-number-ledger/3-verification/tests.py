#!/usr/bin/env python3
"""loom/C016 검증 — 번호 원장 규율. 판정은 2-design.md에 선고정 (T1~T3)."""
import os
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
GIL = os.path.join(BASE, "gil", "gil.py")
RESULTS = []


def sh(cwd, *cli, env=None):
    return subprocess.run(list(cli), cwd=cwd, capture_output=True, text=True, env=env)


def git(repo, *cli):
    return sh(repo, "git", *cli)


def check(tid, desc, cond, detail=""):
    RESULTS.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {tid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


tmp = tempfile.mkdtemp(prefix="gil-c016-")
bare = os.path.join(tmp, "ledger.git")
subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)

# 씨앗 저장소: 템플릿 + demo 체인(C001 닫힘)
seed = os.path.join(tmp, "seed")
tpl = os.path.join(seed, "rooms", "experiment", "_template")
os.makedirs(os.path.join(tpl, "3-verification"))
for name, body in [("cycle.yaml", "id: C000-slug\nchain: c\nparent: null\nstatus: open\nopened: 2026-01-01\nclosed: null\ntitle: \"\"\n"),
                   ("1-hypothesis.md", "# 1\n"), ("2-design.md", "# 2\n"),
                   ("3-verification/README.md", "# 3\n"), ("4-analysis.md", "# 4\n"), ("5-report.md", "# 5\n")]:
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
rA = sh(A, sys.executable, GIL, "open", "demo", "alpha-path", "--title", "A의 폭",
        "--author", "a", "--date", "2026-01-03", "--git", "--push")
check("T2", "무경합 open --git --push 정상 (A → C002)", rA.returncode == 0
      and os.path.isdir(os.path.join(A, "rooms/experiment/chains/demo/C002-alpha-path")),
      (rA.stderr or "").strip()[-150:])

# T1 (병렬 경합): B는 fetch 없이 같은 번호로 open → 자동 재번호로 성공해야
rB = sh(B, sys.executable, GIL, "open", "demo", "beta-path", "--title", "B의 폭",
        "--author", "b", "--date", "2026-01-03", "--git", "--push")
probe = clone("probe")
y = os.path.join(probe, "rooms/experiment/chains/demo/C003-beta-path/cycle.yaml")
intact = os.path.isfile(y) and all(k in open(y, encoding="utf-8").read()
                                   for k in ("id: C003-beta-path", 'title: "B의 폭"', "author: b"))
fsck = sh(probe, sys.executable, GIL, "fsck")
check("T1", "병렬 경합 자동 해소 (B: C002→C003 재번호, 원장 무위반, 내용 무손상)",
      rB.returncode == 0 and "재번호" in (rB.stderr or "")
      and os.path.isdir(os.path.join(probe, "rooms/experiment/chains/demo/C002-alpha-path"))
      and intact and fsck.returncode == 0,
      (rB.stderr or "").strip()[-200:])

# T3 (해소 불가): C는 chain.md 충돌 커밋을 안고 open --push → 명시적 오류 + rebase abort
git(A, "pull", "-q", "--rebase", "origin", "main")  # B의 커밋 수용 (없으면 push가 조용히 거절됨 — 1차 실행의 교훈)
sh(A, "bash", "-c", "echo A수정 >> rooms/experiment/chains/demo/chain.md")
git(A, "commit", "-aqm", "A: chain.md 수정")
rpush = git(A, "push", "origin", "main")
assert rpush.returncode == 0, rpush.stderr
C = clone("beingC")
git(C, "fetch", "-q", "origin")  # 최신이지만…
sh(C, "bash", "-c", "git reset -q --hard origin/main~1")  # A의 chain.md 수정 이전으로
sh(C, "bash", "-c", "echo C수정 >> rooms/experiment/chains/demo/chain.md")
git(C, "commit", "-aqm", "C: chain.md 충돌 수정")
rC = sh(C, sys.executable, GIL, "open", "demo", "gamma-path", "--title", "C의 폭",
        "--author", "c", "--date", "2026-01-04", "--git", "--push")
rebase_clean = not os.path.isdir(os.path.join(C, ".git", "rebase-merge"))
check("T3", "rebase 충돌 시 명시적 오류 + abort (조용한 실패 없음)", rC.returncode != 0
      and ("rebase" in (rC.stderr or "") or "수동" in (rC.stderr or "")) and rebase_clean,
      (rC.stderr or "").strip()[-150:])

shutil.rmtree(tmp, ignore_errors=True)
total, passed = len(RESULTS), sum(RESULTS)
print(f"\n결과: {passed}/{total} 통과")
sys.exit(0 if passed == total else 1)
