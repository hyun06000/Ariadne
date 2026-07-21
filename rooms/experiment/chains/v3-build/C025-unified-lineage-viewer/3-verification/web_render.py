#!/usr/bin/env python3
"""web_render (C025) — 통합 계보 뷰어 HTML 생성기.

상위 = 사이클 간 계보 DAG(한 화면). 노드 클릭 → 그 사이클의 스텝 트리(드릴다운).
순수 git notes에서 재구성한 두 층(notes_reconstruct)을 자기완결 단일 HTML로.

⭐ 재사용(재구현 금지):
  - 하위 스텝 트리 SVG = C004 steptree.render_html에서 <svg…</svg> 구간 추출.
    steptree는 닫힌 사이클이라 안 고친다 — 그 검증된 좌표 로직을 그대로 쓴다.
  - 상위 DAG는 이 사이클이 새로 그린다(사이클=노드, v2 뷰어와 위상이 다름).

자기완결: CSS·JS 인라인, 외부 리소스 0(v2 web 계약). 드릴다운은 C006 교훈 —
각 패널 독립 + hidden 하나만 토글(fetch 0, 간섭 경로 없음).
"""
import html, re
import steptree  # C004, 재사용


# ---- 하위 스텝 트리 SVG 추출 (steptree 재사용) ----
_SVG_RE = re.compile(r"(<svg class=\"steptree\".*?</svg>)", re.DOTALL)


def step_tree_svg(nodes, chain, cycle):
    """C004 steptree로 스텝 트리 완전 문서를 만들고 <svg> 구간만 추출.
    노드 0(도출실패 섬)이면 정직히 빈 표시."""
    if not nodes:
        return '<p class="empty-tree">스텝 트리 없음 — notes 지문 부재(도출실패 섬 또는 빈 사이클).</p>'
    doc = steptree.render_html(nodes, chain=chain, cycle=cycle)
    m = _SVG_RE.search(doc)
    return m.group(1) if m else '<p class="empty-tree">스텝 트리 렌더 실패.</p>'


# ---- 상위 DAG 레이아웃 (사이클=노드) ----
DAG_COL_W = 210
DAG_ROW_H = 78
DAG_NODE_W = 150
DAG_NODE_H = 40
DAG_PAD_X = 40
DAG_PAD_Y = 40


def _dag_depths(dag):
    """각 사이클 노드의 depth = 루트로부터 Cycle-Parent 체인 최장 길이.
    부모는 bare short_id(예: 'C011')이라 같은 chain 내에서 해소한다(splice가 그렇게 각인)."""
    # 부모 키 해소: 'C011' → 'chain/C011' (같은 체인 가정, splice_topology와 동일 규약)
    depth = {}
    def resolve(child_key, pshort):
        chain = child_key.split("/", 1)[0]
        cand = "%s/%s" % (chain, pshort)
        return cand if cand in dag else None

    def d(key, seen):
        if key in depth:
            return depth[key]
        if key in seen:
            return 0  # 사이클 방지(원장엔 DAG라 없어야 하나 방어)
        seen = seen | {key}
        parents = dag.get(key, [])
        pk = [resolve(key, p) for p in parents]
        pk = [p for p in pk if p]
        depth[key] = 0 if not pk else 1 + max(d(p, seen) for p in pk)
        return depth[key]

    for k in dag:
        d(k, set())
    return depth, resolve


def _dag_columns(dag, depth):
    """같은 depth 노드에 가로 슬롯 부여(단순 순차). 안정 정렬로 재현성."""
    by_depth = {}
    for k in sorted(dag):
        by_depth.setdefault(depth[k], []).append(k)
    col = {}
    for dpt, keys in by_depth.items():
        for i, k in enumerate(keys):
            col[k] = i
    return col, by_depth


def dag_svg(dag, chain_of, cid_of):
    depth, resolve = _dag_depths(dag)
    col, by_depth = _dag_columns(dag, depth)
    max_col = max((len(v) for v in by_depth.values()), default=1)
    max_depth = max(depth.values(), default=0)
    width = DAG_PAD_X * 2 + max_col * DAG_COL_W + DAG_NODE_W
    height = DAG_PAD_Y * 2 + (max_depth + 1) * DAG_ROW_H + DAG_NODE_H

    def xy(k):
        cx = DAG_PAD_X + col[k] * DAG_COL_W + DAG_NODE_W / 2
        cy = DAG_PAD_Y + depth[k] * DAG_ROW_H + DAG_NODE_H / 2
        return cx, cy

    edges, dangling, nodes_svg = [], [], []
    for k in sorted(dag):
        cx, cy = xy(k)
        for p in dag.get(k, []):
            pk = resolve(k, p)
            if not pk:
                # ⭐ H4 정직: 부모 사이클이 DAG에 없다(도출실패 섬 — 그 사이클엔 step
                # 커밋이 없어 루트 지문이 없다). 엣지를 소리 없이 버리지 않고, 노드 위로
                # 뻗는 짧은 stub + 부모 id 라벨로 '계보는 있으나 대상이 섬'임을 비춘다.
                dangling.append(
                    '<g class="dag-dangling" data-to="%s" data-parent="%s">'
                    '<line class="dag-edge dangling" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" />'
                    '<text class="dangling-label" x="%.1f" y="%.1f" text-anchor="middle">'
                    '↑ %s (섬)</text></g>'
                    % (html.escape(k), html.escape(p),
                       cx, cy - DAG_NODE_H / 2, cx, cy - DAG_NODE_H / 2 - 16,
                       cx, cy - DAG_NODE_H / 2 - 20, html.escape(p)))
                continue
            px, py = xy(pk)
            edges.append(
                '<line class="dag-edge" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                'data-from="%s" data-to="%s" />'
                % (px, py + DAG_NODE_H / 2, cx, cy - DAG_NODE_H / 2, pk, k))

    for k in sorted(dag):
        cx, cy = xy(k)
        x, y = cx - DAG_NODE_W / 2, cy - DAG_NODE_H / 2
        chain = chain_of[k]
        label = "%s/%s" % (chain, cid_of[k])
        is_root = not [p for p in dag.get(k, []) if resolve(k, p)]
        is_merge = len([p for p in dag.get(k, []) if resolve(k, p)]) >= 2
        cls = ["dag-node", "chain-" + re.sub(r"[^a-z0-9]", "", chain.lower())]
        if is_root:
            cls.append("dag-root")
        if is_merge:
            cls.append("dag-merge")
        nodes_svg.append(
            '<g class="%s" data-key="%s" tabindex="0" role="button" '
            'aria-label="사이클 %s — 클릭하면 스텝 트리">'
            '<rect class="dag-box" x="%.1f" y="%.1f" rx="7" ry="7" width="%d" height="%d" />'
            '<text class="dag-label" x="%.1f" y="%.1f" text-anchor="middle">%s</text>'
            '</g>'
            % (" ".join(cls), html.escape(k), html.escape(label),
               x, y, DAG_NODE_W, DAG_NODE_H, cx, cy + 4, html.escape(label)))

    svg = ('<svg class="dag" viewBox="0 0 %d %d" width="%d" height="%d" '
           'xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="사이클 간 계보 DAG: %d노드">'
           '<g class="dag-edges">%s</g><g class="dag-dangling-edges">%s</g>'
           '<g class="dag-nodes">%s</g></svg>'
           % (width, height, width, height, len(dag),
              "".join(edges), "".join(dangling), "".join(nodes_svg)))
    return svg, len(edges), len(dangling)


# ---- 통합 문서 ----
def render(data, repo_label="."):
    dag = data["dag"]
    trees = data["trees"]
    chain_of = data["chain_of"]
    cid_of = data["cid_of"]

    n_nodes = len(dag)
    n_edges = sum(len([p for p in dag[k]]) for k in dag)
    n_empty = sum(1 for t in trees.values() if not t)
    n_backtrack = sum(1 for t in trees.values() if any(n.get("backtrack") for n in t))
    n_merge = sum(1 for k in dag if len(dag[k]) >= 2)

    dsvg, n_drawn_edges, n_dangling = dag_svg(dag, chain_of, cid_of)

    # 각 사이클의 스텝 트리 패널을 인라인 임베드 (hidden 토글 대상)
    panels = []
    for k in sorted(dag):
        chain, cid = chain_of[k], cid_of[k]
        svg = step_tree_svg(trees[k], chain, "%s/%s" % (chain, cid))
        panels.append(
            '<div class="steptree-panel" id="panel-%s" data-key="%s" hidden>'
            '<div class="panel-head"><b>%s</b> — 스텝 트리 (notes 지문 재구성) '
            '<button class="panel-close" data-key="%s" type="button">닫기 ✕</button></div>'
            '%s</div>'
            % (html.escape(k), html.escape(k), html.escape("%s/%s" % (chain, cid)),
               html.escape(k), svg))

    return DOC_TMPL % {
        "css": CSS, "js": JS,
        "n_nodes": n_nodes, "n_edges": n_edges, "n_merge": n_merge,
        "n_empty": n_empty, "n_backtrack": n_backtrack, "n_dangling": n_dangling,
        "repo": html.escape(repo_label),
        "dag_svg": dsvg,
        "panels": "".join(panels),
    }


DOC_TMPL = '''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>통합 계보 뷰어 — gilv3 web</title>
<style>
%(css)s
</style>
</head>
<body>
<header class="head">
  <h1>통합 계보 뷰어 <span class="sub">gilv3 web · 순수 git notes</span></h1>
  <div class="meta">
    <span>원장: <b>%(repo)s</b></span>
    <span>사이클: <b>%(n_nodes)d</b></span>
    <span>계보 엣지: <b>%(n_edges)d</b></span>
    <span>머지: <b>%(n_merge)d</b></span>
    <span>빈 트리(섬): <b>%(n_empty)d</b></span>
    <span>backtrack 보유: <b>%(n_backtrack)d</b></span>
    <span>섬 부모(dangling): <b>%(n_dangling)d</b></span>
  </div>
  <p class="hint">위 DAG는 사이클 간 계보(Cycle-Parent notes). 노드를 <b>클릭</b>하면 그 사이클의 스텝 트리가 아래 펼쳐진다(드릴다운).</p>
</header>
<div class="dag-canvas">
%(dag_svg)s
</div>
<div class="panels">
%(panels)s
</div>
<footer class="foot">통합 계보 뷰어 — 사이클 간 DAG → 사이클 내 스텝 트리. 순수 git notes 재구성, 자기완결(외부 리소스 0). Sheen(신), v3-build/C025.</footer>
<script>
%(js)s
</script>
</body>
</html>'''


CSS = '''
:root{--bg:#0f1115;--fg:#e6e8ec;--muted:#9aa1ac;--panel:#171a21;--edge:#5b6472;
  --node:#1c2028;--root:#3fbf6f;--merge:#f0a63c;--accent:#4f8cff;}
@media (prefers-color-scheme:light){:root{--bg:#f7f8fa;--fg:#1c1f26;--muted:#5b6472;
  --panel:#eef1f5;--edge:#9aa4b2;--node:#ffffff;}}
*{box-sizing:border-box}
body{margin:0;padding:20px;background:var(--bg);color:var(--fg);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
.head h1{margin:0 0 6px;font-size:20px}
.head h1 .sub{font-size:13px;color:var(--muted);font-weight:400;margin-left:8px}
.head .meta{display:flex;flex-wrap:wrap;gap:14px;color:var(--muted)}
.head .meta b{color:var(--fg)}
.hint{color:var(--muted);margin:8px 0 0}
.dag-canvas{overflow:auto;background:var(--panel);border-radius:10px;padding:10px;margin:14px 0;
  max-height:60vh}
svg.dag{display:block}
svg.dag .dag-edge{stroke:var(--edge);stroke-width:1.4;fill:none}
svg.dag .dag-box{fill:var(--node);stroke:var(--edge);stroke-width:1.5}
svg.dag .dag-node{cursor:pointer}
svg.dag .dag-node:hover .dag-box,svg.dag .dag-node:focus .dag-box{stroke:var(--accent);stroke-width:2.5}
svg.dag .dag-node.dag-root .dag-box{stroke:var(--root);stroke-width:2.5}
svg.dag .dag-node.dag-merge .dag-box{stroke:var(--merge);stroke-width:2.5}
svg.dag .dag-node.active .dag-box{fill:rgba(79,140,255,.18);stroke:var(--accent);stroke-width:3}
svg.dag .dag-label{font-size:11px;fill:var(--fg);pointer-events:none}
svg.dag .dag-edge.dangling{stroke:var(--merge);stroke-width:1.4;stroke-dasharray:4 3}
svg.dag .dangling-label{font-size:9px;fill:var(--merge);pointer-events:none}
.panels{margin-top:8px}
.steptree-panel{background:var(--panel);border-radius:10px;padding:8px 10px;margin:10px 0;
  border:1px solid var(--edge)}
.panel-head{display:flex;align-items:center;gap:10px;margin-bottom:6px;color:var(--muted)}
.panel-head b{color:var(--fg)}
.panel-close{margin-left:auto;background:transparent;border:1px solid var(--edge);
  color:var(--muted);border-radius:6px;padding:2px 8px;cursor:pointer;font-size:12px}
.panel-close:hover{color:var(--fg);border-color:var(--accent)}
.steptree-panel svg.steptree{max-width:100%;height:auto}
.steptree-panel .canvas,.steptree-panel{overflow-x:auto}
.empty-tree{color:var(--muted);font-style:italic;padding:8px}
.foot{margin-top:16px;color:var(--muted);font-size:12px}
'''


JS = '''
// 드릴다운: DAG 노드 클릭 → 그 사이클 스텝 트리 패널 hidden 토글.
// C006 교훈 — 각 패널 독립, hidden 하나만 뒤집는다(간섭 경로 없음, fetch 0).
(function(){
  function panel(key){ return document.getElementById("panel-" + cssEsc(key)); }
  function cssEsc(s){ return s; }
  function nodeG(key){
    var gs = document.querySelectorAll("svg.dag .dag-node");
    for (var i=0;i<gs.length;i++){ if (gs[i].getAttribute("data-key")===key) return gs[i]; }
    return null;
  }
  function toggle(key){
    var p = document.getElementById("panel-" + key);
    if (!p) return;
    var g = nodeG(key);
    if (p.hidden){
      p.hidden = false;
      if (g) g.classList.add("active");
      p.scrollIntoView({behavior:"smooth", block:"nearest"});
    } else {
      p.hidden = true;
      if (g) g.classList.remove("active");
    }
  }
  document.addEventListener("click", function(ev){
    var g = ev.target.closest ? ev.target.closest(".dag-node") : null;
    if (g){ toggle(g.getAttribute("data-key")); return; }
    var b = ev.target.closest ? ev.target.closest(".panel-close") : null;
    if (b){
      var key = b.getAttribute("data-key");
      var p = document.getElementById("panel-" + key);
      if (p){ p.hidden = true; var ng = nodeG(key); if (ng) ng.classList.remove("active"); }
    }
  });
  document.addEventListener("keydown", function(ev){
    if (ev.key !== "Enter" && ev.key !== " ") return;
    var g = document.activeElement;
    if (g && g.classList && g.classList.contains("dag-node")){
      ev.preventDefault(); toggle(g.getAttribute("data-key"));
    }
  });
})();
'''
