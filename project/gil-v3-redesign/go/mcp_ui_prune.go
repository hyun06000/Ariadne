// mcp_ui_prune.go — **삭제 승인이 카드 안에 선다** (상현님, 2026-08-10).
//
// 왜. 삭제는 사람의 판단을 지나야 한다는 규범은 처음부터 있었다. 그런데 그 판단을 **누를
// 자리**가 뷰어 창 하나뿐이었다 — 뷰어는 이 표면에서 열 수 없고, 비개발자에게 터미널은 없다.
// 즉 규범은 "사람이 승인한다"고 말하는데 실제로는 **승인할 수 있는 사람이 없었다.**
// 요청은 쌓이고 아무도 못 푼다.
//
// 그리고 요청이 떠 있다는 사실을 보여 주는 화면도 뷰어뿐이었다. `gil status` 도 `gil handoff`
// 도 prune 대기를 한 글자도 말하지 않았다(실측 grep 0). 뷰어를 지우면 요청이 올라가 있어도
// 아무 화면에도 안 뜬다 — 없는 것과 같아진다.
//
// **무엇을 맞바꿨나.** 이 통로를 세우면 에이전트도 이 툴을 부를 수 있게 된다 —
// `visibility:["app"]` 은 벽이 아니라 힌트고(mcp_ui_interview.go 가 사실대로 적어 둔 것),
// 지금 뷰어의 HTTP POST 는 에이전트가 원리적으로 못 눌렀다. 상현님 판단으로 **도달가능성을
// 택했다**: 못 누르는 안전보다 누를 수 있는 사람이 있는 쪽이 낫다. 방어는 두 겹으로 남는다 —
//
//	① Gil-By 가 **누가 눌렀는지**를 커밋에 적는다(카드에서 누른 것은 "card").
//	② 승인만으로는 **아무것도 안 지워진다.** 실행에는 터미널의 확인 문구가 더 필요하다
//	   (`gil prune <t> --confirm <t> --reason …`). 그 자리는 여전히 사람의 터미널이다.
//
// 안전장치를 둘로 나눈 이유는 하나가 뚫려도 다른 하나가 남게 하기 위해서다 — 뷰어 시절부터
// 같은 설계였고, 통로가 바뀌어도 그 형태는 그대로다.
package main

import (
	"context"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type inPruneAct struct {
	Repo   string `json:"repo,omitempty" jsonschema:"어느 저장소인가(절대경로)"`
	Target string `json:"target" jsonschema:"삭제 요청이 올라온 대상(체인 이름)"`
}

func (i inPruneAct) repoArg() string { return i.Repo }

// registerPruneCardTools — 카드의 [승인]·[요청을 거둔다] 버튼이 도는 통로.
//
// 앱 전용이다(surface.go 의 appOnlyTools 에 선언). 그래서 세션 앞머리(⚡ 도착 고지·버전
// 문의)가 이 응답에는 안 붙는다 — 응답이 사람 화면으로 가기 때문이다.
func registerPruneCardTools(s *mcp.Server) {
	mcp.AddTool(s, &mcp.Tool{
		Name:        "gil_prune_approve",
		Annotations: toolAnn("gil_prune_approve"),
		Description: "앱 전용 — 사람이 카드에서 누른 삭제 승인. 모델이 부를 것이 아니다" +
			"(삭제 판단은 사람이 한다). 승인만으로는 아무것도 지워지지 않는다.",
		Meta: mcp.Meta{"ui": map[string]any{"visibility": []string{"app"}}},
	}, func(ctx context.Context, req *mcp.CallToolRequest, in inPruneAct) (*mcp.CallToolResult, any, error) {
		return pruneCardAct(in, func(t string) { cmdPruneApprove([]string{t, "--by", "card"}) })
	})

	mcp.AddTool(s, &mcp.Tool{
		Name:        "gil_prune_withdraw",
		Annotations: toolAnn("gil_prune_withdraw"),
		Description: "앱 전용 — 사람이 카드에서 삭제 요청을 거둔다. 아무것도 지우지 않고 " +
			"요청만 걷는다.",
		Meta: mcp.Meta{"ui": map[string]any{"visibility": []string{"app"}}},
	}, func(ctx context.Context, req *mcp.CallToolRequest, in inPruneAct) (*mcp.CallToolResult, any, error) {
		return pruneCardAct(in, func(t string) {
			cmdPrune([]string{t, "--withdraw", "--reason", "카드에서 사람이 요청을 거둠", "--by", "card"})
		})
	})
}

// pruneCardAct — 두 버튼의 공통 몸통. 돌고 나서 **다음 화면을 그대로 돌려준다** —
// 사람은 "됐다"가 아니라 지금 상태를 본다(인터뷰 제출이 세운 규칙과 같다).
func pruneCardAct(in inPruneAct, run func(target string)) (*mcp.CallToolResult, any, error) {
	if repo := cardRepo(in.Repo); repo != "" {
		setRepoDir(repo)
	}
	target := strings.TrimSpace(in.Target)
	if target == "" {
		return cardResult(uiIvCard("어느 삭제 요청인지 모른다 — 화면이 대상을 안 실어 보냈다.")), nil, nil
	}
	if _, err := runGil(func() { run(target) }); err != nil {
		// 거부는 오류가 아니라 **사실**이다(이미 승인됐거나, 요청이 없거나). 사람은 화면에서
		// 그 사실을 읽어야 한다 — 프로토콜 오류로 올리면 카드가 통째로 빈칸이 된다.
		return cardResult(uiIvCard("돌지 않았다 — " + firstLine(err.Error()))), nil, nil
	}
	rememberUIRepo()
	var st statusOut
	if _, err := runGil(func() { st = gatherStatus() }); err != nil {
		return cardResult(uiIvCard("됐다.")), nil, nil
	}
	return cardResult(statusCardBodyHTML(st)), nil, nil
}

// pruneCardHTML — 승인을 기다리는 삭제 요청들. 없으면 "".
//
// **왜 요청 이유를 그대로 싣나.** 사람이 판단할 재료가 그것뿐이다 — "chain-x 를 지울까요"
// 만으로는 아무도 판단할 수 없다. 요청을 올린 쪽이 적은 문장을 요약하지 않고 그대로 보여준다.
func pruneCardHTML(st statusOut) string {
	if len(st.PendingPrunes) == 0 {
		return ""
	}
	var b strings.Builder
	for _, p := range st.PendingPrunes {
		b.WriteString(`<div class="box prune" data-prune="` + esc(p.Target) + `">`)
		b.WriteString(`<div class="t">🗑 삭제해도 될지 사람이 정해야 한다 — ` + esc(p.Target) + `</div>`)
		if w := strings.TrimSpace(p.Why); w != "" {
			b.WriteString(`<div class="md">` + mdToHTML(w) + `</div>`)
		}
		// **승인의 뜻을 문장으로 적는다.** 버튼 라벨만으로는 무엇이 일어나는지 모른다 —
		// 실제로 여기서 지워지는 것은 없고, 지우는 것은 터미널의 다음 한 수다.
		b.WriteString(`<div class="prunenote">승인해도 <b>지금 지워지지는 않는다</b> — ` +
			`실행에는 터미널에서 확인 문구가 한 번 더 필요하다. 되돌릴 수 없는 일이라 문을 둘로 나눠 뒀다.</div>`)
		b.WriteString(`<div class="acts">` +
			`<button class="btn primary" data-act="prune-approve" data-tool="gil_prune_approve"` +
			` data-target="` + esc(p.Target) + `"` +
			` data-arm="` + esc(p.Target+" 삭제를 승인한다 — 한 번 더") + `">삭제를 승인한다</button>` +
			// 거두는 것은 아무것도 안 지운다 — 무장 없이 한 번에 돈다. 갇힌 상태에서
			// 빠져나오는 길에 관문을 세우면, 그 관문은 사람을 가두는 데만 쓰인다.
			`<button class="btn" data-act="prune-withdraw" data-tool="gil_prune_withdraw"` +
			` data-target="` + esc(p.Target) + `" data-noarm="1">요청을 거둔다</button>` +
			`</div>`)
		b.WriteString(`</div>`)
	}
	return b.String()
}

// pruneCardCSS — 삭제 칸의 스타일. 붉은 테두리는 **되돌릴 수 없는 일**이라는 표시다.
const pruneCardCSS = `
.prune{border:1px solid var(--danger-line);background:var(--danger-bg);color:var(--danger-fg)}
.prune .t{font-weight:600;margin-bottom:6px}
.prunenote{font-size:12px;opacity:.85;margin:8px 0 2px}
`
