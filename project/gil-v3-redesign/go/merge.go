// merge.go — gil merge: 둘 이상의 조상을 요구하는 모든 합류 (상현님, 2026-07-31).
//
// 층을 넣으면서 두 낱말을 갈랐다:
//
//	배포(gil deploy)  — dev → 대문(main). **층과 층 사이**의 이동이다. main·dev 를 체인으로
//	                    취급할지 아직 정하지 않았으므로 체인 문법을 적용하지 않는다.
//	머지(gil merge)   — dev 아래에서 벌어지는 모든 합류. 체인 간이든, 체인 이하 노드에서
//	                    둘 이상의 부모·계승을 요구하는 자리든 같은 낱말을 쓴다.
//
// 옛 chain-merge 는 "여러 끝단을 모아 **새 체인을 만든다**"는 한 가지 모양만 알았다. 그건
// 합류의 특수한 경우지 합류 자체가 아니다 — 끝난 체인을 dev 로 올리는, 가장 흔한 합류를
// 표현할 수 없었다. 그래서 이름을 넓히고 옛 이름은 별칭으로 남긴다(지우지 않는다).
package main

import "strings"

func cmdMerge(args []string) {
	fs := newFlags("gil merge")
	into := fs.str("into", "")
	reason := fs.str("reason", "")
	// --allow-open: 닫히지 않은 것을 합치는 예외. SPEC 규칙 5 는 "완성만 머지 대상"이다 —
	// 그 규칙을 우회할 길을 아예 막지는 않되, 우회했다는 사실이 기록에 남게 한다.
	allowOpen := fs.boolFlag("allow-open")
	// 층을 건널 때는 확인을 돌린다(checks.go). 건너뛰려면 이유를 밝혀라 — 그 사실이 남는다.
	skipCheck := fs.boolFlag("skip-check")
	skipReason := fs.str("skip-reason", "")
	pos := fs.parse(args)
	if len(pos) == 0 || strings.TrimSpace(*into) == "" {
		die("사용: gil merge <합칠 것>... --into <받는 곳> --reason <왜 합치나>\n" +
			"  닫은 사이클을 체인으로: gil merge <chain>/<cycle> --into <chain> --reason <왜>\n" +
			"  끝난 체인을 층으로:     gil merge <chain> --into " + devBranchName + " --reason <왜>\n" +
			"  체인 간 합류:           gil merge <chain-a> <chain-b> --into <chain-c> --reason <왜>\n" +
			"  (dev → main 은 머지가 아니라 **배포**다: gil deploy --tag <vX>)")
	}
	// **gil 의 주소는 <chain>/<cycle> 이다**(이슈 #103). open·step·close 는 전부 그 형태로
	// 받는데 merge 만 git ref 를 요구했다 — 그래서 사람도 리포트도 `gil merge c/c001` 이라
	// 적었고, git 이 "알 수 없는 리비전"으로 죽었다. 주소 문법이 명령마다 다르면 사람은
	// 도구가 아니라 도구의 사정을 외워야 하고, 그 자리에서 우회로 미끄러진다.
	for i, a := range pos {
		if br := cycleBranchOf(a); br != "" {
			pos[i] = br
		}
	}
	if strings.TrimSpace(*reason) == "" {
		die("거부: --reason 필요 — **왜 이 둘이 한 줄기가 되나**.\n" +
			"  머지는 두 계보가 하나로 합쳐졌다고 선언하는 일이다. 이유 없이 합치면 나중에\n" +
			"  아무도 그 합류가 판단이었는지 사고였는지 모른다.")
	}
	target := strings.TrimSpace(*into)
	if h := homeBranch(); (h == "main" || h == "master") && target == h {
		die("거부: 대문(" + target + ")으로 올리는 것은 머지가 아니라 **배포**다.\n" +
			"    gil deploy --tag <v0.2.0>\n" +
			"  배포된 것만 대문에 온다 — 그 문장을 참으로 유지하려면 통로가 하나여야 한다.")
	}
	if !gitOK("rev-parse", "--verify", "-q", "refs/heads/"+target) {
		die("거부: --into \"" + target + "\" 브랜치가 없다.")
	}
	if strings.TrimSpace(git("status", "--porcelain", "-uno")) != "" {
		die("거부: 추적 파일에 미커밋 변경이 있다 — 머지 전 정리하라")
	}

	// 완성만 머지 대상(SPEC 규칙 5). 체인이면 닫혔는지 본다 — 열린 체인을 합치면 그 체인의
	// 판정이 아직 안 났는데 결과부터 흡수하는 꼴이다.
	var open []string
	for _, s := range pos {
		if chainPurpose(s, "--branches") != "" && !chainClosed(s, "--branches") {
			open = append(open, s)
		}
	}
	if len(open) > 0 && !*allowOpen {
		die("거부: 아직 닫히지 않은 체인이다: " + strings.Join(open, " ") + "\n" +
			"  완성만 머지 대상이다 — 판정이 안 난 것을 합치면 결과부터 흡수하는 꼴이 된다.\n" +
			"    gil chain-close " + open[0] + " --retro <회고파일|->\n" +
			"  그래도 지금 합쳐야 할 이유가 있으면 --allow-open (그 사실이 기록에 남는다).")
	}

	// 위상적 끝단만 — 조상은 자동으로 딸려온다. 다 적어놓고 "다 합쳤다"고 세는 건 부풀리기다.
	leaves := topologicalLeaves(pos)
	var dropped []string
	for _, t := range pos {
		if !contains(leaves, t) {
			dropped = append(dropped, t)
		}
	}
	if len(dropped) > 0 {
		stderr("  조상이라 생략(자동 포함): " + strings.Join(dropped, ", "))
	}
	tgtSHA := strings.TrimSpace(git("rev-parse", target))
	var toMerge []string
	for _, lf := range leaves {
		s := strings.TrimSpace(git("rev-parse", lf))
		if !gitOK("merge-base", "--is-ancestor", s, tgtSHA) {
			toMerge = append(toMerge, lf)
		}
	}
	if len(toMerge) == 0 {
		die("거부: 합칠 것이 없다 — " + target + " 이 이미 전부 담고 있다.")
	}

	// ── 층 검사 ──────────────────────────────────────────────────────────────
	// dev 로 올리는 것은 층을 건너는 일이다. 여기가 SPEC 7 의 'dev verify=smoke' 자리다.
	var checkNote string
	if target == devBranchName {
		if *skipCheck && strings.TrimSpace(*skipReason) == "" {
			die("거부: --skip-check 에는 --skip-reason <왜 확인 없이 건너나> 가 필요하다.\n" +
				"  이유 없는 건너뜀은 나중에 '확인했다'와 구별되지 않는다.")
		}
		ran, passed, note := runLayerCheck(devBranchName, *skipCheck, *skipReason)
		if !passed {
			die("거부: " + note)
		}
		checkNote = note
		_ = ran
	}
	back := strings.TrimSpace(git("rev-parse", "--abbrev-ref", "HEAD"))
	if back != target {
		git("checkout", "-q", target)
	}
	for i, lf := range toMerge {
		subject := "gil merge: " + lf + " → " + target
		body := "합류 이유: " + *reason
		if len(open) > 0 && *allowOpen {
			body += "\n\n⚠ 닫히지 않은 채 합쳤다(--allow-open): " + strings.Join(open, " ") +
				" — 판정이 나기 전에 흡수했다는 사실을 여기 남긴다."
		}
		trs := "\n\nGil-Merge: " + lf + "\nGil-Merge-Into: " + target + "\nGil-Merge-Reason: " + *reason
		for _, t := range checkTrailers(devBranchName, target == devBranchName && !*skipCheck, *skipCheck, *skipReason) {
			trs += "\n" + t[0] + ": " + t[1]
		}
		if _, err := gitTry("merge", "--no-ff", "-q", "-m", subject+"\n\n"+body+trs, lf); err != nil {
			conflicts := strings.TrimSpace(git("diff", "--name-only", "--diff-filter=U"))
			rest := "(없음)"
			if i+1 < len(toMerge) {
				rest = strings.Join(toMerge[i+1:], ", ")
			}
			stderr("⚠ 충돌 — [" + lf + "] 합류에서 멈췄다 (" + itoa(i+1) + "/" + itoa(len(toMerge)) + ").\n" +
				"충돌 파일:\n" + conflicts + "\n\n" +
				"해결한 뒤:  git add <해결한 파일> && git commit\n" +
				"남은 것: " + rest)
			gilExit(2) // 2 = 충돌로 멈춤 (거부 1과 구분)
		}
		println2("merge: " + lf + " → " + target + " ✓")
	}
	invalidateGraphNodes()
	if back != target {
		git("checkout", "-q", back)
	}
	println2("  이유: " + *reason)
	if checkNote != "" {
		println2("  ⓘ " + checkNote)
	}
	if target == devBranchName {
		println2("  ▸ 층에 모였다. 세상으로 내보내려면: gil deploy --tag <v0.2.0>")
	}
}

// cycleBranchOf — "<chain>/<cycle>" 을 그 사이클의 브랜치 이름으로. 그 형태가 아니거나
// 브랜치가 없으면 "" (그러면 인자를 그대로 둔다 — git ref 로 받는 길은 그대로 산다).
func cycleBranchOf(a string) string {
	ch, cy, ok := strings.Cut(strings.TrimSpace(a), "/")
	if !ok || ch == "" || cy == "" || strings.Contains(cy, "/") {
		return ""
	}
	if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+a) {
		return "" // 그런 이름의 브랜치가 실제로 있다 — 사람이 가리킨 것을 존중한다
	}
	br := ch + "-" + cy
	if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+br) {
		return br
	}
	return ""
}
