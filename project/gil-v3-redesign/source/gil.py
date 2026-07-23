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


def _gitlog(*args):
    """git log 래퍼. 커밋이 아직 없는 빈 저장소(HEAD 부재)에선 빈 문자열.

    첫 체인을 gil chain으로 여는 시나리오처럼 커밋 0개일 때 git log는 exit 128로
    죽는다 — 그건 오류가 아니라 '아직 노드 없음'이므로 빈 결과로 흡수한다.
    """
    r = subprocess.run(["git", "log", *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


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
    out = _gitlog("--format=" + fmt, rev_range)
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


def body_index(rev_range="--all"):
    """sha(9자) → 순수 본문(디테일) 인덱스를 **단일 git log**로 만든다.

    step_body를 스텝마다 git fork로 부르면 O(스텝수)의 프로세스 생성이 된다(62초 벽,
    gil-v3-study/c002/s4). 이 함수는 git log 한 번(--all 2320커밋 0.037초)으로 모든
    커밋의 본문을 뽑아, step_body(sha, idx)가 fork 없이 인덱스에서 읽게 한다.
    """
    fmt = "%H" + _FSEP + "%b" + _SEP
    out = _git("log", "--format=" + fmt, rev_range)
    idx = {}
    for rec in out.split(_SEP):
        rec = rec.strip("\n")
        if not rec:
            continue
        f = rec.split(_FSEP, 1)
        if len(f) < 2:
            continue
        idx[f[0][:9]] = _strip_trailers(f[1].rstrip("\n"))
    return idx


TRAILER_PREFIXES = ("Gil-", "Co-Authored-By:", "Co-authored-by:", "Signed-off-by:")


def _strip_trailers(body):
    """본문 끝의 trailer 블록(알려진 키로 시작하는 라인)을 걷어내 순수 본문만 남긴다."""
    lines = body.split("\n")
    end = len(lines)
    while end > 0:
        ln = lines[end - 1].strip()
        if ln == "":
            end -= 1
            continue
        if ln.startswith(TRAILER_PREFIXES):
            end -= 1
        else:
            break
    return "\n".join(lines[:end]).strip()


def step_body(sha, idx=None):
    """한 스텝 커밋의 본문(디테일) — 제목·trailer 제외한 순수 마크다운 본문.

    idx(body_index 결과)를 주면 fork 없이 인덱스에서 읽는다(빠른 경로). 없으면 단건 조회.
    커밋 = 제목 + 빈줄 + 본문 + 빈줄 + Gil-* trailer. %b는 본문+trailer를 준다.
    본문에도 "막힘: …"처럼 콜론이 흔하므로 알려진 접두사로만 trailer를 엄격히 구분한다.
    """
    if idx is not None:
        return idx.get(sha[:9], "")
    return _strip_trailers(_git("log", "-1", "--format=%b", sha).rstrip("\n"))


def declared_chains(rev_range="HEAD"):
    """선언된 체인 = Gil-Chain trailer를 가진 모든 커밋 (체인 루트 포함).

    체인 루트 커밋(gil init·chain-root)엔 Gil-Step이 없어 collect_nodes가 안 잡지만,
    Gil-Chain은 있다. 계보 부모가 체인일 수 있으므로(원칙 2) 이걸 따로 수집한다.
    """
    out = _gitlog("--format=%(trailers:key=Gil-Chain,valueonly)", rev_range)
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


# 체인·사이클 목적성 (자연어). 커밋-층에 Gil-Chain-Purpose·Gil-Cycle-Purpose로
# 선언된다. gil은 이를 판별하지 않고 시작 지점에서 눈앞에 띄운다 — 정합성 판단은
# AI(Clew)의 몫 (상현님: "자연어 목적을 알려주고 지금 일과 정합한지 AI가 판별").
def chain_purpose(chain, rev_range="HEAD"):
    """체인 목적성(자연어)을 커밋 그래프에서 읽는다. 없으면 None.

    같은 Gil-Chain을 가진 커밋 중 Gil-Chain-Purpose가 있는 첫(최신) 값. 체인 루트가
    선언하고 이후 노드가 상속. 시작 지점에서 이 목적을 띄워 정합 판단의 근거로 쓴다.
    """
    # valueonly는 값 뒤에 개행을 남겨 한 커밋 출력이 여러 줄로 쪼개진다. 레코드
    # 구분자(_SEP)로 커밋마다 묶어 먼저 나눈 뒤 필드를 분리한다(collect_nodes 패턴).
    fmt = ("%(trailers:key=Gil-Chain,valueonly)" + _FSEP
           + "%(trailers:key=Gil-Chain-Purpose,valueonly)" + _SEP)
    out = _gitlog("--format=" + fmt, rev_range)
    for rec in out.split(_SEP):
        c, _, k = rec.partition(_FSEP)
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
           + "%(trailers:key=Gil-Cycle-Purpose,valueonly)" + _SEP)
    out = _gitlog("--format=" + fmt, rev_range)
    for rec in out.split(_SEP):
        c, _, rest = rec.partition(_FSEP)
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
    """체인이 닫혔는가 — Gil-Kind: chain-close 커밋이 이 체인에 있으면 True.

    주의: 사이클 close(Gil-Kind: close, Gil-Cycle 있음)와 체인 close(chain-close,
    Gil-Cycle 없음)는 다르다. 사이클 하나를 닫았다고 체인이 닫힌 게 아니다 — 그러면
    닫힌 사이클 끝에서 다음 사이클을 여는 정상 흐름까지 막힌다(도그푸딩이 잡은 버그).
    닫힌 부모 체인 안에서만 새 사이클을 금하고 새 자식 체인을 강제한다(원칙 6).
    """
    fmt = ("%(trailers:key=Gil-Chain,valueonly)" + _FSEP
           + "%(trailers:key=Gil-Kind,valueonly)" + _SEP)
    out = _gitlog("--format=" + fmt, rev_range)
    for rec in out.split(_SEP):
        c, _, k = rec.partition(_FSEP)
        if c.strip() == chain and k.strip() == "chain-close":
            return True
    return False


def chain_has_children(chain, rev_range="--all"):
    """이 체인을 부모로 선언한 다른 체인이 있는가 (Gil-Chain-Parent).

    자식이 분기해 나간 닫힌 부모 체인은 봉인된 것 — 그 안에서 다시 자라면
    자식 체인들과 조상을 다툰다(배포 계보 꼬임).
    """
    out = _gitlog("--format=%(trailers:key=Gil-Chain-Parent,valueonly)",
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
        # ── 6a. 스텝 머지 (Gil-Merge = 같은 사이클 안 산 잎 스텝 id, 역순 머지 맨 아래) ──
        # Gil-Merge는 두 의미: 스텝 머지(스텝 id, 같은 사이클) 또는 체인/사이클 머지.
        # 스텝 id(같은 사이클 안 실재)면 스텝으로 검증하고 넘어간다.
        step_merges = []
        cyc_chain_merges = []
        for ref in n["merges"]:
            if (n["chain"], n["cycle"], ref) in step_keys:
                step_merges.append(ref)  # 스텝 머지 — 같은 사이클 산 잎
            else:
                cyc_chain_merges.append(ref)  # 체인/사이클 머지
        # (스텝 머지 대상 실재는 step_keys로 이미 확인됨 — 위반 없음)

        # ── 6b. 계보 참조 무결성 (Cycle-Parent + 체인/사이클 Merge 실재) ──
        # 참조 세 꼴: 알려진 체인(체인 부모) · "cycle"(같은 체인 사이클) · "chain/cycle"(외부).
        # 사이클은 체인 시작점에서 태어날 수 있으니 알려진 체인이면 유효. 외부는 경계 넘는
        # 계보라 미검사. 같은 체인 사이클 참조만 실재 강제.
        for ref in n["cycle_parents"] + cyc_chain_merges:
            if ref in chains:
                continue  # 체인 부모/머지 — 유효
            if "/" in ref:
                continue  # 외부 참조 — 실재 미검사
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


def _resolve_body(a):
    """--body(문자열) 또는 --body-file(경로)에서 스텝 디테일 본문을 얻는다."""
    if getattr(a, "body_file", None):
        with open(a.body_file, encoding="utf-8") as fh:
            return fh.read().strip()
    return getattr(a, "body", None) or ""


def cmd_step(args):
    """gil step <chain>/<cycle> --kind K [--outcome O] [--to define]
       [--title T] [--body TEXT | --body-file PATH]

    제목(subject) = --title(짧은 위계 요약). 본문(디테일, 마크다운) = --body 또는
    --body-file. 본문 없으면 제목이 본문을 겸한다(하위호환). '본문은 커밋 로그에'.
    """
    import argparse
    p = argparse.ArgumentParser(prog="gil step")
    p.add_argument("ref")
    p.add_argument("--kind", required=True)
    p.add_argument("--outcome")
    p.add_argument("--to")
    p.add_argument("--title", default="")
    p.add_argument("--body")
    p.add_argument("--body-file")
    p.add_argument("--merge", action="append", default=[],
                   help="합류할 산 잎 스텝 id (여러 번). 이 스텝이 두 조상을 상속")
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

    # ── 스텝 원칙 (상현님): 막히면 실패 노드로 닫고 → backtrack으로 조상 define로
    #   되돌아가 새 형제 가지. parent를 세 경우로 명확히 나눈다.
    tip = _growing_tip(steps)
    tip_id = tip["step"] if tip else None
    define_ids = {s["step"] for s in steps if s["kind"] == "define"}

    # 산 잎(analyze/success) id 집합 — 머지 대상 검증용
    live_leaves = {s["step"] for s in steps
                   if s["kind"] == "analyze" and s["outcome"] == "success"}

    if a.merge:
        # 스텝 머지: 한 사이클 안 산 잎들을 합류 (역순 머지 맨 아래, 상현님).
        # parent=첫 산 잎, Gil-Merge=나머지. 이후 노드는 두 갈래를 조상으로.
        # 완성(산 잎)만 머지 대상 — 죽은 잎은 벽의 지도로 남을 뿐.
        targets = a.merge
        for m in targets:
            if m not in live_leaves:
                sys.exit(f"거부: --merge {m}는 산 잎(analyze/success)이어야 함 "
                         f"(완성만 머지 대상, 죽은 잎은 벽의 지도)")
        parent = targets[0]
        merge_rest = targets[1:]
    elif a.kind == "hypothesis" and a.to:
        # 되돌아가 새 형제 가지: 조상 define(--to)의 새 자식. (백트래킹의 '나아가는' 절반)
        if a.to not in define_ids:
            sys.exit(f"거부: --to {a.to}는 조상 define이어야 함")
        parent = a.to
        merge_rest = []
    elif a.outcome == "backtrack":
        # 막힌 지점을 죽은 잎으로 닫음 — 선형 끝(팁의 자식). Gil-Backtrack=되돌아갈 define.
        if not a.to:
            sys.exit("거부: backtrack은 --to <조상 define> 필요 (되돌아갈 곳)")
        if a.to not in define_ids:
            sys.exit(f"거부: --to {a.to}는 조상 define이어야 함")
        parent = tip_id or "null"
        merge_rest = []
    else:
        # 선형 전진 (define→hypothesis→verify→analyze) 또는 success 잎.
        parent = tip_id or "null"
        merge_rest = []

    sid = _next_step_id(steps)
    subject = f"gil {chain}/{cycle}/{sid} {a.kind}: {a.title or a.kind}"
    body = _resolve_body(a) or a.title or a.kind
    tr = [("Gil-Chain", chain), ("Gil-Cycle", cycle),
          ("Gil-Step", sid), ("Gil-Kind", a.kind), ("Gil-Parent", parent)]
    if a.outcome:
        tr.append(("Gil-Outcome", a.outcome))
    if a.outcome == "backtrack":
        tr.append(("Gil-Backtrack", a.to))
    for m in merge_rest:
        tr.append(("Gil-Merge", m))
    _commit(subject, body, tr)
    tail = f" ⤳backtrack→{a.to}" if a.outcome == "backtrack" else (
        f" (형제 가지 ←{a.to})" if a.kind == "hypothesis" and a.to else (
            f" ⋈merge {'+'.join(a.merge)}" if a.merge else ""))
    print(f"step: {a.ref}/{sid} {a.kind} ←{parent}{tail}")


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
    # Gil-Kind: chain-root — 이 커밋이 체인 루트임을 표식. 뷰어·fsck가 체인 루트를
    # 이 kind로 감지한다(없으면 뷰어가 체인을 못 그림, 이번 세션에 잡은 버그).
    tr = [("Gil-Chain", a.name), ("Gil-Kind", "chain-root"),
          ("Gil-Chain-Purpose", a.purpose)]
    _commit(subject, body, tr)
    print(f"chain: {a.name} 개설 — 목적: {a.purpose}")


def topological_leaves(tips):
    """팁 목록에서 위상적 끝단만 추린다 — 다른 팁의 조상인 팁은 제외.

    상현님 통찰: "위상이 같은 끝단끼리 머지하면 된다. 모든 노드를 각각 머지하는
    건 바보 같다." 다른 팁의 조상인 팁은 그 팁을 머지하면 자동 포함되므로, 누구의
    조상도 아닌 끝단만 머지하면 전부 묶인다.
    """
    shas = {t: _git("rev-parse", t).strip() for t in tips}
    leaves = []
    for a in tips:
        covered = False
        for b in tips:
            if a == b:
                continue
            # a가 b의 조상이면(그리고 같은 커밋이 아니면) a는 끝단 아님
            r = subprocess.run(["git", "merge-base", "--is-ancestor",
                                shas[a], shas[b]], capture_output=True)
            if r.returncode == 0 and shas[a] != shas[b]:
                covered = True
                break
        if not covered and a not in [l for l in leaves]:
            # 같은 sha 중복 제거
            if shas[a] not in {shas[l] for l in leaves}:
                leaves.append(a)
    return leaves


def cmd_chain_merge(args):
    """gil chain-merge <newchain> --purpose <P> <tip>...

    흩어진 체인들을 하나로 묶는다 (상현님: **체인 머지는 gil 레벨 표현이고 실동작은
    브랜치 머지 — git merge로 동작한다**). 주어진 팁들 중 위상적 끝단만 자동 추려
    실제 `git merge`로 파일 트리까지 병합한다. Gil-Merge trailer는 그 위에 얹는 gil
    레벨 표현일 뿐, 실체는 진짜 머지 커밋(파일 병합·다부모).

    현재 브랜치(HEAD) 위에서 끝단들을 octopus 머지한다. 충돌이 나면 자동 해결하지
    않고 abort 후 멈춘다 — 충돌 해결은 git 표준 흐름(사람/후속 스텝)이 맡는다.
    """
    import argparse
    p = argparse.ArgumentParser(prog="gil chain-merge")
    p.add_argument("name")
    p.add_argument("--purpose", required=True)
    p.add_argument("tips", nargs="+", help="묶을 체인 팁들 (브랜치/ref). 위상적 "
                                           "끝단만 자동 추려 머지한다.")
    a = p.parse_args(args)
    if not ID_RE.match(a.name):
        sys.exit(f'거부: 체인 이름 "{a.name}"은 소문자·숫자·하이픈만')
    if chain_purpose(a.name):
        sys.exit(f'거부: 체인 "{a.name}" 이미 존재')

    # 추적 파일에 미커밋 변경이 있으면 머지 불가(충돌·섞임 방지). untracked
    # 산출물(빌드 결과 등)은 머지와 무관하므로 무시(-uno).
    if _git("status", "--porcelain", "-uno").strip():
        sys.exit("거부: 추적 파일에 미커밋 변경이 있다 — 머지 전 정리하라")

    leaves = topological_leaves(a.tips)
    dropped = [t for t in a.tips if t not in leaves]
    print(f"위상적 끝단 {len(leaves)}개: {', '.join(leaves)}", file=sys.stderr)
    if dropped:
        print(f"조상이라 생략(자동 포함): {', '.join(dropped)}", file=sys.stderr)

    # 현재 HEAD가 이미 어떤 끝단의 후손이면 그 끝단은 머지 불필요(이미 포함). 남은
    # 끝단만 실제 머지 대상.
    head = _git("rev-parse", "HEAD").strip()
    to_merge = []
    for lf in leaves:
        s = _git("rev-parse", lf).strip()
        r = subprocess.run(["git", "merge-base", "--is-ancestor", s, head],
                           capture_output=True)
        if r.returncode != 0:  # 아직 HEAD 조상 아님 → 머지 필요
            to_merge.append(lf)
    if not to_merge:
        sys.exit("거부: 머지할 끝단이 없다 — HEAD가 이미 모두 포함")

    # 순차 머지 (한 끝단씩). octopus는 충돌 해결을 못 하므로, 끝단을 하나씩 git
    # merge하며 충돌이 나면 **abort하지 않고 멈춘다** — 충돌 상태를 워킹트리에 남겨
    # 충돌 해결 체인의 사이클이 해결하게 한다 (상현님: 순차 머지하며 충돌 해결을
    # 체인·사이클로). Gil-Merge trailer는 각 머지 커밋에 얹는 gil 레벨 표현.
    for i, lf in enumerate(to_merge, 1):
        subject = f"gil {a.name} chain-merge ({i}/{len(to_merge)}): {lf} 병합"
        r = subprocess.run(["git", "merge", "--no-ff", "-m", subject, lf],
                           capture_output=True, text=True)
        if r.returncode != 0:
            # 충돌 — 멈춘다(abort 안 함). 해결은 충돌 해결 체인이 이어서.
            conflicts = _git("diff", "--name-only", "--diff-filter=U").strip()
            print(f"⚠ 충돌 — [{lf}] 병합에서 멈춤 ({i}/{len(to_merge)}).\n"
                  f"충돌 파일:\n{conflicts}\n\n"
                  f"충돌 해결 체인을 열어 사이클로 해결하라. 해결 후:\n"
                  f"  git add <해결한 파일> && gil chain-merge-continue {a.name} {lf}\n"
                  f"남은 끝단: {', '.join(to_merge[i:]) or '(없음)'}", file=sys.stderr)
            sys.exit(2)  # 2 = 충돌로 멈춤 (거부 1과 구분)
        # 머지 성공 → 이 머지 커밋에 Gil-* trailer amend. 첫 머지 커밋이 통합 체인의
        # 루트 — Gil-Kind: chain-root로 표식(뷰어·fsck가 체인 루트를 이 kind로 감지).
        tr = [("Gil-Chain", a.name)]
        if i == 1:
            tr.append(("Gil-Kind", "chain-root"))
            tr.append(("Gil-Chain-Purpose", a.purpose))
        tr.append(("Gil-Merge", lf))
        cur = _git("log", "-1", "--format=%B").rstrip()
        msg = cur + "\n\n" + "\n".join(f"{k}: {v}" for k, v in tr)
        subprocess.run(["git", "commit", "--amend", "-q", "-F", "-"],
                       input=msg, text=True, check=True)
        print(f"  ✓ {lf} 병합 ({i}/{len(to_merge)})", file=sys.stderr)

    new = _git("rev-parse", "HEAD").strip()
    print(f"chain-merge: {a.name} 개설 — {len(to_merge)}갈래 순차 병합 완료 "
          f"(커밋 {new[:9]})")


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


def cmd_web(args):
    """gil web [-o out.html] [--live [--port P] [--interval S] [--no-open]]

    -o     : 정적 자기완결 번들(file://로 열림). 지금까지의 동작.
    --live : ThreadingHTTPServer + SSE. 커밋 그래프가 자라면 브라우저 자동 갱신.
    (인자 없음): 정적 문서를 stdout으로.
    """
    import gilweb
    rest = list(args)

    if "--live" in rest:
        rest.remove("--live")
        port, interval, open_browser = 8737, 1.0, True
        if "--port" in rest:
            i = rest.index("--port"); port = int(rest[i + 1]); del rest[i:i + 2]
        if "--interval" in rest:
            i = rest.index("--interval"); interval = float(rest[i + 1]); del rest[i:i + 2]
        if "--no-open" in rest:
            rest.remove("--no-open"); open_browser = False
        gilweb.serve_live(port=port, interval=interval, open_browser=open_browser)
        return

    dst = None
    if "-o" in rest:
        i = rest.index("-o")
        dst = rest[i + 1]
        del rest[i:i + 2]
    if dst:
        size, n = gilweb.write_bundle(dst)  # 메인 HTML + 사이드 번들(지연 로드)
        print(f"wrote {dst} ({size} bytes) + {gilweb.DATA_DIR}/ ({n} step pages)")
    else:
        sys.stdout.write(gilweb.render())


# ── 글로벌 진실원 (refs/gil/global — 브랜치 아닌 전용 ref, 모든 체인 공유) ──
#   대문(memory·handoff 상태)이 체인 브랜치마다 흩어지는 긴장을, 브랜치 밖 단일 ref로
#   해소. 어느 체인에서든 같은 글로벌을 읽고 쓴다. checkout 불필요. 브랜치 목록에 안 뜸.

GLOBAL_REF = "refs/gil/global"


def _global_read(name):
    """글로벌 ref에서 파일 하나를 읽는다. 없으면 None."""
    try:
        return subprocess.run(["git", "show", f"{GLOBAL_REF}:{name}"],
                              capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None


def _global_list():
    """글로벌 ref에 담긴 파일 목록. ref 없으면 []."""
    try:
        out = subprocess.run(["git", "ls-tree", "--name-only", "-r", GLOBAL_REF],
                             capture_output=True, text=True, check=True).stdout
        return [x for x in out.splitlines() if x.strip()]
    except subprocess.CalledProcessError:
        return []


def _global_write(name, content, message):
    """글로벌 ref의 파일 하나를 갱신(추가/덮어쓰기). checkout 없이 저수준 git으로.

    기존 트리에 name→새 blob을 얹어 새 트리·커밋을 만들고 refs/gil/global을 옮긴다.
    다른 파일은 보존된다.
    """
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          input=content, text=True, capture_output=True,
                          check=True).stdout.strip()
    # 기존 트리 항목 수집 (있으면)
    entries = {}
    try:
        out = subprocess.run(["git", "ls-tree", GLOBAL_REF],
                             capture_output=True, text=True, check=True).stdout
        for ln in out.splitlines():
            meta, _, fn = ln.partition("\t")
            if fn:
                entries[fn] = meta  # "100644 blob <sha>"
    except subprocess.CalledProcessError:
        pass
    entries[name] = f"100644 blob {blob}"
    tree_input = "".join(f"{meta}\t{fn}\n" for fn, meta in sorted(entries.items()))
    tree = subprocess.run(["git", "mktree"], input=tree_input, text=True,
                          capture_output=True, check=True).stdout.strip()
    # 부모(있으면)로 커밋 연쇄 — 글로벌도 append-only 히스토리
    parent = []
    try:
        p = subprocess.run(["git", "rev-parse", GLOBAL_REF],
                           capture_output=True, text=True, check=True).stdout.strip()
        parent = ["-p", p]
    except subprocess.CalledProcessError:
        pass
    commit = subprocess.run(["git", "commit-tree", tree, *parent],
                            input=message, text=True, capture_output=True,
                            check=True).stdout.strip()
    subprocess.run(["git", "update-ref", GLOBAL_REF, commit], check=True)
    return commit[:9]


def _global_push():
    """글로벌 ref를 원격에 푸시 — 커스텀 ref라 기본 push엔 안 딸려오므로 명시적으로.

    여러 머신에서 동일 글로벌을 유지하려면 필수(상현님). 원격 없으면 조용히 넘어간다.
    """
    r = subprocess.run(["git", "push", "origin",
                        f"{GLOBAL_REF}:{GLOBAL_REF}"],
                       capture_output=True, text=True)
    return r.returncode == 0


def _global_pull():
    """원격의 글로벌 ref를 로컬로 가져온다 — 다른 머신·세션이 갱신한 걸 받는다."""
    r = subprocess.run(["git", "fetch", "origin",
                        f"{GLOBAL_REF}:{GLOBAL_REF}"],
                       capture_output=True, text=True)
    return r.returncode == 0


def _ensure_global_refspec():
    """글로벌 ref가 일반 fetch에 자동으로 딸려오도록 refspec을 config에 등록(멱등).

    이러면 `git fetch`만으로도 원격 글로벌이 로컬에 동기화된다. 여러 머신 일관성.
    """
    spec = f"+{GLOBAL_REF}:{GLOBAL_REF}"
    existing = subprocess.run(
        ["git", "config", "--get-all", "remote.origin.fetch"],
        capture_output=True, text=True).stdout.splitlines()
    if spec not in existing:
        subprocess.run(["git", "config", "--add", "remote.origin.fetch", spec],
                       check=True)
        return True
    return False


def _global_write_paths(paths, message):
    """여러 파일/디렉토리를 글로벌 ref에 이전(중첩 디렉토리 지원). 기존 글로벌 보존.

    임시 git index에 (1) 기존 글로벌 트리를 read-tree로 얹고 (2) paths를 add해
    write-tree로 새 트리를 만든다. checkout·작업트리 오염 없음.
    """
    import tempfile
    import os as _os
    idx = tempfile.NamedTemporaryFile(delete=False, suffix=".gilidx").name
    env = dict(_os.environ, GIT_INDEX_FILE=idx)
    try:
        # 기존 글로벌 트리를 임시 index에 (있으면)
        if subprocess.run(["git", "rev-parse", "--verify", "-q", GLOBAL_REF],
                          capture_output=True).returncode == 0:
            subprocess.run(["git", "read-tree", GLOBAL_REF], env=env, check=True)
        # paths(작업트리의 파일/디렉토리)를 index에 add
        subprocess.run(["git", "add", "--", *paths], env=env, check=True)
        tree = subprocess.run(["git", "write-tree"], env=env,
                              capture_output=True, text=True, check=True).stdout.strip()
    finally:
        if _os.path.exists(idx):
            _os.remove(idx)
    parent = []
    p = subprocess.run(["git", "rev-parse", "-q", "--verify", GLOBAL_REF],
                       capture_output=True, text=True)
    if p.returncode == 0:
        parent = ["-p", p.stdout.strip()]
    commit = subprocess.run(["git", "commit-tree", tree, *parent],
                            input=message, text=True, capture_output=True,
                            check=True).stdout.strip()
    subprocess.run(["git", "update-ref", GLOBAL_REF, commit], check=True)
    return commit[:9]


def cmd_global(args):
    """gil global <list|read|write|push|pull|sync> — 글로벌 진실원(refs/gil/global).

      gil global list                  — 담긴 파일 목록
      gil global read <name>           — 파일 내용 출력
      gil global write <name> <file>   — <file>을 글로벌 <name>으로 갱신 (+자동 push)
      gil global push / pull           — 원격과 수동 동기화
      gil global sync                  — refspec 등록 + pull (다른 머신 갱신 받기)

    커스텀 ref는 기본 git push/fetch에 안 딸려오므로 gil이 명시적으로 동기화한다 —
    여러 머신에서 동일 글로벌을 유지(상현님).
    """
    if not args:
        sys.exit("사용: gil global <list|read|write|push|pull|sync>")
    sub = args[0]
    if sub == "list":
        files = _global_list()
        if not files:
            print(f"글로벌 비어 있음 ({GLOBAL_REF} 없음).")
        for f in files:
            print(f)
    elif sub == "read":
        if len(args) < 2:
            sys.exit("사용: gil global read <name>")
        c = _global_read(args[1])
        if c is None:
            sys.exit(f"거부: 글로벌에 {args[1]} 없음")
        sys.stdout.write(c)
    elif sub == "write":
        if len(args) < 3:
            sys.exit("사용: gil global write <name> <file>")
        name, path = args[1], args[2]
        content = open(path, encoding="utf-8").read()
        sha = _global_write(name, content, f"gil global write: {name}\n")
        pushed = _global_push()  # 갱신 즉시 원격 동기화(여러 머신 일관성)
        note = " + 원격 push" if pushed else " (원격 push 실패/없음 — gil global push 재시도)"
        print(f"글로벌 {name} 갱신 → {GLOBAL_REF} ({sha}){note}")
    elif sub == "write-tree":
        # gil global write-tree <path>... — 여러 파일/디렉토리를 글로벌로 이전
        if len(args) < 2:
            sys.exit("사용: gil global write-tree <path>...")
        paths = args[1:]
        sha = _global_write_paths(paths, f"gil global write-tree: {' '.join(paths)}\n")
        pushed = _global_push()
        note = " + 원격 push" if pushed else " (push 실패/없음)"
        print(f"글로벌에 이전: {', '.join(paths)} → {GLOBAL_REF} ({sha}){note}")
    elif sub == "checkout":
        # gil global checkout <path> [dest] — 글로벌 ref의 경로를 로컬로 꺼낸다(조회용)
        if len(args) < 2:
            sys.exit("사용: gil global checkout <path> [dest]")
        src = args[1]
        dest = args[2] if len(args) > 2 else src
        import os as _os
        # 디렉토리면 전체, 파일이면 하나
        files = subprocess.run(["git", "ls-tree", "--name-only", "-r",
                                f"{GLOBAL_REF}", "--", src],
                               capture_output=True, text=True).stdout.splitlines()
        if not files:
            sys.exit(f"거부: 글로벌에 {src} 없음")
        for f in files:
            content = _global_read(f)
            if content is None:
                continue
            out = f if dest == src else f.replace(src, dest, 1)
            _os.makedirs(_os.path.dirname(out) or ".", exist_ok=True)
            open(out, "w", encoding="utf-8").write(content)
        print(f"글로벌 {src} → 로컬 {dest} ({len(files)}파일 꺼냄)")
    elif sub == "push":
        print("원격 push 완료" if _global_push() else "원격 push 실패(원격 없음?)")
    elif sub == "pull":
        print("원격 pull 완료" if _global_pull() else "원격 pull 실패(글로벌 ref 없음?)")
    elif sub == "sync":
        added = _ensure_global_refspec()
        pulled = _global_pull()
        print(f"글로벌 동기화 — refspec {'등록' if added else '이미 있음'}, "
              f"pull {'완료' if pulled else '실패'}. 이제 git fetch에 글로벌이 딸려온다.")
    else:
        sys.exit(f"거부: 알 수 없는 global 하위명령 {sub!r}")


def _next_allowed(tip_kind, tip_outcome):
    """스텝 원칙상 팁 다음에 허용되는 동작 (다음 세션이 이어받을 것)."""
    if tip_kind == "define":
        return "step --kind hypothesis"
    if tip_kind == "hypothesis":
        return "step --kind verify"
    if tip_kind == "verify":
        return "step --kind analyze --outcome {success|backtrack|fail} | step --kind pending"
    if tip_kind == "pending":
        return "사람 답 대기 — 승인→analyze/success, 기각→analyze/backtrack --to <define>"
    if tip_kind == "analyze" and tip_outcome == "success":
        return "close (산 잎) | step --kind hypothesis --to <define> (다른 정답 탐색)"
    if tip_kind == "analyze" and tip_outcome in ("backtrack", "fail"):
        return "step --kind hypothesis --to <조상 define> (되돌아가 새 가지)"
    return "?"


def cmd_handoff(args):
    """gil handoff — 커밋 그래프에서 세션 부활 정보를 자동으로 뽑는다.

    다음 세션이 "무엇을 이어받아야 하는지"를 한눈에: 열린 체인·사이클, 각 팁,
    다음 허용 동작, pending(사람 대기), 계보. 사람이 memory를 훑는 수고를 줄인다.

    --update-docs: CLAUDE.md의 gil:status 마커 사이를 이 정보로 자동 갱신(문서 항상 최신).
    """
    report = _handoff_report()
    if "--update-docs" in args:
        _update_status_docs(report)
        print(report)
        print("\n[--update-docs] CLAUDE.md의 gil:status 섹션을 갱신했다.")
    else:
        print(report)


def _handoff_report():
    """세션 부활 정보를 문자열로 (print·문서 삽입 공용)."""
    import gilweb
    L = ["═══ gil handoff — 세션 부활 정보 ═══", ""]
    chains = gilweb.chains_from_graph()
    open_chains = {k: v for k, v in chains.items() if v["status"] == "open"}
    if not open_chains:
        L.append("열린 체인 없음 — 모든 체인이 닫혔거나 init뿐. 새 체인을 열 수 있다.")
    for cname, cinfo in open_chains.items():
        L.append(f"▶ 열린 체인: {cname} ({cinfo['mode']} 모드)")
        cyc = gilweb.cycles_of(cname)
        open_cyc = {cid: c for cid, c in cyc.items()
                    if c["status"] in ("in_progress", "pending")}
        if not open_cyc:
            L.append("    열린 사이클 없음 — 닫힌 사이클 끝에서 새 사이클을 연다.")
        for cid, c in open_cyc.items():
            tip = c["steps"][-1]
            nxt = _next_allowed(tip["kind"], tip["outcome"])
            oc = f"/{tip['outcome']}" if tip["outcome"] else ""
            L.append(f"    ◦ 사이클 {cid} ({c['status']})")
            L.append(f"        팁: {tip['step']} [{tip['kind']}{oc}]")
            L.append(f"        다음 허용: {nxt}")
            if tip["kind"] == "pending":
                L.append("        ⏳ PENDING — 재개 시 먼저 사람 답을 받아야 한다.")
    L.append("")
    L.append(f"▶ 체인 계보 ({len(chains)}개):")
    for cname, cinfo in chains.items():
        par = "+".join(cinfo["parents"]) or "(대문)"
        L.append(f"    {cname} ({cinfo['status']}) ← {par}")
    L.append("")
    # 글로벌 진실원 안내 (refs/gil/global — 어느 체인에서든 같은 것)
    gfiles = _global_list()
    if gfiles:
        L.append("")
        L.append(f"▶ 글로벌 진실원 ({GLOBAL_REF} — 체인 넘어 단일):")
        for f in gfiles:
            L.append(f"    {f}  (읽기: gil global read {f})")
    L.append("")
    L.append("복원 경로: CLAUDE.md → 존재(existence) → gil global read memory.md "
             "→ 이 handoff → 위 팁에서 이어간다.")
    return "\n".join(L)


def _update_status_docs(report):
    """CLAUDE.md의 <!-- gil:status:start --> ~ end 사이를 report로 갱신."""
    import os
    # 대문 CLAUDE.md 위치 — source/gil.py에서 레포 루트로
    #   source → gil-v3-redesign → project → 루트 (3단계)
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.normpath(os.path.join(here, "..", "..", ".."))
    path = os.path.join(root, "CLAUDE.md")
    if not os.path.exists(path):
        sys.exit(f"거부: {path} 없음 (gil:status 마커를 둔 CLAUDE.md 필요)")
    text = open(path, encoding="utf-8").read()
    START, END = "<!-- gil:status:start -->", "<!-- gil:status:end -->"
    if START not in text or END not in text:
        sys.exit("거부: CLAUDE.md에 gil:status 마커 없음")
    pre = text[:text.index(START) + len(START)]
    post = text[text.index(END):]
    block = (f"\n## 현재 상태 (gil handoff 자동 갱신)\n\n```\n{report}\n```\n")
    open(path, "w", encoding="utf-8").write(pre + block + post)


COMMANDS = {
    "chain": cmd_chain, "chain-merge": cmd_chain_merge,
    "open": cmd_open, "step": cmd_step, "close": cmd_close,
    "log": cmd_log, "fsck": cmd_fsck, "web": cmd_web, "handoff": cmd_handoff,
    "global": cmd_global,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "log"
    rest = sys.argv[2:]
    if cmd not in COMMANDS:
        sys.exit(f"gil: 알 수 없는 명령 {cmd!r} — {list(COMMANDS)}")
    COMMANDS[cmd](rest)
