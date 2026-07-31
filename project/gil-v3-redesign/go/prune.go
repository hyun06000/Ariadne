// prune.go — 체인 정리: 괴리 진단(drift) · 흡수(reconcile) · 폐기(retire) · 삭제(prune).
//
// 왜 (상현님, 2026-07-29). "git 그래프와 gil 그래프가 너무 다르게 찍힌다. 언젠가 체인을
// 쳐내거나 없애는 과정이 있을 텐데, 괴리가 심하면 그것도 큰일이다."
//
// 설계의 축은 하나다 — **append-only 는 그래프 *안*의 규율이지 저장소의 물리 법칙이 아니다.**
// 스텝을 고치거나 되돌리는 것은 영원히 막는다. 그러나 "이 체인은 폐기됐다"는 **새 사실**이고,
// 새 사실은 append 로 표현된다. 그래서 정리를 네 단으로 나눈다:
//
//  1. gil drift      — 괴리를 이름 붙여 보여준다(읽기 전용). 무엇이 왜 어긋났나.
//  2. gil reconcile  — 설명 가능한 괴리는 **선언으로 흡수**한다(무손실). orphan 뿌리는
//                      "의도된 조상 0"으로, 적층은 "병렬 선언"으로. 없어지는 건 위반이지
//                      역사가 아니다. gil 이 기준이므로 git 쪽(잃은 ref)은 복원해 맞춘다.
//  3. gil chain-retire — 폐기 선언 + 브랜치를 refs/gil/retired/* 로 옮긴다. **객체는 하나도
//                      안 지운다.** 되돌릴 수 있다(unretire). 대부분의 '정리'는 여기서 끝난다.
//  4. gil prune      — 진짜 삭제. 여기서만 되돌릴 수 없고, 그래서 조건이 셋이다:
//                      (a) 사람의 승인 커밋(뷰어 카드에서 누른 것), (b) CLI 확인 문구,
//                      (c) 묘비와 번들. **묘비 없는 삭제는 없다** — 계보가 "여기 뭔가 있었고
//                      결론은 이랬다"를 계속 말해야 한다. 그게 없으면 gil 이 지운 자리는
//                      git 이 지운 자리와 똑같아진다.
package main

import (
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

const retiredPrefix = "refs/gil/retired/"

// ── 1. drift — 괴리 진단 ──────────────────────────────────────────────

type driftItem struct {
	chain string
	kind  string // orphan-root | stacked | ref-missing | stray-branch | retired
	note  string
	fix   string
}

// chainRoots — 체인 이름 → chain-root 커밋 sha(전체 그래프 기준).
func chainRoots(rng string) map[string]string {
	roots := map[string]string{}
	fmtStr := "%H" + fsep + trailer("Gil-Chain") + fsep + trailer("Gil-Kind") + sep
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, rng), sep) {
		sha, rest, _ := cut(strings.TrimSpace(rec), fsep)
		ch, kind, _ := cut(rest, fsep)
		if strings.TrimSpace(kind) == "chain-root" && strings.TrimSpace(ch) != "" {
			roots[strings.TrimSpace(ch)] = strings.TrimSpace(sha)
		}
	}
	return roots
}

// reconciled — 이 체인이 어떤 선언으로 괴리를 흡수했나(Gil-Reconcile 트레일러). 없으면 "".
func reconciled(chain string) (kind, with string) {
	fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Reconcile") + fsep + trailer("Gil-Reconcile-With") + sep
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--all"), sep) {
		ch, rest, _ := cut(strings.TrimSpace(rec), fsep)
		rc, w, _ := cut(rest, fsep)
		if strings.TrimSpace(ch) == chain && strings.TrimSpace(rc) != "" {
			return strings.TrimSpace(rc), strings.TrimSpace(w)
		}
	}
	return "", ""
}

// retiredChains — refs/gil/retired/* 에 들어간 체인 이름들.
func retiredChains() map[string]bool {
	out := map[string]bool{}
	for _, ln := range strings.Fields(git("for-each-ref", "--format=%(refname:short)", retiredPrefix)) {
		name := strings.TrimPrefix(strings.TrimSpace(ln), "gil/retired/")
		if i := strings.Index(name, "/"); i >= 0 {
			name = name[:i]
		}
		if name != "" {
			out[name] = true
		}
	}
	return out
}

// driftReport — gil 그래프와 git 그래프가 어긋난 자리들. gil 이 기준이다.
func driftReport(only string) []driftItem {
	var items []driftItem
	roots := chainRoots("--all")
	retired := retiredChains()
	// 대문(첫 커밋) — orphan 판정의 기준점. gil init 이 심은 뿌리다.
	base := strings.TrimSpace(git("rev-list", "--max-parents=0", "HEAD"))
	if i := strings.Index(base, "\n"); i >= 0 {
		base = base[:i]
	}
	var names []string
	for c := range roots {
		if only == "" || c == only {
			names = append(names, c)
		}
	}
	sort.Strings(names)
	for _, c := range names {
		rk, rw := reconciled(c)
		if retired[c] {
			items = append(items, driftItem{c, "retired", "폐기됨(refs/gil/retired/) — 객체는 남아 있다",
				"되돌리려면: gil chain-unretire " + c})
			continue
		}
		// (a) ref 유실 — gil 은 이 체인을 아는데 git 브랜치가 없다. gil 이 기준이니 복원한다.
		if !gitOK("rev-parse", "--verify", "-q", "refs/heads/"+c) {
			items = append(items, driftItem{c, "ref-missing",
				"gil 그래프엔 있는데 refs/heads/" + c + " 가 없다 — git 쪽이 gil 을 못 따라간다",
				"복원: gil reconcile " + c + " --restore-ref"})
		}
		// (b) orphan 뿌리 — 조상 0. 의도된 격리일 수 있으나(SPEC: orphan 실작업 체인),
		// 선언이 없으면 뷰어·fsck 는 그걸 '끊긴 계보'로 읽는다.
		if base != "" && roots[c] != "" && !gitOK("merge-base", "--is-ancestor", base, roots[c]) {
			if rk != "orphan" {
				items = append(items, driftItem{c, "orphan-root",
					"체인 루트가 대문 계보에 없다(조상 0 또는 다른 뿌리) — 선언이 없으면 '끊긴 계보'로 읽힌다",
					"의도한 격리면: gil reconcile " + c + " --as orphan --reason <왜 독립 뿌리인가>"})
			}
		}
		// (c) 적층 — 다른 체인 루트 위에 얹혔는데 계승이 아니다(fsck 와 같은 축, 이슈 #65).
		//
		// **가장 가까운 조상 하나만** 본다. 체인은 닫힌 체인 끝에서 자라므로 오래 산 저장소에서는
		// 모든 체인이 모든 앞 체인의 후손이 된다 — 실사용 저장소(26체인)에서 쌍마다 보고했더니
		// 243건이 나왔고, 그건 진단이 아니라 잡음이다. 어긋남은 "바로 위 무엇에 얹혔나" 하나로
		// 족하고, 그마저 계승으로 설명되면 괴리가 아니다.
		if near := nearestStackedChain(c, roots); near != "" {
			if !(rk == "parallel" && (rw == near || rw == "")) && !declaredParallel(c, near) {
				// **두 그래프가 서로 다른 부모를 그린다**는 사실을 그대로 말한다. gil 이 계승으로
				// 인정한 부모(닫힌 끝에서 태어남, #53)와 git 이 보여주는 '바로 위'가 다르면,
				// 사람은 뷰어와 git log 를 번갈아 보며 어느 쪽이 참인지 모른다 — 그게 괴리의 정체다.
				gilParent := chainParents()[c]
				note := "git 은 이 체인이 " + near + " 위에 얹혔다고 하는데, "
				if gilParent != "" {
					note += "gil 은 " + gilParent + " 를 계승으로 본다 — 두 그래프가 다른 부모를 그린다"
				} else {
					note += "gil 은 계승 부모가 없다고 본다(닫힌 체인 끝에서 태어나지 않았다)"
				}
				fix := "둘 중 하나다:\n" +
					"      · 정말 이어받은 것이면 → 그 체인을 닫아라: gil chain-close " + near + "  (닫힌 끝에서 자란 것만 계승이다)\n" +
					"      · 그냥 그 자리에 있었을 뿐이면 → gil reconcile " + c + " --as parallel --with " + near + " --reason <왜>"
				if chainClosed(near, "--all") {
					fix = "이어받음이 아니면 병렬로 선언하라: gil reconcile " + c + " --as parallel --with " + near + " --reason <왜>"
				}
				items = append(items, driftItem{c, "stacked", note, fix})
			}
		}
	}
	// (e) dev 층 없음 — 이 저장소엔 **새 계보를 시작할 자리가 없다.** 그래서 무관한 탐색선도
	// 앞 체인 위에 얹히고, 위의 stacked 보고가 끝없이 재발한다. 증상만 세고 원인을 말하지
	// 않으면 사람은 같은 항목을 매번 다시 읽는다 — 원인을 한 줄로 세운다.
	if only == "" && len(names) > 0 && !hasDevLayer() {
		items = append(items, driftItem{devBranchName, "no-dev-layer",
			"dev 층이 없다 — 새 계보를 시작할 자리가 문법에 없어, 무관한 체인도 앞 체인 위에 얹힌다",
			"나무 전체를 옮기려면: gil migrate --to-dev-layout"})
	}
	// (d) 잔재 브랜치 — 브랜치는 있는데 gil 이 모르는 것. 정리 후보다.
	if only == "" {
		home := homeBranch()
		for _, b := range branches() {
			if roots[b] != "" || strings.Contains(b, "-") { // 사이클·스텝 가지는 체인 브랜치가 대표한다
				continue
			}
			if b == home {
				continue // 대문이 사는 브랜치다 — gil 커밋이 없어도 잔재가 아니다(뿌리다)
			}
			if b == devBranchName && hasDevLayer() {
				continue // 층이다. 체인이 아직 하나도 없어도 잔재가 아니다 — 모든 체인이 여기서 난다.
			}
			// 대문 계보(체인들이 그 위에서 자란 자리)도 잔재가 아니다.
			ancestorOfChain := false
			for _, rsha := range roots {
				if rsha != "" && gitOK("merge-base", "--is-ancestor", b, rsha) {
					ancestorOfChain = true
					break
				}
			}
			if ancestorOfChain {
				continue
			}
			if strings.TrimSpace(gitlog("--format="+trailer("Gil-Chain"), b, "--")) != "" {
				continue // gil 커밋을 담고 있다 — 잔재가 아니다
			}
			items = append(items, driftItem{b, "stray-branch",
				"gil 커밋이 하나도 없는 브랜치 — gil 그래프에 존재하지 않는다",
				"정리하려면: gil chain-retire " + b + " --reason <왜>  (객체는 안 지운다)"})
		}
	}
	return items
}

// declaredParallel — 체인을 열 때 --parallel-with 로 이미 선언했나(이슈 #54). 선언된 병렬은
// 사고가 아니라 판단이므로 괴리로 세지 않는다 — fsck 와 같은 판정을 쓴다.
func declaredParallel(a, b string) bool {
	fmtStr := trailer("Gil-Chain") + fsep + trailerMulti("Gil-Parallel-With") + sep
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--all"), sep) {
		ch, pw, _ := cut(strings.TrimSpace(rec), fsep)
		c, ps := strings.TrimSpace(ch), strings.Fields(pw)
		for _, p := range ps {
			if (c == a && p == b) || (c == b && p == a) {
				return true
			}
		}
	}
	return false
}

// nearestStackedChain — 이 체인 루트의 **가장 가까운** 조상 체인(진짜 계승이면 빈 문자열).
// 가까움은 루트까지의 커밋 수로 잰다 — 깊을수록 가깝다.
func nearestStackedChain(c string, roots map[string]string) string {
	parents := chainParents()
	best, bestN := "", -1
	for other, osha := range roots {
		if other == c || osha == "" || parents[c] == other {
			continue
		}
		if !gitOK("merge-base", "--is-ancestor", osha, roots[c]) {
			continue
		}
		n := 0
		if cnt, err := gitTry("rev-list", "--count", osha); err == nil {
			n, _ = strconv.Atoi(strings.TrimSpace(cnt))
		}
		if n > bestN {
			best, bestN = other, n
		}
	}
	return best
}

func cmdDrift(args []string) {
	fs := newFlags("gil drift")
	pos := fs.parse(args)
	only := ""
	if len(pos) > 0 {
		only = pos[0]
	}
	items := driftReport(only)
	if len(items) == 0 {
		println2("drift: 괴리 0 — gil 그래프와 git 그래프가 같은 이야기를 한다.")
		return
	}
	println2("drift: 괴리 " + itoa(len(items)) + "건 — gil 이 기준이다. 설명되는 괴리는 선언으로 흡수하고,")
	println2("       설명되지 않는 것만 정리(retire) 대상이 된다.")
	for _, it := range items {
		println2("")
		println2("  [" + it.kind + "] " + it.chain)
		println2("    " + it.note)
		println2("    → " + it.fix)
	}
	println2("")
	println2("  정리 단계: gil reconcile(흡수·무손실) → gil chain-retire(폐기·가역) → gil prune(삭제·비가역)")
}

// ── 2. reconcile — 괴리를 선언으로 흡수 ────────────────────────────────

func cmdReconcile(args []string) {
	fs := newFlags("gil reconcile")
	as := fs.str("as", "")
	with := fs.str("with", "")
	reason := fs.str("reason", "")
	restoreRef := fs.boolFlag("restore-ref")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil reconcile <chain> --as orphan|parallel [--with <다른체인>] --reason <왜>\n" +
			"      또는: gil reconcile <chain> --restore-ref   (gil 은 아는데 git 브랜치가 없을 때)\n" +
			"  괴리를 지우는 게 아니라 **설명을 append 한다** — 역사는 그대로 두고 위반만 없앤다.")
	}
	chain := pos[0]
	if chainPurpose(chain, "--all") == "" {
		die("거부: 체인 \"" + chain + "\" 이 gil 그래프에 없다 — 먼저 gil drift 로 확인하라.")
	}
	if *restoreRef {
		if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+chain) {
			die("거부: refs/heads/" + chain + " 는 이미 있다 — 복원할 것이 없다.")
		}
		tip := chainLatestCommit(chain)
		if tip == "" {
			// ref 가 없으면 chainLatestCommit 도 못 찾는다 — 그래프 전체에서 이 체인 소속
			// 커밋 중 가장 최근 것을 쓴다. 스텝만 보면 안 된다: 스텝 없는 체인(chain-root 만)도
			// 복원 대상이고, 그게 오히려 흔하다.
			fmtStr := "%H" + fsep + trailer("Gil-Chain") + sep
			for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--all"), sep) {
				sha, ch, _ := cut(strings.TrimSpace(rec), fsep)
				if strings.TrimSpace(ch) == chain {
					tip = strings.TrimSpace(sha)
					break
				}
			}
		}
		if tip == "" {
			die("거부: 이 체인의 커밋을 찾지 못했다 — 객체가 이미 사라졌을 수 있다(git fsck 로 확인).")
		}
		git("update-ref", "refs/heads/"+chain, tip)
		println2("reconcile: refs/heads/" + chain + " 복원 → " + tip)
		println2("  gil 이 기준이다 — git 쪽이 gil 그래프를 다시 따라간다.")
		return
	}
	if *as != "orphan" && *as != "parallel" {
		die("거부: --as 는 orphan|parallel 중 하나\n" +
			"  orphan   — 조상 0의 독립 뿌리다(의도된 격리, SPEC 의 orphan 실작업 체인).\n" +
			"  parallel — 다른 체인 위에 얹혔지만 계승이 아니라 나란히 자란 것이다(--with 필요).")
	}
	if *as == "parallel" && strings.TrimSpace(*with) == "" {
		die("거부: --as parallel 은 --with <다른체인> 필요 — 무엇과 나란한지 적어야 선언이 된다.")
	}
	if strings.TrimSpace(*reason) == "" {
		die("거부: --reason <왜> 필요 — 선언은 이유가 있어야 다음 세대가 읽는다.\n" +
			"  예: --reason '뷰어는 버려질 수 있는 실작업이라 대문 계보에 이력을 박지 않는다(SPEC orphan 체인).'")
	}
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Kind", "reconcile"},
		{"Gil-Reconcile", *as},
	}
	if *with != "" {
		tr = append(tr, [2]string{"Gil-Reconcile-With", *with})
	}
	body := "괴리 흡수 선언(" + *as + ")\n\n" + *reason + "\n\n" +
		"이 선언은 그래프를 바꾸지 않는다 — 커밋 조상관계는 그대로다. 바뀌는 것은 **읽는 법**이다:\n" +
		"gil fsck·뷰어가 이 관계를 사고(事故)가 아니라 판단으로 읽는다."
	if tip := strings.TrimSpace(git("rev-parse", "--verify", "-q", "refs/heads/"+chain)); tip != "" {
		alignHeadToTip(first9(tip), chain)
	}
	commit("gil "+chain+" reconcile: "+*as, body, tr, true)
	println2("reconcile: " + chain + " — " + *as + " 로 선언됨" + orDefault(" (with "+*with+")", ""))
	println2("  괴리는 사라지지 않는다. 사라지는 것은 위반이다 — 역사는 그대로 남는다.")
}

// ── 3. retire — 폐기(가역) ────────────────────────────────────────────

// chainRefs — 이 체인이 쓰는 로컬 ref 들(체인 브랜치 + 사이클/스텝 가지).
func chainRefs(chain string) []string {
	var out []string
	for _, b := range branches() {
		if b == chain || strings.HasPrefix(b, chain+"-") {
			out = append(out, b)
		}
	}
	sort.Strings(out)
	return out
}

// byTrailer — 출처가 있으면 Gil-By 한 줄, 없으면 비어 있다.
func byTrailer(by string) [][2]string {
	if b := strings.TrimSpace(by); b != "" {
		return [][2]string{{"Gil-By", b}}
	}
	return nil
}

// retiredChainNames — refs/gil/retired/ 에 접혀 있는 체인 이름들.
func retiredChainNames() []string {
	seen := map[string]bool{}
	var out []string
	for _, ln := range strings.Fields(git("for-each-ref", "--format=%(refname:short)", retiredPrefix)) {
		short := strings.TrimPrefix(strings.TrimSpace(ln), "gil/retired/")
		if short == "" {
			continue
		}
		name := short
		if i := strings.Index(short, "-"); i > 0 {
			// <chain>-<cycle>… 형태의 하위 브랜치도 그 체인의 것으로 센다.
			if !seen[short] {
				// 체인 루트 이름을 정확히 모르므로 가장 긴 접두 후보를 그대로 쓴다.
				name = short
			}
		}
		if !seen[name] {
			seen[name] = true
			out = append(out, name)
		}
	}
	sort.Strings(out)
	return out
}

// hiddenViolationCount — 접힌(retired) 영역에 있어 **기본 보고에서 빠지는** 위반 수.
//
// 왜 이게 필요한가(이슈 #92): retire 는 객체를 지우지 않지만 **세는 범위에서 뺀다.** 그래서
// 위반이 있는 체인을 접으면 `gil fsck` 의 숫자가 뚝 떨어진다 — 아무것도 고치지 않았는데
// 건강해 보인다. 실사용에서 229 → 1 이 됐고, 그 228건은 그대로 남아 있었다.
// 없는 게 죄가 아니라 감춘 게 죄다(#87 의 축) — 그러니 접힌 것은 **집계로라도** 보여야 한다.
func hiddenViolationCount() int {
	if len(retiredChainNames()) == 0 {
		return 0
	}
	all := fsck(collectNodes("--all"), declaredChains("--all"), collectNodes("--all"), closedCycles("--all"))
	live := fsck(collectNodes("--branches"), declaredChains("--branches"), collectNodes("--branches"), closedCycles("--branches"))
	if n := len(all) - len(live); n > 0 {
		return n
	}
	return 0
}

// violationsMentioning — 지금 보고되는 위반 중 이 체인을 가리키는 것의 수(접히면 사라질 것들).
func violationsMentioning(chain string) int {
	vs := fsck(collectNodes("--branches"), declaredChains("--branches"),
		collectNodes("--branches"), closedCycles("--branches"))
	n := 0
	for _, v := range vs {
		if strings.Contains(v, chain+"/") || strings.Contains(v, " "+chain+" ") {
			n++
		}
	}
	return n
}

func cmdChainRetire(args []string) {
	fs := newFlags("gil chain-retire")
	reason := fs.str("reason", "")
	// 이슈 #92: 삭제엔 문이 셋인데 폐기엔 0개였다. 되돌릴 수 있다는 것이 게이트를 면제하는
	// 근거가 되고 있었는데, **되돌릴 수 있는 것과 되돌릴 필요를 알아차릴 수 있는 것은 다르다.**
	dryRun := fs.boolFlag("dry-run")
	confirm := fs.str("confirm", "")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil chain-retire <chain> --reason <왜 폐기하나> [--dry-run] [--confirm <chain>]\n" +
			"  폐기를 커밋으로 선언하고 브랜치를 " + retiredPrefix + " 로 옮긴다. **객체는 하나도 안 지운다** —\n" +
			"  기본 뷰에서 접힐 뿐이고, gil chain-unretire 로 되돌릴 수 있다.\n" +
			"  --dry-run: 무엇이 접히는지 먼저 본다(ref 수 · 사이클/스텝 수 · 함께 접히는 위반 수).")
	}
	chain := pos[0]
	if strings.TrimSpace(*reason) == "" {
		die("거부: --reason <왜> 필요 — 폐기도 기록이다. 이유 없는 폐기는 다음 세대가 읽을 수 없다.")
	}
	refs := chainRefs(chain)
	if len(refs) == 0 {
		// 거부만 하고 길이 없으면 벽이다(이슈 #91 ③). prune 은 이 체인을 아는데 retire 는
		// 모른다 — 정리 사다리(drift → reconcile → retire → prune)의 아래 칸이 위 칸의 대상을
		// 포함하지 않으면, 그 사이에 낀 체인은 접을 수도 지울 수도 없는 막다른 길이 된다.
		// 그러니 **무엇이 실재하는지 말하고, 갈 수 있는 길을 준다.**
		msg := "거부: " + chain + " 의 로컬 브랜치가 없다 — 접어서 감출 ref 자체가 없다.\n"
		already := false
		for _, r := range retiredChainNames() {
			if r == chain || strings.HasPrefix(r, chain+"-") {
				already = true
				break
			}
		}
		steps := 0
		for _, n := range collectNodes("--all") {
			if n.chain == chain {
				steps++
			}
		}
		switch {
		case already:
			msg += "  이미 접혀 있다(" + retiredPrefix + "). 펼치려면: gil chain-unretire " + chain
		case steps > 0 || chainPurpose(chain, "--all") != "":
			msg += "  다만 그래프에는 살아 있다(스텝 " + itoa(steps) + "개) — 브랜치만 없는 상태다.\n" +
				"    · 정말 지우려면: gil prune " + chain + " --dry-run  (prune 은 이 체인을 인식한다)\n" +
				"    · 올려둔 삭제 요청을 거두려면: gil prune " + chain + " --withdraw --reason <왜>\n" +
				"    · 이름·상태를 확인하려면: gil drift"
		default:
			msg += "  이 이름의 체인을 그래프에서도 못 찾았다 — 이름이 틀렸을 수 있다(gil drift 로 확인)."
		}
		die(msg)
	}
	// ── 영향 요약 — 접기 전에 **무엇이 시야에서 사라지는지** 말한다(이슈 #92) ──
	var cycSet = map[string]bool{}
	steps := 0
	for _, n := range collectNodes("--branches") {
		if n.chain == chain {
			steps++
			if n.cycle != "" {
				cycSet[n.cycle] = true
			}
		}
	}
	hides := violationsMentioning(chain)
	println2("chain-retire " + chain + " — 접히면 이렇게 된다:")
	println2("  · 브랜치(ref) " + itoa(len(refs)) + "개가 " + retiredPrefix + " 로 옮겨진다(객체는 안 지운다).")
	println2("  · 사이클 " + itoa(len(cycSet)) + "개 · 스텝 " + itoa(steps) + "개가 기본 뷰에서 접힌다.")
	if hides > 0 {
		println2("  · ⚠ **fsck 위반 " + itoa(hides) + "건이 기본 보고에서 함께 접힌다** — 고쳐지는 게 아니라 안 보이게 된다.")
	} else {
		println2("  · fsck 위반은 접히지 않는다(이 체인에 보고된 위반 0).")
	}
	println2("  · 되돌리기: gil chain-unretire " + chain)
	if *dryRun {
		println2("")
		println2("(--dry-run — 아무것도 옮기지 않았다. 실행하려면 --dry-run 을 빼라.)")
		return
	}
	// 위반을 함께 접는 것은 정리가 아니라 **은닉**이다 — 그때만 문을 단다(이슈 #92 제안 2·4).
	// 위반 없는 체인을 접는 건 지금처럼 한 줄로 끝난다: 규율은 마찰이 아니라 방향이다.
	if hides > 0 && strings.TrimSpace(*confirm) != chain {
		die("거부: 이 폐기는 fsck 위반 " + itoa(hides) + "건을 기본 보고에서 함께 접는다 — 그건 정리가 아니라 은닉이다.\n" +
			"  둘 중 하나를 골라라:\n" +
			"    ▸ 먼저 고친다   → gil fsck  로 그 " + itoa(hides) + "건을 보고 해결한 뒤 접어라.\n" +
			"    ▸ 알고도 접는다 → --confirm " + chain + " 를 붙여라(이 이름을 직접 타이핑하는 것이 그 게이트다).\n" +
			"  (접어도 위반은 사라지지 않는다 — gil fsck --all 에 그대로 있고, 기본 fsck 도 집계로 한 줄 남긴다.)")
	}
	// 폐기 선언을 **먼저** 남긴다 — 브랜치를 옮긴 뒤엔 그 체인 계보에 커밋할 자리가 없다.
	if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+chain) {
		alignHeadToTip(first9(strings.TrimSpace(git("rev-parse", "refs/heads/"+chain))), chain)
		commit("gil "+chain+" chain-retire: 폐기",
			"이 체인을 폐기한다.\n\n"+*reason+"\n\n"+
				"객체는 지우지 않았다 — 브랜치가 "+retiredPrefix+" 로 옮겨졌을 뿐이다.\n"+
				"되돌리려면: gil chain-unretire "+chain,
			[][2]string{{"Gil-Chain", chain}, {"Gil-Kind", "chain-retire"}, {"Gil-Reason", *reason}}, true)
		refs = chainRefs(chain) // 방금 커밋으로 팁이 움직였다
	}
	// HEAD 가 그 체인 위면 먼저 비켜준다 — 체크아웃된 브랜치는 옮길 수 없다.
	cur := strings.TrimSpace(git("rev-parse", "--abbrev-ref", "HEAD"))
	for _, r := range refs {
		if r == cur {
			home := homeBranch()
			if home == "" {
				die("거부: 지금 " + r + " 에 서 있는데 옮겨갈 브랜치가 없다 — 먼저 다른 브랜치로 이동하라.")
			}
			git("checkout", "-q", home)
			println2("  ▸ HEAD 를 " + home + " 로 옮겼다(폐기할 브랜치에 서 있을 수 없다).")
			break
		}
	}
	for _, r := range refs {
		sha := strings.TrimSpace(git("rev-parse", r))
		git("update-ref", retiredPrefix+r, sha)
		git("update-ref", "-d", "refs/heads/"+r)
	}
	println2("chain-retire: " + chain + " 폐기됨 — 브랜치 " + itoa(len(refs)) + "개를 " + retiredPrefix + " 로 옮겼다.")
	println2("  객체는 하나도 안 지웠다. 기본 뷰(gil log·뷰어·handoff)에서 접히고, 되돌릴 수 있다:")
	println2("    gil chain-unretire " + chain)
	println2("  정말 지우려면(비가역, 사람 승인 필요): gil prune " + chain + " --dry-run")
}

// homeBranch — 대문이 사는 브랜치(main/master), 없으면 아무 브랜치.
func homeBranch() string {
	for _, want := range []string{"main", "master"} {
		if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+want) {
			return want
		}
	}
	for _, b := range branches() {
		return b
	}
	return ""
}

func cmdChainUnretire(args []string) {
	fs := newFlags("gil chain-unretire")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil chain-unretire <chain>   (폐기한 체인을 되살린다)")
	}
	chain := pos[0]
	var moved int
	for _, ln := range strings.Fields(git("for-each-ref", "--format=%(refname:short)", retiredPrefix)) {
		short := strings.TrimPrefix(strings.TrimSpace(ln), "gil/retired/")
		if short != chain && !strings.HasPrefix(short, chain+"-") {
			continue
		}
		sha := strings.TrimSpace(git("rev-parse", retiredPrefix+short))
		git("update-ref", "refs/heads/"+short, sha)
		git("update-ref", "-d", retiredPrefix+short)
		moved++
	}
	if moved == 0 {
		die("거부: 폐기된 체인 \"" + chain + "\" 이 없다 — gil drift 로 확인하라.")
	}
	commit("gil "+chain+" chain-unretire: 복귀", "폐기를 되돌린다 — 브랜치 "+itoa(moved)+"개 복원.",
		[][2]string{{"Gil-Chain", chain}, {"Gil-Kind", "chain-unretire"}}, true)
	println2("chain-unretire: " + chain + " 복귀 — 브랜치 " + itoa(moved) + "개 복원.")
}

// ── 4. prune — 삭제(비가역) ───────────────────────────────────────────

// pruneApproved — 이 대상에 대한 **사람의 승인 커밋**이 있나(뷰어 카드에서 누른 것).
// pruneState — 이 대상의 **최신 사실**: none | requested | withdrawn | approved | pruned.
//
// 왜 상태로 보나(이슈 #91): 옛 코드는 "prune-request 커밋이 있나"만 봤다. 그래서 요청을 한 번
// 올리면 되돌릴 문법이 없어 **빠져나올 수 없었다** — 카드가 뷰어 상단을 영구히 덮었다.
// append-only 는 그래프 안의 규율이지 새 사실을 못 적는다는 뜻이 아니다: '이 요청은 더 이상
// 유효하지 않다' 도 새 사실이라 append 로 표현된다(prune 문서가 스스로 그렇게 말한다).
func pruneState(target string) string {
	fmtStr := trailer("Gil-Kind") + fsep + trailer("Gil-Prune-Target") + sep
	// gitlog 는 new→old — 가장 최근의 결정적 사실 하나만 보면 된다.
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--all"), sep) {
		k, t, _ := cut(strings.TrimSpace(rec), fsep)
		if strings.TrimSpace(t) != target {
			continue
		}
		switch strings.TrimSpace(k) {
		case "prune":
			return "pruned"
		case "prune-approve":
			return "approved"
		case "prune-withdraw":
			return "withdrawn"
		case "prune-request":
			return "requested"
		}
	}
	return "none"
}

func pruneApproved(target string) bool { return pruneState(target) == "approved" }

// pruneScope — 삭제 대상이 무엇이고 무엇을 잃는가. 체인 전체 또는 잎 스텝 하나.
type pruneScope struct {
	chain, cycle, step string
	refs               []string
	nodes              []node
	isNode             bool
}

func resolvePruneTarget(target string) pruneScope {
	parts := strings.Split(target, "/")
	switch len(parts) {
	case 1:
		chain := parts[0]
		var nodes []node
		for _, n := range collectNodes("--all") {
			if n.chain == chain {
				nodes = append(nodes, n)
			}
		}
		refs := chainRefs(chain)
		for _, ln := range strings.Fields(git("for-each-ref", "--format=%(refname:short)", retiredPrefix)) {
			short := strings.TrimPrefix(strings.TrimSpace(ln), "gil/retired/")
			if short == chain || strings.HasPrefix(short, chain+"-") {
				refs = append(refs, "gil/retired/"+short)
			}
		}
		if len(nodes) == 0 && len(refs) == 0 {
			die("거부: 체인 \"" + chain + "\" 을 찾지 못했다.")
		}
		return pruneScope{chain: chain, refs: refs, nodes: nodes}
	case 3:
		chain, cycle, step := parts[0], parts[1], parts[2]
		var all, hit []node
		for _, n := range collectNodes("--all") {
			if n.chain == chain && n.cycle == cycle {
				all = append(all, n)
				if n.step == step {
					hit = append(hit, n)
				}
			}
		}
		if len(hit) == 0 {
			die("거부: " + target + " 없음")
		}
		// 잎만 지운다. 중간 노드를 지우면 후손 커밋을 다시 쓰게 되고, 그건 삭제가 아니라
		// **역사 재작성**이다 — gil 이 절대 하지 않아야 할 일.
		for _, n := range all {
			if n.parent == step {
				die("거부: " + target + " 은 잎이 아니다 — 자식(" + n.step + ")이 있다.\n" +
					"  중간 노드를 지우면 후손을 다시 써야 하고, 그건 삭제가 아니라 역사 재작성이다.\n" +
					"  잎부터 지워라(가장 큰 번호부터), 아니면 체인 단위로: gil prune " + chain)
			}
		}
		return pruneScope{chain: chain, cycle: cycle, step: step, nodes: hit, isNode: true}
	}
	die("거부: 대상은 <chain> 또는 <chain>/<cycle>/<step> 꼴이어야 한다 — 받음: " + target)
	return pruneScope{}
}

// pruneReport — 무엇을 잃는지 전부 보고한다. 사람이 승인 버튼을 누르기 전에 읽을 글이다.
func pruneReport(sc pruneScope) []string {
	L := []string{"── 삭제하면 잃는 것 ──"}
	if sc.isNode {
		n := sc.nodes[0]
		L = append(L, "  스텝 "+sc.chain+"/"+sc.cycle+"/"+sc.step+" ["+n.kind+"] "+n.subject)
		L = append(L, "  이 스텝은 잎이다 — 사이클 브랜치를 부모("+orDefault(n.parent, "없음")+")로 되감는다.")
		return L
	}
	cycles := map[string]int{}
	for _, n := range sc.nodes {
		if n.cycle != "" {
			cycles[n.cycle]++
		}
	}
	L = append(L, "  체인 "+sc.chain+" — 사이클 "+itoa(len(cycles))+"개 · 스텝 "+itoa(len(sc.nodes))+"개")
	if p := chainPurpose(sc.chain, "--all"); p != "" {
		L = append(L, "  목적: "+p)
	}
	var names []string
	for c := range cycles {
		names = append(names, c)
	}
	sort.Strings(names)
	for _, c := range names {
		L = append(L, "    ◆ "+c+" (스텝 "+itoa(cycles[c])+")")
	}
	L = append(L, "  ref "+itoa(len(sc.refs))+"개: "+strings.Join(sc.refs, " "))
	return L
}

// tombstone — 지워진 자리에 남는 묘비. 목적·기준·회고·마지막 sha 를 담아 계보가 계속 말하게
// 한다. 묘비 없는 삭제는 없다 — 그게 없으면 gil 이 지운 자리는 git 이 지운 자리와 같다.
func tombstoneText(sc pruneScope, reason, bundle string) string {
	var b strings.Builder
	b.WriteString("# 묘비 — ")
	if sc.isNode {
		b.WriteString(sc.chain + "/" + sc.cycle + "/" + sc.step)
	} else {
		b.WriteString("체인 " + sc.chain)
	}
	b.WriteString("\n\n지워졌다. 이 글은 지워진 자리에 남는 유일한 기록이다.\n\n")
	b.WriteString("## 왜 지웠나\n" + reason + "\n\n")
	if p := chainPurpose(sc.chain, "--all"); p != "" {
		b.WriteString("## 그 체인의 목적\n" + p + "\n\n")
	}
	b.WriteString("## 남긴 것\n")
	for _, n := range sc.nodes {
		line := "- " + n.cycle + "/" + n.step + " [" + n.kind + "] " + n.subject + "  (" + n.sha + ")"
		b.WriteString(line + "\n")
		if n.toward != "" {
			b.WriteString("    회고(목적에 다가선 정도): " + n.toward + "\n")
		}
		if n.nextDesign != "" {
			b.WriteString("    다음 설계: " + n.nextDesign + "\n")
		}
	}
	b.WriteString("\n## 되살리는 법\n")
	if bundle != "" {
		b.WriteString("번들이 남아 있다: `" + bundle + "`\n")
		b.WriteString("    git bundle unbundle " + bundle + "   후 원하는 ref 를 복원한다.\n")
	} else {
		b.WriteString("번들 생성에 실패했다 — 객체가 GC 되면 되살릴 수 없다.\n")
	}
	return b.String()
}

func cmdPrune(args []string) {
	fs := newFlags("gil prune")
	dryRun := fs.boolFlag("dry-run")
	request := fs.boolFlag("request")
	withdraw := fs.boolFlag("withdraw")
	by := fs.str("by", "") // 뷰어가 부르면 "viewer" — 사람이 거둔 것이라 에이전트에게 고지한다
	confirm := fs.str("confirm", "")
	reason := fs.str("reason", "")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil prune <chain>|<chain>/<cycle>/<step> --dry-run     (무엇을 잃는지 먼저 본다)\n" +
			"      gil prune <대상> --request --reason <왜>               (사람 승인을 요청한다 — 뷰어에 카드가 뜬다)\n" +
			"      gil prune <대상> --withdraw --reason <왜>              (요청을 거둔다 — 카드가 사라진다)\n" +
			"      gil prune <대상> --confirm <대상> --reason <왜>        (승인이 있을 때만 실제 삭제)\n" +
			"  삭제는 되돌릴 수 없다. 그래서 셋을 다 요구한다 — 사람의 승인 커밋, CLI 확인 문구, 그리고 묘비.")
	}
	target := pos[0]
	// ── 요청 철회 (이슈 #91) ─────────────────────────────────────────────────────
	// 요청을 올린 순간 빠져나올 수 없으면, 그 문은 문이 아니라 덫이다. 대상 해석(그래프 조회)
	// 보다 먼저 처리한다 — 대상이 이미 사라진 뒤에도 요청은 거둘 수 있어야 하니까.
	if *withdraw {
		if strings.TrimSpace(*reason) == "" {
			die("거부: --withdraw 는 --reason <왜 거두나> 필요 — 철회도 기록이다.")
		}
		switch pruneState(target) {
		case "none":
			die("거부: \"" + target + "\" 에 대한 삭제 요청이 없다 — 거둘 것이 없다.")
		case "pruned":
			die("거부: \"" + target + "\" 은 이미 삭제됐다 — 철회로 되돌릴 수 없다(삭제는 비가역).")
		}
		commit("gil prune-withdraw: "+target,
			"이 삭제 요청을 거둔다.\n\n"+*reason+"\n\n"+
				"아무것도 지워지지 않았다. 요청은 이력에 남고(append-only), 이 커밋이 그 위에\n"+
				"'더 이상 유효하지 않다'는 새 사실을 얹는다 — 뷰어의 승인 카드가 사라진다.",
			append([][2]string{{"Gil-Kind", "prune-withdraw"}, {"Gil-Prune-Target", target},
				{"Gil-Reason", *reason}}, byTrailer(*by)...), true)
		println2("prune-withdraw: " + target + " — 요청을 거뒀다. 뷰어의 승인 카드가 사라진다.")
		println2("  아무것도 지워지지 않았다. 다시 올리려면: gil prune " + target + " --request --reason <왜>")
		return
	}
	sc := resolvePruneTarget(target)
	report := pruneReport(sc)

	if *dryRun || (!*request && strings.TrimSpace(*confirm) == "") {
		// 이 자리가 "사람의 손을 읽는" 자리다 — 아래에서 승인 여부를 그대로 보여준다.
		// 봤으니 도착 고지를 끈다(영원히 뜨는 경고는 안 읽힌다).
		defer markAllPruneActsSeen()
		for _, ln := range report {
			println2(ln)
		}
		println2("")
		if pruneApproved(target) {
			println2("  ✔ 사람의 승인이 있다. 실행하려면 확인 문구까지:")
			println2("      gil prune " + target + " --confirm " + target + " --reason <왜>")
		} else {
			println2("  아직 사람의 승인이 없다. 승인을 요청하라(뷰어에 카드가 뜬다):")
			println2("      gil prune " + target + " --request --reason <왜 지워야 하나>")
		}
		println2("  삭제 대신 폐기를 먼저 생각하라 — 되돌릴 수 있고, 대부분의 정리는 그걸로 끝난다:")
		println2("      gil chain-retire " + sc.chain + " --reason <왜>")
		return
	}

	if *request {
		if strings.TrimSpace(*reason) == "" {
			die("거부: --request 는 --reason <왜 지워야 하나> 필요 — 사람이 읽고 판단할 글이다.")
		}
		body := strings.Join(report, "\n") + "\n\n## 왜 지우자는가\n" + *reason +
			"\n\n사람이 승인해야만 실행된다(뷰어 카드 또는 gil prune-approve). 승인 뒤에도 CLI 확인 문구가 필요하다."
		commit("gil prune-request: "+target, body, [][2]string{
			{"Gil-Kind", "prune-request"}, {"Gil-Prune-Target", target}, {"Gil-Reason", *reason},
		}, true)
		println2("prune-request: " + target + " — 사람의 승인을 기다린다.")
		println2("  뷰어에 승인 카드가 뜬다(🗑 삭제 승인). 사람이 누르기 전엔 아무것도 지워지지 않는다.")
		println2("  마음이 바뀌면 거둘 수 있다: gil prune " + target + " --withdraw --reason <왜>")
		return
	}

	// 실제 삭제 — 조건 셋을 모두 확인한다.
	if strings.TrimSpace(*confirm) != target {
		die("거부: --confirm 문구가 대상과 다르다.\n" +
			"  지우려는 대상 이름을 그대로 타이핑하라: gil prune " + target + " --confirm " + target)
	}
	if !pruneApproved(target) {
		die("거부: 이 삭제에 대한 **사람의 승인**이 없다.\n" +
			"  gil prune " + target + " --request --reason <왜> 로 승인을 요청하고, 사람이 뷰어에서 승인해야 한다.\n" +
			"  (에이전트가 혼자 지울 수 없다 — 이게 이 명령의 유일한 안전장치다.)")
	}
	if strings.TrimSpace(*reason) == "" {
		die("거부: --reason <왜> 필요 — 묘비에 새길 글이다.")
	}
	// (1) 번들 백업 — "지웠지만 되살릴 수 있다"가 기본값이어야 한다.
	bundle := ""
	if dir := strings.TrimSpace(git("rev-parse", "--absolute-git-dir")); dir != "" {
		arc := filepath.Join(dir, "gil", "archive")
		if err := os.MkdirAll(arc, 0o755); err == nil {
			p := filepath.Join(arc, strings.ReplaceAll(target, "/", "-")+".bundle")
			bundleArgs := []string{"bundle", "create", p}
			if sc.isNode {
				bundleArgs = append(bundleArgs, sc.nodes[0].sha)
			} else {
				for _, r := range sc.refs {
					bundleArgs = append(bundleArgs, r)
				}
			}
			if _, err := gitTry(bundleArgs...); err == nil {
				bundle = p
			}
		}
	}
	// (2) 묘비 — 지우기 **전에** 남긴다. 순서가 뒤바뀌면 실패했을 때 아무것도 안 남는다.
	tomb := tombstoneText(sc, *reason, bundle)
	if globalExists() {
		globalWrite("tombstones/"+strings.ReplaceAll(target, "/", "-")+".md", tomb,
			"gil prune: 묘비 — "+target)
	}
	home := homeBranch()
	cur := strings.TrimSpace(git("rev-parse", "--abbrev-ref", "HEAD"))
	if home != "" && cur != home && !sc.isNode {
		git("checkout", "-q", home) // 지울 브랜치 위에서 묘비를 심을 수 없다
	}
	commit("gil prune: "+target+" 삭제", tomb, [][2]string{
		{"Gil-Kind", "prune"}, {"Gil-Prune-Target", target}, {"Gil-Reason", *reason},
	}, true)
	// (3) 삭제.
	if sc.isNode {
		n := sc.nodes[0]
		parentSHA := ""
		for _, m := range collectNodes("--all") {
			if m.chain == sc.chain && m.cycle == sc.cycle && m.step == n.parent {
				parentSHA = m.sha
				break
			}
		}
		if parentSHA == "" {
			die("거부: 부모 커밋을 못 찾았다 — 되감을 자리가 없다. 체인 단위 prune 을 쓰라.")
		}
		for _, r := range chainRefs(sc.chain) {
			if strings.TrimSpace(git("rev-parse", r)) == strings.TrimSpace(git("rev-parse", n.sha)) {
				git("update-ref", "refs/heads/"+r, parentSHA)
				println2("prune: " + target + " 삭제 — " + r + " 를 " + n.parent + "(" + parentSHA + ") 로 되감았다.")
			}
		}
	} else {
		for _, r := range sc.refs {
			ref := "refs/heads/" + r
			if strings.HasPrefix(r, "gil/retired/") {
				ref = "refs/" + r
			}
			git("update-ref", "-d", ref)
		}
		println2("prune: 체인 " + sc.chain + " 삭제 — ref " + itoa(len(sc.refs)) + "개 제거.")
	}
	tombWhere := "커밋"
	if globalExists() {
		tombWhere = "커밋 + refs/gil/global tombstones/"
	}
	println2("  묘비를 남겼다(" + tombWhere + ") — 계보는 여기 무엇이 있었는지 계속 말한다.")
	if bundle != "" {
		println2("  번들: " + bundle + "  (git bundle unbundle 로 되살릴 수 있다)")
	} else {
		println2("  ⚠ 번들 생성 실패 — GC 후에는 되살릴 수 없다.")
	}
	println2("  객체는 아직 남아 있다. 정말 공간에서 지우려면 사람이 실행하라(되돌릴 수 없다):")
	println2("      git reflog expire --expire=now --all && git gc --prune=now")
}

// cmdPruneApprove — 사람의 승인. 뷰어 카드가 이걸 부른다(에이전트가 직접 부르지 말 것).
func cmdPruneApprove(args []string) {
	fs := newFlags("gil prune-approve")
	// --by <출처>: 뷰어가 부르면 "viewer" — **사람이 눌렀다**는 뜻이다. 그 사실이 있어야
	// 다음 접촉 때 에이전트에게 고지할 수 있다(자기가 부른 것까지 자기에게 알리면 소음이다).
	by := fs.str("by", "")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil prune-approve <대상>   (사람의 승인 — 보통 뷰어 카드가 부른다)")
	}
	target := pos[0]
	if !pruneRequested(target) {
		die("거부: \"" + target + "\" 에 대한 삭제 요청이 없다 — 먼저 gil prune " + target + " --request.")
	}
	tr := [][2]string{{"Gil-Kind", "prune-approve"}, {"Gil-Prune-Target", target}}
	if b := strings.TrimSpace(*by); b != "" {
		tr = append(tr, [2]string{"Gil-By", b})
	}
	commit("gil prune-approve: "+target, "사람이 이 삭제를 승인했다.\n\n"+
		"승인만으로는 아무것도 지워지지 않는다 — 실행에는 CLI 확인 문구가 더 필요하다:\n"+
		"    gil prune "+target+" --confirm "+target+" --reason <왜>", tr, true)
	println2("prune-approve: " + target + " — 승인됨. 실행에는 확인 문구가 더 필요하다.")
}

func pruneRequested(target string) bool { return pruneState(target) == "requested" }


