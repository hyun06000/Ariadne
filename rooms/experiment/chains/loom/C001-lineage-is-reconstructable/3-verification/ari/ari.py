#!/usr/bin/env python3
"""ari — Ariadne 사이클 체인 도구 (loom/C001 프로토타입).

서브커맨드:
    log <chains-root>   체인들의 계보를 재구성해 그래프로 렌더한다.

제약: Python 3 표준 라이브러리만 사용한다. 범용 하네스는 설치 장벽이 없어야 한다.
cycle.yaml은 평탄한 key-value 문서이므로 YAML 라이브러리 없이 직접 파싱한다.
"""
import argparse
import os
import re
import sys


class ChainError(Exception):
    """계보 재구성을 불가능하게 만드는 결함 — 침묵하지 않고 보고되어야 한다."""


# ---------- 파싱 ----------

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")


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


def load_chain(chain_dir):
    """체인 디렉토리에서 사이클들을 읽는다. cycle.yaml이 있는 하위 디렉토리만 사이클이다."""
    cycles = {}
    warnings = []
    for entry in sorted(os.listdir(chain_dir)):
        yaml_path = os.path.join(chain_dir, entry, "cycle.yaml")
        if not os.path.isfile(yaml_path):
            continue
        data = parse_cycle_yaml(yaml_path)
        cid = data.get("id")
        if not cid:
            raise ChainError(f"{yaml_path}: id 필드가 없다")
        if cid != entry:
            warnings.append(f"경고: 디렉토리명 '{entry}' ≠ id '{cid}' — id를 기준으로 처리")
        if cid in cycles:
            raise ChainError(f"체인 '{os.path.basename(chain_dir)}': id '{cid}' 중복")
        parent = data.get("parent")
        data["parents"] = [parent] if isinstance(parent, str) else (parent or [])
        cycles[cid] = data
    return cycles, warnings


# ---------- 그래프 재구성 ----------

def build_graph(chain_name, cycles):
    """parent 참조로 DAG를 구성하고 토폴로지 순서(동순위는 id 오름차순)를 반환한다."""
    children = {cid: [] for cid in cycles}
    indegree = {cid: 0 for cid in cycles}
    for cid, data in cycles.items():
        for p in data["parents"]:
            if p not in cycles:
                raise ChainError(
                    f"체인 '{chain_name}': {cid}의 parent '{p}'가 존재하지 않는다 (끊어진 참조)"
                )
            children[p].append(cid)
            indegree[cid] += 1
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
    if len(order) < len(cycles):
        stuck = sorted(set(cycles) - set(order))
        raise ChainError(f"체인 '{chain_name}': 순환 참조 발견 — 다음 사이클이 그래프를 이루지 못한다: {', '.join(stuck)}")
    return order, children


# ---------- 렌더링 ----------

def _row(cells, tail=""):
    return (" ".join(cells).rstrip() + ("  " + tail if tail else "")).rstrip()


def render_graph(order, cycles, children):
    """오래된 사이클이 위로 오는 트랙 기반 ASCII 그래프.

    tracks[i] = 아직 그려지지 않은 자식 노드의 id (부모→자식 간선 하나당 트랙 하나).
    """
    lines = []
    tracks = []
    for node in order:
        incoming = [i for i, t in enumerate(tracks) if t == node]
        kids = children[node]

        if incoming:
            col = incoming[0]
            if len(incoming) > 1:  # 병합: 다른 트랙들이 col로 합류
                span = incoming[-1]
                cells = []
                for i in range(len(tracks)):
                    if i == col:
                        cells.append("├")
                    elif i in incoming:
                        cells.append("┘" if i == span else "┴")
                    elif col < i < span:
                        cells.append("┼" if tracks[i] != node else "─")
                    else:
                        cells.append("│" if i < len(tracks) else " ")
                merged = ""
                for i, c in enumerate(cells):
                    merged += c
                    if i < len(cells) - 1:
                        merged += "─" if col <= i < span else " "
                lines.append(merged.rstrip())
                for i in reversed(incoming[1:]):
                    tracks.pop(i)
        else:  # root
            tracks.append(None)
            col = len(tracks) - 1

        cells = ["●" if i == col else "│" for i in range(len(tracks))]
        meta = cycles[node]
        status = meta.get("status") or "?"
        title = meta.get("title") or ""
        badge = f"[{status}]"
        merge_note = f"  ◀ 병합: {' + '.join(meta['parents'])}" if len(meta["parents"]) > 1 else ""
        lines.append(_row(cells, f"{node} {badge} {title}{merge_note}"))

        if kids:
            tracks[col] = kids[0]
            extra = kids[1:]
            if extra:  # 분기: 새 트랙을 끝에 추가하고 연결선을 그린다
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
    branches = {c: kids for c, kids in children.items() if len(kids) > 1}
    merges = {c: cycles[c]["parents"] for c in order if len(cycles[c]["parents"]) > 1}
    lines = [f"root: {', '.join(roots)}"]
    for b, kids in sorted(branches.items()):
        lines.append(f"분기점: {b} → {', '.join(kids)}")
    for m, parents in sorted(merges.items()):
        lines.append(f"병합점: {m} ← {', '.join(parents)}")
    return lines


def log_chain(chain_name, chain_dir):
    cycles, warnings = load_chain(chain_dir)
    for w in warnings:
        print(w, file=sys.stderr)
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


def cmd_log(args):
    root = args.chains_root
    if not os.path.isdir(root):
        raise ChainError(f"체인 루트가 없다: {root}")
    chain_dirs = sorted(
        e for e in os.listdir(root)
        if os.path.isdir(os.path.join(root, e)) and (not args.chain or e == args.chain)
    )
    if args.chain and not chain_dirs:
        raise ChainError(f"체인 '{args.chain}'이 {root}에 없다")
    for name in chain_dirs:
        log_chain(name, os.path.join(root, name))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ari", description="Ariadne 사이클 체인 도구 (프로토타입)")
    sub = parser.add_subparsers(dest="command", required=True)
    p_log = sub.add_parser("log", help="체인 계보를 그래프로 렌더")
    p_log.add_argument("chains_root", nargs="?", default="rooms/experiment/chains",
                       help="체인들이 있는 루트 디렉토리 (기본: rooms/experiment/chains)")
    p_log.add_argument("--chain", help="특정 체인만")
    p_log.set_defaults(func=cmd_log)
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ChainError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
