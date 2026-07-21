#!/usr/bin/env python3
"""circletree — v3 스텝 트리를 사이클 DAG와 같은 원형 노드+실선 언어로 렌더 (V1 목업).

C004 steptree의 파서·트리·컬럼 배치를 재사용하고(닫힌 사이클 코드 import),
**노드 렌더만 박스→원으로** 교체한다. 변화를 노드 표현에 국소화 — 원형이 유일 변수.
순수 stdlib, 자기완결 SVG(외부 리소스 0).
"""
import os, sys, html

HERE = os.path.dirname(os.path.abspath(__file__))
C004 = os.path.normpath(os.path.join(
    HERE, "..", "..", "..", "v3-build", "C004-v3-viewer-step-tree", "3-verification"))
sys.path.insert(0, C004)
from steptree import parse_steps_yaml, build_tree, assign_columns  # noqa: E402

# 레이아웃 — 가로 흐름 (사이클 DAG처럼 왼→오른). depth=가로축, 형제(col)=세로축.
# v2 DAG 실측: 원 반경 r=9, 노드 간격 116px (간격/반경 ≈ 13 — 여백 넉넉, 작고 귀여움).
STEP_W = 116   # depth 한 칸당 가로 간격 (DAG와 동일)
LANE_H = 96    # 형제 가지 한 칸당 세로 간격
PAD_X = 60
PAD_Y = 150
R = 11  # 원 반경 (DAG r=9에 근접, 작고 귀엽게)

KIND_COLOR = {
    "define": "#2563eb",      # 파랑 — 문제정의 (루트든 분석 다음이든 하나로 통합)
    "hypothesis": "#7c3aed",  # 보라 — 가설
    "verify": "#0d9488",      # 청록 — 검증
    "analyze": "#64748b",     # 회색 — 분석
    # 분석 다음 결과 — 문제정의(define)/실패/성공/대기
    "fail": "#dc2626",        # 빨강 — 실패 (백트래킹)
    "success": "#16a34a",     # 초록 — 성공 (산 잎, 끝)
    "pending": "#e879f9",     # 분홍 — 대기 (사람에게 묻는 중, 아직 미결정)
}
KIND_LABEL = {"fail": "실패", "success": "성공", "pending": "대기",
              "define": "문제정의", "hypothesis": "가설",
              "verify": "검증", "analyze": "분석"}
# 분석 다음에 올 수 있는 것: 문제정의(define, 앞으로)·실패·성공·대기.
# define/redefine 구별 폐지 — 문제정의는 그냥 문제정의(상현님).
RESULT_KINDS = {"fail", "success", "pending"}


def node_xy(nid, col, depth):
    # 가로: depth가 x를 밀고(왼→오른), 세로: col(형제)이 y를 쌓는다.
    return PAD_X + depth[nid] * STEP_W + R, PAD_Y + col[nid] * LANE_H + R


CSS = """
:root{color-scheme:light dark}
body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#fff;color:#0f172a}
@media (prefers-color-scheme:dark){body{background:#0b1120;color:#e2e8f0}}
.head{padding:20px 24px 6px}.head h1{margin:0;font-size:19px}
.meta{color:#64748b;font-size:13px;margin-top:4px}
.legend{display:flex;flex-wrap:wrap;gap:14px 20px;padding:12px 24px;margin:8px 24px;
  background:#f8fafc;border-radius:10px;font-size:12.5px}
@media (prefers-color-scheme:dark){.legend{background:#111a2e}}
.lg{display:flex;align-items:center;gap:6px}
.sw{width:16px;height:16px;border-radius:50%;display:inline-block;border:2px solid}
.wrap{overflow-x:auto;padding:8px 24px 32px}
.edge-parent{stroke:#94a3b8;stroke-width:1.8;fill:none}
.edge-backtrack{stroke:#f59e0b;stroke-width:1.8;stroke-dasharray:6 5;fill:none}
.n-circle{stroke-width:2}
.n-name{font-size:12.5px;font-weight:600;fill:#334155}
.n-sub{font-size:10.5px;fill:#94a3b8}
@media (prefers-color-scheme:dark){.n-name{fill:#cbd5e1}.n-sub{fill:#64748b}}
.result-success .n-circle{stroke-width:3}
.result-fail .n-name{fill:#dc2626}
.result-success .n-name{fill:#16a34a}
/* 대기 — 아직 미결정. 채움 흐리게 + 파선 테두리로 "기다리는 중" 표시. */
.result-pending .n-circle{fill-opacity:.35;stroke-dasharray:3 3}
.result-pending .n-name{fill:#c026d3;font-weight:700}
"""


def render_html(nodes, chain="v3-view", cycle="case-c012-c014", bodies=None):
    bodies = bodies or {}
    by_id, children, root, depth = build_tree(nodes)
    col = assign_columns(children, root)
    max_col = max(col.values())
    max_depth = max(depth.values())
    # 가로 흐름: 너비는 depth가, 높이는 형제(col)가 정한다.
    width = int(PAD_X * 2 + max_depth * STEP_W + R * 2 + 60)
    height = int(PAD_Y + max_col * LANE_H + R * 2 + 40)

    p_edges, bt_edges, node_svg, region_svg = [], [], [], []
    live, dead = [], []
    by = {n["id"]: n for n in nodes}

    # --- 문제 영역 리본 (상현님: "백트래킹을 문제 단위로") ---
    # 각 문제정의(define)는 자기 하위 시도(다음 define 전까지)를 하나의 문제로 소유한다.
    # 그 소유 노드들의 bbox를 연한 배경 리본으로 그려 "이 시도들은 이 문제에 속한다"를 보인다.
    def owned(root_id):
        """root_id(define)가 소유하는 노드 id들 — 자식으로 내려가되 다른 define에서 멈춘다."""
        acc, stack = [root_id], list(children.get(root_id, []))
        while stack:
            cid = stack.pop()
            if by[cid]["kind"] == "define":   # 다른 문제의 시작 — 소유 밖
                continue
            acc.append(cid)
            stack.extend(children.get(cid, []))
        return acc
    RIB_PAL = ["#3b82f6", "#8b5cf6", "#14b8a6", "#f59e0b", "#ec4899", "#64748b"]
    define_ids = [n["id"] for n in nodes if n["kind"] == "define"]
    for i, did in enumerate(define_ids):
        ids = owned(did)
        xs = [node_xy(x, col, depth)[0] for x in ids]
        ys = [node_xy(x, col, depth)[1] for x in ids]
        x0, x1 = min(xs) - R - 12, max(xs) + R + 12
        y0, y1 = min(ys) - R - 10, max(ys) + R + 34  # 아래 라벨 공간
        c = RIB_PAL[i % len(RIB_PAL)]
        region_svg.append(
            f'<rect class="region" x="{x0:.0f}" y="{y0:.0f}" '
            f'width="{x1 - x0:.0f}" height="{y1 - y0:.0f}" rx="16" '
            f'fill="{c}" fill-opacity="0.06" stroke="{c}" stroke-opacity="0.22" '
            f'data-problem="{did}" />')

    for n in nodes:
        nid, kind, outcome = n["id"], n["kind"], n.get("outcome")
        cx, cy = node_xy(nid, col, depth)

        # parent 엣지 = 실선 (부모 원 우측 → 자식 원 좌측, 왼→오른 흐름)
        p = n.get("parent")
        if p is not None:
            px, py = node_xy(p, col, depth)
            # 부드러운 수평 베지어 (같은 lane이면 직선, 다른 lane이면 S자)
            mx = (px + cx) / 2
            p_edges.append(
                f'<path class="edge-parent" d="M {px + R:.0f} {py:.0f} '
                f'C {mx:.0f} {py:.0f}, {mx:.0f} {cy:.0f}, {cx - R:.0f} {cy:.0f}" '
                f'data-from="{p}" data-to="{nid}" />')

        classes = ["node", f"kind-{kind}"]
        color = KIND_COLOR[kind]
        badge = ""
        # 분석 다음: 문제정의(define)·실패·성공·대기.
        #   define(문제정의) = 루트든 분석 다음이든 하나. 앞으로 새 가지를 뻗는다(백트래킹 없음).
        #   success = 산 잎 (끝).
        #   fail    = 죽은 잎 + 백트래킹 파선(조상 문제정의로 되돌아감).
        #   pending = 사람에게 묻는 중. 아직 미결정 — 잎도 분기도 아니다(파선 테두리).
        if kind == "pending":
            classes.append("result-pending")
        elif kind == "success":
            classes.append("result-success"); live.append(nid)
        elif kind == "fail":
            classes.append("result-fail"); dead.append(nid)
            # 실패만이 백트래킹과 연결된다 (파선으로 조상 문제정의 복귀).
            bt = n.get("backtrack")
            if bt and bt in by_id:
                tx, ty = node_xy(bt, col, depth)
                sx, sy = cx, cy - R
                dx, dy = tx, ty - R
                arch = min(sy, dy) - 42
                bt_edges.append(
                    f'<path class="edge-backtrack" marker-end="url(#bt-arrow)" '
                    f'd="M {sx:.0f} {sy:.0f} C {sx:.0f} {arch:.0f}, {dx:.0f} {arch:.0f}, '
                    f'{dx:.0f} {dy:.0f}" data-from="{nid}" data-to="{bt}" />')

        # 원 안엔 아무 것도 안 넣고(작은 원), 이름(kind 라벨)을 원 아래에 — 사이클 DAG처럼.
        # clickable + data-body: 클릭하면 그 스텝의 본문 카드가 아래에 펼쳐진다(C007 패턴).
        label = KIND_LABEL.get(kind, kind)
        classes.append("clickable")
        node_svg.append(
            f'<g class="{" ".join(classes)}" data-id="{nid}" data-kind="{kind}" '
            f'data-outcome="{outcome or ""}" data-body="body-{nid}" '
            f'tabindex="0" role="button" aria-label="스텝 {nid} 본문 열기">'
            f'<circle class="n-hit" cx="{cx:.0f}" cy="{cy:.0f}" r="{R + 8}" '
            f'fill="transparent" />'
            f'<circle class="n-circle" cx="{cx:.0f}" cy="{cy:.0f}" r="{R}" '
            f'fill="{color}" stroke="{color}" />'
            f'<text class="n-name" x="{cx:.0f}" y="{cy + R + 16:.0f}" '
            f'text-anchor="middle">{label}</text>'
            f'<text class="n-sub" x="{cx:.0f}" y="{cy + R + 31:.0f}" '
            f'text-anchor="middle">{nid}</text>'
            f'{badge}</g>')

    # 범례 — 스텝 종류 + 결과 잎 + 엣지
    order = ["define", "hypothesis", "verify", "analyze",
             "fail", "success", "pending"]
    legend = "".join(
        f'<span class="lg"><span class="sw" style="background:{KIND_COLOR[k]};'
        f'border-color:{KIND_COLOR[k]}"></span>{KIND_LABEL[k]}</span>'
        for k in order)
    legend += ('<span class="lg"><svg width="34" height="10"><line x1="0" y1="5" x2="34" y2="5" '
               'stroke="#94a3b8" stroke-width="2"/></svg>스텝 실선</span>'
               '<span class="lg"><svg width="34" height="10"><line x1="0" y1="5" x2="34" y2="5" '
               'stroke="#f59e0b" stroke-width="2" stroke-dasharray="6 5"/></svg>되돌아감 파선</span>')

    svg = (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
           f'xmlns="http://www.w3.org/2000/svg">'
           '<defs><marker id="bt-arrow" viewBox="0 0 10 10" refX="8" refY="5" '
           'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
           '<path d="M0 0 L10 5 L0 10 z" fill="#f59e0b"/></marker></defs>'
           + "".join(region_svg)  # 리본은 맨 뒤(엣지·노드 아래)
           + "".join(p_edges) + "".join(bt_edges) + "".join(node_svg) + '</svg>')

    # 본문 카드 — 각 스텝의 md를 인라인 임베드(fetch 없음, 자기완결). 기본 hidden.
    panels = []
    for n in nodes:
        nid, kind = n["id"], n["kind"]
        raw = bodies.get(nid, "(본문 없음)")
        panels.append(
            f'<article class="stepbody" id="body-{nid}" hidden>'
            f'<div class="sb-head"><span class="sb-dot" style="background:{KIND_COLOR[kind]}">'
            f'</span><span class="sb-name">{html.escape(KIND_LABEL.get(kind, kind))}</span>'
            f'<span class="sb-id">{nid}</span>'
            f'<button class="sb-close" type="button" data-close="body-{nid}" '
            f'aria-label="닫기">✕</button></div>'
            f'<pre class="sb-body">{html.escape(raw)}</pre></article>')
    bodies_section = (
        '<div class="bodies"><div class="bodies-title">스텝 본문 '
        '<span class="bodies-hint">(위 노드를 클릭하면 그 스텝 본문만 여기 펼쳐진다)'
        '</span></div>' + "".join(panels) + '</div>')

    return (f'<!doctype html><meta charset="utf-8"><style>{CSS}{INTERACT_CSS}</style>'
            f'<div class="head"><h1>v3 스텝 트리 — 원형 노드 (사이클 DAG 시각 언어 통일)</h1>'
            f'<div class="meta">chain: <b>{chain}</b> · cycle: <b>{cycle}</b> · '
            f'노드 {len(nodes)} · 산 잎 {len(live)} · 죽은 잎 {len(dead)}</div></div>'
            f'<div class="legend">{legend}</div><div class="wrap">{svg}</div>'
            f'{bodies_section}'
            f'<div class="head"><div class="meta">v3-view/C001 목업 · Clew · 자기완결</div></div>'
            f'<script>{JS}</script>')


INTERACT_CSS = """
.node.clickable{cursor:pointer}
.node.clickable:hover .n-circle{stroke:#0f172a;stroke-width:3}
.node.open .n-circle{stroke:#0f172a;stroke-width:3.5}
.bodies{padding:8px 24px 40px;max-width:820px}
.bodies-title{font-size:14px;font-weight:700;margin:6px 0 10px}
.bodies-hint{font-weight:400;color:#94a3b8;font-size:12px}
.stepbody{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px;margin:8px 0}
@media (prefers-color-scheme:dark){.stepbody{background:#111a2e;border-color:#1e293b}}
.stepbody[hidden]{display:none}
.sb-head{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.sb-dot{width:11px;height:11px;border-radius:50%;display:inline-block}
.sb-name{font-weight:700;font-size:13px}
.sb-id{color:#94a3b8;font-size:11px}
.sb-close{margin-left:auto;border:none;background:transparent;cursor:pointer;color:#94a3b8;font-size:14px}
.sb-body{white-space:pre-wrap;font:12.5px/1.55 -apple-system,BlinkMacSystemFont,sans-serif;margin:0;color:#334155}
@media (prefers-color-scheme:dark){.sb-body{color:#cbd5e1}}
"""

# 노드 클릭 → 그 스텝 본문만 보인다. 다른 열린 본문은 닫는다(한 번에 하나, 상현님).
JS = """
(function(){
  function closeAll(){
    document.querySelectorAll('.stepbody').forEach(function(p){ p.setAttribute('hidden',''); });
    document.querySelectorAll('.node.clickable.open').forEach(function(g){ g.classList.remove('open'); });
  }
  function toggle(g){
    var id=g.getAttribute('data-body'), p=document.getElementById(id);
    if(!p) return;
    var wasOpen = !p.hasAttribute('hidden');
    closeAll();                         // 먼저 전부 닫고
    if(!wasOpen){                       // 닫혀 있던 걸 클릭했으면 그것만 연다
      p.removeAttribute('hidden'); g.classList.add('open'); p.scrollIntoView({block:'nearest'});
    }                                   // 이미 열린 걸 다시 클릭하면 닫힌 채로 (토글)
  }
  document.querySelectorAll('.node.clickable').forEach(function(g){
    g.addEventListener('click', function(){ toggle(g); });
    g.addEventListener('keydown', function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggle(g); } });
  });
  document.querySelectorAll('.sb-close').forEach(function(b){
    b.addEventListener('click', function(){
      var id=b.getAttribute('data-close'), p=document.getElementById(id);
      if(p) p.setAttribute('hidden','');
      var g=document.querySelector('.node.clickable[data-body="'+id+'"]');
      if(g) g.classList.remove('open');
    });
  });
})();
"""


def _load_bodies(nodes, steps_dir):
    """steps/<id>.md 본문을 읽어 {id: text}. 없으면 건너뜀."""
    out = {}
    for n in nodes:
        p = os.path.join(steps_dir, n["id"] + ".md")
        if os.path.exists(p):
            out[n["id"]] = open(p, encoding="utf-8").read()
    return out


def html_from_yaml_text(text, chain="v3-view", cycle="case-c012-c014", bodies=None):
    return render_html(parse_steps_yaml(text), chain, cycle, bodies)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(os.path.join(
        HERE, "..", "..", "..", "v3-build", "C002-design-v3-data-model",
        "3-verification", "case-c012-c014", "steps.yaml"))
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "out.html")
    nodes = parse_steps_yaml(open(src, encoding="utf-8").read())
    steps_dir = os.path.join(os.path.dirname(os.path.abspath(src)), "steps")
    bodies = _load_bodies(nodes, steps_dir)
    doc = render_html(nodes, bodies=bodies)
    open(dst, "w", encoding="utf-8").write(doc)
    print(f"wrote {dst} ({len(doc)} bytes, 본문 {len(bodies)}개)")
