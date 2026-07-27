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
	if *repo != "" {
		abs, err := filepath.Abs(*repo)
		if err != nil || os.Chdir(abs) != nil {
			die("거부: --repo 경로로 이동 못 함: " + *repo)
		}
	}
	requireGit()
	mcpMode = true

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

// tool — cmd* 를 부르는 표준 핸들러를 만든다. 입력 구조체 → CLI 인자 조립은 호출부가 준다.
func tool[In any](s *mcp.Server, name, desc string, argv func(In) []string, run func([]string)) {
	mcp.AddTool(s, &mcp.Tool{Name: name, Description: desc},
		func(ctx context.Context, req *mcp.CallToolRequest, in In) (*mcp.CallToolResult, any, error) {
			out, err := runGil(func() { run(argv(in)) })
			if err != nil {
				return nil, nil, err
			}
			return text(out), nil, nil
		})
}

// ── 툴 입력 구조체 ──
//
// 필드 설명(jsonschema 태그)은 LLM 이 읽는 유일한 사용법이다 — CLI 도움말과 같은 말을 한다.

type inChain struct {
	Name      string `json:"name" jsonschema:"체인 이름(소문자·숫자·하이픈)"`
	Purpose   string `json:"purpose" jsonschema:"이 체인이 무엇을 풀려는지 자연어로"`
	Inherit   string `json:"inherit,omitempty" jsonschema:"앞 체인에서 물려받은 전제·교훈"`
	Reference string `json:"reference,omitempty" jsonschema:"기준 문서 파일 경로. 보통 비워 두고 gil_interview 로 사람에게 물어 만든다"`
}

type inOpen struct {
	Target  string   `json:"target" jsonschema:"chain/cycle"`
	Author  string   `json:"author" jsonschema:"이 사이클을 여는 존재의 이름"`
	Purpose string   `json:"purpose" jsonschema:"이 사이클이 풀려는 문제"`
	Inherit string   `json:"inherit,omitempty" jsonschema:"앞 사이클에서 물려받은 지식·전제·교훈"`
	Parent  []string `json:"parent,omitempty" jsonschema:"계보 부모 사이클들"`
	Refutes []string `json:"refutes,omitempty" jsonschema:"이 사이클이 뒤집는 앞 verify 스텝(chain/cycle/step)"`
	Title   string   `json:"title,omitempty"`
	Body    string   `json:"body,omitempty"`
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
	Merge       []string `json:"merge,omitempty"`
}

type inTarget struct {
	Target  string `json:"target" jsonschema:"chain/cycle"`
	Verdict string `json:"verdict,omitempty" jsonschema:"닫는 판정(기본 supported)"`
	Abandon bool   `json:"abandon,omitempty" jsonschema:"이 사이클을 성과 없이 접는다"`
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

type inEmpty struct{}

type inDeploy struct {
	At    string `json:"at" jsonschema:"chain/cycle/step — 무엇을 배포했나"`
	Tag   string `json:"tag" jsonschema:"릴리스 태그(v0.2.0)"`
	URL   string `json:"url,omitempty"`
	Title string `json:"title,omitempty"`
}

func registerGilTools(s *mcp.Server) {
	tool(s, "gil_chain", "새 체인을 연다. 닫힌 체인 끝에서만 열 수 있다. 체인을 연 뒤에는 gil_interview 로 사람에게 기준을 물어야 사이클을 열 수 있다.",
		func(in inChain) []string {
			a := []string{in.Name}
			a = addFlag(a, "purpose", in.Purpose)
			a = addFlag(a, "inherit", in.Inherit)
			return addFlag(a, "reference", in.Reference)
		}, cmdChain)

	tool(s, "gil_open", "체인 안에 새 사이클을 연다. 기준 문서(인터뷰)가 확정된 체인에서만 열린다.",
		func(in inOpen) []string {
			a := []string{in.Target}
			a = addFlag(a, "author", in.Author)
			a = addFlag(a, "purpose", in.Purpose)
			a = addFlag(a, "inherit", in.Inherit)
			a = addList(a, "parent", in.Parent)
			a = addList(a, "refutes", in.Refutes)
			a = addFlag(a, "title", in.Title)
			return addFlag(a, "body", in.Body)
		}, cmdOpen)

	tool(s, "gil_step", "사이클에 스텝을 남긴다(define/hypothesis/experiment/verify/analyze/backtrack). hypothesis 는 falsify·falsify_to 가, verify 는 verdict 가 필수다.",
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
			return addList(a, "merge", in.Merge)
		}, cmdStep)

	tool(s, "gil_close", "사이클을 닫는다. 모든 잎이 종결돼야 닫힌다.",
		func(in inTarget) []string {
			a := addFlag([]string{in.Target}, "verdict", in.Verdict)
			if in.Abandon {
				a = append(a, "--abandon")
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

	tool(s, "gil_log", "사고 그래프를 읽는다. 분기·죽은 잎이 한눈에 보인다.",
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

	tool(s, "gil_fsck", "그래프 무결성을 검사한다 — 미종결 잎, 어긋난 계보를 잡는다.",
		func(in inEmpty) []string { return nil }, cmdFsck)

	tool(s, "gil_handoff", "다음 세션에 넘길 상태를 보고한다. 세션을 이어받을 때 가장 먼저 부른다.",
		func(in inEmpty) []string { return nil }, cmdHandoff)

	tool(s, "gil_deploy", "배포(공개) 지점을 그래프의 1급 시민으로 남긴다.",
		func(in inDeploy) []string {
			a := addFlag(nil, "at", in.At)
			a = addFlag(a, "tag", in.Tag)
			a = addFlag(a, "url", in.URL)
			return addFlag(a, "title", in.Title)
		}, cmdDeploy)

	registerInterviewTool(s)
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
			// --ask 는 파일 경로(또는 -)를 받는다 — 질문 JSON 을 임시 파일로 건넨다.
			qf, qerr := writeTemp("gil-interview-*.json", string(askJSON))
			if qerr != nil {
				return nil, nil, qerr
			}
			defer os.Remove(qf)
			out, ferr := runGil(func() { cmdInterview(append([]string{in.Chain}, askArgs(qf, in.Title)...)) })
			if ferr != nil {
				return nil, nil, ferr
			}
			return text(out + "\n(호스트가 네이티브 폼을 지원하지 않아 뷰어 폼으로 넘겼다: " + err.Error() + ")"), nil, nil
		}
		if res.Action != "accept" {
			// 취소·거절도 사람의 선택이다. 답을 지어내지 말고 그대로 멈춘다.
			return nil, nil, errString("인터뷰가 사람에 의해 " + res.Action + " 되었다 — 기준 문서는 만들어지지 않았다. " +
				"답을 대신 지어내지 말고, 무엇을 물어야 할지 사람과 대화로 정한 뒤 다시 물어라.")
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
