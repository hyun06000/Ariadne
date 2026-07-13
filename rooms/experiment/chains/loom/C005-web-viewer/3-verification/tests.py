#!/usr/bin/env python3
"""loom/C005 검증 드라이버 — fixtures/expected-structure.md 의 판정을 실행한다 (T1~T6)."""
import json
import os
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

BASE = os.path.dirname(os.path.abspath(__file__))
ARI = os.path.join(BASE, "ari", "ari.py")
FX = os.path.join(BASE, "fixtures")
RESULTS = []


def ari(*cli, cwd=BASE):
    return subprocess.run([sys.executable, ARI, *cli], cwd=cwd, capture_output=True, text=True)


def check(tid, desc, cond, detail=""):
    RESULTS.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {tid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


def extract_json(html_text):
    m = re.search(r'<script type="application/json" id="ari-data">(.*?)</script>', html_text, re.S)
    return json.loads(m.group(1)) if m else None


def edges_of(data, chain):
    c = data["chains"][chain]["cycles"]
    return {(p, cid) for cid, m in c.items() for p in m["parents"]}


def lineage_of(data):
    out = set()
    for name, chain in data["chains"].items():
        for cid, m in chain["cycles"].items():
            for ref in m["lineage"]:
                out.add((ref, f"{name}/{cid}"))
    return out


def gen(fixture, name):
    out = os.path.join(tempfile.mkdtemp(prefix="ari-c005-"), name)
    r = ari("web", os.path.join(FX, fixture), "-o", out)
    return r, out


# T1: maze — 구조 동일성 (분기·병합)
r, out = gen("maze", "maze.html")
page = open(out, encoding="utf-8").read() if r.returncode == 0 else ""
data = extract_json(page)
EXP_NODES = {"C001-enter", "C002-crossroad", "C003-left-path", "C004-right-path", "C005-reunion", "C006-exit"}
EXP_EDGES = {("C001-enter", "C002-crossroad"), ("C002-crossroad", "C003-left-path"),
             ("C002-crossroad", "C004-right-path"), ("C003-left-path", "C005-reunion"),
             ("C004-right-path", "C005-reunion"), ("C005-reunion", "C006-exit")}
check("T1", "maze: 내장 JSON 구조가 기대와 일치", r.returncode == 0 and data
      and set(data["chains"]["test-maze"]["cycles"]) == EXP_NODES
      and edges_of(data, "test-maze") == EXP_EDGES
      and lineage_of(data) == set()
      and {c for c, m in data["chains"]["test-maze"]["cycles"].items() if m["status"] == "open"} == {"C006-exit"},
      r.stderr.strip())

# T2: lineage — 체인 간 간선의 구조
r2, out2 = gen("lineage", "lineage.html")
page2 = open(out2, encoding="utf-8").read() if r2.returncode == 0 else ""
data2 = extract_json(page2)
check("T2", "lineage: 체인 간 간선 구조 일치", r2.returncode == 0 and data2
      and set(data2["chains"]) == {"alpha", "beta"}
      and lineage_of(data2) == {("alpha/C001-seed", "beta/C001-sprout")}
      and edges_of(data2, "alpha") == set() and edges_of(data2, "beta") == set(), r2.stderr.strip())

# T3: 시각 표현 — 노드 수, 상태별 모양, 점선 lineage path, 테이블 행
maze_nodes = len(re.findall(r'data-cycle="', page))
open_hollow = 'stroke="var(--node)"' in page  # 열린 노드 = 빈 원
lineage_dashed = re.search(r'<path class="lineage"[^>]*stroke-dasharray', page2)
maze_rows = len(re.findall(r'<td class="id">', page))
check("T3", "시각 표현: 노드·모양·점선 lineage·테이블", maze_nodes == 6 and open_hollow
      and lineage_dashed is not None and maze_rows == 6,
      f"nodes={maze_nodes}, rows={maze_rows}, dashed={bool(lineage_dashed)}")

# T4: 자기완결 — 외부 URL 참조 0건
external = re.findall(r'(?:src=|href=|url\(|@import)[^>\n]*https?://', page + page2)
check("T4", "자기완결: 외부 리소스 참조 0건", external == [], str(external))

# T5: 깨진 체인 → 거부 + 파일 미생성
out5 = os.path.join(tempfile.mkdtemp(prefix="ari-c005-"), "broken.html")
r5 = ari("web", os.path.join(FX, "broken"), "-o", out5)
check("T5", "깨진 체인 거부 + 부분 산출물 없음", r5.returncode != 0 and not os.path.exists(out5),
      f"rc={r5.returncode}, exists={os.path.exists(out5)}")


# T6: HTML 파싱 가능 (표준 파서 무오류) + svg 존재
class Strict(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


try:
    p = Strict(); p.feed(page); p.feed(page2)
    parsed_ok = "svg" in p.tags and "table" in p.tags
except Exception as e:  # noqa: BLE001
    parsed_ok = False
check("T6", "HTML 파싱 가능 + svg·table 존재", parsed_ok)

total, passed = len(RESULTS), sum(RESULTS)
print(f"\n결과: {passed}/{total} 통과")
sys.exit(0 if passed == total else 1)
