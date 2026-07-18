#!/usr/bin/env python3
"""loom/C059 검증 — gil show(지식그래프 노드 조회)의 계약면 판정.

합성 픽스처(결정론적, 저장소 진화 무관 — C047·C051 방식)로 작은 그래프를 만들고
참조 gil의 `show --json`을 실행해 엣지 집합을 판정한다. 렌더가 아니라 계약면(JSON)만 본다.

픽스처 그래프:
    체인 alpha:  A ← B ← C   (C의 parent=B, B의 parent=A; parent 체인)
    체인 beta:   X            (X의 lineage = alpha/A;  cross-chain lineage)

기대 엣지:
    show alpha/A : forward 없음(루트),  backlinks.parents=[alpha/B], backlinks.lineage=[beta/X]
    show alpha/B : forward.parents=[alpha/A], backlinks.parents=[alpha/C]
    show beta/X  : forward.lineage=[alpha/A],  backlinks 없음
    show alpha/C999-ghost : 부재 → exit≠0, JSON node 미생성(지어냄 없음)

실행:  python3 show_probe.py --gil <참조 gil.py 절대경로>
       (--gil 상대경로 함정 주의 — C028·C043·C045. 절대경로로.)
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

CYCLE_YAML = """id: {cid}
chain: {chain}
title: {title}
author: tester
status: closed
verdict: supported
opened: 2026-07-19
closed: 2026-07-19
parent: {parent}
lineage: {lineage}
"""


def write_cycle(root, chain, cid, parent=None, lineage=None, title="t"):
    d = os.path.join(root, chain, cid)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "cycle.yaml"), "w", encoding="utf-8") as f:
        f.write(CYCLE_YAML.format(
            cid=cid, chain=chain, title=title,
            parent=(parent if parent else "null"),
            lineage=(lineage if lineage else "null"),
        ))
    with open(os.path.join(d, "5-report.md"), "w", encoding="utf-8") as f:
        f.write(f"# {cid}\n")


def make_fixture(root):
    # 체인 alpha: A ← B ← C
    write_cycle(root, "alpha", "C001-a")
    write_cycle(root, "alpha", "C002-b", parent="C001-a")
    write_cycle(root, "alpha", "C003-c", parent="C002-b")
    # 체인 beta: X lineage→ alpha/A
    write_cycle(root, "beta", "C001-x", lineage="alpha/C001-a")


def run_show(gil, root, ref, want_json=True):
    cmd = [sys.executable, gil, "show", ref, "--root", root]
    if want_json:
        cmd.append("--json")
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p


def refs(edge_list):
    """forward 엣지 리스트 [{ref,exists}] → ref 집합."""
    return sorted(e["ref"] for e in edge_list)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gil", required=True, help="참조 gil.py 절대경로")
    args = ap.parse_args()
    gil = os.path.abspath(args.gil)
    assert os.path.isfile(gil), f"gil 없음: {gil}"

    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    with tempfile.TemporaryDirectory() as root:
        make_fixture(root)

        # SHOW-NODE
        p = run_show(gil, root, "alpha/C001-a")
        d = json.loads(p.stdout) if p.returncode == 0 else {}
        check("SHOW-NODE",
              p.returncode == 0 and d.get("node", {}).get("id") == "C001-a"
              and d.get("node", {}).get("chain") == "alpha",
              f"rc={p.returncode} id={d.get('node',{}).get('id')}")

        # SHOW-FORWARD (beta/X의 lineage → alpha/A, exists=True)
        p = run_show(gil, root, "beta/C001-x")
        d = json.loads(p.stdout)
        fl = d["forward"]["lineage"]
        check("SHOW-FORWARD",
              fl == [{"ref": "alpha/C001-a", "exists": True}],
              f"forward.lineage={fl}")

        # SHOW-BACKLINKS-PARENT (alpha/B ← alpha/C)
        p = run_show(gil, root, "alpha/C002-b")
        d = json.loads(p.stdout)
        check("SHOW-BACKLINKS-PARENT",
              d["backlinks"]["parents"] == ["alpha/C003-c"],
              f"backlinks.parents={d['backlinks']['parents']}")

        # SHOW-BACKLINKS-LINEAGE (alpha/A ← beta/X, cross-chain)
        p = run_show(gil, root, "alpha/C001-a")
        d = json.loads(p.stdout)
        check("SHOW-BACKLINKS-LINEAGE",
              d["backlinks"]["lineage"] == ["beta/C001-x"],
              f"backlinks.lineage={d['backlinks']['lineage']}")

        # SHOW-EDGES-MATCH-GRAPH: show의 forward.parents == build_graph(=web JSON) 엣지
        webhtml = os.path.join(root, "w.html")
        subprocess.run([sys.executable, gil, "web", root, "-o", webhtml, "--chain", "alpha"],
                       capture_output=True, text=True)
        import re
        m = re.search(r'id="gil-data"[^>]*>(.*?)</script>', open(webhtml).read(), re.S)
        webdata = json.loads(m.group(1))
        # web JSON 구조: {version, bake, chains: {<chain>: {cycles, order, children, ...}}}
        web_parents = set(webdata["chains"]["alpha"]["cycles"]["C003-c"]["parents"])  # ['C002-b']
        p = run_show(gil, root, "alpha/C003-c")
        d = json.loads(p.stdout)
        show_parents = set(e["ref"].split("/", 1)[1] for e in d["forward"]["parents"])
        check("SHOW-EDGES-MATCH-GRAPH", web_parents == show_parents,
              f"web={web_parents} show={show_parents}")

        # SHOW-MISSING: 부재 노드 → exit≠0, stdout에 JSON node 없음(지어냄 없음)
        p = run_show(gil, root, "alpha/C999-ghost")
        no_fabrication = True
        try:
            json.loads(p.stdout)  # stdout이 JSON이면 node를 지어낸 것 → 실패
            no_fabrication = False
        except Exception:
            no_fabrication = True
        check("SHOW-MISSING", p.returncode != 0 and no_fabrication,
              f"rc={p.returncode} stdout_empty={not p.stdout.strip()}")

    print("=== gil show 계약면 판정 ===")
    passed = 0
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}")
        passed += ok
    print(f"--- {passed}/{len(results)} ---")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
