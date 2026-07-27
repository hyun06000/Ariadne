// MCP Apps (SEP-1865) — 그래프 뷰어를 호스트 안에 띄운다 (단계 C).
//
// 왜. 뷰어는 지금까지 localhost 서버였다. 그래서 사람은 "127.0.0.1:8790" 이라는 날 주소를
// 받아들고 뭔지 몰라 넘어갔고(윈도우 실사용), 포트가 충돌하면 시스템 브라우저로 새고, Claude
// Desktop 처럼 샌드박스 안에서 도는 호스트에서는 아예 못 열기도 했다. MCP Apps 는 이 마찰을
// 통째로 없앤다 — 서버가 ui:// 리소스로 HTML 을 내주면 호스트가 자기 안의 샌드박스 iframe 에
// 직접 렌더한다. 주소도, 포트도, 브라우저도 없다.
//
// 규범(SEP-1865, Final):
//   - UI 리소스는 ui:// 스킴, mimeType 은 text/html;profile=mcp-app.
//   - 툴은 _meta.ui.resourceUri 로 자기 UI 를 가리킨다.
//   - 서버는 initialize 에서 확장 io.modelcontextprotocol/ui 를 선언한다.
//   - iframe↔호스트는 postMessage 위의 JSON-RPC(ui/initialize 핸드셰이크 등).
//
// 신선도에 대한 정직성. gil 의 체인 그래프 SVG 레이아웃은 Go 가 그린다(chainLayout). 그래서
// "빈 껍데기 + 데이터 주입"으로 쪼개려면 레이아웃 로직을 JS 로 이중화해야 하는데, 그 이중화가
// 바로 나중에 어긋나는 종류의 빚이다. 그래서 여기서는 리소스를 **읽는 시점에 통째로 렌더**한다
// (읽는 순간의 데이터는 언제나 최신). 대신 호스트가 템플릿을 캐시해 낡은 화면이 남을 수 있으므로,
// 페이지가 tool-result 알림으로 최신 팁 서명을 받아 자기 것과 다르면 **낡았다고 스스로 밝힌다**.
// 살아있는 척하지 않는다 — 낡음을 숨기는 화면이 없는 화면보다 나쁘다.
package main

import (
	"context"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const (
	uiGraphURI  = "ui://gil/graph"
	uiGraphMIME = "text/html;profile=mcp-app"
	uiExtension = "io.modelcontextprotocol/ui"
)

// uiCapabilities — initialize 에서 내보낼 확장 선언. MCP Apps 는 옵트인 확장이라
// 이걸 선언해야 호스트가 ui:// 리소스를 렌더한다.
func uiCapabilities() *mcp.ServerCapabilities {
	caps := &mcp.ServerCapabilities{Logging: &mcp.LoggingCapabilities{}}
	caps.AddExtension(uiExtension, map[string]any{
		"mimeTypes": []string{uiGraphMIME},
	})
	return caps
}

func registerGilUI(s *mcp.Server) {
	s.AddResource(&mcp.Resource{
		URI:      uiGraphURI,
		Name:     "gil-graph",
		Title:    "gil 그래프 관전",
		MIMEType: uiGraphMIME,
		Description: "사고 그래프(체인>사이클>스텝)를 호스트 안에서 본다. 읽는 시점의 커밋 그래프를 " +
			"통째로 렌더한 자기완결 HTML.",
	}, func(ctx context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
		var html string
		if _, err := runGil(func() { html = renderHTML(buildGraph(), true) }); err != nil {
			return nil, err
		}
		return &mcp.ReadResourceResult{Contents: []*mcp.ResourceContents{{
			URI:      uiGraphURI,
			MIMEType: uiGraphMIME,
			Text:     injectUIBridge(html, tipSignature()),
		}}}, nil
	})

	mcp.AddTool(s, &mcp.Tool{
		Name: "gil_graph",
		Description: "사고 그래프를 호스트 화면에 띄운다(체인>사이클>스텝 관전 뷰). 사람이 " +
			"'그래프 보여줘'라고 하거나, 지금까지의 사고 흐름을 눈으로 확인해야 할 때 부른다.",
		Meta: mcp.Meta{"ui": map[string]any{
			"resourceUri": uiGraphURI,
			"visibility":  []string{"model", "app"},
		}},
	}, func(ctx context.Context, req *mcp.CallToolRequest, in inEmpty) (*mcp.CallToolResult, any, error) {
		// 툴 결과는 두 독자를 갖는다: 모델(텍스트 요약)과 앱(팁 서명 → 낡음 감지).
		summary, err := runGil(func() { cmdLog([]string{"--depth", "chain"}) })
		if err != nil {
			return nil, nil, err
		}
		sig := tipSignature()
		return &mcp.CallToolResult{
			Content:           []mcp.Content{&mcp.TextContent{Text: strings.TrimSpace(summary)}},
			StructuredContent: map[string]any{"tipSignature": sig},
		}, nil, nil
	})
}

// injectUIBridge — 정적 HTML 에 MCP Apps 브리지를 얹는다.
//
// 하는 일 셋. (1) ui/initialize 핸드셰이크 — 호스트에게 "나 떴다"고 알린다. (2) 크기 보고 —
// 호스트가 iframe 높이를 맞추게. (3) 낡음 감지 — 호스트가 보내는 tool-result 의 팁 서명이 이
// 화면을 그릴 때의 서명과 다르면, 그래프가 그 뒤로 움직였다는 뜻이니 배너로 밝힌다.
func injectUIBridge(html, sig string) string {
	bridge := `<div id="gil-stale-banner" hidden>이 화면은 그 뒤 움직인 그래프를 아직 못 봤다 —
최신으로 보려면 gil_graph 를 다시 불러라.</div>
<style>
#gil-stale-banner{position:sticky;bottom:0;margin:12px 0 0;padding:10px 14px;border-radius:10px;
  background:#3a2a12;color:#ffd79a;border:1px solid #7a5a24;font-size:13px;line-height:1.5}
</style>
<script>
(function(){
  var MY_SIG=` + jsString(sig) + `;
  var id=0, host=window.parent;
  if(host===window) return;              // iframe 이 아니면 브리지는 무의미
  function send(msg){ host.postMessage(Object.assign({jsonrpc:"2.0"},msg),"*"); }
  function notify(method,params){ send({method:method,params:params||{}}); }

  // (1) 핸드셰이크. 호스트가 hostCapabilities 를 돌려준다.
  send({id:++id,method:"ui/initialize",params:{
    appCapabilities:{}, clientInfo:{name:"gil-graph",version:` + jsString(gilVersion) + `}}});

  // (2) 크기 보고 — 내용이 바뀌면(카드 펼침 등) 다시 알린다.
  function reportSize(){
    notify("ui/notifications/size-changed",{height:document.documentElement.scrollHeight});
  }
  window.addEventListener("load",reportSize);
  if(window.ResizeObserver) new ResizeObserver(reportSize).observe(document.documentElement);

  // (3) 낡음 감지. 호스트가 gil_graph 결과를 넘겨줄 때 팁 서명을 비교한다.
  window.addEventListener("message",function(e){
    var m=e.data; if(!m||m.method!=="ui/notifications/tool-result") return;
    var sc=(m.params&&m.params.result&&m.params.result.structuredContent)||{};
    if(sc.tipSignature && sc.tipSignature!==MY_SIG){
      var b=document.getElementById("gil-stale-banner"); if(b){b.hidden=false; reportSize();}
    }
  });
})();
</script>`
	// </body> 직전에 끼운다 — 본문 렌더를 건드리지 않게.
	if i := strings.LastIndex(html, "</body>"); i >= 0 {
		return html[:i] + bridge + html[i:]
	}
	return html + bridge
}

// jsString — 문자열을 JS 리터럴로 안전하게. 팁 서명엔 개행이 들어가고, "</script>" 가
// 스크립트를 조기 종료시킬 수 있으므로 <, > 까지 유니코드 이스케이프한다.
func jsString(str string) string {
	var b strings.Builder
	b.WriteByte('"')
	for _, r := range str {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		case '<':
			b.WriteString(`\u003c`)
		case '>':
			b.WriteString(`\u003e`)
		case '&':
			b.WriteString(`\u0026`)
		default:
			b.WriteRune(r)
		}
	}
	b.WriteByte('"')
	return b.String()
}
