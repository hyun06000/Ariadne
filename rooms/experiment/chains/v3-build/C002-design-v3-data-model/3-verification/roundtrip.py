#!/usr/bin/env python3
"""C002 검증 하네스 — v3 스텝 트리 데이터 모델.

순수 stdlib. steps.yaml(최소 서브셋)을 자작 파서로 읽어:
  M1: 실사례 재표현 왜곡 0 (백트래킹·죽은 잎·산 잎 보존)
  M2: 왕복 무손실 (읽기→재직렬화→비교, 노드/엣지 동형)
  M3: 명령 파생 (트리만으로 각 노드의 다음 허용 행동 결정)
을 판정한다.

사용: python3 roundtrip.py case-c012-c014/steps.yaml
"""
import sys, os

KINDS = {"define", "hypothesis", "verify", "analyze"}
OUTCOMES = {"fail", "backtrack", "success"}
# kind 상태기계: 한 가지 안에서 이 노드 다음에 허용되는 kind
NEXT_KIND = {
    "define": "hypothesis",
    "hypothesis": "verify",
    "verify": "analyze",
    # analyze는 outcome으로 분기 — 아래 derive_action에서 처리
}


def parse_val(s):
    s = s.strip()
    if s == "null":
        return None
    return s


def load_steps(path):
    """steps.yaml 최소 서브셋 파서. '- id:' 로 노드 시작, '  key: val' 로 필드."""
    nodes = []
    cur = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("- "):
                if cur is not None:
                    nodes.append(cur)
                cur = {}
                stripped = stripped[2:]  # "id: s1"
            if ":" not in stripped:
                continue
            key, _, val = stripped.partition(":")
            cur[key.strip()] = parse_val(val)
    if cur is not None:
        nodes.append(cur)
    return nodes


def dump_steps(nodes):
    """정규화 재직렬화 — 필드 고정 순서로. 왕복 비교의 기준형."""
    order = ["id", "kind", "parent", "outcome", "backtrack", "body"]
    out = []
    for n in nodes:
        out.append("- " + "id: " + str(n["id"]))
        for k in order[1:]:
            v = n.get(k)
            out.append("  %s: %s" % (k, "null" if v is None else v))
    return "\n".join(out)


def build_tree(nodes):
    by_id = {n["id"]: n for n in nodes}
    children = {n["id"]: [] for n in nodes}
    for n in nodes:
        p = n.get("parent")
        if p is not None:
            children[p].append(n["id"])
    return by_id, children


def validate_schema(nodes):
    """스키마 불변식 검사. 위반 리스트 반환(빈 리스트=통과)."""
    errs = []
    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        i = n["id"]
        if n["kind"] not in KINDS:
            errs.append(f"{i}: bad kind {n['kind']}")
        oc = n.get("outcome")
        if n["kind"] == "analyze":
            if oc not in OUTCOMES:
                errs.append(f"{i}: analyze needs outcome in {OUTCOMES}")
        else:
            if oc is not None:
                errs.append(f"{i}: non-analyze must have outcome=null")
        bt = n.get("backtrack")
        if oc == "backtrack":
            if bt is None:
                errs.append(f"{i}: outcome=backtrack needs backtrack target")
            elif by_id.get(bt, {}).get("kind") != "define":
                errs.append(f"{i}: backtrack must point to a define node")
        else:
            if bt is not None:
                errs.append(f"{i}: backtrack must be null unless outcome=backtrack")
        p = n.get("parent")
        if p is not None and p not in by_id:
            errs.append(f"{i}: parent {p} not found")
    roots = [n["id"] for n in nodes if n.get("parent") is None]
    if len(roots) != 1:
        errs.append(f"expected exactly 1 root define, got {roots}")
    elif by_id[roots[0]]["kind"] != "define":
        errs.append(f"root {roots[0]} must be a define")
    return errs


def derive_action(n, by_id):
    """M3: 트리 스키마만으로 이 노드에서의 '다음 허용 행동'을 파생."""
    k = n["kind"]
    if k in NEXT_KIND:
        return f"step → {NEXT_KIND[k]}"
    # analyze
    oc = n["outcome"]
    if oc == "success":
        return "close (산 잎 — 사이클 닫기 가능)"
    if oc == "backtrack":
        tgt = n["backtrack"]
        return f"backtrack → new sibling branch under {tgt} (죽은 잎)"
    if oc == "fail":
        return "backtrack → nearest ancestor define (자동 해소)"
    return "??? (미결정 — 스키마 밖 관습 필요, K3 발동)"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "case-c012-c014/steps.yaml"
    base = os.path.dirname(os.path.abspath(path))
    nodes = load_steps(path)

    print("=" * 64)
    print(f"로드: {len(nodes)} 노드 from {path}")
    print("=" * 64)

    # 스키마 검증
    errs = validate_schema(nodes)
    print("\n[스키마 불변식]", "PASS" if not errs else "FAIL")
    for e in errs:
        print("  ✗", e)

    # 본문 파일 존재
    missing = [n["id"] for n in nodes if not os.path.exists(os.path.join(base, n["body"]))]
    print("[본문 .md 존재]", "PASS" if not missing else f"FAIL missing={missing}")

    # 트리 위상 출력
    by_id, children = build_tree(nodes)
    root = [n["id"] for n in nodes if n.get("parent") is None][0]
    print("\n[트리 위상]")

    def show(nid, depth):
        n = by_id[nid]
        tag = n["kind"]
        oc = n.get("outcome")
        if oc:
            tag += f"/{oc}"
            if oc == "backtrack":
                tag += f"→{n['backtrack']}"
        print("  " + "  " * depth + f"{nid} [{tag}]")
        for c in children[nid]:
            show(c, depth + 1)

    show(root, 0)

    # M1: 왜곡 0 — 3요소 보존 확인
    dead = [n["id"] for n in nodes if n.get("outcome") == "backtrack"]
    live = [n["id"] for n in nodes if n.get("outcome") == "success"]
    bts = [(n["id"], n["backtrack"]) for n in nodes if n.get("outcome") == "backtrack"]
    m1 = bool(dead) and bool(live) and all(t for _, t in bts)
    print("\n[M1 왜곡 0]", "PASS" if m1 else "FAIL")
    print(f"    백트래킹(포인터)={bts}")
    print(f"    죽은 잎={dead}  산 잎={live}")

    # M2: 왕복 무손실
    ser1 = dump_steps(nodes)
    nodes2 = load_steps_from_str(ser1)
    ser2 = dump_steps(nodes2)
    m2 = (ser1 == ser2) and (len(nodes2) == len(nodes))
    print("\n[M2 왕복 무손실]", "PASS" if m2 else "FAIL")
    print(f"    노드수 {len(nodes)}→{len(nodes2)}, 재직렬화 정규형 일치={ser1 == ser2}")

    # M3: 명령 파생
    print("\n[M3 명령 파생 — 트리만으로 각 노드의 다음 행동]")
    m3 = True
    for n in nodes:
        act = derive_action(n, by_id)
        if act.startswith("???"):
            m3 = False
        print(f"    {n['id']} [{n['kind']}] → {act}")
    print("[M3]", "PASS" if m3 else "FAIL")

    ok = (not errs) and (not missing) and m1 and m2 and m3
    print("\n" + "=" * 64)
    print("판정:", "ALL PASS ✅" if ok else "FAIL ✗")
    print("=" * 64)
    return 0 if ok else 1


def load_steps_from_str(s):
    lines = s.split("\n")
    nodes = []
    cur = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            if cur is not None:
                nodes.append(cur)
            cur = {}
            stripped = stripped[2:]
        if ":" not in stripped:
            continue
        key, _, val = stripped.partition(":")
        cur[key.strip()] = parse_val(val)
    if cur is not None:
        nodes.append(cur)
    return nodes


if __name__ == "__main__":
    sys.exit(main())
