#!/usr/bin/env python3
"""gilv3 v0.2 — v3 스텝 트리 명령 (open/step/close/status/view) + 깃 각인.

C002가 확정한 steps.yaml 표현 위에서만 동작. 순수 stdlib.
핵심 원리:
  - **커서를 데이터에 저장하지 않는다** (C003) — 성장 팁을 트리에서 계산.
  - **깃은 별개 층** (C005) — 스텝=커밋 각인은 opt-in(--git)이며 steps.yaml에
    깃 메타를 넣지 않는다. id 순서 == 커밋 순서로 "스텝=커밋"이 나타난다.
  - **뷰어는 재구현 금지** (C005) — C004 steptree를 import 재사용.

명령:
  gilv3 open   <dir> --title <문제> [--git]
  gilv3 step   <dir> --kind <k> [--outcome <o>] [--to <define-id>] [--git]
  gilv3 close  <dir> [--git]
  gilv3 status <dir>
  gilv3 view   <dir> [-o out.html]
"""
import sys, os, argparse, subprocess


# ---- 깃 각인 (C005) — 별개 층, opt-in ----
def git_imprint(dir_, message, allow_empty=False):
    """사이클 디렉토리를 스텝 하나의 커밋으로 각인. 깃 저장소가 아니면 거부.
    allow_empty: close 봉인처럼 파일 변경 없이 의미만 각인하는 스텝(빈 커밋)."""
    repo = _git_root(dir_)
    if repo is None:
        sys.exit("거부: --git 이나 깃 저장소가 아님 (git init 먼저)")
    subprocess.run(["git", "-C", dir_, "add", "."], check=True,
                   stdout=subprocess.DEVNULL)
    cmd = ["git", "-C", dir_, "commit", "-q", "-m", message]
    if allow_empty:
        cmd.insert(4, "--allow-empty")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


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
        git_imprint(dir_, "gilv3 open %s: s1 define" % os.path.basename(os.path.abspath(dir_)))
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

    nodes.append(node)
    dump(dir_, nodes)
    write_body(dir_, sid, "# %s · %s%s\n\n%s" % (
        sid, kind,
        ("/" + node["outcome"]) if node["outcome"] else "",
        args.note or "(서술 미기재)"))
    if getattr(args, "git", False):
        git_imprint(dir_, "gilv3 step: %s %s%s" % (
            sid, kind, ("/" + node["outcome"]) if node["outcome"] else ""))
    print("step: %s [%s%s] parent=%s%s" % (
        sid, kind, ("/" + node["outcome"]) if node["outcome"] else "",
        node["parent"],
        (" backtrack=" + node["backtrack"]) if node["backtrack"] else ""))


def cmd_close(args):
    nodes = load(args.dir)
    live = [n for n in nodes if n.get("outcome") == "success"]
    if not live:
        sys.exit("거부: 산 잎(success analyze) 없음 — 아직 닫을 수 없다")
    if getattr(args, "git", False):
        git_imprint(args.dir, "gilv3 close %s: 산 잎 %s (봉인)" % (
            os.path.basename(os.path.abspath(args.dir)), ",".join(n["id"] for n in live)),
            allow_empty=True)
    print("close: %s — 산 잎 %s, 사이클 닫힘 가능" % (args.dir, [n["id"] for n in live]))


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
    tip, state = growing_tip(nodes)
    print("노드 %d, 상태=%s, 팁=%s" % (len(nodes), state, tip["id"] if tip else "-"))
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
    c.add_argument("--git", action="store_true"); c.set_defaults(fn=cmd_close)
    st = sub.add_parser("status"); st.add_argument("dir"); st.set_defaults(fn=cmd_status)
    v = sub.add_parser("view"); v.add_argument("dir"); v.add_argument("-o", "--out")
    v.set_defaults(fn=cmd_view)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
