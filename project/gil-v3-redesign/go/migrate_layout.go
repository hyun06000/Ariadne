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
	sha, tree string
	parents   []string
	chain     string
	an, ae, ad string // 저자 이름·메일·날짜 — 이주는 저자를 바꾸지 않는다
}

// collectLayoutCommits — 브랜치 전체의 커밋을 다시 그리기에 필요한 만큼만 읽는다.
func collectLayoutCommits() (map[string]*lcommit, []string) {
	fmtStr := "%H" + fsep + "%T" + fsep + "%P" + fsep + trailer("Gil-Chain") +
		fsep + "%an" + fsep + "%ae" + fsep + "%aI" + sep
	byS := map[string]*lcommit{}
	var order []string // git log 순(최신→과거)
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches", "--topo-order"), sep) {
		rec = strings.Trim(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		f := strings.SplitN(rec, fsep, 7)
		if len(f) < 7 {
			continue
		}
		c := &lcommit{
			sha: strings.TrimSpace(f[0]), tree: strings.TrimSpace(f[1]),
			parents: strings.Fields(f[2]), chain: strings.TrimSpace(f[3]),
			an: f[4], ae: f[5], ad: strings.TrimSpace(f[6]),
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

// cmdMigrateToDevLayout — 옛 나무를 main-dev-chain 으로 다시 그린다.
func cmdMigrateToDevLayout(prefix string, dryRun bool) {
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
		for _, c := range inChain[ch] {
			var ps []string
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
			msg := git("log", "-1", "--format=%B", c.sha)
			msg = renameChainInMsg(msg, ch, prefix+ch)
			if p := fromOf[ch]; p != "" && contains(chains, p) {
				msg = renameChainInMsg(msg, p, prefix+p) // 계승 선언도 새 이름을 가리켜야 한다
			}
			msg = strings.TrimRight(msg, "\n") + "\nGil-Migrated-From: " + first9(c.sha) + "\n"
			// 체인 루트가 dev 에서 나면 **그 사실을 선언한다.** 선언이 없으면 뷰어는 그 체인의
			// 출발을 층에 못 묶고(시조가 미아처럼 보인다), fsck 도 대조할 것이 없다.
			// 옮겨 놓고 선언을 안 하면, 새 나무는 참인데 아무도 그걸 못 읽는다.
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
			newSha[c.sha] = n
			chainTip[ch] = n
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
	println2("migrate --to-dev-layout 완료 — 커밋 " + itoa(len(newSha)) + "개를 다시 그렸고 " +
		"브랜치 " + itoa(made) + "개를 세웠다(접두 \"" + prefix + "\").")
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
