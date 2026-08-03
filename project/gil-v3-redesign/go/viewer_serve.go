// serve.go — 브라우저 관전 서버. 대상 레포(--repo)의 gil 그래프를 HTML 로 그리고
// 팁 시그니처 폴링으로 자동 새로고침. stdlib 만.
package main

import (
	"encoding/json"
	"fmt"
	"html"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"syscall"
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
		// 질문이 여러 줄이면 **첫 줄만 제목**이고 나머지는 인용(`> `)으로 접는다(이슈 #109).
		// 제목 아래 맨 줄로 두면 그 줄들이 사람의 답과 구분되지 않아, --purpose-from 이
		// 고르지도 않은 후보 목록까지 체인 목적에 통째로 박았다. 답은 답만이어야 한다.
		qLines := strings.Split(strings.TrimSpace(a.Q), "\n")
		b.WriteString("## " + itoa(i+1) + ". " + strings.TrimSpace(qLines[0]) + "\n\n")
		for _, ql := range qLines[1:] {
			b.WriteString("> " + strings.TrimSpace(ql) + "\n")
		}
		if len(qLines) > 1 {
			b.WriteString("\n")
		}
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

// ── 뷰어 로그 (상현님 실사용: "인터뷰 진행하다가 갑자기 서버가 죽었어") ──────────────
//
// 자동 기동되는 뷰어는 stdout/stderr 를 /dev/null 로 버렸다. 그래서 뷰어가 죽어도 **한 글자도
// 안 남는다** — 패닉이든 git 실패든 OOM 이든 사후에 알 방법이 원리적으로 없다. 관전 도구가
// 죽은 이유를 못 밝히면, 같은 일이 몇 번을 반복돼도 계속 모른다(침묵은 '이상 없음'과
// 구분되지 않는다 — 이슈 #84 의 교훈이 도구 자신에게도 선다).
//
// 로그는 저장소의 .git 안에 둔다: 작업트리를 더럽히지 않고(미커밋 파일로 잡히지 않는다),
// 저장소마다 하나이며, 저장소를 지우면 함께 사라진다.
var viewerLogFile *os.File

// viewerServeMode — 이 프로세스가 관전 서버인가. die()/gilExit() 가 여기서는 프로세스를
// 죽이지 않고 그 요청 하나만 끝내게 한다(아래 handle 의 recover 가 받는다).
var viewerServeMode bool

// handle — 모든 뷰어 핸들러의 단일 관문. 어떤 조각이 죽어도 **서버는 산다**:
// 그 요청만 500 으로 끝나고, 이유는 로그와 응답 본문에 남는다. 관전 도구가 조용히
// 사라지는 것보다 한 요청이 실패하는 편이 언제나 낫다.
func handle(path string, fn func(http.ResponseWriter, *http.Request)) {
	http.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			rec := recover()
			if rec == nil {
				return
			}
			msg := "패닉"
			if ab, ok := rec.(gilAbort); ok {
				msg = "거부"
				if strings.TrimSpace(ab.msg) != "" {
					msg = ab.msg
				}
			} else {
				msg = fmt.Sprintf("패닉: %v", rec)
			}
			viewerLogWrite("요청 " + r.Method + " " + path + " 실패(서버는 계속 산다) — " + msg)
			defer func() { _ = recover() }() // 헤더가 이미 나갔으면 쓰기도 실패한다
			http.Error(w, "이 요청은 실패했다(서버는 살아 있다):\n"+msg+
				"\n\n자세한 이유: <레포>/.git/gil-viewer.log", http.StatusInternalServerError)
		}()
		fn(w, r)
	})
}

// repoGone — 관전 대상 저장소가 사라졌는가(삭제·이동·이름변경). 이건 일시적 오류가 아니라
// **이 뷰어의 존재 이유가 없어진 것**이다. 실사용에서 그런 뷰어가 기본 포트를 쥔 채 남아,
// handoff 가 그 주소를 "지금 열어라"로 가리켰고 사람은 남의(없는) 그래프를 봤다.
func repoGone() bool {
	if viewerRepoDir == "" {
		return false
	}
	if _, err := os.Stat(viewerRepoDir); err != nil {
		return true
	}
	if _, err := os.Stat(filepath.Join(viewerRepoDir, ".git")); err != nil {
		// .git 이 파일(worktree)일 수도 있으니 rev-parse 로 한 번 더 묻는다.
		if _, gerr := gitTryIn(viewerRepoDir, "rev-parse", "--git-dir"); gerr != nil {
			return true
		}
	}
	return false
}

func viewerLogPath() string { return viewerLogPathFor(viewerRepoDir) }

// viewerLogPathFor — 그 저장소의 뷰어 로그 경로(기동하는 쪽에서도 같은 자리를 쓴다).
func viewerLogPathFor(repo string) string {
	gd, err := gitTryIn(repo, "rev-parse", "--git-dir")
	dir := strings.TrimSpace(gd)
	if err != nil || dir == "" {
		return filepath.Join(os.TempDir(), "gil-viewer.log")
	}
	if !filepath.IsAbs(dir) {
		abs, aerr := filepath.Abs(filepath.Join(repo, dir))
		if aerr == nil {
			dir = abs
		}
	}
	return filepath.Join(dir, "gil-viewer.log")
}

// viewerLogOpen — 로그를 열고 기동 한 줄을 남긴다. 실패해도 서버는 뜬다(로그는 보조다).
func viewerLogOpen(port string) {
	f, err := os.OpenFile(viewerLogPath(), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	viewerLogFile = f
	abs, _ := filepath.Abs(viewerRepoDir)
	viewerLogWrite("기동 — pid " + itoa(os.Getpid()) + " · 포트 " + port + " · 레포 " + abs +
		" · gil " + gilVersion)
}

// viewerLogWrite — 시각과 함께 한 줄. 뷰어가 죽은 뒤 사람이 읽을 유일한 자리다.
func viewerLogWrite(msg string) {
	if viewerLogFile == nil {
		return
	}
	fmt.Fprintf(viewerLogFile, "[%s] %s\n", time.Now().Format("2006-01-02 15:04:05"), msg)
}

func serve(args []string) {
	port := "8790"
	for i := 0; i < len(args); i++ {
		if args[i] == "--port" && i+1 < len(args) {
			port = args[i+1]
			i++
		}
		// --lang 은 **기본값**일 뿐이다. 사람이 화면에서 고른 적이 있으면 그 선택이 이긴다 —
		// 도구가 사람의 선택을 매번 되돌리면 그건 설정이 아니라 강요다.
		if args[i] == "--lang" && i+1 < len(args) {
			if !i18nSupported(args[i+1]) {
				die("거부: 모르는 언어 " + args[i+1] + " — 쓸 수 있는 것: " + strings.Join(i18nLangs, " · "))
			}
			viewerLang = args[i+1]
			i++
		}
	}
	viewerServeMode = true // die/gilExit 가 이 프로세스를 죽이지 않는다(요청 하나만 끝난다)
	viewerLogOpen(port)
	// 관전 레포가 사라지면 스스로 물러난다 — 기본 포트를 쥔 채 남아 있으면 사람이 남의(없는)
	// 그래프를 자기 것으로 읽는다. 사라짐은 일시적 오류가 아니라 존재 이유의 소멸이다.
	go func() {
		for {
			time.Sleep(5 * time.Second)
			if repoGone() {
				viewerLogWrite("종료 — 관전 레포가 사라졌다(" + viewerRepoDir + "). 포트를 놓고 물러난다.")
				if viewerLogFile != nil {
					viewerLogFile.Close()
				}
				os.Exit(0)
			}
		}
	}()
	// 핸들러 패닉은 net/http 가 연결 단위로 회수하고 ErrorLog 로 흘린다 — 그 흐름을 로그
	// 파일로 돌린다. 안 그러면 자동 기동 뷰어에서는 패닉 스택이 /dev/null 로 사라진다.
	if viewerLogFile != nil {
		log.SetOutput(viewerLogFile)
	}
	// 신호로 죽는 경우(SIGTERM/SIGINT)도 이유를 남긴다 — "그냥 사라졌다"를 없앤다.
	go func() {
		ch := make(chan os.Signal, 1)
		signal.Notify(ch, syscall.SIGINT, syscall.SIGTERM, syscall.SIGHUP)
		sig := <-ch
		viewerLogWrite("종료 — 신호 " + sig.String() + " 를 받았다")
		if viewerLogFile != nil {
			viewerLogFile.Close()
		}
		os.Exit(0)
	}()
	handle("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write([]byte(servePage()))
	})
	// /whoami — 이 뷰어가 **어느 저장소**를 보고 있는지 밝힌다(온보딩 실측).
	// 포트가 열려 있다는 것만으로 "그 뷰어가 내 저장소를 본다"고 말할 수 없다. 실제로
	// 다른 프로젝트의 뷰어가 같은 기본 포트를 쥐고 있었고, handoff 는 그 주소를 "지금
	// 열어라(선택이 아니다)"로 지시했다 — 사람은 남의 그래프를 자기 것으로 읽는다.
	handle("/whoami", func(w http.ResponseWriter, r *http.Request) {
		abs := viewerRepoAbs()
		w.Header().Set("Content-Type", "application/json")
		// pid 도 밝힌다 — 세션이 **자기가 띄운 뷰어를 끄려면**(gil viewer stop) 누구를
		// 끌지 알아야 한다. 포트만으로는 남의 프로세스를 끄는 사고를 막을 수 없다.
		// id(뿌리 커밋 7자)는 이슈 #110: 경로는 사람이 대조하고, 자동화는 이 값을 대조한다.
		// **화면에 뜨는 값과 같은 값이어야 한다** — 다르면 대조가 성립하지 않는다.
		fmt.Fprintf(w, "{\"repo\":%q,\"id\":%q,\"pid\":%d}\n", abs, repoIdentity(viewerGit), os.Getpid())
	})
	handle("/poll", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.Write([]byte(tipSignature()))
	})
	// /step?sha=<full> — 한 스텝 커밋의 상세 보고서(제목+본문+트레일러) 원문.
	handle("/step", func(w http.ResponseWriter, r *http.Request) {
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
	handle("/approve", func(w http.ResponseWriter, r *http.Request) { pendingAction(w, r, "approve") })
	handle("/reject", func(w http.ResponseWriter, r *http.Request) { pendingAction(w, r, "reject") })
	// POST /interview?chain=  — 사람이 인터뷰 폼을 제출한다(이슈 #33). 본문 = 답변 JSON 배열
	// [{q,type,answer}]. 서버가 이걸 마크다운 기준 문서로 조립해 reference-<chain>.md 로 저장하고,
	// gil interview <chain> --resolve <파일> 을 호출해 레퍼런스를 커밋한다. 파일은 워킹트리에
	// 남아 사람이 열어보고 편집할 수 있다. 127.0.0.1 로컬 전용.
	// POST /prune-approve?target=  — 사람이 삭제를 승인한다(상현님). 승인만으로는 아무것도
	// 지워지지 않는다 — 실행에는 CLI 확인 문구가 더 필요하다. 안전장치를 둘로 나눈 이유는
	// 하나가 뚫려도 다른 하나가 남게 하기 위해서다.
	handle("/prune-approve", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", http.StatusMethodNotAllowed)
			return
		}
		target := r.URL.Query().Get("target")
		if target == "" || strings.ContainsAny(target, " ;&|$`\n") {
			http.Error(w, "bad target", http.StatusBadRequest)
			return
		}
		out, err := gilExec("prune-approve", target, "--by", "viewer")
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
		}
		w.Write(out)
	})
	// POST /prune-withdraw?target= — 요청을 거둔다(이슈 #91). 승인과 달리 사람만의 문이 아니다:
	// 아무것도 지우지 않고 카드만 걷는다. 갇힌 상태에서 빠져나오는 길은 화면에도 있어야 한다.
	handle("/prune-withdraw", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", http.StatusMethodNotAllowed)
			return
		}
		target := r.URL.Query().Get("target")
		if target == "" || strings.ContainsAny(target, " ;&|$`\n") {
			http.Error(w, "bad target", http.StatusBadRequest)
			return
		}
		out, err := gilExec("prune", target, "--withdraw",
			"--reason", "뷰어에서 사람이 요청을 거둠", "--by", "viewer")
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
		}
		w.Write(out)
	})
	handle("/interview", func(w http.ResponseWriter, r *http.Request) {
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
	srv := &http.Server{Addr: addr}
	if viewerLogFile != nil {
		srv.ErrorLog = log.New(viewerLogFile, "http: ", log.LstdFlags)
	}
	if err := srv.ListenAndServe(); err != nil {
		viewerLogWrite("종료 — ListenAndServe: " + err.Error())
		fmt.Fprintln(os.Stderr, "거부: 서버 실패 —", err)
		os.Exit(1)
	}
}

// ── 단일 비행 — 뷰어는 한 번에 하나의 스캔만 돈다 (이슈 #89) ──
//
// 실사용 사고: 뷰어를 띄운 채 27사이클을 연속으로 닫았더니 **같은 git log 자식이 437개**까지
// 쌓여 10코어 머신의 로드가 512 가 됐다. 뷰어는 자기가 만든 포크 폭풍에 막혀 자기 HTTP
// 요청에도 180초 동안 응답하지 못했고, 같은 저장소를 쓰는 gil 명령들이 전부 I/O 대기에
// 갇혔다(그게 #88 의 진짜 원인이었다 — 나는 고아 커밋 스캔을 의심했고 틀렸다).
//
// 병의 이름은 "겹침이 가속되는 양의 피드백"이다: 갱신 트리거마다 새로 fork 하고 앞선 것이
// 끝났는지 보지 않으면, 스캔이 느려질수록 더 많이 겹치고 겹칠수록 더 느려진다.
//
// 처방 셋. (1) **한 번에 하나** — 뮤텍스가 스캔을 직렬화하고, 기다린 요청은 방금 끝난
// 결과를 함께 쓴다. (2) **ref 서명이 같으면 아예 안 돈다** — 바뀌지 않은 그래프를 다시
// 그리는 건 순수한 낭비다. (3) **자식 수 상한** — 어떤 경로로도 저장소에 동시에 달라붙는
// git 이 정해진 수를 못 넘게 한다.
var (
	pageMu    sync.Mutex
	pageCache string
	pageSig   string
)

func servePage() string {
	sig := tipSignature()
	pageMu.Lock()
	defer pageMu.Unlock()
	// 기다리는 동안 앞선 스캔이 같은 서명으로 이미 그려 뒀다면 그걸 쓴다(단일 비행의 핵심).
	if pageCache != "" && pageSig == sig {
		return pageCache
	}
	pageCache = renderHTML(buildGraph(), false)
	pageSig = sig
	return pageCache
}

func tipSignature() string {
	const fs = "\x1f"
	out, err := viewerGit("for-each-ref", "--format=%(refname:short)"+fs+"%(objectname)", "refs/heads/")
	if err != nil {
		return "err"
	}
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	// 로컬 상태도 서명에 넣는다(상현님: 제출해도 아무 일도 안 일어난다). 커밋이 안 바뀌어도
	// **누가 기다리는지·에이전트가 읽었는지**는 바뀐다 — 그게 사람이 가장 보고 싶은 변화다.
	if dir := viewerGitDir(); dir != "" {
		if ents, err := os.ReadDir(filepath.Join(dir, "gil")); err == nil {
			for _, e := range ents {
				n := e.Name()
				if strings.HasPrefix(n, "interview-waiting-") {
					if viewerWaiterActive(strings.TrimPrefix(n, "interview-waiting-")) {
						lines = append(lines, "wait"+fs+n)
					}
					continue
				}
				if n == "interview-seen" {
					if b, err := os.ReadFile(filepath.Join(dir, "gil", n)); err == nil {
						lines = append(lines, "seen"+fs+strings.TrimSpace(string(b)))
					}
				}
			}
		}
	}
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
		// 봉인·대체 표식(이슈 #85). 지우지 않는다 — 흐리게 그리고 표식을 단다. "끝난 것이
		// 끝나 보이고, 뒤집힌 것이 뒤집혀 보이는 것"이 정리의 실체였다(버릴 체인은 없었다).
		mark := ""
		if chainClosedViewer(ch.name) {
			cls += " sealed"
			mark += `<text class="cmark" dy="-34">✓ 봉인</text>`
		}
		if sb := supersededByViewer(ch.name); sb != "" {
			cls += " superseded"
			mark += `<text class="cmark sup" dy="64">⤳ ` + esc(sb) + ` 로 대체됨</text>`
		}
		nodes.WriteString(fmt.Sprintf(
			`<g class="%s" data-chain="%s" transform="translate(%d,%d)">`+
				`<circle r="26"/><text class="cyc" dy="5">%d</text>`+
				`<text class="clabel" dy="48">%s</text>%s%s</g>`,
			cls, esc(ch.name), c.x, c.y, len(ch.cycles), esc(ch.name), head, mark))
	}

	var b strings.Builder
	// 마크업에는 한국어 원문을 그대로 두고 `data-i18n` 만 단다 — JS 가 죽어도 화면이 비지
	// 않는다. 갈아끼움은 applyLang() 이 첫 걸음에서 한다(viewer_i18n.go).
	b.WriteString(`<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title` + i18nAttr("app.title") + `>` + i18nT("app.title") + `</title>
<style>` + css + `</style></head><body>
<header><h1` + i18nAttr("app.h1") + `>` + i18nT("app.h1") + `</h1>
<button id="gohere" class="gohere" title="` + i18nT("head.gohere.title") + `" data-i18n-title="head.gohere.title"` +
		i18nAttr("head.gohere") + `>` + i18nT("head.gohere") + `</button>
<span class="meta"><span` + i18nAttr("head.meta") + i18nArgs(map[string]string{
		"chains": itoa(len(g.chains)), "steps": itoa(g.nodeCount), "tips": itoa(g.tipCount),
	}) + `>체인 ` + itoa(len(g.chains)) + `개 · 스텝 ` + itoa(g.nodeCount) + `개 · 현재위치 ` +
		itoa(g.tipCount) + `개</span> · ` + liveIndicator(static) + workBadge(g, static) + `</span>
<span id="langpick" class="langpick"></span>
<div class="repostamp" title="` + i18nT("head.repo.title") + `" data-i18n-title="head.repo.title"><span` +
		i18nAttr("head.repo") + `>` + i18nT("head.repo") + `</span> <code class="repopath">` +
		esc(viewerRepoAbs()) + `</code> <code class="repoid">#` + esc(repoIdentity(viewerGit)) + `</code></div></header>
<script id="i18ndata" type="application/json">` + i18nPayload() + `</script>
<script id="repodata" type="application/json">` + fmt.Sprintf(`{"repo":%q,"id":%q}`,
		viewerRepoAbs(), repoIdentity(viewerGit)) + `</script>
<main>`)
	// 인터뷰 폼(이슈 #33): 사람 답을 기다리는 인터뷰 요구가 있으면 최상단에 폼을 띄운다.
	// 정적 build(서버 없음)엔 제출할 곳이 없어 감춘다. JS(buildInterviews)가 질문 JSON 을 읽어
	// textarea·라디오·체크박스를 그리고, 제출 시 POST /interview 로 답변을 넘긴다.
	// 삭제 승인 카드 — 비가역 행위는 사람 손에서만 눌린다.
	if !static && len(g.prunes) > 0 {
		b.WriteString(`<section class="pane" id="pane-prune"><h2 class="panehead"` + i18nAttr("pane.prune") + `>` + i18nT("pane.prune") + `</h2><div id="prunes"></div></section>`)
		b.WriteString(`<script id="prunedata" type="application/json">` + prunesJSON(g) + `</script>`)
	}
	// 제출의 **결과**가 화면에 남아야 한다(상현님: 제출해도 아무 일도 안 일어난다). 확정된
	// 기준 문서와, 그 답이 에이전트에게 도달했는지를 지속적으로 보여준다.
	if len(g.references) > 0 {
		b.WriteString(`<section class="pane" id="pane-reference"><h2 class="panehead"` + i18nAttr("pane.reference") + `>` + i18nT("pane.reference") + `</h2><div id="references"></div></section>`)
		b.WriteString(`<script id="referencedata" type="application/json">` + referencesJSON(g) + `</script>`)
	}
	if !static && len(g.interviews) > 0 {
		b.WriteString(`<section class="pane" id="pane-interview"><h2 class="panehead"` + i18nAttr("pane.interview") + `>` + i18nT("pane.interview") + `</h2><div id="interviews"></div></section>`)
		b.WriteString(`<script id="interviewdata" type="application/json">` + interviewsJSON(g) + `</script>`)
	}
	if len(g.chains) == 0 {
		b.WriteString(`<p class="empty"` + i18nAttr("empty") + `>` + i18nT("empty") + `</p>`)
	} else {
		// ── 이 화면 읽는 법(필드테스트) ────────────────────────────────────────────
		// 노드가 무엇을 뜻하는지 모르는 사람이 너무 많았다. 관전 도구는 관전자를 가르치지
		// 않으면 그림일 뿐이다. 맨 위에 접이식 안내를 두되, **처음 온 사람에게는 펼쳐** 둔다
		// (한 번 닫으면 그 브라우저에선 계속 닫힌 채 — localStorage).
		b.WriteString(`<section class="pane" id="pane-guide"><details id="guide"><summary class="panehead">` +
			`<span` + i18nAttr("guide.summary") + `>` + i18nT("guide.summary") + `</span> <span class="gtoggle"` + i18nAttr("guide.toggle") + `>` + i18nT("guide.toggle") + `</span></summary>` +
			`<div class="guide">` +
			`<p` + i18nAttr("guide.intro") + `>` + i18nT("guide.intro") + `</p>` +
			`<ul>` +
			`<li` + i18nAttr("guide.li.chain") + `>` + i18nT("guide.li.chain") + `</li>` +
			`<li` + i18nAttr("guide.li.cycle") + `>` + i18nT("guide.li.cycle") + `</li>` +
			`<li` + i18nAttr("guide.li.step") + `>` + i18nT("guide.li.step") + `</li>` +
			`</ul>` +
			// 글만으로는 한눈에 안 들어온다(상현님) — 실제 그래프와 **같은 색·모양**의 그림 하나.
			// 여기 쓰인 파랑/초록/빨강/주황은 아래 진짜 그래프의 그 색 그대로다.
			`<svg class="gdiagram" viewBox="0 0 700 250" role="img" ` +
			`aria-label="` + i18nT("diag.aria") + `">` +
			`<rect x="8" y="34" width="684" height="150" rx="12" class="gd-chain"/>` +
			`<text x="18" y="26" class="gd-lbl gd-lbl-chain"` + i18nAttr("diag.chain") + `>` + i18nT("diag.chain") + `</text>` +
			`<rect x="24" y="52" width="404" height="116" rx="9" class="gd-cyc"/>` +
			`<text x="34" y="70" class="gd-lbl"` + i18nAttr("diag.cycle1") + `>` + i18nT("diag.cycle1") + `</text>` +
			`<line x1="60" y1="104" x2="140" y2="104" class="gd-edge"/>` +
			`<line x1="140" y1="104" x2="220" y2="104" class="gd-edge"/>` +
			`<line x1="220" y1="104" x2="300" y2="104" class="gd-edge"/>` +
			`<line x1="300" y1="104" x2="380" y2="104" class="gd-edge"/>` +
			`<line x1="60" y1="104" x2="140" y2="148" class="gd-edge gd-dead"/>` +
			`<circle cx="60" cy="104" r="11" class="gd-n"/>` +
			`<circle cx="140" cy="104" r="11" class="gd-n"/>` +
			`<circle cx="220" cy="104" r="11" class="gd-n"/>` +
			`<circle cx="300" cy="104" r="11" class="gd-n"/>` +
			`<circle cx="380" cy="104" r="11" class="gd-n gd-alive"/>` +
			`<circle cx="140" cy="148" r="11" class="gd-n gd-deadn"/>` +
			`<text x="60" y="128" class="gd-k"` + i18nAttr("diag.k.define") + `>` + i18nT("diag.k.define") + `</text>` +
			`<text x="140" y="128" class="gd-k"` + i18nAttr("diag.k.hypothesis") + `>` + i18nT("diag.k.hypothesis") + `</text>` +
			`<text x="220" y="128" class="gd-k"` + i18nAttr("diag.k.verify") + `>` + i18nT("diag.k.verify") + `</text>` +
			`<text x="300" y="128" class="gd-k"` + i18nAttr("diag.k.analyze") + `>` + i18nT("diag.k.analyze") + `</text>` +
			`<text x="380" y="128" class="gd-k"` + i18nAttr("diag.k.success") + `>` + i18nT("diag.k.success") + `</text>` +
			`<text x="176" y="153" class="gd-k gd-kdead"` + i18nAttr("diag.dead") + `>` + i18nT("diag.dead") + `</text>` +
			`<rect x="444" y="52" width="236" height="116" rx="9" class="gd-cyc"/>` +
			`<text x="454" y="70" class="gd-lbl"` + i18nAttr("diag.cycle2") + `>` + i18nT("diag.cycle2") + `</text>` +
			`<line x1="480" y1="104" x2="560" y2="104" class="gd-edge"/>` +
			`<line x1="560" y1="104" x2="640" y2="104" class="gd-edge"/>` +
			`<circle cx="480" cy="104" r="11" class="gd-n"/>` +
			`<circle cx="560" cy="104" r="11" class="gd-n"/>` +
			`<circle cx="640" cy="104" r="11" class="gd-n gd-here"/>` +
			`<path d="M 640 78 l -7 -11 l 14 0 z" class="gd-arrow"/>` +
			`<text x="640" y="46" class="gd-k gd-khere"` + i18nAttr("diag.here") + `>` + i18nT("diag.here") + `</text>` +
			`<text x="480" y="128" class="gd-k"` + i18nAttr("diag.k.define") + `>` + i18nT("diag.k.define") + `</text>` +
			`<text x="560" y="128" class="gd-k"` + i18nAttr("diag.k.hypothesis") + `>` + i18nT("diag.k.hypothesis") + `</text>` +
			`<text x="640" y="128" class="gd-k"` + i18nAttr("diag.k.verifying") + `>` + i18nT("diag.k.verifying") + `</text>` +
			`<text x="18" y="207" class="gd-cap"` + i18nAttr("diag.cap1") + `>` + i18nT("diag.cap1") + `</text>` +
			`<text x="18" y="230" class="gd-cap"` + i18nAttr("diag.cap2") + `>` + i18nT("diag.cap2") + `</text>` +
			`</svg>` +
			`<p class="glegend"` + i18nAttr("guide.legend.marks") + `>` + i18nT("guide.legend.marks") + `</p>` +
			`<p class="glegend"` + i18nAttr("guide.legend.dead") + `>` + i18nT("guide.legend.dead") + `</p>` +
			`<p class="glegend"` + i18nAttr("guide.legend.where") + `>` + i18nT("guide.legend.where") + `</p>` +
			`</div></details></section>`)
		// 탭 없이 세로로: 안내 → 전체맵 → (접힘)체인 → (접힘)사이클 → 스텝 → 디테일.
		// 기본 열림은 **전체맵·스텝 그래프·스텝 디테일** 셋이다(필드테스트: 처음 온 사람은
		// 체인/사이클 그래프보다 "지금 무슨 걸음을 밟고 있나"를 먼저 봐야 한다).
		b.WriteString(`<section class="pane"><h2 class="panehead"><span` + i18nAttr("map.head") + `>` + i18nT("map.head") + `</span> <span id="depthseg" class="depthseg">` +
			depthBtn("chain", "") + depthBtn("cycle", "") + depthBtn("step", " class=\"on\"") +
			`</span></h2><div id="view-map"></div></section>`)
		// 층(main·dev)은 **따로 그리지 않는다**(상현님). 전체맵이 이미 좋은 그림이라,
		// 같은 사실을 두 번 그리면 사람은 어느 쪽을 봐야 하는지부터 고민한다. 데이터만
		// 심고 전체맵이 위에 두 줄로 얹는다 — 체인들이 어디로 모여 어디로 나갔나.
		b.WriteString(`<script id="layergraphdata" type="application/json">` + layerGraphJSON() + `</script>`)
		// **날것의 git 그래프**(상현님). gil 이 아무리 예쁘게 계보를 그려도 그게 실재 브랜치로
		// 갈라지지 않으면 아무 의미가 없다 — 그러니 사람이 직접 점검할 수 있어야 한다.
		// 커밋·부모·브랜치 이름을 그대로 심고, 화면에서 레인 배치로 그린다(ASCII 는 사람이 못 읽는다).
		b.WriteString(`<section class="pane"><details id="det-gitgraph"><summary class="panehead">` +
			`<span` + i18nAttr("pane.gitgraph") + `>` + i18nT("pane.gitgraph") + `</span> <span class="gtoggle"` + i18nAttr("pane.gitgraph.toggle") + `>` + i18nT("pane.gitgraph.toggle") + `</span></summary>` +
			`<p class="hint"` + i18nAttr("pane.gitgraph.hint") + `>` + i18nT("pane.gitgraph.hint") + `</p>` +
			`<div id="gitgraph"></div></details></section>`)
		b.WriteString(`<script id="gitgraphdata" type="application/json">` + gitGraphJSON() + `</script>`)
		b.WriteString(`<section class="pane"><details id="det-chain"><summary class="panehead"><span` + i18nAttr("pane.chaingraph") + `>` + i18nT("pane.chaingraph") + `</span> <span class="gtoggle"` + i18nAttr("pane.unfold") + `>` + i18nT("pane.unfold") + `</span></summary><div id="view-chain">`)
		b.WriteString(fmt.Sprintf(
			`<svg id="graph" viewBox="0 0 %d %d" width="%d" height="%d"><g id="edges">%s</g><g id="nodes">%s</g></svg>`,
			w, h, w, h, edges.String(), nodes.String()))
		b.WriteString(`<p class="hint"` + i18nAttr("pane.chaingraph.hint") + `>` + i18nT("pane.chaingraph.hint") + `</p>`)
		b.WriteString(`</div></details></section>`)
		b.WriteString(`<section class="pane" id="pane-card" hidden><details id="det-cycle"><summary class="panehead"><span` + i18nAttr("pane.cyclegraph") + `>` + i18nT("pane.cyclegraph") + `</span> <span class="gtoggle"` + i18nAttr("pane.unfold") + `>` + i18nT("pane.unfold") + `</span></summary><div id="card"></div></details></section>`)
		b.WriteString(`<section class="pane" id="pane-step" hidden><h2 class="panehead"` + i18nAttr("pane.stepgraph") + `>` + i18nT("pane.stepgraph") + `</h2><div id="stepcard"></div></section>`)
		b.WriteString(`<section class="pane" id="pane-report" hidden><h2 class="panehead"` + i18nAttr("pane.stepdetail") + `>` + i18nT("pane.stepdetail") + `</h2><div id="reportcard"></div></section>`)
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
		return `<span class="meta"` + i18nAttr("head.static") + `>` + i18nT("head.static") + `</span>`
	}
	return `<span id="live"` + i18nAttr("head.live") + `>` + i18nT("head.live") + `</span>`
}

// workBadge — 헤더에 미커밋 작업 요약을 단다. serve(라이브)에서만 의미 있다 —
// static build 는 워킹트리와 무관한 스냅샷이라 뺀다. serve 는 자동 새로고침이라
// 이 배지가 실시간 진행 표시가 되어 "멈춘 듯" 오해를 없앤다(상현님).
func workBadge(g graphView, static bool) string {
	if static || !g.work.dirty {
		return ""
	}
	// 숫자는 자리표시자로 넘기고 문장은 사전이 짓는다 — 어순이 다른 언어에서 조각을 이어붙이면
	// 부서진다. 마크업에 박히는 한국어 원문은 JS 가 죽었을 때의 바닥이다.
	key := "head.work"
	args := map[string]string{"files": itoa(g.work.files)}
	if g.work.added > 0 || g.work.deleted > 0 {
		key = "head.work.diff"
		args["added"] = itoa(g.work.added)
		args["deleted"] = itoa(g.work.deleted)
	}
	return ` · <span class="work"` + i18nAttr(key) + i18nArgs(args) + `>✎ 작업중: ` + esc(g.work.summary()) + `</span>`
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
// lastStepOfCycle — 그 사이클의 마지막 스텝 ref(chain/cycle/step). 없으면 "".
func lastStepOfCycle(g graphView, chain, cycle string) string {
	best := ""
	bestN := -1
	for _, n := range g.allNodes {
		if n.chain != chain || n.cycle != cycle {
			continue
		}
		if k := stepNum(n.step); k > bestN {
			bestN, best = k, n.chain+"/"+n.cycle+"/"+n.step
		}
	}
	return best
}

// cycleEntryParents — 각 사이클의 진입 부모 스텝(AIL #7). 사이클 첫 스텝(가장 낮은 s번호)의
// 커밋 부모 사슬을 거슬러, 다른 사이클/체인에 속한 가장 가까운 gil 스텝을 찾는다. 반환:
// (chain\x01cycle) → "chain/cycle/step". 위상 유도라 Gil-Cycle-Parent 선언이 없어도 잡힌다.
// **부모는 여럿일 수 있다.** open 은 --parent 를 여러 번 받고(Gil-Cycle-Parent 트레일러가
// 그 수만큼 박힌다), 두 갈래에서 나온 것을 한 사이클에서 합치는 건 실제로 있는 일이다.
// 그런데 뷰어는 첫 하나만 싣고 나머지를 버렸다 — 선언한 계보가 그림에서 줄어들면, 사람은
// 자기가 적은 것보다 가난한 나무를 본다(상현님: 부모를 여럿 두는 것도 해보자).
// 첫 번째는 예전과 같은 자리(parent)로 그대로 나가고, 전부는 parents 로 나간다.
func cycleEntryParentsAll(g graphView) map[string][]string {
	one := cycleEntryParents(g)
	out := map[string][]string{}
	first := map[string]viewerNode{}
	for _, n := range g.allNodes {
		if n.cycle == "" || n.step == "" {
			continue
		}
		k := n.chain + "\x01" + n.cycle
		if cur, ok := first[k]; !ok || stepNum(n.step) < stepNum(cur.step) {
			first[k] = n
		}
	}
	for k, def := range first {
		seen := map[string]bool{}
		add := func(ref string) {
			if ref != "" && !seen[ref] {
				seen[ref] = true
				out[k] = append(out[k], ref)
			}
		}
		add(one[k]) // 유도·선언 중 이긴 것이 늘 첫째다(옛 동작 그대로)
		for _, pc := range def.cycleParents {
			pc = strings.TrimSpace(pc)
			if pc == "" {
				continue
			}
			if tip := lastStepOfCycle(g, def.chain, pc); tip != "" {
				add(tip)
			} else if anchor := cycleAnchorStep(g, def.chain, pc); anchor != "" {
				add(anchor)
			}
		}
	}
	return out
}

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
		// **선언이 먼저다**(상현님 실사용: 사이클 분기가 사이클 그래프에서 일직선으로 보였다).
		// 옛 순서는 위상(커밋 조상)을 먼저 보고 없을 때만 선언을 썼는데, 사이클 계보에서
		// 위상은 부수적이다: 새 사이클을 열 때 HEAD 가 어느 브랜치에 서 있었느냐가 그대로
		// 커밋 조상이 된다. cy1 에서 갈라진 cy2·cy3 를 차례로 열면 cy3 의 커밋 조상은 cy2 라,
		// 진짜 분기(cy1 → cy2, cy1 → cy3)가 일직선(cy1 → cy2 → cy3)으로 그려졌다.
		// --parent 는 open 이 **강제·검증**하는 선언이다(부모가 닫혀 있어야 통과한다) —
		// 사람이 한 말이 아니라 문법이 받은 사실이다. 그러니 이쪽이 먼저다.
		for _, pc := range def.cycleParents {
			pc = strings.TrimSpace(pc)
			if pc == "" {
				continue
			}
			// 선언은 사이클 id 또는 체인명이다 — 그 사이클의 마지막 스텝을 진입점으로 삼는다.
			if tip := lastStepOfCycle(g, def.chain, pc); tip != "" {
				out[k] = tip
				break
			}
		}
		if out[k] != "" {
			continue
		}
		// def 의 커밋 부모에서 시작해, 다른 사이클의 gil 스텝을 만날 때까지 거슬러 오른다.
		seen := map[string]bool{}
		var walk func(sha string) string
		walk = func(sha string) string {
			if seen[sha] {
				return ""
			}
			seen[sha] = true
			if s, ok := stepBySHA[sha]; ok && !(s.chain == def.chain && s.cycle == def.cycle) {
				// **체인을 넘는 진입은 계승일 때만.** 체인 계보에 세운 판정(#53)을 사이클에도
				// 그대로 적용한다: 앞 체인이 닫힌 끝에서 태어났을 때만 이어받음이다.
				// 안 그러면 층에서 난 시조들이 전부 "첫 체인의 마지막 스텝에서 났다"고 그려진다 —
				// dev 로 합류한 앞 체인이 커밋 조상에 들어오기 때문이다(실측: 여섯 체인 중
				// 다섯이 같은 스텝을 부모로 물고 있었다). 조상관계는 사실이지만 계승은 아니다.
				if s.chain != def.chain && g.parents[def.chain] != s.chain {
					return "" // 나란히 간 것이다 — 없는 계보를 그리느니 안 그린다
				}
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
	for k, refs := range cycleEntryParentsAll(g) {
		chain, cycle, _ := strings.Cut(k, "\x01")
		for _, parentRef := range refs { // 부모가 둘이면 **둘 다** 진출을 갖는다
			out[parentRef] = append(out[parentRef], chain+"/"+cycle)
		}
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
	cycleEntryAll := cycleEntryParentsAll(g)
	exits := cycleExits(g) // 진출은 추측이 아니라 사실로만 그린다(이슈 #72)
	var sb strings.Builder
	sb.WriteString("{")
	for i, ch := range g.chains {
		if i > 0 {
			sb.WriteString(",")
		}
		c := pos[ch.name]
		// 봉인·대체 여부를 함께 싣는다(이슈 #85) — 끝난 것이 끝나 보이고, 뒤집힌 것이
		// 뒤집혀 보이게. 뷰어는 지우지 않는다: 흐리게 그리고 표식을 단다.
		sb.WriteString(fmt.Sprintf(`%q:{"x":%d,"y":%d,"closed":%t,"supersededBy":%q,"cycles":[`,
			ch.name, c.x, c.y, chainClosedViewer(ch.name), supersededByViewer(ch.name)))
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
			cycPars := cycleEntryAll[ch.name+"\x01"+cy.name]
			// 측정의 좌표(이슈 #79·#81) — 뷰어 사이클 카드가 "어디서/무엇을" 을 함께 보인다.
			ds, sj := cycleCoordOf(ch.name, cy.name)
			sb.WriteString(fmt.Sprintf(`{"name":%q,"steps":%d,"status":%q,"here":%t,"parent":%q,"parents":%s,"dataset":%s,"subject":%s,"nodes":[`,
				cy.name, len(cy.steps), cy.status(), here, cycPar, jsonStrings(cycPars), jsonStrings(ds), jsonStrings(sj)))
			// 정정(AIL #12 → 정정은 분기다). 뷰어도 두 사실을 보여야 한다: 이 스텝이 무엇을
			// 정정했나(⟲), 그리고 이 스텝은 대체됐나(구버전 가지 — 대상뿐 아니라 자손 전부).
			// 텍스트 그래프에만 있고 뷰어엔 없어서, 정작 사람이 보는 화면에서 두 판본이
			// 나란히 살아있는 것처럼 보였다.
			tuples := make([][4]string, 0, len(cy.steps))
			supBy := map[string]string{}
			for _, s := range cy.steps {
				tuples = append(tuples, [4]string{s.chain + "\x01" + s.cycle, s.step, s.parent, s.supersedes})
				if s.supersedes != "" {
					supBy[s.supersedes] = s.step
				}
			}
			goneC := supersededIDs(tuples)
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
				if n.supersedes != "" {
					sb.WriteString(fmt.Sprintf(`,"supersedes":%q`, n.supersedes))
				}
				if goneC[stepKey(n.chain, n.cycle, n.step)] {
					// 직접 정정된 놈은 누가 대체했는지까지, 그 자손은 "구버전 가지"로만.
					sb.WriteString(fmt.Sprintf(`,"gone":true,"goneBy":%q`, supBy[n.step]))
				}
				// 목적 각인과 회고(상현님) — 카드 툴팁에서 계보가 읽히게.
				if n.advances != "" {
					sb.WriteString(fmt.Sprintf(`,"advances":%q`, n.advances))
				}
				if n.toward != "" || n.nextDesign != "" {
					sb.WriteString(fmt.Sprintf(`,"toward":%q,"nextDesign":%q`, n.toward, n.nextDesign))
				}
				// 설계 고정과 그 결과(이슈 #76) — 가설 카드에 ⚙, 깨진 verify 에 ⚠.
				if n.plan != "" {
					sb.WriteString(fmt.Sprintf(`,"plan":%q`, n.plan))
				}
				if n.planOutcome != "" {
					sb.WriteString(fmt.Sprintf(`,"planOutcome":%q,"planDiff":%q`, n.planOutcome, n.planDiff))
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

// gitGraphJSON — **git 자신의 그래프**를 그대로 넘긴다(해석 없이): 커밋 sha·부모들·ref
// 이름·제목. gil 스텝인지도 함께 실어 화면에서 구분한다.
// layerGraphJSON — **층 그래프**의 데이터 (main-dev-chain, 2026-07-31).
//
// git 그래프가 "실재가 무엇인가"를 날것으로 보여준다면, 층 그래프는 "그 실재가 **어느 층의
// 일인가**"를 보여준다. 두 그림은 같은 커밋을 그리되 세로축이 다르다: git 그래프의 레인은
// 위상이 정하고, 층 그래프의 레인은 **선언**이 정한다(체인 트레일러·머지 대상·배포).
//
// 왜 선언인가. 배포 머지가 일어난 뒤 main 은 모든 커밋을 조상으로 갖는다 — 위상만 보면
// 전부 main 의 일이 된다. 그러나 "로그인 체인의 s3" 은 배포됐다고 해서 대문의 일이 되지
// 않는다. 어느 층에서 벌어진 일인가는 그 일이 태어날 때 선언된 사실이다.
func layerGraphJSON() string {
	// **--all 이 아니라 브랜치·태그다**(이슈 #100③). --all 은 refs/gil/global 까지 끌어와,
	// 존재·기억 커밋들이 대문 레일에 이어 그려진다 — main 이 대문 끝에서 멈추지 않은 것처럼
	// 읽힌다. 이 그림은 **작업의 나무**를 보는 자리이고, 존재는 브랜치에 살지 않는다.
	out, err := viewerGit("log", "--branches", "--tags", "--topo-order", "-n", "400",
		"--format=%H\x1f%P\x1f%D\x1f%s\x1f"+
			"%(trailers:key=Gil-Chain,valueonly)\x1f"+
			"%(trailers:key=Gil-Kind,valueonly)\x1f"+
			"%(trailers:key=Gil-Merge-Into,valueonly)\x1f"+
			"%(trailers:key=Gil-Deploy,valueonly)\x1f"+
			"%(trailers:key=Gil-Chain-Orphan,valueonly)\x1f"+
			"%(trailers:key=Gil-Intake,valueonly)\x1e")
	if err != nil {
		return `{"lanes":[],"rows":[]}`
	}
	// 배포 마커의 귀속(이슈 #108). 층 그림은 마커를 **못 찾았을 때에도** 그려야 한다 —
	// 옛 동작은 귀속 실패를 침묵으로 처리해, 배포가 아예 없었던 것처럼 보였다.
	// 여기서 함께 실어 보내면 화면이 "어느 잎에서 나갔나"와 "그걸 모른다"를 가려 말한다.
	// 마커가 하나도 없는 저장소가 대부분이라, 표는 **처음 필요할 때** 긁는다.
	var dattr map[string]string
	dattrOf := func(sha string) string {
		if dattr == nil {
			dattr = deployAttributions(viewerGit, "--branches", "--tags")
		}
		return dattr[sha]
	}
	type row struct{ sha, parents, refs, subj, layer, deploy, deployAt string }
	var rows []row
	seen := map[string]bool{}
	// 체인 → **실제로 갈라진 dev 커밋**(chain-root 의 첫 부모). 선언(Gil-Chain-Orphan: dev)만
	// 보고 "모두 dev 팁에서 갈라졌다"고 그리면, dev 가 커밋을 쌓은 뒤에 난 체인이 맨 앞에서
	// 갈라진 것처럼 보인다 — 그림이 없는 동시성을 만든다(상현님, 실사용 관전). 자리는 선언이
	// 아니라 사실이 정한다: 어느 층의 일인가는 선언이, 어디서 갈라졌나는 커밋 부모가.
	devRoots := map[string]string{}
	var chainOrder []string
	for _, rec := range strings.Split(string(out), "\x1e") {
		rec = strings.Trim(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		f := strings.SplitN(rec, "\x1f", 10)
		if len(f) < 10 {
			continue
		}
		chain := strings.TrimSpace(f[4])
		kind := strings.TrimSpace(f[5])
		into := strings.TrimSpace(f[6])
		deploy := strings.TrimSpace(f[7])
		// dev 에서 났다는 **선언**. 이게 있어야 전체맵이 그 체인의 출발을 층에 묶는다 —
		// 묶지 않으면 시조가 화면에서 orphan(끊긴 계보)처럼 보인다. 시조와 미아는 다르다.
		if strings.TrimSpace(f[8]) == devBranchName && chain != "" {
			fork := ""
			if ps := strings.Fields(f[1]); len(ps) > 0 {
				fork = first9(ps[0])
			}
			devRoots[chain] = fork
		}
		// 선언이 층을 정한다. 순서가 곧 우선순위다 — 합류는 **받는 쪽**의 일이고(그래서
		// --into 가 먼저), 그다음이 그 커밋이 속한 체인이다.
		// **앞머리는 층의 것이다**(이슈 #100①·#102). intake·개시 인터뷰 커밋은 `Gil-Chain`
		// 에 **슬러그**를 달고 있어서, 옛 판정은 그 슬러그를 체인으로 보고 제 레인을 만들었다.
		// 그 이름의 브랜치는 어디에도 없다 — 사람은 실존하지 않는 가지를 읽게 된다(실사용에서
		// 그 레인을 dev 로 오해해 층 위반으로 두 번 읽었다). 앞머리는 체인보다 먼저 있는 것이라
		// 어느 체인의 몸도 아니고, 그 자리는 dev 다.
		intake := strings.TrimSpace(f[9]) != ""
		layer := "main"
		switch {
		case into != "":
			layer = into
		case intake:
			layer = devBranchName
		case chain != "":
			layer = chain
		case kind == "dev-root" || deploy != "":
			layer = devBranchName
		}
		if layer != "main" && layer != devBranchName && !seen[layer] {
			seen[layer] = true
			chainOrder = append(chainOrder, layer)
		}
		var ps []string
		for _, p := range strings.Fields(f[1]) {
			ps = append(ps, fmt.Sprintf("%q", first9(p)))
		}
		dAt := ""
		if deploy != "" {
			dAt = dattrOf(strings.TrimSpace(f[0]))
		}
		rows = append(rows, row{first9(f[0]), "[" + strings.Join(ps, ",") + "]",
			strings.TrimSpace(f[2]), f[3], layer, deploy, dAt})
	}
	// 레인 순서: 대문이 맨 위, 그다음 층, 그 아래 체인들(오래된 것부터 — git log 는 최신부터
	// 오므로 뒤집는다). 사람이 그린 그림과 같은 순서다: main / dev / chain…
	lanes := []string{"main", devBranchName}
	for i := len(chainOrder) - 1; i >= 0; i-- {
		lanes = append(lanes, chainOrder[i])
	}
	var sb strings.Builder
	sb.WriteString(`{"lanes":[`)
	for i, l := range lanes {
		if i > 0 {
			sb.WriteString(",")
		}
		sb.WriteString(fmt.Sprintf("%q", l))
	}
	// 갈라진 자리와 층의 순서는 **CLI 와 같은 자에게 묻는다**(devLayerFacts). 화면과 터미널이
	// 서로 다른 답을 하면, 사람은 어느 쪽을 믿을지부터 고민한다 — 뷰어만 고치는 건 반쪽이다.
	lay := devLayerFacts(func(a ...string) ([]byte, error) { return viewerGit(a...) })
	sb.WriteString(`],"devroots":{`)
	{
		// 층에서 난 체인 = **갈라진 자리가 층 위인** 체인. 선언(Gil-Chain-Orphan)만 보면
		// --parallel-with 로 연 병렬 트랙이 빠진다 — 그건 형제와 같은 dev 커밋에서 갈라지는데
		// 시조 선언은 안 단다. 그러면 층에서 난 체인이 화면에서 미아로 선다.
		// (선언은 했는데 실재가 층 밖이면 그대로 실어 보낸다 — fsck 가 짚을 거짓이다.)
		pick := map[string]string{}
		for c, fork := range lay.forks {
			if _, on := lay.step[fork]; on {
				pick[c] = fork
			}
		}
		for c, fork := range devRoots {
			if _, ok := pick[c]; !ok {
				if f, ok2 := lay.forks[c]; ok2 {
					fork = f
				}
				pick[c] = fork
			}
		}
		var dr []string
		for c := range pick {
			dr = append(dr, c)
		}
		sort.Strings(dr)
		for i, c := range dr {
			if i > 0 {
				sb.WriteString(",")
			}
			sb.WriteString(fmt.Sprintf("%q:%q", c, pick[c]))
		}
	}
	// devorder — dev 층이 산 순서(첫 부모 사슬, 오래된 것부터, 층이 열린 커밋에서 자른다).
	// 전체맵이 출발·합류를 이 순서대로 왼쪽→오른쪽에 놓고, 커밋 하나하나를 점으로 찍는다.
	sb.WriteString(`},"devorder":[`)
	for i, s := range lay.order {
		if i > 0 {
			sb.WriteString(",")
		}
		sb.WriteString(fmt.Sprintf("%q", s))
	}
	sb.WriteString(`],"rows":[`)
	for i, r := range rows {
		if i > 0 {
			sb.WriteString(",")
		}
		sb.WriteString(fmt.Sprintf(`{"sha":%q,"parents":%s,"refs":%q,"subj":%q,"layer":%q,"deploy":%q,"deployAt":%q}`,
			r.sha, r.parents, r.refs, r.subj, r.layer, r.deploy, r.deployAt))
	}
	sb.WriteString(`]}`)
	return sb.String()
}

func gitGraphJSON() string {
	// --topo-order: 날짜순으로 섞으면 한 가지의 커밋들이 다른 가지 사이사이에 끼어 그림이
	// 읽히지 않는다. 위상 순서로 묶어야 "이 가지가 여기서 갈라졌다"가 눈에 들어온다.
	// 브랜치·태그만 — refs/gil/global(존재·기억)은 작업의 나무가 아니다(이슈 #100③).
	out, err := viewerGit("log", "--branches", "--tags", "--topo-order", "-n", "400",
		"--format=%H\x1f%P\x1f%D\x1f%s\x1f"+
			"%(trailers:key=Gil-Chain,valueonly)\x1f"+
			"%(trailers:key=Gil-Kind,valueonly)\x1f"+
			"%(trailers:key=Gil-Merge-Into,valueonly)\x1f"+
			"%(trailers:key=Gil-Deploy,valueonly)\x1f"+
			"%(trailers:key=Gil-Intake,valueonly)\x1e")
	if err != nil {
		return "[]"
	}
	gil := map[string]bool{}
	for _, n := range viewerCollectNodes() {
		gil[n.full] = true
	}
	type rec struct{ sha, full, parents, refs, subj, layer string }
	var rows []rec
	firstParent := map[string]string{}
	for _, r := range strings.Split(string(out), "\x1e") {
		r = strings.Trim(r, "\n")
		if strings.TrimSpace(r) == "" {
			continue
		}
		f := strings.SplitN(r, "\x1f", 9)
		if len(f) < 9 {
			continue
		}
		var ps []string
		for _, p := range strings.Fields(f[1]) {
			ps = append(ps, fmt.Sprintf("%q", first9(p)))
		}
		if len(ps) > 0 {
			firstParent[first9(f[0])] = strings.Trim(ps[0], `"`)
		}
		// 층 판정은 layerGraphJSON 과 **같은 규칙**이다(합류는 받는 쪽의 일 → --into 가 먼저).
		// 두 그림이 같은 커밋을 다른 층으로 치면 나란히 놓을 이유가 없어진다.
		layer := ""
		switch chain, kind, into, deploy, intake :=
			strings.TrimSpace(f[4]), strings.TrimSpace(f[5]), strings.TrimSpace(f[6]),
			strings.TrimSpace(f[7]), strings.TrimSpace(f[8]); {
		case into != "":
			layer = into
		case intake != "": // 앞머리는 층의 것 — 슬러그로 가짜 레인을 만들지 않는다(이슈 #100①)
			layer = devBranchName
		case chain != "":
			layer = chain
		case kind == "dev-root" || deploy != "":
			layer = devBranchName
		}
		rows = append(rows, rec{first9(f[0]), strings.TrimSpace(f[0]), "[" + strings.Join(ps, ",") + "]",
			strings.TrimSpace(f[2]), f[3], layer})
	}
	// 트레일러가 없는 평범 커밋은 **첫 부모의 층을 물려받는다** — 체인 브랜치 위의 평범
	// 커밋은 그 체인의 일이고, dev 위의 평범 커밋은 층의 일이다. 안 물려주면 그것들이 전부
	// main 으로 떨어져, 대문 레인에 남의 커밋이 줄줄이 선다.
	byIdx := map[string]int{}
	for i, r := range rows {
		byIdx[r.sha] = i
	}
	for i := len(rows) - 1; i >= 0; i-- { // rows 는 최신부터 — 오래된 것부터 물려준다
		if rows[i].layer != "" {
			continue
		}
		if j, ok := byIdx[firstParent[rows[i].sha]]; ok {
			rows[i].layer = rows[j].layer
		}
	}
	var sb strings.Builder
	sb.WriteString("[")
	for i, r := range rows {
		if i > 0 {
			sb.WriteString(",")
		}
		layer := r.layer
		if layer == "" {
			layer = "main"
		}
		sb.WriteString(fmt.Sprintf(`{"sha":%q,"parents":%s,"refs":%q,"subj":%q,"gil":%t,"layer":%q}`,
			r.sha, r.parents, r.refs, r.subj, gil[r.full], layer))
	}
	sb.WriteString("]")
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
	stepOf := map[string]viewerNode{}
	for _, n := range g.allNodes {
		stepOf[n.sha] = n
	}
	// **체인의 기준선**(chain-root·인터뷰·기준문서 등 — 그 체인의 것이지만 스텝은 아닌 커밋).
	// 여기서 난 사이클이 정석 발아다(이슈 #104).
	chainBase := chainLevelCommits()
	// nearestStep — sha 조상에서 가장 가까운 gil 스텝 sha 들(비-스텝은 뚫고 올라감).
	//
	// **체인을 넘는 엣지는 계승일 때만.** 체인 계보에 세운 판정(#53)을 전체맵의 선에도 그대로
	// 적용한다. 안 그러면 나란히 간 체인이 조상으로 걸린다: 앞 체인이 dev 로 합류한 뒤 열린
	// 사이클은 그 체인의 스텝을 커밋 조상으로 갖기 때문이다(실측: notification/c1/s1 이
	// user-authentication/c3/s9 과 followup/c1/s5 두 곳에서 이어받은 것으로 그려졌고,
	// c2/s1 은 병렬 트랙 observability 의 스텝에서 났다고 그려졌다).
	//
	// 버리기만 하면 **진짜 부모까지 잃는다** — 그 자리를 지나 더 올라가야 같은 체인의 앞
	// 스텝이 나온다. 그래서 멈추지 않고 계속 거슬러 오른다.
	var nearestStep func(own, sha string, seen map[string]bool) []string
	nearestStep = func(own, sha string, seen map[string]bool) []string {
		if st, ok := stepOf[sha]; ok {
			if st.chain == own || g.parents[own] == st.chain {
				return []string{sha} // 같은 체인이거나, 진짜 계승이다
			}
			// 나란히 간 체인 — 이 스텝은 부모가 아니다. 그 위로 계속 올라간다.
		}
		// **자기 체인의 기준선에서 멈춘다**(이슈 #104). 여기까지 왔다는 것은 이 사이클이
		// 체인의 기준선(chain-root·인터뷰·기준문서)에서 곧장 났다는 뜻이다 — 즉 **정석 발아**다.
		// 옛 코드는 이 커밋들을 뚫고 더 올라가, 앞 사이클의 스텝에 붙거나(건너뛴 사이클이
		// 있으면 "그 성공의 직계 후속"으로 거짓 주장) 아무것도 못 찾고 선을 안 그렸다.
		// 그래서 화면에서 **정석 발아는 벌점(선 없음), 우연히 스텝 위에 얹힌 발아는 가산점**
		// 이 됐다 — gil 이 가르치는 정석과 시각 신호가 정확히 역전됐다.
		// 다만 **이어받음을 선언한 체인은 예외**다. 시조(--from 없음)의 기준선 너머에는 층과
		// 앞 체인이 있을 뿐이라 그 자리를 지나가면 없는 계승을 그리게 되지만, `--from <앞 체인>`
		// 을 선언한 체인의 기준선 너머에는 **바로 그 앞 체인의 끝**이 있다 — 그건 진짜 계승이고
		// 그리는 것이 옳다. 처음엔 이 갈래 없이 막았다가 경계 넘는 전수를 끊어 먹었다.
		if chainBase[sha] == own && g.parents[own] == "" {
			return nil
		}
		if seen[sha] {
			return nil
		}
		seen[sha] = true
		var out []string
		src := nonStepParents[sha]
		if st, ok := stepOf[sha]; ok {
			src = st.gitParents // 스텝 커밋이지만 계승이 아니어서 뚫고 지나가는 경우
			_ = st
		}
		for _, p := range src {
			out = append(out, nearestStep(own, p, seen)...)
		}
		return out
	}
	// 정정으로 대체된 구버전 가지 — 전체맵에서도 흐려야 한다. 사이클 카드에서만 흐리면
	// 첫 화면(전체맵)에는 두 판본이 나란히 살아있는 것처럼 보인다.
	dagTuples := make([][4]string, 0, len(g.allNodes))
	for _, n := range g.allNodes {
		dagTuples = append(dagTuples, [4]string{n.chain + "\x01" + n.cycle, n.step, n.parent, n.supersedes})
	}
	dagGone := supersededIDs(dagTuples)
	// 사이클 첫 스텝에만 붙인다 — 선언은 "이 사이클이 무엇을 잇는가"이지 스텝마다의 것이 아니다.
	declaredCycleParents := map[string][]string{}
	firstOfCycle := map[string]string{}
	for _, n := range g.allNodes {
		k := n.chain + "\x01" + n.cycle
		if cur, ok := firstOfCycle[k]; !ok || stepNum(n.step) < stepNum(cur) {
			firstOfCycle[k] = n.step
		}
	}
	for k, refs := range cycleEntryParentsAll(g) {
		declaredCycleParents[k] = refs
	}
	shaOfStepRef := map[string]string{}
	for _, n := range g.allNodes {
		shaOfStepRef[n.chain+"/"+n.cycle+"/"+n.step] = n.sha
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
			ps = append(ps, nearestStep(n.chain, p, seenP)...)
		}
		// **정석 발아를 무계보와 구분한다**(이슈 #104(b)). 부모 스텝이 없더라도, 커밋 부모가
		// 자기 체인의 기준선이면 그건 미아가 아니라 "체인에서 곧장 난" 것이다. 화면이 둘을
		// 같게 그리면 사람은 "orphan 인데 git 엔 부모가 있네?"라는 불신을 갖는다(실제로 그렇게
		// 발견됐다). 아무것도 안 그리는 대신 발아 표식을 준다.
		sprout := false
		if len(ps) == 0 && g.parents[n.chain] == "" {
			for _, p := range n.gitParents {
				if chainBase[p] == n.chain {
					sprout = true
					break
				}
			}
		}
		sb.WriteString(fmt.Sprintf(
			`{"sha":%q,"chain":%q,"cycle":%q,"step":%q,"kind":%q,"outcome":%q,"here":%t,"sprout":%t,"parents":[`,
			n.sha, n.chain, n.cycle, n.step, n.kind, n.outcome, nhere, sprout))
		for j, p := range ps {
			if j > 0 {
				sb.WriteString(",")
			}
			sb.WriteString(fmt.Sprintf("%q", p))
		}
		sb.WriteString(`],"dparents":[`)
		// 선언된 사이클 부모(open --parent) 중 **커밋 위상에 없는 것**. 전체맵은 커밋 부모로
		// 그리므로, 두 갈래를 합친 사이클의 둘째 부모가 여기선 통째로 빠졌다(상현님: c4 의
		// 부모가 하나다). 선언도 사실이다 — 다만 위상이 아니라 선언이라, 파선으로 구분해 그린다.
		if n.step != "" && firstOfCycle[n.chain+"\x01"+n.cycle] == n.step {
			have := map[string]bool{}
			for _, p := range ps {
				have[p] = true
			}
			j := 0
			for _, ref := range declaredCycleParents[n.chain+""+n.cycle] {
				if sha, ok := shaOfStepRef[ref]; ok && !have[sha] && sha != n.sha {
					if j > 0 {
						sb.WriteString(",")
					}
					sb.WriteString(fmt.Sprintf("%q", sha))
					j++
				}
			}
		}
		sb.WriteString(fmt.Sprintf(`],"subj":%q`, n.subject))
		if n.supersedes != "" {
			sb.WriteString(fmt.Sprintf(`,"supersedes":%q`, n.supersedes))
		}
		if dagGone[n.chain+"\x01"+n.cycle+"\x01"+n.step] {
			sb.WriteString(`,"gone":true`)
		}
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

// referencesJSON — 확정된 기준 문서들을 JS 로. 상태(읽음·대기)까지 함께 넘긴다 — 사람이
// "내 답이 어디까지 갔나"를 화면에서 알 수 있게.
func referencesJSON(g graphView) string {
	var sb strings.Builder
	sb.WriteString("[")
	for i, r := range g.references {
		if i > 0 {
			sb.WriteString(",")
		}
		cb, _ := json.Marshal(r.chain)
		tb, _ := json.Marshal(r.text)
		shb, _ := json.Marshal(r.sha)
		sb.WriteString(fmt.Sprintf(`{"chain":%s,"sha":%s,"seen":%t,"waiting":%t,"text":%s}`,
			cb, shb, r.seen, r.wait, tb))
	}
	sb.WriteString("]")
	return sb.String()
}

// prunesJSON — 승인 대기 중인 삭제 요청들.
func prunesJSON(g graphView) string {
	var sb strings.Builder
	sb.WriteString("[")
	for i, p := range g.prunes {
		if i > 0 {
			sb.WriteString(",")
		}
		tb, _ := json.Marshal(p.target)
		bb, _ := json.Marshal(p.body)
		shb, _ := json.Marshal(p.sha)
		sb.WriteString(fmt.Sprintf(`{"target":%s,"sha":%s,"body":%s}`, tb, shb, bb))
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
padding:12px 20px;display:flex;align-items:baseline;gap:16px;z-index:9;flex-wrap:wrap}
/* 이 화면이 보는 저장소(이슈 #110). 포트가 저장소 사이를 떠도는데 화면에 정체가 없으면,
   사람은 남의 그래프를 자기 것으로 읽는다 — 한 줄이면 그 사고 전체가 예방된다. */
.repostamp{flex-basis:100%;color:var(--dim);font-size:11px;margin-top:2px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.repostamp code{font-size:11px}
.repostamp .repopath{color:var(--fg)}
.repostamp .repoid{color:var(--dim)}
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
.cnode.sealed circle{stroke:var(--dim);stroke-dasharray:4 3}
.cnode.sealed .cyc{fill:var(--dim)}
.cnode.sealed .clabel{fill:var(--dim);opacity:.75}
.cnode .cmark{font-size:10px;font-weight:700;fill:var(--dim);text-anchor:middle}
.cnode .cmark.sup{fill:#f59e0b}
.cnode.superseded circle{stroke:#f59e0b}
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
/* 둘째 부모 — 사실이되 나무의 줄기는 아니다(파선으로 함께 그린다). */
.cyedge.second{stroke-dasharray:5 4;opacity:.7}
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
.prunecard{margin:4px 16px 16px;padding:14px 18px;background:var(--card,var(--bg));border:1px solid #e0574a;border-radius:10px}
.prunehead{font-size:13px;color:#e0574a;font-weight:700;margin-bottom:8px}
.prunebody{white-space:pre-wrap;font-size:12px;color:var(--dim);margin-bottom:12px;max-height:260px;overflow:auto}
.prunebtn{font:inherit;font-size:13px;font-weight:700;padding:8px 18px;border-radius:7px;cursor:pointer;border:1px solid #e0574a;background:transparent;color:#e0574a}
.prunebtn.armed{background:#e0574a;color:#fff}  /* 두 번째 클릭을 기다리는 상태가 눈에 보인다(이슈 #96) */
#pane-prune .panehead{color:#e0574a}
.refcard{margin:4px 16px 10px;padding:10px 14px;background:var(--card,var(--bg));border:1px solid var(--line);border-radius:10px}
.refcard{position:relative}
.refsum{font-size:12px;color:var(--dim);cursor:pointer;list-style:none}
.refsum::-webkit-details-marker{display:none}
.refsum::before{content:"▸ ";color:var(--node)}
details[open]>.refsum::before{content:"▾ "}
.refx{position:absolute;top:8px;right:10px}
.refbody{white-space:pre-wrap;font-size:12px;color:var(--dim);border-top:1px solid var(--line);padding-top:10px;margin-top:8px;max-height:280px;overflow:auto}
.refjust{font-size:12px;color:#2dd4bf;font-weight:700;margin:0 0 8px}
#pane-reference .panehead{color:#2dd4bf}
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
/* 화면 언어 토글 — 헤더 끝에 조용히. 관전자가 자기 언어를 못 찾으면 이 화면은 그림일 뿐이다. */
.langpick{ margin-left:auto; }
.langsel{ font:12px system-ui,sans-serif; padding:3px 6px; border-radius:6px;
  border:1px solid var(--line,#ccc); background:transparent; color:inherit; cursor:pointer; }
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
/* 발아 스텁 — 체인 기준선에서 곧장 난 사이클(이슈 #104). 흐린 점선: 부모 스텝은 없지만
   미아도 아니다. 이 구분이 없으면 정석 발아가 화면에서 벌점을 받는다. */
.dag .dedge.sprout{stroke:var(--dim);stroke-width:1.5;stroke-dasharray:2 3;opacity:.55}
.dag .sproutcap{fill:var(--dim);opacity:.55}
.dag .dnode{cursor:pointer}
.dag .dnode circle{fill:var(--node);stroke:var(--bg);stroke-width:1.5}
.dag .dnode.k-dead circle{fill:#ff6b6b}
.dag .dnode.k-alive.leaf circle{fill:#3ddc84}
.dag .dnode.k-pending circle{fill:#ffd166}
.dag .dnode.here circle{stroke:var(--here);stroke-width:2.5}
.dag .dnode .headarrow{fill:var(--here)}
.dag .dnode.deployed circle{stroke:#2dd4bf;stroke-width:2.5}
.cardwarn{margin:10px 16px;padding:8px 12px;border:1px solid #f59e0b;border-radius:8px;color:#f59e0b;font-size:12px;white-space:pre-wrap}
.cardwarn.err{border-color:#e0574a;color:#e0574a}
.gohere{margin-left:auto;font:inherit;font-size:12px;padding:4px 12px;border-radius:7px;cursor:pointer;
 border:1px solid var(--here);background:transparent;color:var(--here)}
.gohere:hover{background:var(--here);color:var(--bg)}
.snode.working circle{fill:none;stroke:var(--here);stroke-dasharray:5 4;stroke-width:2.5}
.snode.working .sid,.snode.working .skind{fill:var(--here)}
.stepedge.work{stroke:var(--here);stroke-dasharray:5 4;stroke-width:2}
.snode.flash circle{animation:gilflash 1.4s ease-out}
@keyframes gilflash{0%{stroke-width:2.5}30%{stroke-width:7}100%{stroke-width:2.5}}
.planbadge{font-size:10px;font-weight:700;fill:var(--dim);text-anchor:middle;pointer-events:none}
.planbadge.broke{fill:#f59e0b}
/* 요청 철회 — 승인 옆의 낮은 무게 버튼(아무것도 지우지 않는다, 이슈 #91) */
.prunewd{margin-left:8px;font:inherit;font-size:12px;padding:5px 12px;border-radius:7px;cursor:pointer;
 border:1px solid var(--line);background:transparent;color:var(--dim)}
.prunewd:hover{border-color:var(--fg);color:var(--fg)}
/* 정정(AIL #12) — ⟲정정한 스텝은 호박색 표식, 대체된 구버전 가지는 통째로 흐리게.
   지우는 게 아니라 '살아있지 않다'를 보이는 것이다: 이력은 그대로 남는다. */
.supbadge{font-size:10px;font-weight:700;fill:#f59e0b;text-anchor:middle;pointer-events:none}
.supbadge.gone{fill:var(--dim)}
.snode.gone{opacity:.42}
.snode.gone circle{stroke-dasharray:3 3}
.dnode.gone{opacity:.4}
/* 선언된 부모(커밋 위상엔 없다) — 사실이되 다른 종류의 사실이라 파선으로. */
.dedge.declared{stroke:var(--edge);stroke-width:1.6;stroke-dasharray:5 4;opacity:.75}
/* 날것의 git 그래프 — 등폭 글꼴 그대로, 가로 스크롤(그래프 선이 깨지면 안 된다). */
.ggwrap{margin-top:8px;padding:10px 12px;background:var(--card);border:1px solid var(--line);
 border-radius:8px;overflow-x:auto}
/* 레인 이름 칸은 안 밀린다 — 그림만 스크롤한다(오른쪽을 봐도 어느 줄인지 안다). */
.ggwrap.split{display:flex;gap:0;overflow-x:hidden}
.gggutcol{flex:0 0 auto}
.ggscroll{flex:1 1 auto;overflow-x:auto}
.ggsvg{display:block}
.ggedge{stroke-width:2;opacity:.85}
.ggnode circle{stroke:var(--bg);stroke-width:1.2}
.ggreftxt{font-size:10px;fill:var(--node);text-anchor:start}
/* 날것 그래프의 레인 이름 — 전체맵과 같은 순서(main·dev·체인들)임을 눈으로 잇는 자리. */
.gglanerule{stroke:var(--line);stroke-width:1;opacity:.25;stroke-dasharray:3 3}
.gglanename{font:600 10px ui-monospace,SFMono-Regular,Menlo,monospace;text-anchor:end;fill:var(--dim);opacity:.9}
.gglanename.main{fill:#e0574a}
.gglanename.dev{fill:#2dd4bf}
.ggreftxt.head{fill:var(--here);font-weight:700}
/* 층 그래프 — 레인 띠는 흐리게(구조를 잡아주되 점을 이기지 않게), 층을 건너는 선은 굵게. */
/* 층 두 줄(main·dev) — 전체맵 위에 얹는다. 배치는 그대로, 층만 보이게. */
.lanerule{stroke-width:1;opacity:.3;stroke-dasharray:3 3}
.lanerule.lane-main{stroke:#e0574a}
.lanerule.lane-dev{stroke:#2dd4bf}
.lanename{font:600 10px ui-monospace,SFMono-Regular,Menlo,monospace;text-anchor:end;opacity:.85}
.lanename.lane-main{fill:#e0574a}
.lanename.lane-dev{fill:#2dd4bf}
.laneedge{stroke-width:2;opacity:.85}
.laneedge.merge{stroke:#2dd4bf}
.laneedge.start{stroke:#2dd4bf;opacity:.6}
.laneedge.fork{stroke:#2dd4bf;opacity:.85}
.lanelive{stroke-width:2;opacity:.5}
.lanelive.lane-main{stroke:#e0574a}
.lanelive.lane-dev{stroke:#2dd4bf}
.laneedge.deploy{stroke:#e0574a}
/* dev 층이 산 걸음 — 사건(갈라짐·합류)이 아닌 커밋. 작고 흐리게: 세는 데 쓰이되 사건을 이기지 않게. */
.lanestep{fill:#2dd4bf;opacity:.45}
.lanedot.dev{fill:#2dd4bf}
.lanedot.main{fill:#e0574a}
.lanetag{font:600 9px ui-monospace,SFMono-Regular,Menlo,monospace;text-anchor:middle;fill:#e0574a}
details#det-gitgraph>summary{cursor:pointer;list-style:none}
details#det-gitgraph>summary::-webkit-details-marker{display:none}
details#det-gitgraph>summary::before{content:"▸ ";color:var(--dim)}
details#det-gitgraph[open]>summary::before{content:"▾ "}
.dag .dnode .dagdeploy{font-size:10px;font-weight:800;fill:#2dd4bf;text-anchor:middle;pointer-events:none}
/* 집계 노드(사이클/체인 뎁스, AIL #6) — 이름 라벨 + ⚡분기 표식 */
.dag .dnode.agg .agglabel{font-size:10px;font-weight:600;fill:var(--fg);text-anchor:middle}
.dag .dnode .forkmark{font-size:9px;text-anchor:middle;pointer-events:none}
.dag .dnode:hover circle{stroke:var(--fg);stroke-width:2}
/* 이 화면 읽는 법 — 관전자 온보딩(필드테스트: 노드가 뭘 뜻하는지 모르는 사람이 많았다) */
#pane-guide summary{cursor:pointer;list-style:none}
#pane-guide summary::-webkit-details-marker{display:none}
#pane-guide summary::before{content:"▸ ";color:var(--dim)}
#pane-guide details[open] summary::before,#guide[open] summary::before{content:"▾ "}
.gtoggle{font-weight:400;color:var(--dim);font-size:11px}
.guide{font-size:13px;line-height:1.7;margin-top:8px}
.guide ul{margin:8px 0;padding-left:20px}
.guide li{margin:3px 0}
.glegend{color:var(--dim);margin:8px 0 0}
/* 구조 그림 — 아래 진짜 그래프와 같은 색·모양을 쓴다(다르면 두 번 배워야 한다). */
.gdiagram{display:block;width:100%;max-width:720px;height:auto;margin:12px 0 4px}
.gd-chain{fill:none;stroke:var(--line);stroke-width:1.5;stroke-dasharray:6 4}
.gd-cyc{fill:var(--card);stroke:var(--line);stroke-width:1}
.gd-edge{stroke:var(--edge);stroke-width:2}
.gd-edge.gd-dead{stroke:#ff6b6b;stroke-dasharray:5 4}
.gd-n{fill:var(--node)}
.gd-alive{fill:#3ddc84}
.gd-deadn{fill:#ff6b6b}
.gd-here{fill:none;stroke:var(--here);stroke-width:2.5;stroke-dasharray:5 4}
.gd-arrow{fill:var(--here)}
.gd-lbl{font-size:12px;font-weight:700;fill:var(--dim)}
.gd-lbl-chain{fill:var(--fg)}
.gd-k{font-size:11px;fill:var(--dim);text-anchor:middle}
.gd-kdead{fill:#ff6b6b;text-anchor:start}
.gd-khere{fill:var(--here);font-weight:700}
.gd-cap{font-size:12px;fill:var(--dim)}
.gdim{opacity:.45}
details#det-chain>summary,details#det-cycle>summary{cursor:pointer;list-style:none}
details#det-chain>summary::-webkit-details-marker,details#det-cycle>summary::-webkit-details-marker{display:none}
details#det-chain>summary::before,details#det-cycle>summary::before{content:"▸ ";color:var(--dim)}
details#det-chain[open]>summary::before,details#det-cycle[open]>summary::before{content:"▾ "}
.hint .lg-branch{color:#ff6b6b}.hint .lg-dead{color:#ff6b6b}.hint .lg-alive{color:#3ddc84}.hint .lg-cross{color:var(--here)}.hint .lg-main{color:#e0574a}.hint .lg-dev{color:#2dd4bf}
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
window.__gilPollUrl='/poll';   // 살아있음 확인용 주소(서브 모드에서만 심긴다)
// 폴링 규율 (이슈 #89). 옛 코드는 1.5초 고정이었고, 서명이 바뀌면 **즉시** location.reload()
// 했다. 커밋이 연달아 나는 구간(사이클 27개 결산 배치)에서는 매 틱마다 바뀌므로 매 틱마다
// 전체 페이지를 다시 그리게 되고, 그 렌더가 저장소 전체 스캔이라 서로 겹쳐 쌓인다.
// 셋을 고친다: 겹치지 않게(in-flight 가드) · 조용하면 뜸하게(백오프) · 바뀌는 중엔 잠깐
// 기다렸다가(디바운스 — 폭주가 끝난 뒤 한 번만 다시 그린다).
let sig=null, busy=false, tick=1500, pendingSig=null;
const MIN=1500, MAX=10000;
// gilSafeReload — **사람이 쓰고 있는 동안에는 새로고침하지 않는다** (윈도우 필드테스트).
// 인터뷰 답을 길게 쓰는 중에 폴링이 location.reload() 를 때리면 폼이 통째로 다시 그려져
// 입력이 사라진다("주기적으로 싹 사라진다"). 그래서: 폼이 더러우면(입력이 있거나 포커스가
// 안에 있으면) 리로드를 **미루고** 배너로 알린다 — sig 를 갱신하지 않으므로, 사람이 제출해
// 폼이 깨끗해지는 순간 다음 틱이 알아서 새로고침한다.
// (그래도 초안은 localStorage 에 저장된다 — 리로드가 어떤 경로로 오든 되살아난다.)
// 반환값: 새로고침했으면 true, 미뤘으면 false(호출자가 폴링을 늦춘다).
function gilSafeReload(){
  try{
    if(typeof window.__gilIvDirty==='function' && window.__gilIvDirty()){
      if(typeof window.__gilIvNotifyStale==='function') window.__gilIvNotifyStale();
      return false;
    }
  }catch(e){}
  location.reload();
  return true;
}
async function poll(){
  if(busy) return;              // 앞선 요청이 아직 안 끝났다 — 겹쳐 부르지 않는다
  busy=true;
  try{
    const r=await fetch('/poll',{cache:'no-store'});
    const t=await r.text();
    if(sig===null){ sig=t; tick=MIN; }
    else if(t!==sig){
      // 변화를 봤다. 곧바로 다시 그리지 않고 **한 틱 더** 같은 값인지 본다 — 커밋 폭주
      // 중이면 아직 계속 바뀌는 중이고, 그때 그리면 그리는 족족 낡는다.
      // 미뤄졌으면 뜸하게 — 사람이 오래 쓰는 동안 1.5초마다 저장소를 훑을 이유가 없다(#89).
      if(pendingSig===t){ if(!gilSafeReload()) tick=Math.min(MAX, Math.round(tick*1.5)); }
      else { pendingSig=t; tick=MIN; }
    } else {
      pendingSig=null;
      tick=Math.min(MAX, Math.round(tick*1.5));   // 조용하면 점점 뜸하게
    }
    const l=document.getElementById('live'); if(l)l.classList.remove('stale');
  }catch(e){
    tick=Math.min(MAX, Math.round(tick*2));       // 서버가 막혔으면 더 물러선다
    const l=document.getElementById('live'); if(l)l.classList.add('stale');
  }finally{ busy=false; setTimeout(poll, tick); }
}
poll();
`

const js = `
const SVGNS='http://www.w3.org/2000/svg';
// ── 화면 언어 ──────────────────────────────────────────────────────────────────
// 사전은 페이지에 통째로 실려 온다(viewer_i18n.go). 그래서 토글이 왕복 없이 즉시 먹고,
// 서버 없는 정적 출력에서도 그대로 돈다. 마크업의 한국어 원문은 그대로 두고 갈아끼우므로
// JS 가 죽어도 화면은 비지 않는다.
const I18N=JSON.parse(document.getElementById('i18ndata')?.textContent||'{}');
const I18N_KEY='gil.viewer.lang';

// pickLang — 사람이 고른 적이 있으면 그게 이긴다. 없으면 --lang, 그다음 브라우저 언어.
// 브라우저가 'zh-Hant-TW'·'zh-HK' 처럼 말해도 번체로 알아듣는다(en-US → en 도 같은 이치).
function pickLang(){
  const langs=I18N.langs||['ko'];
  const saved=localStorage.getItem(I18N_KEY);
  if(saved&&langs.includes(saved)) return saved;
  if(I18N.default&&langs.includes(I18N.default)) return I18N.default;
  for(const raw of (navigator.languages||[navigator.language||''])){
    const m=normLang(raw,langs);
    if(m) return m;
  }
  return langs[0];
}
function normLang(raw,langs){
  if(!raw) return '';
  const t=raw.toLowerCase();
  if(langs.includes(raw)) return raw;
  if(t.startsWith('zh')){
    // 번체를 쓰는 자리를 먼저 가른다 — 아니면 대만·홍콩 사람이 간체 화면을 받는다.
    const hant=t.includes('hant')||t.includes('-tw')||t.includes('-hk')||t.includes('-mo');
    const want=hant?'zh-TW':'zh-CN';
    if(langs.includes(want)) return want;
  }
  const base=t.split('-')[0];
  for(const l of langs) if(l.toLowerCase().split('-')[0]===base) return l;
  return '';
}
let LANG=pickLang();

// T — 키 하나를 지금 언어로. 없는 키는 **눈에 보이게** 남긴다(조용히 한국어로 떨어지면
// 낡은 화면을 아무도 모른다 — 누락은 시험이 잡지만, 화면에서도 숨기지 않는다).
function T(key,args){
  const row=(I18N.dict||{})[key];
  let s=row?(row[LANG]||row['ko']||''):('⟦'+key+'⟧');
  if(args) for(const k in args) s=s.split('{'+k+'}').join(args[k]);
  return s;
}
// applyLang — data-i18n 이 달린 자리를 훑어 갈아끼운다. title 속성은 data-i18n-title 로.
function applyLang(){
  document.documentElement.lang=LANG;
  document.querySelectorAll('[data-i18n]').forEach(el=>{
    let args=null;
    const raw=el.getAttribute('data-i18n-args');
    if(raw){ try{ args=JSON.parse(raw); }catch(e){} }
    const key=el.getAttribute('data-i18n');
    // SVG 안의 글은 innerHTML 로 갈면 안 된다(마크업이 아니라 글자다) — textContent 로.
    if(el.ownerSVGElement||el.namespaceURI===SVGNS) el.textContent=T(key,args);
    else el.innerHTML=T(key,args);
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el=>{
    el.title=T(el.getAttribute('data-i18n-title'));
  });
  // 탭 제목에도 저장소를 적는다(이슈 #110). 탭이 여럿이면 제목이 유일한 단서인데, 모든
  // 저장소가 같은 제목을 달고 있어서 사람이 남의 화면을 자기 것으로 열었다. 경로는 **번역
  // 대상이 아니다** — 사람이 만든 사실이라 옮기면 그 자리를 못 찾는다.
  const t=T('app.title');
  if(t){
    let R={}; try{ R=JSON.parse(document.getElementById('repodata')?.textContent||'{}'); }catch(e){}
    const nm=(R.repo||'').split('/').filter(Boolean).pop()||'';
    document.title = nm ? t+' · '+nm : t;
  }
}
function setLang(l){
  LANG=l;
  localStorage.setItem(I18N_KEY,l);
  applyLang();
  // 토글은 화면의 **거울**이다. 브라우저 언어로 자동 선택된 자리에서 어긋나면, 사람은
  // 자기가 무슨 언어를 보고 있는지 토글에게 물어볼 수 없게 된다.
  const sel=document.querySelector('.langsel');
  if(sel&&sel.value!==l) sel.value=l;
  // 코드가 만드는 자리(그림 안의 범례·카드·폼)는 data-i18n 이 닿지 않는다 — 다시 그린다.
  // 인터뷰 폼은 한 글자마다 초안이 저장되므로 다시 그려도 쓰던 답을 잃지 않는다(그게 아니면
  // 언어를 바꿨다는 이유로 답이 날아간다 — 언어 토글이 덫이 되는 자리다).
  ['buildStepMap','buildPrunes','buildReferences','buildInterviews'].forEach(fn=>{
    if(typeof window[fn]==='function'){ try{ window[fn](); }catch(e){ console.error('[gil viewer] '+fn,e); } }
  });
}
function buildLangToggle(){
  const host=document.getElementById('langpick');
  if(!host) return;
  const sel=document.createElement('select');
  sel.className='langsel';
  sel.setAttribute('aria-label',T('lang.label'));
  (I18N.langs||[]).forEach(l=>{
    const o=document.createElement('option');
    o.value=l; o.textContent=(I18N.names||{})[l]||l; o.selected=(l===LANG);
    sel.appendChild(o);
  });
  sel.addEventListener('change',()=>{ setLang(sel.value); sel.title=T('lang.note'); });
  sel.title=T('lang.note');
  host.appendChild(sel);
}

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

  // 이 체인의 기준 문서 — 사이클을 보기 전에 잣대를 먼저 본다(상현님).
  const rb=refBlock(chain);
  if(rb)card.appendChild(rb);

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
  // **사이클도 계보로 배치한다**(상현님 실사용: 사이클 분기가 났는데 일직선으로 보였다).
  // 옛 배치는 cy[i] 를 i*gap 자리에 놓고 앞 노드와 선을 이었다 — 부모를 아예 안 봤다.
  // 그래서 같은 부모에서 갈라진 두 사이클이 앞뒤로 줄지어 서고, 진짜 분기가 사라졌다.
  // 바로 아래 스텝 그래프는 이미 이렇게 그린다: col=부모 사슬 깊이, row=형제마다 한 칸.
  const byName={}; cy.forEach(c=>byName[c.name]=c);
  // 부모는 **여럿일 수 있다**(open --parent 를 여러 번). 배치는 첫 부모로 하고(나무가
  // 되려면 줄기가 하나여야 한다), 나머지 부모는 선으로 함께 그린다 — 선언한 계보를
  // 그림에서 줄이지 않는다.
  const parentsOf=c=>{
    const src=(c.parents&&c.parents.length)?c.parents:(c.parent?[c.parent]:[]);
    const out=[];
    src.forEach(ref=>{ const p=(ref||'').split('/');   // "chain/cycle/step"
      if(p.length>=2 && p[0]===chain && byName[p[1]] && p[1]!==c.name && out.indexOf(p[1])<0) out.push(p[1]); });
    return out;
  };
  const parentOf=c=>{ const ps=parentsOf(c); return ps.length?ps[0]:null; };
  const kids={}; const roots=[];
  cy.forEach(c=>{ const p=parentOf(c); if(p){ (kids[p]=kids[p]||[]).push(c); } else roots.push(c); });
  const col={}, row={};
  let nextRow=0;
  const place=(c,depth)=>{
    col[c.name]=depth;
    const ks=kids[c.name]||[];
    if(!ks.length){ row[c.name]=nextRow++; return; }
    const rs=[];
    ks.forEach((k,i)=>{ if(i>0) nextRow++; place(k,depth+1); rs.push(row[k.name]); });
    row[c.name]=rs[0];                             // 부모는 첫 자식 줄에 선다
  };
  roots.forEach((c,i)=>{ if(i>0) nextRow++; place(c,0); });
  let maxCol=0, maxRow=0;
  cy.forEach(c=>{ maxCol=Math.max(maxCol,col[c.name]||0); maxRow=Math.max(maxRow,row[c.name]||0); });
  const rowGap=r*2+34;
  const w=Math.max(160, padX*2+maxCol*gap+r*2);
  const h=padY*2+r*2+18+maxRow*rowGap;
  const svg=svgEl('svg',{class:'cygraph',viewBox:'0 0 '+w+' '+h,width:w,height:h});
  const cx0=padX+r, cyy0=padY+r;
  const X=c=>cx0+(col[c.name]||0)*gap, Y=c=>cyy0+(row[c.name]||0)*rowGap;
  // 엣지 먼저(노드 아래로 깔린다) — 부모에서 자식으로. 줄이 다르면 꺾어 내린다.
  cy.forEach(c=>{
    parentsOf(c).forEach((p,i)=>{
      const pc=byName[p], x1=X(pc)+r, y1=Y(pc), x2=X(c)-r, y2=Y(c);
      // 둘째 부모부터는 흐리게 — 줄기(배치를 정한 첫 부모)와 구별되게. 둘 다 사실이지만
      // 나무의 모양을 정한 건 첫째다.
      const cls='cyedge'+(i?' second':'');
      const e=(y1===y2)?svgEl('line',{class:cls,x1:x1,y1:y1,x2:x2,y2:y2})
        :(()=>{ const mx=(x1+x2)/2; return svgEl('path',{class:cls,fill:'none',
            d:'M '+x1+' '+y1+' L '+mx+' '+y1+' L '+mx+' '+y2+' L '+x2+' '+y2}); })();
      e.appendChild(svgEl('title',{},(i?'또 하나의 부모: ':'부모: ')+p+' → '+c.name));
      svg.appendChild(e);
    });
  });
  cy.forEach(c=>{
    const g=svgEl('g',{class:'cynode '+c.status+(c.here?' here':''),transform:'translate('+X(c)+','+Y(c)+')'});
    g.dataset.cycle=c.name;
    g.appendChild(svgEl('circle',{r:r}));
    g.appendChild(svgEl('text',{class:'cystep',dy:4},c.steps));
    g.appendChild(svgEl('text',{class:'cyname',dy:r+18},c.name));
    if(c.here) g.appendChild(svgEl('path',{class:'headarrow',d:'M 0 '+(-r-8)+' l -6 -9 l 12 0 z'})); // HEAD ▼
    g.addEventListener('click',ev=>{
      ev.stopPropagation();
      document.querySelectorAll('.cynode.sel').forEach(x=>x.classList.remove('sel'));
      g.classList.add('sel');
      saveSel({chain:chain,cycle:c.name});
      openStepCard(chain,c);
    });
    svg.appendChild(g);
  });
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
  //
  // **키는 sha 다**(이슈 #84, 상현님). 옛 코드는 스텝 번호(s7)를 노드의 정체성으로 썼는데,
  // 번호는 표시용 라벨일 뿐이다. 옛 gil(≤3.28)이 같은 번호를 여러 스텝에 찍은 저장소에서는
  // byId 가 충돌해 **자기 자신이 부모인 노드**가 생기고, place() 가 무한재귀로 죽었다.
  // 원장은 다시 쓸 수 없다(이력 위조다) — 그러니 뷰어가 오염된 데이터를 견뎌야 한다.
  try{
  const bySha={}, byNum={}, kids={};
  steps.forEach(n=>{ bySha[n.sha]=n; (byNum[n.id]=byNum[n.id]||[]).push(n); });
  // 부모 해석: 번호로 가리키므로 중복이 있으면 **자기 자신이 아닌** 첫 후보를 쓴다.
  const pSha=n=>{
    if(!n.parent||n.parent==='null')return '';
    const cands=byNum[n.parent]||[];
    for(const c of cands){ if(c.sha!==n.sha) return c.sha; }
    return '';
  };
  const numSha=(id,self)=>{ // backtrack 등 번호 참조를 sha 로(자기 자신 제외)
    const cands=byNum[id]||[];
    for(const c of cands){ if(!self||c.sha!==self) return c.sha; }
    return '';
  };
  steps.forEach(n=>{ const p=pSha(n); if(p) (kids[p]=kids[p]||[]).push(n); });
  const col={}, row={};
  let nextRow=0;
  // 루트(부모가 이 사이클 안에 없는 것)부터 DFS. 첫 자식은 같은 행, 둘째+ 자식은 새 행(분기).
  const seen=new Set();
  function place(sha, depth){
    if(seen.has(sha))return;   // 순환 가드 — 데이터가 순환해도 관전 도구는 죽으면 안 된다
    seen.add(sha);
    col[sha]=depth;
    const cs=(kids[sha]||[]).slice().sort((a,b)=>stepNumJS(a.id)-stepNumJS(b.id));
    cs.forEach((c,i)=>{
      if(i>0) nextRow++;      // 형제 가지 → 아래로 한 줄
      row[c.sha]=nextRow;
      place(c.sha, depth+1);
    });
  }
  const roots=steps.filter(n=>!pSha(n));
  roots.forEach(rt=>{ row[rt.sha]=nextRow; place(rt.sha,0); });
  // 어느 루트에서도 안 닿은 노드(순환에 갇힌 것)도 자리를 준다 — 안 그리면 조용히 사라진다.
  steps.forEach(n=>{ if(col[n.sha]===undefined){ nextRow++; col[n.sha]=0; row[n.sha]=nextRow; } });

  const colGap=96, rowGap=82, r=20, padX=30, padYtop=48, padY=30;
  let maxCol=0,maxRow=0;
  steps.forEach(n=>{ maxCol=Math.max(maxCol,col[n.sha]||0); maxRow=Math.max(maxRow,row[n.sha]||0); });
  // 진입 부모는 여럿일 수 있다 — 선언한 만큼 고스트를 세운다(하나만 세우면 "두 갈래를
  // 합쳤다"가 화면에서 한 갈래로 줄어든다).
  const ENTRIES=(cyc.parents&&cyc.parents.length)?cyc.parents:(cyc.parent?[cyc.parent]:[]);
  const hasEntry=ENTRIES.length>0;            // 사이클 부모(Gil-Cycle-Parent)가 있으면 진입 경계.
  const exited=steps.filter(n=>n.exit);
  const gx=hasEntry?1:0;                        // 진입 고스트가 있으면 실노드를 한 칸 오른쪽으로.
  const X=sha=>padX+r+(gx+(col[sha]||0))*colGap;
  const Y=sha=>padYtop+r+(row[sha]||0)*rowGap; // 위쪽 여유(backtrack 곡선이 위로 지나감)
  const GEX=padX+r+(gx+maxCol+1)*colGap;        // 진출 고스트 X(맨 오른쪽 한 칸 밖).
  const w=Math.max(160, padX*2+(gx+maxCol+(exited.length?1:0))*colGap+r*2);
  const h=padYtop+padY+maxRow*rowGap+r*2;
  const svg=svgEl('svg',{class:'cygraph',viewBox:'0 0 '+w+' '+h,width:w,height:h});
  const GX=padX+r; // 진입 고스트 X(맨 왼쪽 칸).
  if(hasEntry&&roots.length){
    const inh=(steps[0]&&steps[0].inherit)||'';
    const y0=Y(roots[0].sha);
    ENTRIES.forEach((pref,i)=>{
      const gy=y0+(i? i*(r*2+14) : 0);          // 부모가 여럿이면 아래로 나란히 세운다
      roots.forEach(rt=>{
        svg.appendChild(svgEl('path',{class:'stepedge ghost',fill:'none',
          d:'M '+(GX+r)+' '+gy+' C '+((GX+r+X(rt.sha)-r)/2)+' '+gy+' '+((GX+r+X(rt.sha)-r)/2)+' '+Y(rt.sha)+' '+(X(rt.sha)-r)+' '+Y(rt.sha)}));
      });
      const gg=svgEl('g',{class:'snode ghost',transform:'translate('+GX+','+gy+')'});
      gg.appendChild(svgEl('title',{},(i?'또 하나의 부모 사이클: ':'부모 사이클: ')+pref+(inh?'\n물려받음: '+inh:'')));
      gg.appendChild(svgEl('circle',{r:r}));
      gg.appendChild(svgEl('text',{class:'sid',dy:3},'←'));
      const short=pref.length>26?pref.slice(0,12)+'…'+pref.slice(-12):pref;
      const t=svgEl('text',{class:'skind',dy:r+16},short); t.appendChild(svgEl('title',{},pref));
      gg.appendChild(t);
      if(inh&&!i){ gg.appendChild(svgEl('text',{class:'inhlbl',dy:-r-14},'⇐'+(inh.length>22?inh.slice(0,22)+'…':inh))); }
      svg.appendChild(gg);
    });
  }
  if(exited.length){
    const anchorRow=Math.round(exited.reduce((s,n)=>s+(row[n.sha]||0),0)/exited.length);
    const GEY=padYtop+r+anchorRow*rowGap;
    exited.forEach(lf=>{
      svg.appendChild(svgEl('path',{class:'stepedge ghost',fill:'none',
        d:'M '+(X(lf.sha)+r)+' '+Y(lf.sha)+' C '+((X(lf.sha)+r+GEX-r)/2)+' '+Y(lf.sha)+' '+((X(lf.sha)+r+GEX-r)/2)+' '+GEY+' '+(GEX-r)+' '+GEY}));
    });
    const ge=svgEl('g',{class:'snode ghost',transform:'translate('+GEX+','+GEY+')'});
    ge.appendChild(svgEl('title',{},'이어받은 곳: '+exited.map(n=>n.id+' → '+n.exit).join('\n')));
    ge.appendChild(svgEl('circle',{r:r}));
    ge.appendChild(svgEl('text',{class:'sid',dy:3},'→'));
    svg.appendChild(ge);
  }
  // 엣지: 부모→자식(꺾은 선), backtrack 파선.
  steps.forEach(n=>{
    const p=pSha(n);
    if(p&&bySha[p]){
      const x1=X(p)+r,y1=Y(p),x2=X(n.sha)-r,y2=Y(n.sha);
      const mx=(x1+x2)/2;
      svg.appendChild(svgEl('path',{class:'stepedge',fill:'none',
        d:'M '+x1+' '+y1+' C '+mx+' '+y1+' '+mx+' '+y2+' '+x2+' '+y2}));
    }
    const bt=n.backtrack?numSha(n.backtrack,n.sha):'';
    if(bt){ // 되돌아간 목표로 빨강 파선 — 그래프 위로 지나가 글자 안 가림(피드백 2)
      svg.appendChild(svgEl('path',{class:'btedge',fill:'none',
        d:'M '+X(n.sha)+' '+(Y(n.sha)-r)+' Q '+((X(n.sha)+X(bt))/2)+' '+(Y(n.sha)-r-28)+' '+X(bt)+' '+(Y(bt)-r)}));
    }
  });
  // 종결(success/fail/pending)은 이제 진짜 스텝 노드다(gil 모델 변경) — 일반 스텝 노드와
  // 같은 스타일로 그리되, kind 로 색만 구분(피드백 1·2·3). 가상 종결 노드는 없앴다.
  steps.forEach(n=>{
    const dup=(byNum[n.id]||[]).length>1;
    const g=svgEl('g',{class:'snode '+stepClass(n)+(n.here?' here':''),transform:'translate('+X(n.sha)+','+Y(n.sha)+')'});
    const t=svgEl('title',{},n.id+' '+n.kind+(n.outcome?' ='+n.outcome:'')+'\n'+n.subj+
      (dup?'\n⚠ 이 번호를 쓰는 스텝이 여럿이다(옛 gil 의 번호 중복) — 정체성은 커밋 '+n.sha.slice(0,9)+' 이다':'')+
      (n.plan?'\n⚙ 고정한 설계: '+n.plan:'')+
      (n.planOutcome==='broke'?'\n⚠ 설계가 깨졌다: '+(n.planDiff||''):'')+
      (n.planOutcome==='held'?'\n⚙ 설계 유지':'')+
      (n.advances?'\n◎ 목적에 다가서려는 몫: '+n.advances:'')+
      (n.toward?'\n◎ 목적에 다가선 정도: '+n.toward:'')+
      (n.nextDesign?'\n◎ 다음 설계: '+n.nextDesign:'')+
      (n.supersedes?'\n⟲ 이 스텝이 '+n.supersedes+' 를 정정한다(그 자리에서 갈라졌다)':'')+
      (n.gone?'\n⤳ 구버전 — '+(n.goneBy?n.goneBy+' 이 정정했다':'정정된 가지에 속한다')+
        '\n(지워지지 않았다: 이력에 그대로 남아 있고, 살아있는 계산에서만 빠진다)':''));
    // 정정된 구버전 가지는 **흐리게** — 두 판본이 나란히 살아있는 것처럼 보이면 안 된다.
    if(n.gone) g.classList.add('gone');
    g.appendChild(svgEl('circle',{r:r}));
    g.appendChild(t);
    g.appendChild(svgEl('text',{class:'sid',dy:3},n.id));
    g.appendChild(svgEl('text',{class:'skind',dy:r+16},n.kind+(dup?' ⚠':'')));
    if(n.here){ // 현재위치(HEAD) — 색만이 아니라 ▼HEAD 라벨+화살표로 직관화(피드백 5)
      g.appendChild(svgEl('text',{class:'headlbl',dy:-r-14},'HEAD'));
      g.appendChild(svgEl('path',{class:'headarrow',d:'M 0 '+(-r-11)+' l -5 -8 l 10 0 z'}));
    }
    if(n.supersedes||n.gone){ // 정정 표식 — ⟲정정 / ⤳구버전
      const b=svgEl('text',{class:'supbadge'+(n.gone?' gone':''),dy:n.here?-r-30:-r-14},
        n.supersedes?('⟲ 정정 '+n.supersedes):'⤳ 구버전');
      b.appendChild(svgEl('title',{},n.supersedes
        ?('이 스텝이 '+n.supersedes+' 를 정정한다 — 옛 가지는 그대로 보존된다')
        :('정정으로 대체된 가지'+(n.goneBy?' ('+n.goneBy+' 이 정정)':'')+' — 이력엔 남는다')));
      g.appendChild(b);
    }
    if(n.plan||n.planOutcome){
      const broke=n.planOutcome==='broke';
      const badge=svgEl('text',{class:'planbadge'+(broke?' broke':''),dy:n.here?-r-30:-r-14},
        broke?'⚠ 설계깨짐':'⚙ 설계');
      badge.appendChild(svgEl('title',{},broke?('설계가 깨졌다: '+(n.planDiff||'')):(n.plan||'설계 유지')));
      g.appendChild(badge);
    }
    if(n.deploy){ // 배포 지점(이슈 #34) — 🚀 + 태그 라벨. 이 스텝에서 세상으로 나갔다.
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
  // 작업중(미커밋) 노드를 **스텝 그래프에도** 그린다(상현님). 전체맵에만 있으면, 정작
  // 일이 벌어지는 화면(사이클 카드)에서는 "지금 어디서 손대고 있나"가 안 보인다.
  // 그리고 그 자리가 진짜 현재위치다 — 커밋된 마지막 스텝이 아니라, 그 다음에서 손이 움직인다.
  if(WORK&&WORK.dirty){
    const inThis=(WORK.chain===chain&&WORK.cycle===cyc.name);
    const anchor=inThis?(steps.find(n=>n.sha===WORK.sha)||steps.find(n=>n.id===WORK.step)||
      steps.slice().sort((a,b)=>stepNumJS(b.id)-stepNumJS(a.id))[0]):null;
    if(anchor){
      const wx=X(anchor.sha)+colGap, wy=Y(anchor.sha);
      svg.appendChild(svgEl('path',{class:'stepedge work',fill:'none',
        d:'M '+(X(anchor.sha)+r)+' '+Y(anchor.sha)+' L '+(wx-r)+' '+wy}));
      const wg=svgEl('g',{class:'snode working',transform:'translate('+wx+','+wy+')'});
      wg.appendChild(svgEl('title',{},T('map.work.tip')+WORK.summary+
        (WORK.branch?'\n브랜치: '+WORK.branch:'')+
        (WORK.ahead?'\n앵커 이후 평범한 커밋 '+WORK.ahead+'개':'')+
        (WORK.files&&WORK.files.length?'\n'+WORK.files.join('\n'):'')+
        '\n커밋하면 이 자리에 진짜 스텝이 선다.'));
      wg.appendChild(svgEl('circle',{r:r}));
      wg.appendChild(svgEl('text',{class:'sid',dy:3},'✎'));
      wg.appendChild(svgEl('text',{class:'skind',dy:r+16},T('map.work.label')));
      // 현재위치는 여기다 — 커밋된 잎이 아니라 손이 움직이는 자리(상현님).
      wg.appendChild(svgEl('text',{class:'headlbl',dy:-r-14},'HEAD'));
      wg.appendChild(svgEl('path',{class:'headarrow',d:'M 0 '+(-r-11)+' l -5 -8 l 10 0 z'}));
      wg.classList.add('here');
      // 앵커 스텝의 ▼HEAD 는 지운다 — 현재위치는 하나여야 한다(둘이면 어느 쪽인지 모른다).
      svg.querySelectorAll('.snode.here .headlbl, .snode.here .headarrow').forEach(el=>{
        if(!wg.contains(el))el.remove();
      });
      svg.appendChild(wg);
      // 카드가 한 칸 넓어졌으니 그만큼 뷰박스를 늘린다(안 늘리면 잘린다).
      const nw=Math.max(w, wx+r+padX);
      svg.setAttribute('width',nw); svg.setAttribute('viewBox','0 0 '+nw+' '+h);
    }
  }
  const wrap=document.createElement('div');
  wrap.className='cygraph-wrap'; wrap.appendChild(svg);
  sc.appendChild(wrap);
  // 번호 중복은 조용히 넘기지 않는다 — 뷰어가 견딜 뿐, 저장소는 실제로 오염돼 있다.
  const dups=Object.keys(byNum).filter(k=>byNum[k].length>1);
  if(dups.length){
    const warn=document.createElement('div');
    warn.className='cardwarn';
    warn.textContent=T('card.dupwarn',{dups:dups.join(', ')});
    sc.appendChild(warn);
  }
  }catch(err){
    // 관전 도구의 침묵은 "이상 없음"과 구분이 안 된다(이슈 #84, 상현님). 실패하면 그 사유를
    // 카드 안에 찍는다 — 사람이 "안 뜬다" 대신 "이래서 안 뜬다"를 본다.
    const box=document.createElement('div');
    box.className='cardwarn err';
    box.textContent=T('card.stepgraph.failed',{err:(err&&err.message?err.message:err)});
    sc.appendChild(box);
  }
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
// goHere — 현재위치로 데려간다(상현님). 미커밋 작업이 있으면 **그 자리**가 현재위치다:
// 그 사이클 카드를 열고, 작업중 노드가 그려진 스텝 그래프로 스크롤한다. 없으면 HEAD 스텝으로.
function goHere(){
  let target=null;
  if(WORK&&WORK.dirty&&WORK.chain){
    const cy=DATA[WORK.chain]?.cycles.find(c=>c.name===WORK.cycle)||DATA[WORK.chain]?.cycles.slice(-1)[0];
    if(cy){
      selectChain(WORK.chain);
      openStepCard(WORK.chain,cy);
      const w=document.querySelector('#stepcard .snode.working');
      (w||document.getElementById('pane-step'))?.scrollIntoView({behavior:'smooth',block:'center'});
      flashHere();
      return;
    }
  }
  target=DAG.find(d=>d.here);
  if(target){ jumpToNode(target); flashHere(); return; }
  // 현재위치가 그래프 밖이면(대문·빈 저장소) 그 사실을 말한다 — 조용히 아무 일도 안 하면
  // 버튼이 고장 난 것으로 읽힌다.
  const b=document.getElementById('gohere');
  if(b){ const t=b.textContent; b.textContent=T('head.gohere.missing'); setTimeout(()=>b.textContent=t,2000); }
}
function flashHere(){
  setTimeout(()=>{
    document.querySelectorAll('.snode.here,.snode.working').forEach(el=>{
      el.classList.add('flash'); setTimeout(()=>el.classList.remove('flash'),1400);
    });
  },350);
}
document.getElementById('gohere')?.addEventListener('click',goHere);
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
    const msg=document.createElement('span'); msg.className='pendmsg'; msg.textContent=T('pend.msg');
    const ok=document.createElement('button'); ok.className='pendbtn approve'; ok.textContent=T('pend.approve');
    const no=document.createElement('button'); no.className='pendbtn reject'; no.textContent=T('pend.reject');
    const status=document.createElement('span'); status.className='pendstatus';
    const act=async(kind)=>{
      ok.disabled=no.disabled=true; status.textContent=T('pend.working');
      const qs='chain='+encodeURIComponent(chain)+'&cycle='+encodeURIComponent(cycle)+
        (kind==='reject'?'&to=s1':''); // 기각은 사이클 뿌리 define(s1)로 되돌린다
      try{
        const res=await fetch('/'+kind+'?'+qs,{method:'POST'});
        const txt=await res.text();
        if(res.ok){ status.textContent=T('pend.done'); setTimeout(()=>location.reload(),400); }
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
  body.textContent=T('report.loading');
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
    }else{ body.textContent=T('report.failed',{status:res.status}); }
  }catch(e){ body.textContent=T('report.neterr',{err:e}); }
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
  // 표 판정·분해는 한 자리에서(문단 처리도 같은 isRow 를 봐야 한다).
  const isRow=s=>/^\s*\|.*\|\s*$/.test(s);
  const isSep=s=>/^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(s) && s.indexOf('-')>=0;
  // mdCells — 한 행을 칸으로 쪼갠다. **이스케이프된 파이프(\\|)는 칸 구분이 아니다** —
  // 셀 안의 인라인 코드에 든 파이프가 표를 두 칸으로 찢던 결함.
  const mdCells=s=>s.replace(/^\s*\|/,'').replace(/\|\s*$/,'')
    .split(/(?<!\\)\|/).map(c=>c.trim().replace(/\\\|/g,'|'));
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
    if(isRow(ln) && i+1<lines.length && isSep(lines[i+1])){
      closeList();
      const head=mdCells(ln);
      let t='<table><thead><tr>'+head.map(c=>'<th>'+mdInline(c)+'</th>').join('')+'</tr></thead><tbody>';
      i+=2; // 헤더·구분 소비
      while(i<lines.length && isRow(lines[i]) && !isSep(lines[i])){
        // 칸 수를 헤더에 맞춘다(GFM): 남으면 버리고 모자라면 빈 칸으로 채운다. 안 그러면
        // 한 행이 어긋난 순간 표 전체가 밀려 보인다 — 사람이 "표가 깨졌다"고 하는 그 모양이다.
        const cs=mdCells(lines[i]);
        while(cs.length<head.length) cs.push('');
        cs.length=head.length;
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
    // 표는 **문단의 일부가 아니다.** 앞 문단과 빈 줄 없이 붙은 표(에이전트 보고서에서 아주
    // 흔하다)를 문단이 통째로 삼켜 표 문법이 날것으로 찍히던 결함.
    const startsTable=k=>k+1<lines.length && isRow(lines[k]) && isSep(lines[k+1]);
    while(i+1<lines.length && lines[i+1].trim()!=='' && !BLOCK.test(lines[i+1]) && !startsTable(i+1)){
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
  const lab=document.createElement('span'); lab.className='zhint'; lab.textContent=T('map.filter.label');
  const sel=document.createElement('select');
  const mk=(v,t)=>{const o=document.createElement('option');o.value=v;o.textContent=t;
    if(v===MAP_CHAIN)o.selected=true;sel.appendChild(o);};
  mk('',T('map.filter.all',{n:chains.length}));
  chains.forEach(c=>mk(c,c));
  sel.addEventListener('change',()=>{
    MAP_CHAIN=sel.value;
    try{ localStorage.setItem('gilMapChain',MAP_CHAIN); }catch(e){}
    buildStepMap();
  });
  bar.appendChild(lab); bar.appendChild(sel);
  if(MAP_CHAIN){
    const hint=document.createElement('span'); hint.className='zhint';
    hint.textContent=T('map.filter.only');
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
  // 체인이 하나도 없으면 서버가 전체맵 컨테이너를 안 낸다 — 개시 인터뷰(gil intake)의
  // **정상 상태**가 정확히 그 모양이다(인터뷰는 있고 체인은 아직 없다). 옛 코드는 여기서
  // null 에 replaceChildren 을 불러 죽었고, 그 뒤 buildInterviews() 가 영영 실행되지
  // 않아 **폼이 아예 안 떴다** — 사람이 답할 수단이 사라진 것이다(이슈 #90 검증에서 발견).
  if(!host)return;
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
  // 선언된 부모(위상에 없는 것) — 파선으로 함께 그린다. 접기(집계) 모드에서는 노드가 묶여
  // 대응이 깨지므로 스텝 모드에서만 쓴다.
  // 집계(사이클·체인) 모드에서는 노드가 묶여 스텝 대응이 깨지므로 선언 엣지를 쓰지 않는다.
  VIS.forEach(n=>{ if(MAP_DEPTH!=='step'||!Array.isArray(n.dparents)) n.dparents=[]; });
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
  // ── 층 두 줄 (main-dev-chain, 2026-07-31) ────────────────────────────────
  // 전체맵의 배치는 손대지 않는다 — 지금 그대로가 좋다. 다만 이 그림에는 **어디서 나서
  // 어디로 갔나**가 없었다: 체인들은 보이는데 그것들이 모이는 층(dev)과 세상으로 나가는
  // 대문(main)이 화면에 없다. 그래서 위에 두 줄만 얹는다. 나머지는 두 칸 아래로 내린다.
  //
  // 층이 없는 저장소(옛 레이아웃)에서는 아무것도 하지 않는다 — 없는 층을 그리면 거짓말이다.
  const LAYER=(()=>{ try{ return JSON.parse(document.getElementById('layergraphdata')?.textContent||'{}'); }catch(e){ return {}; } })();
  const LAYERED=(LAYER.lanes||[]).includes('dev');
  // ── 체인마다 제 띠(band) ────────────────────────────────────────────────
  // 레인을 체인 무관하게 채우면, 커질수록 서로 다른 체인의 사이클이 세로로 뒤섞인다. 그러면
  // 사이클 박스가 서로를 관통하고, 라벨은 겹침 회피에 밀려 통째로 생략된다(실측: 6체인 111
  // 커밋에서 체인 이름이 하나도 안 그려졌다 — 겹침 대신 실종).
  //
  // 그래서 **한 체인은 붙어 있는 줄들만 쓴다.** 띠의 순서는 층의 선언(main·dev·체인들)과 같다 —
  // 날것의 git 그래프도 같은 순서로 서므로, 세 그림의 세로축이 하나로 맞는다. 띠 안에서는
  // 원래 규칙(첫 부모의 줄을 물려받고 다툴 때만 아래로)이 그대로 산다: 되돌아간 가지는 여전히
  // 제 줄로 갈라진다.
  (()=>{
    const chains=[...new Set(VIS.map(n=>n.chain).filter(Boolean))];
    if(chains.length<2)return;
    const lanes=LAYER.lanes||[];
    const key=c=>{ const i=lanes.indexOf(c); return i>=0?i:lanes.length+chains.indexOf(c); };
    chains.sort((a,b)=>key(a)-key(b));
    let base=0, top=0;
    chains.forEach(c=>{
      const ns=VIS.filter(n=>n.chain===c);
      const rows=[...new Set(ns.map(n=>row[n.sha]))].sort((a,b)=>a-b);
      const rank={}; rows.forEach((r,i)=>rank[r]=i);
      ns.forEach(n=>{ row[n.sha]=base+rank[row[n.sha]]; });
      top=Math.max(top, base+rows.length-1);
      base+=rows.length;
    });
    maxRow=top;
  })();
  const LMERGE=[], LDEPLOY=[], LDEPLOYAT={};
  (LAYER.rows||[]).forEach(c=>{
    const m=/^gil merge: (\S+) → (\S+)/.exec(c.subj||'');
    if(m&&m[2]==='dev') LMERGE.push({chain:m[1], sha:c.sha}); // sha: dev 순서대로 놓으려고
    // 배포는 **마커 커밋**이 말한다(이슈 #108). 옛 코드는 승격 머지의 제목만 읽어서,
    // --no-promote 로 남긴 배포는 층 그림에 아예 없었고 귀속 여부도 알 수 없었다.
    if(c.deploy){ if(!(c.deploy in LDEPLOYAT)) LDEPLOY.push(c.deploy); LDEPLOYAT[c.deploy]=c.deployAt||''; }
    const d=/^gil deploy (\S+):.*승격/.exec(c.subj||'');
    if(d && !LDEPLOY.includes(d[1])) LDEPLOY.push(d[1]);
  });
  // 층은 **자기 띠**를 위에 갖는다(아래 LANEH). 노드 행을 내리면 라벨(사이클·체인 이름)이
  // 그 자리로 올라와 두 줄과 겹친다 — 겹침은 실종과 같다(이슈 #37 에서 값을 치른 교훈).
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
  // 라벨이 들어갈 머리 공간. 체인 이름을 안 그리게 된 뒤로 옛 값(62)은 과했다 —
  // 남은 건 사이클 이름 한 줄뿐이다.
  const labelRoom = aggMode ? 26 : 20+rotHead;
  // 층 사이 간격을 **층과 체인 사이 간격과 같게** 맞춘다. 그냥 두면 main–dev 는 붙어 있고
  // dev–체인만 멀어져, 같은 종류의 거리(한 층 내려감)가 두 가지로 보인다.
  //   yMain=16, yDev=16+s, 첫 행=padTop+r 이고 padTop=labelRoom+LANEH, LANEH=s+20 일 때
  //   (16+s)-16 == (padTop+r)-(16+s)  →  s = labelRoom+9.
  const LANE_S = LAYERED ? labelRoom+9 : 0;   // 층과 층 사이 = 층과 체인 사이
  const LANEH  = LAYERED ? LANE_S+20 : 0;     // 두 줄이 차지하는 머리 띠(라벨은 이 아래)
  const padTop = labelRoom + LANEH;
  let longestLabel=0;
  if(aggMode) VIS.forEach(n=>{ const s=(MAP_DEPTH==='cycle'?n.cycle:n.chain)||''; longestLabel=Math.max(longestLabel,s.length); });
  const colW = aggMode ? Math.max(48, longestLabel*7+18) : 34; // ~7px/글자 + 여백
  // 집계 모드는 첫 노드 라벨(중앙정렬)이 왼쪽으로 삐져나가니 padX 를 라벨 절반만큼 확보.
  let padX = aggMode ? Math.max(26, longestLabel*7/2+8) : 26;
  // 층 이름(main·dev)은 왼쪽 여백에 서고, 그 오른쪽으로 **출발 곡선이 달릴 자리**를 둔다.
  // 이 자리가 없으면 첫 점(깊이 0)이 왼쪽 끝이라 출발선이 수직으로 떨어져 '갈라져 나왔다'가
  // 아니라 '떨어졌다'로 보인다.
  // 내려오는 곡선은 **왼쪽으로 달릴 자리**가 없으면 거기서 잘린다 — 그러면 같은 공식을
  // 써도 내려오는 쪽만 급해 보인다(실측: 달림 52px 대 105px). 어림짐작으로 여백을 주지 말고
  // **가장 깊은 낙차를 실제로 계산해** 그만큼 확보한다. 올라가는 쪽은 오른쪽 여백이 넉넉하니,
  // 이 자리가 맞아떨어져야 두 쪽이 같은 곡률로 읽힌다.
  const LANE_X0 = 30;                                    // 층 선 왼쪽 끝 ~ dev 시작점
  const deepestDrop = LAYERED ? (padTop + r + maxRow*rowH) - (16+LANE_S) : 0;
  const LANEPAD = LAYERED ? Math.max(70, Math.min(320, LANE_X0 + deepestDrop*0.75 + 16)) : 0;
  padX += LAYERED ? 46+LANEPAD : 0;
  let maxD=0; VIS.forEach(n=>{ if(depth[n.sha]>maxD)maxD=depth[n.sha]; });
  // 오른쪽 여유 = 가장 긴 체인 이름이 박스 위 라벨로 삐져나가도 안 잘리게.
  let maxName=0; VIS.forEach(n=>{ maxName=Math.max(maxName,(n.chain||'').length); });
  let maxColUsed=false;
  const workPad=(WORK&&WORK.dirty)?colW+40:0;   // 작업중 유령 노드가 잘리지 않게 한 칸 더
  const rightPad=Math.max(padX, maxName*7+16)+workPad+(LAYERED?90:0); // 층 곡선이 달릴 자리
  const W=padX+rightPad+maxD*colW+r*2, H=padTop+padBot+maxRow*rowH+r*2;
  const X=sha=>padX+r+depth[sha]*colW;
  const Y=sha=>padTop+r+row[sha]*rowH;
  const svg=svgEl('svg',{class:'dag',viewBox:'0 0 '+W+' '+H,width:W,height:H});
  const agg=aggMode; // 집계 모드(사이클/체인)면 사이클 박스 대신 노드 라벨을 쓴다.
  // 0) 층 두 줄 — main(대문)·dev(층). 체인들이 어디서 나서 어디로 갔는지가 이 두 줄로 닫힌다.
  //    **떠 있는 점을 만들지 않는다**: 대문에서 dev 가 갈라져 나오고, dev 에서 체인이 갈라지고,
  //    체인이 dev 로 합류하고, dev 가 대문으로 오른다 — 그 사슬이 실선으로 끊김 없이 이어진다.
  //    (엷은 점선은 층이 계속 살아 있다는 배경일 뿐, 사건은 실선이 잇는다.)
  if(LAYERED){
    const yMain=16, yDev=16+LANE_S, xL=padX+r-LANEPAD, xR=W-6;
    [['main',yMain,'배포된 것만 온다 — 대문'],['dev',yDev,'모든 작업이 시작하는 층']].forEach(([nm,y,tip])=>{
      const ln=svgEl('line',{class:'lanerule lane-'+nm,x1:xL,y1:y,x2:xR,y2:y});
      ln.appendChild(svgEl('title',{},nm+' — '+tip)); svg.appendChild(ln);
      const t=svgEl('text',{class:'lanename lane-'+nm,x:xL-6,y:y+4}); t.textContent=nm;
      svg.appendChild(t);
    });
    // 대칭 S곡선. 제어점을 **가로 달림의 절반씩** 양쪽에 두면 들어오는 꺾임과 나가는 꺾임이
    // 같아진다(0.6 은 나가는 쪽이 더 완만해 보였다). 가로 달림도 세로 낙차에 같은 비율로
    // 묶는다 — 한쪽만 잘리면 그쪽이 급해 보인다.
    const runFor=dy=>Math.max(colW*1.6, Math.abs(dy)*0.75);
    const curve=(x1,y1,x2,y2,cls,tip)=>{
      const k=Math.abs(x2-x1)*0.5;
      const p=svgEl('path',{class:'laneedge '+cls,fill:'none',
        d:'M '+x1+' '+y1+' C '+(x1+k)+' '+y1+' '+(x2-k)+' '+y2+' '+x2+' '+y2});
      if(tip)p.appendChild(svgEl('title',{},tip));
      svg.appendChild(p); return p;
    };
    // 출발선은 **꺾어 내린다**(곡선 아님). 여섯 체인이 층에서 사선으로 내려오면 그 사선들이
    // 첫 칸의 점·엣지를 가로질러 서로 겹치고, 시작 지점이 뭉개진다(상현님: 다닥다닥 붙어
    // 구분이 안 된다). 갈라진 자리마다 **제 세로선**으로 내려가면 선이 서로 안 겹치고, 어느
    // 선이 어느 체인으로 갔는지가 눈으로 따라진다 — git 그래프가 쓰는 그 꺾임이다.
    const elbowDown=(x1,y1,x2,y2,cls,tip)=>{
      const R=Math.min(9, Math.max(4,(x2-x1)/2));
      const p=svgEl('path',{class:'laneedge '+cls,fill:'none',
        d:'M '+x1+' '+y1+' V '+(y2-R)+' Q '+x1+' '+y2+' '+(x1+R)+' '+y2+' H '+x2});
      if(tip)p.appendChild(svgEl('title',{},tip));
      svg.appendChild(p); return p;
    };
    const elbowUp=(x1,y1,x2,y2,cls,tip)=>{   // 합류: 오른쪽으로 달리다 제 세로선으로 올라간다
      const R=Math.min(9, Math.max(4,(x2-x1)/2));
      const p=svgEl('path',{class:'laneedge '+cls,fill:'none',
        d:'M '+x1+' '+y1+' H '+(x2-R)+' Q '+x2+' '+y1+' '+x2+' '+(y1-R)+' V '+y2});
      if(tip)p.appendChild(svgEl('title',{},tip));
      svg.appendChild(p); return p;
    };
    const dot=(x,y,cls,tip)=>{
      const c=svgEl('circle',{class:'lanedot '+cls,cx:x,cy:y,r:4});
      if(tip)c.appendChild(svgEl('title',{},tip)); svg.appendChild(c); return c;
    };
    // (1) 대문 → dev. 층은 대문에서 갈라져 나온 것이다 — 그 사실이 그림에 없으면 dev 가
    //     어디서 왔는지 알 수 없고, 첫 점이 떠 있는 것처럼 보인다.
    const xMainStart=xL+6, xDevStart=xL+LANE_X0;
    dot(xMainStart,yMain,'main','대문(main) — 여기서 층이 갈라진다');
    curve(xMainStart,yMain,xDevStart,yDev,'fork','dev 는 대문에서 갈라진 층이다 (gil init)');
    dot(xDevStart,yDev,'dev','dev 층 시작');
    // (2)(3) dev 위의 사건들 — 갈라짐(체인의 출발)과 합류(gil merge).
    //
    // **한 점에서 갈라지지 않는다.** 옛 코드는 모든 dev 시조를 xDevStart 한 점에서 뽑았다.
    // 근거는 "dev 시조들은 모두 dev 팁에서 갈라진다"였는데, 그게 사실이 아니다: dev 가
    // 커밋을 쌓은 뒤에 난 체인은 **그 중간 커밋**에서 갈라진다. 한 점에 겹쳐 그리면 나중에
    // 난 체인이 처음부터 나란히 달린 것처럼 보이고, 같은 화면의 git 그래프(날것의 %P)와
    // 어긋난다(상현님). 그림이 사실과 다르면 사람은 없는 동시성을 읽는다.
    //
    // 그래서 자리를 dev 자신의 순서(devorder — 첫 부모 사슬)로 정한다. 갈라짐은 chain-root
    // 의 실제 부모 커밋 자리에, 합류는 그 머지 커밋 자리에. 순서만 쓰고 간격은 화면이
    // 정한다 — 층 줄에는 depth 축이 없으니 x 는 "몇 번째 사건인가"로만 읽혀야 한다.
    const devIdx={}; (LAYER.devorder||[]).forEach((s,i)=>{ devIdx[s]=i; });
    const ordered=(LAYER.devorder||[]).length>0;
    // 체인의 **첫 걸음**은 깊이만으로 안 정해진다. 뿌리가 여럿일 수 있어서(계보가 끊긴
    // 사이클도 깊이 0 이다), 깊이가 같으면 사이클 이름·스텝 번호로 가른다 — c1/s1 이
    // c2/s1 보다 먼저다. 안 그러면 출발선이 엉뚱한 사이클에 붙어, 정작 첫 걸음은 층과
    // 안 이어진 것처럼 보인다(상현님: c1/s1 이 dev 와 안 이어져 있다).
    const stepNo=s=>{ const m=/^s(\d+)/.exec(s||''); return m?+m[1]:0; };
    const firstKey=n=>[depth[n.sha], (n.cycle||''), stepNo(n.step)];
    const lessKey=(a,b)=>{ for(let i=0;i<3;i++){ if(a[i]<b[i])return true; if(a[i]>b[i])return false; } return false; };
    const chainFirst=ch=>{ const ns=VIS.filter(n=>n.chain===ch); if(!ns.length)return null;
      let f=ns[0]; ns.forEach(n=>{ if(lessKey(firstKey(n),firstKey(f))) f=n; }); return f; };
    const chainLast=ch=>{ const ns=VIS.filter(n=>n.chain===ch); if(!ns.length)return null;
      let l=ns[0]; ns.forEach(n=>{ if(depth[n.sha]>depth[l.sha]) l=n; }); return l; };
    const evs=[];
    Object.keys(LAYER.devroots||{}).forEach(ch=>{
      const f=chainFirst(ch); if(!f)return;
      const fork=(LAYER.devroots||{})[ch];
      evs.push({kind:'fork', chain:ch, node:f, at:(fork in devIdx)?devIdx[fork]:0});
    });
    LMERGE.forEach(m=>{
      const l=chainLast(m.chain); if(!l)return;
      evs.push({kind:'merge', chain:m.chain, node:l, at:(m.sha in devIdx)?devIdx[m.sha]:Infinity});
    });
    // dev 순서대로. 같은 자리(같은 커밋)면 갈라짐이 먼저 — 합류는 받는 쪽의 일이라 뒤에 온다.
    evs.sort((a,b)=> (a.at-b.at) || (a.kind==='fork'?-1:1));
    // 같은 dev 커밋에서 난 갈라짐은 **같은 점**에서 나와야 한다(그건 사실이다). 그래서 자리는
    // 사건이 아니라 커밋 단위로 정한다: 그 커밋에서 난 체인들의 첫 점 중 가장 왼쪽보다 조금
    // 왼쪽. dev 뿌리(0번)는 층이 시작한 그 점 그대로.
    const forkX={};
    evs.filter(e=>e.kind==='fork').forEach(e=>{
      const want = (!ordered || e.at===0) ? xDevStart
                 : Math.min(X(e.node.sha)-colW*0.6, xR-60);
      forkX[e.at] = (e.at in forkX) ? Math.min(forkX[e.at], want) : want;
    });
    // 그리고 **다른 커밋이면 다른 자리**여야 한다. 자리를 그 체인의 첫 점에서만 끌어오면,
    // 나중에 난 체인이 (합류가 없어 깊이가 얕은 탓에) 앞 체인과 같은 x 로 도로 겹친다 —
    // 고치려던 그 거짓이 그대로 돌아온다. 그래서 dev 커밋 **하나하나에 자리를 준다**.
    //
    // 자리를 주고 나면 그 자리에 점을 찍을 수 있다. 그러면 층 줄이 세는 그림이 된다:
    // 두 갈라짐 사이에 놓인 작은 점의 수 = 그 사이 dev 가 쌓은 커밋 수. 간격만으로는
    // "먼저·나중"까지만 읽혔고, "얼마나 뒤"는 못 읽혔다(직전 매듭에서 남긴 한계).
    const devSeq=LAYER.devorder||[];
    // 간격: 사건들이 원하는 자리를 담되, 커밋이 많으면 줄여 층 줄 안에 들어오게. 층 줄에는
    // depth 축이 없으니 간격은 눈금이 아니다 — 세는 것은 점이고, 간격은 점이 겹치지 않을 만큼.
    const SEP=Math.max(6, Math.min(14, (xR-60-xDevStart)/Math.max(1,devSeq.length-1)));
    // 사건이 원하는 자리(합류는 그 체인 마지막 점에서 내려오는 자리).
    const wantX={};
    const put=(i,x)=>{ if(i===undefined||i===null||!isFinite(i))return;
      wantX[i]=(i in wantX)?Math.max(wantX[i],x):x; };
    Object.keys(forkX).forEach(k=>put(Number(k), forkX[k]));
    const mergeAt={};
    evs.filter(e=>e.kind==='merge').forEach(e=>{
      const x1=X(e.node.sha), y1=Y(e.node.sha);
      mergeAt[e.at]=Math.min(xR-40, x1+runFor(y1-yDev)); put(e.at, mergeAt[e.at]);
    });
    // 왼→오른으로 훑으며 자리를 굳힌다: 앞 커밋보다 최소 SEP 오른쪽, 원하는 자리가 있으면 거기.
    const devX=[]; let xRun=xDevStart;
    devSeq.forEach((sha,i)=>{
      xRun = i===0 ? xDevStart : Math.max(xRun+SEP, (i in wantX)?wantX[i]:xRun+SEP);
      devX.push(Math.min(xRun, xR-8)); xRun=devX[i];
    });
    const atX=i=>(ordered && devX[i]!==undefined) ? devX[i] : xDevStart;
    // dev 커밋 자체를 점으로 — 사건이 아닌 커밋은 작게(층이 산 걸음), 사건 자리는 아래에서
    // 제 색으로 덧그린다. 이름은 그 커밋의 제목 그대로: 뷰어는 요약하지 않는다.
    const subjOf={}; (LAYER.rows||[]).forEach(c=>{ subjOf[c.sha]=c.subj||''; });
    devSeq.forEach((sha,i)=>{
      if(i===0)return; // 층 시작점은 위에서 이미 찍었다
      const c=svgEl('circle',{class:'lanestep',cx:atX(i),cy:yDev,r:2.5});
      c.appendChild(svgEl('title',{},'dev '+(i)+'걸음: '+(subjOf[sha]||sha)));
      svg.appendChild(c);
    });
    const devEvents=[xDevStart];
    // "원인이 결과보다 뒤에 설 수 없다"는 clamp 가 **순서를 이기지 못하게** 한다. 체인들의 첫
    // 점이 같은 깊이에 서면 clamp 값이 같아져, 서로 다른 dev 커밋에서 난 갈라짐이 도로 한 점에
    // 뭉쳤다(실측: 여섯 체인 중 넷이 x=230 에 포갬 — 고친 그 거짓이 스케일에서 되살아났다).
    // 그래서 clamp 는 걸되, 앞 갈라짐보다는 언제나 오른쪽에 선다.
    // 내려가는 세로선은 **점밭 왼쪽 여백에서만** 달린다. 각자 제 첫 점 바로 왼쪽에서 떨어지게
    // 하면, 그 세로선이 위쪽 띠들의 사이클 박스를 뚫고 내려간다(체인이 여섯이면 여섯 번).
    // 층 왼쪽 여백(LANEPAD)은 이러라고 있는 자리다: 모든 첫 점보다 왼쪽에서, 서로 벌려서.
    const forkEvs=evs.filter(e=>e.kind==='fork');
    const minFirstX=Math.min(...forkEvs.map(e=>X(e.node.sha)));
    const forkSlots=[...new Set(forkEvs.map(e=>e.at))].sort((a,b)=>a-b);
    const slotGap=(minFirstX-10-xDevStart)/(forkSlots.length+1);
    const slotX={}; forkSlots.forEach((at,i)=>{ slotX[at]=xDevStart+slotGap*(i+1); });
    evs.forEach(e=>{
      if(e.kind==='fork'){
        const x=(slotX[e.at]!==undefined && slotGap>6) ? slotX[e.at]
              : Math.min(atX(e.at), Math.max(xDevStart, X(e.node.sha)-r*2));
        elbowDown(x,yDev,X(e.node.sha),Y(e.node.sha),'start',
          '출발: dev → '+e.chain+' (계보상 시조 — 대문은 물려받는다)');
        if(x>xDevStart) dot(x,yDev,'dev','갈라짐: dev → '+e.chain);
        devEvents.push(x);
      }else{
        const x1=X(e.node.sha), y1=Y(e.node.sha);
        const x2=isFinite(e.at)?atX(e.at):Math.min(xR-40, x1+runFor(y1-yDev));
        elbowUp(x1,y1,x2,yDev,'merge','합류: '+e.chain+' → dev (gil merge)');
        dot(x2,yDev,'dev','합류: '+e.chain+' → dev');
        devEvents.push(x2);
      }
    });
    // (4) dev → 대문(gil deploy). **마지막 합류 자리에서** 오른다 — 허공에서 시작하지 않는다.
    const xDevLast=Math.max(...devEvents);
    LDEPLOY.forEach(tag=>{
      const x1=xDevLast, x2=Math.min(xR-8, x1+runFor(yDev-yMain));
      // 귀속 스텝을 못 찾았어도 그린다 — 침묵하면 배포가 없었던 것처럼 보인다(이슈 #108).
      // 못 찾은 것과 없는 것은 다르고, 그 차이는 화면이 말해야 한다.
      const lost=(tag in LDEPLOYAT) && !LDEPLOYAT[tag];
      const at=LDEPLOYAT[tag];
      curve(x1,yDev,x2,yMain,'deploy','배포 '+tag+': dev → main (gil deploy)'+
        (at?'\n내보낸 잎: '+at:(lost?'\n귀속 스텝 미상 — 이 배포 계보에서 산 잎을 찾지 못했다':'')));
      dot(x2,yMain,'main','배포 '+tag); devEvents.push(x1);
      const t=svgEl('text',{class:'lanetag',x:x2,y:yMain-8});
      t.textContent='🚀 '+tag+(lost?' (귀속 스텝 미상)':'');
      svg.appendChild(t);
      // 대문도 실선으로 잇는다 — 갈라진 자리에서 배포가 도착한 자리까지가 대문이 산 구간이다.
      svg.appendChild(svgEl('line',{class:'lanelive lane-main',x1:xMainStart,y1:yMain,x2:x2,y2:yMain}));
    });
    // dev 가 산 구간을 실선으로 — 점들이 그 위에 앉아 하나로 읽힌다.
    svg.appendChild(svgEl('line',{class:'lanelive lane-dev',x1:xDevStart,y1:yDev,x2:Math.max(...devEvents),y2:yDev}));
  }
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
      if(y-h < LANEH+2) return false; // 머리 공간(층 띠 아래)을 넘었다 — 생략(박스 title 로 여전히 읽을 수 있다)
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

  // 3) 체인 이름은 **그리지 않는다**(상현님). 라벨이 많아질수록 전체맵은 그림이 아니라
  //    글자판이 된다 — 이름은 늘 거기 있지만, 사람이 매 순간 알아야 하는 건 아니다.
  //    필요할 때 점·박스에 올리면 툴팁으로 뜬다(사이클 박스 title = <체인>/<사이클>,
  //    노드 title = <체인>/<사이클>/<스텝>). 겹침 회피에 쓰던 머리 공간도 그만큼 돌려준다.
  function X_(d){ return padX+r+d*colW; }
  function Y_(rw){ return padTop+r+rw*rowH; }
  // 2) 엣지(부모→자식). backtrack 형제가지=빨강 파선. 경계 넘는(체인 전환) 엣지=주황.
  VIS.forEach(n=>{ (n.dparents||[]).forEach(p=>{ if(!byId[p])return;
    const x1=X(p),y1=Y(p),x2=X(n.sha),y2=Y(n.sha), mx=(x1+x2)/2;
    const e=svgEl('path',{class:'dedge declared',fill:'none',
      d:'M '+x1+' '+y1+' C '+mx+' '+y1+' '+mx+' '+y2+' '+x2+' '+y2});
    e.appendChild(svgEl('title',{},'선언된 부모: '+byId[p].cycle+'/'+byId[p].step+' → '+n.cycle+'/'+n.step));
    svg.appendChild(e);
  }); });
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
  // 3-0) **발아 스텁**(이슈 #104). 부모 스텝은 없지만 체인의 기준선에서 난 사이클 —
  // 정석 발아다. 아무것도 안 그리면 미아와 구별되지 않아 "orphan 인데 git 엔 부모가 있네?"
  // 라는 불신이 생긴다. 없는 부모를 지어내지 않되, **여기서 났다**는 것은 말한다.
  VIS.forEach(n=>{
    if(!n.sprout)return;
    const x=X(n.sha), y=Y(n.sha);
    svg.appendChild(svgEl('path',{class:'dedge sprout',fill:'none',
      d:'M '+(x-colW*0.55)+' '+y+' L '+(x-r-1)+' '+y}));
    const st=svgEl('circle',{class:'sproutcap',cx:x-colW*0.55,cy:y,r:2.5});
    st.appendChild(svgEl('title',{},T('map.sprout')));
    svg.appendChild(st);
  });
  // 3) 노드 + HEAD ▼. 스텝 모드=작은 점(글씨 없음). 집계 모드=큰 점+이름 라벨(+⚡분기).
  VIS.forEach(n=>{
    const g=svgEl('g',{class:'dnode k-'+stepClass(n)+(n.here?' here':'')+(isLeaf(n,kids)?' leaf':'')+(agg?' agg':'')+(n.gone?' gone':''),transform:'translate('+X(n.sha)+','+Y(n.sha)+')'});
    const tip=agg?(n.subj+(n.here?'  ◀ HEAD':'')):(n.chain+'/'+n.cycle+'/'+n.step+' '+n.kind+(n.here?' ◀ HEAD':'')+
      (n.supersedes?'  ⟲정정 '+n.supersedes:'')+(n.gone?'  ⤳구버전(정정으로 대체)':'')+'\n'+n.subj);
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
      const tip=T('map.work.tip')+WORK.summary+
        (WORK.branch?'\n브랜치: '+WORK.branch:'')+
        (WORK.ahead?'\n앵커 이후 평범한 커밋 '+WORK.ahead+'개':'')+
        (WORK.files&&WORK.files.length?'\n'+WORK.files.join('\n'):'')+
        '\n커밋하면 이 자리에 진짜 스텝이 선다.';
      wg.appendChild(svgEl('title',{},tip));
      wg.appendChild(svgEl('circle',{r:agg?r+2:r}));
      const lb=svgEl('text',{class:'worklbl',x:0,y:-(r+6)}); lb.textContent=T('map.work.label.pen'); wg.appendChild(lb);
      // 현재위치는 손이 움직이는 자리다(상현님) — 커밋된 마지막 스텝이 아니라 이 자리.
      // 전체맵과 스텝 그래프가 같은 말을 하게 한다(둘이 다르면 어느 쪽이 참인지 모른다).
      if(anchor.here){
        svg.querySelectorAll('.dnode .headlbl, .dnode .headarrow').forEach(el=>el.remove());
        const hl=svgEl('text',{class:'headlbl',x:0,y:-(r+20)}); hl.textContent='HEAD'; wg.appendChild(hl);
        wg.appendChild(svgEl('path',{class:'headarrow',d:'M 0 '+(-(r+15))+' l -5 -8 l 10 0 z'}));
        wg.classList.add('here');
      }
      svg.appendChild(wg);
      maxColUsed=true;
    }
  }
  const wrap=document.createElement('div'); wrap.className='dagwrap'; wrap.appendChild(svg);
  host.appendChild(enableZoomPan(wrap,svg,W,H));
  host.appendChild(wrap);
  const leg=document.createElement('p'); leg.className='hint';
  if(MAP_DEPTH==='step')
    leg.innerHTML=T('map.legend.step');
  else
    leg.innerHTML=T(MAP_DEPTH==='cycle'?'map.legend.folded.cycle':'map.legend.folded.chain');
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
  btn('＋',T('map.zoom.in'),()=>{const c=center();zoomAt(1/1.4,c.x,c.y);});
  btn('−',T('map.zoom.out'),()=>{const c=center();zoomAt(1.4,c.x,c.y);});
  btn(T('map.zoom.fit'),T('map.zoom.fit.title'),()=>{vb={x:0,y:0,w:W,h:H};apply();});
  const zh=document.createElement('span'); zh.className='zhint';
  zh.textContent=T('map.zoom.hint'); bar.appendChild(zh);
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
  // 저장된 선택이 없으면(첫 방문) **현재위치를 스스로 연다** — 스텝 그래프와 스텝 디테일이
  // 처음부터 채워져 있어야 한다(필드테스트: 뭘 눌러야 할지 몰라 빈 화면에서 멈췄다).
  // 스크롤·플래시는 하지 않는다 — 사람이 누른 것이 아니라 기본 상태일 뿐이니까.
  if(!sel||!DATA[sel.chain]){ openDefaultView(); return; }
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
// openDefaultView — 첫 화면의 기본 열림 상태(상현님): 전체맵 · 스텝 그래프 · 스텝 디테일.
// 체인/사이클 그래프는 접힌 채 둔다(필요할 때 펼친다). 열 자리는 **현재위치**가 우선이고,
// 없으면 가장 최근 사이클의 마지막 스텝 — 어느 쪽이든 "지금 무슨 걸음인가"가 먼저 보인다.
function openDefaultView(){
  let chain=null, cyc=null, step=null;
  const here=DAG.find(d=>d.here && d.chain && d.cycle);
  if(WORK&&WORK.dirty&&WORK.chain&&DATA[WORK.chain]){
    chain=WORK.chain;
    cyc=DATA[chain].cycles.find(c=>c.name===WORK.cycle)||DATA[chain].cycles.slice(-1)[0];
  } else if(here&&DATA[here.chain]){
    chain=here.chain;
    cyc=DATA[chain].cycles.find(c=>c.name===here.cycle);
    step=here.step;
  }
  if(!chain){
    const names=Object.keys(DATA);
    if(!names.length)return;
    chain=names[names.length-1];
    cyc=(DATA[chain].cycles||[]).slice(-1)[0];
  }
  if(!cyc)return;
  selectChain(chain);
  openStepCard(chain,cyc);
  const nodes=cyc.nodes||[];
  const n=(step&&nodes.find(x=>x.id===step))||nodes[nodes.length-1];
  if(n)openReport(chain,cyc.name,n);
}
// git 그래프는 **펼칠 때** 한 번 불러온다 — 항상 긁으면 큰 저장소에서 비싸고, 접혀 있는
// 동안은 아무도 안 본다. 폴링 리로드마다 다시 접히므로 상태는 기억한다.
// buildGitGraph — 날것의 git 그래프를 **그림으로** 그린다.
//
// ASCII 그래프(git log --graph)는 사람이 못 읽는다 — 선이 문자로 그려져 몇 갈래인지 눈에 안 들어온다.
// 그래서 같은 사실을 레인 배치로 그린다: 세로=시간(위가 최신), 가로 레인=동시에 살아있는 가지,
// 점=커밋, 선=부모로 가는 길, 칩=브랜치 이름. **여기서 갈라져 보이지 않으면 그 계보는 거짓이다.**
function buildGitGraph(){
  const host=document.getElementById('gitgraph');
  if(!host)return;
  const rows=JSON.parse(document.getElementById('gitgraphdata')?.textContent||'[]');
  if(!rows.length){ host.textContent=T('gitgraph.empty'); return; }
  const LAYER=(()=>{ try{ return JSON.parse(document.getElementById('layergraphdata')?.textContent||'{}'); }catch(e){ return {}; } })();
  const LAYERED=(LAYER.lanes||[]).includes('dev');
  // 전체맵과 같은 눈높이로 **간결하게**: 왼→오른 흐름, 점=커밋, 선=부모, 칩=브랜치 이름만.
  // 커밋마다 sha·제목을 늘어놓으면 그건 그림이 아니라 목록이다(그리고 ASCII 와 다를 바 없다).
  // 자세한 것은 점에 얹은 툴팁으로 — 눈으로 보는 것은 **몇 갈래로 갈라졌나** 하나다.
  const old2new=rows.slice().reverse();          // git log 는 최신부터 — 왼쪽이 과거가 되게
  const idx={}; old2new.forEach((c,i)=>idx[c.sha]=i);
  // **레인 규칙을 전체맵과 같게 한다**(상현님: 둘이 달라 눈으로 대조가 안 된다).
  // 전체맵은 "첫 자식이 줄기를 잇고, 뒤에 갈라진 형제는 아래로 내려간다". git 방식(최신부터
  // 훑으며 빈 레인 잡기)은 줄기가 위에 있으리란 보장이 없어 같은 그래프가 달리 보였다.
  // 그래서 **오래된 것부터** 훑으며 첫 자식에게 부모의 레인을 물려준다.
  // 레인은 **비면 다시 쓴다.** 옛 코드는 "지금까지 나온 레인은 전부 쓰는 중"으로 쳐서 새 가지가
  // 날 때마다 한 칸씩 아래로만 갔다 — 400 커밋이면 400줄이고, 그림은 계단 하나가 된다(상현님:
  // 겹쳐서 안 보인다). 한 레인이 살아 있는 구간은 그 커밋에서 **마지막 자식**까지다. 그 뒤엔 빈다.
  const lastChild={};                             // sha → 그 커밋을 부모로 삼는 자식 중 가장 나중 것
  old2new.forEach((c,i)=>{
    (c.parents||[]).forEach(p=>{ if(idx[p]!==undefined) lastChild[p]=Math.max(lastChild[p]??idx[p], i); });
  });
  const lane={}, taken={};                        // taken[sha]=부모 레인을 이미 물려준 자식이 있다
  let maxL=0;
  // **세로 자리는 전체맵과 같은 순서로.** 두 그림을 나란히 두는 이유가 대조인데, 같은 것이
  // 다른 자리에 있으면 대조가 성립하지 않는다(상현님: main 이 아래로 뻗어 너무 다르게 보인다).
  // 위상(점·선)은 날것 그대로다 — 레인 번호는 git 그래프에서 원래 아무 뜻이 없고, 뜻은 선이
  // 진다. 그래서 순서만 층의 선언(main·dev·체인들)에 맞춘다. 사실을 바꾸는 게 아니라
  // **같은 사실을 같은 모양으로** 놓는 일이다. 층이 없는 저장소는 옛 방식(위상)으로 둔다.
  const LANES=(LAYER.lanes||[]);
  const laneOf={}; LANES.forEach((n,i)=>laneOf[n]=i);
  const byLayer=LAYERED && rows.some(c=>c.layer&&laneOf[c.layer]!==undefined);
  old2new.forEach((c,i)=>{
    const ps=(c.parents||[]).filter(p=>idx[p]!==undefined);
    let L=null;
    if(byLayer){
      L = laneOf[c.layer];
      if(L===undefined) L = LANES.length;         // 선언에 없는 것(옛 브랜치 등)은 맨 아래로
      lane[c.sha]=L; if(L>maxL) maxL=L; return;
    }
    for(const p of ps){ if(!taken[p]){ L=lane[p]; taken[p]=true; break; } }
    if(L===null||L===undefined){                  // 뿌리이거나, 부모의 줄기를 이미 형제가 가져갔다
      const busy={};
      old2new.slice(0,i).forEach((o,j)=>{         // 아직 오른쪽으로 갈 길이 남은 레인만 피한다
        if((lastChild[o.sha]??j) >= i) busy[lane[o.sha]]=true;
      });
      L=0; while(busy[L]) L++;
    }
    lane[c.sha]=L; if(L>maxL) maxL=L;
  });
  // **x 는 '부모로부터의 깊이'다**(상현님: 스텝 전체맵과 형제가 다르게 보였다).
  // 로그 순서로 x 를 잡으면 같은 부모에서 갈라진 둘이 서로 다른 칸에 서서 "차례로 이어진 것"
  // 처럼 보인다 — 전체맵은 깊이로 잡아 형제를 **같은 열**에 세운다. 같은 사실은 같은 모양이어야
  // 눈으로 대조할 수 있다.
  const depth={};
  const depthOf=sha=>{
    if(depth[sha]!==undefined) return depth[sha];
    depth[sha]=0;                                  // 순환 방어(있을 수 없지만)
    const c=old2new[idx[sha]];
    let d=0;
    (c&&c.parents||[]).forEach(p=>{ if(idx[p]!==undefined) d=Math.max(d, depthOf(p)+1); });
    return depth[sha]=d;
  };
  old2new.forEach(c=>depthOf(c.sha));
  let maxDepth=0; old2new.forEach(c=>maxDepth=Math.max(maxDepth,depth[c.sha]));
  // **자리를 채운다.** 옛 코드는 colW=15 로 좁게 그린 뒤 width:100%·viewBox 로 늘렸는데,
  // 높이는 px 로 고정이라 SVG 가 비율을 지키며 가운데에 작게 박혔다 — 750px 짜리 칸에 그림은
  // 150px, 점과 이름이 서로 포개졌다(상현님: 너무 겹쳐서 안 보인다). 이제 칸 너비에서 칸 폭을
  // 거꾸로 잡고, SVG 를 그 크기 그대로 놓는다(넘치면 wrap 이 가로로 스크롤한다).
  const laneH=22, padY=16, r=3.5;
  // 레인 이름은 **따로 선 칸**에 세운다(아래 gutter). 옛 방식은 그림 안에 그려서, 그림이
  // 패널보다 넓어 가로로 스크롤하는 순간 이름이 같이 밀려 사라졌다 — 오른쪽을 보는 사람은
  // 어느 줄이 어느 체인인지 알 수 없었다(실측: 그림 2294px, 패널 651px).
  const GUT=byLayer?96:0;
  const padX=14;
  const avail=Math.max(320, (host.clientWidth||760)-28-140-GUT);   // 140 = 오른쪽 이름표 자리
  const colW=Math.max(26, Math.min(72, avail/Math.max(1,maxDepth)));
  const maxLane=maxL;
  const W=Math.max((host.clientWidth-28-GUT)||0, padX+14+Math.max(1,maxDepth)*colW+140);
  // 이름표가 아래·위로 한 줄씩 비킬 자리를 남긴다 — 자리가 없으면 비킴이 곧 실종이 된다.
  const H=padY*2+maxLane*laneH+34;
  const svg=svgEl('svg',{class:'ggsvg',viewBox:'0 0 '+W+' '+H,width:W,height:H});
  const X=sha=>padX+depth[sha]*colW, Y=sha=>padY+lane[sha]*laneH;
  const color=L=>['var(--node)','#3ddc84','#f59e0b','#e0574a','#2dd4bf','#a78bfa'][L%6];
  // 레인 이름 — 어느 줄이 무엇인지 말하지 않으면 순서를 맞춰 놓아도 대조가 안 된다.
  // 이름은 gutter(안 밀리는 칸)에, 줄자(점선)는 그림 안에.
  let gutter=null;
  if(byLayer){
    gutter=svgEl('svg',{class:'gggutter',viewBox:'0 0 '+GUT+' '+H,width:GUT,height:H});
    // **몇 개인지 함께 적는다**(이슈 #100②). 이 그림은 가로로 스크롤되므로, 왼쪽만 보고 있으면
    // 오른쪽에 있는 레인이 **비어 보인다** — 실측: 보이는 폭 529 에 그래프 폭 1416 이라
    // beta·gamma·delta 가 통째로 화면 밖이었고, 그 줄들은 "그 체인엔 아무것도 없다"로 읽혔다.
    // 개수 한 자리가 "없는 것"과 "지금 안 보이는 것"을 가른다.
    const shown={}; rows.forEach(c=>{ shown[c.layer]=(shown[c.layer]||0)+1; });
    LANES.concat(['(그 밖)']).forEach((nm,i)=>{
      if(nm!=='(그 밖)' && !shown[nm])return;
      if(nm==='(그 밖)' && maxL<LANES.length)return;
      const y=padY+i*laneH;
      svg.appendChild(svgEl('line',{class:'gglanerule',x1:0,y1:y,x2:W-6,y2:y}));
      const n=shown[nm]||0;
      const cap=n?' '+n:'';
      const room=13-cap.length;
      const t=svgEl('text',{class:'gglanename'+(nm==='main'?' main':(nm==='dev'?' dev':'')),
        x:GUT-8,y:y+3.5}); t.textContent=(nm.length>room?nm.slice(0,room-1)+'…':nm)+cap;
      t.appendChild(svgEl('title',{},nm+(n?' — 커밋 '+n+'개':''))); gutter.appendChild(t);
    });
  }
  rows.forEach(c=>{
    (c.parents||[]).forEach(p=>{
      if(idx[p]===undefined)return;
      const x1=X(p), y1=Y(p), x2=X(c.sha), y2=Y(c.sha);   // 부모(왼) → 자식(오른)
      const d=(y1===y2)?('M '+x1+' '+y1+' L '+x2+' '+y2)
        :('M '+x1+' '+y1+' L '+(x2-colW*0.6)+' '+y1+' Q '+x2+' '+y1+' '+x2+' '+y2);
      svg.appendChild(svgEl('path',{class:'ggedge',d:d,stroke:color(lane[c.sha]),fill:'none'}));
    });
  });
  const placedRefs=[];  // 이미 놓인 이름표 상자 — 새 이름표는 이걸 피해 앉는다
  rows.forEach(c=>{
    const g=svgEl('g',{class:'ggnode'+(c.gil?' gil':''),transform:'translate('+X(c.sha)+','+Y(c.sha)+')'});
    g.appendChild(svgEl('circle',{r:c.gil?r:r-1.2,fill:color(lane[c.sha])}));
    g.appendChild(svgEl('title',{},c.sha+'  '+c.subj+
      (c.layer?'\n층: '+c.layer:'')+(c.refs?'\n['+c.refs+']':'')));
    svg.appendChild(g);
    // 브랜치 이름은 **그 ref 가 가리키는 커밋에만** 붙인다 — 그게 가지의 끝이다.
    //
    // 그리고 **길게 적지 않는다**(상현님). 40자짜리 이름을 그림에 다 적으면 그림보다 글자가
    // 커져, 이름이 점을 덮고 선을 끊는다. 여기서 눈으로 볼 것은 "몇 갈래로 갈라졌나"지
    // "이름이 무엇인가"가 아니다 — 이름은 **올리면 뜬다**(점 툴팁에 전부, 이름표에도 전문).
    // 한 커밋에 ref 가 여럿이면 첫 하나만 적고 나머지는 +N 으로 접는다.
    //
    // 자리는 점 **오른쪽**에, 겹치면 비킨다. 점 위에 가운데 맞춤으로 얹던 옛 방식은 이름이
    // 길수록 옆 점의 이름을 덮었다(login·login-c1·dev·main 이 한 덩어리로 뭉갰다). 덮인 이름은
    // 없는 이름과 같다 — 이 그림은 "여기서 갈라졌나"를 눈으로 대조하라고 있는 것이라, 어느
    // 가지 이름인지 안 읽히면 대조가 성립하지 않는다.
    const all=(c.refs||'').split(',').map(x=>x.trim()).filter(Boolean);
    // 한 커밋의 ref 는 하나만 적는다(HEAD 가 있으면 그것부터 — 사람이 제일 찾는 자리다).
    const pick=all.find(x=>/HEAD/.test(x))||all[0];
    (pick?[pick]:[]).forEach(rf=>{
      const head=/HEAD/.test(rf);
      const full=rf.replace('HEAD -> ','▶ ').replace(/^tag: /,'🏷 ');
      // 이름은 짧게, 전문은 올리면. 체인 이름이 길수록 뒤가 중요하다(…-c2 가 어느 사이클인지)
      // — 그래서 뒤를 살리고 가운데를 접는다.
      const short=s=>s.length<=16?s:s.slice(0,7)+'…'+s.slice(-8);
      const txt=short(full)+(all.length>1?' +'+(all.length-1):'');
      const w=txt.length*5.8+6;
      // 판 밖으로 나가면 잘린다 — 오른쪽 끝 커밋의 이름표가 그랬다(실측: 이름표 끝 2401px,
      // 판 2294px). 넘칠 것 같으면 점 **왼쪽**에 붙인다. 자리를 못 찾는 것보다 방향을 바꾸는
      // 편이 낫다.
      const right=X(c.sha)+r+5;
      const flip = right+w > W-6;
      const x = flip ? Math.max(padX, X(c.sha)-r-5-w) : right;
      // 기본 자리는 점 **위**다 — 줄에 얹으면 이름이 선을 끊어 가지가 이어져 보이지 않는다.
      const y0=Y(c.sha)-7;
      // 비키는 자리는 **그림 안**이어야 한다. 위로만 밀다가 viewBox 를 넘긴 이름표는 잘려서
      // 아예 사라졌다(login-c1·search-c1 이 y=-24 에 그려졌다) — 겹침을 고치려다 실종을 만든
      // 셈이다. 그래서 후보를 아래·위로 번갈아 내되, 판 밖은 후보에서 뺀다.
      const cand=[y0];
      for(let k=1;k<=6;k++){ cand.push(y0+11*k, y0-11*k); }
      const fits=cand.filter(y=>y>=11 && y<=H-5);
      const free=fits.find(y=>!placedRefs.some(b=>x<b.x2&&x+w>b.x1&&y-9<b.y2&&y+3>b.y1));
      const y=free!==undefined?free:(fits[0]!==undefined?fits[0]:y0);
      placedRefs.push({x1:x,x2:x+w,y1:y-9,y2:y+3});
      const t=svgEl('text',{class:'ggreftxt'+(head?' head':''),x:x,y:y},txt);
      t.appendChild(svgEl('title',{},all.join('\n')));   // 전문은 올리면 뜬다
      svg.appendChild(t);
    });
  });
  const wrap=document.createElement('div'); wrap.className='ggwrap';
  if(gutter){
    const gcol=document.createElement('div'); gcol.className='gggutcol'; gcol.appendChild(gutter);
    const scroll=document.createElement('div'); scroll.className='ggscroll'; scroll.appendChild(svg);
    wrap.classList.add('split'); wrap.appendChild(gcol); wrap.appendChild(scroll);
  }else{
    wrap.appendChild(svg);
  }
  host.replaceChildren(wrap);
}
(function initGitGraph(){
  const det=document.getElementById('det-gitgraph');
  if(!det)return;
  let drawn=false;
  const draw=()=>{ if(drawn)return; drawn=true; step('git 그래프', buildGitGraph); };
  try{ if(localStorage.getItem('gil-gitgraph-open')==='1'){ det.open=true; draw(); } }catch(e){}
  det.addEventListener('toggle',()=>{
    try{ localStorage.setItem('gil-gitgraph-open', det.open?'1':'0'); }catch(e){}
    if(det.open) draw();
  });
})();
// 안내는 **처음 온 사람에게 펼쳐** 둔다. 한 번 접으면 그 브라우저에선 접힌 채 기억한다 —
// 매번 같은 설명을 다시 펼쳐 보이면 그건 안내가 아니라 방해다(#85 의 교훈).
(function initGuide(){
  const g=document.getElementById('guide');
  if(!g)return;
  let closed=false;
  try{ closed=localStorage.getItem('gil-guide-closed')==='1'; }catch(e){}
  g.open=!closed;
  g.addEventListener('toggle',()=>{
    try{ localStorage.setItem('gil-guide-closed', g.open?'0':'1'); }catch(e){}
  });
})();
// ── 인터뷰 폼(이슈 #33) — LLM 이 심은 질문을 사람이 폼으로 답하고 제출하면 레퍼런스가 커밋된다 ──
// 삭제 승인 카드(상현님) — 비가역이라 사람 손에서만 눌린다.
const PRUNES=JSON.parse(document.getElementById('prunedata')?.textContent||'[]');
function buildPrunes(){
  const host=document.getElementById('prunes');
  if(!host||!PRUNES.length)return;
  host.replaceChildren();
  PRUNES.forEach(p=>{
    const card=document.createElement('div'); card.className='prunecard';
    const head=document.createElement('div'); head.className='prunehead';
    head.textContent=T('prune.head',{target:p.target,sha:p.sha});
    const body=document.createElement('div'); body.className='prunebody'; body.textContent=p.body;
    const btn=document.createElement('button'); btn.className='prunebtn'; btn.textContent=T('prune.approve');
    // 요청을 올린 순간 빠져나올 수 없으면 그 문은 문이 아니라 덫이다(이슈 #91). 철회는
    // 아무것도 지우지 않으므로 승인과 같은 무게의 문을 달지 않는다 — 카드만 걷는다.
    const wbtn=document.createElement('button'); wbtn.className='prunewd'; wbtn.textContent=T('prune.withdraw');
    wbtn.title=T('prune.withdraw.title');
    const st=document.createElement('span'); st.style.marginLeft='10px'; st.style.fontSize='12px';
    // **브라우저 대화상자에 문을 걸지 않는다**(이슈 #96). confirm() 이 막히는 환경(차단
    // 설정·자동화 브라우저·포커스를 잃은 창)에서는 아무 흔적 없이 return 해서, 사람 눈에는
    // "버튼이 죽었다"로 보였다. 그리고 승인은 뷰어 전용이라 그 저장소는 정리를 못 했다.
    // 무게는 유지하되(두 번 눌러야 한다) **눌린 것이 눈에 보이게** 카드 안에서 확인받는다.
    let armed=0;
    btn.addEventListener('click',async()=>{
      if(!armed){
        armed=Date.now(); btn.textContent=T('prune.armed2');
        btn.classList.add('armed'); st.textContent=T('prune.armed');
        setTimeout(()=>{ if(armed){ armed=0; btn.textContent=T('prune.approve');
          btn.classList.remove('armed'); st.textContent=T('prune.timeout'); } },5000);
        return;
      }
      armed=0; btn.classList.remove('armed');
      btn.disabled=true; st.textContent=T('prune.approving');
      try{
        const res=await fetch('/prune-approve?target='+encodeURIComponent(p.target),{method:'POST'});
        const t=await res.text();
        // 승인한 사람이 **다음에 무엇을 쳐야 하는지** 그 자리에서 준다(이슈 #96 곁다리):
        // 지금까지는 "CLI 확인 문구가 더 필요하다"고만 하고 그 한 줄을 안 적었다.
        if(res.ok){ st.textContent=T('prune.approved',{target:p.target});
          setTimeout(()=>location.reload(),2500); }
        else{ st.textContent=' ✕ '+t.split('\n')[0]; btn.textContent=T('prune.approve'); btn.disabled=false; }
      }catch(e){ st.textContent=' ✕ '+e; btn.textContent=T('prune.approve'); btn.disabled=false; }
    });
    wbtn.addEventListener('click',async()=>{
      wbtn.disabled=true; st.textContent=T('prune.withdrawing');
      try{
        const res=await fetch('/prune-withdraw?target='+encodeURIComponent(p.target),{method:'POST'});
        const t=await res.text();
        if(res.ok){ st.textContent=T('prune.withdrawn'); setTimeout(()=>location.reload(),900); }
        else{ st.textContent=' ✕ '+t.split('\n')[0]; wbtn.disabled=false; }
      }catch(e){ st.textContent=' ✕ '+e; wbtn.disabled=false; }
    });
    card.appendChild(head); card.appendChild(body); card.appendChild(btn); card.appendChild(wbtn); card.appendChild(st);
    host.appendChild(card);
  });
}
buildPrunes();
// 확정된 기준 문서(상현님) — 제출은 결과가 남아야 제출이다.
const REFERENCES=JSON.parse(document.getElementById('referencedata')?.textContent||'[]');
// refFor — 이 체인의 확정된 기준 문서 하나(없으면 null).
function refFor(chain){
  for(const r of REFERENCES){ if(r.chain===chain) return r; }
  return null;
}

// refBlock — 체인 카드 안에 붙일 기준 문서 블록(상현님).
//
// 왜 여기인가. 확정된 기준은 **그 체인의 것**이다. 상단에 모든 체인 것을 쌓아 두면 첫
// 화면이 그래프가 아니라 남의 체인 문서가 되고(실측: 전체맵까지 스크롤 두 번), 정작
// "지금 보는 체인의 잣대가 무엇인가"는 눈에 안 들어온다. 체인을 누른 자리에서 그 하나만.
//
// 그리고 **마크다운으로 렌더한다.** 기준 문서는 사람이 쓴 산문인데 raw 텍스트로 뿌리면
// 제목·목록이 뭉개져 읽히지 않는다 — 스텝 보고서는 이미 renderMarkdown 을 쓰고 있었다.
function refBlock(chain){
  const r=refFor(chain);
  if(!r)return null;
  const det=document.createElement('details'); det.className='refcard';
  const sum=document.createElement('summary'); sum.className='refsum';
  const state=T(r.waiting?'ref.state.waiting':(r.seen?'ref.state.seen':'ref.state.unseen'));
  sum.textContent=T('ref.pinned',{sha:r.sha})+state;
  det.appendChild(sum);
  const body=document.createElement('div'); body.className='refbody';
  body.innerHTML=renderMarkdown(r.text||T('ref.empty'));
  det.appendChild(body);
  return det;
}

function buildReferences(){
  const host=document.getElementById('references');
  if(!host||!REFERENCES.length)return;
  host.replaceChildren();
  let just=null;
  try{ just=sessionStorage.getItem('gil-just-submitted'); sessionStorage.removeItem('gil-just-submitted'); }catch(e){}
  let shown=0;
  REFERENCES.forEach(r=>{
    // 확정된 기준은 **끝난 것**이다 — 화면을 계속 차지하면 지금 살아 있는 국면을 덮는다
    // (이슈 #85 의 교훈을 이 패널이 먼저 어겼다). 기본은 한 줄, 필요할 때만 펼친다.
    // 한 번 닫으면 그 확정본은 다시 안 뜬다(sha 로 기억 — 새 차수가 오면 다시 뜬다).
    // 확정본은 이제 **체인 카드 안**이 제자리다(상현님). 상단에는 방금 제출한 것만 잠깐
    // 남긴다 — 제출 직후의 "내 답이 도착했나"는 그 자리에서 보여야 하니까(#82).
    if(just!==r.chain)return;
    let dismissed=false;
    try{ dismissed=localStorage.getItem('gil-ref-seen-'+r.chain)===r.sha; }catch(e){}
    if(dismissed)return;
    shown++;
    const card=document.createElement('div'); card.className='refcard';
    const det=document.createElement('details');
    if(just===r.chain)det.open=true;               // 방금 제출한 것만 펼친 채로
    const sum=document.createElement('summary'); sum.className='refsum';
    const state=r.waiting?'⏳ 에이전트가 기다리는 중':(r.seen?'✓ 에이전트가 읽었습니다':'· 아직 안 읽음');
    sum.textContent=(just===r.chain?T('ref.just'):'')+
      T('ref.sum',{chain:r.chain,sha:r.sha})+state;
    det.appendChild(sum);
    const body=document.createElement('div'); body.className='refbody';
    body.innerHTML=renderMarkdown(r.text||T('ref.empty'));
    det.appendChild(body);
    card.appendChild(det);
    const x=document.createElement('button'); x.className='card-close refx'; x.textContent='✕';
    x.title=T('ref.dismiss.title');
    x.addEventListener('click',()=>{
      try{ localStorage.setItem('gil-ref-seen-'+r.chain,r.sha); }catch(e){}
      card.remove();
      if(!host.children.length){ const p=document.getElementById('pane-reference'); if(p)p.style.display='none'; }
    });
    card.appendChild(x);
    host.appendChild(card);
  });
  if(!shown){ const p=document.getElementById('pane-reference'); if(p)p.style.display='none'; }
}
buildReferences();
const INTERVIEWS=JSON.parse(document.getElementById('interviewdata')?.textContent||'[]');
// ── 쓰던 답을 잃지 않는다 (윈도우 필드테스트) ──────────────────────────────────────
// 증상: 인터뷰를 뷰어에서 쓰는 도중 주기적으로 입력이 싹 사라진다. 원인은 폴링의
// location.reload() — 커밋이 하나만 나도 페이지가 통째로 다시 그려지고, 폼은 매번 새로
// 만들어지므로 사람이 쓰던 글이 같이 날아간다. 답을 길게 쓰는 인터뷰일수록 크게 물린다.
//
// 두 겹으로 막는다. (1) **초안 저장** — 입력할 때마다 localStorage 에 넣고 폼을 그릴 때
// 되살린다. 그래서 리로드가 어떤 경로로 오든(수동 F5·서버 재시작 포함) 답은 남는다.
// (2) **쓰는 중엔 리로드를 미룬다** — 초안이 있거나 포커스가 폼 안이면 폴링이 새로고침을
// 보류하고 배너로만 알린다(위 gilSafeReload). 제출로 폼이 깨끗해지면 자동으로 풀린다.
const ivDraftKey=c=>'gil-iv-draft-'+c;
function ivLoadDraft(chain){
  try{ return JSON.parse(localStorage.getItem(ivDraftKey(chain))||'{}')||{}; }catch(e){ return {}; }
}
function ivSaveDraft(chain,form,questions){
  const d={};
  (questions||[]).forEach((q,qi)=>{
    const nm='q'+qi;
    if(q.type==='text'){ const el=form.querySelector('[name="'+nm+'"]'); if(el&&el.value)d[nm]=el.value; }
    else if(q.type==='radio'){ const el=form.querySelector('[name="'+nm+'"]:checked'); if(el)d[nm]=el.value; }
    else if(q.type==='checkbox'){ const v=[...form.querySelectorAll('[name="'+nm+'"]:checked')].map(e=>e.value); if(v.length)d[nm]=v; }
  });
  try{
    if(Object.keys(d).length) localStorage.setItem(ivDraftKey(chain),JSON.stringify(d));
    else localStorage.removeItem(ivDraftKey(chain));
  }catch(e){}
}
function ivClearDraft(chain){ try{ localStorage.removeItem(ivDraftKey(chain)); }catch(e){} }
// 지금 사람이 쓰고 있는가 — 초안이 하나라도 있거나, 포커스가 인터뷰 폼 안에 있으면 참.
window.__gilIvDirty=function(){
  const a=document.activeElement;
  if(a&&a.closest&&a.closest('.ivform'))return true;
  for(const iv of INTERVIEWS){ if(Object.keys(ivLoadDraft(iv.chain)).length)return true; }
  return false;
};
// 리로드를 미뤘다는 사실을 **말한다** — 관전 도구의 침묵은 '이상 없음'과 구분되지 않는다.
window.__gilIvNotifyStale=function(){
  if(document.getElementById('ivstalebar'))return;
  const bar=document.createElement('div'); bar.id='ivstalebar'; bar.className='ivwait on';
  bar.style.cssText='margin:8px 12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap';
  const t=document.createElement('span');
  t.textContent=T('iv.deferred');
  const b=document.createElement('button'); b.className='ivsubmit'; b.textContent=T('iv.refresh');
  b.title=T('iv.refresh.title');
  b.addEventListener('click',()=>location.reload());
  bar.appendChild(t); bar.appendChild(b);
  const host=document.getElementById('interviews');
  if(host&&host.parentNode)host.parentNode.insertBefore(bar,host);
  else document.body.insertBefore(bar,document.body.firstChild);
};
function buildInterviews(){
  const host=document.getElementById('interviews');
  if(!host||!INTERVIEWS.length)return;
  host.replaceChildren();
  INTERVIEWS.forEach(iv=>{
    const card=document.createElement('div'); card.className='ivcard';
    const head=document.createElement('div'); head.className='ivhead';
    head.innerHTML=T('iv.head',{chain:esc(iv.chain)});
    card.appendChild(head);
    // 기다리는 사람이 보이게(이슈 #82) — 제출하고 아무 반응이 없으면 "놓쳤나"를 의심하게 된다.
    const wait=document.createElement('div');
    wait.className='ivwait'+(iv.waiting?' on':'');
    wait.textContent=T(iv.waiting?'iv.waiting':'iv.notwaiting');
    card.appendChild(wait);
    const form=document.createElement('form'); form.className='ivform';
    const draft=ivLoadDraft(iv.chain);            // 앞선 리로드에서 살아남은 초안
    (iv.questions||[]).forEach((q,qi)=>{
      const fld=document.createElement('div'); fld.className='ivfield';
      const label=document.createElement('label'); label.className='ivq';
      label.textContent=(qi+1)+'. '+(q.q||''); fld.appendChild(label);
      const nm='q'+qi;
      if(q.type==='text'){
        const ta=document.createElement('textarea'); ta.name=nm; ta.rows=3; ta.className='ivinput';
        if(typeof draft[nm]==='string')ta.value=draft[nm];
        fld.appendChild(ta);
      } else if(q.type==='radio'||q.type==='checkbox'){
        const opts=document.createElement('div'); opts.className='ivopts';
        (q.options||[]).forEach((o,oi)=>{
          const id=nm+'_'+oi;
          const wrap=document.createElement('label'); wrap.className='ivopt';
          const inp=document.createElement('input'); inp.type=q.type; inp.name=nm; inp.value=o; inp.id=id;
          const dv=draft[nm];
          if(q.type==='radio'&&dv===o)inp.checked=true;
          if(q.type==='checkbox'&&Array.isArray(dv)&&dv.indexOf(o)>=0)inp.checked=true;
          const span=document.createElement('span'); span.textContent=o;
          wrap.appendChild(inp); wrap.appendChild(span); opts.appendChild(wrap);
        });
        fld.appendChild(opts);
      }
      form.appendChild(fld);
    });
    const foot=document.createElement('div'); foot.className='ivfoot';
    const submit=document.createElement('button'); submit.type='submit'; submit.className='ivsubmit'; submit.textContent=T('iv.submit');
    const status=document.createElement('span'); status.className='ivstatus';
    foot.appendChild(submit); foot.appendChild(status);
    form.appendChild(foot);
    // 한 글자 칠 때마다 초안을 남긴다 — 리로드·서버 재시작·탭 닫힘 어느 쪽에도 안 진다.
    const saveNow=()=>ivSaveDraft(iv.chain,form,iv.questions);
    form.addEventListener('input',saveNow);
    form.addEventListener('change',saveNow);
    if(Object.keys(draft).length){
      const back=document.createElement('div'); back.className='ivwait';
      back.textContent=T('iv.restored');
      form.insertBefore(back,form.firstChild);
    }
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
      submit.disabled=true; status.textContent=T('iv.saving');
      try{
        const res=await fetch('/interview?chain='+encodeURIComponent(iv.chain),
          {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(answers)});
        const txt=await res.text();
        if(res.ok){
          status.textContent=T('iv.saved');
          ivClearDraft(iv.chain);   // 도착한 뒤에만 지운다(제출 실패면 초안은 그대로 남는다)
          try{ sessionStorage.setItem('gil-just-submitted',iv.chain); }catch(e){}
          setTimeout(()=>location.reload(),700);
        }
        else{ status.textContent=' ✕ '+txt.split('\n')[0]; submit.disabled=false; }
      }catch(e){
        // "TypeError: Failed to fetch" 는 사람에게 아무것도 안 알려준다(상현님 실사용).
        // 이 자리에 오는 원인은 대개 하나다 — **이 페이지를 만든 서버가 이미 없다**(뷰어를
        // 껐거나 다시 띄웠거나, 옛 탭을 그대로 두고 있었다). 답은 사라지지 않았다: 아직
        // 제출되지 않았을 뿐이라, 새로고침한 뒤 다시 누르면 된다. 그 사실을 말한다.
        // 서버가 살아 있나 되묻는다. 주소는 폴링 스크립트가 심어 둔 것을 쓴다 — 정적
        // build 에는 서버가 없고, 이 문자열이 정적 산출물에 섞이면 자기완결이 깨진다.
        let alive=false;
        const probe=window.__gilPollUrl;
        if(probe){ try{ const p=await fetch(probe,{cache:'no-store'}); alive=p.ok; }catch(_){} }
        status.textContent=alive?(T('iv.failed')+e):
          ' ✕ 뷰어 서버에 닿지 못했습니다 — 이 페이지를 띄운 서버가 꺼졌거나 다시 떴습니다.';
        if(!alive){
          const hint=document.createElement('div');
          hint.className='ivwait';
          hint.innerHTML=T('iv.failed.hint')+
            '<br>서버가 꺼져 있으면 터미널에서: <code>gil viewer serve</code>';
          form.appendChild(hint);
        }
        submit.disabled=false;
      }
    });
    card.appendChild(form); host.appendChild(card);
  });
}
function esc(s){ const d=document.createElement('div'); d.textContent=s==null?'':s; return d.innerHTML; }
document.querySelectorAll('#depthseg button').forEach(b=>b.addEventListener('click',()=>setMapDepth(b.dataset.depth))); // 뎁스 토글(AIL #6)
// 한 조각이 죽어도 나머지는 그린다 — 특히 **인터뷰 폼**은 사람이 답할 유일한 수단이라
// 앞 단계의 예외에 같이 묻히면 안 된다. 그리고 죽었다는 사실을 **화면에 띄운다**:
// 관전 도구의 침묵은 '이상 없음'과 구분되지 않는다(이슈 #84·#90).
function step(name, fn){
  try{ fn(); }catch(e){
    console.error('[gil viewer] '+name+' 실패:', e);
    const b=document.createElement('div');
    b.style.cssText='margin:8px 12px;padding:8px 12px;border:1px solid #c33;border-radius:6px;color:#c33;font:12px ui-monospace,monospace';
    b.textContent=T('viewer.partfail',{name:name,err:(e&&e.message||e)});
    document.body.insertBefore(b, document.body.firstChild);
  }
}
step('화면 언어', ()=>{ applyLang(); buildLangToggle(); }); // 그림보다 먼저 — 범례가 맞는 언어로 나야 한다
step('전체맵', buildStepMap);          // 전체맵은 항상 맨 위에 렌더(탭 없음). 기본 뎁스=step.
step('체인그래프 줌', enableChainGraphZoom); // 이슈 #79
step('인터뷰 폼', buildInterviews);     // 사람 답 대기 인터뷰 폼(이슈 #33)
step('선택 복원', restoreSel);
`
