// git.go — git 서브프로세스 껍질 + 커밋 그래프 파싱.
//
// gil은 git 래퍼다. 진실원은 언제나 커밋 그래프이고, 이 파일은 그걸 파싱하는 얇은 층.
// 참조 구현(gil.py)의 _git·collect_nodes·body_index를 그대로 옮긴다 — 로직 1:1, 언어만 Go.
// 외부 의존성 0: 표준 라이브러리만. git은 라이브러리가 아니라 도구 의존(os/exec).
package main

import (
	"errors"
	"os"
	"os/exec"
	"sort"
	"strings"
	"sync"
	"time"
)

const (
	sep  = "\x1e" // 레코드 구분자 (커밋 사이)
	fsep = "\x1f" // 필드 구분자
	nul  = "\x00" // 멀티값 트레일러 구분자
)

// git 은 git을 실행하고 stdout을 준다. 실패하면 exit(참조: check=True).
func git(args ...string) string {
	out, err := gitTry(args...)
	if err != nil {
		die("git " + strings.Join(args, " ") + " 실패: " + err.Error())
	}
	return out
}

// gitCommand — 모든 git 자식 프로세스는 이걸 거친다. 윈도우에서 콘솔 창이 번쩍이지 않게
// hideConsole 을 붙인다(콘솔 없는 부모가 gil 을 돌릴 때, git 호출마다 cmd 창이 계단식으로
// 뜨고 꺼지는 실사용 공포 방지). 유닉스에선 no-op 이라 무해하다.
func gitCommand(args ...string) *exec.Cmd {
	cmd := exec.Command("git", args...)
	hideConsole(cmd)
	traceGit(cmd, args)
	return cmd
}

// ── GIL_TRACE — "느리다"를 "여기서 느리다"로 바꾼다 (이슈 #88) ──
//
// 실사용 보고: fsck 7분·handoff 5분인데 CPU 누적은 0.12초. 계산이 아니라 **기다림**인데,
// 사용자가 말할 수 있는 건 "느리다"뿐이었다. 관전 도구의 침묵과 같은 병이다(#84·#87) —
// 도구가 자기 시간을 못 보여주면 원인 규명이 통째로 사람 몫이 된다.
//
// GIL_TRACE=1 → 종료 시 요약(호출 수·총 시간·가장 느린 호출 10개).
// GIL_TRACE=all → 호출마다 한 줄씩(폭주하는 호출 패턴을 눈으로 본다).
var (
	traceOn    = os.Getenv("GIL_TRACE")
	traceStart = time.Now()
	traceCalls []traceRec
	traceMu    sync.Mutex
)

type traceRec struct {
	args []string
	dur  time.Duration
}

// traceGit — 자식 프로세스의 실제 소요를 재도록 Cmd 를 감싼다. exec.Cmd 에는 훅이 없어
// Wait 를 가로챌 수 없으므로, 시작 시각을 기록해 두고 종료 시각을 Cancel/Wait 대신
// **호출자 쪽 래퍼**(gitTry/gitOK/gitInput)가 아니라 여기서 프로세스 상태로 잡는다.
func traceGit(cmd *exec.Cmd, args []string) {
	if traceOn == "" {
		return
	}
	traceMu.Lock()
	traceCalls = append(traceCalls, traceRec{args: args})
	traceIndex[cmd] = traceEntry{idx: len(traceCalls) - 1, start: time.Now()}
	traceMu.Unlock()
}

type traceEntry struct {
	idx   int
	start time.Time
}

var traceIndex = map[*exec.Cmd]traceEntry{}

// traceDone — git 자식이 끝난 직후 호출. 소요를 채우고 GIL_TRACE=all 이면 한 줄 찍는다.
func traceDone(cmd *exec.Cmd) {
	if traceOn == "" {
		return
	}
	traceMu.Lock()
	e, ok := traceIndex[cmd]
	if !ok {
		traceMu.Unlock()
		return
	}
	delete(traceIndex, cmd)
	d := time.Since(e.start)
	traceCalls[e.idx].dur = d
	rec := traceCalls[e.idx]
	traceMu.Unlock()
	if traceOn == "all" {
		stderr("  [trace] " + d.Round(time.Millisecond).String() + "  git " + traceArgs(rec.args))
	}
}

func traceArgs(args []string) string {
	s := strings.Join(args, " ")
	if len(s) > 120 {
		s = s[:120] + "…"
	}
	return s
}

// traceSummary — 종료 직전 요약. 호출 수가 폭주하는지, 한 호출이 오래 잡는지를 가른다.
func traceSummary() {
	if traceOn == "" {
		return
	}
	traceMu.Lock()
	recs := append([]traceRec(nil), traceCalls...)
	traceMu.Unlock()
	var total time.Duration
	for _, r := range recs {
		total += r.dur
	}
	wall := time.Since(traceStart)
	stderr("")
	stderr("── GIL_TRACE 요약 ──")
	stderr("  벽시계 " + wall.Round(time.Millisecond).String() +
		"  ·  git 호출 " + itoa(len(recs)) + "회, 합계 " + total.Round(time.Millisecond).String() +
		"  ·  git 밖 " + (wall - total).Round(time.Millisecond).String())
	if wall-total > wall/2 && wall > time.Second {
		stderr("  ⚠ 시간의 절반 이상이 git 밖에 있다 — 계산도 자식 프로세스도 아닌 기다림이다.")
	}
	// 같은 스캔을 몇 번 반복하는가 — 한 호출이 느린 것과 같은 걸 백 번 부르는 것은 처방이
	// 다르다. 큰 저장소에서 무너지는 쪽은 대개 후자다(전체 스캔 하나가 수 초면 71회는 몇 분).
	type agg struct {
		n   int
		sum time.Duration
	}
	byArgs := map[string]*agg{}
	for _, r := range recs {
		k := traceArgs(r.args)
		a := byArgs[k]
		if a == nil {
			a = &agg{}
			byArgs[k] = a
		}
		a.n++
		a.sum += r.dur
	}
	var keys []string
	for k, a := range byArgs {
		if a.n > 1 {
			keys = append(keys, k)
		}
	}
	sort.SliceStable(keys, func(i, j int) bool { return byArgs[keys[i]].sum > byArgs[keys[j]].sum })
	if len(keys) > 0 {
		stderr("  반복된 스캔(같은 인자) — 여기가 큰 저장소에서 몇 분이 되는 자리다:")
		for i, k := range keys {
			if i >= 5 {
				break
			}
			stderr("    ×" + itoa(byArgs[k].n) + "  " + byArgs[k].sum.Round(time.Millisecond).String() + "  git " + k)
		}
	}
	sort.SliceStable(recs, func(i, j int) bool { return recs[i].dur > recs[j].dur })
	n := 10
	if len(recs) < n {
		n = len(recs)
	}
	stderr("  가장 느린 호출:")
	for i := 0; i < n; i++ {
		stderr("    " + recs[i].dur.Round(time.Millisecond).String() + "  git " + traceArgs(recs[i].args))
	}
}

// ── 읽기 캐시 — 같은 스캔을 두 번 돌지 않는다 (이슈 #88) ──
//
// 실측: handoff 한 번에 git 호출 71회, 그중 24회가 **인자까지 똑같은 전체 브랜치 스캔**이다.
// 작은 저장소에선 스캔 하나가 20ms 라 안 보이지만, 브랜치 97개·오펀 커밋 1295개인 실사용
// 저장소에선 스캔 하나가 수 초다 — 그러면 24번의 중복이 곧 몇 분이 된다. gil 프로세스의
// CPU 가 0.12초인데 벽시계가 5분인 모양이 정확히 이것이다: 일은 전부 git 자식이 한다.
//
// gil 한 번의 실행은 한 가지 일만 하므로 프로세스 수명 동안 읽기 결과는 안 변한다 — 단
// **쓰기가 한 번이라도 일어나면 통째로 버린다**(캐시가 거짓말하지 않게 하는 유일한 규칙).
var gitReadCache = map[string]gitCached{}

// gitCacheOn — **짧게 살다 죽는 CLI 명령에서만** 캐시가 참이다. 오래 사는 프로세스
// (viewer serve · mcp serve · --wait 폴링)에서는 저장소가 밖에서 바뀌므로 캐시가 곧
// 거짓말이 된다 — 실제로 --wait 이 첫 응답에 얼어붙었다(테스트가 잡았다). 그런 경로는
// 시작할 때 stopGitCache() 로 끈다.
var gitCacheOn = true

// stopGitCache — 오래 사는 모드로 들어간다. 이후 모든 읽기는 매번 git 에 되묻는다.
func stopGitCache() {
	gitCacheOn = false
	gitReadCache = map[string]gitCached{}
}

type gitCached struct {
	out string
	err error
}

// gitReadOnly — 저장소를 바꾸지 않는 명령인가. 보수적으로 **확실한 읽기만** 넣는다.
func gitReadOnly(args []string) bool {
	if len(args) == 0 {
		return false
	}
	switch args[0] {
	case "log", "for-each-ref", "rev-list", "ls-tree", "cat-file", "merge-base", "show":
		return true
	case "rev-parse", "symbolic-ref":
		// --abbrev-ref/--verify 등 조회형만. 쓰기 옵션이 섞이면 캐시하지 않는다.
		for _, a := range args {
			if a == "--" || strings.HasPrefix(a, "--git-path") {
				return false
			}
		}
		return true
	}
	return false
}

// gitTry 는 git을 실행하고 (stdout, err). 호출자가 실패를 흡수할 수 있게 한다.
func gitTry(args ...string) (string, error) {
	key := ""
	if gitCacheOn && gitReadOnly(args) {
		key = strings.Join(args, nul)
		if c, ok := gitReadCache[key]; ok {
			return c.out, c.err
		}
	} else {
		// 쓰기(commit·branch·checkout·update-ref…)가 지나갔다 — 읽기 캐시는 여기서 죽는다.
		gitReadCache = map[string]gitCached{}
	}
	cmd := gitCommand(args...)
	var out, errOut strings.Builder
	cmd.Stdout = &out
	// git 의 stderr 를 삼키지 않는다(이슈 #64③). "exit status 128" 한 줄만 나오면 원인을
	// 좁힐 수 없다 — 실사용에서 뷰어와의 index.lock 경합을 찾는 데 그 한 줄이 없어 오래 걸렸다.
	cmd.Stderr = &errOut
	err := cmd.Run()
	traceDone(cmd)
	if err != nil && strings.TrimSpace(errOut.String()) != "" {
		err = errors.New(err.Error() + " — " + strings.TrimSpace(errOut.String()))
	}
	if key != "" {
		gitReadCache[key] = gitCached{out: out.String(), err: err}
	}
	return out.String(), err
}

// gitInput 은 stdin으로 msg를 넣고 git을 실행한다(commit/hash-object/mktree/commit-tree).
func gitInput(msg string, args ...string) string {
	// 여기는 **쓰기 통로**다(commit-tree·hash-object·mktree). 읽기 캐시를 안 버리면 방금
	// 만든 노드가 안 보인다 — 실제로 위치 카드가 자기 스텝을 못 찾았다. 캐시는 쓰기를
	// 놓치는 순간 거짓말이 된다.
	gitReadCache = map[string]gitCached{}
	cmd := gitCommand(args...)
	cmd.Stdin = strings.NewReader(msg)
	var out, errOut strings.Builder
	cmd.Stdout = &out
	cmd.Stderr = &errOut // 원인을 삼키지 않는다(이슈 #64③)
	if err := cmd.Run(); err != nil {
		if e := strings.TrimSpace(errOut.String()); e != "" {
			err = errors.New(err.Error() + " — " + e)
		}
		die("git " + strings.Join(args, " ") + " 실패: " + err.Error())
	}
	return out.String()
}

// gitOK 는 git을 실행하고 성공 여부만 준다(merge-base --is-ancestor 등 판정용).
func gitOK(args ...string) bool {
	if gitCacheOn && gitReadOnly(args) {
		_, err := gitTry(args...) // 캐시 경유 — 같은 존재 판정을 수십 번 되묻는다
		return err == nil
	}
	gitReadCache = map[string]gitCached{}
	cmd := gitCommand(args...)
	err := cmd.Run()
	traceDone(cmd)
	return err == nil
}

// gitlog 는 git log 래퍼. 커밋 0개(HEAD 부재)면 빈 문자열 — 오류가 아니라 '노드 없음'.
// 참조: _gitlog. 첫 체인을 여는 빈 저장소에서 git log는 exit 128로 죽지만 정상 흐름이다.
func gitlog(args ...string) string {
	out, err := gitTry(append([]string{"log"}, args...)...)
	if err != nil {
		return ""
	}
	return out
}

// node — 스텝 노드(Gil-Step 트레일러를 가진 커밋). 참조: collect_nodes의 dict.
type node struct {
	sha          string
	subject      string
	chain        string
	cycle        string
	step         string
	kind         string
	parent       string
	author       string
	cycleParents []string
	outcome      string
	backtrack    string
	merges       []string
	verdict      string   // verify 스텝: supported|refuted (제안 1, AIL #1)
	falsify      string   // hypothesis 스텝: 반증조건 (제안 2, AIL #1)
	refutes      []string // 이 스텝/사이클이 소급 반증하는 verify 스텝들 (제안 B, AIL #1)
	refines      []string // 이 스텝/사이클이 해석을 정밀화하는 verify·analyze 스텝들 (이슈 #42)
	inherit      string   // 부모에게서 물려받은 지식·전제·교훈 (AIL #3)
	supersedes   string   // 이 스텝이 정정(대체)하는 앞선 같은-kind 스텝 (AIL #12)
	polarity     string   // hypothesis 극성: supported 면 목표 달성(goal-met)인가 실패(goal-missed)인가 (AIL #13)
	plan         string   // hypothesis: 가설 전에 고정한 설계 — 이번에 무엇을 몇 개 만들 것인가 (이슈 #76)
	planOutcome  string   // verify: 그 설계가 유지됐나 — held|broke (이슈 #76)
	planDiff     string   // verify: 깨졌으면 무엇이 달랐나 (이슈 #76)
	advances     string   // hypothesis: 이 가설이 **체인 목적**에 얼마나·어떻게 다가서게 하나 (상현님)
	toward       string   // success/fail: 그래서 체인 목적에 얼마나 가까워졌나 (회고)
	nextDesign   string   // success/fail: 목적을 이루기 위한 **다음 설계**는 무엇인가
	falsifyTo    string   // hypothesis: 반증되면 되돌아갈 조상 define|analyze (퇴로)
	falsifyOut   string   // verify: 반증조건이 충족됐나 — met|unmet (규칙 17)
	falsifyObs   string   // verify: 그 판단의 근거가 된 관측
	finding      string   // analyze: 이 분석이 밝힌 것(결론 한 줄) — 재분기가 딛는 문장(상현님)
	despiteMap   string   // hypothesis: 벽의 지도와 다른 자리에서 갈라진 이유(상현님)
}

// collectNodes — 커밋 그래프를 훑어 Gil-Step 트레일러를 가진 커밋을 스텝 노드로 수집.
// 참조: collect_nodes. 단일 git log로 모든 트레일러를 뽑는다(스텝별 fork 없음).
func collectNodes(revRange string) []node {
	fmt := strings.Join([]string{
		"%H", "%s",
		trailer("Gil-Chain"),
		trailer("Gil-Cycle"),
		trailer("Gil-Step"),
		trailer("Gil-Kind"),
		trailer("Gil-Parent"),
		trailer("Gil-Cycle-Author"),
		trailerMulti("Gil-Cycle-Parent"),
		trailer("Gil-Outcome"),
		trailer("Gil-Backtrack"),
		trailerMulti("Gil-Merge"),
		trailer("Gil-Verdict"),
		trailer("Gil-Falsify"),
		trailerMulti("Gil-Refutes"),
		trailerMulti("Gil-Refines"),
		trailer("Gil-Inherit"),
		trailer("Gil-Supersedes"),
		trailer("Gil-Goal-Polarity"),
		trailer("Gil-Plan"),
		trailer("Gil-Plan-Outcome"),
		trailer("Gil-Plan-Diff"),
		trailer("Gil-Advances"),
		trailer("Gil-Toward"),
		trailer("Gil-Next-Design"),
		trailer("Gil-Falsify-To"),       // 반증 시 되돌아갈 자리 — 위치 카드의 '퇴로' 칸(상현님)
		trailer("Gil-Falsify-Outcome"),  // verify: 반증조건이 충족됐나 met|unmet (규칙 17)
		trailer("Gil-Falsify-Observed"), // verify: 그래서 무엇을 관측했나
		trailer("Gil-Finding"),          // analyze 의 결론 — 지식 누적이 인용하는 문장
		trailer("Gil-Despite-Map"),      // 벽의 지도를 벗어난 재분기의 이유
	}, fsep) + sep
	// revRange 뒤 "--" 로 revision 확정 — 체인/브랜치명이 디렉토리명과 겹치면(예: viewer)
	// git 이 revision/path ambiguity 로 exit 128 로 죽는다(실사용 발견, viewer 실작업).
	out := gitlog("--format="+fmt, revRange, "--")
	var nodes []node
	for _, rec := range strings.Split(out, sep) {
		rec = strings.Trim(rec, "\n")
		if rec == "" {
			continue
		}
		f := strings.Split(rec, fsep)
		if len(f) < 30 {
			continue
		}
		step := strings.TrimSpace(f[4])
		if step == "" { // Gil-Step 없으면 일반 커밋
			continue
		}
		nodes = append(nodes, node{
			sha:          first9(f[0]),
			subject:      f[1],
			chain:        strings.TrimSpace(f[2]),
			cycle:        strings.TrimSpace(f[3]),
			step:         step,
			kind:         strings.TrimSpace(f[5]),
			parent:       strings.TrimSpace(f[6]),
			author:       strings.TrimSpace(f[7]),
			cycleParents: splitMulti(f[8]),
			outcome:      strings.TrimSpace(f[9]),
			backtrack:    strings.TrimSpace(f[10]),
			merges:       splitMulti(f[11]),
			verdict:      strings.TrimSpace(f[12]),
			falsify:      strings.TrimSpace(f[13]),
			refutes:      splitMulti(f[14]),
			refines:      splitMulti(f[15]),
			inherit:      strings.TrimSpace(f[16]),
			supersedes:   strings.TrimSpace(f[17]),
			polarity:     strings.TrimSpace(f[18]),
			plan:         strings.TrimSpace(f[19]),
			planOutcome:  strings.TrimSpace(f[20]),
			planDiff:     strings.TrimSpace(f[21]),
			advances:     strings.TrimSpace(f[22]),
			toward:       strings.TrimSpace(f[23]),
			nextDesign:   strings.TrimSpace(f[24]),
			falsifyTo:    strings.TrimSpace(f[25]),
			falsifyOut:   strings.TrimSpace(f[26]),
			falsifyObs:   strings.TrimSpace(f[27]),
			finding:      strings.TrimSpace(f[28]),
			despiteMap:   strings.TrimSpace(f[29]),
		})
	}
	return nodes
}

// bodyIndex — sha(9자) → 순수 본문(트레일러 제외) 인덱스를 단일 git log로.
// 참조: body_index. 스텝별 fork를 없앤다(62초 벽 → O(1), gil-v3-study/c002/s4).
func bodyIndex(revRange string) map[string]string {
	fmt := "%H" + fsep + "%b" + sep
	out := git("log", "--format="+fmt, revRange, "--") // "--": revision 확정(path ambiguity 방지)
	idx := map[string]string{}
	for _, rec := range strings.Split(out, sep) {
		rec = strings.Trim(rec, "\n")
		if rec == "" {
			continue
		}
		f := strings.SplitN(rec, fsep, 2)
		if len(f) < 2 {
			continue
		}
		idx[first9(f[0])] = stripTrailers(strings.TrimRight(f[1], "\n"))
	}
	return idx
}

var trailerPrefixes = []string{"Gil-", "Co-Authored-By:", "Co-authored-by:", "Signed-off-by:"}

// stripTrailers — 본문 끝의 트레일러 블록(알려진 키로 시작하는 라인)을 걷어낸다.
// 참조: _strip_trailers. 본문에도 콜론이 흔하므로 알려진 접두사로만 엄격히 구분한다.
func stripTrailers(body string) string {
	lines := strings.Split(body, "\n")
	end := len(lines)
	for end > 0 {
		ln := strings.TrimSpace(lines[end-1])
		if ln == "" {
			end--
			continue
		}
		if hasAnyPrefix(ln, trailerPrefixes) {
			end--
		} else {
			break
		}
	}
	return strings.TrimSpace(strings.Join(lines[:end], "\n"))
}

// ── 작은 헬퍼들 ─────────────────────────────────────────────────────────

func trailer(key string) string {
	return "%(trailers:key=" + key + ",valueonly)"
}

func trailerMulti(key string) string {
	return "%(trailers:key=" + key + ",valueonly,separator=%x00)"
}

func splitMulti(s string) []string {
	var out []string
	for _, x := range strings.Split(s, nul) {
		if strings.TrimSpace(x) != "" {
			out = append(out, strings.TrimSpace(x))
		}
	}
	return out
}

func first9(s string) string {
	if len(s) > 9 {
		return s[:9]
	}
	return s
}

func hasAnyPrefix(s string, prefixes []string) bool {
	for _, p := range prefixes {
		if strings.HasPrefix(s, p) {
			return true
		}
	}
	return false
}

// dieHooks — die 직전에 불릴 정리·보고 훅(이슈 #64②). os.Exit 는 defer 를 돌리지 않으므로,
// "중간까지 만들어 둔 것"을 알리려면 여기 걸어야 한다. 훅은 지우지 않고 **말한다** —
// 무엇이 남았고 어떻게 치우는지. 사람 몰래 브랜치를 지우는 것보다, 남은 걸 정확히 알려주는
// 편이 append-only 도구의 태도에 맞는다.
var dieHooks []func()

func onDie(f func()) { dieHooks = append(dieHooks, f) }

func runDieHooks() {
	for _, f := range dieHooks {
		f()
	}
	dieHooks = nil
}

func die(msg string) {
	// MCP 서버로 돌 때는 프로세스를 죽이면 안 된다 — 한 번의 거부가 세션 전체를 끊는다.
	// 거부는 그 툴 호출의 에러로만 올라가야 한다(gilAbort 로 panic → 핸들러가 recover).
	if mcpMode {
		runDieHooks()
		panic(gilAbort{msg: msg, code: 1})
	}
	os.Stderr.WriteString(msg + "\n")
	traceSummary() // 거부로 끝나도 시간은 밝힌다 — 느린 거부가 제일 답답하다(이슈 #88)
	runDieHooks() // 원인을 먼저, 뒷정리 안내는 그 다음(이슈 #64②)
	os.Exit(1)
}

// gilExit — os.Exit 를 쓰던 자리. MCP 모드에서는 종료 대신 그 호출만 끝낸다.
func gilExit(code int) {
	if mcpMode {
		panic(gilAbort{code: code})
	}
	traceSummary() // os.Exit 는 defer 를 건너뛴다 — 여기서도 시간을 밝힌다(이슈 #88)
	os.Exit(code)
}
