#!/usr/bin/env python3
"""ari — Ariadne 사이클 체인 도구 (loom/C005: 웹 뷰어).

서브커맨드:
    log  [chains-root]                 체인들의 계보를 재구성해 그래프로 렌더한다.
    fsck [chains-root]                 스키마 v0.2 규칙(R1~R8) 위반을 전부 수집해 보고한다.
    open  <chain> <slug> [옵션]        v0.2 준수 사이클을 생성한다 (사전 검증 → 템플릿 복사 → fsck 확인).
    close <chain> <cycle-id> [옵션]    보고서를 검증하고 사이클을 닫는다. --git이면 사이클
                                       디렉토리만을 담은 커밋 + 주석 태그 cycle/<chain>/<id>를 남긴다.
    verify [chains-root]               닫힌 사이클마다 태그와 작업 트리를 대조해 변조를 탐지한다.
    web  [chains-root] -o out.html     log와 같은 파서로 자기완결적 정적 HTML 뷰어를 생성한다.

계승: loom/C001(log) → C002(fsck) → C003(open/close) → C004(깃 바인딩)의 ari.py를 확장.
의존성: Python 3 표준 라이브러리 + 깃 CLI (verify/close --git에만).
스키마 규칙의 정의는 loom/C002의 schema-v0.2-draft.md 를 따른다.
"""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys


class ChainError(Exception):
    """계보 재구성을 불가능하게 만드는 결함 — 침묵하지 않고 보고되어야 한다."""


# ---------- 파싱 ----------

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
_ID_RE = re.compile(r"^C(\d{3,})-[a-z0-9][a-z0-9-]*$")  # R1


def _parse_value(raw):
    raw = raw.strip()
    if raw.startswith('"'):
        end = raw.find('"', 1)
        return raw[1:end] if end != -1 else raw[1:]
    if raw.startswith("["):
        end = raw.find("]")
        inner = raw[1 : end if end != -1 else len(raw)]
        return [v.strip().strip('"') for v in inner.split(",") if v.strip()]
    raw = re.split(r"\s+#", raw, maxsplit=1)[0].strip()  # 뒤따르는 주석 제거
    if raw in ("null", "~", ""):
        return None
    return raw


def parse_cycle_yaml(path):
    data = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = _KEY_RE.match(line)
            if m:
                data[m.group(1)] = _parse_value(m.group(2))
    return data


def _as_list(value):
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def load_chain_records(chain_dir):
    """cycle.yaml이 있는 하위 디렉토리를 전부 읽는다. 검증하지 않고 수집만 한다 (fsck용)."""
    records = []
    for entry in sorted(os.listdir(chain_dir)):
        yaml_path = os.path.join(chain_dir, entry, "cycle.yaml")
        if not os.path.isfile(yaml_path):
            continue
        data = parse_cycle_yaml(yaml_path)
        data["_dir"] = entry
        data["parents"] = _as_list(data.get("parent"))
        data["lineage_list"] = _as_list(data.get("lineage"))
        records.append(data)
    return records


def load_chain(chain_dir):
    """log용 로더 — 재구성을 막는 결함은 즉시 오류로 보고한다."""
    cycles = {}
    for data in load_chain_records(chain_dir):
        cid = data.get("id")
        if not cid:
            raise ChainError(f"{os.path.join(chain_dir, data['_dir'])}: id 필드가 없다")
        if cid != data["_dir"]:
            print(f"경고: 디렉토리명 '{data['_dir']}' ≠ id '{cid}' — id를 기준으로 처리", file=sys.stderr)
        if cid in cycles:
            raise ChainError(f"체인 '{os.path.basename(chain_dir)}': id '{cid}' 중복")
        cycles[cid] = data
    return cycles


# ---------- 그래프 재구성 ----------

def _toposort(ids, edges):
    """edges: {child: [parents]}. (순서, 자식맵, 순환에 갇힌 노드들)을 반환."""
    children = {cid: [] for cid in ids}
    indegree = {cid: 0 for cid in ids}
    for child, parents in edges.items():
        for p in parents:
            children[p].append(child)
            indegree[child] += 1
    for p in children:
        children[p].sort()
    order, ready = [], sorted(cid for cid, d in indegree.items() if d == 0)
    while ready:
        node = ready.pop(0)
        order.append(node)
        newly = []
        for ch in children[node]:
            indegree[ch] -= 1
            if indegree[ch] == 0:
                newly.append(ch)
        ready = sorted(ready + newly)
    stuck = sorted(set(ids) - set(order))
    return order, children, stuck


def build_graph(chain_name, cycles):
    edges = {}
    for cid, data in cycles.items():
        for p in data["parents"]:
            if p not in cycles:
                raise ChainError(
                    f"체인 '{chain_name}': {cid}의 parent '{p}'가 존재하지 않는다 (끊어진 참조)"
                )
        edges[cid] = data["parents"]
    order, children, stuck = _toposort(set(cycles), edges)
    if stuck:
        raise ChainError(f"체인 '{chain_name}': 순환 참조 발견 — 다음 사이클이 그래프를 이루지 못한다: {', '.join(stuck)}")
    return order, children


# ---------- log 렌더링 ----------

def _row(cells, tail=""):
    return (" ".join(cells).rstrip() + ("  " + tail if tail else "")).rstrip()


def render_graph(order, cycles, children):
    lines = []
    tracks = []  # tracks[i] = 아직 그려지지 않은 자식 노드의 id (부모→자식 간선 하나당 하나)
    for node in order:
        incoming = [i for i, t in enumerate(tracks) if t == node]
        kids = children[node]

        if incoming:
            col = incoming[0]
            if len(incoming) > 1:  # 병합
                span = incoming[-1]
                merged = ""
                for i in range(len(tracks)):
                    if i == col:
                        merged += "├"
                    elif i in incoming:
                        merged += "┘" if i == span else "┴"
                    elif col < i < span:
                        merged += "┼" if tracks[i] != node else "─"
                    else:
                        merged += "│"
                    if i < len(tracks) - 1:
                        merged += "─" if col <= i < span else " "
                lines.append(merged.rstrip())
                for i in reversed(incoming[1:]):
                    tracks.pop(i)
        else:  # root
            tracks.append(None)
            col = len(tracks) - 1

        cells = ["●" if i == col else "│" for i in range(len(tracks))]
        meta = cycles[node]
        tail = f"{node} [{meta.get('status') or '?'}] {meta.get('title') or ''}"
        if len(meta["parents"]) > 1:
            tail += f"  ◀ 병합: {' + '.join(meta['parents'])}"
        if meta["lineage_list"]:
            tail += f"  ⇠ lineage: {', '.join(meta['lineage_list'])}"
        lines.append(_row(cells, tail))

        if kids:
            tracks[col] = kids[0]
            extra = kids[1:]
            if extra:  # 분기
                start = len(tracks)
                tracks.extend(extra)
                span = len(tracks) - 1
                branched = ""
                for i in range(len(tracks)):
                    if i == col:
                        branched += "├"
                    elif start <= i:
                        branched += "┐" if i == span else "┬"
                    elif col < i:
                        branched += "┼" if i < start else "─"
                    else:
                        branched += "│"
                    if i < len(tracks) - 1:
                        branched += "─" if col <= i < span else " "
                lines.append(branched.rstrip())
        else:
            tracks.pop(col)
    return lines


def summarize(order, cycles, children):
    roots = [c for c in order if not cycles[c]["parents"]]
    lines = [f"root: {', '.join(roots)}"]
    for b, kids in sorted(children.items()):
        if len(kids) > 1:
            lines.append(f"분기점: {b} → {', '.join(kids)}")
    for c in order:
        if len(cycles[c]["parents"]) > 1:
            lines.append(f"병합점: {c} ← {', '.join(cycles[c]['parents'])}")
    return lines


def log_chain(chain_name, chain_dir):
    cycles = load_chain(chain_dir)
    if not cycles:
        return
    order, children = build_graph(chain_name, cycles)
    print(f"=== chain: {chain_name} — 사이클 {len(cycles)}개 ===")
    print()
    for line in render_graph(order, cycles, children):
        print(line)
    print()
    for line in summarize(order, cycles, children):
        print(line)
    print()
    print("계보 (토폴로지 순서, 동순위는 id 오름차순):")
    for cid in order:
        parents = cycles[cid]["parents"]
        print(f"  {cid}  ←  {', '.join(parents) if parents else '(root)'}")
    print()


# ---------- fsck (스키마 v0.2 규칙 R1~R8) ----------

def fsck_collect(chains):
    """chains: {체인명: records}. 위반 리스트 [(규칙, 위치, 메시지)]를 반환한다."""
    violations = []
    ids_by_chain = {ch: {r.get("id") for r in recs} for ch, recs in chains.items()}

    for ch, recs in sorted(chains.items()):
        numbers = {}
        for r in recs:
            cid = r.get("id")
            loc = f"{ch}/{r['_dir']}"
            if not cid:
                violations.append(("R1", loc, "id 필드가 없다"))
                continue
            m = _ID_RE.match(cid)
            if not m:
                violations.append(("R1", loc, f"id '{cid}' 형식 위반 — C<3자리 이상 번호>-<소문자 케밥 슬러그>"))
            else:
                numbers.setdefault(m.group(1), []).append(cid)
            if r.get("chain") != ch:
                violations.append(("R4", loc, f"chain 필드 '{r.get('chain')}' ≠ 소속 체인 '{ch}'"))
            if cid != r["_dir"]:
                violations.append(("R5", loc, f"id '{cid}' ≠ 디렉토리명 '{r['_dir']}'"))
            for p in r["parents"]:
                if "/" in p:  # 표기가 틀리면 해소 검사는 중복 보고하지 않는다
                    violations.append(("R3", loc, f"parent '{p}'는 로컬 id여야 한다 (전역 표기 금지)"))
                elif p not in ids_by_chain[ch]:
                    violations.append(("R6", loc, f"parent '{p}'가 존재하지 않는다 (끊어진 참조)"))
            for l in r["lineage_list"]:
                if l.count("/") != 1:
                    violations.append(("R3", loc, f"lineage '{l}'는 전역 표기(<chain>/<id>)여야 한다"))
                    continue
                lch, lid = l.split("/")
                if lch == ch:
                    violations.append(("R3", loc, f"lineage '{l}'가 같은 체인을 가리킨다 (같은 체인의 계보는 parent)"))
                elif lid not in ids_by_chain.get(lch, set()):
                    violations.append(("R2", loc, f"lineage '{l}'가 존재하지 않는다"))
            status, closed = r.get("status"), r.get("closed")
            if status == "closed" and not closed:
                violations.append(("R8", loc, "status가 closed인데 closed 일자가 없다"))
            elif status == "open" and closed:
                violations.append(("R8", loc, "status가 open인데 closed 일자가 있다"))
        for num, dupes in sorted(numbers.items()):
            if len(dupes) > 1:
                violations.append(("R1", ch, f"번호 {num} 중복: {', '.join(sorted(dupes))}"))
        # R7: 해소 가능한 로컬 간선만으로 순환 검사
        valid = {r.get("id") for r in recs if r.get("id")}
        edges = {
            r["id"]: [p for p in r["parents"] if "/" not in p and p in valid]
            for r in recs if r.get("id")
        }
        _, _, stuck = _toposort(valid, edges)
        if stuck:
            violations.append(("R7", ch, f"순환 참조: {', '.join(stuck)}"))
    return violations


def cmd_fsck(args):
    chains = _scan_chains(args.chains_root, args.chain)
    violations = fsck_collect(chains)
    total = sum(len(recs) for recs in chains.values())
    if violations:
        for rule, loc, msg in sorted(violations):
            print(f"{rule}  {loc}: {msg}")
        print(f"\n검사: 체인 {len(chains)}개, 사이클 {total}개 — 위반 {len(violations)}건", file=sys.stderr)
        return 1
    print(f"OK — 체인 {len(chains)}개, 사이클 {total}개, 위반 0건 (스키마 v0.2)")
    return 0


# ---------- open / close (쓰기 porcelain) ----------

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")  # R1의 슬러그 부분


def _template_dir(chains_root):
    return os.path.normpath(os.path.join(chains_root, "..", "_template"))


def _next_number(records):
    nums = []
    for r in records:
        m = _ID_RE.match(r.get("id") or "")
        if m:
            nums.append(int(m.group(1)))
    return max(nums, default=0) + 1


def _fsck_or_report(chains_root):
    violations = fsck_collect(_scan_chains(chains_root))
    if violations:
        lines = "; ".join(f"{rule} {loc}: {msg}" for rule, loc, msg in violations)
        raise ChainError(f"fsck 위반 — {lines}")


def cmd_open(args):
    chains_root = args.root
    chain_dir = os.path.join(chains_root, args.chain)
    template = _template_dir(chains_root)

    # ---- 사전 검증: 저장소를 건드리기 전에 전부 확인한다 (부분 생성물 방지) ----
    if not _SLUG_RE.match(args.slug):
        raise ChainError(f"슬러그 '{args.slug}' 형식 위반 — R1: 소문자·숫자·하이픈만 (마침표 금지)")
    if not os.path.isdir(template):
        raise ChainError(f"템플릿이 없다: {template}")
    new_chain = not os.path.isdir(chain_dir)
    if new_chain and not args.new_chain:
        raise ChainError(f"체인 '{args.chain}'이 없다 — 새로 만들려면 --new-chain")
    _fsck_or_report(chains_root)  # 깨진 저장소 위에는 짓지 않는다

    records = load_chain_records(chain_dir) if not new_chain else []
    ids = {r.get("id") for r in records}
    for p in args.parent:
        if "/" in p:
            raise ChainError(f"parent '{p}'는 로컬 id여야 한다 (R3)")
        if p not in ids:
            raise ChainError(f"parent '{p}'가 체인 '{args.chain}'에 없다 (R6 위반 예정)")
    chains = _scan_chains(chains_root)
    for l in args.lineage:
        if l.count("/") != 1:
            raise ChainError(f"lineage '{l}'는 전역 표기(<chain>/<id>)여야 한다 (R3)")
        lch, lid = l.split("/")
        if lch == args.chain:
            raise ChainError(f"lineage '{l}'가 같은 체인을 가리킨다 — 같은 체인의 계보는 parent (R3)")
        if lid not in {r.get("id") for r in chains.get(lch, [])}:
            raise ChainError(f"lineage '{l}'가 존재하지 않는다 (R2 위반 예정)")

    cid = f"C{_next_number(records):03d}-{args.slug}"
    dest = os.path.join(chain_dir, cid)
    if os.path.exists(dest):
        raise ChainError(f"이미 존재한다: {dest}")

    # ---- 생성 ----
    if new_chain:
        os.makedirs(chain_dir)
        with open(os.path.join(chain_dir, "chain.md"), "w", encoding="utf-8") as f:
            f.write(f"# Chain: {args.chain}\n\n## 이 체인이 정복하려는 문제\n\n(작성할 것)\n")
    shutil.copytree(template, dest)
    parent_val = ("null" if not args.parent
                  else args.parent[0] if len(args.parent) == 1
                  else "[" + ", ".join(args.parent) + "]")
    lineage_val = "[" + ", ".join(args.lineage) + "]"
    title = (args.title or "").replace('"', "'")
    with open(os.path.join(dest, "cycle.yaml"), "w", encoding="utf-8") as f:
        f.write(
            f"id: {cid}\n"
            f"chain: {args.chain}\n"
            f"parent: {parent_val}\n"
            f"lineage: {lineage_val}\n"
            f"author: {args.author}\n"
            f"status: open\n"
            f"opened: {args.date}\n"
            f"closed: null\n"
            f'title: "{title}"\n'
        )

    # ---- 사후 확인: 생성물이 규칙을 어기면 되돌리고 실패한다 ----
    try:
        _fsck_or_report(chains_root)
    except ChainError:
        shutil.rmtree(dest)
        raise
    print(f"열림: {args.chain}/{cid}")
    return 0


# ---------- 웹 뷰어 (log와 같은 파서, 다른 렌더러) ----------

def _layout_columns(order, cycles, children):
    """render_graph와 같은 트랙 규칙으로 각 노드의 (행, 열)을 계산한다."""
    pos, tracks = {}, []
    for row, node in enumerate(order):
        incoming = [i for i, t in enumerate(tracks) if t == node]
        if incoming:
            col = incoming[0]
            for i in reversed(incoming[1:]):
                tracks.pop(i)
        else:
            tracks.append(None)
            col = len(tracks) - 1
        pos[node] = (row, col)
        kids = children[node]
        if kids:
            tracks[col] = kids[0]
            tracks.extend(kids[1:])
        else:
            tracks.pop(col)
    return pos


# 검증된 기본 팔레트 (dataviz 레퍼런스) — 상태는 색+모양(채움/빈 원)의 이중 인코딩
_WEB_CSS = """
.ari{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;--muted:#898781;
--hairline:#e1e0d9;--edge:#a5a49c;--node:#2a78d6;--lineage:#1baf7a;--ring:rgba(11,11,11,.1);
font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--page);color:var(--ink);
margin:0;padding:32px 24px;min-height:100vh;box-sizing:border-box}
@media (prefers-color-scheme:dark){.ari{--page:#0d0d0d;--surface:#1a1a19;--ink:#ffffff;
--ink-2:#c3c2b7;--muted:#898781;--hairline:#2c2c2a;--edge:#6b6a64;--node:#3987e5;
--lineage:#199e70;--ring:rgba(255,255,255,.1)}}
:root[data-theme="dark"] .ari{--page:#0d0d0d;--surface:#1a1a19;--ink:#ffffff;--ink-2:#c3c2b7;
--muted:#898781;--hairline:#2c2c2a;--edge:#6b6a64;--node:#3987e5;--lineage:#199e70;
--ring:rgba(255,255,255,.1)}
:root[data-theme="light"] .ari{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;
--muted:#898781;--hairline:#e1e0d9;--edge:#a5a49c;--node:#2a78d6;--lineage:#1baf7a;
--ring:rgba(11,11,11,.1)}
.ari .wrap{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:20px}
.ari header h1{font-size:20px;font-weight:650;margin:0;text-wrap:balance}
.ari header p{margin:4px 0 0;color:var(--ink-2);font-size:13px}
.ari .legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--ink-2);align-items:center}
.ari .legend span{display:inline-flex;align-items:center;gap:6px}
.ari .card{background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:20px;overflow-x:auto}
.ari svg{display:block}
.ari svg text{font-family:inherit}
.ari .card h2{font-size:14px;font-weight:650;margin:0 0 12px;color:var(--ink)}
.ari table{border-collapse:collapse;width:100%;font-size:12.5px}
.ari th{text-align:left;color:var(--muted);font-weight:600;letter-spacing:.02em;
border-bottom:1px solid var(--hairline);padding:6px 10px 6px 0}
.ari td{border-bottom:1px solid var(--hairline);padding:7px 10px 7px 0;vertical-align:top;color:var(--ink-2)}
.ari td.id{color:var(--ink);font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}
.ari .pill{display:inline-block;border:1.5px solid var(--node);border-radius:99px;
padding:1px 8px;font-size:11px;color:var(--ink-2);white-space:nowrap}
.ari .pill.closed{background:var(--node);color:#fff;border-color:var(--node)}
.ari footer{color:var(--muted);font-size:11.5px}
""".strip()

_ROW_H, _COL_W, _LANE_GAP, _TOP_PAD = 64, 26, 60, 46


def _build_web_data(chains_root, only=None):
    """log와 동일한 로더·그래프 재구성. 깨진 체인이면 ChainError가 그대로 전파된다."""
    data = {}
    names = sorted(
        e for e in os.listdir(chains_root)
        if os.path.isdir(os.path.join(chains_root, e)) and (not only or e == only)
    )
    for name in names:
        cycles = load_chain(os.path.join(chains_root, name))
        if not cycles:
            continue
        order, children = build_graph(name, cycles)
        data[name] = {
            "order": order,
            "cycles": {
                cid: {
                    "status": c.get("status"), "title": c.get("title") or "",
                    "opened": c.get("opened"), "closed": c.get("closed"),
                    "parents": c["parents"], "lineage": c["lineage_list"],
                } for cid, c in cycles.items()
            },
            "children": children,
        }
    return data


def _render_svg(data):
    """모든 체인을 하나의 SVG에 레인으로 배치하고, lineage는 레인을 건너는 점선으로 그린다."""
    lanes, node_xy, lane_x = {}, {}, 24
    max_rows = 0
    for name, chain in data.items():
        pos = _layout_columns(chain["order"],
                              {cid: {"parents": c["parents"]} for cid, c in chain["cycles"].items()},
                              chain["children"])
        max_col = max((c for _, c in pos.values()), default=0)
        label_w = 230
        for cid, (row, col) in pos.items():
            node_xy[f"{name}/{cid}"] = (lane_x + 14 + col * _COL_W, _TOP_PAD + 28 + row * _ROW_H)
        lanes[name] = lane_x
        lane_x += 14 + max_col * _COL_W + label_w + _LANE_GAP
        max_rows = max(max_rows, len(chain["order"]))
    width = max(lane_x - _LANE_GAP + 24, 320)
    height = _TOP_PAD + 28 + max(max_rows - 1, 0) * _ROW_H + 56

    parts = [f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
             f'role="img" aria-label="사이클 체인 그래프">']
    # 체인 내 간선
    for name, chain in data.items():
        for child, meta in chain["cycles"].items():
            x2, y2 = node_xy[f"{name}/{child}"]
            for p in meta["parents"]:
                x1, y1 = node_xy[f"{name}/{p}"]
                parts.append(f'<path d="M{x1},{y1 + 9} C{x1},{y1 + 32} {x2},{y2 - 32} {x2},{y2 - 9}" '
                             f'fill="none" stroke="var(--edge)" stroke-width="1.6"/>')
    # lineage 간선 (점선, 레인 횡단)
    for name, chain in data.items():
        for cid, meta in chain["cycles"].items():
            x2, y2 = node_xy[f"{name}/{cid}"]
            for ref in meta["lineage"]:
                if ref in node_xy:
                    x1, y1 = node_xy[ref]
                    mx = (x1 + x2) / 2
                    parts.append(f'<path class="lineage" d="M{x1 + 10},{y1} C{mx},{y1} {mx},{y2} {x2 - 10},{y2}" '
                                 f'fill="none" stroke="var(--lineage)" stroke-width="1.6" '
                                 f'stroke-dasharray="5 4"/>')
    # 레인 헤더 + 노드
    for name, chain in data.items():
        parts.append(f'<text x="{lanes[name]}" y="{_TOP_PAD - 18}" font-size="13" font-weight="650" '
                     f'fill="var(--ink)">{html.escape(name)}</text>')
        for cid in chain["order"]:
            meta = chain["cycles"][cid]
            x, y = node_xy[f"{name}/{cid}"]
            closed = meta["status"] == "closed"
            shape = (f'<circle cx="{x}" cy="{y}" r="8" fill="var(--node)"/>' if closed else
                     f'<circle cx="{x}" cy="{y}" r="7" fill="var(--surface)" '
                     f'stroke="var(--node)" stroke-width="2.5"/>')
            tip = html.escape(f"{cid} [{meta['status']}] {meta['title']}")
            parts.append(f'<g data-cycle="{html.escape(name + "/" + cid)}"><title>{tip}</title>{shape}'
                         f'<text x="{x + 16}" y="{y - 1}" font-size="12" font-weight="600" '
                         f'fill="var(--ink)">{html.escape(cid)}</text>'
                         f'<text x="{x + 16}" y="{y + 13}" font-size="10.5" '
                         f'fill="var(--muted)">{html.escape(meta["status"] or "?")}'
                         f'{" · ⇠ " + html.escape(", ".join(meta["lineage"])) if meta["lineage"] else ""}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def _render_tables(data):
    out = []
    for name, chain in data.items():
        rows = []
        for cid in chain["order"]:
            m = chain["cycles"][cid]
            pill = f'<span class="pill{" closed" if m["status"] == "closed" else ""}">{html.escape(m["status"] or "?")}</span>'
            parents = ", ".join(m["parents"]) or "(root)"
            lineage = ", ".join(m["lineage"]) or "—"
            period = f'{m["opened"] or "?"} → {m["closed"] or "진행 중"}'
            rows.append(f'<tr><td class="id">{html.escape(cid)}</td><td>{pill}</td>'
                        f'<td>{html.escape(m["title"])}</td><td>{html.escape(parents)}</td>'
                        f'<td>{html.escape(lineage)}</td><td>{html.escape(period)}</td></tr>')
        out.append(f'<div class="card"><h2>chain: {html.escape(name)} — 사이클 {len(chain["order"])}개</h2>'
                   f'<table><thead><tr><th>사이클</th><th>상태</th><th>가설(제목)</th>'
                   f'<th>parent</th><th>lineage</th><th>기간</th></tr></thead>'
                   f'<tbody>{"".join(rows)}</tbody></table></div>')
    return "".join(out)


def render_web_page(data, page_title, generated):
    json_payload = {
        "version": "0.2",
        "chains": {
            name: {
                "order": chain["order"],
                "cycles": chain["cycles"],
            } for name, chain in data.items()
        },
    }
    n_cycles = sum(len(c["order"]) for c in data.values())
    n_lineage = sum(len(m["lineage"]) for c in data.values() for m in c["cycles"].values())
    body = f"""<div class="ari"><style>{_WEB_CSS}</style><div class="wrap">
<header><h1>{html.escape(page_title)}</h1>
<p>체인 {len(data)}개 · 사이클 {n_cycles}개 · 체인 간 lineage {n_lineage}건 · 생성 {html.escape(generated)}</p></header>
<div class="legend"><span><svg width="16" height="16"><circle cx="8" cy="8" r="6.5" fill="var(--node)"/></svg>닫힌 사이클</span>
<span><svg width="16" height="16"><circle cx="8" cy="8" r="5.5" fill="var(--surface)" stroke="var(--node)" stroke-width="2"/></svg>열린 사이클</span>
<span><svg width="26" height="16"><path d="M2,8 H24" stroke="var(--edge)" stroke-width="1.6"/></svg>parent (체인 내 계보)</span>
<span><svg width="26" height="16"><path d="M2,8 H24" stroke="var(--lineage)" stroke-width="1.6" stroke-dasharray="5 4"/></svg>lineage (체인 간 교훈)</span></div>
<div class="card">{_render_svg(data)}</div>
{_render_tables(data)}
<footer>Ariadne — 사이클은 행동 체인의 기록이다. 이 문서는 ari web이 생성한 자기완결적 정적 페이지다.</footer>
</div></div>
<script type="application/json" id="ari-data">{json.dumps(json_payload, ensure_ascii=False)}</script>"""
    return ("<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{html.escape(page_title)}</title>\n</head>\n<body>\n{body}\n</body>\n</html>\n")


def cmd_web(args):
    chains_root = args.chains_root
    if not os.path.isdir(chains_root):
        raise ChainError(f"체인 루트가 없다: {chains_root}")
    data = _build_web_data(chains_root, args.chain)  # 깨진 체인이면 여기서 실패 — 파일을 쓰지 않는다
    if not data:
        raise ChainError(f"렌더할 체인이 없다: {chains_root}")
    page = render_web_page(data, args.title, datetime.date.today().isoformat())
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"생성: {args.output} (체인 {len(data)}개)")
    return 0


# ---------- 깃 바인딩 ----------

def _git(repo, *cli, check=True):
    r = subprocess.run(["git", "-C", repo, *cli], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise ChainError(f"git {' '.join(cli)} 실패: {(r.stderr or r.stdout).strip()}")
    return r


def _repo_root(path):
    r = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _tag_name(chain, cycle_id):
    return f"cycle/{chain}/{cycle_id}"


def _tag_exists(repo, tag):
    r = _git(repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}", check=False)
    return r.returncode == 0


def cmd_verify(args):
    chains_root = args.chains_root
    repo = _repo_root(chains_root)
    if not repo:
        raise ChainError(f"깃 저장소가 아니다: {chains_root}")
    tampered, untagged, checked = [], [], 0
    for ch, recs in sorted(_scan_chains(chains_root, args.chain).items()):
        for r in recs:
            if r.get("status") != "closed" or not r.get("id"):
                continue
            checked += 1
            tag = _tag_name(ch, r["id"])
            cycle_rel = os.path.relpath(
                os.path.join(chains_root, ch, r["_dir"]), repo)
            if not _tag_exists(repo, tag):
                untagged.append(f"{ch}/{r['id']}")
                continue
            diff = _git(repo, "diff", "--name-only", tag, "--", cycle_rel)
            new = _git(repo, "status", "--porcelain", "--untracked-files=all", "--", cycle_rel)
            paths = sorted(
                set(diff.stdout.split())
                | {line[3:] for line in new.stdout.splitlines() if line.startswith("??")}
            )
            if paths:
                tampered.append((tag, paths))
    for tag, paths in tampered:
        print(f"변조 감지 [{tag}]:")
        for p in paths:
            print(f"  {p}")
    for u in untagged:
        print(f"경고: 닫힌 사이클에 태그가 없다 — {u} (백필 필요)", file=sys.stderr)
    if tampered:
        print(f"\n닫힌 사이클 {checked}개 검사 — 변조 {len(tampered)}건", file=sys.stderr)
        return 1
    print(f"OK — 닫힌 사이클 {checked}개 검사, 변조 0건" + (f" (태그 없음 {len(untagged)}건)" if untagged else ""))
    return 0


def cmd_close(args):
    chains_root = args.root
    cycle_dir = os.path.join(chains_root, args.chain, args.cycle_id)
    yaml_path = os.path.join(cycle_dir, "cycle.yaml")
    if not os.path.isfile(yaml_path):
        raise ChainError(f"사이클이 없다: {os.path.join(args.chain, args.cycle_id)}")
    data = parse_cycle_yaml(yaml_path)
    if data.get("status") == "closed":
        raise ChainError(f"{args.chain}/{args.cycle_id}: 이미 닫힌 사이클이다 — 닫힌 사이클은 수정하지 않는다")

    # --git 사전 검증: 저장소를 건드리기 전에 전부 확인한다
    repo = tag = None
    if args.git:
        repo = _repo_root(chains_root)
        if not repo:
            raise ChainError(f"--git: 깃 저장소가 아니다 — {chains_root}")
        tag = _tag_name(args.chain, args.cycle_id)
        if _tag_exists(repo, tag):
            raise ChainError(f"--git: 태그 '{tag}'가 이미 존재한다")

    report_path = os.path.join(cycle_dir, "5-report.md")
    if not os.path.isfile(report_path):
        raise ChainError(f"{args.chain}/{args.cycle_id}: 5-report.md가 없다 — 보고 없이 닫을 수 없다")
    template_report = os.path.join(_template_dir(chains_root), "5-report.md")
    if os.path.isfile(template_report):
        with open(report_path, encoding="utf-8") as f1, open(template_report, encoding="utf-8") as f2:
            if f1.read() == f2.read():
                raise ChainError(f"{args.chain}/{args.cycle_id}: 보고서가 템플릿 그대로다 — 결과 보고를 작성할 것")

    with open(yaml_path, encoding="utf-8") as f:
        original = f.read()
    updated = re.sub(r"^status:.*$", "status: closed", original, count=1, flags=re.M)
    updated = re.sub(r"^closed:.*$", f"closed: {args.date}", updated, count=1, flags=re.M)
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(updated)
    try:
        _fsck_or_report(chains_root)
    except ChainError:
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(original)  # 원상 복구
        raise
    if args.git:
        cycle_rel = os.path.relpath(cycle_dir, repo)
        title = data.get("title") or ""
        try:
            _git(repo, "add", "-A", "--", cycle_rel)
            _git(repo, "commit",
                 "-m", f"ari: close {args.chain}/{args.cycle_id}\n\n{title}",
                 "--", cycle_rel)
            _git(repo, "tag", "-a", tag, "-m", f"{args.chain}/{args.cycle_id}: {title}")
        except ChainError:
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write(original)  # 원상 복구
            _git(repo, "reset", "-q", "--", cycle_rel, check=False)
            raise
        print(f"각인: 커밋 + 태그 {tag}")
    print(f"닫힘: {args.chain}/{args.cycle_id} ({args.date})")
    return 0


# ---------- CLI ----------

def _scan_chains(root, only=None):
    if not os.path.isdir(root):
        raise ChainError(f"체인 루트가 없다: {root}")
    names = sorted(
        e for e in os.listdir(root)
        if os.path.isdir(os.path.join(root, e)) and (not only or e == only)
    )
    if only and not names:
        raise ChainError(f"체인 '{only}'이 {root}에 없다")
    return {name: load_chain_records(os.path.join(root, name)) for name in names}


def cmd_log(args):
    root = args.chains_root
    if not os.path.isdir(root):
        raise ChainError(f"체인 루트가 없다: {root}")
    names = sorted(
        e for e in os.listdir(root)
        if os.path.isdir(os.path.join(root, e)) and (not args.chain or e == args.chain)
    )
    if args.chain and not names:
        raise ChainError(f"체인 '{args.chain}'이 {root}에 없다")
    for name in names:
        log_chain(name, os.path.join(root, name))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ari", description="Ariadne 사이클 체인 도구 (스키마 v0.2 + 쓰기 porcelain)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, help_text in (
        ("log", cmd_log, "체인 계보를 그래프로 렌더"),
        ("fsck", cmd_fsck, "스키마 v0.2 규칙 위반을 전부 수집해 보고"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("chains_root", nargs="?", default="rooms/experiment/chains",
                       help="체인들이 있는 루트 디렉토리 (기본: rooms/experiment/chains)")
        p.add_argument("--chain", help="특정 체인만")
        p.set_defaults(func=func)

    today = datetime.date.today().isoformat()
    p_open = sub.add_parser("open", help="v0.2 준수 사이클 생성")
    p_open.add_argument("chain")
    p_open.add_argument("slug", help="id의 슬러그 부분 (소문자 케밥) — 번호는 자동 증가")
    p_open.add_argument("--title", default="", help="정복하려는 가장 작은 문제 한 줄")
    p_open.add_argument("--parent", action="append", default=[], help="부모 사이클의 로컬 id (병합이면 여러 번)")
    p_open.add_argument("--lineage", action="append", default=[], help="교훈의 연원, 전역 표기 <chain>/<id> (여러 번 가능)")
    p_open.add_argument("--author", default="clew", help="수행하는 존재 (존재의 방 이름)")
    p_open.add_argument("--date", default=today, help="opened 일자 (기본: 오늘)")
    p_open.add_argument("--new-chain", action="store_true", help="체인이 없으면 chain.md 스텁과 함께 생성")
    p_open.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_open.set_defaults(func=cmd_open)

    p_close = sub.add_parser("close", help="보고서 검증 후 사이클 닫기")
    p_close.add_argument("chain")
    p_close.add_argument("cycle_id")
    p_close.add_argument("--date", default=today, help="closed 일자 (기본: 오늘)")
    p_close.add_argument("--root", default="rooms/experiment/chains", help="체인 루트")
    p_close.add_argument("--git", action="store_true",
                         help="닫기와 동시에 사이클 디렉토리만 커밋하고 태그 cycle/<chain>/<id>를 남긴다")
    p_close.set_defaults(func=cmd_close)

    p_verify = sub.add_parser("verify", help="닫힌 사이클의 태그↔작업 트리 대조 (변조 탐지)")
    p_verify.add_argument("chains_root", nargs="?", default="rooms/experiment/chains",
                          help="체인 루트 (기본: rooms/experiment/chains)")
    p_verify.add_argument("--chain", help="특정 체인만")
    p_verify.set_defaults(func=cmd_verify)

    p_web = sub.add_parser("web", help="자기완결적 정적 HTML 뷰어 생성")
    p_web.add_argument("chains_root", nargs="?", default="rooms/experiment/chains",
                       help="체인 루트 (기본: rooms/experiment/chains)")
    p_web.add_argument("-o", "--output", default="ariadne-chains.html", help="출력 파일 경로")
    p_web.add_argument("--title", default="Ariadne — 사이클 체인", help="페이지 제목")
    p_web.add_argument("--chain", help="특정 체인만")
    p_web.set_defaults(func=cmd_web)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ChainError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
