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


DATA_DIR = "gil-viewer.data"  # 사이드 번들 — 스텝 본문·이미지 (지연 로딩)

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


_TR_SEP = "\x1f"
_REC_SEP = "\x1e"
# 커밋 인덱스에 담을 트레일러 키 (chains_from_graph가 쓰는 것들).
_IDX_KEYS = ["Gil-Chain", "Gil-Kind", "Gil-Mode", "Gil-Cycle-Parent", "Gil-Merge"]


def commit_index():
    """단일 `git log --branches`로 모든 커밋의 subject·주요 트레일러를 인덱스한다.

    brancheswise sha별 `git log -1` 반복(62초 벽, gil-v3-study/c002/s4)을 없앤다.
    반환: {sha9: {subject, chain, kind, mode, cycle_parents[], merges[]}}.
    한 줄에 담기지 않는 멀티값(Cycle-Parent·Merge)은 %x00 구분.
    """
    parts = ["%H", "%s"]
    for k in _IDX_KEYS[:3]:  # 단일값
        parts.append(f"%(trailers:key={k},valueonly)")
    for k in _IDX_KEYS[3:]:  # 멀티값
        parts.append(f"%(trailers:key={k},valueonly,separator=%x00)")
    fmt = _TR_SEP.join(parts) + _REC_SEP
    out = _git("log", "--branches", "--format=" + fmt)
    idx = {}
    for rec in out.split(_REC_SEP):
        rec = rec.strip("\n")
        if not rec:
            continue
        f = rec.split(_TR_SEP)
        if len(f) < 7:
            continue
        idx[f[0][:9]] = {
            "subject": f[1],
            "chain": f[2].strip() or None,
            "kind": f[3].strip() or None,
            "mode": f[4].strip() or None,
            "cycle_parents": [x for x in f[5].split("\x00") if x.strip()],
            "merges": [x for x in f[6].split("\x00") if x.strip()],
        }
    return idx


def _branch_shas(br):
    """한 브랜치의 커밋 sha(9자) 리스트 — sha만 뽑는 가벼운 단일 호출."""
    return [s[:9] for s in _git("log", "--format=%H", br).split()]


def chains_from_graph():
    """커밋 그래프에서 체인 단위로 집계.

    반환: {chain: {parent, mode, status, kind, cycles(수), subject}}.
    체인 = Gil-Kind가 init 또는 chain-root인 커밋으로 선언된다. 부모는 그 커밋의
    Gil-Cycle-Parent(체인을 가리킴). 상태는 chain-close 커밋 존재로 판정.
    """
    idx = commit_index()  # 단일 git log — 브랜치×sha별 fork 제거 (c002/s5)
    all_nodes = gil.collect_nodes("--branches")  # 사이클 집계용, 역시 단일 log
    chains = {}
    for br in _branches():
        shas = _branch_shas(br)  # sha만 (가벼운 단일 호출)
        root = None
        closed = False
        head = idx.get(shas[0]) if shas else None
        # chain_name = 브랜치 HEAD의 Gil-Chain (이 브랜치가 대표하는 체인)
        chain_name = head["chain"] if head else None
        for sha in shas:
            info = idx.get(sha)
            if not info:
                continue
            kind = info["kind"]
            ch = info["chain"]
            # 이 체인 루트만 (조상 체인의 root 배제)
            if kind in ("init", "chain-root") and ch == chain_name and root is None:
                # 부모 체인: Gil-Cycle-Parent 여러 줄 = 체인 머지(닫힌 체인들 합류).
                parents = info["cycle_parents"] or info["merges"]
                root = {"parents": parents,
                        "mode": info["mode"] or "autonomous",
                        "kind": kind, "subject": info["subject"]}
            # chain-close는 이 체인 이름의 것만 센다(조상 체인의 close 배제).
            if kind == "chain-close" and ch == chain_name:
                closed = True
        if not chain_name or not root:
            continue
        br_shas = set(shas)
        cyc = {n["cycle"] for n in all_nodes
               if n["chain"] == chain_name and n["cycle"] and n["sha"] in br_shas}
        status = "init" if root["kind"] == "init" else (
            "closed" if closed else "open")
        chains[chain_name] = {
            "parents": root["parents"], "mode": root["mode"],
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


import re as _re


def md_to_html(text):
    """작은 마크다운 → HTML (stdlib만). 제목·리스트·코드펜스·굵게·인라인코드·문단."""
    if not text.strip():
        return '<p class="md-empty">(본문 없음 — 이 스텝은 제목만)</p>'
    def inline(s):
        # 이미지 ![alt](url) — data URI 포함. escape 전에 뽑아 placeholder로 보호.
        imgs = []
        def _img(m):
            imgs.append((m.group(1), m.group(2)))
            return f"\x00IMG{len(imgs)-1}\x00"
        s = _re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _img, s)
        s = html.escape(s)
        s = _re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = _re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        for idx, (alt, url) in enumerate(imgs):
            tag = (f'<img class="md-img" src="{html.escape(url, quote=True)}" '
                   f'alt="{html.escape(alt, quote=True)}">')
            s = s.replace(f"\x00IMG{idx}\x00", tag)
        return s
    out, i = [], 0
    lines = text.split("\n")
    while i < len(lines):
        ln = lines[i]
        # 단독 이미지 라인 (긴 data URI 등) — 문단으로 감싸지 않고 그대로
        mi = _re.match(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$", ln)
        if mi:
            out.append(f'<p class="md-imgline">{inline(ln.strip())}</p>')
            i += 1
            continue
        if ln.startswith("```"):  # 코드펜스
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(html.escape(lines[i])); i += 1
            i += 1
            out.append('<pre class="md-code"><code>' + "\n".join(code) + "</code></pre>")
            continue
        m = _re.match(r"^(#{1,6})\s+(.*)", ln)
        if m:
            lv = len(m.group(1))
            out.append(f'<h{lv} class="md-h">{inline(m.group(2))}</h{lv}>')
            i += 1
            continue
        if _re.match(r"^\s*[-*]\s+", ln):  # 리스트
            items = []
            while i < len(lines) and _re.match(r"^\s*[-*]\s+", lines[i]):
                items.append("<li>" + inline(_re.sub(r"^\s*[-*]\s+", "", lines[i])) + "</li>")
                i += 1
            out.append("<ul class='md-ul'>" + "".join(items) + "</ul>")
            continue
        if ln.strip() == "":
            i += 1
            continue
        # 문단 (연속 비어있지 않은 줄)
        para = []
        while i < len(lines) and lines[i].strip() != "" \
                and not lines[i].startswith(("#", "```")) \
                and not _re.match(r"^\s*[-*]\s+", lines[i]):
            para.append(lines[i]); i += 1
        out.append("<p class='md-p'>" + inline(" ".join(para)) + "</p>")
    return "".join(out)


def render_step_body_page(chain, cid, sid, kind, sha, body_idx=None):
    """한 스텝 본문의 자기완결 HTML 페이지 (사이드 번들 파일). 이미지 data URI 포함.

    이 파일 하나가 자기완결 — 뷰어 iframe이 클릭 시 로드한다. 메인 HTML엔 안 들어가
    뷰어 단독 크기를 지킨다(상현님 교훈).
    """
    detail = md_to_html(gil.step_body(sha, body_idx))
    color = KIND_COLOR.get(kind, "#64748b")
    return f"""<!doctype html><meta charset="utf-8"><style>
:root{{color-scheme:light dark}}
body{{margin:0;padding:14px 16px;font:13px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#fff;color:#334155}}
@media(prefers-color-scheme:dark){{body{{background:#0b1120;color:#cbd5e1}}}}
.md-h{{font-weight:700;margin:12px 0 6px;line-height:1.3}}
h1.md-h{{font-size:17px}} h2.md-h{{font-size:15px}} h3.md-h{{font-size:14px}}
.md-p{{margin:6px 0}} .md-ul{{margin:6px 0;padding-left:20px}} .md-ul li{{margin:2px 0}}
.md-code{{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:6px;padding:8px 10px;
  overflow-x:auto;font-size:12px;font-family:ui-monospace,monospace}}
@media(prefers-color-scheme:dark){{.md-code{{background:#111a2e;border-color:#1e293b}}}}
code{{background:#f1f5f9;border-radius:4px;padding:0 4px;font-size:12px;font-family:ui-monospace,monospace}}
@media(prefers-color-scheme:dark){{code{{background:#111a2e}}}}
.md-img{{max-width:100%;height:auto;border:1px solid #e2e8f0;border-radius:8px;margin:8px 0;display:block}}
.md-empty{{color:#94a3b8;font-style:italic}}
</style><div class="sb-md">{detail}</div>"""


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
        # 스텝 머지 — 두 번째(+) 조상. 산 잎에서 이 노드로 실선(두 조상 상속).
        for mstep in s.get("merges", []):
            if mstep in pos:
                px, py = pos[mstep]
                m = (px + cx) / 2
                edges.append(f'<path class="edge merge-edge" d="M {px+R:.0f} {py:.0f} '
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
        bid = f"stepbody-{chain}-{cid}-{sid}"
        nodes.append(
            f'<g class="node kind-{kind} clickable" data-body="{bid}" tabindex="0" '
            f'role="button"><circle cx="{cx:.0f}" cy="{cy:.0f}" r="{R}" '
            f'fill="{color}" stroke="{color}"/>'
            f'<text class="nm" x="{cx:.0f}" y="{cy+R+15:.0f}" text-anchor="middle">'
            f'{KIND_LABEL.get(kind, kind)}</text>'
            f'<text class="sub" x="{cx:.0f}" y="{cy+R+29:.0f}" text-anchor="middle">'
            f'{html.escape(sid)}</text><title>{html.escape(sid)} · {kind}</title></g>')
    svg = (f'<svg width="{mx}" height="{my}" viewBox="0 0 {mx} {my}" '
           f'xmlns="http://www.w3.org/2000/svg">'
           + "".join(edges) + "".join(nodes) + "</svg>")
    # 각 스텝의 본문 카드 — 지연 로딩(상현님 교훈: 뷰어 HTML 단독 크기 방지).
    # 본문·이미지는 메인 HTML에 인라인하지 않고 사이드 번들(DATA_DIR/<...>.html)로 분리.
    # 클릭 시에만 iframe이 그 파일을 로드(loading=lazy). 번들 전체가 자기완결.
    cards = []
    for s in steps:
        sid = s["step"]
        bid = f"stepbody-{chain}-{cid}-{sid}"
        color = KIND_COLOR.get(s["kind"], "#64748b")
        src = f"{DATA_DIR}/{chain}-{cid}-{sid}.html"
        cards.append(
            f'<article class="stepbody" id="{bid}" hidden>'
            f'<div class="sb-head"><span class="sb-dot" style="background:{color}"></span>'
            f'<b>{html.escape(sid)}</b> · {KIND_LABEL.get(s["kind"], s["kind"])} '
            f'<span class="sb-sha">{html.escape(s["sha"])}</span>'
            f'<button class="sb-close" data-close="{bid}">✕</button></div>'
            f'<iframe class="sb-frame" data-src="{html.escape(src, quote=True)}" '
            f'loading="lazy"></iframe></article>')
    return svg + "".join(cards)


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
        # 첫 부모 = 일반 실선. 둘째+ 부모 = 머지 엣지(초록 굵게, 두 조상 상속 — 상현님
        # 역순 머지 둘째 층: 닫힌 산 사이클들이 합류). 스텝 머지와 일관된 시각.
        for i, p in enumerate(c["parents"]):
            if p in pos:
                px, py = pos[p]
                m = (px + cx) / 2
                cls = "edge" if i == 0 else "edge merge-edge"
                edges.append(f'<path class="{cls}" d="M {px+R:.0f} {py:.0f} '
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
        ps = [p for p in chains.get(c, {}).get("parents", []) if p in chains]
        depth[c] = 0 if not ps else 1 + max(d(p) for p in ps)
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


def render_graph_inner():
    """그래프 본문 조각만 (head 메타·legend·wrap·layer2·드릴다운).

    셸(<!doctype>·<style>·<script>)을 뺀 순수 갱신 대상. 정적 render()도, 실시간
    --live도 이 조각을 공유한다. --live는 그래프가 자랄 때 이 조각만 다시 만들어
    SSE로 밀어넣고, 브라우저는 #graph-root.innerHTML을 이걸로 교체한다.

    반환: (inner_html, ok). 체인 없으면 ("<p>체인 없음</p>", False).
    """
    chains = chains_from_graph()
    if not chains:
        return "<p class='empty'>체인 없음</p>", False
    pos = layout(chains)
    max_x = max(x for x, y in pos.values()) + R + 120
    max_y = max(y for x, y in pos.values()) + R + 60
    edges, nodes = [], []
    for c, info in chains.items():
        cx, cy = pos[c]
        # 첫 부모=실선, 둘째+=머지 엣지(초록 굵게 — 체인 머지: 닫힌 체인들 합류).
        # 역순 머지 셋째 층. 스텝·사이클 머지와 일관된 시각.
        for i, p in enumerate(info.get("parents", [])):
            if p in pos:
                px, py = pos[p]
                mx = (px + cx) / 2
                cls = "edge" if i == 0 else "edge merge-edge"
                edges.append(
                    f'<path class="{cls}" d="M {px+R:.0f} {py:.0f} '
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
    inner = f"""<div class="head"><h1>gil 뷰어 — 체인 층</h1>
<div class="meta">체인 {len(chains)}개 · 순수 커밋 그래프에서 읽음 (Gil-* trailer).
체인이 어떻게 이어지는지 — gil init → 개발 → … 배포 순환. <b>체인 노드를 클릭하면
그 체인 안의 사이클 DAG가 아래에 열린다.</b></div></div>
<div class="legend">{legend}<span class="lg"><svg width=34 height=10><line x1=0 y1=5 x2=34 y2=5 stroke=#94a3b8 stroke-width=2/></svg>체인 계보</span><span class="lg">🔒승인 = approval 모드</span></div>
<div class="wrap">{svg}</div>
<div class="layer2"><div class="l2h">사이클 층 <span class="dh">(체인 클릭 → 그 안의 사이클 트리)</span></div>
<div class="cyc-legend">{cyc_legend}</div>
{"".join(drills)}
<div class="drill-empty" id="drill-empty">위 체인 노드를 클릭하면 그 체인의 사이클 DAG가 여기 펼쳐집니다.</div></div>"""
    return inner, True


def render():
    """정적 자기완결 문서 (file://로 열림). 그래프 조각을 셸로 감싼다."""
    inner, ok = render_graph_inner()
    if not ok:
        return "<!doctype html><meta charset=utf-8><p>체인 없음</p>"
    return f"""<!doctype html><meta charset="utf-8"><style>{CSS}</style>
<div id="graph-root">{inner}</div>
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
.merge-edge{stroke:#16a34a;stroke-width:2.4}
.steptree{border:1px solid #e2e8f0;border-radius:10px;margin:8px 0;overflow:hidden;
  background:#f8fafc}
@media(prefers-color-scheme:dark){.steptree{border-color:#1e293b;background:#0d1526}}
.steptree[hidden]{display:none}
.kind-success circle{stroke-width:3}
.kind-fail circle{stroke-width:2}
.kind-fail .nm{fill:#dc2626}
.kind-success .nm{fill:#16a34a}
.kind-pending circle{fill-opacity:.35;stroke-dasharray:3 3}
.stepbody{background:#fff;border:1px solid #e2e8f0;border-radius:10px;margin:8px 14px;
  padding:12px 14px;max-width:760px}
@media(prefers-color-scheme:dark){.stepbody{background:#0b1120;border-color:#1e293b}}
.stepbody[hidden]{display:none}
.sb-head{display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:8px}
.sb-dot{width:11px;height:11px;border-radius:50%;display:inline-block}
.sb-sha{color:#94a3b8;font-size:11px;font-family:ui-monospace,monospace}
.sb-close{margin-left:auto;border:none;background:transparent;cursor:pointer;
  color:#94a3b8;font-size:15px}
.sb-md{font-size:13px;line-height:1.6;color:#334155}
@media(prefers-color-scheme:dark){.sb-md{color:#cbd5e1}}
.sb-frame{width:100%;min-height:120px;border:0;display:block;background:transparent}
.md-h{font-weight:700;margin:12px 0 6px;line-height:1.3}
h1.md-h{font-size:17px} h2.md-h{font-size:15px} h3.md-h{font-size:14px}
.md-p{margin:6px 0} .md-ul{margin:6px 0;padding-left:20px} .md-ul li{margin:2px 0}
.md-code{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:6px;padding:8px 10px;
  overflow-x:auto;font-size:12px;font-family:ui-monospace,monospace}
@media(prefers-color-scheme:dark){.md-code{background:#111a2e;border-color:#1e293b}}
.sb-md code{background:#f1f5f9;border-radius:4px;padding:0 4px;font-size:12px;
  font-family:ui-monospace,monospace}
@media(prefers-color-scheme:dark){.sb-md code{background:#111a2e}}
.md-empty{color:#94a3b8;font-style:italic}
.md-img{max-width:100%;height:auto;border:1px solid #e2e8f0;border-radius:8px;margin:8px 0;display:block}
@media(prefers-color-scheme:dark){.md-img{border-color:#1e293b}}
.md-imgline{margin:8px 0}
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
  // 스텝 노드(data-body) 클릭 → 본문 카드 토글. iframe은 지연 로드(클릭 시 data-src→src).
  function fitFrame(fr){
    try{ var d=fr.contentDocument;
      if(d) fr.style.height=(d.body.scrollHeight+24)+'px';
    }catch(e){}
  }
  function body(g){
    var id=g.getAttribute('data-body'); if(!id) return;
    var s=document.getElementById(id); if(!s) return;
    var scope=g.closest('.steptree')||document;
    var was=!s.hasAttribute('hidden');
    scope.querySelectorAll('.stepbody').forEach(function(x){x.setAttribute('hidden','');});
    scope.querySelectorAll('.node.open').forEach(function(n){n.classList.remove('open');});
    if(!was){ s.removeAttribute('hidden'); g.classList.add('open');
      var fr=s.querySelector('.sb-frame');
      if(fr && !fr.src && fr.getAttribute('data-src')){   // 지연 로드: 클릭 때 처음 로드
        fr.addEventListener('load', function(){fitFrame(fr);});
        fr.src=fr.getAttribute('data-src');
      } else if(fr){ fitFrame(fr); }
      s.scrollIntoView({block:'nearest',behavior:'smooth'}); }
  }
  // 리스너 바인딩을 함수로 — 실시간 innerHTML 교체 후 다시 부를 수 있게(idempotent).
  function bind(root){
    root=root||document;
    root.querySelectorAll('.node.clickable').forEach(function(g){
      if(g._gilBound) return; g._gilBound=true;
      var isBody=g.hasAttribute('data-body');
      g.addEventListener('click', function(){ isBody?body(g):drill(g); });
      g.addEventListener('keydown', function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault(); isBody?body(g):drill(g);}});
    });
    root.querySelectorAll('.dc').forEach(function(b){
      if(b._gilBound) return; b._gilBound=true;
      b.addEventListener('click', function(){
        var s=document.getElementById(b.getAttribute('data-close'));
        if(s) s.setAttribute('hidden','');
        var e=document.getElementById('drill-empty');
        if(e && s && s.classList.contains('drill')) e.style.display='';
      });
    });
    root.querySelectorAll('.sb-close').forEach(function(b){
      if(b._gilBound) return; b._gilBound=true;
      b.addEventListener('click', function(){
        var s=document.getElementById(b.getAttribute('data-close'));
        if(s){ s.setAttribute('hidden',''); }
      });
    });
  }
  bind(document);

  // ── 실시간(--live): SSE로 그래프 조각을 받아 #graph-root 교체 + 상태 보존 ──
  // 서버가 그래프 셸에 window.__GIL_LIVE__=true를 심으면 구독한다. 정적 file://은 미구독.
  if(window.__GIL_LIVE__){
    var root=document.getElementById('graph-root');
    function openIds(){  // 현재 열려 있는 드릴다운·본문 카드 id 집합 (상태 보존용)
      var ids=[];
      document.querySelectorAll('.drill:not([hidden]),.steptree:not([hidden]),.stepbody:not([hidden])')
        .forEach(function(x){ if(x.id) ids.push(x.id); });
      return ids;
    }
    function restore(ids){  // 교체 후 같은 id를 다시 연다(데이터만 갈고 열림 보존)
      ids.forEach(function(id){
        var s=document.getElementById(id); if(!s) return;
        s.removeAttribute('hidden');
        var e=document.getElementById('drill-empty');
        if(e && s.classList.contains('drill')) e.style.display='none';
        // 사이드 iframe은 지연 로드였으니 다시 열릴 때 로드 트리거
        var fr=s.querySelector&&s.querySelector('.sb-frame');
        if(fr && !fr.src && fr.getAttribute('data-src')) fr.src=fr.getAttribute('data-src');
      });
    }
    var es=new EventSource('/events');
    es.addEventListener('graph', function(ev){
      if(!root) return;
      var keep=openIds();
      root.innerHTML=ev.data;   // 그래프 조각 교체(데이터만 갈림)
      bind(root);               // 새 노드에 리스너 재바인딩
      restore(keep);            // 열려 있던 것 복원
    });
    es.onerror=function(){ /* EventSource가 자동 재연결(서버 재시작 견딤) */ };
  }
})();
"""


def _write_step_pages(ddir):
    """모든 스텝 본문을 ddir에 자기완결 HTML로 쓴다. 반환: 쓴 페이지 수.

    단일 collect_nodes("--branches") + 단일 body_index로 굽는다 — 브랜치×스텝별
    git fork(62초 벽, c002/s4)를 없앤 빠른 경로(c002/s5). (chain,cycle,step) dedup.
    """
    os.makedirs(ddir, exist_ok=True)
    body_idx = gil.body_index("--branches")
    seen, count = set(), 0
    for n in gil.collect_nodes("--branches"):
        if not (n["chain"] and n["cycle"] and n["step"]):
            continue
        key = (n["chain"], n["cycle"], n["step"])
        if key in seen:
            continue
        seen.add(key)
        page = render_step_body_page(n["chain"], n["cycle"], n["step"],
                                     n["kind"], n["sha"], body_idx)
        fp = os.path.join(ddir, f'{n["chain"]}-{n["cycle"]}-{n["step"]}.html')
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(page)
        count += 1
    return count


def write_bundle(dst):
    """메인 HTML(그래프만, 가벼움) + 사이드 번들(스텝 본문 파일들, 지연 로드) 생성.

    dst 옆에 DATA_DIR/ 디렉토리를 만들고 각 스텝 본문을 자기완결 HTML로 쓴다.
    메인 HTML엔 본문·이미지가 안 들어가 뷰어 단독 크기가 작다(상현님 교훈).
    """
    doc = render()
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(doc)
    ddir = os.path.join(os.path.dirname(os.path.abspath(dst)), DATA_DIR)
    count = _write_step_pages(ddir)
    return len(doc), count


# ── 실시간 서버 (--live): stdlib만, SSE로 그래프 조각 push ──────────────────

def _graph_signature():
    """그래프 시그니처 = 모든 로컬 브랜치 팁 sha 집합. 팁이 하나라도 바뀌면(=새 스텝
    커밋) 값이 변한다. git for-each-ref 한 번 — 싸다."""
    out = _git("for-each-ref", "--format=%(objectname)", "refs/heads/")
    return "|".join(sorted(out.split()))


def _live_shell():
    """실시간 셸 문서 — 정적 render()의 셸과 같되 window.__GIL_LIVE__=true를 심어
    브라우저가 /events를 구독하게 한다. 그래프 조각은 최초 1회 인라인, 이후 SSE 교체."""
    inner, ok = render_graph_inner()
    if not ok:
        inner = "<p class='empty'>체인 없음 — gil open으로 시작하라.</p>"
    return f"""<!doctype html><meta charset="utf-8"><style>{CSS}</style>
<script>window.__GIL_LIVE__=true;</script>
<div id="graph-root">{inner}</div>
<div class="head"><div class="meta">gil web --live · Clew · 실시간(SSE) · 커밋 그래프가 자라면 자동 갱신</div></div>
<script>{JS}</script>"""


def serve_live(port=8737, interval=1.0, open_browser=True):
    """gil web --live — ThreadingHTTPServer + SSE. 커밋 그래프 변화를 브라우저에 push.

    라우트: GET / (실시간 셸) · GET /events (SSE 스트림) · GET /<data_dir>/<f> (스텝 본문).
    watcher 스레드가 interval마다 그래프 시그니처를 재보고 변하면 최신 그래프 조각을
    모든 SSE 구독자에게 flush. 외부 의존 0 (http.server·threading·queue 전부 stdlib).
    """
    import http.server
    import threading
    import queue as _queue

    subscribers = []      # 각 구독자의 Queue
    sub_lock = threading.Lock()
    ddir = os.path.join(os.getcwd(), DATA_DIR)

    def _refresh_bundle():
        """스텝 본문 사이드 번들을 현재 그래프 기준으로 다시 쓴다(/data/ 라우트가 서빙).

        단일 log+인덱스 경로(_write_step_pages)로 굽는다 — watcher가 매 변화마다 불러도
        62초가 아니라 1초 이하. 실시간성 회복(c002/s5).
        """
        try:
            _write_step_pages(ddir)
        except Exception:
            pass  # 번들 갱신 실패는 실시간 갱신을 막지 않는다

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass  # 요청 로그 침묵

        def _send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if body is not None:
                self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/" or path == "/index.html":
                self._send(200, "text/html; charset=utf-8",
                           _live_shell().encode("utf-8"))
                return
            if path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                q = _queue.Queue()
                with sub_lock:
                    subscribers.append(q)
                # 연결 즉시 현재 그래프 1회 push (첫 화면 동기화)
                inner, _ = render_graph_inner()
                q.put(inner)
                try:
                    while True:
                        data = q.get()
                        if data is None:
                            break
                        payload = "event: graph\ndata: " + \
                            data.replace("\n", "\ndata: ") + "\n\n"
                        self.wfile.write(payload.encode("utf-8"))
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    with sub_lock:
                        if q in subscribers:
                            subscribers.remove(q)
                return
            # /<DATA_DIR>/<file> — 스텝 본문 사이드 번들
            if path.startswith("/" + DATA_DIR + "/"):
                fname = os.path.basename(path)
                fp = os.path.join(ddir, fname)
                if os.path.isfile(fp):
                    with open(fp, "rb") as fh:
                        self._send(200, "text/html; charset=utf-8", fh.read())
                else:
                    self._send(404, "text/plain", b"not found")
                return
            self._send(404, "text/plain", b"not found")

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server._gil_stop = threading.Event()

    def watcher():
        last = None
        while True:
            try:
                sig = _graph_signature()
            except Exception:
                sig = last
            if sig != last:
                last = sig
                _refresh_bundle()
                inner, ok = render_graph_inner()
                if ok:
                    with sub_lock:
                        for q in list(subscribers):
                            q.put(inner)
            server._gil_stop.wait(interval)
            if server._gil_stop.is_set():
                break

    _refresh_bundle()
    t = threading.Thread(target=watcher, daemon=True)
    t.start()

    url = f"http://127.0.0.1:{port}/"
    print(f"gil web --live — {url} (Ctrl-C로 종료)")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ngil web --live 종료.")
    finally:
        server._gil_stop.set()
        with sub_lock:
            for q in list(subscribers):
                q.put(None)   # 구독자 스레드 깨워 종료
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    dst = None
    if "-o" in sys.argv:
        dst = sys.argv[sys.argv.index("-o") + 1]
    if dst:
        size, n = write_bundle(dst)
        print(f"wrote {dst} ({size} bytes) + {DATA_DIR}/ ({n} step pages)")
    else:
        sys.stdout.write(render())
