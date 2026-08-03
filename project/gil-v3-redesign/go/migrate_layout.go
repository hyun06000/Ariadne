// migrate_layout.go — gil migrate --to-dev-layout: 옛 나무를 main-dev-chain 으로 다시 그린다.
//
// v3.46.0 이 층을 세웠지만, 그건 **앞으로 여는** 체인에만 적용된다. 이미 자란 저장소는
// 체인들이 대문 위에·서로 위에 얹힌 채 남았고, drift 는 그걸 계속 stacked 로 짖는다.
// 상현님: "이게 돼야 나무 전체를 옮길 수 있게 된다."
//
// ## 무엇을 하나 — 다시 그린다(re-graft)
//
// 각 체인을 **dev 에서 다시 갈라지게** 새 브랜치로 옮겨 그린다. 트리(파일 내용)와 메시지는
// 그대로 옮기고 **부모만 새 자리로** 바꾼다 — 그래서 사고의 내용은 한 글자도 안 바뀌고
// 계보만 참이 된다. 이어받음을 선언한 체인(Gil-Chain-From)은 그 부모 체인의 끝에 이어 붙어
// 계승이 유지된다.
//
// ## 왜 옛 브랜치를 남기나
//
// 다시 그리면 **모든 SHA 가 바뀐다.** 옛 것을 지우면 이미 클론한 사람의 이력과 갈라지고,
// 잘못 옮겼을 때 돌아갈 곳이 없다. v2→v3 이주가 legacy 를 남긴 것과 같은 이유다:
// 이주는 **무손실이어야 하고, 무손실인지는 두 나무를 나란히 놓고 세어서** 확인한다.
package main

import (
	"os"
	"sort"
	"strings"
)

// lcommit — 다시 그릴 커밋 하나.
type lcommit struct {
	sha, tree  string
	parents    []string
	chain      string
	cycle      string // Gil-Cycle — 어느 사이클의 커밋인가
	cycParent  string // Gil-Cycle-Parent — **선언된** 사이클 계보(이슈 #97①)
	an, ae, ad string // 저자 이름·메일·날짜 — 이주는 저자를 바꾸지 않는다
}

// collectLayoutCommits — 브랜치 전체의 커밋을 다시 그리기에 필요한 만큼만 읽는다.
func collectLayoutCommits() (map[string]*lcommit, []string) {
	fmtStr := "%H" + fsep + "%T" + fsep + "%P" + fsep + trailer("Gil-Chain") +
		fsep + "%an" + fsep + "%ae" + fsep + "%aI" + fsep + trailer("Gil-Cycle") +
		fsep + trailer("Gil-Cycle-Parent") + sep
	byS := map[string]*lcommit{}
	var order []string // git log 순(최신→과거)
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches", "--topo-order"), sep) {
		rec = strings.Trim(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		f := strings.SplitN(rec, fsep, 9)
		if len(f) < 9 {
			continue
		}
		c := &lcommit{
			sha: strings.TrimSpace(f[0]), tree: strings.TrimSpace(f[1]),
			parents: strings.Fields(f[2]), chain: strings.TrimSpace(f[3]),
			an: f[4], ae: f[5], ad: strings.TrimSpace(f[6]),
			cycle: strings.TrimSpace(f[7]), cycParent: strings.TrimSpace(f[8]),
		}
		byS[c.sha] = c
		order = append(order, c.sha)
	}
	return byS, order
}

// gateTipSHA — 대문 계보의 끝. dev 를 심을 자리다.
//
// 대문 브랜치의 첫-부모를 따라 내려가며 **체인에 속하지 않는 첫 커밋**을 찾는다. 배포
// 머지로 체인 커밋이 대문에 올라와 있어도, 첫-부모 사슬은 대문 자신의 줄기를 따라간다.
func gateTipSHA(byS map[string]*lcommit) string {
	home := homeBranch()
	if home == "" {
		return ""
	}
	cur := strings.TrimSpace(git("rev-parse", home))
	for i := 0; i < 10000 && cur != ""; i++ {
		c := byS[cur]
		if c == nil {
			return cur // 그래프 밖(수집 범위 밖) — 여기가 끝이다
		}
		if c.chain == "" {
			return cur
		}
		if len(c.parents) == 0 {
			return cur
		}
		cur = c.parents[0]
	}
	return cur
}

// layoutChainOrder — 다시 그릴 순서. 이어받음(Gil-Chain-From)을 선언한 체인은 **부모를
// 옮긴 뒤에** 옮겨야 그 끝에 이어 붙일 수 있다. 순환이면 남은 것을 이름순으로 뒤에 붙인다
// (거부하지 않는다 — 옛 저장소의 결함 때문에 이주 자체가 막히면 안 된다).
func layoutChainOrder(chains []string, from map[string]string) []string {
	sort.Strings(chains)
	done := map[string]bool{}
	var out []string
	for i := 0; i < len(chains)+2 && len(out) < len(chains); i++ {
		for _, c := range chains {
			if done[c] {
				continue
			}
			p := from[c]
			if p == "" || done[p] || !contains(chains, p) {
				done[c] = true
				out = append(out, c)
			}
		}
	}
	for _, c := range chains { // 순환에 걸린 나머지
		if !done[c] {
			out = append(out, c)
		}
	}
	return out
}

// renameChainInMsg — 커밋 메시지 안의 **체인 이름**을 새 이름으로 바꾼다.
//
// 접두는 브랜치 이름만이 아니라 **체인의 이름**을 바꾼다(v2→v3 이주가 세운 규칙과 같다).
// 안 그러면 옛 나무와 새 나무가 같은 이름의 같은 체인이 되어, 한 사이클의 스텝이 두 벌씩
// 존재하는 상태가 된다 — fsck 가 곧바로 "s4 ×2" 로 짖었다. 이름이 곧 정체성이다.
func renameChainInMsg(msg, old, nw string) string {
	var out []string
	for _, ln := range strings.Split(msg, "\n") {
		for _, k := range []string{"Gil-Chain: ", "Gil-Chain-From: ", "Gil-Parallel-With: "} {
			if strings.TrimSpace(ln) == k+old {
				ln = k + nw
			}
		}
		// 제목 첫 낱말도 체인을 가리킨다("gil alpha chain: …", "gil alpha/c1/s1 define: …").
		// 트레일러만 고치면 제목이 옛 이름을 말해, 사람이 보는 화면이 거짓이 된다.
		if strings.HasPrefix(ln, "gil "+old+" ") {
			ln = "gil " + nw + " " + strings.TrimPrefix(ln, "gil "+old+" ")
		} else if strings.HasPrefix(ln, "gil "+old+"/") {
			ln = "gil " + nw + "/" + strings.TrimPrefix(ln, "gil "+old+"/")
		}
		out = append(out, ln)
	}
	return strings.Join(out, "\n")
}

// chainPreamble — 체인 앞머리: **chain-root 보다 먼저 찍힌 그 체인의 커밋들**(intake·인터뷰).
//
// 왜 이걸 갈라야 하나(이슈 #95①). `gil intake` 는 사람이 **dev 에 서서** 부르는 명령이라,
// 살아 있는 흐름에서 intake 커밋은 dev 의 커밋이고 chain-root 는 그 위에서 갈라진다. 그런데
// 이주는 intake 커밋도 Gil-Chain 을 달고 있다는 이유로 체인 가지에 실었다 — 그러면 chain-root
// 의 부모가 dev 에서 안 닿게 되고, fsck 가 "선언만 있고 분기는 없다"로 잡는다.
// **적층을 풀려고 부른 명령이 적층을 남긴 것**이다.
//
// 그래서 앞머리는 dev 층에 얹고(살아 있는 흐름과 같은 모양), chain-root 는 그 위에서 가른다.
func chainPreamble(cs []*lcommit, root string, byS map[string]*lcommit) (pre []*lcommit, rest []*lcommit) {
	if root == "" {
		return nil, cs
	}
	// root 의 조상인지는 부모 사슬로 판정한다(같은 체인 안에서).
	anc := map[string]bool{}
	stack := []string{root}
	for len(stack) > 0 {
		sha := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		c := byS[sha]
		if c == nil {
			continue
		}
		for _, p := range c.parents {
			if !anc[p] {
				anc[p] = true
				stack = append(stack, p)
			}
		}
	}
	for _, c := range cs {
		if anc[c.sha] {
			pre = append(pre, c)
		} else {
			rest = append(rest, c)
		}
	}
	return pre, rest
}

// dirtyChainTips — 체인 커밋을 담고 있으면서 **끝이 gil 커밋이 아닌** 브랜치들(이슈 #95③).
func dirtyChainTips(byS map[string]*lcommit, chains []string) []string {
	var out []string
	home := homeBranch()
	for _, b := range branches() {
		// **층 브랜치는 체인 브랜치가 아니다**(이슈 #101). 이 검사는 "체인 브랜치의 끝이
		// 평범한 커밋이면 그 사이클이 통째로 빠진다"를 막으려는 것인데, 체인이 dev 로 합류하면
		// dev 가 그 체인의 커밋을 담게 되어 아래 holds 가 참이 되고, dev 의 끝(gil merge 가
		// 만든 머지 커밋)이 "gil 커밋이 아니다"로 걸렸다 — **정본 흐름(chain-close → merge
		// --into dev → 다음 체인)을 밟은 사람이 이주를 거부당했다.** 층은 원래 gil 스텝으로
		// 끝나지 않는다(대문은 배포로, dev 는 합류로 끝난다). 층에 속한 스텝은 제 체인
		// 브랜치가 따로 쥐고 있으므로 여기서 빼도 유실 검사는 성기지 않는다.
		if b == home || b == devBranchName {
			continue
		}
		tip := strings.TrimSpace(git("rev-parse", b))
		c := byS[tip]
		if c == nil || c.chain != "" {
			continue // 수집 범위 밖이거나 gil 커밋이다 — 정상
		}
		// 이 브랜치가 옮길 체인의 커밋을 담고 있을 때만 문제다.
		holds := false
		for _, sha := range strings.Fields(gitlog("--format=%H", b)) {
			if pc := byS[sha]; pc != nil && pc.chain != "" && contains(chains, pc.chain) {
				holds = true
				break
			}
		}
		if !holds {
			continue
		}
		subj := strings.TrimSpace(git("log", "-1", "--format=%s", tip))
		out = append(out, b+" 의 끝이 gil 커밋이 아니다 ("+first9(tip)+" \""+subj+"\")")
	}
	sort.Strings(out)
	return out
}

// cmdMigrateToDevLayout — 옛 나무를 main-dev-chain 으로 다시 그린다.
func cmdMigrateToDevLayout(prefix string, dryRun, allowDirtyTips bool) {
	if strings.TrimSpace(git("status", "--porcelain", "-uno")) != "" {
		die("거부: 추적 파일에 미커밋 변경이 있다 — 이주 전에 정리하라(브랜치를 옮겨 다닌다).")
	}
	byS, order := collectLayoutCommits()
	if len(byS) == 0 {
		die("거부: 커밋이 없다.")
	}
	// 체인별 커밋을 모은다(과거→최신 순으로 뒤집어 둔다 — 부모가 먼저 그려져야 한다).
	inChain := map[string][]*lcommit{}
	roots := chainRoots("--branches")
	for i := len(order) - 1; i >= 0; i-- {
		c := byS[order[i]]
		if c.chain != "" {
			inChain[c.chain] = append(inChain[c.chain], c)
		}
	}
	var chains []string
	for ch := range inChain {
		if _, ok := roots[ch]; ok {
			chains = append(chains, ch)
		}
	}
	if len(chains) == 0 {
		die("거부: 옮길 체인이 없다 — 이 저장소엔 아직 gil 체인이 없다.")
	}
	// 이어받음 선언 읽기(Gil-Chain-From) — 계승은 이주 뒤에도 계승이어야 한다.
	fromOf := map[string]string{}
	fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Kind") + fsep + trailer("Gil-Chain-From") + sep
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches"), sep) {
		a, r, _ := cut(strings.TrimSpace(rec), fsep)
		k, f, _ := cut(r, fsep)
		if strings.TrimSpace(k) == "chain-root" && strings.TrimSpace(f) != "" {
			fromOf[strings.TrimSpace(a)] = strings.TrimSpace(f)
		}
	}
	ordered := layoutChainOrder(chains, fromOf)
	// **끝이 gil 커밋이 아닌 체인 브랜치는 이주 전에 막는다**(이슈 #95③, 상현님 실사용).
	//
	// 왜 거부인가. 3)단계는 옛 브랜치의 팁을 새 sha 로 옮겨 새 브랜치를 세운다. 팁이 gil
	// 커밋이 아니면(사람이 평범한 커밋 하나를 얹었으면) 그 팁은 새 나무에 대응이 없어 브랜치가
	// **조용히 안 세워진다** — 커밋은 다시 그려졌는데 아무도 안 가리켜, 그 사이클이 통째로
	// 사라진다. 실측: 스텝 6개 유실, 종료코드 0, 경고 없음. gil step 은 브랜치 순수성을
	// 지키는데(#74 계열) migrate 는 그게 깨진 상태를 말없이 통과했다.
	if bad := dirtyChainTips(byS, chains); len(bad) > 0 && !allowDirtyTips {
		msg := "거부: 체인 브랜치의 끝이 gil 커밋이 아니다 — 옮기면 그 사이클이 통째로 빠진다.\n"
		for _, b := range bad {
			msg += "  " + b + "\n"
		}
		msg += "  그 커밋을 다른 브랜치로 옮기고(체인 끝을 gil 커밋으로 되돌리고) 다시 실행하라:\n" +
			"    git branch <보관용> <브랜치>   &&   git branch -f <브랜치> <그 gil 커밋>\n" +
			"  (거부하는 이유: 이 상태로 옮기면 아무 경고 없이 스텝이 사라진다. 실제로 6개가 사라졌다.)\n" +
			"  그래도 강행하려면 --allow-dirty-tips — 다만 무엇이 빠졌는지는 끝의 대조가 이름을 부른다."
		die(msg)
	}
	gate := gateTipSHA(byS)
	if gate == "" {
		die("거부: 대문 계보를 못 찾았다 — main/master 브랜치가 필요하다.")
	}

	stderr("migrate --to-dev-layout: 체인 " + itoa(len(ordered)) + "개를 dev 에서 다시 그린다.")
	stderr("  대문 끝(층을 심을 자리): " + first9(gate))
	for _, ch := range ordered {
		base := "dev"
		if p := fromOf[ch]; p != "" && contains(chains, p) {
			base = "체인 " + p + " 의 끝(계승 유지)"
		}
		stderr("  " + ch + ": 커밋 " + itoa(len(inChain[ch])) + "개 → " + base)
	}
	if dryRun {
		stderr("  (--dry-run — 아무것도 쓰지 않았다.)")
		return
	}

	// 1) dev 층. 이미 있으면 그대로 쓴다(멱등).
	if !hasDevLayer() {
		back := strings.TrimSpace(git("rev-parse", "--abbrev-ref", "HEAD"))
		if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+devBranchName) {
			die("거부: \"" + devBranchName + "\" 브랜치가 이미 있는데 gil 층이 아니다.\n" +
				"  남의 브랜치를 층으로 삼키지 않는다 — 이름을 비켜 주고 다시 실행하라:\n" +
				"    git branch -m " + devBranchName + " " + devBranchName + "-old")
		}
		commitOn(devBranchName, gate, "gil migrate: dev 층 개설",
			"옛 나무를 main-dev-chain 으로 다시 그리며 심은 층. 대문 끝("+first9(gate)+")에서 갈라진다.",
			[][2]string{{"Gil-Kind", "dev-root"}, {"Gil-Dev-From", gate}}, true)
		if back != "" && back != devBranchName {
			gitTry("checkout", "-q", back)
		}
		stderr("  ✓ dev 층 심음.")
	}
	devTip := devTipSHA()

	// 2) 커밋을 하나씩 다시 그린다. 트리와 메시지는 그대로, **부모만** 새 자리로.
	newSha := map[string]string{}
	chainTip := map[string]string{}
	for _, ch := range ordered {
		base := devTip
		if p := fromOf[ch]; p != "" && chainTip[p] != "" {
			base = chainTip[p] // 계승은 이주 뒤에도 계승이다
		}
		// 앞머리(intake·인터뷰)는 **dev 층에 얹는다** — 살아 있는 흐름과 같은 모양이 되게
		// (이슈 #95①). 그러면 chain-root 의 부모가 dev 에서 닿고, 층 선언이 참이 된다.
		body := inChain[ch]
		if base == devTip {
			pre, rest := chainPreamble(inChain[ch], roots[ch], byS)
			for _, c := range pre {
				n := regraft(c, []string{base}, ch, prefix, fromOf, chains, roots, base, devTip)
				newSha[c.sha] = n
				base = n // 앞머리는 층 위로 이어 자란다
			}
			if len(pre) > 0 {
				git("update-ref", "refs/heads/"+devBranchName, base) // dev 가 앞머리를 품는다
				devTip = base
			}
			body = rest
		}
		// **선언이 실재를 정한다**(이슈 #97①). 사이클이 `Gil-Cycle-Parent` 로 앞 사이클을
		// 선언했으면, 그 사이클의 **옮긴 끝**에 이어 붙인다. 옛 나무의 커밋 부모를 그대로
		// 따르지 않는 이유: v3.45.0 이전의 `open --parent` 는 선언만 하고 실제로 갈라지지
		// 않았다. 그런 나무를 부모 포인터대로 옮기면 **납작한 실재가 그대로 복사되고**,
		// 새 나무에서도 여덟 사이클이 전부 한 커밋에 붙는다(상현님 실측). 이주는 옮기는
		// 일이자 **선언과 실재를 맞추는** 일이다 — 그러라고 부르는 명령이다.
		//
		// 그리고 **선언한 순서로 그린다.** 납작한 나무에서는 git 이 사이클을 거꾸로 내놓아
		// (c3 가 c1 보다 먼저 나온다) 부모가 아직 안 그려진 채 자식이 도착한다 — 그러면 붙일
		// 자리가 없어 조용히 밑동으로 떨어진다. 순서를 git 에 맡기지 않는다.
		body = orderByDeclaredCycles(body)
		cycTip := map[string]string{} // 사이클 → 옮긴 끝
		drawn := map[string]bool{}    // 이 사이클의 첫 커밋을 이미 그렸나
		for _, c := range body {
			var ps []string
			// 사이클의 첫 커밋이고 부모 사이클을 **선언**했으면 그 선언이 자리를 정한다.
			if c.cycle != "" && !drawn[c.cycle] {
				drawn[c.cycle] = true
				if pcy := c.cycParent; pcy != "" && pcy != "null" && cycTip[pcy] != "" {
					n := regraft(c, []string{cycTip[pcy]}, ch, prefix, fromOf, chains, roots, base, devTip)
					newSha[c.sha] = n
					chainTip[ch] = n
					cycTip[c.cycle] = n
					continue
				}
			}
			for _, p := range c.parents {
				// **같은 체인 안의 부모만** 그대로 잇는다. 이미 옮겼다는 이유로 다른 체인의
				// 커밋을 부모로 삼으면, 옛 적층이 새 나무에 그대로 복사된다(실측: gamma 가
				// 옮겨진 beta 뒤에 다시 붙어 적층이 하나도 안 풀렸다). 적층을 푸는 것이
				// 이 이주의 전부인데, 그 자리에서 다시 얹으면 이주는 이름만 남는다.
				if pc := byS[p]; pc != nil && pc.chain == ch {
					if n, ok := newSha[p]; ok {
						ps = append(ps, n)
						continue
					}
				}
				// 체인 밖(대문·옛 부모 체인·적층된 앞 체인)에서 온 부모 → 새 자리로.
				if !contains(ps, base) {
					ps = append(ps, base)
				}
			}
			if len(ps) == 0 {
				ps = []string{base}
			}
			n := regraft(c, ps, ch, prefix, fromOf, chains, roots, base, devTip)
			newSha[c.sha] = n
			chainTip[ch] = n
			if c.cycle != "" {
				cycTip[c.cycle] = n
			}
		}
	}

	// 3) 브랜치를 새로 세운다. **옛 브랜치는 건드리지 않는다** — 되돌아갈 곳이 있어야 한다.
	made := 0
	for _, b := range branches() {
		tip := strings.TrimSpace(git("rev-parse", b))
		n, ok := newSha[tip]
		if !ok {
			continue // 체인 브랜치가 아니다(대문·dev 등)
		}
		nb := prefix + b
		if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+nb) {
			die("거부: 브랜치 " + nb + " 이미 있다 — 다른 --prefix 를 줘라.")
		}
		git("update-ref", "refs/heads/"+nb, n)
		made++
	}
	invalidateGraphNodes()

	// 4) **스스로 센다.** 무손실 확인을 사람의 스크립트에 맡기면, 그건 무손실 안내가 아니다
	//    (이슈 #95②④ — 사람이 직접 세는 스크립트를 짜서야 사이클 하나가 통째로 빠진 걸 알았다).
	//    체인마다 옛 스텝과 새 스텝을 세어 대조하고, 빠진 것은 (사이클, 스텝, kind)로 이름을 부른다.
	lost := layoutLossReport(prefix, ordered)
	// 5) 그리고 **자기 목적을 만족했는지 스스로 검사한다** — 모든 체인이 dev 에서 갈라졌나.
	//    지금까지는 fsck 를 따로 불러야 알았다. 만든 자가 자기 결과를 안 보는 것은 검사가 아니다.
	viol := fsckDevLayer()
	println2("migrate --to-dev-layout 완료 — 커밋 " + itoa(len(newSha)) + "개를 다시 그렸고 " +
		"브랜치 " + itoa(made) + "개를 세웠다(접두 \"" + prefix + "\").")
	for _, ln := range lost.lines {
		println2(ln)
	}
	if len(viol) > 0 {
		println2("  ⚠ 층 검사(스스로 돌렸다) — 새 나무가 목적을 만족하지 못했다:")
		for _, v := range viol {
			println2("    " + v)
		}
	}
	if lost.missing > 0 || len(viol) > 0 {
		// 조용한 성공보다 시끄러운 실패가 낫다. 종료코드로도 말한다 — 스크립트가 이걸 읽는다.
		die("거부: 이주가 온전하지 않다 — 스텝 " + itoa(lost.missing) + "개 유실 · 층 위반 " +
			itoa(len(viol)) + "건.\n" +
			"  새 브랜치(" + prefix + "*)는 남겨 두었다. 위 목록을 보고 원인을 고친 뒤,\n" +
			"  그 브랜치들을 지우고(git branch -D) 다시 실행하라. **옛 나무는 그대로다.**")
	}
	println2("  옛 브랜치는 그대로 있다 — 지우지 않는다. 두 나무를 나란히 놓고 세어서 무손실을 확인하라:")
	println2("    gil fsck            (새 나무의 위반)")
	println2("    gil viewer serve    (전체맵 맨 위 두 줄에 층이 보인다)")
	println2("  확인이 끝나면 옛 체인을 접어라(객체는 안 지운다 — 되돌릴 수 있다):")
	for _, ch := range ordered {
		println2("    gil chain-retire " + ch + " --reason '" + prefix + " 로 이주함'")
	}
	// 옛 나무에 위반(적층 등)이 있으면 retire 가 --confirm <이름> 을 요구한다. 그 문법을
	// 여기서 미리 주지 않으면, 이주를 마친 사람이 마지막 칸에서 멈춘다(내가 그랬다).
	println2("  ▸ 그 체인에 위반이 있으면(적층 등) 접는 것이 위반을 감추는 일이라 gil 이 한 번 더 묻는다:")
	println2("      gil chain-retire <옛체인> --reason '...' --confirm <옛체인>   (이름을 직접 타이핑하는 것이 그 게이트다)")
}

// runEnvIn — 환경변수와 stdin 을 함께 주고 실행(commit-tree 용). runEnv 계열의 짝.
func runEnvIn(env []string, in string, args ...string) string {
	return gitInputEnv(env, in, args...)
}

// regraft — 커밋 하나를 새 부모 위에 다시 그린다. 트리·메시지·저자는 그대로, 부모만 새 자리로.
// (앞머리를 dev 에 얹는 길과 체인 몸통을 그리는 길이 **같은 코드**를 써야 한다 — 갈라 두면
// 언젠가 한쪽만 고쳐지고, 새 나무의 절반만 참이 된다.)
func regraft(c *lcommit, ps []string, ch, prefix string, fromOf map[string]string,
	chains []string, roots map[string]string, base, devTip string) string {
	msg := git("log", "-1", "--format=%B", c.sha)
	msg = renameChainInMsg(msg, ch, prefix+ch)
	if p := fromOf[ch]; p != "" && contains(chains, p) {
		msg = renameChainInMsg(msg, p, prefix+p) // 계승 선언도 새 이름을 가리켜야 한다
	}
	msg = strings.TrimRight(msg, "\n") + "\nGil-Migrated-From: " + first9(c.sha) + "\n"
	// 체인 루트가 dev 에서 나면 **그 사실을 선언한다.** 선언이 없으면 뷰어는 그 체인의
	// 출발을 층에 못 묶고(시조가 미아처럼 보인다), fsck 도 대조할 것이 없다.
	if c.sha == roots[ch] && base == devTip &&
		!strings.Contains(msg, "Gil-Chain-Orphan:") {
		msg = strings.TrimRight(msg, "\n") + "\nGil-Chain-Orphan: " + devBranchName + "\n"
	}
	args := []string{"commit-tree", c.tree}
	for _, p := range ps {
		args = append(args, "-p", p)
	}
	env := append(os.Environ(),
		"GIT_AUTHOR_NAME="+c.an, "GIT_AUTHOR_EMAIL="+c.ae, "GIT_AUTHOR_DATE="+c.ad,
		"GIT_COMMITTER_NAME="+c.an, "GIT_COMMITTER_EMAIL="+c.ae, "GIT_COMMITTER_DATE="+c.ad)
	n := strings.TrimSpace(runEnvIn(env, msg, args...))
	if n == "" {
		die("거부: 커밋을 다시 그리지 못했다: " + first9(c.sha))
	}
	return n
}

// lossSummary — 이주가 스스로 센 결과.
type lossSummary struct {
	missing int
	lines   []string
}

// layoutLossReport — 체인마다 **옛 스텝 수 / 새 스텝 수**를 세고, 빠진 것의 이름을 부른다.
//
// 왜 도구가 세야 하나(이슈 #95②). 무손실 확인 안내가 "fsck 와 뷰어 육안"이었는데, 브랜치가
// 안 세워진 사이클은 fsck 에 안 잡힌다(옛 나무가 아직 살아 있어 조용하다). 상현님은 스텝
// identity 를 직접 세는 스크립트를 짜서야 사이클 하나가 통째로 빠진 걸 발견했다.
// **사람이 스크립트를 짜야 알 수 있으면 그건 무손실 안내가 아니다.**
func layoutLossReport(prefix string, chains []string) lossSummary {
	type key struct{ cycle, step string }
	kindOf := map[string]string{}
	oldOf := map[string]map[key]bool{}
	newOf := map[string]map[key]bool{}
	fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Cycle") + fsep +
		trailer("Gil-Step") + fsep + trailer("Gil-Kind") + sep
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches"), sep) {
		ch, r1, ok := cut(strings.TrimSpace(rec), fsep)
		if !ok {
			continue
		}
		cy, r2, _ := cut(r1, fsep)
		st, kd, _ := cut(r2, fsep)
		ch, cy, st, kd = strings.TrimSpace(ch), strings.TrimSpace(cy), strings.TrimSpace(st), strings.TrimSpace(kd)
		if st == "" {
			continue
		}
		k := key{cy, st}
		if strings.HasPrefix(ch, prefix) && contains(chains, strings.TrimPrefix(ch, prefix)) {
			base := strings.TrimPrefix(ch, prefix)
			if newOf[base] == nil {
				newOf[base] = map[key]bool{}
			}
			newOf[base][k] = true
			continue
		}
		if contains(chains, ch) {
			if oldOf[ch] == nil {
				oldOf[ch] = map[key]bool{}
			}
			oldOf[ch][k] = true
			kindOf[ch+"/"+cy+"/"+st] = kd
		}
	}
	var sum lossSummary
	sum.lines = append(sum.lines, "  대조(이주가 스스로 셌다) — 체인별 옛 스텝 / 새 스텝:")
	for _, ch := range chains {
		o, n := oldOf[ch], newOf[ch]
		var miss []string
		for k := range o {
			if !n[k] {
				miss = append(miss, "      빠짐: "+ch+"/"+k.cycle+"/"+k.step+" ["+kindOf[ch+"/"+k.cycle+"/"+k.step]+"]")
			}
		}
		sort.Strings(miss)
		mark := "✓"
		if len(miss) > 0 {
			mark = "✗"
		}
		sum.lines = append(sum.lines, "    "+mark+" "+ch+": "+itoa(len(o))+" → "+itoa(len(n)))
		sum.lines = append(sum.lines, miss...)
		sum.missing += len(miss)
	}
	return sum
}

// orderByDeclaredCycles — 체인의 커밋을 **선언된 사이클 순서**로 늘어놓는다(이슈 #97①).
//
// 사이클 밖 커밋(chain-root·기준·인터뷰·chain-close)은 원래 자리를 지킨다: 첫 사이클 앞에
// 있던 것은 앞에, 뒤에 있던 것은 뒤에. 사이클은 선언(Gil-Cycle-Parent)을 따라 부모가 먼저
// 오도록 세운다. 선언이 순환이거나 없는 것은 원래 순서대로 뒤에 붙인다 — 옛 저장소의 결함
// 때문에 이주 자체가 막히면 안 된다(layoutChainOrder 와 같은 태도).
func orderByDeclaredCycles(body []*lcommit) []*lcommit {
	group := map[string][]*lcommit{}
	var cycOrderSeen []string
	var head, tail []*lcommit
	seenCycle := false
	parentOf := map[string]string{}
	for _, c := range body {
		if c.cycle == "" {
			if seenCycle {
				tail = append(tail, c)
			} else {
				head = append(head, c)
			}
			continue
		}
		seenCycle = true
		if _, ok := group[c.cycle]; !ok {
			cycOrderSeen = append(cycOrderSeen, c.cycle)
		}
		group[c.cycle] = append(group[c.cycle], c)
		if p := c.cycParent; p != "" && p != "null" && parentOf[c.cycle] == "" {
			parentOf[c.cycle] = p
		}
	}
	// 부모 먼저(위상 정렬). 못 세우는 것은 원래 순서로 뒤에.
	done := map[string]bool{}
	var order []string
	for i := 0; i < len(cycOrderSeen)+2 && len(order) < len(cycOrderSeen); i++ {
		for _, cy := range cycOrderSeen {
			if done[cy] {
				continue
			}
			p := parentOf[cy]
			if p == "" || done[p] || group[p] == nil {
				done[cy] = true
				order = append(order, cy)
			}
		}
	}
	for _, cy := range cycOrderSeen {
		if !done[cy] {
			order = append(order, cy)
		}
	}
	out := append([]*lcommit{}, head...)
	for _, cy := range order {
		out = append(out, group[cy]...)
	}
	return append(out, tail...)
}
