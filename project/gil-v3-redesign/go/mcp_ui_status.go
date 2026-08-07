// mcp_ui_status.go — 상태 카드 위젯. **제로에서 새로 짓는다** (상현님).
//
// 왜 뷰어 HTML 을 재활용하지 않나. 그 화면은 "다 끝난 뒤 전체를 훑는" 물건이라 전체맵·
// 체인그래프·사이클그래프·스텝디테일을 다 담는다. 실측: 렌더된 HTML 이 **1,611,910 바이트**
// 였다. 샌드박스 iframe 에 1.6MB 를 미는 것은 호스트가 조용히 거절할 만한 크기고, 위젯이
// 끝내 안 뜬 이유의 하나로 보인다. 즉 "한 번에 다 보여준다"는 미학 문제가 아니라 **동작
// 문제**였다 — 덜어내야 뜬다.
//
// 그래서 이 카드는 gil status 가 답하는 것만 담는다: 지금 어디 · 무엇을 재는 중 · 사람이
// 나설 자리 · 다음 한 수. 그래프는 없다. 전체를 훑어야 할 때는 gil_graph 가 그 일을 한다.
//
// 자기완결이다 — 외부 스크립트·폰트·이미지 0. 호스트 샌드박스는 바깥을 못 부른다.
package main

import (
	"context"
	"net/url"
	"os"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const uiStatusURI = "ui://gil/status"

func registerGilStatusUI(s *mcp.Server) {
	read := func(ctx context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
		uri := uiStatusURI
		if req.Params != nil && req.Params.URI != "" {
			uri = req.Params.URI
		}
		return renderStatusResource(uri, uiRepoFor(uri))
	}
	s.AddResource(&mcp.Resource{
		Meta: uiResourceMeta(),
		URI:  uiStatusURI, Name: "gil-status", Title: "gil 상태 카드", MIMEType: uiGraphMIME,
		Description: "지금 어디·무엇을 재는 중·사람이 나설 자리·다음 한 수. 그래프는 담지 않는다.",
	}, read)
	s.AddResourceTemplate(&mcp.ResourceTemplate{
		Meta:        uiResourceMeta(),
		URITemplate: uiStatusURI + "/{repo}", Name: "gil-status-for-repo",
		Title: "gil 상태 카드 (저장소 지정)", MIMEType: uiGraphMIME,
		Description: "ui://gil/status/<경로> — 호스트가 열린 폴더를 안 알려줄 때(roots 미지원).",
	}, read)

	mcp.AddTool(s, &mcp.Tool{
		Name: "gil_status",
		Description: "지금 어디까지 왔는지를 카드로 보여준다 — 체인·사이클·스텝, 사람이 나설 " +
			"자리, 다음 한 수. 사람이 '어디까지 왔어'·'뭐 하는 중이야'라고 묻거나 스텝을 하나 " +
			"끝냈을 때 부른다. 전체 그래프가 필요할 때만 gil_graph 를 쓴다(이건 가볍고 그건 무겁다).",
		Meta: mcp.Meta{"ui": map[string]any{
			"resourceUri": uiStatusURI,
			"visibility":  []string{"model", "app"},
		}},
	}, func(ctx context.Context, req *mcp.CallToolRequest, in inEmpty) (*mcp.CallToolResult, any, error) {
		var st statusOut
		out, err := runGil(func() {
			adoptCallRepo(in)
			requireRepoHere()
			rememberUIRepo() // 뒤따르는 resources/read 가 이 자리를 쓴다
			st = gatherStatus()
		})
		if err != nil {
			return nil, nil, err
		}
		_ = out
		// 모델에게는 **줄인 텍스트**를 준다(카드와 같은 사실). JSON 을 통째로 주면 그것이
		// 그대로 대화에 실린다 — tipSignature 로 이미 한 번 값을 치른 자리다.
		res := &mcp.CallToolResult{
			Content:           []mcp.Content{&mcp.TextContent{Text: strings.Join(statusLines(st), "\n")}},
			StructuredContent: map[string]any{"tipSignature": tipSignatureDigest()},
		}
		// **선언된 URI 그대로**(변형 URI 는 호스트의 UI 리소스 목록에 없다 — 읽기는 되고
		// 렌더가 안 되던 자리). 저장소는 서버가 기억한다.
		res.Meta = mcp.Meta{"ui": map[string]any{
			"resourceUri": uiStatusURI,
			"visibility":  []string{"model", "app"},
		}}
		return res, nil, nil
	})
}

func repoFromStatusURI(uri string) string {
	rest := strings.TrimPrefix(uri, uiStatusURI+"/")
	if rest == uri {
		return ""
	}
	p, err := url.PathUnescape(rest)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(p)
}

// renderStatusResource — **껍데기를 낸다.** 카드는 앱이 gil_status_card 로 가져온다.
//
// 왜 여기서 통짜로 안 그리나. 호스트는 이 읽기를 **툴보다 먼저** 한다(실측 프레임). 그 순간
// 우리는 어느 저장소인지 알 수 없고, 그래서 지금까지 651 바이트짜리 "어느 저장소를 볼지
// 모른다" 를 내보내고 있었다 — 화면이 안 뜬 이유가 그것이다. 껍데기는 저장소를 몰라도 옳고,
// 내용은 앱이 제 통로로 가져오면 언제나 지금의 것이다.
//
// 저장소를 이미 아는 자리(예: URI 에 실려 온 경우)에서도 껍데기를 낸다. 두 길을 두면 어느
// 쪽으로 그려졌는지에 따라 화면이 달라지고, 그건 나중에 갈리는 종류의 이중화다.
func renderStatusResource(uri, repo string) (*mcp.ReadResourceResult, error) {
	if repo != "" {
		if _, err := gitTryIn(repo, "rev-parse", "--git-dir"); err == nil && os.Chdir(repo) == nil {
			stopGitCache()
			rememberUIRepo()
		}
	}
	return &mcp.ReadResourceResult{Contents: []*mcp.ResourceContents{{
		URI: uri, MIMEType: uiGraphMIME, Text: statusCardShellHTML(),
	}}}, nil
}

// statusCardShellHTML — 템플릿. 스타일과 빈 자리, 그리고 **제 내용을 가져오는 통로**.
//
// 이 페이지가 하는 일: (1) 호스트와 핸드셰이크 (2) `gil_status_card` 를 불러 카드 조각을 받아
// 그려 넣는다 (3) `ui/notifications/tool-result` 가 올 때마다(= gil 이 무엇을 했다는 뜻)
// 다시 가져온다. 레이아웃은 Go 에만 있다 — 앱은 받은 조각을 넣기만 한다.
func statusCardShellHTML() string {
	return statusCardDocHead() + `<body><div id="gil-card" class="card"><div class="lbl">gil</div>
<div class="none">상태를 가져오는 중…</div></div>
<script>
(function(){
  var host=window.parent, id=0, pending={}, fetching=false, fetches=0, drawn=false;
  var VER=` + jsString(gilVersion) + `, seen=[], repo="";
  function slot(){ return document.getElementById("gil-card"); }
  function send(m){ if(host!==window) host.postMessage(Object.assign({jsonrpc:"2.0"},m),"*"); }
  function notify(m,p){ send({method:m,params:p||{}}); }
  function reportSize(){ notify("ui/notifications/size-changed",
    {width:document.documentElement.scrollWidth,
     height:document.documentElement.scrollHeight}); }

  // **받은 것을 전부 적어 둔다.** 보내는 길은 되는데(호출이 서버에 도착한다) 응답이 콜백에
  // 안 닿는다 — 실측: 카드 조회 14번, 화면은 계속 "가져오는 중". iframe↔호스트 프레임은
  // 서버에 오지 않으니, 무엇이 어떤 모양으로 돌아오는지는 화면이 적어 보내야 알 수 있다.
  function note(m){
    if(seen.length<12) seen.push({
      m:(m&&m.method)||null, id:(m&&m.id)!==undefined?m.id:null,
      k:m&&typeof m==="object"?Object.keys(m).slice(0,8):typeof m,
      rk:m&&m.result&&typeof m.result==="object"?Object.keys(m.result).slice(0,8):undefined,
      e:m&&m.error?String(m.error.code||"")+":"+String(m.error.message||"").slice(0,60):undefined});
  }
  function report(tag){
    send({id:++id,method:"tools/call",params:{name:"gil_status_card",arguments:{
      probe:JSON.stringify({tag:tag,drawn:drawn,fetches:fetches,seen:seen}).slice(0,1900)}}});
  }

  // 카드는 **어느 칸으로 와도** 받는다. 호스트가 앱에게 넘겨주는 것은 content 뿐이었다
  // (structuredContent 는 안 넘어온다 — 실측). 둘 다 본다: 통로가 하나뿐이라고 가정하면
  // 호스트가 바뀔 때 다시 빈 화면이 된다.
  function cardOf(res){
    if(!res) return "";
    var sc=res.structuredContent;
    if(sc && sc.cardHtml) return sc.cardHtml;
    var c=res.content;
    if(c && c.length){
      for(var i=0;i<c.length;i++){
        var x=c[i];
        if(x && x.type==="text" && typeof x.text==="string" && x.text.indexOf("<div")>=0) return x.text;
      }
    }
    return "";
  }

  function fetchCard(){
    if(fetching || drawn || fetches>=4) return;
    fetching=true; fetches++;
    var i=++id;
    pending[i]=function(res,err){
      fetching=false;
      var s=slot(); if(!s) return;
      if(err){ s.innerHTML='<div class="lbl">gil</div><div class="none">가져오지 못했다: '+
        String((err&&(err.message||err.code))||err)+'</div>'; reportSize(); return; }
      var html=cardOf(res);
      // 조각이 없으면 **그 사실을 화면에 적는다** — 빈 화면은 고장과 아직을 구별해 주지 않는다.
      if(html){ s.innerHTML=html; drawn=true; }
      else { s.innerHTML='<div class="lbl">gil</div><div class="none">응답에 카드가 없다: '+
        String(res&&Object.keys(res).join(","))+'</div>'; }
      reportSize();
    };
    send({id:i,method:"tools/call",params:{name:"gil_status_card",
      arguments: repo ? {repo:repo} : {}}});
  }

  // **호스트가 알려주는 저장소를 줍는다.** 앱의 조회에는 인자가 없어서 서버가 cwd 가 / 인 자리에서
  // 돌다 거부했다(실측: isError 13회). 그런데 호스트는 tool-input/tool-result 알림에 모델이
  // 넘긴 인자를 실어 준다 — 그걸 기억해 우리 조회에 실으면 서버의 기억에 의존하지 않는다.
  function learnRepo(m){
    try{
      var p=m&&m.params||{};
      var cands=[p.arguments,p.input,p.toolInput,p.params,(p.request&&p.request.arguments)];
      for(var i=0;i<cands.length;i++){
        var c=cands[i];
        if(c && typeof c==="object" && typeof c.repo==="string" && c.repo){ 
          if(c.repo!==repo){ repo=c.repo; drawn=false; fetches=0; fetchCard(); }
          return;
        }
      }
    }catch(_){}
  }

  // ── 버튼 ─────────────────────────────────────────────────────────────────
  // **두 번 눌러야 돈다.** confirm() 은 샌드박스에서 조용히 죽는다(v3.49.0 에 값을 치른
  // 자리 — 승인 자체가 불가능했고 아무 표시도 없었다). 그래서 확인은 카드 안에서 한다:
  // 첫 클릭에 버튼이 "정말 …?" 로 바뀌고, 두 번째 클릭에 실행한다. 4초 지나면 원복 —
  // 무장한 채 남아 있으면 다음에 무심코 누른 것이 실행된다.
  function say(msg){ var s=slot(); if(!s) return;
    var d=s.querySelector(".said"); if(!d){ d=document.createElement("div");
      d.className="said"; s.appendChild(d); } d.textContent=msg; reportSize(); }

  function runAct(b){
    var tool=b.getAttribute("data-tool"), msg=b.getAttribute("data-msg"), to=b.getAttribute("data-to");
    if(tool){
      // 진짜 명령이 돈다(pending 의 승인·기각). 결과는 사람에게 한 줄로 알린다.
      var args={}; if(to) args.to=to;
      var i=++id;
      pending[i]=function(res,err){
        if(err){ say("돌지 않았다: "+String((err&&(err.message||err.code))||err)); return; }
        var txt=(res&&res.content&&res.content[0]&&res.content[0].text)||"";
        say(res&&res.isError ? ("거부됐다 — "+txt.split("\n")[0]) : "됐다. 화면을 다시 가져온다.");
        if(!(res&&res.isError)){ drawn=false; fetches=0; fetchCard(); }
      };
      send({id:i,method:"tools/call",params:{name:tool,arguments:args}});
      return;
    }
    if(msg){
      // gil 에 없는 문법은 버튼이 지어내지 않는다 — **사람의 판정을 대화에 넣고** 다음은
      // 에이전트가 쓴다(ui/message). 이유를 적었으면 그 문장을 함께 보낸다.
      var s=slot(), ta=s&&s.querySelector(".reason");
      var reason=(ta&&ta.value||"").trim();
      var text=msg.replace("{REASON}", reason ? (" 이유: "+reason) : "");
      send({id:++id,method:"ui/message",params:{role:"user",
        content:{type:"text",text:text}}});
      say(reason ? "대화에 전했다(이유 포함). 다음은 에이전트가 쓴다." :
                   "대화에 전했다. 다음은 에이전트가 쓴다.");
      return;
    }
  }

  document.addEventListener("click",function(ev){
    var b=ev.target.closest && ev.target.closest("[data-act],[data-open]");
    if(!b) return;
    ev.preventDefault();
    var open=b.getAttribute("data-open");
    if(open){ var box=document.getElementById(open);
      if(box){ box.hidden=!box.hidden; reportSize(); } return; }
    // 이유를 묻는 버튼은 첫 클릭에 입력칸을 함께 띄운다 — 기각의 값은 이유에 있다.
    if(b.getAttribute("data-ask-reason") && !b.hasAttribute("data-armed")){
      var s=slot();
      if(s && !s.querySelector(".reason")){
        var ta=document.createElement("textarea");
        ta.className="reason"; ta.rows=2;
        ta.placeholder="왜 기각인가 — 한 줄이면 충분하다(비워도 된다)";
        b.parentNode.parentNode.insertBefore(ta,b.parentNode.nextSibling);
      }
    }
    if(!b.hasAttribute("data-armed")){
      b.setAttribute("data-armed","1");
      b.dataset.label=b.textContent;
      b.textContent="정말? — 한 번 더";
      reportSize();
      setTimeout(function(){ if(b.hasAttribute("data-armed")){
        b.removeAttribute("data-armed"); b.textContent=b.dataset.label||b.textContent; reportSize(); } },4000);
      return;
    }
    b.removeAttribute("data-armed"); b.textContent=b.dataset.label||b.textContent;
    runAct(b);
  });

  window.addEventListener("message",function(e){
    var m=e.data; note(m); if(!m) return;
    if(m.method==="ui/notifications/tool-input"||m.method==="ui/notifications/tool-result") learnRepo(m);
    // 응답이 **어떤 모양으로 와도** 받는다: 우리 id 에 대한 답이거나, 툴 결과 알림이거나.
    var res=null;
    if(m.id!==undefined && pending[m.id]){ var cb=pending[m.id]; delete pending[m.id];
      cb(m.result,m.error); return; }
    if(m.method==="ui/notifications/tool-result"){
      res=(m.params&&(m.params.result||m.params))||null;
      var h2=cardOf(res);
      if(h2){ var s=slot(); if(s){ s.innerHTML=h2; drawn=true; reportSize(); } return; }
      if(!drawn) fetchCard();
    }
  });

  var hs=++id;
  pending[hs]=function(res,err){
    if(!err) notify("ui/notifications/initialized",{});
    reportSize(); fetchCard();
  };
  send({id:hs,method:"ui/initialize",params:{
    protocolVersion:"2026-01-26",
    appInfo:{name:"gil-status-card",version:VER},
    clientInfo:{name:"gil-status-card",version:VER},
    capabilities:{},
    appCapabilities:{availableDisplayModes:["inline","fullscreen"]}}});
  setTimeout(function(){ if(!drawn) fetchCard(); },900);
  setTimeout(function(){ report("2s"); },2000);
  setTimeout(function(){ report("6s"); },6000);
  window.addEventListener("load",reportSize);
  if(window.ResizeObserver) new ResizeObserver(reportSize).observe(document.documentElement);
})();
</script></body>`
}


// statusActionsHTML — **사람이 정하는 두 갈래.** 라벨은 일곱 kind 에서 같고, 뒤에서 도는
// 것은 다르다(status-card.md). 그래서 버튼은 자기가 무엇을 할지 데이터로 지고 있고, 껍데기는
// 그것을 그대로 실행한다 — 화면에 무엇이 도는지를 숨기지 않으면서 배선은 한 곳에 둔다.
//
// 두 통로가 있고, **아무 때나 아무 것이나 고르지 않는다**:
//
//	pending  → 진짜 관문이다. gil 문법에 승인·기각이 있다(gil approve / gil reject --to).
//	           그러니 버튼이 그 명령을 직접 돈다(tools/call).
//	그 밖    → gil 에는 "define 을 승인한다"는 문법이 없다. 사람의 판정을 **대화에 넣고**
//	           (ui/message) 다음 스텝은 에이전트가 쓴다 — 반증조건·퇴로·설계는 판단이고,
//	           클릭으로 채울 수 있는 값이 아니다. 없는 문법을 버튼으로 지어내지 않는다.
func statusActionsHTML(st statusOut) string {
	if st.Step == nil || st.Cycle == nil || st.Chain == nil {
		return ""
	}
	ref := st.Chain.Name + "/" + st.Cycle.Name + "/" + st.Step.ID
	if st.Waiting != nil && st.Waiting.Kind == "approval" {
		return pendingActionsHTML(st, ref)
	}
	// 사람의 판정을 대화에 넣는다. 문장은 **에이전트가 다음에 할 일**까지 말한다 — "승인함"
	// 한 줄만 던지면 그 뒤가 세션마다 갈린다.
	ok := "gil " + ref + " (" + st.Step.Kind + ") 를 승인한다. 이 자리를 딛고 다음 스텝을 " +
		"세워라 — 가설이라면 반증조건·반증 시 물러설 자리·고정할 설계를 함께 정해서."
	no := "gil " + ref + " (" + st.Step.Kind + ") 를 기각한다.{REASON} 같은 자리에서 다시 " +
		"정의하거나(정정), 이 사이클을 무르고 원하는 자리에서 새 사이클을 열어라. " +
		"어느 쪽이 맞는지 먼저 말해 달라."
	return `<div class="acts">` +
		`<button class="btn primary" data-act="approve" data-msg="` + esc(ok) + `">승인</button>` +
		`<button class="btn" data-act="reject" data-msg="` + esc(no) + `" data-ask-reason="1">기각 · 수정</button>` +
		`</div>`
}

// pendingActionsHTML — 사람을 기다리는 스텝. 여기서는 버튼이 **진짜 명령을 돈다.**
//
// 기각은 되돌아갈 자리를 요구한다(gil reject --to). 그 문자열을 비개발자가 알 방법은 없으므로
// (그래프를 읽고 스텝을 세어야 나온다) 후보를 **무엇을 잃는가와 함께** 버튼으로 세운다 —
// 사람이 고르는 근거는 "s4"가 아니라 "s5~s7 이 버려진다"다.
func pendingActionsHTML(st statusOut, ref string) string {
	var b strings.Builder
	b.WriteString(`<div class="acts">` +
		`<button class="btn primary" data-act="approve" data-tool="gil_approve">승인</button>` +
		`<button class="btn" data-act="reject" data-open="gil-back">기각 — 되돌아갈 자리를 고른다</button>` +
		`</div>`)
	if len(st.Rollback) == 0 {
		return b.String()
	}
	b.WriteString(`<div id="gil-back" class="panel" hidden>` +
		`<div class="lbl">어디로 되돌리나 — 고르면 그 뒤가 버려진다</div>`)
	for _, c := range st.Rollback {
		lose := "버릴 것 없음"
		if len(c.Discards) > 0 {
			lose = "버려진다: " + foldRanges(c.Discards)
		}
		b.WriteString(`<div class="backrow">` +
			`<button class="btn" data-act="reject" data-tool="gil_reject" data-to="` + esc(c.ID) + `">` +
			esc(c.ID) + `</button>` +
			`<span class="backlab">` + esc(clip(c.Label, 70)) + `</span>` +
			`<span class="backlose">` + esc(lose) + `</span></div>`)
	}
	b.WriteString(`</div>`)
	return b.String()
}

// foldRanges — 연속한 스텝은 범위로 접는다(s5, s6, s7 → s5~s7). 나열이 길면 사람은 안 읽는다.
func foldRanges(ids []string) string {
	if len(ids) == 0 {
		return ""
	}
	var out []string
	start, prev := ids[0], ids[0]
	flush := func() {
		if start == prev {
			out = append(out, start)
			return
		}
		out = append(out, start+"~"+prev)
	}
	for _, id := range ids[1:] {
		if stepNum(id) == stepNum(prev)+1 {
			prev = id
			continue
		}
		flush()
		start, prev = id, id
	}
	flush()
	return strings.Join(out, ", ")
}

// statusCardHTML — 통짜 페이지(문서 + 스타일 + 카드). `gil status --card` 와, 저장소를 이미
// 아는 자리에서 리소스를 읽을 때 쓴다.
func statusCardHTML(st statusOut) string {
	return statusCardDocHead() + `<body>` + statusCardBodyHTML(st) + `</body>`
}

// statusCardDocHead — 문서 껍데기와 스타일. **카드 조각과 갈라 둔다** — 앱이 조각만 받아
// 그려 넣을 때 스타일은 이미 템플릿에 있어야 한다(조각마다 스타일을 실어 보내면 같은 CSS 가
// 호출마다 왕복한다).
func statusCardDocHead() string {
	return `<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#fff;--fg:#26262a;--dim:#6f6e69;--line:#dedcd4;--card:#f1efe8;
      --warn-bg:#fff6e5;--warn-fg:#7a4d00;--warn-line:#f0d9a8;
      --wait-bg:#eaf2ff;--wait-fg:#12406b;--wait-line:#bcd6f5;--code:#f1efe8;--panel:#fff;--acc:#444441;--acc-fg:#fff}
@media (prefers-color-scheme:dark){
:root{--bg:#17171a;--fg:#e9e7e1;--dim:#9b9992;--line:#3a3a3d;--card:#232326;
      --warn-bg:#3a2a12;--warn-fg:#ffd79a;--warn-line:#7a5a24;
      --wait-bg:#12283f;--wait-fg:#bcd9ff;--wait-line:#2a557f;--code:#2f2f33;--panel:#2e2e32;--acc:#d3d1c7;--acc-fg:#26262a}}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);
 font:14px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.card{max-width:720px;border:1px solid var(--line);border-radius:12px;
 background:var(--card);padding:14px 16px}
.crumb{font-size:15px;font-weight:600;letter-spacing:-.01em;word-break:break-word}
.crumb .sep{color:var(--dim);font-weight:400;margin:0 6px}
.kind{font-size:12px;font-weight:600;color:#1c1c1f;border-radius:99px;
 padding:2px 10px;margin-left:8px;white-space:nowrap;vertical-align:1px}
.k-define{background:#D3D1C7}
.k-hypothesis{background:#CECBF6}
.k-verify{background:#B5D4F4}
.k-analyze{background:#9FE1CB}
.k-pending{background:#FAC775}
.k-success{background:#C0DD97}
.k-fail{background:#F5C4B3}
.repo{font-size:12px;color:var(--dim);margin-top:2px;word-break:break-all}
.row{margin-top:12px}
.lbl{font-size:11px;color:var(--dim);letter-spacing:.04em;text-transform:uppercase}
.val{margin-top:2px}
.box{margin-top:12px;border-radius:10px;padding:11px 13px;border:1px solid}
.wait{background:var(--wait-bg);color:var(--wait-fg);border-color:var(--wait-line)}
.warn{background:var(--warn-bg);color:var(--warn-fg);border-color:var(--warn-line);margin-top:8px}
.box .t{font-weight:600}
ul{margin:4px 0 0;padding-left:18px}li{margin:3px 0}
code{background:var(--code);border-radius:5px;padding:1px 5px;
 font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}
.foot{margin-top:12px;font-size:12px;color:var(--dim)}
.panel{background:var(--panel);border-radius:10px;padding:11px 13px;margin-top:10px}
.panel .lbl{margin-bottom:3px}
.panel.strip-panel{padding:6px 10px 4px}
.big{font-size:16px;line-height:1.5}
.orig{margin-top:7px;font-size:13px;color:var(--dim);white-space:pre-wrap;word-break:break-word}
.none{font-size:13px;color:var(--dim)}
.acts{display:flex;gap:8px;margin-top:10px}
.btn{display:inline-block;border-radius:7px;padding:5px 14px;font:13px/1.4 inherit;
 border:1px solid var(--line);background:var(--panel);color:var(--fg);cursor:pointer}
.btn.primary{background:var(--acc);color:var(--acc-fg);border-color:var(--acc)}
.btn[data-armed]{background:var(--warn-bg);color:var(--warn-fg);border-color:var(--warn-line)}
.backrow{display:flex;gap:9px;align-items:baseline;margin-top:7px;flex-wrap:wrap}
.backlab{font-size:13px}
.backlose{font-size:12px;color:var(--dim)}
.reason{width:100%;margin-top:8px;border-radius:8px;border:1px solid var(--line);
 background:var(--panel);color:var(--fg);font:13px/1.5 inherit;padding:7px 9px}
.said{margin-top:9px;font-size:13px;color:var(--dim)}

.strip{display:block;margin:10px 0 2px;max-width:100%;height:auto}
.strip .e{stroke:var(--dim);stroke-width:1.5;fill:none}
.strip .bt{stroke:#D85A30;stroke-width:1.5;stroke-dasharray:4 3;fill:none}
.strip .ring{fill:none;stroke-width:1.5}
.strip .knd{font-size:9.5px;fill:var(--dim);text-anchor:middle}
.legend{display:flex;flex-wrap:wrap;gap:4px 12px;margin:2px 0 2px;font-size:11px;color:var(--dim)}
.legend i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:0}
</style>`
}

// statusCardBodyHTML — **카드 조각 하나.** 앱이 이걸 받아 그려 넣는다.
func statusCardBodyHTML(st statusOut) string {
	var b strings.Builder
	b.WriteString(`<div class="card">`)

	if st.Chain == nil {
		b.WriteString(`<div class="crumb">체인 밖</div><div class="repo">` + esc(st.Repo) + `</div>`)
		b.WriteString(`<div class="row"><div class="val">아직 연 체인이 없거나 층(dev·main) 위에 서 있다.</div></div>`)
	} else {
		// 사람이 나설 자리 — 있으면 맨 위.
		if st.Waiting != nil {
			b.WriteString(`<div class="box wait"><div class="t">⏳ 사람이 정할 자리</div><div>` +
				esc(st.Waiting.What) + `</div><div style="margin-top:6px">`)
			for _, ln := range strings.Split(st.Waiting.Answer, "\n") {
				b.WriteString(`<div>` + codeify(ln) + `</div>`)
			}
			b.WriteString(`</div></div>`)
		}
		// 머리글은 **체인 › 사이클 › 스텝** 셋을 다 부른다. 체인 이름이 빠지면 여러 체인을
		// 오가는 사람이 지금 어느 계보 안에 있는지 모른다(#110 이 저장소 이름에서 겪은 병).
		// 머리글은 **체인 › 사이클 › 스텝 (kind)**. kind 는 그 끝에 **제 색으로 채운 타원**이다
		// (상현님) — 옅은 회색 알약이었을 때는 지금 무슨 스텝에 서 있는지가 눈에 안 들어왔다.
		// 색은 띠와 같은 램프를 쓰고 글자는 검정이라, 라이트·다크 어느 쪽에서도 같이 읽힌다.
		b.WriteString(`<div class="crumb">` + esc(st.Chain.Name))
		if st.Cycle != nil {
			b.WriteString(`<span class="sep">›</span>` + esc(st.Cycle.Name))
		}
		if st.Step != nil {
			b.WriteString(`<span class="sep">›</span>` + esc(st.Step.ID) +
				`<span class="kind k-` + esc(st.Step.Kind) + `">` + esc(st.Step.Kind) + `</span>`)
		}
		b.WriteString(`</div><div class="repo">` + esc(st.Repo) + `</div>`)

		// 띠 — **카드 종류와 무관하게 여기 있다.** 본문은 kind 마다 다르지만 "어디에 서 있나"
		// 는 어느 카드에서도 같은 질문이고, 나타나고 사라지면 카드가 한 물건으로 안 읽힌다.
		if st.Cycle != nil {
			cur := ""
			if st.Step != nil {
				cur = st.Step.ID
			}
			if svg := statusStripSVG(st.Cycle.Steps, cur); svg != "" {
				b.WriteString(`<div class="panel strip-panel">` + svg + statusKindLegend() + `</div>`)
			}
		}

		b.WriteString(statusCardBody(st))
	}

	for _, w := range st.Warnings {
		b.WriteString(`<div class="box warn">⚠ ` + esc(w) + `</div>`)
	}

	// define 에서는 다음 한 수를 적지 않는다(상현님) — 다음은 hypothesis 하나뿐이라 자명하고,
	// 그 자리는 **사람이 정하는 두 갈래**(승인·기각)가 쓴다. 선택지가 하나면 목록이 아니다.
	if len(st.Next) > 0 && !(st.Step != nil && st.Step.Kind == "define") {
		b.WriteString(`<div class="panel"><div class="lbl">다음 한 수</div><ul>`)
		for _, n := range st.Next {
			b.WriteString(`<li>` + codeify(n) + `</li>`)
		}
		b.WriteString(`</ul></div>`)
	}

	b.WriteString(`</div>`)
	return b.String()
}

// statusCardBody — **kind 마다 다른 본문.** 같은 데이터라도 그 순간에만 의미 있는 것이
// 다르다(status-card.md 의 일곱 얼굴). 아직 얼굴이 없는 kind 는 공통 본문으로 떨어진다 —
// 없는 얼굴을 있는 척 그리지 않는다.
func statusCardBody(st statusOut) string {
	if st.Cycle == nil || st.Step == nil {
		return ""
	}
	if st.Step.Kind == "define" {
		return defineCardBody(st)
	}
	var b strings.Builder
	if st.Cycle.RefutesIf != "" {
		b.WriteString(`<div class="panel"><div class="lbl">재는 중 — 무엇이 관측되면 틀리나</div>` +
			`<div class="big">` + esc(clip(st.Cycle.RefutesIf, 220)) + `</div></div>`)
	}
	if st.Cycle.FalsifyTo != "" {
		b.WriteString(`<div class="panel"><div class="lbl">반증되면 돌아갈 자리</div><div>` +
			`<code>` + esc(st.Cycle.FalsifyTo) + `</code></div></div>`)
	}
	b.WriteString(statusActionsHTML(st))
	return b.String()
}

// defineCardBody — **문제정의**와 **기반사실** 둘이 분명하게 드러나야 한다 (상현님).
//
// 이 두 칸이 define 카드의 전부다: 무엇을 어떻게 정했나, 그리고 **어떤 물려받은 사실로부터**
// 그 문제를 정했나. 뒤 칸이 없으면 문제정의는 근거 없는 선언으로 읽히고, 사람은 승인할지
// 판단할 재료가 없다.
//
// 물음으로 다시 쓰지 않는다 — 그건 읽기 보조고 **에이전트의 몫**이다(status-card.md).
// 코드가 물음을 지어내면 기록에 없는 문장이 카드에 앉는다. 여기서는 선언문과 원문을 낸다.
func defineCardBody(st statusOut) string {
	var b strings.Builder
	b.WriteString(`<div class="panel"><div class="lbl">문제정의 — 무엇을 풀려고 하나</div>`)
	if p := st.Cycle.Purpose; p != "" {
		b.WriteString(`<div class="big">` + esc(p) + `</div>`)
	} else {
		b.WriteString(`<div class="none">이 사이클엔 목적 문장이 없다.</div>`)
	}
	// 원문은 **반드시 함께** 둔다. 요약만 두면 지어내서 감춘 것이 된다.
	if body := st.Step.Body; body != "" {
		b.WriteString(`<div class="orig">` + esc(body) + `</div>`)
	}
	b.WriteString(`</div>`)

	b.WriteString(`<div class="panel"><div class="lbl">기반사실 — 어떤 물려받은 사실에서 이 문제가 나왔나</div>`)
	if inh := st.Cycle.Inherit; inh != "" {
		b.WriteString(`<div class="big">` + esc(inh) + `</div>`)
	} else {
		// 없는 것을 채우지 않되, **없다는 사실은 말한다.** 빈 칸을 지우면 근거가 없다는 것이
		// 화면에서 사라지고, 그건 근거가 있는 것과 같아 보인다.
		b.WriteString(`<div class="none">물려받은 사실이 기록에 없다 — 이 문제정의는 앞 사이클의 결론을 딛고 있지 않다.</div>`)
	}
	b.WriteString(`</div>`)

	// 사람이 정하는 두 갈래. **라벨은 일곱 kind 에서 같고, 뒤에서 도는 것은 다르다** —
	// 그래서 부제로 무슨 일이 일어나는지 적는다(라벨은 통일하되 숨기지 않는다).
	// 부제는 붙이지 않는다(상현님). 승인은 가설로 이어지고 기각은 문제정의를 다시 세운다 —
	// 그건 이 자리에 서 본 사람이면 아는 것이고, 매번 설명하면 화면만 길어진다.
	b.WriteString(statusActionsHTML(st))
	return b.String()
}

// codeify — "gil …" 로 시작하는 앞부분을 <code> 로 감싸고 설명은 그대로 둔다.
// 사람이 **칠 수 있는 것**과 읽을 것을 눈으로 가른다.
func codeify(s string) string {
	s = strings.TrimSpace(s)
	if !strings.HasPrefix(s, "gil ") {
		return esc(s)
	}
	cmd, rest := s, ""
	if i := strings.Index(s, "  —"); i >= 0 {
		cmd, rest = strings.TrimSpace(s[:i]), s[i:]
	} else if i := strings.Index(s, " (") ; i >= 0 {
		cmd, rest = strings.TrimSpace(s[:i]), s[i:]
	}
	return `<code>` + esc(cmd) + `</code>` + esc(rest)
}

func escHTML(s string) string {
	return strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;", `"`, "&quot;").Replace(s)
}
