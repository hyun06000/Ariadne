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
		return renderStatusResource(uri, repoFromStatusURI(uri))
	}
	s.AddResource(&mcp.Resource{
		URI: uiStatusURI, Name: "gil-status", Title: "gil 상태 카드", MIMEType: uiGraphMIME,
		Description: "지금 어디·무엇을 재는 중·사람이 나설 자리·다음 한 수. 그래프는 담지 않는다.",
	}, read)
	s.AddResourceTemplate(&mcp.ResourceTemplate{
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
			st = gatherStatus()
		})
		if err != nil {
			return nil, nil, err
		}
		_ = out
		wd, _ := os.Getwd()
		// 모델에게는 **줄인 텍스트**를 준다(카드와 같은 사실). JSON 을 통째로 주면 그것이
		// 그대로 대화에 실린다 — tipSignature 로 이미 한 번 값을 치른 자리다.
		res := &mcp.CallToolResult{
			Content:           []mcp.Content{&mcp.TextContent{Text: strings.Join(statusLines(st), "\n")}},
			StructuredContent: map[string]any{"tipSignature": tipSignatureDigest()},
		}
		res.Meta = mcp.Meta{"ui": map[string]any{
			"resourceUri": uiStatusURI + "/" + url.PathEscape(wd),
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

func renderStatusResource(uri, repo string) (*mcp.ReadResourceResult, error) {
	page := func(html string) (*mcp.ReadResourceResult, error) {
		return &mcp.ReadResourceResult{Contents: []*mcp.ResourceContents{{
			URI: uri, MIMEType: uiGraphMIME, Text: html,
		}}}, nil
	}
	if repo != "" {
		if _, err := gitTryIn(repo, "rev-parse", "--git-dir"); err != nil {
			return page(uiProblemPage("이 경로는 git 저장소가 아니다", repo,
				"사람이 보고 있는 폴더의 최상위(.git 이 있는 자리)를 repo 인자에 실어 다시 불러라."))
		}
		if os.Chdir(repo) != nil {
			return page(uiProblemPage("저장소로 이동하지 못했다", repo, "경로 권한을 확인하라."))
		}
		stopGitCache()
	}
	if !gitOK("rev-parse", "--git-dir") {
		wd, _ := os.Getwd()
		return page(uiProblemPage("어느 저장소를 볼지 모른다", wd,
			"이 창은 인자를 실을 수 없는 자리에서 열렸고, 호스트가 열린 폴더를 알려주지 않았다"+
				"(MCP roots 미지원). gil_status 를 repo 인자와 함께 부르면 그 저장소가 보인다."))
	}
	var st statusOut
	if _, err := runGil(func() { st = gatherStatus() }); err != nil {
		return page(uiProblemPage("상태를 읽지 못했다", err.Error(), "gil fsck 로 그래프 상태를 확인하라."))
	}
	return page(injectUIBridge(statusCardHTML(st), tipSignatureDigest()))
}

// statusCardHTML — 카드 한 장. 다크·라이트 둘 다.
//
// 읽는 순서를 화면 순서로 고정한다: **사람이 나설 자리 → 지금 어디 → 무엇을 재는 중 →
// 경고 → 다음 한 수.** 기다리는 것이 있으면 그게 맨 위다 — 그것이 지금 유일하게 할 일이고,
// 아래로 밀면 다른 줄을 읽는 동안 묻혀 버린다.
func statusCardHTML(st statusOut) string {
	var b strings.Builder
	b.WriteString(`<!doctype html><meta charset="utf-8">
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

.strip{display:block;margin:10px 0 2px;max-width:100%;height:auto}
.strip .e{stroke:var(--dim);stroke-width:1.5;fill:none}
.strip .bt{stroke:#D85A30;stroke-width:1.5;stroke-dasharray:4 3;fill:none}
.strip .ring{fill:none;stroke-width:1.5}
.strip .knd{font-size:9.5px;fill:var(--dim);text-anchor:middle}
.legend{display:flex;flex-wrap:wrap;gap:4px 12px;margin:2px 0 2px;font-size:11px;color:var(--dim)}
.legend i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:0}
</style><body><div class="card">`)

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

	b.WriteString(`</div></body>`)
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
	b.WriteString(`<div class="acts">` +
		`<button class="btn primary" data-act="approve">승인</button>` +
		`<button class="btn" data-act="reject">기각 · 수정</button></div>`)
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
