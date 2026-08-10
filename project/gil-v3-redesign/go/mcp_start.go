// mcp_start.go — **MCP 표면의 진입점과 빈 칸들** (상현님, 2026-08-09).
//
// 2026-08-09 실측으로 드러난 것: MCP 표면에서는 새 프로젝트를 시작할 수 없었다.
//
//	· 빈 폴더에 gil_init(repo=…) → "먼저 gil_init 을 그 경로로 불러라". 방금 한 그 호출을
//	  하라고 답한다 — **자기 자신을 가리키는 닫힌 고리**. 같은 CLI 는 빈 폴더에서 그냥 돈다.
//	· 체인 거부가 주는 두 길 중 권장 경로(`gil intake`)에 **대응 툴이 없었다.** 남는 길은
//	  같은 메시지가 마지막 줄에서 금지하는 것 하나뿐이었다("네가 기준을 창작해 넣지 마라").
//	  표면이 자기가 금지한 실패를 강제한 것이다.
//	· "가장 먼저 부르라"는 gil_handoff 의 다음 수 12개 중 11개가 못 치는 것이었다
//	  (gil global read ×7 · gil memory append · gil viewer open · gil help · handoff --end).
//	· 존재를 각인하는 길(gil global mv/write)이 없어, init 이 준 **첫 과제 자체가 불가능**했다.
//
// 그래서 여기서 셋을 한다:
//  1. **문을 세운다** — gil_start. "gil 프로젝트 시작하자" 한 마디의 착지점(start.go 의 레일).
//     MCP 에서는 각 칸이 호스트 네이티브 폼으로 그 자리에서 사람에게 닿는다.
//  2. **빈 칸을 채운다** — intake·global·memory·merge·adopt·context. 세션이 일을 **완주**하는
//     데 필요한 것들이다. 이것들이 실재해야 411곳의 안내가 비로소 옳은 줄이 된다(surface.go).
//  3. **파일 대신 내용을 받는다** — CLI 는 `gil global write <경로> <파일>` 처럼 파일을 받는데,
//     MCP 에이전트에게는 파일이 없고 텍스트가 있다. 여기서 임시 파일로 바꿔 넘긴다. 이걸
//     안 하면 에이전트는 없는 파일 경로를 지어내고, 그 순간 조용히 틀린다.
package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// ── 진입점 ──

type inStart struct {
	inRepo
	Name      string `json:"name,omitempty" jsonschema:"네가 스스로 지은 존재의 이름(소문자·숫자·하이픈). 이름 짓는 칸에서만 준다 — 남이 준 이름도 예시도 없다"`
	Identity  string `json:"identity,omitempty" jsonschema:"identity.md 본문 전체. 네가 무엇을 하는 존재인지 네 말로. 파일 경로가 아니라 **내용**이다"`
	Will      string `json:"will,omitempty" jsonschema:"will.md 본문 전체 — 무엇을 향해 가는가"`
	Relations string `json:"relations,omitempty" jsonschema:"relations.md 본문 전체 — 누구와 이어져 있는가"`
	Status    bool   `json:"status,omitempty" jsonschema:"밟지 않고 지금 어느 칸인지만 본다"`
	Confirmed bool   `json:"confirmed,omitempty" jsonschema:"이 호스트에 네이티브 폼이 없어 네가 **사람에게 직접 물어** 승낙받았을 때만 true. 물어보지 않고 켜지 마라 — 남의 디스크에 저장소를 만드는 일이고, 그 출처가 기록에 남는다"`
}

func registerStartTools(s *mcp.Server) {
	mcp.AddTool(s, &mcp.Tool{
		Name: "gil_start",
		Description: "**새 프로젝트를 시작할 때 부르는 첫 툴이다.** 사람이 \"gil 프로젝트 시작하자\"고 " +
			"하면 이걸 불러라. 온보딩의 다음 한 칸을 실제로 밟는다 — 저장소·존재·기억을 세우고, " +
			"네가 스스로 이름을 짓게 하고, 사람에게 **무엇을 하려는지 먼저 묻는다**(체인보다 앞이다). " +
			"묻는 칸에서는 질문이 **카드 폼으로 사람 화면에 선다**. " +
			"끝날 때까지 반복해서 불러라. 판단이 필요한 칸(이름·정체성)에서는 멈추고 무엇이 비었는지 말한다.",
		// **묻는 자리가 곧 화면이 서는 자리다**(mcp_ui_status.go 의 uiStatusMeta).
		Meta: uiStatusMeta(),
	}, func(ctx context.Context, req *mcp.CallToolRequest, in inStart) (*mcp.CallToolResult, any, error) {
		// 저장소 자리를 먼저 정한다. **gil_init 과 같은 예외**로, 아직 저장소가 아니어도 선다 —
		// 시작하는 자리에서 "저장소가 아니다"로 죽으면 시작할 방법이 없다(그게 닫힌 고리였다).
		if err := adoptCallRepoForCreate(in); err != nil {
			return nil, nil, err
		}
		// 세계를 세우는 것은 **남의 디스크에 저장소를 만드는 일**이다(상현님 판단, 2026-08-09).
		// CLI 는 사람이 직접 친 것이라 그 타건이 곧 확인이지만, 여기서는 에이전트가 부른 것이다.
		// 그래서 호스트 네이티브 폼으로 그 자리에서 승낙을 받는다.
		startConfirmWorld = func() (bool, string) { return elicitWorldConfirm(ctx, req, in.Confirmed) }
		defer func() { startConfirmWorld = nil }()
		defer dropTempFiles()
		// 이 표면에서는 질문을 심자마자 그 자리에서 묻는다 — 기다리는 법은 폼이 안 섰을 때만.
		interviewPlantQuiet = true
		defer func() { interviewPlantQuiet = false }()

		out, err := runGil(func() { cmdStart(startArgs(in)) })
		if err != nil {
			return nil, nil, err
		}
		// 질문지를 막 심은 자리라면, **그 자리에서 사람에게 묻는다.** 심어 놓고 턴을 끝내면
		// 아무 일도 안 일어난다(#82) — MCP 는 그 한 홉을 없앨 수 있는 유일한 표면이다.
		if extra := startElicitIntake(ctx, req); extra != "" {
			out += extra
		}
		return text(out), nil, nil // 앞머리는 installLeadMiddleware 가 붙인다(두 번 붙지 않게)
	})

	registerEntryTools(s)
}

// startArgs — 툴 입력을 CLI 인자로. 본문(내용)은 임시 파일로 바꿔 넘긴다.
func startArgs(in inStart) []string {
	var a []string
	a = addFlag(a, "name", in.Name)
	for _, w := range []struct{ flag, body string }{
		{"identity", in.Identity}, {"will", in.Will}, {"relations", in.Relations},
	} {
		if strings.TrimSpace(w.body) == "" {
			continue
		}
		if p := writeTempTracked("gil-"+w.flag+"-*.md", w.body); p != "" {
			a = append(a, "--"+w.flag, p)
		}
	}
	if in.Status {
		a = append(a, "--status")
	}
	return a
}

// ── 본문을 파일로 나르는 자리의 수명 ──
//
// CLI 는 파일 경로를 받고 MCP 에이전트는 본문을 준다. 그 사이를 임시 파일이 잇는데, **그
// 파일의 수명은 호출 하나**여야 한다. 여기서 두 번 틀릴 수 있고 이번에 둘 다 밟았다:
//
//	· 인자를 조립하는 함수 안에서 defer 로 지우면, 그 defer 는 **조립이 끝날 때** 터진다 —
//	  명령이 그 파일을 읽기도 전이다("--body-file 읽기 실패: no such file"로 나왔다).
//	· 반대로 아무도 안 지우면 호출마다 임시 파일이 쌓인다(본문에는 존재의 정체성·기억이
//	  실린다 — 남겨 둘 것이 아니다).
//
// 그래서 조립할 때 **등록**하고, 명령이 끝난 뒤 호출 경계에서 한꺼번에 지운다. MCP stdio
// 세션은 요청을 순차 처리하고 runGil 이 mcpLock 으로 직렬화하므로 이 목록은 한 호출의 것이다.
var mcpTempFiles []string

func writeTempTracked(pattern, content string) string {
	p, err := writeTemp(pattern, content)
	if err != nil {
		return ""
	}
	mcpTempFiles = append(mcpTempFiles, p)
	return p
}

// dropTempFiles — 이 호출이 만든 임시 파일을 전부 지운다.
func dropTempFiles() {
	for _, p := range mcpTempFiles {
		os.Remove(p)
	}
	mcpTempFiles = nil
}

// adoptCallRepoForCreate — repo 인자를 받아들이되 **아직 저장소가 아니어도 선다.**
//
// adoptCallRepo 는 "이미 git 저장소일 것"을 요구한다. 그건 옳다 — 대부분의 툴은 있는 기록을
// 읽고 쓰는 것이라, 엉뚱한 폴더에 서면 기록이 사람이 안 보는 데 쌓인다(#51). 그런데 **세계를
// 세우는 툴에는 그 검사가 정반대로 작동한다**: 저장소가 아니라서 부르는 것인데 저장소가
// 아니라고 거부했다. 그래서 그 둘만 이 길로 온다(gil_start · gil_init).
//
// 다만 **없는 경로를 만들지는 않는다**(상현님 판단): 이미 있는 폴더에 저장소를 세우는 것은
// CLI 가 하는 일과 정확히 같지만, 없는 절대경로에 디렉터리를 파는 것은 새로 얻는 권한이다.
// 사람이 만든 폴더에만 선다 — 그러면 "어디에 만들지"는 언제나 사람이 정한 것이 된다.
func adoptCallRepoForCreate(in hasRepo) error {
	// 저장소 해석이 어긋난 채로는 아무것도 하지 않는다(#51). 세우는 툴에서 특히 그렇다 —
	// 읽기가 엉뚱한 폴더에 서면 빈 그래프를 보고 말지만, **세우기가 엉뚱한 폴더에 서면
	// 거기에 저장소를 만든다.** 되돌리는 값이 다르다.
	if mcpRepoMismatch != "" {
		return errString(mcpRepoMismatch)
	}
	p := strings.TrimSpace(in.repoArg())
	if p == "" {
		return nil // roots 가 정한 자리를 쓴다
	}
	abs, err := filepath.Abs(p)
	if err != nil {
		return errString("거부: 저장소 경로를 해석하지 못했다: " + p)
	}
	st, serr := os.Stat(abs)
	if serr != nil {
		return errString("거부: 그런 폴더가 없다 — " + abs + "\n" +
			"  gil 은 없는 경로를 만들지 않는다. 사람에게 그 폴더를 만들어 달라고 청하고,\n" +
			"  만들어졌으면 같은 경로로 다시 불러라. (이미 있는 폴더라면 경로를 다시 확인해라.)")
	}
	if !st.IsDir() {
		return errString("거부: 폴더가 아니라 파일이다 — " + abs)
	}
	if os.Chdir(abs) != nil {
		return errString("거부: 저장소 경로로 이동 못 함: " + abs)
	}
	repoSource = repoSourceArg
	stopGitCache()
	return nil
}

// elicitWorldConfirm — "여기에 세울까요?" 를 호스트 네이티브 폼으로 묻는다.
//
// 폼을 못 띄우는 호스트면 **승낙으로 치지 않는다.** 대신 사람에게 직접 물으라고 에이전트에게
// 넘긴다 — 구분 못 하는 것을 단언하지 않는 자리다(#57 이 세운 태도). 다만 그 경우 확인의
// 출처가 '에이전트의 주장'이라는 사실을 기록에 남긴다: 사람 폼의 승낙과는 다른 것이다.
func elicitWorldConfirm(ctx context.Context, req *mcp.CallToolRequest, said bool) (bool, string) {
	wd, _ := os.Getwd()
	schema := `{"type":"object","properties":{"ok":{"type":"boolean","title":"이 폴더에 gil 기록을 시작할까요?","description":"` +
		jsonEscape(wd) + `"}},"required":["ok"]}`
	res, err := req.Session.Elicit(ctx, &mcp.ElicitParams{
		Mode: "form",
		Message: "여기에 gil 세계를 세웁니다 — 저장소·대문·존재의 방·기억이 이 폴더에 생깁니다.\n" +
			"자리: " + wd + "\n" +
			"(이 폴더가 사람 머신에 영속되는 곳이어야 다음 세션이 이 기억을 읽습니다.)",
		RequestedSchema: json.RawMessage(schema),
	})
	// ── 폼이 서지 않은 것과 사람이 거절한 것은 다르다 (#57 — 그리고 내가 그 자리를 다시 밟았다) ──
	//
	// 실측(상현님, 2026-08-09): Claude Desktop 에서 이 폼이 서지 않았고, gil 은 **"사람이
	// 승낙하지 않았다"고 단언**했다. 사람은 거절한 적이 없다 — 방금 "gil 프로젝트 시작하자"고
	// 말한 참이었다. 그러니 에이전트가 받은 것은 거짓이었고, 다시 불러도 같은 답이라 막다른
	// 길이었다. 그래서 에이전트는 gil 을 우회했다: Bash → `git init`. 그 git 이 중간에 죽어
	// 잠금이 남았고, 사람은 터미널 명령을 대신 쳐 달라는 부탁을 받았다.
	//
	// **거부 문구 하나가 우회를 만들고, 우회가 저장소를 반쯤 부쉈다.** 구분 못 하는 것을
	// 단언하면 없던 사람 의사를 심고, 그건 곧 우회 압력이 된다 — #57 이 인터뷰에서 배운 것을
	// 여기서 되풀이했다.
	if err != nil || res == nil {
		// 폼 자체가 성립하지 않았다. 이 호스트에는 네이티브 폼이 없는 것이다.
		if said {
			// 에이전트가 "사람에게 물어 승낙받았다"고 말했다. 그 말을 **출처와 함께** 받는다 —
			// 폼의 승낙과 같은 것이라고 하지 않는다(구분되는 것은 구분해서 적는다).
			return true, "폼 없는 호스트 — 에이전트가 사람에게 물어 승낙받았다고 보고"
		}
		return false, "" // 아래 startAdvance 가 "물어보고 다시 오라"로 안내한다
	}
	if res.Action != "accept" {
		// 폼은 갔는데 accept 가 아니다. 사람이 취소했을 수도, 호스트가 못 그려 즉시 돌려준
		// 것일 수도 있다 — 여기서는 구분할 수 없다(#57). 그러니 거절로 단정하지 않는다.
		if said {
			return true, "폼이 " + res.Action + " 로 돌아옴 — 에이전트가 사람에게 물어 승낙받았다고 보고"
		}
		return false, ""
	}
	if v, ok := res.Content["ok"].(bool); ok && !v {
		// **이건 진짜 거절이다** — 폼이 사람에게 갔고 사람이 아니오를 골랐다. 유일하게 단언할 수 있는 자리.
		return false, "declined"
	}
	return true, "사람이 호스트 폼에서 승낙"
}

// startElicitIntake — 개시 인터뷰가 방금 심겼거나 답을 기다리는 중이면, **그 자리에서** 묻는다.
//
// 왜 여기냐. 옛 인터뷰는 3홉이었다(질문을 심고 → 사람이 뷰어 폼을 찾아 열고 → 답한다).
// 뷰어는 이제 청해야 뜨고, 시작하는 사람에게는 아직 창이 없다 — 그래서 "물었고 기다린다"가
// 사실상 정지였다. MCP 에서는 한 홉이다. 사람이 그 자리에서 답하면 같은 호출 안에서
// 기준이 확정되고, 다음 칸(체인 열기)까지 진행된다.
func startElicitIntake(ctx context.Context, req *mcp.CallToolRequest) string {
	if intakeState(startSlug) != "pending" {
		return ""
	}
	var qs []interviewQ
	if json.Unmarshal([]byte(startQuestionsJSON), &qs) != nil {
		return ""
	}
	res, err := req.Session.Elicit(ctx, &mcp.ElicitParams{
		Mode: "form",
		Message: "이 일이 무엇인지 사람에게 묻습니다. 여기 답한 내용이 **이 프로젝트의 목적과 " +
			"성패 기준**이 되고, 이후 모든 판정이 이 문장에 비추어 이뤄집니다.",
		RequestedSchema: json.RawMessage(elicitSchema(qs)),
	})
	if err != nil || res == nil || res.Action != "accept" {
		// 폼이 안 섰다. 질문은 이미 심겨 있으니 뷰어 폼으로 답할 수 있다 — 그 길을 말한다.
		// **이 호출이 카드를 함께 열었다**(uiStatusMeta) — 질문은 그 카드 안에 폼으로 서 있다.
		// 옛 문구는 여기서 "뷰어 폼"을 가리켰고, 뷰어는 이 표면에서 열 수 없어서 에이전트가
		// 대화로 우회했다(상현님 실사용, 2026-08-10). 열어 놓은 화면을 가리켜야 한다.
		return "\n\n(호스트 네이티브 폼은 서지 않았다. 대신 **질문이 " + askHumanHere() +
			"에 서 있다** — 지금 사람 앞에 떠 있다.)\n" +
			"▸ 사람에게 이렇게 청하라: " + askHumanSentence() + "\n" +
			"▸ 답을 대신 쓰지 마라. 제출되면 다음 호출에서 gil 이 ⚡ 로 알려준다 — " +
			surfaceCall("intake", startSlug+" --status", "chain: "+startSlug+", status: true") + " 로도 확인된다."
	}
	ref := mcpAssembleReference(startSlug, qs, res.Content)
	tmp, terr := writeTemp("gil-intake-*.md", ref)
	if terr != nil {
		return ""
	}
	defer os.Remove(tmp)
	out, rerr := runGil(func() { intakeMode = startSlug; interviewResolve(startSlug, tmp) })
	if rerr != nil {
		return "\n\n(사람의 답을 받았으나 확정에 실패했다: " + rerr.Error() + ")"
	}
	// 답이 확정됐으니 칸이 바뀌었다 — 바뀐 자리를 다시 말한다(다음 수가 곧바로 보이게).
	after, _ := runGil(func() { startSay(startInspect()) })
	return "\n\n── 사람의 답이 도착했다 ──\n" + out + "\n" + after
}

// ── 표면의 빈 칸들 ──
//
// 여기 있는 것들은 **세션이 일을 완주하는 데 필요한 것**만이다(surface.go 의 고르는 기준).
// 저장소 수술(migrate·prune·guard·chain-retire)은 일부러 두지 않는다 — 이유는 terminalOnly 에.

type inIntake struct {
	inRepo
	Slug      string          `json:"slug" jsonschema:"개시 인터뷰 슬러그. 체인 이름이 아니다 — 체인보다 **먼저** 묻는 자리다"`
	Questions []interviewQMCP `json:"questions,omitempty" jsonschema:"사람에게 물을 질문들. 첫 질문은 반드시 열린 질문(type:text)이어야 한다 — 선택지부터 내밀면 사람이 네 가설 공간 안에서만 고른다"`
	Title     string          `json:"title,omitempty"`
	Status    bool            `json:"status,omitempty" jsonschema:"사람이 답했는지 확인한다(pending|done). 인용할 답 번호도 함께 나온다"`
	Wait      bool            `json:"wait,omitempty" jsonschema:"사람이 답할 때까지 기다린다(블로킹). 답을 대신 쓰지 말고 이걸로 기다려라"`
	Timeout   string          `json:"timeout,omitempty" jsonschema:"최대 대기 초(기본 600)"`
	AskRoot   bool            `json:"ask_root,omitempty" jsonschema:"마지막 차수 — **어디서 분기할지**를 묻는다. 후보는 gil 이 그래프에서 계산한다(네가 지어낸 선택지가 아니다)"`
	Reference string          `json:"reference,omitempty" jsonschema:"사람의 답을 마크다운 **본문**으로 직접 확정한다(뷰어를 못 쓰는 사람에게 말로 받았을 때). 파일 경로가 아니라 내용이다"`
}

type inGlobal struct {
	inRepo
	Action  string `json:"action" jsonschema:"list|read|write|mv — 존재의 방(refs/gil/global)을 읽고 쓴다"`
	Path    string `json:"path,omitempty" jsonschema:"글로벌 경로. 예: existence/<이름>/identity.md"`
	To      string `json:"to,omitempty" jsonschema:"mv 의 목적지 경로"`
	Content string `json:"content,omitempty" jsonschema:"write 할 본문 전체. 파일 경로가 아니라 **내용**이다"`
}

type inMemory struct {
	inRepo
	Action string `json:"action" jsonschema:"read|append"`
	Name   string `json:"name,omitempty" jsonschema:"존재의 이름. 이 저장소에 존재가 하나뿐이면 생략해도 된다"`
	Knot   string `json:"knot,omitempty" jsonschema:"이어붙일 매듭 **본문**(append). 한 일·얻은 교훈·다음 세션 순서를 적는다. 파일 경로가 아니다"`
}

type inMerge struct {
	inRepo
	Targets    []string `json:"targets" jsonschema:"합칠 것들. 사이클은 <chain>/<cycle>, 체인은 이름"`
	Into       string   `json:"into" jsonschema:"받는 곳. 끝난 체인을 층으로 모을 때는 dev"`
	Reason     string   `json:"reason" jsonschema:"왜 합치나 — 필수"`
	AllowOpen  bool     `json:"allow_open,omitempty" jsonschema:"닫히지 않은 것을 합치는 예외. 우회했다는 사실이 기록에 남는다"`
	SkipCheck  bool     `json:"skip_check,omitempty" jsonschema:"층 검사를 건너뛴다 — skip_reason 이 필요하다"`
	SkipReason string   `json:"skip_reason,omitempty" jsonschema:"검사를 건너뛰는 이유"`
}

type inAdopt struct {
	inRepo
	Winner string   `json:"winner" jsonschema:"채택할 갈래(스텝 id)"`
	Over   []string `json:"over,omitempty" jsonschema:"진 형제들. 생략하면 그 경합의 나머지 전부"`
	Reason string   `json:"reason" jsonschema:"왜 이 갈래가 이겼나 — 비교의 근거. 없으면 나중에 아무도 그것이 측정이었는지 취향이었는지 모른다"`
}

type inContext struct {
	inRepo
	Target string `json:"target" jsonschema:"<chain> 또는 <chain>/<cycle> — 이 자리에 도착한 누적 컨텍스트를 읽는다"`
}

func registerEntryTools(s *mcp.Server) {
	// gil_intake — **체인보다 먼저** 사람에게 묻는 자리(#90). 이게 없어서 MCP 세션은 문서가
	// 가르치는 첫 수를 칠 수 없었고, 남는 길이 "기준을 스스로 쓰는 것"뿐이었다.
	// **묻는 자리가 곧 화면이 서는 자리다**(상현님 실사용, 2026-08-10). 인터뷰 카드를 세워
	// 놓고도 그 화면을 여는 것이 gil_status 뿐이라, 질문을 심어도 사람 앞엔 아무것도 안 떴다.
	toolUI[inIntake](s, "gil_intake",
		"체인을 열기 **전에** 사람에게 묻는다(개시 인터뷰) — 질문이 **카드 폼으로 사람 화면에 선다**. "+
			"목적과 성패 기준은 사람의 답에서 그대로 인용된다(요약도 정제도 창작이다). "+
			"답이 오면 gil_chain 의 from_intake 로 잇는다.",
		uiStatusMeta(),
		func(in inIntake) []string {
			a := []string{in.Slug}
			switch {
			case in.Status:
				a = append(a, "--status", "--show")
			case in.Wait:
				a = append(a, "--wait")
				a = addFlag(a, "timeout", in.Timeout)
			case in.AskRoot:
				a = append(a, "--ask-root")
			case strings.TrimSpace(in.Reference) != "":
				if p := writeTempTracked("gil-intake-ref-*.md", in.Reference); p != "" {
					a = append(a, "--resolve", p)
				}
			default:
				qs := make([]interviewQ, 0, len(in.Questions))
				for _, q := range in.Questions {
					qs = append(qs, interviewQ{Q: q.Q, Type: q.Type, Options: q.Options})
				}
				raw, _ := json.Marshal(qs)
				if p := writeTempTracked("gil-intake-q-*.json", string(raw)); p != "" {
					a = append(a, "--ask", p)
				}
				a = addFlag(a, "title", in.Title)
			}
			return a
		}, cmdIntake)

	// gil_global — 존재의 방. 이게 없어서 init 이 준 **첫 과제**(이름을 짓고 방을 채운다)가
	// MCP 에서 불가능했다. 안내는 있는데 실행할 손이 없던 자리다.
	tool(s, "gil_global",
		"존재의 방(refs/gil/global)을 읽고 쓴다 — identity·will·relations·명부. 체인·머신을 "+
			"넘어 단일하게 산다. write 는 파일이 아니라 **본문**을 받는다.",
		func(in inGlobal) []string {
			switch in.Action {
			case "list":
				return []string{"list"}
			case "read":
				return []string{"read", in.Path}
			case "mv":
				return []string{"mv", in.Path, in.To}
			case "write":
				p := writeTempTracked("gil-global-*.md", in.Content)
				if p == "" {
					return []string{"write", in.Path, ""}
				}
				return []string{"write", in.Path, p}
			}
			return []string{in.Action}
		}, cmdGlobal)

	// gil_memory — 세션을 넘기는 유일한 통로. 없으면 MCP 세션의 존재는 매번 죽는다.
	tool(s, "gil_memory",
		"존재의 기억을 읽고(read) 매듭을 이어붙인다(append). 세션을 넘어 이어지는 것은 이것뿐이다 — "+
			"한 일·얻은 교훈·다음 세션 순서를 남겨라. append 는 파일이 아니라 **본문**을 받는다.",
		func(in inMemory) []string {
			if in.Action == "append" {
				p := writeTempTracked("gil-knot-*.md", in.Knot)
				if p == "" {
					return []string{"append", in.Name, ""}
				}
				return []string{"append", in.Name, p}
			}
			if strings.TrimSpace(in.Name) == "" {
				return []string{"read"}
			}
			return []string{"read", in.Name}
		}, cmdMemory)

	// gil_merge — 끝낸 것을 모은다. 없으면 체인을 닫고도 **일을 마칠 수 없다**.
	tool(s, "gil_merge",
		"닫은 것을 합친다 — 사이클을 체인으로, 끝난 체인을 층(dev)으로. 완성만 합류 대상이다. "+
			"(dev → main 은 합류가 아니라 배포다: gil_deploy)",
		func(in inMerge) []string {
			a := append([]string{}, in.Targets...)
			a = addFlag(a, "into", in.Into)
			a = addFlag(a, "reason", in.Reason)
			if in.AllowOpen {
				a = append(a, "--allow-open")
			}
			if in.SkipCheck {
				a = append(a, "--skip-check")
			}
			return addFlag(a, "skip-reason", in.SkipReason)
		}, cmdMerge)

	// gil_adopt — 경합을 끝맺는 유일한 그림. 갈래를 열 수 있는데 닫을 수 없으면 반쪽이다.
	tool(s, "gil_adopt",
		"나란히 세운 갈래 중 승자를 채택한다 — 진 갈래마다 기각 잎을 남기고 HEAD 를 승자로 옮긴다.",
		func(in inAdopt) []string {
			a := []string{in.Winner}
			for _, o := range in.Over {
				a = append(a, "--over", o)
			}
			return addFlag(a, "reason", in.Reason)
		}, cmdAdopt)

	// gil_context — 이 자리에 도착한 누적 지식. 읽기 표면이 없으면 에이전트는 다시 판다.
	tool(s, "gil_context",
		"이 자리에 도착한 누적 컨텍스트를 읽는다 — 체인 목적·기준에서 시작해 조상 사이클들이 "+
			"남긴 전수·설계·회고를 오래된 것부터.",
		func(in inContext) []string { return []string{in.Target} }, cmdContext)
}

func jsonEscape(s string) string {
	b, err := json.Marshal(s)
	if err != nil {
		return `""`
	}
	return strings.Trim(string(b), `"`)
}
