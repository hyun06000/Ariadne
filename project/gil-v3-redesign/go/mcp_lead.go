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
