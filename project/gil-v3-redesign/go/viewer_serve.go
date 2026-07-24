// serve.go — 브라우저 관전 서버. 대상 레포(--repo)의 gil 그래프를 HTML 로 그리고
// 팁 시그니처 폴링으로 자동 새로고침. stdlib 만.
package main

import (
	"fmt"
	"html"
	"net/http"
	"os"
	"sort"
	"strings"
)

func serve(args []string) {
	port := "8790"
	for i := 0; i < len(args); i++ {
		if args[i] == "--port" && i+1 < len(args) {
			port = args[i+1]
			i++
		}
	}
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write([]byte(renderHTML(buildGraph(), false)))
	})
	http.HandleFunc("/poll", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.Write([]byte(tipSignature()))
	})
	// /step?sha=<full> — 한 스텝 커밋의 상세 보고서(제목+본문+트레일러) 원문.
	http.HandleFunc("/step", func(w http.ResponseWriter, r *http.Request) {
		sha := r.URL.Query().Get("sha")
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		if !validSHA(sha) {
			http.Error(w, "bad sha", http.StatusBadRequest)
			return
		}
		out, err := viewerGit("show", "-s", "--format=%B", sha)
		if err != nil {
			http.Error(w, "not found", http.StatusNotFound)
			return
		}
		w.Write(out)
	})
	addr := "127.0.0.1:" + port
	fmt.Println("gil 뷰어 서버 → http://" + addr + "  (관전 레포: " + viewerRepoDir + ")")
	if err := http.ListenAndServe(addr, nil); err != nil {
		fmt.Fprintln(os.Stderr, "거부: 서버 실패 —", err)
		os.Exit(1)
	}
}

func tipSignature() string {
	const fs = "\x1f"
	out, err := viewerGit("for-each-ref", "--format=%(refname:short)"+fs+"%(objectname)", "refs/heads/")
	if err != nil {
		return "err"
	}
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	sort.Strings(lines)
	return strings.Join(lines, "\n")
}

func kindClass(n viewerNode) string {
	if n.outcome == "fail" || n.outcome == "backtrack" || (n.kind == "analyze" && n.outcome != "success") {
		return "dead"
	}
	switch n.kind {
	case "analyze":
		return "alive"
	case "pending":
		return "pending"
	default:
		return "live"
	}
}

// chainLayout — 체인들을 계보 깊이로 배치한다. 뿌리(부모 없음)=depth 0, 자식은 부모+1.
// 같은 depth 는 세로로 쌓는다. 반환: 체인명→(x,y) 좌표(px).
type xy struct{ x, y int }

func chainLayout(g graphView) (map[string]xy, int, int) {
	// depth 계산(부모를 따라 올라가며). 사이클/누락 방지 위해 상한.
	depth := map[string]int{}
	var d func(c string, seen map[string]bool) int
	d = func(c string, seen map[string]bool) int {
		if v, ok := depth[c]; ok {
			return v
		}
		p := g.parents[c]
		if p == "" || seen[c] || p == c {
			depth[c] = 0
			return 0
		}
		seen[c] = true
		v := d(p, seen) + 1
		depth[c] = v
		return v
	}
	for _, ch := range g.chains {
		d(ch.name, map[string]bool{})
	}
	// depth 별 행 인덱스.
	rowAt := map[int]int{}
	pos := map[string]xy{}
	const colW, rowH, padX, padY = 210, 90, 70, 60
	maxCol, maxRow := 0, 0
	for _, ch := range g.chains { // 등장 순서 유지 → 같은 depth 안에서 안정적
		dep := depth[ch.name]
		row := rowAt[dep]
		rowAt[dep]++
		pos[ch.name] = xy{padX + dep*colW, padY + row*rowH}
		if dep > maxCol {
			maxCol = dep
		}
		if row > maxRow {
			maxRow = row
		}
	}
	w := padX*2 + maxCol*colW + 40
	h := padY*2 + maxRow*rowH + 40
	return pos, w, h
}

// renderHTML — 체인 그래프(동그라미 노드 + 계보 엣지 + 라벨). 노드 클릭 시 확장(사이클)은
// 다음 단계 — 지금은 클릭하면 그 체인이 선택 표시되고 사이클 목록을 옆 패널에 편다.
// renderHTML — 그래프를 자기완결 HTML 로. static=true 면 서버 없이 도는 정적 페이지
// (폴링 비활성 + 스텝 본문 인라인 — Pages 등 정적 호스팅용). false 면 serve 용(폴링·본문 페치).
func renderHTML(g graphView, static bool) string {
	pos, w, h := chainLayout(g)
	hc := g.hereChains()

	var edges, nodes strings.Builder
	// 엣지(노드 밑에 깔리게).
	for _, ch := range g.chains {
		p := g.parents[ch.name]
		if p == "" {
			continue
		}
		pp, ok := pos[p]
		if !ok {
			continue
		}
		cp := pos[ch.name]
		edges.WriteString(fmt.Sprintf(
			`<line class="edge" x1="%d" y1="%d" x2="%d" y2="%d"/>`, pp.x, pp.y, cp.x, cp.y))
	}
	// 체인 노드.
	for _, ch := range g.chains {
		c := pos[ch.name]
		cls := "cnode"
		if hc[ch.name] {
			cls += " here"
		}
		nodes.WriteString(fmt.Sprintf(
			`<g class="%s" data-chain="%s" transform="translate(%d,%d)">`+
				`<circle r="26"/><text class="cyc" dy="5">%d</text>`+
				`<text class="clabel" dy="48">%s</text></g>`,
			cls, esc(ch.name), c.x, c.y, len(ch.cycles), esc(ch.name)))
	}

	var b strings.Builder
	b.WriteString(`<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>gil 그래프 뷰어</title>
<style>` + css + `</style></head><body>
<header><h1>gil 그래프 뷰어 — 체인 그래프</h1>
<span class="meta">체인 ` + itoa(len(g.chains)) + `개 · 스텝 ` + itoa(g.nodeCount) + `개 · 현재위치 ` +
		itoa(g.tipCount) + `개 · ` + liveIndicator(static) + `</span></header>
<main>`)
	if len(g.chains) == 0 {
		b.WriteString(`<p class="empty">아직 gil 체인이 없다. 체인을 만들면 여기 노드로 나타난다.</p>`)
	} else {
		b.WriteString(`<div class="tabs"><button id="tab-chain" class="tab on">체인 그래프</button><button id="tab-map">전체 스텝맵</button></div>`)
		b.WriteString(`<div id="view-chain">`)
		b.WriteString(fmt.Sprintf(
			`<svg id="graph" viewBox="0 0 %d %d" width="%d" height="%d"><g id="edges">%s</g><g id="nodes">%s</g></svg>`,
			w, h, w, h, edges.String(), nodes.String()))
		b.WriteString(`<p class="hint">동그라미 = 체인(숫자는 사이클 수), 선 = 계보(부모→자식). 주황 = 현재위치(스텝에선 <b>▼HEAD</b> 표시). <b>노드 클릭 → 사이클 카드.</b></p>`)
		b.WriteString(`</div>`)
		b.WriteString(`<div id="view-map" hidden></div>`) // 전체 스텝맵(JS 로 DATA 에서 렌더)
		b.WriteString(`<div id="card" hidden></div>`)       // 체인 클릭 → 사이클 카드
		b.WriteString(`<div id="stepcard" hidden></div>`)   // 사이클 클릭 → 스텝 카드
		b.WriteString(`<div id="reportcard" hidden></div>`) // 스텝 클릭 → 상세 보고서
		b.WriteString(`<script id="cycledata" type="application/json">` + cycleJSON(g, static) + `</script>`)
		b.WriteString(`<script id="parentdata" type="application/json">` + parentsJSON(g) + `</script>`)
	}
	script := js
	if !static {
		script = jsPoll + js // serve 모드에만 폴링을 앞에 붙인다
	}
	b.WriteString(`</main><script>` + script + `</script></body></html>`)
	return b.String()
}

// liveIndicator — serve 모드면 폴링 상태 표시(● live), 정적 build 면 스냅샷 표시.
func liveIndicator(static bool) string {
	if static {
		return `<span class="meta">정적 스냅샷</span>`
	}
	return `<span id="live">● live</span>`
}

// nodes SVG 를 edges 뒤 별도 <g id="nodes"> 에 넣기 위해 renderHTML 의 svg 조립을
// 분리했어야 하나, 간결히: 위에서 만든 svg(엣지+노드)를 그대로 두고 expand 레이어만 추가.
// (실제로는 위 Sprintf 의 두 번째 %s 를 비우고 nodes 를 edges 와 함께 첫 %s 에 넣는다.)

// cycleJSON — 체인별 사이클 데이터를 JS 로 넘긴다(추가 요청 없이 클릭 확장용).
// 각 체인의 노드 좌표도 함께 실어 확장 패널을 그 자리에 띄운다.
// static=true 면 각 노드에 "body"(스텝 커밋 본문)를 임베드 — 서버 /step 페치 없이 보고서를
// 바로 렌더한다. serve(static=false)면 본문은 클릭 시 /step 으로 페치(HTML 을 가볍게 유지).
func cycleJSON(g graphView, static bool) string {
	pos, _, _ := chainLayout(g)
	var sb strings.Builder
	sb.WriteString("{")
	for i, ch := range g.chains {
		if i > 0 {
			sb.WriteString(",")
		}
		c := pos[ch.name]
		sb.WriteString(fmt.Sprintf(`%q:{"x":%d,"y":%d,"cycles":[`, ch.name, c.x, c.y))
		for j, cy := range ch.cycles {
			if j > 0 {
				sb.WriteString(",")
			}
			here := false
			for _, n := range cy.steps {
				if _, ok := g.here[posKey(n)]; ok {
					here = true
				}
			}
			if _, ok := g.hereCyc[ch.name+"/"+cy.name]; ok {
				here = true // HEAD 가 이 사이클(스텝 팁 아닌 close 등)
			}
			sb.WriteString(fmt.Sprintf(`{"name":%q,"steps":%d,"status":%q,"here":%t,"nodes":[`,
				cy.name, len(cy.steps), cy.status(), here))
			for k, n := range cy.steps {
				if k > 0 {
					sb.WriteString(",")
				}
				_, nhere := g.here[posKey(n)]
				sb.WriteString(fmt.Sprintf(
					`{"id":%q,"kind":%q,"outcome":%q,"parent":%q,"backtrack":%q,"here":%t,"sha":%q,"subj":%q`,
					n.step, n.kind, n.outcome, n.parent, n.backtrack, nhere, n.full, n.subject))
				if static {
					sb.WriteString(fmt.Sprintf(`,"body":%q`, n.body)) // 정적: 본문 인라인
				}
				sb.WriteString("}")
			}
			sb.WriteString("]}")
		}
		sb.WriteString("]}")
	}
	sb.WriteString("}")
	return sb.String()
}

// parentsJSON — 체인 계보(자식→부모)를 JS 로 넘긴다. 사이클 첫 스텝(define)을 열 때
// "이 체인이 무엇을 이어받았는지"(들어오는 계보)를 보고서 카드에 보이려고.
func parentsJSON(g graphView) string {
	var sb strings.Builder
	sb.WriteString("{")
	first := true
	for child, par := range g.parents {
		if par == "" {
			continue
		}
		if !first {
			sb.WriteString(",")
		}
		first = false
		sb.WriteString(fmt.Sprintf("%q:%q", child, par))
	}
	sb.WriteString("}")
	return sb.String()
}

func esc(s string) string { return html.EscapeString(s) }

// validSHA — git 인자 주입 방지: 16진수 7~40자만 허용.
func validSHA(s string) bool {
	if len(s) < 7 || len(s) > 40 {
		return false
	}
	for _, c := range s {
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
			return false
		}
	}
	return true
}

const css = `
:root{--bg:#0f1115;--fg:#e6e6e6;--dim:#8a94a6;--card:#171a21;--line:#39414f;
--node:#5aa9ff;--here:#ffb454;--edge:#4a5568}
@media(prefers-color-scheme:light){:root{--bg:#f7f8fa;--fg:#1a1d23;--dim:#5b6472;
--card:#fff;--line:#cdd4e0;--node:#2a6fd6;--here:#e08600;--edge:#b3bccb}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
padding:12px 20px;display:flex;align-items:baseline;gap:16px;z-index:9}
h1{font-size:16px;margin:0}.meta{color:var(--dim);font-size:12px}
#live{color:#3ddc84}#live.stale{color:var(--dim)}
main{padding:8px 20px 40px}.empty{color:var(--dim)}
.hint{color:var(--dim);font-size:12px;margin-top:10px}
svg#graph{display:block;max-width:100%;height:auto}
/* 엣지 */
.edge{stroke:var(--edge);stroke-width:2}
/* 체인 노드 */
.cnode{cursor:pointer}
.cnode circle{fill:var(--card);stroke:var(--node);stroke-width:2.5;transition:.15s}
.cnode:hover circle{fill:var(--node);fill-opacity:.15}
.cnode text{fill:var(--fg);text-anchor:middle;font-family:inherit;pointer-events:none}
.cnode .cyc{font-size:16px;font-weight:700;fill:var(--node)}
.cnode .clabel{font-size:12px;fill:var(--dim)}
.cnode.here circle{stroke:var(--here);stroke-width:3.5}
.cnode.here .cyc{fill:var(--here)}
.cnode.here .clabel{fill:var(--here);font-weight:700}
.cnode.sel circle{fill:var(--node);fill-opacity:.22}
/* 클릭 시 뜨는 HTML 카드 (둥근 모서리 사각형) — SVG 밖이라 안 잘림 */
#card{margin:16px 0 0;background:var(--card);border:1px solid var(--node);border-radius:14px;
 box-shadow:0 8px 24px rgba(0,0,0,.28);max-width:100%;overflow:hidden}
.card-head{display:flex;align-items:center;justify-content:space-between;
 padding:12px 16px;border-bottom:1px solid var(--line)}
.card-title{font-weight:700;font-size:14px}
.card-close{background:none;border:none;color:var(--dim);font:inherit;font-size:15px;cursor:pointer;padding:2px 6px}
.card-close:hover{color:var(--fg)}
.cygraph-wrap{padding:12px 16px;overflow-x:auto}
svg.cygraph{display:block}
.cyedge{stroke:var(--edge);stroke-width:2}
.cynode circle{fill:var(--card);stroke:var(--dim);stroke-width:2}
.cynode text{fill:var(--fg);text-anchor:middle;font-family:inherit;pointer-events:none}
.cynode .cystep{font-size:13px;font-weight:700}
.cynode .cyname{font-size:11px;fill:var(--dim)}
.cynode.success circle{stroke:#3ddc84}
.cynode.success .cystep{fill:#3ddc84}
.cynode.dead circle{stroke:#ff6b6b}
.cynode.dead .cystep{fill:#ff6b6b}
.cynode.pending circle{stroke:#ffd166}
.cynode.open circle{stroke:var(--node);stroke-dasharray:4 3}
.cynode.here circle{stroke:var(--here);stroke-width:3}
.cynode{cursor:pointer}
.cynode.sel circle{fill:var(--node);fill-opacity:.18}
/* 스텝 카드 (사이클 클릭 → 스텝 그래프) */
#stepcard{margin:12px 0 0;background:var(--card);border:1px solid var(--dim);border-radius:14px;
 box-shadow:0 8px 24px rgba(0,0,0,.28);max-width:100%;overflow:hidden}
.stepedge{stroke:var(--edge);stroke-width:2}
.btedge{stroke:#ff6b6b;stroke-width:1.6;stroke-dasharray:4 3;fill:none;opacity:.8}
.snode circle{fill:var(--card);stroke:var(--dim);stroke-width:2}
.snode text{fill:var(--fg);text-anchor:middle;font-family:inherit;pointer-events:none}
.snode .sid{font-size:12px;font-weight:700}
.snode .skind{font-size:10px;fill:var(--dim)}
.snode.live circle{stroke:var(--node)}
.snode.alive circle{stroke:#3ddc84}.snode.alive .sid{fill:#3ddc84}
.snode.dead circle{stroke:#ff6b6b}.snode.dead .sid{fill:#ff6b6b}
.snode.pending circle{stroke:#ffd166}.snode.pending .sid{fill:#ffd166}
.snode.here circle{stroke:var(--here);stroke-width:3}
.snode .headlbl{text-anchor:middle;font-size:10px;font-weight:800;fill:var(--here);letter-spacing:.5px}
.snode .headarrow{fill:var(--here)}
.snode{cursor:pointer}
.snode.sel circle{fill:var(--node);fill-opacity:.18}
/* 종결 노드 (analyze/pending 잎의 결말: 성공/실패·기각/대기) */
.tnode circle{stroke-width:2}
.tnode .tsym{text-anchor:middle;font-size:14px;font-weight:700;pointer-events:none}
.termedge{stroke-width:2}
.t-success circle{fill:#3ddc84;stroke:#3ddc84}.t-success .tsym{fill:#08351d}
.t-success.termedge{stroke:#3ddc84}
.t-dead circle{fill:#ff6b6b;stroke:#ff6b6b}.t-dead .tsym{fill:#3a0d0d}
.t-dead.termedge{stroke:#ff6b6b;stroke-dasharray:4 3}
.t-pending circle{fill:#ffd166;stroke:#ffd166}.t-pending .tsym{fill:#3a2e05}
.t-pending.termedge{stroke:#ffd166}
/* 상세 보고서 카드 (스텝 클릭) */
#reportcard{margin:12px 0 0;background:var(--card);border:1px solid var(--dim);border-radius:14px;
 box-shadow:0 8px 24px rgba(0,0,0,.28);max-width:100%;overflow:hidden}
.rmeta{display:flex;flex-wrap:wrap;gap:6px;padding:10px 16px 0}
.badge{font-size:11px;border:1px solid var(--line);border-radius:5px;padding:1px 7px;color:var(--dim)}
.badge.k-live{border-color:var(--node);color:var(--node)}
.badge.k-alive{border-color:#3ddc84;color:#3ddc84}
.badge.k-dead{border-color:#ff6b6b;color:#ff6b6b}
.badge.k-pending{border-color:#ffd166;color:#ffd166}
.badge.k-here{border-color:var(--here);color:var(--here);font-weight:700}
.lineage{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:10px 16px 0;padding:8px 12px;background:var(--bg);border:1px solid var(--line);border-radius:8px;font-size:11px}
.lineage .lgroup{display:inline-flex;flex-wrap:wrap;gap:4px}
.lchip{font-size:11px;border:1px solid var(--line);border-radius:5px;padding:1px 7px;color:var(--fg);background:var(--card);font-family:inherit}
.lchip.lhead{border:none;background:none;color:var(--dim);font-weight:700;padding:1px 2px}
.lchip.lself{font-weight:700;border-width:2px}
button.lchip{cursor:pointer}
button.lchip:hover{border-color:var(--node);color:var(--node)}
.lchip.lin{border-color:var(--node)}
.lchip.lout{border-color:#3ddc84}
.lchip.lbranch{border-color:#ff6b6b;border-style:dashed}
.lchip.lchain{border-color:var(--here);color:var(--here);background:none}
.lchip.ldim{border:none;background:none;color:var(--dim)}
.tabs{display:flex;gap:4px;margin:0 0 12px}
.tab{font-size:13px;padding:5px 14px;border:1px solid var(--line);border-radius:7px;background:var(--card);color:var(--dim);cursor:pointer;font-family:inherit}
.tab.on{border-color:var(--node);color:var(--node);font-weight:700}
#view-map{display:flex;flex-direction:column;gap:16px}
.mapchain{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--card)}
.mapchain-h{font-size:14px;margin-bottom:8px}
.mapchain-h .mapdot{color:var(--node)}
.mapfrom{font-size:11px;color:var(--here)}
.mapcyc{margin:8px 0 4px;padding-left:8px;border-left:2px solid var(--line)}
.mapcyc-h{font-size:12px;color:var(--dim);margin-bottom:6px}
.mapstatus{font-size:10px;border:1px solid var(--line);border-radius:4px;padding:0 5px;margin-left:4px}
.mapstatus.s-success{border-color:#3ddc84;color:#3ddc84}
.mapstatus.s-dead{border-color:#ff6b6b;color:#ff6b6b}
.mapstatus.s-pending{border-color:#ffd166;color:#ffd166}
.mapstatus.s-open{border-color:var(--node);color:var(--node)}
.maprow{display:flex;flex-wrap:wrap;align-items:center;gap:4px}
.maparrow{color:var(--dim);font-size:12px}
.mapstep{font-size:11px;border:1px solid var(--line);border-radius:6px;padding:3px 9px;background:var(--bg);color:var(--fg);cursor:pointer;font-family:inherit}
.mapstep:hover{border-color:var(--node)}
.mapstep .mk{color:var(--dim);font-size:10px}
.mapstep.k-alive{border-color:#3ddc84}.mapstep.k-dead{border-color:#ff6b6b}.mapstep.k-pending{border-color:#ffd166}
.mapstep.here{border-color:var(--here);border-width:2px}
.mapstep .mhead{color:var(--here);font-weight:800;font-size:9px}
.report{margin:10px 16px 16px;padding:14px 16px;background:var(--bg);border:1px solid var(--line);
 border-radius:8px;font-size:13px;line-height:1.65;max-height:60vh;overflow:auto;word-break:break-word}
/* 마크다운 렌더 */
.md h1,.md h2,.md h3,.md h4{margin:.8em 0 .4em;line-height:1.3}
.md h1{font-size:1.35em}.md h2{font-size:1.2em}.md h3{font-size:1.08em}.md h4{font-size:1em}
.md p{margin:.5em 0}.md ul,.md ol{margin:.4em 0;padding-left:1.4em}.md li{margin:.15em 0}
.md code{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:0 4px;font-size:.92em}
.md pre.code{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:10px 12px;
 overflow-x:auto;font-size:12px;line-height:1.5;white-space:pre}
.md pre.code code{background:none;border:none;padding:0}
.md blockquote{margin:.5em 0;padding:.2em 0 .2em 12px;border-left:3px solid var(--line);color:var(--dim)}
.md img{max-width:100%;height:auto;border-radius:6px;margin:.4em 0;display:block;border:1px solid var(--line)}
.md a{color:var(--node)}
.md strong{color:var(--fg)}
.md table{border-collapse:collapse;margin:.6em 0;font-size:12.5px;display:block;overflow-x:auto;max-width:100%}
.md th,.md td{border:1px solid var(--line);padding:4px 10px;text-align:left}
.md th{background:var(--card);font-weight:700}
.md tbody tr:nth-child(even){background:rgba(127,127,127,.06)}
`

// jsPoll — 자동 새로고침 폴링. serve 모드에만 붙인다(정적 build 엔 서버가 없어 뺀다).
const jsPoll = `
let sig=null;
async function poll(){
  try{
    const r=await fetch('/poll',{cache:'no-store'});
    const t=await r.text();
    if(sig===null){sig=t;}
    else if(t!==sig){location.reload();}
    const l=document.getElementById('live'); if(l)l.classList.remove('stale');
  }catch(e){const l=document.getElementById('live'); if(l)l.classList.add('stale');}
}
poll();setInterval(poll,1500);
`

const js = `
const SVGNS='http://www.w3.org/2000/svg';
const DATA=JSON.parse(document.getElementById('cycledata')?.textContent||'{}');
const PARENTS=JSON.parse(document.getElementById('parentdata')?.textContent||'{}');
let openChain=null;

// 열린 카드 경로를 세션에 저장 — 폴링 리로드 후 복원해 카드가 닫히지 않게(피드백 1).
const SELKEY='gilviewer.sel';
function saveSel(sel){ try{ sel? sessionStorage.setItem(SELKEY,JSON.stringify(sel)) : sessionStorage.removeItem(SELKEY);}catch(e){} }
function loadSel(){ try{ return JSON.parse(sessionStorage.getItem(SELKEY)||'null'); }catch(e){ return null; } }

function svgEl(name,attrs,text){
  const e=document.createElementNS(SVGNS,name);
  for(const k in attrs)e.setAttribute(k,attrs[k]);
  if(text!=null)e.textContent=text;
  return e;
}
function stepNumJS(s){ const m=/^s(\d+)/.exec(s||''); return m?parseInt(m[1],10):0; }

function collapseReport(){
  const rc=document.getElementById('reportcard');
  rc.hidden=true; rc.replaceChildren();
  document.querySelectorAll('.snode.sel').forEach(x=>x.classList.remove('sel'));
}
function collapseStep(){
  const sc=document.getElementById('stepcard');
  sc.hidden=true; sc.replaceChildren();
  document.querySelectorAll('.cynode.sel').forEach(x=>x.classList.remove('sel'));
  collapseReport();
}
function collapse(){
  const card=document.getElementById('card');
  card.hidden=true; card.replaceChildren();
  document.querySelectorAll('.cnode.sel').forEach(x=>x.classList.remove('sel'));
  collapseStep();
  openChain=null;
  saveSel(null);
}

// 체인 노드 클릭 → HTML 카드가 뜨고, 그 안에 사이클 노드-엣지 그래프(작은 SVG).
// 카드는 SVG 밖 HTML 이라 잘리지 않는다.
function openCard(chain){
  const d=DATA[chain]; if(!d)return;
  const cy=d.cycles;
  const card=document.getElementById('card');
  card.replaceChildren();
  collapseStep(); // 다른 체인을 열면 이전 사이클/스텝/보고서 카드를 닫는다.

  // 헤더.
  const head=document.createElement('div');
  head.className='card-head';
  const title=document.createElement('span');
  title.className='card-title';
  title.textContent=chain+' — 사이클 '+cy.length+'개';
  const close=document.createElement('button');
  close.className='card-close'; close.textContent='✕';
  close.addEventListener('click',ev=>{ev.stopPropagation();collapse();});
  head.appendChild(title); head.appendChild(close);
  card.appendChild(head);

  // 사이클 노드-엣지 그래프(내부 SVG). 가로 배치, 순차 엣지.
  const gap=104, r=24, padX=34, padY=30;
  const w=Math.max(160, padX*2+(cy.length-1)*gap+r*2);
  const h=padY*2+r*2+18;
  const svg=svgEl('svg',{class:'cygraph',viewBox:'0 0 '+w+' '+h,width:w,height:h});
  const cx0=padX+r, cyy=padY+r;
  for(let i=0;i<cy.length;i++){
    const cx=cx0+i*gap;
    if(i>0) svg.appendChild(svgEl('line',{class:'cyedge',x1:cx0+(i-1)*gap+r,y1:cyy,x2:cx-r,y2:cyy}));
    const g=svgEl('g',{class:'cynode '+cy[i].status+(cy[i].here?' here':''),transform:'translate('+cx+','+cyy+')'});
    g.dataset.cycle=cy[i].name;
    g.appendChild(svgEl('circle',{r:r}));
    g.appendChild(svgEl('text',{class:'cystep',dy:4},cy[i].steps));
    g.appendChild(svgEl('text',{class:'cyname',dy:r+18},cy[i].name));
    g.addEventListener('click',ev=>{
      ev.stopPropagation();
      document.querySelectorAll('.cynode.sel').forEach(x=>x.classList.remove('sel'));
      g.classList.add('sel');
      saveSel({chain:chain,cycle:cy[i].name});
      openStepCard(chain,cy[i]);
    });
    svg.appendChild(g);
  }
  const wrap=document.createElement('div');
  wrap.className='cygraph-wrap'; wrap.appendChild(svg);
  card.appendChild(wrap);

  card.hidden=false;
}

// 스텝 종류별 색 클래스 (산 잎/죽은 잎 등).
function stepClass(n){
  // 종결 스텝 모델: success=산 잎, fail=죽은 잎, pending=대기. (하위호환: analyze --outcome)
  if(n.kind==='success'||(n.kind==='analyze'&&n.outcome==='success'))return 'alive';
  if(n.kind==='fail'||n.outcome==='fail'||n.outcome==='backtrack')return 'dead';
  if(n.kind==='pending')return 'pending';
  return 'live';
}

// 사이클 노드 클릭 → 그 사이클의 스텝 그래프(부모-자식 엣지 + backtrack 파선).
function openStepCard(chain,cyc){
  const sc=document.getElementById('stepcard');
  sc.replaceChildren();
  collapseReport(); // 다른 사이클을 열면 이전 스텝 보고서 카드를 닫는다.
  const steps=cyc.nodes||[];

  const head=document.createElement('div');
  head.className='card-head';
  const title=document.createElement('span');
  title.className='card-title';
  title.textContent=chain+' / '+cyc.name+' — 스텝 '+steps.length+'개';
  const close=document.createElement('button');
  close.className='card-close'; close.textContent='✕';
  close.addEventListener('click',ev=>{ev.stopPropagation();collapseStep();});
  head.appendChild(title); head.appendChild(close);
  sc.appendChild(head);

  // 스텝을 부모-자식 트리로 배치 — 형제 가지(같은 부모의 여러 자식)를 세로로 갈라
  // 진짜 분기가 보이게 한다(피드백 4). col=부모 사슬 깊이, row=DFS 분기 배정.
  const byId={}, kids={};
  steps.forEach(n=>{ byId[n.id]=n; (kids[n.parent]=kids[n.parent]||[]).push(n); });
  const col={}, row={};
  let nextRow=0;
  // 루트(parent=null 또는 없음)부터 DFS. 첫 자식은 같은 행, 둘째+ 자식은 새 행(분기).
  function place(id, depth){
    col[id]=depth;
    const cs=(kids[id]||[]).slice().sort((a,b)=>stepNumJS(a.id)-stepNumJS(b.id));
    cs.forEach((c,i)=>{
      if(i>0) nextRow++;      // 형제 가지 → 아래로 한 줄
      row[c.id]=nextRow;
      place(c.id, depth+1);
    });
  }
  // 루트 노드들(부모가 이 사이클 안에 없는 것).
  const roots=steps.filter(n=>!n.parent||n.parent==='null'||!byId[n.parent]);
  roots.forEach(rt=>{ row[rt.id]=nextRow; place(rt.id,0); });

  const colGap=96, rowGap=82, r=20, padX=30, padYtop=48, padY=30;
  let maxCol=0,maxRow=0;
  steps.forEach(n=>{ maxCol=Math.max(maxCol,col[n.id]||0); maxRow=Math.max(maxRow,row[n.id]||0); });
  const X=id=>padX+r+(col[id]||0)*colGap;
  const Y=id=>padYtop+r+(row[id]||0)*rowGap; // 위쪽 여유(backtrack 곡선이 위로 지나감)
  const w=Math.max(160, padX*2+maxCol*colGap+r*2);
  const h=padYtop+padY+maxRow*rowGap+r*2;
  const svg=svgEl('svg',{class:'cygraph',viewBox:'0 0 '+w+' '+h,width:w,height:h});
  // 엣지: 부모→자식(꺾은 선), backtrack 파선.
  steps.forEach(n=>{
    if(n.parent&&n.parent!=='null'&&byId[n.parent]){
      const x1=X(n.parent)+r,y1=Y(n.parent),x2=X(n.id)-r,y2=Y(n.id);
      const mx=(x1+x2)/2;
      svg.appendChild(svgEl('path',{class:'stepedge',fill:'none',
        d:'M '+x1+' '+y1+' C '+mx+' '+y1+' '+mx+' '+y2+' '+x2+' '+y2}));
    }
    if(n.backtrack&&byId[n.backtrack]){ // 되돌아간 목표로 빨강 파선 — 그래프 위로 지나가 글자 안 가림(피드백 2)
      svg.appendChild(svgEl('path',{class:'btedge',fill:'none',
        d:'M '+X(n.id)+' '+(Y(n.id)-r)+' Q '+((X(n.id)+X(n.backtrack))/2)+' '+(Y(n.id)-r-28)+' '+X(n.backtrack)+' '+(Y(n.backtrack)-r)}));
    }
  });
  // 종결(success/fail/pending)은 이제 진짜 스텝 노드다(gil 모델 변경) — 일반 스텝 노드와
  // 같은 스타일로 그리되, kind 로 색만 구분(피드백 1·2·3). 가상 종결 노드는 없앴다.
  steps.forEach(n=>{
    const g=svgEl('g',{class:'snode '+stepClass(n)+(n.here?' here':''),transform:'translate('+X(n.id)+','+Y(n.id)+')'});
    const t=svgEl('title',{},n.id+' '+n.kind+(n.outcome?' ='+n.outcome:'')+'\n'+n.subj);
    g.appendChild(svgEl('circle',{r:r}));
    g.appendChild(t);
    g.appendChild(svgEl('text',{class:'sid',dy:3},n.id));
    g.appendChild(svgEl('text',{class:'skind',dy:r+16},n.kind));
    if(n.here){ // 현재위치(HEAD) — 색만이 아니라 ▼HEAD 라벨+화살표로 직관화(피드백 5)
      g.appendChild(svgEl('text',{class:'headlbl',dy:-r-14},'HEAD'));
      g.appendChild(svgEl('path',{class:'headarrow',d:'M 0 '+(-r-11)+' l -5 -8 l 10 0 z'}));
    }
    g.addEventListener('click',ev=>{
      ev.stopPropagation();
      document.querySelectorAll('.snode.sel').forEach(x=>x.classList.remove('sel'));
      g.classList.add('sel');
      saveSel({chain:chain,cycle:cyc.name,step:n.id});
      openReport(chain,cyc.name,n);
    });
    svg.appendChild(g);
  });
  const wrap=document.createElement('div');
  wrap.className='cygraph-wrap'; wrap.appendChild(svg);
  sc.appendChild(wrap);
  sc.hidden=false;
}

// lineage — 이 스텝의 지식 전파를 한 줄로: (들어오는) 부모 → [이 스텝] → 자식들 (나가는).
// 부모/자식 칩은 클릭하면 그 스텝 보고서로 이동. 사이클 첫 스텝(define)이면 부모 체인을
// "이어받음"으로 표시(체인 계보 = 이전 국면의 지식 상속).
function lineage(chain,cycle,n){
  const wrap=document.createElement('div');
  wrap.className='lineage';
  const cyc=(DATA[chain]?.cycles||[]).find(c=>c.name===cycle);
  const nodes=cyc?cyc.nodes:[];
  const byId={}; nodes.forEach(x=>byId[x.id]=x);
  const jump=(sid)=>{ const t=byId[sid]; if(t) openReport(chain,cycle,t); };
  const chip=(label,cls,onclick,title)=>{
    const s=document.createElement(onclick?'button':'span');
    s.className='lchip '+(cls||''); s.textContent=label;
    if(title)s.title=title;
    if(onclick){ s.addEventListener('click',ev=>{ev.stopPropagation();onclick();}); }
    return s;
  };
  // 들어오는(부모).
  wrap.appendChild(chip('들어옴','lhead'));
  const inbox=document.createElement('span'); inbox.className='lgroup';
  const parent=(n.parent&&n.parent!=='null')?n.parent:null;
  if(parent && byId[parent]){
    inbox.appendChild(chip(parent+' '+byId[parent].kind,'lin',()=>jump(parent),'부모 스텝'));
  }else if(n.id==='s1'){
    // 사이클 첫 스텝 — 체인 계보(부모 체인)를 이어받음으로.
    const pc=PARENTS[chain];
    if(pc) inbox.appendChild(chip('체인 '+pc+' 에서 이어받음','lchain',null,'이전 국면(닫힌 부모 체인)의 대문·지식·판정을 상속'));
    else inbox.appendChild(chip('시작점(대문에서)','lchain'));
  }else{
    inbox.appendChild(chip('—','ldim'));
  }
  wrap.appendChild(inbox);
  // 이 스텝.
  wrap.appendChild(chip('→',''));
  wrap.appendChild(chip(n.id+' '+n.kind,'lself k-'+stepClass(n)));
  wrap.appendChild(chip('→',''));
  // 나가는(자식들) — 같은 사이클에서 parent===n.id 인 스텝. backtrack 형제가지 포함.
  wrap.appendChild(chip('낳음','lhead'));
  const outbox=document.createElement('span'); outbox.className='lgroup';
  const kids=nodes.filter(x=>x.parent===n.id);
  if(kids.length){
    kids.forEach(k=>outbox.appendChild(chip(k.id+' '+k.kind,'lout'+(k.parent!==prevOf(nodes,k)?' lbranch':''),()=>jump(k.id),
      k.backtrack?'되돌아온 형제 가지':'다음 스텝')));
  }else{
    outbox.appendChild(chip(n.backtrack?'죽은 잎(벽) — 여기서 끝, ⤳'+n.backtrack+' 로 되돌아감':'잎(여기서 끝)','ldim',null,
      n.backtrack?'이 가지는 여기서 죽고, 조상 define 으로 되돌아가 다른 가지를 폈다':''));
  }
  wrap.appendChild(outbox);
  return wrap;
}
// prevOf — nodes 배열에서 k 의 직전 스텝 id(선형 판정용). 없으면 ''.
function prevOf(nodes,k){ const i=nodes.indexOf(k); return i>0?nodes[i-1].id:''; }

// 스텝 노드 클릭 → 그 스텝의 상세 보고서(커밋 본문 원문)를 /step 에서 가져와 카드로.
async function openReport(chain,cycle,n){
  const rc=document.getElementById('reportcard');
  rc.replaceChildren();

  const head=document.createElement('div');
  head.className='card-head';
  const title=document.createElement('span');
  title.className='card-title';
  title.textContent=chain+' / '+cycle+' / '+n.id+' · '+n.kind+(n.outcome?' ='+n.outcome:'');
  const close=document.createElement('button');
  close.className='card-close'; close.textContent='✕';
  close.addEventListener('click',ev=>{ev.stopPropagation();collapseReport();});
  head.appendChild(title); head.appendChild(close);
  rc.appendChild(head);

  // 메타 배지.
  const meta=document.createElement('div');
  meta.className='rmeta';
  const badge=(label,cls)=>{const s=document.createElement('span');s.className='badge '+(cls||'');s.textContent=label;meta.appendChild(s);};
  badge(n.kind,'k-'+stepClass(n));
  if(n.outcome)badge('=' +n.outcome);
  if(n.here)badge('◀ 현재위치','k-here');
  rc.appendChild(meta);

  // 지식 전파 계보(피드백 3): 이 스텝이 무엇을 이어받고(들어오는) 무엇을 낳는지(나가는).
  rc.appendChild(lineage(chain,cycle,n));

  // 본문(제목+body)을 마크다운으로 렌더(피드백 6·7). /step 에서 원문을 가져온다.
  const body=document.createElement('div');
  body.className='report md';
  body.textContent='(불러오는 중…)';
  rc.appendChild(body);
  rc.hidden=false;
  // 정적 build: 본문이 노드에 인라인 임베드돼 있으면 서버 페치 없이 바로 렌더.
  if(typeof n.body==='string'){
    body.innerHTML=renderMarkdown(stripTrailers(n.body));
    return;
  }
  try{
    const res=await fetch('/step?sha='+encodeURIComponent(n.sha),{cache:'no-store'});
    if(res.ok){
      let raw=await res.text();
      raw=stripTrailers(raw); // Gil-* 트레일러 블록 제거(메타는 위 배지로 이미 보임)
      body.innerHTML=renderMarkdown(raw);
    }else{ body.textContent='(보고서를 불러오지 못했다: '+res.status+')'; }
  }catch(e){ body.textContent='(네트워크 오류: '+e+')'; }
}

// stripTrailers — 커밋 메시지 끝의 Gil-*: 트레일러 블록을 떼어낸다(마지막 문단이 트레일러면).
function stripTrailers(txt){
  const lines=txt.replace(/\s+$/,'').split('\n');
  let i=lines.length-1;
  while(i>=0 && /^[A-Z][A-Za-z-]*:\s/.test(lines[i])) i--;
  // i 는 트레일러 아닌 마지막 줄. 그 아래가 전부 트레일러면 자른다(빈 줄 포함).
  let end=lines.length;
  if(i<lines.length-1){ end=i+1; while(end>0 && lines[end-1].trim()==='') end--; }
  return lines.slice(0,end).join('\n');
}

// renderMarkdown — 외부 라이브러리 없는 최소 마크다운 → HTML(의존성 0).
// 지원: 제목·굵게·기울임·인라인코드·코드블록·이미지·링크·리스트·인용·문단.
// 이미지 ![alt](data:...혹은 url), 링크 [t](url), 리스트(- / 숫자.), 인용(>), 문단.
function mdEsc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
const BT=String.fromCharCode(96); // 백틱 — Go raw string 안에서 리터럴로 못 씀
const RE_CODE=new RegExp(BT+'([^'+BT+']+)'+BT,'g');
const RE_FENCE=new RegExp('^'+BT+BT+BT);
function mdInline(s){
  s=mdEsc(s);
  // 이미지 먼저(링크보다). data: 와 http(s): 만 허용.
  s=s.replace(/!\[([^\]]*)\]\((data:[^)]+|https?:\/\/[^)]+)\)/g,
    (m,alt,src)=>'<img alt="'+alt+'" src="'+src+'" loading="lazy">');
  s=s.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
    (m,t,u)=>'<a href="'+u+'" target="_blank" rel="noopener">'+t+'</a>');
  s=s.replace(RE_CODE,(m,c)=>'<code>'+c+'</code>');
  s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  s=s.replace(/(^|[^*])\*([^*]+)\*/g,'$1<em>$2</em>');
  // 본문에 문자 그대로 쓴 <br>·<br/> 를 실제 줄바꿈으로(이스케이프됐던 것을 복원).
  s=s.replace(/&lt;br\s*\/?&gt;/gi,'<br>');
  return s;
}
function renderMarkdown(txt){
  const lines=txt.split('\n');
  let html='', i=0, inCode=false, code='';
  let list=null; // 'ul'|'ol'|null
  const closeList=()=>{ if(list){ html+='</'+list+'>'; list=null; } };
  while(i<lines.length){
    let ln=lines[i];
    if(RE_FENCE.test(ln)){
      if(!inCode){ inCode=true; code=''; }
      else { inCode=false; closeList(); html+='<pre class="code">'+mdEsc(code)+'</pre>'; }
      i++; continue;
    }
    if(inCode){ code+=(code?'\n':'')+ln; i++; continue; }
    const h=/^(#{1,6})\s+(.*)$/.exec(ln);
    if(h){ closeList(); const lv=h[1].length; html+='<h'+lv+'>'+mdInline(h[2])+'</h'+lv+'>'; i++; continue; }
    if(/^\s*>\s?/.test(ln)){ closeList(); html+='<blockquote>'+mdInline(ln.replace(/^\s*>\s?/,''))+'</blockquote>'; i++; continue; }
    // 마크다운 표: 헤더행(| a | b |) + 구분행(|---|---|) + 데이터행들.
    const isRow=s=>/^\s*\|.*\|\s*$/.test(s);
    const isSep=s=>/^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(s) && s.indexOf('-')>=0;
    if(isRow(ln) && i+1<lines.length && isSep(lines[i+1])){
      closeList();
      const cells=s=>s.replace(/^\s*\|/,'').replace(/\|\s*$/,'').split('|').map(c=>c.trim());
      const head=cells(ln);
      let t='<table><thead><tr>'+head.map(c=>'<th>'+mdInline(c)+'</th>').join('')+'</tr></thead><tbody>';
      i+=2; // 헤더·구분 소비
      while(i<lines.length && isRow(lines[i]) && !isSep(lines[i])){
        const cs=cells(lines[i]);
        t+='<tr>'+cs.map(c=>'<td>'+mdInline(c)+'</td>').join('')+'</tr>';
        i++;
      }
      t+='</tbody></table>';
      html+=t; continue;
    }
    const ul=/^\s*[-*]\s+(.*)$/.exec(ln);
    const ol=/^\s*\d+\.\s+(.*)$/.exec(ln);
    if(ul){ if(list!=='ul'){ closeList(); html+='<ul>'; list='ul'; } html+='<li>'+mdInline(ul[1])+'</li>'; i++; continue; }
    if(ol){ if(list!=='ol'){ closeList(); html+='<ol>'; list='ol'; } html+='<li>'+mdInline(ol[1])+'</li>'; i++; continue; }
    if(ln.trim()===''){ closeList(); i++; continue; }
    // 문단: 이어지는 비어있지 않은 줄을 모은다.
    closeList();
    let para=ln;
    const BLOCK=new RegExp('^(#{1,6}\\s|'+BT+BT+BT+'|\\s*[-*]\\s|\\s*\\d+\\.\\s|\\s*>)');
    while(i+1<lines.length && lines[i+1].trim()!=='' && !BLOCK.test(lines[i+1])){
      i++; para+='<br>'+lines[i];
    }
    html+='<p>'+mdInline(para)+'</p>';
    i++;
  }
  if(inCode) html+='<pre class="code">'+mdEsc(code)+'</pre>';
  closeList();
  return html;
}

function selectChain(chain){
  const g=document.querySelector('.cnode[data-chain="'+chain+'"]');
  document.querySelectorAll('.cnode.sel').forEach(x=>x.classList.remove('sel'));
  if(g)g.classList.add('sel');
  openChain=chain;
  openCard(chain);
}

// 전체 스텝맵(피드백 4): 체인·사이클도 보이되 모든 스텝을 한 화면에 펼친다.
// DATA(이미 로드됨)만으로 렌더 — 서버 왕복 없음. 스텝 클릭 → 그 보고서 카드.
function buildStepMap(){
  const host=document.getElementById('view-map');
  host.replaceChildren();
  for(const chain of Object.keys(DATA)){
    const d=DATA[chain];
    const ch=document.createElement('section'); ch.className='mapchain';
    const pc=PARENTS[chain];
    const h=document.createElement('div'); h.className='mapchain-h';
    h.innerHTML='<span class="mapdot">●</span> 체인 <b>'+mdEsc(chain)+'</b>'+(pc?' <span class="mapfrom">← '+mdEsc(pc)+' 에서 이어받음</span>':'');
    ch.appendChild(h);
    for(const cy of d.cycles){
      const cyd=document.createElement('div'); cyd.className='mapcyc';
      const ch2=document.createElement('div'); ch2.className='mapcyc-h';
      ch2.innerHTML='◆ 사이클 <b>'+mdEsc(cy.name)+'</b> <span class="mapstatus s-'+cy.status+'">'+cy.status+'</span>';
      cyd.appendChild(ch2);
      const row=document.createElement('div'); row.className='maprow';
      (cy.nodes||[]).forEach((n,idx)=>{
        if(idx>0){ const a=document.createElement('span'); a.className='maparrow';
          a.textContent=(n.parent&&n.parent!==(cy.nodes[idx-1]?.id))?'⤴':'→'; row.appendChild(a); }
        const s=document.createElement('button');
        s.className='mapstep k-'+stepClass(n)+(n.here?' here':'');
        s.innerHTML=mdEsc(n.id)+' <span class="mk">'+mdEsc(n.kind)+'</span>'+(n.here?' <span class="mhead">◀HEAD</span>':'');
        s.title=n.subj||'';
        s.addEventListener('click',()=>{ showView('chain'); selectChain(chain);
          const cyc=DATA[chain].cycles.find(c=>c.name===cy.name);
          openStepCard(chain,cyc); openReport(chain,cy.name,n); });
        row.appendChild(s);
      });
      cyd.appendChild(row);
      ch.appendChild(cyd);
    }
    host.appendChild(ch);
  }
}
function showView(which){
  const chainOn=which==='chain';
  document.getElementById('view-chain').hidden=!chainOn;
  document.getElementById('view-map').hidden=chainOn;
  document.getElementById('tab-chain').classList.toggle('on',chainOn);
  document.getElementById('tab-map').classList.toggle('on',!chainOn);
  if(!chainOn) buildStepMap();
}

document.addEventListener('click',e=>{
  const g=e.target.closest('.cnode');
  if(!g)return;
  const chain=g.dataset.chain;
  if(openChain===chain){collapse();return;} // 다시 클릭 → 닫기
  selectChain(chain);
  saveSel({chain:chain});
});

// 폴링 리로드 후 열려 있던 카드를 복원(피드백 1) — reload를 유지하되 상태 보존.
function restoreSel(){
  const sel=loadSel();
  if(!sel||!DATA[sel.chain])return;
  selectChain(sel.chain);
  if(!sel.cycle)return;
  const cyc=DATA[sel.chain].cycles.find(c=>c.name===sel.cycle);
  if(!cyc)return;
  const cn=document.querySelector('.cynode[data-cycle="'+sel.cycle+'"]');
  if(cn)cn.classList.add('sel');
  openStepCard(sel.chain,cyc);
  if(!sel.step)return;
  const n=(cyc.nodes||[]).find(x=>x.id===sel.step);
  if(n)openReport(sel.chain,sel.cycle,n);
}
const tc=document.getElementById('tab-chain'), tm=document.getElementById('tab-map');
if(tc)tc.addEventListener('click',()=>showView('chain'));
if(tm)tm.addEventListener('click',()=>showView('map'));
restoreSel();
`
