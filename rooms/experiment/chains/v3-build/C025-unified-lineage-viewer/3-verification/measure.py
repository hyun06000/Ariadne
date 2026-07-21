#!/usr/bin/env python3
"""measure (C025) — 통합 계보 뷰어 4측정 헤드리스 실측.

M1 상위 진실원 일치 · M2 v3 구조 보존(backtrack) · M3 자기완결 · M4 드릴다운(CDP).

M1·M3은 살아있는 원장(마이그레이션 notes)에서. M2는 v3 네이티브 사이클이 원장에 없어
(원장 전량이 gil v2로 돌아 마이그레이션됨 — 정직한 발견) 샌드박스에 gilv3로 backtrack
사이클을 만들어 재구성→렌더가 구조를 보존함을 증명. M4는 실 Chrome CDP(있으면).
"""
import os, sys, re, subprocess, tempfile, json
from html.parser import HTMLParser
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


# ---- SVG 노드/엣지/클래스 카운터 ----
class TagCounter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.class_counts = {}
        self.tag_counts = {}
    def handle_starttag(self, tag, attrs):
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1
        d = dict(attrs)
        cls = d.get("class", "")
        for c in cls.split():
            self.class_counts[c] = self.class_counts.get(c, 0) + 1


def count(html_text):
    p = TagCounter(); p.feed(html_text); return p


def m1_truth_source(repo, out_html):
    """M1: 렌더 DAG 노드/엣지 == rebuild_cycle_dag 진실원."""
    import notes_reconstruct as NR
    data = NR.all_cycles_with_trees(repo)
    truth_nodes = len(data["dag"])
    truth_edges = sum(len(p) for p in data["dag"].values())
    p = count(open(out_html, encoding="utf-8").read())
    dom_nodes = p.class_counts.get("dag-node", 0)
    # dag-edge 클래스는 그린 엣지 + dangling stub 둘 다 씀 → 합이 진실 엣지 수와 같아야 한다
    # (dangling도 dag-edge 클래스, .dangling 추가). 노드 잇는 엣지 + 섬 부모 엣지 = 전체.
    dom_edges = p.class_counts.get("dag-edge", 0)
    dom_dangling = p.class_counts.get("dangling", 0)
    ok = (dom_nodes == truth_nodes and dom_edges == truth_edges)
    print("M1 상위 진실원: 진실 %d노드/%d엣지 vs DOM %d노드/%d엣지"
          "(그린 %d + 섬부모 %d) → %s"
          % (truth_nodes, truth_edges, dom_nodes, dom_edges,
             dom_edges - dom_dangling, dom_dangling, "PASS" if ok else "FAIL"))
    return ok


def m2_v3_structure():
    """M2: v3 네이티브 backtrack 사이클의 재구성→렌더가 구조(backtrack/산잎/죽은잎)를 보존.

    원장엔 네이티브 v3 사이클이 없다(전량 v2 마이그레이션 — 정직한 발견). 그래서 샌드박스에
    gilv3로 backtrack 사이클을 만들고, notes_reconstruct의 트레일러 폴백으로 재구성해
    steptree로 렌더 → edge-backtrack/leaf-live/leaf-dead 클래스 존재를 확인한다.
    """
    import notes_reconstruct as NR
    import web_render as WR
    gilv3 = os.path.join(HERE, "gilv3.py")
    sbx = tempfile.mkdtemp(prefix="c025-m2-")
    subprocess.run(["git", "-C", sbx, "init", "-q"], check=True)
    subprocess.run(["git", "-C", sbx, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", sbx, "config", "user.name", "t"], check=True)
    cyc = os.path.join(sbx, "cyc"); os.makedirs(cyc)
    def g3(*a):
        subprocess.run([sys.executable, gilv3] + list(a),
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=sbx)
    g3("open", cyc, "--title", "backtrack demo", "--git")
    g3("step", cyc, "--kind", "hypothesis", "--git")
    g3("step", cyc, "--kind", "verify", "--git")
    g3("step", cyc, "--kind", "analyze", "--outcome", "backtrack", "--to", "s1", "--git")
    g3("step", cyc, "--kind", "hypothesis", "--to", "s1", "--git")
    g3("step", cyc, "--kind", "verify", "--git")
    g3("step", cyc, "--kind", "analyze", "--outcome", "success", "--git")

    # 네이티브 사이클: Step-Id trailer로 커밋 발견(cycle_step_commits는 v2 subject 전용).
    fmt = "%H\x1f%(trailers:key=Step-Id,valueonly)"
    r = subprocess.run(["git", "-C", sbx, "log", "--all", "--reverse", "--format=" + fmt],
                       stdout=subprocess.PIPE).stdout.decode()
    ordered = []
    for line in r.splitlines():
        if "\x1f" not in line: continue
        h, sid = line.split("\x1f", 1)
        if sid.strip():
            ordered.append((sid.strip(), h))
    # sid 순서(s1..s7)로 정렬
    ordered.sort(key=lambda t: int(t[0][1:]))
    nodes = []
    for sid, h in ordered:
        note = NR._fingerprint_lines(sbx, h)
        f, _ = NR._parse_fingerprint(note)
        parent = f.get("Parent");  parent = None if parent in ("null","",None) else parent
        nodes.append({"id": f.get("Step-Id"), "kind": f.get("Kind"), "parent": parent,
                      "outcome": f.get("Outcome"), "backtrack": f.get("Backtrack-To"),
                      "body": None})
    ids = {n["id"] for n in nodes}
    for n in nodes:
        if n["parent"] and n["parent"] not in ids:
            n["parent"] = None
    svg = WR.step_tree_svg(nodes, "sandbox", "backtrack-demo")
    p = count(svg)
    has_bt = p.class_counts.get("edge-backtrack", 0) >= 1
    has_live = p.class_counts.get("leaf-live", 0) >= 1
    has_dead = p.class_counts.get("leaf-dead", 0) >= 1
    n_bt = sum(1 for n in nodes if n.get("backtrack"))
    ok = has_bt and has_live and has_dead and n_bt >= 1
    print("M2 v3 구조 보존: 재구성 %d노드 · backtrack지문 %d · edge-backtrack %d · "
          "leaf-live %d · leaf-dead %d → %s"
          % (len(nodes), n_bt, p.class_counts.get("edge-backtrack",0),
             p.class_counts.get("leaf-live",0), p.class_counts.get("leaf-dead",0),
             "PASS" if ok else "FAIL"))
    return ok


def m3_self_contained(out_html):
    """M3: 외부 fetch 벡터 0 (xmlns 네임스페이스는 fetch 아님 — 제외)."""
    txt = open(out_html, encoding="utf-8").read()
    fetch_vectors = re.findall(r'src=|<link[ >]|<script src=|url\(http', txt)
    http_all = re.findall(r'https?://[^"\'> ]*', txt)
    non_xmlns = [u for u in http_all if u != "http://www.w3.org/2000/svg"]
    ok = (len(fetch_vectors) == 0 and len(non_xmlns) == 0)
    print("M3 자기완결: fetch벡터 %d · 비-xmlns http %d (xmlns %d개는 SVG 네임스페이스) → %s"
          % (len(fetch_vectors), len(non_xmlns),
             len(http_all) - len(non_xmlns), "PASS" if ok else "FAIL"))
    return ok


def m4_drilldown(out_html):
    """M4: 실 Chrome raw-WebSocket CDP로 DAG 노드 클릭 → 스텝 트리 패널 hidden 해제."""
    try:
        import cdp_probe
    except Exception as e:
        print("M4 드릴다운: SKIP (cdp_probe 없음: %s)" % e)
        return None
    return cdp_probe.run(out_html)


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    repo = os.path.abspath(repo)
    out = tempfile.mktemp(suffix="-gilv3-web.html")
    import gilv3
    class A: pass
    a = A(); a.dir = repo; a.out = out
    gilv3.cmd_web(a)
    print("--- 측정 ---")
    r1 = m1_truth_source(repo, out)
    r2 = m2_v3_structure()
    r3 = m3_self_contained(out)
    r4 = m4_drilldown(out)
    print("--- 요약 ---")
    results = {"M1": r1, "M2": r2, "M3": r3, "M4": r4}
    for k, v in results.items():
        print("  %s: %s" % (k, "PASS" if v is True else ("FAIL" if v is False else "SKIP")))
    hard = [v for v in results.values() if v is not None]
    print("판정:", "ALL PASS" if all(hard) else "일부 FAIL")


if __name__ == "__main__":
    main()
