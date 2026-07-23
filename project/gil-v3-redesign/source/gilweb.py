#!/usr/bin/env python3
"""gilweb — gil 커밋 그래프를 사람 눈에 드러내는 뷰어 (자기완결 HTML).

3층(체인·사이클·스텝) 중 **가장 먼저 체인 층**을 그린다: 체인들이 어떻게 이어지는지
(gil init → dev → viewer → staging → release 순환). 체인=원형 노드, 체인 간 계보=실선.
v3-view 시각 언어(원형 노드·실선·status 색)를 순수 커밋 그래프 위에서 재현.

외부 리소스 0 — file://로 열린다.
"""
import os
import subprocess
import sys
import html

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gil  # noqa: E402


CHAIN_COLOR = {
    "open": "#7c3aed",     # 진행중(열림) — 보라
    "closed": "#16a34a",   # 닫힘(완주) — 초록
    "init": "#2563eb",     # gil init 대문 — 파랑
}
CHAIN_LABEL = {"open": "열림(진행중)", "closed": "닫힘(완주)", "init": "init(대문)"}
R = 13
COL_W, LANE_H, PAD_X, PAD_Y = 190, 96, 70, 80


def _git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True).stdout


def _branches():
    """로컬 브랜치 중 Gil-Chain 루트를 가진 것 = 체인."""
    out = _git("for-each-ref", "--format=%(refname:short)", "refs/heads/")
    return [b.strip() for b in out.splitlines() if b.strip()]


def chains_from_graph():
    """커밋 그래프에서 체인 단위로 집계.

    반환: {chain: {parent, mode, status, kind, cycles(수), subject}}.
    체인 = Gil-Kind가 init 또는 chain-root인 커밋으로 선언된다. 부모는 그 커밋의
    Gil-Cycle-Parent(체인을 가리킴). 상태는 chain-close 커밋 존재로 판정.
    """
    chains = {}
    for br in _branches():
        # 이 브랜치의 커밋들을 sha 단위로 순회 — 트레일러는 커밋별 개별 조회(멀티라인 안전).
        shas = _git("log", "--format=%H", br).split()
        root = None
        closed = False
        # chain_name = 브랜치 HEAD의 Gil-Chain (이 브랜치가 대표하는 체인)
        chain_name = _git("log", "-1", "--format=%(trailers:key=Gil-Chain,"
                          "valueonly)", br).strip() or None
        for sha in shas:
            def tr(key):
                return _git("log", "-1",
                            f"--format=%(trailers:key={key},valueonly)",
                            sha).strip()
            kind = tr("Gil-Kind")
            ch = tr("Gil-Chain")
            # 이 체인 루트만 (조상 체인의 root 배제)
            if kind in ("init", "chain-root") and ch == chain_name and root is None:
                subj = _git("log", "-1", "--format=%s", sha).strip()
                root = {"parent": tr("Gil-Cycle-Parent") or None,
                        "mode": tr("Gil-Mode") or "autonomous",
                        "kind": kind, "subject": subj}
            # chain-close는 이 체인 이름의 것만 센다(조상 체인의 close 배제).
            if kind == "chain-close" and ch == chain_name:
                closed = True
        if not chain_name or not root:
            continue
        cyc = {n["cycle"] for n in gil.collect_nodes(br)
               if n["chain"] == chain_name and n["cycle"]}
        status = "init" if root["kind"] == "init" else (
            "closed" if closed else "open")
        chains[chain_name] = {
            "parent": root["parent"], "mode": root["mode"],
            "status": status, "cycles": len(cyc), "subject": root["subject"]}
    return chains


def layout(chains):
    depth = {}

    def d(c):
        if c in depth:
            return depth[c]
        p = chains.get(c, {}).get("parent")
        depth[c] = 0 if not p or p not in chains else 1 + d(p)
        return depth[c]
    for c in chains:
        d(c)
    by_depth, pos = {}, {}
    for c in sorted(chains, key=lambda x: (depth[x], x)):
        dd = depth[c]
        lane = by_depth.get(dd, 0)
        by_depth[dd] = lane + 1
        pos[c] = (PAD_X + dd * COL_W + R, PAD_Y + lane * LANE_H + R)
    return pos


def render():
    chains = chains_from_graph()
    if not chains:
        return "<!doctype html><meta charset=utf-8><p>체인 없음</p>"
    pos = layout(chains)
    max_x = max(x for x, y in pos.values()) + R + 120
    max_y = max(y for x, y in pos.values()) + R + 60
    edges, nodes = [], []
    for c, info in chains.items():
        cx, cy = pos[c]
        p = info["parent"]
        if p and p in pos:
            px, py = pos[p]
            mx = (px + cx) / 2
            edges.append(
                f'<path class="edge" d="M {px+R:.0f} {py:.0f} '
                f'C {mx:.0f} {py:.0f}, {mx:.0f} {cy:.0f}, {cx-R:.0f} {cy:.0f}"/>')
        color = CHAIN_COLOR[info["status"]]
        mode_badge = "🔒승인" if info["mode"] == "approval" else ""
        nodes.append(
            f'<g class="node status-{info["status"]}" tabindex="0" role="button">'
            f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{R}" fill="{color}" stroke="{color}"/>'
            f'<text class="nm" x="{cx:.0f}" y="{cy+R+18:.0f}" text-anchor="middle">'
            f'{html.escape(c)}</text>'
            f'<text class="sub" x="{cx:.0f}" y="{cy+R+33:.0f}" text-anchor="middle">'
            f'사이클 {info["cycles"]} {mode_badge}</text>'
            f'<title>{html.escape(c)} · {info["status"]} · {info["mode"]}\n'
            f'{html.escape(info["subject"])}</title></g>')
    legend = "".join(
        f'<span class="lg"><span class="sw" style="background:{CHAIN_COLOR[k]}"></span>'
        f'{CHAIN_LABEL[k]}</span>' for k in ["init", "open", "closed"])
    svg = (f'<svg width="{max_x}" height="{max_y}" viewBox="0 0 {max_x} {max_y}" '
           f'xmlns="http://www.w3.org/2000/svg">'
           + "".join(edges) + "".join(nodes) + "</svg>")
    return f"""<!doctype html><meta charset="utf-8"><style>{CSS}</style>
<div class="head"><h1>gil 뷰어 — 체인 층</h1>
<div class="meta">체인 {len(chains)}개 · 순수 커밋 그래프에서 읽음 (Gil-* trailer).
체인이 어떻게 이어지는지 — gil init → 개발 → … 배포 순환. 원형 노드+실선.</div></div>
<div class="legend">{legend}<span class="lg"><svg width=34 height=10><line x1=0 y1=5 x2=34 y2=5 stroke=#94a3b8 stroke-width=2/></svg>체인 계보</span><span class="lg">🔒승인 = approval 모드</span></div>
<div class="wrap">{svg}</div>
<div class="head"><div class="meta">gil-v3-viewer/c001 · Clew · 자기완결 (외부 리소스 0)</div></div>"""


CSS = """
:root{color-scheme:light dark}
body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#fff;color:#0f172a}
@media(prefers-color-scheme:dark){body{background:#0b1120;color:#e2e8f0}}
.head{padding:20px 24px 6px}.head h1{margin:0;font-size:20px}
.meta{color:#64748b;font-size:13px;margin-top:4px}
.legend{display:flex;flex-wrap:wrap;gap:14px 20px;padding:10px 24px;margin:6px 24px;
  background:#f8fafc;border-radius:10px;font-size:12.5px}
@media(prefers-color-scheme:dark){.legend{background:#111a2e}}
.lg{display:flex;align-items:center;gap:6px}
.sw{width:16px;height:16px;border-radius:50%;display:inline-block}
.wrap{overflow-x:auto;padding:8px 24px 32px}
.edge{stroke:#94a3b8;stroke-width:1.8;fill:none}
.nm{font-size:13px;font-weight:700;fill:#334155}
.sub{font-size:10.5px;fill:#94a3b8}
@media(prefers-color-scheme:dark){.nm{fill:#cbd5e1}.sub{fill:#64748b}}
.status-closed circle{stroke-width:3}
.node:hover circle{stroke:#0f172a;stroke-width:3.5}
"""


if __name__ == "__main__":
    dst = None
    if "-o" in sys.argv:
        dst = sys.argv[sys.argv.index("-o") + 1]
    doc = render()
    if dst:
        open(dst, "w", encoding="utf-8").write(doc)
        print(f"wrote {dst} ({len(doc)} bytes)")
    else:
        sys.stdout.write(doc)
