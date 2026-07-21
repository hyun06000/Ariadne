#!/usr/bin/env python3
"""gil v3.5 — v3 스텝 트리 명령 (open/step/close/status/view) + 깃 각인.

이 도구는 별개 프로토타입이 아니라 **gil 그 자체의 v3 궤도**다 (상현님, C010).
gil v2(v2.50.0)가 사이클 단위였다면 gil v3는 스텝 트리 단위이며, v3.5에서
스텝 메타를 git trailer 계약면으로 각인한다.

C002가 확정한 steps.yaml 표현 위에서만 동작. 순수 stdlib.
핵심 원리:
  - **커서를 데이터에 저장하지 않는다** (C003) — 성장 팁을 트리에서 계산.
  - **깃은 별개 층** (C005) — 스텝=커밋 각인은 opt-in(--git)이며 steps.yaml에
    깃 메타를 넣지 않는다. id 순서 == 커밋 순서로 "스텝=커밋"이 나타난다.
  - **뷰어는 재구현 금지** (C005) — C004 steptree를 import 재사용.
  - **깃 = append-only 전진기록** (C008, 상현님이 세운 정신) — 각인은 오직
    add+commit으로 앞으로만 쌓인다. reset/checkout/revert/amend/force/rebase를
    절대 호출하지 않는다. 백트래킹(죽은 잎→조상 define으로 되돌아가 새 형제 가지)
    조차 **새 전진 커밋**이다 — 되돌아감의 논리는 gil이 steps.yaml의
    parent/backtrack 포인터에 담고, 깃은 그 결과를 전진 커밋으로 받아 적을 뿐이다.
    죽은 가지의 커밋은 히스토리에 그대로 남아 '벽의 지도'가 된다.
    → _assert_forward_only가 각 각인 후 HEAD 전진 단조성을 스스로 집행한다.

명령:
  gilv3 open   <dir> --title <문제> [--git]
  gilv3 step   <dir> --kind <k> [--outcome <o>] [--to <define-id>] [--git]
  gilv3 close  <dir> [--git]
  gilv3 status <dir>
  gilv3 view   <dir> [-o out.html]
"""
import sys, os, argparse, subprocess


# ---- 깃 각인 (C005) — 별개 층, opt-in. append-only (C008). ----
def _head(dir_):
    """현재 HEAD 커밋 해시. 커밋이 없으면 None."""
    r = subprocess.run(["git", "-C", dir_, "rev-parse", "-q", "--verify", "HEAD"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.stdout.decode().strip() if r.returncode == 0 else None


def _all_commits(dir_):
    """저장소의 모든 도달 가능한 커밋 집합 (--all: 모든 ref)."""
    r = subprocess.run(["git", "-C", dir_, "rev-list", "--all"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return set(r.stdout.decode().split()) if r.returncode == 0 else set()


def _assert_append_only(dir_, before_commits):
    """각인 후 이전에 있던 모든 커밋이 여전히 존재하는가 — 커밋 불소멸 집행.

    ⭐ C014의 C008 정정 (C011 모델):
    C008의 원래 집행(_assert_forward_only)은 HEAD 전진 단조성을 봤다. 그런데 그것은
    두 가지를 뭉뚱그렸다 — (A) 커밋을 지우지 않음(append-only의 진짜 가치)과
    (B) HEAD를 뒤로 안 옮김. C008은 (A)를 지키려 (B)까지 금지해, 백트래킹=checkout
    (C011)을 불가능하게 했다.

    C011의 정정: 백트래킹=checkout은 (B)를 하지만(HEAD가 조상으로 이동) (A)는 절대
    안 한다 — 커밋을 하나도 안 지운다. 그러니 append-only의 진짜 계약은
    **커밋 도달가능성 단조**(집합이 오직 늘어남)이다. checkout은 이를 지키고,
    reset --hard/amend/rebase/push --force는 깬다.

    → 이 함수는 HEAD 전진이 아니라 '이전 커밋이 다 살아있는가'를 본다.
      checkout 백트래킹은 통과, 히스토리 재작성은 거부."""
    after = _all_commits(dir_)
    lost = before_commits - after
    if lost:
        sys.exit("거부(C014/C008): 이전 커밋 %d개가 사라졌다 — 히스토리 재작성 금지 "
                 "(reset --hard/amend/rebase/push --force). checkout은 커밋을 안 "
                 "지우므로 허용된다. 사라진 커밋: %s" % (
                     len(lost), ", ".join(sorted(c[:8] for c in lost))))


def git_imprint(dir_, message, allow_empty=False, trailers=None):
    """사이클 디렉토리를 스텝 하나의 커밋으로 각인. 깃 저장소가 아니면 거부.
    allow_empty: close 봉인처럼 파일 변경 없이 의미만 각인하는 스텝(빈 커밋).
    trailers: 스텝 메타를 커밋 본문에 git trailer로 각인 (C010, 계약면).
      subject(message)는 사람용 서술로 유지하고, 기계용 계약은 trailer로.
      복원은 `git log --format=%(trailers:key=…)`로 이 계약을 읽는다.

    append-only 계약 (C008 → C014 정정): 이 함수가 호출하는 git 하위명령은 add·commit
    (+ 백트래킹 시 checkout — cmd_step이 미리 함). reset/revert/amend/push --force/
    rebase를 절대 호출하지 않는다. 백트래킹은 C011대로 checkout 후 새 커밋으로 분기한다
    — 되돌아감은 gil이 steps.yaml 포인터로 결정하고, 깃은 그 결과를 새 가지 커밋으로
    받아 적는다. 죽은 가지 커밋은 사라지지 않는다(커밋 불소멸 = _assert_append_only)."""
    repo = _git_root(dir_)
    if repo is None:
        sys.exit("거부: --git 이나 깃 저장소가 아님 (git init 먼저)")
    before = _all_commits(dir_)  # C014: HEAD가 아니라 커밋 집합을 스냅샷
    subprocess.run(["git", "-C", dir_, "add", "."], check=True,
                   stdout=subprocess.DEVNULL)
    # 커밋 메시지 = subject + (빈 줄) + trailer 블록. trailer는 append-only에 무해.
    full = message
    if trailers:
        body = "\n".join("%s: %s" % (k, v) for k, v in trailers)
        full = message + "\n\n" + body
    cmd = ["git", "-C", dir_, "commit", "-q", "-m", full]
    if allow_empty:
        cmd.insert(4, "--allow-empty")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    _assert_append_only(dir_, before)  # C014: 커밋 불소멸 자기 집행 (checkout 허용)


def _commit_of_sid(dir_, sid):
    """스텝 id를 그 스텝의 커밋 해시로 조회 — trailer(Step-Id)를 역인덱스.
    steps.yaml에 커밋 해시를 저장하지 않는다(C005 유지) — 깃 자신에게 물어본다.
    checkout 백트래킹의 대상 커밋을 찾는 데 쓴다."""
    fmt = "%H\x1f%(trailers:key=Step-Id,valueonly)"
    r = subprocess.run(["git", "-C", dir_, "log", "--all", "--format=" + fmt],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for line in r.stdout.decode().splitlines():
        if "\x1f" not in line:
            continue
        h, tid = line.split("\x1f", 1)
        if tid.strip() == sid:
            return h.strip()
    return None


def _git_root(dir_):
    r = subprocess.run(["git", "-C", dir_, "rev-parse", "--show-toplevel"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.stdout.decode().strip() if r.returncode == 0 else None


KINDS = ["define", "hypothesis", "verify", "analyze"]
CYCLE = {"define": "hypothesis", "hypothesis": "verify", "verify": "analyze"}
OUTCOMES = {"success", "backtrack", "fail"}

KINDS = ["define", "hypothesis", "verify", "analyze"]
CYCLE = {"define": "hypothesis", "hypothesis": "verify", "verify": "analyze"}
OUTCOMES = {"success", "backtrack", "fail"}

# ---- steps.yaml I/O (C002 형식과 동일) ----
FIELDS = ["id", "kind", "parent", "outcome", "backtrack", "body"]


def _pv(s):
    s = s.strip()
    return None if s == "null" else s


def load(dir_):
    path = os.path.join(dir_, "steps.yaml")
    nodes = []
    if not os.path.exists(path):
        return nodes
    cur = None
    for raw in open(path, encoding="utf-8"):
        st = raw.strip()
        if not st or st.startswith("#"):
            continue
        if st.startswith("- "):
            if cur is not None:
                nodes.append(cur)
            cur = {}
            st = st[2:]
        if ":" not in st:
            continue
        k, _, v = st.partition(":")
        cur[k.strip()] = _pv(v)
    if cur is not None:
        nodes.append(cur)
    return nodes


def dump(dir_, nodes):
    os.makedirs(os.path.join(dir_, "steps"), exist_ok=True)
    lines = ["# v3 스텝 트리 — gilv3 생성. 트리는 parent/backtrack 포인터로만 담긴다."]
    for n in nodes:
        lines.append("- id: " + n["id"])
        for f in FIELDS[1:]:
            v = n.get(f)
            lines.append("  %s: %s" % (f, "null" if v is None else v))
    with open(os.path.join(dir_, "steps.yaml"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def write_body(dir_, sid, text):
    with open(os.path.join(dir_, "steps", sid + ".md"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


# ---- 트리 계산 ----
def next_id(nodes):
    return "s%d" % (len(nodes) + 1)


def by_id(nodes):
    return {n["id"]: n for n in nodes}


def live_leaves(nodes):
    return [n for n in nodes if n.get("kind") == "analyze" and n.get("outcome") == "success"]


def dead_leaves(nodes):
    return [n for n in nodes if n.get("kind") == "analyze" and n.get("outcome") == "backtrack"]


def cycle_state(nodes):
    """사이클 상태를 스텝 트리에서 순수 계산 (C006, 상태 필드 저장 안 함).
    in_progress: 산 잎 0 (죽은 잎만 있거나 아직 analyze 전) — 못 닫음.
    solved:      산 잎 1 — 정답 도달, 닫을 수 있음.
    multi_solution: 산 잎 ≥2 — 최적화 사이클(chain.md '다른 정답도?')."""
    n_live = len(live_leaves(nodes))
    if n_live >= 2:
        return "multi_solution"
    if n_live == 1:
        return "solved"
    return "in_progress"


def growing_tip(nodes):
    """성장 팁 = 마지막(시간순) 노드. 커서 없이 순수 계산.
    반환: (tip_node_or_None, state) — state ∈ {empty, open_branch, dead_leaf, live_leaf}"""
    if not nodes:
        return None, "empty"
    tip = nodes[-1]
    if tip["kind"] != "analyze":
        return tip, "open_branch"
    oc = tip.get("outcome")
    if oc == "success":
        return tip, "live_leaf"
    return tip, "dead_leaf"  # backtrack/fail


def allowed_next(nodes):
    """이 트리에서 지금 허용되는 행동 목록 (사람·테스트 가독)."""
    tip, state = growing_tip(nodes)
    if state == "empty":
        return ["open (루트 define 생성)"]
    if state == "open_branch":
        nk = CYCLE.get(tip["kind"])
        if nk == "analyze":
            return ["step --kind analyze --outcome {success|backtrack --to <define>}"]
        return ["step --kind %s" % nk]
    if state == "dead_leaf":
        return ["step --kind hypothesis --to <ancestor-define> (새 형제 가지)"]
    if state == "live_leaf":
        return ["close"]
    return []


# ---- 명령 ----
def cmd_open(args):
    dir_ = args.dir
    if load(dir_):
        sys.exit("거부: 이미 steps.yaml 존재 (open은 빈 사이클에만)")
    root = {"id": "s1", "kind": "define", "parent": None, "outcome": None,
            "backtrack": None, "body": "steps/s1.md"}
    dump(dir_, [root])
    write_body(dir_, "s1", "# s1 · define (루트)\n\n" + (args.title or "(문제 미기술)"))
    if getattr(args, "git", False):
        # 루트 define — 계약 trailer로 각인 (C010). Parent: null.
        git_imprint(dir_, "gilv3 open %s: s1 define" % os.path.basename(os.path.abspath(dir_)),
                    trailers=[("Step-Id", "s1"), ("Kind", "define"),
                              ("Parent", "null")])
    print("open: %s — 루트 define s1 생성" % dir_)


def cmd_step(args):
    dir_ = args.dir
    nodes = load(dir_)
    if not nodes:
        sys.exit("거부: steps.yaml 없음 (먼저 open)")
    tip, state = growing_tip(nodes)
    kind = args.kind
    if kind not in KINDS:
        sys.exit("거부: 알 수 없는 kind %r" % kind)

    if state == "live_leaf":
        sys.exit("거부: 산 잎(success)에서는 step 불가 — close만 가능")

    sid = next_id(nodes)
    node = {"id": sid, "kind": kind, "parent": None, "outcome": None,
            "backtrack": None, "body": "steps/%s.md" % sid}

    if state == "dead_leaf":
        # 되돌아감 후 새 형제 가지: 반드시 --to 조상 define + kind=hypothesis
        if kind != "hypothesis":
            sys.exit("거부: 죽은 잎 뒤에는 새 가지의 hypothesis만 (받은 kind=%s)" % kind)
        if not args.to:
            sys.exit("거부: 새 형제 가지는 --to <ancestor-define> 필요")
        tgt = by_id(nodes).get(args.to)
        if not tgt or tgt["kind"] != "define":
            sys.exit("거부: --to 대상 %r 이 조상 define 아님" % args.to)
        node["parent"] = args.to
    else:  # open_branch — 순환 강제
        want = CYCLE.get(tip["kind"])
        if want is None:
            sys.exit("거부: analyze 뒤 전이는 outcome이 결정 (내부 오류)")
        if kind != want:
            sys.exit("거부: %s 다음은 %s만 (받은 kind=%s)" % (tip["kind"], want, kind))
        node["parent"] = tip["id"]

    if kind == "analyze":
        oc = args.outcome
        if oc not in OUTCOMES:
            sys.exit("거부: analyze는 --outcome {success|backtrack|fail} 필요")
        node["outcome"] = oc
        if oc == "backtrack":
            if not args.to:
                sys.exit("거부: outcome=backtrack은 --to <ancestor-define> 필요")
            tgt = by_id(nodes).get(args.to)
            if not tgt or tgt["kind"] != "define":
                sys.exit("거부: backtrack --to %r 이 조상 define 아님" % args.to)
            node["backtrack"] = args.to
    else:
        if args.outcome:
            sys.exit("거부: outcome은 analyze에만")

    # ⭐ C014: 백트래킹 = git checkout <조상 커밋> (C011).
    # 죽은 잎 뒤 새 형제 가지(state==dead_leaf)는 조상 define으로 실제 checkout해
    # detached HEAD를 만든 뒤 그 위에 새 커밋을 친다 → 깃이 자동으로 새 가지를 친다.
    # C010판은 이 checkout 없이 선형으로 쌓아 깃 그래프가 분기를 못 그렸다.
    # steps.yaml/body 쓰기는 checkout 후 워킹트리에서 해야 커밋에 담긴다.
    did_checkout = False
    if getattr(args, "git", False) and state == "dead_leaf":
        tgt_commit = _commit_of_sid(dir_, node["parent"])
        if not tgt_commit:
            sys.exit("거부: 조상 %s 의 커밋을 찾을 수 없다 (--git 각인 이력 필요)" % node["parent"])
        # ⭐ C011 발견: checkout으로 떠나면 죽은 가지 팁이 ref 없으면 dangling→gc돼
        # git log --all에서 사라진다. 그것을 막는 '최소 못'을 떠나기 전에 박는다.
        # (C011은 이 못을 '태그'로 결론지었다 — 잎=불변 시점. 태그 자동화는 다음
        #  사이클이므로 여기선 최소 못으로 브랜치 ref를 쓴다: gil/dead/<떠나는-팁-sid>.
        #  '어떤 ref든 못이면 가지가 산다'는 C011 M3의 실측을 도구가 강제한다.)
        leaving_tip = tip["id"]  # 지금 dead_leaf 팁(방금 친 backtrack analyze 커밋)
        subprocess.run(["git", "-C", dir_, "branch", "-q",
                        "gil/dead/%s" % leaving_tip, "HEAD"],
                       check=True, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "-C", dir_, "checkout", "-q", tgt_commit],
                       check=True, stderr=subprocess.DEVNULL)
        did_checkout = True

    nodes.append(node)
    dump(dir_, nodes)
    write_body(dir_, sid, "# %s · %s%s\n\n%s" % (
        sid, kind,
        ("/" + node["outcome"]) if node["outcome"] else "",
        args.note or "(서술 미기재)"))
    if getattr(args, "git", False):
        # subject(사람용 서술) — C008 서술 유지. 되돌아감을 사람 눈에.
        note = ""
        if node["parent"] and state == "dead_leaf":
            note = " (new branch from %s after checkout-backtrack)" % node["parent"]
        elif node["backtrack"]:
            note = " (backtrack to %s)" % node["backtrack"]
        # 견고성 대조용(C010 M3): subject의 자연어 마커를 제거해도 trailer는 유지.
        # 이 모드로 각인한 저장소는 C009 자연어 복원을 깨뜨리지만 trailer 복원은 불변.
        if os.environ.get("GILV3_SCRAMBLE_SUBJECT"):
            note = ""
        subject = "gilv3 step: %s %s%s%s" % (
            sid, kind, ("/" + node["outcome"]) if node["outcome"] else "", note)
        # trailer(기계용 계약, C010) — 복원의 진실원. Parent를 명시해 자기완결.
        tr = [("Step-Id", sid), ("Kind", kind), ("Parent", node["parent"])]
        if node["outcome"]:
            tr.append(("Outcome", node["outcome"]))
        if node["backtrack"]:
            tr.append(("Backtrack-To", node["backtrack"]))
        git_imprint(dir_, subject, trailers=tr)
    print("step: %s [%s%s] parent=%s%s" % (
        sid, kind, ("/" + node["outcome"]) if node["outcome"] else "",
        node["parent"],
        (" backtrack=" + node["backtrack"]) if node["backtrack"] else ""))


def write_cycle_yaml(dir_, state, verdict, live_ids, date):
    """봉인 메타를 cycle.yaml에 쓴다 — steps.yaml과 별개 층 (C006, 트리 무오염)."""
    lines = [
        "state: %s" % state,
        "verdict: %s" % (verdict or "null"),
        "live_leaves: [%s]" % ", ".join(live_ids),
        "closed: %s" % date,
    ]
    with open(os.path.join(dir_, "cycle.yaml"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def cmd_close(args):
    nodes = load(args.dir)
    state = cycle_state(nodes)
    # S3 게이트 — 분류기에서 파생
    if state == "in_progress":
        sys.exit("거부: in_progress (산 잎 없음) — 아직 닫을 수 없다")
    live = live_leaves(nodes)
    live_ids = [n["id"] for n in live]
    if state == "multi_solution":
        sys.stderr.write("경고: multi_solution — 산 잎 %s. 여러 정답 중 선택은 "
                         "새 사이클(최적화, chain.md 그리디).\n" % live_ids)
    # S2 봉인 — cycle.yaml (steps.yaml 안 건드림)
    date = args.date or _today()
    write_cycle_yaml(args.dir, state, args.verdict, live_ids, date)
    if getattr(args, "git", False):
        # ⭐ C011: 산 잎도 못이 필요하다. 백트래킹 checkout으로 산 가지는 detached
        # HEAD에만 매달려 있어 ref가 없으면 dangling→gc된다(죽은 가지와 대칭).
        # close 시 각 산 잎을 gil/live/<sid> 브랜치로 못박아 산 가지를 살린다.
        # (죽은 잎은 step의 checkout 백트래킹 시 gil/dead/<sid>로 이미 못박음.
        #  '모든 잎에 못' = C011 build_branches.sh가 태그로 한 것의 최소 형태.
        #  태그 vs 브랜치, 해시 이름 규칙은 잎=태그 자동화 사이클(다음)의 몫.)
        for lid in live_ids:
            lc = _commit_of_sid(args.dir, lid)
            if lc:
                subprocess.run(["git", "-C", args.dir, "branch", "-q",
                                "gil/live/%s" % lid, lc],
                               stderr=subprocess.DEVNULL)
        git_imprint(args.dir, "gilv3 close %s: %s 산 잎 %s (봉인)" % (
            os.path.basename(os.path.abspath(args.dir)), state, ",".join(live_ids)))
        # ⭐ 사이클 종결 못 — close 커밋 자체를 못박는다 (C011 cycle/<name>/solved).
        # close 커밋은 산 잎 위 detached HEAD라 이 못이 없으면 checkout 시 dangling.
        # 봉인 = 사이클 종결의 불변 시점이므로 반드시 ref로 산다.
        head = _head(args.dir)
        if head:
            cyc = os.path.basename(os.path.abspath(args.dir))
            subprocess.run(["git", "-C", args.dir, "branch", "-q",
                            "gil/sealed/%s" % cyc, head],
                           stderr=subprocess.DEVNULL)
    print("close: %s — state=%s, 산 잎 %s, cycle.yaml 봉인" % (args.dir, state, live_ids))


def _today():
    # 재현성: 날짜는 인자로 받는 게 원칙이나 미지정 시 환경에서.
    import datetime
    return datetime.date.today().isoformat()


def cmd_view(args):
    """C004 steptree를 import 재사용 — 뷰어 로직 재구현 금지."""
    here = os.path.dirname(os.path.abspath(__file__))
    c004 = os.path.normpath(os.path.join(
        here, "..", "..", "C004-v3-viewer-step-tree", "3-verification"))
    sys.path.insert(0, c004)
    from steptree import html_from_yaml_text
    path = os.path.join(args.dir, "steps.yaml")
    if not os.path.exists(path):
        sys.exit("거부: %s 없음 (먼저 open/step)" % path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    doc = html_from_yaml_text(text, cycle=os.path.basename(os.path.abspath(args.dir)))
    out = args.out or os.path.join(args.dir, "out.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    print("view: %s (%d bytes) ← %s" % (out, len(doc), path))


def cmd_status(args):
    nodes = load(args.dir)
    tip, tipstate = growing_tip(nodes)
    print("노드 %d, 팁상태=%s, 팁=%s" % (len(nodes), tipstate, tip["id"] if tip else "-"))
    print("사이클 상태=%s (산 잎 %s, 죽은 잎 %s)" % (
        cycle_state(nodes),
        [n["id"] for n in live_leaves(nodes)],
        [n["id"] for n in dead_leaves(nodes)]))
    print("다음 허용:", allowed_next(nodes))


def main():
    p = argparse.ArgumentParser(prog="gilv3")
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open"); o.add_argument("dir"); o.add_argument("--title")
    o.add_argument("--git", action="store_true"); o.set_defaults(fn=cmd_open)
    s = sub.add_parser("step"); s.add_argument("dir"); s.add_argument("--kind", required=True)
    s.add_argument("--outcome"); s.add_argument("--to"); s.add_argument("--note")
    s.add_argument("--git", action="store_true"); s.set_defaults(fn=cmd_step)
    c = sub.add_parser("close"); c.add_argument("dir")
    c.add_argument("--verdict"); c.add_argument("--date")
    c.add_argument("--git", action="store_true"); c.set_defaults(fn=cmd_close)
    st = sub.add_parser("status"); st.add_argument("dir"); st.set_defaults(fn=cmd_status)
    v = sub.add_parser("view"); v.add_argument("dir"); v.add_argument("-o", "--out")
    v.set_defaults(fn=cmd_view)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
