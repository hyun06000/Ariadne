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
        if "step" in fields:
            f.write(f"step: {fields['step']}\n")


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
          and all(k in y for k in ("id: C001-first-step", "chain: demo", "parent: null", "status: open", "step: 1"))
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

    # ---- step (자체 구축 샌드박스, v0.6.0 계약) ----
    sroot = make_sandbox(os.path.join(work, "step"))
    write_cycle(sroot, "demo", "C001-first-step", step="1")
    write_cycle(sroot, "demo", "C009-done", status="closed", closed="2026-01-02", step="5")
    sy = os.path.join(sroot, "rooms/experiment/chains/demo/C001-first-step/cycle.yaml")
    r = impl.run(sroot, "step", "demo", "C001-first-step", "3")
    check("STEP-OK", "step 전이 반영 (1→3)", r.returncode == 0
          and "step: 3" in open(sy, encoding="utf-8").read(), r.stderr.strip()[-120:])
    before = open(sy, encoding="utf-8").read()
    r = impl.run(sroot, "step", "demo", "C001-first-step", "9")
    check("STEP-REJECT-RANGE", "범위 밖 step 거부 + 무변화", r.returncode != 0
          and open(sy, encoding="utf-8").read() == before)
    r = impl.run(sroot, "step", "demo", "C009-done", "3")
    check("STEP-REJECT-CLOSED", "닫힌 사이클 step 변경 거부", r.returncode != 0)
    rroot = make_sandbox(os.path.join(work, "bad-r9"))
    write_cycle(rroot, "demo", "C001-x", step="7")
    r = impl.run(rroot, "fsck")
    check("FSCK-R9", "R9 위반 탐지 (step 범위)", r.returncode != 0)

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
    steps_present = bool(m) and all("step" in c for ch in json.loads(m.group(1))["chains"].values()
                                     for c in ch["cycles"].values())
    check("WEB-JSON", 'web 내장 JSON (id="gil-data") 구조·step 일치', nodes ==
          {"demo/C001-first-step", "demo/C002-second-step"} and steps_present, str(nodes))  # lroot의 두 사이클

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

        # ---- open --git: 열 때부터 보이게 (SPEC §2.1-3) — 자체 구축 샌드박스 (판정 항목 독립) ----
        og = make_sandbox(os.path.join(work, "gitopen"))

        def gito(*cli):
            return subprocess.run(["git", "-C", og, *cli], capture_output=True, text=True)

        gito("init", "-q"); gito("config", "user.name", "fx"); gito("config", "user.email", "fx@t")
        write_cycle(og, "demo", "C001-first-step", status="closed", closed="2026-01-02")
        with open(os.path.join(og, "unrelated.txt"), "w", encoding="utf-8") as f:
            f.write("무관 파일\n")
        gito("add", "-A"); gito("commit", "-q", "-m", "init")
        with open(os.path.join(og, "unrelated.txt"), "a", encoding="utf-8") as f:
            f.write("더러움\n")  # 무관한 더러운 파일은 커밋에 섞이면 안 된다
        r = impl.run(og, "open", "demo", "second-step", "--parent", "C001-first-step",
                     "--title", "t", "--author", "fx", "--date", "2026-01-03", "--git")
        committed = gito("show", "--name-only", "--format=", "HEAD").stdout.split()
        cyc = "rooms/experiment/chains/demo/C002-second-step"
        check("OPEN-GIT", "open --git: 새 사이클 경로만 커밋 (열림 즉시 각인)",
              r.returncode == 0 and committed
              and all(p.startswith(cyc) for p in committed)
              and f"{cyc}/cycle.yaml" in committed,
              r.stderr.strip()[-120:] or str(committed))

        # ---- open --push: 번호 원장 규율 (SPEC §6-6) — 로컬 bare 원장 + 병렬 클론, 네트워크 무의존 ----
        ledger = os.path.join(work, "ledger.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", ledger], check=True)
        seed = make_sandbox(os.path.join(work, "seed"))
        write_cycle(seed, "demo", "C001-seed", status="closed", closed="2026-01-02")
        for cli in (["init", "-q", "-b", "main"], ["config", "user.name", "fx"],
                    ["config", "user.email", "fx@t"], ["add", "-A"], ["commit", "-q", "-m", "seed"],
                    ["remote", "add", "origin", ledger], ["push", "-q", "origin", "main"]):
            subprocess.run(["git", "-C", seed, *cli], capture_output=True, text=True)

        def clone(name):
            d = os.path.join(work, name)
            subprocess.run(["git", "clone", "-q", ledger, d], capture_output=True, text=True)
            for cli in (["config", "user.name", name], ["config", "user.email", f"{name}@t"]):
                subprocess.run(["git", "-C", d, *cli], capture_output=True, text=True)
            return d

        A, B = clone("beingA"), clone("beingB")
        # A가 먼저 원장에 올린다 (무경합 경로)
        ra = impl.run(A, "open", "demo", "alpha", "--parent", "C001-seed", "--title", "A",
                      "--author", "a", "--date", "2026-01-03", "--git", "--push")
        # B는 원장을 모른 채 같은 번호(C002)로 연다 → 경합 → 자동 재번호(C003)로 해소되어야 한다
        rb = impl.run(B, "open", "demo", "beta", "--parent", "C001-seed", "--title", "B",
                      "--author", "b", "--date", "2026-01-03", "--git", "--push")
        probe = clone("probe")  # 원장의 진실을 제3의 클론으로 관찰한다
        pdir = os.path.join(probe, "rooms/experiment/chains/demo")
        ypath = os.path.join(pdir, "C003-beta", "cycle.yaml")
        y = open(ypath, encoding="utf-8").read() if os.path.isfile(ypath) else ""
        rf = impl.run(probe, "fsck")  # 원장에 번호 중복(R1)이 남았다면 여기서 걸린다
        check("OPEN-PUSH-RENUMBER", "open --push: 번호 경합을 자동 재번호로 해소 (원장 규율)",
              ra.returncode == 0 and rb.returncode == 0
              and os.path.isdir(os.path.join(pdir, "C002-alpha"))     # A의 것은 그대로
              and os.path.isdir(os.path.join(pdir, "C003-beta"))      # B는 재번호되어 공존
              and not os.path.isdir(os.path.join(pdir, "C002-beta"))  # 옛 번호는 남지 않는다
              and "id: C003-beta" in y and "author: b" in y and 'title: "B"' in y  # 내용 무손상
              and rf.returncode == 0,                                 # 원장 무위반
              (rb.stderr or "").strip()[-150:])

    shutil.rmtree(work, ignore_errors=True)
    total, passed = len(RESULTS), sum(RESULTS)
    print(f"\n계약 준수: {passed}/{total}" + ("  ✔ 이 구현은 gil이다" if passed == total else "  ✘ 계약 위반"))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
