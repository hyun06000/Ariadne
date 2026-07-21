#!/usr/bin/env python3
"""헤드리스 실측 — out.html을 파싱해 M1~M4(=K1~K4)를 판정.

SVG는 정적 마크업이라 브라우저 없이 stdlib html.parser로 요소/클래스/좌표/데이터
속성을 뽑아 측정한다. 판정기가 SVG 좌표를 안 보므로(SPEC §3.1), 뷰어 정확성은 이
실측이 스스로 증명한다 — v2 뷰어 규율(두 구현 대조·실측)의 정적판.
"""
import os
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
IN_YAML = os.path.normpath(os.path.join(
    HERE, "..", "..",
    "C002-design-v3-data-model", "3-verification",
    "case-c012-c014", "steps.yaml"))


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []  # (tag, attrs_dict)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def parse_yaml_parents(path):
    """steps.yaml에서 (id -> parent) 진실원 추출 (독립 파서, steptree.py와 별개)."""
    parents = {}
    cur = None
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            cur = {}
            line = line[2:]
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip(); v = v.strip()
            cur[k] = None if v in ("null", "") else v
            if k == "backtrack":  # last field of a block in this data
                parents[cur["id"]] = (cur.get("parent"), cur.get("outcome"),
                                      cur.get("backtrack"), cur.get("kind"))
    return parents


def classes(attrs):
    return set(attrs.get("class", "").split())


def main():
    out = os.path.join(HERE, "out.html")
    if not os.path.exists(out):
        print("FAIL: out.html 없음 — render.py 먼저 실행"); sys.exit(1)
    doc = open(out, encoding="utf-8").read()
    c = Collector(); c.feed(doc)
    els = c.elements

    truth = parse_yaml_parents(IN_YAML)  # id -> (parent, outcome, backtrack, kind)

    results = []

    # --- M1: 구조 무왜곡 ---
    parent_edges = [a for t, a in els if "edge-parent" in classes(a) and "data-from" in a]
    rendered_pe = {(a["data-from"], a["data-to"]) for a in parent_edges}
    truth_pe = {(v[0], nid) for nid, v in truth.items() if v[0] is not None}
    s1_children = sum(1 for nid, v in truth.items() if v[0] == "s1")
    rendered_s1_children = sum(1 for f, t in rendered_pe if f == "s1")
    m1 = (rendered_pe == truth_pe) and (rendered_s1_children == s1_children == 3)
    results.append(("M1 구조 무왜곡 (K1)", m1,
        f"parent엣지 {len(rendered_pe)}=={len(truth_pe)} 진실원 일치={rendered_pe==truth_pe}; "
        f"s1 형제가지 렌더={rendered_s1_children} 진실={s1_children} (기대 3)"))

    # --- M2: backtrack 가시·구별 ---
    # 그래프 엣지만 — data-from을 가진 것 (범례 스와치 line은 제외, M1의 parent 필터와 동형)
    bt_edges = [a for t, a in els if "edge-backtrack" in classes(a) and "data-from" in a]
    # 방향: 잎→조상 (도착 y < 출발 y, 위로)
    dir_ok = all(float(a["data-y-to"]) < float(a["data-y-from"]) for a in bt_edges if "data-y-to" in a)
    bt_pairs = {(a["data-from"], a["data-to"]) for a in bt_edges}
    truth_bt = {(nid, v[2]) for nid, v in truth.items() if v[1] == "backtrack"}
    has_marker = all(a.get("marker-end") for a in bt_edges)
    # parent와 다른 태그(path vs line)로 구별 — 그래프 backtrack 엣지는 모두 path
    bt_is_path = all(t == "path" for t, a in els
                     if "edge-backtrack" in classes(a) and "data-from" in a)
    pe_is_line = all(t == "line" for t, a in els
                     if "edge-parent" in classes(a) and "data-from" in a)
    m2 = (len(bt_edges) == 2 and bt_pairs == truth_bt and dir_ok
          and has_marker and bt_is_path and pe_is_line)
    results.append(("M2 backtrack 가시·구별 (K2)", m2,
        f"backtrack엣지={len(bt_edges)} (기대 2) {sorted(bt_pairs)}=={sorted(truth_bt)}; "
        f"방향 잎→조상(위로)={dir_ok}; 마커={has_marker}; path/line구별={bt_is_path and pe_is_line}"))

    # --- M3: 잎 운명 구별 ---
    dead = [a for t, a in els if t == "g" and "leaf-dead" in classes(a)]
    live = [a for t, a in els if t == "g" and "leaf-live" in classes(a)]
    dead_ids = {a["data-id"] for a in dead}
    live_ids = {a["data-id"] for a in live}
    truth_dead = {nid for nid, v in truth.items() if v[1] == "backtrack"}
    truth_live = {nid for nid, v in truth.items() if v[1] == "success"}
    m3 = (dead_ids == truth_dead and live_ids == truth_live
          and len(dead) == 2 and len(live) == 1 and not (dead_ids & live_ids))
    results.append(("M3 잎 운명 구별 (K3)", m3,
        f"죽은잎={sorted(dead_ids)} (기대 {sorted(truth_dead)}); "
        f"산잎={sorted(live_ids)} (기대 {sorted(truth_live)}); 클래스 분리={not (dead_ids & live_ids)}"))

    # --- M4: 자기완결 ---
    bad = []
    for t, a in els:
        if t == "link":
            bad.append("<link>")
        if t == "script" and a.get("src"):
            bad.append("script src")
        if t == "img" and a.get("src", "").startswith(("http", "//")):
            bad.append("remote img")
    lowered = doc.lower()
    for token in ("http://", "https://", "fetch(", "xmlhttprequest", "cdn"):
        # http(s) allowed only inside svg xmlns namespace URI
        if token in ("http://", "https://"):
            # count occurrences not part of the svg namespace declaration
            cnt = lowered.count(token)
            ns = lowered.count("http://www.w3.org/2000/svg")
            if token == "http://" and cnt - ns > 0:
                bad.append(f"{token}x{cnt-ns}")
            if token == "https://" and cnt > 0:
                bad.append(f"{token}x{cnt}")
        elif token in lowered:
            bad.append(token)
    m4 = not bad
    results.append(("M4 자기완결 (K4)", m4,
        f"외부 리소스 참조={'없음' if not bad else bad}"))

    print("=== v3 스텝 트리 뷰어 — 헤드리스 실측 ===\n")
    allpass = True
    for name, ok, detail in results:
        allpass = allpass and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        print(f"       {detail}\n")
    print("=" * 42)
    print("ALL PASS ✓" if allpass else "SOME FAIL ✗")
    sys.exit(0 if allpass else 1)


if __name__ == "__main__":
    main()
