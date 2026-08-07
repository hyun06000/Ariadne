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
:root{--bg:#fff;--fg:#1c1c1f;--dim:#6b6b76;--line:#e3e3e8;--card:#fafafc;
      --warn-bg:#fff6e5;--warn-fg:#7a4d00;--warn-line:#f0d9a8;
      --wait-bg:#eaf2ff;--wait-fg:#12406b;--wait-line:#bcd6f5;--code:#f0f0f4}
@media (prefers-color-scheme:dark){
:root{--bg:#1b1b1f;--fg:#e8e8ee;--dim:#9a9aa6;--line:#33333c;--card:#232329;
      --warn-bg:#3a2a12;--warn-fg:#ffd79a;--warn-line:#7a5a24;
      --wait-bg:#12283f;--wait-fg:#bcd9ff;--wait-line:#2a557f;--code:#2a2a32}}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);
 font:14px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.card{max-width:720px;border:1px solid var(--line);border-radius:12px;
 background:var(--card);padding:14px 16px}
.crumb{font-size:15px;font-weight:600;letter-spacing:-.01em;word-break:break-word}
.crumb .sep{color:var(--dim);font-weight:400;margin:0 6px}
.kind{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);
 border:1px solid var(--line);border-radius:99px;padding:1px 8px;margin-left:6px;white-space:nowrap}
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
.foot{margin-top:12px;padding-top:9px;border-top:1px solid var(--line);
 font-size:12px;color:var(--dim)}
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
		b.WriteString(`<div class="crumb">` + esc(st.Chain.Name) +
			`<span class="sep">›</span>`)
		if st.Cycle != nil {
			b.WriteString(esc(st.Cycle.Name))
		}
		if st.Step != nil {
			b.WriteString(`<span class="sep">›</span>` + esc(st.Step.ID) +
				`<span class="kind">` + esc(st.Step.Kind) + `</span>`)
		}
		b.WriteString(`</div><div class="repo">` + esc(st.Repo) + `</div>`)

		if st.Cycle != nil && st.Cycle.RefutesIf != "" {
			b.WriteString(`<div class="row"><div class="lbl">재는 중 — 무엇이 관측되면 틀리나</div>` +
				`<div class="val">` + esc(clip(st.Cycle.RefutesIf, 220)) + `</div></div>`)
		}
		if st.Cycle != nil && st.Cycle.FalsifyTo != "" {
			b.WriteString(`<div class="row"><div class="lbl">반증되면 돌아갈 자리</div><div class="val">` +
				`<code>` + esc(st.Cycle.FalsifyTo) + `</code></div></div>`)
		}
	}

	for _, w := range st.Warnings {
		b.WriteString(`<div class="box warn">⚠ ` + esc(w) + `</div>`)
	}

	if len(st.Next) > 0 {
		b.WriteString(`<div class="row"><div class="lbl">다음 한 수</div><ul>`)
		for _, n := range st.Next {
			b.WriteString(`<li>` + codeify(n) + `</li>`)
		}
		b.WriteString(`</ul></div>`)
	}

	b.WriteString(`<div class="foot">전체 그래프를 훑으려면 <code>gil_graph</code>. ` +
		`이 카드는 지금 선 자리만 말한다.</div></div></body>`)
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
