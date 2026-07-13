#!/usr/bin/env python3
"""gil 계약 준수 스위트 (Ariadne Spec §7의 실행 가능형).

어떤 gil 구현이든 — 파이썬 참조 구현이든 미래의 단일 바이너리든 — 같은 판정을 받는다.

원칙 (구현 독립):
  * 구현은 --gil "<명령 문자열>"로만 주입된다 (예: --gil "python3 gil.py", --gil "./gil").
  * 판정 수단은 셋뿐이다: 종료 코드, 파일시스템 관찰, 산출물 텍스트. 구현 내부는 알지 못한다.
  * 샌드박스(템플릿 포함)는 스위트가 스스로 만든다 — 외부 픽스처 의존 없음.

사용: python3 conformance.py --gil "python3 /path/to/gil.py" [--skip-git]
종료 코드: 전 항목 통과 0, 하나라도 실패 1.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

RESULTS = []


def check(cid, desc, cond, detail=""):
    RESULTS.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {cid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


class Impl:
    def __init__(self, cmd):
        self.argv = shlex.split(cmd)

    def run(self, cwd, *cli):
        return subprocess.run(self.argv + list(cli), cwd=cwd, capture_output=True, text=True)


def make_sandbox(root):
    """rooms/experiment/{_template, chains} 를 갖춘 최소 저장소를 만든다."""
    tpl = os.path.join(root, "rooms", "experiment", "_template")
    os.makedirs(os.path.join(tpl, "3-verification"))
    os.makedirs(os.path.join(root, "rooms", "experiment", "chains"))
    for name, body in [
        ("cycle.yaml", "id: C000-slug\nchain: chain-name\nparent: null\nlineage: []\n"
                       "author: someone\nstatus: open\nopened: 2026-01-01\nclosed: null\ntitle: \"\"\n"),
        ("1-hypothesis.md", "# 1. 가설 수립\n(작성할 것)\n"),
        ("2-design.md", "# 2. 실험 설계\n(작성할 것)\n"),
        ("3-verification/README.md", "# 3. 가설 검증\n(작성할 것)\n"),
        ("4-analysis.md", "# 4. 결과 분석\n(작성할 것)\n"),
        ("5-report.md", "# 5. 결과 보고\n(작성할 것)\n"),
    ]:
        path = os.path.join(tpl, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    return root


def write_cycle(root, chain_dir, cid_dir, **fields):
    d = os.path.join(root, "rooms", "experiment", "chains", chain_dir, cid_dir)
    os.makedirs(d, exist_ok=True)
    data = {"id": cid_dir, "chain": chain_dir, "parent": "null", "lineage": "[]", "author": "fx",
            "status": "open", "opened": "2026-01-01", "closed": "null", "title": '"t"'}
    data.update(fields)
    with open(os.path.join(d, "cycle.yaml"), "w", encoding="utf-8") as f:
        for k in ("id", "chain", "parent", "lineage", "author", "status", "opened", "closed", "title"):
            f.write(f"{k}: {data[k]}\n")


def snapshot(root):
    out = {}
    for base, dirs, files in os.walk(root):
        if ".git" in dirs:
            dirs.remove(".git")
        for n in files:
            p = os.path.join(base, n)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = hash(f.read())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gil", required=True, help='구현 호출 명령 (예: "python3 gil.py")')
    ap.add_argument("--skip-git", action="store_true")
    args = ap.parse_args()
    impl = Impl(args.gil)
    work = tempfile.mkdtemp(prefix="gil-conformance-")

    # ---- fsck: 깨끗한 저장소 ----
    root = make_sandbox(os.path.join(work, "clean"))
    write_cycle(root, "alpha", "C001-first", status="closed", closed="2026-01-02")
    write_cycle(root, "alpha", "C002-second", parent="C001-first")
    r = impl.run(root, "fsck")
    check("FSCK-CLEAN", "규칙 준수 저장소에서 fsck exit 0", r.returncode == 0, r.stderr.strip()[-120:])

    # ---- fsck: R1~R8 위반 각각 ----
    violations = {
        "R1": dict(cid="C01-short", fields={}),                                  # 번호 3자리 미만
        "R2": dict(cid="C003-r2", fields={"lineage": "[ghost/C001-x]"}),         # 유령 lineage
        "R3": dict(cid="C003-r3", fields={"parent": "beta/C001-first"}),         # 전역 표기 parent
        "R4": dict(cid="C003-r4", fields={"chain": "elsewhere"}),                # chain 필드 불일치
        "R5": dict(cid="C003-r5", fields={"id": "C003-other"}),                  # id ≠ 디렉토리명
        "R6": dict(cid="C003-r6", fields={"parent": "C099-ghost"}),              # 끊어진 parent
        "R8": dict(cid="C003-r8", fields={"status": "closed"}),                  # closed인데 일자 없음
    }
    for rule, spec in violations.items():
        root = make_sandbox(os.path.join(work, f"bad-{rule.lower()}"))
        write_cycle(root, "alpha", "C001-first", status="closed", closed="2026-01-02")
        write_cycle(root, "alpha", spec["cid"], **{"parent": "C001-first", **spec["fields"]})
        r = impl.run(root, "fsck")
        check(f"FSCK-{rule}", f"{rule} 위반 탐지 (exit ≠ 0)", r.returncode != 0)
    root = make_sandbox(os.path.join(work, "bad-r7"))  # R7 순환
    write_cycle(root, "alpha", "C001-a", parent="C002-b")
    write_cycle(root, "alpha", "C002-b", parent="C001-a")
    r = impl.run(root, "fsck")
    check("FSCK-R7", "R7 순환 탐지 (exit ≠ 0)", r.returncode != 0)

    # ---- open ----
    root = make_sandbox(os.path.join(work, "open"))
    r = impl.run(root, "open", "demo", "first-step", "--new-chain", "--title", "t",
                 "--author", "fx", "--date", "2026-01-01")
    ypath = os.path.join(root, "rooms/experiment/chains/demo/C001-first-step/cycle.yaml")
    y = open(ypath, encoding="utf-8").read() if os.path.isfile(ypath) else ""
    check("OPEN-CREATE", "open이 v0.2 준수 사이클 생성", r.returncode == 0
          and all(k in y for k in ("id: C001-first-step", "chain: demo", "parent: null", "status: open"))
          and os.path.isfile(os.path.join(root, "rooms/experiment/chains/demo/C001-first-step/5-report.md")),
          r.stderr.strip()[-120:])
    r = impl.run(root, "open", "demo", "second-step", "--parent", "C001-first-step",
                 "--title", "t", "--author", "fx", "--date", "2026-01-02")
    check("OPEN-INCREMENT", "번호 자동 증가 (C002)", r.returncode == 0
          and os.path.isdir(os.path.join(root, "rooms/experiment/chains/demo/C002-second-step")))
    before = snapshot(root)
    r = impl.run(root, "open", "demo", "Bad.Slug", "--title", "t", "--date", "2026-01-03")
    check("OPEN-REJECT-SLUG", "형식 위반 슬러그 거부 + 무변화", r.returncode != 0 and snapshot(root) == before)

    # ---- close (자체 구축 샌드박스 — 판정 항목 간 독립: 각 검사는 자기가 판정하는 명령에만 의존한다) ----
    croot = make_sandbox(os.path.join(work, "close"))
    write_cycle(croot, "demo", "C001-first-step")
    cdir = os.path.join(croot, "rooms/experiment/chains/demo/C001-first-step")
    shutil.copyfile(os.path.join(croot, "rooms/experiment/_template/5-report.md"),
                    os.path.join(cdir, "5-report.md"))
    cy = os.path.join(cdir, "cycle.yaml")
    before = open(cy, encoding="utf-8").read()
    r = impl.run(croot, "close", "demo", "C001-first-step", "--date", "2026-01-05")
    check("CLOSE-TEMPLATE-REJECT", "템플릿 그대로의 보고서로는 닫기 거부", r.returncode != 0
          and open(cy, encoding="utf-8").read() == before)
    with open(os.path.join(cdir, "5-report.md"), "w", encoding="utf-8") as f:
        f.write("# 5. 결과 보고\n\n## 요약\n\n계약 검증용 실보고서.\n")
    r = impl.run(croot, "close", "demo", "C001-first-step", "--date", "2026-01-05")
    y = open(cy, encoding="utf-8").read()
    check("CLOSE-OK", "정상 닫기 (status·closed 전이)", r.returncode == 0
          and "status: closed" in y and "closed: 2026-01-05" in y, r.stderr.strip()[-120:])
    r = impl.run(croot, "close", "demo", "C001-first-step", "--date", "2026-01-06")
    check("CLOSE-DOUBLE-REJECT", "이중 닫기 거부", r.returncode != 0)

    # ---- log (자체 구축 샌드박스) ----
    lroot = make_sandbox(os.path.join(work, "log-ok"))
    write_cycle(lroot, "demo", "C001-first-step", status="closed", closed="2026-01-02")
    write_cycle(lroot, "demo", "C002-second-step", parent="C001-first-step")
    r = impl.run(lroot, "log")
    check("LOG-OK", "log 정상 렌더 (exit 0 + 사이클 id 표기)", r.returncode == 0 and "C001-first-step" in r.stdout)
    broken = make_sandbox(os.path.join(work, "log-broken"))
    write_cycle(broken, "alpha", "C001-x", parent="C099-ghost")
    r = impl.run(broken, "log")
    check("LOG-BROKEN", "끊어진 참조에서 log 거부", r.returncode != 0)

    # ---- web (자체 구축 샌드박스) ----
    out = os.path.join(work, "chains.html")
    r = impl.run(lroot, "web", "-o", out, "--title", "t")
    page = open(out, encoding="utf-8").read() if os.path.isfile(out) else ""
    external = re.findall(r'(?:src=|href=|url\(|@import)[^>\n]*https?://', page)
    m = re.search(r'<script type="application/json" id="gil-data">(.*?)</script>', page, re.S)
    nodes = set()
    if m:
        data = json.loads(m.group(1))
        nodes = {f"{c}/{i}" for c, ch in data.get("chains", {}).items() for i in ch.get("cycles", {})}
    check("WEB-SELFCONTAINED", "web 산출물 외부 리소스 0", r.returncode == 0 and page and external == [],
          str(external))
    check("WEB-JSON", 'web 내장 JSON (id="gil-data") 구조 일치', nodes ==
          {"demo/C001-first-step", "demo/C002-second-step"}, str(nodes))  # lroot의 두 사이클

    # ---- 깃 각인 (가용 시) ----
    if args.skip_git or shutil.which("git") is None:
        print("SKIP GIT-*: 깃 검사 생략")
    else:
        g = make_sandbox(os.path.join(work, "gitrepo"))

        def git(*cli):
            return subprocess.run(["git", "-C", g, *cli], capture_output=True, text=True)

        git("init", "-q"); git("config", "user.name", "fx"); git("config", "user.email", "fx@t")
        write_cycle(g, "demo", "C001-first-step")
        with open(os.path.join(g, "rooms/experiment/chains/demo/C001-first-step/5-report.md"),
                  "w", encoding="utf-8") as f:
            f.write("# 5. 결과 보고\n\n실보고서.\n")
        with open(os.path.join(g, "unrelated.txt"), "w", encoding="utf-8") as f:
            f.write("무관 파일\n")
        git("add", "-A"); git("commit", "-q", "-m", "init")
        with open(os.path.join(g, "unrelated.txt"), "a", encoding="utf-8") as f:
            f.write("더러움\n")
        r = impl.run(g, "close", "demo", "C001-first-step", "--date", "2026-01-05", "--git")
        committed = git("show", "--name-only", "--format=", "HEAD").stdout.split()
        tag_ok = git("tag", "-l", "cycle/demo/C001-first-step").stdout.strip() == "cycle/demo/C001-first-step"
        check("GIT-CLOSE", "close --git: 태그 + 사이클 경로만 커밋", r.returncode == 0 and tag_ok
              and committed and all(p.startswith("rooms/experiment/chains/demo/C001-first-step") for p in committed),
              r.stderr.strip()[-120:])
        r = impl.run(g, "verify")
        check("VERIFY-CLEAN", "무변조 verify exit 0", r.returncode == 0, r.stderr.strip()[-120:])
        with open(os.path.join(g, "rooms/experiment/chains/demo/C001-first-step/5-report.md"),
                  "a", encoding="utf-8") as f:
            f.write("(몰래 수정)\n")
        r = impl.run(g, "verify")
        check("VERIFY-TAMPER", "닫힌 사이클 변조 탐지 (exit ≠ 0)", r.returncode != 0)

    shutil.rmtree(work, ignore_errors=True)
    total, passed = len(RESULTS), sum(RESULTS)
    print(f"\n계약 준수: {passed}/{total}" + ("  ✔ 이 구현은 gil이다" if passed == total else "  ✘ 계약 위반"))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
