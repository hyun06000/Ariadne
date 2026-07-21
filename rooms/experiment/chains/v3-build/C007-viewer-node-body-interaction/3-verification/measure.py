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


class BodyCollector(HTMLParser):
    """<article class="stepbody" id="body-<id>"> 안 <pre class="sb-body"> 텍스트 수집.
    C006 M5: 임베드된 본문이 진실원 steps/<id>.md와 일치하는지 대조용."""
    def __init__(self):
        super().__init__()
        self.cur_id = None       # 현재 stepbody의 노드 id
        self.in_pre = False
        self.texts = {}          # id -> 본문 텍스트

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article" and "stepbody" in a.get("class", "").split():
            self.cur_id = a.get("data-id")
        if tag == "pre" and "sb-body" in a.get("class", "").split():
            self.in_pre = True
            self.texts.setdefault(self.cur_id, "")

    def handle_endtag(self, tag):
        if tag == "pre":
            self.in_pre = False
        if tag == "article":
            self.cur_id = None

    def handle_data(self, data):
        if self.in_pre and self.cur_id is not None:
            self.texts[self.cur_id] += data

    def handle_entityref(self, name):
        if self.in_pre and self.cur_id is not None:
            import html as _h
            self.texts[self.cur_id] += _h.unescape("&%s;" % name)


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

    # --- M5 (C006): 본문 인라인 임베드 · 진실원 일치 ---
    # (a) 노드 수 == 클릭 가능 노드 수 == 본문 패널 수 == 10
    # (b) 각 노드는 data-body="body-<id>" 를 갖고, 그 id의 패널이 존재
    # (c) 임베드된 본문 텍스트가 진실원 steps/<id>.md와 일치 (정규화 후)
    import re as _re
    node_gs = [a for t, a in els if t == "g" and "node" in classes(a) and "data-id" in a]
    clickable_gs = [a for a in node_gs if "clickable" in classes(a)
                    and a.get("role") == "button" and a.get("data-body")]
    panels = [a for t, a in els if t == "article" and "stepbody" in classes(a)]
    panel_ids = {a.get("id") for a in panels}
    # 노드↔패널 배선: 모든 노드의 data-body가 실재 패널을 가리킴
    wire_ok = all(a.get("data-body") in panel_ids for a in clickable_gs)

    bc = BodyCollector(); bc.feed(doc)
    steps_dir = os.path.join(os.path.dirname(IN_YAML), "steps")

    def norm(s):
        return _re.sub(r"\s+", " ", s or "").strip()

    truth_bodies = {}
    for nid in truth:
        p = os.path.join(steps_dir, "%s.md" % nid)
        if os.path.exists(p):
            truth_bodies[nid] = open(p, encoding="utf-8").read()
    embed_match = {nid: (norm(bc.texts.get(nid, "")) == norm(txt))
                   for nid, txt in truth_bodies.items()}
    n_match = sum(1 for v in embed_match.values() if v)
    mismatched = sorted(nid for nid, v in embed_match.items() if not v)

    m5 = (len(node_gs) == len(clickable_gs) == len(panels) == 10
          and wire_ok and n_match == len(truth_bodies) == 10)
    results.append(("M5 본문 임베드·진실원 일치 (K2)", m5,
        f"노드={len(node_gs)} 클릭가능={len(clickable_gs)} 패널={len(panels)} (기대 10); "
        f"노드↔패널 배선={wire_ok}; 본문 진실원 일치 {n_match}/{len(truth_bodies)}"
        + (f" 불일치={mismatched}" if mismatched else "")))

    # --- M4b (C006): 새 상호작용 자기완결 재확인 ---
    # 인라인 <script>는 허용(src 없음), 외부 로드/네트워크 토큰만 금지
    inline_scripts = [a for t, a in els if t == "script" and not a.get("src")]
    js_bad = []
    for tok in ("fetch(", "xmlhttprequest", "new websocket", "import(", "eval("):
        if tok in lowered:
            js_bad.append(tok)
    m4b = (len(inline_scripts) >= 1 and not js_bad)
    results.append(("M4b 상호작용 자기완결 (K3)", m4b,
        f"인라인 script={len(inline_scripts)} (외부 src 0); 네트워크/동적로드 토큰="
        f"{'없음' if not js_bad else js_bad}"))

    print("=== v3 스텝 트리 뷰어 (C006 상호작용) — 헤드리스 실측 ===\n")
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
