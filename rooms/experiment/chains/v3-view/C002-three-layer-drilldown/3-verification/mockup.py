#!/usr/bin/env python3
"""mockup — v3-view/C002 3층 드릴다운 목업 (V0, 방향 확인용).

목적: 체인 → 사이클 DAG → 스텝 트리 세 층을 **한 페이지·한 시각 언어**로 배선한 모습을
상현님께 캡쳐로 보이고 방향(승인/리젝트)을 받는다. 실 gil 배선 아님 — 샘플 데이터.

시각 언어 (C001 확정 계승):
- 원형 노드 + 원 아래 이름 + 작은 sub. R=11, 가로 흐름(왼→오른).
- 실선 parent 엣지, 파선 backtrack 엣지, kind/status 색.
- 사이클 DAG도 **똑같이** 원형 노드+실선 — 층이 바뀌어도 시각이 튀지 않는다(연속감).

드릴다운: 사이클 노드 클릭 → 그 아래 카드가 열리며 그 사이클의 스텝 트리가 펼쳐진다.
스텝 트리는 C001 circletree 그대로. 자기완결(외부 리소스 0).
"""
import os, sys, html

HERE = os.path.dirname(os.path.abspath(__file__))
C001 = os.path.normpath(os.path.join(
    HERE, "..", "..", "..", "v3-view",
    "C001-circular-step-tree-unified-language", "3-verification"))
sys.path.insert(0, C001)
import circletree as ct  # noqa: E402

R = ct.R
STEP_W = ct.STEP_W
LANE_H = ct.LANE_H

# ── 층 1: 사이클 DAG 색 (status로 구분 — 스텝 kind 색과 겹치되 의미는 사이클 상태) ──
# 진행중=보라, solved=초록, 죽음(폐기)=빨강, pending(사람 대기)=분홍.
CYC_COLOR = {
    "solved":      "#16a34a",   # 초록 — 산 사이클
    "in_progress": "#7c3aed",   # 보라 — 진행 중
    "pending":     "#e879f9",   # 분홍 — 사람 대기
    "dead":        "#dc2626",   # 빨강 — 폐기(죽은 잎)
    "root":        "#2563eb",   # 파랑 — 체인 루트(문제정의 층)
}
CYC_LABEL = {"solved": "solved", "in_progress": "진행중",
             "pending": "대기", "dead": "폐기", "root": "루트"}

# ── 샘플 데이터 (실 데이터 아님, 방향 확인용) ──
# 사이클 DAG: parent 계보. col=세로 lane, depth=가로.
CYCLES = [
    # id,           parent,  status,        depth, col,  스텝트리 steps.yaml (있으면)
    ("C001-seed",   None,    "solved",       0, 1, None),
    ("C002-split",  "C001-seed", "solved",   1, 0, None),
    ("C003-merge",  "C001-seed", "solved",   1, 2, None),
    ("C004-tree",   "C002-split", "solved",  2, 0, "TREE"),   # 실 스텝트리 임베드
    ("C005-probe",  "C003-merge", "dead",    2, 2, None),
    ("C006-now",    "C004-tree", "in_progress", 3, 0, None),
    ("C007-ask",    "C004-tree", "pending",  3, 1, None),
]

PAD_X, PAD_Y = 60, 70


def cyc_xy(depth, col):
    return PAD_X + depth * (STEP_W + 20) + R, PAD_Y + col * (LANE_H + 4) + R


def render_cycle_dag():
    edges, nodes = [], []
    pos = {c[0]: cyc_xy(c[3], c[4]) for c in CYCLES}
    max_d = max(c[3] for c in CYCLES)
    max_c = max(c[4] for c in CYCLES)
    width = int(PAD_X * 2 + max_d * (STEP_W + 20) + R * 2 + 40)
    height = int(PAD_Y + max_c * (LANE_H + 4) + R * 2 + 40)
    for cid, parent, status, d, c, tree in CYCLES:
        cx, cy = pos[cid]
        if parent:
            px, py = pos[parent]
            mx = (px + cx) / 2
            edges.append(
                f'<path class="edge-parent" d="M {px+R:.0f} {py:.0f} '
                f'C {mx:.0f} {py:.0f}, {mx:.0f} {cy:.0f}, {cx-R:.0f} {cy:.0f}" />')
        color = CYC_COLOR[status]
        cls = f"cyc-node status-{status}"
        drill = f'data-tree="tree-{cid}"' if tree else ""
        clickable = "clickable" if tree else "noleaf"
        nodes.append(
            f'<g class="{cls} {clickable}" data-id="{cid}" {drill} tabindex="0" '
            f'role="button" aria-label="사이클 {cid} 드릴다운">'
            f'<circle class="c-hit" cx="{cx:.0f}" cy="{cy:.0f}" r="{R+9}" fill="transparent"/>'
            f'<circle class="c-circle" cx="{cx:.0f}" cy="{cy:.0f}" r="{R}" '
            f'fill="{color}" stroke="{color}"/>'
            f'<text class="c-name" x="{cx:.0f}" y="{cy+R+16:.0f}" text-anchor="middle">'
            f'{html.escape(cid.split("-",1)[0])}</text>'
            f'<text class="c-sub" x="{cx:.0f}" y="{cy+R+31:.0f}" text-anchor="middle">'
            f'{html.escape(cid.split("-",1)[1] if "-" in cid else "")}</text></g>')
    svg = (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
           f'xmlns="http://www.w3.org/2000/svg">'
           + "".join(edges) + "".join(nodes) + '</svg>')
    return svg


def step_tree_html_for(cid, steps_src):
    """C001 circletree로 한 사이클의 스텝 트리 SVG+본문을 만든다."""
    nodes = ct.parse_steps_yaml(open(steps_src, encoding="utf-8").read())
    steps_dir = os.path.join(os.path.dirname(os.path.abspath(steps_src)), "steps")
    bodies = ct._load_bodies(nodes, steps_dir)
    # circletree.render_html은 완전한 문서 → 우리는 SVG+본문 조각만 필요.
    # 간단히: 전체 문서를 iframe srcdoc로 임베드하면 스타일 격리까지 공짜.
    doc = ct.render_html(nodes, chain="v3-view", cycle=cid, bodies=bodies)
    return doc


def build():
    tree_src = os.path.normpath(os.path.join(
        C001, "design-steptree", "steps.yaml"))
    dag_svg = render_cycle_dag()

    # 드릴다운 카드들 — 각 사이클의 스텝 트리. 지금은 TREE 하나만 실데이터.
    drill_cards = []
    for cid, parent, status, d, c, tree in CYCLES:
        if not tree:
            continue
        inner = step_tree_html_for(cid, tree_src)
        srcdoc = html.escape(inner, quote=True)
        drill_cards.append(
            f'<section class="drill" id="tree-{cid}" hidden>'
            f'<div class="drill-head"><span class="drill-badge" '
            f'style="background:{CYC_COLOR[status]}"></span>'
            f'<b>{html.escape(cid)}</b> 의 스텝 트리 '
            f'<span class="drill-hint">— 사이클 안으로 드릴다운 (같은 시각 언어)</span>'
            f'<button class="drill-close" data-close="tree-{cid}" aria-label="닫기">✕'
            f'</button></div>'
            f'<iframe class="drill-frame" srcdoc="{srcdoc}" loading="lazy"></iframe>'
            f'</section>')

    legend = "".join(
        f'<span class="lg"><span class="sw" style="background:{CYC_COLOR[k]};'
        f'border-color:{CYC_COLOR[k]}"></span>{CYC_LABEL[k]}</span>'
        for k in ["root", "in_progress", "solved", "pending", "dead"])

    return f"""<!doctype html><meta charset="utf-8">
<style>{PAGE_CSS}</style>
<div class="head">
  <h1>v3 통합 뷰어 — 3층 드릴다운 (목업)</h1>
  <div class="meta">체인 <b>v3-view</b> · 사이클 DAG {len(CYCLES)}개 · 원형 노드+실선 —
  스텝 트리와 <b>같은 시각 언어</b>. 사이클 노드를 클릭하면 그 사이클의 스텝 트리가 아래에 열린다.</div>
</div>
<div class="layer-label">층 1 · 사이클 DAG <span class="ll-hint">(체인 안의 사이클 계보 — 어느 사이클이 어느 사이클에서 태어났나)</span></div>
<div class="legend">{legend}<span class="lg"><svg width="34" height="10"><line x1="0" y1="5" x2="34" y2="5" stroke="#94a3b8" stroke-width="2"/></svg>계보 실선</span></div>
<div class="wrap">{dag_svg}</div>
<div class="layer-label">층 2 · 스텝 트리 <span class="ll-hint">(사이클 노드 클릭 → 그 사이클 내부의 사고 트리가 여기 열린다)</span></div>
<div class="drill-zone">{"".join(drill_cards)}
  <div class="drill-empty" id="drill-empty">위 사이클 DAG에서 <b>C004</b>(초록 노드)를 클릭해보세요 — 그 사이클의 스텝 트리가 같은 시각 언어로 펼쳐집니다.</div>
</div>
<div class="head"><div class="meta">v3-view/C002 목업 · Clew · 자기완결 (외부 리소스 0)</div></div>
<script>{PAGE_JS}</script>
"""


PAGE_CSS = """
:root{color-scheme:light dark}
body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#fff;color:#0f172a}
@media (prefers-color-scheme:dark){body{background:#0b1120;color:#e2e8f0}}
.head{padding:20px 24px 6px}.head h1{margin:0;font-size:20px}
.meta{color:#64748b;font-size:13px;margin-top:4px}
.layer-label{padding:16px 24px 2px;font-size:13px;font-weight:700;color:#475569}
@media (prefers-color-scheme:dark){.layer-label{color:#94a3b8}}
.ll-hint{font-weight:400;color:#94a3b8}
.legend{display:flex;flex-wrap:wrap;gap:14px 20px;padding:10px 24px;margin:6px 24px;
  background:#f8fafc;border-radius:10px;font-size:12.5px}
@media (prefers-color-scheme:dark){.legend{background:#111a2e}}
.lg{display:flex;align-items:center;gap:6px}
.sw{width:16px;height:16px;border-radius:50%;display:inline-block;border:2px solid}
.wrap{overflow-x:auto;padding:6px 24px 8px}
.edge-parent{stroke:#94a3b8;stroke-width:1.8;fill:none}
.c-circle{stroke-width:2}
.c-name{font-size:12.5px;font-weight:700;fill:#334155}
.c-sub{font-size:10px;fill:#94a3b8}
@media (prefers-color-scheme:dark){.c-name{fill:#cbd5e1}.c-sub{fill:#64748b}}
.status-solved .c-circle{stroke-width:3}
.status-pending .c-circle{fill-opacity:.35;stroke-dasharray:3 3}
.status-dead .c-name{fill:#dc2626}
.cyc-node.clickable{cursor:pointer}
.cyc-node.clickable:hover .c-circle{stroke:#0f172a;stroke-width:3.5}
.cyc-node.open .c-circle{stroke:#0f172a;stroke-width:4}
.cyc-node.noleaf{cursor:default;opacity:.9}
.drill-zone{padding:2px 24px 24px}
.drill-empty{color:#94a3b8;font-size:13px;padding:24px;text-align:center;
  border:1.5px dashed #cbd5e1;border-radius:12px;margin:8px 0}
@media (prefers-color-scheme:dark){.drill-empty{border-color:#334155}}
.drill{border:1px solid #e2e8f0;border-radius:12px;margin:8px 0;overflow:hidden;
  background:#fff}
@media (prefers-color-scheme:dark){.drill{border-color:#1e293b;background:#0d1526}}
.drill[hidden]{display:none}
.drill-head{display:flex;align-items:center;gap:8px;padding:10px 14px;
  border-bottom:1px solid #eef2f7;font-size:13px}
@media (prefers-color-scheme:dark){.drill-head{border-color:#1e293b}}
.drill-badge{width:11px;height:11px;border-radius:50%;display:inline-block}
.drill-hint{color:#94a3b8;font-weight:400}
.drill-close{margin-left:auto;border:none;background:transparent;cursor:pointer;
  color:#94a3b8;font-size:15px}
.drill-frame{width:100%;height:640px;border:0;display:block}
"""

PAGE_JS = """
(function(){
  function closeAll(){
    document.querySelectorAll('.drill').forEach(function(s){ s.setAttribute('hidden',''); });
    document.querySelectorAll('.cyc-node.open').forEach(function(g){ g.classList.remove('open'); });
    var e=document.getElementById('drill-empty'); if(e) e.style.display='';
  }
  function drill(g){
    var id=g.getAttribute('data-tree'); if(!id) return;
    var s=document.getElementById(id); if(!s) return;
    var wasOpen=!s.hasAttribute('hidden');
    closeAll();
    if(!wasOpen){
      s.removeAttribute('hidden'); g.classList.add('open');
      var e=document.getElementById('drill-empty'); if(e) e.style.display='none';
      s.scrollIntoView({block:'nearest',behavior:'smooth'});
    }
  }
  document.querySelectorAll('.cyc-node.clickable').forEach(function(g){
    g.addEventListener('click', function(){ drill(g); });
    g.addEventListener('keydown', function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); drill(g);} });
  });
  document.querySelectorAll('.drill-close').forEach(function(b){
    b.addEventListener('click', function(){
      var id=b.getAttribute('data-close'), s=document.getElementById(id);
      if(s) s.setAttribute('hidden','');
      var g=document.querySelector('.cyc-node[data-tree="'+id+'"]');
      if(g) g.classList.remove('open');
      var e=document.getElementById('drill-empty'); if(e) e.style.display='';
    });
  });
})();
"""


if __name__ == "__main__":
    dst = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out.html")
    doc = build()
    open(dst, "w", encoding="utf-8").write(doc)
    print(f"wrote {dst} ({len(doc)} bytes)")
