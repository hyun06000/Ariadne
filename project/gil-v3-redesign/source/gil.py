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


def declared_chains(rev_range="HEAD"):
    """선언된 체인 = Gil-Chain trailer를 가진 모든 커밋 (체인 루트 포함).

    체인 루트 커밋(gil init·chain-root)엔 Gil-Step이 없어 collect_nodes가 안 잡지만,
    Gil-Chain은 있다. 계보 부모가 체인일 수 있으므로(원칙 2) 이걸 따로 수집한다.
    """
    out = _git("log", "--format=%(trailers:key=Gil-Chain,valueonly)", rev_range)
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


# 체인·사이클 목적성 (자연어). 커밋-층에 Gil-Chain-Purpose·Gil-Cycle-Purpose로
# 선언된다. gil은 이를 판별하지 않고 시작 지점에서 눈앞에 띄운다 — 정합성 판단은
# AI(Clew)의 몫 (상현님: "자연어 목적을 알려주고 지금 일과 정합한지 AI가 판별").
def chain_purpose(chain, rev_range="HEAD"):
    """체인 목적성(자연어)을 커밋 그래프에서 읽는다. 없으면 None.

    같은 Gil-Chain을 가진 커밋 중 Gil-Chain-Purpose가 있는 첫(최신) 값. 체인 루트가
    선언하고 이후 노드가 상속. 시작 지점에서 이 목적을 띄워 정합 판단의 근거로 쓴다.
    """
    fmt = ("%(trailers:key=Gil-Chain,valueonly)" + _FSEP
           + "%(trailers:key=Gil-Chain-Purpose,valueonly)")
    out = _git("log", "--format=" + fmt, rev_range)
    for ln in out.splitlines():
        c, _, k = ln.partition(_FSEP)
        if c.strip() == chain and k.strip():
            return k.strip()
    return None


def cycle_purpose(chain, cycle, rev_range="HEAD"):
    """사이클 목적성(자연어)을 커밋 그래프에서 읽는다. 없으면 None.

    사이클 루트(s1 define)의 Gil-Cycle-Purpose. 스텝 시작 때 이 목적을 띄워
    "지금 스텝이 이 사이클 목적에 부합하는가"를 판단하게 한다.
    """
    fmt = ("%(trailers:key=Gil-Chain,valueonly)" + _FSEP
           + "%(trailers:key=Gil-Cycle,valueonly)" + _FSEP
           + "%(trailers:key=Gil-Cycle-Purpose,valueonly)")
    out = _git("log", "--format=" + fmt, rev_range)
    for ln in out.splitlines():
        c, _, rest = ln.partition(_FSEP)
        cy, _, pu = rest.partition(_FSEP)
        if c.strip() == chain and cy.strip() == cycle and pu.strip():
            return pu.strip()
    return None


def _show_purpose_context(chain, cycle=None, cycle_purpose_str=None):
    """시작 지점(체인/사이클/스텝)에서 목적성을 눈앞에 띄운다.

    gil은 정합을 판별하지 않는다 — 목적을 표시하고 AI(Clew)가 판단하게 한다
    (상현님: "자연어 목적을 알려주고 지금 일과 정합한지 AI가 판별").
    """
    cp = chain_purpose(chain)
    if cp:
        print(f"─ 체인 [{chain}] 목적: {cp}", file=sys.stderr)
    if cycle:
        pu = cycle_purpose_str or cycle_purpose(chain, cycle)
        if pu:
            print(f"─ 사이클 [{cycle}] 목적: {pu}", file=sys.stderr)
    if cp or cycle:
        print("─ 지금 하려는 일이 위 목적에 정합하는지 판단하고, 어긋나면 멈춰라.",
              file=sys.stderr)


def chain_closed(chain, rev_range="HEAD"):
    """체인이 닫혔는가 — Gil-Kind: close 커밋이 이 체인에 있으면 True.

    닫힌 부모 체인 안에서는 새 사이클을 못 연다(dev/c002 죽은 잎이 가르친 규칙).
    새 사이클은 새 자식 체인에서만.
    """
    fmt = ("%(trailers:key=Gil-Chain,valueonly)" + _FSEP
           + "%(trailers:key=Gil-Kind,valueonly)")
    out = _git("log", "--format=" + fmt, rev_range)
    for ln in out.splitlines():
        c, _, k = ln.partition(_FSEP)
        if c.strip() == chain and k.strip() == "close":
            return True
    return False


def chain_has_children(chain, rev_range="--all"):
    """이 체인을 부모로 선언한 다른 체인이 있는가 (Gil-Chain-Parent).

    자식이 분기해 나간 닫힌 부모 체인은 봉인된 것 — 그 안에서 다시 자라면
    자식 체인들과 조상을 다툰다(배포 계보 꼬임).
    """
    out = _git("log", "--format=%(trailers:key=Gil-Chain-Parent,valueonly)",
               rev_range)
    return any(ln.strip() == chain for ln in out.splitlines())


def fsck(nodes, chains_known=None, universe=None):
    """SPEC §3 무결성 검사. 반환: 위반 문자열 리스트 (빈 리스트=건강).

    nodes = 검사 대상(범위 내). universe = 참조 실재 확인용 전체 노드(부모·사이클이
    범위 밖에 있어도 실재하면 통과). universe 미지정 시 nodes로 대체.
    """
    violations = []
    universe = universe if universe is not None else nodes
    chains = set(chains_known or [])
    cycles = {}   # cycle id -> chain (전체 그래프 기준)
    step_keys = set()  # (chain,cycle,step) — 전체 그래프 기준

    # 선언된 체인·사이클·스텝은 전체 그래프(universe)에서 수집 — 범위 밖 참조도 실재 인정
    for n in universe:
        if n["chain"]:
            chains.add(n["chain"])
        step_keys.add((n["chain"], n["cycle"], n["step"]))
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
        # ── 4. dangling parent (전체 그래프 기준 — 부모가 범위 밖이어도 실재하면 OK) ──
        p = n["parent"]
        if p and p not in ("null",):
            if (n["chain"], n["cycle"], p) not in step_keys:
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
        # 참조는 세 꼴: 알려진 체인(체인 부모) · "cycle"(같은 체인 안 사이클) ·
        # "chain/cycle"(다른 체인/외부). 사이클은 체인에서 태어날 수 있으므로(원칙 2:
        # 체인 시작점) 참조가 알려진 체인이면 유효하다. 같은 체인 안 사이클 참조만 실재를
        # 강제하고, 외부 chain/cycle 꼴은 경계 넘는 계보라 미검사.
        for ref in n["cycle_parents"] + n["merges"]:
            if ref in chains:
                continue  # 체인 부모 — 사이클이 체인 시작점에서 태어남 (유효)
            if "/" in ref:
                continue  # 외부 참조 — 실재 미검사 (경계 넘는 계보 허용)
            if ref not in cycles:
                violations.append(f'계보: {cc} — 같은 체인 참조 "{ref}" 실재 안 함')
    return violations


# ── 쓰기 (커밋 노드를 새긴다 — 손 커밋의 코드화) ───────────────────────────

def _commit(subject, body, trailers, allow_empty=True):
    """제목+본문+Gil-* trailer로 커밋 하나를 새긴다. trailers=[(k,v)...]."""
    msg = subject + "\n\n" + body.rstrip() + "\n\n"
    msg += "\n".join(f"{k}: {v}" for k, v in trailers)
    args = ["commit", "-q", "-F", "-"]
    if allow_empty:
        args.append("--allow-empty")
    subprocess.run(["git", *args], input=msg, text=True, check=True)


def _current_cycle(chain, cycle):
    """이 (chain,cycle)의 스텝들을 커밋 그래프에서 수집. 없으면 []."""
    return [n for n in collect_nodes()
            if n["chain"] == chain and n["cycle"] == cycle]


def _next_step_id(steps):
    n = 1 + max([int(s["step"][1:]) for s in steps if s["step"][1:].isdigit()],
                default=0)
    return f"s{n}"


def _growing_tip(steps):
    """가장 최근 스텝(팁). 선형 전진의 부모가 된다."""
    return steps[0] if steps else None  # collect_nodes는 새→old 순


def cmd_open(args):
    """gil open <chain>/<cycle> --author <who> [--parent <cyc>...] [--title T]"""
    import argparse
    p = argparse.ArgumentParser(prog="gil open")
    p.add_argument("ref")  # chain/cycle
    p.add_argument("--author", required=True)
    p.add_argument("--parent", action="append", default=[])
    p.add_argument("--title", default="")
    p.add_argument("--purpose", required=True,
                   help="이 사이클의 목적성 (자연어). 시작 지점에서 체인 목적과 함께 "
                        "떠올라, 지금 작업이 정합한지 AI가 판별하는 근거가 된다.")
    a = p.parse_args(args)
    if "/" not in a.ref:
        sys.exit("거부: <chain>/<cycle> 꼴이어야 함")
    chain, cycle = a.ref.split("/", 1)
    for label, v in (("chain", chain), ("cycle", cycle)):
        if not ID_RE.match(v):
            sys.exit(f'거부: {label} id "{v}"는 소문자·숫자·하이픈만')
    if _current_cycle(chain, cycle):
        sys.exit(f"거부: {a.ref} 이미 존재 (open은 새 사이클만)")

    # ── 닫힌 부모 체인 사이클 금지 (dev/c002 죽은 잎이 가르친 규칙) ──
    # 닫힌 체인 안에서 새 사이클을 열면 배포 계보가 꼬인다. 특히 자식 체인이 분기해
    # 나갔으면 절대 — 봉인된 부모에서 다시 자라면 자식들과 조상을 다툰다. 새 사이클은
    # 무조건 새 자식 체인에서.
    if chain_closed(chain):
        why = "자식 체인이 분기함" if chain_has_children(chain) else "닫힌 체인"
        sys.exit(f'거부: "{chain}"은 닫힌 부모 체인({why}) — 그 안에 새 사이클을 '
                 f'열 수 없다. 새 자식 체인을 열어라 (gil chain <name> --purpose ...). '
                 f'닫힌 부모에서 다시 자라면 배포 계보가 꼬인다.')

    # ── 체인 적합성 점검 (상현님: 사이클 시작 시 목적성 정합 판별) ──
    # gil은 판별하지 않는다 — 체인 목적을 눈앞에 띄워 AI(Clew)가 정합성을 판단하게
    # 한다. gil의 강제는 "목적성을 반드시 명시(--purpose)" + "시작 때 목적 표시".
    _show_purpose_context(chain, cycle, cycle_purpose_str=a.purpose)

    subject = f"gil {chain}/{cycle}/s1 define: {a.title or a.purpose}"
    body = a.title or "(문제 미기술 — 본문을 커밋 수정으로 채우라)"
    tr = [("Gil-Chain", chain), ("Gil-Cycle", cycle),
          ("Gil-Step", "s1"), ("Gil-Kind", "define"), ("Gil-Parent", "null"),
          ("Gil-Cycle-Author", a.author),
          ("Gil-Cycle-Purpose", a.purpose)]
    for par in a.parent:
        tr.append(("Gil-Cycle-Parent", par))
    _commit(subject, body, tr)
    print(f"open: {a.ref}/s1 define")


def cmd_step(args):
    """gil step <chain>/<cycle> --kind K [--outcome O] [--to define] [--title T]"""
    import argparse
    p = argparse.ArgumentParser(prog="gil step")
    p.add_argument("ref")
    p.add_argument("--kind", required=True)
    p.add_argument("--outcome")
    p.add_argument("--to")
    p.add_argument("--title", default="")
    a = p.parse_args(args)
    chain, cycle = a.ref.split("/", 1)
    steps = _current_cycle(chain, cycle)
    if not steps:
        sys.exit(f"거부: {a.ref} 없음 (먼저 gil open)")
    if a.kind not in KINDS:
        sys.exit(f'거부: 알 수 없는 kind "{a.kind}"')
    # 매 스텝 시작 시 체인·사이클 목적을 띄워 정합 판단을 강제 (상현님).
    _show_purpose_context(chain, cycle)
    if a.kind == "analyze" and a.outcome not in OUTCOMES:
        sys.exit("거부: analyze는 --outcome success|backtrack|fail 필요")
    sid = _next_step_id(steps)
    parent = a.to or (_growing_tip(steps)["step"] if steps else "null")
    subject = f"gil {chain}/{cycle}/{sid} {a.kind}: {a.title or a.kind}"
    tr = [("Gil-Chain", chain), ("Gil-Cycle", cycle),
          ("Gil-Step", sid), ("Gil-Kind", a.kind), ("Gil-Parent", parent)]
    if a.outcome:
        tr.append(("Gil-Outcome", a.outcome))
    if a.outcome == "backtrack" and a.to:
        tr.append(("Gil-Backtrack", a.to))
    _commit(subject, a.title or a.kind, tr)
    print(f"step: {a.ref}/{sid} {a.kind} ←{parent}")


def cmd_close(args):
    """gil close <chain>/<cycle> [--verdict V]"""
    import argparse
    p = argparse.ArgumentParser(prog="gil close")
    p.add_argument("ref")
    p.add_argument("--verdict", default="supported")
    a = p.parse_args(args)
    chain, cycle = a.ref.split("/", 1)
    steps = _current_cycle(chain, cycle)
    if not steps:
        sys.exit(f"거부: {a.ref} 없음")
    live = [s for s in steps if s["kind"] == "analyze"
            and s["outcome"] == "success"]
    if not live:
        sys.exit("거부: 산 잎(analyze/success) 없음 — 닫을 수 없다")
    subject = f"gil {chain}/{cycle} close: {a.verdict}"
    body = f"사이클 봉인. 산 잎 {[s['step'] for s in live]}. 판정: {a.verdict}."
    tr = [("Gil-Chain", chain), ("Gil-Cycle", cycle),
          ("Gil-Kind", "close"), ("Gil-Verdict", a.verdict)]
    _commit(subject, body, tr)
    print(f"close: {a.ref} — {a.verdict}")


def cmd_chain(args):
    """gil chain <name> --purpose <자연어> [--kind study|dev|staging|deploy]

    새 체인 루트를 연다. 체인 시작 지점에서 목적성을 반드시 명시(--purpose 필수).
    이 목적이 이후 사이클·스텝 시작 때 눈앞에 떠 정합 판단의 근거가 된다 (상현님:
    "체인 시작 때 목적을 물어보고 명시하게"). 체인 위계 규칙(닫힌 체인 끝에서만)은
    git 브랜치·머지로 표현되므로 여기선 목적 각인에 집중한다.
    """
    import argparse
    p = argparse.ArgumentParser(prog="gil chain")
    p.add_argument("name")
    p.add_argument("--purpose", required=True,
                   help="이 체인의 목적성 (자연어). 이후 모든 시작 지점에서 떠오른다.")
    a = p.parse_args(args)
    if not ID_RE.match(a.name):
        sys.exit(f'거부: 체인 이름 "{a.name}"은 소문자·숫자·하이픈만')
    if chain_purpose(a.name):
        sys.exit(f'거부: 체인 "{a.name}" 이미 목적 선언됨 (chain은 새 체인만)')
    subject = f"gil {a.name} chain: {a.purpose}"
    body = (f"체인 [{a.name}] 개설. 목적: {a.purpose}\n\n"
            f"이 목적은 이후 사이클·스텝 시작 때 떠올라, 그 작업이 이 체인에 "
            f"정합하는지 판단하는 근거가 된다.")
    tr = [("Gil-Chain", a.name), ("Gil-Chain-Purpose", a.purpose)]
    _commit(subject, body, tr)
    print(f"chain: {a.name} 개설 — 목적: {a.purpose}")


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
    # 검사는 범위(rng), 참조 실재 확인은 전체 그래프(universe). 부모·사이클·체인이
    # 범위 밖에 있어도 실재하면 통과 — dangling 오검 방지.
    v = fsck(collect_nodes(rng), chains_known=declared_chains("HEAD"),
             universe=collect_nodes("HEAD"))
    if not v:
        print("fsck: 위반 0 — 커밋 그래프 건강")
        return
    for x in v:
        print("위반: " + x)
    sys.exit(1)


COMMANDS = {
    "chain": cmd_chain, "open": cmd_open, "step": cmd_step, "close": cmd_close,
    "log": cmd_log, "fsck": cmd_fsck,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "log"
    rest = sys.argv[2:]
    if cmd not in COMMANDS:
        sys.exit(f"gil: 알 수 없는 명령 {cmd!r} — {list(COMMANDS)}")
    COMMANDS[cmd](rest)
