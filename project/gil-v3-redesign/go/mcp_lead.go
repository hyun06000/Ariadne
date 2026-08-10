// mcp_lead.go — **세션 앞머리는 한 자리에서 선다** (2026-08-10).
//
// 무엇이 문제였나. 이 표면에는 툴을 등록하는 자리가 여섯이다:
//
//	registerGilTools · registerStartTools · registerGilUI · registerGilStatusUI
//	registerInterviewSubmitTool · registerGilCardTool
//
// 그런데 세션이 알아야 할 앞머리를 그중 **두 곳에만** 붙여 놨었다. 결과:
//
//	· **⚡ 도착 고지(#77)가 MCP 세션에 한 번도 안 섰다.** 유일한 호출자가 main.go 의 부팅
//	  자리인데 MCP 는 cmd* 를 직접 부르므로 그 자리를 지나지 않는다. 사람이 카드에서 답을
//	  제출하거나 pending 을 승인해도 에이전트는 그 사실을 못 받았다 — 그러면 사람이 다시
//	  말을 걸어야 하고, 그건 사람에게 두 번 일을 시키는 것이다.
//	· **버전 문의(v3.48.0)도 반만 닿았다.** gil_status·gil_graph 로만 도는 세션은 통째로
//	  비껴갔다 — 낡은 gil 을 쥔 줄 모르고 한 세션을 다 보낸다.
//
// 이건 새 병이 아니다. mcp.go 의 옛 주석이 "MCP 는 main 의 부팅 자리를 지나지 않는다"고
// 정확히 적어 놓고 **버전 문의만** 다시 붙였다 — 그 옆줄에서 도착 고지가 빠진 것을 아무도
// 안 봤다. 한쪽을 고치고 그 짝을 안 본 자리가 하나 더 있었던 것이다.
//
// 그래서 붙이는 자리를 **열거하지 않는다.** 수신 미들웨어 하나가 모든 tools/call 응답을
// 지나가므로, 등록 자리가 늘어도 안 샌다(열거는 늘 뒤늦다 — v3.58.3 이 값을 치른 규칙).
package main

import (
	"context"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// installLeadMiddleware — 모든 툴 응답의 맨 앞에 세션이 알아야 할 것을 세운다.
func installLeadMiddleware(s *mcp.Server) {
	s.AddReceivingMiddleware(func(next mcp.MethodHandler) mcp.MethodHandler {
		return func(ctx context.Context, method string, req mcp.Request) (mcp.Result, error) {
			res, err := next(ctx, method, req)
			if method != "tools/call" || err != nil {
				return res, err
			}
			call, ok := req.(*mcp.CallToolRequest)
			if !ok || call == nil || call.Params == nil {
				return res, err
			}
			out, ok := res.(*mcp.CallToolResult)
			if !ok || out == nil {
				return res, err
			}
			if lead := mcpLead(call.Params.Name); lead != "" {
				prependText(out, lead)
			}
			holdOneScreen(out, call.Params.Name)
			mirrorTextIntoStructured(out)
			return out, err
		}
	})
}

// mcpLead — 이 툴 응답 앞에 설 글. 없으면 "".
//
// **앞머리를 계산하는 자리는 핸들러가 끝난 뒤다.** 그래야 adoptCallRepo 가 옮겨 놓은
// 저장소에서 읽는다 — 앞에서 계산하면 남의 저장소의 도착 고지를 낸다.
func mcpLead(tool string) string {
	// 화면이 부르는 통로는 비켜선다. 이 글은 **에이전트에게 하는 말**이라, 카드로 가는
	// 응답에 붙이면 사람이 보는 화면 한복판에 그 문장이 앉는다(surface.go 의 appOnlyTools).
	if _, isApp := appOnlyTools[tool]; isApp {
		return ""
	}
	var b strings.Builder
	// 도착이 먼저다 — **사람이 이미 자기 몫을 다했다는 사실**이 이 세션의 다음 수를 바꾼다.
	// 버전은 그다음(handoff 는 제 현행성 배너가 이미 묻는다).
	b.WriteString(arrivalBanner())
	if tool != "gil_handoff" {
		b.WriteString(versionAskBanner())
	}
	return b.String()
}


// prependText — 결과의 **첫 텍스트 칸** 앞에 글을 얹는다. 텍스트 칸이 없으면 하나 만든다.
//
// 카드(HTML)를 담은 칸에는 안 얹는다 — 위에서 앱 전용 툴을 걸렀지만, 평범한 툴이 카드를
// 함께 낼 수도 있으므로 여기서도 본다. 화면에 들어갈 글과 에이전트가 읽을 글은 다르다.
func prependText(res *mcp.CallToolResult, lead string) {
	for i, c := range res.Content {
		t, ok := c.(*mcp.TextContent)
		if !ok || strings.HasPrefix(strings.TrimSpace(t.Text), "<div") {
			continue
		}
		res.Content[i] = &mcp.TextContent{Text: lead + t.Text}
		return
	}
	res.Content = append([]mcp.Content{&mcp.TextContent{Text: lead}}, res.Content...)
}

// mirrorTextIntoStructured — 모델에게 가는 글을 structuredContent 에도 실어 둔다.
//
// **어느 칸이 모델에게 갈지는 호스트가 정한다 — 우리는 못 고른다.** 실측(2026-08-10,
// Claude Code Desktop): 이 호스트는 structuredContent 가 있으면 **그것만** 모델에게 주고
// Content 를 버린다. gil_status 를 부른 에이전트가 받은 것은 `{"tipSignature":"…"}` 한 줄이
// 전부였고, 상태 줄도·표면을 말하는 줄도·바로 위에서 얹은 ⚡ 도착 고지도 버전 문의도 그
// 자리에서 통째로 사라졌다. **이 미들웨어가 존재하는 이유가 그 호스트에서 무효였다.**
// 오류는 없었다 — 같은 세션의 gil_log 는 본문이 그대로 왔다(그쪽엔 이 칸이 없다). 그러니
// 빈 것이 아니라 **가려진** 것이고, 가려진 것은 아무도 못 본다.
//
// 그래서 하나를 고르지 않는다: 둘 다 사실이게 한다. 그리고 **붙이는 자리를 열거하지
// 않는다** — 이 미들웨어가 모든 tools/call 을 지나므로 툴이 늘어도 안 샌다(v3.58.3 이
// 값을 치른 규칙).
//
// 지키는 것 둘:
//   - **없던 칸은 만들지 않는다.** structuredContent 가 없는 결과에 이 칸을 새로 달면 그
//     순간 이 호스트가 Content 를 버리기 시작한다 — 고치려던 병을 우리가 만든다.
//   - **카드(HTML)는 안 싣는다.** 그건 화면의 몸이지 모델에게 하는 말이 아니다.
func mirrorTextIntoStructured(res *mcp.CallToolResult) {
	sc, ok := res.StructuredContent.(map[string]any)
	if !ok || sc == nil {
		return
	}
	var b strings.Builder
	for _, c := range res.Content {
		t, ok := c.(*mcp.TextContent)
		if !ok || strings.HasPrefix(strings.TrimSpace(t.Text), "<div") {
			continue
		}
		if b.Len() > 0 {
			b.WriteString("\n")
		}
		b.WriteString(t.Text)
	}
	if b.Len() == 0 {
		return
	}
	sc["text"] = b.String()
}

// holdOneScreen — **사람 앞에 시작하는 화면은 한 장만 선다.**
//
// 실사용 두 번(상현님). 처음엔 gil_start 를 두 번 불러서 두 장이 떴고, 그건 gil_start 안에서
// 막았다. 그런데 또 두 장이 떴다 — 이번엔 **다른 툴**이 열었다. 화면을 여는 것은 결과에 실린
// `_meta.ui.resourceUri` 하나뿐이고, 그걸 다는 툴이 여럿이기 때문이다(gil_status·gil_start·
// gil_intake·gil_interview…). 호스트는 그 표식이 달린 툴 호출마다 카드를 한 장씩 그린다.
//
// **막는 자리를 툴마다 두면 하나 늘 때 또 샌다** — 이 저장소가 세션 앞머리에서 이미 치른 값이다.
// 그래서 나가는 모든 결과가 지나는 이 한 자리에서 판정한다: 시작하는 화면이 사람의 손을
// 기다리는 동안에는, 그 화면을 연 호출 말고는 아무도 새 카드를 열지 않는다.
//
// 왜 이게 UX 문제인가. 같은 질문을 하는 카드가 둘 서면 어디에 적어야 할지 알 수 없고,
// **초안은 화면마다 따로 살아서** 한쪽에 적은 것은 다른 쪽이 모른다. 사람이 적다가 다른
// 카드를 보면 자기가 쓴 것이 사라진 것처럼 보인다.
func holdOneScreen(out *mcp.CallToolResult, tool string) {
	if out == nil || out.Meta == nil {
		return
	}
	ui, ok := out.Meta["ui"].(map[string]any)
	if !ok {
		return
	}
	if _, has := ui["resourceUri"]; !has {
		return
	}
	// 앱 전용 통로는 건드리지 않는다 — 그건 화면이 자기 내용을 가져오는 길이지 새 화면이 아니다.
	if _, isApp := appOnlyTools[tool]; isApp {
		return
	}
	// **이 규칙은 시작하는 국면에만 산다.** 평소에는 gil_status 를 부를 때마다 카드가 서는
	// 것이 맞다 — 그게 이 표면의 모양이다. 막는 것은 "사람이 아직 안 누른 시작 화면"뿐이다.
	if !hostDeclaresUI || !startNeedsPlace() {
		startScreenOpen = false
		return
	}
	// **여는 쪽과 막는 쪽이 한 자리에 있어야 한다.** 처음엔 핸들러가 플래그를 세우고 여기서
	// 막았더니 **첫 장까지 막혔다**(핸들러가 먼저 돌기 때문이다). 지나가는 것을 세는 자리와
	// 세운 값을 읽는 자리가 갈리면 늘 이런 순서 사고가 난다.
	if !startScreenOpen {
		startScreenOpen = true // 이 호출이 그 화면을 연다
		return
	}
	next := map[string]any{}
	for k, v := range ui {
		if k == "resourceUri" {
			continue
		}
		next[k] = v
	}
	out.Meta["ui"] = next
	prependText(out, "(시작하는 화면이 이미 떠 있어 새 카드를 열지 않았다 — "+
		"사람이 거기서 이름을 적고 [여기에 시작한다] 를 누를 차례다.)\n\n")
}
