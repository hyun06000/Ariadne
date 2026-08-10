// serve.go — 브라우저 관전 서버. 대상 레포(--repo)의 gil 그래프를 HTML 로 그리고
// 팁 시그니처 폴링으로 자동 새로고침. stdlib 만.
package main

import (
	"encoding/json"
	"fmt"
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
	// 옮겨 적는 규칙은 **한 벌이다**(intake.go 의 writeRefSections) — 여기와 카드 쪽이 두
	// 벌이던 동안 카드 쪽만 #109 를 안 배웠고, 그 차이가 조용히 체인 목적을 오염시켰다.
	// 이 함수가 하는 일은 이제 답의 **모양을 알아보는 것**뿐이다(배열이냐 문자열이냐).
	secs := make([]refSection, 0, len(answers))
	for _, a := range answers {
		s := refSection{Q: a.Q}
		var arr []string
		if json.Unmarshal(a.Answer, &arr) == nil {
			s.List, s.Items = true, arr
		} else if err := json.Unmarshal(a.Answer, &s.Text); err != nil {
			s.Text = "" // 알아볼 수 없는 답은 없는 답으로 — 지어내지 않는다
		}
		secs = append(secs, s)
	}
	var b strings.Builder
	b.WriteString("# 기준 문서 (레퍼런스 트루스) — " + chain + "\n\n")
	b.WriteString("이 체인의 사이클·가설·성패판정이 비추어야 할 기준. 사람과의 인터뷰로 확정됐다.\n\n")
	writeRefSections(&b, secs)
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
