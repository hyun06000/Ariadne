// gil mcp serve — gil 을 MCP 서버로 연다 (단계 A+B).
//
// 왜. 인터뷰가 두 채널로 쪼개져 있었다: LLM 은 대화창에서 질문지를 만들고, 사람은 뷰어 폼에서
// 답한다. 둘이 서로를 모르니 LLM 은 pending 인 줄 모르고 또 질문지를 만들고, 사람은 127.0.0.1
// 링크·포트충돌과 씨름했다(상현님 실사용, gil-test-2). MCP 는 정확히 이 구멍을 메운다 —
// 호스트(Claude Desktop 등)가 gil 툴을 직접 호출하고, 인터뷰는 Elicitation 으로 **그 자리에서**
// 네이티브 폼을 띄워 답을 받는다. 채널이 하나가 된다.
//
// 설계 원칙 두 가지.
//  1. 얇은 래퍼. 툴 핸들러는 기존 cmd* 함수를 그대로 부른다. 검증·문법 거부(인터뷰 필수·pending
//     잠금 등)가 CLI 와 MCP 에서 갈라지지 않게 — 규율은 한 곳에만 산다.
//  2. CLI 병존. gil mcp serve 는 새 진입점일 뿐, 기존 gil open… CLI 는 그대로다(터미널·Cursor용).
package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// mcpMode — 켜지면 die/os.Exit 가 프로세스를 죽이지 않고 그 호출만 끝내며(gilAbort),
// 모든 출력이 stdout 대신 mcpOut 버퍼로 간다(stdout 은 JSON-RPC 전송선이다).
var mcpMode bool
var mcpOut strings.Builder

// mcpRepoMismatch — 설정의 --repo 와 호스트가 연 폴더가 어긋날 때의 경고문(이슈 #49).
// 비면 어긋남 없음. 모든 툴 응답 머리에 붙어, 조용한 실패가 조용하지 않게 만든다.
var mcpRepoMismatch string

// gilAbort — die/gilExit 가 MCP 모드에서 던지는 값. 핸들러가 recover 해 툴 에러로 바꾼다.
type gilAbort struct {
	msg  string
	code int
}

// runGil — 기존 cmd* 함수를 한 번 돌리고 그 출력을 회수한다. 거부(die)는 error 로 올라간다.
// 출력이 전역 버퍼라 동시 호출은 섞인다 — MCP stdio 세션은 요청을 순차 처리하므로 직렬화는
// 여기서 mcpLock 으로 못박는다.
func runGil(fn func()) (out string, err error) {
	mcpLock.Lock()
	defer mcpLock.Unlock()
	mcpOut.Reset()
	defer func() {
		if r := recover(); r != nil {
			a, ok := r.(gilAbort)
			if !ok {
				panic(r)
			}
			out = mcpOut.String()
			msg := a.msg
			if msg == "" {
				msg = "gil: 종료 코드 " + strconv.Itoa(a.code)
			}
			if s := strings.TrimSpace(out); s != "" {
				msg = s + "\n" + msg
			}
			err = errString(msg)
		}
	}()
	fn()
	return mcpOut.String(), nil
}

type errString string

func (e errString) Error() string { return string(e) }

var mcpLock sync.Mutex

// ── 진입점 ──

func cmdMCP(args []string) {
	if len(args) == 0 || args[0] != "serve" {
		die("사용: gil mcp serve [--repo <경로>]\n" +
			"  gil 을 MCP 서버(stdio)로 연다 — 호스트(Claude Desktop 등)가 gil 명령을 툴로 직접 부르고,\n" +
			"  인터뷰는 호스트의 네이티브 폼(Elicitation)으로 사람에게 그 자리에서 묻는다.")
	}
	fs := newFlags("gil mcp serve")
	repo := fs.str("repo", "")
	fs.parse(args[1:])
	// 어느 저장소를 볼 것인가. 우선순위: --repo > 호스트가 알려준 프로젝트 루트 > 현재 위치.
	//
	// **--repo 를 설정에 박지 않는 게 기본이다.** 박으면 그 사람은 다른 작업을 할 때마다 MCP
	// 설정 파일을 고쳐야 하는데, 비개발자에겐 불가능한 요구다. Claude Code 는 서버를 띄울 때
	// CLAUDE_PROJECT_DIR 에 프로젝트 루트를 넣어주므로, 그걸 따라가면 **사람이 여는 폴더마다
	// gil 이 알아서 따라붙는다** — 등록은 한 번, 경로는 사람이 몰라도 된다.
	target := *repo
	if target == "" {
		target = os.Getenv("CLAUDE_PROJECT_DIR")
	}
	if target != "" {
		abs, err := filepath.Abs(target)
		if err != nil || os.Chdir(abs) != nil {
			die("거부: 저장소 경로로 이동 못 함: " + target)
		}
	}
	// --repo 가 호스트의 정답을 덮으면 **거부**한다(이슈 #51, 경고에서 승격).
	//
	// 왜 경고로는 부족한가. MCP 서버는 세션마다 새로 뜨고 그때 CLAUDE_PROJECT_DIR 을 물어
	// 해석한다 — 즉 --repo 만 없으면 이 구조는 **원래 이미 "열린 폴더를 따라가는"** 동작이다.
	// --repo 는 기본값을 바꾸는 옵션처럼 보이지만 실제로는 **호스트가 주는 정답을 무효화하는
	// 스위치**이고, ~/.claude.json 사용자 스코프에 한 번 박히면 이후 모든 프로젝트·모든
	// 세션에 영원히 적용된다. 사람이 그걸 박은 순간은 대개 gil 을 처음 시험하던 폴더 하나에서다.
	//
	// 그 결과가 실측으로 나왔다: 같은 폴더에서 CLI 는 체인 2개, MCP 는 체인 0개 — 사람과
	// 에이전트가 **서로 다른 그래프**를 봤고, 에이전트는 "기록이 거의 없다"며 새 체인을 열 뻔했다.
	// 이건 경고 한 줄로 감당할 위험이 아니다. 막고, 왜 막았는지와 다음 한 수를 준다(이슈 #47).
	if *repo != "" {
		if host := os.Getenv("CLAUDE_PROJECT_DIR"); host != "" {
			a, _ := filepath.Abs(*repo)
			b, _ := filepath.Abs(host)
			if a != b {
				mcpRepoMismatch = "거부: 설정의 --repo 가 지금 열린 폴더를 덮어쓰고 있다.\n" +
					"  --repo(설정에 박힌 곳): " + a + "\n" +
					"  지금 열린 폴더:        " + b + "\n" +
					"  이대로 두면 사람이 보는 폴더가 아닌 곳에 기록이 쌓인다 — 아무 에러도 없이.\n" +
					"  (실측: 같은 폴더에서 사람은 체인 2개를, 에이전트는 0개를 봤다.)\n\n" +
					"  고치는 법 — MCP 설정에서 \"--repo\" 인자만 빼라. 그러면 gil 이 열린 폴더를\n" +
					"  자동으로 따라간다(세션마다 새로 해석한다). 보통 ~/.claude.json 에 있고,\n" +
					"  gil 을 처음 시험하던 폴더가 그대로 박혀 있는 경우가 대부분이다:\n" +
					"    \"args\": [\"mcp\", \"serve\"]      ← 이렇게 (--repo 없이)\n" +
					"  고친 뒤 앱을 완전히 종료했다 다시 켜라.\n\n" +
					"  사람에게는 이렇게 말해라: \"설정에 예전 테스트 폴더가 박혀 있어서, 지금 보고\n" +
					"  계신 폴더가 아닌 곳에 기록이 쌓이게 돼 있어요. 설정 한 줄만 지우면 됩니다.\""
			}
		}
	}
	requireGit()
	mcpMode = true
	stopGitCache() // 한 프로세스가 여러 툴 호출을 처리한다 — 캐시는 두 번째 호출부터 거짓말이다

	s := mcp.NewServer(&mcp.Implementation{
		Name:    "gil",
		Title:   "gil — 사고 역사를 git 커밋 그래프 위에",
		Version: gilVersion,
	}, &mcp.ServerOptions{Capabilities: uiCapabilities()})
	registerGilTools(s)
	registerGilUI(s)
	if err := s.Run(context.Background(), &mcp.StdioTransport{}); err != nil {
		mcpMode = false
		die("gil mcp: 서버 종료: " + err.Error())
	}
}

// text — 툴 결과를 사람·LLM 이 읽는 텍스트로. gil 의 출력은 언제나 "다음에 무엇을 하라"는
// 프롬프트라, MCP 에서도 그대로 실어 보낸다.
func text(s string) *mcp.CallToolResult {
	if strings.TrimSpace(s) == "" {
		s = "(완료)"
	}
	return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: s}}}
}

// addFlag — 값이 비지 않았을 때만 플래그를 붙인다(CLI 인자 조립).
func addFlag(args []string, name, val string) []string {
	if strings.TrimSpace(val) == "" {
		return args
	}
	return append(args, "--"+name, val)
}

func addList(args []string, name string, vals []string) []string {
	for _, v := range vals {
		args = addFlag(args, name, v)
	}
	return args
}

// requireReady — 이 폴더가 gil 로 관리되고 있나. 아니면 **사람 언어로** 거부하고 다음 한 수를
// 준다. 이걸 안 하면 날 git 에러("git checkout 실패: exit status 128")가 그대로 올라가는데,
// 비개발자는 물론 에이전트도 거기서 다음 수를 못 찾는다(이슈 #47 의 최악 형태).
func requireReady() {
	// 저장소 해석이 어긋난 채로는 아무것도 하지 않는다(이슈 #51). 여기서 막지 않으면
	// 기록이 사람이 안 보는 폴더에 조용히 쌓인다.
	if mcpRepoMismatch != "" {
		die(mcpRepoMismatch)
	}
	if !gitOK("rev-parse", "--git-dir") {
		die("거부: 이 폴더는 아직 gil 로 관리되지 않는다(git 저장소가 아니다).\n" +
			"  먼저 gil_init 툴을 불러라 — 저장소를 만들고 존재·기억까지 한 번에 세운다.\n" +
			"  사람에게는 이렇게 말해라: \"이 폴더에서 작업 기록을 시작할게요.\"")
	}
	if !gitOK("rev-parse", "--verify", "-q", globalRef) {
		die("거부: 이 저장소엔 아직 gil 세계가 없다(존재·기억이 사는 refs/gil/global 부재).\n" +
			"  먼저 gil_init 툴을 불러라. 그 전에는 체인도 사이클도 열 수 없다.")
	}
}

// tool — cmd* 를 부르는 표준 핸들러를 만든다. 입력 구조체 → CLI 인자 조립은 호출부가 준다.
func tool[In any](s *mcp.Server, name, desc string, argv func(In) []string, run func([]string)) {
	mcp.AddTool(s, &mcp.Tool{Name: name, Description: desc},
		func(ctx context.Context, req *mcp.CallToolRequest, in In) (*mcp.CallToolResult, any, error) {
			out, err := runGil(func() { requireReady(); run(argv(in)) })
			if err != nil {
				return nil, nil, err
			}
			if name == "gil_log" || name == "gil_handoff" || name == "gil_fsck" {
				out = repoBanner() + out
			}
			return text(out), nil, nil
		})
}

// repoBanner — 지금 읽고 있는 저장소가 어디인지 한 줄(이슈 #51). 읽기 툴에만 붙인다 —
// 모든 응답에 붙이면 잡음이 되어 아무도 안 읽는다.
func repoBanner() string {
	wd, err := os.Getwd()
	if err != nil || wd == "" {
		return ""
	}
	return "📂 " + wd + "\n" +
		"  (이 폴더의 기록을 읽고 있다. 사람이 보고 있는 폴더와 다르면 그 자리에서 알려라.)\n\n"
}

// ── 툴 입력 구조체 ──
//
// 필드 설명(jsonschema 태그)은 LLM 이 읽는 유일한 사용법이다 — CLI 도움말과 같은 말을 한다.

type inChain struct {
	Name          string `json:"name" jsonschema:"체인 이름(소문자·숫자·하이픈)"`
	Purpose       string `json:"purpose" jsonschema:"이 체인이 무엇을 풀려는지 자연어로"`
	Inherit       string `json:"inherit,omitempty" jsonschema:"앞 체인에서 물려받은 전제·교훈"`
	Reference     string `json:"reference,omitempty" jsonschema:"사람이 준 기준 문서 파일 경로. criterion 과 짝이다 — 보통은 비워 두고 gil_intake 로 체인보다 먼저 사람에게 물어 그 답을 인용한다"`
	Criterion     string `json:"criterion,omitempty" jsonschema:"무엇이 관측되면 이 체인이 풀린 것인가 — 판정 문장. 기준 없이는 체인이 만들어지지 않는다(목적과 기준은 쌍)"`
	FromIntake    string `json:"from_intake,omitempty" jsonschema:"개시 인터뷰 슬러그 — 그 답에서 목적·기준을 인용한다(권장)"`
	PurposeFrom   string `json:"purpose_from,omitempty" jsonschema:"개시 인터뷰의 몇 번째 답을 목적으로 삼을지(누적 번호)"`
	CriterionFrom string `json:"criterion_from,omitempty" jsonschema:"개시 인터뷰의 몇 번째 답을 성패 기준으로 삼을지(누적 번호)"`
	// 이슈 #54: 열린 체인이 있는데 동시에 굴리는 트랙이면 선언해야 통과한다. 툴 표면에
	// 없으면 거부만 당하고 따를 수단이 없다 — 그건 레일이 아니라 벽이다(#57 과 같은 실패).
	ParallelWith []string `json:"parallel_with,omitempty" jsonschema:"열린 체인과 동시에 굴리는 트랙이면 그 체인 이름들. 선언 없이는 새 체인이 거부된다"`
}

type inOpen struct {
	Target  string   `json:"target" jsonschema:"chain/cycle"`
	Fits    string   `json:"fits,omitempty" jsonschema:"이 사이클이 체인 목적에 어떻게 기여하는가 — 필수. 여는 자리에서 체인 목적과 대면한다"`
	Misfit  string   `json:"misfit,omitempty" jsonschema:"이 체인의 것이 아니라고 판단했으면 그 이유. 열지 않고 기억에 남긴다"`
	Author  string   `json:"author" jsonschema:"이 사이클을 여는 존재의 이름"`
	Purpose string   `json:"purpose" jsonschema:"이 사이클이 풀려는 문제"`
	Inherit string   `json:"inherit,omitempty" jsonschema:"앞 사이클에서 물려받은 지식·전제·교훈"`
	Parent  []string `json:"parent,omitempty" jsonschema:"계보 부모 사이클들"`
	Refutes []string `json:"refutes,omitempty" jsonschema:"이 사이클이 뒤집는 앞 verify 스텝(chain/cycle/step)"`
	Refines []string `json:"refines,omitempty" jsonschema:"앞 verify·analyze 의 해석만 정밀화한다(판정은 그대로). chain/cycle/step"`
	Goal    string   `json:"goal,omitempty" jsonschema:"이 사이클이 무엇이 되면 끝인가(달성 판정 기준). 선언하면 닫을 때 goal_met 으로 답해야 한다"`
	// 이슈 #45: 미해결 사이클이 있으면 새 사이클 open 이 거부된다. 알면서 나란히 여는
	// 것이면 여기에 그 사이클 이름을 선언한다.
	Parallel []string `json:"parallel,omitempty" jsonschema:"미해결(fail 잎만·미종결) 사이클을 알면서 나란히 열 때 그 사이클 이름들"`
	Title    string   `json:"title,omitempty"`
	Body     string   `json:"body,omitempty"`
}

type inStep struct {
	Target      string   `json:"target" jsonschema:"chain/cycle"`
	Kind        string   `json:"kind" jsonschema:"define|hypothesis|experiment|verify|analyze|backtrack"`
	Title       string   `json:"title,omitempty"`
	Body        string   `json:"body,omitempty"`
	To          string   `json:"to,omitempty" jsonschema:"이 스텝이 이어붙는 앞 스텝(가지치기 지점)"`
	Outcome     string   `json:"outcome,omitempty" jsonschema:"success|fail 등 이 스텝의 결과"`
	Falsify     string   `json:"falsify,omitempty" jsonschema:"hypothesis 필수 — 무엇이 관측되면 이 가설은 거짓인가"`
	FalsifyTo   string   `json:"falsify_to,omitempty" jsonschema:"hypothesis 필수 — 반증되면 되돌아갈 조상 define"`
	IfSupported string   `json:"if_supported,omitempty" jsonschema:"goal-met|goal-missed — 이 가설이 맞으면 사이클 목표는 달성인가"`
	Verdict     string   `json:"verdict,omitempty" jsonschema:"verify 필수 — supported|refuted"`
	Refutes     []string `json:"refutes,omitempty"`
	Refines     []string `json:"refines,omitempty" jsonschema:"앞 verify·analyze 의 해석만 정밀화(판정 불변). chain/cycle/step"`
	At          string   `json:"at,omitempty" jsonschema:"종결(success|fail|pending)을 두고 온 잎 자리에 박는다 — HEAD 가 떠난 가지를 닫을 때"`
	Supersede   string   `json:"supersede,omitempty" jsonschema:"정정 — 앞선 같은 kind 스텝을 이 스텝이 대체한다(inherit 필수). 정정은 분기다: 대상의 부모 자리에서 새 브랜치로 갈라지고 옛 가지는 그대로 보존된다. 같은 kind 로만 되므로 판정 뒤집기는 불가(그건 backtrack/refutes)"`
	Merge       []string `json:"merge,omitempty"`
	// CLI 가 요구하는 필수 플래그는 MCP 스키마에도 있어야 한다(이슈 #86 제안 c). 없으면
	// 에이전트가 흐름 중간에 CLI 로 갈아타야 하고, 그 갈아탐 자체가 실수 표면적을 늘린다.
	Inherit    string   `json:"inherit,omitempty" jsonschema:"backtrack·머지·계보 간선 필수 — 앞 가지에서 물려받은 지식·전제·교훈"`
	Plan       string   `json:"plan,omitempty" jsonschema:"hypothesis 필수 — 가설을 세우기 전에 고정하는 설계('몇 개일지 추정'이 아니라 '몇 개로 만들지 결정')"`
	PlanHeld   bool     `json:"plan_held,omitempty" jsonschema:"verify — 고정한 설계가 그대로 유지됐다"`
	PlanBroke  string   `json:"plan_broke,omitempty" jsonschema:"verify — 설계가 깨졌다 + 무엇이 달랐나(되돌아갈 자리의 신호)"`
	Advances   string   `json:"advances,omitempty" jsonschema:"hypothesis 필수 — 이 가설이 체인 전체 목적에 어떻게·얼마나 다가서나"`
	Toward     string   `json:"toward,omitempty" jsonschema:"success·fail 필수 — 그래서 체인 목적에 얼마나 가까워졌나(회고)"`
	NextDesign string   `json:"next_design,omitempty" jsonschema:"success·fail 필수 — 목적을 이루기 위한 다음 설계(다음 세대가 물려받는다)"`
	LeaveOpen  bool     `json:"leave_open,omitempty" jsonschema:"미종결 잎을 두고 떠난다는 명시적 선언(매달린 잎이 남고 fsck 가 짚는다)"`
	Dataset    []string `json:"dataset,omitempty" jsonschema:"이 측정이 어디서 섰나 — 평가셋과 sha256"`
	Subject    []string `json:"subject,omitempty" jsonschema:"이 측정이 무엇을 쟀나 — 모델·체크포인트·옵션"`
}

type inTarget struct {
	Target  string `json:"target" jsonschema:"chain/cycle"`
	Verdict string `json:"verdict,omitempty" jsonschema:"닫는 판정(기본 supported)"`
	Abandon bool   `json:"abandon,omitempty" jsonschema:"이 사이클을 성과 없이 접는다"`
	GoalMet bool   `json:"goal_met,omitempty" jsonschema:"열 때 선언한 목표에 닿았다 — goal 을 선언한 사이클은 이게 없으면 안 닫힌다"`
}

type inChainName struct {
	Name    string `json:"name" jsonschema:"체인 이름"`
	Verdict string `json:"verdict,omitempty"`
	Retro   string `json:"retro,omitempty" jsonschema:"회고 파일 경로 — 기준 대비 달성도. 기준(인터뷰)이 있는 체인은 필수"`
	Seed    string `json:"seed,omitempty" jsonschema:"다음 체인 인터뷰의 재료가 될 시드 파일 경로"`
}

type inApprove struct {
	Target string `json:"target" jsonschema:"chain/cycle"`
	Title  string `json:"title,omitempty"`
	Body   string `json:"body,omitempty"`
}

type inReject struct {
	Target string `json:"target" jsonschema:"chain/cycle"`
	To     string `json:"to" jsonschema:"되돌아갈 조상 define 스텝"`
	Title  string `json:"title,omitempty"`
	Body   string `json:"body,omitempty"`
}

type inLog struct {
	Chain string `json:"chain,omitempty" jsonschema:"범위를 좁힐 체인(생략=전체)"`
	Depth string `json:"depth,omitempty" jsonschema:"chain|cycle|step (기본 step)"`
	All   bool   `json:"all,omitempty" jsonschema:"죽은 잎·형제 가지까지 — 벽의 지도"`
}

type inGoto struct {
	Ref string `json:"ref" jsonschema:"<chain>/<cycle> (그 사이클의 산 잎으로) 또는 <chain>/<cycle>/<step> (그 자리로)"`
}

type inEmpty struct{}

type inDeploy struct {
	At    string `json:"at" jsonschema:"chain/cycle/step — 무엇을 배포했나"`
	Tag   string `json:"tag" jsonschema:"릴리스 태그(v0.2.0)"`
	URL   string `json:"url,omitempty"`
	Title string `json:"title,omitempty"`
	State string `json:"state,omitempty" jsonschema:"staged|live(기본). staged = 배포 단위는 확정됐으나 아직 안 올라갔다"`
	// 이슈 #56: staged 로 찍어둔 것이 실제로 올라갔음을 잇는다(앞 마커는 그대로 남는다).
	Promote bool `json:"promote,omitempty" jsonschema:"staged 였던 배포가 실제로 올라갔다"`
}

func registerGilTools(s *mcp.Server) {
	tool(s, "gil_chain", "새 체인을 연다. 닫힌 체인 끝에서만 열 수 있다. 체인을 연 뒤에는 gil_interview 로 사람에게 기준을 물어야 사이클을 열 수 있다.",
		func(in inChain) []string {
			a := []string{in.Name}
			a = addFlag(a, "purpose", in.Purpose)
			a = addFlag(a, "inherit", in.Inherit)
			a = addList(a, "parallel-with", in.ParallelWith)
			a = addFlag(a, "criterion", in.Criterion)
			a = addFlag(a, "from-intake", in.FromIntake)
			a = addFlag(a, "purpose-from", in.PurposeFrom)
			a = addFlag(a, "criterion-from", in.CriterionFrom)
			return addFlag(a, "reference", in.Reference)
		}, cmdChain)

	tool(s, "gil_open", "체인 안에 새 사이클을 연다. 기준 문서(인터뷰)가 확정된 체인에서만 열린다.",
		func(in inOpen) []string {
			a := []string{in.Target}
			a = addFlag(a, "author", in.Author)
			a = addFlag(a, "purpose", in.Purpose)
			a = addFlag(a, "fits", in.Fits)
			a = addFlag(a, "misfit", in.Misfit)
			a = addFlag(a, "inherit", in.Inherit)
			a = addList(a, "parent", in.Parent)
			a = addList(a, "refutes", in.Refutes)
			a = addList(a, "refines", in.Refines)
			a = addList(a, "parallel", in.Parallel)
			a = addFlag(a, "goal", in.Goal)
			a = addFlag(a, "title", in.Title)
			return addFlag(a, "body", in.Body)
		}, cmdOpen)

	tool(s, "gil_step", "사이클에 스텝을 남긴다(define/hypothesis/verify/analyze/success/fail/pending). 필수: hypothesis=falsify·falsify_to·plan·advances, verify=verdict(+고정한 설계가 있으면 plan_held|plan_broke), success·fail=toward·next_design, backtrack=inherit.",
		func(in inStep) []string {
			a := []string{in.Target}
			a = addFlag(a, "kind", in.Kind)
			a = addFlag(a, "title", in.Title)
			a = addFlag(a, "body", in.Body)
			a = addFlag(a, "to", in.To)
			a = addFlag(a, "outcome", in.Outcome)
			a = addFlag(a, "falsify", in.Falsify)
			a = addFlag(a, "falsify-to", in.FalsifyTo)
			a = addFlag(a, "if-supported", in.IfSupported)
			a = addFlag(a, "verdict", in.Verdict)
			a = addList(a, "refutes", in.Refutes)
			a = addList(a, "refines", in.Refines)
			a = addFlag(a, "supersede", in.Supersede)
			a = addFlag(a, "at", in.At)
			a = addFlag(a, "inherit", in.Inherit)
			a = addFlag(a, "plan", in.Plan)
			a = addFlag(a, "plan-broke", in.PlanBroke)
			a = addFlag(a, "advances", in.Advances)
			a = addFlag(a, "toward", in.Toward)
			a = addFlag(a, "next-design", in.NextDesign)
			if in.PlanHeld {
				a = append(a, "--plan-held")
			}
			if in.LeaveOpen {
				a = append(a, "--leave-open")
			}
			a = addList(a, "dataset", in.Dataset)
			a = addList(a, "subject", in.Subject)
			return addList(a, "merge", in.Merge)
		}, cmdStep)

	tool(s, "gil_close", "사이클을 닫는다. 모든 잎이 종결돼야 닫힌다.",
		func(in inTarget) []string {
			a := addFlag([]string{in.Target}, "verdict", in.Verdict)
			if in.Abandon {
				a = append(a, "--abandon")
			}
			if in.GoalMet {
				a = append(a, "--goal-met")
			}
			return a
		}, cmdClose)

	tool(s, "gil_chain_close", "체인을 완결로 봉인한다. 모든 사이클이 닫혀야 하고, 사람이 세운 기준(인터뷰)이 있는 체인은 그 기준 대비 회고(retro)가 필수다.",
		func(in inChainName) []string {
			a := addFlag([]string{in.Name}, "verdict", in.Verdict)
			a = addFlag(a, "retro", in.Retro)
			return addFlag(a, "seed", in.Seed)
		}, cmdChainClose)

	tool(s, "gil_approve", "approval 체인에서 pending 사이클을 승인한다(사람의 판단).",
		func(in inApprove) []string {
			a := addFlag([]string{in.Target}, "title", in.Title)
			return addFlag(a, "body", in.Body)
		}, cmdApprove)

	tool(s, "gil_reject", "pending 사이클을 기각하고 조상 define 으로 되돌린다.",
		func(in inReject) []string {
			a := addFlag([]string{in.Target}, "to", in.To)
			a = addFlag(a, "title", in.Title)
			return addFlag(a, "body", in.Body)
		}, cmdReject)

	// 읽기 툴은 **대상 경로를 늘 앞에 찍는다**(이슈 #51 제안 4). 경고는 어긋났을 때만 뜨지만,
	// 진짜 위험한 건 "어긋났는데도 아무 이상 없이 잘 도는" 경우다 — gil 의 대상은 폴더가
	// 아니라 폴더 **안의** refs/gil/* 라, 엉뚱한 폴더에서도 빈 그래프를 새로 만들며 정상처럼
	// 보인다(git 이라면 "not a git repository" 로 즉시 멎을 상황). 그건 경고로는 못 잡고
	// 상시 표시로만 잡힌다. 세션마다 새로 해석되는 값이니 세션마다 한 번은 눈에 보여야 한다.
	tool(s, "gil_log", "사고 그래프를 읽는다. 분기·죽은 잎이 한눈에 보인다. 응답 첫 줄에 지금 읽고 있는 저장소 경로가 찍힌다.",
		func(in inLog) []string {
			var a []string
			if in.Chain != "" {
				a = append(a, in.Chain)
			}
			a = addFlag(a, "depth", in.Depth)
			if in.All {
				a = append(a, "--all")
			}
			return a
		}, cmdLog)

	// 갇힘의 탈출로(이슈 #67). 죽은 가지 끝에 서면 --to/--falsify-to 가 산 가지의 스텝을
	// "조상이 아니다"로 거부한다 — 그때 가지를 옮기는 유일한 gil 문법이다. 그래프는 안 바뀐다.
	tool(s, "gil_goto", "사고 나무 안에서 자리를 옮긴다 — 그 사이클의 산 잎으로, 또는 지정한 스텝 자리로. "+
		"그래프는 바뀌지 않는다(커밋·브랜치 없음). 죽은 가지에 갇혔을 때의 탈출로다.",
		func(in inGoto) []string {
			if in.Ref == "" {
				return nil
			}
			return []string{in.Ref}
		}, cmdGoto)

	tool(s, "gil_fsck", "그래프 무결성을 검사한다 — 미종결 잎, 어긋난 계보를 잡는다.",
		func(in inEmpty) []string { return nil }, cmdFsck)

	// 세션을 이어받는 첫 관문. 관전 뷰어를 자동으로 띄우고 "인앱 브라우저로 열어라"를 규범으로
	// 지시한다(이슈 #55) — cmdHandoff 안에서 처리하므로 CLI 와 MCP 가 같은 레일을 쓴다.
	tool(s, "gil_handoff", "다음 세션에 넘길 상태를 보고한다. **세션을 이어받을 때 가장 먼저 부른다.** "+
		"관전 뷰어를 자동으로 띄우고 그 주소를 준다 — 받은 주소는 네 인앱 브라우저 패널로 곧바로 열어라.",
		func(in inEmpty) []string { return nil }, cmdHandoff)

	tool(s, "gil_deploy", "배포(공개) 지점을 그래프의 1급 시민으로 남긴다.",
		func(in inDeploy) []string {
			a := addFlag(nil, "at", in.At)
			a = addFlag(a, "tag", in.Tag)
			a = addFlag(a, "url", in.URL)
			a = addFlag(a, "state", in.State)
			if in.Promote {
				a = append(a, "--promote")
			}
			return addFlag(a, "title", in.Title)
		}, cmdDeploy)

	// gil_init 은 requireReady 게이트 밖에 산다 — 이게 바로 그 준비를 하는 툴이다.
	// 세팅을 터미널로 내몰면 "프롬프트만으로 완주"가 깨진다(비개발자는 터미널을 안 쓴다).
	mcp.AddTool(s, &mcp.Tool{
		Name: "gil_init",
		Description: "이 폴더에 gil 세계를 세운다(저장소·대문·존재·기억). 다른 gil 툴이 " +
			"'아직 gil 로 관리되지 않는다'고 거부하면 이걸 먼저 부른다. 이미 세워져 있으면 거부한다.",
	}, func(ctx context.Context, req *mcp.CallToolRequest, in inInit) (*mcp.CallToolResult, any, error) {
		// 관전 서버의 시스템 브라우저 자동 실행은 끈다 — 호스트 안에서 도는 에이전트에게는
		// 밖으로 튀어나오는 창이 방해다(이슈 #48). 주소는 출력에 그대로 나온다.
		a := []string{"--no-open"}
		out, err := runGil(func() { cmdInit(addFlag(a, "name", in.Name)) })
		if err != nil {
			return nil, nil, err
		}
		return text(out), nil, nil
	})

	registerInterviewTool(s)

	// 사람 제출을 에이전트가 확인할 수단(이슈 #58). MCP 툴은 스스로 깨어나지 못하니 블로킹 대기
	// 대신 "물어보면 정직하게 답하는 한 줄"을 준다 — 사람이 "제출했어"라고 말할 때 부르면 된다.
	tool(s, "gil_interview_status",
		"인터뷰가 사람 답을 받았는지 확인한다(pending|done). 뷰어 폼으로 넘어간 인터뷰는 사람이 "+
			"제출해도 자동 통지가 없다 — 사람이 제출했다고 하면 이걸로 확인하고, 확인 전에는 기준을 "+
			"대신 쓰지 마라.",
		func(in inInterviewStatus) []string { return []string{in.Chain, "--status"} },
		cmdInterview)

	// **MCP 에서는 셸 백그라운드 문제가 없다**(이슈 #94). 툴 호출은 호스트가 스스로 추적하므로,
	// 블로킹 대기를 툴로 노출하면 "제출 → 이 호출이 끝남 → 호스트가 그 결과로 턴을 이어감" 이
	// 한 홉으로 성립한다. 셸에서 `&` 로 떼어낸 프로세스가 추적 밖이라 완료가 턴을 못 열던
	// 바로 그 구멍을, 이 경로는 애초에 갖지 않는다.
	tool(s, "gil_interview_wait",
		"사람이 인터뷰 폼에 답할 때까지 **기다린다**(블로킹). 답이 오면 확정된 기준 문서를 그대로 "+
			"돌려준다. 셸 백그라운드(`&`)와 달리 이 호출의 완료는 호스트가 추적하므로, 제출이 "+
			"곧바로 다음 행동으로 이어진다. 기준을 대신 쓰지 말고 이걸로 기다려라.",
		func(in inInterviewWait) []string {
			a := []string{in.Chain, "--wait"}
			if strings.TrimSpace(in.Timeout) != "" {
				a = append(a, "--timeout", in.Timeout)
			}
			return a
		},
		cmdInterview)
}

type inInterviewWait struct {
	Chain   string `json:"chain" jsonschema:"기다릴 체인 이름(또는 개시 인터뷰 슬러그)"`
	Timeout string `json:"timeout,omitempty" jsonschema:"최대 대기 초(기본 600). 대화형이면 넉넉히"`
}

type inInterviewStatus struct {
	Chain string `json:"chain" jsonschema:"확인할 체인 이름"`
}

type inInit struct {
	Name string `json:"name,omitempty" jsonschema:"이 저장소에서 깨어날 존재의 이름. 생략하면 이름 없이 심고, 이름 짓는 것이 그 존재의 첫 과제가 된다"`
}

// ── 단계 B: 인터뷰 = Elicitation ──
//
// 기존 인터뷰는 "질문을 커밋으로 심고(pending) → 사람이 뷰어 폼에서 답하고 → 뷰어 서버가
// interview --resolve 를 부른다"는 3홉이었다. MCP 에서는 한 홉이다: 툴 호출 안에서 호스트에
// 폼을 띄우고(Elicit), 사람 답을 그 자리에서 받아 레퍼런스를 확정한다. 대기가 하나뿐이라
// "LLM 은 pending 을 모르고 또 질문지를 만든다"는 실패가 구조적으로 불가능하다.
//
// 폴백: 호스트가 Elicitation 을 지원하지 않으면(또는 사람이 폼을 취소하면) 옛 경로로 돌아가
// 질문을 pending 으로 심는다 — 뷰어 폼에서 답할 수 있게. 어느 쪽이든 사람의 답이 기준이 된다.

type inInterview struct {
	Chain     string          `json:"chain" jsonschema:"기준 문서를 만들 체인 이름"`
	Title     string          `json:"title,omitempty"`
	Questions []interviewQMCP `json:"questions" jsonschema:"사람에게 물을 질문들. 스스로 답을 지어내지 말고 반드시 물어라"`
}

type interviewQMCP struct {
	Q       string   `json:"q" jsonschema:"질문 텍스트"`
	Type    string   `json:"type" jsonschema:"text|radio|checkbox"`
	Options []string `json:"options,omitempty" jsonschema:"radio·checkbox 의 선택지"`
}

func registerInterviewTool(s *mcp.Server) {
	mcp.AddTool(s, &mcp.Tool{
		Name: "gil_interview",
		Description: "체인의 기준 문서(레퍼런스 트루스)를 사람에게 물어 만든다. 체인을 연 직후 반드시 한 번 " +
			"불러야 하며, 이걸 통과해야 사이클을 열 수 있다. 사람의 답이 기준이다 — 답을 대신 지어내지 마라.",
	}, func(ctx context.Context, req *mcp.CallToolRequest, in inInterview) (*mcp.CallToolResult, any, error) {
		qs := make([]interviewQ, 0, len(in.Questions))
		for _, q := range in.Questions {
			qs = append(qs, interviewQ{Q: q.Q, Type: q.Type, Options: q.Options})
		}
		askJSON, _ := json.Marshal(qs)

		// 1) 호스트에 네이티브 폼을 띄운다. 여기서 실패하면 옛 뷰어 경로로 폴백.
		res, err := req.Session.Elicit(ctx, &mcp.ElicitParams{
			Mode: "form",
			Message: "체인 [" + in.Chain + "] 의 기준 문서를 만들기 위한 인터뷰다. " +
				"여기 답한 내용이 이후 모든 사이클의 성패를 재는 자로 쓰인다.",
			RequestedSchema: json.RawMessage(elicitSchema(qs)),
		})
		if err != nil {
			return interviewFallback(in.Chain, in.Title, askJSON,
				"이 호스트는 네이티브 폼을 렌더하지 못한다("+err.Error()+")")
		}
		if res.Action != "accept" {
			// 이슈 #57(상현님 실사용): 여기서 "사람이 decline 했다"고 단언했었다. 그런데 폼이 사람
			// 화면에 뜬 적조차 없었다 — 호스트가 렌더하지 못하고 즉시 decline 으로 돌려준 것이다.
			// 우리는 이 자리에서 둘(사람이 거절함 / 호스트가 못 띄움)을 구분할 수 없다. 구분 못 하는
			// 것을 단언하면 에이전트에게 없던 사람 의사를 심고, 그게 "사람이 원치 않으니 내가 기준을
			// 쓰자"는 우회 압력이 된다. 그래서 단언하지 않고 뷰어 폼 경로로 넘긴 뒤, 사람에게 직접
			// 확인하라고 말한다 — 어느 쪽이든 사람의 답이 기준이라는 성질은 지켜진다.
			return interviewFallback(in.Chain, in.Title, askJSON,
				"호스트가 폼을 \""+res.Action+"\" 로 돌려줬다 — 사람이 취소한 것인지, 호스트가 폼을 "+
					"띄우지 못한 것인지 여기서는 구분할 수 없다")
		}

		// 2) 답을 기준 문서(markdown)로 조립해 레퍼런스로 확정한다.
		ref := mcpAssembleReference(in.Chain, qs, res.Content)
		tmp, terr := writeTemp("gil-reference-*.md", ref)
		if terr != nil {
			return nil, nil, terr
		}
		defer os.Remove(tmp)
		out, rerr := runGil(func() { interviewResolve(in.Chain, tmp) })
		if rerr != nil {
			return nil, nil, rerr
		}
		return text(out + "\n\n── 확정된 기준 문서 ──\n" + ref), nil, nil
	})
}

// interviewFallback — 네이티브 폼이 성립하지 않았을 때 옛 경로(질문을 pending 으로 심고 뷰어
// 폼에서 사람이 답한다)로 넘긴다. why 에는 "왜 폼 경로가 아닌가"를 사실 그대로 적는다 —
// 사람의 의사를 추측해 적지 않는다(이슈 #57).
func interviewFallback(chain, title string, askJSON []byte, why string) (*mcp.CallToolResult, any, error) {
	// --ask 는 파일 경로(또는 -)를 받는다 — 질문 JSON 을 임시 파일로 건넨다.
	qf, qerr := writeTemp("gil-interview-*.json", string(askJSON))
	if qerr != nil {
		return nil, nil, qerr
	}
	defer os.Remove(qf)
	out, ferr := runGil(func() { cmdInterview(append([]string{chain}, askArgs(qf, title)...)) })
	if ferr != nil {
		return nil, nil, ferr
	}
	return text(out + "\n(" + why + " — 질문을 뷰어 폼으로 심었다. 사람은 아직 답하지 않았다.)\n" +
		"▸ 다음 한 수: 사람에게 뷰어 폼(📋 인터뷰)에 답해 달라고 지금 말로 청하라. 답을 대신 지어내지 마라.\n" +
		"▸ 제출됐는지는 gil_interview_status 로 확인한다(pending|done). 사람이 \"제출했어\"라고 하면 그때 부르면 된다."), nil, nil
}

func askArgs(askJSON, title string) []string {
	a := addFlag(nil, "ask", askJSON)
	return addFlag(a, "title", title)
}

// elicitSchema — 질문 목록을 Elicitation 스키마(평면 프로퍼티만 허용)로 바꾼다.
// text→string, radio→enum, checkbox→선택지마다 boolean 하나(배열·중첩이 금지라서).
func elicitSchema(qs []interviewQ) []byte {
	props := map[string]any{}
	var required []string
	for i, q := range qs {
		base := "q" + strconv.Itoa(i+1)
		switch q.Type {
		case "radio":
			props[base] = map[string]any{"type": "string", "title": q.Q, "enum": q.Options}
			required = append(required, base)
		case "checkbox":
			for j, o := range q.Options {
				key := base + "_o" + strconv.Itoa(j+1)
				props[key] = map[string]any{"type": "boolean", "title": q.Q + " — " + o}
			}
		default:
			props[base] = map[string]any{"type": "string", "title": q.Q}
			required = append(required, base)
		}
	}
	b, _ := json.Marshal(map[string]any{
		"type": "object", "properties": props, "required": required,
	})
	return b
}

// assembleReference — 사람의 답을 그대로 기준 문서로 옮긴다. LLM 의 요약·윤색을 끼우지 않는다
// (윤색이 들어가는 순간 "사람의 답이 기준"이라는 성질이 깨진다).
func mcpAssembleReference(chain string, qs []interviewQ, ans map[string]any) string {
	var b strings.Builder
	b.WriteString("# 기준 문서 — " + chain + "\n\n")
	b.WriteString("사람과의 인터뷰(호스트 네이티브 폼)로 확정했다. 이후 사이클의 성패는 이 기준에 비추어 판정한다.\n\n")
	for i, q := range qs {
		base := "q" + strconv.Itoa(i+1)
		b.WriteString("## " + strconv.Itoa(i+1) + ". " + q.Q + "\n\n")
		switch q.Type {
		case "checkbox":
			var picked []string
			for j, o := range q.Options {
				if v, ok := ans[base+"_o"+strconv.Itoa(j+1)].(bool); ok && v {
					picked = append(picked, o)
				}
			}
			if len(picked) == 0 {
				b.WriteString("(선택 없음)\n\n")
			} else {
				for _, p := range picked {
					b.WriteString("- " + p + "\n")
				}
				b.WriteString("\n")
			}
		default:
			s, _ := ans[base].(string)
			if strings.TrimSpace(s) == "" {
				s = "(답 없음)"
			}
			b.WriteString(s + "\n\n")
		}
	}
	return b.String()
}

func writeTemp(pattern, content string) (string, error) {
	f, err := os.CreateTemp("", pattern)
	if err != nil {
		return "", err
	}
	defer f.Close()
	if _, err := f.WriteString(content); err != nil {
		return "", err
	}
	return f.Name(), nil
}
