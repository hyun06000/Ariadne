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
	// 곁에 세우기를 청한 결과. **청한 것(Asked)과 받은 것(Grant/Err)을 가른다** — 안 가르면
	// 거절·무응답·안 청함이 화면 밖에서 전부 똑같이 "인라인 카드"로 보인다.
	Asked string `json:"asked"`
	Grant string `json:"grant"`
	Err   string `json:"err"`
	Why   string `json:"why"`
	// **어느 표면에서 온 보고인가.** 규범의 hostContext.userAgent·platform.
	// 이 칸이 없던 동안, 한 서버를 여러 표면(Code·Cowork·채팅)이 나눠 쓰는 바람에 읽은
	// 표시모드가 **어느 표면의 것인지 알 수 없었다** — 마지막에 보고한 화면이 앞의 값을
	// 덮으니까. 출처 없는 값은 잰 것이 아니다.
	UA   string `json:"ua"`
	Plat string `json:"plat"`
	// **크게 보기는 곁에 세우기와 따로 적는다.** 둘은 청하는 방식부터 다르다 — pip 은 화면이
	// 스스로, fullscreen 은 **사람이 눌러야**(정본 패턴). 한 칸에 겹쳐 적으면 "곁엔 못 서지만
	// 크게는 된다" 같은 갈래가 한 값으로 뭉개지고, 그러면 다음 수가 다시 추측이 된다.
	FSAsked string `json:"fsAsked"`
	FSGrant string `json:"fsGrant"`
	FSErr   string `json:"fsErr"`
	FSWhy   string `json:"fsWhy"`
	// **바깥의 것을 여는 것.** pip 이 없다는 것이 확정된 뒤(2026-08-11), 대화 곁에 서는
	// 화면은 카드 안에서 못 만든다 — 남은 길은 카드가 바깥의 앱을 여는 것이다. 규범은
	// ui/open-link 의 스킴을 제한하지 않고, 디렉터리 정책은 커스텀 스킴을 자기 앱에 한해
	// 허용한다. 그 둘 사이에 실제로 무엇이 통과하는지는 재야 안다.
	LnAsked string `json:"lnAsked"`
	LnGrant string `json:"lnGrant"`
	LnErr   string `json:"lnErr"`
	LnWhy   string `json:"lnWhy"`
	// Ver — **화면에 떠 있는 껍데기의 판.** 호스트가 ui:// 리소스를 캐시하고 다시 안 읽으므로
	// (규범 허용), 서버를 새로 깔아도 사람 화면에는 옛 껍데기가 남을 수 있다.
	Ver   string `json:"ver"`
	known bool
}

// uiShellStale — 화면의 껍데기가 이 서버의 판과 다른가("" = 같거나 모른다).
//
// 왜 이 한 줄이 값을 하나. 2026-08-10 에 같은 자리를 세 번 고치고 세 번 "안 된다"고 읽었다 —
// 실제로는 고친 껍데기가 **화면에 닿은 적이 없었다.** 고친 것과 뜬 것이 다른데 구별할 방법이
// 없으면, 그 뒤의 판정이 전부 헛것 위에 선다. 그래프는 이미 제 낡음을 밝히고 있었고
// (mcp_ui.go 의 팁 서명), 카드만 그걸 안 배웠다.
func uiShellStale() string {
	if !mcpUIHost.known || mcpUIHost.Ver == "" || mcpUIHost.Ver == gilVersion {
		return ""
	}
	return "⚠ 화면의 껍데기가 낡았다: 떠 있는 것 " + mcpUIHost.Ver + " · 이 서버 " + gilVersion +
		" — 호스트가 옛 화면을 캐시하고 있다. **껍데기를 고쳤다면 그 수정은 아직 화면에 없다.** " +
		"확장을 다시 설치하거나 대화를 새로 열어야 새 껍데기를 읽는다."
}

// uiHostLine — 이 표면에 대해 **아는 것만** 한 줄로. 모르면 빈 값(모르는 것은 말하지 않는다).
func uiHostLine() string {
	// **카드가 안 떴어도 말할 수 있는 것이 하나 있다.** 호스트가 MCP Apps 확장을 선언하지
	// 않았다면 카드는 영영 안 뜬다 — 그건 핸드셰이크에 이미 와 있는 사실이라, 화면의 보고를
	// 기다릴 이유가 없다. 침묵하면 그 자리의 세션은 "왜 카드가 없지"를 추측하게 되고,
	// 안내가 카드를 가리키면 없는 곳을 가리키게 된다(실측: Cowork).
	if hostCapsKnown && !hostDeclaresUI {
		s := "화면: 이 호스트는 MCP Apps 를 선언하지 않았다 — 카드·인터뷰 폼이 뜨지 않는다."
		// **남은 통로가 있는지까지 말한다.** 없다는 말만 하면 그 자리의 세션은 대화로 가고,
		// 대화로 가면 옮겨쓰기가 낀다. 호스트 네이티브 폼(elicitation)이 있으면 그걸 가리킨다.
		if hostDeclaresElicit {
			s += " 다만 호스트 네이티브 폼(elicitation)은 선언했다 — 사람에게 묻는 것은 그 길로 간다."
		} else {
			s += " 호스트 네이티브 폼(elicitation)도 없다 — 물을 곳은 이 대화뿐이다. " +
				"사람이 쓴 문장을 그대로 실어라(요약도 정제도 창작이다)."
		}
		return s
	}
	if !mcpUIHost.known {
		return ""
	}
	s := "화면: 카드가 떠 있다"
	if st := uiShellStale(); st != "" {
		// **낡음을 먼저 말한다.** 아래 줄들은 그 낡은 화면이 보고한 것이라, 낡았다는 사실을
		// 모르고 읽으면 지금 서버의 사실로 오해한다.
		s = st + "\n" + s
	}
	if mcpUIHost.Mode != "" {
		s += "(" + mcpUIHost.Mode + ")"
	}
	// **이 보고가 어느 표면에서 왔는지 먼저 말한다.** 한 서버를 여러 표면이 나눠 쓰므로,
	// 출처를 안 적으면 아래 모드 목록이 어느 화면의 사실인지 아무도 모른다.
	if who := strings.TrimSpace(mcpUIHost.UA + " " + mcpUIHost.Plat); who != "" {
		s += " · 그 화면이 선 곳: " + who
	} else {
		s += " · 그 화면은 자기가 어디인지 안 밝혔다"
	}
	if len(mcpUIHost.Modes) > 0 {
		s += " · 이 호스트가 여는 모드: " + strings.Join(mcpUIHost.Modes, "·")
	} else {
		s += " · 표시 모드는 호스트가 안 밝혔다"
	}
	// **호스트가 할 수 있다고 밝힌 것.** 규범의 hostCapabilities — openLinks·downloadFile·
	// serverTools·serverResources·logging·sandbox·updateModelContext·message·sampling.
	// 화면은 이미 이 키들을 실어 보내고 있었는데 아무 데도 안 보여줬다. 모아 놓고 안 보면
	// 없는 것과 같다 — 그리고 그 침묵 위에서 "이건 되나?"를 매번 추측하게 된다.
	if len(mcpUIHost.Caps) > 0 {
		s += " · 호스트가 할 수 있다는 것: " + strings.Join(mcpUIHost.Caps, "·")
	}
	// **왜 인라인인지를 말한다.** 이 줄이 없으면 사람도 에이전트도 "곁에 안 뜨네"까지만 알고
	// 그 앞의 갈래(거절/무응답/애초에 안 청함)를 구별할 수 없다 — 그러면 다음 수가 추측이 된다.
	switch {
	case mcpUIHost.Why != "":
		s += " · 곁에 세우기: 안 청했다(" + mcpUIHost.Why + ")"
	case mcpUIHost.Err != "":
		s += " · 곁에 세우기(pip) 청함 → " + mcpUIHost.Err + " · 인라인으로 남는다"
	case mcpUIHost.Grant != "":
		s += " · 곁에 세우기(pip) 청함 → 호스트가 준 자리: " + mcpUIHost.Grant
	case mcpUIHost.Asked != "":
		s += " · 곁에 세우기(pip) 청함 → 아직 답을 못 받았다"
	}
	// **크게 보기는 사람이 눌러야 청해진다.** 그러니 여기 아무것도 안 적혀 있으면 그것은
	// "거절됐다"가 아니라 **아직 아무도 안 눌렀다**는 뜻이다 — 그 둘을 섞으면 다음 세션이
	// "호스트가 안 준다"고 결론짓고 실제로는 한 번도 안 청해 본 채로 넘어간다.
	switch {
	case mcpUIHost.FSErr != "":
		s += " · 크게 보기(fullscreen) 사람이 누름 → " + mcpUIHost.FSErr
	case mcpUIHost.FSGrant != "":
		s += " · 크게 보기(fullscreen) 사람이 누름 → 호스트가 준 자리: " + mcpUIHost.FSGrant
	case mcpUIHost.FSAsked != "":
		s += " · 크게 보기(fullscreen) 사람이 누름 → 아직 답을 못 받았다"
	case mcpUIHost.FSWhy != "":
		s += " · 크게 보기: 버튼을 안 냈다(" + mcpUIHost.FSWhy + ")"
	default:
		s += " · 크게 보기: 버튼은 있고 아직 아무도 안 눌렀다"
	}
	// **링크는 아무도 안 누르면 아무 말도 안 한다.** 이건 계기(GIL_UI_PROBE=1)를 켠 동안만
	// 나오는 시험 버튼이라, 안 눌린 것이 기본이다 — 기본 상태를 매번 한 줄로 적으면 그 줄이
	// 나머지를 덮는다. 누른 뒤에만 말한다.
	switch {
	case mcpUIHost.LnErr != "":
		s += " · 링크 열기(" + mcpUIHost.LnAsked + ") 사람이 누름 → " + mcpUIHost.LnErr
	case mcpUIHost.LnGrant != "":
		s += " · 링크 열기(" + mcpUIHost.LnAsked + ") 사람이 누름 → " + mcpUIHost.LnGrant
	case mcpUIHost.LnAsked != "":
		s += " · 링크 열기(" + mcpUIHost.LnAsked + ") 사람이 누름 → 아직 답을 못 받았다"
	case mcpUIHost.LnWhy != "":
		s += " · 링크 열기: 안 청했다(" + mcpUIHost.LnWhy + ")"
	}
	return s
}

func (i inCardArgs) repoArg() string { return i.Repo }

// registerGilCardTool — 앱 전용 카드 공급 툴.
func registerGilCardTool(s *mcp.Server) {
	mcp.AddTool(s, &mcp.Tool{
		Name:        "gil_status_card",
		Annotations: toolAnn("gil_status_card"),
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
			setRepoDir(repo)
		}
		if !gitOK("rev-parse", "--git-dir") {
			return cardResult(uiNoRepoCard(hereAbs())), nil, nil
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
	// **저장소를 못 찾은 것은 막다른 길이 아니라 첫 칸이다.**
	//
	// 옛 카드는 여기서 "어느 저장소를 볼지 모른다"고만 말하고, 에이전트에게 repo 인자를
	// 실어 다시 부르라고 시켰다. 그런데 MVP 표면(Desktop 일반 채팅)은 roots 를 안 주므로
	// **거의 모든 첫 화면이 이 자리**이고, 그러면 비개발자가 절대경로를 말해야 한다.
	// 거기서 흐름이 끝난다 — 그건 이 사람들이 답할 수 있는 질문이 아니다.
	//
	// 그래서 이 화면이 **시작하는 화면**이 된다: gil 이 자리를 제안하고, 사람은 이름만
	// 적고, 버튼을 누른다. 경로는 아무도 치지 않는다.
	root := defaultPlaceRoot()
	if root == "" {
		// 홈을 모르면 제안할 수 없다 — 그때는 사실대로 못 한다고 말한다.
		return `<div class="card"><div class="crumb">gil</div>` +
			`<div class="repo">` + esc(detail) + `</div>` +
			`<div class="panel"><div class="lbl">어느 저장소를 볼지 모른다</div>` +
			`<div class="none">홈 폴더를 알 수 없어 만들 자리를 제안하지 못한다. ` +
			`저장소의 절대경로를 <code>repo</code> 인자에 실어 불러라.</div></div></div>`
	}
	short := shortenHome(root)
	return `<div class="card" data-start="1">` +
		`<div class="crumb">새 프로젝트를 시작합니다</div>` +
		`<div class="row"><div class="lbl">무엇에 대한 기록인가요</div>` +
		`<input class="ivin" data-start-name="1" placeholder="예: 타이타닉 생존자 분석" ` +
		`data-root="` + esc(short) + `"></div>` +
		`<div class="row"><div class="lbl">여기에 만듭니다</div>` +
		`<div class="repo" data-start-preview="1">` + esc(short) + `/…</div></div>` +
		`<div class="acts">` +
		`<button class="btn primary" data-act="start-here" ` +
		`data-arm="이 폴더를 만듭니다 — 한 번 더">여기에 시작한다</button></div>` +
		`<details class="startmore"><summary>다른 자리에 만들기</summary>` +
		`<input class="ivin" data-start-place="1" value="` + esc(short) + `">` +
		`<div class="none">폴더가 없으면 만들어집니다. 홈 폴더 안이어야 합니다 — ` +
		`바깥에 만들려면 그 경로를 <code>repo</code> 인자에 실어 부릅니다.</div></details>` +
		// 진단은 남긴다. 없애면 "왜 저장소를 못 찾았나"를 다시 추측하게 된다.
		`<div class="foot">지금 선 자리: <code>` + esc(detail) + `</code> — ` +
		`이미 만들어 둔 저장소가 있으면 그 경로를 <code>repo</code> 인자에 실어 불러라.</div>` +
		`</div>`
}
