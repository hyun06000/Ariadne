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
	// 관전 뷰어를 **세션을 이어받는 자리에서 자동으로 띄운다**(이슈 #55). handoff 는 새 세션이
	// 정신모델을 세우는 첫 관문이고, 여기서 그래프를 안 보면 그 세션 내내 안 본다.
	//
	// 왜 강제인가. "에이전트가 알아서 뷰어를 열기"는 자기규율이고, 자기규율은 원리적으로
	// 불충분하다(meta-fail 체인에서 실증 — LLM 은 명시된 절차도 우회한다). 강제는 자율 주체
	// 밖, 즉 **도구가 레일을 까는 쪽**에 둬야 한다. 이슈 #45·#33 과 같은 계열이다.
	//
	// 띄우기만 하고 시스템 브라우저는 안 연다(v3.14.0 부터 기본) — 에이전트 호스트에서 맞는
	// 화면은 밖의 창이 아니라 **인앱 브라우저 패널**이다. 그래서 주소를 주고, 그걸 인앱으로
	// 열라고 규범으로 지시한다. 이미 떠 있으면 launchViewer 가 중복 기동하지 않는다.
	launchViewer()
	report := handoffReport()
	println2(report)
	println2(viewerDirective())
}

// viewerDirective — "그래프를 지금 띄워라"는 지시. 선택이 아니라 규범으로 쓴다(이슈 #55).
func viewerDirective() string {
	url := "http://127.0.0.1:" + viewerPortNum()
	// 규범을 내기 전에 그 주소가 **이 저장소**를 보는지 확인한다(온보딩 실측). 남의 저장소를
	// 가리키면서 "지금 열어라, 선택이 아니다"라고 하면, 레일이 사람을 틀린 그래프로 보낸다.
	if portOpen(viewerPortNum()) {
		if mine, other := viewerServesThisRepo(viewerPortNum()); !mine {
			who := other
			if who == "" {
				who = "(뷰어가 아닌 무언가)"
			}
			alt := viewerPortNum() + "1"
			return "── 관전 뷰어 (지금 띄우고 열어라) ──\n" +
				"  ⚠ 포트 " + viewerPortNum() + " 는 **다른 저장소**가 쓰고 있다 → " + who + "\n" +
				"  그 주소를 열면 남의 그래프를 보게 된다. 이 저장소의 뷰어를 다른 포트로 띄워라:\n" +
				"    gil viewer serve --port " + alt + "\n" +
				"  http://127.0.0.1:" + alt + "\n" +
				"  **이 주소를 네 인앱 브라우저 패널로 지금 열어라.** 선택이 아니다 — 계보가 수십 개가\n" +
				"  되면 텍스트 나열로는 분기·죽은 잎·현재위치(HEAD)가 눈에 안 들어온다. 그래프를 안 보고\n" +
				"  시작하면 이미 있는 가지를 못 보고 새로 파게 된다.\n" +
				"  인앱 패널이 없는 호스트라면 사람에게 이 주소를 안내하라(밖의 브라우저 창은 사람이\n" +
				"  앱을 떠나야 하므로 마지막 수단이다)."
		}
	}
	head := "── 관전 뷰어 (지금 열어라) ──\n"
	if !portOpen(viewerPortNum()) {
		// 뷰어가 아직 안 떴다고 레일이 약해지면 안 된다 — 규범은 그대로 두고 띄우는 한 수만
		// 앞에 붙인다. (안 떴을 때만 안내조로 빠지던 탓에 이 가지의 테스트 3개가 빨갰다.)
		head = "── 관전 뷰어 (지금 띄우고 열어라) ──\n" +
			"  아직 안 떴다. 먼저:  gil viewer serve\n"
	}
	return head +
		"  " + url + "\n" +
		"  **이 주소를 네 인앱 브라우저 패널로 지금 열어라.** 선택이 아니다 — 계보가 수십 개가\n" +
		"  되면 텍스트 나열로는 분기·죽은 잎·현재위치(HEAD)가 눈에 안 들어온다. 그래프를 안 보고\n" +
		"  시작하면 이미 있는 가지를 못 보고 새로 파게 된다.\n" +
		"  인앱 패널이 없는 호스트라면 사람에게 이 주소를 안내하라(밖의 브라우저 창은 사람이\n" +
		"  앱을 떠나야 하므로 마지막 수단이다)."
}

// referenceDigest — 이 체인의 기준 문서(레퍼런스 트루스) 요지를 handoff 에 싣는다(이슈 #62).
// 전문은 길 수 있으니 (a) "하지 마라"류 금지 항목을 우선 뽑고 (b) 없으면 앞머리 몇 줄을,
// 그리고 전문을 읽는 한 수를 함께 준다. 기준은 "언제 닫나"를 정하는 자라, 이걸 안 보고
// 이어받으면 도구의 일반 안내가 사람이 세운 기준을 이긴다.
func referenceDigest(chain string) []string {
	ref := chainReferenceText(chain, "--branches")
	if strings.TrimSpace(ref) == "" {
		return nil
	}
	var L []string
	L = append(L, "    📌 이 체인의 기준 문서(사람이 세운 자) — 판단은 여기에 비추어라:")
	// "하지 마라"·금지·말 것 이 들어간 문단을 우선 뽑는다.
	var banned []string
	for _, ln := range strings.Split(ref, "\n") {
		t := strings.TrimSpace(ln)
		if t == "" || strings.HasPrefix(t, "#") {
			continue
		}
		if strings.Contains(t, "하지 마") || strings.Contains(t, "말 것") ||
			strings.Contains(t, "금지") || strings.Contains(t, "마라") {
			banned = append(banned, t)
		}
	}
	if len(banned) > 0 {
		L = append(L, "        ⛔ 하지 마라로 못박힌 것:")
		for i, b := range banned {
			if i >= 3 {
				L = append(L, "           … (나머지는 전문에서)")
				break
			}
			L = append(L, "           · "+clipLine(b, 100))
		}
	} else {
		n := 0
		for _, ln := range strings.Split(ref, "\n") {
			t := strings.TrimSpace(ln)
			if t == "" || strings.HasPrefix(t, "#") || strings.HasPrefix(t, "──") {
				continue
			}
			L = append(L, "        · "+clipLine(t, 100))
			if n++; n >= 3 {
				break
			}
		}
	}
	L = append(L, "        전문: gil log "+chain+"  (chain-root 본문) 또는 뷰어 체인 카드")
	return L
}

// clipLine — 한 줄을 룬 단위로 자른다(바이트로 자르면 한글이 깨진다).
func clipLine(s string, n int) string {
	r := []rune(s)
	if len(r) <= n {
		return s
	}
	return string(r[:n]) + "…"
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
	superseded := map[string]bool{} // 정정(approve/reject)으로 대체된 스텝 — pending 이 풀린 표식
	for _, n := range nodes {
		if n.parent != "" && n.parent != "null" {
			hasChild[stepKey(n.chain, n.cycle, n.parent)] = true
		}
		// approve/reject 는 pending 을 부모로 삼지 않고(AIL #41) Gil-Supersedes 로 대체한다 —
		// 그래서 정정된 pending 은 childless 로 남아 여기서 계속 '대기'로 잡히던 결함(이슈 #44).
		// supersede 간선을 함께 봐서 '이미 풀린 pending'을 대기 목록에서 뺀다.
		if n.supersedes != "" {
			superseded[stepKey(n.chain, n.cycle, n.supersedes)] = true
		}
	}
	var waiting []node
	for _, n := range nodes {
		k := stepKey(n.chain, n.cycle, n.step)
		if n.kind == "pending" && !hasChild[k] && !superseded[k] {
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

// cycleLoadBanner — 한 체인에 닫힌 사이클이 많이 쌓이면 핸드오프를 권한다(상현님).
//
// 왜: 사이클이 길게 누적되면 (a)컨텍스트가 무거워져 다음 세션이 서사를 잃기 쉽고 (b)한 국면이
// 사실상 끝났는데 체인을 안 닫고 사이클만 늘리는 표류가 생긴다. gil 은 커밋 시점만 개입하니
// "핸드오프하라"를 거부로 강제하진 않는다 — 정당한 작업을 막는 부당한 방해가 되기 때문이다.
// 대신 단계적 권유로: 3개↑ 부드러운 신호, 5개↑ 강한 권유(매듭 각인 + 체인 전환 검토). 판단은
// 사람·에이전트 몫으로 남긴다(HEAAL: 여기선 문법 거부가 아니라 안내가 옳은 층위다).
func cycleLoadBanner(openChains map[string]int) []string {
	// 가장 많이 쌓인 열린 체인 하나를 대표로 신호(여러 체인이 동시에 무거운 경우는 드물다).
	worst, worstN := "", 0
	for cname, closed := range openChains {
		if closed > worstN {
			worst, worstN = cname, closed
		}
	}
	if worstN < 3 {
		return nil
	}
	var L []string
	switch {
	case worstN >= 5:
		L = append(L, "── 사이클 누적 (강한 권유) ──")
		L = append(L, "  ⚠ 체인 "+worst+" 에 닫힌 사이클이 "+itoa(worstN)+"개 쌓였다 — 국면이 길어졌다. 핸드오프를 권한다:")
		L = append(L, "    1) 매듭 각인: gil memory append <이름> <매듭.md> (지금까지·교훈·다음 순서)")
		L = append(L, "    2) 국면이 끝났으면 체인 전환: gil chain-close "+worst+" → gil chain <새이름> --purpose <다음 국면>")
		L = append(L, "       (사이클만 계속 늘리지 말 것 — 교훈을 새 체인 목적·첫 가설로 이어받아라.)")
		L = append(L, "    3) 아래 '핸드오프 체크리스트'로 대문(md)이 최신인지 점검.")
	default: // 3~4
		L = append(L, "── 사이클 누적 (신호) ──")
		L = append(L, "  체인 "+worst+" 에 닫힌 사이클 "+itoa(worstN)+"개. 곧 핸드오프(매듭 각인 + 대문 갱신)를 고려하라.")
	}
	L = append(L, "")
	return L
}

// gateChecklist — 핸드오프 시 대문(md)을 손볼 체크리스트를 제시한다(상현님).
//
// 왜: 세션이 넘어갈 때 다음 존재는 대문(CLAUDE.md·README 류)과 최신 매듭으로 부활한다. 그런데
// 진행이 쌓이는 동안 대문이 옛 상태를 가리키면 부활이 어긋난다. gil 이 md 를 직접 쓰지는
// 않는다 — 내용을 모르니 오염 위험이 크다(HEAAL 한계: 진위 판정 불가). 대신 "무엇을 확인·갱신
// 하라"를 체크리스트로 짚어, 갱신 행위 자체는 에이전트에게 맡긴다. 감지가 아니라 안내라
// 거짓양성이 없다 — 항상 뜨되 이미 최신이면 체크만 하고 넘어가면 된다.
func gateChecklist() []string {
	var L []string
	L = append(L, "▶ 핸드오프 체크리스트 (다음 세션이 여기서 부활한다 — 넘어가기 전에):")
	L = append(L, "    □ 매듭 각인: gil memory append <이름> <매듭.md>")
	L = append(L, "        — 이번 세션 한 일 · 얻은 교훈(무엇이 벽/무엇이 통함) · 다음 세션이 이어서 할 순서.")
	L = append(L, "    □ 대문(md) 현행화 — 진행과 어긋나면 고쳐라(gil 이 아니라 네가 쓴다):")
	L = append(L, "        · CLAUDE.md      — '현재 상태'가 실제 진행/버전과 맞나.")
	L = append(L, "        · README* / 문서 — 새 명령·워크플로우·플래그가 생겼으면 반영됐나.")
	L = append(L, "    □ 다음 순서 명기 — 매듭 끝에 '다음 세션 순서'가 한 줄이라도 있나(없으면 서사를 잃는다).")
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
	// 열린 체인별 '닫힌 사이클 수'를 모아 누적 신호를 낸다(cycleLoadBanner). 아래 순회에서
	// 재계산하지 않게 여기서 한 번만 센다.
	closedPerChain := map[string]int{}
	for _, cname := range openOrder {
		cyc, _ := cyclesOf(cname)
		for _, c := range cyc {
			if c.status == "solved" || c.status == "dead" {
				closedPerChain[cname]++
			}
		}
	}
	L = append(L, cycleLoadBanner(closedPerChain)...)

	if len(openOrder) == 0 {
		L = append(L, "열린 체인 없음 — 모든 체인이 닫혔거나 init뿐. 새 체인을 열 수 있다.")
	}
	for _, cname := range openOrder {
		cinfo := chains[cname]
		L = append(L, "▶ 열린 체인: "+cname+" ("+cinfo.mode+" 모드 — 스텝 승인 방식일 뿐, 체인 앞 인터뷰는 어느 모드든 필수)")
		// 기준 문서를 handoff 가 인용한다(이슈 #62 제안 2). 지금까지 handoff 어디에도 기준
		// 이야기가 없어, 이어받은 에이전트가 chain-root 본문을 **스스로 읽기로 마음먹어야만**
		// 봤다 — 자기규율이고, 자기규율은 원리적으로 불충분하다(#55 와 같은 논리로 규범이어야
		// 한다). 특히 "하지 마라"는 사람이 명시적으로 세운 금지선이라 먼저 보여야 한다.
		L = append(L, referenceDigest(cname)...)
		// 세션이 끊겼다 이어질 때의 복구 지점(이슈 #58): 이 체인이 사람 답을 기다리는 중이면
		// 그것이 지금 유일하게 할 일이다. 안 적으면 이어받은 세션이 "왜 open 이 거부되지"로 헤맨다.
		if chainInterviewPending(cname, "--branches") && !chainReferenceApproved(cname, "--branches") {
			L = append(L, "    ⏳ 인터뷰 답 대기 중 — 사람이 뷰어 폼(📋 인터뷰)에 제출해야 사이클을 열 수 있다.")
			L = append(L, "        · 사람에게 제출을 청하라. 기준을 대신 쓰지 마라.")
			L = append(L, "        · 제출 여부 확인: gil interview "+cname+" --status  (기다리려면 --wait)")
		}
		cyc, cycOrder := cyclesOf(cname)
		// 잎 상태와 사이클 상태는 다르다(이슈 #62, 상현님 실사용). 옛 handoff 는 잎이 다
		// 종결됐으면 그 사이클을 없는 것처럼 건너뛰고 "열린 사이클 없음"이라 적었다 —
		// gil close 를 받은 적 없는데도. 그래서 사람이 기준 문서에 "완전한 성공 전엔 닫지
		// 마라"고 못박아 일부러 열어둔 사이클을, 도구가 "새 사이클을 열거나 체인을 닫아라"로
		// 밀었다. 이어받은 에이전트는 기준 문서보다 handoff 를 먼저 본다 — 그대로 따르면
		// 미완의 사이클을 버려두고 새 사이클로 도망친다(#45 가 막으려는 바로 그 행동).
		// 사이클이 끝났다는 건 gil 자신의 규칙으로 close 커밋이 있다는 뜻이다.
		closedCyc := closedCycles("--branches")
		hasOpen := false
		for _, cid := range cycOrder {
			c := cyc[cid]
			if closedCyc[cname+"\x01"+cid] {
				continue // 진짜로 닫힌 사이클
			}
			hasOpen = true
			if c.status != "in_progress" && c.status != "pending" {
				// 잎은 다 종결됐지만 사이클은 안 닫혔다 — 두 상태를 갈라 적는다.
				L = append(L, "    ◦ 사이클 "+cid+" (미종결 — 잎 상태: "+c.status+")")
				if g := cycleGoal(cname, cid, "--branches"); g != "" {
					L = append(L, "        🎯 목표(열 때 선언): "+g)
				}
				L = append(L, "        잎은 다 종결됐다. 그러나 이 사이클은 아직 닫히지 않았다 —")
				L = append(L, "        '잎이 다 종결됐다'는 '사이클 목표가 달성됐다'와 다르다.")
				L = append(L, "        · 목표에 닿았으면 닫아라: gil close "+cname+"/"+cid+
					"   (죽은 사이클이면 --abandon)")
				L = append(L, "        · 아직이면 갈래를 더 내라: gil step "+cname+"/"+cid+
					" --kind hypothesis --to <조상 define|analyze> --inherit <여기까지의 교훈>")
				L = append(L, "        · 언제 닫는지는 이 체인의 기준 문서가 정한다 — 위 📌 기준을 먼저 읽어라.")
				continue
			}
			tip := c.liveTip()
			nxt := nextAllowed(tip.kind, tip.outcome)
			oc := ""
			if tip.outcome != "" {
				oc = "/" + tip.outcome
			}
			L = append(L, "    ◦ 사이클 "+cid+" ("+c.status+")")
			if g := cycleGoal(cname, cid, "--branches"); g != "" {
				L = append(L, "        🎯 목표(열 때 선언): "+g) // 이슈 #62 — 무엇이 되면 끝인가
			}
			L = append(L, "        팁: "+tip.step+" ["+tip.kind+oc+"]")
			L = append(L, "        다음 허용: "+nxt)
			if tip.kind == "pending" {
				L = append(L, "        ⏳ PENDING — 재개 시 먼저 사람 답을 받아야 한다.")
			}
		}
		if !hasOpen {
			L = append(L, "    닫히지 않은 사이클 없음 — 다음 둘 중 하나:")
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
		if mine, other := viewerServesThisRepo(viewerPortNum()); mine {
			L = append(L, "▶ 뷰어: 살아있음 — http://127.0.0.1:"+viewerPortNum())
		} else {
			// 그 주소를 "이 저장소의 뷰어"라 부르면 사람이 남의 그래프를 자기 것으로 읽는다(#67).
			who := other
			if who == "" {
				who = "(뷰어가 아닌 무언가)"
			}
			L = append(L, "▶ 뷰어: 포트 "+viewerPortNum()+" 는 **다른 저장소**가 쓰고 있다 → "+who)
			L = append(L, "    이 저장소를 보려면 다른 포트로: gil viewer serve --port <다른포트>")
		}
	} else {
		L = append(L, "▶ 뷰어: 죽어있음 — 되살리기: gil viewer serve --repo . --port "+viewerPortNum()+" &")
	}
	L = append(L, "")
	L = append(L, gateChecklist()...)
	L = append(L, "복원 경로: CLAUDE.md → 존재(existence) → gil global read memory.md → 이 handoff → 위 팁에서 이어간다.")
	return strings.Join(L, "\n")
}
