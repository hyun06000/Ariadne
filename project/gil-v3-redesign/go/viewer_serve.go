// serve.go — 브라우저 관전 서버. 대상 레포(--repo)의 gil 그래프를 HTML 로 그리고
// 팁 시그니처 폴링으로 자동 새로고침. stdlib 만.
package main

import (
	"encoding/json"
	"fmt"
	"html"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// validIdent — approve/reject 인자(체인·사이클·스텝 id) 검증. 명령 주입/경로 이탈을 막는다:
// 뷰어는 자기 자신(gil)을 exec 하므로, 사용자가 못 보내는 값은 애초에 서버가 거부한다.
// gil id 문법과 같은 보수적 집합만 허용(영숫자·- · _).
func validIdent(s string) bool {
	if s == "" || len(s) > 128 {
		return false
	}
	for _, c := range s {
		if !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
			(c >= '0' && c <= '9') || c == '-' || c == '_') {
			return false
		}
	}
	return true
}

// gilExec — 뷰어가 관전 중인 저장소에서 gil 하위명령을 자식 프로세스로 돌린다. cmdApprove/
// cmdReject 는 실패 시 die(프로세스 종료)라 함수로 직접 부르면 서버가 죽는다 — 별도 프로세스로
// 격리한다. gil 바이너리는 지금 도는 자기 자신(os.Executable). --repo 대신 -C 로 실행 위치를
// 옮긴다(gil 은 cwd 의 git 을 본다).
func gilExec(args ...string) ([]byte, error) {
	self, err := os.Executable()
	if err != nil {
		return nil, err
	}
	cmd := exec.Command(self, args...)
	cmd.Dir = viewerRepoDir
	cmd.Env = append(os.Environ(), "GIL_NO_VIEWER=1") // 자식이 또 뷰어를 띄우지 않게
	hideConsole(cmd)                                  // 윈도우 콘솔 창 번쩍임 방지(결함 A)
	return cmd.CombinedOutput()
}

// assembleReference — 인터뷰 답변을 사람이 읽는 마크다운 기준 문서로 조립한다. 각 질문을
// 소제목으로, 답을 그 아래에 둔다. 체크박스(다중)는 리스트, 나머지는 문단. answer 는 문자열
// 또는 문자열 배열(JSON RawMessage) — 둘 다 처리한다.
func assembleReference(chain string, answers []struct {
	Q      string          `json:"q"`
	Type   string          `json:"type"`
	Answer json.RawMessage `json:"answer"`
}) string {
	var b strings.Builder
	b.WriteString("# 기준 문서 (레퍼런스 트루스) — " + chain + "\n\n")
	b.WriteString("이 체인의 사이클·가설·성패판정이 비추어야 할 기준. 사람과의 인터뷰로 확정됐다.\n\n")
	for i, a := range answers {
		b.WriteString("## " + itoa(i+1) + ". " + strings.TrimSpace(a.Q) + "\n\n")
		// answer 가 배열이면 리스트로, 문자열이면 문단으로.
		var arr []string
		if json.Unmarshal(a.Answer, &arr) == nil {
			if len(arr) == 0 {
				b.WriteString("_(답 없음)_\n\n")
			} else {
				for _, v := range arr {
					b.WriteString("- " + strings.TrimSpace(v) + "\n")
				}
				b.WriteString("\n")
			}
			continue
		}
		var s string
		if json.Unmarshal(a.Answer, &s) == nil {
			if strings.TrimSpace(s) == "" {
				b.WriteString("_(답 없음)_\n\n")
			} else {
				b.WriteString(strings.TrimSpace(s) + "\n\n")
			}
			continue
		}
		b.WriteString("_(답 없음)_\n\n")
	}
	return b.String()
}

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
	// /whoami — 이 뷰어가 **어느 저장소**를 보고 있는지 밝힌다(온보딩 실측).
	// 포트가 열려 있다는 것만으로 "그 뷰어가 내 저장소를 본다"고 말할 수 없다. 실제로
	// 다른 프로젝트의 뷰어가 같은 기본 포트를 쥐고 있었고, handoff 는 그 주소를 "지금
	// 열어라(선택이 아니다)"로 지시했다 — 사람은 남의 그래프를 자기 것으로 읽는다.
	http.HandleFunc("/whoami", func(w http.ResponseWriter, r *http.Request) {
		abs, err := filepath.Abs(viewerRepoDir)
		if err != nil {
			abs = viewerRepoDir
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, "{\"repo\":%q}\n", abs)
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
	// POST /approve?chain=&cycle=  ·  POST /reject?chain=&cycle=&to=
	// pending 스텝을 사람이 뷰어에서 직접 승인/기각한다(상현님). 상태를 바꾸므로 POST 만
	// 허용(GET 은 CSRF/오작동 방지). 서버는 127.0.0.1 만 바인딩하니 로컬 전용이다.
	pendingAction := func(w http.ResponseWriter, r *http.Request, kind string) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", http.StatusMethodNotAllowed)
			return
		}
		q := r.URL.Query()
		chain, cycle := q.Get("chain"), q.Get("cycle")
		if !validIdent(chain) || !validIdent(cycle) {
			http.Error(w, "bad chain/cycle", http.StatusBadRequest)
			return
		}
		ref := chain + "/" + cycle
		var out []byte
		var err error
		if kind == "approve" {
			out, err = gilExec("approve", ref)
		} else {
			to := q.Get("to")
			if !validIdent(to) {
				http.Error(w, "reject 는 --to <define> 필요", http.StatusBadRequest)
				return
			}
			out, err = gilExec("reject", ref, "--to", to)
		}
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		if err != nil {
			w.WriteHeader(http.StatusBadRequest) // gil 이 거부(pending 아님 등) — 본문에 이유
		}
		w.Write(out)
	}
	http.HandleFunc("/approve", func(w http.ResponseWriter, r *http.Request) { pendingAction(w, r, "approve") })
	http.HandleFunc("/reject", func(w http.ResponseWriter, r *http.Request) { pendingAction(w, r, "reject") })
	// POST /interview?chain=  — 사람이 인터뷰 폼을 제출한다(이슈 #33). 본문 = 답변 JSON 배열
	// [{q,type,answer}]. 서버가 이걸 마크다운 기준 문서로 조립해 reference-<chain>.md 로 저장하고,
	// gil interview <chain> --resolve <파일> 을 호출해 레퍼런스를 커밋한다. 파일은 워킹트리에
	// 남아 사람이 열어보고 편집할 수 있다. 127.0.0.1 로컬 전용.
	http.HandleFunc("/interview", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", http.StatusMethodNotAllowed)
			return
		}
		chain := r.URL.Query().Get("chain")
		if !validIdent(chain) {
			http.Error(w, "bad chain", http.StatusBadRequest)
			return
		}
		raw, err := io.ReadAll(io.LimitReader(r.Body, 1<<20)) // 1MB 상한
		if err != nil {
			http.Error(w, "read fail", http.StatusBadRequest)
			return
		}
		var answers []struct {
			Q      string          `json:"q"`
			Type   string          `json:"type"`
			Answer json.RawMessage `json:"answer"`
		}
		if err := json.Unmarshal(raw, &answers); err != nil || len(answers) == 0 {
			http.Error(w, "답변 형식 오류(JSON 배열 필요)", http.StatusBadRequest)
			return
		}
		// 답변을 마크다운 기준 문서로 조립.
		md := assembleReference(chain, answers)
		fname := "reference-" + chain + ".md"
		if err := os.WriteFile(filepath.Join(viewerRepoDir, fname), []byte(md), 0o644); err != nil {
			http.Error(w, "파일 저장 실패: "+err.Error(), http.StatusInternalServerError)
			return
		}
		out, err := gilExec("interview", chain, "--resolve", fname)
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
		}
		w.Write(out)
	})
	addr := "127.0.0.1:" + port
	url := "http://" + addr
	fmt.Println("gil 뷰어 서버가 떴다 → " + url + "   (Ctrl+C 로 종료. 관전 레포: " + viewerRepoDir + ")")
	// 포그라운드 serve 를 사람이 직접 띄웠으면 브라우저도 자동으로 연다(실사용 피드백: 날 IP
	// 주소만 보면 뭔지 몰라 넘어간다). launchViewer(자동 기동)는 부모가 이미 열므로 GIL_NO_BROWSER
	// 로 이 경로를 끈다. 서버가 실제 바인딩된 뒤 열려고 잠깐 기다렸다 연다(goroutine).
	if os.Getenv("GIL_OPEN_BROWSER") != "" {
		go func() {
			if waitPort(port, 2*time.Second) {
				if openBrowser(url) {
					fmt.Println("  브라우저로 열었다 — 사고 그래프를 본다.")
				}
			}
		}()
	}
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
	// 행(row) 배정 — 자식 체인은 부모의 row 를 물려받아 그 옆(같은 높이)에 놓는다. 그래야
	// 부모→자식 엣지가 수평으로 흐른다(상현님 관전: 예전엔 depth 별 '등장 순서' 로만 row 를
	// 매겨, 아래층 가지의 자식이 다음 depth 의 첫 체인이면 row 0(맨 위)에 배치돼 엣지가 위로
	// 꺾여 올라갔다). 물려받을 row 가 이미 그 depth 에서 찼으면 아래 빈 row 로 밀어 겹침만 피한다.
	rowChosen := map[string]int{} // 체인명 → row
	usedAtDepth := map[int]map[int]bool{}
	take := func(dep, want int) int {
		if usedAtDepth[dep] == nil {
			usedAtDepth[dep] = map[int]bool{}
		}
		r := want
		for usedAtDepth[dep][r] {
			r++
		}
		usedAtDepth[dep][r] = true
		return r
	}
	pos := map[string]xy{}
	// 간격은 **그려질 글자 크기에서** 나와야 한다(이슈 #71). 옛 상수는 라벨을 셈에 넣지
	// 않아, 라벨(dy=48)과 한 줄 아래 노드의 HEAD ▼(y-44) 가 포갰다 — 실측: "gil-v3-redesign"
	// 위로 주황 ▼ 가 얹혔다. 가로도 같다: 이름이 길면 이웃 라벨과 부딪힌다.
	// clabel 은 12px(≈7.2px/글자, 한글은 더 넓어 8px 로 잡는다), 라벨 baseline dy=48.
	longest := 0
	for _, ch := range g.chains {
		if n := len([]rune(ch.name)); n > longest {
			longest = n
		}
	}
	labelW := longest*8 + 24
	colW := labelW + 60
	if colW < 210 {
		colW = 210
	}
	const rowH, padX, padY = 118, 70, 60 // rowH: 라벨 바닥(≈52) + ▼ 높이(≈44) + 여유
	maxCol, maxRow := 0, 0
	// 부모가 먼저 row 를 얻도록 depth 오름차순으로 처리(등장 순서는 같은 depth 안 tie-break).
	order := make([]chainView, len(g.chains))
	copy(order, g.chains)
	sort.SliceStable(order, func(i, j int) bool { return depth[order[i].name] < depth[order[j].name] })
	for _, ch := range order {
		dep := depth[ch.name]
		want := 0
		if p := g.parents[ch.name]; p != "" {
			if pr, ok := rowChosen[p]; ok {
				want = pr // 부모 row 를 물려받아 수평으로
			}
		}
		row := take(dep, want)
		rowChosen[ch.name] = row
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
		head := ""
		if hc[ch.name] {
			cls += " here"
			head = `<path class="headarrow" d="M 0 -33 l -7 -11 l 14 0 z"/>` // HEAD ▼
		}
		nodes.WriteString(fmt.Sprintf(
			`<g class="%s" data-chain="%s" transform="translate(%d,%d)">`+
				`<circle r="26"/><text class="cyc" dy="5">%d</text>`+
				`<text class="clabel" dy="48">%s</text>%s</g>`,
			cls, esc(ch.name), c.x, c.y, len(ch.cycles), esc(ch.name), head))
	}

	var b strings.Builder
	b.WriteString(`<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>gil 그래프 뷰어</title>
<style>` + css + `</style></head><body>
<header><h1>gil 그래프 뷰어 — 체인 그래프</h1>
<span class="meta">체인 ` + itoa(len(g.chains)) + `개 · 스텝 ` + itoa(g.nodeCount) + `개 · 현재위치 ` +
		itoa(g.tipCount) + `개 · ` + liveIndicator(static) + workBadge(g, static) + `</span></header>
<main>`)
	// 인터뷰 폼(이슈 #33): 사람 답을 기다리는 인터뷰 요구가 있으면 최상단에 폼을 띄운다.
	// 정적 build(서버 없음)엔 제출할 곳이 없어 감춘다. JS(buildInterviews)가 질문 JSON 을 읽어
	// textarea·라디오·체크박스를 그리고, 제출 시 POST /interview 로 답변을 넘긴다.
	if !static && len(g.interviews) > 0 {
		b.WriteString(`<section class="pane" id="pane-interview"><h2 class="panehead">📋 인터뷰 — 기준 문서 만들기</h2><div id="interviews"></div></section>`)
		b.WriteString(`<script id="interviewdata" type="application/json">` + interviewsJSON(g) + `</script>`)
	}
	if len(g.chains) == 0 {
		b.WriteString(`<p class="empty">아직 gil 체인이 없다. 체인을 만들면 여기 노드로 나타난다.</p>`)
	} else {
		// 탭 없이 세로로 다 펼친다: 전체맵(맨 위) → 체인 그래프 → 사이클 → 스텝 → 디테일.
		b.WriteString(`<section class="pane"><h2 class="panehead">전체맵 <span id="depthseg" class="depthseg">` +
			`<button data-depth="chain" title="체인 단위 — 국면 계보만">체인</button>` +
			`<button data-depth="cycle" title="사이클 단위 — 각 사이클 상태·분기(⚡)">사이클</button>` +
			`<button data-depth="step" class="on" title="스텝 단위 — 모든 스텝 커밋 DAG">스텝</button>` +
			`</span></h2><div id="view-map"></div></section>`)
		b.WriteString(`<section class="pane"><h2 class="panehead">체인 그래프</h2><div id="view-chain">`)
		b.WriteString(fmt.Sprintf(
			`<svg id="graph" viewBox="0 0 %d %d" width="%d" height="%d"><g id="edges">%s</g><g id="nodes">%s</g></svg>`,
			w, h, w, h, edges.String(), nodes.String()))
		b.WriteString(`<p class="hint">동그라미 = 체인(숫자는 사이클 수), 선 = 계보(부모→자식). ▼ = 현재위치(HEAD). <b>노드 클릭 → 아래 사이클 그래프.</b></p>`)
		b.WriteString(`</div></section>`)
		b.WriteString(`<section class="pane" id="pane-card" hidden><h2 class="panehead">사이클 그래프</h2><div id="card"></div></section>`)
		b.WriteString(`<section class="pane" id="pane-step" hidden><h2 class="panehead">스텝 그래프</h2><div id="stepcard"></div></section>`)
		b.WriteString(`<section class="pane" id="pane-report" hidden><h2 class="panehead">스텝 디테일</h2><div id="reportcard"></div></section>`)
		b.WriteString(`<script id="cycledata" type="application/json">` + cycleJSON(g, static) + `</script>`)
		b.WriteString(`<script id="parentdata" type="application/json">` + parentsJSON(g) + `</script>`)
		b.WriteString(`<script id="dagdata" type="application/json">` + dagJSON(g, static) + `</script>`)
		// 작업중(미커밋)이 **어디서** 벌어지는지(#79 후속). static 스냅샷은 워킹트리와 무관하다.
		if !static {
			b.WriteString(`<script id="workdata" type="application/json">` + workJSON(g) + `</script>`)
		}
	}
	script := js
	if !static {
		script = jsPoll + js // serve 모드에만 폴링을 앞에 붙인다
	}
	// LIVE_STATIC: 정적 build(서버 없음)면 true — 승인/기각 버튼처럼 서버가 필요한 UI 를 숨긴다.
	staticFlag := "false"
	if static {
		staticFlag = "true"
	}
	b.WriteString(`</main><script>const LIVE_STATIC=` + staticFlag + `;` + script + `</script></body></html>`)
	return b.String()
}

// liveIndicator — serve 모드면 폴링 상태 표시(● live), 정적 build 면 스냅샷 표시.
func liveIndicator(static bool) string {
	if static {
		return `<span class="meta">정적 스냅샷</span>`
	}
	return `<span id="live">● live</span>`
}

// workBadge — 헤더에 미커밋 작업 요약을 단다. serve(라이브)에서만 의미 있다 —
// static build 는 워킹트리와 무관한 스냅샷이라 뺀다. serve 는 자동 새로고침이라
// 이 배지가 실시간 진행 표시가 되어 "멈춘 듯" 오해를 없앤다(상현님).
func workBadge(g graphView, static bool) string {
	if static || !g.work.dirty {
		return ""
	}
	return ` · <span class="work">✎ 작업중: ` + esc(g.work.summary()) + `</span>`
}

// nodes SVG 를 edges 뒤 별도 <g id="nodes"> 에 넣기 위해 renderHTML 의 svg 조립을
// 분리했어야 하나, 간결히: 위에서 만든 svg(엣지+노드)를 그대로 두고 expand 레이어만 추가.
// (실제로는 위 Sprintf 의 두 번째 %s 를 비우고 nodes 를 edges 와 함께 첫 %s 에 넣는다.)

// workJSON — 미커밋 작업과 그 앵커(가장 가까운 조상 스텝). 뷰어가 '작업중' 유령 노드를 그린다.
func workJSON(g graphView) string {
	if !g.work.dirty {
		return `{"dirty":false}`
	}
	a := g.anchor
	return fmt.Sprintf(`{"dirty":true,"summary":%q,"branch":%q,"sha":%q,"chain":%q,"cycle":%q,"step":%q,"ahead":%d,"files":%s}`,
		g.work.summary(), a.branch, a.sha, a.chain, a.cycle, a.step, a.ahead, jsonStrings(g.work.sample))
}

// jsonStrings — 문자열 슬라이스를 JSON 배열로(작은 헬퍼 — 의존성 0 원칙).
func jsonStrings(in []string) string {
	b, err := json.Marshal(in)
	if err != nil {
		return "[]"
	}
	return string(b)
}

// cycleJSON — 체인별 사이클 데이터를 JS 로 넘긴다(추가 요청 없이 클릭 확장용).
// 각 체인의 노드 좌표도 함께 실어 확장 패널을 그 자리에 띄운다.
// static=true 면 각 노드에 "body"(스텝 커밋 본문)를 임베드 — 서버 /step 페치 없이 보고서를
// 바로 렌더한다. serve(static=false)면 본문은 클릭 시 /step 으로 페치(HTML 을 가볍게 유지).
// cycleEntryParents — 각 사이클의 진입 부모 스텝(AIL #7). 사이클 첫 스텝(가장 낮은 s번호)의
// 커밋 부모 사슬을 거슬러, 다른 사이클/체인에 속한 가장 가까운 gil 스텝을 찾는다. 반환:
// (chain\x01cycle) → "chain/cycle/step". 위상 유도라 Gil-Cycle-Parent 선언이 없어도 잡힌다.
func cycleEntryParents(g graphView) map[string]string {
	stepBySHA := map[string]viewerNode{}
	for _, n := range g.allNodes {
		stepBySHA[n.sha] = n
	}
	nonStep := commitParentMap()
	// 각 (chain,cycle)의 첫 스텝(정의) 노드.
	first := map[string]viewerNode{}
	for _, n := range g.allNodes {
		k := n.chain + "\x01" + n.cycle
		if cur, ok := first[k]; !ok || stepNum(n.step) < stepNum(cur.step) {
			first[k] = n
		}
	}
	out := map[string]string{}
	for k, def := range first {
		// def 의 커밋 부모에서 시작해, 다른 사이클의 gil 스텝을 만날 때까지 거슬러 오른다.
		seen := map[string]bool{}
		var walk func(sha string) string
		walk = func(sha string) string {
			if seen[sha] {
				return ""
			}
			seen[sha] = true
			if s, ok := stepBySHA[sha]; ok && !(s.chain == def.chain && s.cycle == def.cycle) {
				return s.chain + "/" + s.cycle + "/" + s.step // 다른 사이클/체인의 스텝 — 진입 부모.
			}
			for _, p := range nonStep[sha] {
				if r := walk(p); r != "" {
					return r
				}
			}
			return ""
		}
		for _, p := range def.gitParents {
			if r := walk(p); r != "" {
				out[k] = r
				break
			}
		}
		// 위상으로 못 찾으면 **선언**(Gil-Cycle-Parent)에 기댄다(이슈 #72). 실사용에서 새 사이클은
		// 체인 브랜치에서 갈라져 나오는 일이 흔해, --parent 로 이어받음을 명시해도 커밋 조상관계
		// 에는 그 사실이 없다. 선언은 사람이 한 말이라 위상보다 약하지만, 없는 것보다 참이다 —
		// 위상을 먼저 보고, 없을 때만 선언을 쓴다.
		if out[k] == "" {
			for _, pc := range def.cycleParents {
				if anchor := cycleAnchorStep(g, def.chain, pc); anchor != "" {
					out[k] = anchor
					break
				}
			}
		}
	}
	return out
}

// cycleAnchorStep — 선언된 부모 사이클에서 "여기서 이어받았다"고 볼 자리. 산 잎(종결이 아닌
// 가장 큰 번호의 잎이 없으면 가장 큰 번호의 스텝)을 고른다. 반환: "chain/cycle/step".
func cycleAnchorStep(g graphView, chain, cycle string) string {
	// 선언은 "c001" 처럼 사이클 이름만 오기도 하고 "chain/cycle" 로 오기도 한다.
	if c, cy, ok := strings.Cut(cycle, "/"); ok {
		chain, cycle = c, cy
	}
	best := ""
	bestN := -1
	for _, n := range g.allNodes {
		if n.chain != chain || n.cycle != cycle {
			continue
		}
		if k := stepNum(n.step); k > bestN {
			best, bestN = n.step, k
		}
	}
	if best == "" {
		return ""
	}
	return chain + "/" + cycle + "/" + best
}

// cycleExits — 진출 경계의 **사실 근거**(이슈 #72). 어떤 스텝이 다른 사이클/체인의 진입
// 부모로 실제 지목됐을 때만 그 스텝은 "나갔다". 반환: "chain/cycle/step" → 나간 곳들.
//
// 왜 뒤집어 쓰나. 진출 고스트는 카드 안에서 자식 없는 잎을 전부 "나갔다"고 그렸다 — 아무도
// 이어받지 않은 잎에도, 심지어 잎 판정이 무너지면 모든 노드에도 붙었다. 진입 고스트는
// 처음부터 사실(위상 유도한 진입 부모)에 기댔는데 진출만 추측이었다. 같은 자료를 뒤집으면
// 추측이 사라진다: 나간 곳이 실재할 때만 선이 그려진다.
//
// 종결(success/fail) 잎에 진출이 붙지 않는 것도 여기서 따라온다 — 종결 뒤 부착은 문법으로
// 막혀 있으니(#60) 그 스텝을 진입 부모로 삼은 카드가 있을 수 없다.
func cycleExits(g graphView) map[string][]string {
	out := map[string][]string{}
	for k, parentRef := range cycleEntryParents(g) {
		chain, cycle, _ := strings.Cut(k, "\x01")
		out[parentRef] = append(out[parentRef], chain+"/"+cycle)
	}
	for _, v := range out {
		sort.Strings(v) // 결정성 — 같은 그래프면 같은 라벨
	}
	return out
}

func cycleJSON(g graphView, static bool) string {
	pos, _, _ := chainLayout(g)
	// 경계 진입 부모(AIL #7): 각 사이클의 첫 스텝이 커밋 위상상 어느 다른 사이클/체인의 스텝에서
	// 태어났나. Gil-Cycle-Parent 선언이 없어도(실사용은 위상 분기라 대개 없다) 커밋 부모 사슬로
	// 유도한다 — dagJSON 의 nearestStep 과 같은 원리. key=(chain\x01cycle) → "chain/cycle/step".
	cycleEntry := cycleEntryParents(g)
	exits := cycleExits(g) // 진출은 추측이 아니라 사실로만 그린다(이슈 #72)
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
			// 사이클 부모(경계 stub 엣지용, AIL #7): 위상 유도한 진입 부모 스텝 ref(다른 카드).
			cycPar := cycleEntry[ch.name+"\x01"+cy.name]
			// 측정의 좌표(이슈 #79·#81) — 뷰어 사이클 카드가 "어디서/무엇을" 을 함께 보인다.
			ds, sj := cycleCoordOf(ch.name, cy.name)
			sb.WriteString(fmt.Sprintf(`{"name":%q,"steps":%d,"status":%q,"here":%t,"parent":%q,"dataset":%s,"subject":%s,"nodes":[`,
				cy.name, len(cy.steps), cy.status(), here, cycPar, jsonStrings(ds), jsonStrings(sj)))
			for k, n := range cy.steps {
				if k > 0 {
					sb.WriteString(",")
				}
				_, nhere := g.here[posKey(n)]
				sb.WriteString(fmt.Sprintf(
					`{"id":%q,"kind":%q,"outcome":%q,"parent":%q,"backtrack":%q,"here":%t,"sha":%q,"inherit":%q,"subj":%q`,
					n.step, n.kind, n.outcome, n.parent, n.backtrack, nhere, n.full, n.inherit, n.subject))
				// 이 스텝을 진입 부모로 삼은 카드가 실재하면 그 목록을 싣는다 — 뷰어는 이게
				// 있는 노드에만 진출 고스트를 그린다.
				if ex := exits[ch.name+"/"+cy.name+"/"+n.step]; len(ex) > 0 {
					sb.WriteString(fmt.Sprintf(`,"exit":%q`, strings.Join(ex, ", ")))
				}
				if n.deployTag != "" { // 배포 마커(이슈 #34) — 뷰어가 🚀 + 태그 라벨로 렌더.
					sb.WriteString(fmt.Sprintf(`,"deploy":%q,"deployUrl":%q,"deployState":%q,"deployTarget":%q`,
						n.deployTag, n.deployURL, n.deployState, n.deployTarget))
				}
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

// dagJSON — 전체 스텝을 진짜 커밋 DAG(포도송이)로 넘긴다. 각 노드는 실제 커밋 부모 SHA
// 중 gil 스텝인 것만 엣지로 잇는다(init 대문 등 비-gil 부모는 제외). 사이클·체인 경계를
// 넘는 연결(예: staging/s1 의 부모가 dev chain-close 계열)도 이 커밋 부모로 그대로 살아있다.
func dagJSON(g graphView, static bool) string {
	// gil 스텝 커밋 sha 집합(엣지가 이 안의 노드로만 향하게).
	stepSHA := map[string]bool{}
	for _, n := range g.allNodes {
		stepSHA[n.sha] = true
	}
	// 비-gil 커밋(chain/open/close/chain-close/init 대문)의 부모 사슬 — 이들을 건너뛰어
	// 가장 가까운 조상 gil 스텝을 찾으려고. 사이클·체인 경계를 넘는 지식 전수(부모 사이클의
	// 종결 스텝 → 자식 사이클 첫 스텝)가 이 건너뛰기로 진짜 엣지가 된다.
	nonStepParents := commitParentMap()
	// nearestStep — sha 조상에서 가장 가까운 gil 스텝 sha 들(비-스텝은 뚫고 올라감).
	var nearestStep func(sha string, seen map[string]bool) []string
	nearestStep = func(sha string, seen map[string]bool) []string {
		if stepSHA[sha] {
			return []string{sha}
		}
		if seen[sha] {
			return nil
		}
		seen[sha] = true
		var out []string
		for _, p := range nonStepParents[sha] {
			out = append(out, nearestStep(p, seen)...)
		}
		return out
	}
	var sb strings.Builder
	sb.WriteString("[")
	for i, n := range g.allNodes {
		if i > 0 {
			sb.WriteString(",")
		}
		_, nhere := g.here[posKey(n)]
		// 부모: 커밋 부모가 gil 스텝이면 그대로, 아니면(chain/close 등) 건너뛰어 조상 스텝.
		seenP := map[string]bool{}
		var ps []string
		for _, p := range n.gitParents {
			if stepSHA[p] {
				ps = append(ps, p)
			} else {
				ps = append(ps, nearestStep(p, seenP)...)
			}
		}
		sb.WriteString(fmt.Sprintf(
			`{"sha":%q,"chain":%q,"cycle":%q,"step":%q,"kind":%q,"outcome":%q,"here":%t,"parents":[`,
			n.sha, n.chain, n.cycle, n.step, n.kind, n.outcome, nhere))
		for j, p := range ps {
			if j > 0 {
				sb.WriteString(",")
			}
			sb.WriteString(fmt.Sprintf("%q", p))
		}
		sb.WriteString(fmt.Sprintf(`],"subj":%q`, n.subject))
		if n.deployTag != "" { // 배포 마커(이슈 #34) — 전체맵 DAG 에도 🚀 표시.
			sb.WriteString(fmt.Sprintf(`,"deploy":%q,"deployUrl":%q,"deployState":%q,"deployTarget":%q`,
				n.deployTag, n.deployURL, n.deployState, n.deployTarget))
		}
		if static {
			sb.WriteString(fmt.Sprintf(`,"body":%q`, n.body))
		}
		sb.WriteString("}")
	}
	sb.WriteString("]")
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

// interviewsJSON — 사람 답 대기 인터뷰들을 JS 로 넘긴다(이슈 #33). questions 는 이미 JSON
// 배열 문자열이라, 유효하면 그대로 싣고(원본 보존), 아니면 빈 배열로 폴백한다.
func interviewsJSON(g graphView) string {
	var sb strings.Builder
	sb.WriteString("[")
	for i, iv := range g.interviews {
		if i > 0 {
			sb.WriteString(",")
		}
		q := strings.TrimSpace(iv.questions)
		if !json.Valid([]byte(q)) {
			q = "[]"
		}
		cb, _ := json.Marshal(iv.chain)
		shb, _ := json.Marshal(iv.sha)
		sb.WriteString(fmt.Sprintf(`{"chain":%s,"sha":%s,"waiting":%t,"questions":%s}`, cb, shb, iv.waiting, q))
	}
	sb.WriteString("]")
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
.work{color:#e6b800}
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
/* 배포 지점(이슈 #34) — 세상으로 나간 스텝. 🚀 + 태그, 링걸린 청록 테. */
.snode.deployed circle{stroke:#2dd4bf;stroke-width:3}
.snode .deploybadge{text-anchor:middle;font-size:11px;font-weight:800;fill:#2dd4bf}
/* staged(이슈 #56) — 배포 단위는 확정됐으나 아직 안 올라갔다. live 와 눈으로 갈린다. */
.snode .deploybadge.staged{fill:var(--dim);font-weight:600}
.dagdeploy.staged{fill:var(--dim)}
.snode.deployed.staged circle{stroke:var(--dim)}
.snode{cursor:pointer}
.snode.sel circle{fill:var(--node);fill-opacity:.18}
/* 경계 고스트 노드·stub 엣지(AIL #7) — 계보가 카드 밖으로 이어짐을 흐리게 표시(orphan 착시 제거) */
.snode.ghost circle{fill:none;stroke:var(--dim);stroke-dasharray:3 3;opacity:.55}
.snode.ghost .sid{fill:var(--dim);opacity:.7}.snode.ghost .skind{opacity:.6}
.snode.ghost{cursor:default}
.snode .inhlbl{text-anchor:middle;font-size:9px;fill:var(--node);opacity:.75}
.stepedge.ghost{stroke:var(--dim);stroke-dasharray:3 3;opacity:.5}
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
/* pending 승인/기각 액션 박스(서버 /approve·/reject) */
.pendbox{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:10px 16px 0;padding:10px 12px;
 background:var(--bg);border:1px solid #ffd166;border-radius:8px;font-size:12px}
.pendmsg{color:#ffd166;font-weight:700}
.pendbtn{font:inherit;font-size:12px;font-weight:700;padding:4px 12px;border-radius:6px;cursor:pointer;border:1px solid}
.pendbtn.approve{border-color:#3ddc84;color:#3ddc84;background:none}
.pendbtn.approve:hover:not(:disabled){background:#3ddc84;color:#08351d}
.pendbtn.reject{border-color:#ff6b6b;color:#ff6b6b;background:none}
.pendbtn.reject:hover:not(:disabled){background:#ff6b6b;color:#3a0d0d}
.pendbtn:disabled{opacity:.5;cursor:default}
.pendstatus{color:var(--dim)}
/* 인터뷰 폼(이슈 #33) — 기준 문서를 사람이 폼으로 작성 */
#pane-interview .panehead{color:var(--node)}
.ivcard{margin:4px 16px 16px;padding:16px 18px;background:var(--card,var(--bg));border:1px solid var(--node);border-radius:10px}
.ivhead{font-size:13px;color:var(--fg);margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--line)}
.ivhead b{color:var(--node)}
.ivwait{font-size:12px;color:var(--dim,#888);margin:-6px 0 12px}
.ivwait.on{color:var(--node);font-weight:600}
.ivform{display:flex;flex-direction:column;gap:16px}
.ivfield{display:flex;flex-direction:column;gap:6px}
.ivq{font-size:13px;font-weight:600;color:var(--fg)}
.ivinput{font:inherit;font-size:13px;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);resize:vertical;width:100%;box-sizing:border-box}
.ivinput:focus{outline:2px solid var(--node);outline-offset:1px;border-color:var(--node)}
.ivopts{display:flex;flex-direction:column;gap:6px;padding-left:2px}
.ivopt{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--fg);cursor:pointer}
.ivopt input{accent-color:var(--node);width:15px;height:15px;cursor:pointer}
.ivfoot{display:flex;align-items:center;gap:12px;margin-top:4px}
.ivsubmit{font:inherit;font-size:13px;font-weight:700;padding:8px 18px;border-radius:7px;cursor:pointer;border:1px solid var(--node);background:var(--node);color:var(--bg)}
.ivsubmit:hover:not(:disabled){filter:brightness(1.1)}
.ivsubmit:disabled{opacity:.5;cursor:default}
.ivstatus{color:var(--dim);font-size:12px}
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
/* 세로 스택 pane — 탭 없이 전체맵→체인→사이클→스텝→디테일 순으로 펼침 */
.pane{margin:0 0 22px}
.panehead{font-size:13px;font-weight:700;color:var(--dim);margin:0 0 8px;padding-bottom:5px;border-bottom:1px solid var(--line)}
/* 뎁스 토글 세그먼트(AIL #6) — gil log --depth 의 뷰어판. 사람이 항상 스텝맵만 강제로 보던 것을 해소. */
.depthseg{float:right;display:inline-flex;gap:0;border:1px solid var(--line);border-radius:6px;overflow:hidden;font-weight:600}
.depthseg button{font:inherit;font-size:11px;padding:2px 9px;border:0;background:var(--panel,transparent);color:var(--dim);cursor:pointer;border-left:1px solid var(--line)}
.depthseg button:first-child{border-left:0}
.depthseg button.on{background:var(--here);color:#fff}
.depthseg button:hover:not(.on){color:var(--fg)}
/* 진짜 커밋 DAG(전체 스텝맵) — 왼→오른 한 줄 흐름, 체인 이름=박스 위 라벨 */
.dagwrap{overflow-x:auto;padding:4px 0 8px}
svg.dag{display:block}
.dag .chlabel{font-size:11px;font-weight:700;fill:var(--dim)}
.dag .cyclabel{font-size:9px;fill:var(--dim);opacity:.85}
/* 전체맵 줌/팬 컨트롤 — 대형 그래프(수백 스텝) 항해용 */
.dagbar{display:flex;gap:6px;margin:0 0 6px}
.dagbar button{background:var(--card);border:1px solid var(--line);border-radius:6px;
 color:var(--fg);font:inherit;font-size:13px;min-width:28px;padding:2px 8px;cursor:pointer}
.dagbar button:hover{border-color:var(--node);color:var(--node)}
.dagbar .zhint{color:var(--dim);font-size:11px;align-self:center}
.dagwrap.grabbing{cursor:grabbing}
.dagwrap.zoomed{cursor:grab}
/* 미니맵(이슈 #79): 확대하면 어디를 보고 있는지 잃는다 — 전체 축소본 위에 지금 창을 그린다. */
.minimap{background:var(--card);border:1px solid var(--line);
  border-radius:6px;padding:3px;cursor:pointer;display:none;margin-left:auto}
.dagbar.zoomed .minimap{display:block}
.dagbar{align-items:center}
.minimap svg{display:block;max-width:none;flex:0 0 auto}
.minimap{flex:0 0 auto;line-height:0}
.dnode.working circle{fill:var(--here);fill-opacity:.18;stroke:var(--here);stroke-dasharray:3 3}
.dag .worklbl{fill:var(--here);font-size:10px;font-weight:700;text-anchor:middle}
.dedge.work{stroke:var(--here);stroke-dasharray:4 3;opacity:.9}
.minimap .mmview{fill:var(--node);fill-opacity:.18;stroke:var(--node);stroke-width:2;vector-effect:non-scaling-stroke}
.dagbar select{background:var(--card);border:1px solid var(--line);border-radius:6px;color:var(--fg);
  font:inherit;font-size:11px;padding:2px 6px}
.dag .cycbox{fill:none;stroke:var(--line);stroke-dasharray:3 3;opacity:.7}
.dag .dedge{stroke:var(--edge);stroke-width:1.5}
.dag .dedge.cross{stroke:var(--here);stroke-width:2}
.dag .dedge.branch{stroke:#ff6b6b;stroke-dasharray:4 3}
.dag .dnode{cursor:pointer}
.dag .dnode circle{fill:var(--node);stroke:var(--bg);stroke-width:1.5}
.dag .dnode.k-dead circle{fill:#ff6b6b}
.dag .dnode.k-alive.leaf circle{fill:#3ddc84}
.dag .dnode.k-pending circle{fill:#ffd166}
.dag .dnode.here circle{stroke:var(--here);stroke-width:2.5}
.dag .dnode .headarrow{fill:var(--here)}
.dag .dnode.deployed circle{stroke:#2dd4bf;stroke-width:2.5}
.dag .dnode .dagdeploy{font-size:10px;font-weight:800;fill:#2dd4bf;text-anchor:middle;pointer-events:none}
/* 집계 노드(사이클/체인 뎁스, AIL #6) — 이름 라벨 + ⚡분기 표식 */
.dag .dnode.agg .agglabel{font-size:10px;font-weight:600;fill:var(--fg);text-anchor:middle}
.dag .dnode .forkmark{font-size:9px;text-anchor:middle;pointer-events:none}
.dag .dnode:hover circle{stroke:var(--fg);stroke-width:2}
.hint .lg-branch{color:#ff6b6b}.hint .lg-dead{color:#ff6b6b}.hint .lg-alive{color:#3ddc84}.hint .lg-cross{color:var(--here)}
.headarrow{fill:var(--here)}  /* HEAD ▼ — 모든 그래프 공통 */
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
const DAG=JSON.parse(document.getElementById('dagdata')?.textContent||'[]');
// 미커밋 작업은 아직 커밋이 아니라 노드가 없다 — 그래서 커밋 전까지 "어디서 손대고 있는지"가
// 그래프 어디에도 없었다(상현님). 앵커(가장 가까운 조상 스텝) 옆에 유령 노드로 그린다.
const WORK=JSON.parse(document.getElementById('workdata')?.textContent||'{}');
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

// pane 표시/숨김 — 카드를 감싸는 섹션(헤더 포함)을 함께 토글한다.
function showPane(id,on){ const p=document.getElementById(id); if(p)p.hidden=!on; }
function collapseReport(){
  const rc=document.getElementById('reportcard');
  rc.replaceChildren(); showPane('pane-report',false);
  document.querySelectorAll('.snode.sel').forEach(x=>x.classList.remove('sel'));
}
function collapseStep(){
  const sc=document.getElementById('stepcard');
  sc.replaceChildren(); showPane('pane-step',false);
  document.querySelectorAll('.cynode.sel').forEach(x=>x.classList.remove('sel'));
  collapseReport();
}
function collapse(){
  const card=document.getElementById('card');
  card.replaceChildren(); showPane('pane-card',false);
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

  // 이 카드가 선 측정 좌표(이슈 #79·#81) — 사이클마다 다를 수 있으니 카드에 붙인다.
  const coordCy=cy.filter(c=>(c.dataset&&c.dataset.length)||(c.subject&&c.subject.length));
  if(coordCy.length){
    const box=document.createElement('div'); box.className='hint';
    box.textContent=coordCy.map(c=>c.name+': '+
      [...(c.dataset||[]).map(d=>'📐 '+d),...(c.subject||[]).map(x=>'🎯 '+x)].join(' · ')).join('  |  ');
    card.appendChild(box);
  }

  // 사이클 노드-엣지 그래프(내부 SVG). 가로 배치, 순차 엣지.
  // 간격을 이름 길이에서 뽑는다(이슈 #71) — cyname 은 12px, 한글·긴 이름이면 104px 로는
  // 이웃과 겹친다(실측: label-overlap-case-01 류가 서로 파고들었다).
  const r=24, padY=30;
  let longestCy=0; cy.forEach(c=>{ longestCy=Math.max(longestCy,(c.name||'').length); });
  const gap=Math.max(104, longestCy*8+20);
  const padX=Math.max(34, longestCy*4+10);
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
    if(cy[i].here) g.appendChild(svgEl('path',{class:'headarrow',d:'M 0 '+(-r-8)+' l -6 -9 l 12 0 z'})); // HEAD ▼
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

  showPane('pane-card',true);
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
  // 경계 stub 엣지(AIL #7): 사이클이 부모(다른 카드)에서 왔으면 왼쪽에 진입 고스트,
  // 잎(자식 없는 산/죽은 노드)에서 다음 카드로 나가면 오른쪽에 진출 고스트를 둔다 —
  // orphan 착시(뿌리 없는 가지)를 깬다. 진입 고스트엔 물려받은 전수(Gil-Inherit)를 라벨로.
  const hasEntry=!!cyc.parent;                 // 사이클 부모(Gil-Cycle-Parent)가 있으면 진입 경계.
  // 진출 경계(이슈 #72): 카드 안에서 자식이 없다는 것만으로 "나갔다"고 그리지 않는다.
  // 서버가 실은 exit(이 스텝을 진입 부모로 삼은 카드들)이 있을 때만 나간 것이다 — 아무도
  // 이어받지 않은 잎에도, 잎 판정이 무너져 모든 노드에도 붙던 거짓 표시를 사실로 대체한다.
  const exited=steps.filter(n=>n.exit);
  const gx=hasEntry?1:0;                        // 진입 고스트가 있으면 실노드를 한 칸 오른쪽으로.
  const X=id=>padX+r+(gx+(col[id]||0))*colGap;
  const Y=id=>padYtop+r+(row[id]||0)*rowGap; // 위쪽 여유(backtrack 곡선이 위로 지나감)
  const GEX=padX+r+(gx+maxCol+1)*colGap;        // 진출 고스트 X(맨 오른쪽 한 칸 밖).
  const w=Math.max(160, padX*2+(gx+maxCol+(exited.length?1:0))*colGap+r*2);
  const h=padYtop+padY+maxRow*rowGap+r*2;
  const svg=svgEl('svg',{class:'cygraph',viewBox:'0 0 '+w+' '+h,width:w,height:h});
  // 고스트 노드·stub 엣지를 실노드보다 먼저(밑에) 그린다.
  const GX=padX+r; // 진입 고스트 X(맨 왼쪽 칸).
  if(hasEntry){
    // 진입 고스트: 부모 사이클을 가리키는 흐린 노드. 각 루트로 stub 엣지.
    const inh=(steps[0]&&steps[0].inherit)||'';
    roots.forEach(rt=>{
      svg.appendChild(svgEl('path',{class:'stepedge ghost',fill:'none',
        d:'M '+(GX+r)+' '+Y(rt.id)+' C '+((GX+r+X(rt.id)-r)/2)+' '+Y(rt.id)+' '+((GX+r+X(rt.id)-r)/2)+' '+Y(rt.id)+' '+(X(rt.id)-r)+' '+Y(rt.id)}));
    });
    const gg=svgEl('g',{class:'snode ghost',transform:'translate('+GX+','+Y(roots[0].id)+')'});
    gg.appendChild(svgEl('title',{},'부모 사이클: '+cyc.parent+(inh?'\n물려받음: '+inh:'')));
    gg.appendChild(svgEl('circle',{r:r}));
    gg.appendChild(svgEl('text',{class:'sid',dy:3},'←'));
    gg.appendChild(svgEl('text',{class:'skind',dy:r+16},cyc.parent));
    if(inh){ gg.appendChild(svgEl('text',{class:'inhlbl',dy:-r-14},'⇐'+(inh.length>22?inh.slice(0,22)+'…':inh))); }
    svg.appendChild(gg);
  }
  if(exited.length){
    // 진출 고스트: **실제로 다음 카드가 이어받은** 스텝에서만 나감을 표시(흐린 노드로 수렴).
    const anchorRow=Math.round(exited.reduce((s,n)=>s+(row[n.id]||0),0)/exited.length);
    const GEY=padYtop+r+anchorRow*rowGap;
    exited.forEach(lf=>{
      svg.appendChild(svgEl('path',{class:'stepedge ghost',fill:'none',
        d:'M '+(X(lf.id)+r)+' '+Y(lf.id)+' C '+((X(lf.id)+r+GEX-r)/2)+' '+Y(lf.id)+' '+((X(lf.id)+r+GEX-r)/2)+' '+GEY+' '+(GEX-r)+' '+GEY}));
    });
    const ge=svgEl('g',{class:'snode ghost',transform:'translate('+GEX+','+GEY+')'});
    ge.appendChild(svgEl('title',{},'이어받은 곳: '+exited.map(n=>n.id+' → '+n.exit).join('\n')));
    ge.appendChild(svgEl('circle',{r:r}));
    ge.appendChild(svgEl('text',{class:'sid',dy:3},'→'));
    svg.appendChild(ge);
  }
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
    if(n.deploy){ // 배포 지점(이슈 #34) — 🚀 + 태그 라벨. 이 스텝에서 세상으로 나갔다.
      // staged 는 아직 안 올라간 것이다(이슈 #56) — 🚀 로 그리면 그래프가 거짓을 말한다.
      const staged=n.deployState==='staged';
      const rk=svgEl('text',{class:'deploybadge'+(staged?' staged':''),dy:n.here?-r-30:-r-14},
        (staged?'📦 ':'🚀 ')+n.deploy+(staged?' (staged)':''));
      const tt=svgEl('title',{},'배포 '+n.deploy+
        (n.deployTarget?'\n대상: '+n.deployTarget:'')+(n.deployUrl?'\n'+n.deployUrl:''));
      rk.appendChild(tt); g.appendChild(rk);
      g.classList.add('deployed');
      if(n.deployUrl){ rk.style.cursor='pointer'; rk.addEventListener('click',ev=>{ev.stopPropagation();window.open(n.deployUrl,'_blank');}); }
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
  showPane('pane-step',true);
}

// lineage — 이 스텝의 지식 전파를 진짜 커밋 부모/자식으로: (들어옴) 부모 → [이 스텝] → 자식(낳음).
// DAG(커밋 부모)를 써서 사이클·체인 경계를 넘는 전수도 보인다 — 부모 사이클/체인의 종결
// 스텝에서 태어난 첫 스텝이면 그 부모 노드를 그대로 가리킨다. 칩 클릭 → 그 스텝 보고서로.
function lineage(chain,cycle,n){
  const wrap=document.createElement('div');
  wrap.className='lineage';
  // DAG 에서 이 스텝 노드를 찾는다(sha 우선, 없으면 chain/cycle/step 로).
  const self=DAG.find(d=>d.sha===n.sha)||DAG.find(d=>d.chain===chain&&d.cycle===cycle&&d.step===n.id);
  const bySha={}; DAG.forEach(d=>bySha[d.sha]=d);
  const chip=(label,cls,target,title)=>{
    const s=document.createElement(target?'button':'span');
    s.className='lchip '+(cls||''); s.textContent=label;
    if(title)s.title=title;
    if(target){ s.addEventListener('click',ev=>{ev.stopPropagation();jumpToNode(target);}); }
    return s;
  };
  // 다른 사이클/체인이면 라벨에 그 위치를 밝힌다(경계 넘는 전수를 드러냄).
  const label=(d)=> (d.chain!==chain||d.cycle!==cycle) ? (d.chain+'/'+d.cycle+'/'+d.step+' '+d.kind) : (d.step+' '+d.kind);
  const crossHint=(d)=> (d.chain!==chain) ? '부모 체인 '+d.chain+' 의 종결 스텝에서 이어받음'
                      : (d.cycle!==cycle) ? '부모 사이클 '+d.cycle+' 의 스텝에서 이어받음' : '부모 스텝';
  // 들어옴(부모들).
  wrap.appendChild(chip('들어옴','lhead'));
  const inbox=document.createElement('span'); inbox.className='lgroup';
  const parents=(self&&self.parents||[]).map(p=>bySha[p]).filter(Boolean);
  if(parents.length){
    parents.forEach(p=>{
      const cross=(p.chain!==chain||p.cycle!==cycle);
      inbox.appendChild(chip(label(p),'lin'+(cross?' lchain':''),p,crossHint(p)));
    });
  }else{
    inbox.appendChild(chip('시작점(대문에서)','lchain',null,'이 체인의 첫 스텝 — 대문(루트)에서 시작'));
  }
  wrap.appendChild(inbox);
  // 이 스텝.
  wrap.appendChild(chip('→',''));
  wrap.appendChild(chip(n.id+' '+n.kind,'lself k-'+stepClass(n)));
  wrap.appendChild(chip('→',''));
  // 낳음(자식들) — DAG 에서 parents 에 self.sha 를 포함하는 노드(경계 넘는 자식 포함).
  wrap.appendChild(chip('낳음','lhead'));
  const outbox=document.createElement('span'); outbox.className='lgroup';
  const kids=self?DAG.filter(d=>d.parents.includes(self.sha)):[];
  if(kids.length){
    kids.forEach(k=>{
      const cross=(k.chain!==chain||k.cycle!==cycle);
      const branch=(k.parent&&k.parent!=='null'&&k.parent!==n.id); // backtrack 형제가지
      outbox.appendChild(chip(label(k),'lout'+(branch?' lbranch':'')+(cross?' lchain':''),k,
        cross?'자식 '+(k.chain!==chain?'체인 '+k.chain:'사이클 '+k.cycle)+' 이 여기서 이어받음':(branch?'되돌아온 형제 가지':'다음 스텝')));
    });
  }else{
    outbox.appendChild(chip(n.kind==='fail'?'죽은 잎(벽) — 여기서 끝':'잎(여기서 끝)','ldim',null,
      n.kind==='fail'?'이 가지는 여기서 죽었다 — 조상 define 으로 되돌아가 다른 가지를 폈다':'이 사이클의 결말 노드'));
  }
  wrap.appendChild(outbox);
  return wrap;
}
// jumpToNode — DAG 노드 d 로 이동: 그 체인 선택 → 사이클 카드 → 스텝 보고서 → 스크롤.
function jumpToNode(d){
  selectChain(d.chain);
  const cyc=DATA[d.chain]?.cycles.find(c=>c.name===d.cycle);
  if(!cyc)return;
  openStepCard(d.chain,cyc);
  const sn=(cyc.nodes||[]).find(x=>x.id===d.step);
  if(sn)openReport(d.chain,d.cycle,sn);
  document.getElementById('pane-report')?.scrollIntoView({behavior:'smooth',block:'nearest'});
}
// jumpToAgg — 집계 노드(사이클/체인) 클릭 → 그 사이클(또는 체인 첫 사이클)의 첫 스텝으로 내려간다.
function jumpToAgg(n){
  selectChain(n.chain);
  const cy=DATA[n.chain]?.cycles||[];
  const target=MAP_DEPTH==='cycle'?cy.find(c=>c.name===n.cycle):cy[0];
  if(!target)return;
  openStepCard(n.chain,target);
  const first=(target.nodes||[])[0];
  if(first)openReport(n.chain,target.name,first);
  document.getElementById('pane-report')?.scrollIntoView({behavior:'smooth',block:'nearest'});
}
// setMapDepth — 뎁스 토글(AIL #6). 세그먼트 버튼 on 상태 갱신 + 전체맵 재렌더.
function setMapDepth(depth){
  MAP_DEPTH=depth;
  document.querySelectorAll('#depthseg button').forEach(b=>b.classList.toggle('on',b.dataset.depth===depth));
  buildStepMap();
}

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

  // pending 잎이면 사람이 여기서 직접 승인/기각한다(상현님). 버튼이 서버 /approve·/reject 를
  // 쳐서 gil approve/reject 를 실행 → 폴링이 곧 갱신하지만 즉시 리로드해 반영한다. 정적 build
  // 모드(서버 없음)에선 버튼을 숨긴다(누를 서버가 없다).
  if(n.kind==='pending' && !LIVE_STATIC){
    const box=document.createElement('div');
    box.className='pendbox';
    const msg=document.createElement('span'); msg.className='pendmsg'; msg.textContent='⏳ 사람 답 대기 —';
    const ok=document.createElement('button'); ok.className='pendbtn approve'; ok.textContent='✓ 승인(산 잎)';
    const no=document.createElement('button'); no.className='pendbtn reject'; no.textContent='✕ 기각(되돌림)';
    const status=document.createElement('span'); status.className='pendstatus';
    const act=async(kind)=>{
      ok.disabled=no.disabled=true; status.textContent=' 처리 중…';
      const qs='chain='+encodeURIComponent(chain)+'&cycle='+encodeURIComponent(cycle)+
        (kind==='reject'?'&to=s1':''); // 기각은 사이클 뿌리 define(s1)로 되돌린다
      try{
        const res=await fetch('/'+kind+'?'+qs,{method:'POST'});
        const txt=await res.text();
        if(res.ok){ status.textContent=' ✓ 완료 — 갱신 중'; setTimeout(()=>location.reload(),400); }
        else{ status.textContent=' ✕ '+txt.split('\n')[0]; ok.disabled=no.disabled=false; }
      }catch(e){ status.textContent=' ✕ '+e; ok.disabled=no.disabled=false; }
    };
    ok.addEventListener('click',ev=>{ev.stopPropagation();act('approve');});
    no.addEventListener('click',ev=>{ev.stopPropagation();act('reject');});
    box.appendChild(msg); box.appendChild(ok); box.appendChild(no); box.appendChild(status);
    rc.appendChild(box);
  }

  // 지식 전파 계보(피드백 3): 이 스텝이 무엇을 이어받고(들어오는) 무엇을 낳는지(나가는).
  rc.appendChild(lineage(chain,cycle,n));

  // 본문(제목+body)을 마크다운으로 렌더(피드백 6·7). /step 에서 원문을 가져온다.
  const body=document.createElement('div');
  body.className='report md';
  body.textContent='(불러오는 중…)';
  rc.appendChild(body);
  showPane('pane-report',true);
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

// 전체 스텝맵(피드백 4): 모든 스텝을 진짜 커밋 DAG 로 — git 그래프처럼 왼→오른 한 줄 흐름.
// 체인은 세로로 쌓지 않는다: 부모→자식 체인이 x축으로 이어져 한 흐름이 된다. backtrack
// 분기만 아래 레인으로 살짝 갈라졌다 합류. 체인 이름은 그 체인 사이클 박스 '위'에 얹는다.
// 사이클=옅은 점선 박스, 스텝=작은 점(글씨 없이). 현재위치(HEAD)는 ▼ 역삼각형.
// 현재 뎁스(AIL #6). 'step'(기본)·'cycle'·'체인'. gil log --depth 의 뷰어판.
let MAP_DEPTH='step';
// 전체맵 체인 필터(이슈 #79). 26체인·381스텝이 되면 전체맵은 사람이 눈으로 따라갈 수 없다.
// 뎁스 접기(AIL #6)는 '얼마나 자세히'를 줄이지만 '무엇을'은 못 줄인다 — 지금 보려는 체인
// 하나만 남기는 축이 따로 필요하다. ''=전체.
let MAP_CHAIN=(()=>{ try{ return localStorage.getItem('gilMapChain')||''; }catch(e){ return ''; } })();

// aggregateDAG — 스텝 DAG 를 사이클/체인 단위로 접어 합성 노드 배열을 만든다(AIL #6).
// 반환 노드는 buildStepMap 이 쓰는 필드(sha·chain·cycle·step·kind·outcome·parents·here·subj)를
// 흉내낸다 — 같은 배치·엣지·줌팬 엔진에 그대로 태우려고. 새 데이터 주입 없이 순수 클라이언트
// 집계라 Warp-anchor(새 명령·채널 최소) 원칙에 맞는다.
// chainFilterBar — "지금 이 체인만" 을 고르는 줄(이슈 #79). 26개가 넘어가면 칩은 줄을 먹으니
// select 로 둔다. 고른 값은 localStorage 에 남아 폴링 리로드를 넘어 유지된다.
function chainFilterBar(chains){
  const bar=document.createElement('div'); bar.className='dagbar';
  const lab=document.createElement('span'); lab.className='zhint'; lab.textContent='체인:';
  const sel=document.createElement('select');
  const mk=(v,t)=>{const o=document.createElement('option');o.value=v;o.textContent=t;
    if(v===MAP_CHAIN)o.selected=true;sel.appendChild(o);};
  mk('','전체 ('+chains.length+'개 체인)');
  chains.forEach(c=>mk(c,c));
  sel.addEventListener('change',()=>{
    MAP_CHAIN=sel.value;
    try{ localStorage.setItem('gilMapChain',MAP_CHAIN); }catch(e){}
    buildStepMap();
  });
  bar.appendChild(lab); bar.appendChild(sel);
  if(MAP_CHAIN){
    const hint=document.createElement('span'); hint.className='zhint';
    hint.textContent='— 이 체인만 그린다(다른 체인은 숨김). 계보 전체는 "전체".';
    bar.appendChild(hint);
  }
  return bar;
}

function aggregateDAG(depth){
  if(depth==='step')return DAG;
  const keyOf=n=>depth==='cycle'?(n.chain+'/'+n.cycle):n.chain;
  const groups={}, order=[];
  DAG.forEach(n=>{ const k=keyOf(n); if(!(k in groups)){groups[k]={key:k,steps:[]};order.push(k);} groups[k].steps.push(n); });
  // 스텝 sha → 그룹키(엣지 접기용).
  const g4sha={}; DAG.forEach(n=>{ g4sha[n.sha]=keyOf(n); });
  const out=[];
  order.forEach(k=>{
    const g=groups[k], steps=g.steps;
    // 그룹 상태: success 스텝 하나라도 있으면 solved, 아니면 죽은 잎(fail) 있으면 dead, 그 외 pending/open.
    // 텍스트판 cycleView.status() 와 일관 — leaf 여부가 아니라 종결 kind 로 판정한다. (다음 사이클이
    // 이 사이클 산 잎 위에서 태어나면 그 잎은 전역 DAG 상 leaf 가 아니지만, 여전히 이 사이클의 결말이다.)
    let hasAlive=false,hasDead=false,hasPending=false,hasHere=false;
    steps.forEach(n=>{ const c=stepClass(n);
      if(c==='alive')hasAlive=true; if(c==='dead')hasDead=true; if(c==='pending')hasPending=true; if(n.here)hasHere=true; });
    // 부모 그룹키: 이 그룹 스텝의 부모 중 다른 그룹에 속한 것(경계 넘는 엣지) → 그 그룹 대표 sha.
    const pkeys=new Set();
    steps.forEach(n=>n.parents.forEach(p=>{ const pk=g4sha[p]; if(pk&&pk!==k)pkeys.add(pk); }));
    // 합성 kind: solved면 success(초록), dead면 fail(붉음), pending, 그 외 live.
    const synthKind=hasAlive?'success':hasDead?'fail':hasPending?'pending':'live';
    out.push({
      sha:'grp:'+k, chain:steps[0].chain, cycle:depth==='cycle'?steps[0].cycle:'',
      step:depth==='cycle'?steps[0].cycle:steps[0].chain, kind:synthKind, outcome:'', here:hasHere,
      parents:[...pkeys].map(pk=>'grp:'+pk),
      // ⚡ 분기: solved 인데 죽은 잎도 품음(일자 solved 와 구분, 텍스트판 v3.4.1 과 일관).
      forked:hasAlive&&hasDead, nsteps:steps.length,
      subj:(depth==='cycle'?'사이클 '+k:'체인 '+k)+' — '+steps.length+'스텝'+(hasAlive&&hasDead?' ⚡분기 밟은 solved':''),
    });
  });
  return out;
}

function buildStepMap(){
  const host=document.getElementById('view-map');
  host.replaceChildren();
  const folded=aggregateDAG(MAP_DEPTH);
  const ALLCHAINS=[...new Set(folded.map(n=>n.chain).filter(Boolean))].sort();
  if(MAP_CHAIN&&!ALLCHAINS.includes(MAP_CHAIN))MAP_CHAIN='';   // 사라진 체인이 필터에 남지 않게
  const VIS=folded.filter(n=>!MAP_CHAIN||n.chain===MAP_CHAIN);
  host.appendChild(chainFilterBar(ALLCHAINS));
  if(!VIS.length){ host.appendChild(document.createTextNode('아직 노드가 없다.')); return; }
  const byId={}; VIS.forEach(n=>byId[n.sha]=n);
  // 전체맵의 선은 **gil 룰**로 그린다(이슈 #70). 옛 전체맵은 커밋 조상관계를 날것으로 이어,
  // 계보상 무관한 체인 — orphan 이거나 그냥 나중에 열린 체인 — 까지 한 줄로 길게 붙였다.
  // 아래 하위 패널(체인·사이클 그래프)은 gil 판정(닫힌 끝에서 태어났을 때만 계승, #53)을
  // 쓰는데 위아래가 다른 그림을 냈다. #65 에서 "주황이라 주장하는 자리"만 통일했고, 이제
  // **선 자체**를 통일한다: 같은 체인 안이면 잇고, 체인을 넘으면 진짜 계승일 때만 잇는다.
  // 커밋 조상관계는 사실이지만 여기서는 안 그린다 — 적층은 gil fsck 가 이미 짚는다(#65).
  const gilParents=n=>n.parents.filter(p=>{
    const pn=byId[p]; if(!pn) return false;
    if(pn.chain===n.chain) return true;              // 체인 안의 흐름 — 언제나 계보다
    return PARENTS[n.chain]===pn.chain;              // 체인 넘기는 진짜 계승일 때만
  });
  VIS.forEach(n=>{ n.gparents=gilParents(n); });
  const kids={}; VIS.forEach(n=>{ n.gparents.forEach(p=>{ (kids[p]=kids[p]||[]).push(n.sha); }); });
  // x = 위상 깊이(시간, 왼→오른). 계보 부모→자식이 이 x축으로 이어진다. 계보가 끊긴 체인은
  // depth 0 에서 새로 시작한다 — 무관한 체인이 앞 체인 꼬리에 길게 붙지 않는다.
  const depth={};
  function dep(sha){ if(sha in depth)return depth[sha]; const n=byId[sha]; if(!n)return 0;
    let d=0; n.gparents.forEach(p=>{ if(byId[p])d=Math.max(d,dep(p)+1); }); depth[sha]=d; return d; }
  VIS.forEach(n=>dep(n.sha));
  // 전역 레인(row) 배정 — git 그래프식: 첫 부모의 레인을 물려받고(선형 연속), 자리 다툼일
  // 때만 아래 빈 레인으로. 체인 무관 → 메인 흐름이 한 줄(row 0)로 흐르고 분기만 내려간다.
  // 교차 최소화(AIL #10, 상현님 실 AIL 216노드 관전으로 재확인): 같은 depth 안에서 노드를
  // '첫 부모의 row' 로 2차 정렬한다 — 위쪽 부모의 자식이 위쪽 레인에 먼저 자리 잡아 부모→자식
  // 선이 덜 엇갈린다(barycenter 근사). 처음엔 단순 fixture 로 효과 0 이라 뺐으나, 실사용
  // 216노드에선 교차 162→48(약 70%↓) 로 결정적이었다. 단순 fixture 로 성급히 철회한 걸 실
  // 데이터로 되돌린다. Sugiyama 완전판(레이어 반복 교차정렬)은 아직 과하다 — 이 1패스로 충분.
  const parentRow=n=>{ const gp=n.gparents.filter(p=>byId[p]); return gp.length?Math.min(...gp.map(p=>row[p]??0)):-1; };
  const byDepth={}; VIS.forEach(n=>{ (byDepth[depth[n.sha]]=byDepth[depth[n.sha]]||[]).push(n); });
  const row={}, busy={}; let maxRow=0; // busy[row]=그 레인을 마지막 점유한 depth
  Object.keys(byDepth).map(Number).sort((a,b)=>a-b).forEach(d=>{
    byDepth[d].slice().sort((a,b)=>parentRow(a)-parentRow(b)).forEach(n=>{
      const gp=n.gparents.filter(p=>byId[p]);
      let L=gp.length?(row[gp[0]]||0):0;
      const owns=gp.some(p=>row[p]===L);
      if(!owns || (busy[L]!==undefined && busy[L]>=d)){ L=0; while(busy[L]!==undefined && busy[L]>=d)L++; }
      row[n.sha]=L; busy[L]=d; if(L>maxRow)maxRow=L;
    });
  });
  const rowH=24, padBot=14, r=5;
  // colW: 스텝맵은 촘촘히(34px). 집계 모드(사이클/체인)는 노드 위에 이름 라벨이 붙으니, 가장 긴
  // 이름이 안 겹치게 x간격을 그 폭 기준으로 넓힌다(AIL #9 집계판 — 헤드리스로 못 본 픽셀 버그).
  const aggMode = MAP_DEPTH!=='step';
  // padTop: 라벨이 들어갈 머리 공간. 스텝 뎁스는 사이클 라벨 + 체인 라벨 두 종류가 쌓이고
  // 둘 다 겹치면 계단식으로 최대 2단씩 더 올라가므로 그만큼 확보한다(이슈 #37).
  // 좁게 잡으면 위로 피한 라벨이 화면 밖으로 잘려 "겹침 대신 실종"이 된다.
  // 사이클 라벨은 박스보다 길면 통째로 생략됐다 — 겹침 대신 실종(이슈 #37 의 대가). 상현님
  // 제안대로 **기울여** 그리면 가로 폭이 줄어 살아난다: 폭 W 라벨이 35° 기울면 가로는
  // W·cos35(≈0.82W), 대신 세로로 W·sin35(≈0.57W)를 먹는다. 그래서 기울일 만큼 머리 공간을
  // 미리 확보한다 — 확보 없이 기울이면 위로 잘려 실종만 모양을 바꾼다(이슈 #71).
  const ROT=35, RAD=ROT*Math.PI/180;
  let longestCyName=0;
  if(!aggMode) VIS.forEach(n=>{ longestCyName=Math.max(longestCyName,(n.cycle||'').length); });
  const cyLabelW=longestCyName*6;                       // cyclabel 9px ≈ 6px/글자
  const rotHead=Math.min(120, Math.ceil(cyLabelW*Math.sin(RAD)));
  const padTop = aggMode ? 38 : 62+rotHead;
  let longestLabel=0;
  if(aggMode) VIS.forEach(n=>{ const s=(MAP_DEPTH==='cycle'?n.cycle:n.chain)||''; longestLabel=Math.max(longestLabel,s.length); });
  const colW = aggMode ? Math.max(48, longestLabel*7+18) : 34; // ~7px/글자 + 여백
  // 집계 모드는 첫 노드 라벨(중앙정렬)이 왼쪽으로 삐져나가니 padX 를 라벨 절반만큼 확보.
  const padX = aggMode ? Math.max(26, longestLabel*7/2+8) : 26;
  let maxD=0; VIS.forEach(n=>{ if(depth[n.sha]>maxD)maxD=depth[n.sha]; });
  // 오른쪽 여유 = 가장 긴 체인 이름이 박스 위 라벨로 삐져나가도 안 잘리게.
  let maxName=0; VIS.forEach(n=>{ maxName=Math.max(maxName,(n.chain||'').length); });
  let maxColUsed=false;
  const workPad=(WORK&&WORK.dirty)?colW+40:0;   // 작업중 유령 노드가 잘리지 않게 한 칸 더
  const rightPad=Math.max(padX, maxName*7+16)+workPad;
  const W=padX+rightPad+maxD*colW+r*2, H=padTop+padBot+maxRow*rowH+r*2;
  const X=sha=>padX+r+depth[sha]*colW;
  const Y=sha=>padTop+r+row[sha]*rowH;
  const svg=svgEl('svg',{class:'dag',viewBox:'0 0 '+W+' '+H,width:W,height:H});
  const agg=aggMode; // 집계 모드(사이클/체인)면 사이클 박스 대신 노드 라벨을 쓴다.
  // 1) 사이클 구간 박스(x 범위 = 그 사이클 스텝들의 depth, y 범위 = 그 스텝들의 row). 집계 모드는 생략.
  const cyc={}; if(!agg) VIS.forEach(n=>{ const k=n.chain+'/'+n.cycle; (cyc[k]=cyc[k]||[]).push(n); });
  // 체인별 첫(가장 왼쪽) 사이클 — 그 위에 체인 이름을 얹는다.
  const chainMinD={}; VIS.forEach(n=>{ if(chainMinD[n.chain]===undefined||depth[n.sha]<chainMinD[n.chain])chainMinD[n.chain]=depth[n.sha]; });
  // 라벨 겹침 회피(이슈 #37). 옛 방식은 **직전 같은 종류 라벨** 하나하고만 비교하고 11px 씩
  // 계단을 올렸는데, 두 가지가 다 틀렸다: (a) 체인 라벨(11px 굵게)은 높이가 11px 를 넘어서
  // 한 단 올려도 여전히 포갰다 (b) 체인 라벨과 사이클 라벨은 서로 다른 종류라 비교조차 안 됐다.
  // 실측: "gil-v3-dev ↰" 와 "gil-v3-redesign" 이 2px 차이로 겹쳐 둘 다 안 읽혔다.
  //
  // 이제 종류를 섞어 **실제 사각형끼리** 밀어낸다: x 순으로 놓되, 이미 놓인 것과 부딪히면
  // 안 부딪힐 때까지 한 칸씩 위로. 머리 공간을 넘으면 그 라벨은 생략한다(박스 title 로 남는다)
  // — 화면 밖으로 밀어 올리면 "겹침 대신 실종"이 될 뿐이다.
  const placed=[]; // 이미 자리 잡은 라벨 사각형들
  const LSTEP=13;  // 한 칸 = 가장 큰 라벨(11px 굵게)이 확실히 안 닿는 높이
  function placeLabel(x,yBase,w,h,mk){
    let y=yBase;
    const hit=()=>placed.some(p=> x < p.x+p.w && p.x < x+w && (y-h) < p.y && p.y-p.h < y);
    while(hit()){
      y-=LSTEP;
      if(y-h < 2) return false; // 머리 공간을 넘었다 — 생략(박스 title 로 여전히 읽을 수 있다)
    }
    placed.push({x,y,w,h});
    const el=mk(y); svg.appendChild(el);
    return true;
  }
  const CW=6, cylW=k=>{ const s=k.slice(k.indexOf('/')+1); return s.length*CW; };
  const cycKeys=Object.keys(cyc).sort((a,b)=>{ // x(dmin) 오름차순
    const da=Math.min(...cyc[a].map(n=>depth[n.sha])), db=Math.min(...cyc[b].map(n=>depth[n.sha])); return da-db; });

  // 1) 박스를 먼저 다 그리고 기하만 모은다. 라벨은 두 번에 나눠 놓는다(아래 2·3).
  const boxes=[];
  cycKeys.forEach(k=>{ const ns=cyc[k];
    let dmin=Infinity,dmax=-Infinity,rmin=Infinity,rmax=-Infinity;
    ns.forEach(n=>{ dmin=Math.min(dmin,depth[n.sha]); dmax=Math.max(dmax,depth[n.sha]);
      rmin=Math.min(rmin,row[n.sha]); rmax=Math.max(rmax,row[n.sha]); });
    const x1=X_(dmin)-r-5, x2=X_(dmax)+r+5, y1=Y_(rmin)-r-4, y2=Y_(rmax)+r+4;
    const box=svgEl('rect',{class:'cycbox',x:x1,y:y1,width:x2-x1,height:y2-y1,rx:6});
    box.appendChild(svgEl('title',{},k));
    svg.appendChild(box);
    boxes.push({k,ns,x1,x2,y1,dmin});
  });

  // 2) **사이클 라벨을 먼저** 놓는다(이슈 #52). 자리 다툼에서 살아남아야 할 건 "어느
  //    사이클인가"다 — 체인 이름은 몇 개뿐이고 반복되지만, 사이클 이름은 그 박스의 유일한
  //    신원이다. 나중에 놓으면 앞서 놓인 체인 라벨들에 밀려 머리 공간을 넘고 통째로 생략된다
  //    (실측: 64 사이클 저장소에서 사이클 라벨이 64개 중 1개만 그려졌다).
  boxes.forEach(b=>{
    const boxW=b.x2-b.x1, lblW=cylW(b.k), name=b.k.slice(b.k.indexOf('/')+1);
    if(lblW <= boxW+colW){ // 박스에 눕혀도 들어간다 — 읽기 쉬운 가로가 우선.
      placeLabel(b.x1+2, b.y1-3, lblW, 11, y=>{
        const t=svgEl('text',{class:'cyclabel',x:b.x1+2,y:y},name);
        t.appendChild(svgEl('title',{},b.k)); return t;
      });
      return;
    }
    // 눕히면 이웃을 침범한다 — 기울여 세운다. 자리 다툼은 **기울인 실제 footprint**로 한다.
    const fw=Math.ceil(lblW*Math.cos(RAD)), fh=Math.ceil(lblW*Math.sin(RAD))+4;
    placeLabel(b.x1+2, b.y1-3, fw, fh, y=>{
      const t=svgEl('text',{class:'cyclabel',x:b.x1+2,y:y},name);
      t.setAttribute('transform','rotate(-'+ROT+','+(b.x1+2)+','+y+')');
      t.appendChild(svgEl('title',{},b.k)); return t;
    });
  });

  // 3) 체인 라벨은 **체인당 딱 한 번**(이슈 #52). 옛 판정은 "이 사이클의 dmin 이 체인 최소
  //    dmin 과 같은가"였는데, migrate 산물처럼 사이클들이 체인 루트에서 나란히 갈라지면 그
  //    조건이 사이클마다 참이 되어 같은 이름이 사이클 수만큼 방출됐다(실측: 36 사이클 체인에
  //    라벨 36개). 깊이 비교가 아니라 **이미 그렸는지**로 판정한다. cycKeys 가 x 오름차순이라
  //    첫 등장이 곧 가장 왼쪽이다.
  const chainDone=new Set();
  boxes.forEach(b=>{
    const ch=b.ns[0].chain;
    if(chainDone.has(ch)) return;
    chainDone.add(ch);
    const pc=PARENTS[ch], chName=ch+(pc?' ↰':'');
    placeLabel(b.x1+2, b.y1-3-LSTEP, chName.length*(CW+1), 13, y=>{
      const lab=svgEl('text',{class:'chlabel',x:b.x1+2,y:y});
      lab.textContent=chName;
      lab.appendChild(svgEl('title',{},pc?('체인 '+ch+' — 부모 체인 '+pc+' 에서 이어받음'):('체인 '+ch)));
      return lab;
    });
  });
  function X_(d){ return padX+r+d*colW; }
  function Y_(rw){ return padTop+r+rw*rowH; }
  // 2) 엣지(부모→자식). backtrack 형제가지=빨강 파선. 경계 넘는(체인 전환) 엣지=주황.
  VIS.forEach(n=>{ n.gparents.forEach(p=>{ if(!byId[p])return;
    const x1=X(p),y1=Y(p),x2=X(n.sha),y2=Y(n.sha);
    const branch=n.parent&&n.parent!=='null'&&byId[p].step!==n.parent;
    // 체인을 넘는 엣지를 "체인 전환(주황)"이라 부르려면, 그게 **진짜 계승**이어야 한다
    // (이슈 #65). PARENTS 는 체인 그래프가 쓰는 것과 같은 판정 결과다 — 닫힌 끝에서
    // 태어났을 때만 계승(#53). 두 패널이 같은 자리에서 끊고 같은 자리에서 잇게 한다.
    // 계승이 아닌 경계 넘기는 회색 실선으로 남는다: 커밋 조상관계는 사실이므로 그리되,
    // "이어받았다"고 주장하지 않는다.
    // 여기까지 온 체인 넘기는 엣지는 gilParents 를 통과한 것이므로 곧 진짜 계승이다.
    const realSuccession=byId[p].chain!==n.chain;
    const cls='dedge'+(branch?' branch':'')+(realSuccession?' cross':'');
    const mx=(x1+x2)/2;
    svg.appendChild(svgEl('path',{class:cls,fill:'none',d:'M '+x1+' '+y1+' C '+mx+' '+y1+' '+mx+' '+y2+' '+x2+' '+y2}));
  }); });
  // 3) 노드 + HEAD ▼. 스텝 모드=작은 점(글씨 없음). 집계 모드=큰 점+이름 라벨(+⚡분기).
  VIS.forEach(n=>{
    const g=svgEl('g',{class:'dnode k-'+stepClass(n)+(n.here?' here':'')+(isLeaf(n,kids)?' leaf':'')+(agg?' agg':''),transform:'translate('+X(n.sha)+','+Y(n.sha)+')'});
    const tip=agg?(n.subj+(n.here?'  ◀ HEAD':'')):(n.chain+'/'+n.cycle+'/'+n.step+' '+n.kind+(n.here?' ◀ HEAD':'')+'\n'+n.subj);
    g.appendChild(svgEl('title',{},tip));
    g.appendChild(svgEl('circle',{r:agg?r+2:r}));
    if(n.forked){ const s=svgEl('text',{class:'forkmark',x:0,y:3}); s.textContent='⚡'; g.appendChild(s); } // 분기 밟은 solved
    if(agg){ const lab=svgEl('text',{class:'agglabel',x:0,y:-(r+6)}); lab.textContent=(MAP_DEPTH==='cycle'?n.cycle:n.chain); g.appendChild(lab); }
    if(n.here) g.appendChild(svgEl('path',{class:'headarrow',d:'M 0 '+(-r-3)+' l -5 -7 l 10 0 z'}));
    if(n.deploy){ // 배포 지점(이슈 #34) — 전체맵에도 🚀 + 태그. 세상으로 나간 스텝.
      g.classList.add('deployed');
      const stagedD=n.deployState==='staged';
      const rk=svgEl('text',{class:'dagdeploy'+(stagedD?' staged':''),x:0,y:n.here?-r-14:-(r+5)},
        (stagedD?'📦':'🚀')+(agg?'':' '+n.deploy));
      rk.appendChild(svgEl('title',{},'배포 '+n.deploy+
        (n.deployTarget?'\n대상: '+n.deployTarget:'')+(n.deployUrl?'\n'+n.deployUrl:'')));
      g.appendChild(rk);
    }
    g.addEventListener('click',()=>agg?jumpToAgg(n):jumpToNode(n));
    svg.appendChild(g);
  });
  // 작업중(미커밋) 유령 노드 — 앵커 스텝 오른쪽에 점선 원 + ✎ 라벨(상현님). 커밋 전에도
  // "지금 어디서 손대고 있나"가 그래프에 보인다. 커밋되면 진짜 노드가 그 자리를 잇는다.
  if(WORK&&WORK.dirty){
    // 앵커 찾기는 층으로 내려간다. HEAD 가 분리(detached)돼 있으면 그 스텝이 어느 브랜치에도
    // 없어 sha 로는 안 잡힌다(실사용 저장소가 정확히 그 상태였다) — 그때는 id 로, 그것도
    // 없으면 같은 사이클·체인의 마지막 노드로 붙인다. 자리를 못 찾아 안 그리는 것이 최악이다.
    const inView=n=>!MAP_CHAIN||n.chain===MAP_CHAIN;
    const newest=list=>list.slice().sort((a,b)=>stepNumJS(b.step||'')-stepNumJS(a.step||''))[0];
    const anchor=
      VIS.find(n=>n.sha===WORK.sha) ||
      VIS.find(n=>n.chain===WORK.chain&&n.cycle===WORK.cycle&&n.step===WORK.step) ||
      newest(VIS.filter(n=>n.chain===WORK.chain&&n.cycle===WORK.cycle)) ||
      newest(VIS.filter(n=>n.chain===WORK.chain));
    void inView;
    if(anchor){
      const wx=X(anchor.sha)+colW, wy=Y(anchor.sha);
      svg.appendChild(svgEl('path',{class:'dedge work',fill:'none',
        d:'M '+(X(anchor.sha)+r)+' '+Y(anchor.sha)+' L '+(wx-r)+' '+wy}));
      const wg=svgEl('g',{class:'dnode working',transform:'translate('+wx+','+wy+')'});
      const tip='✎ 작업중(미커밋) — '+WORK.summary+
        (WORK.branch?'\n브랜치: '+WORK.branch:'')+
        (WORK.ahead?'\n앵커 이후 평범한 커밋 '+WORK.ahead+'개':'')+
        (WORK.files&&WORK.files.length?'\n'+WORK.files.join('\n'):'')+
        '\n커밋하면 이 자리에 진짜 스텝이 선다.';
      wg.appendChild(svgEl('title',{},tip));
      wg.appendChild(svgEl('circle',{r:agg?r+2:r}));
      const lb=svgEl('text',{class:'worklbl',x:0,y:-(r+6)}); lb.textContent='✎ 작업중'; wg.appendChild(lb);
      svg.appendChild(wg);
      maxColUsed=true;
    }
  }
  const wrap=document.createElement('div'); wrap.className='dagwrap'; wrap.appendChild(svg);
  host.appendChild(enableZoomPan(wrap,svg,W,H));
  host.appendChild(wrap);
  const leg=document.createElement('p'); leg.className='hint';
  if(MAP_DEPTH==='step')
    leg.innerHTML='gil 계보 그래프 — 왼→오른 흐름, 선은 gil 룰(같은 체인의 흐름 + 닫힌 끝에서 태어난 체인 계승)로만 잇는다. 계보가 없는 체인은 이어지지 않고 따로 선다(커밋 조상관계는 사실이지만 여기선 안 그린다 — 적층은 gil fsck 가 짚는다). 점선 박스=사이클(박스 위 작은 글씨=사이클 이름, 체인 첫 박스 위=체인 이름), 점=스텝. <b class="lg-cross">주황</b>=체인 전환(부모 체인 종결→자식), <b class="lg-branch">빨강 파선</b>=backtrack, <b class="lg-dead">붉은 점</b>=죽은 잎, <b class="lg-alive">초록 점</b>=산 잎, <b>🚀</b>=배포(공개) 지점, <b>▼</b>=현재위치(HEAD). 점 클릭 → 아래 상세.';
  else
    leg.innerHTML=(MAP_DEPTH==='cycle'?'사이클':'체인')+' 단위 접힌 맵(<b>gil log --depth</b> 뷰어판) — 노드 하나=한 '+(MAP_DEPTH==='cycle'?'사이클':'체인')+'. <b class="lg-alive">초록</b>=solved(산 잎 있음), <b class="lg-dead">붉음</b>=dead, <b>⚡</b>=분기 밟은 solved(죽은 잎도 품음, 일자 solved 와 구분). 엣지=계보. 노드 클릭 → 그 '+(MAP_DEPTH==='cycle'?'사이클 첫 스텝':'체인 첫 사이클')+'으로 이동.';
  host.appendChild(leg);
}
// isLeaf — 이 노드를 부모로 삼는 gil 스텝이 없으면 잎(사이클 결말: 산 잎 or 죽은 잎).
function isLeaf(n,kids){ return !(kids[n.sha]&&kids[n.sha].length); }

// enableZoomPan — 전체맵 줌/팬(대형 그래프 항해). viewBox 를 움직인다:
// ＋/−/전체 버튼, Ctrl(⌘)+휠 = 포인터 위치 중심 줌, 확대 상태에서 드래그 = 팬.
// 반환: 컨트롤 바(dagbar) — 호출자가 그래프 위에 붙인다.
function enableZoomPan(wrap,svg,W,H){
  const MINW=W/16;                       // 최대 16배 확대
  let vb={x:0,y:0,w:W,h:H};
  function clamp(){
    vb.w=Math.min(Math.max(vb.w,MINW),W); vb.h=vb.w*H/W;
    vb.x=Math.min(Math.max(vb.x,0),W-vb.w); vb.y=Math.min(Math.max(vb.y,0),H-vb.h);
  }
  let apply=function(){
    svg.setAttribute('viewBox',vb.x+' '+vb.y+' '+vb.w+' '+vb.h);
    wrap.classList.toggle('zoomed',vb.w<W-0.5);
  };
  // 화면 픽셀 → viewBox 좌표.
  function toVB(e){
    const rc=svg.getBoundingClientRect();
    return {x:vb.x+(e.clientX-rc.left)/rc.width*vb.w, y:vb.y+(e.clientY-rc.top)/rc.height*vb.h};
  }
  function zoomAt(f,cx,cy){ // f<1 = 확대. (cx,cy) viewBox 좌표를 고정점으로.
    const nw=Math.min(Math.max(vb.w*f,MINW),W);
    vb.x=cx-(cx-vb.x)*nw/vb.w; vb.y=cy-(cy-vb.y)*nw/vb.w; vb.w=nw;
    clamp(); apply();
  }
  const center=()=>({x:vb.x+vb.w/2,y:vb.y+vb.h/2});
  // 컨트롤 바.
  const bar=document.createElement('div'); bar.className='dagbar';
  const btn=(label,title,fn)=>{const b=document.createElement('button');b.textContent=label;b.title=title;
    b.addEventListener('click',ev=>{ev.stopPropagation();fn();});bar.appendChild(b);};
  btn('＋','확대',()=>{const c=center();zoomAt(1/1.4,c.x,c.y);});
  btn('−','축소',()=>{const c=center();zoomAt(1.4,c.x,c.y);});
  btn('전체','전체 보기(리셋)',()=>{vb={x:0,y:0,w:W,h:H};apply();});
  const zh=document.createElement('span'); zh.className='zhint';
  zh.textContent='Ctrl+휠=줌 · 확대 후 드래그=이동 · 미니맵 클릭=그 자리로'; bar.appendChild(zh);
  // 미니맵(이슈 #79): 확대하면 전체 속 위치를 잃는다. 전체 축소본에 지금 보는 창을 그리고,
  // 클릭·드래그로 그 자리로 뛴다. 큰 그래프에서 확대 없이는 읽을 수 없고, 확대하면 길을
  // 잃는 딜레마를 푸는 최소 장치다. 노드를 다시 그리지 않고 원본 SVG 를 통째로 복제한다.
  const MMW=170, MMH=Math.max(40,Math.round(MMW*H/W));
  const mm=document.createElement('div'); mm.className='minimap';
  const mmsvg=svgEl('svg',{class:'mmsvg',viewBox:'0 0 '+W+' '+H,width:MMW,height:MMH,
    style:'width:'+MMW+'px;height:'+MMH+'px'});
  const shrunk=svg.cloneNode(true);
  shrunk.removeAttribute('width'); shrunk.removeAttribute('height');
  shrunk.removeAttribute('class');   // .dag 등 원본 클래스가 미니맵 크기를 다시 늘리지 않게
  shrunk.removeAttribute('style');
  shrunk.setAttribute('viewBox','0 0 '+W+' '+H);
  const holder=svgEl('g',{}); holder.appendChild(shrunk); mmsvg.appendChild(holder);
  const mmview=svgEl('rect',{class:'mmview',x:0,y:0,width:W,height:H});
  mmsvg.appendChild(mmview); mm.appendChild(mmsvg);
  function mmJump(e){
    const rc=mmsvg.getBoundingClientRect();
    const cx=(e.clientX-rc.left)/rc.width*W, cy=(e.clientY-rc.top)/rc.height*H;
    vb.x=cx-vb.w/2; vb.y=cy-vb.h/2; clamp(); apply();
  }
  mm.addEventListener('pointerdown',e=>{e.stopPropagation();mm.setPointerCapture(e.pointerId);mmJump(e);});
  mm.addEventListener('pointermove',e=>{if(e.buttons)mmJump(e);});
  // Ctrl(⌘)+휠 줌 — 포인터 위치 중심. 일반 휠은 페이지 스크롤 그대로 둔다.
  svg.addEventListener('wheel',e=>{
    if(!e.ctrlKey&&!e.metaKey)return;
    e.preventDefault();
    const p=toVB(e); zoomAt(e.deltaY>0?1.18:1/1.18,p.x,p.y);
  },{passive:false});
  // 드래그 팬 — 움직였으면 뒤따르는 클릭(노드 열기)을 삼킨다.
  let drag=null, moved=false;
  svg.addEventListener('pointerdown',e=>{
    if(vb.w>=W-0.5)return;               // 전체 보기에선 팬 없음
    drag={px:e.clientX,py:e.clientY,vx:vb.x,vy:vb.y}; moved=false;
    svg.setPointerCapture(e.pointerId); wrap.classList.add('grabbing');
  });
  svg.addEventListener('pointermove',e=>{
    if(!drag)return;
    const rc=svg.getBoundingClientRect();
    const dx=(e.clientX-drag.px)/rc.width*vb.w, dy=(e.clientY-drag.py)/rc.height*vb.h;
    if(Math.abs(e.clientX-drag.px)+Math.abs(e.clientY-drag.py)>4)moved=true;
    vb.x=drag.vx-dx; vb.y=drag.vy-dy; clamp(); apply();
  });
  svg.addEventListener('pointerup',()=>{drag=null;wrap.classList.remove('grabbing');});
  svg.addEventListener('click',e=>{ if(moved){e.stopPropagation();moved=false;} },true);
  const mmapply=()=>{
    mmview.setAttribute('x',vb.x); mmview.setAttribute('y',vb.y);
    mmview.setAttribute('width',vb.w); mmview.setAttribute('height',vb.h);
    wrap.classList.toggle('zoomed',vb.w<W-0.5);
    bar.classList.toggle('zoomed',vb.w<W-0.5);
  };
  const baseApply=apply;
  apply=function(){ baseApply(); mmapply(); };
  bar.appendChild(mm);
  apply();
  return bar;
}

// 체인 그래프에도 줌·팬·미니맵(이슈 #79). 체인이 늘수록 SVG 가 넓어지고 CSS 가 폭에 맞춰
// 줄이니, 26체인에서 노드가 39px 까지 작아져 **누르기 힘들어졌다**. 전체맵과 같은 엔진을
// 그대로 태운다 — 새 장치를 만들지 않고 이미 검증된 하나를 공유한다.
function enableChainGraphZoom(){
  // 체인 그래프 = .cnode(체인 노드)를 품은 서버 렌더 SVG. 'class 없는 svg' 같은 느슨한
  // 선택자는 미니맵의 복제 SVG 까지 집어 자기 자신을 감싸는 사고를 낸다(실측).
  const svg=[...document.querySelectorAll('svg')].find(x=>x.querySelector('.cnode')&&!x.closest('.minimap'));
  if(!svg||svg.dataset.zoomed)return;
  const W=parseFloat(svg.getAttribute('width')), H=parseFloat(svg.getAttribute('height'));
  if(!W||!H)return;
  svg.dataset.zoomed='1';
  const wrap=document.createElement('div'); wrap.className='dagwrap';
  svg.parentNode.insertBefore(wrap,svg); wrap.appendChild(svg);
  const bar=enableZoomPan(wrap,svg,W,H);
  wrap.parentNode.insertBefore(bar,wrap);
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
// ── 인터뷰 폼(이슈 #33) — LLM 이 심은 질문을 사람이 폼으로 답하고 제출하면 레퍼런스가 커밋된다 ──
const INTERVIEWS=JSON.parse(document.getElementById('interviewdata')?.textContent||'[]');
function buildInterviews(){
  const host=document.getElementById('interviews');
  if(!host||!INTERVIEWS.length)return;
  host.replaceChildren();
  INTERVIEWS.forEach(iv=>{
    const card=document.createElement('div'); card.className='ivcard';
    const head=document.createElement('div'); head.className='ivhead';
    head.innerHTML='체인 <b>'+esc(iv.chain)+'</b> 의 기준 문서를 함께 만든다 — 문제 풀듯 답하고 제출하세요.';
    card.appendChild(head);
    // 기다리는 사람이 보이게(이슈 #82) — 제출하고 아무 반응이 없으면 "놓쳤나"를 의심하게 된다.
    const wait=document.createElement('div');
    wait.className='ivwait'+(iv.waiting?' on':'');
    wait.textContent=iv.waiting?'⏳ 에이전트가 이 답을 기다리는 중 — 제출하면 곧바로 이어집니다.'
                               :'· 지금은 아무도 기다리고 있지 않습니다. 제출은 저장되고, 에이전트는 다음 접촉 때 읽습니다.';
    card.appendChild(wait);
    const form=document.createElement('form'); form.className='ivform';
    (iv.questions||[]).forEach((q,qi)=>{
      const fld=document.createElement('div'); fld.className='ivfield';
      const label=document.createElement('label'); label.className='ivq';
      label.textContent=(qi+1)+'. '+(q.q||''); fld.appendChild(label);
      const nm='q'+qi;
      if(q.type==='text'){
        const ta=document.createElement('textarea'); ta.name=nm; ta.rows=3; ta.className='ivinput';
        fld.appendChild(ta);
      } else if(q.type==='radio'||q.type==='checkbox'){
        const opts=document.createElement('div'); opts.className='ivopts';
        (q.options||[]).forEach((o,oi)=>{
          const id=nm+'_'+oi;
          const wrap=document.createElement('label'); wrap.className='ivopt';
          const inp=document.createElement('input'); inp.type=q.type; inp.name=nm; inp.value=o; inp.id=id;
          const span=document.createElement('span'); span.textContent=o;
          wrap.appendChild(inp); wrap.appendChild(span); opts.appendChild(wrap);
        });
        fld.appendChild(opts);
      }
      form.appendChild(fld);
    });
    const foot=document.createElement('div'); foot.className='ivfoot';
    const submit=document.createElement('button'); submit.type='submit'; submit.className='ivsubmit'; submit.textContent='제출 — 기준 문서로 저장';
    const status=document.createElement('span'); status.className='ivstatus';
    foot.appendChild(submit); foot.appendChild(status);
    form.appendChild(foot);
    form.addEventListener('submit',async ev=>{
      ev.preventDefault();
      // 답변을 {질문, 답} 배열로 조립. 체크박스는 다중값.
      const answers=(iv.questions||[]).map((q,qi)=>{
        const nm='q'+qi; let a='';
        if(q.type==='text'){ const el=form.querySelector('[name="'+nm+'"]'); a=el?el.value.trim():''; }
        else if(q.type==='radio'){ const el=form.querySelector('[name="'+nm+'"]:checked'); a=el?el.value:''; }
        else if(q.type==='checkbox'){ a=[...form.querySelectorAll('[name="'+nm+'"]:checked')].map(e=>e.value); }
        return {q:q.q, type:q.type, answer:a};
      });
      submit.disabled=true; status.textContent=' 저장 중…';
      try{
        const res=await fetch('/interview?chain='+encodeURIComponent(iv.chain),
          {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(answers)});
        const txt=await res.text();
        if(res.ok){ status.textContent=' ✓ 기준 문서 저장됨 — 갱신 중'; setTimeout(()=>location.reload(),500); }
        else{ status.textContent=' ✕ '+txt.split('\n')[0]; submit.disabled=false; }
      }catch(e){ status.textContent=' ✕ '+e; submit.disabled=false; }
    });
    card.appendChild(form); host.appendChild(card);
  });
}
function esc(s){ const d=document.createElement('div'); d.textContent=s==null?'':s; return d.innerHTML; }
document.querySelectorAll('#depthseg button').forEach(b=>b.addEventListener('click',()=>setMapDepth(b.dataset.depth))); // 뎁스 토글(AIL #6)
buildStepMap();  // 전체맵은 항상 맨 위에 렌더(탭 없음). 기본 뎁스=step.
enableChainGraphZoom(); // 체인 그래프도 줌·팬·미니맵(이슈 #79)
buildInterviews(); // 사람 답 대기 인터뷰 폼(이슈 #33)
restoreSel();
`
