#!/usr/bin/env python3
"""ari — Ariadne 사이클 체인 도구 (loom/C002: 스키마 v0.2).

서브커맨드:
    log  <chains-root>   체인들의 계보를 재구성해 그래프로 렌더한다.
    fsck <chains-root>   스키마 v0.2 규칙(R1~R8) 위반을 전부 수집해 보고한다.

계승: loom/C001의 ari.py를 확장. Python 3 표준 라이브러리 전용 유지.
스키마 규칙의 정의는 ../schema-v0.2-draft.md 를 따른다.
"""
import argparse
import os
import re
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
    parser = argparse.ArgumentParser(prog="ari", description="Ariadne 사이클 체인 도구 (스키마 v0.2)")
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
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ChainError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
