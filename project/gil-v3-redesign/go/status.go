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

type statusCycle struct {
	Name      string `json:"name"`
	Hypothesis string `json:"hypothesis,omitempty"`
	RefutesIf  string `json:"refutes_if,omitempty"`
	Plan       string `json:"plan,omitempty"`
	FalsifyTo  string `json:"falsify_to,omitempty"` // 반증되면 물러설 자리(퇴로)
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
}

type statusStep struct {
	ID      string `json:"id"`
	Kind    string `json:"kind"`
	Subject string `json:"subject,omitempty"`
	SHA     string `json:"sha,omitempty"`
}

// statusWaiting — 사람이 나설 자리. **null 이 아니면 그것이 지금 유일하게 할 일이다.**
//
// 이 필드가 이 JSON 의 존재 이유다. 나머지는 이걸 읽기 위한 맥락이다 — 사람이 이 시스템에
// 값을 더하는 순간은 그래프를 볼 때가 아니라 "그거 검증할 값어치 있나"와 "어디까지
// 되돌릴까" 두 지점이고, 그 두 순간이 여기로 나온다.
type statusWaiting struct {
	Kind   string `json:"kind"`             // interview | approval
	Chain  string `json:"chain"`
	What   string `json:"what"`             // 무엇을 기다리나(사람 언어)
	Answer string `json:"how_to_answer"`    // 사람이 답하면 무엇이 풀리나 / 에이전트가 칠 한 수
}

type statusOut struct {
	Repo    string         `json:"repo"`
	Branch  string         `json:"branch,omitempty"`
	Chain   *statusChain   `json:"chain"`
	Cycle   *statusCycle   `json:"cycle"`
	Step    *statusStep    `json:"step"`
	Waiting *statusWaiting `json:"waiting_for_human"`
	LastVerdict *statusVerdict  `json:"last_verdict"`
	Rollback    []statusRollback `json:"rollback_candidates"`
	Next    []string       `json:"next"`
	// RenderGuide — **이 데이터를 사람에게 보여주는 규칙이 어디 있나.**
	//
	// 왜 데이터에 문서 경로를 싣나. 규칙을 문서에만 두면 "에이전트가 알아서 읽기"가 되고,
	// 그건 자기규율이다 — 이 저장소가 반복해서 확인한 대로 자기규율은 원리적으로 불충분하다
	// (#55·#45). 데이터를 읽는 순간 규칙의 자리도 함께 알게 하면, 읽을 이유가 있는 자리에서
	// 읽힌다. 화면을 Go 에 박지 않으면서 규칙이 도달하는 유일한 길이다.
	RenderGuide string    `json:"render_guide"`
	Warnings []string      `json:"warnings"`
}

func cmdStatus(args []string) {
	fs := newFlags("gil status")
	asJSON := fs.boolFlag("json")
	fs.parse(args)
	st := gatherStatus()
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
		Rollback: []statusRollback{},
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
		if tip, ok := headStepNode(nodes, tipSHA); ok {
			st.Step = &statusStep{ID: tip.step, Kind: tip.kind, Subject: tip.subject, SHA: clip(tip.sha, 12)}
			if h, ok := nearestKindUp(byID, tip, "hypothesis"); ok {
				st.Cycle.Hypothesis = h.subject
				st.Cycle.RefutesIf = h.falsify
				st.Cycle.Plan = h.plan
				st.Cycle.FalsifyTo = h.falsifyTo
			}
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
			What:   "이 스텝에 대한 사람의 승인 또는 기각",
			Answer: "승인하려면 gil approve\n" +
				"기각하려면 gil reject --to <조상 define>\n" +
				"사람의 답 전엔 이 사이클을 못 이어간다."}
	}

	if ln := behindLine(chain, ""); ln != "" {
		st.Warnings = append(st.Warnings, strings.TrimSpace(strings.ReplaceAll(ln, "\n", " ")))
	}
	return st
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
	cur := tip
	for i := 0; i < 64; i++ {
		if cur.kind == "define" || cur.kind == "analyze" {
			if cur.step != tip.step && !seen[cur.step] {
				seen[cur.step] = true
				out = append(out, statusRollback{ID: cur.step, Kind: cur.kind,
					Label: clip(humanLabel(cur.subject), 90)})
			}
		}
		p, ok := byID[cur.parent]
		if !ok {
			break
		}
		cur = p
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
			"gil step " + ref + " --kind success  — 산 잎",
			"gil step " + ref + " --kind fail --to <조상 define|analyze>  — 죽은 잎, 되돌아갈 자리와 함께",
			"gil step " + ref + " --kind pending  — 사람에게 넘긴다",
			"gil step " + ref + " --kind hypothesis --competing <갈래>  — 형제 가설을 나란히 세운다",
		}
	case "pending":
		return []string{
			"gil approve",
			"gil reject --to <조상 define>",
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
		}
		if st.Step != nil {
			L = append(L, "스텝  "+st.Step.ID+" "+st.Step.Kind+"  "+clip(st.Step.Subject, 70))
		}
	}
	if st.Waiting != nil {
		L = append(L, "", "⏳ 사람을 기다린다 — "+st.Waiting.What, "   "+st.Waiting.Answer)
	}
	for _, w := range st.Warnings {
		L = append(L, "⚠ "+w)
	}
	if len(st.Next) > 0 {
		L = append(L, "", "다음 한 수:")
		for _, n := range st.Next {
			L = append(L, "  "+n)
		}
	}
	return L
}
