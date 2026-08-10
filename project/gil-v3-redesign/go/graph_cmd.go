// graph_cmd.go — `gil graph` : 사고 그래프를 **그림으로** 낸다.
//
// 왜 새 이름인가. 이 진입점은 `gil viewer build` 로 살았다 — 그런데 뷰어(브라우저 서버)는
// 은퇴하고 렌더러는 남는다(graph_render.go 의 첫 주석). 진입점이 죽는 매체의 이름을 달고
// 있으면, 매체를 지울 때 **살아 있는 코드의 문이 함께 닫힌다.**
//
// 그리고 이 문은 사용자 기능이자 **검증면**이다: 시험 40여 개가 이 HTML 을 파싱해 계승(#53)·
// 발아(#104)·배포 귀속(#108)·경합(#112)·층 뿌리(#113)·형제 레인(#114) 을 단언한다. 문을
// 닫으면 **계속 살아서 MCP 화면을 그리는 코드의 시험만** 사라진다 — 가장 나쁜 조합이다.
//
// 이름을 `graph` 로 둔 이유: MCP 표면에 이미 `gil_graph` 가 있다. 두 표면이 같은 것을 같은
// 이름으로 부르면 안내가 한 문장으로 두 곳에서 옳다(surface.go 가 세운 규칙).
package main

import (
	"os"
	"strings"
)

func cmdGraph(args []string) {
	fs := newFlags("gil graph")
	// --html: 그림을 **자기완결 HTML 한 장**으로. 서버도 브라우저도 필요 없다.
	asHTML := fs.boolFlag("html")
	out := fs.str("out", "")
	// --repo: 저장소 **밖에서** 다른 저장소의 그림을 굽는다. `viewer build --repo` 가 하던
	// 일이고, 온라인 예시 그래프를 다시 굽는 길이기도 하다 — 진입점만 옮기고 이 플래그를
	// 흘리면 그 사용례가 조용히 사라진다.
	repo := fs.str("repo", "")
	lang := fs.str("lang", "")
	fs.parse(args)

	if strings.TrimSpace(*repo) != "" {
		viewerRepoDir = *repo
	}
	if l := strings.TrimSpace(*lang); l != "" {
		if !i18nSupported(l) {
			die("거부: 모르는 언어 " + l + " — 쓸 수 있는 것: " + strings.Join(i18nLangs, " · "))
		}
		viewerLang = l
	}
	if !*asHTML {
		// 그림 없이 부르면 **터미널의 그림**을 낸다. 없는 것을 요구하지 않는다 —
		// `gil graph` 한 줄이 아무것도 안 하고 사용법만 뱉으면 그건 문이 아니라 벽이다.
		renderText(buildGraph())
		return
	}
	if strings.TrimSpace(*out) == "" {
		die("사용: gil graph --html --out <파일> [--repo <경로>] [--lang <언어>]\n" +
			"  자기완결 HTML 한 장(서버 없이 열린다). 그림 없이 보려면: gil graph")
	}
	writeGraphHTML(*out)
}

// writeGraphHTML — 정적 HTML 을 파일 하나로 굳힌다(서버 없이 자기완결).
//
// **MCP 의 그래프 화면과 같은 한 줄을 부른다**(mcp_ui.go 의 renderHTML(buildGraph(), true)).
// 두 벌로 갈라 놓으면 한쪽만 고쳐지고, 그러면 시험이 재는 그림과 사람이 보는 그림이 달라진다.
func writeGraphHTML(out string) {
	page := renderHTML(buildGraph(), true)
	if err := os.WriteFile(out, []byte(page), 0644); err != nil {
		die("거부: 정적 HTML 쓰기 실패: " + err.Error())
	}
	println2("graph → " + out + " (정적 자기완결 HTML · " + itoa(len(page)) + " 바이트)")
}
