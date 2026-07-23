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


# ── 사이클 층 (체인 안의 사이클 DAG — 드릴다운 대상) ──────────────────────

CYC_COLOR = {"solved": "#16a34a", "in_progress": "#7c3aed",
             "pending": "#e879f9", "dead": "#dc2626"}
CYC_LABEL = {"solved": "solved", "in_progress": "진행중",
             "pending": "대기", "dead": "폐기"}


def cycles_of(chain):
    """한 체인 안의 사이클들을 집계. 반환 {cid:{parents,status,steps}}."""
    cyc = {}
    for n in reversed(gil.collect_nodes(chain)):  # old→new
        if n["chain"] != chain or not n["cycle"]:
            continue
        c = cyc.setdefault(n["cycle"], {"parents": [], "steps": []})
        c["steps"].append(n)
        for p in n["cycle_parents"]:
            # 같은 체인 안 사이클 부모만(체인 참조는 루트 표시라 제외)
            if p != chain and p not in c["parents"]:
                c["parents"].append(p)
    for cid, c in cyc.items():
        ks = [(s["kind"], s["outcome"]) for s in c["steps"]]
        if any(k == "analyze" and o == "success" for k, o in ks):
            c["status"] = "solved"
        elif any(k == "analyze" and o == "fail" for k, o in ks):
            c["status"] = "dead"
        elif any(k == "pending" for k, o in ks):
            c["status"] = "pending"
        else:
            c["status"] = "in_progress"
    return cyc


# ── 스텝 층 (사이클 안의 스텝 트리 — 세 번째 드릴다운) ────────────────────

KIND_COLOR = {"define": "#2563eb", "hypothesis": "#7c3aed", "verify": "#0d9488",
              "analyze": "#64748b", "success": "#16a34a", "fail": "#dc2626",
              "pending": "#e879f9"}
KIND_LABEL = {"define": "문제정의", "hypothesis": "가설", "verify": "검증",
              "analyze": "분석", "success": "성공", "fail": "실패", "pending": "대기"}


def render_step_tree(chain, cid, steps):
    """한 사이클의 스텝 트리 SVG. parent 실선·backtrack 파선·kind 색.

    success=산 잎(초록), fail·backtrack=죽은 잎(빨강, 벽의 지도). 상현님 스텝 원칙:
    막힌 지점(backtrack)은 죽은 잎으로 그려지고, 파선이 조상 define으로 되돌아간다.
    """
    by = {s["step"]: s for s in steps}
    depth = {}

    def d(sid):
        if sid in depth:
            return depth[sid]
        p = by[sid]["parent"]
        p = p if p not in (None, "null") and p in by else None
        depth[sid] = 0 if not p else 1 + d(p)
        return depth[sid]
    for s in steps:
        d(s["step"])
    by_depth, pos = {}, {}
    SW, LH, PX, PY = 108, 74, 40, 40
    for sid in sorted(by, key=lambda x: (depth[x], int(x[1:]) if x[1:].isdigit() else 0)):
        dd = depth[sid]
        lane = by_depth.get(dd, 0)
        by_depth[dd] = lane + 1
        pos[sid] = (PX + dd * SW + R, PY + lane * LH + R)
    mx = max(x for x, y in pos.values()) + R + 40
    my = max(y for x, y in pos.values()) + R + 40
    edges, nodes = [], []
    for s in steps:
        sid = s["step"]
        cx, cy = pos[sid]
        p = s["parent"]
        if p not in (None, "null") and p in pos:
            px, py = pos[p]
            m = (px + cx) / 2
            edges.append(f'<path class="edge" d="M {px+R:.0f} {py:.0f} '
                         f'C {m:.0f} {py:.0f}, {m:.0f} {cy:.0f}, {cx-R:.0f} {cy:.0f}"/>')
        if s["outcome"] == "backtrack" and s.get("backtrack") in pos:
            tx, ty = pos[s["backtrack"]]
            arch = min(cy, ty) - 34
            edges.append(f'<path class="bt" d="M {cx:.0f} {cy-R:.0f} '
                         f'C {cx:.0f} {arch:.0f}, {tx:.0f} {arch:.0f}, {tx:.0f} {ty-R:.0f}"/>')
        kind = s["kind"]
        if kind == "analyze" and s["outcome"] == "success":
            kind = "success"
        elif kind == "analyze" and s["outcome"] in ("fail", "backtrack"):
            kind = "fail"
        color = KIND_COLOR.get(kind, "#64748b")
        nodes.append(
            f'<g class="node kind-{kind}"><circle cx="{cx:.0f}" cy="{cy:.0f}" r="{R}" '
            f'fill="{color}" stroke="{color}"/>'
            f'<text class="nm" x="{cx:.0f}" y="{cy+R+15:.0f}" text-anchor="middle">'
            f'{KIND_LABEL.get(kind, kind)}</text>'
            f'<text class="sub" x="{cx:.0f}" y="{cy+R+29:.0f}" text-anchor="middle">'
            f'{html.escape(sid)}</text><title>{html.escape(sid)} · {kind}</title></g>')
    return (f'<svg width="{mx}" height="{my}" viewBox="0 0 {mx} {my}" '
            f'xmlns="http://www.w3.org/2000/svg">'
            + "".join(edges) + "".join(nodes) + "</svg>")


def render_cycle_dag(chain):
    """한 체인의 사이클 DAG SVG + 스텝트리 드릴다운 카드. 사이클 없으면 안내."""
    cyc = cycles_of(chain)
    if not cyc:
        return '<p class="empty">이 체인엔 아직 사이클이 없다.</p>'
    depth = {}

    def d(cid):
        if cid in depth:
            return depth[cid]
        ps = [p for p in cyc[cid]["parents"] if p in cyc]
        depth[cid] = 0 if not ps else 1 + max(d(p) for p in ps)
        return depth[cid]
    for cid in cyc:
        d(cid)
    by_depth, pos = {}, {}
    CW, LH, PX, PY = 150, 84, 40, 40
    for cid in sorted(cyc, key=lambda x: (depth[x], x)):
        dd = depth[cid]
        lane = by_depth.get(dd, 0)
        by_depth[dd] = lane + 1
        pos[cid] = (PX + dd * CW + R, PY + lane * LH + R)
    mx = max(x for x, y in pos.values()) + R + 40
    my = max(y for x, y in pos.values()) + R + 40
    edges, nodes = [], []
    for cid, c in cyc.items():
        cx, cy = pos[cid]
        for p in c["parents"]:
            if p in pos:
                px, py = pos[p]
                m = (px + cx) / 2
                edges.append(f'<path class="edge" d="M {px+R:.0f} {py:.0f} '
                             f'C {m:.0f} {py:.0f}, {m:.0f} {cy:.0f}, {cx-R:.0f} {cy:.0f}"/>')
        color = CYC_COLOR[c["status"]]
        sp = cid.split("-", 1)
        stid = f"steptree-{chain}-{cid}"
        nodes.append(
            f'<g class="node status-{c["status"]} clickable" data-drill="{stid}" '
            f'tabindex="0" role="button"><circle cx="{cx:.0f}" cy="{cy:.0f}" '
            f'r="{R}" fill="{color}" stroke="{color}"/>'
            f'<text class="nm" x="{cx:.0f}" y="{cy+R+16:.0f}" text-anchor="middle">'
            f'{html.escape(sp[0])}</text>'
            f'<text class="sub" x="{cx:.0f}" y="{cy+R+30:.0f}" text-anchor="middle">'
            f'{html.escape(sp[1] if len(sp)>1 else "")} · {len(c["steps"])}스텝</text>'
            f'<title>{html.escape(cid)} · {c["status"]}</title></g>')
    svg = (f'<svg width="{mx}" height="{my}" viewBox="0 0 {mx} {my}" '
           f'xmlns="http://www.w3.org/2000/svg">'
           + "".join(edges) + "".join(nodes) + "</svg>")
    trees = []
    for cid, c in cyc.items():
        stid = f"steptree-{chain}-{cid}"
        tree = render_step_tree(chain, cid, c["steps"])
        trees.append(
            f'<section class="steptree" id="{stid}" hidden>'
            f'<div class="drill-head"><b>{html.escape(cid)}</b> 의 스텝 트리 '
            f'<span class="dh">— 사이클 안 사고 트리</span>'
            f'<button class="dc" data-close="{stid}">✕</button></div>'
            f'<div class="drill-body">{tree}</div></section>')
    return svg + "".join(trees)


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
        drill = f'data-drill="drill-{html.escape(c)}"' if info["cycles"] else ""
        clk = "clickable" if info["cycles"] else ""
        nodes.append(
            f'<g class="node status-{info["status"]} {clk}" tabindex="0" role="button" '
            f'{drill}>'
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
    # 드릴다운 카드 — 각 체인의 사이클 DAG (기본 숨김, 체인 클릭 시 열림)
    drills = []
    for c, info in chains.items():
        if not info["cycles"]:
            continue
        dag = render_cycle_dag(c)
        drills.append(
            f'<section class="drill" id="drill-{html.escape(c)}" hidden>'
            f'<div class="drill-head"><b>{html.escape(c)}</b> 의 사이클 DAG '
            f'<span class="dh">— 체인 안으로 드릴다운</span>'
            f'<button class="dc" data-close="drill-{html.escape(c)}">✕</button></div>'
            f'<div class="drill-body">{dag}</div></section>')
    cyc_legend = "".join(
        f'<span class="lg"><span class="sw" style="background:{CYC_COLOR[k]}"></span>'
        f'{CYC_LABEL[k]}</span>' for k in ["in_progress", "solved", "pending", "dead"])
    return f"""<!doctype html><meta charset="utf-8"><style>{CSS}</style>
<div class="head"><h1>gil 뷰어 — 체인 층</h1>
<div class="meta">체인 {len(chains)}개 · 순수 커밋 그래프에서 읽음 (Gil-* trailer).
체인이 어떻게 이어지는지 — gil init → 개발 → … 배포 순환. <b>체인 노드를 클릭하면
그 체인 안의 사이클 DAG가 아래에 열린다.</b></div></div>
<div class="legend">{legend}<span class="lg"><svg width=34 height=10><line x1=0 y1=5 x2=34 y2=5 stroke=#94a3b8 stroke-width=2/></svg>체인 계보</span><span class="lg">🔒승인 = approval 모드</span></div>
<div class="wrap">{svg}</div>
<div class="layer2"><div class="l2h">사이클 층 <span class="dh">(체인 클릭 → 그 안의 사이클 트리)</span></div>
<div class="cyc-legend">{cyc_legend}</div>
{"".join(drills)}
<div class="drill-empty" id="drill-empty">위 체인 노드를 클릭하면 그 체인의 사이클 DAG가 여기 펼쳐집니다.</div></div>
<div class="head"><div class="meta">gil-v3-viewer/c001 · Clew · 자기완결 (외부 리소스 0)</div></div>
<script>{JS}</script>"""


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
.status-solved circle{stroke-width:3}
.status-pending circle{fill-opacity:.35;stroke-dasharray:3 3}
.node.clickable{cursor:pointer}
.node.open circle{stroke:#0f172a;stroke-width:4}
.layer2{padding:8px 24px 24px}
.l2h{font-size:13px;font-weight:700;color:#475569;padding:8px 0 4px}
@media(prefers-color-scheme:dark){.l2h{color:#94a3b8}}
.dh{font-weight:400;color:#94a3b8}
.cyc-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:#64748b;padding:0 0 8px}
.drill{border:1px solid #e2e8f0;border-radius:12px;margin:8px 0;overflow:hidden}
@media(prefers-color-scheme:dark){.drill{border-color:#1e293b}}
.drill[hidden]{display:none}
.drill-head{display:flex;align-items:center;gap:8px;padding:10px 14px;
  border-bottom:1px solid #eef2f7;font-size:13px}
@media(prefers-color-scheme:dark){.drill-head{border-color:#1e293b}}
.dc{margin-left:auto;border:none;background:transparent;cursor:pointer;color:#94a3b8;font-size:15px}
.drill-body{overflow-x:auto;padding:8px 14px}
.drill-empty{color:#94a3b8;font-size:13px;padding:22px;text-align:center;
  border:1.5px dashed #cbd5e1;border-radius:12px;margin:8px 0}
@media(prefers-color-scheme:dark){.drill-empty{border-color:#334155}}
.empty{color:#94a3b8;font-size:13px;padding:12px}
.bt{stroke:#f59e0b;stroke-width:1.8;stroke-dasharray:6 5;fill:none}
.steptree{border:1px solid #e2e8f0;border-radius:10px;margin:8px 0;overflow:hidden;
  background:#f8fafc}
@media(prefers-color-scheme:dark){.steptree{border-color:#1e293b;background:#0d1526}}
.steptree[hidden]{display:none}
.kind-success circle{stroke-width:3}
.kind-fail circle{stroke-width:2}
.kind-fail .nm{fill:#dc2626}
.kind-success .nm{fill:#16a34a}
.kind-pending circle{fill-opacity:.35;stroke-dasharray:3 3}
"""

JS = """
(function(){
  // 두 레벨 드릴다운: 체인→사이클(.drill), 사이클→스텝(.steptree). 같은 레벨만 닫는다.
  function drill(g){
    var id=g.getAttribute('data-drill'); if(!id) return;
    var s=document.getElementById(id); if(!s) return;
    var cls=s.classList.contains('steptree')?'steptree':'drill';
    var was=!s.hasAttribute('hidden');
    document.querySelectorAll('.'+cls).forEach(function(x){x.setAttribute('hidden','');});
    (g.closest('svg')||document).querySelectorAll('.node.open')
      .forEach(function(n){n.classList.remove('open');});
    if(!was){ s.removeAttribute('hidden'); g.classList.add('open');
      var e=document.getElementById('drill-empty');
      if(e && cls==='drill') e.style.display='none';
      s.scrollIntoView({block:'nearest',behavior:'smooth'});
    }
  }
  document.querySelectorAll('.node.clickable').forEach(function(g){
    g.addEventListener('click', function(){drill(g);});
    g.addEventListener('keydown', function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();drill(g);}});
  });
  document.querySelectorAll('.dc').forEach(function(b){
    b.addEventListener('click', function(){
      var s=document.getElementById(b.getAttribute('data-close'));
      if(s) s.setAttribute('hidden','');
      var e=document.getElementById('drill-empty');
      if(e && s && s.classList.contains('drill')) e.style.display='';
    });
  });
})();
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
