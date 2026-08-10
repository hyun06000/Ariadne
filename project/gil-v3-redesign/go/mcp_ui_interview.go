// mcp_ui_interview.go — **인터뷰가 카드 안에 선다** (상현님, 2026-08-10).
//
// 왜. 사람에게 묻는 통로가 이 표면에서 계속 없어졌다:
//
//	① 뷰어 폼 — 창을 청해야 뜨고, **시작하는 사람에겐 아직 창이 없다**.
//	② 호스트 네이티브 폼(Elicitation) — Claude Desktop 은 못 띄운다(2026-08-09 실측 두 판).
//	③ 그래서 남은 것이 대화다 — 에이전트가 질문을 하나씩 말로 묻는다(상현님 실사용).
//
// ③이 왜 나쁜가. 질문지는 **한 벌**인데 대화는 한 줄씩 흐른다. 사람은 앞 질문을 다시 볼 수
// 없고, 몇 개 남았는지 모르고, 고쳐 쓸 수 없다. 무엇보다 **에이전트가 사람의 말을 옮겨 적는
// 단계가 끼어든다** — gil 이 문법으로 지켜 온 단 하나("기준은 사람의 문장 그 자체다")가
// 거기서 옮겨쓰기가 된다. 요약도 정제도 창작이라고 못박아 놓고, 정작 답을 받는 자리를
// 에이전트의 타건에 맡긴 셈이다.
//
// 그런데 이 표면에는 **이미 서는 화면이 있다** — 상태 카드(MCP Apps 위젯). 게다가 카드 안
// 버튼이 실제 명령을 도는 통로도 이미 세워 뒀다(승인·기각). 인터뷰는 그 통로에 정확히 맞는
// 일이다: statusActionsHTML 이 적어 둔 규칙 그대로 — **gil 문법에 있는 것은 버튼이 직접 돌고,
// 없는 것은 대화로 넘긴다.** 인터뷰 답 확정은 문법에 있다(interviewResolve). 그러니 여기서 돈다.
//
// 그리고 답을 받는 툴은 **앱 전용으로 표시한다**(visibility: app). 그 표시는 벽이 아니라
// 힌트다 — 지키는 호스트가 모델의 목록에서 빼 준다(서버는 여전히 싣는다. 실측). 그러니
// 여기서 얻는 것은 "에이전트가 못 한다"가 아니라 **무심코 부르지 않는다**이다. 그 구분을
// registerInterviewSubmitTool 주석에 사실대로 적어 뒀다.
package main

import (
	"context"
	"encoding/json"
	"strconv"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// pendingIV — 지금 사람의 답을 기다리는 인터뷰 하나.
type pendingIV struct {
	Chain     string // 체인 이름 또는 개시 인터뷰 슬러그
	SHA       string
	Questions string // 커밋 본문의 ```gil-interview 펜스 안 JSON
}

// pendingInterviewsAll — **기다리는 인터뷰 전부**를 한 번에 훑는다(--branches).
//
// 왜 전부인가. 카드는 지금까지 **HEAD 가 선 체인 하나**만 봤다(gatherStatus → headChainCycle).
// 그런데 질문을 찾는 규칙은 처음부터 브랜치 전체였고, 세션은 goto·open·merge 로 HEAD 를
// 옮긴다. 그러면 **질문은 저장소에 살아 있는데 답할 폼이 없어진다** — 그리고 체인 밖(dev·main)
// 에 서 있으면 gatherStatus 가 조기 반환해 폼이 아예 안 뜬다. 요청을 올린 사람이 대개 서 있는
// 자리가 바로 거기다.
//
// 뷰어는 처음부터 전부 띄웠다(pendingInterviews). 카드가 뷰어를 대신하려면 같은 것을 봐야 한다.
// 그리고 **한 번만 훑는다** — 체인마다 부르면 같은 사실을 N 번 읽고, 그 N 개가 갈릴 자리가 된다.
//
// **최신 마커가 상태를 정한다**(#75) — 확정 뒤의 재인터뷰를 못 보면 안 된다.
func pendingInterviewsAll() []pendingIV {
	out := gitlog("--format="+trailer("Gil-Chain")+fsep+trailer("Gil-Intake")+fsep+
		trailer("Gil-Interview")+fsep+"%H"+fsep+"%B"+sep, "--branches", "--")
	settled := map[string]bool{} // 이 이름의 최신 마커를 이미 봤다
	var open []pendingIV
	for _, rec := range strings.Split(out, sep) {
		rec = strings.Trim(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		f := strings.SplitN(rec, fsep, 5)
		if len(f) < 5 {
			continue
		}
		ch, intake, iv, sha, body := strings.TrimSpace(f[0]), strings.TrimSpace(f[1]),
			strings.TrimSpace(f[2]), strings.TrimSpace(f[3]), f[4]
		// 개시 인터뷰는 Gil-Intake 로 산다(체인이 아직 없다). intake 커밋은 폼이 그려지도록
		// Gil-Chain 도 같은 값으로 달므로 둘 중 있는 것을 쓰면 된다.
		name := ch
		if name == "" {
			name = intake
		}
		if name == "" || iv == "" || settled[name] {
			continue
		}
		settled[name] = true // git log 는 새→옛 — 처음 만난 것이 최신이다
		if iv == "done" {
			continue
		}
		open = append(open, pendingIV{Chain: name, SHA: sha, Questions: extractInterviewJSON(body)})
	}
	return open
}

// pendingInterviewQuestions — 이 체인(또는 개시 인터뷰 슬러그)이 지금 기다리는 질문 JSON.
// 없으면 "". 판정은 위 pendingInterviewsAll 하나가 진다 — 두 벌이면 한쪽만 낡는다.
func pendingInterviewQuestions(chain string) string {
	for _, iv := range pendingInterviewsAll() {
		if iv.Chain == chain {
			return iv.Questions
		}
	}
	return ""
}

// interviewCardHTML — 기다리는 질문을 **카드 안 폼**으로 그린다. 없으면 "".
//
// 여기서 지키는 것 둘:
//   - **답을 미리 채우지 않는다.** 기본값도, 예시도, 자리표시자에 그럴듯한 문장도 넣지 않는다.
//     사람이 빈 칸을 보고 자기 문장을 쓰는 것이 이 폼의 존재 이유다(#90 이 세운 것).
//   - **몇 개 중 몇 번째인지 보인다.** 대화로 물을 때 사라졌던 것이 그거다 — 사람은 앞 질문을
//     다시 볼 수 없었고 얼마나 남았는지 몰랐다.
func interviewCardHTML(chain string) string {
	raw := pendingInterviewQuestions(chain)
	if strings.TrimSpace(raw) == "" {
		return ""
	}
	var qs []interviewQ
	if json.Unmarshal([]byte(raw), &qs) != nil || len(qs) == 0 {
		return ""
	}
	var b strings.Builder
	b.WriteString(`<div class="box iv" data-iv="` + esc(chain) + `">`)
	b.WriteString(`<div class="t">📋 사람에게 묻는다 — 답이 이 일의 기준이 된다</div>`)
	b.WriteString(`<div class="ivnote">여기 적은 문장이 <b>그대로</b> 목적과 성패 기준이 된다. ` +
		`요약하지 않고 인용된다 — 편한 말로 적어도 된다.</div>`)
	for i, q := range qs {
		base := "q" + strconv.Itoa(i+1)
		b.WriteString(`<div class="ivq"><div class="ivlbl">` +
			strconv.Itoa(i+1) + `/` + strconv.Itoa(len(qs)) + `. ` + esc(q.Q) + `</div>`)
		switch q.Type {
		case "radio":
			for j, o := range q.Options {
				id := base + "_r" + strconv.Itoa(j+1)
				b.WriteString(`<label class="ivopt"><input type="radio" name="` + esc(base) +
					`" id="` + esc(id) + `" data-q="` + esc(base) + `" value="` + esc(o) +
					`"> <span>` + esc(o) + `</span></label>`)
			}
		case "checkbox":
			for j, o := range q.Options {
				key := base + "_o" + strconv.Itoa(j+1)
				b.WriteString(`<label class="ivopt"><input type="checkbox" data-q="` + esc(key) +
					`" value="` + esc(o) + `"> <span>` + esc(o) + `</span></label>`)
			}
		default: // text
			b.WriteString(`<textarea class="ivin" data-q="` + esc(base) + `" rows="3"></textarea>`)
		}
		b.WriteString(`</div>`)
	}
	// 제출도 두 번 눌러야 돈다(껍데기의 무장 규칙). **그 되묻는 문구가 무엇을 확정하는지
	// 말하게 한다** — 공용 문구 "정말? — 한 번 더" 는 되묻기만 하고 아무것도 안 알려 준다.
	// 여기서 확정되는 것은 이 체인의 기준이고, 그건 되묻을 값이 있는 일이다.
	b.WriteString(`<div class="acts">` +
		`<button class="btn primary" data-act="interview-submit" data-chain="` + esc(chain) +
		`" data-arm="이 문장이 기준이 된다 — 한 번 더">답을 제출한다</button></div>`)
	b.WriteString(`<div class="ivnote">제출하면 이 답이 기록에 남고, 그때부터 다음 칸으로 간다. ` +
		`아직 생각 중이면 그냥 두면 된다 — 창을 닫아도 질문은 사라지지 않는다.</div>`)
	b.WriteString(`</div>`)
	return b.String()
}

// interviewCardCSS — 폼 조각의 스타일. 카드의 변수(--line·--card…)를 그대로 쓴다.
const interviewCardCSS = `
.iv{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:8px 0}
.iv .t{font-weight:600;margin-bottom:4px}
.ivnote{font-size:12px;opacity:.75;margin:4px 0 8px}
.ivq{margin:10px 0}
.ivlbl{font-size:13px;font-weight:600;margin-bottom:4px}
.ivin{width:100%;box-sizing:border-box;border:1px solid var(--line);border-radius:8px;
 padding:7px 9px;font:13px/1.5 inherit;background:var(--card);color:inherit;resize:vertical}
.ivopt{display:flex;align-items:flex-start;gap:6px;margin:3px 0;font-size:13px}
.ivopt input{margin-top:3px}
`

// ── 답을 받는 자리 ──

type inInterviewSubmit struct {
	Repo    string `json:"repo,omitempty" jsonschema:"어느 저장소인가(절대경로)"`
	Chain   string `json:"chain" jsonschema:"답이 붙을 체인 이름(또는 개시 인터뷰 슬러그)"`
	Answers string `json:"answers" jsonschema:"사람이 폼에 적은 답 JSON — {\"q1\":\"…\",\"q2_o1\":true}"`
}

func (i inInterviewSubmit) repoArg() string { return i.Repo }

// registerInterviewSubmitTool — 화면이 사람의 답을 되돌리는 통로.
//
// **앱 전용은 벽이 아니라 힌트다 — 여기서 그걸 정확히 적는다.** `visibility: ["app"]` 은
// 규범이 주는 표시이고, 그걸 지키는 호스트가 모델의 툴 목록에서 빼 준다. 서버는 여전히
// tools/list 에 싣는다(실측: 날 프로토콜로 물으면 그대로 보인다). 그러니 "에이전트는 답을
// 대신 제출할 수 없다"고 말하면 **그건 사실이 아니다** — 지키는 호스트에서만 참이다.
//
// 구분 못 하는 것을 단언하지 않는 것이 이 저장소의 태도이므로(#57), 이 자리의 값은 이렇게
// 적는다: 표시는 **미끄러짐을 막고**(모델이 목록에서 보고 무심코 부르는 일이 없어진다),
// 답이 사람의 것이라는 **판정은 다른 곳이 진다** — 폼이 사람 화면에 서고, 사람이 적은 값이
// 그대로 인용되며, 그 사실이 커밋에 남는다. gil guard 가 훅과 fsck 를 가른 것과 같은 모양이다
// (예방은 미끄러짐을 막고, 판정은 탐지가 한다).
func registerInterviewSubmitTool(s *mcp.Server) {
	mcp.AddTool(s, &mcp.Tool{
		Name: "gil_interview_submit",
		Description: "앱 전용 — 사람이 카드 폼에 적은 인터뷰 답을 확정한다. 모델이 부를 것이 " +
			"아니다(답은 사람이 쓴다). 인터뷰를 여는 것은 gil_interview·gil_intake 다.",
		Meta: mcp.Meta{"ui": map[string]any{"visibility": []string{"app"}}},
	}, func(ctx context.Context, req *mcp.CallToolRequest, in inInterviewSubmit) (*mcp.CallToolResult, any, error) {
		defer dropTempFiles()
		if repo := cardRepo(in.Repo); repo != "" {
			setRepoDir(repo)
		}
		chain := strings.TrimSpace(in.Chain)
		if chain == "" {
			return cardResult(uiIvCard("어느 인터뷰인지 모른다 — 화면이 체인 이름을 안 실어 보냈다.")), nil, nil
		}
		raw := pendingInterviewQuestions(chain)
		if strings.TrimSpace(raw) == "" {
			// **이미 확정됐거나 그런 인터뷰가 없다.** 오류가 아니라 사실이다 — 사람이 두 번
			// 눌렀을 수도 있고, 그사이 다른 자리에서 확정됐을 수도 있다.
			return cardResult(uiIvCard("기다리는 질문이 없다 — 이미 답이 확정됐거나 취소된 인터뷰다.")), nil, nil
		}
		var qs []interviewQ
		if json.Unmarshal([]byte(raw), &qs) != nil {
			return cardResult(uiIvCard("질문을 읽지 못했다.")), nil, nil
		}
		var ans map[string]any
		if json.Unmarshal([]byte(orDefault(in.Answers, "{}")), &ans) != nil {
			return cardResult(uiIvCard("답을 읽지 못했다.")), nil, nil
		}
		// **빈 제출은 받지 않는다.** 빈 채로 확정하면 기준이 빈 문서가 되고, 그 뒤의 모든
		// 판정이 빈 자를 대고 재는 일이 된다(형해화). 화면이 막지만 여기서도 막는다 —
		// 판정이 화면에만 있으면 다음 화면이 그걸 잊는다.
		if !answersHaveContent(ans) {
			return cardResult(uiIvCard("아직 아무것도 적히지 않았다 — 한 칸이라도 채워야 확정된다.")), nil, nil
		}
		ref := mcpAssembleReference(chain, qs, ans)
		tmp := writeTempTracked("gil-reference-*.md", ref)
		if tmp == "" {
			return cardResult(uiIvCard("답을 저장하지 못했다.")), nil, nil
		}
		if _, err := runGil(func() { intakeMode = chain; interviewResolve(chain, tmp) }); err != nil {
			return cardResult(uiIvCard("확정하지 못했다 — " + firstLine(err.Error()))), nil, nil
		}
		rememberUIRepo()
		var st statusOut
		if _, err := runGil(func() { st = gatherStatus() }); err != nil {
			return cardResult(uiIvCard("답이 확정됐다.")), nil, nil
		}
		// 확정 뒤의 화면을 그대로 돌려준다 — 사람은 "됐다"가 아니라 **다음이 무엇인지**를 본다.
		return cardResult(statusCardBodyHTML(st)), nil, nil
	})
}

// answersHaveContent — 한 칸이라도 채워졌나(빈 문자열·false 는 안 채운 것으로 본다).
func answersHaveContent(ans map[string]any) bool {
	for _, v := range ans {
		switch t := v.(type) {
		case string:
			if strings.TrimSpace(t) != "" {
				return true
			}
		case bool:
			if t {
				return true
			}
		}
	}
	return false
}

// uiIvCard — 인터뷰 통로가 무언가 말해야 할 때의 **카드**(오류가 아니다). 화면은 언제나
// 무언가를 말해야 하고, 못 하는 것은 못 한다고 말해야 한다(mcp_ui_card.go 와 같은 태도).
func uiIvCard(msg string) string {
	return `<div class="card"><div class="crumb">gil · 인터뷰</div>` +
		`<div class="box wait"><div class="t">📋 인터뷰</div><div>` + esc(msg) + `</div></div></div>`
}

func firstLine(s string) string {
	if i := strings.Index(s, "\n"); i >= 0 {
		return s[:i]
	}
	return s
}

// (interviewFaceHTML 은 은퇴했다 — 폼을 고르는 자리가 statusOut.Waiting 이었고, 그 값은
// HEAD 커밋의 트레일러가 정한다. 이제 카드는 statusOut.OpenInterviews 를 돌며 **기다리는
// 것 전부**를 그린다. 하나만 고르는 함수가 남아 있으면 다음에 누군가 그걸 다시 쓴다.)
