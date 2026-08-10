// mcp_ui_card.go — **앱이 카드를 가져온다.** MCP Apps 의 실제 흐름에 맞춘 자리 (상현님 실측).
//
// 왜 다시 짓나. 우리는 "읽는 시점에 통째로 렌더"하기로 했었다 — 레이아웃이 Go 에 있으니
// 그 편이 진실원을 하나로 두는 길이라고 봤다. 그런데 프레임 로그가 순서를 보여줬다:
//
//	read  resources/read  ui://gil/status   ← 호스트가 템플릿을 **먼저** 가져간다
//	write result id=3                        ← 651 바이트 "어느 저장소를 볼지 모른다"
//	read  tools/call  gil_status             ← 툴은 그 뒤에 돈다
//
// 호스트는 툴이 돌기 전에 읽고, **그 뒤로 다시 읽지 않는다**(규범: prefetch/cache 허용, 강제
// 재읽기 수단 없음). 그 시점엔 어느 저장소인지 알 방법이 없으니 우리가 낸 것은 카드가 아니라
// 경고 페이지였다. 화면이 안 뜬 이유는 렌더링 미지원이 아니라 **우리가 그 순간에 카드를 낼 수
// 없는 설계**였다는 것이다. 두 호스트 다 io.modelcontextprotocol/ui 를 선언하고 실제로 읽었다.
//
// 그래서 통로를 바꾼다. 템플릿(껍데기)은 한 번 읽히고, **카드는 앱이 툴을 불러 가져온다.**
// 레이아웃은 여전히 Go 하나에만 있다 — 앱은 받은 HTML 을 그려 넣기만 한다(JS 로 이중화하면
// 그게 나중에 어긋나는 빚이다). 그리고 이 통로가 곧 승인·기각 버튼이 쓸 통로다.
//
// 모델 문맥. 카드 HTML 은 6KB 가 넘는다 — 모델이 볼 이유가 없다. 규범은 내용 단위로 감추는
// 길을 주지 않고 **툴 단위**만 준다(visibility: ["app"]). 그래서 이 툴은 앱 전용이다:
// 에이전트의 툴 목록에 안 뜨고, 앱만 부른다.
package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type inCardArgs struct {
	Repo string `json:"repo,omitempty" jsonschema:"어느 저장소인가(절대경로). 비우면 서버가 아는 자리를 쓴다"`
	// Probe — 화면이 **자기가 어떤 자리에 떴는지** 실어 보내는 칸(진단 전용).
	//
	// 왜 이런 칸이 있나. iframe↔호스트의 postMessage 프레임은 서버에 오지 않는다. 그래서
	// "호스트가 핸드셰이크에 무엇이라 답했나 / 프레임이 실제로 보이는 크기인가"를 볼 방법이
	// 없었고, 그 공백에서 판정이 세 번 뒤집혔다. 화면이 제 상태를 이 칸에 적어 보내면 우리
	// 프레임 로그에 남는다 — 추측하지 않으려면 계기가 있어야 한다.
	//
	// **기본은 꺼져 있다.** 껍데기는 `GIL_UI_PROBE=1` 일 때만 이 칸을 채워 보낸다 — 켜 둔
	// 채로 릴리스하면 모든 세션이 매번 두 번씩 진단 호출을 한다. 받는 쪽(여기)은 늘 열어
	// 둔다: 켠 사람이 다음 릴리스를 기다릴 이유가 없다.
	Probe string `json:"probe,omitempty" jsonschema:"진단용 — 화면이 자기 상태(호스트 응답·크기)를 적어 보내는 칸. GIL_UI_PROBE=1 일 때만 온다"`
	// Host — 화면이 선 **표면의 사실**. 호스트가 핸드셰이크에서 밝힌 것을 화면이 적어 보낸다.
	//
	// 왜 진단(Probe)과 따로인가. Probe 는 켤 때만 오는 계기지만, 이건 **늘 필요한 사실**이다:
	// 도구가 "곁에 띄울 수 있다"·"크게 볼 수 있다"를 사람에게 말하려면 이 호스트가 그걸
	// 지원하는지 알아야 하고, iframe↔호스트 프레임은 서버에 안 오므로 화면이 실어 보내는
	// 길밖에 없다. 모르면서 말하면 없는 화면을 가리키는 그 병이 된다.
	Host string `json:"host,omitempty" jsonschema:"화면이 선 표면 — 호스트가 밝힌 표시모드·테마변수·능력(JSON)"`
}

// mcpUIHost — 화면이 마지막으로 알려준 표면의 사실. 비면 아직 화면이 안 떴거나 안 알려줬다.
var mcpUIHost struct {
	Modes []string `json:"modes"`
	Mode  string   `json:"mode"`
	Vars  int      `json:"vars"`
	Caps  []string `json:"caps"`
	known bool
}

// uiHostLine — 이 표면에 대해 **아는 것만** 한 줄로. 모르면 빈 값(모르는 것은 말하지 않는다).
func uiHostLine() string {
	if !mcpUIHost.known {
		return ""
	}
	s := "화면: 카드가 떠 있다"
	if mcpUIHost.Mode != "" {
		s += "(" + mcpUIHost.Mode + ")"
	}
	if len(mcpUIHost.Modes) > 0 {
		s += " · 이 호스트가 여는 모드: " + strings.Join(mcpUIHost.Modes, "·")
	} else {
		s += " · 표시 모드는 호스트가 안 밝혔다"
	}
	return s
}

func (i inCardArgs) repoArg() string { return i.Repo }

// registerGilCardTool — 앱 전용 카드 공급 툴.
func registerGilCardTool(s *mcp.Server) {
	mcp.AddTool(s, &mcp.Tool{
		Name: "gil_status_card",
		Description: "앱 전용 — 상태 카드의 HTML 조각을 낸다. 사람이나 모델이 부를 것이 아니다" +
			"(화면이 자기 내용을 가져오는 통로다). 사람에게 상태를 보여주려면 gil_status 를 부른다.",
		Meta: mcp.Meta{"ui": map[string]any{"visibility": []string{"app"}}},
	}, func(ctx context.Context, req *mcp.CallToolRequest, in inCardArgs) (*mcp.CallToolResult, any, error) {
		if h := strings.TrimSpace(in.Host); h != "" {
			// 못 읽어도 죽지 않는다 — 이건 사실을 더하는 칸이지 관문이 아니다.
			if json.Unmarshal([]byte(h), &mcpUIHost) == nil {
				mcpUIHost.known = true
			}
		}
		if in.Probe != "" {
			// 프레임 로그에도, Desktop 로그에도 남게 한다(둘 중 하나만 켜져 있을 수 있다).
			stderr("gil ui probe: " + clip(in.Probe, 1200))
		}
		// **저장소를 찾는 순서.** 앱의 호출에는 인자가 없을 수 있다 — 화면은 사람이 무엇을
		// 열었는지 모르고, 호스트가 roots 를 안 주는 자리도 있다(실측: cwd 가 `/`).
		// ① 인자 ② 지금 선 자리(git 이면) ③ 이 서버가 앞선 호출에서 기억한 자리.
		//
		// 그리고 **실패해도 오류가 아니라 카드로 답한다.** 앱에게 isError 를 주면 화면은
		// "응답에 카드가 없다"만 적고 사람은 왜 그런지 모른다 — 실측으로 그 자리를 봤다.
		// 화면은 언제나 무언가를 말해야 하고, 못 하는 것은 못 한다고 말해야 한다.
		if repo := cardRepo(in.Repo); repo != "" {
			if os.Chdir(repo) == nil {
				stopGitCache()
			}
		}
		if !gitOK("rev-parse", "--git-dir") {
			wd, _ := os.Getwd()
			return cardResult(uiNoRepoCard(wd)), nil, nil
		}
		rememberUIRepo()
		var st statusOut
		if _, err := runGil(func() { st = gatherStatus() }); err != nil {
			return cardResult(uiNoRepoCard(err.Error())), nil, nil
		}
		// **카드를 content 에 싣는다.** 실측: 호스트가 앱의 tools/call 에 돌려주는 것은
		// `{content, isError}` 뿐이고 structuredContent 는 앱에게 전달하지 않는다 — 화면이
		// "응답에 카드가 없다: content,isError" 를 적어 보내 그걸 알려줬다. 그래서 조각은
		// 텍스트 내용으로 간다. 이 툴은 앱 전용이라(visibility: ["app"]) 이 6KB 가 모델
		// 문맥에 실리지는 않는다 — 통로를 옮겨도 그 값은 지킨다.
		return cardResult(statusCardBodyHTML(st)), nil, nil
	})
}

// cardRepo — 이 조회가 볼 저장소. 인자 > 지금 선 자리(git) > 서버가 기억한 자리.
func cardRepo(arg string) string {
	if strings.TrimSpace(arg) != "" {
		if abs, err := filepath.Abs(arg); err == nil {
			if _, e := gitTryIn(abs, "rev-parse", "--git-dir"); e == nil {
				return abs
			}
		}
	}
	if gitOK("rev-parse", "--git-dir") {
		return "" // 이미 옳은 자리에 서 있다 — 옮기지 않는다
	}
	return mcpUIRepo
}

// cardResult — 카드 조각을 앱에게 준다. **content 와 structuredContent 둘 다에** 싣는다:
// 실측으로 호스트가 앱에게 넘겨준 것은 content 뿐이었지만, 통로가 하나뿐이라고 가정하면
// 호스트가 바뀔 때 화면이 다시 빈다.
func cardResult(card string) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		Content: []mcp.Content{&mcp.TextContent{Text: card}},
		StructuredContent: map[string]any{
			"cardHtml":     card,
			"tipSignature": tipSignatureDigest(),
		},
	}
}

// uiNoRepoCard — 어느 저장소인지 모를 때의 **카드**(오류가 아니다).
func uiNoRepoCard(detail string) string {
	return `<div class="card"><div class="crumb">gil</div>` +
		`<div class="repo">` + esc(detail) + `</div>` +
		`<div class="panel"><div class="lbl">어느 저장소를 볼지 모른다</div>` +
		`<div class="none">이 화면은 인자를 실을 수 없는 자리에서 열렸고, 호스트가 열린 폴더를 ` +
		`알려주지 않았다(roots 미지원). 에이전트가 <code>gil_status</code> 를 repo 인자와 함께 ` +
		`한 번 부르면, 그 뒤로 이 화면도 그 저장소를 본다.</div></div></div>`
}
