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
	"crypto/sha256"
	"encoding/hex"
	"net/url"
	"os"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// tipSignatureDigest — 팁 서명을 **짧은 지문 하나로** 접는다. MCP 경계 전용.
//
// 왜. tipSignature() 는 브랜치 하나하나와 로컬 대기 상태를 줄줄이 잇는다. 뷰어 안에서는
// 그래도 됐다 — 브라우저가 이전 값과 문자열 비교만 하고 사람은 그걸 볼 일이 없다. 그런데
// MCP 로 나가는 순간 그 문자열은 **대화에 실린다.** 실측(AIL): 브랜치 130여 개와 seen 집합이
// 통째로 나가 4KB 가 넘었고, 사람이 툴 응답으로 본 것이 그 날 데이터 전부였다. 화면에도
// 문맥에도 잡음이고, 호출마다 반복된다.
//
// 서명은 **같은지 다른지**만 답하면 된다. 내용은 필요 없다. 그러니 접는다 — 접힌 값도
// 같은 판정을 내리고(같은 입력 → 같은 지문), 사람이 읽을 것이 아니라는 게 눈에 보인다.
func tipSignatureDigest() string {
	sum := sha256.Sum256([]byte(tipSignature()))
	return hex.EncodeToString(sum[:])[:16]
}

// uiResourceMeta — 리소스 수준 `_meta.ui`(규범 SEP-1865).
//
// 우리 화면은 자기완결이라 바깥을 하나도 안 부른다 — 스크립트·스타일은 인라인이고, 그림은
// `data:` 만 싣는다(markdown.go 의 mdImage 가 바깥 주소를 거부하고 그 사실을 화면에 적는다).
// 그 사실을 **빈 목록으로 명시**한다: 선언이 없는 것과 "필요 없다"고 선언한 것은 다르다.
//
// **키 이름은 규범이 정한 그대로여야 한다.** 우리는 오래 `connect-src`·`resource-src` 라고
// 적어 뒀는데(CSP 지시어 이름을 그대로 옮긴 것이다), 규범의 필드는 `connectDomains`·
// `resourceDomains`·`frameDomains`·`baseUriDomains` 다. 호스트는 모르는 키를 **무시하고
// 기본 CSP 를 건다** — 즉 우리 선언은 한 글자도 효과가 없었다. 화면이 뜬 것은 기본 CSP 가
// 인라인 스크립트를 허용하기 때문이지 우리가 선언해서가 아니다. 안 도는 선언은 선언이 아니다.
func uiResourceMeta() mcp.Meta {
	return mcp.Meta{"ui": map[string]any{
		"csp": map[string]any{
			"connectDomains":  []string{},
			"resourceDomains": []string{},
			"frameDomains":    []string{},
			"baseUriDomains":  []string{},
		},
		"prefersBorder": false,
	}}
}

// mcpUIRepo — **툴 호출이 알려준 저장소를 서버가 기억한다.**
//
// 왜. resources/read 는 인자를 못 싣는다. 그래서 지금까지 툴이 저장소를 URI 에 박아 돌려줬고
// (ui://gil/status/%2FUsers%2F…), 호스트는 그걸 읽어 성공했지만 **화면엔 아무것도 안 떴다.**
// 유력한 이유: 렌더할 UI 리소스를 목록(resources/list)에서 찾을 때 그 변형 URI 는 없다.
// 그러니 툴은 **선언된 URI 그대로** 가리키고, 저장소는 이 프로세스가 기억한다 — 한 세션의
// 서버는 한 호스트만 상대하므로 마지막 호출의 자리가 곧 사람이 보고 있는 자리다.
var mcpUIRepo string

// rememberUIRepo — 지금 선 자리를 기억한다(툴 핸들러가 저장소를 정한 직후에 부른다).
func rememberUIRepo() {
	if wd, err := os.Getwd(); err == nil {
		mcpUIRepo = wd
	}
}

// uiRepoFor — 이 읽기가 볼 저장소. URI 에 실려 왔으면 그것, 아니면 기억한 자리.
func uiRepoFor(uri string) string {
	if r := repoFromURI(uri); r != "" {
		return r
	}
	if r := repoFromStatusURI(uri); r != "" {
		return r
	}
	return mcpUIRepo
}

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
		Meta:     uiResourceMeta(),
		URI:      uiGraphURI,
		Name:     "gil-graph",
		Title:    "gil 그래프 관전",
		MIMEType: uiGraphMIME,
		Description: "사고 그래프(체인>사이클>스텝)를 호스트 안에서 본다. 읽는 시점의 커밋 그래프를 " +
			"통째로 렌더한 자기완결 HTML.",
	}, func(ctx context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
		return renderUIResource(uiGraphURI, uiRepoFor(uiGraphURI))
	})

	// 저장소를 **URI 에 실어** 읽는 길. resources/read 는 툴과 달리 인자를 못 싣는다 —
	// 그래서 호스트가 roots 를 안 주면(Claude Desktop) 이 읽기는 프로세스가 뜬 자리(`/`)에서
	// 돌고 git 이 죽는다. 실측 로그가 그대로다:
	//   resources/read → 거부: git log 실패(레포 경로·gil 그래프 확인) — exit status 128
	// 사람 화면에는 아무것도 안 뜨고, 왜 안 뜨는지도 안 보인다. 그래서 툴이 결과에 **이 호출의
	// 저장소가 박힌 URI** 를 실어 주고(_meta.ui.resourceUri), 호스트는 그걸 읽는다.
	s.AddResourceTemplate(&mcp.ResourceTemplate{
		Meta:        uiResourceMeta(),
		URITemplate: uiGraphURI + "/{repo}",
		Name:        "gil-graph-for-repo",
		Title:       "gil 그래프 관전 (저장소 지정)",
		MIMEType:    uiGraphMIME,
		Description: "ui://gil/graph?repo=<절대경로> — 호스트가 열린 폴더를 안 알려줄 때 쓰는 길.",
	}, func(ctx context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
		uri := ""
		if req.Params != nil {
			uri = req.Params.URI
		}
		return renderUIResource(uri, uiRepoFor(uri))
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
		// 저장소를 실어 왔으면 먼저 그리로 — 그래프는 "어느 저장소의 것이냐"가 전부다.
		summary, err := runGil(func() {
			adoptCallRepo(in)
			requireRepoHere()
			rememberUIRepo() // 이 자리를 기억한다 — 뒤따르는 resources/read 가 쓴다
			cmdLog([]string{"--depth", "chain"})
		})
		if err != nil {
			return nil, nil, err
		}
		sig := tipSignatureDigest()
		// **이 호출의 저장소를 URI 에 박아 돌려준다.** 안 그러면 호스트의 resources/read 는
		// 어느 저장소인지 모른 채 돌고, roots 를 안 주는 호스트에서는 반드시 실패한다.
		res := &mcp.CallToolResult{
			Content:           []mcp.Content{&mcp.TextContent{Text: strings.TrimSpace(summary)}},
			StructuredContent: map[string]any{"tipSignature": sig},
		}
		// **선언된 URI 그대로.** 저장소는 URI 가 아니라 서버의 기억이 답한다(위 mcpUIRepo).
		res.Meta = mcp.Meta{"ui": map[string]any{
			"resourceUri": uiGraphURI,
			"visibility":  []string{"model", "app"},
		}}
		return res, nil, nil
	})
}

// injectUIBridge — 정적 HTML 에 MCP Apps 브리지를 얹는다.
//
// 하는 일 셋. (1) ui/initialize 핸드셰이크 — 호스트에게 "나 떴다"고 알린다. (2) 크기 보고 —
// 호스트가 iframe 높이를 맞추게. (3) 낡음 감지 — 호스트가 보내는 tool-result 의 팁 서명이 이
// 화면을 그릴 때의 서명과 다르면, 그래프가 그 뒤로 움직였다는 뜻이니 배너로 밝힌다.
func injectUIBridge(html, sig string) string {
	probeJS := "false"
	if os.Getenv("GIL_UI_PROBE") == "1" {
		probeJS = "true"
	}
	bridge := `<div id="gil-stale-banner" hidden>이 화면은 그 뒤 움직인 그래프를 아직 못 봤다 —
최신으로 보려면 gil_graph 를 다시 불러라.</div>
<div id="gil-fs-bar" hidden><button type="button" id="gil-fs-btn">크게 본다</button><span
 id="gil-fs-note"></span></div>
<style>
#gil-stale-banner{position:sticky;bottom:0;margin:12px 0 0;padding:10px 14px;border-radius:10px;
  background:#3a2a12;color:#ffd79a;border:1px solid #7a5a24;font-size:13px;line-height:1.5}
#gil-fs-bar{position:fixed;top:10px;right:12px;z-index:9999;display:flex;gap:8px;
  align-items:center;font:13px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
#gil-fs-btn{border-radius:7px;padding:5px 14px;font:inherit;cursor:pointer;
  border:1px solid #7a5a24;background:#3a2a12;color:#ffd79a}
#gil-fs-note{color:#ffd79a}
</style>
<script>
(function(){
  var MY_SIG=` + jsString(sig) + `, PROBE=` + probeJS + `;
  var id=0, host=window.parent, pending={};
  if(host===window) return;              // iframe 이 아니면 브리지는 무의미
  function send(msg){ host.postMessage(Object.assign({jsonrpc:"2.0"},msg),"*"); }
  function notify(method,params){ send({method:method,params:params||{}}); }

  // (1) 핸드셰이크. **호스트가 요구하는 이름으로**(protocolVersion·appInfo) — 옛 이름
  // {appCapabilities, clientInfo} 은 -32603 으로 거부됐고, 거부되면 호스트는 이 프레임을
  // 화면에 세우지 않는다(실측 probe).
  send({id:++id,method:"ui/initialize",params:{
    protocolVersion:"2026-01-26",
    appInfo:{name:"gil-graph",version:` + jsString(gilVersion) + `},
    clientInfo:{name:"gil-graph",version:` + jsString(gilVersion) + `},
    capabilities:{}, appCapabilities:{availableDisplayModes:["inline","fullscreen"]}}});
  // (전체맵은 pip 를 선언하지 않는다 — 곁에 두고 보는 그림이 아니다.)
  // 응답을 받으면 **initialized** 를 보낸다 — 규범이 "이 알림 전에는 호스트가 뷰에 아무것도
  // 보내지 않는다"고 정한 관문이다(그래서 이걸 빼면 화면이 서지 않는다).
  window.addEventListener("message",function(e){
    var m=e.data; if(!m) return;
    if(m.id===1 && m.result && m.result.protocolVersion){
      notify("ui/notifications/initialized",{}); reportSize();
      askBig(m.result);
      return;
    }
    // 우리가 보낸 요청의 답은 그 자리에서 받는다 — 전에는 id===1 말고는 아무것도 안 들어서
    // 표시모드 요청의 답이 어디에도 안 적혔다(청했는지만 알고 결과는 몰랐다).
    if(m.id!==undefined && pending[m.id]){ var cb=pending[m.id]; delete pending[m.id];
      cb(m.result,m.error); return; }
    // 렌더 뒤에 호스트가 모드를 바꿀 수 있다(규범: host-context-changed).
    if(m.method==="ui/notifications/host-context-changed"){
      var hc=m.params||{};
      if(hc.availableDisplayModes) MODES=hc.availableDisplayModes;
      if(hc.displayMode) MODE=hc.displayMode;
      syncBig();
    }
  });
  document.addEventListener("click",function(ev){
    if(ev.target && ev.target.id==="gil-fs-btn"){ ev.preventDefault(); toggleBig(); }
  });

  // (1b) **이 그림은 크게 봐야 하는 것이다.** 상태 카드와 일이 다르다: 상태 카드는 곁에 두고
  // 일하는 동안 계속 보는 것이고, 전체맵은 한 번 크게 펼쳐 보고 닫는 것이다. 빈 저장소에서도
  // 226KB 짜리 그림이라, 인라인 칸에 눌러 넣으면 사람은 스크롤로 그것을 더듬게 된다.
  //
  // **그런데 크게 여는 것은 사람이 정한다.** 전에는 여기서 **자동으로** 청했다 — 정본
  // (ext-apps docs/patterns.md · add-app-to-server)은 반대다: 목록에 fullscreen 이 있으면
  // **버튼을 보이고**, 사람이 누르면 그때 청한다. 자동으로만 청해 온 탓에 이 저장소는
  // "호스트가 안 준다"와 "제스처가 없어서 안 준다"를 아직 못 갈랐다.
  //
  // 언제 버튼을 보이나 — 상태 카드와 같은 규칙(mcp_ui_status.go 의 fsState 주석):
  //   · 목록에 있다 → 보인다(정본)  · 목록을 안 줬다 → 모르는 것이라 보인다
  //   · 목록을 줬는데 없다 → 규범이 청하지 말라 하므로 안 보인다(계기 GIL_UI_PROBE=1 일 때만).
  var MODES=[], MODE="";
  function askBig(res){
    try{
      var hc=(res&&res.hostContext)||{};
      MODES=hc.availableDisplayModes||[]; MODE=hc.displayMode||"";
      syncBig();
    }catch(_){}
  }
  function syncBig(){
    var el=document.getElementById("gil-fs-bar"); if(!el) return;
    var declared=MODES.indexOf("fullscreen")>=0, unknown=!MODES.length;
    if(!(declared||unknown||PROBE)){ el.hidden=true; return; }
    var big=(MODE==="fullscreen");
    el.hidden=false;
    el.firstChild.textContent=big?"작게 되돌린다":"크게 본다";
  }
  function toggleBig(){
    var want=(MODE==="fullscreen")?"inline":"fullscreen";
    var i=++id;
    pending[i]=function(res,err){
      if(!err && res && res.mode){ MODE=res.mode; syncBig(); }
      else { var el=document.getElementById("gil-fs-note");
        if(el){ el.textContent=err?("호스트가 거절했다: "+String((err&&(err.message||err.code))||err))
                                  :"호스트가 답에 모드를 안 실었다"; } }
    };
    send({id:i,method:"ui/request-display-mode",params:{mode:want}});
  }

  // (2) 크기 보고 — 내용이 바뀌면(카드 펼침 등) 다시 알린다.
  function reportSize(){
    notify("ui/notifications/size-changed",{width:document.documentElement.scrollWidth,
      height:document.documentElement.scrollHeight});
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

// repoFromURI — ui://gil/graph?repo=<절대경로> 에서 저장소를 꺼낸다.
func repoFromURI(uri string) string {
	rest := strings.TrimPrefix(uri, uiGraphURI+"/")
	if rest == uri {
		return ""
	}
	p, err := url.PathUnescape(rest)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(p)
}

// renderUIResource — 위젯 HTML 을 만든다. **실패해도 에러를 돌려주지 않는다.**
//
// 왜. 리소스 읽기가 에러로 끝나면 호스트는 아무것도 안 그리고, 사람은 빈 자리를 본다 —
// 무엇이 잘못됐는지도, 무엇을 하면 되는지도 화면에 없다(실측: Claude Desktop 에서 위젯이
// 끝내 안 떴고, 이유는 서버 로그를 뒤져야 나왔다). **없는 화면보다 나쁜 것은 이유 없이
// 빈 화면이다.** 그러니 못 그릴 때는 못 그린 이유를 그린다.
func renderUIResource(uri, repo string) (*mcp.ReadResourceResult, error) {
	if uri == "" {
		uri = uiGraphURI
	}
	page := func(html string) (*mcp.ReadResourceResult, error) {
		return &mcp.ReadResourceResult{Contents: []*mcp.ResourceContents{{
			URI: uri, MIMEType: uiGraphMIME, Text: html,
		}}}, nil
	}
	if repo != "" {
		if _, err := gitTryIn(repo, "rev-parse", "--git-dir"); err != nil {
			return page(uiProblemPage("이 경로는 git 저장소가 아니다", repo,
				"사람이 보고 있는 폴더의 최상위(.git 이 있는 자리)를 repo 인자에 실어 gil_graph 를 다시 불러라."))
		}
		if os.Chdir(repo) != nil {
			return page(uiProblemPage("저장소로 이동하지 못했다", repo, "경로 권한을 확인하라."))
		}
		stopGitCache()
	}
	if !gitOK("rev-parse", "--git-dir") {
		wd, _ := os.Getwd()
		return page(uiProblemPage("어느 저장소를 그릴지 모른다", wd,
			"이 창은 인자를 실을 수 없는 자리(resources/read)에서 열렸고, 호스트가 열린 폴더를 "+
				"알려주지 않았다(MCP roots 미지원). gil_graph 를 repo 인자와 함께 부르면 그 저장소가 그려진다."))
	}
	var html string
	if _, err := runGil(func() { html = renderHTML(buildGraph(), true) }); err != nil {
		return page(uiProblemPage("그래프를 그리지 못했다", err.Error(),
			"gil fsck 로 그래프 상태를 확인하라."))
	}
	return page(injectUIBridge(html, tipSignatureDigest()))
}

// uiProblemPage — 못 그린 이유를 **화면에** 적는다. 자기완결 HTML(외부 자원 0).
func uiProblemPage(title, detail, next string) string {
	esc := func(s string) string {
		r := strings.NewReplacer("&", "\u0026amp;", "<", "\u0026lt;", ">", "\u0026gt;")
		return r.Replace(s)
	}
	return `<!doctype html><meta charset="utf-8"><body style="margin:0;padding:20px;` +
		`font:14px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;` +
		`background:#1b1b1f;color:#e6e6ea">` +
		`<div style="max-width:640px;border:1px solid #7a5a24;background:#3a2a12;` +
		`border-radius:10px;padding:16px 18px">` +
		`<div style="font-size:15px;font-weight:600;color:#ffd79a">gil 그래프 — ` + esc(title) + `</div>` +
		`<div style="margin-top:8px;font-family:ui-monospace,Menlo,monospace;font-size:12px;` +
		`color:#c9c9d1;word-break:break-all">` + esc(detail) + `</div>` +
		`<div style="margin-top:12px">` + esc(next) + `</div></div></body>`
}
