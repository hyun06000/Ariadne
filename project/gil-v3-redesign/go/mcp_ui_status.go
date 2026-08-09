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

// uiStatusMeta — **이 툴은 상태 카드를 함께 연다**는 선언.
//
// 화면을 여는 툴이 gil_status 하나뿐이던 동안, 사람에게 묻는 자리(인터뷰를 심는 툴)는
// 물어 놓고 아무것도 안 띄웠다 — 그래서 안내가 "화면의 폼에 답해 달라고 청하라"고 말해도
// 사람 앞에는 화면이 없었다(상현님 실사용, 2026-08-10). **묻는 자리가 곧 화면이 서는 자리다.**
func uiStatusMeta() mcp.Meta {
	return mcp.Meta{"ui": map[string]any{
		"resourceUri": uiStatusURI,
		"visibility":  []string{"model", "app"},
	}}
}

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
		Description: "지금 어느 단계인지·무엇을 측정 중인지·사람의 판단이 필요한지·다음 단계. 그래프는 담지 않는다.",
	}, read)
	s.AddResourceTemplate(&mcp.ResourceTemplate{
		Meta:        uiResourceMeta(),
		URITemplate: uiStatusURI + "/{repo}", Name: "gil-status-for-repo",
		Title: "gil 상태 카드 (저장소 지정)", MIMEType: uiGraphMIME,
		Description: "ui://gil/status/<경로> — 호스트가 열린 폴더를 안 알려줄 때(roots 미지원).",
	}, read)

	mcp.AddTool(s, &mcp.Tool{
		Name: "gil_status",
		Description: "지금 어디까지 왔는지를 카드로 보여준다 — 체인·사이클·스텝, 사람의 판단이 " +
			"필요한 곳, 다음 단계. 사람이 '어디까지 왔어'·'뭐 하는 중이야'라고 묻거나 스텝을 하나 " +
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
	// **계기는 기본으로 꺼 둔다.** 이 보고는 화면이 안 뜨던 자리를 찾는 데 값을 다 했다 —
	// 호스트가 무엇으로 답했는지, 프레임이 실제로 섰는지는 이 길 말고는 볼 수 없었다. 그런데
	// 켜 둔 채로 릴리스하면 **모든 세션이 매번 두 번씩** 진단 호출을 하고, 그 호출이 사람의
	// 도구 목록과 프레임 로그에 남는다. 도구가 자기를 진단하는 비용을 사용자가 늘 치를 이유는
	// 없다. 필요할 때 켠다: `GIL_UI_PROBE=1`(MCP 서버 프로세스의 환경변수).
	probe := os.Getenv("GIL_UI_PROBE") == "1"
	probeJS := "false"
	if probe {
		probeJS = "true"
	}
	return statusCardDocHead() + `<body><div id="gil-card" class="card"><div class="lbl">gil</div>
<div class="none">상태를 가져오는 중…</div></div>
<script>
(function(){
  var host=window.parent, id=0, pending={}, fetching=false, fetches=0, drawn=false;
  var VER=` + jsString(gilVersion) + `, seen=[], repo="", PROBE=` + probeJS + `;
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
    if(!PROBE) return;
    if(seen.length<12) seen.push({
      m:(m&&m.method)||null, id:(m&&m.id)!==undefined?m.id:null,
      k:m&&typeof m==="object"?Object.keys(m).slice(0,8):typeof m,
      rk:m&&m.result&&typeof m.result==="object"?Object.keys(m.result).slice(0,8):undefined,
      // 호스트가 핸드셰이크에 무엇을 실어 주는지 — 테마를 실제로 주는지가 여기서만 보인다.
      hc:m&&m.result&&m.result.hostContext&&typeof m.result.hostContext==="object"
        ?Object.keys(m.result.hostContext).slice(0,8).concat(["theme="+String(m.result.hostContext.theme||"")])
        :undefined,
      e:m&&m.error?String(m.error.code||"")+":"+String(m.error.message||"").slice(0,60):undefined});
  }
  function report(tag){
    if(!PROBE) return;
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
    // **인터뷰 제출.** 사람이 폼에 적은 것을 그대로 모아 보낸다 — 화면은 답을 고치지도,
    // 채우지도 않는다(그 순간 기준이 사람의 문장이 아니게 된다).
    if(b.getAttribute("data-act")==="interview-submit"){
      var box=b.closest("[data-iv]"); if(!box) return;
      var ans={}, filled=false;
      var els=box.querySelectorAll("[data-q]");
      for(var k=0;k<els.length;k++){
        var el=els[k], key=el.getAttribute("data-q");
        if(el.type==="checkbox"){ if(el.checked){ ans[key]=true; filled=true; } }
        else if(el.type==="radio"){ if(el.checked){ ans[key]=el.value; filled=true; } }
        else { var v=(el.value||"").trim(); if(v){ ans[key]=v; filled=true; } }
      }
      // 빈 제출은 보내지 않는다 — 빈 기준으로 확정되면 그 뒤 판정이 전부 형해화된다.
      if(!filled){ say("아직 아무것도 적히지 않았다 — 한 칸이라도 채워야 보낼 수 있다."); return; }
      var j=++id;
      pending[j]=function(res,err){
        if(err){ say("보내지 못했다: "+String((err&&(err.message||err.code))||err)); return; }
        var h=cardOf(res);
        if(h){ var s2=slot(); if(s2){ s2.innerHTML=h; drawn=true; reportSize(); } return; }
        say("보냈다. 화면을 다시 가져온다."); drawn=false; fetches=0; fetchCard();
      };
      send({id:j,method:"tools/call",params:{name:"gil_interview_submit",arguments:{
        chain:b.getAttribute("data-chain")||"", answers:JSON.stringify(ans),
        repo:repo||undefined}}});
      say("보내는 중…");
      return;
    }
    if(tool){
      // 진짜 명령이 돈다(pending 의 승인·기각). 결과는 사람에게 한 줄로 알린다.
      // **대상과 저장소를 함께 싣는다.** target 은 스키마가 필수로 광고하므로 빼면 호출이
      // gil 에 닿기 전에 검증에서 죽고, repo 를 빼면 서버가 선 자리(cwd)에 기댄다 — 앱의
      // 조회에 인자가 없어서 거부됐던 그 자리다(위 learnRepo 주석, 실측 isError 13회).
      // 인터뷰 제출은 처음부터 둘 다 실었는데 이 갈래만 안 실었다.
      var args={};
      var tgt=b.getAttribute("data-target"); if(tgt) args.target=tgt;
      if(to) args.to=to;
      if(repo) args.repo=repo;
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

  // **호스트가 제 테마를 말해 주면 그것이 이긴다.** 샌드박스 안의 prefers-color-scheme 은
  // OS 의 것이라, 앱만 어둡게 써 온 사람에게는 어두운 화면 한가운데 흰 카드가 선다.
  // 어느 칸으로 오는지는 호스트마다 다를 수 있으니 몇 자리를 본다 — cardOf·learnRepo 와
  // 같은 이유다(통로가 하나뿐이라 가정하면 호스트가 바뀔 때 화면이 어긋난다).
  // 색 변수 자체는 **가져다 쓰지 않는다**: 이름을 모르는 채 우리 --bg 에 꽂으면 배경이
  // 아닌 값이 배경이 되어 카드가 통째로 안 읽힌다. 모르는 것은 안 한다.
  function applyTheme(res){
    try{
      var hc=(res&&res.hostContext)||{};
      var t=hc.theme||(hc.styles&&hc.styles.theme)||(res&&res.theme)||"";
      if(t==="dark"||t==="light") document.documentElement.setAttribute("data-theme",t);
    }catch(_){}
  }

  var hs=++id;
  pending[hs]=function(res,err){
    if(!err){ applyTheme(res); notify("ui/notifications/initialized",{}); }
    reportSize(); fetchCard();
  };
  send({id:hs,method:"ui/initialize",params:{
    protocolVersion:"2026-01-26",
    appInfo:{name:"gil-status-card",version:VER},
    clientInfo:{name:"gil-status-card",version:VER},
    capabilities:{},
    appCapabilities:{availableDisplayModes:["inline","fullscreen"]}}});
  setTimeout(function(){ if(!drawn) fetchCard(); },900);
  if(PROBE){ setTimeout(function(){ report("2s"); },2000);
             setTimeout(function(){ report("6s"); },6000); }
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
		return pendingActionsHTML(st)
	}
	// 사람의 판정을 대화에 넣는다. 문장은 **에이전트가 다음에 할 일**까지 말한다 — "승인함"
	// 한 줄만 던지면 그 뒤가 세션마다 갈린다.
	// 승인 문장은 **다음에 무엇을 하라**까지 말한다("승인함" 한 줄만 던지면 그 뒤가 세션마다
	// 갈린다). 그 한 수는 **gil 이 준 것**을 그대로 옮긴다 — 여기서 창작하면 문법이 허용하지
	// 않는 수를 사람 입으로 지시하게 된다(v3.58.1·v3.58.2 가 고친 병).
	ok := "gil " + ref + " (" + st.Step.Kind + ") 를 승인한다. 이 결과를 근거로 다음 단계를 세워라."
	// **종결은 잎이다** — 그 뒤에 스텝을 이어 붙일 수 없다(#60①). 여기서 "다음 스텝을
	// 세워라"고 쓰면 사람이 승인을 누른 그 순간, 에이전트는 gil 이 거부할 수를 지시받는다.
	// 없는 문법을 버튼이 지어내지 않는다는 규칙은 **문장에도** 걸린다.
	if st.Step.Kind == "success" || st.Step.Kind == "fail" {
		ok = "gil " + ref + " (" + st.Step.Kind + ") 를 승인한다. 이 분기는 여기서 종결된다 — " +
			"뒤에 단계를 잇지 말고 아래 중 하나로 가라."
	}
	// **후보가 여럿이면 여럿을 준다.** 첫 줄만 실으면 그건 카드가 사람 대신 고른 것이다 —
	// analyze 뒤는 넷(지지로 종결·기각으로 종결·사람 판단 요청·경쟁 가설)이고,
	// 그 선택이 이 사이클의 방향이다.
	if len(st.Next) > 0 {
		ok += " 다음 단계: " + strings.Join(st.Next, " / ")
		if len(st.Next) > 1 {
			ok += " (gil 이 준 후보 전부다 — 어느 쪽인지 먼저 판단해라)"
		}
	}
	no := "gil " + ref + " (" + st.Step.Kind + ") 를 기각한다.{REASON} 같은 단계에서 다시 " +
		"정의하거나(정정), 이 사이클을 무르고 원하는 단계에서 새 사이클을 열어라. " +
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
func pendingActionsHTML(st statusOut) string {
	// **대상을 버튼이 싣는다.** `gil approve`·`gil reject` 는 `<chain>/<cycle>` 을 위치인자로
	// 받고 스키마도 그것을 필수로 광고한다(mcp.go 의 inApprove.Target·inReject.Target).
	// 안 실으면 호출이 gil 에 닿기도 **전에** 검증에서 죽고, 사람 화면에는 runAct 가 받은
	// 첫 줄이 그대로 찍힌다 — `거부됐다 — validating "arguments"… missing properties: ["target"]`.
	// 비개발자에게 도착하는 문장이 그것이었다. 카드는 이 값을 이미 알고 있었다(바로 아래
	// 두 줄이 그것이다) — 넘기지 않고 있었을 뿐이다. gil_chain 의 purpose 가 이미 값을
	// 치른 병이고, 스키마와 호출을 **두 자리에 따로 적으면 한쪽만 낡는다**.
	target := st.Chain.Name + "/" + st.Cycle.Name
	var b strings.Builder
	b.WriteString(`<div class="acts">` +
		`<button class="btn primary" data-act="approve" data-tool="gil_approve" data-target="` +
		esc(target) + `">승인</button>`)
	// **되돌아갈 자리가 없으면 그 버튼을 세우지 않는다.** data-open 이 가리키는 칸이 없으면
	// 눌러도 아무 일도 안 일어나고(핸들러가 box==null 에서 조용히 끝난다), 사람은 화면이
	// 고장 났다고 읽는다. 없는 것과 안 도는 것은 다르다 — 없으면 없다고 적는다.
	if len(st.Rollback) == 0 {
		b.WriteString(`</div><div class="none">기각하려면 되돌아갈 define 단계가 있어야 한다 — ` +
			`이 사이클엔 아직 없다.</div>`)
		return b.String()
	}
	b.WriteString(`<button class="btn" data-act="reject" data-open="gil-back">기각 — 되돌아갈 단계를 고른다</button>` +
		`</div>`)
	b.WriteString(`<div id="gil-back" class="panel" hidden>` +
		`<div class="lbl">어느 단계로 되돌아가나 — 고르면 그 뒤 단계가 버려진다</div>`)
	for _, c := range st.Rollback {
		lose := "버릴 것 없음"
		if len(c.Discards) > 0 {
			lose = "버려진다: " + foldRanges(c.Discards)
		}
		b.WriteString(`<div class="backrow">` +
			`<button class="btn" data-act="reject" data-tool="gil_reject" data-target="` + esc(target) +
			`" data-to="` + esc(c.ID) + `">` +
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

// hypothesisCardBody — **무엇이 참이라고 보나, 그리고 무엇이 관측되면 멈추나** (상현님).
//
// 세 칸이 이 카드다: 세운 가설 · 그것이 무엇에서 나왔나(문제정의) · 가드레일(반증조건과 퇴로).
// 반증조건은 여기서 **앞으로 잴 것**이다 — analyze 에서는 이미 지나간 것이고, 같은 문장을
// 같은 자리에 두면 사람은 그 차이를 못 읽는다(status-card.md).
//
// **없는 칸은 만들지 않는다.** 상현님이 물은 "옳다고 보이려면 무엇이 관측되어야 하나"는
// gil 에 필드가 없다 — 문법은 반증 쪽만 요구하고(--falsify), 기대되는 관측은 본문 산문에
// 묻혀 있다. 그래서 그 자리는 **본문 원문**으로 답한다(요약해서 감추지 않는다). 빈 칸을
// 제목만 남겨 두면 화면은 그럴듯해지고 판단은 틀려진다.
func hypothesisCardBody(st statusOut) string {
	var b strings.Builder

	b.WriteString(`<div class="panel"><div class="lbl">가설 — 무엇이 참이라고 보나</div>`)
	if h := st.Cycle.Hypothesis; h != "" {
		b.WriteString(`<div class="big">` + mdInlineHTML(h) + `</div>`)
	} else {
		b.WriteString(`<div class="none">가설 문장이 없다.</div>`)
	}
	// 본문(보고서)은 이 스텝에 서 있을 때만 그 스텝의 것이다 — 뒤 스텝에 서 있으면 여기
	// 실리는 본문은 다른 스텝의 것이 된다. 없는 것을 남의 것으로 채우지 않는다.
	if st.Step.Kind == "hypothesis" && st.Step.Body != "" {
		b.WriteString(`<div class="orig md">` + mdToHTML(st.Step.Body) + `</div>`)
	}
	b.WriteString(`</div>`)

	b.WriteString(`<div class="panel"><div class="lbl">무엇에서 나왔나 — 이 사이클의 문제정의</div>`)
	if p := st.Cycle.Purpose; p != "" {
		b.WriteString(`<div class="big">` + mdInlineHTML(p) + `</div>`)
	} else {
		b.WriteString(`<div class="none">문제 정의 문장이 없다.</div>`)
	}
	if inh := st.Cycle.Inherit; inh != "" {
		b.WriteString(`<div class="orig">앞에서 확인된 사실: ` + mdInlineHTML(inh) + `</div>`)
	}
	b.WriteString(`</div>`)

	// 가드레일. **반증조건과 퇴로는 한 칸에 함께 선다** — "무엇이 관측되면 멈추나"와 "멈추면
	// 어디로 물러서나"는 한 결정이고, 떼어 놓으면 퇴로가 부속처럼 읽힌다.
	b.WriteString(`<div class="panel"><div class="lbl">반증조건 — 이것이 관측되면 가설을 기각한다</div>`)
	if r := st.Cycle.RefutesIf; r != "" {
		b.WriteString(`<div class="big">` + mdInlineHTML(r) + `</div>`)
	} else {
		b.WriteString(`<div class="none">반증조건이 없다 — 어떤 관측으로도 이 가설을 기각할 수 없다(반증 가능성이 없다).</div>`)
	}
	if to := st.Cycle.FalsifyTo; to != "" {
		line := "반증되면 " + to + " 단계로 되돌아간다"
		for _, c := range st.Rollback {
			if c.ID == to {
				line += " — " + clip(c.Label, 60)
				if len(c.Discards) > 0 {
					line += " (버려진다: " + foldRanges(c.Discards) + ")"
				}
				break
			}
		}
		b.WriteString(`<div class="orig">` + esc(line) + `</div>`)
	}
	// 지도를 벗어나 갈라진 이유는 **삼키지 않는다**(#105) — 감추면 두 계획이 동시에 유효한
	// 것처럼 보인다.
	if d := st.Cycle.DespiteMap; d != "" {
		b.WriteString(`<div class="orig">미리 정한 복귀 단계가 아닌 곳에서 분기한 이유: ` + esc(d) + `</div>`)
	}
	b.WriteString(`</div>`)

	// 재기 전에 못박은 것과, 이 측정이 체인 목적에 다가서려는 몫. 둘 다 있을 때만 칸을 만든다.
	if st.Cycle.Plan != "" || st.Cycle.Advances != "" {
		b.WriteString(`<div class="panel">`)
		if st.Cycle.Plan != "" {
			b.WriteString(`<div class="lbl">측정 전에 정한 방법</div><div class="big">` +
				mdInlineHTML(st.Cycle.Plan) + `</div>`)
		}
		if st.Cycle.Advances != "" {
			b.WriteString(`<div class="orig">이 측정의 목적: ` + mdInlineHTML(st.Cycle.Advances))
			if st.Chain.Criterion != "" {
				b.WriteString(` · 체인 판정 기준: ` + esc(st.Chain.Criterion))
			}
			b.WriteString(`</div>`)
		}
		b.WriteString(`</div>`)
	}

	b.WriteString(competingHTML(st))
	b.WriteString(statusActionsHTML(st))
	return b.String()
}

// competingHTML — 나란히 겨루는 갈래들. **세지 말고 이름을 부른다**(#112) — "경합 3개"는
// 비교의 재료가 아니다. 하나뿐이면 경합이 아니라 재분기라 아무것도 그리지 않는다.
func competingHTML(st statusOut) string {
	if len(st.Cycle.Competing) < 2 {
		return ""
	}
	var b strings.Builder
	b.WriteString(`<div class="panel"><div class="lbl">동시에 검증 중인 경쟁 가설 ` +
		itoa(len(st.Cycle.Competing)) + `</div>`)
	for _, s := range st.Cycle.Competing {
		state := map[string]string{"open": "검증 중", "won": "채택됨", "fail": "반증됨"}[s.State]
		if s.State == "lost" {
			state = "채택 안 됨"
			if i := strings.LastIndex(s.LostTo, "/"); i >= 0 {
				state += " → " + s.LostTo[i+1:]
			}
		}
		if state == "" {
			state = s.State
		}
		here := ""
		if s.Current {
			here = ` <span class="backlose">현재</span>`
		}
		b.WriteString(`<div class="backrow"><code>` + esc(s.ID) + `</code>` + here +
			`<span class="backlab">` + esc(clip(s.Hypothesis, 60)) + `</span>` +
			`<span class="backlose">반증: ` + esc(clip(s.RefutesIf, 50)) + ` · ` + esc(state) + `</span></div>`)
	}
	b.WriteString(`</div>`)
	return b.String()
}

// statusCardHTML — 통짜 페이지(문서 + 스타일 + 카드). `gil status --card` 와, 저장소를 이미
// 아는 자리에서 리소스를 읽을 때 쓴다.
func statusCardHTML(st statusOut) string {
	return statusCardDocHead() + `<body>` + statusCardBodyHTML(st) + `</body>`
}

// 팔레트는 **한 벌씩만 쓴다.** 같은 색을 CSS 에 두 번 적으면(미디어 쿼리 하나, 명시 테마
// 하나) 다음에 한쪽만 고쳐지고, 그러면 호스트가 테마를 말해 준 사람과 안 말해 준 사람이
// 다른 화면을 본다. CSS 는 선언 블록을 재사용할 방법이 없으니 Go 에서 잇는다.
const cardVarsLight = `--bg:#fff;--fg:#26262a;--dim:#6f6e69;--line:#dedcd4;--card:#f1efe8;` +
	`--warn-bg:#fff6e5;--warn-fg:#7a4d00;--warn-line:#f0d9a8;` +
	`--wait-bg:#eaf2ff;--wait-fg:#12406b;--wait-line:#bcd6f5;--code:#f1efe8;--panel:#fff;--acc:#444441;--acc-fg:#fff`

const cardVarsDark = `--bg:#17171a;--fg:#e9e7e1;--dim:#9b9992;--line:#3a3a3d;--card:#232326;` +
	`--warn-bg:#3a2a12;--warn-fg:#ffd79a;--warn-line:#7a5a24;` +
	`--wait-bg:#12283f;--wait-fg:#bcd9ff;--wait-line:#2a557f;--code:#2f2f33;--panel:#2e2e32;--acc:#d3d1c7;--acc-fg:#26262a`

// statusCardDocHead — 문서 껍데기와 스타일. **카드 조각과 갈라 둔다** — 앱이 조각만 받아
// 그려 넣을 때 스타일은 이미 템플릿에 있어야 한다(조각마다 스타일을 실어 보내면 같은 CSS 가
// 호출마다 왕복한다).
//
// **테마는 호스트가 말해 주면 그것이 이긴다.** 샌드박스 iframe 의 `prefers-color-scheme` 은
// OS·브라우저의 것이지 호스트 앱의 것이 아니다 — 사람이 앱을 어둡게 해 두고 OS 는 밝게 둔
// 흔한 조합에서, 어두운 화면 한가운데 흰 카드가 선다. 그래서 `data-theme` 이 양쪽 방향으로
// 미디어 쿼리를 이긴다(밝게 고정한 사람이 밤에 어두워지지도 않게).
func statusCardDocHead() string {
	return `<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root,:root[data-theme="light"]{` + cardVarsLight + `}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){` + cardVarsDark + `}}
:root[data-theme="dark"]{` + cardVarsDark + `}
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

/* 렌더된 본문. .orig 의 pre-wrap 을 끈다 — 진짜 요소를 그리는 자리라 원문 줄바꿈을
   그대로 지키면 표·리스트 사이에 빈 줄이 겹쳐 쌓인다. */
/* 색도 되돌린다. .orig 는 원래 '곁들이는 원문' 이라 흐린 톤인데, 렌더된 보고서는 곁들이는
   것이 아니라 **판단의 재료 그 자체**다(pending 의 물음, verify 의 측정 기록). 위계는 크기가
   진다 — 머리 문장은 .big 이 더 크다. */
.md{white-space:normal;color:var(--fg)}
.md>*:first-child{margin-top:0}
.md>*:last-child{margin-bottom:0}
.md p{margin:.5em 0}
.md h1,.md h2,.md h3,.md h4,.md h5,.md h6{margin:.9em 0 .35em;font-size:14px;color:var(--fg)}
.md h1{font-size:16px}.md h2{font-size:15px}
.md ul,.md ol{margin:.4em 0;padding-left:20px}
.md li{margin:2px 0}
.md blockquote{margin:.5em 0;padding:2px 0 2px 10px;border-left:2px solid var(--line)}
.md pre.code{margin:.6em 0;padding:9px 11px;border-radius:8px;background:var(--code);
 overflow-x:auto;white-space:pre;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
/* 표는 카드 폭을 넘길 수 있다 — 제 칸 안에서 가로로 구른다(페이지가 흔들리지 않게). */
.md table{display:block;overflow-x:auto;border-collapse:collapse;margin:.6em 0;max-width:100%}
.md th,.md td{border:1px solid var(--line);padding:4px 9px;text-align:left;
 font-size:12.5px;white-space:nowrap}
.md th{background:var(--card);font-weight:600}
/* 그림은 이 본문의 몸이다 — 카드 폭에 맞추되 잘라내지 않는다. */
.md .mdimg{display:block;max-width:100%;height:auto;margin:.6em 0;border-radius:8px}
.md .mdnote{display:block;margin:.5em 0;font-size:12px;color:var(--warn-fg);
 background:var(--warn-bg);border:1px solid var(--warn-line);border-radius:8px;padding:6px 9px}
.md a{color:inherit}
` + interviewCardCSS + `
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
		//
		// **명령줄은 여기에도 안 온다.** 예전엔 `waiting_for_human.how_to_answer` 를 그대로
		// 실었고, 그러면 카드가 `gil approve` · `gil reject --to <조상 define>` 두 줄을
		// 그렸다 — 바로 그 두 줄을 도는 버튼 **바로 위에**. 사람이 읽을 이유 없는 줄이
		// 화면에서 가장 눈에 띄는 자리를 차지했고, `<조상 define>` 같은 자리표시자는
		// 비개발자에게는 답이 아니라 새 물음이다. 그 문자열은 데이터에 그대로 있다 —
		// 그건 에이전트가 읽고 치는 값이다.
		if st.Waiting != nil {
			// **인터뷰는 글이 아니라 폼이다.** 옛 카드는 "에이전트가 여는 인터뷰 창구에
			// 적으면"이라고 말했는데, 이 표면에는 그 창구가 없었다(뷰어는 청해야 뜨고
			// 시작하는 사람에겐 창이 없다, Elicitation 은 Desktop 이 못 띄운다). 가리키는
			// 것이 실재하지 않는 안내였다 — 그래서 **카드가 그 창구가 된다**.
			if form := interviewFaceHTML(st.Waiting); form != "" {
				b.WriteString(form)
			} else {
				b.WriteString(`<div class="box wait"><div class="t">⏳ 사람의 판단이 필요하다</div><div>` +
					esc(st.Waiting.What) + `</div><div style="margin-top:6px">` +
					esc(waitHumanLine(st.Waiting)) + `</div></div>`)
			}
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
			// kind 이름 옆에 **뜻 한 마디**를 붙인다. 이름은 gil 의 문법이라 못 바꾸고,
			// 이름만 놓으면 이 도구를 아는 사람만 읽을 수 있다 — 카드는 도구를 모르는 사람이
			// 판단하려고 보는 화면이다.
			label := st.Step.Kind
			if g := kindGloss[st.Step.Kind]; g != "" {
				label += " · " + g
			}
			b.WriteString(`<span class="sep">›</span>` + esc(st.Step.ID) +
				`<span class="kind k-` + esc(st.Step.Kind) + `">` + esc(label) + `</span>`)
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

	// **다음 한 수는 카드에 없다**(상현님). 이 화면은 사람이 보는 것이고, 사람이 정할 것은
	// 승인·기각 두 갈래다 — 그 자리는 버튼이 쓴다. gil 명령줄은 에이전트가 칠 것이라 카드에
	// 두면 사람에게는 읽을 이유 없는 줄이 되고, 화면에서 가장 길어지는 칸이 된다.
	// (데이터에는 그대로 있다 — status --json 의 next 는 에이전트가 읽고 그대로 친다.)

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
	switch st.Step.Kind {
	case "define":
		return defineCardBody(st)
	case "hypothesis":
		return hypothesisCardBody(st)
	case "verify":
		return verifyCardBody(st)
	case "analyze":
		return analyzeCardBody(st)
	case "pending":
		return pendingCardBody(st)
	case "success":
		return successCardBody(st)
	case "fail":
		return failCardBody(st)
	}
	// 알 수 없는 kind. **없는 얼굴을 있는 척 그리지 않는다** — 무엇에 서 있는지만 말하고
	// 판정은 사람에게 넘긴다.
	var b strings.Builder
	b.WriteString(`<div class="panel"><div class="lbl">이 단계 종류의 표시 규칙이 아직 없다</div>` +
		`<div class="none">` + esc(st.Step.Kind) + ` — 이 스텝이 무엇을 담는지는 gil status --json 이 말한다.</div></div>`)
	b.WriteString(statusActionsHTML(st))
	return b.String()
}

// verifyCardBody — **쟀다, 무엇이 나왔나** (status-card.md).
//
// 시제가 이 카드의 전부다. 지금까지 여기엔 얼굴이 없어서 공통 본문이 "재는 중 — 무엇이
// 관측되면 틀리나"를 그렸다. 그런데 verify 스텝은 **판정과 함께 태어난다**(문법이 그걸
// 요구한다: `--verdict supported|refuted` 와 `--falsify-met|--falsify-unmet <관측>`). 이미
// 지나간 측정을 "재는 중"이라 부르면 사람은 아직 결과가 없는 줄 안다 — 문서가 hypothesis·
// analyze 사이에서 경계한 바로 그 병이고, 그 사이에 낀 이 카드가 제일 크게 앓았다.
//
// **되돌아갈 후보는 여기 없다.** 되돌릴지는 analyze 에서 정한다(status-card.md).
func verifyCardBody(st statusOut) string {
	var b strings.Builder
	m := st.Cycle.Measured

	b.WriteString(`<div class="panel"><div class="lbl">측정 결과 — 무엇이 관측됐나</div>`)
	if m != nil && m.Verdict != "" {
		b.WriteString(`<div class="big">` + esc(verdictWord(m.Verdict)) + `</div>`)
	} else {
		b.WriteString(`<div class="none">판정이 기록에 없다 — 이 측정이 가설을 지지했는지 반증했는지 알 수 없다.</div>`)
	}
	// 판정과 관측은 **따로** 적힌다(규칙 17). 판정만 보이고 관측이 사라지면 사람은 그
	// 판정을 검산할 수 없다 — 승인을 누르는 근거가 통째로 없어진다.
	if m != nil && m.Falsify != "" {
		line := falsifyWord(m.Falsify)
		if m.Observed != "" {
			line += " · 관측: " + m.Observed
		}
		b.WriteString(`<div class="orig">` + esc(line) + `</div>`)
	}
	b.WriteString(`</div>`)

	// **과거형이다.** 이 조건은 가설이 심어 둔 것이고 방금 지나갔다.
	b.WriteString(`<div class="panel"><div class="lbl">반증조건 — 무엇이 관측되면 기각하기로 했나</div>`)
	if r := st.Cycle.RefutesIf; r != "" {
		b.WriteString(`<div class="big">` + mdInlineHTML(r) + `</div>`)
	} else {
		b.WriteString(`<div class="none">반증조건이 없다 — 이 측정으로는 가설을 기각할 수 없다.</div>`)
	}
	b.WriteString(`</div>`)

	// 고정한 설계. **깨진 것은 강한 신호다** — 잰 것이 못박은 것과 다르면 이 측정은 다른
	// 물건을 잰 것이고, 그게 사람이 기각할 가장 큰 근거다. 그런데 색으로 소리치지는 않는다:
	// 색은 kind 에서만 뜻을 갖는다(status-card.md). 신호는 ⚠ 한 글자가 진다.
	if st.Cycle.Plan != "" || (m != nil && m.PlanOutcome != "") {
		b.WriteString(`<div class="panel"><div class="lbl">측정 전에 정한 방법 — 그대로 실행됐나</div>`)
		switch {
		case m != nil && m.PlanOutcome == "broke":
			b.WriteString(`<div class="big">⚠ 그대로 실행되지 않았다 — 계획한 방법과 실제가 다르다</div>`)
			if m.PlanDiff != "" {
				b.WriteString(`<div class="orig">무엇이 달랐나: ` + esc(m.PlanDiff) + `</div>`)
			}
		case m != nil && m.PlanOutcome == "held":
			b.WriteString(`<div class="big">그대로 실행됐다</div>`)
		default:
			b.WriteString(`<div class="none">정한 방법대로 실행됐는지에 대한 답이 기록에 없다.</div>`)
		}
		if st.Cycle.Plan != "" {
			b.WriteString(`<div class="orig">정한 방법: ` + mdInlineHTML(st.Cycle.Plan) + `</div>`)
		}
		b.WriteString(`</div>`)
	}

	// 측정 보고서 원문. **자르지 않는다** — 표·수치가 이 스텝의 몸이고, 접는 것은 사람의 몫이다.
	if body := st.Step.Body; body != "" {
		b.WriteString(`<div class="panel"><div class="lbl">측정 기록 — 원문</div>` +
			`<div class="orig md">` + mdToHTML(body) + `</div></div>`)
	}

	b.WriteString(competingHTML(st))
	b.WriteString(statusActionsHTML(st))
	return b.String()
}

// analyzeCardBody — **그래서 무엇을 알았나, 그리고 어디로 되돌아갈 수 있나** (status-card.md).
//
// 결론(`finding`)은 gil 이 문법으로 요구하는 값이다 — 상현님 실사용에서 analyze 가 결론 없이
// 지나가고 곧장 define 으로 되돌아간 뒤 필수가 됐다. 그런데 카드에는 그 문장이 **한 번도 뜬
// 적이 없다**. 재분기가 딛는 문장이 화면에서 빠져 있었다.
//
// 반증조건 **전문은 빼고** 측정 한 줄만 남긴다: 여기서 그 조건은 이미 지나갔고, 사람이 볼
// 것은 "무엇이 관측됐고 그래서 무엇을 알았나"다.
func analyzeCardBody(st statusOut) string {
	var b strings.Builder

	b.WriteString(`<div class="panel"><div class="lbl">결론 — 이 분석이 밝힌 것</div>`)
	if f := st.Step.Finding; f != "" {
		b.WriteString(`<div class="big">` + mdInlineHTML(f) + `</div>`)
	} else {
		b.WriteString(`<div class="none">결론 문장이 없다 — 다음 가설이 근거로 삼을 문장이 없다.</div>`)
	}
	if body := st.Step.Body; body != "" {
		b.WriteString(`<div class="orig md">` + mdToHTML(body) + `</div>`)
	}
	b.WriteString(`</div>`)

	if m := st.Cycle.Measured; m != nil {
		b.WriteString(measurePanel("근거가 된 측정 — "+m.Step, m,
			hypothesisNote(st, "검증한 가설: ")))
	}

	// **되돌아갈 자리는 여기서 처음 뜬다.** analyze 가 그 판단을 하는 자리다(status-card.md).
	// 버튼은 달지 않는다 — 다시 분기하려면 `--inherit <이 기각에서 알게 된 것>` 이 필요하고 그건 판단이지
	// 클릭으로 채울 값이 아니다. 없는 문법을 버튼으로 지어내지 않는 것과 같은 규칙이다.
	if len(st.Rollback) > 0 {
		b.WriteString(`<div class="panel"><div class="lbl">되돌아갈 수 있는 단계 — 고르면 그 뒤 단계가 버려진다</div>`)
		for _, c := range st.Rollback {
			lose := "버릴 것 없음"
			if len(c.Discards) > 0 {
				lose = "버려진다: " + foldRanges(c.Discards)
			}
			b.WriteString(`<div class="backrow"><code>` + esc(c.ID) + `</code>` +
				`<span class="backlab">` + esc(clip(c.Label, 70)) + `</span>` +
				`<span class="backlose">` + esc(lose) + `</span></div>`)
		}
		b.WriteString(`</div>`)
	}

	b.WriteString(competingHTML(st))
	b.WriteString(statusActionsHTML(st))
	return b.String()
}

// pendingCardBody — **사람이 정할 것 하나. 나머지는 전부 뺀다** (status-card.md).
//
// 이 카드는 gil 전체에서 사람이 실제로 값을 더하는 두 자리 중 하나다. 그런데 지금까지 그
// 자리에 뜬 것은 공통 본문의 "재는 중 — 무엇이 관측되면 틀리나" 였고, **에이전트가 사람에게
// 물으려고 쓴 보고서(step.body)는 화면에 한 글자도 안 나왔다.** 물음이 없는 물음 화면이었다.
func pendingCardBody(st statusOut) string {
	var b strings.Builder

	b.WriteString(`<div class="panel"><div class="lbl">무엇을 묻는가</div>`)
	if s := humanLabel(st.Step.Subject); s != "" {
		b.WriteString(`<div class="big">` + esc(s) + `</div>`)
	}
	if body := st.Step.Body; body != "" {
		b.WriteString(`<div class="orig md">` + mdToHTML(body) + `</div>`)
	} else {
		// gil 자신이 이 자리에서 "본문이 얇다 — pending 스텝은 보고서여야 한다"고 경고한다.
		// 카드도 같은 것을 말한다: 물음만 있고 재료가 없으면 사람은 판단할 수 없다.
		b.WriteString(`<div class="none">보고서가 없다 — 판단할 재료 없이 승인·기각을 묻고 있다.</div>`)
	}
	b.WriteString(`</div>`)

	// 무엇에 비추어 판단하나. 기준이 없으면 승인·기각을 묻는 물음 자체가 의미가 없다.
	b.WriteString(`<div class="panel"><div class="lbl">무엇에 비추어 판단하나 — 이 체인이 풀렸다고 할 기준</div>`)
	if c := st.Chain.Criterion; c != "" {
		b.WriteString(`<div class="big">` + mdInlineHTML(c) + `</div>`)
	} else {
		b.WriteString(`<div class="none">이 체인엔 사람이 세운 판정 기준이 없다 — 무엇에 비추어 판단하라는 것인지가 기록에 없다.</div>`)
	}
	b.WriteString(`</div>`)

	b.WriteString(statusActionsHTML(st))
	return b.String()
}

// successCardBody — **이 사이클이 무엇을 남겼나** (status-card.md).
//
// 작업 중인 다섯과 순서가 뒤집힌다: 다음 한 수가 아니라 **판정 기준과의 대조**가 본문이다.
// 그래서 `toward` 를 기준 문장과 한 칸에 나란히 놓는다 — 떼어 놓으면 "얼마나 다가섰나"가
// 무엇에 비추어 한 말인지가 사라진다.
func successCardBody(st statusOut) string {
	var b strings.Builder

	b.WriteString(`<div class="panel"><div class="lbl">판정 기준에 얼마나 접근했나</div>`)
	if t := st.Step.Toward; t != "" {
		b.WriteString(`<div class="big">` + mdInlineHTML(t) + `</div>`)
	} else {
		// **사람이 pending 을 승인해 gil 이 만든 success 에는 회고가 없다** — approve 는
		// --toward·--next-design 을 묻지 않는다. 빈 칸을 지우면 회고를 쓴 종결과 안 쓴
		// 종결이 화면에서 같아 보인다. 없다는 것도 사실이라 말한다.
		b.WriteString(`<div class="none">판정 기준과 대조한 기록이 없다 — 사람이 pending(사람 판단 대기)을 승인해 만들어진 종결에는 gil 이 그것을 묻지 않는다.</div>`)
	}
	if c := st.Chain.Criterion; c != "" {
		b.WriteString(`<div class="orig">체인 판정 기준: ` + mdInlineHTML(c) + `</div>`)
	}
	b.WriteString(`</div>`)

	if n := st.Step.NextDesign; n != "" {
		b.WriteString(`<div class="panel"><div class="lbl">다음 설계</div><div class="big">` +
			mdInlineHTML(n) + `</div></div>`)
	}

	// 근거가 된 측정 — 이 종결이 무엇 위에 섰는지. 한 칸이면 충분하다.
	if m := st.Cycle.Measured; m != nil {
		b.WriteString(measurePanel("근거가 된 측정", m, hypothesisNote(st, "검증한 가설: ")))
	}
	if body := st.Step.Body; body != "" {
		b.WriteString(`<div class="panel"><div class="lbl">종결 기록 — 원문</div>` +
			`<div class="orig md">` + mdToHTML(body) + `</div></div>`)
	}

	b.WriteString(statusActionsHTML(st))
	return b.String()
}

// failCardBody — **왜 죽었나, 어디로 물러서나, 무엇을 배웠나** (status-card.md).
//
// 어조가 이 카드의 값이다. **fail 은 죽음이 아니라 발견이다** — 죽은 것은 이 가설이지
// 사이클이 아니다. 카드가 실패를 사과하는 어조로 쓰이면 사람은 되돌리기를 손실로 읽고,
// 그러면 앞으로만 가려는 압력이 생긴다. gil 이 막으려는 바로 그것이다.
//
// **다음 설계(`next_design`)는 그리지 않는다**(status-card.md). 기각된 분기 위에 그것을
// 크게 놓으면 화면이 "이제 앞으로 간다"고 말하는데, 옳은 읽기는 "물러서서 다시 갈라진다"다.
// 데이터에는 그대로 있다 — 그건 에이전트가 읽는 값이다.
func failCardBody(st statusOut) string {
	var b strings.Builder
	m := st.Cycle.Measured

	b.WriteString(`<div class="panel"><div class="lbl">왜 기각됐나</div>`)
	if m != nil && m.Observed != "" {
		b.WriteString(`<div class="big">` + esc(m.Observed) + `</div>`)
	} else {
		b.WriteString(`<div class="none">기각의 근거가 된 관측이 기록에 없다.</div>`)
	}
	if r := st.Cycle.RefutesIf; r != "" {
		line := "반증조건: " + r
		// 조건과 관측을 나란히 두기만 하면 사람이 둘을 대조해야 한다. gil 은 그 대조를
		// 이미 기록해 두었다(`--falsify-met`) — 적어 두었으면 말한다.
		if m != nil && m.Falsify == "met" {
			line += " → 이 조건이 실제로 관측됐다"
		}
		b.WriteString(`<div class="orig">` + esc(line) + `</div>`)
	}
	if body := st.Step.Body; body != "" {
		b.WriteString(`<div class="orig md">` + mdToHTML(body) + `</div>`)
	}
	b.WriteString(`</div>`)

	// 복귀 단계 — **어디로 되돌아가나.** 이 칸이 없으면 사람은 반증된 뒤에 그래프를 뒤져
	// 스텝 번호를 세게 된다(비개발자에게 가장 넘기 어려운 자리다).
	b.WriteString(`<div class="panel"><div class="lbl">어느 단계로 되돌아가나 — 가설을 세울 때 미리 정한 복귀 단계</div>`)
	switch to := backOfCurrent(st); {
	case to == "pending":
		b.WriteString(`<div class="big">아직 정해지지 않았다</div>` +
			`<div class="orig">다음 가설을 세울 때 확정한다 — 지금 지어내지 않는다.</div>`)
	case to != "":
		line := to + " 단계로 되돌아간다"
		var extra string
		for _, c := range st.Rollback {
			if c.ID == to {
				line += " — " + clip(c.Label, 70)
				if len(c.Discards) > 0 {
					extra = "버려진다: " + foldRanges(c.Discards)
				}
				break
			}
		}
		b.WriteString(`<div class="big">` + esc(line) + `</div>`)
		if extra != "" {
			b.WriteString(`<div class="orig">` + esc(extra) + `</div>`)
		}
	default:
		b.WriteString(`<div class="none">되돌아갈 단계가 기록에 없다.</div>`)
	}
	// 어조. 여기서 "실패했다"고 쓰면 사람은 되돌리기를 손실로 읽는다. 그리고 **사이클이
	// 살아 있다고 단정하지도 않는다** — 사람이 이 define 자체를 접기로 할 수도 있다.
	// 사실만 적는다: 이 자리에서 다른 갈래를 낼 수 있다는 것.
	b.WriteString(`<div class="orig">기각된 것은 이 가설이다 — 이 단계에서 다른 가설을 세울 수 있다.</div>`)
	b.WriteString(`</div>`)

	if t := st.Step.Toward; t != "" {
		b.WriteString(`<div class="panel"><div class="lbl">이 기각으로 알게 된 것</div>` +
			`<div class="big">` + mdInlineHTML(t) + `</div>`)
		if c := st.Chain.Criterion; c != "" {
			b.WriteString(`<div class="orig">체인 판정 기준: ` + mdInlineHTML(c) + `</div>`)
		}
		b.WriteString(`</div>`)
	}

	b.WriteString(competingHTML(st))
	b.WriteString(statusActionsHTML(st))
	return b.String()
}

// measurePanel — 한 번의 측정을 한 칸에. **판정은 크게, 관측은 그 아래로.**
//
// 짧은 형태(`gil status`)는 이 넷을 한 줄로 잇는다(measureLine). 카드에서 같은 줄을 16px
// 로 키우면 화면에서 가장 긴 칸이 되고, 그러면 판정이 관측에 묻힌다 — 사람이 먼저 볼 것은
// "지지됐나 반증됐나"고, 관측은 그 판정을 검산할 때 읽는 것이다.
func measurePanel(lbl string, m *statusMeasure, note string) string {
	var head []string
	if w := verdictWord(m.Verdict); w != "" {
		head = append(head, w)
	}
	if w := falsifyWord(m.Falsify); w != "" {
		head = append(head, w)
	}
	var b strings.Builder
	b.WriteString(`<div class="panel"><div class="lbl">` + esc(lbl) + `</div>`)
	if len(head) > 0 {
		b.WriteString(`<div class="big">` + esc(strings.Join(head, " · ")) + `</div>`)
	} else {
		b.WriteString(`<div class="none">판정이 기록에 없다.</div>`)
	}
	if m.Observed != "" {
		b.WriteString(`<div class="orig">관측: ` + esc(m.Observed) + `</div>`)
	}
	// 설계가 깨진 것은 뒤 카드에서도 사라지면 안 된다 — 잰 것이 못박은 것과 다르면 그 뒤의
	// 결론·종결이 다 그 위에 서 있다.
	if m.PlanOutcome == "broke" {
		line := "⚠ 정한 방법대로 실행되지 않았다"
		if m.PlanDiff != "" {
			line += ": " + m.PlanDiff
		}
		b.WriteString(`<div class="orig">` + esc(line) + `</div>`)
	}
	if note != "" {
		b.WriteString(`<div class="orig">` + esc(note) + `</div>`)
	}
	b.WriteString(`</div>`)
	return b.String()
}

// hypothesisNote — "이 측정이 무엇을 재려 한 것인가" 한 줄. 없으면 빈 값(칸을 안 만든다).
func hypothesisNote(st statusOut, prefix string) string {
	if st.Cycle == nil || st.Cycle.Hypothesis == "" {
		return ""
	}
	return prefix + clip(st.Cycle.Hypothesis, 120)
}

// backOfCurrent — 지금 선 스텝이 되돌아간 자리(Gil-Backtrack). 띠를 그리는 데이터에 이미
// 있으므로 새 필드를 만들지 않는다 — 같은 사실이 두 자리에 살면 언젠가 갈린다.
func backOfCurrent(st statusOut) string {
	if st.Cycle == nil || st.Step == nil {
		return ""
	}
	for _, n := range st.Cycle.Steps {
		if n.ID == st.Step.ID {
			return n.Back
		}
	}
	return ""
}

// waitHumanLine — 사람이 무엇을 하면 되는지, **명령줄 없이** 한 줄.
//
// `waiting_for_human.how_to_answer` 는 에이전트가 읽고 치는 값이다(`gil approve`,
// `gil reject --to <조상 define>`). 그걸 카드에 그대로 실으면 자리표시자가 사람에게
// 답 대신 새 물음으로 도착한다 — 게다가 그 두 줄을 실제로 도는 버튼이 바로 아래 있다.
func waitHumanLine(w *statusWaiting) string {
	switch w.Kind {
	case "approval":
		return "아래 승인·기각 버튼이 그 판정을 그대로 옮긴다. 사람의 답 전엔 이 사이클을 못 이어간다."
	case "interview":
		return "체인의 기준 문서에 대한 답이다. 에이전트가 여는 인터뷰 창구에 적으면 그때부터 사이클을 열 수 있다."
	}
	return ""
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
		b.WriteString(`<div class="big">` + mdInlineHTML(p) + `</div>`)
	} else {
		b.WriteString(`<div class="none">이 사이클엔 목적 문장이 없다.</div>`)
	}
	// 원문은 **반드시 함께** 둔다. 요약만 두면 지어내서 감춘 것이 된다.
	if body := st.Step.Body; body != "" {
		b.WriteString(`<div class="orig md">` + mdToHTML(body) + `</div>`)
	}
	b.WriteString(`</div>`)

	b.WriteString(`<div class="panel"><div class="lbl">전제 — 앞에서 확인된 어떤 사실에서 이 문제가 나왔나</div>`)
	if inh := st.Cycle.Inherit; inh != "" {
		b.WriteString(`<div class="big">` + mdInlineHTML(inh) + `</div>`)
	} else {
		// 없는 것을 채우지 않되, **없다는 사실은 말한다.** 빈 칸을 지우면 근거가 없다는 것이
		// 화면에서 사라지고, 그건 근거가 있는 것과 같아 보인다.
		b.WriteString(`<div class="none">앞에서 확인된 사실이 기록에 없다 — 이 문제 정의는 앞 사이클의 결론에 근거하지 않는다.</div>`)
	}
	b.WriteString(`</div>`)

	// 사람이 정하는 두 갈래. **라벨은 일곱 kind 에서 같고, 뒤에서 도는 것은 다르다** —
	// 그래서 부제로 무슨 일이 일어나는지 적는다(라벨은 통일하되 숨기지 않는다).
	// 부제는 붙이지 않는다(상현님). 승인은 가설로 이어지고 기각은 문제정의를 다시 세운다 —
	// 그건 이 자리에 서 본 사람이면 아는 것이고, 매번 설명하면 화면만 길어진다.
	b.WriteString(statusActionsHTML(st))
	return b.String()
}

// (codeify 는 지웠다. "gil …" 줄을 <code> 로 감싸 사람이 칠 수 있는 것과 읽을 것을 눈으로
// 가르던 헬퍼였는데, 카드가 **명령줄을 아예 안 그리게** 되면서 부를 자리가 없어졌다.
// 안 쓰는 채로 두면 다음 세션이 "여기 명령줄을 그려도 되는구나"로 읽는다.)

func escHTML(s string) string {
	return strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;", `"`, "&quot;").Replace(s)
}
