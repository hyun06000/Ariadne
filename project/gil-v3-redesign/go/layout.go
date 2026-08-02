// layout.go — main-dev-chain 레이아웃 (상현님, 2026-07-31).
//
// 옛 문법에는 **새 계보를 시작할 자리가 없었다.** 체인은 "닫힌 체인 끝에서만" 열렸으므로,
// 무관한 탐색선도 앞 체인 위에 얹혔다 — 데모 체인이 끝나면 그 데모에서 이어서 프로젝트를
// 계속하는 식이었다. 계보가 실제 사고 구조를 왜곡했고, drift 는 그걸 stacked 로 계속 짖었다.
// 짖는 게 옳았다. 얹을 수밖에 없는 문법이 문제였다.
//
// 그래서 층을 하나 넣는다:
//
//	main  — 대문(README·CLAUDE.md·existence·project)의 뿌리. 배포된 것만 여기 온다.
//	dev   — main 의 **루트 커밋**에서 갈라진 유일한 층. 모든 작업이 여기서 시작한다.
//	chain — dev 팁에서 갈라지거나(= 시조), 다른 닫힌 체인을 이어받거나(--from).
//
// **dev 를 부모로 둔 체인은 orphan 이다.** 이때 orphan 은 "대문을 못 물려받는다"가 아니다 —
// dev 는 main 루트의 자손이라 대문은 그대로 물려받는다(SPEC 규칙 2 유지). 끊기는 것은
// **gil 이 인정하는 계승**뿐이다: 앞선 체인이 없다는 선언, 즉 계보상 시조.
// 실재(커밋)와 선언(계보)은 다른 축이라는 v3.45.0 의 원칙이 여기서도 그대로 선다.
//
// dev → main 승격 = 배포(gil deploy). 체인 간 합류 = 머지(gil merge). 둘은 구분한다 —
// main·dev 를 체인으로 취급할지는 아직 정하지 않았기 때문이다.
package main

import (
	"sort"
	"strings"
)

// devBranchName — dev 층의 브랜치 이름. 고정이다(레이아웃의 이름은 문법의 일부).
const devBranchName = "dev"

// gateRootSHA — 대문의 뿌리 커밋. dev 가 갈라져 나오는 자리이자, 계보 판정의 기준점이다.
// 커밋이 없으면 "".
func gateRootSHA() string {
	out, err := gitTry("rev-list", "--max-parents=0", "HEAD")
	if err != nil {
		return ""
	}
	s := strings.TrimSpace(out)
	if i := strings.Index(s, "\n"); i >= 0 {
		s = s[:i] // 뿌리가 여럿이면(옛 orphan 브랜치들) 가장 오래된 하나 — 첫 줄이 HEAD 계보의 것이다.
	}
	return s
}

// hasDevLayer — 이 저장소가 dev 층을 갖췄나. 브랜치가 있는 것만으로는 부족하다:
// 사람이 만든 평범한 dev 브랜치와, gil 이 심은 층은 다른 것이다. 표식(dev-root)으로 가른다.
//
// 표식 없는 dev 브랜치를 층으로 오인하면, 체인들이 남의 작업 브랜치 위에 태어난다.
func hasDevLayer() bool {
	return devRootSHA() != ""
}

// devRootSHA — dev 층의 뿌리 커밋(Gil-Kind: dev-root). 없으면 "".
func devRootSHA() string {
	if !gitOK("rev-parse", "--verify", "-q", "refs/heads/"+devBranchName) {
		return ""
	}
	fmtStr := "%H" + fsep + trailer("Gil-Kind") + sep
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, devBranchName), sep) {
		sha, kind, _ := cut(strings.TrimSpace(rec), fsep)
		if strings.TrimSpace(kind) == "dev-root" {
			return strings.TrimSpace(sha)
		}
	}
	return ""
}

// devTipSHA — 체인이 갈라져 나올 자리. **루트가 아니라 팁이다** — dev 에 얹힌 대문 갱신을
// 새 체인이 물려받아야 하기 때문이다(뿌리에서 갈라지면 대문이 init 시점에서 멈춘다).
func devTipSHA() string {
	if !hasDevLayer() {
		return ""
	}
	return strings.TrimSpace(git("rev-parse", devBranchName))
}

// ensureDevLayer — dev 층을 심는다(gil init 전용). 이미 있으면 아무 일도 하지 않는다.
// 반환: 새로 심었나.
//
// **대문이 다 선 자리에서** 갈라진다. 뿌리 커밋에서 갈라고 싶은 유혹이 있지만(그러면 main
// 팁엔 배포된 것만 남는다), 그렇게 하면 dev 가 대문 파일(docs/gil·llms.txt·진입점 블록)을
// 못 물려받는다 — SPEC 규칙 2 가 깨진다. 대문이 완성된 시점의 main 팁이 곧 대문이고,
// 그 자리가 dev 의 뿌리다. 어디서 갈라졌는지는 트레일러에 남겨 나중에 대조 가능하게 한다.
func ensureDevLayer() bool {
	if hasDevLayer() {
		return false
	}
	base := strings.TrimSpace(git("rev-parse", "HEAD"))
	if base == "" {
		return false // 커밋이 하나도 없는 저장소 — 대문부터 서야 층이 선다.
	}
	if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+devBranchName) {
		// 표식 없는 dev 가 이미 있다. 남의 브랜치를 층으로 삼키지 않는다 — 조용히 물러난다.
		// (드리프트가 이걸 no-dev-layer 로 보고하고, migrate 가 이름 충돌을 다룬다.)
		return false
	}
	commitOn(devBranchName, base,
		"gil init: dev 층 개설",
		"모든 작업은 dev 에서 시작한다. dev 를 부모로 둔 체인은 계보상 시조(orphan)다 —\n"+
			"대문(README·CLAUDE.md·existence·project)은 dev 가 main 루트의 자손이라 그대로\n"+
			"물려받고, 끊기는 것은 '앞선 체인' 뿐이다.\n\n"+
			"dev 에서 main 으로의 승격 = 배포(gil deploy). 체인 간 합류 = gil merge.",
		[][2]string{{"Gil-Kind", "dev-root"}, {"Gil-Dev-From", base}}, true)
	return true
}

// promoteDevToMain — dev 를 대문(main)에 머지한다 = **배포**.
//
// 승격은 머지와 구분한다(상현님): main·dev 를 체인으로 취급할지 아직 정하지 않았으므로,
// 여기서는 체인 문법(두 조상·역순·완성만)을 적용하지 않는다. 층과 층 사이의 이동일 뿐이다.
// 그래서 gil merge 가 아니라 gil deploy 가 이 일을 한다.
//
// --no-ff 로 머지한다: fast-forward 로 붙이면 "언제 무엇이 배포됐나"가 커밋 하나로 남지
// 않는다. 배포는 사건이고, 사건은 자기 커밋을 가져야 한다.
//
// 반환: (했나, 사람에게 할 말). 실패는 die 하지 않는다 — 배포 마커는 이미 새겨졌고,
// 그 사실을 남긴 채 승격만 못 했다고 말하는 게 정직하다.
func promoteDevToMain(tag string) (bool, string) {
	if !hasDevLayer() {
		return false, "dev 층이 없어 승격할 것이 없다(옛 레이아웃) — gil migrate --to-dev-layout"
	}
	home := homeBranch()
	if home != "main" && home != "master" {
		return false, "대문 브랜치(main/master)를 못 찾았다 — 승격 대상이 없다"
	}
	if home == devBranchName {
		return false, "대문과 층이 같은 브랜치다 — 승격이 성립하지 않는다"
	}
	// 추적 파일만 본다(-uno). 추적되지 않은 파일은 브랜치를 옮겨도 따라올 뿐 승격을 막지
	// 않는다 — 그걸로 거부하면 회고 초안 하나가 배포를 세운다(실제로 그랬다).
	if dirty := strings.TrimSpace(git("status", "--porcelain", "-uno")); dirty != "" {
		return false, "작업트리가 깨끗하지 않다 — 승격은 브랜치를 옮겨 다니므로 먼저 커밋하거나 치워라:\n" +
			"    git status"
	}
	// 이미 대문에 다 들어가 있으면 승격할 것이 없다. 그 사실을 조용히 성공으로 위장하지 않는다.
	if gitOK("merge-base", "--is-ancestor", devBranchName, home) {
		return false, "dev 에 " + home + " 로 올릴 새 것이 없다 — 이미 다 배포됐다.\n" +
			"    (체인의 작업은 gil merge 로 dev 에 모인 뒤에야 배포 대상이 된다.)"
	}
	back := strings.TrimSpace(git("rev-parse", "--abbrev-ref", "HEAD"))
	if _, err := gitTry("checkout", "-q", home); err != nil {
		return false, "대문 브랜치로 옮기지 못했다: " + err.Error()
	}
	msg := "gil deploy " + tag + ": dev → " + home + " 승격\n\n" +
		"배포된 것만 대문에 온다. 이 머지 커밋이 그 사건이다."
	_, err := gitTry("merge", "--no-ff", "-q", "-m", msg, devBranchName)
	if err != nil {
		gitTry("merge", "--abort")
		gitTry("checkout", "-q", back)
		return false, "머지가 충돌했다 — 사람이 풀어야 한다:\n" +
			"    git checkout " + home + " && git merge --no-ff " + devBranchName
	}
	// 작업은 dev 에서 계속된다 — 배포했다고 사람을 대문에 세워두지 않는다.
	gitTry("checkout", "-q", back)
	invalidateGraphNodes()
	return true, ""
}

// devLayerFacts — 층이 산 순서와, 각 체인이 **실제로** 갈라진 자리. 뷰어와 CLI 가 같은 답을
// 하도록 한 군데서 센다: 두 표면이 다르면 사람은 어느 쪽을 믿을지부터 고민한다.
//
// order 는 dev-root(층 개설)부터 dev 팁까지 첫 부모 사슬을 오래된 것부터. forks 는 체인 →
// 그 체인 chain-root 의 첫 부모(9자). step 은 order 안의 자리(0=층이 열린 그 커밋).
type devLayerFactsT struct {
	order []string          // 오래된 것부터 — order[0] = dev-root
	step  map[string]int    // sha9 → 층에서 몇 걸음째
	subj  map[string]string // sha9 → 그 커밋 제목
	forks map[string]string // 체인 → 갈라진 dev 커밋(sha9)
	// 시조라고 **선언**한 체인(Gil-Chain-Orphan: dev). 갈라진 자리는 실재로 알지만, 선언은
	// 따로 안다 — 병렬 트랙(--parallel-with)은 층에서 갈라지되 시조 선언을 달지 않는다.
	declared map[string]bool
}

func devLayerFacts(run func(...string) ([]byte, error)) devLayerFactsT {
	f := devLayerFactsT{step: map[string]int{}, subj: map[string]string{}, forks: map[string]string{},
		declared: map[string]bool{}}
	var seq []string // 최신부터
	for _, ref := range []string{devBranchName, "origin/" + devBranchName} {
		o, err := run("log", "--first-parent", "--format=%H"+fsep+"%s"+fsep+trailer("Gil-Kind")+sep, ref)
		if err != nil {
			continue
		}
		for _, rec := range strings.Split(string(o), sep) {
			rec = strings.Trim(rec, "\n")
			if strings.TrimSpace(rec) == "" {
				continue
			}
			sha, r1, ok := cut(rec, fsep)
			if !ok {
				continue
			}
			subj, kind, _ := cut(r1, fsep)
			s := first9(strings.TrimSpace(sha))
			seq = append(seq, s)
			f.subj[s] = strings.TrimSpace(subj)
			// 층이 개설된 커밋에서 자른다 — 그 앞은 대문(main)이 산 구간이라, 층의 걸음으로
			// 세면 수가 틀리고 갈라진 자리도 그만큼 밀린다.
			if strings.TrimSpace(kind) == "dev-root" {
				break
			}
		}
		break
	}
	for i := len(seq) - 1; i >= 0; i-- { // 오래된 것부터
		f.step[seq[i]] = len(f.order)
		f.order = append(f.order, seq[i])
	}
	// 각 체인이 갈라진 자리 — 선언(Gil-Chain-Orphan)이 아니라 chain-root 의 실제 부모.
	fmtStr := "%P" + fsep + trailer("Gil-Chain") + fsep + trailer("Gil-Kind") + fsep +
		trailer("Gil-Chain-Orphan") + sep
	o, err := run("log", "--branches", "--remotes", "--format="+fmtStr)
	if err != nil {
		return f
	}
	for _, rec := range strings.Split(string(o), sep) {
		par, r1, ok := cut(strings.Trim(rec, "\n"), fsep)
		if !ok {
			continue
		}
		ch, r2, _ := cut(r1, fsep)
		kind, orphan, _ := cut(r2, fsep)
		if strings.TrimSpace(kind) != "chain-root" {
			continue
		}
		// 선언이 아니라 **실재**로 싣는다: 첫 부모가 층 위면 그 체인은 층에서 갈라졌다.
		// 선언만 보면 병렬 트랙의 출발이 그림에서 통째로 빠져, 층에서 난 체인이 미아로 보인다.
		name := strings.TrimSpace(ch)
		if name == "" {
			continue
		}
		if strings.TrimSpace(orphan) == devBranchName {
			f.declared[name] = true
		}
		if ps := strings.Fields(par); len(ps) > 0 {
			f.forks[name] = first9(ps[0])
		}
	}
	return f
}

// devLayerFactsCLI — CLI 쪽 러너(현재 저장소). 뷰어는 viewerGit 을 넘긴다(--repo 를 본다).
func devLayerFactsCLI() devLayerFactsT {
	return devLayerFacts(func(a ...string) ([]byte, error) {
		return []byte(git(a...)), nil
	})
}

// devForkLine — "이 체인은 층의 어디에서 갈라졌나" 한 줄. 층이 없거나 모르면 빈 문자열.
func devForkLine(chain string) string {
	if !hasDevLayer() {
		return ""
	}
	f := devLayerFactsCLI()
	sha, ok := f.forks[chain]
	if !ok {
		return ""
	}
	i, on := f.step[sha]
	if !on {
		if !f.declared[chain] {
			return "" // 층에서 난 체인이 아니다(계승·이주 등) — 여기서 할 말이 없다
		}
		return "  층: 이 체인은 dev 에서 갈라졌다고 선언했는데 실재는 dev 밖(" + sha + ")이다 — gil fsck 가 짚는다."
	}
	where := "층이 열린 그 자리"
	if i > 0 {
		where = "dev " + itoa(i) + "걸음째"
	}
	return "  층: 이 체인은 " + where + "(" + sha + " " + clip(f.subj[sha], 48) + ")에서 갈라졌다 — " +
		"그 앞의 dev 는 물려받았고, 그 뒤의 dev 는 아직 모른다."
}

// fsckDevLayer — **층의 선언과 실재를 대조한다.**
//
// `Gil-Chain-Orphan: dev` 는 "나는 dev 에서 갈라졌다"는 선언이다. 트레일러에 그렇게 적고
// 실제로는 다른 자리에서 갈라졌다면, 그 계보는 거짓이다 — v3.45.0 이 사이클에 세운 판정을
// 층에도 그대로 세운다. 판정은 눈이 아니라 도구가 한다.
//
// 약한 검사를 경계한다: "dev 의 어느 커밋이든 조상이면 통과"로 짜면, dev 에서 난 체인 위에
// 얹힌 체인도 통과한다(그 체인 역시 dev 의 자손이므로). 그래서 **부모 커밋이 dev 브랜치에서
// 실제로 닿는 커밋인가**를 본다 — 체인 위에 얹혔다면 그 부모는 dev 에서 안 닿는다.
func fsckDevLayer() []string {
	if !hasDevLayer() {
		return nil
	}
	// dev 브랜치에서 닿는 커밋 전부. 체인 브랜치의 커밋은 여기 없다.
	onDev := map[string]bool{}
	for _, l := range strings.Split(gitlog("--format=%H", devBranchName), "\n") {
		if s := strings.TrimSpace(l); s != "" {
			onDev[s] = true
		}
	}
	fmtStr := "%H" + fsep + "%P" + fsep + trailer("Gil-Chain") + fsep +
		trailer("Gil-Kind") + fsep + trailer("Gil-Chain-Orphan") + sep
	var out []string
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches"), sep) {
		sha, r1, ok := cut(strings.TrimSpace(rec), fsep)
		if !ok {
			continue
		}
		par, r2, _ := cut(r1, fsep)
		ch, r3, _ := cut(r2, fsep)
		kind, orphan, _ := cut(r3, fsep)
		if strings.TrimSpace(kind) != "chain-root" || strings.TrimSpace(orphan) != "dev" {
			continue
		}
		_ = sha
		ps := strings.Fields(par)
		if len(ps) == 0 {
			out = append(out, "층: 체인 "+strings.TrimSpace(ch)+" — dev 에서 갈라졌다고 선언했는데 "+
				"**부모가 없다**(저장소의 첫 커밋이다). 선언과 실재가 다르다.")
			continue
		}
		if !onDev[ps[0]] {
			out = append(out, "층: 체인 "+strings.TrimSpace(ch)+" — dev 에서 갈라졌다고 선언했는데 "+
				"**실제로는 dev 에서 닿지 않는 커밋("+first9(ps[0])+")에서 갈라졌다**.\n"+
				"    dev 층에서 난 시조가 아니라 무언가에 얹힌 체인이다 — 선언만 있고 분기는 없다.\n"+
				"    확인: git log --oneline --graph "+devBranchName+" "+strings.TrimSpace(ch))
		}
	}
	sort.Strings(out)
	return out
}

// devLayerNudge — dev 층이 없는 저장소(옛 레이아웃)에게 주는 안내. 거부가 아니라 안내인
// 이유: 이 저장소들은 gil 이 층을 만들기 전에 태어났고, 이주 경로(gil migrate)가 서기
// 전에 문법으로 막으면 이미 있는 나무가 통째로 얼어붙는다. 집행 지점은 **탄생**(gil init)이다.
func devLayerNudge() {
	stderr("  ▸ 이 저장소엔 dev 층이 없다 — 새 계보를 시작할 자리가 문법에 없다는 뜻이다.")
	stderr("    그래서 무관한 탐색선도 앞 체인 위에 얹히고, drift 가 그걸 stacked 로 계속 짖는다.")
	stderr("    나무 전체를 main-dev-chain 으로 옮기려면(먼저 무엇이 일어날지 본다):")
	stderr("      gil migrate --to-dev-layout --dry-run")
}
