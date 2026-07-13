#!/usr/bin/env python3
"""loom/C003 검증 드라이버 — fixtures/expected-behavior.md 의 T1~T11을 실행한다.

각 테스트는 독립된 샌드박스 사본에서 실행된다. 거부 케이스는 exit ≠ 0 에 더해
실행 전후 저장소 스냅샷(모든 파일의 해시)이 동일함(무변화)까지 확인한다.
표준 라이브러리 전용.
"""
import hashlib
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


def fresh_sandbox():
    tmp = tempfile.mkdtemp(prefix="ari-c003-")
    _TMPDIRS.append(tmp)
    dst = os.path.join(tmp, "repo")
    shutil.copytree(SANDBOX, dst)
    return dst


def ari(cwd, *cli):
    return subprocess.run([sys.executable, ARI, *cli], cwd=cwd, capture_output=True, text=True)


def snapshot(repo):
    snap = {}
    for root, _, files in os.walk(repo):
        for name in files:
            path = os.path.join(root, name)
            with open(path, "rb") as f:
                snap[os.path.relpath(path, repo)] = hashlib.sha256(f.read()).hexdigest()
    return snap


def check(tid, desc, cond, detail=""):
    RESULTS.append(cond)
    mark = "PASS" if cond else "FAIL"
    print(f"{mark} {tid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


def read(repo, rel):
    with open(os.path.join(repo, rel), encoding="utf-8") as f:
        return f.read()


def setup_weave(repo):
    """T1과 동일한 명령으로 전제 상태(weave 체인 + C001)를 만든다."""
    r = ari(repo, "open", "weave", "first-step", "--title", "첫 걸음", "--new-chain",
            "--date", "2026-07-14", "--author", "fixture")
    assert r.returncode == 0, f"전제 셋업 실패: {r.stderr}"


CY1 = "rooms/experiment/chains/weave/C001-first-step"

# ---- 정상 계열 ----

# T1: 새 체인 + 첫 사이클
repo = fresh_sandbox()
r = ari(repo, "open", "weave", "first-step", "--title", "첫 걸음", "--new-chain",
        "--date", "2026-07-14", "--author", "fixture")
yaml1 = read(repo, f"{CY1}/cycle.yaml") if r.returncode == 0 else ""
check("T1", "새 체인에 v0.2 준수 사이클 생성", r.returncode == 0
      and os.path.isdir(os.path.join(repo, CY1))
      and "id: C001-first-step" in yaml1 and "parent: null" in yaml1
      and "status: open" in yaml1 and "opened: 2026-07-14" in yaml1
      and os.path.isfile(os.path.join(repo, CY1, "5-report.md"))
      and os.path.isfile(os.path.join(repo, "rooms/experiment/chains/weave/chain.md"))
      and ari(repo, "fsck").returncode == 0, r.stderr.strip())

# T2: 번호 자동 증가 + parent 기록
repo = fresh_sandbox(); setup_weave(repo)
r = ari(repo, "open", "weave", "second-step", "--title", "둘째 걸음",
        "--parent", "C001-first-step", "--date", "2026-07-14", "--author", "fixture")
y = read(repo, "rooms/experiment/chains/weave/C002-second-step/cycle.yaml") if r.returncode == 0 else ""
check("T2", "번호 자동 증가(C002) + parent 기록", r.returncode == 0
      and "id: C002-second-step" in y and "parent: C001-first-step" in y
      and ari(repo, "fsck").returncode == 0, r.stderr.strip())

# T3: 체인 간 lineage
repo = fresh_sandbox(); setup_weave(repo)
r = ari(repo, "open", "weave", "with-roots", "--title", "뿌리 있는 걸음",
        "--lineage", "seed/C001-origin", "--date", "2026-07-14", "--author", "fixture")
y = read(repo, "rooms/experiment/chains/weave/C002-with-roots/cycle.yaml") if r.returncode == 0 else ""
check("T3", "lineage 전역 참조 해소·기록", r.returncode == 0
      and "lineage: [seed/C001-origin]" in y and ari(repo, "fsck").returncode == 0, r.stderr.strip())

# T4: 실제 보고서 작성 후 close
repo = fresh_sandbox(); setup_weave(repo)
with open(os.path.join(repo, CY1, "5-report.md"), "w", encoding="utf-8") as f:
    f.write("# 5. 결과 보고\n\n## 요약\n\n가설 채택. 검증용 실제 보고서.\n\n## 교훈\n\n1. 테스트는 실제 내용으로.\n")
r = ari(repo, "close", "weave", "C001-first-step", "--date", "2026-07-15")
y = read(repo, f"{CY1}/cycle.yaml")
check("T4", "close: 상태 전이 + 일자 기록 + 나머지 보존", r.returncode == 0
      and "status: closed" in y and "closed: 2026-07-15" in y
      and "id: C001-first-step" in y and "opened: 2026-07-14" in y
      and ari(repo, "fsck").returncode == 0, r.stderr.strip())

# ---- 거부 계열 (exit ≠ 0 + 저장소 무변화) ----

def reject(tid, desc, repo, *cli):
    before = snapshot(repo)
    r = ari(repo, *cli)
    check(tid, desc, r.returncode != 0 and snapshot(repo) == before,
          f"rc={r.returncode}, 변화={snapshot(repo) != before}")

repo = fresh_sandbox(); setup_weave(repo)
reject("T5", "마침표 슬러그 거부 (C002의 그 실수)", repo,
       "open", "weave", "v0.2", "--title", "x", "--date", "2026-07-14")
reject("T6", "유령 parent 거부", repo,
       "open", "weave", "x", "--parent", "C099-nope", "--date", "2026-07-14")
reject("T7", "유령 lineage 거부", repo,
       "open", "weave", "y", "--lineage", "nowhere/C001-x", "--date", "2026-07-14")
reject("T8", "없는 체인 거부 (--new-chain 없이)", repo,
       "open", "ghost-chain", "z", "--title", "x", "--date", "2026-07-14")
reject("T11", "같은 체인 lineage 거부", repo,
       "open", "weave", "w", "--lineage", "weave/C001-first-step", "--date", "2026-07-14")

repo = fresh_sandbox(); setup_weave(repo)
r = ari(repo, "open", "weave", "second-step", "--title", "둘째", "--parent", "C001-first-step",
        "--date", "2026-07-14", "--author", "fixture")
assert r.returncode == 0
reject("T9", "보고서가 템플릿 그대로인 사이클 close 거부", repo,
       "close", "weave", "C002-second-step", "--date", "2026-07-15")

repo = fresh_sandbox()
reject("T10", "이미 닫힌 사이클 close 거부", repo,
       "close", "seed", "C001-origin", "--date", "2026-07-15")

# ---- 요약 ----
for d in _TMPDIRS:
    shutil.rmtree(d, ignore_errors=True)
total, passed = len(RESULTS), sum(RESULTS)
print(f"\n결과: {passed}/{total} 통과")
sys.exit(0 if passed == total else 1)
