// context.go — **조상의 지식이 자식에게 도착하게 한다** (상현님, 2026-07-28).
//
// gil 의 핵심은 "부모의 부모, 더 먼 조상까지 그들이 만든 지식 하나하나가 아래 세대로 전파되며
// 쌓여 하나의 컨텍스트를 만든다"이다. 그런데 지금까지 gil 이 보증한 것은 **기록**뿐이었다:
// --inherit·--plan·--toward 는 커밋에 남지만, 새 사이클을 여는 자식에게 자동으로 **도착**하지
// 않았다. 자식이 스스로 gil log 를 뒤져 조상을 거슬러 읽어야 했고, 그건 자기규율이다 —
// 자기규율은 원리적으로 불충분하다(이 레포가 몇 번이나 확인한 명제).
//
// 그래서 계보 브리핑을 만든다. 조상 사슬(사이클 계보 + 그 사이클 안의 가지 교훈)을 거슬러
// 모아 한 화면으로 준다. 그리고 **자식이 태어나는 순간**(gil open)과 **회고하는 순간**
// (종결 스텝)에 gil 이 먼저 읽어 준다 — 물어보지 않아도 도착하게.
package main

import (
	"sort"
	"strings"
)

// cycleAncestry — 이 사이클의 조상 사이클들을 오래된 것부터 나열한다(자기 자신 제외).
// Gil-Cycle-Parent(사이클 계보 간선)를 거슬러 올라간다. 순환·중복은 접는다.
func cycleAncestry(chain, cycle string) []string {
	return cycleAncestryFrom(graphNodes(), chain, cycle)
}

// graphNodes — 이 프로세스에서 그래프를 **한 번만** 읽는다(성능). gil 은 한 번 실행에 한 가지
// 일만 하므로 캐시가 낡을 여지가 없다. 안 하면 계보 브리핑 한 번이 조상 수만큼 전체 그래프를
// 다시 훑는다 — 테스트가 3분에서 14분으로 늘어 발각됐다.
var graphNodesCache []node

// invalidateGraphNodes — 커밋 뒤에는 캐시를 버린다. 안 그러면 방금 만든 노드가 안 보인다 —
// 실제로 계보 브리핑이 "조상 사이클 없음"이라 답했다(테스트가 잡았다). 성능을 위해 캐시를
// 두되, **쓰는 순간 버린다**는 규칙이 함께 있어야 캐시가 거짓말을 안 한다.
func invalidateGraphNodes() { graphNodesCache = nil }

func graphNodes() []node {
	if graphNodesCache == nil {
		graphNodesCache = collectNodes("--branches")
	}
	return graphNodesCache
}

func cycleAncestryFrom(all []node, chain, cycle string) []string {
	parents := map[string][]string{}
	for _, n := range all {
		if n.chain != chain || n.cycle == "" || len(n.cycleParents) == 0 {
			continue
		}
		for _, p := range n.cycleParents {
			p = strings.TrimSpace(p)
			// 계보 간선은 "cycle" 또는 "chain/cycle" 로 적힌다 — 뒤 칸만 쓴다.
			if i := strings.LastIndex(p, "/"); i >= 0 {
				p = p[i+1:]
			}
			if p != "" && p != n.cycle {
				parents[n.cycle] = append(parents[n.cycle], p)
			}
		}
	}
	var chainUp []string
	seen := map[string]bool{cycle: true}
	cur := cycle
	for range make([]struct{}, 64) { // 깊이 상한 — 손상된 그래프에서도 멈춘다
		ps := parents[cur]
		if len(ps) == 0 {
			break
		}
		next := ""
		for _, p := range ps {
			if !seen[p] {
				next = p
				break
			}
		}
		if next == "" {
			break
		}
		seen[next] = true
		chainUp = append(chainUp, next)
		cur = next
	}
	// 거슬러 올라간 순서(가까운 조상부터)를 뒤집어 **오래된 조상부터** 준다 — 지식은 그
	// 순서로 쌓였고, 읽는 사람도 그 순서로 읽어야 강이 흐르는 방향을 본다.
	for i, j := 0, len(chainUp)-1; i < j; i, j = i+1, j-1 {
		chainUp[i], chainUp[j] = chainUp[j], chainUp[i]
	}
	return chainUp
}

// stepHeadline — 스텝 커밋 subject 에서 사람이 쓴 제목만 뽑는다.
// subject 는 "gil <chain>/<cycle>/<step> <kind>: <제목>" 꼴이라 앞머리를 잘라낸다.
func stepHeadline(n node) string {
	s := n.subject
	if i := strings.Index(s, ": "); i >= 0 && strings.HasPrefix(s, "gil ") {
		s = s[i+2:]
	}
	return strings.TrimSpace(s)
}

// deadAttempts — 이 사이클에서 **접힌 시도**들을 오래된 것부터, 그래프가 이미 아는 사실만으로.
//
// 왜: backtrack 은 `--inherit` 한 줄을 강제해 교훈을 지고 가게 한다. 하지만 그 한 줄은
// 에이전트가 손으로 쓴 **요약**이고, 요약은 쓰는 자의 성실함에 걸려 있다. 정작 "무엇을
// 세웠고 무엇으로 깨졌나"는 그래프에 정확히 적혀 있는데(hypothesis 제목 · verify 의
// refuted · analyze 의 해석) 브리핑이 그걸 싣지 않았다 — 실측으로 확인했다. 기록은
// 있는데 전파가 없으면 없는 지식이다. 그래서 **인용한다, 요약하지 않고.**
//
// 그리고 이 목록은 backtrack 마다 **쌓인다**. 두 번째 되돌아온 가지는 첫 번째 벽도 함께
// 본다 — 누적되지 않으면 세 번째 시도가 첫 번째 벽을 다시 민다.
func deadAttempts(chain, cycle string, indent string) []string {
	var steps []node
	byID := map[string]node{} // Gil-Parent 는 sha 가 아니라 **스텝 id** 다
	for _, n := range graphNodes() {
		if n.chain == chain && n.cycle == cycle {
			steps = append(steps, n)
			byID[n.step] = n
		}
	}
	sort.Slice(steps, func(i, j int) bool { return stepNum(steps[i].step) < stepNum(steps[j].step) })

	var L []string
	for _, end := range steps {
		// 접힌 자리 = 되돌아간 analyze(backtrack) 또는 벽으로 못박은 fail.
		if !(end.outcome == "backtrack" || end.kind == "fail") {
			continue
		}
		// 그 가지를 조상 쪽으로 거슬러 올라가 무엇을 세웠고(hypothesis) 무엇으로 깨졌는지
		// (verify)를 줍는다. 분기점(define)에 닿으면 멈춘다 — 그 위는 형제와 공유하는 몸통이다.
		var hyp, ver *node
		for cur, hops := end, 0; hops < 64; hops++ {
			p, ok := byID[cur.parent]
			if !ok {
				break
			}
			if p.kind == "hypothesis" && hyp == nil {
				h := p
				hyp = &h
			}
			if p.kind == "verify" && ver == nil {
				v := p
				ver = &v
			}
			if p.kind == "define" {
				break
			}
			cur = p
		}
		head := indent + "✖ 접힌 시도 "
		if hyp != nil {
			head += hyp.step + " → " + end.step + ": " + stepHeadline(*hyp)
		} else {
			head += end.step + ": " + stepHeadline(end)
		}
		L = append(L, head)
		if ver != nil && ver.verdict == "refuted" {
			L = append(L, indent+"    반증됨("+ver.step+"): "+stepHeadline(*ver))
		}
		// 접힌 가지의 **결론**을 인용한다(상현님). 지식 누적은 backtrack 을 따라 흐르는데,
		// 정작 그 가지가 무엇을 밝혔는지(analyze 의 --finding)가 안 실리면 다음 가지는
		// "여기서 막혔다"만 알고 "왜 막혔는지"는 모른 채 출발한다.
		if an := lastAnalyzeOf(end, byID); an != nil && an.finding != "" {
			L = append(L, indent+"    밝힌 것("+an.step+"): "+an.finding)
		}
		if end.outcome == "backtrack" {
			L = append(L, indent+"    해석("+end.step+"): "+stepHeadline(end)+"  → "+end.backtrack+" 로 되돌아감")
		} else {
			L = append(L, indent+"    벽("+end.step+"): "+stepHeadline(end))
		}
		// 지도의 **지금 상태**를 함께 적는다(이슈 #105). 옛 화면은 fail 이 적어 둔 자리 하나만
		// 보여줬고, 그래서 (a) 아직 정해지지 않은 지도와 (b) 나중에 다른 자리에서 갈라져
		// 갱신된 지도가 둘 다 '유효한 계획'처럼 읽혔다 — 사람이 "뭐가 맞는 거냐"고 물었다.
		// 도구는 이미 알고 있다(pending 이거나 despite 가 그 자리를 적었다). 말만 안 했을 뿐이다.
		if end.backtrack == "pending" {
			L = append(L, indent+"    ⌖ 지도 미정 — 다음 재분기(또는 사람의 판정)가 되돌아갈 자리를 정한다.")
		}
		for _, later := range steps {
			if later.despiteMap == "" || stepNum(later.step) <= stepNum(end.step) {
				continue
			}
			if end.backtrack != "" && end.backtrack != "pending" && later.parent != end.backtrack {
				L = append(L, indent+"    ⟲ 이 지도는 "+later.step+" 이 갱신했다(despite → "+later.parent+"): "+
					clipLine(later.despiteMap, 90))
				break
			}
		}
	}
	if len(L) > 0 {
		L = append(L, indent+"↺ 위는 이미 민 벽이다 — 같은 벽을 다시 밀지 마라.")
	}
	return L
}

// lastAnalyzeOf — 접힌 자리에서 조상 쪽으로 가장 가까운 analyze(그 가지가 밝힌 것).
// end 자신이 analyze(backtrack)면 그것이다.
func lastAnalyzeOf(end node, byID map[string]node) *node {
	if end.kind == "analyze" {
		e := end
		return &e
	}
	for cur, hops := end, 0; hops < 64; hops++ {
		p, ok := byID[cur.parent]
		if !ok || p.kind == "define" {
			return nil
		}
		if p.kind == "analyze" {
			return &p
		}
		cur = p
	}
	return nil
}

// cycleKnowledge — 한 사이클이 남긴 지식 줄들(전수·설계·회고). 없으면 빈 슬라이스.
func cycleKnowledge(chain, cycle string, indent string) []string {
	var steps []node
	for _, n := range graphNodes() {
		if n.chain == chain && n.cycle == cycle {
			steps = append(steps, n)
		}
	}
	sort.Slice(steps, func(i, j int) bool { return stepNum(steps[i].step) < stepNum(steps[j].step) })
	var L []string
	if p := cyclePurpose(chain, cycle, "--branches"); p != "" {
		L = append(L, indent+"목적: "+p)
	}
	if g := cycleGoal(chain, cycle, "--branches"); g != "" {
		L = append(L, indent+"목표: "+g)
	}
	// 접힌 시도들이 먼저다 — "이미 민 벽"을 알고 나서 살아있는 선을 읽어야 순서가 맞는다.
	L = append(L, deadAttempts(chain, cycle, indent)...)
	for _, s := range steps {
		switch {
		case s.kind == "define" && s.inherit != "":
			L = append(L, indent+"전수(←부모): "+s.inherit)
		case s.kind == "analyze" && s.finding != "":
			L = append(L, indent+s.step+" 분석이 밝힌 것: "+s.finding)
		case s.kind == "hypothesis":
			if s.despiteMap != "" {
				L = append(L, indent+s.step+" 벽의 지도를 벗어난 이유: "+s.despiteMap)
			}
			if s.advances != "" {
				L = append(L, indent+s.step+" 가설이 목적에 다가서려던 몫: "+s.advances)
			}
			if s.plan != "" {
				L = append(L, indent+s.step+" 고정한 설계: "+s.plan)
			}
			if s.inherit != "" {
				L = append(L, indent+s.step+" 이 가지가 물려받은 교훈: "+s.inherit)
			}
		case s.kind == "verify" && s.falsifyOut == "met":
			L = append(L, indent+s.step+" ✖ 반증조건이 충족됐다: "+s.falsifyObs)
		case s.kind == "verify" && s.planOutcome == "broke":
			L = append(L, indent+s.step+" ⚠ 설계가 깨졌다: "+s.planDiff)
		case s.kind == "success" || s.kind == "fail":
			mark := "✔"
			if s.kind == "fail" {
				mark = "✖"
			}
			if s.toward != "" {
				L = append(L, indent+mark+" "+s.step+" 목적에 다가선 정도: "+s.toward)
			}
			if s.nextDesign != "" {
				L = append(L, indent+mark+" "+s.step+" 다음 설계: "+s.nextDesign)
			}
		}
	}
	return L
}

// lineageBrief — 이 자리에 도착한 **누적 컨텍스트** 전체. 체인의 목적·기준에서 시작해
// 조상 사이클들이 남긴 지식을 오래된 것부터 쌓아 보여주고, 마지막에 이 사이클 자신을 둔다.
func lineageBrief(chain, cycle string) []string {
	L := []string{"── 계보 브리핑: 조상에게서 여기까지 쌓인 컨텍스트 ──"}
	if cp := chainPurpose(chain, "--branches"); cp != "" {
		L = append(L, "  체인 ["+chain+"] 목적: "+cp)
	}
	if c := chainTrailer(chain, "Gil-Chain-Criterion"); strings.TrimSpace(c) != "" {
		L = append(L, "  체인 성패 기준(사람이 세운 자): "+c)
	}
	if plan := chainPlanItems(chain); len(plan) > 0 {
		L = append(L, "  사람이 나눈 사이클 문제 "+itoa(len(plan))+"개 — gil open <chain>/<cycle> --from-plan <n>:")
		for i, it := range plan {
			L = append(L, "    "+itoa(i+1)+") "+clip(it, 80))
		}
	}
	if chainHasReference(chain, "--branches") {
		L = append(L, "  체인 기준 문서(사람이 승인한 레퍼런스 트루스)가 있다 — 전문: gil log "+chain+" (chain-root 본문)")
	}
	// 층에서 어디서 갈라졌나. 이게 없으면 "dev 에서 났다"까지만 알고 **언제**를 모른다 —
	// 그러면 dev 가 그 뒤 쌓은 것을 이미 가진 줄 알고 판단한다(뷰어에만 그리던 사실이다).
	if ln := devForkLine(chain); ln != "" {
		L = append(L, ln)
	}
	anc := cycleAncestry(chain, cycle)
	if len(anc) == 0 {
		L = append(L, "  조상 사이클 없음 — 이 사이클이 이 계보의 시작이다.")
	}
	for _, a := range anc {
		L = append(L, "  ◆ "+a+" (조상)")
		k := cycleKnowledge(chain, a, "      ")
		if len(k) == 0 {
			k = []string{"      (남긴 지식 없음 — 이 사이클은 다음 세대에 아무것도 전하지 못했다)"}
		}
		L = append(L, k...)
	}
	if cycle != "" {
		if k := cycleKnowledge(chain, cycle, "      "); len(k) > 0 {
			L = append(L, "  ◆ "+cycle+" (여기)")
			L = append(L, k...)
		}
	}
	L = append(L, "  ▸ 위는 조상들이 만든 지식이다. 이어받아 쌓아라 — 무시하고 새로 시작하면 계보가 거기서 끊긴다.")
	return L
}

// lineageTowardLines — 종결 거부문에 붙이는 "지금까지 목적에 다가선 기록" 요약(최근 3개).
// 회고를 요구하면서 앞선 회고를 안 보여주면, 매번 처음부터 다시 판단하게 된다.
func lineageTowardLines(chain, cycle string) string {
	var rows []string
	all := graphNodes()
	for _, a := range append(cycleAncestryFrom(all, chain, cycle), cycle) {
		for _, n := range all {
			if n.chain == chain && n.cycle == a && n.toward != "" {
				rows = append(rows, "    · "+a+"/"+n.step+": "+n.toward)
			}
		}
	}
	if len(rows) == 0 {
		return ""
	}
	if len(rows) > 3 {
		rows = rows[len(rows)-3:]
	}
	return "  지금까지의 회고(목적에 다가선 정도):\n" + strings.Join(rows, "\n") + "\n"
}

// cmdContext — `gil context <chain>[/<cycle>]`. 계보 브리핑을 사람·에이전트가 언제든 부른다.
func cmdContext(args []string) {
	// context 는 "지금까지를 읽는" 명령이다 — 사람의 판정도 여기서 읽힌다(고지를 끈다).
	defer markAllJudgmentsSeen()
	defer markAllPruneActsSeen()
	fs := newFlags("gil context")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil context <chain>[/<cycle>]\n" +
			"  이 자리에 도착한 누적 컨텍스트를 준다 — 체인 목적·기준에서 시작해 조상 사이클들이\n" +
			"  남긴 전수·설계·회고를 오래된 것부터 쌓아 보여준다(부모의 부모까지).")
	}
	chain, cycle, _ := cut(pos[0], "/")
	if chainPurpose(chain, "--branches") == "" {
		die("거부: 체인 \"" + chain + "\" 선언된 적 없음 — gil chain 으로 먼저 열어라.")
	}
	if cycle != "" && len(cycleAnywhere(chain, cycle)) == 0 {
		die("거부: " + chain + "/" + cycle + " 없음")
	}
	for _, ln := range lineageBrief(chain, cycle) {
		println2(ln)
	}
}
