#!/usr/bin/env python3
"""loom/C004 검증 드라이버 — fixtures/expected-behavior.md 의 T1~T8을 실행한다.

각 테스트는 독립된 샌드박스 사본에서 실행된다. 깃이 필요한 테스트는 사본을
깃 저장소로 초기화(init + 전체 커밋)한 뒤 진행한다.
"""
import os
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
ARI = os.path.join(BASE, "ari", "ari.py")
SANDBOX = os.path.join(BASE, "fixtures", "sandbox")
RESULTS = []
_TMPDIRS = []
CY1 = "rooms/experiment/chains/weave/C001-first-step"
TAG1 = "cycle/weave/C001-first-step"


def sh(cwd, *cli):
    return subprocess.run(list(cli), cwd=cwd, capture_output=True, text=True)


def git(repo, *cli):
    return sh(repo, "git", *cli)


def ari(cwd, *cli):
    return sh(cwd, sys.executable, ARI, *cli)


def fresh_sandbox(with_git=True):
    tmp = tempfile.mkdtemp(prefix="ari-c004-")
    _TMPDIRS.append(tmp)
    repo = os.path.join(tmp, "repo")
    shutil.copytree(SANDBOX, repo)
    if with_git:
        git(repo, "init", "-q")
        git(repo, "config", "user.name", "fixture")
        git(repo, "config", "user.email", "fixture@test")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "init")
    return repo


def setup_ready_to_close(repo):
    """weave/C001을 열고 실제 보고서까지 작성해 close 직전 상태로 만든다."""
    r = ari(repo, "open", "weave", "first-step", "--title", "첫 걸음", "--new-chain",
            "--date", "2026-07-14", "--author", "fixture")
    assert r.returncode == 0, r.stderr
    with open(os.path.join(repo, CY1, "5-report.md"), "w", encoding="utf-8") as f:
        f.write("# 5. 결과 보고\n\n## 요약\n\n가설 채택. 검증용 실제 보고서.\n")


def check(tid, desc, cond, detail=""):
    RESULTS.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {tid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


def read(repo, rel):
    with open(os.path.join(repo, rel), encoding="utf-8") as f:
        return f.read()


# T1: close --git → 커밋(사이클 파일만) + 주석 태그 + fsck OK
repo = fresh_sandbox(); setup_ready_to_close(repo)
r = ari(repo, "close", "weave", "C001-first-step", "--date", "2026-07-15", "--git")
committed = git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
tag_ok = git(repo, "tag", "-l", TAG1).stdout.strip() == TAG1
check("T1", "close --git: 사이클만 담은 커밋 + 주석 태그", r.returncode == 0
      and "status: closed" in read(repo, f"{CY1}/cycle.yaml")
      and committed and all(p.startswith(CY1) for p in committed)
      and tag_ok and ari(repo, "fsck").returncode == 0, r.stderr.strip())

# T2: 무변조 verify → OK (같은 저장소 이어서)
r = ari(repo, "verify")
check("T2", "무변조 verify OK", r.returncode == 0 and "변조 0건" in r.stdout, r.stdout.strip())

# T3: 수정 + 추가 변조 → verify가 둘 다 탐지 (같은 저장소 이어서)
with open(os.path.join(repo, CY1, "5-report.md"), "a", encoding="utf-8") as f:
    f.write("\n(몰래 고친 줄)\n")
with open(os.path.join(repo, CY1, "smuggled.txt"), "w", encoding="utf-8") as f:
    f.write("몰래 추가한 파일\n")
r = ari(repo, "verify")
check("T3", "변조 탐지: 수정·추가 둘 다", r.returncode != 0
      and f"{CY1}/5-report.md" in r.stdout and f"{CY1}/smuggled.txt" in r.stdout, r.stdout.strip())

# T4: 깃 없는 샌드박스에서 --git 없는 close → 하위 호환
repo = fresh_sandbox(with_git=False); setup_ready_to_close(repo)
r = ari(repo, "close", "weave", "C001-first-step", "--date", "2026-07-15")
check("T4", "--git 없는 close는 깃 없이도 동작", r.returncode == 0
      and "status: closed" in read(repo, f"{CY1}/cycle.yaml"), r.stderr.strip())

# T5: 태그 선점 → close --git 거부 + cycle.yaml 무변화
repo = fresh_sandbox(); setup_ready_to_close(repo)
git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "pre")
git(repo, "tag", TAG1)
before = read(repo, f"{CY1}/cycle.yaml")
r = ari(repo, "close", "weave", "C001-first-step", "--date", "2026-07-15", "--git")
check("T5", "태그 선점 시 거부 + 무변화", r.returncode != 0
      and read(repo, f"{CY1}/cycle.yaml") == before and "status: open" in before, r.stderr.strip())

# T6: 깃 저장소 아님 → close --git 거부 + cycle.yaml 무변화
repo = fresh_sandbox(with_git=False); setup_ready_to_close(repo)
before = read(repo, f"{CY1}/cycle.yaml")
r = ari(repo, "close", "weave", "C001-first-step", "--date", "2026-07-15", "--git")
check("T6", "깃 저장소 아니면 --git 거부 + 무변화", r.returncode != 0
      and read(repo, f"{CY1}/cycle.yaml") == before, r.stderr.strip())

# T7: 경로 격리 — 무관한 변경은 커밋되지 않는다
repo = fresh_sandbox(); setup_ready_to_close(repo)
chainmd = "rooms/experiment/chains/seed/chain.md"
with open(os.path.join(repo, chainmd), "a", encoding="utf-8") as f:
    f.write("\n(무관한 수정)\n")
with open(os.path.join(repo, "stray.txt"), "w", encoding="utf-8") as f:
    f.write("무관한 미추적 파일\n")
r = ari(repo, "close", "weave", "C001-first-step", "--date", "2026-07-15", "--git")
committed = git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
status = git(repo, "status", "--porcelain").stdout
check("T7", "무관한 변경 미오염 (사이클 경로만 커밋)", r.returncode == 0
      and committed and all(p.startswith(CY1) for p in committed)
      and f" M {chainmd}" in status and "?? stray.txt" in status, status)

# T8: 태그 없는 닫힌 사이클 → verify 경고 + exit 0
repo = fresh_sandbox()  # seed/C001-origin: closed, 태그 없음
r = ari(repo, "verify")
check("T8", "태그 없는 닫힌 사이클은 경고 + exit 0", r.returncode == 0
      and "seed/C001-origin" in r.stderr and "백필" in r.stderr, r.stderr.strip())

for d in _TMPDIRS:
    shutil.rmtree(d, ignore_errors=True)
total, passed = len(RESULTS), sum(RESULTS)
print(f"\n결과: {passed}/{total} 통과")
sys.exit(0 if passed == total else 1)
