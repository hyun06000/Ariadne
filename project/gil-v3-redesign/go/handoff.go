// handoff.go — 세션 부활 정보를 커밋 그래프에서 자동으로 뽑는다.
//
// 참조 구현(gil.py)의 cmd_handoff·_handoff_report·_next_allowed를 옮긴다. 다음 세션이
// "무엇을 이어받아야 하는지"를 한눈에: 열린 체인·사이클, 각 팁, 다음 허용 동작, 계보.
package main

import (
	"runtime"
	"strings"
	"time"
)

// nextAllowed — 스텝 원칙상 팁 다음에 허용되는 동작. 참조: _next_allowed.
func nextAllowed(tipKind, tipOutcome string) string {
	switch {
	case tipKind == "define":
		return "step --kind hypothesis"
	case tipKind == "hypothesis":
		return "step --kind verify"
	case tipKind == "verify":
		return "step --kind analyze (분석) | step --kind pending (사람에게 물음)"
	case tipKind == "analyze":
		return "step --kind success (산 잎, 보고서) | step --kind fail --to <define> (죽은 잎) | step --kind pending"
	case tipKind == "pending":
		return "사람 답 대기 — gil approve <ref> (승인) | gil reject <ref> --to <define> (기각). 다른 step 은 거부됨."
	case tipKind == "success" || (tipKind == "analyze" && tipOutcome == "success"):
		return "close (산 잎) | step --kind hypothesis --to <define> (다른 정답 탐색)"
	case tipKind == "fail" || (tipKind == "analyze" && (tipOutcome == "backtrack" || tipOutcome == "fail")):
		return "step --kind hypothesis --to <조상 define> (되돌아가 새 가지)"
	}
	return "?"
}

// cmdHandoff — 참조: cmd_handoff.
func cmdHandoff(args []string) {
	report := handoffReport()
	println2(report)
}

// currencyBanner — 도구 현행성 확인(AIL #12). 새 존재가 계승될 때 구버전 정신모델로
// 작업하다 우회로에 빠지는 걸 막는다(open --body 미사용→amend, which gil→소스 오인 등이
// 모두 "낡은 도구·문서를 안 짚어서"였다). handoff 첫 관문에서 (a)현재 버전 (b)최신 대비
// 구버전 경고 (c)핵심 문서 포인터를 짚는다. 네트워크 조회는 비차단 — 실패하면 조용히
// 버전만 보이고 handoff 를 막지 않는다(오프라인 세션도 이어받게).
func currencyBanner() []string {
	var L []string
	L = append(L, "── 도구 현행성 (먼저 확인) ──")
	L = append(L, "  현재 gil: "+gilVersion+" ("+runtime.GOOS+"/"+runtime.GOARCH+")")
	// handoff 는 자주 불리니 최신 조회를 짧게(3s) 끊는다 — 오프라인이어도 handoff 가 멈추지
	// 않게. 확실한 대조가 필요하면 gil version --check(15s) 를 따로 쓴다.
	latest, err := latestTagTimeout(3 * time.Second)
	switch {
	case err != nil:
		L = append(L, "  최신 릴리스 조회 못 함(오프라인/네트워크) — 확실히 하려면: gil version --check")
	case gilVersion == "dev":
		L = append(L, "  ⚠ 개발 빌드(dev)다 — 릴리스 "+latest+"와 다를 수 있다. 실사용은 릴리스 바이너리로.")
	case latest != gilVersion:
		L = append(L, "  ⚠ 새 버전 "+latest+" 있음 (현재 "+gilVersion+"). 새/바뀐 명령·워크플로우가 있을 수 있다 —")
		L = append(L, "    갱신: gil version --update   그 뒤 이 handoff 를 다시 읽어라.")
	default:
		L = append(L, "  최신이다 ("+latest+").")
	}
	L = append(L, "  이 빌드가 뭘 하는지·새 명령은: gil help   |   워크플로우 문서: README.ai.md")
	L = append(L, "")
	return L
}

// pendingBanner — 사람 답을 기다리는 pending 잎을 최상단에 모아 띄운다(AIL #41, 상현님).
// pending 은 종결이 아니라 '사람 대기'다 — 답 없이 방치되면 사이클이 열린 채 잊힌다. gil 은
// 커밋 시점만 개입하니 "언제까지 답하라"는 강제할 수 없지만(행위 시점), 부활 첫 화면에 대기를
// 못박아 방치를 드러낸다. pending 을 종결로 위장해 열린 노드를 만드는 꼼수의 가시화.
func pendingBanner() []string {
	nodes := collectNodes("--branches")
	hasChild := map[string]bool{}
	for _, n := range nodes {
		if n.parent != "" && n.parent != "null" {
			hasChild[stepKey(n.chain, n.cycle, n.parent)] = true
		}
	}
	var waiting []node
	for _, n := range nodes {
		if n.kind == "pending" && !hasChild[stepKey(n.chain, n.cycle, n.step)] {
			waiting = append(waiting, n)
		}
	}
	if len(waiting) == 0 {
		return nil
	}
	var L []string
	L = append(L, "⏳ 사람 답 대기(pending) — 종결 아님, 답 전엔 못 이어간다:")
	for _, n := range waiting {
		ref := n.chain + "/" + n.cycle
		L = append(L, "  · "+ref+"/"+n.step+"  — 승인: gil approve "+ref+"  |  기각: gil reject "+ref+" --to <조상 define>")
	}
	L = append(L, "")
	return L
}

// handoffReport — 세션 부활 정보를 문자열로. 참조: _handoff_report.
func handoffReport() string {
	var L []string
	L = append(L, "═══ gil handoff — 세션 부활 정보 ═══", "")
	L = append(L, currencyBanner()...)
	L = append(L, pendingBanner()...)
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
			tip := c.liveTip()
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
			L = append(L, "    열린 사이클 없음 — 다음 둘 중 하나:")
			L = append(L, "      · 이 국면을 더 판다 → 닫힌 사이클 끝에서 새 사이클: gil open "+cname+"/<cycle> --author <a> --purpose <p>")
			L = append(L, "      · 이 국면이 완결됐다 → 체인을 닫고 새 체인으로: gil chain-close "+cname+" → gil chain <새이름> --purpose <다음 국면>")
			L = append(L, "        (사이클만 계속 늘리지 말 것 — 국면이 끝났으면 체인을 전환해 교훈을 이어받는다.)")
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
	// 뷰어 생존 보고(이슈 #30) — 죽어 있으면 다음 세션이 바로 되살리게 명령을 준다.
	if portOpen(viewerPortNum()) {
		L = append(L, "▶ 뷰어: 살아있음 — http://127.0.0.1:"+viewerPortNum())
	} else {
		L = append(L, "▶ 뷰어: 죽어있음 — 되살리기: gil viewer serve --repo . --port "+viewerPortNum()+" &")
	}
	L = append(L, "")
	L = append(L, "복원 경로: CLAUDE.md → 존재(existence) → gil global read memory.md → 이 handoff → 위 팁에서 이어간다.")
	return strings.Join(L, "\n")
}
