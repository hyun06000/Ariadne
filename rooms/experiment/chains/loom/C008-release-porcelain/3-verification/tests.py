#!/usr/bin/env python3
"""loom/C008 검증 드라이버 — fixtures/expected-release-tool.md 의 T1~T7을 실행한다.

샌드박스: 체인(seed) + 배포 패키지(구버전 스텁 ari.py → 항상 '도구 변경' 상태) + 태그 v0.1.0.
거부 케이스는 파일 스냅샷·커밋 수·태그 목록의 무변화까지 확인한다.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
ARI = os.path.join(BASE, "ari", "ari.py")
C3_SANDBOX = os.path.join(os.path.dirname(BASE), "..", "C003-open-close-porcelain",
                          "3-verification", "fixtures", "sandbox")
RESULTS = []
_TMP = []


def sh(cwd, *cli, inp=None):
    return subprocess.run(list(cli), cwd=cwd, capture_output=True, text=True, input=inp)


def git(repo, *cli):
    return sh(repo, "git", *cli)


def ari(cwd, *cli):
    return sh(cwd, sys.executable, ARI, *cli)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def snapshot(repo):
    files = {}
    for root, dirs, names in os.walk(repo):
        if ".git" in dirs:
            dirs.remove(".git")
        for n in names:
            p = os.path.join(root, n)
            files[os.path.relpath(p, repo)] = sha(p)
    ncommits = git(repo, "rev-list", "--count", "HEAD").stdout.strip()
    tags = git(repo, "tag", "-l").stdout
    return (files, ncommits, tags)


def check(tid, desc, cond, detail=""):
    RESULTS.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {tid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


def fresh(release_version_in_md="0.2.0"):
    tmp = tempfile.mkdtemp(prefix="ari-c008-")
    _TMP.append(tmp)
    repo = os.path.join(tmp, "repo")
    shutil.copytree(C3_SANDBOX, repo)
    pkg = os.path.join(repo, "rooms", "deployment", "ariadne-spec")
    os.makedirs(pkg)
    with open(os.path.join(pkg, "ari.py"), "w", encoding="utf-8") as f:
        f.write("# OLD TOOL STUB (v0.1.0)\n")
    with open(os.path.join(pkg, "RELEASE.md"), "w", encoding="utf-8") as f:
        f.write(f"# Release\n\n## v{release_version_in_md}\n\n검증용 릴리스 서술.\n\n## v0.1.0\n\n첫 릴리스.\n"
                if release_version_in_md else "# Release\n\n## v0.1.0\n\n첫 릴리스.\n")
    shutil.copytree(os.path.join(repo, "rooms", "experiment", "_template"),
                    os.path.join(pkg, "template"))
    # 템플릿 사본을 일부러 낡게 만든다 (동기화 검증용)
    with open(os.path.join(pkg, "template", "5-report.md"), "a", encoding="utf-8") as f:
        f.write("\n<!-- stale -->\n")
    with open(os.path.join(repo, "rooms", "deployment", "CHANGELOG.md"), "w", encoding="utf-8") as f:
        f.write("# Changelog\n\n## [Unreleased]\n\n## [0.1.0] — 2026-01-01\n\n- 첫 릴리스\n")
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "fixture")
    git(repo, "config", "user.email", "fixture@test")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")
    return repo


def reject(tid, desc, repo, *cli):
    before = snapshot(repo)
    r = ari(repo, *cli)
    after = snapshot(repo)
    check(tid, desc, r.returncode != 0 and before == after,
          f"rc={r.returncode}, 변화={before != after}: {(r.stderr or '').strip()[-120:]}")


# T1: 정상 릴리스 (도구 변경 + 마이너 승격) + 경로 격리(T6 통합)
repo = fresh()
with open(os.path.join(repo, "rooms", "experiment", "chains", "seed", "chain.md"), "a", encoding="utf-8") as f:
    f.write("\n(무관한 수정)\n")
r = ari(repo, "release", "0.2.0", "--notes", "검증 릴리스", "--date", "2026-07-14")
pkg = os.path.join(repo, "rooms", "deployment", "ariadne-spec")
committed = git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
log = open(os.path.join(repo, "rooms", "deployment", "CHANGELOG.md"), encoding="utf-8").read()
tpl_synced = "stale" not in open(os.path.join(pkg, "template", "5-report.md"), encoding="utf-8").read()
status = git(repo, "status", "--porcelain").stdout
check("T1", "정상 릴리스: 동기화·CHANGELOG·태그·격리", r.returncode == 0
      and sha(os.path.join(pkg, "ari.py")) == sha(ARI)
      and tpl_synced
      and "## [0.2.0] — 2026-07-14" in log and log.index("[Unreleased]") < log.index("[0.2.0]")
      and committed and all(p.startswith("rooms/deployment/") for p in committed)
      and git(repo, "tag", "-l", "v0.2.0").stdout.strip() == "v0.2.0"
      and " M rooms/experiment/chains/seed/chain.md" in status,
      (r.stderr or "").strip()[-150:])

# T2: 도구 변경 + 패치 승격 → 거부
reject("T2", "패치 승격 거부 (도구 변경 시 마이너 이상)", fresh("0.1.1"),
       "release", "0.1.1", "--notes", "x", "--date", "2026-07-14")

# T3: 비단조 / 비SemVer → 거부
repo3 = fresh("0.1.0")
reject("T3a", "비단조 버전 거부 (0.1.0 ≤ v0.1.0)", repo3,
       "release", "0.1.0", "--notes", "x", "--date", "2026-07-14")
reject("T3b", "비SemVer 거부", repo3,
       "release", "abc", "--notes", "x", "--date", "2026-07-14")

# T4: RELEASE.md에 버전 서술 없음 → 거부
reject("T4", "문서 강제: RELEASE.md에 버전 서술 없으면 거부", fresh(release_version_in_md=None),
       "release", "0.2.0", "--notes", "x", "--date", "2026-07-14")

# T5: 태그 선점 → 거부
repo5 = fresh()
git(repo5, "tag", "v0.2.0")
reject("T5", "태그 선점 거부", repo5,
       "release", "0.2.0", "--notes", "x", "--date", "2026-07-14")

# T7: fsck 위반 저장소 → 거부
repo7 = fresh()
bad = os.path.join(repo7, "rooms", "experiment", "chains", "seed", "C002-broken")
os.makedirs(bad)
with open(os.path.join(bad, "cycle.yaml"), "w", encoding="utf-8") as f:
    f.write("id: C002-broken\nchain: seed\nparent: C099-ghost\nauthor: f\nstatus: open\n"
            "opened: 2026-01-01\nclosed: null\ntitle: \"broken\"\n")
git(repo7, "add", "-A"); git(repo7, "commit", "-q", "-m", "break")
reject("T7", "fsck 위반 저장소에서 릴리스 거부", repo7,
       "release", "0.2.0", "--notes", "x", "--date", "2026-07-14")

for d in _TMP:
    shutil.rmtree(d, ignore_errors=True)
total, passed = len(RESULTS), sum(RESULTS)
print(f"\n결과: {passed}/{total} 통과")
sys.exit(0 if passed == total else 1)
