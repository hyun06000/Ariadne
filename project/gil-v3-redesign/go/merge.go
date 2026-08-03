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
	// **층은 아래로 흐르지 않는다**(이슈 #115, 실사용). 체인이 dev 보다 한참 뒤처지면
	// 그 트리엔 정본이 없다 — 그 자리에서 에이전트가 발명한 수가 `gil merge dev --into <체인>`
	// 이었다. 충돌 0, 문법 통과, fsck 위반 0. 층 모델을 정면으로 거스르는데 아무것도 막지
	// 않았고 사람이 잡았다.
	//
	// 왜 문법이 침묵했나: --help 가 **허용을 열거**하고 금지를 말하지 않았다. 열거형 문서
	// 옆에 `<합칠 것> --into <받는 곳>` 이라는 일반형 문법이 있으면, 없는 항목은 금지가
	// 아니라 **미기재**로 읽힌다. 그러니 열거가 아니라 방향을 검사한다.
	if !isLayerBranch(target) {
		var layers []string
		for _, s := range pos {
			if isLayerBranch(s) {
				layers = append(layers, s)
			}
		}
		if len(layers) > 0 {
			msg := "거부: " + strings.Join(layers, " ") + " 를 " + target + " 로 합칠 수 없다 — **층은 아래로 흐르지 않는다.**\n" +
				"  체인은 " + devBranchName + " 에서 갈라져 자라고, 끝나면 " + devBranchName + " 로 **올라간다**.\n" +
				"  층을 체인으로 끌어오면 그 체인은 자기가 시작한 자리를 잃고, 이후의 합류는\n" +
				"  '무엇이 이 체인의 성과인가'를 말할 수 없게 된다.\n"
			// 이 수를 두려는 이유는 대개 하나다 — 뒤처져서 정본이 트리에 없다. 그 진단과
			// 정당한 경로를 그 자리에서 준다(거부만 하고 길이 없으면 벽이다, #67).
			if f := behindDev("refs/heads/" + target); f != nil && f.commits > 0 {
				msg += "  진단: 이 체인은 " + devBranchName + " 보다 " + itoa(f.commits) + " 커밋 뒤처졌다"
				if f.touched > 0 {
					msg += "(그중 " + itoa(f.touched) + " 개가 이 트리의 파일을 건드린다)"
				}
				msg += ".\n"
			}
			msg += "  정당한 길은 **국면을 넘기는 것**이다:\n" +
				"    gil chain-close " + target + " --retro <회고>\n" +
				"    gil merge " + target + " --into " + devBranchName + " --reason <왜>\n" +
				"    gil intake <슬러그> --ask <질문JSON>   →   gil chain <새 이름> --from-intake <슬러그> --ask-root\n" +
				"  (새 체인은 " + devBranchName + " 의 지금 자리에서 갈라진다 — 정본을 처음부터 쥐고 시작한다.)"
			die(msg)
		}
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

// cycleBranchOf — "<chain>/<cycle>" 을 **그 사이클이 실제로 끝난 자리**로.
//
// 이름이 <chain>-<cycle> 인 브랜치를 그대로 쓰면 안 된다. 정정(--supersede)이나 재분기
// (--to)를 거친 사이클은 척추와 종결이 **분기 브랜치**(…-sNbM)에 살고, 사이클 본 브랜치는
// 정정된 그 자리에 멈춰 있다. 그 낡은 브랜치를 합치면 **성공한 작업과 close 가 통째로 빠진
// 채** 합류가 성공했다고 보고된다 — 복잡한 나무를 지어 git 과 대조해서야 드러났다(a2 의
// s3~s10 과 close 가 체인에 없었고, 아무도 아무 말을 안 했다).
//
// 그래서 이름이 아니라 **사실**로 찾는다: 그 사이클의 종결(close) 커밋, 없으면 가장 늦은
// 스텝. 그 커밋을 담은 브랜치가 있으면 이름으로, 없으면 sha 로 돌려준다.
func cycleBranchOf(a string) string {
	ch, cy, ok := strings.Cut(strings.TrimSpace(a), "/")
	if !ok || ch == "" || cy == "" || strings.Contains(cy, "/") {
		return ""
	}
	if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+a) {
		return "" // 그런 이름의 브랜치가 실제로 있다 — 사람이 가리킨 것을 존중한다
	}
	end := cycleEndSHA(ch, cy)
	if end == "" {
		return ""
	}
	// 그 커밋을 **끝으로 갖는** 브랜치가 있으면 이름으로 부른다(출력이 읽히게).
	for _, b := range branches() {
		if strings.TrimSpace(git("rev-parse", b)) == end {
			return b
		}
	}
	return end
}

// cycleEndSHA — 그 사이클이 실제로 끝난 커밋. 종결(close)이 있으면 그것, 없으면 가장 늦은
// 스텝. 정정·재분기로 가지가 갈렸어도 **사실**을 따라가므로 낡은 자리를 짚지 않는다.
func cycleEndSHA(chain, cycle string) string {
	fmtStr := "%H" + fsep + trailer("Gil-Chain") + fsep + trailer("Gil-Cycle") + fsep +
		trailer("Gil-Kind") + fsep + trailer("Gil-Step") + sep
	best, bestN := "", -1
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches"), sep) {
		sha, r1, ok := cut(strings.TrimSpace(rec), fsep)
		if !ok {
			continue
		}
		c, r2, _ := cut(r1, fsep)
		cy, r3, _ := cut(r2, fsep)
		kind, step, _ := cut(r3, fsep)
		if strings.TrimSpace(c) != chain || strings.TrimSpace(cy) != cycle {
			continue
		}
		if strings.TrimSpace(kind) == "close" {
			return strings.TrimSpace(sha) // 종결이 곧 그 사이클의 끝이다
		}
		if n := stepNum(strings.TrimSpace(step)); n > bestN {
			best, bestN = strings.TrimSpace(sha), n
		}
	}
	return best
}
