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


def step_body(sha):
    """한 스텝 커밋의 본문(디테일) — 제목·trailer 제외한 순수 마크다운 본문.

    커밋 = 제목 + 빈줄 + 본문 + 빈줄 + Gil-* trailer. %b는 본문+trailer를 준다.
    끝의 연속된 Gil-*(또는 Co-Authored-By 등) trailer 라인을 걷어내 본문만 남긴다.
    """
    body = _git("log", "-1", "--format=%b", sha).rstrip("\n")
    lines = body.split("\n")
    # 끝에서부터 trailer 블록만 제거. trailer는 **알려진 키**(Gil-* 또는 Co-Authored-By)
    # 로 시작하는 라인만 — 본문에도 "막힘: …"처럼 콜론이 흔하므로 접두사로 엄격히 구분.
    TRAILER_PREFIXES = ("Gil-", "Co-Authored-By:", "Co-authored-by:", "Signed-off-by:")
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


def declared_chains(rev_range="HEAD"):
    """선언된 체인 = Gil-Chain trailer를 가진 모든 커밋 (체인 루트 포함).

    체인 루트 커밋(gil init·chain-root)엔 Gil-Step이 없어 collect_nodes가 안 잡지만,
    Gil-Chain은 있다. 계보 부모가 체인일 수 있으므로(원칙 2) 이걸 따로 수집한다.
    """
    out = _git("log", "--format=%(trailers:key=Gil-Chain,valueonly)", rev_range)
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


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
    a = p.parse_args(args)
    if "/" not in a.ref:
        sys.exit("거부: <chain>/<cycle> 꼴이어야 함")
    chain, cycle = a.ref.split("/", 1)
    for label, v in (("chain", chain), ("cycle", cycle)):
        if not ID_RE.match(v):
            sys.exit(f'거부: {label} id "{v}"는 소문자·숫자·하이픈만')
    if _current_cycle(chain, cycle):
        sys.exit(f"거부: {a.ref} 이미 존재 (open은 새 사이클만)")
    subject = f"gil {chain}/{cycle}/s1 define: {a.title or '(문제 미기술)'}"
    body = a.title or "(문제 미기술 — 본문을 커밋 수정으로 채우라)"
    tr = [("Gil-Chain", chain), ("Gil-Cycle", cycle),
          ("Gil-Step", "s1"), ("Gil-Kind", "define"), ("Gil-Parent", "null"),
          ("Gil-Cycle-Author", a.author)]
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
    """gil web [-o out.html] — 커밋 그래프를 체인 층 뷰어로 (가장 상위 층)."""
    import gilweb
    dst = None
    rest = list(args)
    if "-o" in rest:
        i = rest.index("-o")
        dst = rest[i + 1]
        del rest[i:i + 2]
    if dst:
        size, n = gilweb.write_bundle(dst)  # 메인 HTML + 사이드 번들(지연 로드)
        print(f"wrote {dst} ({size} bytes) + {gilweb.DATA_DIR}/ ({n} step pages)")
    else:
        sys.stdout.write(gilweb.render())


COMMANDS = {
    "open": cmd_open, "step": cmd_step, "close": cmd_close,
    "log": cmd_log, "fsck": cmd_fsck, "web": cmd_web,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "log"
    rest = sys.argv[2:]
    if cmd not in COMMANDS:
        sys.exit(f"gil: 알 수 없는 명령 {cmd!r} — {list(COMMANDS)}")
    COMMANDS[cmd](rest)
