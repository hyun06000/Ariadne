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
STEP_W = 128   # depth 한 칸당 가로 간격
LANE_H = 108   # 형제 가지 한 칸당 세로 간격
PAD_X = 70
PAD_Y = 170
R = 18  # 원 반경 (사이클 DAG처럼 작게)

KIND_COLOR = {
    "define": "#2563eb",      # 파랑 — 문제정의
    "hypothesis": "#7c3aed",  # 보라 — 가설
    "verify": "#0d9488",      # 청록 — 검증
    "analyze": "#64748b",     # 회색 — 분석
    # 결과 잎 (analyze 다음, 별도 노드) — 목업 샘플
    "fail": "#dc2626",        # 빨강 — 실패
    "success": "#16a34a",     # 초록 — 성공
    "redefine": "#f59e0b",    # 주황 — 문제정의(되돌아가 새 가지)
}
KIND_LABEL = {"fail": "실패", "success": "성공", "redefine": "문제정의",
              "define": "문제정의", "hypothesis": "가설", "verify": "검증",
              "analyze": "분석"}
RESULT_KINDS = {"fail", "success", "redefine"}


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
.result-redefine .n-name{fill:#d97706}
"""


def render_html(nodes, chain="v3-view", cycle="case-c012-c014"):
    by_id, children, root, depth = build_tree(nodes)
    col = assign_columns(children, root)
    max_col = max(col.values())
    max_depth = max(depth.values())
    # 가로 흐름: 너비는 depth가, 높이는 형제(col)가 정한다.
    width = int(PAD_X * 2 + max_depth * STEP_W + R * 2 + 60)
    height = int(PAD_Y + max_col * LANE_H + R * 2 + 40)

    p_edges, bt_edges, node_svg = [], [], []
    live, dead = [], []

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
        # 분석 다음 세 결과 노드 — 의미가 다르다:
        #   success  = 산 잎 (끝).
        #   fail     = 죽은 잎 + 백트래킹 파선(조상 문제정의로 되돌아감).
        #   redefine = 잎 아님! 새 문제정의로서 앞으로 새 가지를 뻗는 분기점(자식을 낳음).
        if kind == "success":
            classes.append("result-success"); live.append(nid)
        elif kind == "fail":
            classes.append("result-fail"); dead.append(nid)
            # 실패만이 백트래킹과 연결된다 (파선으로 조상 define 복귀).
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
        elif kind == "redefine":
            # 문제정의는 앞으로 뻗는 노드 — 백트래킹 없음. define처럼 자식(가설)을 낳는다.
            classes.append("result-redefine")

        # 원 안엔 아무 것도 안 넣고(작은 원), 이름(kind 라벨)을 원 아래에 — 사이클 DAG처럼.
        label = KIND_LABEL.get(kind, kind)
        node_svg.append(
            f'<g class="{" ".join(classes)}" data-id="{nid}" data-kind="{kind}" '
            f'data-outcome="{outcome or ""}">'
            f'<circle class="n-circle" cx="{cx:.0f}" cy="{cy:.0f}" r="{R}" '
            f'fill="{color}" stroke="{color}" />'
            f'<text class="n-name" x="{cx:.0f}" y="{cy + R + 16:.0f}" '
            f'text-anchor="middle">{label}</text>'
            f'<text class="n-sub" x="{cx:.0f}" y="{cy + R + 31:.0f}" '
            f'text-anchor="middle">{nid}</text>'
            f'{badge}</g>')

    # 범례 — 스텝 종류 + 결과 잎 + 엣지
    order = ["define", "hypothesis", "verify", "analyze", "fail", "success", "redefine"]
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
           + "".join(p_edges) + "".join(bt_edges) + "".join(node_svg) + '</svg>')

    return (f'<!doctype html><meta charset="utf-8"><style>{CSS}</style>'
            f'<div class="head"><h1>v3 스텝 트리 — 원형 노드 (사이클 DAG 시각 언어 통일)</h1>'
            f'<div class="meta">chain: <b>{chain}</b> · cycle: <b>{cycle}</b> · '
            f'노드 {len(nodes)} · 산 잎 {len(live)} · 죽은 잎 {len(dead)}</div></div>'
            f'<div class="legend">{legend}</div><div class="wrap">{svg}</div>'
            f'<div class="head"><div class="meta">v3-view/C001 목업 · Clew · 자기완결</div></div>')


def html_from_yaml_text(text, chain="v3-view", cycle="case-c012-c014"):
    return render_html(parse_steps_yaml(text), chain, cycle)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(os.path.join(
        HERE, "..", "..", "..", "v3-build", "C002-design-v3-data-model",
        "3-verification", "case-c012-c014", "steps.yaml"))
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "out.html")
    doc = html_from_yaml_text(open(src, encoding="utf-8").read())
    open(dst, "w", encoding="utf-8").write(doc)
    print(f"wrote {dst} ({len(doc)} bytes)")
