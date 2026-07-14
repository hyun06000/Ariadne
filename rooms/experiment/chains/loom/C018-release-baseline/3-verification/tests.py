#!/usr/bin/env python3
"""loom/C018 검증 — 승격 규칙 기준 교정 (T1~T3). 판정은 2-design.md에 선고정."""
import os
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
GIL = os.path.join(BASE, "gil", "gil.py")
LOOM = os.path.abspath(os.path.join(BASE, "..", ".."))
C3_SANDBOX = os.path.join(LOOM, "C003-open-close-porcelain", "3-verification", "fixtures", "sandbox")
RESULTS = []
_TMP = []


def sh(cwd, *cli):
    return subprocess.run(list(cli), cwd=cwd, capture_output=True, text=True)


def git(repo, *cli):
    return sh(repo, "git", *cli)


def check(tid, desc, cond, detail=""):
    RESULTS.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {tid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


def fresh(tool_at_tag, tool_now, conf_at_tag="# CONF v1\n", conf_now=None, versions_in_md=("0.1.1", "0.2.0")):
    """태그 v0.1.0 시점의 패키지 상태와 현재 상태를 구분해 구성한다."""
    tmp = tempfile.mkdtemp(prefix="gil-c018-")
    _TMP.append(tmp)
    repo = os.path.join(tmp, "repo")
    shutil.copytree(C3_SANDBOX, repo)
    pkg = os.path.join(repo, "rooms", "deployment", "ariadne-spec")
    os.makedirs(pkg)
    with open(os.path.join(pkg, "gil.py"), "w", encoding="utf-8") as f:
        f.write(tool_at_tag)
    with open(os.path.join(pkg, "conformance.py"), "w", encoding="utf-8") as f:
        f.write(conf_at_tag)
    with open(os.path.join(pkg, "RELEASE.md"), "w", encoding="utf-8") as f:
        f.write("# R\n\n" + "".join(f"## v{v}\n\n서술.\n\n" for v in versions_in_md) + "## v0.1.0\n\n첫.\n")
    shutil.copytree(os.path.join(repo, "rooms", "experiment", "_template"), os.path.join(pkg, "template"))
    with open(os.path.join(repo, "rooms", "deployment", "CHANGELOG.md"), "w", encoding="utf-8") as f:
        f.write("# C\n\n## [Unreleased]\n\n## [0.1.0] — 2026-01-01\n\n- x\n")
    git(repo, "init", "-q", "-b", "main"); git(repo, "config", "user.name", "fx")
    git(repo, "config", "user.email", "fx@t"); git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "release state"); git(repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")
    dirty = False
    if tool_now is not None and tool_now != tool_at_tag:
        with open(os.path.join(pkg, "gil.py"), "w", encoding="utf-8") as f:
            f.write(tool_now)
        dirty = True
    if conf_now is not None and conf_now != conf_at_tag:
        with open(os.path.join(pkg, "conformance.py"), "w", encoding="utf-8") as f:
            f.write(conf_now)
        dirty = True
    if dirty:
        git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "post-tag change")
    return repo


RUNNING = open(GIL, encoding="utf-8").read()

# T1: 패키지 gil.py == 실행 도구(직접 실행과 동등) but 태그 blob과 다름 → 패치 거부, 마이너 성공
repo = fresh(tool_at_tag="# OLD TOOL\n", tool_now=RUNNING)
r_patch = sh(repo, sys.executable, GIL, "release", "0.1.1", "--notes", "x", "--date", "2026-07-14")
r_minor = sh(repo, sys.executable, GIL, "release", "0.2.0", "--notes", "x", "--date", "2026-07-14")
log = open(os.path.join(repo, "rooms/deployment/CHANGELOG.md"), encoding="utf-8").read()
check("T1", "직접 실행 시나리오: 태그 기준으로 변경 감지 (패치 거부·마이너 성공)",
      r_patch.returncode != 0 and "태그" in (r_patch.stderr or "")
      and r_minor.returncode == 0 and "도구 변경: gil" in log,
      f"patch rc={r_patch.returncode}, minor rc={r_minor.returncode}: {(r_minor.stderr or '').strip()[-120:]}")

# T2: 판정기만 변경 → 패치 거부, 마이너 성공
repo = fresh(tool_at_tag=RUNNING, tool_now=None, conf_now="# CONF v2 changed\n")
r_patch = sh(repo, sys.executable, GIL, "release", "0.1.1", "--notes", "x", "--date", "2026-07-14")
r_minor = sh(repo, sys.executable, GIL, "release", "0.2.0", "--notes", "x", "--date", "2026-07-14")
log = open(os.path.join(repo, "rooms/deployment/CHANGELOG.md"), encoding="utf-8").read()
check("T2", "판정기(conformance)도 도구다 (패치 거부·마이너 성공)",
      r_patch.returncode != 0 and "conformance" in (r_patch.stderr or "")
      and r_minor.returncode == 0 and "도구 변경: conformance" in log,
      f"patch rc={r_patch.returncode}: {(r_patch.stderr or '').strip()[-120:]}")

# T3: 문서-only → 패치 성공 + 분류 정확
repo = fresh(tool_at_tag=RUNNING, tool_now=None)
with open(os.path.join(repo, "rooms/deployment/ariadne-spec/RELEASE.md"), "a", encoding="utf-8") as f:
    f.write("\n문서만 고침.\n")
git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "docs")
r = sh(repo, sys.executable, GIL, "release", "0.1.1", "--notes", "문서", "--date", "2026-07-14")
log = open(os.path.join(repo, "rooms/deployment/CHANGELOG.md"), encoding="utf-8").read()
check("T3", "문서-only 패치 허용 + '문서 릴리스' 분류", r.returncode == 0
      and "도구 변경: 없음 (문서 릴리스)" in log, (r.stderr or "").strip()[-150:])

for d in _TMP:
    shutil.rmtree(d, ignore_errors=True)
total, passed = len(RESULTS), sum(RESULTS)
print(f"\n결과: {passed}/{total} 통과")
sys.exit(0 if passed == total else 1)
