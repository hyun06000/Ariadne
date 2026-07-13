#!/usr/bin/env python3
"""loom/C009 검증 — 패치 릴리스 경로 (도구 미변경 상태). 판정은 2-design.md에 선고정."""
import os
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
LOOM = os.path.abspath(os.path.join(BASE, "..", ".."))
ARI = os.path.join(LOOM, "C008-release-porcelain", "3-verification", "ari", "ari.py")
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


def fresh_tool_unchanged(version_in_md):
    """패키지 ari.py = 실행 도구 사본 → '도구 미변경' 상태의 샌드박스."""
    tmp = tempfile.mkdtemp(prefix="ari-c009-")
    _TMP.append(tmp)
    repo = os.path.join(tmp, "repo")
    shutil.copytree(C3_SANDBOX, repo)
    pkg = os.path.join(repo, "rooms", "deployment", "ariadne-spec")
    os.makedirs(pkg)
    shutil.copyfile(ARI, os.path.join(pkg, "ari.py"))
    with open(os.path.join(pkg, "RELEASE.md"), "w", encoding="utf-8") as f:
        f.write(f"# Release\n\n## v{version_in_md}\n\n검증용 서술.\n\n## v0.1.0\n\n첫 릴리스.\n")
    shutil.copytree(os.path.join(repo, "rooms", "experiment", "_template"), os.path.join(pkg, "template"))
    with open(os.path.join(repo, "rooms", "deployment", "CHANGELOG.md"), "w", encoding="utf-8") as f:
        f.write("# Changelog\n\n## [Unreleased]\n\n## [0.1.0] — 2026-01-01\n\n- 첫 릴리스\n")
    git(repo, "init", "-q"); git(repo, "config", "user.name", "fixture")
    git(repo, "config", "user.email", "fixture@test")
    git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "init")
    git(repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")
    return repo


# T1: 도구 미변경 + 패치 승격 → 성공, "문서 릴리스" 기록
repo = fresh_tool_unchanged("0.1.1")
r = sh(repo, sys.executable, ARI, "release", "0.1.1", "--notes", "문서 개정", "--date", "2026-07-14")
log = open(os.path.join(repo, "rooms", "deployment", "CHANGELOG.md"), encoding="utf-8").read()
check("T1", "도구 미변경 패치 릴리스 성공 + 문서 릴리스 구분", r.returncode == 0
      and "## [0.1.1] — 2026-07-14" in log and "도구 동기화: 없음 (문서 릴리스)" in log
      and git(repo, "tag", "-l", "v0.1.1").stdout.strip() == "v0.1.1",
      (r.stderr or "").strip()[-150:])

# T1b: 같은 조건에서 마이너 승격도 허용 (규칙은 '이상'이다)
repo2 = fresh_tool_unchanged("0.2.0")
r2 = sh(repo2, sys.executable, ARI, "release", "0.2.0", "--notes", "문서 개정", "--date", "2026-07-14")
check("T1b", "도구 미변경 상태에서 마이너 승격도 허용", r2.returncode == 0
      and git(repo2, "tag", "-l", "v0.2.0").stdout.strip() == "v0.2.0", (r2.stderr or "").strip()[-150:])

for d in _TMP:
    shutil.rmtree(d, ignore_errors=True)
total, passed = len(RESULTS), sum(RESULTS)
print(f"\n결과: {passed}/{total} 통과")
sys.exit(0 if passed == total else 1)
