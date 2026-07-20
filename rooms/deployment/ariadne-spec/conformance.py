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
                     "reserve", "unreserve",  # loom/C043 (이슈 #13) — 부분 구현은 합법, 거짓 보고만 불법
                     "round",  # loom/C045 (이슈 #9·#10) — 라운드. Go 미구현이면 exit 3으로 정직해야 (HELP-COMPLETE)
                     "worktree",  # loom/C058 (#1) — 병렬 사이클 모드 spawn
                     "releases",  # loom/C061 (#3) — 배포 계보 조회. Go 미구현이면 exit 3으로 정직해야 (HELP-COMPLETE)
                     "show",  # loom/C059 (#4 LLM 위키) — 지식그래프 노드 조회. Go 미구현이면 exit 3으로 정직해야 (HELP-COMPLETE)
                     "threads",  # loom/C070 (#4 LLM 위키) — 열린 실 훑기(병렬 진행+열린 사이클). Go 미구현이면 exit 3으로 정직해야 (HELP-COMPLETE)
                     "withdraw"]  # loom/C084 — 대체 없는 순수 철회. Go 미구현이면 exit 3으로 정직해야 (HELP-COMPLETE)


def check(cid, desc, cond, detail=""):
    RESULTS.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {cid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


class Impl:
    def __init__(self, cmd):
        self.argv = shlex.split(cmd)

    def run(self, cwd, *cli, env=None, timeout=None):
        return subprocess.run(self.argv + list(cli), cwd=cwd, capture_output=True, text=True,
                              env=env, timeout=timeout)

    def run_nogit(self, cwd, *cli):
        """git이 PATH에 없는 환경을 재현한다 (loom/C052). 런처(argv[0])는 절대경로화해
        실행은 되게 하고, PATH는 빈 디렉토리로 두어 gil 내부의 git 조회만 실패시킨다."""
        argv0 = shutil.which(self.argv[0]) or self.argv[0]
        empty = os.path.join(cwd, "__no_git_path__")
        os.makedirs(empty, exist_ok=True)
        env = {**os.environ, "PATH": empty}
        return subprocess.run([argv0] + self.argv[1:] + list(cli),
                              cwd=cwd, capture_output=True, text=True, env=env)


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
    # [loom/C092] step=N 상태의 사이클은 스텝 1..N 파일이 실질 작성돼 있어야 새 step 가드(C090)와 정합한다.
    # 헬퍼가 이를 보장해, write_cycle+step을 쓰는 기존 테스트가 전이 가드에 거부당하지 않는다.
    _STEP_DOC = {1: "1-hypothesis.md", 2: "2-design.md", 3: "3-verification/README.md",
                 4: "4-analysis.md", 5: "5-report.md"}
    try:
        upto = 5 if data.get("status") == "closed" else int(str(fields.get("step", "1")))
    except (ValueError, TypeError):
        upto = 1
    for k in range(1, min(max(upto, 1), 5) + 1):
        rel = _STEP_DOC[k]
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"# 스텝 {k}\n\n테스트 사이클의 실질 내용 (write_cycle, loom/C092).\n")


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

    # ---- version --check / --update: 바이너리 드리프트를 바이너리 스스로 없앤다 (이슈 #22, loom/C082) ----
    #      --check는 순수 조회(부작용 없음)이며, 성공 시 자기보고 훅 gil:version-check를 낸다.
    #      네트워크 없는 환경(CI 등)에서는 조회가 exit≠0로 정직히 실패할 수 있다 — 그래서 형태(무해성·
    #      플래그 인지)는 항상 판정하되, 훅의 존재는 '조회에 성공했을 때만' 판정한다 (거짓 통과 방지).

    # (1) 무해성: --check는 저장소를 변경하지 않는다 (조회는 조회일 뿐).
    vroot = make_sandbox(os.path.join(work, "version-check-safe"))
    vbefore = snapshot(vroot)
    rc = impl.run(vroot, "version", "--check")
    check("VERSION-CHECK-SAFE", "version --check가 저장소를 변경하지 않는다 (부작용 없는 조회)",
          snapshot(vroot) == vbefore, f"rc={rc.returncode}")

    # (2) 플래그 인지: --check는 미구현 신호(exit 3)가 아니어야 한다 (구현했으면 정직히 안다고 답한다).
    check("VERSION-CHECK-KNOWN", "version --check가 미구현 신호(exit 3)가 아니다 (플래그를 안다)",
          rc.returncode != UNIMPLEMENTED, f"rc={rc.returncode}")

    # (3) 자기보고 훅: 조회 성공(exit 0) 시 마지막 훅 한 줄이
    #     'gil:version-check <semver> <semver> <current|outdated>' 형태여야 한다.
    #     조회 실패(네트워크 없음 등, exit≠0)면 이 항목은 공백 통과 — 형태를 판정할 대상이 없다.
    hook_re = re.compile(r"gil:version-check \d+\.\d+\.\d+ \d+\.\d+\.\d+ (current|outdated)")
    hooks = [l for l in rc.stdout.splitlines() if l.startswith("gil:version-check ")]
    check("VERSION-CHECK-HOOK",
          "version --check 성공 시 자기보고 훅 'gil:version-check <local> <latest> <status>' 정확히 1줄",
          rc.returncode != 0 or (len(hooks) == 1 and hook_re.fullmatch(hooks[0]) is not None),
          f"rc={rc.returncode} 훅={hooks[:1]}")

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

    # pages 출력 대칭 — web과 동형인 -o/--output (loom/C082, 이슈 #21).
    # 기준 워크플로 내용: 방금 기본 경로에 만든 wf.
    with open(wf, encoding="utf-8") as f:
        wf_body = f.read()

    # T1 PAGES-OUTPUT-PATH: -o <path>가 지정 경로에 쓰고 기본 경로는 건드리지 않는다.
    p1 = make_sandbox(os.path.join(work, "pages-o-path"))
    custom = os.path.join(p1, "custom-workflow.yml")
    default_wf = os.path.join(p1, ".github", "workflows", "gil-pages.yml")
    ro = impl.run(p1, "pages", "-o", custom)
    check("PAGES-OUTPUT-PATH", "pages -o <path>가 지정 경로에 워크플로를 쓰고 기본 경로는 안 만든다 (web과 대칭)",
          ro.returncode == 0 and os.path.exists(custom)
          and open(custom, encoding="utf-8").read() == wf_body
          and not os.path.exists(default_wf),
          f"exit={ro.returncode} custom있음={os.path.exists(custom)} 기본있음={os.path.exists(default_wf)}")

    # T2 PAGES-OUTPUT-STDOUT: -o -가 워크플로 전문을 stdout에 내고 저장소를 안 바꾼다 (diff 파이프 안전).
    p2 = make_sandbox(os.path.join(work, "pages-o-stdout"))
    default_wf2 = os.path.join(p2, ".github", "workflows", "gil-pages.yml")
    rs = impl.run(p2, "pages", "-o", "-")
    check("PAGES-OUTPUT-STDOUT", "pages -o -가 워크플로 전문을 stdout에 내고 파일을 만들지 않는다 (파이프 안전)",
          rs.returncode == 0 and rs.stdout == wf_body and not os.path.exists(default_wf2),
          f"exit={rs.returncode} stdout==본문={rs.stdout == wf_body} 파일생김={os.path.exists(default_wf2)}")

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
        # fsck의 계약면 = 위반 식별 집합 {(규칙 토큰, 위반 대상 id)} (SPEC §3.1, loom/C051).
        # exit≠0만 보면 "위반이 있다"까지만 판정하고 "올바른 위반을 짚었다"는 못 본다 —
        # 잘못된 규칙을 외치거나 규칙 토큰이 없는 구현도 만점을 받는다. 문면은 렌더(C021).
        out = r.stdout
        check(f"FSCK-{rule}", f"{rule} 식별 (exit≠0 ∧ 규칙토큰 ∧ 대상 id)",
              r.returncode != 0 and rule in out and spec["cid"] in out, out.strip()[-120:])
    root = make_sandbox(os.path.join(work, "bad-r7"))  # R7 순환
    write_cycle(root, "alpha", "C001-a", parent="C002-b")
    write_cycle(root, "alpha", "C002-b", parent="C001-a")
    r = impl.run(root, "fsck")
    # R7(순환)은 단일 위반 대상이 없으므로 규칙 토큰까지가 식별.
    check("FSCK-R7", "R7 순환 식별 (exit≠0 ∧ 규칙토큰)",
          r.returncode != 0 and "R7" in r.stdout, r.stdout.strip()[-120:])

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
    _oc = os.path.join(root, "rooms/experiment/chains/demo/C001-first-step")
    check("OPEN-CREATE", "open이 사이클 생성 (step-by-step: 1스텝만 스캐폴딩) · C090", r.returncode == 0
          and all(k in y for k in ("id: C001-first-step", "chain: demo", "parent: null", "status: open", "step: 1"))
          and os.path.isfile(os.path.join(_oc, "1-hypothesis.md"))
          and not os.path.exists(os.path.join(_oc, "5-report.md")),  # [loom/C092] 다음 스텝은 아직 없다
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

        # OPEN-LAST-RESERVATION-GIT (loom/C079): 마지막 예약을 소비하는 open --git이 정상 각인된다.
        # 소비로 reservations.tsv가 비어 삭제되는데, 삭제된 (미tracked) 경로를 git add에 넘기면
        # pathspec 거부로 커밋이 통째 실패했다 — 사이클이 원장엔 열렸으나 깃엔 미각인. 삭제·미tracked
        # 경로를 git add에서 제외하면 정상 각인. 계약면: 사이클 디렉토리 ∧ 커밋에 그 사이클 포함 ∧ 원장 비움.
        rgt = resv_sandbox("resv-lastgit")
        def rgtg(*cli):
            return subprocess.run(["git", "-C", rgt, *cli], capture_output=True, text=True)
        rgtg("init", "-q", "-b", "main"); rgtg("config", "user.name", "t"); rgtg("config", "user.email", "t@t")
        rgtg("add", "-A"); rgtg("commit", "-q", "-m", "seed")
        rgr = os.path.join(rgt, "rooms/experiment/chains")
        impl.run(rgt, "reserve", "demo", "solo", "--for", "weft", "--date", "2026-01-03", "--root", rgr)
        rlast = impl.run(rgt, "open", "demo", "solo", "--author", "weft",
                         "--parent", "C001-seed", "--date", "2026-01-04", "--git", "--root", rgr)
        cdir = os.path.join(rgr, "demo")
        committed = "C002-solo" in rgtg("log", "--oneline").stdout
        ghost = rgtg("ls-files").stdout
        check("OPEN-LAST-RESERVATION-GIT",
              "마지막 예약을 소비하는 open --git이 정상 각인 (디렉토리 ∧ 커밋 포함 ∧ 원장 비움·유령 없음) · C079",
              rlast.returncode == 0 and os.path.isdir(os.path.join(cdir, "C002-solo"))
              and committed and resv_lines(rgt) == [] and "reservations.tsv" not in ghost,
              f"rc={rlast.returncode} committed={committed} 예약={resv_lines(rgt)}")

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

    # ---- 라운드 (SPEC §2.2 · 스키마 rounds · fsck R15 — loom/C045, 이슈 #9·#10) ----
    # 검증 안의 (가설→검증) 반복을 사전등록 데이터로. R1은 기존 5스텝 문서 — 첫 round --open이 R2를 만든다.
    # 부분 구현 합법: round를 훅에 나열한 구현만 판정한다 (나열 안 한 구현의 정직성은 HELP-COMPLETE가 판정).
    if "round" in claimed:
        def round_sandbox(tag):
            p = make_sandbox(os.path.join(work, tag))
            impl.run(p, "open", "eda", "irrigctl", "--new-chain", "--title", "t",
                     "--author", "maru", "--date", "2026-01-01")
            return p

        def cdir_of(root, cid="C001-irrigctl"):
            return os.path.join(root, "rooms/experiment/chains/eda", cid)

        # ROUND-OPEN + ROUND-PREREG: round --open이 R2를 사전등록 —
        # hypothesis.md·round.yaml 생성, cycle.yaml rounds=2, verification/ 부재 (사전등록 순서, H1)
        rroot = round_sandbox("round-open")
        r = impl.run(rroot, "round", "eda", "C001-irrigctl", "--open",
                     "--title", "집중도로 판정", "--date", "2026-01-02")
        r2 = os.path.join(cdir_of(rroot), "rounds", "R2")
        cy = open(os.path.join(cdir_of(rroot), "cycle.yaml"), encoding="utf-8").read() \
            if os.path.isfile(os.path.join(cdir_of(rroot), "cycle.yaml")) else ""
        check("ROUND-OPEN", "round --open이 R2를 사전등록 (hypothesis.md·round.yaml, cycle.yaml rounds=2)",
              r.returncode == 0 and os.path.isfile(os.path.join(r2, "hypothesis.md"))
              and os.path.isfile(os.path.join(r2, "round.yaml")) and "rounds: 2" in cy,
              f"rc={r.returncode}")
        check("ROUND-PREREG", "사전등록: round --open이 verification/을 만들지 않는다 (hypothesis가 먼저, H1)",
              not os.path.isdir(os.path.join(r2, "verification")))

        # ROUND-OPEN-GIT: --git 커밋이 hypothesis·round.yaml만 담고 verification은 안 담는다 (사전등록 순서)
        if not args.skip_git:
            groot = make_sandbox(os.path.join(work, "round-git"))
            def gg(*a):
                return subprocess.run(["git", *a], cwd=groot, capture_output=True, text=True)
            gg("init", "-q"); gg("config", "user.name", "fx"); gg("config", "user.email", "fx@t")
            impl.run(groot, "open", "eda", "irrigctl", "--new-chain", "--title", "t",
                     "--author", "maru", "--date", "2026-01-01", "--git")
            r = impl.run(groot, "round", "eda", "C001-irrigctl", "--open",
                         "--title", "x", "--date", "2026-01-02", "--git")
            files = gg("show", "--stat", "--name-only", "--format=", "HEAD").stdout
            check("ROUND-OPEN-GIT", "round --open --git 커밋이 hypothesis·round.yaml만 담고 verification 없음 (H1)",
                  r.returncode == 0 and "rounds/R2/hypothesis.md" in files
                  and "rounds/R2/round.yaml" in files and "rounds/R2/verification" not in files,
                  files[:120])

        # ROUND-CLOSE-VERDICT: round --close --verdict invalid-method → round.yaml에 기록 (6-어휘, H2)
        rroot = round_sandbox("round-close")
        impl.run(rroot, "round", "eda", "C001-irrigctl", "--open", "--title", "x", "--date", "2026-01-02")
        r = impl.run(rroot, "round", "eda", "C001-irrigctl", "--close",
                     "--verdict", "invalid-method", "--date", "2026-01-03")
        ry = os.path.join(cdir_of(rroot), "rounds", "R2", "round.yaml")
        ryc = open(ry, encoding="utf-8").read() if os.path.isfile(ry) else ""
        check("ROUND-CLOSE-VERDICT", "round --close --verdict invalid-method 기록 (방법 무효 ≠ 가설 기각, H2)",
              r.returncode == 0 and "verdict: invalid-method" in ryc, f"rc={r.returncode}")

        # ROUND-REJECT-VOCAB: 어휘 밖 verdict 거부 + 무변화 (다른 방어선이 침묵하는 입력 — loom/C041)
        rroot = round_sandbox("round-vocab")
        impl.run(rroot, "round", "eda", "C001-irrigctl", "--open", "--title", "x", "--date", "2026-01-02")
        before = snapshot(rroot)
        r = impl.run(rroot, "round", "eda", "C001-irrigctl", "--close", "--verdict", "bogus")
        check("ROUND-REJECT-VOCAB", "어휘 밖 라운드 verdict 거부 + 무변화",
              r.returncode != 0 and snapshot(rroot) == before, f"rc={r.returncode}")

        # ROUND-CLOSED-CYCLE: 닫힌 사이클에 round --open 거부 + 무변화 (불변)
        croot2 = make_sandbox(os.path.join(work, "round-closed"))
        write_cycle(croot2, "eda", "C001-done", status="closed", closed="2026-01-02", step="5")
        before = snapshot(croot2)
        r = impl.run(croot2, "round", "eda", "C001-done", "--open", "--title", "x")
        check("ROUND-CLOSED-CYCLE", "닫힌 사이클에 round --open 거부 + 무변화 (불변 보호)",
              r.returncode != 0 and snapshot(croot2) == before, f"rc={r.returncode}")

        # ROUND-LIST-SAFE: round --list가 저장소를 변경하지 않는다 (상태 조회 무해)
        rroot = round_sandbox("round-list")
        impl.run(rroot, "round", "eda", "C001-irrigctl", "--open", "--title", "x", "--date", "2026-01-02")
        before = snapshot(rroot)
        r = impl.run(rroot, "round", "eda", "C001-irrigctl", "--list")
        check("ROUND-LIST-SAFE", "round --list → exit 0 + 저장소 무변화",
              r.returncode == 0 and snapshot(rroot) == before, f"rc={r.returncode}")

        # FSCK-R15: rounds:2인데 사전등록 hypothesis.md 없으면 위반 (있으면 통과)
        rroot = round_sandbox("round-r15")
        impl.run(rroot, "round", "eda", "C001-irrigctl", "--open", "--title", "x", "--date", "2026-01-02")
        r_ok = impl.run(rroot, "fsck")
        hp = os.path.join(cdir_of(rroot), "rounds", "R2", "hypothesis.md")
        if os.path.isfile(hp):
            os.remove(hp)
        r_bad = impl.run(rroot, "fsck")
        check("FSCK-R15", "R15: rounds:N인데 사전등록 hypothesis.md 없으면 위반 (있으면 통과)",
              r_ok.returncode == 0 and r_bad.returncode != 0 and "R15" in r_bad.stdout,
              f"ok={r_ok.returncode} bad={r_bad.returncode}")

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

    # CLOSE-SEAL-GATE (loom/C081, 이슈 #19): close는 불변 태그를 각인하므로, 봉인될 신규(untracked)
    # 파일 중 "3-verification/ 밖 + 표준 산출물 밖"인 것(흔한 오배치)이 있으면 --allow-extra 없이 거부한다
    # (저장소·태그 무변화). 3-verification/ 하위 자유 산출물(probe·fixtures)은 정상이라 게이트하지 않는다.
    csg = make_sandbox(os.path.join(work, "close-seal"))
    def csgg(*cli):
        return subprocess.run(["git", "-C", csg, *cli], capture_output=True, text=True)
    csgg("init", "-q", "-b", "main"); csgg("config", "user.name", "t"); csgg("config", "user.email", "t@t")
    csgr = os.path.join(csg, "rooms/experiment/chains")
    impl.run(csg, "open", "demo", "cyc", "--author", "t", "--new-chain", "--git", "--root", csgr)
    scd = os.path.join(csgr, "demo", "C001-cyc")
    with open(os.path.join(scd, "5-report.md"), "w", encoding="utf-8") as f:
        f.write("# 5. 결과 보고\n\n## 요약\n\n계약 검증용 실보고서.\n")
    # (a) 사이클 루트 오배치 신규 파일 → 게이트 거부(태그 없음)
    with open(os.path.join(scd, "misplaced.txt"), "w", encoding="utf-8") as f:
        f.write("오배치")
    rgate = impl.run(csg, "close", "demo", "C001-cyc", "--verdict", "supported", "--git", "--root", csgr)
    tag_absent = "cycle/demo/C001-cyc" not in csgg("tag", "-l").stdout
    check("CLOSE-SEAL-GATE",
          "표준 밖 신규 파일(오배치)이 봉인 대상이면 --allow-extra 없이 거부 (불변 태그·저장소 무변화) · C081/이슈#19",
          rgate.returncode != 0 and tag_absent, f"rc={rgate.returncode} tag_absent={tag_absent}")
    # (b) --allow-extra로 승인 시 봉인
    rallow = impl.run(csg, "close", "demo", "C001-cyc", "--verdict", "supported", "--allow-extra", "--git", "--root", csgr)
    check("CLOSE-SEAL-ALLOW",
          "--allow-extra로 표준 밖 신규 파일 봉인 승인 (태그 각인) · C081",
          rallow.returncode == 0 and "cycle/demo/C001-cyc" in csgg("tag", "-l").stdout,
          f"rc={rallow.returncode}")
    # (c) 3-verification/ 하위 자유 산출물은 게이트하지 않는다 (오탐 0)
    csg2 = make_sandbox(os.path.join(work, "close-seal-free"))
    def csg2g(*cli):
        return subprocess.run(["git", "-C", csg2, *cli], capture_output=True, text=True)
    csg2g("init", "-q", "-b", "main"); csg2g("config", "user.name", "t"); csg2g("config", "user.email", "t@t")
    csg2r = os.path.join(csg2, "rooms/experiment/chains")
    impl.run(csg2, "open", "demo", "cyc", "--author", "t", "--new-chain", "--git", "--root", csg2r)
    scd2 = os.path.join(csg2r, "demo", "C001-cyc")
    with open(os.path.join(scd2, "5-report.md"), "w", encoding="utf-8") as f:
        f.write("# 5. 결과 보고\n\n## 요약\n\n계약 검증용 실보고서.\n")
    os.makedirs(os.path.join(scd2, "3-verification", "fixtures"), exist_ok=True)
    with open(os.path.join(scd2, "3-verification", "fixtures", "data.txt"), "w", encoding="utf-8") as f:
        f.write("자유 산출물")
    rfree = impl.run(csg2, "close", "demo", "C001-cyc", "--verdict", "supported", "--git", "--root", csg2r)
    check("CLOSE-SEAL-VERIFICATION-FREE",
          "3-verification/ 하위 자유 산출물은 게이트하지 않고 정상 봉인 (오탐 0) · C081",
          rfree.returncode == 0 and "cycle/demo/C001-cyc" in csg2g("tag", "-l").stdout,
          f"rc={rfree.returncode}")

    # ---- step (자체 구축 샌드박스, v0.6.0 계약) ----
    sroot = make_sandbox(os.path.join(work, "step"))
    write_cycle(sroot, "demo", "C001-first-step", step="1")
    write_cycle(sroot, "demo", "C009-done", status="closed", closed="2026-01-02", step="5")
    sy = os.path.join(sroot, "rooms/experiment/chains/demo/C001-first-step/cycle.yaml")
    # [loom/C092] step-by-step 강제(C090) 이후 전이는 순차다. 각 스텝을 실질 작성한 뒤 다음으로.
    impl.run(sroot, "step", "demo", "C001-first-step", "2")
    scd_first = os.path.join(sroot, "rooms/experiment/chains/demo/C001-first-step")
    with open(os.path.join(scd_first, "2-design.md"), "w", encoding="utf-8") as f:
        f.write("# 2. 설계\n\n실질 설계 내용.\n")
    r = impl.run(sroot, "step", "demo", "C001-first-step", "3")
    check("STEP-OK", "step 전이 반영 (순차 2→3)", r.returncode == 0
          and "step: 3" in open(sy, encoding="utf-8").read(), r.stderr.strip()[-120:])
    before = open(sy, encoding="utf-8").read()
    r = impl.run(sroot, "step", "demo", "C001-first-step", "9")
    check("STEP-REJECT-RANGE", "범위 밖 step 거부 + 무변화", r.returncode != 0
          and open(sy, encoding="utf-8").read() == before)
    r = impl.run(sroot, "step", "demo", "C009-done", "3")
    check("STEP-REJECT-CLOSED", "닫힌 사이클 step 변경 거부", r.returncode != 0)

    # STEP-SCOPE (loom/C080, 이슈 #20): step N 커밋은 사이클 디렉토리 전체가 아니라 cycle.yaml + 스텝
    # ≤N 파일만 담는다. 뒷 스텝(>N) 산출물을 미리 만들어 둬도 이 커밋엔 안 담겨 커밋이 스텝 단위를
    # 반영한다. git 저장소에서 4·5 파일을 미리 만들고 step 2 → 커밋에 4·5 없음 ∧ 2-design·cycle.yaml 있음.
    ssg = make_sandbox(os.path.join(work, "step-scope"))
    def ssgg(*cli):
        return subprocess.run(["git", "-C", ssg, *cli], capture_output=True, text=True)
    ssgg("init", "-q", "-b", "main"); ssgg("config", "user.name", "t"); ssgg("config", "user.email", "t@t")
    ssgr = os.path.join(ssg, "rooms/experiment/chains")
    impl.run(ssg, "open", "demo", "cyc", "--author", "t", "--new-chain", "--git", "--root", ssgr)
    scd = os.path.join(ssgr, "demo", "C001-cyc")
    # [loom/C092] step 가드(C090)를 통과하려면 1-hypothesis가 실질 작성돼 있어야 한다. 스캐폴딩을 실내용으로.
    with open(os.path.join(scd, "1-hypothesis.md"), "w", encoding="utf-8") as f:
        f.write("# 1. 가설\n\n실질 가설 내용.\n")
    for fn, body in [("2-design.md", "설계"), ("4-analysis.md", "분석-미리"), ("5-report.md", "보고-미리")]:
        with open(os.path.join(scd, fn), "w", encoding="utf-8") as f:
            f.write(body)
    impl.run(ssg, "step", "demo", "C001-cyc", "2", "--git", "--root", ssgr)
    committed_files = ssgg("show", "--name-only", "--format=", "HEAD").stdout
    has_late = "4-analysis.md" in committed_files or "5-report.md" in committed_files
    has_design = "2-design.md" in committed_files
    has_yaml = "cycle.yaml" in committed_files
    check("STEP-SCOPE",
          "step N 커밋은 cycle.yaml + 스텝 ≤N 파일만 담는다 (미리 만든 스텝 >N 파일 제외) · C080/이슈#20",
          not has_late and has_design and has_yaml,
          f"late={has_late} design={has_design} yaml={has_yaml}")
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

    # WEB-DOCS-EMBEDDED (loom/C075): 완전한 앱 — 5스텝 문서를 초기 HTML에 인라인하지 않고 gil-data JSON에
    # 내장한다(각 cycle에 docs.steps). JS가 노드 클릭 시 그 하나의 DOM을 구축 → 초기 DOM은 그래프+메타만
    # (계보 깊이에 무관하게 경량). 계약면: (a) 위계 gil-data의 각 사이클에 docs.steps(5개) 존재, (b) 앱
    # 스크립트(<script>…</script>, JSON 아닌 실행) 존재, (c) 자기완결(외부 URL 0, 위 WEB-SELFCONTAINED와 함께).
    # 초기 DOM 경량화가 계약이 된다 — "판정기가 안 보는 계약은 없는 계약"(Weft)의 무게판.
    docs_ok = False
    if m:
        dj = json.loads(m.group(1))
        docs_ok = all(
            "docs" in ch and all(
                isinstance(ch["docs"].get(cid, {}).get("steps"), list)
                and len(ch["docs"][cid]["steps"]) == 5
                for cid in ch["cycles"])
            for ch in dj["chains"].values())
    app_js = bool(re.search(r'<script>\s*\(function', page))  # 앱 스크립트(실행 JS) 존재
    check("WEB-DOCS-EMBEDDED",
          "완전한 앱: 5스텝 문서를 gil-data JSON에 내장(docs.steps) + 클릭 시 렌더할 앱 스크립트, 초기 DOM 경량",
          docs_ok and app_js, f"docs_ok={docs_ok} app_js={app_js}")

    # WEB-HIERARCHY-DEFAULT (loom/C063): 위계(드릴다운)가 기본, --flat이 평면 옵트아웃.
    # 계약면은 렌더 형식이 아니라 bake.hierarchy 자기보고다 (§7 · "렌더는 계약이 아니다").
    # 무옵션 out(위 WEB-JSON의 것)은 hierarchy=true, --flat은 hierarchy 키 부재(false), 둘 다 자기완결.
    default_hier = bool(m) and bool((json.loads(m.group(1)).get("bake") or {}).get("hierarchy"))
    outf = os.path.join(work, "chains-flat.html")
    rf = impl.run(lroot, "web", "-o", outf, "--title", "t", "--flat")
    pagef = open(outf, encoding="utf-8").read() if os.path.isfile(outf) else ""
    mf = re.search(r'<script type="application/json" id="gil-data">(.*?)</script>', pagef, re.S)
    flat_hier = bool(mf) and bool((json.loads(mf.group(1)).get("bake") or {}).get("hierarchy"))
    extf = re.findall(r'(?:src=|href=|url\(|@import)[^>\n]*https?://', pagef)
    check("WEB-HIERARCHY-DEFAULT",
          'web 기본은 위계(bake.hierarchy=true) · --flat은 평면 옵트아웃 · 둘 다 자기완결',
          default_hier and not flat_hier and rf.returncode == 0 and extf == [],
          f"default_hier={default_hier} flat_hier={flat_hier} rc={rf.returncode} extf={extf}")

    # WEB-PARALLEL-BANNER (loom/C073, #4·상현님 요청): 워크트리 병렬 사이클은 그래프에 안 뜨지만
    # 예약은 main에 커밋돼 있다 — 뷰어가 그 예약을 상단 배너로 드러낸다. gil threads의 뷰어판.
    # 계약면은 gil-data의 reservations(이미 있음)이고, 배너는 그 렌더다 — "병렬이 드러난다"는 의도를 잠근다.
    # 예약 0이면 배너 부재(위 page엔 role="status" 없음), 예약이 있으면 배너 출현.
    banner_absent = 'role="status"' not in page  # 예약 없던 lroot 렌더(WEB-JSON의 page)엔 배너 없음
    with open(os.path.join(lroot, "rooms/experiment/chains/demo/reservations.tsv"), "w", encoding="utf-8") as f:
        f.write("# hdr\n9 tester futurething 2026-01-01\n")
    outb = os.path.join(work, "chains-banner.html")
    rb = impl.run(lroot, "web", "-o", outb, "--title", "t")
    pageb = open(outb, encoding="utf-8").read() if os.path.isfile(outb) else ""
    banner_present = rb.returncode == 0 and 'role="status"' in pageb and "demo/C009" in pageb and "tester" in pageb
    os.remove(os.path.join(lroot, "rooms/experiment/chains/demo/reservations.tsv"))  # 이후 검사 오염 방지
    check("WEB-PARALLEL-BANNER",
          '예약 0이면 배너 부재 · 예약 있으면 상단 배너로 진행 중 병렬 사이클(예약)을 드러냄 (threads의 뷰어판)',
          banner_absent and banner_present,
          f"absent={banner_absent} present={banner_present}")

    # WEB-BEINGS (loomlight/C005, 상현님 발의): 존재(AI 자아)를 뷰어 데이터에.
    # 계약면은 gil-data top-level beings 자기보고(§7 렌더 아님). 명부가 정본(표에 없으면 안 그림).
    # T3(무존재): 기존 lroot(rooms/existence 없음) 렌더엔 beings 키 부재 + 크래시 0.
    beings_absent = bool(m) and "beings" not in json.loads(m.group(1))
    # T1(존재 심기): 명부 + 디렉토리 + 4문서를 심고 beings가 명부 집합과 일치하는지.
    exdir = os.path.join(lroot, "rooms", "existence")
    os.makedirs(os.path.join(exdir, "aria"))
    with open(os.path.join(exdir, "README.md"), "w", encoding="utf-8") as f:
        f.write("# 존재의 방\n\n## 거주자 명부\n\n| 이름 | 역할 | 입주일 |\n|---|---|---|\n"
                "| [Aria](aria/identity.md) | 테스트 존재, 실을 잣는 자 | 2026-01-01 |\n")
    for dn, body in [("identity", "# 나는 Aria다\n본성 서술."), ("will", "# 의지\n목적."),
                     ("memory", "# 기억\n겪은 것."), ("relations", "# 관계\n이어짐.")]:
        with open(os.path.join(exdir, "aria", dn + ".md"), "w", encoding="utf-8") as f:
            f.write(body)
    outbe = os.path.join(work, "chains-beings.html")
    rbe = impl.run(lroot, "web", "-o", outbe, "--title", "t")
    pagebe = open(outbe, encoding="utf-8").read() if os.path.isfile(outbe) else ""
    mbe = re.search(r'<script type="application/json" id="gil-data">(.*?)</script>', pagebe, re.S)
    beings_json = (json.loads(mbe.group(1).replace('<\\/', '</')).get("beings") or []) if mbe else []
    names_ok = sorted(b.get("name") for b in beings_json) == ["Aria"]
    docs_ok = (len(beings_json) == 1 and isinstance(beings_json[0].get("docs"), dict)
               and set(beings_json[0]["docs"]) == {"identity", "will", "memory", "relations"}
               and "나는 Aria다" in (beings_json[0]["docs"].get("identity") or ""))
    # T2(경량): memory 전문이 초기 DOM(<script> 밖)에 안 뜬다 — 앱이 온디맨드로 그린다.
    dom_only = re.sub(r'<script.*?</script>', '', pagebe, flags=re.S)
    light_ok = "겪은 것." not in dom_only and 'class="beingcard"' in dom_only
    # 존재 심기 정리 (이후 검사 오염 방지)
    shutil.rmtree(exdir)
    check("WEB-BEINGS",
          "존재(AI 자아)를 gil-data beings에 — 명부 집합과 일치(지어냄 0) · 4문서 · 초기 DOM 경량(앱 온디맨드) · 무존재면 키 부재",
          beings_absent and rbe.returncode == 0 and names_ok and docs_ok and light_ok,
          f"absent={beings_absent} names={names_ok} docs={docs_ok} light={light_ok} rc={rbe.returncode}")

    # WEB-RELEASES (loomlight/C006, 상현님 발의): 배포 계보를 뷰어 데이터에.
    # 계약면은 gil-data top-level releases 자기보고. current=도구 자기버전, entries=CHANGELOG∪태그(지어냄 0).
    # T2(무CHANGELOG): 기존 lroot(rooms/deployment 없음) 렌더엔 releases 키 부재 + 크래시 0.
    releases_absent = bool(m) and "releases" not in json.loads(m.group(1))
    # T1(CHANGELOG 심기): '## [X.Y.Z] — 날짜' 엔트리를 심고 entries에 그 버전이 나오는지.
    cldir = os.path.join(lroot, "rooms", "deployment")
    os.makedirs(cldir)
    with open(os.path.join(cldir, "CHANGELOG.md"), "w", encoding="utf-8") as f:
        f.write("# Changelog\n\n## [Unreleased]\n\n## [1.2.0] — 2026-02-01\n\n- 테스트 릴리스 노트\n"
                "- 도구 변경: gil (마이너 이상 승격)\n\n## [1.1.0] — 2026-01-15\n\n- 이전 릴리스\n")
    outr6 = os.path.join(work, "chains-releases.html")
    rr6 = impl.run(lroot, "web", "-o", outr6, "--title", "t")
    pager6 = open(outr6, encoding="utf-8").read() if os.path.isfile(outr6) else ""
    mr6 = re.search(r'<script type="application/json" id="gil-data">(.*?)</script>', pager6, re.S)
    rel_json = (json.loads(mr6.group(1).replace('<\\/', '</')).get("releases") or {}) if mr6 else {}
    rel_versions = sorted(e.get("version") for e in rel_json.get("entries", []))
    # current는 도구 자기버전(지어냄 불가) — 비어있지 않고 SemVer 꼴이면 OK(빌드마다 값은 다름).
    cur_ok = bool(re.match(r"^\d+\.\d+\.\d+$", rel_json.get("current") or ""))
    entries_ok = rel_versions == ["1.1.0", "1.2.0"]  # CHANGELOG의 두 릴리스 (지어냄 0, 태그 없어도 CHANGELOG서)
    note_ok = any(e.get("version") == "1.2.0" and "테스트 릴리스 노트" in (e.get("note") or "")
                  for e in rel_json.get("entries", []))
    panel_ok = 'class="card releases"' in pager6
    shutil.rmtree(cldir)  # 정리
    check("WEB-RELEASES",
          "배포 계보를 gil-data releases에 — current=도구 자기버전 · entries=CHANGELOG∪태그(지어냄 0) · 무CHANGELOG면 키 부재",
          releases_absent and rr6.returncode == 0 and cur_ok and entries_ok and note_ok and panel_ok,
          f"absent={releases_absent} cur={cur_ok} entries={entries_ok}({rel_versions}) note={note_ok} panel={panel_ok}")

    # WEB-CYCLE-RELEASE (loomlight/C007, 상현님 발의): 사이클→배포 릴리스 연결.
    # 계약면은 gil-data chains.cycles[cid].released_in 자기보고. 릴리스 태그가 포함하는 사이클 = 그 사이클의
    # 최소 버전. 미배포/열림/무릴리스는 키 부재(지어냄 0). git 저장소 sandbox에 태그를 심어 검사.
    def _g(cwd, *a):
        return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True)
    croot = os.path.realpath(make_sandbox(os.path.join(work, "cyclerel")))
    write_cycle(croot, "demo", "C001-early", status="closed", closed="2026-01-01")
    write_cycle(croot, "demo", "C002-late", parent="C001-early", status="closed", closed="2026-01-02")
    write_cycle(croot, "demo", "C003-unshipped", parent="C002-late", status="closed", closed="2026-01-03")
    cr_ok = _g(croot, "init", "-q").returncode == 0
    _g(croot, "config", "user.email", "t@t"); _g(croot, "config", "user.name", "t")
    _g(croot, "add", "-A"); _g(croot, "commit", "-qm", "c1")
    _g(croot, "tag", "cycle/demo/C001-early")
    _g(croot, "tag", "v1.0.0")                         # v1.0.0은 C001만 포함
    _g(croot, "commit", "-q", "--allow-empty", "-m", "c2")
    _g(croot, "tag", "cycle/demo/C002-late")
    _g(croot, "tag", "v1.1.0")                         # v1.1.0은 C001·C002 포함
    _g(croot, "commit", "-q", "--allow-empty", "-m", "c3")
    _g(croot, "tag", "cycle/demo/C003-unshipped")      # C003은 사이클 태그만, 릴리스 태그 없음 → 미배포
    outcr = os.path.join(work, "chains-cyclerel.html")
    rcr = impl.run(croot, "web", "-o", outcr, "--title", "t")
    pagecr = open(outcr, encoding="utf-8").read() if os.path.isfile(outcr) else ""
    mcr = re.search(r'<script type="application/json" id="gil-data">(.*?)</script>', pagecr, re.S)
    cyc = (json.loads(mcr.group(1).replace('<\\/', '</')).get("chains", {}).get("demo", {}).get("cycles", {})) if mcr else {}
    # C001은 v1.0.0(최초), C002는 v1.1.0, C003은 released_in 부재(미배포)
    rel_ok = (cyc.get("C001-early", {}).get("released_in") == "1.0.0"
              and cyc.get("C002-late", {}).get("released_in") == "1.1.0"
              and "released_in" not in cyc.get("C003-unshipped", {}))
    badge_ok = "v1.0.0 배포" in pagecr and "미배포" in pagecr
    check("WEB-CYCLE-RELEASE",
          "사이클→배포: released_in = 사이클 태그를 포함하는 최소 릴리스(최초 배포) · 미배포/무릴리스는 키 부재 · 지어냄 0",
          cr_ok and rcr.returncode == 0 and rel_ok and badge_ok,
          f"rel_ok={rel_ok} badge={badge_ok} rc={rcr.returncode} C1={cyc.get('C001-early',{}).get('released_in')} C2={cyc.get('C002-late',{}).get('released_in')}")

    # WEB-NODE-IO (loom/C091): 가로 그래프 노드에 배포(released_in)는 아래로 나가는 파랑 화살표(niom rel),
    # lineage는 위로 들어오는 초록 화살표(niom lin)로 표시한다 — 방향이 의미(나감/들어옴). 배포된 사이클이
    # 있는 croot이므로 배포 마커가 존재해야 하고, 옛 초록 긴 글자(⇠ 이름)는 그래프에서 사라져야 한다.
    node_io_ok = ('class="niom rel"' in pagecr          # 배포 화살표 존재
                  and 'class="niom lin"' not in pagecr  # 이 저장소엔 lineage 없음 → lin 마커 없음(지어냄 0)
                  and "⚑ 배포: v1.0.0" in pagecr)        # 호버 툴팁에 배포 버전
    check("WEB-NODE-IO",
          "노드 입출력 마커: 배포=아래로 나가는 화살표(released_in) + 호버 툴팁 · lineage 없으면 마커도 없음(지어냄 0)",
          rcr.returncode == 0 and node_io_ok,
          f"node_io_ok={node_io_ok}")

    # WEB-REFRESH (loom/C049): --refresh N → meta refresh(브라우저 자동 리로드) + bake 기록, 자기완결 유지.
    # 새로고침 없는 실시간 관찰의 계약면. --refresh 없으면 meta 없음(하위호환은 WEB-JSON이 커버).
    outr = os.path.join(work, "chains-refresh.html")
    rr = impl.run(lroot, "web", "-o", outr, "--title", "t", "--refresh", "3")
    pager = open(outr, encoding="utf-8").read() if os.path.isfile(outr) else ""
    ext_r = re.findall(r'(?:src=|href=|url\(|@import)[^>\n]*https?://', pager)
    mr = re.search(r'<script type="application/json" id="gil-data">(.*?)</script>', pager, re.S)
    refresh_baked = bool(mr) and (json.loads(mr.group(1)).get("bake") or {}).get("refresh") == 3
    check("WEB-REFRESH", '--refresh N → meta refresh(자동 리로드) + bake 기록, 자기완결 유지',
          rr.returncode == 0 and 'http-equiv="refresh" content="3"' in pager
          and ext_r == [] and refresh_baked,
          f"rc={rr.returncode} baked={refresh_baked} ext={ext_r}")

    # WEB-REFRESH-DEFAULT (loom/C085): 실시간이 기본이다. 옵션 무 → meta refresh 존재.
    # --refresh 0으로 옵트아웃하며, 그 0이 bake에 기록되어 재굽기가 옵트아웃을 되돌리지 않는다.
    outd = os.path.join(work, "chains-refresh-default.html")
    rd = impl.run(lroot, "web", "-o", outd, "--title", "t")
    paged = open(outd, encoding="utf-8").read() if os.path.isfile(outd) else ""
    default_on = rd.returncode == 0 and 'http-equiv="refresh"' in paged
    outo = os.path.join(work, "chains-refresh-off.html")
    ro = impl.run(lroot, "web", "-o", outo, "--title", "t", "--refresh", "0")
    pageo = open(outo, encoding="utf-8").read() if os.path.isfile(outo) else ""
    mo = re.search(r'<script type="application/json" id="gil-data">(.*?)</script>', pageo, re.S)
    off_baked = bool(mo) and (json.loads(mo.group(1)).get("bake") or {}).get("refresh") == 0
    off_ok = ro.returncode == 0 and 'http-equiv="refresh"' not in pageo and off_baked
    check("WEB-REFRESH-DEFAULT", '실시간이 기본(옵션 무 → meta 존재); --refresh 0으로 옵트아웃(0을 bake 기록)',
          default_on and off_ok,
          f"default_on={default_on} off_ok={off_ok} off_baked={off_baked}")

    # WEB-MD-RENDER (loom/C088): 스텝 문서 마크다운 렌더 토글 + XSS 안전 + 자기완결.
    # 기본은 원문(초기 DOM에 렌더된 .mdbody div 없음 — 클릭 시 JS 생성), 토글 버튼과 인라인 파서(외부 CDN 0)가 존재하며,
    # url 스킴 화이트리스트(javascript: 차단)로 XSS를 막는다. 렌더 자체 동작은 헤드리스 검증(3-verification)이 본다.
    outm = os.path.join(work, "chains-md.html")
    rm = impl.run(lroot, "web", "-o", outm, "--title", "t")
    pagem = open(outm, encoding="utf-8").read() if os.path.isfile(outm) else ""
    has_toggle = 'class="mdtoggle"' in pagem and '<button' in pagem
    has_parser = "function renderMd" in pagem and "function inlineMd" in pagem
    # 기본은 원문(렌더 토글 off): 렌더 상태 플래그가 false로 초기화되어, 문서를 처음 열면 <pre> 원문이 그려진다.
    initial_raw = "rendered=false" in pagem.replace(" ", "")
    # XSS: safeUrl이 javascript: 스킴을 차단하는 로직을 담는다.
    xss_guard = "javascript:" in pagem and "safeUrl" in pagem
    # 자기완결: 마크다운 파서가 외부 스크립트/스타일을 끌어오지 않는다(페이지 전체 외부 http src/href 0은 WEB-SELFCONTAINED류가 이미 봄).
    check("WEB-MD-RENDER",
          '스텝 문서 마크다운 렌더 토글(기본 원문·지연) + 인라인 파서(CDN 0) + javascript: 스킴 차단',
          rm.returncode == 0 and has_toggle and has_parser and initial_raw and xss_guard,
          f"rc={rm.returncode} toggle={has_toggle} parser={has_parser} initial_raw={initial_raw} xss={xss_guard}")

    # WEB-LAYOUT-TERMINATES (loom/C076): 레이아웃(_layout_columns)은 분기·병합이 깊이에 걸쳐 반복되는
    # 그래프에서 무한 스핀했다 — free_slot(빈 트랙)과 occupied(빈 좌표) 회피가 분리돼, 트랙이 비었는데
    # 그 좌표가 점유되면 같은 col을 영원히 반환. 이 버그는 소비자 저장소에서 gil 프로세스가 종료 못 하고
    # 누적돼 CPU 100%를 냈다. 종료는 계약이다 — 판정기가 안 보는 계약은 없는 계약(Weft).
    # 스핀을 실제로 유발했던 위상(loom prefix 36, id 무관 순수 parent 인덱스)을 박제해 web에 타임아웃을 건다.
    _spin_parents = [[], [0], [1], [2], [3], [4], [5], [6], [7], [8], [9], [10], [11], [11],
                     [12], [14], [13], [15], [17], [16], [18], [20], [19], [22], [23], [24],
                     [25], [26], [27], [28], [29], [30], [31], [32], [33], []]
    troot = make_sandbox(os.path.join(work, "layout-spin"))
    for i, ps in enumerate(_spin_parents):
        write_cycle(troot, "spin", f"C{i:03}-n",
                    parent=(f"C{ps[0]:03}-n" if ps else "null"),
                    status="closed", closed="2026-01-02")
    outt = os.path.join(work, "spin.html")
    layout_ok = False
    try:
        rt = impl.run(troot, "web", "-o", outt, "--title", "t", timeout=30)
        layout_ok = rt.returncode == 0 and os.path.isfile(outt)
    except subprocess.TimeoutExpired:
        layout_ok = False  # 스핀 = 종료 실패 = FAIL
    check("WEB-LAYOUT-TERMINATES",
          "분기·병합 반복 그래프에서 레이아웃이 유한 시간에 종료(무한 스핀 없음) — 30s 타임아웃 내 web 생성",
          layout_ok, f"terminated={layout_ok}")

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

        # ---- releases: 배포 계보 조회 — 태그↔CHANGELOG 대조 (loom/C061, #3 배포 버저닝) ----
        # 배포는 두 몸으로 기록된다(태그 v<semver> + CHANGELOG). 조회 프리미티브는 그 둘을 대조해
        # 한 기록에만 있는 릴리스(drift)를 드러내야 한다 — git tag -l이 못 하는 일. 읽기 전용이어야 한다.
        # 구현이 releases를 구현했을 때만 판정한다(부분 구현 합법). 미구현이면 HELP-COMPLETE가 이미 정직성을 본다.
        if impl.run(g, "help", "releases").returncode == 0:
            rl = make_sandbox(os.path.join(work, "releases"))

            def rlg(*cli):
                return subprocess.run(["git", "-C", rl, *cli], capture_output=True, text=True)

            os.makedirs(os.path.join(rl, "rooms/deployment/ariadne-spec"))
            with open(os.path.join(rl, "rooms/deployment/CHANGELOG.md"), "w", encoding="utf-8") as f:
                f.write("# Changelog\n\n## [Unreleased]\n\n"
                        "## [1.2.0] — 2026-07-20\n\n- 문서만 릴리스 (태그 없음)\n- 도구 변경: 없음 (문서 릴리스)\n\n"
                        "## [1.0.0] — 2026-07-18\n\n- 첫 릴리스\n- 도구 변경: gil (마이너 이상 승격)\n")
            with open(os.path.join(rl, "rooms/deployment/ariadne-spec/f.txt"), "w", encoding="utf-8") as f:
                f.write("x\n")
            rlg("init", "-q", "-b", "main"); rlg("config", "user.name", "fx"); rlg("config", "user.email", "fx@t")
            rlg("add", "-A"); rlg("commit", "-q", "-m", "init")
            rlg("tag", "-a", "v1.0.0", "-m", "Ariadne release v1.0.0 — 첫 릴리스")   # TC (양쪽)
            rlg("tag", "-a", "v1.1.0", "-m", "Ariadne release v1.1.0 — 태그만")       # T only → drift
            rlg("tag", "-a", "cycle/x/C001-y", "-m", "cycle tag")                      # 릴리스 아님 → 무시돼야
            before = snapshot(rl)
            r = impl.run(rl, "releases")
            after = snapshot(rl)
            hooks = [l for l in r.stdout.splitlines() if l.startswith("gil:release ")]
            summary = [l for l in r.stdout.splitlines() if l.startswith("gil:releases ")]
            # 대조의 증거: 세 릴리스(1.2.0=C, 1.1.0=T, 1.0.0=TC)를 모두 봤고, drift 2건을 셈, cycle 태그는 배제, 무변화.
            saw_all = all(f"gil:release {v} " in "\n".join(hooks) for v in ("1.2.0", "1.1.0", "1.0.0"))
            no_cycle = not any(" C001-y " in h or "cycle/" in h for h in hooks)
            drift_seen = bool(summary) and "drift=2" in summary[0]
            check("RELEASE-LIST",
                  "releases가 태그↔CHANGELOG를 대조 (3릴리스 훅 ∧ drift=2 ∧ cycle태그 배제 ∧ exit0 ∧ 저장소 무변화)",
                  r.returncode == 0 and len(hooks) == 3 and saw_all and no_cycle
                  and drift_seen and after == before,
                  f"rc={r.returncode} 훅={len(hooks)} drift={drift_seen} 무변화={after == before}")

        # ---- release drift 게이트: 봉인 전 배포 계보의 두 기록 일치를 요구 (loom/C072, #3 배포 강화) ----
        # cmd_release는 태그 v<semver>와 CHANGELOG를 한 커밋에 각인 → 정상 경로 drift=0. 한쪽에만 있는
        # 릴리스(drift)는 정상 경로 밖의 손댐 신호. 게이트 계약: drift 저장소는 무변화로 거부(하드 등급),
        # 일치 저장소는 게이트 통과(위양성 0). release는 Go에서 referenceOnly → help release로 참조 구현만 판정.
        if impl.run(g, "help", "release").returncode == 0:
            def _mk_release_repo(name, changelog_body):
                d = make_sandbox(os.path.join(work, name))          # rooms/experiment/{_template,chains}
                os.makedirs(os.path.join(d, "rooms/deployment/ariadne-spec"))
                with open(os.path.join(d, "rooms/deployment/CHANGELOG.md"), "w", encoding="utf-8") as f:
                    f.write(changelog_body)
                with open(os.path.join(d, "rooms/deployment/ariadne-spec/f.txt"), "w", encoding="utf-8") as f:
                    f.write("x\n")
                dg = lambda *c: subprocess.run(["git", "-C", d, *c], capture_output=True, text=True)
                dg("init", "-q", "-b", "main"); dg("config", "user.name", "fx"); dg("config", "user.email", "fx@t")
                dg("add", "-A"); dg("commit", "-q", "-m", "init")
                dg("tag", "-a", "v1.0.0", "-m", "Ariadne release v1.0.0")   # 깃의 진실: v1.0.0 태그
                return d, dg

            def _run_release(d, ver):
                return impl.run(d, "release", ver, "--notes", "n",
                                "--package", os.path.join(d, "rooms/deployment/ariadne-spec"),
                                "--root", os.path.join(d, "rooms/experiment/chains"))

            # (1) drift: 태그 v1.0.0 존재 · CHANGELOG엔 1.0.0 엔트리 없음 → release는 무변화로 거부해야
            dd, ddg = _mk_release_repo("reldrift", "# Changelog\n\n## [Unreleased]\n")
            before = snapshot(dd); head0 = ddg("rev-parse", "HEAD").stdout; tags0 = ddg("tag", "-l").stdout
            rd = _run_release(dd, "1.1.0")
            after = snapshot(dd); head1 = ddg("rev-parse", "HEAD").stdout; tags1 = ddg("tag", "-l").stdout
            drift_msg = "drift" in (rd.stderr + rd.stdout)
            no_change = after == before and head0 == head1 and tags0 == tags1   # 작업트리·커밋·태그 불변
            # (2) 일치: CHANGELOG에 1.0.0 엔트리 → drift 0 → 게이트 통과(하류에서 비-drift 사유로 멈춤)
            dc, _ = _mk_release_repo("relclean",
                "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] — 2026-07-18\n\n- 첫 릴리스\n- 도구 변경: gil (마이너 이상 승격)\n")
            rc = _run_release(dc, "1.1.0")
            gate_passed = "drift" not in (rc.stderr + rc.stdout)   # 위양성 0: 일치 저장소를 drift로 막지 않는다
            check("RELEASE-DRIFT-GATE",
                  "release가 배포 계보 drift를 하드 거부 (drift→exit≠0 ∧ 무변화(트리·커밋·태그) ∧ 처방 ∧ 일치는 통과)",
                  rd.returncode != 0 and drift_msg and no_change and gate_passed,
                  f"drift_rc={rd.returncode} 처방={drift_msg} 무변화={no_change} 일치통과={gate_passed}")

            # RELEASE-CYCLE-SOURCE (loom/C086, 이슈 #25·#18): 배포는 닫힌 사이클을 근거로만.
            # 닫힌 --cycle은 CHANGELOG·태그에 기록되고 releases가 읽는다. 열린/없는 --cycle은 무변화 거부.
            if impl.run(g, "help", "release").returncode == 0:
                def _mk_src_repo(name):
                    # v1.0.0 태그를 다는 _mk_release_repo와 drift가 안 나게 CHANGELOG에도 1.0.0 엔트리를 둔다.
                    d, dg = _mk_release_repo(name,
                        "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] — 2026-07-18\n\n- 첫 릴리스\n")
                    # [loom/C093] release는 봉인 전 RELEASE.md에 그 버전 서술을 요구한다(C038). _mk_release_repo는
                    # drift 게이트용이라 RELEASE.md를 안 만든다 — 여기선 release를 실제 성공시켜야 하므로 추가한다.
                    with open(os.path.join(d, "rooms/deployment/ariadne-spec/RELEASE.md"), "w", encoding="utf-8") as f:
                        f.write("# Release\n\n## v1.1.0\n\n근거 사이클 계약 검증용.\n")
                    write_cycle(d, "src", "C001-done", status="closed", closed="2026-07-20",
                                step='"5"', verdict="supported")
                    write_cycle(d, "src", "C002-open", status="open", step='"1"')
                    dg("add", "-A"); dg("commit", "-q", "-m", "cycles")
                    return d, dg
                def _rel_cyc(d, ver, cyc):
                    return impl.run(d, "release", ver, "--notes", "n", "--cycle", cyc,
                                    "--package", os.path.join(d, "rooms/deployment/ariadne-spec"),
                                    "--root", os.path.join(d, "rooms/experiment/chains"))
                # (1) 닫힌 사이클 근거 → 기록 + releases가 읽음
                ds, dsg = _mk_src_repo("relsrc")
                r1 = _rel_cyc(ds, "1.1.0", "src/C001-done")
                cl_txt = open(os.path.join(ds, "rooms/deployment/CHANGELOG.md"), encoding="utf-8").read()
                tag_txt = dsg("tag", "-l", "--format=%(contents)", "v1.1.0").stdout
                rels = impl.run(ds, "releases", "--package", os.path.join(ds, "rooms/deployment/ariadne-spec"))
                recorded = (r1.returncode == 0 and "근거 사이클: src/C001-done" in cl_txt
                            and "근거 사이클: src/C001-done" in tag_txt
                            and "src/C001-done" in rels.stdout and "cycles=1" in rels.stdout)
                # (2) 열린 사이클 근거 → 무변화 거부
                do, dog = _mk_src_repo("relsrcopen")
                b_head = dog("rev-parse", "HEAD").stdout; b_tags = dog("tag", "-l").stdout
                r2 = _rel_cyc(do, "1.1.0", "src/C002-open")
                open_rejected = (r2.returncode != 0
                                 and dog("rev-parse", "HEAD").stdout == b_head
                                 and dog("tag", "-l").stdout == b_tags)
                # (3) 없는 사이클 근거 → 무변화 거부
                dn, dng = _mk_src_repo("relsrcnone")
                n_head = dng("rev-parse", "HEAD").stdout
                r3 = _rel_cyc(dn, "1.1.0", "src/C999-nope")
                none_rejected = r3.returncode != 0 and dng("rev-parse", "HEAD").stdout == n_head
                check("RELEASE-CYCLE-SOURCE",
                      "release --cycle: 닫힌 사이클을 태그·CHANGELOG에 기록(releases가 읽음); 열린/없는 사이클은 무변화 거부",
                      recorded and open_rejected and none_rejected,
                      f"기록={recorded} 열림거부={open_rejected} 없음거부={none_rejected}")

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

        # STEP-GATE (loom/C090): step-by-step 강제. open은 1스텝만 스캐폴딩, step N은 이전 스텝 완수를
        # 요구하고(미완이면 무변화 거부) 통과 시 N 파일을 생성한다. 다음 스텝 재료가 미리 나와있지 않다.
        sg = make_sandbox(os.path.join(work, "stepgate"))
        sgg = lambda *c: subprocess.run(["git", "-C", sg, *c], capture_output=True, text=True)
        sgg("init", "-q"); sgg("config", "user.name", "fx"); sgg("config", "user.email", "fx@t")
        impl.run(sg, "open", "demo", "one", "--new-chain", "--title", "t", "--author", "fx")
        cdir = os.path.join(sg, "rooms/experiment/chains/demo/C001-one")
        # (1) open은 1-hypothesis만 (2~5·3-verification 부재)
        only_step1 = (os.path.isfile(os.path.join(cdir, "1-hypothesis.md"))
                      and not os.path.exists(os.path.join(cdir, "2-design.md"))
                      and not os.path.exists(os.path.join(cdir, "3-verification"))
                      and not os.path.exists(os.path.join(cdir, "5-report.md")))
        # (2) 1 미완(스캐폴딩만) 상태로 step 2 → 거부(무변화)
        r_block = impl.run(sg, "step", "demo", "C001-one", "2")
        blocked = r_block.returncode != 0 and not os.path.exists(os.path.join(cdir, "2-design.md"))
        # (3) 1 작성 후 step 2 → 통과 + 2-design 생성
        with open(os.path.join(cdir, "1-hypothesis.md"), "w", encoding="utf-8") as f:
            f.write("# 1. 가설\n\n실질 가설 내용.\n")
        r_ok = impl.run(sg, "step", "demo", "C001-one", "2")
        advanced = r_ok.returncode == 0 and os.path.isfile(os.path.join(cdir, "2-design.md"))
        check("STEP-GATE",
              "step-by-step 강제: open은 1스텝만 · 이전 스텝 미완이면 step 거부(무변화) · 완수 후 다음 스텝 생성",
              only_step1 and blocked and advanced,
              f"only_step1={only_step1} blocked={blocked} advanced={advanced}")

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

        # ---- withdraw: 대체 없는 순수 철회 (loom/C084) ----
        # supersede가 대체자를 요구하는 전방 무효화라면, withdraw는 대체 없이 열린 사이클을
        # open 커밋 revert로 되감는다 — 'open 직후 스코프 오판으로 없던 걸로'(graft/C003).
        # 취소조차 역사에 남긴다(하드리셋 아님). git 없이는 각인할 수 없으므로 skip_git 가드 안.
        # 구현이 withdraw를 구현했을 때만 판정한다(부분 구현 합법 — C043). 미구현이면 HELP-COMPLETE가
        # exit 3으로 정직성을 본다: 이 가드가 없으면 거부형 항목(REJECTS-CLOSED·ATOMIC)이 명령 부재의
        # 'unknown command' exit≠0으로 공허 통과한다("판정기가 안 보는 계약은 없는 계약이다" — C012).
        if not args.skip_git and impl.run(make_sandbox(os.path.join(work, "wd-probe")),
                                          "help", "withdraw").returncode == 0:
            def wd_repo(name):
                d = make_sandbox(os.path.join(work, name))
                def gg(*a):
                    return subprocess.run(["git", "-C", d, *a], capture_output=True, text=True)
                gg("init", "-q"); gg("config", "user.name", "fx"); gg("config", "user.email", "fx@t")
                gg("commit", "-q", "--allow-empty", "-m", "root")
                return d, gg

            # WITHDRAW-RETRACTS: 열린 사이클 withdraw → 디렉토리 소멸 + Revert 커밋 + exit 0
            d, gg = wd_repo("wd-retract")
            impl.run(d, "open", "demo", "second-step", "--new-chain", "--title", "t",
                     "--author", "fx", "--date", "2026-01-01", "--git")
            cdir = os.path.join(d, "rooms/experiment/chains/demo/C001-second-step")
            r = impl.run(d, "withdraw", "demo/C001-second-step")
            log = gg("log", "--format=%s").stdout
            check("WITHDRAW-RETRACTS", "열린 사이클 withdraw → 디렉토리 소멸 + Revert 커밋 각인 (대체 없는 철회)",
                  r.returncode == 0 and not os.path.isdir(cdir)
                  and re.search(r"^Revert ", log, flags=re.M) is not None,
                  (r.stderr or "").strip()[-140:] or log[:120])

            # WITHDRAW-REJECTS-CLOSED: 닫힌(태그된) 사이클 withdraw → exit≠0 + HEAD 불변
            d, gg = wd_repo("wd-closed")
            impl.run(d, "open", "demo", "to-seal", "--new-chain", "--title", "t",
                     "--author", "fx", "--date", "2026-01-01", "--git")
            for n in ("1", "2", "3", "4", "5"):
                impl.run(d, "step", "demo", "C001-to-seal", n)
            with open(os.path.join(d, "rooms/experiment/chains/demo/C001-to-seal/5-report.md"),
                      "w", encoding="utf-8") as f:
                f.write("# 보고\nsupported.\n")
            impl.run(d, "close", "demo", "C001-to-seal", "--verdict", "supported", "--git")
            head_before = gg("rev-parse", "HEAD").stdout.strip()
            r = impl.run(d, "withdraw", "demo/C001-to-seal")
            head_after = gg("rev-parse", "HEAD").stdout.strip()
            check("WITHDRAW-REJECTS-CLOSED", "닫힌 사이클 withdraw 거부 + HEAD 불변 (불변 보호 — supersede/correct의 몫)",
                  r.returncode != 0 and head_before == head_after, f"rc={r.returncode}")

            # WITHDRAW-ATOMIC: 존재하지 않는 ref withdraw → exit≠0 + HEAD 불변 (무변화)
            d, gg = wd_repo("wd-atomic")
            impl.run(d, "open", "demo", "alive", "--new-chain", "--title", "t",
                     "--author", "fx", "--date", "2026-01-01", "--git")
            head_before = gg("rev-parse", "HEAD").stdout.strip()
            r = impl.run(d, "withdraw", "demo/C999-ghost")
            head_after = gg("rev-parse", "HEAD").stdout.strip()
            check("WITHDRAW-ATOMIC", "존재하지 않는 ref withdraw 거부 + HEAD 불변 (원자성)",
                  r.returncode != 0 and head_before == head_after, f"rc={r.returncode}")

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
              bool(cycle_commit) and all(p.startswith("rooms/experiment/chains/demo/C001-first") for p in cycle_commit)
              and web_commit == ["chains.html"],  # [loom/C092] bool() — 빈 리스트가 cond로 새면 sum(RESULTS)가 터진다
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

    # ---- NO-GIT: git 부재 환경에서 우아한 강등 (loom/C052, 비개발자 진입) ----
    # git이 없으면 커밋할 수 없다. 그때 크래시·트레이스백·오도 경고 대신 파일을 남기고
    # rc 0로 완주해야 한다 — 계약은 "완주 + 파일 + 무크래시"(의미), 안내 문면은 렌더(C051).
    ng = make_sandbox(os.path.join(work, "nogit"))
    ngcr = os.path.join(ng, "rooms/experiment/chains")
    r = impl.run_nogit(ng, "open", "demo", "first-try",
                       "--author", "tester", "--new-chain", "--git", "--root", ngcr)
    yaml_made = os.path.isfile(os.path.join(ngcr, "demo", "C001-first-try", "cycle.yaml"))
    no_crash = "Traceback" not in r.stderr and "panic:" not in r.stderr
    check("NO-GIT-GRACEFUL", "git 부재에서 open이 rc0 + 사이클 파일 생성 + 무크래시 (파일은 남고 각인만 건너뜀)",
          r.returncode == 0 and yaml_made and no_crash,
          f"rc={r.returncode} yaml={yaml_made} crash={not no_crash} err={r.stderr.strip()[:80]}")

    # ---- NO-REMOTE: git은 있으나 원격이 없는 환경에서 --push 우아화 (loom/C054, 비개발자 진입) ----
    # git이 있으면 커밋은 되지만 원격이 없으면 push할 곳이 없다. 그때 날것 fatal(rc≠0)도
    # 조용한 삼킴(침묵)도 아닌 "커밋 보존 + 원인 안내 + rc0"으로 강등해야 한다 (C052의 원격판).
    # 계약: rc0 ∧ 사이클 파일 ∧ 로컬 커밋 존재 ∧ 무크래시. 안내 문면은 렌더(C051).
    # realpath: macOS tmpdir의 /var→/private/var 심볼릭 링크가 git --show-toplevel와
    # 절대 --root를 어긋나게 해 relpath를 깨뜨린다 (C028·C029 환경 함정). 이 테스트의 의도는
    # push 우아화이지 경로 해석이 아니므로 경로를 미리 정규화한다.
    nr = os.path.realpath(make_sandbox(os.path.join(work, "noremote")))
    subprocess.run(["git", "-C", nr, "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", nr, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", nr, "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", nr, "add", "-A"], check=True)
    subprocess.run(["git", "-C", nr, "commit", "-q", "-m", "init"], check=True)
    nrcr = os.path.join(nr, "rooms/experiment/chains")
    r = impl.run(nr, "open", "demo", "first-try",
                 "--author", "tester", "--new-chain", "--git", "--push", "--root", nrcr)
    yaml_made = os.path.isfile(os.path.join(nrcr, "demo", "C001-first-try", "cycle.yaml"))
    no_crash = "Traceback" not in r.stderr and "panic:" not in r.stderr
    logout = subprocess.run(["git", "-C", nr, "log", "--oneline"], capture_output=True, text=True).stdout
    committed = "gil: open" in logout  # 원격은 없어도 로컬 각인은 보존된다
    check("NO-REMOTE-GRACEFUL",
          "원격 부재에서 --push가 rc0 + 사이클 파일 + 로컬 커밋 보존 + 무크래시 (날것 fatal도 침묵도 아님)",
          r.returncode == 0 and yaml_made and committed and no_crash,
          f"rc={r.returncode} yaml={yaml_made} committed={committed} crash={not no_crash} err={r.stderr.strip()[:80]}")

    # ---- PATH-SYMLINK: 심볼릭 링크를 통과하는 절대 --root에서 --git 우아화 (loom/C055) ----
    # macOS /var→/private/var 류의 심링크 때문에 git rev-parse --show-toplevel(realpath)과
    # 사용자가 준 절대 --root(심링크 그대로)가 어긋나면, 저장소 상대 경로가 저장소를 탈출하는
    # ../…로 붕괴해 git add가 거부한다. 참조는 날것 fatal로 커밋 실패(반쪽 상태 — 파일은
    # 생겼는데 각인이 없다), Go는 EvalSymlinks로 견딘다 — 두 몸, 한 계약의 위반.
    # 계약: 심링크 루트에서도 rc0 ∧ 사이클 파일 ∧ 로컬 커밋 보존 ∧ 무크래시. 안내 문면은 렌더(C051).
    # (C054의 NO-REMOTE 테스트가 realpath로 미리 정규화해 우회했던 바로 그 경로를 정면으로 밟는다.)
    sreal = os.path.realpath(make_sandbox(os.path.join(work, "symreal")))
    subprocess.run(["git", "-C", sreal, "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", sreal, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", sreal, "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", sreal, "add", "-A"], check=True)
    subprocess.run(["git", "-C", sreal, "commit", "-q", "-m", "init"], check=True)
    ssym = os.path.join(work, "symlink")   # symlink → sreal (심링크를 통과하는 --root의 뿌리)
    os.symlink(sreal, ssym)
    scr = os.path.join(ssym, "rooms/experiment/chains")  # 절대·심링크 경로
    r = impl.run(sreal, "open", "demo", "sym-root",
                 "--author", "tester", "--new-chain", "--git", "--root", scr)
    yaml_made = os.path.isfile(os.path.join(sreal, "rooms/experiment/chains",
                                             "demo", "C001-sym-root", "cycle.yaml"))
    no_crash = "Traceback" not in r.stderr and "panic:" not in r.stderr
    logout = subprocess.run(["git", "-C", sreal, "log", "--oneline"],
                            capture_output=True, text=True).stdout
    committed = "gil: open" in logout  # 심링크 루트에서도 로컬 각인이 되어야 한다
    check("PATH-SYMLINK-GIT",
          "심볼릭 링크 절대 --root에서 open --git이 rc0 + 사이클 파일 + 로컬 커밋 보존 + 무크래시 (relpath가 저장소를 탈출하지 않는다)",
          r.returncode == 0 and yaml_made and committed and no_crash,
          f"rc={r.returncode} yaml={yaml_made} committed={committed} crash={not no_crash} err={r.stderr.strip()[:80]}")

    # ---- DEVIATIONS-COUNT: close는 deviations.yaml 레코드 수 ≠ 카운트면 봉인을 거부한다 (loom/C057) ----
    # C053 슬립(deviations.yaml은 썼는데 cycle.yaml의 deviations 카운트를 손으로 못 고쳐 내부 불일치가
    # 봉인됨) 차단. deviations.yaml은 사람이 읽는 자유 서술 문서라 스키마(R13)가 아니라 '몇 건인가'만
    # 계약한다 — 최상위 '- ' 레코드 수 = deviations 필드. 계약: 불일치면 rc≠0 ∧ 무봉인(거부),
    # 카운트를 맞추면 rc0 ∧ 봉인. T(문다)·F(안 문다) 두 얼굴을 함께 요구(C038 쌍 검증).
    dvroot = make_sandbox(os.path.join(work, "devcount"))
    write_cycle(dvroot, "demo", "C001-dev")
    dvdir = os.path.join(dvroot, "rooms/experiment/chains/demo/C001-dev")
    dvy = os.path.join(dvdir, "cycle.yaml")
    with open(dvy, "a", encoding="utf-8") as f:
        f.write("deviations: 0\n")   # gil open 스캐폴드와 동일 (카운트는 0인데…)
    with open(os.path.join(dvdir, "5-report.md"), "w", encoding="utf-8") as f:
        f.write("# 5. 결과 보고\n\n## 요약\n\n계약 검증용 실보고서.\n")
    with open(os.path.join(dvdir, "deviations.yaml"), "w", encoding="utf-8") as f:
        f.write("- id: D1\n  what: 테스트 이탈\n  why: |\n    블록 스칼라 내용 줄 (콜론 없음)\n")  # …레코드는 1건
    before = open(dvy, encoding="utf-8").read()
    r_bad = impl.run(dvroot, "close", "demo", "C001-dev", "--date", "2026-01-07")
    rejected = r_bad.returncode != 0 and "status: closed" not in open(dvy, encoding="utf-8").read()
    with open(dvy, "w", encoding="utf-8") as f:   # 카운트를 레코드 수(1)로 맞춘다
        f.write(re.sub(r"(?m)^deviations:.*$", "deviations: 1", before))
    r_ok = impl.run(dvroot, "close", "demo", "C001-dev", "--date", "2026-01-07")
    accepted = r_ok.returncode == 0 and "status: closed" in open(dvy, encoding="utf-8").read()
    check("DEVIATIONS-COUNT",
          "close는 deviations.yaml 레코드 수 ≠ deviations 카운트면 봉인 거부, 맞추면 봉인 (C053 슬립 차단)",
          rejected and accepted,
          f"rejected={rejected} accepted={accepted} bad_rc={r_bad.returncode} ok_rc={r_ok.returncode}")

    # ---- WORKTREE-SPAWN: gil worktree add가 워크트리+브랜치+사이클을 원자적으로, 메인 격리 (loom/C058, #1) ----
    # 병렬 사이클 모드의 진입점. open을 워크트리 안에서 self-invoke하므로 커밋이 그 브랜치에만 가고
    # 메인 저장소는 오염되지 않는다 — C050(워크트리 아닌 메인에 잘못 open)의 구조적 봉인.
    # 계약: rc0 ∧ 워크트리에 사이클 ∧ 브랜치 생성 ∧ 메인 작업트리 격리 ∧ 메인 log에 open 커밋 없음 ∧ 무크래시.
    # 음성(쌍 검증, C038): 비저장소에서 거부(rc≠0). realpath: sibling 워크트리 경로 계산의 심링크 흡수.
    wsroot = os.path.realpath(make_sandbox(os.path.join(work, "wtspawn")))
    for cfg in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", wsroot, *cfg], check=True)
    subprocess.run(["git", "-C", wsroot, "add", "-A"], check=True)
    subprocess.run(["git", "-C", wsroot, "commit", "-q", "-m", "init"], check=True)
    wscr = os.path.join(wsroot, "rooms/experiment/chains")
    r = impl.run(wsroot, "worktree", "add", "demo", "para", "--author", "tester", "--new-chain", "--root", wscr)
    wt_path = os.path.join(os.path.dirname(wsroot), os.path.basename(wsroot) + "-worktrees", "demo-para")
    cyc_in_wt = os.path.isfile(os.path.join(wt_path, "rooms/experiment/chains/demo/C001-para/cycle.yaml"))
    br = subprocess.run(["git", "-C", wsroot, "branch", "--list", "tester/demo-para"], capture_output=True, text=True).stdout
    branch_made = "tester/demo-para" in br
    main_isolated = not os.path.isdir(os.path.join(wscr, "demo"))  # 메인 작업트리에 사이클 없음
    mlog = subprocess.run(["git", "-C", wsroot, "log", "--oneline", "main"], capture_output=True, text=True).stdout
    main_no_open = "gil: open" not in mlog  # C050 봉인: open 커밋이 main에 안 샜다
    no_crash = "Traceback" not in r.stderr and "panic:" not in r.stderr
    # 음성: 비저장소에서 거부
    nbroot = make_sandbox(os.path.join(work, "wtnorepo"))
    nbcr = os.path.join(nbroot, "rooms/experiment/chains")
    r_neg = impl.run(nbroot, "worktree", "add", "demo", "x", "--author", "t", "--new-chain", "--root", nbcr)
    check("WORKTREE-SPAWN",
          "worktree add가 rc0 + 워크트리에 사이클 + 브랜치 + 메인 격리 + main에 open 커밋 없음 + 무크래시; 비저장소는 거부 (C050 봉인)",
          r.returncode == 0 and cyc_in_wt and branch_made and main_isolated and main_no_open
          and no_crash and r_neg.returncode != 0,
          f"rc={r.returncode} cyc={cyc_in_wt} br={branch_made} iso={main_isolated} noopen={main_no_open} "
          f"crash={not no_crash} neg_rc={r_neg.returncode}")
    subprocess.run(["git", "-C", wsroot, "worktree", "remove", "--force", wt_path], capture_output=True)
    shutil.rmtree(os.path.join(os.path.dirname(wsroot), os.path.basename(wsroot) + "-worktrees"), ignore_errors=True)

    # ---- WORKTREE-LAND: gil worktree land가 브랜치를 main에 --no-ff 병합 + 충돌 안전 + 워크트리 정리 (loom/C060, #1) ----
    # 병렬 사이클 모드의 닫는 반쪽. add의 결정론적 매핑을 역산해 브랜치를 main에 --no-ff로 봉합하고,
    # 성공 시에만 워크트리+브랜치를 정리한다. 충돌은 삼키지 않는다 — abort로 되돌리고 워크트리를 보존한다.
    # 계약(양성): rc0 ∧ main에 병합 반영 ∧ --no-ff 병합 커밋(부모 2개) ∧ 워크트리 제거 ∧ 브랜치 삭제 ∧ 무크래시.
    # 음성(쌍 검증, C038): main에 충돌을 심으면 land가 거부(rc≠0) + 워크트리·브랜치 보존 + MERGE_HEAD 무잔재.
    def _mk_repo(path):
        os.makedirs(path, exist_ok=True)
        for cfg in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", path, *cfg], check=True)
        subprocess.run(["git", "-C", path, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    # 양성: add로 브랜치 생성 → land로 착지
    lroot = os.path.realpath(make_sandbox(os.path.join(work, "wtland")))
    _mk_repo(lroot)
    lcr = os.path.join(lroot, "rooms/experiment/chains")
    l_wt = os.path.join(os.path.dirname(lroot), os.path.basename(lroot) + "-worktrees", "demo-para")
    impl.run(lroot, "worktree", "add", "demo", "para", "--author", "tester", "--new-chain", "--root", lcr)
    rl = impl.run(lroot, "worktree", "land", "demo", "para", "--author", "tester", "--root", lcr)
    landed = os.path.isfile(os.path.join(lcr, "demo/C001-para/cycle.yaml"))  # main 작업트리에 병합 반영
    head_parents = subprocess.run(["git", "-C", lroot, "rev-list", "--parents", "-n1", "HEAD"],
                                  capture_output=True, text=True).stdout.split()
    merge_commit = len(head_parents) == 3  # --no-ff → 병합 커밋(자신 + 부모 2)
    hmsg = subprocess.run(["git", "-C", lroot, "log", "-1", "--pretty=%s"], capture_output=True, text=True).stdout
    land_msg = "gil: land" in hmsg
    wt_gone = not os.path.isdir(l_wt)
    lbr = subprocess.run(["git", "-C", lroot, "branch", "--list", "tester/demo-para"], capture_output=True, text=True).stdout
    branch_gone = "tester/demo-para" not in lbr
    l_no_crash = "Traceback" not in rl.stderr and "panic:" not in rl.stderr
    # 음성: 충돌을 심고 land → 거부 + 보존
    croot = os.path.realpath(make_sandbox(os.path.join(work, "wtlandc")))
    _mk_repo(croot)
    ccr = os.path.join(croot, "rooms/experiment/chains")
    c_wt = os.path.join(os.path.dirname(croot), os.path.basename(croot) + "-worktrees", "demo-para")
    impl.run(croot, "worktree", "add", "demo", "para", "--author", "tester", "--new-chain", "--root", ccr)
    # main에 같은 경로로 충돌 내용을 커밋 (브랜치의 cycle.yaml과 충돌)
    conflict_path = os.path.join(ccr, "demo/C001-para/cycle.yaml")
    os.makedirs(os.path.dirname(conflict_path), exist_ok=True)
    with open(conflict_path, "w", encoding="utf-8") as f:
        f.write("id: C001-para\nchain: demo\nstatus: CONFLICT-ON-MAIN\n")
    subprocess.run(["git", "-C", croot, "add", "-A"], check=True)
    subprocess.run(["git", "-C", croot, "commit", "-q", "-m", "conflicting change on main"], check=True)
    rc = impl.run(croot, "worktree", "land", "demo", "para", "--author", "tester", "--root", ccr)
    conflict_rejected = rc.returncode != 0
    wt_kept = os.path.isdir(c_wt)
    cbr = subprocess.run(["git", "-C", croot, "branch", "--list", "tester/demo-para"], capture_output=True, text=True).stdout
    branch_kept = "tester/demo-para" in cbr
    no_merging = not os.path.isfile(os.path.join(croot, ".git", "MERGE_HEAD"))  # abort 확인
    c_no_crash = "Traceback" not in rc.stderr and "panic:" not in rc.stderr
    check("WORKTREE-LAND",
          "worktree land가 rc0 + main에 --no-ff 병합(부모2) + 워크트리·브랜치 정리 + 무크래시; 충돌은 거부+보존+abort (C060 봉합)",
          rl.returncode == 0 and landed and merge_commit and land_msg and wt_gone and branch_gone and l_no_crash
          and conflict_rejected and wt_kept and branch_kept and no_merging and c_no_crash,
          f"rc={rl.returncode} landed={landed} merge={merge_commit} msg={land_msg} wtgone={wt_gone} brgone={branch_gone} "
          f"crash={not l_no_crash} | neg_rc={rc.returncode} wtkept={wt_kept} brkept={branch_kept} nomerging={no_merging}")
    for r_, w_ in ((lroot, l_wt), (croot, c_wt)):
        subprocess.run(["git", "-C", r_, "worktree", "remove", "--force", w_], capture_output=True)
        shutil.rmtree(os.path.join(os.path.dirname(r_), os.path.basename(r_) + "-worktrees"), ignore_errors=True)

    # ---- show: 지식그래프 노드 조회 — 신원+정방향 엣지+백링크(cited-by) (loom/C059, #4 LLM 위키) ----
    # 사이클 DAG는 이미 지식그래프다(엣지는 cycle.yaml에 데이터로 있다). show는 한 노드 + 양방향 이웃을
    # 질의자가 파일을 안 읽고 얻게 한다(표적 탐색). 계약면 = 엣지 집합(정방향 parent·lineage + 백링크).
    # 구현이 show를 구현했을 때만 판정(부분 구현 합법). 미구현이면 HELP-COMPLETE가 정직성을 본다.
    if impl.run(work, "help", "show").returncode == 0:
        sh = make_sandbox(os.path.join(work, "show"))
        shr = os.path.join(sh, "rooms/experiment/chains")
        # 픽스처: alpha에 A←B←C(parent 체인), beta의 X가 lineage로 alpha/A를 가리킴(cross-chain)
        write_cycle(sh, "alpha", "C001-a")
        write_cycle(sh, "alpha", "C002-b", parent="C001-a")
        write_cycle(sh, "alpha", "C003-c", parent="C002-b")
        write_cycle(sh, "beta", "C001-x", lineage="alpha/C001-a")

        def showj(ref):
            r = impl.run(sh, "show", ref, "--json", "--root", shr)
            try:
                return r, json.loads(r.stdout)
            except Exception:
                return r, None

        r, dA = showj("alpha/C001-a")
        check("SHOW-NODE", "show <chain>/<id> --json이 그 노드의 신원을 반환 (exit0 ∧ id·chain 일치)",
              r.returncode == 0 and dA and dA["node"].get("id") == "C001-a"
              and dA["node"].get("chain") == "alpha",
              f"rc={r.returncode}")
        r, dX = showj("beta/C001-x")
        check("SHOW-FORWARD", "정방향 lineage 엣지가 대상+존재여부로 해석된다 (X ⇠ alpha/A, exists)",
              dX and dX["forward"]["lineage"] == [{"ref": "alpha/C001-a", "exists": True}],
              f"forward.lineage={dX and dX['forward']['lineage']}")
        r, dB = showj("alpha/C002-b")
        check("SHOW-BACKLINKS-PARENT", "parent 백링크(체인 내 cited-by): alpha/B ← alpha/C",
              dB and dB["backlinks"]["parents"] == ["alpha/C003-c"],
              f"backlinks.parents={dB and dB['backlinks']['parents']}")
        check("SHOW-BACKLINKS-LINEAGE", "lineage 백링크(cross-chain cited-by): alpha/A ← beta/X",
              dA and dA["backlinks"]["lineage"] == ["beta/C001-x"],
              f"backlinks.lineage={dA and dA['backlinks']['lineage']}")
        # 엣지 집합이 build_graph(web JSON)와 일치 — 두 표면이 다른 그래프를 말하면 지식그래프 신뢰 붕괴
        wpath = os.path.join(sh, "w.html")
        impl.run(sh, "web", shr, "-o", wpath, "--chain", "alpha")
        m = re.search(r'id="gil-data"[^>]*>(.*?)</script>', open(wpath).read(), re.S)
        wparents = set(json.loads(m.group(1))["chains"]["alpha"]["cycles"]["C003-c"]["parents"])
        r, dC = showj("alpha/C003-c")
        sparents = set(e["ref"].split("/", 1)[1] for e in dC["forward"]["parents"]) if dC else set()
        check("SHOW-EDGES-MATCH-GRAPH", "show의 정방향 parent 엣지 == web JSON(build_graph) 엣지",
              wparents == sparents and wparents == {"C002-b"}, f"web={wparents} show={sparents}")
        # 부재 노드는 지어내지 않는다 (§3.2 P2, C040) — exit≠0 ∧ stdout에 JSON node 없음
        r, dG = showj("alpha/C999-ghost")
        check("SHOW-MISSING", "부재 노드 → exit≠0 ∧ 지어낸 JSON 없음",
              r.returncode != 0 and dG is None, f"rc={r.returncode}")

    # ---- threads: 열린 실 훑기 — 진행 중 병렬(예약)+열린 사이클 전역 조회 (loom/C070, #4 LLM 위키) ----
    # 병렬 워크트리 사이클은 브랜치에 살아 main 뷰어에 안 잡힌다. 그러나 reserve가 reservations.tsv를
    # main에 커밋하므로 "진행 중 병렬"은 이미 데이터다. threads는 그 미소비 예약 + status=open 사이클을
    # 기계 계약면(--json)으로 반환한다. 지어내지 않는다: 소비된(사이클로 존재하는) 예약은 제외.
    # 구현이 threads를 구현했을 때만 판정(부분 구현 합법). 미구현이면 HELP-COMPLETE가 정직성을 본다.
    if impl.run(work, "help", "threads").returncode == 0:
        def write_res(root, chain_dir, lines):
            p = os.path.join(root, "rooms/experiment/chains", chain_dir, "reservations.tsv")
            with open(p, "w", encoding="utf-8") as f:
                f.write("# gil 예약 원장\n")
                for ln in lines:
                    f.write(ln + "\n")

        def threadsj(root_sb, cr):
            r = impl.run(root_sb, "threads", "--json", "--root", cr)
            try:
                return r, json.loads(r.stdout)
            except Exception:
                return r, None

        # 픽스처 gamma: C001-open(열림)·C002-done(닫힘), 예약 5(미소비)·1(=C001 소비됨)
        th = make_sandbox(os.path.join(work, "threads"))
        thr = os.path.join(th, "rooms/experiment/chains")
        write_cycle(th, "gamma", "C001-open", status="open", author="alice", step="3")
        write_cycle(th, "gamma", "C002-done", status="closed")
        write_res(th, "gamma", ["5 bob newthing 2026-01-01", "1 alice already 2026-01-01"])
        r, d = threadsj(th, thr)
        shape_ok = (r.returncode == 0 and d is not None and isinstance(d.get("reserved"), list)
                    and isinstance(d.get("open"), list)
                    and d.get("reserved_count") == len(d["reserved"])
                    and d.get("open_count") == len(d["open"]))
        check("THREADS-JSON-SHAPE", "threads --json이 reserved·open·*_count 키를 가진 유효 JSON (exit0)",
              shape_ok, f"rc={r.returncode} keys={sorted(d) if d else None}")
        res_nums = {x["num"]: x for x in (d["reserved"] if d else [])}
        check("THREADS-RESERVED", "미소비 예약이 reserved에 정확히 나온다 (num5·for=bob·slug)",
              5 in res_nums and res_nums[5]["for"] == "bob" and res_nums[5]["slug"] == "newthing",
              f"reserved={d and d['reserved']}")
        check("THREADS-CONSUMED-EXCLUDED", "소비된 예약(num1=C001-open 존재)은 reserved에서 제외 (지어냄 방지, C040)",
              d is not None and 1 not in res_nums, f"reserved_nums={sorted(res_nums)}")
        open_ids = {(x["chain"], x["id"]) for x in (d["open"] if d else [])}
        check("THREADS-OPEN", "status=open 사이클은 open에, closed는 제외 (gamma/C001-open ∈, C002-done ∉)",
              ("gamma", "C001-open") in open_ids and ("gamma", "C002-done") not in open_ids,
              f"open={sorted(open_ids)}")
        # threads의 open 집합 == 픽스처를 직접 스캔한 open 집합 (두 표면이 다른 그래프를 말하면 안 됨, C042 threads판)
        scanned = set()
        for ch in os.listdir(thr):
            chp = os.path.join(thr, ch)
            if not os.path.isdir(chp):
                continue
            for cyc in os.listdir(chp):
                yp = os.path.join(chp, cyc, "cycle.yaml")
                if os.path.isfile(yp):
                    txt = open(yp, encoding="utf-8").read()
                    if re.search(r"^status:\s*open\s*$", txt, re.M):
                        scanned.add((ch, cyc))
        check("THREADS-OPEN-MATCHES-SCAN", "threads의 open 집합 == 직접 스캔한 open 집합 (불일치 기각, C042)",
              open_ids == scanned, f"threads={sorted(open_ids)} scan={sorted(scanned)}")
        # 빈 상태: 닫힌 사이클만·예약 없음 → reserved==[]·open==[], exit0 (부재 정직)
        te = make_sandbox(os.path.join(work, "threads_empty"))
        ter = os.path.join(te, "rooms/experiment/chains")
        write_cycle(te, "delta", "C001-only", status="closed")
        r, de = threadsj(te, ter)
        check("THREADS-EMPTY", "예약·열린 사이클 0 → reserved==[]·open==[], exit0 (빈 상태 정직)",
              r.returncode == 0 and de is not None and de["reserved"] == [] and de["open"] == [],
              f"rc={r.returncode} d={de}")

    # ---- worktree owner guard: 주 체크아웃 소유 강제 (loom/C062, #1 — 상현님 발의) ----
    # 존재가 자기 워크트리 밖 공유 main으로 cd해 커밋하는 C050 사고를 도구가 커밋 이전에 거부한다.
    # 주 체크아웃만 규제(gil.owner≠author → 거부), 링크드 워크트리는 오탐 0으로 통과. 쌍 검증(C038).
    gd = os.path.join(work, "guard")

    def gdg(*cli):
        return subprocess.run(["git", "-C", gd, *cli], capture_output=True, text=True)

    make_sandbox(gd)
    gdr = os.path.join(gd, "rooms/experiment/chains")
    gdg("init", "-q", "-b", "main"); gdg("config", "user.name", "o"); gdg("config", "user.email", "o@t")
    gdg("config", "gil.owner", "owner-x")
    gdg("add", "-A"); gdg("commit", "-q", "-m", "init")
    head0 = gdg("rev-parse", "HEAD").stdout.strip()
    r = impl.run(gd, "open", "demo", "intrude", "--author", "intruder", "--new-chain", "--git", "--root", gdr)
    dir_made = os.path.isdir(os.path.join(gdr, "demo"))
    head1 = gdg("rev-parse", "HEAD").stdout.strip()
    check("GUARD-PRIMARY-REFUSE",
          "주 체크아웃에서 author≠gil.owner의 open을 거부 (exit≠0 ∧ 사이클 미생성 ∧ HEAD 무변화) — C050 봉인",
          r.returncode != 0 and not dir_made and head1 == head0,
          f"rc={r.returncode} dir={dir_made} head={head1 == head0}")
    r = impl.run(gd, "open", "demo", "mine", "--author", "owner-x", "--new-chain", "--git", "--root", gdr)
    check("GUARD-OWNER-OK", "주 체크아웃에서 주인(gil.owner) author의 open은 통과",
          r.returncode == 0 and os.path.isdir(os.path.join(gdr, "demo")), f"rc={r.returncode}")
    # 링크드 워크트리(존재의 정당한 공간)에서는 남의 author도 통과 — 오탐 0
    gwt = os.path.join(work, "guard-wt")
    gdg("worktree", "add", "-q", "-b", "feat", gwt)
    gwtr = os.path.join(gwt, "rooms/experiment/chains")
    r = impl.run(gwt, "open", "demo2", "inwt", "--author", "someone", "--new-chain", "--git", "--root", gwtr)
    check("GUARD-LINKED-OK", "링크드 워크트리에서는 남의 author open도 통과 (오탐 0 — 존재의 작업공간)",
          r.returncode == 0 and os.path.isdir(os.path.join(gwtr, "demo2")), f"rc={r.returncode}")
    gdg("worktree", "remove", "--force", gwt)

    # GUARD-RESERVED-OK / GUARD-RESERVED-AUTHOR (loom/C078): 예약은 소유자의 명시적 승인이다 —
    # 주 체크아웃에서도 예약 대상 author의 open은 guard가 허용한다(병렬 온보딩 마찰 제거). 단 예약된
    # author 본인만 — A 앞 예약을 B가 여는 것은 여전히 거부(예약 예외가 C050 방지를 안 뚫는다).
    # 예약을 둘 걸어 하나 소비 후에도 reservations.tsv가 안 비게 한다(빈 원장 삭제 시 git add 경로 문제 회피).
    impl.run(gd, "reserve", "demo", "res-a", "--for", "alice", "--root", gdr)
    impl.run(gd, "reserve", "demo", "res-b", "--for", "bob", "--root", gdr)
    ra = impl.run(gd, "open", "demo", "res-a", "--author", "alice", "--parent", "C001-mine", "--git", "--root", gdr)
    check("GUARD-RESERVED-OK",
          "주 체크아웃에서 예약 대상 author의 예약된 open은 통과 (예약=소유자 승인 · C078)",
          ra.returncode == 0 and os.path.isdir(os.path.join(gdr, "demo", "C002-res-a")),
          f"rc={ra.returncode}")
    # bob 앞 예약(res-b)을 mallory가 열려 하면 거부 — 예약 예외는 예약된 author 본인에게만
    rm_ = impl.run(gd, "open", "demo", "res-b", "--author", "mallory", "--parent", "C001-mine", "--git", "--root", gdr)
    check("GUARD-RESERVED-AUTHOR",
          "남 앞으로 예약된 slug을 다른 author가 열면 거부 (예약 예외는 C050 방지를 안 뚫는다 · C078)",
          rm_.returncode != 0 and not os.path.isdir(os.path.join(gdr, "demo", "C003-res-b")),
          f"rc={rm_.returncode}")

    shutil.rmtree(work, ignore_errors=True)
    total, passed = len(RESULTS), sum(RESULTS)
    print(f"\n계약 준수: {passed}/{total}" + ("  ✔ 이 구현은 gil이다" if passed == total else "  ✘ 계약 위반"))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
