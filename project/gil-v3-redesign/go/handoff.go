// handoff.go — 세션 부활 정보를 커밋 그래프에서 자동으로 뽑는다.
//
// 참조 구현(gil.py)의 cmd_handoff·_handoff_report·_next_allowed를 옮긴다. 다음 세션이
// "무엇을 이어받아야 하는지"를 한눈에: 열린 체인·사이클, 각 팁, 다음 허용 동작, 계보.
package main

import "strings"

// nextAllowed — 스텝 원칙상 팁 다음에 허용되는 동작. 참조: _next_allowed.
func nextAllowed(tipKind, tipOutcome string) string {
	switch {
	case tipKind == "define":
		return "step --kind hypothesis"
	case tipKind == "hypothesis":
		return "step --kind verify"
	case tipKind == "verify":
		return "step --kind analyze --outcome {success|backtrack|fail} | step --kind pending"
	case tipKind == "pending":
		return "사람 답 대기 — 승인→analyze/success, 기각→analyze/backtrack --to <define>"
	case tipKind == "analyze" && tipOutcome == "success":
		return "close (산 잎) | step --kind hypothesis --to <define> (다른 정답 탐색)"
	case tipKind == "analyze" && (tipOutcome == "backtrack" || tipOutcome == "fail"):
		return "step --kind hypothesis --to <조상 define> (되돌아가 새 가지)"
	}
	return "?"
}

// cmdHandoff — 참조: cmd_handoff.
func cmdHandoff(args []string) {
	report := handoffReport()
	println2(report)
}

// handoffReport — 세션 부활 정보를 문자열로. 참조: _handoff_report.
func handoffReport() string {
	var L []string
	L = append(L, "═══ gil handoff — 세션 부활 정보 ═══", "")
	chains, order := chainsFromGraph()

	var openOrder []string
	for _, name := range order {
		if chains[name].status == "open" {
			openOrder = append(openOrder, name)
		}
	}
	if len(openOrder) == 0 {
		L = append(L, "열린 체인 없음 — 모든 체인이 닫혔거나 init뿐. 새 체인을 열 수 있다.")
	}
	for _, cname := range openOrder {
		cinfo := chains[cname]
		L = append(L, "▶ 열린 체인: "+cname+" ("+cinfo.mode+" 모드)")
		cyc, cycOrder := cyclesOf(cname)
		hasOpen := false
		for _, cid := range cycOrder {
			c := cyc[cid]
			if c.status != "in_progress" && c.status != "pending" {
				continue
			}
			hasOpen = true
			tip := c.steps[len(c.steps)-1]
			nxt := nextAllowed(tip.kind, tip.outcome)
			oc := ""
			if tip.outcome != "" {
				oc = "/" + tip.outcome
			}
			L = append(L, "    ◦ 사이클 "+cid+" ("+c.status+")")
			L = append(L, "        팁: "+tip.step+" ["+tip.kind+oc+"]")
			L = append(L, "        다음 허용: "+nxt)
			if tip.kind == "pending" {
				L = append(L, "        ⏳ PENDING — 재개 시 먼저 사람 답을 받아야 한다.")
			}
		}
		if !hasOpen {
			L = append(L, "    열린 사이클 없음 — 닫힌 사이클 끝에서 새 사이클을 연다.")
		}
	}
	L = append(L, "")
	L = append(L, "▶ 체인 계보 ("+itoa(len(chains))+"개):")
	for _, cname := range order {
		cinfo := chains[cname]
		par := strings.Join(cinfo.parents, "+")
		if par == "" {
			par = "(대문)"
		}
		L = append(L, "    "+cname+" ("+cinfo.status+") ← "+par)
	}
	L = append(L, "")
	if gfiles := globalList(); len(gfiles) > 0 {
		L = append(L, "")
		L = append(L, "▶ 글로벌 진실원 ("+globalRef+" — 체인 넘어 단일):")
		for _, f := range gfiles {
			L = append(L, "    "+f+"  (읽기: gil global read "+f+")")
		}
	}
	L = append(L, "")
	L = append(L, "복원 경로: CLAUDE.md → 존재(existence) → gil global read memory.md → 이 handoff → 위 팁에서 이어간다.")
	return strings.Join(L, "\n")
}
