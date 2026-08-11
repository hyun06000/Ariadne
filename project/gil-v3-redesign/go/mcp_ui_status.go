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
		Name:        "gil_status",
		Annotations: toolAnn("gil_status"),
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
		lines := statusLines(st)
		// **도구가 자기 표면에 대해 아는 것을 말한다.** 이 줄이 없으면 에이전트는 "곁에
		// 띄워 드릴까요"를 말할 근거가 없고, 근거 없이 말하면 없는 화면을 가리키게 된다.
		// 아직 화면이 안 떴으면 아무 말도 안 한다(모르는 것은 말하지 않는다).
		if ln := uiHostLine(); ln != "" {
			lines = append(lines, ln)
		}
		// 이 줄들이 structuredContent 에도 실린다 — **여기서가 아니라** 미들웨어에서
		// (mcp_lead.go 의 mirrorTextIntoStructured). 이 호스트는 structuredContent 가 있으면
		// 그것만 모델에게 주고 Content 를 버려서, 지금까지 이 줄들이 한 글자도 안 닿았다.
		// 툴마다 손으로 실으면 다음에 생기는 툴이 또 샌다 — 열거는 늘 뒤늦다.
		res := &mcp.CallToolResult{
			Content:           []mcp.Content{&mcp.TextContent{Text: strings.Join(lines, "\n")}},
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
		if _, err := gitTryIn(repo, "rev-parse", "--git-dir"); err == nil {
			setRepoDir(repo)
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
	// 없다. 필요할 때 켠다 — 두 창구가 있다(uiProbeOn): `GIL_UI_PROBE=1` 환경변수, 또는
	// 그 저장소의 `.git/gil/ui-probe` 파일. 호스트가 서버의 env 를 제가 정해 버리는 표면에서는
	// 뒤엣것이 유일하게 사람 손이 닿는 스위치다.
	probe := uiProbeOn()
	probeJS := "false"
	if probe {
		probeJS = "true"
	}
	return statusCardDocHead() + `<body><div id="gil-mode" class="modebar" hidden></div>
<div id="gil-card" class="card"><div class="lbl">gil</div>
<div class="none">상태를 가져오는 중…</div></div>
<script>
(function(){
  var host=window.parent, id=0, pending={}, fetching=false, fetches=0, drawn=false;
  // drafts: 사람이 폼에 쓰던 것. **메모리에 둔다** — 샌드박스 iframe 의 localStorage 는
  // 호스트마다 있고 없고가 다르고, 없으면 예외도 없이 그냥 안 된다(뷰어는 브라우저 위라
  // 그걸 쓸 수 있었다). lastInput: 마지막 타건 시각 — 쓰는 중에는 다시 그리지 않는다.
  var drafts={}, lastInput=0, holdTimer=null, refreshTimer=null;
  // HOST: 호스트가 핸드셰이크에서 밝힌 것. 지금까지 theme 한 칸만 읽고 나머지를 **버렸다** —
  // 그래서 이 화면이 풀스크린으로 설 수 있는지, 곁에 띄울 수 있는지(pip), 호스트가 제 색을
  // 알려주는지를 우리가 몰랐다. 모르면 짓지 못한다: 먼저 받아 두고, 받은 것 안에서만 청한다.
  // asked/grant/err/why — **청한 것과 받은 것을 갈라 적는다.** 지금까지 이 칸이 없어서,
  // 카드가 인라인으로 남았을 때 그것이 ㄱ) 호스트가 거절한 것인지 ㄴ) 이 호스트가 그
  // 요청 자체를 안 받는 것인지 ㄷ) 우리가 아예 안 청한 것인지 **아무도 구별할 수 없었다.**
  // 이 저장소가 여러 번 적은 그대로다: 추측하지 않으려면 계기가 있어야 한다.
  //
  // ua/plat — **이 화면이 어느 호스트에 떠 있나.** 규범이 hostContext.userAgent(호스트
  // 애플리케이션 식별자)·platform(web·desktop·mobile)으로 주는데 지금까지 버렸다. 그래서
  // 표시모드를 읽고도 **그 값이 어느 표면의 것인지 알 수 없었다** — 한 gil 서버를 여러
  // 표면이 나눠 쓰고, 보고는 전역 한 칸에 덮어쓰이기 때문이다(실측 2026-08-10). 재는 값에
  // 출처가 없으면 그건 잰 것이 아니다.
  //
  // fs* — **풀스크린은 pip 과 따로 적는다.** 하나의 칸에 겹쳐 적으면 "곁에 세우기는 거절,
  // 크게 보기는 승인" 같은 갈래가 화면 밖에서 한 값으로 뭉개진다. 그리고 이 둘은 청하는
  // 방식 자체가 다르다 — pip 은 화면이 스스로 청하고(곁에 서는 것이 기본), 풀스크린은
  // **사람이 눌러야** 청한다(정본 패턴: availableDisplayModes 에 있으면 버튼을 보이고,
  // 누르면 그때 requestDisplayMode). 지금까지 우리는 버튼 없이 자동으로만 청해 봤다.
  //
  // ln* — **링크를 여는 것도 따로 적는다.** 2026-08-11 에 pip 이 없다는 것이 확정되면서
  // (호스트가 여는 모드: inline·fullscreen), 대화 곁에 계속 서 있는 화면은 카드 안에서
  // 원리적으로 불가능해졌다. 남은 길은 **카드가 바깥의 것을 여는 것**이고, 이 호스트는
  // 핸드셰이크에서 openLinks 를 할 수 있다고 밝혔다. 그런데 그것이 https 만인지
  // 커스텀 스킴(gil://)까지인지는 규범이 안 정한다 — "Invalid URL" 오류가 있다는 것만
  // 적혀 있다. 정하지 않은 것은 재야 안다.
  var HOST={modes:[],mode:"",dims:null,vars:0,caps:[],asked:"",grant:"",err:"",why:"",ua:"",plat:"",
            fsAsked:"",fsGrant:"",fsErr:"",fsWhy:"",
            lnAsked:"",lnGrant:"",lnErr:"",lnWhy:""};
  var VER=` + jsString(gilVersion) + `, seen=[], repo="", PROBE=` + probeJS + `;
  function slot(){ return document.getElementById("gil-card"); }
  function send(m){ if(host!==window) host.postMessage(Object.assign({jsonrpc:"2.0"},m),"*"); }
  function notify(m,p){ send({method:m,params:p||{}}); }
  // **내용을 잰다 — 칸을 재지 않는다.** 칸을 채우는 모드에서는 documentElement.scrollHeight
  // 가 곧 칸의 높이라, 그걸 보고하면 "지금 크기가 딱 맞다"는 말이 되어 영영 안 자란다.
  // 카드 조각의 실제 높이를 재면 그 고리가 끊긴다.
  function reportSize(){
    var el=slot(), de=document.documentElement;
    var h=de.scrollHeight, w=de.scrollWidth;
    if(el){
      var r=el.getBoundingClientRect();
      // 바깥 여백(body padding)을 더해 준다 — 안 더하면 매번 조금씩 잘린다.
      h=Math.max(h, Math.ceil(r.height)+24);
      w=Math.max(w, Math.ceil(r.width)+24);
    }
    notify("ui/notifications/size-changed",{width:w,height:h});
  }

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

  // ── 조각을 갈아끼울 때 **사람이 쓰던 것을 잃지 않는다** ────────────────────────
  //
  // 조각 교체는 innerHTML 이라 DOM 이 통째로 새것이 된다 — 폼에 적던 문장도 함께 사라진다.
  // 뷰어는 이걸 윈도우 필드테스트에서 값을 치르고 배웠고(초안 저장 + 쓰는 중 새로고침 보류),
  // 카드는 그걸 모른 채였다. 지금까지 안 아팠던 것은 **카드가 아예 다시 안 그려져서**다 —
  // 아래 refresh 가 그걸 고치면 이 보존이 없을 때 비로소 답이 날아간다. 그래서 둘은 같은
  // 커밋이어야 한다.
  function harvest(){
    var s=slot(); if(!s) return;
    var boxes=s.querySelectorAll("[data-iv]");
    for(var i=0;i<boxes.length;i++){
      var iv=boxes[i].getAttribute("data-iv"), d=drafts[iv]||(drafts[iv]={});
      var els=boxes[i].querySelectorAll("[data-q]");
      for(var k=0;k<els.length;k++){
        var el=els[k], key=el.getAttribute("data-q");
        if(el.type==="checkbox") d[key]=el.checked;
        else if(el.type==="radio"){ if(el.checked) d[key]=el.value; }
        else if((el.value||"")!=="") d[key]=el.value;
      }
    }
    // **시작 화면의 이름 칸도 사람이 쓰던 것이다.** 위 문단이 "둘은 같은 커밋이어야 한다"고
    // 적어 둔 그 규칙을, 칸을 새로 만들면서 그대로 어겼다 — 카드가 다시 그려질 때마다 적던
    // 이름이 사라지고 만들 자리 미리보기가 되돌아갔다(상현님 실사용). **보존은 새 입력 칸마다
    // 다시 챙겨야 하는 것**이지, 한 번 세우면 따라오는 것이 아니다.
    var sb=s.querySelector("[data-start]");
    if(sb){
      var sd=drafts.__start||(drafts.__start={});
      var nm=sb.querySelector("[data-start-name]"), pl=sb.querySelector("[data-start-place]");
      if(nm&&(nm.value||"")!=="") sd.name=nm.value;
      if(pl&&(pl.value||"")!=="") sd.place=pl.value;
    }
  }
  function restore(){
    var s=slot(); if(!s) return;
    var boxes=s.querySelectorAll("[data-iv]");
    for(var i=0;i<boxes.length;i++){
      var d=drafts[boxes[i].getAttribute("data-iv")]; if(!d) continue;
      var els=boxes[i].querySelectorAll("[data-q]");
      for(var k=0;k<els.length;k++){
        var el=els[k], v=d[el.getAttribute("data-q")];
        if(v===undefined) continue;
        if(el.type==="checkbox") el.checked=!!v;
        else if(el.type==="radio") el.checked=(el.value===v);
        else el.value=v;
      }
    }
  }
  // 되돌린 뒤에는 **미리보기도 같이 맞춘다** — 값만 되돌리고 그림을 안 맞추면 사람은 자기가
  // 친 이름과 다른 자리를 보게 된다(그 둘이 갈리는 것이 이 화면에서 제일 나쁜 일이다).
  function restoreStart(){
    var s=slot(); if(!s) return;
    var sb=s.querySelector("[data-start]"); if(!sb) return;
    var sd=drafts.__start;
    if(sd){
      var nm=sb.querySelector("[data-start-name]"), pl=sb.querySelector("[data-start-place]");
      if(nm&&sd.name) nm.value=sd.name;
      if(pl&&sd.place) pl.value=sd.place;
    }
    // **위임에만 기대지 않는다.** document 위의 위임 하나로 충분해야 맞지만, 실사용에서
    // 미리보기가 안 따라온 판이 있었다(상현님 — 가짜 호스트에서는 같은 코드가 따라왔다).
    // 무엇이 막았는지 아직 못 갈랐으므로, **막힐 수 있는 자리를 줄인다**: 칸에 직접 걸고,
    // 타건 신호도 셋으로 넓힌다(IME 조합 중에는 input 이 안 오는 구성이 있다).
    // 재는 값이 없을 때 고르는 쪽은 "덜 영리한 쪽"이다.
    var els=sb.querySelectorAll("[data-start-name],[data-start-place]");
    for(var i=0;i<els.length;i++){
      var el=els[i];
      el.oninput=el.onkeyup=el.onchange=function(){ startBeat("event"); syncStartPreview(sb); };
    }
    startBeat("bind:"+els.length);
    syncStartPreview(sb);
  }
  // **계기.** 미리보기가 실제 호스트에서만 안 따라왔고 세 번 추측해서 세 번 틀렸다.
  // 추측을 그만두려면 그 안에서 무슨 일이 나는지 봐야 한다 — 화면이 자기 상태를 서버로
  // 실어 보내고, 서버가 그것을 stderr 로 적는다(호스트 로그에 남는다).
  // 기본은 꺼져 있다: GIL_UI_PROBE=1 일 때만.
  function startBeat(what){
    if(!PROBE) return;
    try{
      var s=slot(), sb=s&&s.querySelector("[data-start]");
      var nm=sb&&sb.querySelector("[data-start-name]");
      var out=sb&&sb.querySelector("[data-start-preview]");
      report("start:"+what+" box="+(sb?"1":"0")+" name="+(nm?"1":"0")+
             " out="+(out?"1":"0")+" val="+((nm&&nm.value)||"")+
             " shown="+((out&&out.textContent)||""));
    }catch(e){ report("start:"+what+" throw="+String(e&&e.message||e)); }
  }
  // 이름 → 만들 자리. 화면은 미리 보여주기만 하고 **판정은 서버가 다시 한다**(placeSlug).
  function syncStartPreview(box){
    if(!box) return;
    var nameEl=box.querySelector("[data-start-name]");
    var placeEl=box.querySelector("[data-start-place]");
    var out=box.querySelector("[data-start-preview]"); if(!out) return;
    var root=(placeEl&&placeEl.value||"").trim() || (nameEl&&nameEl.getAttribute("data-root")) || "";
    var slug=slugPreview(nameEl&&nameEl.value);
    out.textContent=root.replace(/\/+$/,"")+"/"+(slug||"…");
  }
  function paint(html){
    harvest();
    var s=slot(); if(!s) return;
    s.innerHTML=html; restore(); restoreStart(); drawn=true; reportSize();
    maybeAside();
  }

  // ── 곁에 서는 것이 기본이다 (상현님, 2026-08-10) ──────────────────────────
  //
  // 인라인 카드는 **대화와 함께 스크롤돼 올라간다.** 사람이 3번 문항을 쓰다 1번을 다시
  // 보려면 위로 올려야 하고, 승인 버튼은 대화가 길어지면 화면 밖으로 나간다. 브라우저
  // 뷰어가 주던 값 하나가 정확히 "창이 계속 거기 있다"였고 — 그건 그림이 아니라 자리였다.
  //
  // 처음엔 "답할 것이 있을 때만" 청했다. 상현님 판단으로 **기본으로 올린다**: 상태 카드는
  // 원래 곁에 두고 일하는 화면이지, 답할 것이 생길 때만 꺼내 보는 화면이 아니다.
  //
  // **다만 이 구분은 지킨다 — 지원 안 한다고 밝힌 것과 아예 안 밝힌 것은 다르다.**
  //   · 목록을 줬는데 pip 이 없다  → 지원 안 한다. 청하지 않는다(규범이 금한다).
  //   · 목록을 아예 안 줬다        → **모르는 것이다.** 청해 보고 답을 받는 수밖에 없다.
  //     거절되면 그대로 인라인이다 — 잃는 것이 없다.
  // 이 저장소가 여러 번 배운 것과 같은 모양이다: 없는 것과 못 찾은 것은 다르다. 그리고
  // roots 에서 이미 겪었다 — 선언과 구현이 갈리는 호스트는 실재한다.
  //
  // **한 번만 청한다.** 사람이 도로 인라인으로 돌려놨는데 우리가 다시 밀면 그건 싸움이다.
  //
  // **그리고 청한 결과를 적는다.** 안 적으면 위의 세 갈래가 화면 밖에서 전부 똑같이
  // "인라인 카드"로 보인다 — 실제로 그래서 한 세션을 통째로 추측에 썼다.
  var askedAside=false, asideSettled=false, hsOK=false;
  function maybeAside(){
    if(askedAside) return;
    // **관문 전에는 청하지 않는다.** 규범은 initialized 를 보내기 전의 앱에게 호스트가
    // 아무것도 보내지 않게 한다 — 핸드셰이크가 깨진 자리에서 청하면 그 침묵을 "거절"로
    // 잘못 적게 된다. paint() 도 이 함수를 부르므로 여기서 막아야 한다.
    if(!hsOK){ HOST.why="핸드셰이크가 안 됐다 — 관문(initialized) 전에는 청하지 않는다"; return; }
    if(HOST.mode==="pip"||HOST.mode==="fullscreen"){ HOST.why="이미 제 자리에 서 있다"; return; }
    if(HOST.modes.length && HOST.modes.indexOf("pip")<0){ // 안 한다고 밝혔다
      HOST.why="호스트가 여는 모드 목록에 pip 이 없다"; return; }
    askedAside=true; HOST.asked="pip";
    var i=++id;
    pending[i]=function(res,err){
      // **돌아온 값을 믿는다** — 청한 것과 다를 수 있다(규범). 거절이면 인라인 그대로다.
      if(err) HOST.err=String((err&&(err.message||err.code))||err);
      else if(res&&res.mode){ HOST.err=""; HOST.grant=res.mode; HOST.mode=res.mode; applyContainer(); }
      else HOST.grant="(응답에 mode 가 없다)";
      // **늦게 온 답도 기록을 고친다.** 타임아웃을 찍고 나서 지워 버리면 호스트가 늦게
      // 열어 준 자리를 놓치고, 그냥 두면 "답이 없다"가 사실이 아닌 채 서버에 남는다.
      if(asideSettled){ reportSize(); refresh(); return; }
      asideDone();
    };
    send({id:i,method:"ui/request-display-mode",params:{mode:"pip"}});
    // **답이 없는 것도 답이다** — 이 호스트가 이 요청을 아예 안 받는다는 뜻이다. 그걸
    // 침묵으로 남기면 "청했다"까지만 알고 결과는 영영 모른다(거절과 구별이 안 된다).
    setTimeout(function(){ if(!asideSettled){ HOST.err="답이 없다(700ms)"; asideDone(); } },700);
  }
  // **자리가 정해진 뒤에 첫 조각을 가져온다.** 첫 조회가 그 결과를 서버로 실어 가야
  // 도구가 사람에게 사실대로 말할 수 있다 — 조회가 먼저 나가면 서버는 늘 한 발 늦는다.
  // 이미 그려진 뒤에 답이 정해졌으면 **다시 가져온다** — 안 그러면 그 결과가 서버에
  // 영영 안 가고, 도구는 "청했고 아직 답을 못 받았다"에서 멈춘 채 늙는다. 조각은 같으니
  // 화면은 안 바뀌고, 쓰던 답은 refresh 가 지킨다.
  function asideDone(){
    if(asideSettled) return;
    asideSettled=true; reportSize();
    if(drawn) refresh(); else fetchCard();
  }

  // ── 크게 보는 것은 사람이 정한다 ─────────────────────────────────────────────
  //
  // 정본 패턴(ext-apps add-app-to-server · docs/patterns.md)은 **버튼**이다:
  // availableDisplayModes 에 fullscreen 이 있으면 버튼을 보이고, **사람이 누르면** 그때
  // ui/request-display-mode 를 보낸다. 우리는 지금까지 버튼 없이 자동으로만 청했고 —
  // 이 호스트는 목록에 fullscreen 을 안 넣으므로 — **사람의 제스처가 있는 요청은 한 번도
  // 안 해 봤다.** 그래서 "호스트가 안 준다"와 "제스처가 없어서 안 준다"가 안 갈렸다.
  //
  // 언제 버튼을 보이나:
  //   · 목록에 fullscreen 이 있다 → 보인다(정본).
  //   · 목록을 아예 안 줬다       → **모르는 것이다.** 보인다 — 누르는 것은 사람이고,
  //     거절되면 그대로다. pip 에서 이미 값을 치른 구분이다(b83a94dd).
  //   · 목록을 줬는데 없다        → **안 보인다.** 규범이 "청하기 전에 목록을 확인하라"를
  //     MUST 로 적었다. 다만 그 자리를 재려면 청해 봐야 하므로, **계기(GIL_UI_PROBE=1)를
  //     켠 동안만** 버튼을 낸다 — 기본 배포는 규범대로 조용하다.
  function fsState(){
    var declared=HOST.modes.indexOf("fullscreen")>=0;
    var unknown=!HOST.modes.length;
    return {declared:declared, unknown:unknown,
            show:declared||unknown||PROBE, forced:!declared&&!unknown};
  }
  function syncModeBar(){
    var el=document.getElementById("gil-mode"); if(!el) return;
    var st=fsState();
    if(!st.show){
      if(!HOST.fsWhy) HOST.fsWhy="호스트가 여는 모드 목록에 fullscreen 이 없다";
      if(!el.hidden){ el.hidden=true; el.innerHTML=""; reportSize(); }
      return;
    }
    var big=(HOST.mode==="fullscreen");
    var label=big?"작게 되돌린다":"크게 본다";
    if(st.forced) label+=" (계기 — 호스트가 안 밝힌 모드다)";
    // **다시 그릴 이유를 전부 센다.** 링크 시험의 결과가 이 표식에 없으면, 눌러서 답이
    // 와도 화면이 안 바뀐다 — 누른 사람에게는 "아무 일도 안 일어났다"로 보인다.
    var sig=label+"|"+HOST.fsErr+"|"+HOST.lnAsked+"|"+HOST.lnErr+"|"+HOST.lnGrant;
    if(el.dataset.sig===sig && !el.hidden) return;
    el.dataset.sig=sig; el.hidden=false; el.innerHTML="";
    var b=document.createElement("button");
    b.className="btn modebtn"; b.setAttribute("data-act","mode"); b.setAttribute("data-noarm","1");
    b.textContent=label; el.appendChild(b);
    // 실패는 **그 자리에** 적는다 — 누른 사람이 결과를 보는 곳이 여기다.
    if(HOST.fsErr){ var n=document.createElement("span");
      n.className="modenote"; n.textContent=HOST.fsErr; el.appendChild(n); }
    // **계기를 켠 동안만** 링크 시험 버튼을 낸다. 커스텀 스킴을 먼저 놓는다 — 그것이
    // 물음이고, https 는 그것이 실패했을 때 "링크 자체가 안 되는 것"과 "스킴이 막힌 것"을
    // 가르는 대조군이다. 둘을 한 번에 누르게 하면 무엇이 무엇을 답한 것인지 섞인다.
    if(PROBE){
      [["gil://monitor-probe","링크 시험 (gil://)"],
       ["https://example.com","대조군 (https)"]].forEach(function(p){
        var lb=document.createElement("button");
        lb.className="btn modebtn"; lb.setAttribute("data-act","link-probe");
        lb.setAttribute("data-url",p[0]); lb.setAttribute("data-noarm","1");
        lb.textContent=p[1]; el.appendChild(lb);
      });
      if(HOST.lnAsked){ var ln=document.createElement("span"); ln.className="modenote";
        ln.textContent=HOST.lnAsked+" → "+(HOST.lnErr||HOST.lnGrant||"기다리는 중");
        el.appendChild(ln); }
    }
    reportSize();
  }
  // **한 번 누르면 한 번 청한다.** 그리고 답이 없는 것도 답이다 — 안 적으면 "눌렀는데
  // 아무 일도 없었다"가 거절·무응답·안 보냄과 구별되지 않는다(pip 에서 배운 그대로).
  function askFullscreen(){
    if(!hsOK){ HOST.fsWhy="핸드셰이크가 안 됐다"; syncModeBar(); return; }
    var want=(HOST.mode==="fullscreen")?"inline":"fullscreen";
    HOST.fsAsked=want; HOST.fsGrant=""; HOST.fsErr=""; HOST.fsWhy="";
    var settled=false, i=++id;
    pending[i]=function(res,err){
      settled=true;
      // **돌아온 값을 믿는다** — 청한 것과 다를 수 있다(규범: 지원 안 하면 지금 모드를 준다).
      if(err) HOST.fsErr=String((err&&(err.message||err.code))||err);
      else if(res&&res.mode){ HOST.fsGrant=res.mode; HOST.mode=res.mode; applyContainer(); }
      else HOST.fsGrant="(응답에 mode 가 없다)";
      syncModeBar(); refresh();
    };
    send({id:i,method:"ui/request-display-mode",params:{mode:want}});
    setTimeout(function(){ if(!settled){ HOST.fsErr="답이 없다(1500ms)"; syncModeBar(); refresh(); } },1500);
    syncModeBar();
  }

  // ── 바깥의 것을 여는 것도 사람이 정한다 ──────────────────────────────────────
  //
  // **왜 이 계기가 있나.** pip 이 없다는 것이 확정된 자리에서(2026-08-11 실측), "대화 곁에
  // 계속 서 있는 화면"은 카드 안에서 못 만든다. 그러면 남는 것은 카드가 **바깥의 앱**을 여는
  // 것이고, 그 길이 실재하는지는 커스텀 URI 스킴이 ui/open-link 를 통과하는가에 달렸다.
  // 규범은 스킴을 제한하지 않지만 "Invalid URL"·"Policy violation" 오류를 정의해 둔다 —
  // **정하지 않은 것은 재야 안다.** 디렉터리 제출 문서는 반대편에서 이걸 가리킨다:
  // allowed link URIs 에 myapp: 꼴의 커스텀 스킴을 **자기 앱에 한해** 적으라고 한다.
  //
  // **누르는 것은 사람이다.** 링크를 여는 것은 이 기계에 보이는 부작용이 있다(브라우저 탭이
  // 뜨거나, 등록된 앱이 뜨거나, OS 가 "여는 앱이 없다"고 한다). 화면이 스스로 열면 그건
  // 사람이 고른 것이 아니다 — fullscreen 에서 배운 그대로다.
  //
  // **기본 배포에는 안 나온다**(PROBE). 이건 제품 기능이 아니라 재려고 놓은 자리다.
  function askOpenLink(url){
    if(!hsOK){ HOST.lnWhy="핸드셰이크가 안 됐다"; syncModeBar(); return; }
    HOST.lnAsked=url; HOST.lnGrant=""; HOST.lnErr=""; HOST.lnWhy="";
    var settled=false, i=++id;
    pending[i]=function(res,err){
      settled=true;
      // **성공은 빈 결과다**(규범: result {}). 그러니 "res 가 비었다"를 실패로 읽으면 안 된다 —
      // 여기서 그걸 뒤집어 읽으면 되는 것을 안 된다고 적고, 그 위에서 다음 판단이 선다.
      if(err) HOST.lnErr=String((err&&(err.code!==undefined?err.code+":":""))||"")+
                          String((err&&err.message)||err);
      else HOST.lnGrant="열렸다고 답했다(빈 결과)";
      syncModeBar(); refresh();
    };
    send({id:i,method:"ui/open-link",params:{url:url}});
    // **답이 없는 것도 답이다** — 이 호스트가 이 요청을 아예 안 받는다는 뜻이다.
    setTimeout(function(){ if(!settled){ HOST.lnErr="답이 없다(1500ms)"; syncModeBar(); refresh(); } },1500);
    syncModeBar();
  }

  // ── 화면이 스스로 따라간다 ──────────────────────────────────────────────────
  //
  // 전에는 한 번 그려지면(drawn=true) 끝이었다 — fetchCard 가 즉시 되돌아가고, tool-result
  // 알림은 **카드 HTML 을 실은 것만** 다시 그렸다. 그런 결과를 내는 것은 앱 전용 툴 둘뿐이라,
  // 모델이 gil_step·gil_close 를 아무리 불러도 사람이 보는 화면은 처음 그대로였다. 뷰어에는
  // /poll 이 있었고 카드에는 대응하는 것이 없었다 — "카드는 알림이 올 때 다시 가져온다"는
  // 우리 쪽 오독이었다(실측으로 확인).
  function refresh(){
    // **쓰는 중에는 안 그린다.** 값은 위에서 보존되지만 커서와 스크롤은 못 지킨다 —
    // 문장 한가운데서 화면이 갈리면 사람은 자기가 쓰던 것을 잃었다고 읽는다.
    if(Date.now()-lastInput < 2500){
      clearTimeout(holdTimer); holdTimer=setTimeout(refresh,2500); return;
    }
    drawn=false; fetches=0; fetchCard();
  }
  // 한 턴에 툴이 여러 번 돌면 알림도 여러 번 온다 — 마지막 것 하나로 접는다.
  function scheduleRefresh(){ clearTimeout(refreshTimer); refreshTimer=setTimeout(refresh,350); }
  document.addEventListener("input",function(){ lastInput=Date.now(); },true);

  // **만들 자리를 치는 동안 보여준다.** 경로를 아무도 안 치는 대신, 어디에 생기는지는
  // 누르기 **전에** 눈에 보여야 한다 — 안 보이면 그건 사람이 정한 것이 아니라 도구가
  // 정하고 사람이 승인한 것이 된다(그 둘은 다르다).
  //
  // 접는 것은 화면이 하고 **판정은 서버가 다시 한다**(placeSlug). 화면이 만든 경로를 그대로
  // 믿고 만들면, 화면과 서버가 갈릴 때 사람이 본 것과 다른 자리에 폴더가 생긴다.
  function slugPreview(s){
    // 같은 규칙을 서버가 다시 써다(placeSlug) — 화면은 미리 보여 주기만 한다.
    var out="";
    var t=String(s||"").trim();
    for(var i=0;i<t.length;i++){
      var ch=t.charAt(i), code=t.charCodeAt(i);
      if(ch==="/"||ch==="\\"||ch===":") continue;   // 경로를 벗어나게 하는 글자
      if(code<32) continue;                       // 제어문자
      out += /\s/.test(ch) ? "-" : ch;
    }
    return out.replace(/^[-.]+|[-.]+$/g,"");
  }
  document.addEventListener("input",function(ev){
    var el=ev.target;
    if(!el || !(el.hasAttribute&&(el.hasAttribute("data-start-name")||el.hasAttribute("data-start-place")))) return;
    startBeat("delegate");
    syncStartPreview(el.closest("[data-start]"));
  },true);

  function fetchCard(){
    if(fetching || drawn || fetches>=4) return;
    fetching=true; fetches++;
    var i=++id;
    pending[i]=function(res,err){
      fetching=false;
      var s=slot(); if(!s) return;
      if(err){ s.innerHTML=fail("가져오지 못했다: "+
        String((err&&(err.message||err.code))||err)); reportSize(); return; }
      var html=cardOf(res);
      // 조각이 없으면 **그 사실을 화면에 적는다** — 빈 화면은 고장과 아직을 구별해 주지 않는다.
      if(html){ paint(html); return; }
      s.innerHTML=fail("응답에 카드가 없다: "+String(res&&Object.keys(res).join(",")));
      reportSize();
    };
    var a={};
    if(repo) a.repo=repo;
    // **이 화면이 선 표면을 서버에 알린다.** iframe↔호스트 프레임은 서버에 오지 않으니,
    // 호스트가 무엇을 지원한다고 답했는지는 화면이 적어 보내야만 알 수 있다. 그걸 알아야
    // 도구가 사람에게 "곁에 띄울 수 있다"를 말할 수 있고, 없으면 조용히 인라인으로 남는다.
    // **이 껍데기가 몇 판인지 함께 싣는다.** 호스트는 ui:// 리소스를 캐시하고 다시 안 읽는다
    // (규범이 허용한다). 그래서 서버를 새로 깔아도 **사람 화면에는 옛 껍데기가 그대로 남을 수
    // 있다** — 2026-08-10 에 이걸 몰라서 같은 자리를 세 번 "고치고" 세 번 안 됐다고 읽었다.
    // 고친 것과 뜬 것이 다른데 그걸 구별할 방법이 없으면, 그 뒤 판정은 전부 헛것 위에 선다.
    // 서버가 제 판과 대조해서 다르면 그 사실을 말한다(uiHostLine).
    a.host=JSON.stringify({ver:VER,modes:HOST.modes,mode:HOST.mode,vars:HOST.vars,caps:HOST.caps,
      asked:HOST.asked,grant:HOST.grant,err:HOST.err,why:HOST.why,ua:HOST.ua,plat:HOST.plat,
      fsAsked:HOST.fsAsked,fsGrant:HOST.fsGrant,fsErr:HOST.fsErr,fsWhy:HOST.fsWhy,
      lnAsked:HOST.lnAsked,lnGrant:HOST.lnGrant,lnErr:HOST.lnErr,lnWhy:HOST.lnWhy});
    send({id:i,method:"tools/call",params:{name:"gil_status_card",arguments:a}});
  }

  // **실패는 막다른 길이 아니어야 한다.** 조회는 네 번에서 멈추는데(fetches>=4), 그 뒤 다시
  // 조회를 거는 자리가 없었다 — 사람은 "가져오지 못했다" 한 줄 앞에서 끝이었다. 뷰어가 있는
  // 동안은 브라우저 새로고침이 폴백이었다. 그 폴백이 사라지므로, 화면이 제 손으로 되살아날
  // 길을 준다. 무장(두 번 클릭)은 면제한다 — 다시 읽는 것은 아무것도 안 바꾼다.
  function fail(msg){
    return '<div class="lbl">gil</div><div class="none">'+msg+'</div>'+
      '<div class="acts"><button class="btn" data-act="refetch" data-noarm="1">다시 가져온다</button></div>';
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
    if(b.getAttribute("data-act")==="refetch"){ drawn=false; fetches=0; fetchCard(); return; }
    // **여기가 사람의 제스처다.** 정본이 요구하는 것도, 우리가 한 번도 안 해 본 것도 이것이다.
    if(b.getAttribute("data-act")==="mode"){ askFullscreen(); return; }
    if(b.getAttribute("data-act")==="link-probe"){ askOpenLink(b.getAttribute("data-url")||""); return; }
    // **어디에 만들까 — 사람이 이름만 정하고 경로는 아무도 치지 않는다.**
    if(b.getAttribute("data-act")==="start-here"){
      var box=b.closest("[data-start]"); if(!box) return;
      var nameEl=box.querySelector("[data-start-name]");
      var name=(nameEl&&nameEl.value||"").trim();
      // **빈 이름으로는 안 보낸다.** 그 이름으로 폴더가 생기고, 빈 이름은 자리를 못 만든다.
      if(!name){ say("이름을 한 줄 적어 주세요 — 그 이름으로 폴더가 생깁니다.");
        if(nameEl) nameEl.focus(); return; }
      var placeEl=box.querySelector("[data-start-place]");
      var a={name:name};
      var place=(placeEl&&placeEl.value||"").trim();
      if(place) a.place=place;
      var i=++id;
      pending[i]=function(res,err){
        if(err){ say("세우지 못했다: "+String((err&&(err.message||err.code))||err)); return; }
        var txt=(res&&res.content&&res.content[0]&&res.content[0].text)||"";
        if(res&&res.isError){ say("거부됐다 — "+txt.split("\n")[0]); return; }
        say("세웠다. 화면을 다시 가져온다."); drawn=false; fetches=0; fetchCard();
      };
      send({id:i,method:"tools/call",params:{name:"gil_start_here",arguments:a}});
      say("세우는 중…");
      return;
    }
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
        // 확정됐으면 그 체인의 초안은 **비운다** — 안 비우면 다음 인터뷰 폼에 옛 답이
        // 되심겨 사람이 안 쓴 문장이 화면에 앉는다(그 순간 기준이 사람의 것이 아니게 된다).
        delete drafts[b.getAttribute("data-chain")||""];
        var h=cardOf(res);
        if(h){ paint(h); return; }
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
    // **무장 면제**(data-noarm) — 아무것도 안 바꾸는 버튼까지 두 번 누르게 하면, 두 번
    // 누르는 일이 값싼 동작이 되어 정작 승인·삭제에서 그 관문이 무뎌진다.
    // 그리고 무장 문구는 **버튼이 정한다**(data-arm). "정말? — 한 번 더" 는 무엇을 되묻는지
    // 말하지 않는다 — 되묻는 값은 그 자리에서 무엇이 확정되는지를 말할 때 나온다.
    if(!b.hasAttribute("data-armed") && !b.hasAttribute("data-noarm")){
      b.setAttribute("data-armed","1");
      b.dataset.label=b.textContent;
      b.textContent=b.getAttribute("data-arm")||"정말? — 한 번 더";
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
    // 렌더 **뒤**에 테마·표시모드·칸 크기가 바뀔 수 있다(규범: host-context-changed).
    // 안 들으면 사람이 앱을 어둡게 바꿔도 카드만 밝은 채로 남는다.
    if(m.method==="ui/notifications/host-context-changed"){
      var hc=(m.params)||{};
      if(hc.theme==="dark"||hc.theme==="light") document.documentElement.setAttribute("data-theme",hc.theme);
      if(hc.styles) applyHostStyles(hc);
      if(hc.availableDisplayModes) HOST.modes=hc.availableDisplayModes;
      if(hc.displayMode) HOST.mode=hc.displayMode;
      if(hc.userAgent) HOST.ua=String(hc.userAgent);
      if(hc.platform) HOST.plat=String(hc.platform);
      if(hc.containerDimensions){ HOST.dims=hc.containerDimensions; applyContainer(); }
      // 목록이나 현재 모드가 바뀌면 버튼도 따라간다 — 호스트가 뒤늦게 fullscreen 을 열어
      // 주는 자리가 있고(규범이 이 알림으로 알린다), 그때 버튼이 없으면 그 자리를 못 쓴다.
      syncModeBar();
      reportSize();
      return;
    }
    // 응답이 **어떤 모양으로 와도** 받는다: 우리 id 에 대한 답이거나, 툴 결과 알림이거나.
    var res=null;
    if(m.id!==undefined && pending[m.id]){ var cb=pending[m.id]; delete pending[m.id];
      cb(m.result,m.error); return; }
    if(m.method==="ui/notifications/tool-result"){
      res=(m.params&&(m.params.result||m.params))||null;
      var h2=cardOf(res);
      if(h2){ paint(h2); return; }
      // **카드를 안 실어 온 결과도 세계가 바뀌었다는 뜻이다.** 전에는 여기서 if(!drawn)
      // 이라 이미 그려진 화면은 영영 그대로였다 — 모델이 gil_step 을 불러 스텝이 늘어도
      // 사람 앞의 카드는 처음 상태였다. 다시 가져온다(쓰는 중이면 refresh 가 미룬다).
      scheduleRefresh();
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
      applyHostStyles(hc);
    }catch(_){}
  }

  // **호스트가 제 색·글꼴을 알려주면 그것을 쓴다.**
  //
  // 옛 주석은 "색 변수는 가져다 쓰지 않는다 — 이름을 모르는 채 우리 --bg 에 꽂으면 배경이
  // 아닌 값이 배경이 되어 카드가 통째로 안 읽힌다" 였다. 그때는 맞았다. **지금은 이름을
  // 안다** — 규범이 변수 집합을 표준화했다(--color-background-*·--font-sans·--border-radius-*).
  // 그래서 이름을 아는 것만 골라 우리 변수에 잇는다. 안 오면 지금 팔레트가 그대로 답이다.
  function applyHostStyles(hc){
    var v=(hc&&hc.styles&&hc.styles.variables)||null;
    if(!v) return;
    HOST.vars=Object.keys(v).length;
    var map={
      "--color-background-primary":"--bg", "--color-background-secondary":"--card",
      "--color-background-tertiary":"--panel", "--color-text-primary":"--fg",
      "--color-text-secondary":"--dim", "--color-border-primary":"--line",
      "--font-sans":"--font-sans"
    };
    var root=document.documentElement;
    for(var k in map){ if(v[k]) root.style.setProperty(map[k], v[k]); }
    // 규범이 준 변수를 그대로도 심어 둔다 — 카드 조각이 직접 쓸 수 있게.
    for(var k2 in v){ if(k2.indexOf("--")===0) root.style.setProperty(k2, v[k2]); }
  }

  // **호스트가 밝힌 것을 기억한다.** 지원 안 하는 모드를 청하면 안 된다는 것이 규범이라,
  // 청하기 전에 이 목록을 본다. 목록이 **비어 있는 것**은 "안 한다"가 아니라 "안 밝혔다"라,
  // 그때는 청해 보고 답을 받는다 — 판정은 maybeAside 에 있다(b83a94dd).
  function learnHost(res){
    try{
      var hc=(res&&res.hostContext)||{}, hcap=(res&&res.hostCapabilities)||{};
      HOST.modes=hc.availableDisplayModes||[];
      HOST.mode=hc.displayMode||"";
      HOST.dims=hc.containerDimensions||null;
      HOST.caps=Object.keys(hcap);
      // **호스트가 자기 이름을 말해 준다** — 규범의 userAgent·platform. 이게 없으면 잰 값에
      // 출처가 없다(hostInfo 로 오는 호스트도 있어 두 자리를 본다).
      HOST.ua=String(hc.userAgent||(res&&res.hostInfo&&(res.hostInfo.name||""))||"");
      HOST.plat=String(hc.platform||"");
      applyContainer(); syncModeBar();
    }catch(_){}
  }

  // **좁은 칸에서 사는 법 — 그런데 전용 칸을 받았을 때만.**
  //
  // 처음엔 "호스트가 height 를 주면 무조건 그 칸을 채운다"로 했다. 실측(상현님)에서 그게
  // 인라인 카드를 **읽을 수 없게** 만들었다: 세로가 짧게 눌리고 안에서 스크롤해야 했다.
  //
  // 기제는 자기를 강화하는 고리다. html 에 height:100%·overflow:hidden 을 걸면
  // documentElement.scrollHeight 가 **내용 높이가 아니라 칸 높이**가 된다 → 작은 높이를
  // 보고한다 → 호스트가 그 크기를 유지한다 → 다시 작은 높이를 보고한다. 한 번 눌리면
  // 스스로는 못 빠져나온다.
  //
  // 그러니 칸을 채우는 것은 **전용 칸(pip·fullscreen)** 을 실제로 받았을 때뿐이다.
  // 인라인에서는 예전처럼 자란다 — 대화 흐름 안에서는 우리가 높이를 정하는 쪽이 맞다.
  function applyContainer(){
    var d=HOST.dims||{};
    var own=(HOST.mode==="pip"||HOST.mode==="fullscreen");
    var fixed=own&&((typeof d.height==="number")||(typeof d.width==="number"));
    document.documentElement.setAttribute("data-fit", fixed?"fixed":"flex");
    reportSize();
  }

  var hs=++id;
  pending[hs]=function(res,err){
    if(!err){ learnHost(res); applyTheme(res); notify("ui/notifications/initialized",{});
      hsOK=true;
      // **가능한 한 일찍 청한다** — 내용을 그린 뒤에 옮기면 사람 눈앞에서 화면이 한 번 뛴다.
      maybeAside(); }
    reportSize();
    // 청했으면 답(또는 무응답 판정)을 기다렸다가 asideDone 이 가져온다. 안 청했으면 지금.
    if(!askedAside) fetchCard();
  };
  send({id:hs,method:"ui/initialize",params:{
    protocolVersion:"2026-01-26",
    appInfo:{name:"gil-status-card",version:VER},
    clientInfo:{name:"gil-status-card",version:VER},
    capabilities:{},
    // **곁에 두는 모드(pip)까지 선언한다.** 상태 카드는 한 번 보고 닫는 화면이 아니라
    // 일하는 동안 곁에 두는 화면이다 — 인라인은 대화와 함께 스크롤돼 올라가서, 사람이
    // 3번 문항을 쓰다 1번을 다시 보려면 위로 올려야 한다. 선언은 "할 수 있다"일 뿐이고,
    // 실제로 청할지는 호스트가 답한 목록을 보고 정한다(learnHost).
    appCapabilities:{availableDisplayModes:["inline","fullscreen","pip"]}}});
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
	`--danger-bg:#fdf0ed;--danger-fg:#8c2f18;--danger-line:#e0574a;` +
	`--wait-bg:#eaf2ff;--wait-fg:#12406b;--wait-line:#bcd6f5;--code:#f1efe8;--panel:#fff;--acc:#444441;--acc-fg:#fff`

const cardVarsDark = `--bg:#17171a;--fg:#e9e7e1;--dim:#9b9992;--line:#3a3a3d;--card:#232326;` +
	`--warn-bg:#3a2a12;--warn-fg:#ffd79a;--warn-line:#7a5a24;` +
	`--danger-bg:#3a1d16;--danger-fg:#ffbfae;--danger-line:#e0574a;` +
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
/* **전용 칸(pip·fullscreen)을 받았을 때만** 칸을 채우고 안에서 구른다(규범
   containerDimensions). 인라인에서는 걸지 않는다 — 걸었더니 카드가 짧게 눌려 읽을 수
   없었다(상현님 실측). 판정은 applyContainer 에 있고 여기는 그 결과를 그릴 뿐이다. */
html[data-fit="fixed"],html[data-fit="fixed"] body{height:100%;overflow:hidden}
html[data-fit="fixed"] body{display:flex;flex-direction:column;padding:10px}
html[data-fit="fixed"] .card{overflow-y:auto;flex:1 1 auto;max-width:none}
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
/* 표시모드 바 — **카드 조각 바깥**에 산다. 카드는 다시 그려질 때마다 통째로 갈리므로
   (paint 가 innerHTML 을 갈아끼운다) 안에 두면 누를 자리가 깜빡이며 사라진다. */
.modebar{display:flex;gap:8px;align-items:center;margin:0 auto 8px;max-width:720px;
 justify-content:flex-end}
.modenote{font-size:12px;color:var(--dim)}
.startmore{margin-top:10px;font-size:13px;color:var(--dim)}
.startmore summary{cursor:pointer}
.startmore .ivin{margin-top:6px}
html[data-fit="fixed"] .modebar{margin:0 0 6px}
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
` + interviewCardCSS + pruneCardCSS + `
</style>`
}

// statusCardBodyHTML — **카드 조각 하나.** 앱이 이걸 받아 그려 넣는다.
func statusCardBodyHTML(st statusOut) string {
	var b strings.Builder
	// **카드가 "지금 사람이 나설 자리가 있다"를 스스로 표시한다.** 껍데기는 카드 내용을
	// 모른다(레이아웃은 Go 에만 있다) — 그런데 곁에 띄울지(pip) 정하려면 그걸 알아야 한다.
	// 판정은 여기 한 자리에서 하고, 껍데기는 표식만 읽는다.
	needs := st.Waiting != nil || len(st.OpenInterviews) > 0 || len(st.PendingPrunes) > 0
	b.WriteString(`<div class="card"` + map[bool]string{true: ` data-needs-human="1"`}[needs] + `>`)

	// **기다리는 인터뷰는 HEAD 와 무관하게, 전부, 맨 위에 선다.**
	//
	// 전에는 폼이 st.Chain != nil 분기 **안에서만** 그려졌고 그 조건은 HEAD 커밋의 트레일러가
	// 정했다. 그래서 두 가지가 조용히 일어났다: ① 체인 밖(dev·main)에 서 있으면 폼이 아예
	// 안 떴다 — 질문을 심어 놓고 사람을 기다리는 자리가 바로 거기다 ② 질문이 두 체인에 떠
	// 있으면 사람은 HEAD 가 선 쪽에만 답할 수 있었다. 뷰어는 처음부터 전부 띄웠고, 카드가
	// 그 자리를 대신하려면 같은 것을 보여야 한다.
	drawn := map[string]bool{}
	for _, iv := range st.OpenInterviews {
		if f := interviewCardHTML(iv.Chain); f != "" {
			b.WriteString(f)
			drawn[iv.Chain] = true
		}
	}
	// 삭제 승인도 같은 자리다 — **요청을 올린 사람이 대개 서 있는 곳이 층(dev·main) 위**라,
	// st.Chain 분기 안에 두면 정작 필요한 자리에서 안 보인다. 그리고 지금까지 이 사실을
	// 보여 주는 화면은 뷰어 창 하나뿐이었다(status·handoff 는 prune 을 한 글자도 안 말했다).
	b.WriteString(pruneCardHTML(st))

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
		// **인터뷰는 글이 아니라 폼이다.** 옛 카드는 "에이전트가 여는 인터뷰 창구에
		// 적으면"이라고 말했는데, 이 표면에는 그 창구가 없었다(뷰어는 청해야 뜨고
		// 시작하는 사람에겐 창이 없다, Elicitation 은 Desktop 이 못 띄운다). 가리키는
		// 것이 실재하지 않는 안내였다 — 그래서 **카드가 그 창구가 된다**. 그 폼은 이제
		// 이 분기 **바깥**에서, HEAD 와 무관하게, 기다리는 것 전부가 그려진다(위).
		// 그러니 여기서는 이미 폼으로 선 것을 **글로 또 말하지 않는다.**
		if st.Waiting != nil && !(st.Waiting.Kind == "interview" && drawn[st.Waiting.Chain]) {
			b.WriteString(`<div class="box wait"><div class="t">⏳ 사람의 판단이 필요하다</div><div>` +
				esc(st.Waiting.What) + `</div><div style="margin-top:6px">` +
				esc(waitHumanLine(st.Waiting)) + `</div></div>`)
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
		// **여기로 오는 것은 폼이 안 선 경우뿐이다**(질문을 못 읽었거나 그사이 확정됐다).
		// 폼이 서면 카드가 위에서 그리고 이 줄은 안 나온다. 그러니 이 문장은 "어디에 적어라"가
		// 아니라 **왜 지금 적을 자리가 없는지**를 말해야 한다 — 옛 문장은 "에이전트가 여는
		// 인터뷰 창구에 적으면"이었는데 이 표면에 그런 창구가 없다. 없는 것을 가리키는 안내가
		// 이 저장소를 아홉 번 물게 한 그 병이다.
		return "체인의 기준 문서에 대한 답이다. 답할 폼이 아직 안 섰으면 에이전트에게 " +
			"gil_interview 를 다시 불러 달라고 하면 이 카드에 폼이 선다."
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
