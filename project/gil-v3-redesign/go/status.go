// status.go — **지금 어디, 개입할 때인가**를 한 번에 답한다 (상현님).
//
// 왜 새 명령인가. 뷰어의 마찰은 UI 완성도가 아니라 **성격이 다른 두 요구가 한 화면에 섞인
// 것**이었다. 작업 중에 필요한 건 "지금 어디, 사람이 나설 자리인가" 세 줄이고, 전체 그래프는
// 다 끝난 뒤에 한 번 읽는 물건이다. 전자를 보려고 브라우저를 띄우는 것이 비용의 정체다.
//
// 그리고 이 자리는 **고정된 화면보다 에이전트가 낫다**. gil 은 애초에 에이전트가 모는 도구라
// 사람이 CLI 를 직접 치지 않는다. "두 번째랑 세 번째 시도가 뭐가 달랐어?" 같은 질문에 답하는
// 뷰어는 만들 수 없지만, 데이터가 있으면 에이전트는 그냥 답한다. 그러니 gil 은 **데이터만**
// 낸다 — 그리는 규칙은 코드가 아니라 문서(스킬)에 둔다. 화면을 Go 에 박으면 이 방식의
// 값어치를 그 자리에서 버린다.
//
// 무엇을 담지 않는가. **그래프를 담지 않는다.** 노드 목록·엣지·레이아웃은 여기 없다.
// 그건 "다 끝난 뒤 한 번" 쪽의 요구고, 여기 섞으면 이 명령도 뷰어와 같은 병에 걸린다.
// 담는 것은 지금 선 자리와 **다음 한 수**, 그리고 사람이 나설 자리뿐이다.
//
// 파생이지 기록이 아니다. 이 JSON 은 커밋 그래프에서 매번 계산된다 — 어디에도 저장하지
// 않는다. 저장하면 진실원이 둘이 되고, 갈리면 사람이 어느 쪽을 믿을지 모른다(이 저장소가
// 반복해서 앓은 병).
package main

import (
	"encoding/json"
	"os"
	"sort"
	"strings"
)

type statusChain struct {
	Name      string `json:"name"`
	Purpose   string `json:"purpose,omitempty"`
	Mode      string `json:"mode,omitempty"`
	Interview string `json:"interview"` // none|pending|approved — 기준 문서의 상태
	// Criterion — **무엇이 관측되면 이 체인이 풀린 것인가.** 사람이 세운 판정 문장.
	//
	// 왜 여기 있나. 승인·기각을 묻는 자리에서 기준이 없으면 그 물음은 의미가 없다 — 무엇에
	// 비추어 판단하라는 건지가 없으니까. 지금까지 이 문장은 chain-root 커밋 트레일러에만
	// 있어서, 읽으려면 그 커밋을 스스로 찾아 열어야 했다(자기규율).
	Criterion string `json:"criterion,omitempty"`
}

// statusStepNode — 사이클 스텝 하나. **띠를 그리는 재료 전부**가 여기 있다.
//
// 왜 이걸 싣나. 이 넷이 없으면 그리는 쪽이 git log 를 직접 뒤져야 하고, 세션마다 다르게
// 뒤진다. 실측으로 값을 치렀다: 손으로 그리는 동안 없는 간선을 지어내고(s9→s8), 있는
// 간선을 빠뜨리고(s12→s14), 브랜치 이름을 분기로 읽어 없는 갈라짐을 만들었다(three-curves).
// 셋 다 데이터를 안 보고 그려서 난 일이다.
type statusStepNode struct {
	ID     string `json:"id"`
	Kind   string `json:"kind"`
	Parent string `json:"parent,omitempty"`
	Back   string `json:"back,omitempty"` // 되돌아간 자리(Gil-Backtrack) — 없으면 빈 값
}

type statusCycle struct {
	Name string `json:"name"`
	// Purpose — 이 사이클이 무엇을 풀려는가(Gil-Cycle-Purpose). **define 카드의 몸통이다.**
	//
	// 지금까지 이 문장은 스텝 제목에 앞머리와 함께 붙어서만 나왔다("gil c/cy/s1 define: …").
	// 카드에 그걸 그대로 실으면 사람이 읽을 자리에 주소가 앉는다.
	Purpose string `json:"purpose,omitempty"`
	// Steps — 이 사이클의 스텝 전부(선언 순). 그리는 규칙은 docs/gil/status-card.md.
	Steps []statusStepNode `json:"steps"`
	// Inherit — 이 사이클이 앞에서 물려받은 것. define 카드의 **근거** 칸이 이것이다.
	// 왜 이 문제를 정의했는지는 대개 앞 사이클이 남긴 문장에 있다.
	Inherit    string `json:"inherit,omitempty"`
	Hypothesis string `json:"hypothesis,omitempty"`
	RefutesIf  string `json:"refutes_if,omitempty"`
	Plan       string `json:"plan,omitempty"`
	FalsifyTo  string `json:"falsify_to,omitempty"` // 반증되면 물러설 자리(퇴로)
	// Advances — 이 가설이 **체인 목적에 얼마나·어떻게 다가서게 하나**(Gil-Advances).
	//
	// hypothesis 카드의 "이걸 왜 재나" 칸이다. 반증조건만 있으면 카드는 "무엇을 재나"까지만
	// 답하고, 그 측정이 체인의 판정 기준과 무슨 상관인지는 사람이 스스로 이어야 한다.
	Advances string `json:"advances,omitempty"`
	// DespiteMap — 벽의 지도(falsify_to)와 **다른 자리**에서 갈라진 이유(Gil-Despite-Map, #105).
	//
	// 이건 삼키면 안 된다. 지도를 벗어난 재분기는 `--despite` 없이는 문법이 거부하는 것이고,
	// 그 이유는 사람이 판단해야 할 재료다. 감추면 두 계획이 동시에 유효한 것처럼 보인다.
	DespiteMap string `json:"despite_map,omitempty"`
	// Measured — 이 자리에서 **가장 가까운 verify 가 무엇을 재서 무엇이 나왔나**.
	//
	// 왜 사이클에 있나. verify 스텝의 판정(verdict·반증조건 충족 여부·관측·설계 유지 여부)은
	// 지금까지 status 에 **아예 나오지 않았다** — 카드를 만들다 잡았다. 그래서 verify 카드는
	// 그릴 것이 없었고, analyze·success·fail 카드도 "무엇을 재서 그렇게 됐나"에 답할 수
	// 없었다. 그 넷이 다 이 하나를 본다: 두 자리에서 따로 세면 같은 측정이 다르게 읽힌다.
	//
	// **가장 가까운 조상**이다(가설과 같은 규칙) — 형제 가지가 있으면 사이클에서 아무 verify 나
	// 집는 것은 지금 선 가지의 측정이 아니다.
	Measured *statusMeasure `json:"measured,omitempty"`
	// Competing — 지금 이 자리에서 **나란히 겨루는** 형제 갈래들(#106·#107·#112).
	//
	// 왜 status 에도 있나. v3.55.0 이 형제 비교를 뷰어에 그렸는데, 그 화면은 브라우저를 띄운
	// 사람만 본다. 경합의 요점은 **비교**고, 비교할 자리가 없으면 갈래는 열어 둔 채 잊힌다 —
	// 우리가 없애려던 그 매달린 잎이다. 하나뿐이면 경합이 아니라 그냥 재분기라 비운다.
	Competing []statusSibling `json:"competing,omitempty"`
}

// statusMeasure — 한 번의 측정이 남긴 것 전부. verify 카드의 몸통이고, 그 뒤 세 카드
// (analyze·success·fail)가 "무엇을 딛고 있나"를 말할 때 쓰는 근거다.
//
// 왜 관측(Observed)이 판정(Verdict)과 따로 있나. gil 은 둘을 따로 받는다 —
// `--verdict supported|refuted` 는 **가설에 대한 판정**이고, `--falsify-met|--falsify-unmet
// <무엇을 관측했나>` 는 **반증조건에 대한 답**이다. 규칙 17 이 그 둘의 모순을 막는다(충족됐는데
// supported 는 거부). 카드에서 판정만 보이고 관측이 사라지면 사람은 그 판정을 검산할 수 없다.
type statusMeasure struct {
	Step     string `json:"step"`
	Verdict  string `json:"verdict,omitempty"`         // supported | refuted — 이 측정이 가설을 지지했나
	Falsify  string `json:"falsify_outcome,omitempty"` // met | unmet — 반증조건이 관측됐나
	Observed string `json:"observed,omitempty"`        // 그 판단의 근거가 된 관측
	// Plan* — 재기 전에 못박은 설계가 실측에서 유지됐나(이슈 #76). **broke 는 강한 신호다**:
	// 잰 것이 못박은 것과 다르면, 그 측정은 다른 물건을 잰 것이다. 사람이 기각할 근거가
	// 여기 있는데 카드가 안 보여주면 그 자리는 없는 것과 같다.
	PlanOutcome string `json:"plan_outcome,omitempty"` // held | broke
	PlanDiff    string `json:"plan_diff,omitempty"`    // 깨졌으면 무엇이 달랐나
}

// 측정을 **사람이 쓰는 말로** 옮긴다. 필드 이름(`supported`·`met`·`broke`)을 그대로 읽지
// 마라 — status-card.md 가 못박은 규칙이고, 여기 한 곳에 두어야 카드와 터미널이 같은 말을 한다.
func verdictWord(v string) string {
	switch v {
	case "supported":
		return "가설을 지지했다"
	case "refuted":
		return "가설을 반증했다"
	}
	return v
}

func falsifyWord(f string) string {
	switch f {
	case "met":
		return "반증조건이 관측됐다"
	case "unmet":
		return "반증조건은 관측되지 않았다"
	}
	return f
}

// measureLine — 한 줄짜리 측정 요약(짧은 형태·카드가 함께 쓴다).
func measureLine(m *statusMeasure) string {
	var parts []string
	if w := verdictWord(m.Verdict); w != "" {
		parts = append(parts, w)
	}
	if w := falsifyWord(m.Falsify); w != "" {
		parts = append(parts, w)
	}
	if m.Observed != "" {
		parts = append(parts, "관측: "+clip(m.Observed, 70))
	}
	// 설계가 깨진 것은 **짧은 형태에서도 사라지면 안 된다** — 잰 것이 못박은 것과 다르면
	// 그 측정은 다른 물건을 잰 것이고, 그게 사람이 기각할 가장 큰 근거다.
	if m.PlanOutcome == "broke" {
		parts = append(parts, "⚠ 정한 방법대로 실행되지 않았다")
	}
	return strings.Join(parts, " · ")
}

// statusSibling — 경합의 한 갈래. hypothesis 카드에서 **나란히 놓는 한 줄**이다.
//
// 상태를 어떻게 아나. 그 갈래의 잎이 말한다 — 뷰어(competitionsJSON)와 **같은 규칙**이다.
// 두 창구가 경합의 승패를 다르게 세면 사람은 어느 쪽을 믿을지 모른다.
type statusSibling struct {
	ID         string `json:"id"` // 갈래의 뿌리(--competing 을 선언한 그 가설)
	Hypothesis string `json:"hypothesis,omitempty"`
	RefutesIf  string `json:"refutes_if,omitempty"`
	Plan       string `json:"plan,omitempty"`
	Leaf       string `json:"leaf,omitempty"` // 그 갈래가 지금 선 자리
	State      string `json:"state"`          // open | won | lost | fail
	LostTo     string `json:"lost_to,omitempty"`
	Current    bool   `json:"current,omitempty"` // 내가 밟고 있는 갈래
}

// statusVerdict — 이 체인에서 **마지막으로 닫힌 사이클**과 그 판정.
//
// 왜. 사람이 가장 자주 묻는 것이 "왜 실패했어"인데, 그 답의 재료가 지금 어디에도 없었다.
// 지금 선 자리(step)만으로는 답할 수 없다 — 실패는 이미 닫힌 사이클에 있다.
type statusVerdict struct {
	Cycle  string `json:"cycle"`
	Result string `json:"result"` // success | fail | pending
	Why    string `json:"why,omitempty"`
}

// statusRollback — 되돌아갈 수 있는 자리 하나.
//
// 왜 이게 중요한가. gil reject --to / close --verdict fail --to 는 "조상 define" 을
// 문자열로 받는데, **비개발자는 그 문자열을 알 방법이 없다.** 그래프를 읽고 스텝 번호를
// 세어야 나온다. 후보를 사람이 읽을 수 있는 라벨과 함께 내주면 그 자리가 사라진다 —
// 이 도구의 비개발자 진입 장벽에서 가장 단단한 부분이다.
type statusRollback struct {
	ID    string `json:"id"`
	Kind  string `json:"kind"`  // define | analyze — --to 가 받는 두 kind
	Label string `json:"label"` // 사람이 읽는 한 줄
	// Discards — 여기로 되돌리면 버려지는 스텝들.
	//
	// 목록만으로는 고를 수 없다. 사람이 알고 싶은 것은 스텝 번호가 아니라 **되돌리면
	// 무엇을 잃는가**다 — "s4" 와 "s5~s7 이 버려진다"는 다른 정보고, 판단은 후자로 한다.
	Discards []string `json:"discards"`
}

type statusStep struct {
	ID      string `json:"id"`
	Kind    string `json:"kind"`
	Subject string `json:"subject,omitempty"`
	SHA     string `json:"sha,omitempty"`
	// Body — 이 스텝의 본문(트레일러 제외). define 카드가 **원문**을 함께 두는 자리다.
	//
	// 왜 필요한가. 문제정의를 물음으로 다시 쓰는 것은 읽기 보조고, 원문을 함께 두지 않으면
	// 지어내서 감춘 것이 된다(status-card.md). 그런데 지금까지 본문은 status 에 없어서
	// 원문을 둘 방법이 아예 없었다 — 그리는 쪽이 커밋을 스스로 열어야 했다.
	Body string `json:"body,omitempty"`
	// 아래 셋은 **kind 마다 다른 자리에서 본문이 된다.** analyze 는 결론이, success·fail 은
	// 판정 기준과의 대조와 다음 설계가 카드의 몸통이다. 트레일러엔 이미 있었는데 여기로
	// 안 나와서, 그리는 쪽이 커밋 본문을 스스로 열어야 했다(자기규율).
	Finding    string `json:"finding,omitempty"`     // analyze — 이 분석이 밝힌 것 한 줄
	Toward     string `json:"toward,omitempty"`      // success·fail — 체인 목적에 얼마나 다가섰나
	NextDesign string `json:"next_design,omitempty"` // success·fail — 다음 설계
}

// statusWaiting — 사람이 나설 자리. **null 이 아니면 그것이 지금 유일하게 할 일이다.**
//
// 이 필드가 이 JSON 의 존재 이유다. 나머지는 이걸 읽기 위한 맥락이다 — 사람이 이 시스템에
// 값을 더하는 순간은 그래프를 볼 때가 아니라 "그거 검증할 값어치 있나"와 "어디까지
// 되돌릴까" 두 지점이고, 그 두 순간이 여기로 나온다.
type statusWaiting struct {
	Kind   string `json:"kind"` // interview | approval
	Chain  string `json:"chain"`
	What   string `json:"what"`          // 무엇을 기다리나(사람 언어)
	Answer string `json:"how_to_answer"` // 사람이 답하면 무엇이 풀리나 / 에이전트가 칠 한 수
}

type statusOut struct {
	Repo        string           `json:"repo"`
	Branch      string           `json:"branch,omitempty"`
	Chain       *statusChain     `json:"chain"`
	Cycle       *statusCycle     `json:"cycle"`
	Step        *statusStep      `json:"step"`
	Waiting     *statusWaiting   `json:"waiting_for_human"`
	LastVerdict *statusVerdict   `json:"last_verdict"`
	Rollback    []statusRollback `json:"rollback_candidates"`
	Next        []string         `json:"next"`
	// RenderGuide — **이 데이터를 사람에게 보여주는 규칙이 어디 있나.**
	//
	// 왜 데이터에 문서 경로를 싣나. 규칙을 문서에만 두면 "에이전트가 알아서 읽기"가 되고,
	// 그건 자기규율이다 — 이 저장소가 반복해서 확인한 대로 자기규율은 원리적으로 불충분하다
	// (#55·#45). 데이터를 읽는 순간 규칙의 자리도 함께 알게 하면, 읽을 이유가 있는 자리에서
	// 읽힌다. 화면을 Go 에 박지 않으면서 규칙이 도달하는 유일한 길이다.
	RenderGuide string   `json:"render_guide"`
	Warnings    []string `json:"warnings"`
}

func cmdStatus(args []string) {
	fs := newFlags("gil status")
	asJSON := fs.boolFlag("json")
	// --card — 카드 한 장을 HTML 로 낸다. **MCP 호스트만 그리는 화면은 검증할 수 없다**:
	// 지금까지 이 카드는 어떤 시험도 안 지나갔고(실측), 그래서 정작 그리는 규칙을 지키는지
	// 아무도 몰랐다. 여기로 내면 시험이 실제로 읽고, 사람도 파일로 저장해 열어 볼 수 있다.
	asCard := fs.boolFlag("card")
	fs.parse(args)
	st := gatherStatus()
	if *asCard {
		println2(statusCardHTML(st))
		return
	}
	if *asJSON {
		b, err := json.MarshalIndent(st, "", "  ")
		if err != nil {
			die("gil status: JSON 을 만들지 못했다: " + err.Error())
		}
		println2(string(b))
		return
	}
	// 사람이 터미널에서 칠 때를 위한 짧은 형태. **JSON 과 같은 값을 말한다** — 두 출력이
	// 다른 것을 세면 어느 쪽이 사실인지 알 수 없게 된다.
	for _, ln := range statusLines(st) {
		println2(ln)
	}
}

func gatherStatus() statusOut {
	wd, _ := os.Getwd()
	st := statusOut{Repo: wd, Branch: currentBranch(), Next: []string{}, Warnings: []string{},
		Rollback:    []statusRollback{},
		RenderGuide: "docs/gil/status-card.md — 이 데이터를 사람에게 어떻게 보여줄지. 통째로 붙여넣지 마라."}

	chain, cycle := headChainCycle()
	// 팁이 gil 커밋이 아니면 **거슬러 올라가 가장 가까운 gil 커밋**을 쓴다.
	//
	// 왜 그냥 "체인 밖"이라 답하지 않나. 실측(AIL): 체인 가지 끝에 트레일러 없는 평범한 git
	// 커밋이 얹혀 있었다 — #116 이 "괴리의 주범"이라 부른 그 자리다. 그때 팁만 보면 gil 은
	// "아직 아무것도 안 열렸다"고 답하는데, 사람은 사이클 한복판에 서 있다. 도구가 사람의
	// 현실과 다른 것을 말하면 사람은 도구를 끈다.
	//
	// 다만 **조용히 메우지는 않는다.** 거슬러 오른 만큼을 세어 경고로 낸다 — 그 커밋들의
	// 변경은 어느 스텝의 것도 아니고, 그 뒤 gil 이 세는 모든 것이 실제와 갈린다. 메우기만
	// 하고 입을 다물면 #116 이 탐지로 세운 신호를 이 화면이 도로 지운다.
	plain, tipSHA := 0, strings.TrimSpace(git("rev-parse", "HEAD"))
	if chain == "" {
		plain, chain, cycle, tipSHA = walkBackToGil()
	}
	if plain > 0 {
		st.Warnings = append(st.Warnings, "이 가지 끝에 gil 밖 커밋 "+itoa(plain)+
			"개가 얹혀 있다 — 그 변경은 어느 스텝의 것도 아니다(gil guard 로 막을 수 있다).")
	}
	if chain == "" {
		// 층에 서 있거나(dev·main) 아직 아무것도 안 열렸다. 없는 것을 지어내지 않는다 —
		// 빈 값을 채워 넣으면 화면은 그럴듯해지고 판단은 틀려진다.
		st.Next = append(st.Next, "gil intake   — 체인보다 먼저 사람에게 묻는다(개시 인터뷰)")
		return st
	}

	agg, _ := chainsFromGraph()
	sc := statusChain{Name: chain, Purpose: chainPurpose(chain, "--branches"), Interview: interviewState(chain)}
	if a, ok := agg[chain]; ok {
		sc.Mode = a.mode
	}
	sc.Criterion = chainCriterionOf(chain)
	st.Chain = &sc
	st.LastVerdict = lastVerdictOf(chain)

	if cycle != "" {
		st.Cycle = &statusCycle{Name: cycle}
		nodes := cycleNodesOf(chain, cycle)
		// 가설은 **가장 가까운 조상**의 것이다 — 형제 가지가 있으면 사이클 전체에서 아무거나
		// 집으면 지금 서 있는 가지의 것이 아니다(#106 이 세운 경합에서 특히).
		byID := map[string]node{}
		for _, n := range nodes {
			byID[n.step] = n
		}
		st.Cycle.Steps = cycleStepNodes(nodes)
		for _, n := range nodes {
			if n.kind == "define" && n.inherit != "" {
				st.Cycle.Inherit = n.inherit
				break
			}
		}
		st.Cycle.Purpose = cyclePurpose(chain, cycle, "--branches")
		if tip, ok := headStepNode(nodes, tipSHA); ok {
			st.Step = &statusStep{ID: tip.step, Kind: tip.kind, Subject: tip.subject, SHA: clip(tip.sha, 12),
				Body: stepBodyOf(tip.sha), Finding: tip.finding, Toward: tip.toward, NextDesign: tip.nextDesign}
			if h, ok := nearestKindUp(byID, tip, "hypothesis"); ok {
				// gil 이 붙인 앞머리("gil c/cy/s3 hypothesis: ")를 걷는다 — 카드에 그대로
				// 실리면 사람이 읽을 자리에 주소가 앉는다(경합 목록은 이미 걷고 있었고,
				// 두 자리가 다른 꼴로 나오면 같은 문장이 다른 것처럼 보인다).
				st.Cycle.Hypothesis = humanLabel(h.subject)
				st.Cycle.RefutesIf = h.falsify
				st.Cycle.Plan = h.plan
				st.Cycle.FalsifyTo = h.falsifyTo
				st.Cycle.Advances = h.advances
				st.Cycle.DespiteMap = h.despiteMap
			}
			// 무엇을 재서 무엇이 나왔나. 가설과 **같은 규칙**(가장 가까운 조상)이다 —
			// 형제 가지가 있을 때 사이클에서 아무 verify 나 집으면 이 가지의 측정이 아니다.
			if v, ok := nearestKindUp(byID, tip, "verify"); ok {
				st.Cycle.Measured = &statusMeasure{Step: v.step, Verdict: v.verdict,
					Falsify: v.falsifyOut, Observed: v.falsifyObs,
					PlanOutcome: v.planOutcome, PlanDiff: v.planDiff}
			}
			st.Cycle.Competing = competingSiblings(nodes, tip)
			st.Next = nextMoves(chain, cycle, tip)
			st.Rollback = rollbackCandidates(byID, tip)
		}
	}

	// 사람이 나설 자리. 인터뷰가 먼저다 — 그게 안 풀리면 사이클 자체를 못 연다.
	switch interviewState(chain) {
	case "pending":
		st.Waiting = &statusWaiting{Kind: "interview", Chain: chain,
			What:   "체인 기준 문서에 대한 사람의 답",
			Answer: "사람이 답하면 사이클을 열 수 있다. 상태 확인: gil interview " + chain + " --status"}
	case "none":
		st.Warnings = append(st.Warnings,
			"이 체인엔 사람이 승인한 기준 문서가 없다 — 이대로는 사이클을 못 연다(gil interview "+chain+" --ask …).")
	}
	// 종결 pending 은 **스텝 노드가 아니라 종결 커밋**에 산다 — 스텝 목록만 보면 그 앞의
	// analyze 가 잡히고, 사람을 기다리는 중이라는 사실이 통째로 사라진다(실측: 시험 하나가
	// 이 자리를 잡았다). 그러니 지금 선 커밋의 kind 를 직접 읽는다.
	if st.Waiting == nil && trailerOf(tipSHA, "Gil-Kind") == "pending" {
		st.Waiting = &statusWaiting{Kind: "approval", Chain: chain,
			What: "이 스텝에 대한 사람의 승인 또는 기각",
			Answer: "승인하려면 gil approve\n" +
				"기각하려면 gil reject --to <조상 define>\n" +
				"사람의 답 전엔 이 사이클을 못 이어간다."}
	}

	if ln := behindLine(chain, ""); ln != "" {
		st.Warnings = append(st.Warnings, strings.TrimSpace(strings.ReplaceAll(ln, "\n", " ")))
	}
	return st
}

// stepBodyOf — 그 커밋의 본문(트레일러 문단 제외). 없으면 빈 값.
//
// **자르지 않는다.** 이 본문은 스텝의 보고서고(가설 근거·문제정의·관측), 줄이면 사람이
// 판단할 재료가 사라진다. 화면에서 접는 것은 그리는 쪽의 몫이다 — 데이터가 미리 잘라
// 버리면 접었다 펴는 것조차 불가능해진다.
func stepBodyOf(sha string) string {
	if sha == "" {
		return ""
	}
	out, err := gitTry("log", "-1", sha, "--format=%b")
	if err != nil {
		return ""
	}
	// 마지막 문단이 전부 트레일러면 걷어낸다(그건 기계의 말이고 사람의 보고서가 아니다).
	paras := strings.Split(strings.TrimSpace(out), "\n\n")
	if n := len(paras); n > 0 {
		allTrailer := true
		for _, ln := range strings.Split(strings.TrimSpace(paras[n-1]), "\n") {
			if ln == "" || strings.HasPrefix(ln, " ") || strings.HasPrefix(ln, "\t") {
				continue
			}
			if !strings.HasPrefix(ln, "Gil-") {
				allTrailer = false
				break
			}
		}
		if allTrailer {
			paras = paras[:n-1]
		}
	}
	return strings.TrimSpace(strings.Join(paras, "\n\n"))
}

// chainCriterionOf — 이 체인의 판정 문장(chain-root 의 Gil-Chain-Criterion).
func chainCriterionOf(chain string) string {
	const fs, rs = "\x1f", "\x1e"
	out, err := gitTry("log", "--branches",
		"--format=%(trailers:key=Gil-Chain,valueonly,unfold)"+fs+
			"%(trailers:key=Gil-Chain-Criterion,valueonly,unfold)"+rs)
	if err != nil {
		return ""
	}
	for _, rec := range strings.Split(out, rs) {
		f := strings.SplitN(rec, fs, 2)
		if len(f) < 2 || strings.TrimSpace(f[0]) != chain {
			continue
		}
		if c := strings.TrimSpace(f[1]); c != "" {
			return c
		}
	}
	return ""
}

// lastVerdictOf — 이 체인에서 마지막으로 닫힌 사이클과 판정. 없으면 nil.
func lastVerdictOf(chain string) *statusVerdict {
	for _, n := range collectNodes("--branches") { // 새→옛 순
		if n.chain != chain || n.cycle == "" {
			continue
		}
		switch n.kind {
		case "success", "fail", "pending":
			why := n.finding
			if why == "" {
				why = n.subject
			}
			return &statusVerdict{Cycle: n.cycle, Result: n.kind, Why: clip(why, 200)}
		}
	}
	return nil
}

// rollbackCandidates — 지금 자리에서 **되돌아갈 수 있는** 조상들(define·analyze).
//
// --to 가 받는 것이 그 둘이다. 그 밖의 kind 를 후보로 내면 사람이 고른 것을 문법이 거부한다 —
// 고를 수 없는 것을 보여주는 목록은 없느니만 못하다.
func rollbackCandidates(byID map[string]node, tip node) []statusRollback {
	out := []statusRollback{}
	seen := map[string]bool{}
	var passed []string // 팁에서 여기까지 지나온 스텝 = 되돌리면 버려지는 것들
	cur := tip
	for i := 0; i < 64; i++ {
		if cur.kind == "define" || cur.kind == "analyze" {
			if cur.step != tip.step && !seen[cur.step] {
				seen[cur.step] = true
				d := append([]string{}, passed...)
				out = append(out, statusRollback{ID: cur.step, Kind: cur.kind,
					Label: clip(humanLabel(cur.subject), 90), Discards: d})
			}
		}
		passed = append([]string{cur.step}, passed...)
		p, ok := byID[cur.parent]
		if !ok {
			break
		}
		cur = p
	}
	return out
}

// competingSiblings — 지금 밟고 있는 갈래가 속한 경합의 **갈래 전부**(#106·#107·#112).
//
// 왜 competingLeaves 를 쓰지 않나. 그건 "지금 겨루는 중"만 낸다(종결된 갈래를 뺀다). 카드가
// 비교로 쓰이려면 **끝난 갈래도 있어야** 한다 — 진 갈래가 왜 졌는지가 남은 갈래를 고르는
// 근거고, 목록에서 빠지면 사람은 그 갈래를 아직 열려 있는 것으로 오해한다.
//
// 상태 판정은 뷰어(competitionsJSON)와 같은 규칙이다. 채택된 갈래는 제 커밋에 표식이 없으니
// (채택은 진 쪽에 Gil-Lost-To 로 적힌다) 승자는 진 갈래가 가리키는 자리로 역산한다.
func competingSiblings(nodes []node, tip node) []statusSibling {
	root := competitionRoot(tip, nodes)
	if root == "" {
		return nil
	}
	byStep := map[string]node{}
	kids := map[string][]node{}
	for _, n := range nodes {
		if _, dup := byStep[n.step]; dup {
			continue
		}
		byStep[n.step] = n
		if n.parent != "" {
			kids[n.parent] = append(kids[n.parent], n)
		}
	}
	var br []node
	seen := map[string]bool{}
	for _, n := range nodes {
		if n.competing != root || n.kind != "hypothesis" || seen[n.step] {
			continue // 갈래의 뿌리는 가설이다(adopt 가 남기는 fail 도 Gil-Competing 을 단다)
		}
		seen[n.step] = true
		br = append(br, n)
	}
	if len(br) < 2 {
		return nil // 혼자 서 있으면 경합이 아니라 그냥 재분기다
	}
	sort.Slice(br, func(i, j int) bool { return stepNum(br[i].step) < stepNum(br[j].step) })

	// 갈래의 잎들 = 그 뿌리에서 뻗은 자손 중 자식 없는 것.
	leavesOf := func(rootStep string) []node {
		var out []node
		visited := map[string]bool{}
		stack := []string{rootStep}
		for len(stack) > 0 {
			cur := stack[len(stack)-1]
			stack = stack[:len(stack)-1]
			if visited[cur] {
				continue
			}
			visited[cur] = true
			cs := kids[cur]
			if len(cs) == 0 {
				if n, ok := byStep[cur]; ok {
					out = append(out, n)
				}
				continue
			}
			for _, c := range cs {
				stack = append(stack, c.step)
			}
		}
		return out
	}
	type st struct{ state, lostTo, leaf string }
	states := map[string]st{}
	for _, b := range br {
		s := st{state: "open"}
		for _, lf := range leavesOf(b.step) {
			s.leaf = lf.step
			switch {
			case lf.lostTo != "":
				s.state, s.lostTo = "lost", lf.lostTo
			case lf.kind == "success":
				s.state = "won"
			case lf.kind == "fail" && s.state == "open":
				s.state = "fail"
			}
			if s.state == "won" || s.state == "lost" {
				break
			}
		}
		states[b.step] = s
	}
	// 진 갈래가 가리키는 승자가 어느 갈래에 속하나 — 그 갈래가 이겼다.
	inBranch := func(rootStep, target string) bool {
		cands := append(leavesOf(rootStep), byStep[rootStep])
		for _, lf := range cands {
			for cur, hops := lf, 0; cur.step != "" && hops < 200; hops++ {
				if cur.step == target {
					return true
				}
				if cur.step == rootStep {
					break
				}
				nxt, ok := byStep[cur.parent]
				if !ok {
					break
				}
				cur = nxt
			}
		}
		return false
	}
	for _, b := range br {
		if states[b.step].state != "lost" {
			continue
		}
		win := states[b.step].lostTo
		if i := strings.LastIndex(win, "/"); i >= 0 {
			win = win[i+1:]
		}
		for _, o := range br {
			if o.step != b.step && states[o.step].state == "open" && inBranch(o.step, win) {
				s := states[o.step]
				s.state = "won"
				states[o.step] = s
			}
		}
	}
	// 내가 밟고 있는 갈래 — 팁에서 거슬러 오르다 만나는 첫 경합 선언.
	mine := ""
	for cur, hops := tip, 0; cur.step != "" && hops < 200; hops++ {
		if cur.competing == root {
			mine = cur.step
			break
		}
		nxt, ok := byStep[cur.parent]
		if !ok {
			break
		}
		cur = nxt
	}
	out := []statusSibling{}
	for _, b := range br {
		s := states[b.step]
		out = append(out, statusSibling{ID: b.step, Hypothesis: humanLabel(b.subject),
			RefutesIf: b.falsify, Plan: b.plan, Leaf: s.leaf, State: s.state,
			LostTo: s.lostTo, Current: b.step == mine})
	}
	return out
}

// humanLabel — 커밋 제목에서 gil 이 붙인 앞머리를 걷어 **사람이 읽는 한 줄**만 남긴다.
// "gil c/cy/s1 define: 무엇을 풀려는가" → "무엇을 풀려는가".
func humanLabel(subject string) string {
	if i := strings.Index(subject, ": "); i >= 0 && strings.HasPrefix(subject, "gil ") {
		return strings.TrimSpace(subject[i+2:])
	}
	return strings.TrimSpace(subject)
}

// cycleStepNodes — 스텝을 선언 순(s1, s2, …)으로 정렬해 낸다.
//
// 순서가 이름순인 이유: 그리는 쪽은 parent 로 배치를 계산하므로 순서 자체는 배치에 안 쓰이지만,
// **첫 자식이 부모의 줄을 잇는다**는 규칙 때문에 자식들의 순서는 그림을 바꾼다. 선언 순이면
// 먼저 난 갈래가 척추가 된다 — 사람이 "원래 가던 길"이라고 읽는 그것이다.
func cycleStepNodes(nodes []node) []statusStepNode {
	out := []statusStepNode{}
	seen := map[string]bool{}
	for _, n := range nodes {
		if n.step == "" || seen[n.step] {
			continue
		}
		seen[n.step] = true
		// 뿌리 스텝의 부모는 트레일러에 **문자열 "null"** 로 산다(오래된 파수꾼 값 —
		// 코드 곳곳이 그걸 빈 값과 같이 취급한다). 그걸 그대로 내보내면 그리는 쪽은
		// `null` 이라는 이름의 스텝으로 가는 간선을 그린다 — 문서가 "없는 것을 그리지 마라"
		// 라고 못박은 바로 그 자리다. 여기서 접는다.
		parent := n.parent
		if parent == "null" {
			parent = ""
		}
		out = append(out, statusStepNode{ID: n.step, Kind: n.kind, Parent: parent, Back: n.backtrack})
	}
	sort.Slice(out, func(i, j int) bool { return stepNum(out[i].ID) < stepNum(out[j].ID) })
	return out
}

// walkBackToGil — 팁에서 첫-부모를 거슬러 가장 가까운 gil 커밋을 찾는다.
// 반환: 지나온 gil 밖 커밋 수, 그 자리의 chain·cycle. 못 찾으면 (0, "", "").
func walkBackToGil() (int, string, string, string) {
	// **커밋 단위 구분자를 쓴다.** %(trailers:…) 는 값 끝에 개행을 붙이므로, 줄 단위로 쪼개면
	// 한 커밋이 여러 줄로 흩어져 개수도 짝도 어긋난다(실측: 체인은 우연히 맞고 사이클은 빈
	// 채로 나왔다). \x1e 로 커밋을, \x1f 로 필드를 가른다.
	const fs, rs = "\x1f", "\x1e"
	// 40개까지만 본다 — 층(dev·main)에 서 있으면 끝까지 거슬러도 gil 커밋이 안 나오는데,
	// 그때 저장소 전체를 훑으면 "체인 밖"이라는 정상 상태에 큰 비용을 문다.
	out, err := gitTry("log", "-40", "--first-parent", "HEAD",
		"--format=%H"+fs+"%(trailers:key=Gil-Chain,valueonly,unfold)"+fs+
			"%(trailers:key=Gil-Cycle,valueonly,unfold)"+rs)
	if err != nil {
		return 0, "", "", ""
	}
	for i, rec := range strings.Split(out, rs) {
		f := strings.SplitN(rec, fs, 3)
		if len(f) < 3 {
			continue
		}
		if ch := strings.TrimSpace(f[1]); ch != "" {
			return i, ch, strings.TrimSpace(f[2]), strings.TrimSpace(f[0])
		}
	}
	return 0, "", "", ""
}

// trailerOf — 그 커밋의 트레일러 한 줄. unfold 로 접힌 값도 편다(#109).
func trailerOf(sha, key string) string {
	if sha == "" {
		return ""
	}
	out, err := gitTry("log", "-1", sha, "--format=%(trailers:key="+key+",valueonly,unfold)")
	if err != nil {
		return ""
	}
	return strings.TrimSpace(out)
}

// headStepNode — 지금 HEAD 가 선 스텝. 사이클의 아무 팁이 아니라 **밟고 있는 가지**의 것이다
// (currentCycle 이 HEAD 범위를 쓰는 것과 같은 이유 — 죽은 형제 가지의 커밋을 팁으로 잡으면
// 다음 한 수가 통째로 어긋난다).
func headStepNode(nodes []node, tipSHA string) (node, bool) {
	for _, n := range nodes {
		if n.sha == tipSHA || strings.HasPrefix(tipSHA, n.sha) || strings.HasPrefix(n.sha, tipSHA) {
			return n, true
		}
	}
	// 그 자리가 스텝이 아니다(close·merge 등). 조상 중 **가장 가까운** 것을 고른다.
	//
	// 첫 번째로 찾은 조상이 아니다 — cycleNodesOf 의 순서는 조상 거리와 무관해서, 실측에서
	// s7 자리에 서 있는데 s1(define)이 잡혔고 그래서 "다음은 hypothesis" 라는 **한 사이클
	// 앞선 안내**가 나왔다. 다음 한 수를 틀리게 말하는 화면은 없는 화면보다 나쁘다.
	best, found := node{}, false
	for _, n := range nodes {
		if !gitOK("merge-base", "--is-ancestor", n.sha, tipSHA) {
			continue
		}
		if !found || gitOK("merge-base", "--is-ancestor", best.sha, n.sha) {
			best, found = n, true
		}
	}
	return best, found
}

// nextMoves — 지금 kind 다음에 **문법이 허용하는** 수. 안내와 문법이 갈리면 느슨한 쪽이
// 실질 규칙이 되므로(v3.53.0 의 교훈), 문구는 commands.go 의 guideNext 와 같은 것을 말한다.
func nextMoves(chain, cycle string, tip node) []string {
	ref := chain + "/" + cycle
	switch tip.kind {
	case "define":
		return []string{"gil step " + ref + " --kind hypothesis --falsify <반증조건> --falsify-to <조상 define>"}
	case "hypothesis":
		return []string{"gil step " + ref + " --kind verify --verdict supported|refuted"}
	case "verify":
		return []string{"gil step " + ref + " --kind analyze --finding <결론 한 줄>"}
	case "analyze":
		// **종결은 close 가 아니라 step 의 kind 다.** close 는 그렇게 선 사이클을 봉인하는
		// 다음 단계고, 그 --verdict 는 supported|partial|rejected 다. 처음 쓴 이 목록은
		// 둘을 뭉개 `gil close … --verdict success --to …` 라는 **없는 문법**을 가르쳤다 —
		// 막힌 사람이 그대로 쳤을 때 한 번 더 막히는 자리(v3.58.1·v3.58.2 가 고친 병).
		return []string{
			"gil step " + ref + " --kind success  — 가설이 지지됨: 이 분기를 종결한다",
			"gil step " + ref + " --kind fail --to <조상 define|analyze>  — 가설이 기각됨: 되돌아갈 단계와 함께 종결한다",
			"gil step " + ref + " --kind pending  — 사람의 판단을 요청한다",
			"gil step " + ref + " --kind hypothesis --to <조상 define|analyze> --competing  — 경쟁 가설을 동시에 세운다",
		}
	case "pending":
		return []string{
			"gil approve",
			"gil reject --to <조상 define>",
		}
	case "success":
		// **잎에서는 다음이 스텝이 아니다** — 종결 뒤에 이어 붙이면 "이 가지는 끝났다"는 뜻이
		// 사라진다(#60①). 그런데 지금까지 여기가 빈 목록이었고, 그 공백을 카드의 승인 버튼이
		// "이 자리를 딛고 다음 스텝을 세워라"로 메웠다 — 없는 수를 사람 입으로 지시한 것이다.
		// 빈 자리는 채워지지 않는 게 아니라 **지어내서 채워진다**.
		return []string{"gil close " + ref + "  — 모든 분기가 종결됐으면 이 사이클을 닫는다"}
	case "fail":
		// fail 은 죽음이 아니라 발견이다 — 기본 수는 닫는 것이 아니라 **다시 갈라지는 것**이다.
		// 그 자리는 이미 기록에 있다(Gil-Backtrack = 벽의 지도). 지도가 미정이면(#105) 그
		// 자리를 지어내지 않고 물음표로 남긴다 — 다음 재분기가 확정한다.
		to := tip.backtrack
		if to == "" || to == "pending" {
			to = "<조상 define|analyze>"
		}
		return []string{
			"gil step " + ref + " --kind hypothesis --to " + to + " --inherit <이 기각에서 알게 된 것>  — 다른 가설을 세운다",
			"gil close " + ref + " --abandon --reason <왜 중단하나>  — 이 문제 정의로는 답에 이를 수 없다고 판단되면",
		}
	}
	return []string{}
}

func statusLines(st statusOut) []string {
	L := []string{"📂 " + st.Repo}
	if st.Chain == nil {
		L = append(L, "체인 밖(층에 서 있다) — 아직 연 체인이 없거나 dev·main 위다.")
	} else {
		L = append(L, "체인  "+st.Chain.Name+"  ("+st.Chain.Mode+", 기준 "+st.Chain.Interview+")")
		if st.Cycle != nil {
			L = append(L, "사이클 "+st.Cycle.Name)
			if st.Cycle.RefutesIf != "" {
				L = append(L, "  반증조건  "+clip(st.Cycle.RefutesIf, 90))
			}
			// 측정도 짧은 형태에 나온다 — 카드가 말하는 것을 터미널이 안 말하면 두 출력이
			// 다른 것을 세는 것이 된다(이 파일이 처음부터 지킨 규칙).
			if m := st.Cycle.Measured; m != nil {
				L = append(L, "  측정("+m.Step+")  "+measureLine(m))
			}
			// 경합은 **세지 말고 이름을 부른다** — "3개"는 비교의 재료가 아니다.
			if len(st.Cycle.Competing) > 1 {
				var parts []string
				for _, s := range st.Cycle.Competing {
					mark := s.ID
					if s.Current {
						mark += "(현재)"
					}
					switch s.State {
					case "won":
						mark += "[채택]"
					case "lost":
						mark += "[채택 안 됨]"
					case "fail":
						mark += "[반증됨]"
					}
					parts = append(parts, mark)
				}
				L = append(L, "  ⚖ 경쟁 가설  "+strings.Join(parts, " · "))
			}
		}
		if st.Step != nil {
			// 카드와 같은 뜻풀이를 단다 — 두 출력이 다른 말을 하면 안 된다.
			kind := st.Step.Kind
			if g := kindGloss[kind]; g != "" {
				kind += "(" + g + ")"
			}
			L = append(L, "스텝  "+st.Step.ID+" "+kind+"  "+clip(st.Step.Subject, 70))
		}
	}
	if st.Waiting != nil {
		L = append(L, "", "⏳ 사람의 판단을 기다린다 — "+st.Waiting.What, "   "+st.Waiting.Answer)
	}
	for _, w := range st.Warnings {
		L = append(L, "⚠ "+w)
	}
	if len(st.Next) > 0 {
		L = append(L, "", "다음 단계:")
		for _, n := range st.Next {
			L = append(L, "  "+n)
		}
	}
	return L
}
