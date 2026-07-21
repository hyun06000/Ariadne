#!/usr/bin/env python3
"""v3 스텝 트리 뷰어 생성기 (순수 stdlib).

steps.yaml(C002 확정 표현) → 자기완결 단일 HTML(인라인 SVG+CSS+JS, 외부 리소스 0).

v2 뷰어(사이클=노드, 5스텝 선형)와 달리, 한 사이클 안의 **스텝 트리**를 그린다:
  (a) parent 엣지 = 가지, (b) backtrack 엣지 = 죽은 잎→조상 define 되돌아감,
  (c) 죽은 잎(outcome=backtrack, 벽의 지도) vs 산 잎(outcome=success) 구별.

C006 확장 (v3-build/C006, Sheen): 각 노드의 본문(steps/<id>.md)을 HTML에 **인라인
임베드**하고, 노드 클릭에 **본문 패널 토글**을 배선한다(상호작용). fetch 0 — 본문은
문서에 이미 있어 file://로 열린다. 상태보존(C010/C014 계보): 각 본문 패널은 독립,
`hidden` 속성만 뒤집어 다른 노드 조작이 이미 열린 본문을 지우지 않는다.

yaml 미의존 — C002 roundtrip.py와 같은 최소 서브셋 자작 파서.
"""
import html


# --- steps.yaml 파서 (C002 최소 서브셋: `- key: value` 블록 리스트) -------------
def parse_steps_yaml(text):
    nodes = []
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.lstrip().startswith("- "):
            if cur is not None:
                nodes.append(cur)
            cur = {}
            line = line.lstrip()[2:]  # strip "- "
            # first key on the dash line
        # now line is "key: value"
        if ":" not in line:
            continue
        key, _, val = line.strip().partition(":")
        key = key.strip()
        val = val.strip()
        if val == "null" or val == "":
            val = None
        cur[key] = val
    if cur is not None:
        nodes.append(cur)
    return nodes


# --- 트리 위상 -----------------------------------------------------------------
def build_tree(nodes):
    by_id = {n["id"]: n for n in nodes}
    children = {n["id"]: [] for n in nodes}
    root = None
    for n in nodes:
        p = n.get("parent")
        if p is None:
            root = n["id"]
        else:
            children[p].append(n["id"])
    # depth = 루트에서 parent 체인 길이 (순수 위상, id와 독립)
    depth = {}

    def set_depth(nid, d):
        depth[nid] = d
        for c in children[nid]:
            set_depth(c, d + 1)

    set_depth(root, 0)
    return by_id, children, root, depth


def assign_columns(children, root):
    """각 노드에 가로 슬롯(col) 부여: 서브트리를 빈틈없이 leaf 순서로 배치.
    각 가지가 선형인 이 데이터에선 leaf마다 1콜, 조상은 자식 콜 평균."""
    col = {}
    counter = [0]

    def walk(nid):
        kids = children[nid]
        if not kids:
            col[nid] = counter[0]
            counter[0] += 1
            return col[nid]
        cs = [walk(k) for k in kids]
        col[nid] = sum(cs) / len(cs)
        return col[nid]

    walk(root)
    return col


# --- 좌표 ----------------------------------------------------------------------
COL_W = 190
ROW_H = 130
NODE_W = 150
NODE_H = 66
PAD_X = 60
PAD_Y = 150  # 범례/헤더 공간

KIND_LABEL = {
    "define": "define",
    "hypothesis": "hypothesis",
    "verify": "verify",
    "analyze": "analyze",
}


def node_xy(nid, col, depth):
    cx = PAD_X + col[nid] * COL_W + NODE_W / 2
    cy = PAD_Y + depth[nid] * ROW_H + NODE_H / 2
    return cx, cy


def render_html(nodes, chain="v3-build", cycle="case-c012-c014", bodies=None):
    bodies = bodies or {}
    by_id, children, root, depth = build_tree(nodes)
    col = assign_columns(children, root)

    max_col = max(col.values())
    max_depth = max(depth.values())
    width = int(PAD_X * 2 + max_col * COL_W + NODE_W)
    height = int(PAD_Y + (max_depth + 1) * ROW_H + 40)

    parent_edges = []
    backtrack_edges = []
    node_svg = []

    live_leaves = []
    dead_leaves = []

    for n in nodes:
        nid = n["id"]
        kind = n["kind"]
        outcome = n.get("outcome")
        cx, cy = node_xy(nid, col, depth)
        x = cx - NODE_W / 2
        y = cy - NODE_H / 2

        # parent 엣지 (가지): 부모 하단 중앙 → 자식 상단 중앙, 실선 직선
        p = n.get("parent")
        if p is not None:
            px, py = node_xy(p, col, depth)
            parent_edges.append(
                f'<line class="edge-parent" x1="{px:.1f}" y1="{py + NODE_H/2:.1f}" '
                f'x2="{cx:.1f}" y2="{cy - NODE_H/2:.1f}" '
                f'data-from="{p}" data-to="{nid}" />'
            )

        # 잎 운명 표식
        node_classes = ["node", f"kind-{kind}"]
        badge = ""
        if kind == "analyze" and outcome == "success":
            node_classes.append("leaf-live")
            live_leaves.append(nid)
            badge = (
                f'<text class="badge badge-live" x="{cx:.1f}" y="{cy + NODE_H/2 + 18:.1f}" '
                f'text-anchor="middle">✓ 산 잎 (success)</text>'
            )
        elif kind == "analyze" and outcome == "backtrack":
            node_classes.append("leaf-dead")
            dead_leaves.append(nid)
            bt = n.get("backtrack")
            badge = (
                f'<text class="badge badge-dead" x="{cx:.1f}" y="{cy + NODE_H/2 + 18:.1f}" '
                f'text-anchor="middle">✕ 죽은 잎 · '
                f'벽의 지도 (backtrack→{html.escape(bt or "?")})</text>'
            )

        # backtrack 엣지 (되돌아감): 잎 → 조상 define, 파선 곡선 + 화살촉
        if outcome == "backtrack":
            bt = n.get("backtrack")
            if bt is not None and bt in by_id:
                tx, ty = node_xy(bt, col, depth)
                # 출발: 잎 좌측; 도착: 조상 define 좌측. 왼쪽 밖으로 크게 우회.
                sx, sy = x, cy
                dx, dy = tx - NODE_W / 2, ty
                bulge = PAD_X - 30
                path = (
                    f'M {sx:.1f} {sy:.1f} '
                    f'C {bulge:.1f} {sy:.1f}, {bulge:.1f} {dy:.1f}, {dx:.1f} {dy:.1f}'
                )
                backtrack_edges.append(
                    f'<path class="edge-backtrack" d="{path}" '
                    f'marker-end="url(#bt-arrow)" '
                    f'data-from="{nid}" data-to="{bt}" '
                    f'data-y-from="{sy:.1f}" data-y-to="{dy:.1f}" />'
                )

        label_kind = KIND_LABEL.get(kind, kind)
        node_classes.append("clickable")
        node_svg.append(
            f'<g class="{" ".join(node_classes)}" data-id="{nid}" data-kind="{kind}" '
            f'data-outcome="{outcome or ""}" data-body="body-{nid}" '
            f'role="button" tabindex="0" '
            f'aria-label="{nid} {label_kind} — 클릭하면 본문 펼침">'
            f'<rect class="node-box" x="{x:.1f}" y="{y:.1f}" rx="10" ry="10" '
            f'width="{NODE_W}" height="{NODE_H}" />'
            f'<text class="node-id" x="{cx:.1f}" y="{cy - 8:.1f}" text-anchor="middle">{nid}</text>'
            f'<text class="node-kind" x="{cx:.1f}" y="{cy + 14:.1f}" text-anchor="middle">{label_kind}</text>'
            f'{badge}</g>'
        )

    closeable = "예 (산 잎 도달)" if live_leaves else "아니오 (진행 중)"

    # --- 본문 인라인 임베드 (C006): 각 노드의 steps/<id>.md를 escape 후 패널로 ------
    body_panels = []
    for n in nodes:
        nid = n["id"]
        kind = n["kind"]
        raw = bodies.get(nid, "")
        body_panels.append(
            f'<article class="stepbody" id="body-{nid}" data-id="{nid}" hidden>'
            f'<div class="stepbody-head">'
            f'<span class="sb-id kind-{kind}-tag">{nid}</span>'
            f'<span class="sb-kind">{html.escape(KIND_LABEL.get(kind, kind))}</span>'
            f'<button class="sb-close" type="button" data-close="body-{nid}" '
            f'aria-label="닫기">✕</button>'
            f'</div>'
            f'<pre class="sb-body">{html.escape(raw)}</pre>'
            f'</article>'
        )
    bodies_section = (
        '<section class="bodies" aria-label="스텝 본문">'
        '<h2 class="bodies-title">스텝 본문 <span class="bodies-hint">'
        '(위 트리에서 노드를 클릭하면 여기 펼쳐진다 · 여러 개 동시 열림 유지)</span></h2>'
        + "".join(body_panels)
        + '</section>'
    )

    svg = f'''<svg class="steptree" viewBox="0 0 {width} {height}" width="{width}" height="{height}"
   xmlns="http://www.w3.org/2000/svg" role="img"
   aria-label="v3 스텝 트리: {len(nodes)}노드">
  <defs>
    <marker id="bt-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" class="bt-arrowhead" />
    </marker>
  </defs>
  <g class="edges-parent">{"".join(parent_edges)}</g>
  <g class="edges-backtrack">{"".join(backtrack_edges)}</g>
  <g class="nodes">{"".join(node_svg)}</g>
</svg>'''

    legend = f'''<div class="legend">
  <span class="lg lg-parent"><svg width="34" height="12"><line x1="2" y1="6" x2="32" y2="6" class="edge-parent"/></svg> parent 엣지 (가지)</span>
  <span class="lg lg-backtrack"><svg width="34" height="12"><line x1="2" y1="6" x2="32" y2="6" class="edge-backtrack"/></svg> backtrack 엣지 (되돌아감)</span>
  <span class="lg"><b class="chip leaf-live-chip">✓</b> 산 잎 (success)</span>
  <span class="lg"><b class="chip leaf-dead-chip">✕</b> 죽은 잎 (backtrack · 벽의 지도)</span>
  <span class="lg"><b class="chip kind-define-chip"></b>define</span>
  <span class="lg"><b class="chip kind-hypothesis-chip"></b>hypothesis</span>
  <span class="lg"><b class="chip kind-verify-chip"></b>verify</span>
  <span class="lg"><b class="chip kind-analyze-chip"></b>analyze</span>
</div>'''

    header = f'''<header class="head">
  <h1>v3 스텝 트리 뷰어</h1>
  <div class="meta">
    <span>chain: <b>{html.escape(chain)}</b></span>
    <span>cycle: <b>{html.escape(cycle)}</b></span>
    <span>노드: <b>{len(nodes)}</b></span>
    <span>산 잎: <b>{len(live_leaves)}</b></span>
    <span>죽은 잎: <b>{len(dead_leaves)}</b></span>
    <span>close 가능: <b>{closeable}</b></span>
  </div>
</header>'''

    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>v3 스텝 트리 뷰어 — {html.escape(cycle)}</title>
<style>
{CSS}
</style>
</head>
<body>
{header}
{legend}
<div class="canvas">
{svg}
</div>
{bodies_section}
<footer class="foot">v3 뷰어 — 사이클=스텝들의 트리. 노드 클릭 → 본문 펼침(상태보존). 자기완결(외부 리소스 0). Sheen(신), v3-build/C006.</footer>
<script>
{JS}
</script>
</body>
</html>'''


CSS = '''
:root{
  --bg:#0f1115; --fg:#e6e8ec; --muted:#9aa1ac; --panel:#171a21;
  --edge:#5b6472; --bt:#f08a3c; --live:#3fbf6f; --dead:#6b7280;
  --define:#3b82f6; --hypothesis:#a855f7; --verify:#14b8a6; --analyze:#4b5563;
}
@media (prefers-color-scheme: light){
  :root{ --bg:#f7f8fa; --fg:#1c1f26; --muted:#5b6472; --panel:#eef1f5; --edge:#9aa4b2; }
}
*{box-sizing:border-box}
body{margin:0;padding:20px;background:var(--bg);color:var(--fg);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
.head h1{margin:0 0 6px;font-size:19px}
.head .meta{display:flex;flex-wrap:wrap;gap:14px;color:var(--muted)}
.head .meta b{color:var(--fg)}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin:14px 0;padding:10px 12px;
  background:var(--panel);border-radius:8px;color:var(--muted)}
.legend .lg{display:inline-flex;align-items:center;gap:6px}
.chip{display:inline-block;width:14px;height:14px;border-radius:3px;font-size:11px;
  line-height:14px;text-align:center;color:#fff}
.kind-define-chip{background:var(--define)}
.kind-hypothesis-chip{background:var(--hypothesis)}
.kind-verify-chip{background:var(--verify)}
.kind-analyze-chip{background:var(--analyze)}
.leaf-live-chip{background:var(--live)}
.leaf-dead-chip{background:transparent;color:var(--dead);border:1px dashed var(--dead)}
.canvas{overflow-x:auto;background:var(--panel);border-radius:10px;padding:8px}
svg.steptree{max-width:100%;height:auto;display:block}

/* 엣지 — 두 종류를 명확히 가른다 */
.edge-parent{stroke:var(--edge);stroke-width:2;fill:none}
.edge-backtrack{stroke:var(--bt);stroke-width:2.4;stroke-dasharray:7 5;fill:none}
.bt-arrowhead{fill:var(--bt)}

/* 노드 */
.node .node-box{fill:var(--panel);stroke:var(--edge);stroke-width:1.5}
.node .node-id{font-weight:700;font-size:15px;fill:var(--fg)}
.node .node-kind{font-size:11px;fill:var(--muted)}
.kind-define .node-box{stroke:var(--define);stroke-width:2.5}
.kind-hypothesis .node-box{stroke:var(--hypothesis);stroke-width:2}
.kind-verify .node-box{stroke:var(--verify);stroke-width:2}
.kind-analyze .node-box{stroke:var(--analyze);stroke-width:2}

/* 잎 두 운명 */
.leaf-live .node-box{stroke:var(--live);stroke-width:3.5;fill:rgba(63,191,111,.14)}
.leaf-dead .node-box{stroke:var(--dead);stroke-width:2;stroke-dasharray:5 4;
  fill:rgba(107,114,128,.10);opacity:.9}
.leaf-dead .node-id,.leaf-dead .node-kind{opacity:.75}
.badge{font-size:11px;font-weight:600}
.badge-live{fill:var(--live)}
.badge-dead{fill:var(--dead)}
.foot{margin-top:16px;color:var(--muted);font-size:12px}

/* --- C006: 클릭 가능 노드 + 열림 강조 --- */
.node.clickable{cursor:pointer}
.node.clickable:focus{outline:none}
.node.clickable:focus .node-box{stroke:var(--define);stroke-width:3}
.node.clickable:hover .node-box{filter:brightness(1.15)}
.node.open .node-box{stroke:var(--live);stroke-width:3.5}
.node.open .node-id::after{content:" ▾"}

/* --- C006: 본문 패널 --- */
.bodies{margin-top:22px}
.bodies-title{font-size:15px;margin:0 0 10px}
.bodies-hint{font-weight:400;color:var(--muted);font-size:12px}
.stepbody{background:var(--panel);border:1px solid var(--edge);border-radius:9px;
  padding:12px 14px;margin:0 0 12px;border-left:4px solid var(--define)}
.stepbody[hidden]{display:none}
.stepbody-head{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.sb-id{font-weight:700;font-size:14px;padding:2px 8px;border-radius:5px;color:#fff}
.kind-define-tag{background:var(--define)}
.kind-hypothesis-tag{background:var(--hypothesis)}
.kind-verify-tag{background:var(--verify)}
.kind-analyze-tag{background:var(--analyze)}
.sb-kind{color:var(--muted);font-size:12px}
.sb-close{margin-left:auto;background:transparent;border:1px solid var(--edge);
  color:var(--muted);border-radius:5px;cursor:pointer;font-size:12px;padding:2px 7px}
.sb-close:hover{color:var(--fg);border-color:var(--fg)}
.sb-body{margin:0;white-space:pre-wrap;word-break:break-word;font:13px/1.6
  ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--fg)}
'''

# --- C006: 상호작용 JS (인라인, 외부 src 0) ---------------------------------------
# 노드 클릭 → 그 노드의 본문 패널 hidden 토글. 각 패널 독립 → 다른 노드 조작이
# 이미 열린 본문을 안 지운다(C010/C014 상태보존: hidden 속성만 뒤집는다).
JS = '''
(function(){
  function panelOf(id){ return document.getElementById(id); }
  function nodeOf(bodyId){
    return document.querySelector('.node.clickable[data-body="'+bodyId+'"]');
  }
  function toggle(g){
    var bodyId = g.getAttribute('data-body');
    var panel = panelOf(bodyId);
    if(!panel) return;
    var willOpen = panel.hasAttribute('hidden');
    if(willOpen){ panel.removeAttribute('hidden'); g.classList.add('open'); }
    else { panel.setAttribute('hidden',''); g.classList.remove('open'); }
    // 상태보존: 다른 패널·노드는 전혀 건드리지 않는다 (통스왑 없음).
  }
  document.querySelectorAll('.node.clickable').forEach(function(g){
    g.addEventListener('click', function(){ toggle(g); });
    g.addEventListener('keydown', function(e){
      if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggle(g); }
    });
  });
  document.querySelectorAll('.sb-close').forEach(function(btn){
    btn.addEventListener('click', function(){
      var bodyId = btn.getAttribute('data-close');
      var panel = panelOf(bodyId);
      if(panel){ panel.setAttribute('hidden',''); }
      var g = nodeOf(bodyId);
      if(g){ g.classList.remove('open'); }
    });
  });
})();
'''


def _read_body(nid, node, base_dir):
    """steps/<id>.md 본문을 읽는다. base_dir 기준 상대경로(node['body'])."""
    import os
    rel = node.get("body") or ("steps/%s.md" % nid)
    path = os.path.join(base_dir, rel)
    with open(path, encoding="utf-8") as f:
        return f.read()


def html_from_yaml_text(text, chain="v3-build", cycle="case-c012-c014", base_dir=None):
    nodes = parse_steps_yaml(text)
    bodies = {}
    if base_dir is not None:
        for n in nodes:
            bodies[n["id"]] = _read_body(n["id"], n, base_dir)
    return render_html(nodes, chain=chain, cycle=cycle, bodies=bodies)
