#!/usr/bin/env python3
"""gil v3 — 커밋 그래프 위의 체인·사이클·스텝 (씨앗 구현).

옛 gil(폴더+md)은 버렸다. v3는 폴더도 md 파일도 만들지 않는다. 모든 위계는 커밋의 Gil-*
trailer로, 본문은 커밋 로그로 산다. 이 파일은 손 시연으로 확립한 규약(SPEC.md)을 코드로
옮긴 첫 씨앗 — 지금은 **읽기(수집·조회·fsck)** 만. 쓰기(open/step/close)는 다음 스텝.

진실원은 언제나 git 커밋 그래프. 이 코드는 그걸 파싱하는 얇은 층이다.
"""
import subprocess
import sys
import re

# Gil- 네임스페이스 trailer 키 (SPEC §2)
HIER_KEYS = ["Gil-Chain", "Gil-Cycle", "Gil-Step", "Gil-Kind", "Gil-Parent"]
ROOT_KEYS = ["Gil-Cycle-Author", "Gil-Cycle-Parent"]
RESULT_KEYS = ["Gil-Outcome", "Gil-Backtrack"]
MERGE_KEY = "Gil-Merge"

KINDS = {"define", "hypothesis", "verify", "analyze",
         "success", "fail", "pending"}
OUTCOMES = {"success", "backtrack", "fail"}
ID_RE = re.compile(r"^[a-z0-9-]+$")  # 옛 R1: 소문자·숫자·하이픈만 (git ref 안전)

_SEP = "\x1e"  # record separator (커밋 사이)
_FSEP = "\x1f"  # field separator


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=True).stdout


def collect_nodes(rev_range="HEAD"):
    """커밋 그래프를 훑어 Gil-Step trailer를 가진 커밋을 스텝 노드로 수집.

    반환: [{sha, chain, cycle, step, kind, parent, author, cycle_parents,
            outcome, backtrack, merges, subject}]  (없는 값은 None/[])
    한 커밋에 여러 값 가능한 키(Gil-Cycle-Parent·Gil-Merge)는 리스트.
    """
    # 커밋마다: sha, subject, 그리고 각 trailer를 개별 포맷으로.
    fmt = _FSEP.join([
        "%H", "%s",
        "%(trailers:key=Gil-Chain,valueonly)",
        "%(trailers:key=Gil-Cycle,valueonly)",
        "%(trailers:key=Gil-Step,valueonly)",
        "%(trailers:key=Gil-Kind,valueonly)",
        "%(trailers:key=Gil-Parent,valueonly)",
        "%(trailers:key=Gil-Cycle-Author,valueonly)",
        "%(trailers:key=Gil-Cycle-Parent,valueonly,separator=%x00)",
        "%(trailers:key=Gil-Outcome,valueonly)",
        "%(trailers:key=Gil-Backtrack,valueonly)",
        "%(trailers:key=Gil-Merge,valueonly,separator=%x00)",
    ]) + _SEP
    out = _git("log", "--format=" + fmt, rev_range)
    nodes = []
    for rec in out.split(_SEP):
        rec = rec.strip("\n")
        if not rec:
            continue
        f = rec.split(_FSEP)
        if len(f) < 12:
            continue
        step = f[4].strip()
        if not step:  # Gil-Step 없으면 스텝 노드 아님 (일반 커밋)
            continue
        nodes.append({
            "sha": f[0][:9], "subject": f[1],
            "chain": f[2].strip() or None,
            "cycle": f[3].strip() or None,
            "step": step,
            "kind": f[5].strip() or None,
            "parent": (f[6].strip() or None),
            "author": f[7].strip() or None,
            "cycle_parents": [x for x in f[8].split("\x00") if x.strip()],
            "outcome": f[9].strip() or None,
            "backtrack": f[10].strip() or None,
            "merges": [x for x in f[11].split("\x00") if x.strip()],
        })
    return nodes


def fsck(nodes):
    """SPEC §3 무결성 검사. 반환: 위반 문자열 리스트 (빈 리스트=건강)."""
    violations = []
    chains = set()
    cycles = {}   # cycle id -> chain
    steps = {}    # (chain,cycle,step) -> node

    # 선언된 체인·사이클 수집
    for n in nodes:
        if n["chain"]:
            chains.add(n["chain"])
        if n["cycle"] and n["kind"] == "define" and n["parent"] in (None, "null"):
            cycles[n["cycle"]] = n["chain"]

    for n in nodes:
        cc = f'{n["chain"]}/{n["cycle"]}/{n["step"]}'
        # ── 1. 위계 무결성 ──
        if not n["chain"]:
            violations.append(f'위계: {cc} — Gil-Chain 없음 (체인 없는 스텝 금지)')
        elif n["chain"] not in chains:  # (수집상 항상 참이나 방어)
            violations.append(f'위계: {cc} — 미선언 체인 {n["chain"]}')
        if not n["cycle"]:
            violations.append(f'위계: {cc} — Gil-Cycle 없음 (사이클 없는 스텝 금지)')
        # ── 2. id 문법 (옛 R1) ──
        for kind_, val in (("chain", n["chain"]), ("cycle", n["cycle"]),
                           ("step", n["step"])):
            if val and not ID_RE.match(val):
                violations.append(f'id문법: {cc} — {kind_} id "{val}" '
                                  f'는 소문자·숫자·하이픈만 (마침표 금지)')
        # ── 3. kind 유효 ──
        if n["kind"] and n["kind"] not in KINDS:
            violations.append(f'kind: {cc} — 알 수 없는 kind "{n["kind"]}"')
        # ── 4. dangling parent ──
        p = n["parent"]
        if p and p not in ("null",):
            key = (n["chain"], n["cycle"], p)
            if key not in {(x["chain"], x["cycle"], x["step"]) for x in nodes}:
                violations.append(f'위계: {cc} — 부모 스텝 {p} 실재 안 함 '
                                  f'(dangling parent)')
        # ── 5. analyze는 outcome 강제 ──
        if n["kind"] == "analyze" and n["outcome"] not in OUTCOMES:
            violations.append(f'스텝순환: {cc} — analyze는 Gil-Outcome '
                              f'(success|backtrack|fail) 필요')
        if n["outcome"] == "backtrack" and not n["backtrack"]:
            violations.append(f'스텝순환: {cc} — backtrack은 Gil-Backtrack '
                              f'(조상 define) 필요')
        # ── 6. 계보 참조 무결성 (Cycle-Parent·Merge 실재) ──
        # 참조는 두 꼴: "cycle"(같은 체인 안) 또는 "chain/cycle"(다른 체인/외부).
        # 외부 참조(chain/cycle 꼴)는 이 그래프 밖일 수 있다 — id 문법만 보고 실재는
        # 검사하지 않는다(체인 경계 넘는 계보는 정상, 머지·부모 사이클로 이어짐).
        # 같은 체인 안 참조(cycle 꼴)만 실재를 강제한다.
        for ref in n["cycle_parents"] + n["merges"]:
            if "/" in ref:
                continue  # 외부 참조 — 실재 미검사 (경계 넘는 계보 허용)
            if ref not in cycles:
                violations.append(f'계보: {cc} — 같은 체인 참조 "{ref}" 실재 안 함')
    return violations


def cmd_log(args):
    ch = args[0] if args else None
    nodes = collect_nodes()
    nodes = [n for n in nodes if not ch or n["chain"] == ch]
    for n in reversed(nodes):  # 오래된→새 (트리 순서)
        line = f'{n["sha"]}  {n["chain"]}/{n["cycle"]}/{n["step"]} [{n["kind"]}]'
        if n["parent"] and n["parent"] != "null":
            line += f' ←{n["parent"]}'
        if n["outcome"]:
            line += f' ={n["outcome"]}'
        if n["merges"]:
            line += f'  ⋈ {",".join(n["merges"])}'
        print(line)


def cmd_fsck(args):
    # 선택 rev-range: 손 시연 초기의 규칙-위반 유산 노드를 범위 밖으로 둘 수 있다.
    # append-only라 옛 노드는 못 고치므로, fsck는 "여기서부터" 건강을 검사한다.
    rng = args[0] if args else "HEAD"
    v = fsck(collect_nodes(rng))
    if not v:
        print("fsck: 위반 0 — 커밋 그래프 건강")
        return
    for x in v:
        print("위반: " + x)
    sys.exit(1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "log"
    rest = sys.argv[2:]
    {"log": cmd_log, "fsck": cmd_fsck}.get(cmd, cmd_log)(rest)
