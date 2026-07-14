#!/usr/bin/env python3
"""loom/C038 검증 — version 표면 계약 + 마스킹 승격 (T3~T10). 판정은 2-design.md에 선고정.

T1·T2·T11(실저장소 릴리스·양 구현 자기보고·회귀)은 실릴리스 경로에서 별도 수행하고 runs/에 기록한다.
픽스처 하네스는 loom/C018의 fresh()를 재사용하고 go/main.go 축을 더해 확장했다.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
GIL = os.path.join(BASE, "gil", "gil.py")
CONF = os.path.join(BASE, "gil", "conformance.py")
GO = os.path.join(BASE, "gil", "go", "main.go")
LOOM = os.path.abspath(os.path.join(BASE, "..", ".."))
C3_SANDBOX = os.path.join(LOOM, "C003-open-close-porcelain", "3-verification", "fixtures", "sandbox")
RESULTS = []
_TMP = []

MARK = "gil:version"
SEMVER = re.compile(r"\d+\.\d+\.\d+")


def sh(cwd, *cli):
    return subprocess.run(list(cli), cwd=cwd, capture_output=True, text=True)


def git(repo, *cli):
    return sh(repo, "git", *cli)


def check(tid, desc, cond, detail=""):
    RESULTS.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {tid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


def set_version(text, v):
    """표식 라인의 첫 SemVer를 v로 — 도구와 독립적으로 하네스가 직접 구현한다 (도구의 답을 훔치지 않는다)."""
    out = []
    for line in text.splitlines(keepends=True):
        if MARK in line and SEMVER.search(line):
            line = SEMVER.sub(v, line, count=1)
        out.append(line)
    return "".join(out)


def snapshot(root):
    h = hashlib.sha256()
    for base, dirs, files in sorted(os.walk(root)):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(files):
            p = os.path.join(base, name)
            h.update(os.path.relpath(p, root).encode())
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


RUNNING = open(GIL, encoding="utf-8").read()      # 실행 도구 (version 1.11.0, 표식 있음)
CONF_SRC = open(CONF, encoding="utf-8").read()
GO_SRC = open(GO, encoding="utf-8").read()


def fresh(tool_at_tag=None, conf_at_tag=None, go_at_tag=None,
          conf_now=None, go_now=None, versions_in_md=("0.1.1", "0.2.0")):
    """태그 v0.1.0 시점의 패키지 상태와 현재 작업 트리 상태를 구분해 구성한다 (C018 하네스 + go 축)."""
    tool_at_tag = set_version(RUNNING, "0.1.0") if tool_at_tag is None else tool_at_tag
    conf_at_tag = CONF_SRC if conf_at_tag is None else conf_at_tag
    go_at_tag = set_version(GO_SRC, "0.1.0") if go_at_tag is None else go_at_tag

    tmp = tempfile.mkdtemp(prefix="gil-c038-")
    _TMP.append(tmp)
    repo = os.path.join(tmp, "repo")
    shutil.copytree(C3_SANDBOX, repo)
    pkg = os.path.join(repo, "rooms", "deployment", "ariadne-spec")
    os.makedirs(os.path.join(pkg, "go"))
    for rel, text in (("gil.py", tool_at_tag), ("conformance.py", conf_at_tag),
                      (os.path.join("go", "main.go"), go_at_tag)):
        with open(os.path.join(pkg, rel), "w", encoding="utf-8") as f:
            f.write(text)
    with open(os.path.join(pkg, "RELEASE.md"), "w", encoding="utf-8") as f:
        f.write("# R\n\n" + "".join(f"## v{v}\n\n서술.\n\n" for v in versions_in_md) + "## v0.1.0\n\n첫.\n")
    shutil.copytree(os.path.join(repo, "rooms", "experiment", "_template"), os.path.join(pkg, "template"))
    with open(os.path.join(repo, "rooms", "deployment", "CHANGELOG.md"), "w", encoding="utf-8") as f:
        f.write("# C\n\n## [Unreleased]\n\n## [0.1.0] — 2026-01-01\n\n- x\n")
    git(repo, "init", "-q", "-b", "main"); git(repo, "config", "user.name", "fx")
    git(repo, "config", "user.email", "fx@t"); git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "release state"); git(repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")

    dirty = False
    for rel, now in (("conformance.py", conf_now), (os.path.join("go", "main.go"), go_now)):
        if now is not None:
            with open(os.path.join(pkg, rel), "w", encoding="utf-8") as f:
                f.write(now)
            dirty = True
    if dirty:
        git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "post-tag change")
    return repo


def release(repo, version, tool=GIL, notes="x"):
    return sh(repo, sys.executable, tool, "release", version, "--notes", notes, "--date", "2026-07-15")


def changelog(repo):
    return open(os.path.join(repo, "rooms/deployment/CHANGELOG.md"), encoding="utf-8").read()


def pkg_file(repo, *rel):
    return open(os.path.join(repo, "rooms/deployment/ariadne-spec", *rel), encoding="utf-8").read()


def marked_semver(text):
    """표식 라인이 선언한 버전 (하네스의 독립 관찰)."""
    for line in text.splitlines():
        if MARK in line:
            m = SEMVER.search(line)
            if m:
                return m.group(0)
    return None


# ── T3 (핵심 회귀): 태그 대비 도구가 version 표면만 다르다 → 패치 승격 허용 ──────────────────
# 이것이 v1.10.1을 거부당하게 만든 바로 그 상황이다. 마스킹이 자기 지시적 순환을 끊어야 한다.
repo = fresh()                       # 태그 blob: 0.1.0 / 실행·작업 트리: 1.11.0 (표면만 차이)
r = release(repo, "0.1.1")
log = changelog(repo)
check("T3", "version 표면만 다른 릴리스는 패치 승격 허용 + '문서 릴리스' 분류 (마스킹 작동)",
      r.returncode == 0 and "도구 변경: 없음 (문서 릴리스)" in log,
      f"rc={r.returncode}: {(r.stderr or '').strip()[-200:]}")

# ── T4: gil.py 실질 변경 → 패치 거부 (마스킹이 진짜 변경을 삼키지 않는다) ────────────────────
repo = fresh(tool_at_tag=set_version(RUNNING, "0.1.0") + "\n# 태그 이후 실질 변경\n")
before = snapshot(repo)
r4 = release(repo, "0.1.1")
after = snapshot(repo)
check("T4", "gil.py 실질 변경 → 패치 거부 ('gil' 지목)",
      r4.returncode != 0 and "gil" in (r4.stderr or ""), (r4.stderr or "").strip()[-160:])
check("T9a", "T4 거부 경로: 저장소 무변화", before == after, f"{before[:12]} → {after[:12]}")

# ── T5: conformance.py 실질 변경 → 패치 거부 (판정기도 도구다 — C018 규칙 유지) ─────────────
repo = fresh(conf_now=CONF_SRC + "\n# 판정기 변경\n")
r5 = release(repo, "0.1.1")
check("T5", "conformance.py 변경 → 패치 거부 ('conformance' 지목)",
      r5.returncode != 0 and "conformance" in (r5.stderr or ""), (r5.stderr or "").strip()[-160:])

# ── T6: go/main.go 실질 변경 → 패치 거부 (신규 관측 범위 — 지금까지 아무도 안 보던 blob) ────
repo = fresh(go_now=set_version(GO_SRC, "0.1.0") + "\n// Go 실질 변경\n")
r6 = release(repo, "0.1.1")
check("T6", "go/main.go 실질 변경 → 패치 거부 ('go' 지목, 신규 관측 범위)",
      r6.returncode != 0 and "go" in (r6.stderr or ""), (r6.stderr or "").strip()[-160:])

# ── T7: 표식 0개 (동봉 구현) → 릴리스 거부 ────────────────────────────────────────────────
repo = fresh(go_now=GO_SRC.replace(" // " + MARK, ""), go_at_tag=GO_SRC.replace(" // " + MARK, ""))
before = snapshot(repo)
r7 = release(repo, "0.2.0")
after = snapshot(repo)
check("T7", "동봉 구현에 version 표식 0개 → 거부 (계약 위반 명시)",
      r7.returncode != 0 and "표면 계약 위반" in (r7.stderr or ""), (r7.stderr or "").strip()[-160:])
check("T9b", "T7 거부 경로: 저장소 무변화", before == after, f"{before[:12]} → {after[:12]}")

# ── T8: 표식 2개 (참조 구현) → 릴리스 거부 ────────────────────────────────────────────────
dup_tool = os.path.join(tempfile.mkdtemp(prefix="gil-c038-dup-"), "gil.py")
_TMP.append(os.path.dirname(dup_tool))
with open(dup_tool, "w", encoding="utf-8") as f:
    f.write(RUNNING.replace('_GIL_VERSION = "1.11.0"  # ' + MARK,
                            '_GIL_VERSION = "1.11.0"  # ' + MARK + '\n_DUP = "9.9.9"  # ' + MARK))
repo = fresh()
r8 = release(repo, "0.2.0", tool=dup_tool)
check("T8", "참조 구현에 version 표식 2개(중복) → 거부",
      r8.returncode != 0 and "표면 계약 위반" in (r8.stderr or ""), (r8.stderr or "").strip()[-160:])

# ── T10: 실질 변경 + 마이너 승격 → 허용, 패키지의 version 표면 전부 갱신 ──────────────────────
repo = fresh(tool_at_tag=set_version(RUNNING, "0.1.0") + "\n# 실질 변경\n")
r10 = release(repo, "0.2.0")
py_v, go_v = marked_semver(pkg_file(repo, "gil.py")), marked_semver(pkg_file(repo, "go", "main.go"))
tagged = git(repo, "tag", "-l", "v0.2.0").stdout.strip()
check("T10", "실질 변경 + 마이너 승격 → 허용, 두 구현의 version 표면이 릴리스 버전으로 갱신",
      r10.returncode == 0 and py_v == "0.2.0" and go_v == "0.2.0" and tagged == "v0.2.0",
      f"rc={r10.returncode} py={py_v} go={go_v} tag={tagged!r}: {(r10.stderr or '').strip()[-160:]}")

# 갱신된 파이썬 구현이 실제로 그 버전을 말하는가 (표면 ↔ 자기보고 일치)
rv = sh(repo, sys.executable, os.path.join(repo, "rooms/deployment/ariadne-spec/gil.py"), "version")
check("T10b", "갱신된 패키지 도구를 실행하면 'gil 0.2.0'을 보고",
      rv.stdout.strip() == "gil 0.2.0", rv.stdout.strip())

for d in _TMP:
    shutil.rmtree(d, ignore_errors=True)
total, passed = len(RESULTS), sum(RESULTS)
print(f"\n결과: {passed}/{total} 통과")
sys.exit(0 if passed == total else 1)
