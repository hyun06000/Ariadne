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

UNIMPLEMENTED = 3  # SPEC §7.2-4: 미구현·미지 명령의 통일된 종료 신호

# SPEC §5가 정의하는 명령 표면. 구현이 이 중 무엇을 구현했는지는 자유이나(부분 구현 합법),
# 자기보고와 실제가 어긋나는 것은 금지다. 이 목록 자체가 목록형 규칙이며 — SPEC이 자라면 함께 자라야 한다.
CONTRACT_COMMANDS = ["log", "fsck", "open", "close", "step", "verify", "release", "version",
                     "handoff", "supersede", "goto", "pages", "web", "help", "correct",
                     "reserve", "unreserve"]  # loom/C043 (이슈 #13) — 부분 구현은 합법, 거짓 보고만 불법


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
    cdir = os.path.join(root, "rooms", "experiment", "chains", chain_dir)
    d = os.path.join(cdir, cid_dir)
    os.makedirs(d, exist_ok=True)
    cm = os.path.join(cdir, "chain.md")  # R14 (loom/C044): 정상 체인은 chain.md를 갖는다
    if not os.path.exists(cm):
        with open(cm, "w", encoding="utf-8") as f:
            f.write(f"# Chain: {chain_dir}\n")
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

    # ---- version: 자기보고 표면 (SPEC §7). 판정기는 릴리스 버전을 모르므로 '형태'만 판정한다 —
    #      값의 진실성(배포 버전과의 일치)은 release가 집행한다 (loom/C038). ----
    r = impl.run(work, "version")
    check("VERSION-SEMVER", "version이 'gil X.Y.Z' (SemVer) 형태로 자기를 보고",
          r.returncode == 0 and re.fullmatch(r"gil \d+\.\d+\.\d+", r.stdout.strip()) is not None,
          r.stdout.strip()[:60])

    # ---- 명령 자기보고 표면 (SPEC §7.2 — loom/C039, maru의 이슈 #12) ----
    #      에이전트는 능력을 문서가 아니라 도구의 자기보고로 판단한다. 그래서 자기보고는 계약이다.
    #      판정기는 각 구현을 '그 자신의 훅'에 비추어 본다 — 부분 구현은 합법이고, 거짓 보고만 불법이다.
    hroot = make_sandbox(os.path.join(work, "help"))
    r = impl.run(hroot, "help")
    hooks = [l for l in r.stdout.splitlines() if l.startswith("gil:commands ")]
    claimed = hooks[0].split()[1:] if len(hooks) == 1 else []
    check("HELP-EXIT0", "help이 exit 0으로 능력 목록 보고 (기계 훅 gil:commands 정확히 1줄)",
          r.returncode == 0 and len(hooks) == 1 and len(claimed) > 0,
          f"rc={r.returncode} 훅={len(hooks)}줄")

    # 무해성: 능력을 물어보는 행위가 저장소를 변경하면 안 된다 (§7.2-6).
    sroot = make_sandbox(os.path.join(work, "help-safe"))
    before = snapshot(sroot)
    impl.run(sroot, "help")
    for c in claimed:
        impl.run(sroot, "help", c)
    impl.run(sroot, "pages", "--dry-run")
    check("HELP-SAFE", "능력 탐침(help·help <명령>·pages --dry-run)이 저장소를 변경하지 않는다",
          snapshot(sroot) == before)

    # 정방향: 나열한 것은 실제로 있다. (help <c> → 0, dispatch가 미구현 신호를 내지 않음)
    troot = make_sandbox(os.path.join(work, "help-truth"))
    liars = [c for c in claimed
             if impl.run(troot, "help", c).returncode != 0
             or impl.run(troot, c).returncode == UNIMPLEMENTED]
    check("HELP-TRUTHFUL", "훅이 나열한 모든 명령이 실재한다 (미구현 신호 없음)",
          bool(claimed) and not liars, f"거짓 보고: {liars}")

    # 역방향: 나열하지 않은 것은 실제로 없다 — '구현했는데 목록에 없다'(이슈 #12의 버그)를 잡는 방향.
    # 미지 명령 'bogus'를 함께 걸어, 모든 명령을 구현한 참조 구현에서도 공허 통과가 되지 않게 한다.
    croot = make_sandbox(os.path.join(work, "help-complete"))
    unclaimed = [c for c in CONTRACT_COMMANDS if c not in claimed] + ["bogus"]
    hidden = [c for c in unclaimed
              if impl.run(croot, "help", c).returncode != UNIMPLEMENTED
              or impl.run(croot, c).returncode != UNIMPLEMENTED]
    check("HELP-COMPLETE", f"나열하지 않은 명령은 미구현 신호(exit {UNIMPLEMENTED})로 답한다",
          not hidden, f"침묵한 명령: {hidden}")

    # 탐침의 무해성 — pages는 두드리기만 해도 파일을 만들던 명령이다 (이슈 #12의 3절).
    proot = make_sandbox(os.path.join(work, "pages"))
    wf = os.path.join(proot, ".github", "workflows", "gil-pages.yml")
    rd = impl.run(proot, "pages", "--dry-run")
    made_on_probe = os.path.exists(wf)
    rr = impl.run(proot, "pages")  # 대조군: 진짜 호출은 만든다
    check("PAGES-DRYRUN", "pages --dry-run이 경로만 보고하고 파일을 만들지 않는다 (대조: pages는 만든다)",
          rd.returncode == 0 and "gil-pages.yml" in rd.stdout and not made_on_probe
          and rr.returncode == 0 and os.path.exists(wf),
          f"탐침이 생성함={made_on_probe}")

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

    # ---- fsck R14: 체인 디렉토리는 chain.md를 가져야 한다 (loom/C044, 이슈 #14) ----
    # OPEN-NEWCHAIN-COMMIT의 짝. fsck에만 의존한다 (open 무관 — write_cycle이 정상 체인을 심는다).
    r14 = make_sandbox(os.path.join(work, "r14"))
    write_cycle(r14, "demo", "C001-first-step")  # 수정된 write_cycle이 chain.md도 만든다
    cm14 = os.path.join(r14, "rooms/experiment/chains/demo/chain.md")
    r_ok = impl.run(r14, "fsck")   # chain.md 있음 → 위반 0
    os.remove(cm14)
    r_bad = impl.run(r14, "fsck")  # chain.md 없음 → R14 위반
    check("FSCK-R14", "R14: 체인에 chain.md가 없으면 위반 (있으면 통과)",
          r_ok.returncode == 0 and r_bad.returncode != 0 and "R14" in r_bad.stdout,
          f"ok={r_ok.returncode} bad={r_bad.returncode} out={r_bad.stdout.strip()[:80]}")

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
    # --author를 준다: 주지 않으면 O1(저자 없음)에 먼저 걸려 '슬러그 규칙'을 판정하지 못한다.
    # 엉뚱한 이유로 통과하는 테스트는 눈먼 테스트다 (loom/C011 동등 변이의 교훈).
    r = impl.run(root, "open", "demo", "Bad.Slug", "--title", "t", "--author", "fx", "--date", "2026-01-03")
    check("OPEN-REJECT-SLUG", "형식 위반 슬러그 거부 + 무변화", r.returncode != 0 and snapshot(root) == before)

    # ---- 출처 계약 (SPEC §3.2 — loom/C040): 도구는 author·parent를 지어내지 않는다.
    #      판정 수단은 종료 코드 + 저장소 무변화뿐이다. 오류 메시지의 문면은 계약이 아니다 (§3.1).
    #      항목마다 자기 샌드박스를 쓴다 — 거부가 뚫린 구현이 뒤 항목의 번호를 밀어
    #      '엉뚱한 이유의 실패'를 만들면 결함의 지목이 흐려진다 (판정 항목 독립, loom/C012). ----
    def prov(tag):
        p = make_sandbox(os.path.join(work, tag))
        write_cycle(p, "demo", "C001-alpha")  # 체인이 비어 있지 않다 → 부모가 필요한 상태
        return p

    proot = prov("prov-author")
    before = snapshot(proot)
    r = impl.run(proot, "open", "demo", "no-author", "--title", "t",
                 "--parent", "C001-alpha", "--date", "2026-01-03")
    check("OPEN-AUTHOR-REQUIRED", "O1: --author 없이 open 거부 + 무변화 (고유명사 기본값 금지)",
          r.returncode != 0 and snapshot(proot) == before, f"rc={r.returncode}")
    proot = prov("prov-parent")
    before = snapshot(proot)
    r = impl.run(proot, "open", "demo", "no-parent", "--title", "t",
                 "--author", "fx", "--date", "2026-01-03")
    check("OPEN-PARENT-REQUIRED", "O2: 비어있지 않은 체인에서 부모 플래그 없이 open 거부 + 무변화",
          r.returncode != 0 and snapshot(proot) == before, f"rc={r.returncode}")
    proot = prov("prov-conflict")
    before = snapshot(proot)
    r = impl.run(proot, "open", "demo", "conflict", "--title", "t", "--author", "fx",
                 "--parent", "C001-alpha", "--new-root", "--date", "2026-01-03")
    check("OPEN-ROOT-CONFLICT", "O3: --parent와 --new-root 동시 지정 거부 + 무변화",
          r.returncode != 0 and snapshot(proot) == before, f"rc={r.returncode}")
    proot = prov("prov-newroot")
    r = impl.run(proot, "open", "demo", "second-root", "--title", "t", "--author", "fx",
                 "--new-root", "--date", "2026-01-04")
    ypath = os.path.join(proot, "rooms/experiment/chains/demo/C002-second-root/cycle.yaml")
    y = open(ypath, encoding="utf-8").read() if os.path.isfile(ypath) else ""
    check("OPEN-NEW-ROOT", "O5: --new-root로 의도된 두 번째 루트 생성 (parent: null)",
          r.returncode == 0 and "parent: null" in y, r.stderr.strip()[-120:])
    # 과잉 작동 방어: 빈 체인의 첫 사이클이 루트라는 것은 추측이 아니라 계산이다 (§3.2 P3).
    # 이 항목이 실패하는 구현은 '정당한 루트'를 불법화한 것이다 — README 대문의 딸깍이 그 증인이다.
    eroot = make_sandbox(os.path.join(work, "open-empty"))
    r = impl.run(eroot, "open", "solo", "very-first", "--new-chain", "--title", "t",
                 "--author", "fx", "--date", "2026-01-01")
    check("OPEN-ROOT-EMPTY-CHAIN", "P3: 빈 체인의 첫 사이클은 부모 플래그 없이 열린다 (과잉 거부 금지)",
          r.returncode == 0
          and os.path.isdir(os.path.join(eroot, "rooms/experiment/chains/solo/C001-very-first")),
          r.stderr.strip()[-120:])
    # R12: 다중 루트는 '경고'다 — 위반이 아니다. exit 0을 깨는 구현은 자기 탈출구(--new-root)를 불법화한 것이다.
    mroot = make_sandbox(os.path.join(work, "multi-root"))
    write_cycle(mroot, "demo", "C001-alpha")
    write_cycle(mroot, "demo", "C002-beta")  # parent 없음 → 두 번째 루트
    r = impl.run(mroot, "fsck")
    check("FSCK-MULTI-ROOT", "R12: 다중 루트를 경고로 판정 (exit 0 — 위반 아님)",
          r.returncode == 0 and "다중루트" in (r.stderr + r.stdout),
          f"rc={r.returncode} {(r.stderr or '')[-90:]}")

    # ---- 번호 예약 (SPEC §6.7 — loom/C043, 이슈 #13) ----
    # 예약을 원장 데이터로 만들면 push 이전(격리 워크트리)의 예약도 선점된다. 원장 규율(§6-6)이
    # 못 풀던 "예정된 것의 충돌"을 데이터가 푼다. 부분 구현은 합법 — 이 표면을 훅에 나열한 구현만 판정한다.
    # (나열하지 않은 구현의 정직성은 HELP-COMPLETE가 exit 3으로 이미 판정했다 — "판정기가 안 보는 계약은 없다".)
    if "reserve" in claimed:
        def resv_lines(root, chain="demo"):
            p = os.path.join(root, "rooms/experiment/chains", chain, "reservations.tsv")
            if not os.path.isfile(p):
                return []
            return [l for l in open(p, encoding="utf-8").read().splitlines()
                    if l.strip() and not l.startswith("#")]

        def resv_sandbox(tag):
            p = make_sandbox(os.path.join(work, tag))
            write_cycle(p, "demo", "C001-seed", status="closed", closed="2026-01-02", step="5")
            return p

        # RESERVE-BASIC: 예약 → exit 0, 원장에 줄 1개, 출력에 대상 이름
        rroot = resv_sandbox("resv-basic")
        r = impl.run(rroot, "reserve", "demo", "go-web", "--for", "weft", "--date", "2026-01-03")
        check("RESERVE-BASIC", "reserve → exit 0 + 원장에 예약 1줄 (번호 선점 데이터화)",
              r.returncode == 0 and len(resv_lines(rroot)) == 1 and "weft" in r.stdout,
              f"rc={r.returncode} 줄={resv_lines(rroot)}")

        # RESERVE-NEEDS-FOR: --for 없이 거부 + 무변화 (§3.2 P1 — 예약 주인도 지어내지 않는다)
        rroot = resv_sandbox("resv-nofor")
        before = snapshot(rroot)
        r = impl.run(rroot, "reserve", "demo", "x", "--date", "2026-01-03")
        check("RESERVE-NEEDS-FOR", "--for 없는 reserve 거부 + 무변화 (§3.2 P1)",
              r.returncode != 0 and snapshot(rroot) == before, f"rc={r.returncode}")

        # RESERVE-NEEDS-CHAIN: 없는 체인에 예약 거부
        rroot = resv_sandbox("resv-nochain")
        r = impl.run(rroot, "reserve", "ghost", "x", "--for", "weft", "--date", "2026-01-03")
        check("RESERVE-NEEDS-CHAIN", "없는 체인에 reserve 거부", r.returncode != 0, f"rc={r.returncode}")

        # OPEN-SKIPS-RESERVED (조건 1, 선점): weft에게 C002 예약 후 clew가 열면 clew는 C003을 받고,
        # 예약은 남는다. 이것이 C037의 버그 — Clew가 Weft의 번호를 재발급하던 — 를 고친다.
        rroot = resv_sandbox("resv-skip")
        impl.run(rroot, "reserve", "demo", "wefts", "--for", "weft", "--date", "2026-01-03")
        r = impl.run(rroot, "open", "demo", "clews", "--author", "clew",
                     "--parent", "C001-seed", "--date", "2026-01-04")
        cdir = os.path.join(rroot, "rooms/experiment/chains/demo")
        check("OPEN-SKIPS-RESERVED", "예약된 번호를 open이 건너뛴다 (clew→C003, 예약 잔존) — 선점",
              r.returncode == 0 and os.path.isdir(os.path.join(cdir, "C003-clews"))
              and not os.path.isdir(os.path.join(cdir, "C002-clews"))
              and len(resv_lines(rroot)) == 1, f"rc={r.returncode} 예약={resv_lines(rroot)}")

        # OPEN-PROMOTES-OWNER (조건 2, 승격): 예약자(weft)가 열면 예약된 번호로 태어나고 예약은 소비된다.
        rroot = resv_sandbox("resv-promote")
        impl.run(rroot, "reserve", "demo", "intended", "--for", "weft", "--date", "2026-01-03")
        r = impl.run(rroot, "open", "demo", "final-slug", "--author", "weft",
                     "--parent", "C001-seed", "--date", "2026-01-04")
        cdir = os.path.join(rroot, "rooms/experiment/chains/demo")
        check("OPEN-PROMOTES-OWNER", "예약자가 열면 예약 번호로 승격 + 예약 소거 (C002-final-slug, 원장 비움)",
              r.returncode == 0 and os.path.isdir(os.path.join(cdir, "C002-final-slug"))
              and resv_lines(rroot) == [], f"rc={r.returncode} 예약={resv_lines(rroot)}")

        # RESERVE-NON-INVASIVE (조건 3): 예약이 있어도 fsck 위반 0, log는 예약을 그래프 노드로 넣지 않는다.
        rroot = resv_sandbox("resv-noninvasive")
        impl.run(rroot, "reserve", "demo", "pending", "--for", "weft", "--date", "2026-01-03")
        rf = impl.run(rroot, "fsck")
        rl = impl.run(rroot, "log")
        # 예약은 그래프의 계보 줄("C0NN ← …")에 나타나면 안 된다 (사이클이 아니므로)
        graph_has_reservation = re.search(r"C002-pending\s+←", rl.stdout) is not None
        check("RESERVE-NON-INVASIVE", "예약 있어도 fsck 위반 0 + log 그래프에 예약 노드 없음 (예약은 사이클 아님)",
              rf.returncode == 0 and rl.returncode == 0 and not graph_has_reservation,
              f"fsck={rf.returncode} 그래프침습={graph_has_reservation}")

        # RESERVE-IN-LOG (조건 3): log가 예약을 별도로 보인다 — 낡은 화면은 침묵보다 나쁘다 (C042).
        check("RESERVE-IN-LOG", "log가 예약을 구별해 표시한다 (예약 대상 이름 포함)",
              "예약" in rl.stdout and "weft" in rl.stdout, rl.stdout[-120:])

        # UNRESERVE: 취소 → 제거; 없는 번호 → 거부
        rroot = resv_sandbox("resv-unreserve")
        impl.run(rroot, "reserve", "demo", "temp", "--for", "weft", "--date", "2026-01-03")
        r_ok = impl.run(rroot, "unreserve", "demo", "2")
        after = resv_lines(rroot)
        r_bad = impl.run(rroot, "unreserve", "demo", "99")
        check("UNRESERVE", "unreserve 2 → 예약 제거(exit 0), 없는 99 → 거부",
              r_ok.returncode == 0 and after == [] and r_bad.returncode != 0,
              f"ok={r_ok.returncode} 잔여={after} bad={r_bad.returncode}")

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

        # ---- open --new-chain --git: 새 체인의 chain.md도 같은 커밋에 (loom/C044, 이슈 #14) — 자체 샌드박스 ----
        # 짝 항목 FSCK-R14와 함께 이슈 #14의 양면이다: open이 커밋하고, fsck가 존재를 요구한다.
        nc = make_sandbox(os.path.join(work, "newchain"))

        def ncg(*cli):
            return subprocess.run(["git", "-C", nc, *cli], capture_output=True, text=True)

        ncg("init", "-q"); ncg("config", "user.name", "fx"); ncg("config", "user.email", "fx@t")
        r = impl.run(nc, "open", "fresh", "first-step", "--new-chain",
                     "--title", "t", "--author", "fx", "--date", "2026-01-03", "--git")
        nc_committed = ncg("show", "--name-only", "--format=", "HEAD").stdout.split()
        nc_md = "rooms/experiment/chains/fresh/chain.md"
        nc_tracked = ncg("ls-files", nc_md).stdout.strip()  # 미추적이면 빈 문자열 (_template 잡음 배제)
        check("OPEN-NEWCHAIN-COMMIT",
              "open --new-chain --git: 새 체인의 chain.md도 같은 커밋에 포함 (미추적으로 남기지 않는다)",
              r.returncode == 0 and nc_md in nc_committed and nc_tracked == nc_md,
              r.stderr.strip()[-120:] or f"committed={nc_committed} tracked={nc_tracked!r}")

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

        # ---- 정정 규정 (SPEC §4.1 — loom/C041): 봉인된 거짓 출처의 정당한 수리 ----
        # 항목마다 자기 샌드박스를 준다 (C040: 공유 샌드박스는 멀쩡한 구현을 범인으로 지목했다).
        CYC = "rooms/experiment/chains/demo/C002-second"

        def sealed(name, second_open=False):
            """회색지대를 그대로 만든다: C002는 parent: null(도구의 대필)로 **봉인**됐지만,
            그 불변 문서 1-hypothesis.md는 부모가 C001-first라고 증언한다."""
            d = make_sandbox(os.path.join(work, name))

            def gg(*cli):
                return subprocess.run(["git", "-C", d, *cli], capture_output=True, text=True)

            gg("init", "-q"); gg("config", "user.name", "fx"); gg("config", "user.email", "fx@t")
            write_cycle(d, "demo", "C001-first", status="closed", closed="2026-01-02", step="5")
            if second_open:
                write_cycle(d, "demo", "C002-second", step="1")
            else:
                write_cycle(d, "demo", "C002-second", status="closed", closed="2026-01-03", step="5")
            # C003은 '그럴듯한 거짓'의 재료다: 실재하므로 스키마상 완벽히 합법이지만,
            # C002의 불변 문서는 이 이름을 한 번도 말하지 않는다. 증거 검사만이 이것을 막을 수 있다.
            write_cycle(d, "demo", "C003-other", parent="C001-first",
                        status="closed", closed="2026-01-03", step="5")
            for cid in ("C001-first", "C002-second", "C003-other"):
                with open(os.path.join(d, f"rooms/experiment/chains/demo/{cid}/5-report.md"),
                          "w", encoding="utf-8") as f:
                    f.write("# 5. 결과 보고\n\n실보고서.\n")
            # 불변 문서의 증언. 3줄=부모, 4줄=수행자, 5줄=결말 낱말('rejected')이 들어 있다 —
            # 필드 제한(L1)을 시험하려면 증거 검사가 침묵해야 하기 때문이다 (심층 방어가 변이를 가린다).
            with open(os.path.join(d, f"{CYC}/1-hypothesis.md"), "w", encoding="utf-8") as f:
                f.write("# 1. 가설 수립\n\n부모: [demo/C001-first](../C001-first/5-report.md)\n"
                        "수행: weft\n기각 조건: 재현되지 않으면 rejected.\n")
            gg("add", "-A"); gg("commit", "-q", "-m", "seed")
            gg("tag", "-a", "cycle/demo/C001-first", "-m", "seal")
            if not second_open:  # 열린 사이클은 봉인되지 않는다 (태그 없음)
                gg("tag", "-a", "cycle/demo/C002-second", "-m", "seal")
            return d, gg

        OK_ARGS = ("correct", "demo/C002-second", "--field", "parent", "--to", "C001-first",
                   "--evidence", "1-hypothesis.md:3", "--author", "fx", "--date", "2026-01-04")

        # C1 — 봉인이 없으면 정정도 없다 (열린 사이클은 직접 고쳐도 위조가 아니다)
        d, _ = sealed("cor-unsealed", second_open=True)
        before = snapshot(d)
        r = impl.run(d, *OK_ARGS)
        check("CORRECT-UNSEALED-REJECT", "봉인되지 않은 사이클의 정정 거부 (exit≠0 + 저장소 무변화)",
              r.returncode != 0 and snapshot(d) == before, f"rc={r.returncode}")

        # C2 — 도구는 정정의 출처도 지어내지 않는다 (§3.2 P1의 재귀)
        d, _ = sealed("cor-noauthor")
        before = snapshot(d)
        r = impl.run(d, "correct", "demo/C002-second", "--field", "parent", "--to", "C001-first",
                     "--evidence", "1-hypothesis.md:3")
        check("CORRECT-NO-AUTHOR", "--author 없는 정정 거부 (정정의 출처도 지어내지 않는다)",
              r.returncode != 0 and snapshot(d) == before, f"rc={r.returncode}")

        # C3 / L1 — 저자의 주장은 정정 대상이 아니다.
        # 증거(5줄)가 'rejected'를 실제로 증언하게 해서, **오직 필드 제한만이** 이것을 막게 한다.
        d, _ = sealed("cor-field")
        before = snapshot(d)
        r = impl.run(d, "correct", "demo/C002-second", "--field", "verdict", "--to", "rejected",
                     "--evidence", "1-hypothesis.md:5", "--author", "fx")
        check("CORRECT-FIELD-LIMIT", "출처 필드가 아닌 것(verdict)의 정정 거부 (L1 — 증거가 있어도 저자의 주장은 불변)",
              r.returncode != 0 and snapshot(d) == before, f"rc={r.returncode}")

        # C4·C5 / L2 — 증거는 인용이 아니라 검사다.
        # 거짓값은 반드시 '그럴듯한' 것이어야 한다: C003-other는 실재하므로 스키마 검사(R6)를
        # 그대로 통과한다. 증거 검사가 없으면 **오직 이것만이** 통과해버린다.
        # (없는 사이클을 쓰면 fsck가 대신 막아줘서 이 조항이 시험되지 않는다 — 심층 방어가 변이를 가린다.)
        d, _ = sealed("cor-evidence")
        before = snapshot(d)
        r_no = impl.run(d, "correct", "demo/C002-second", "--field", "parent", "--to", "C001-first",
                        "--author", "fx")                                     # 증거 없음
        r_lie = impl.run(d, "correct", "demo/C002-second", "--field", "parent", "--to", "C003-other",
                         "--evidence", "1-hypothesis.md", "--author", "fx")   # 실재하나 문서가 증언하지 않는 값
        check("CORRECT-EVIDENCE-REQUIRED", "증거 없는/증언되지 않는 정정 거부 (L2 — 스키마상 합법인 거짓도)",
              r_no.returncode != 0 and r_lie.returncode != 0 and snapshot(d) == before,
              f"rc={r_no.returncode}/{r_lie.returncode}")

        # L3 — 정정은 지우개가 아니라 각주다. **두 번** 정정해야 덧붙임과 덮어쓰기가 구별된다:
        # 한 번만 해서는 과거의 기록을 지우는 구현도 똑같이 통과한다.
        d, _ = sealed("cor-record")
        r = impl.run(d, *OK_ARGS)                                   # ① parent: null → C001-first
        r2 = impl.run(d, "correct", "demo/C002-second", "--field", "author", "--to", "weft",
                      "--evidence", "1-hypothesis.md:4", "--author", "weft",
                      "--date", "2026-01-05")                       # ② author: fx → weft
        y = open(os.path.join(d, f"{CYC}/cycle.yaml"), encoding="utf-8").read()
        cpath = os.path.join(d, f"{CYC}/corrections.yaml")
        rec = open(cpath, encoding="utf-8").read() if os.path.isfile(cpath) else ""
        check("CORRECT-RECORD", "정정 2회: 색인 수리 + 계수 + **모든** 거짓값(from) 영구 보존 (L3 — 덧붙임)",
              r.returncode == 0 and r2.returncode == 0
              and re.search(r"^parent: C001-first\s*$", y, flags=re.M) is not None
              and re.search(r"^author: weft\s*$", y, flags=re.M) is not None
              and re.search(r"^corrections: 2\s*$", y, flags=re.M) is not None
              and re.search(r"^\s*from: null\s*$", rec, flags=re.M) is not None    # ①의 거짓
              and re.search(r"^\s*from: fx\s*$", rec, flags=re.M) is not None      # ②의 거짓 — 지워지지 않았다
              and re.search(r"^\s*to: C001-first\s*$", rec, flags=re.M) is not None,
              (r.stderr or r2.stderr or "").strip()[-140:])

        # 정정한 자는 위조자가 되지 않는다 — 태그 이동 (§4)
        r_v = impl.run(d, "verify")
        r_f = impl.run(d, "fsck")
        check("CORRECT-TAG-MOVE", "정정 후 verify OK (태그 이동) + fsck 위반 0 — 다중루트 해소",
              r_v.returncode == 0 and r_f.returncode == 0,
              (r_v.stderr or r_f.stderr or "").strip()[-140:])

        # 기각 조건 1 — 정정이 위조의 뒷문이 되면 안 된다: 정정 후에도 변조는 잡힌다
        with open(os.path.join(d, f"{CYC}/5-report.md"), "a", encoding="utf-8") as f:
            f.write("(몰래 수정)\n")
        r = impl.run(d, "verify")
        check("CORRECT-VERIFY-STILL-CATCHES", "정정 후에도 문서 변조를 verify가 탐지 (불변성 보증 생존)",
              r.returncode != 0)

        # C6 — 이미 변조된 사이클은 정정으로 세탁할 수 없다
        d, _ = sealed("cor-tamper")
        with open(os.path.join(d, f"{CYC}/5-report.md"), "a", encoding="utf-8") as f:
            f.write("(몰래 수정)\n")
        r = impl.run(d, *OK_ARGS)
        y = open(os.path.join(d, f"{CYC}/cycle.yaml"), encoding="utf-8").read()
        check("CORRECT-TAMPER-GUARD", "이미 변조된 사이클의 정정 거부 (변조 세탁 뒷문 차단)",
              r.returncode != 0 and "parent: null" in y, f"rc={r.returncode}")

        # §4 태그 이동 규약은 supersede에도 적용된다 (v0.4/C035) — 그런데 지금껏 아무도 판정하지 않았다.
        # C041의 변이 시험이 우연히 밟아서 드러났다: 판정기가 안 보는 계약은 없는 계약이다 (Weft).
        d, _ = sealed("sup-tag")
        r = impl.run(d, "supersede", "demo/C002-second", "demo/C003-other")
        r_v = impl.run(d, "verify")
        check("SUPERSEDE-TAG-MOVE", "supersede([migrate]) 후 verify OK — 태그 이동 규약 (§4)",
              r.returncode == 0 and r_v.returncode == 0,
              (r.stderr or r_v.stderr or "").strip()[-140:])

        # ---- 뷰어 자동 갱신 (SPEC §5.2 — loom/C042, maru의 이슈 #16) ----
        # 원장이 자동으로 갱신되면 사람의 창도 자동으로 갱신되어야 한다.
        # 둘 중 하나만 자동인 상태가 가장 나쁘다 — **낡은 화면은 침묵보다 나쁘다.**
        def viewer_repo(name, with_viewer=True, title=None):
            d = make_sandbox(os.path.join(work, name))

            def gg(*cli):
                return subprocess.run(["git", "-C", d, *cli], capture_output=True, text=True)

            gg("init", "-q"); gg("config", "user.name", "fx"); gg("config", "user.email", "fx@t")
            write_cycle(d, "demo", "C001-first", step="1")
            if with_viewer:  # 사용자가 뷰어를 굽는다 = "나는 뷰어를 쓴다"는 선언
                cli = ["web", "-o", "chains.html"]
                if title:
                    cli += ["--title", title]
                impl.run(d, *cli)
            gg("add", "-A"); gg("commit", "-q", "-m", "seed")
            return d, gg

        def viewer_json(d, name="chains.html"):
            p = os.path.join(d, name)
            if not os.path.isfile(p):
                return None
            m = re.search(r'id="gil-data">(.*?)</script>', open(p, encoding="utf-8").read(), re.S)
            return json.loads(m.group(1)) if m else None

        d, gg = viewer_repo("web-auto")
        r = impl.run(d, "step", "demo", "C001-first", "2")
        j = viewer_json(d)
        check("WEB-AUTO-REFRESH", "뷰어가 있으면 step이 그것을 다시 굽는다 (창이 원장을 따른다)",
              r.returncode == 0 and j is not None
              and j["chains"]["demo"]["cycles"]["C001-first"]["step"] == "2",
              (r.stderr or "").strip()[-140:])

        # 뷰어는 사이클이 아니다 — 태그가 사이클 밖의 것을 봉인하면 안 된다 (§4)
        cycle_commit = gg("show", "--name-only", "--format=", "HEAD~1").stdout.split()
        web_commit = gg("show", "--name-only", "--format=", "HEAD").stdout.split()
        check("WEB-AUTO-PURE-COMMIT", "사이클 커밋에 뷰어가 섞이지 않는다 (뷰어는 별도 커밋)",
              cycle_commit and all(p.startswith("rooms/experiment/chains/demo/C001-first") for p in cycle_commit)
              and web_commit == ["chains.html"],
              f"cycle={cycle_commit} web={web_commit}")

        # 강요 금지: 뷰어를 안 쓰는 사람에게는 아무 파일도 생기지 않는다
        d2, _ = viewer_repo("web-none", with_viewer=False)
        before = snapshot(d2)
        impl.run(d2, "step", "demo", "C001-first", "2")
        impl.run(d2, "close", "demo", "C001-first", "--date", "2026-01-09", "--verdict", "supported")
        htmls = [f for f in os.listdir(d2) if f.endswith(".html")]
        check("WEB-AUTO-NONE", "뷰어가 없으면 아무 HTML도 만들지 않는다 (도구는 뷰어를 강요하지 않는다)",
              htmls == [] and len(snapshot(d2)) >= len(before))

        # 자기보고: 산출물이 자기를 어떻게 다시 굽는지 스스로 말한다 (추측하지 않는다)
        d3, _ = viewer_repo("web-meta", title="maru의 체인")
        before3 = open(os.path.join(d3, "chains.html"), encoding="utf-8").read()
        impl.run(d3, "step", "demo", "C001-first", "2")
        j3 = viewer_json(d3)
        impl.run(d3, "step", "demo", "C001-first", "3", "--no-web")   # opt-out
        after3 = viewer_json(d3)
        check("WEB-BAKE-META", "재굽기가 사용자의 --title을 보존(bake 자기보고) + --no-web은 손대지 않는다",
              j3 is not None and j3.get("bake", {}).get("title") == "maru의 체인"
              and j3["chains"]["demo"]["cycles"]["C001-first"]["step"] == "2"
              and after3["chains"]["demo"]["cycles"]["C001-first"]["step"] == "2",  # --no-web → 3이 아니다
              f"bake={j3.get('bake') if j3 else None}")

        # R13 — 정정 기록의 무결성은 fsck가 집행한다 (기록 없는 정정 = 지우개)
        d, _ = sealed("cor-r13")
        ypath = os.path.join(d, f"{CYC}/cycle.yaml")
        with open(ypath, "a", encoding="utf-8") as f:
            f.write("corrections: 1\n")   # 계수만 있고 기록이 없다
        r = impl.run(d, "fsck")
        check("FSCK-R13", "corrections N>0인데 corrections.yaml이 없으면 위반 (R13)",
              r.returncode != 0, f"rc={r.returncode}")

    shutil.rmtree(work, ignore_errors=True)
    total, passed = len(RESULTS), sum(RESULTS)
    print(f"\n계약 준수: {passed}/{total}" + ("  ✔ 이 구현은 gil이다" if passed == total else "  ✘ 계약 위반"))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
