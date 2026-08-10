// surface.go — **안내가 자기가 선 표면을 안다** (상현님, 2026-08-09).
//
// 무엇이 문제였나. gil 의 안내(NEXT·거부·다음 한 수)는 전부 CLI 명령줄로 쓰여 있다.
// 소스 전체에서 `gil <명령>` 을 가리키는 자리가 411곳인데, 그중 MCP 표면에 대응 툴이 없는
// 명령을 가리키는 것이 411곳이었다(2026-08-09 실측: viewer 52 · merge 52 · intake 51 ·
// global 45 · memory 24 …). MCP 로 도는 세션 — 비개발자가 쓰는 바로 그 표면 — 에서는
// 그 줄들이 **칠 수 없는 줄**이다. 실측한 세 자리:
//
//	· 빈 폴더에 gil_init → "먼저 gil_init 을 그 경로로 불러라"  (자기 자신을 가리키는 닫힌 고리)
//	· 체인 거부의 권장 경로가 `gil intake …` — 그 표면에 툴이 없다. 남는 길은 같은 메시지가
//	  금지하는 것("네가 기준을 창작해 넣지 마라") 하나뿐이었다.
//	· "가장 먼저 부르라"는 gil_handoff 의 다음 수 12개 중 11개가 못 치는 것.
//
// 어떻게 고치나 — **두 갈래로 가른다.**
//
//  1. 세션 안에서 일을 **완주하는 데 필요한 명령**은 툴로 세운다. 그러면 안내가 적은
//     `gil intake foo --ask …` 는 그대로 옳다: 이름이 기계적으로 대응하므로
//     (`gil x-y` → `gil_x_y`) 에이전트가 스키마를 툴에서 읽어 그대로 친다.
//     **411곳을 고쳐 쓰는 대신 411곳이 가리키는 것을 실재하게 만든다.**
//  2. 저장소 수술처럼 **사람이 터미널에서 해야 하는 명령**은 툴로 만들지 않는다. 대신
//     그 사실을 안내가 그 자리에서 말한다 — 없는 것을 있는 척 가리키지 않는다.
//
// 그리고 이 규칙을 **시험이 센다**(surface_test 계열): 안내가 가리키는 명령은 툴이 있거나
// 터미널 전용으로 선언돼 있어야 한다. 열거가 아니라 규칙이라, 새 명령이 늘어도 안 샌다
// (열거는 늘 뒤늦다 — v3.58.3 에서 값을 치른 자리).
package main

import (
	"sort"
	"strings"
)

// mcpSurface — MCP 툴로 서는 명령들. **여기 적힌 것과 실제로 등록되는 툴이 어긋나면
// 시험이 잡는다** — 표가 실재를 앞지르면 그 표가 곧 거짓 안내가 되기 때문이다.
//
// 고르는 기준은 하나다: **이 명령 없이 세션이 일을 완주할 수 있는가.** 못 하면 툴로 세운다.
var mcpSurface = map[string]string{
	"start":       "gil_start",
	"init":        "gil_init",
	"intake":      "gil_intake",
	"interview":   "gil_interview",
	"chain":       "gil_chain",
	"open":        "gil_open",
	"step":        "gil_step",
	"close":       "gil_close",
	"chain-close": "gil_chain_close",
	"merge":       "gil_merge",
	"adopt":       "gil_adopt",
	"deploy":      "gil_deploy",
	"approve":     "gil_approve",
	"reject":      "gil_reject",
	"goto":        "gil_goto",
	"log":         "gil_log",
	"fsck":        "gil_fsck",
	"status":      "gil_status",
	"context":     "gil_context",
	"handoff":     "gil_handoff",
	"global":      "gil_global",
	"memory":      "gil_memory",
}

// terminalOnly — **일부러** MCP 에 안 세우는 명령과 그 이유.
//
// 왜 이유까지 적나. 이유 없이 빠진 것과 판단해서 뺀 것은 다르다. 이유가 없으면 다음 세션이
// "빠뜨렸구나" 하고 채우고, 그러면 저장소 수술이 대화 한 줄로 도는 자리가 생긴다.
var terminalOnly = map[string]string{
	"migrate":        "이력을 다시 그린다(모든 SHA 가 바뀐다) — 사람이 터미널에서, 되돌릴 곳을 보고.",
	"prune":          "가지를 지운다 — 삭제는 사람의 손과 승인 화면을 지난다.",
	"chain-retire":   "체인을 접는다 — 되돌리기 어려운 정리라 터미널에서.",
	"chain-unretire": "접은 체인을 되살린다 — 위와 같은 자리.",
	"guard":          "git 훅과 로컬 설정을 건드린다 — 클론마다 사람이 한 번 건다.",
	"docs":           "온보딩 문서를 저장소에 심는다 — 설치의 일이다.",
	"viewer":         "관전 서버·브라우저를 띄운다 — 사람의 창이라 사람이 연다.",
	"version":        "버전 확인은 묻지 않아도 배너가 먼저 한다.",
	"drift":          "바이너리 드리프트 점검 — 설치 진단이라 터미널에서.",
	"reconcile":      "드리프트 정정 — 위와 같은 자리.",
	"chain-merge":    "디프리케이트 — 합류는 gil merge 하나로 말한다.",
	"mcp":            "서버 자신을 띄우는 명령이다.",
	"help":           "표면의 목록 — MCP 에서는 툴 목록이 그 일을 한다.",
}

// appOnlyTools — **화면이 부르는 통로**. 모델의 목록에는 안 뜨고(visibility: app), 응답은
// 사람이 보는 카드 HTML 이다.
//
// 왜 표로 두나. 세션 앞머리(도착 고지·버전 문의)는 **에이전트에게 하는 말**이라, 카드로 가는
// 응답에 붙이면 사람 화면 한복판에 그 문장이 앉는다. 그래서 앞머리 미들웨어가 이 표를 보고
// 비켜선다. 등록 자리에 흩어 두면 한쪽만 낡으므로 표면을 아는 다른 두 표 옆에 둔다 —
// **시험이 소스의 visibility:["app"] 등록을 세어 이 표와 대조한다.**
var appOnlyTools = map[string]string{
	"gil_interview_submit": "사람이 카드 폼에 적은 답이 돌아오는 통로.",
	"gil_status_card":      "화면이 제 내용을 가져오는 통로.",
	"gil_prune_approve":    "사람이 카드에서 누른 삭제 승인.",
	"gil_prune_withdraw":   "사람이 카드에서 삭제 요청을 거둔다.",
}

// retiredCmds — **은퇴한 명령과 그 자리를 대신하는 것.**
//
// 왜 표로 남기나. 명령을 지우면 두 가지가 동시에 일어난다:
//
//	① 소스 곳곳의 안내가 **없는 것을 가리키기 시작한다.** 그런데 "없는 명령을 치라고 하나"를
//	   세는 시험은 `gil x -플래그` · `gil x <인자>` 꼴만 칠 수 있는 줄로 인정한다(영어 산문에서
//	   낱말을 세면 못 쓰게 되므로 좁힌 것이다). 그래서 `gil viewer open` 처럼 **서브명령이
//	   붙은 꼴**은 산문으로 보아 그냥 지나간다 — 실측으로 안내 31곳 중 29곳이 그렇게 샜다.
//	   여기 이름을 적으면 그 이름이 나오는 자리를 **꼴과 무관하게** 잡는다.
//	② 옛 문서를 보고 그 명령을 치는 사람이 "알 수 없는 명령"만 받는다. 도구가 자기가 만든
//	   상태에서 빠져나올 길을 자기가 줘야 한다(v3.58.1 이 chain-merge --resume 에서 세운 규칙).
//	   그래서 값은 **대신 무엇을 하면 되는지**다.
var retiredCmds = map[string]string{}

// humanOnly — 이 표면에서 **사람이 화면에서 누르는** 명령. 툴은 있지만 에이전트의 것이 아니다.
//
// 왜 세 번째 표가 필요한가. 두 표만 있을 때는 답이 둘뿐이었다 — "툴이 있다(에이전트가 쳐라)"
// 또는 "툴이 없다(사람이 터미널에서)". 그런데 카드에 버튼을 세우면서 **둘 다 아닌 것**이
// 생겼다: 툴은 실재하는데(카드가 부른다) 에이전트가 칠 것은 아니다.
//
//	· terminalOnly 에 두면 → "이 표면엔 툴이 없다" 가 **거짓말**이 된다.
//	· mcpSurface 에 두면 → 안내가 툴 이름을 주고, 에이전트가 사람의 판단을 대신 누른다.
//
// 그래서 안내는 **어디를 누르면 되는지**를 말한다. 가리키는 것이 실재하고(카드의 그 버튼),
// 에이전트에게 칠 것을 주지도 않는다.
var humanOnly = map[string]string{
	"prune-approve": "위에 뜬 카드의 [삭제를 승인한다] 버튼 — 사람이 누른다",
}

// surfaceCmd — 이 명령을 **지금 표면의 문법으로** 부른다.
//
// CLI 에서는 `gil intake`, MCP 에서는 `gil_intake 툴`. 새로 쓰는 안내는 이걸 쓴다 —
// 그러면 한 문장이 두 표면에서 각각 옳다.
func surfaceCmd(cmd string) string {
	if !mcpMode {
		return "gil " + cmd
	}
	if t, ok := mcpSurface[cmd]; ok {
		return t + " 툴"
	}
	if where, ok := humanOnly[cmd]; ok {
		return where
	}
	if why, ok := terminalOnly[cmd]; ok {
		return "`gil " + cmd + "` (이 표면엔 툴이 없다 — " + why + ")"
	}
	return "`gil " + cmd + "` (이 표면엔 툴이 없다 — 사람이 터미널에서)"
}

// surfaceCall — 명령과 **인자까지** 이 표면의 문법으로.
//
// surfaceCmd 만으로는 반쪽이다: 명령 이름을 옳게 불러 놓고 인자를 CLI 플래그로 적으면,
// 툴을 쥔 에이전트는 `--identity <파일>` 을 보고 있지도 않은 파일을 찾는다(그리고 없으니
// 하나 만들어 낸다). 두 표면은 인자를 다르게 받는다 — CLI 는 **파일 경로**를, MCP 는
// **내용 그 자체**를. 그 차이까지 말해야 안내가 실제로 도는 줄이 된다.
func surfaceCall(cmd, cliArgs, mcpArgs string) string {
	cli := strings.TrimRight("gil "+cmd+" "+cliArgs, " ")
	if !mcpMode {
		return cli
	}
	// 툴이 없는 명령은 **CLI 문법 그대로** 준다 — 그게 사람이 터미널에서 칠 줄이기 때문이다.
	// (여기서 툴 이름 흉내를 내면 인자가 통째로 사라진다: `gil viewer open` 이 `gil viewer`
	//  가 되어, 사람이 그대로 쳐도 아무 일이 안 일어난다.)
	if where, ok := humanOnly[cmd]; ok {
		return where
	}
	tool, ok := mcpSurface[cmd]
	if !ok {
		why, known := terminalOnly[cmd]
		if !known {
			why = "사람이 터미널에서"
		}
		return "`" + cli + "` (이 표면엔 툴이 없다 — " + why + ")"
	}
	if strings.TrimSpace(mcpArgs) == "" {
		return tool + " 툴"
	}
	return tool + " 툴 (" + mcpArgs + ")"
}

// mcpInstructions — 호스트가 initialize 에서 받는 "이 서버를 어떻게 쓰나".
//
// 왜 이 자리가 중요한가. 이건 **에이전트가 툴을 고르기 전에** 도착하는 유일한 글이다.
// 지금까지 비어 있었고(실측: instructions=None), 그래서 "gil 프로젝트 시작하자"는 말에
// 무엇을 먼저 불러야 하는지 아무도 말해 주지 않았다. 문서는 저장소 안에 있는데, 저장소를
// 아직 안 세운 자리에서는 그 문서를 읽을 수 없다 — 순환이다. 그 순환을 여기서 끊는다.
//
// 짧게 쓴다. 여기 긴 글을 넣으면 매 세션의 맥락을 먹고, 그러면 정작 읽혀야 할 한 줄이 묻힌다.
func mcpInstructions() string {
	return strings.Join([]string{
		"gil 은 사고의 역사를 git 커밋 그래프에 남긴다 — 가설을 세우고, 재고, 판정한 것을 순서대로.",
		"",
		"**새 프로젝트를 시작한다면(사람이 \"gil 프로젝트 시작하자\" 라고 하면) gil_start 를 불러라.**",
		"gil_start 는 온보딩의 다음 한 칸을 실제로 밟는다 — 세계를 세우고, 존재의 이름을 요구하고,",
		"사람에게 무엇을 하려는지 먼저 묻는다. **판단이 필요한 칸에서만 멈춘다**(이름·정체성은",
		"네가 정하는 것이라 도구가 채울 수 없다) — 그러니 준비된 것은 **한 번에 실어라**.",
		"보통 두 번이면 끝난다: ① 세계 ② 이름+정체성. 그 뒤는 사람이 답할 차례다.",
		"",
		"**`git init` 을 먼저 치지 마라** — gil_start 가 저장소까지 세운다. 먼저 치면 브랜치가",
		"제 자리에 안 서고, 그 git 이 중간에 죽으면 잠금 파일이 남아 시작 자체가 막힌다",
		"(실측: 그렇게 막힌 세션이 원인을 추측해 사람에게 엉뚱한 진단을 전했다).",
		"",
		"**이어받는 세션이라면 gil_handoff 를 먼저 불러라** — 어디까지 왔는지가 거기 있다.",
		"지금 어디이고 사람이 나설 자리인지는 gil_status 가 세 줄로 답한다.",
		"",
		"안내에 `gil <명령>` 으로 적힌 다음 수는 이 표면에서 **`gil_<명령>` 툴**이다",
		"(`gil chain-close` → `gil_chain_close`). 플래그는 툴 인자에 그대로 대응한다.",
		"툴이 없는 명령은 안내가 그 자리에서 없다고 말한다 — 지어내지 말고 사람에게 넘겨라.",
		"",
		"사람에게 물어야 하는 것(목적·성패 기준)을 대신 쓰지 마라. gil 이 그걸 문법으로 막는다.",
	}, "\n")
}

// surfaceUnknownCmds — 안내가 가리키는 명령 중 툴도 없고 터미널 전용 선언도 없는 것.
// 시험이 이걸 세고, 비어 있지 않으면 실패한다. (여기 걸리면 둘 중 하나를 해야 한다 —
// 툴을 세우거나, 왜 터미널 전용인지 적거나. 조용히 두는 선택지는 없다.)
func surfaceUnknownCmds(cmds []string) []string {
	var out []string
	for _, c := range cmds {
		if _, ok := mcpSurface[c]; ok {
			continue
		}
		if _, ok := terminalOnly[c]; ok {
			continue
		}
		if _, ok := humanOnly[c]; ok {
			continue
		}
		out = append(out, c)
	}
	sort.Strings(out)
	return out
}

// askHumanHere — **사람이 지금 답할 수 있는 자리**를 이 표면의 말로.
//
// 앞 커밋이 "사람에게 묻는 툴은 자기 화면을 함께 연다"를 세웠다(uiStatusMeta). 이건 그
// **짝**이다: 화면을 열어 놓고도 문구가 다른 화면을 가리키면 아무 소용이 없다.
//
// 실측(상현님, 2026-08-10): 카드가 떴는데 에이전트가 받은 줄은 "사람에게 **뷰어 폼**으로
// 답해 달라고 청하고…"였다. 뷰어는 이 표면에서 열 수 없으니(터미널 전용) 에이전트에게
// 남은 길은 대화뿐이었고, 그래서 이렇게 말했다 — *"뷰어 폼이 이 환경에선 안 떠서 여기서
// 여쭤봅니다."* 카드는 바로 그 호출로 떠 있었다. **열어 놓고 안 가리킨 것이다.**
func askHumanHere() string {
	if mcpMode {
		return "위에 뜬 카드의 인터뷰 폼"
	}
	return "관전 창의 📋 인터뷰 폼"
}

// askHumanLine — "사람에게 이렇게 청하라"의 한 줄. 청할 자리를 표면에 맞춰 부른다.
func askHumanLine() string {
	return "사람에게 " + askHumanHere() + "에 답해 달라고 지금 말로 청하라 — 답을 대신 지어내지 마라"
}
