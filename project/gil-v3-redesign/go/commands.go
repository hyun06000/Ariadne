// commands.go — 쓰기 명령 (커밋 노드를 새긴다, 손 커밋의 코드화).
//
// 참조 구현(gil.py)의 cmd_open·cmd_step·cmd_close·cmd_chain·cmd_chain_merge를 옮긴다.
// 진실원은 커밋 그래프 — 모든 위계는 Gil-* 트레일러로, 본문은 커밋 로그로 산다.
package main

import (
	"encoding/json"
	"io"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
)

// 브랜치 네이밍 (D/F 충돌 회피: 슬래시 대신 하이픈). 위상은 git 브랜치, 의미는 트레일러.
//   체인       = <chain>
//   사이클     = <chain>-<cycle>
//   스텝 가지  = <chain>-<cycle>-<to>b<n>  (형제/backtrack 분기 시에만)
func cycleBranch(chain, cycle string) string { return chain + "-" + cycle }
func stepBranch(chain, cycle, to string, n int) string {
	return chain + "-" + cycle + "-" + to + "b" + strconv.Itoa(n)
}

// commit — 현재 HEAD 위에 커밋 하나를 새긴다(브랜치 이동 없음). 참조: _commit.
func commit(subject, body string, trailers [][2]string, allowEmpty bool) {
	commitOn("", "", subject, body, trailers, allowEmpty)
}

// bodyThin — 본문이 보고서라기엔 너무 얇은가. 거부는 안 하고 안내용(경고 톤 결정).
// 여러 줄(3줄+)이거나 어느 정도 분량(150자+)이면 보고서로 본다 — 둘 다 아니면 얇다.
func bodyThin(body string) bool {
	b := strings.TrimSpace(body)
	return len([]rune(b)) < 150 && strings.Count(b, "\n") < 3
}

// reportGuide — gil 출력은 LLM 에게 주는 프롬프트다(상현님). 스텝을 새긴 뒤, 그 스텝 본문이
// 어떤 보고서여야 하는지 강하게 안내한다. 거부하지 않는다 — 다음에 무엇을 담을지 알려줄 뿐.
// thin 이면 "지금 본문이 얇다"고 콕 집는다.
func reportGuide(kind string, thin bool) {
	report := map[string]string{
		"define":     "이 스텝 본문 = 문제 정의 보고서. 담아라: 무엇을 푸는가·입력/출력·평가 지표·데이터 구조·제약.",
		"hypothesis": "이 스텝 본문 = 가설 보고서. 담아라: 세운 가설·그 근거(관찰/데이터)·검증 방법·기대 결과. (필수 플래그: --falsify 반증조건, --falsify-to 반증 시 되돌아갈 define, --plan 가설 전에 고정한 설계 — 몇 개일지 추정 말고 몇 개로 만들지 정하라.)",
		"verify":     "이 스텝 본문 = 검증 보고서. 담아라: 실행한 절차(코드/명령)·측정 수치(표·코드블록)·관찰. (필수 플래그: --verdict supported|refuted — refuted 면 success 불가, fail/backtrack 만. 가설이 심은 반증조건에도 답한다: --falsify-met|--falsify-unmet <무엇을 관측했나> — 충족됐는데 supported 는 거부된다(규칙 17). 고정한 설계가 있으면 --plan-held|--plan-broke 로 그것에도.)",
		"analyze":    "이 스텝 본문 = 분석 보고서. 담아라: 결과 해석·수치 비교·왜 이 판단인가. 다음은 success/fail/pending 종결 스텝.",
		"success":    "이 스텝 본문 = ⭐누적 종합 보고서. 담아라: 문제정의(s1)부터 여기까지 밟아온 지식·검증·수치를 하나로 정리 — 이 사이클이 무엇을 어떻게 풀었는지 이 하나로 다 읽히게. 표·이미지(data URI) 권장.",
		"fail":       "이 스텝 본문 = 벽 보고서(죽은 잎). 담아라: 무엇에 막혔나·왜 실패했나(수치)·되돌아가 무엇을 다르게 할지. 지도로 영원히 남는다.",
		"pending":    "이 스텝 본문 = 사람에게 묻는 보고서. 담아라: 지금까지의 근거·물음의 선택지·각 선택의 得失. 사람이 이것만 보고 승인/기각할 수 있게.",
	}
	g, ok := report[kind]
	if !ok {
		return
	}
	if thin {
		// 안내는 지금 서 있는 표면에 맞아야 한다(온보딩 실측). MCP 로 도는 에이전트에게
		// "stdin 으로 넘겨라"는 존재하지 않는 길이다 — 거기선 body 인자에 그대로 넣는다.
		if mcpMode {
			stderr("  ⚠ 본문이 얇다 — " + kind + " 스텝은 보고서여야 한다. body 인자에 보고서를 통째로 넣어라")
			stderr("      (툴 인자라 길이 제한이 없다 — 임시 .md 파일을 만들 필요도 없다).")
		} else {
			stderr("  ⚠ 본문이 얇다 — " + kind + " 스텝은 보고서여야 한다. 임시 .md 파일 만들지 말고 stdin 으로 바로 넘겨라:")
			stderr("      gil step … --body-file - <<'EOF'  …보고서…  EOF   (또는 파이프)")
		}
		stderr("    스텝 본문은 커밋이라 나중에 못 고친다(append-only) — 지금 이 스텝을 만들 때 채워라. 얇게 두면 얇은 채로 영원히 남는다.")
	}
	stderr("  ▸ " + g)
	stderr("    (뷰어가 이 본문을 마크다운으로 렌더한다 — 표·코드블록·이미지 ![](data:...) 가능.)")
}

// guideNext — 방금 새긴 스텝(kind)의 '다음에 반드시 올 스텝'을 무조건 출력한다(AIL #41,
// 상현님). 순서 체인(define→hypothesis→verify→analyze→종결)을 매 스텝마다 경고로 각인해,
// 사람도 AI도 다음 강제를 잊고 새지 않게 한다. reportGuide 가 '이 스텝 본문'을 안내한다면
// guideNext 는 '다음 스텝 kind'를 강제로 못박는다.
func guideNext(kind string) {
	switch kind {
	case "define":
		stderr("  ⟹ 다음은 반드시 hypothesis — 무엇을 세우고 무엇이 관측되면 틀리나(--falsify), 그리고 이번에 무엇을 몇 개 만들 것인가(--plan, 이슈 #76). 문제 정의만 하고 실험으로 새지 마라(AIL #41).")
	case "hypothesis":
		stderr("  ⟹ 다음은 반드시 verify — 이 가설을 실측으로 검증하라(--verdict supported|refuted). 고정한 설계에도 답하라(--plan-held|--plan-broke).")
	case "verify":
		stderr("  ⟹ 다음은 반드시 analyze — 검증 결과가 무엇을 뜻하는지 해석하라(그다음이 종결).")
	case "analyze":
		stderr("  ⟹ 다음은 종결 — success(산 잎)/fail(죽은 잎)/pending(사람 대기). 또는 backtrack(hypothesis --to <조상 define>), 문제 정의가 틀렸으면 새 사이클 open.")
		// 갈래를 1급으로 노출한다(이슈 #106·#107). 옛 안내는 매 스텝 "다음은 반드시 하나"로
		// 끝나 **다음 행동은 항상 한 개**라는 리듬을 각인했다 — 실사용 7사이클·스텝 90여 개
		// 동안 병렬 가지가 0회였던 이유다. 도구가 "일자로 흐른다"고 경고하면서 정작 일자를
		// 벗어나는 문장을 화면에 한 번도 안 띄웠다.
		stderr("  ⟹ 이 분석이 선택지를 여럿 내놓았다면 **사람에게 하나를 고르게 하지 말고 다 밟아라** — 형제 가설을 동시에:")
		stderr("       gil step <chain>/<cycle> --kind hypothesis --to <이 analyze> --competing …   (선택지마다 반복)")
		stderr("     경합은 위반이 아니다(선언하면 fsck 가 짚지 않는다). 대신 닫을 때 갈래마다 종결이 필요하다.")
		stderr("     병렬이 잡는 것은 속도가 아니라 **측정의 신뢰성**이다 — 대조군 없이 1표본으로 세운 기준선이 뒤집힌 실사례가 있다(#107).")
	case "fail":
		// fail 은 이 가설의 죽음이지 사이클의 죽음이 아니다(이슈 #45). success 처럼 다음-행동을
		// 명시해, fail 을 '사이클 끝'으로 오인하고 미해결 define 을 방치한 채 새 사이클로 도망치는
		// 걸 막는다. 두 정직한 길만 있다 — 재분기(답을 계속 푼다) 또는 포기(막다른 길로 봉인).
		stderr("  ⟹ fail 은 이 가설의 죽음이지 사이클의 죽음이 아니다. define 의 답을 아직 못 얻었다. 두 길뿐:")
		stderr("     (1) 재분기 — gil step <chain>/<cycle> --kind hypothesis --to <조상 define> --inherit <교훈>  (새 가설로 다시 푼다)")
		stderr("     (2) 포기 — gil close <chain>/<cycle> --abandon  (이 define 이 막다른 길로 확인됐다 — 죽은 사이클로 봉인)")
		stderr("     ⚠ 재분기도 포기도 없이 새 사이클을 open 하지 마라 — 이 define 이 미해결로 방치되고 계보가 끊긴다(이슈 #45).")
	case "pending":
		stderr("  ⟹ 다음은 사람뿐 — gil approve(승인) | gil reject --to <조상 define>(기각). 이 사이클은 사람의 답 전엔 못 이어간다(AIL #41).")
	}
}

// commitOn — 지정한 브랜치 위에 커밋한다. 분기는 진짜 git 브랜치로(상현님, SPEC 원칙 3).
//   branch=="" : 현재 HEAD 에 커밋(브랜치 이동 없음).
//   createFrom!="" : createFrom 커밋/브랜치에서 새 브랜치 branch 를 파고(checkout -b) 커밋.
//   createFrom=="" && branch!="" : 기존 브랜치 branch 로 checkout 후 커밋(이어가기).
// git 브랜치가 위상의 진실원, Gil-* 트레일러가 의미의 진실원 — 한 커밋에 둘 다 실린다.
func commitOn(branch, createFrom, subject, body string, trailers [][2]string, allowEmpty bool) {
	if branch != "" {
		if createFrom != "" {
			if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+branch) {
				die("거부: 브랜치 " + branch + " 이미 있음 (분기 지점 중복)")
			}
			// 커밋이 하나도 없는 빈 저장소면 HEAD(createFrom)가 없다 — 시작점 없이 브랜치만 만든다.
			if gitOK("rev-parse", "--verify", "-q", createFrom) {
				git("checkout", "-q", "-b", branch, createFrom)
			} else {
				git("checkout", "-q", "-b", branch)
			}
		} else if cur, _ := gitTry("rev-parse", "--abbrev-ref", "HEAD"); strings.TrimSpace(cur) != branch {
			git("checkout", "-q", branch)
		}
	}
	defer anchorHead()            // 새긴 커밋을 브랜치 없는 자리에 두지 않는다(이슈 #83)
	defer invalidateGraphNodes() // 커밋했으니 읽어 둔 그래프는 낡았다(캐시 무효화)
	msg := subject + "\n\n" + strings.TrimRight(body, "\n \t") + "\n\n"
	var trs []string
	for _, t := range trailers {
		trs = append(trs, t[0]+": "+foldTrailerValue(t[1]))
	}
	msg += strings.Join(trs, "\n")
	args := []string{"commit", "-q", "-F", "-"}
	if allowEmpty {
		args = append(args, "--allow-empty")
	}
	gitInput(msg, args...)
}

// currentCycle — 이 (chain,cycle)의 스텝들. collectNodes는 새→old 순.
//
// 범위가 HEAD 인 데는 이유가 있다: 한 사이클이 backtrack 으로 갈라지면 죽은 형제 가지와 산
// 가지가 함께 존재하는데, 이어붙일 팁은 **지금 밟고 있는 가지**의 것이어야 한다. 전체 그래프를
// 섞으면 죽은 가지의 커밋이 팁으로 잡혀 순서 강제·종결 판정이 어긋난다.
func currentCycle(chain, cycle string) []node {
	var out []node
	for _, n := range collectNodes("HEAD") {
		if n.chain == chain && n.cycle == cycle {
			out = append(out, n)
		}
	}
	return out
}

// cycleAnywhere — 이 사이클이 **그래프 어딘가에** 있나(브랜치 전체). 존재 확인 전용.
func cycleAnywhere(chain, cycle string) []node {
	var out []node
	for _, n := range collectNodes("--branches") {
		if n.chain == chain && n.cycle == cycle {
			out = append(out, n)
		}
	}
	return out
}

// reachCycle — 대상 사이클로 **찾아가서** 그 가지의 스텝들을 준다(이슈 #44·#47 G6).
//
// HEAD 계보만 보던 시절엔 다른 브랜치에 서 있으면 멀쩡히 존재하는 사이클을 "없음"으로
// 거부했다 — 재분기하고 싶어도 도구가 막는 최악의 형태다(실측: main 에 서서
// gil step b/c001 → "b/c001 없음"). 사이클은 진짜 커밋 그래프에 있는 것이지 지금 무엇을
// 체크아웃했는지에 달린 게 아니다.
//
// **찾기와 이어붙이기는 다른 일이다.** 존재는 그래프 전체에서 찾고, 찾았으면 HEAD 를 그
// 사이클의 팁으로 옮긴 뒤 다시 HEAD 기준으로 읽는다 — 그래야 죽은 형제 가지가 팁 계산에
// 섞이지 않는다.
func reachCycle(chain, cycle, ref string) []node {
	if steps := currentCycle(chain, cycle); len(steps) > 0 {
		return steps // 이미 그 가지 위에 있다
	}
	all := cycleAnywhere(chain, cycle)
	if len(all) == 0 {
		return nil // 정말 없다 — 호출부가 "먼저 gil open" 으로 거부한다
	}
	alignHeadToTip(all[0].sha, ref) // all[0] = 가장 최근 커밋 = 마지막으로 작업하던 가지
	return currentCycle(chain, cycle)
}

// alignHeadToTip — 선형 append(step/reject/approve)가 대상 사이클의 팁 커밋 위에 얹히도록
// HEAD 를 그 팁으로 맞춘다(이슈 #44). gil step/approve/reject 는 현재 HEAD 브랜치에 커밋하는데,
// 여러 사이클을 병렬로 열고 다른 사이클 브랜치가 체크아웃된 상태에서 대상 사이클을 조작하면,
// 종결 커밋이 엉뚱한 브랜치 팁에 얹혀 대상 사이클 팁은 안 움직이고 pending 도 안 풀린다(교착).
// HEAD 가 이미 팁이면 아무것도 안 한다. 아니면 그 팁을 가리키는 브랜치가 있으면 그 브랜치로,
// 없으면 팁 커밋으로 분리(detached) 체크아웃한다 — 어느 쪽이든 커밋이 옳은 계보에 이어진다.
func alignHeadToTip(tipSHA, ref string) {
	if tipSHA == "" {
		return
	}
	head := strings.TrimSpace(git("rev-parse", "HEAD"))
	if strings.HasPrefix(head, tipSHA) || head == tipSHA {
		return // 이미 팁 위 — 정합
	}
	// 팁 커밋을 정확히 가리키는 로컬 브랜치가 있으면 그 브랜치로 옮겨탄다(브랜치 포인터도 함께
	// 전진하도록).
	refs := strings.TrimSpace(git("for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads/"))
	for _, ln := range strings.Split(refs, "\n") {
		name, sha, ok := strings.Cut(strings.TrimSpace(ln), " ")
		if ok && strings.HasPrefix(strings.TrimSpace(sha), tipSHA) {
			git("checkout", "-q", strings.TrimSpace(name))
			stderr("  ▸ HEAD 를 " + ref + " 의 팁(" + tipSHA + ")으로 옮겼다 — 종결 커밋이 옳은 사이클 계보에 얹히도록(이슈 #44).")
			return
		}
	}
	// 팁 위에 **gil 이 만들지 않은 평범한 커밋**이 얹혀 있는 브랜치가 있으면 그 브랜치로
	// 간다(이슈 #74). 옛 코드는 여기서 팁 커밋으로 분리(detached) 체크아웃하고 성공한 척했다 —
	// 새 스텝이 브랜치 밖으로 떨어져, 다음 checkout 한 번에 통째로 사라진다(실사용 사본에서
	// 재현). 평범한 커밋은 정당한 작업이다: 그 위에 이어 붙이면 문서도 스텝도 안 잃는다.
	if br, extra := branchAbove(tipSHA); br != "" {
		git("checkout", "-q", br)
		stderr("  ▸ 브랜치 " + br + " 의 팁이 gil 커밋이 아니다(평범한 커밋 " + itoa(extra) +
			"개가 얹혀 있다) — 그 위에 이어 붙인다. 브랜치는 그대로 전진한다.")
		return
	}
	// 붙일 브랜치가 없다 — 분리 체크아웃하되 **조용히 넘어가지 않는다**(#59·#60 과 같은 축).
	git("checkout", "-q", tipSHA)
	stderr("  ⚠ 붙일 브랜치가 없어 HEAD 를 팁(" + tipSHA + ")으로 분리 체크아웃했다.")
	stderr("    커밋 뒤에는 gil 이 다시 브랜치에 닻을 내린다 — 스텝이 ref 밖에 남지 않는다(이슈 #83).")
}

// anchorHead — 방금 새긴 커밋이 **어떤 브랜치에서도 안 닿는 자리**에 남지 않게 한다(이슈 #83).
//
// 왜 필요한가. gil step/approve/reject 는 현재 HEAD 위에 커밋한다. HEAD 가 한 번 분리되면
// (alignHeadToTip 의 마지막 수단·gil goto·사람의 git checkout <sha>) 그 뒤 모든 선형 스텝은
// 분리된 HEAD 위에 쌓인다 — 팁이 곧 HEAD 라 정합 로직도 "이미 팁"이라며 통과시킨다. 결과는
// 두 겹의 피해였다: (1) 어떤 ref 도 전진하지 않으니 `gil close` 는 성공하고 `gil open --parent`
// 는 "안 닫혔다"고 한다 — 같은 저장소를 보고 두 명령이 다른 답을 한다. (2) 종결 스텝이
// GC 대상이 된다 — 사고를 지우지 않는 것이 존재 이유인 도구에서 가장 나쁜 손실.
//
// 그래서 커밋 직후 여기서 닻을 내린다. 사이클 브랜치가 없으면 만들고, 있고 **조상이면**
// 앞으로 감는다(빨리감기라 잃는 커밋이 없다). 조상이 아니면 — 다른 가지 위에 서 있다는
// 뜻이니 강제로 덮지 않고 옆에 새 가지를 판다. 어느 쪽이든 HEAD 는 브랜치 위에서 끝난다.
func anchorHead() {
	if _, err := gitTry("symbolic-ref", "-q", "HEAD"); err == nil {
		return // 브랜치 위 — 이미 닿는다
	}
	head := strings.TrimSpace(git("rev-parse", "HEAD"))
	if head == "" {
		return
	}
	fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Cycle")
	ch, cy, _ := cut(strings.TrimSpace(gitlog("-1", "--format="+fmtStr, head, "--")), fsep)
	chain, cycle := strings.TrimSpace(ch), strings.TrimSpace(cy)
	if chain == "" {
		// gil 의 체인/사이클 커밋이 아니다(예: 대문). 함부로 브랜치를 만들지 않고 사실만 말한다.
		stderr("  ⚠ HEAD 가 브랜치를 떠나 있다(detached) — 이 커밋은 어느 브랜치에도 없다.")
		stderr("    남기려면: git branch <이름>")
		return
	}
	base := chain
	if cycle != "" {
		base = cycleBranch(chain, cycle)
	}
	name, how := base, "새로 판다"
	switch {
	case !gitOK("rev-parse", "--verify", "-q", "refs/heads/"+base):
		git("branch", base, head)
	case gitOK("merge-base", "--is-ancestor", "refs/heads/"+base, head):
		git("branch", "-f", base, head)
		how = "빨리감기"
	default:
		// 사이클 브랜치가 다른 가지에 있다 — 덮으면 그쪽을 잃는다. 옆에 판다.
		for i := 2; ; i++ {
			name = base + "-d" + itoa(i)
			if !gitOK("rev-parse", "--verify", "-q", "refs/heads/"+name) {
				break
			}
		}
		git("branch", name, head)
		how = "새 가지(사이클 브랜치는 다른 가지에 있어 덮지 않았다)"
	}
	git("checkout", "-q", name)
	stderr("  ▸ HEAD 가 브랜치 밖(detached)이라 " + name + " 에 닻을 내렸다 — " + how + " (이슈 #83).")
	stderr("    이 커밋들은 이제 ref 에서 닿는다(GC 대상 아님). HEAD 는 " + name + " 위에 있다.")
}

// branchAbove — tipSHA 를 조상으로 갖고, 그 사이가 **전부 gil 이 아닌 평범한 커밋**인 로컬
// 브랜치(이슈 #74). 반환: 브랜치 이름과 얹힌 평범 커밋 수. 없으면 ("", 0).
//
// 사이에 gil 스텝이 끼어 있으면 고르지 않는다 — 그건 "평범한 커밋이 얹혔다"가 아니라 계산한
// 팁이 틀렸다는 뜻이고, 그 위에 얹으면 계보를 더 헝클어뜨린다.
func branchAbove(tipSHA string) (string, int) {
	cur := strings.TrimSpace(git("rev-parse", "--abbrev-ref", "HEAD"))
	var names []string
	for _, ln := range strings.Split(strings.TrimSpace(git("for-each-ref", "--format=%(refname:short)", "refs/heads/")), "\n") {
		if n := strings.TrimSpace(ln); n != "" {
			names = append(names, n)
		}
	}
	// 지금 서 있는 브랜치를 먼저 본다 — 사용자가 방금 커밋한 그 자리가 가장 자연스럽다.
	sort.SliceStable(names, func(i, j int) bool { return names[i] == cur && names[j] != cur })
	for _, name := range names {
		if !gitOK("merge-base", "--is-ancestor", tipSHA, name) {
			continue
		}
		out, err := gitTry("log", "--format=%H"+fsep+trailer("Gil-Step"), tipSHA+".."+name, "--")
		if err != nil {
			continue
		}
		extra, gil := 0, false
		for _, rec := range strings.Split(strings.TrimSpace(out), "\n") {
			if strings.TrimSpace(rec) == "" {
				continue
			}
			_, step, _ := strings.Cut(rec, fsep)
			if strings.TrimSpace(step) != "" {
				gil = true
				break
			}
			extra++
		}
		if gil || extra == 0 {
			continue
		}
		return name, extra
	}
	return "", 0
}

// nextStepID — 참조: _next_step_id.
func nextStepID(steps []node) string {
	max := 0
	for _, s := range steps {
		if len(s.step) > 1 {
			if n, err := strconv.Atoi(s.step[1:]); err == nil && n > max {
				max = n
			}
		}
	}
	return "s" + strconv.Itoa(max+1)
}

// growingTip — 가장 최근 스텝(팁). 참조: _growing_tip. collectNodes는 새→old 순이므로 [0].
func growingTip(steps []node) *node {
	if len(steps) == 0 {
		return nil
	}
	return &steps[0]
}

// lineageOf — 사이클 안에서 tipID 스텝부터 Gil-Parent 를 따라 조상으로 거슬러 이 가지의
// 스텝들을 모은다(AIL #41). 순서 강제로 verify→analyze→종결이 되면서, refuted/극성 success
// 가드가 '직전 verify' 가 아니라 '이 가지 계보에 그 판정이 있나'를 봐야 해서 필요해졌다.
// currentAttempt — 이 가지의 **지금 시도**만 잘라낸다(이슈 #78 곁다리).
//
// 왜. #32·#60 이후 새 가설은 조상 analyze 에 뿌리내릴 수 있다. 그런데 종결 가드는 계보를
// 끝까지 거슬러 올라가 거기서 만난 refuted verify 로 후손 전체를 막았다 — 그 verify 는
// **이 가지의 것이 아니다.** 실사용 보고: 자기 verify(s43)는 supported 인데 죽은 가지의
// s3(refuted) 때문에 success 가 거부됐다. 뿌리내린 analyze 위쪽은 앞 시도의 몫이다.
//
// 경계는 **가장 가까운 hypothesis** 다: 한 시도는 가설에서 시작해 verify·analyze 를 거쳐
// 종결로 끝난다. 그 가설보다 위는 이 주장의 근거가 아니라 이 주장이 딛고 선 땅이다.
func currentAttempt(steps []node, tipID string) []node {
	lin := lineageOf(steps, tipID) // tip → 조상 순
	for i, n := range lin {
		if n.kind == "hypothesis" {
			return lin[:i+1]
		}
	}
	return lin
}

func lineageOf(steps []node, tipID string) []node {
	byID := map[string]node{}
	for _, s := range steps {
		byID[s.step] = s
	}
	var out []node
	cur := tipID
	for i := 0; i < 1000; i++ {
		n, ok := byID[cur]
		if !ok {
			break
		}
		out = append(out, n)
		if n.parent == "" || n.parent == "null" || n.parent == cur {
			break
		}
		cur = n.parent
	}
	return out
}

// countClaims — --falsify 가 몇 개의 주장으로 열거됐나(AIL #1 A). 개행/세미콜론을 명백한
// 열거 구분자로 본다(한 문장의 쉼표·구두점은 오탐 않도록 제외). 비어있지 않은 조각 수를
// 센다 — 2 이상이면 복합가설로 보고 형제 hypothesis 로 갈라내게 거부한다.
func countClaims(falsify string) int {
	segs := strings.FieldsFunc(falsify, func(r rune) bool { return r == '\n' || r == ';' || r == '；' })
	n := 0
	for _, s := range segs {
		if strings.TrimSpace(s) != "" {
			n++
		}
	}
	if n == 0 {
		return 1 // 구분자만 있거나 공백 — 상위에서 falsify=="" 는 이미 걸렀으니 단일로 본다
	}
	return n
}

// guideRefutes — 소급 반증(--refutes) 안내(AIL #1 B). 강제하지 않고, 반증된 verify 가
// 딛고 있던 hypothesis 의 falsify 조건을 되짚어 준다: 소급 반증은 "그때 세운 반증조건이
// 뒤늦게 충족됐다"로 계보에 남을 때 가장 정직하다(falsify 가 미래 반증의 앵커). 대상 verify
// 의 직전 hypothesis 형제에서 Gil-Falsify 를 찾아 보여 준다.
func guideRefutes(targets []string) {
	all := collectNodes("--branches")
	byKey := map[string]node{}
	for _, n := range all {
		byKey[stepKey(n.chain, n.cycle, n.step)] = n
	}
	for _, t := range targets {
		stderr("  ▸ 소급 반증(--refutes " + t + "): 이 사이클이 앞서 닫힌 supported 판정을 뒤집는다.")
		parts := strings.Split(t, "/")
		if len(parts) == 3 {
			// 같은 사이클에서 falsify 를 심은 hypothesis 를 찾아, 그 반증조건을 앵커로 제시.
			var fals []string
			for _, n := range all {
				if n.chain == parts[0] && n.cycle == parts[1] && n.kind == "hypothesis" && n.falsify != "" {
					fals = append(fals, n.falsify)
				}
			}
			if len(fals) > 0 {
				stderr("    앵커: 그 판정이 딛은 가설의 반증조건이 뒤늦게 관측된 것인가? 본문에 적어라:")
				for _, f := range fals {
					stderr("      · " + f)
				}
			}
		}
		stderr("    (verdict 는 불변 보존 — 뒤집지 않는다. 새 진실은 이 사이클에 산다. 뷰어가 그 판정에 ⚠refuted-by 를 붙인다.)")
		stderr("    --inherit 는 여기선 '물려받음'이 아니라 '뒤집음' — 무엇을 뒤집고(그 판정) 무엇은 계승하나(구현 등)를 담아라(AIL #3).")
	}
}

// resolveRefutes — --refutes <chain>/<cycle>/<step> 소급 반증 간선의 무결성을 검증한다
// (AIL #1 제안 B). 후속 사이클/스텝이 앞서 닫힌 supported verify 판정을 뒤늦게 반증했음을
// 계보에 forward-pointing 간선으로 남긴다 — verdict 를 뒤집지(supersede) 않고, 과거는
// 불변 보존하되 새 간선으로 재조명한다("새 진실은 앞에 산다"). 대상은 반드시:
//   (a) 실재하는 스텝, (b) 그 사이클이 close 로 봉인됨, (c) kind==verify, (d) verdict==supported.
// (fail/refuted 를 반증하는 건 무의미하므로 supported 만 대상.)
func resolveRefutes(targets []string) {
	if len(targets) == 0 {
		return
	}
	all := collectNodes("--branches")
	byKey := map[string]node{}
	for _, n := range all {
		byKey[stepKey(n.chain, n.cycle, n.step)] = n
	}
	closed := closedCycles("--branches")
	for _, t := range targets {
		parts := strings.Split(t, "/")
		if len(parts) != 3 {
			die("거부: --refutes 대상 \"" + t + "\"는 <chain>/<cycle>/<step> 꼴이어야 함 (스텝 단위)")
		}
		tc, tcy, ts := parts[0], parts[1], parts[2]
		n, ok := byKey[stepKey(tc, tcy, ts)]
		if !ok {
			die("거부: --refutes 대상 " + t + " 실재 안 함 (dangling)")
		}
		if !closed[tc+"\x01"+tcy] {
			die("거부: --refutes 대상 " + t + "의 사이클이 아직 안 닫혔다 — 소급 반증은 닫힌 판정만 대상 " +
				"(열린 사이클은 backtrack/fail 로 그 자리에서 되돌려라)")
		}
		if n.kind != "verify" {
			die("거부: --refutes 대상 " + t + "는 verify 스텝이어야 함 (반증되는 건 판정이다). 현재 kind=" + n.kind)
		}
		if n.verdict != "supported" {
			die("거부: --refutes 대상 " + t + "의 verdict 가 supported 가 아니다(현재 \"" + n.verdict +
				"\") — 반증할 지지 판정이 없다")
		}
	}
}

// resolveRefines — --refines <chain>/<cycle>/<step> 약한 정정 간선의 무결성을 검증한다(이슈 #42).
//
// 왜 refutes 로는 안 되나. 정직한 탐구는 원인을 점층적으로 좁힌다("언어 공백 같다" → "아니
// 문서였다"). 이때 앞 verify 는 **가설도 실험도 맞았고 verdict 도 옳다** — 불완전했던 건 그
// 본문의 *원인 해석*뿐이다. 여기에 refutes 를 걸면 "그 사이클이 틀렸다"고 과하게 말해 유효한
// 성과까지 부정하고, inherit 로만 두면 정정 관계가 그래프에서 사라진다. 그래서 그 사이를 낸다:
// **대상의 verdict 는 불변, 해석만 정밀화한다.** refutes 가 극성 전환이면 refines 는 해석 심화다.
//
// 대상은 반드시 (a) 실재하는 스텝, (b) 그 사이클이 close 로 봉인됨, (c) kind 가 verify 또는
// analyze — 해석을 담는 노드. verdict 는 묻지 않는다(supported 든 refuted 든 해석은 정밀화된다).
func resolveRefines(targets []string) {
	if len(targets) == 0 {
		return
	}
	all := collectNodes("--branches")
	byKey := map[string]node{}
	for _, n := range all {
		byKey[stepKey(n.chain, n.cycle, n.step)] = n
	}
	closed := closedCycles("--branches")
	for _, t := range targets {
		parts := strings.Split(t, "/")
		if len(parts) != 3 {
			die("거부: --refines 대상 \"" + t + "\"는 <chain>/<cycle>/<step> 꼴이어야 함 (스텝 단위)")
		}
		tc, tcy, ts := parts[0], parts[1], parts[2]
		n, ok := byKey[stepKey(tc, tcy, ts)]
		if !ok {
			die("거부: --refines 대상 " + t + " 실재 안 함 (dangling)")
		}
		if !closed[tc+"\x01"+tcy] {
			die("거부: --refines 대상 " + t + "의 사이클이 아직 안 닫혔다 — 정밀화는 닫힌 해석만 대상\n" +
				"  (열린 사이클 안에서는 --supersede 로 그 자리에서 정정하라)")
		}
		if n.kind != "verify" && n.kind != "analyze" {
			die("거부: --refines 대상 " + t + "는 verify 또는 analyze 스텝이어야 함 (정밀화되는 건 해석이다). " +
				"현재 kind=" + n.kind + "\n" +
				"  판정 자체를 뒤집는 것이면 --refines 가 아니라 --refutes 다.")
		}
	}
}

// guideRefines — 정밀화 간선을 놓은 뒤, 그 관계가 무엇을 뜻하는지 못박는다. refines 를
// "약한 refutes" 로 오용하면(실은 판정이 틀렸는데 정밀화라 적으면) 정직화 장치가 무뎌진다.
func guideRefines(targets []string) {
	stderr("")
	for _, t := range targets {
		stderr("  ▸ 정밀화(--refines " + t + "): 그 판정(verdict)은 그대로 선다 — 이 사이클은 그 본문의")
		stderr("    *원인 해석*을 더 좁힌다. 앞 사이클의 성과를 부정하는 게 아니다.")
	}
	stderr("    (판정 자체가 틀렸다면 정밀화가 아니라 소급 반증이다: --refutes <c>/<cy>/<step>)")
	stderr("    본문에 적어라: 앞선 해석이 어디까지 맞았고, 무엇이 진짜 원인이었나.")
}

// ── gil open ──
func cmdOpen(args []string) {
	fs := newFlags("gil open")
	author := fs.str("author", "")
	title := fs.str("title", "")
	purpose := fs.str("purpose", "")
	// --from-plan <n>: 심층 인터뷰가 낳은 **사이클 분할**에서 n번째 문제를 이 사이클의
	// 목적으로 들어 올린다(상현님). 사람이 나눈 작은 문제들로 사이클을 정복하게 하는 자리 —
	// 여기서도 인용이지 창작이 아니다.
	fromPlan := fs.str("from-plan", "")
	bodyF := fs.str("body", "")
	bodyFile := fs.str("body-file", "")
	parents := fs.strList("parent")
	refutes := fs.strList("refutes") // 소급 반증 간선(AIL #1 제안 B): 이 사이클이 뒤집는 앞 verify 스텝
	refines := fs.strList("refines") // 약한 정정 간선(이슈 #42): 판정은 두고 해석만 정밀화
	// --goal (이슈 #62 제안 1): 이 사이클이 **무엇을 만족하면 끝인가**. purpose 가 "무엇을
	// 하려는가"라면 goal 은 "무엇이 되면 됐다고 할 것인가"다 — 둘은 다르다. 옛 도구는 잎이
	// 다 종결되면 사이클을 사실상 끝난 것으로 읽었는데, "잎이 다 종결됐다"는 "목표가
	// 달성됐다"와 다르다(갭 11개 중 3개만 닫힌 사이클이 실제 사례). close 가 verdict 를
	// 받으니 열 때 목표를 받는 건 대칭이고, 그래야 닫는 판단이 자기확신이 아니라 선언에 매인다.
	goal := fs.str("goal", "")
	// --parallel <사이클> (이슈 #45): 미해결 사이클을 **알면서** 나란히 연다는 선언. 거부의
	// 유일한 통로이고, 통과하면 Gil-Parallel-With 로 그래프에 남는다 — 조용한 우회가 아니라
	// 기록되는 판단이 되게.
	parallel := fs.strList("parallel")
	inherit := fs.str("inherit", "") // 물려받은 지식·전제·교훈(AIL #3): 계보 간선 생기면 필수
	// 이 사이클이 이 체인의 것인가 — 여는 자리에서 체인 목적과 대면시킨다(상현님).
	// --fits: 그렇다(어떻게 기여하는가) · --misfit: 아니다(왜 여기가 아닌가 → 기억에 남기고 안 연다).
	fits := fs.str("fits", "")
	misfit := fs.str("misfit", "")
	// 측정의 좌표(이슈 #79·#81): --dataset = 어디서 쟀나, --subject = 무엇을 쟀나.
	// 산문이 아니라 필드라야 기계가 대조한다. 여러 축이면 여러 번.
	datasets := fs.strList("dataset")
	datasetNote := fs.str("dataset-note", "")
	subjects := fs.strList("subject")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil open <chain>/<cycle> [--author <who>] (--purpose <P> | --from-plan <n>) [--parent <cyc>...] [--refutes <c>/<cy>/<step>...] [--refines <c>/<cy>/<step>...] [--goal <달성 기준>] [--inherit <전수>] [--title T] [--body B | --body-file F|-]")
	}
	if *author == "" {
		// 저장소에 사는 존재가 하나뿐이면 그게 너다 — 자기 이름을 매번 다시 타이핑할 이유가
		// 없다. (문서에 예시 이름을 적게 만드는 것도 이 요구였다: 예시는 정답으로 읽힌다.)
		if ns := existenceNames(); len(ns) == 1 {
			*author = ns[0]
		} else if len(ns) > 1 {
			die("거부: 이 저장소엔 존재가 여럿이다 — 누가 여는 사이클인지 밝혀라:\n" +
				"    --author <" + strings.Join(ns, "|") + ">")
		} else {
			die("거부: --author 필요 — 이 저장소엔 존재의 방이 없다(gil init 이 세운다).")
		}
	}
	ref := pos[0]
	if !strings.Contains(ref, "/") {
		die("거부: <chain>/<cycle> 꼴이어야 함")
	}
	chain, cycle, _ := cut(ref, "/")
	if fp := atoiSafe(strings.TrimSpace(*fromPlan)); fp > 0 {
		items := chainPlanItems(chain)
		if len(items) == 0 {
			die("거부: 체인 \"" + chain + "\" 에 사이클 분할이 없다 — --from-plan 으로 고를 것이 없다.\n" +
				"  분할은 개시 인터뷰에서 사람이 나눈다:\n" +
				"    gil intake <슬러그> --ask '[{\"q\":\"이 문제를 사이클 단위 작은 문제로 나눈다면 어떻게 나누시겠습니까? 한 줄에 하나씩 적어 주세요\",\"type\":\"text\"}]'\n" +
				"    gil chain " + chain + " --from-intake <슬러그> … --cycles-from <질문번호>")
		}
		if fp > len(items) {
			msg := "거부: --from-plan " + itoa(fp) + " — 이 체인의 분할은 " + itoa(len(items)) + "개뿐이다.\n"
			for i, it := range items {
				msg += "  " + itoa(i+1) + ") " + clip(it, 90) + "\n"
			}
			die(strings.TrimRight(msg, "\n"))
		}
		if strings.TrimSpace(*purpose) != "" {
			die("거부: --from-plan 과 --purpose 는 함께 못 선다 — 목적은 사람이 나눈 문제에서 인용된다.")
		}
		*purpose = items[fp-1]
		println2("  ◎ 사이클 목적을 사람의 분할에서 인용했다(" + itoa(fp) + "/" + itoa(len(items)) + "): " + *purpose)
	}
	if *purpose == "" {
		die("거부: --purpose 필요")
	}
	for _, kv := range [][2]string{{"chain", chain}, {"cycle", cycle}} {
		if !idRe.MatchString(kv[1]) {
			die("거부: " + kv[0] + " id \"" + kv[1] + "\"는 소문자·숫자·하이픈만")
		}
	}
	// 측정 좌표(이슈 #79·#81) — 체인이 요구하면 선언 없이는 못 연다. 같은 체인 안에서 축이
	// 바뀌면 막지는 않되 조용히 넘어가지 않는다.
	requireCoords(chain, *datasets, *subjects)
	for _, ln := range coordDriftLines(chain, *datasets, *subjects) {
		stderr(ln)
	}
	// 중복 가드는 **그래프 전체**로 본다 — 다른 브랜치에 이미 있는 사이클 이름을 또 여는
	// 구멍이 있었다(같은 이름 사이클이 둘이면 이후 조회가 어느 쪽인지 모른다).
	if len(cycleAnywhere(chain, cycle)) > 0 {
		die("거부: " + ref + " 이미 존재 (open은 새 사이클만)")
	}
	// 닫힌 부모 체인 사이클 금지 (dev/c002 죽은 잎이 가르친 규칙). --branches 로 본다 — 체인은
	// 닫혔으면 닫힌 것이지 현재 HEAD 위치와 무관하다(chain-close 커밋이 다른 브랜치에 얹혀도
	// 닫힘은 유효). cmdChainClose 도 --branches 로 판정하므로 대칭을 맞춘다.
	if chainClosed(chain, "--branches") {
		why := "닫힌 체인"
		if chainHasChildren(chain, "--all") {
			why = "자식 체인이 분기함"
		}
		die("거부: \"" + chain + "\"은 닫힌 부모 체인(" + why + ") — 그 안에 새 사이클을 열 수 없다. " +
			"새 자식 체인을 열어라 (gil chain <name> --purpose ...). 닫힌 부모에서 다시 자라면 배포 계보가 꼬인다.")
	}
	// ── 인터뷰 pending 잠금 (이슈 #33, 상현님) ──
	// 이 체인에 사람 답을 기다리는 인터뷰가 있으면, 그 답이 오기 전엔 어떤 작업 사이클도 못 연다.
	// LLM 이 인터뷰를 심어 사람에게 물어놓고, 답을 안 기다린 채 스스로 진행하던 것을 문법으로
	// 막는다(실사용 gil-test-2: 인터뷰를 심고도/건너뛰고도 자기가 기준을 정해 사이클을 돌렸다).
	// 뷰어 폼 제출(gil interview --resolve)이 pending 을 done 으로 풀면 그제서야 열린다.
	if chainInterviewPending(chain, "--branches") {
		die("거부: \"" + chain + "\" 에 사람 답 대기 중인 인터뷰가 있다 — 사람이 뷰어 폼으로 답할 때까지\n" +
			"  이 체인에서 작업 사이클을 못 연다(인터뷰=pending 잠금, 이슈 #33). LLM 이 스스로 기준을\n" +
			"  정하지 말고, 사람의 답(레퍼런스 트루스)을 기다려라. 뷰어를 열어 사람에게 폼 작성을 청하라:\n" +
			"    gil viewer serve   (또는 이미 떠 있으면 그 창) → 📋 인터뷰 폼 제출 → 기준 확정 후 자동으로 열린다.")
	}
	// ── 기준(레퍼런스) 필수 (이슈 #33, 상현님) ──
	// 체인을 열면 인터뷰 사이클이 필수로 돌아야 한다 — 기준 문서 없이 작업 사이클을 열 수 없다.
	// 기준은 오직 인터뷰 제출(사람)로만 심긴다. LLM 이 사람에게 묻는 마찰을 회피하고 혼자
	// 진행하는 걸 막는 핵심 하드블록(AIL 세션 clew 자신의 결론: 자기규율은 원리적 불충분,
	// 도구가 레일을 깔아야 신뢰가능하게 교정된다). 첫 스텝은 반드시 gil interview 여야 한다.
	if !chainReferenceApproved(chain, "--branches") {
		die("거부: \"" + chain + "\" 에 사람이 승인한 기준 문서(레퍼런스 트루스)가 없다 — 작업 사이클을\n" +
			"  열기 전에 인터뷰가 먼저다(이슈 #33, 상현님).\n" +
			"  판정 근거는 파일이 아니라 **커밋 트레일러**다 — 이 체인의 chain-root 에\n" +
			"  `Gil-Interview: done` 이 안 보인다(확인: git log -1 " + chain + " --format='%(trailers)').\n" +
			"  (v3.37.0 부터 기준 없는 체인은 애초에 만들어지지 않으니, 방금 만든 체인인데 여기\n" +
			"   걸렸다면 그건 도구의 결함이다 — 그 커밋의 트레일러 블록을 그대로 붙여 이슈로 올려라.)\n" +
			"  지금 채우려면:\n" +
			"    1) 인터뷰 질문을 짜서 심어라: gil interview " + chain + " --ask <질문JSON|->\n" +
			"    2) 사람이 뷰어 폼으로 답하고 제출하면 기준이 확정된다.\n" +
			"    3) 그제서야 gil open " + ref + " 로 작업 사이클을 연다.")
	}
	// ── 이 체인에 열 사이클이 맞나 (상현님) ─────────────────────────────────────
	// 체인의 목적을 **그 자리에서 다시 읽히고**, 이 사이클이 거기 속하는지 한 번 대면시킨다.
	// 옛 흐름은 목적을 화면에 뿌리기만 했다 — 뿌린 글은 읽히지 않아도 통과된다. 답을 문법으로
	// 요구하면 최소한 한 번은 비추어 본다. 아니라고 판단했으면 그건 실패가 아니다:
	// --misfit 로 그 판단을 **기억에 남기고** 제 자리(다음 체인)로 간다.
	if mf := strings.TrimSpace(*misfit); mf != "" {
		crit := strings.TrimSpace(chainTrailer(chain, "Gil-Chain-Criterion"))
		knot := "\n## 열지 않은 사이클 — " + ref + "\n\n" +
			"체인 [" + chain + "] 의 목적에 비추어 보니 이 사이클은 여기 속하지 않는다고 판단했다.\n\n" +
			"- 체인 목적: " + chainPurpose(chain, "--branches") + "\n"
		if crit != "" {
			knot += "- 체인 기준: " + crit + "\n"
		}
		knot += "- 열려던 사이클: " + ref + "\n" +
			"- 왜 여기가 아닌가: " + mf + "\n\n" +
			"이 문제는 사라진 것이 아니라 **제 자리를 기다린다**. 다음에 그 자리를 열 때 여기서 꺼내라.\n"
		// 기억을 남길 존재. 이름을 박아두지 않는다 — 옛 기본값("clew")은 이 저장소에 그런
		// 존재가 없어도 그 이름의 방을 만들어냈다. 이 저장소에 실제로 사는 존재에서 읽는다.
		who := strings.TrimSpace(*author)
		if who == "" {
			if ns := existenceNames(); len(ns) == 1 {
				who = ns[0]
			} else {
				die("거부: 이 판단을 누구의 기억에 남길지 모르겠다 — --author <존재이름>\n" +
					"  이 저장소의 존재: gil global read existence/README.md")
			}
		}
		memoryAppendKnot(who, knot)
		println2("")
		println2("열지 않았다 — 이 사이클은 " + chain + " 의 목적에 속하지 않는다고 판단했다.")
		println2("  그 판단을 기억에 남겼다(existence/" + who + "/memory.md) — 잊혀서 사라지지 않는다.")
		println2("  ▸ 이제 **제 자리를 만들어라.** 그 문제의 주인이 될 체인부터 사람에게 묻는다:")
		println2("      gil intake <슬러그> --ask '[{\"q\":\"무엇을 하려고 하십니까\",\"type\":\"text\"}]'")
		println2("      gil chain <새체인> --from-intake <슬러그> --purpose-from 1 --criterion-from 2")
		println2("  ▸ 다시 꺼내 볼 때: gil memory read " + who)
		return
	}
	if strings.TrimSpace(*fits) == "" {
		crit := strings.TrimSpace(chainTrailer(chain, "Gil-Chain-Criterion"))
		msg := "거부: 이 사이클이 **이 체인의 것인지** 먼저 답하라 — --fits <한 줄>\n\n" +
			"  체인 [" + chain + "] 의 목적:\n    " + chainPurpose(chain, "--branches") + "\n"
		if crit != "" {
			msg += "  이 체인이 풀렸다고 할 기준:\n    " + crit + "\n"
		}
		msg += "\n  열려는 사이클: " + ref + "\n" +
			"    목적: " + strings.TrimSpace(*purpose) + "\n\n" +
			"  진짜로 이 체인에 열 사이클인가?\n" +
			"    ▸ 그렇다  → gil open " + ref + " … --fits \"<이 사이클이 위 목적에 어떻게 기여하는가>\"\n" +
			"    ▸ 아니다  → gil open " + ref + " … --misfit \"<왜 여기가 아닌가>\"\n" +
			"       (열지 않고 그 판단을 기억에 남긴다. 그런 뒤 제 자리가 될 체인을 연다.)\n\n" +
			"  체인은 아무 사이클이나 담는 바구니가 아니다 — 목적 하나에서 뻗은 나무다."
		die(msg)
	}
	// 부모 사이클은 반드시 닫혀 있어야 한다 (상현님 실사용: 열린 사이클이 부모가 되면
	// 배포 계보가 꼬인다). 원칙 — 사이클은 닫힌 사이클의 끝에서만 생성된다. --parent 로
	// 지정된 사이클(들)이 close 커밋을 가졌는지 강제한다. (기록만 하고 강제 안 하던 구멍.)
	closed := closedCycles("--branches")
	for _, par := range *parents {
		if !closed[chain+"\x01"+par] {
			die("거부: 부모 사이클 \"" + par + "\"이 아직 닫히지 않았다 — 사이클은 닫힌 사이클의 " +
				"끝에서만 연다. 먼저 `gil close " + chain + "/" + par + "` 로 닫아라.")
		}
	}
	resolveRefutes(*refutes) // 소급 반증 대상 무결성(AIL #1 B)
	resolveRefines(*refines) // 정밀화 대상 무결성(이슈 #42)
	// 제안 A (AIL #3) — 계보 간선이 새로 생기면 물려받은 지식·전제·교훈을 명시한다. 부모
	// 사이클(--parent)이나 소급 반증(--refutes) 간선이 있으면 --inherit 필수 — 간선의 존재는
	// 문법이, 내용의 진실성은 존재가 보증한다("정직 강제 불가, 은폐 영속화만 차단", AIL #1).
	if (len(*parents) > 0 || len(*refutes) > 0 || len(*refines) > 0) && strings.TrimSpace(*inherit) == "" {
		die("거부: 계보 간선(--parent/--refutes/--refines)이 있으면 --inherit <전수> 필요 — 부모에게서 물려받은 " +
			"사전지식·전제·교훈을 명시하고 출발하라. 계보를 포인터 그물이 아니라 지식의 강으로(AIL #3).")
	}
	// 미해결 define 방치 경고(이슈 #45). 이 체인에 '산 잎 없이 fail 잎만 있고 아직 안 닫힌'
	// 사이클이 있으면, 그 define 은 답을 못 얻은 채 방치된 것이다 — 재분기(hypothesis --to)나
	// 포기(close --abandon) 없이 새 사이클로 도망치면 계보가 끊긴다. 거부는 않는다(병렬 사이클은
	// 정당할 수 있다) — 사람이 보고 판단하도록 경고만 한다.
	// 미해결 define 방치 차단(이슈 #45). 이 체인에 '산 잎 없이 fail 잎만 있고 아직 안 닫힌'
	// 사이클이 있으면, 그 define 은 답을 못 얻은 채 방치된 것이다.
	//
	// 옛 동작은 **경고**였다. 그런데 실측에서 4/4 로 도망갔다 — 경고는 읽히지 않거나 읽혀도
	// 다음 줄에서 잊힌다. HEAAL: 규율은 안내가 아니라 문법의 거부여야 한다. 그래서 거부한다.
	//
	// 다만 병렬 사이클은 정당할 수 있다. 그 길을 막지 않되 **조용히 지나가지도 않게** 한다 —
	// --parallel <사이클> 로 "이 미해결 사이클을 알면서 나란히 연다"를 선언하면 통과하고,
	// 그 선언이 그래프에 남는다(Gil-Parallel-With). 우회가 아니라 기록되는 판단이다.
	// **결핍을 발견하기 전에 말한다**(이슈 #103). 새 사이클은 체인 끝에서 나는데, 앞 사이클이
	// 체인으로 합류하지 않았으면 그 산출물이 이 트리에 없다. 에이전트는 그걸 작업 한복판에서
	// (import 실패 같은 모양으로) 발견하고, 그 자리에서 가장 싼 해결책인 트리 복사를 집는다.
	// 여는 순간에 알려주면 그 자리에서 merge 를 택한다.
	for _, ln := range unmergedSiblingsHint(chain) {
		stderr(ln)
	}
	if stranded := strandedCycles(chain); len(stranded) > 0 {
		declared := map[string]bool{}
		for _, p := range *parallel {
			declared[p] = true
		}
		var undeclared []string
		for _, sc := range stranded {
			if !declared[sc] {
				undeclared = append(undeclared, sc)
			}
		}
		if len(undeclared) > 0 {
			die("거부: 이 체인에 미해결 사이클이 있다(fail 잎만, 미종결): " + strings.Join(undeclared, " ") + "\n" +
				"  그 define 은 답을 못 얻은 채다 — 새 사이클로 넘어가면 계보가 거기서 끊긴다.\n" +
				"  셋 중 하나를 골라라:\n" +
				"    (1) 재분기 — gil step " + chain + "/" + undeclared[0] +
				" --kind hypothesis --to <조상 define|analyze> --inherit <그 벽의 교훈>\n" +
				"        (이 define 의 답을 아직 못 얻었다 — 새 가설로 다시 푼다)\n" +
				"    (2) 포기   — gil close " + chain + "/" + undeclared[0] + " --abandon\n" +
				"        (막다른 길로 확인됐다 — 죽은 사이클로 봉인, 벽의 지도로 남긴다)\n" +
				"    (3) 병렬   — gil open " + ref + " … --parallel " + strings.Join(undeclared, " --parallel ") + "\n" +
				"        (정말 나란히 여는 것이다 — 그 선언이 그래프에 남는다)")
		}
	}
	// 밟다 만 사이클을 두고 다음을 열지 못한다(상현님, 2026-07-28). #45 는 "fail 잎만 남은"
	// 경우만 막았고, 그래서 define·hypothesis·verify·analyze 어디서든 손을 놓고 새 사이클을
	// 열 수 있었다 — 사이클이 종결 잎 없이 허공에 매달린다. 사이클은 success/fail 로 끝나야
	// 끝난 것이다. 여기엔 --parallel 우회를 두지 않는다: 나란히 여는 것과 밟다 만 것은 다르다.
	if inflight, tips := inFlightCycles(chain); len(inflight) > 0 {
		first := inflight[0]
		tip := tips[first]
		nextKind := map[string]string{
			"define":     "hypothesis --falsify <반증조건> --falsify-to <조상 define> --plan <고정할 설계>",
			"hypothesis": "verify --verdict supported|refuted --plan-held|--plan-broke <무엇이 달랐나>",
			"verify":     "analyze",
			"analyze":    "success|fail --to <조상 define|analyze>",
		}[tip.kind]
		lines := []string{"거부: 이 체인에 아직 밟는 중인 사이클이 있다: " + strings.Join(inflight, " "),
			"  " + chain + "/" + first + " 은 " + tip.step + "(" + tip.kind + ")에 서 있다 — 종결 잎(success/fail)이 없다.",
			"  사이클은 success/fail 로 끝나고 close 된 뒤에만 다음이 열린다. 중간에서 손을 놓으면",
			"  그 사이클은 '무슨 생각을 하다 말았는지'를 영영 말하지 못한다."}
		if tip.kind == "pending" {
			lines = append(lines,
				"  이 자리는 사람의 답을 기다린다: gil approve "+chain+"/"+first+
					"  또는  gil reject "+chain+"/"+first+" --to <조상 define|analyze>")
		} else {
			lines = append(lines, "  셋 중 하나를 골라라:",
				"    (1) 이어가기 — gil step "+chain+"/"+first+" --kind "+nextKind,
				"    (2) 종결     — analyze 까지 밟은 뒤 success(산 잎)로 닫고 gil close "+chain+"/"+first,
				"    (3) 포기     — analyze → fail 로 **벽을 남긴 뒤** gil close "+chain+"/"+first+" --abandon",
				"                  (봉인에도 죽은 잎이 필요하다 — 벽의 지도 없이 사라지는 사이클은 없다)")
			// **여기가 갈래를 포기하게 되는 자리다.** 형제를 하나 더 열려던 에이전트는 이
			// 거부를 "분기는 안 되는구나"로 읽고 일자로 이어붙인다(상현님 실사용). 안 되는
			// 것은 **동시에 여는 것**뿐이고, 그건 제약이 아니라 원리다 — git 에서 두 브랜치를
			// 동시에 밟으려면 워크트리가 필요한 것과 같다. 갈래 자체는 얼마든지 낼 수 있다.
			if p := cycleParentOf(chain, first); p != "" {
				lines = append(lines,
					"  ▸ **형제 사이클을 열려던 것이라면 — 그 길은 열려 있다.** 지금 것을 닫은 뒤",
					"    같은 부모로 다시 열면 형제로 갈라진다:",
					"      gil close "+chain+"/"+first+" --verdict <판정>",
					"      gil open "+chain+"/<형제> --parent "+p+" --inherit <무엇을 물려받나> --purpose <다른 갈래>",
					"    한 번에 하나만 열리는 것은 제약이 아니라 원리다 — git 도 두 브랜치를 동시에",
					"    밟으려면 워크트리가 필요하다. 갈래는 동시가 아니라 **차례로** 낸다.")
			}
		}
		die(strings.Join(lines, "\n"))
	}
	showPurposeContext(chain, cycle, *purpose)

	subjTitle := *title
	if subjTitle == "" {
		subjTitle = *purpose
	}
	subject := "gil " + chain + "/" + cycle + "/s1 define: " + subjTitle
	// s1 define 본문 = 문제 정의 보고서. step 과 대칭으로 --body/--body-file(- = stdin)을
	// 받는다 — 없으면 raw amend 로 내려가다 trailer 를 날리는 함정에 빠진다(이슈 #31).
	body := resolveBody(*bodyF, *bodyFile)
	if body == "" {
		body = *title
	}
	// 본문 필수(AIL #12): 문제 정의의 뿌리인 s1 을 빈 채로 열면, gil 이 "amend 로 채우라"고
	// 안내하던 옛 경로가 정확히 raw git 우회를 유도했다(append-only 강제와 자기모순). 문법으로
	// 거부한다 — 가설 없는 공부는 다음 스텝이 아니듯, 문제 미기술로 여는 사이클도 사이클이 아니다.
	if strings.TrimSpace(body) == "" {
		die("거부: open 은 문제 정의 본문이 필요하다 — 무엇을 풀려는지 없이 사이클을 열 수 없다.\n" +
			"  gil open " + ref + " --author <who> --purpose <P> --body <문제 정의>\n" +
			"  긴 본문: --body-file <파일>  또는  --body-file -  (stdin). --title <한 줄>도 본문이 된다.\n" +
			"  (raw git amend 로 본문을 채우지 마라 — trailer 를 날리고 append-only 를 우회한다.)")
	}
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
		{"Gil-Step", "s1"}, {"Gil-Kind", "define"}, {"Gil-Parent", "null"},
		{"Gil-Cycle-Author", *author}, {"Gil-Cycle-Purpose", *purpose},
	}
	if g := strings.TrimSpace(*goal); g != "" {
		tr = append(tr, [2]string{"Gil-Cycle-Goal", g}) // 달성 판정 기준(이슈 #62)
	}
	// 이 사이클이 체인 목적에 어떻게 기여하는가(상현님) — 여는 자리에서 답한 그 문장을 남긴다.
	// 남아야 나중에 "이 체인에 왜 이게 있나"를 되짚을 수 있고, 형해화도 눈에 보인다.
	tr = append(tr, [2]string{"Gil-Fits", strings.TrimSpace(*fits)})
	for _, d := range *datasets {
		tr = append(tr, [2]string{"Gil-Dataset", d}) // 어디서 쟀나 — 판정의 분모(이슈 #79)
	}
	if n := strings.TrimSpace(*datasetNote); n != "" {
		tr = append(tr, [2]string{"Gil-Dataset-Note", n})
	}
	for _, sj := range *subjects {
		tr = append(tr, [2]string{"Gil-Subject", sj}) // 무엇을 쟀나 — 판정의 대상(이슈 #81)
	}
	for _, p := range *parallel {
		tr = append(tr, [2]string{"Gil-Parallel-With", p}) // 미해결을 알면서 나란히 연다(이슈 #45)
	}
	for _, par := range *parents {
		tr = append(tr, [2]string{"Gil-Cycle-Parent", par})
	}
	for _, rf := range *refutes {
		tr = append(tr, [2]string{"Gil-Refutes", rf}) // 소급 반증 간선(AIL #1 B)
	}
	for _, rf := range *refines {
		tr = append(tr, [2]string{"Gil-Refines", rf}) // 정밀화 간선(이슈 #42)
	}
	if strings.TrimSpace(*inherit) != "" {
		tr = append(tr, [2]string{"Gil-Inherit", *inherit}) // 물려받은 전수(AIL #3)
	}
	// 사이클 = 체인 안의 git 가지.
	//
	// **선언한 부모가 있으면 진짜 그 자리에서 갈라진다**(상현님). 옛 코드는 무조건 HEAD 에서
	// 갈랐고 --parent 는 트레일러로만 적혔다 — 그래서 커밋 그래프가 계보를 거짓말했다:
	// cy1 에서 갈라진 cy2·cy3 를 차례로 열면 cy3 의 커밋 조상은 (그때 HEAD 가 거기 있었으므로)
	// cy2 가 됐다. 그러면 위상으로 그리는 화면과 선언으로 그리는 화면이 서로 다른 말을 하고,
	// **둘이 다르면 어느 쪽이 참인지 알 수 없다.** 되돌아가서 분기를 치는 것이 사실이어야 한다 —
	// git 그래프 모양과 gil 계보가 위상적으로 같아야 한다.
	cb := cycleBranch(chain, cycle)
	from := "HEAD"
	if len(*parents) > 0 {
		if sha := cycleTipSHA(chain, (*parents)[0]); sha != "" {
			from = sha
		}
	} else if sha := lastCycleTipOfChain(chain); sha != "" {
		// **선언이 없어도 HEAD 에 기대지 않는다.** 새 사이클은 그 체인이 방금까지 서 있던
		// 자리 — 이 체인의 마지막 사이클 — 에서 갈라진다. HEAD 를 쓰면 그때 사람이/스크립트가
		// 어느 브랜치에 서 있었느냐가 계보가 된다(실측: notification/c2 의 커밋 부모가 남의
		// 체인인 observability 의 스텝이었다. 다른 체인 일을 잠깐 보다 열었을 뿐인데).
		// 사이클이 어느 체인의 것인가는 **여는 순간 이미 정해져 있다**(ref 가 그 이름이다).
		from = sha
	}
	commitOn(cb, from, subject, body, tr, true)
	println2("open: " + ref + "/s1 define (브랜치 " + cb + ")")
	if len(*refutes) > 0 {
		guideRefutes(*refutes)
	}
	if len(*refines) > 0 {
		guideRefines(*refines)
	}
	// 조상의 지식이 **묻지 않아도 도착하게** 한다(상현님). 기록만으로는 전파가 아니다 —
	// 자식이 스스로 gil log 를 거슬러 읽어야 한다면 그건 자기규율이고, 자기규율은 불충분하다.
	for _, ln := range lineageBrief(chain, cycle) {
		stderr(ln)
	}
	reportGuide("define", bodyThin(body))
	guideNext("define") // 다음은 반드시 hypothesis (AIL #41)
}

// sealGuard — **봉인된 것은 자라지 않는다.** 닫힌 사이클·닫힌 체인에 스텝을 붙이는 걸 막는다.
//
// 왜. 실측으로 확인한 집행 격차다: close 로 봉인한 사이클에 `--to` 형제 가지가 그냥 들어갔다.
// fsck 는 그 가지가 미종결일 때만 짚으니, verify→analyze→fail 로 **제대로 끝내면 아무도
// 모른다** — 봉인된 사이클이 봉인 뒤에 조용히 자란다. #85·#86 과 같은 병이다: 집행이 두
// 자리에서 갈리면 느슨한 쪽이 실질 규칙이 된다.
//
// append-only 는 "무엇이든 덧붙일 수 있다"가 아니라 "덮어쓸 수 없다"다. 봉인된 영역은
// 읽기전용이고, 정정은 새 사이클 + --refutes/--supersede 라는 **간선**으로만 한다 —
// 그래야 "언제 무엇이 뒤집혔나"가 이력에 남는다.
//
// 예외 둘: 사람의 답(approve/reject — pending 은 봉인 뒤에도 사람을 기다릴 수 있다)과
// 배포 마커(gil deploy — 봉인된 결과물이 세상에 나간 기록). 둘 다 이 함수를 안 부른다.
func sealGuard(chain, cycle string) {
	if chainClosed(chain, "--branches") {
		die("거부: 체인 \"" + chain + "\" 은 닫혔다 — 봉인된 체인엔 스텝을 붙일 수 없다.\n" +
			"  이어갈 것이 있으면 닫힌 끝에서 새 체인을 연다:  gil chain <새체인> --from " + chain + " --inherit <전수>")
	}
	if !closedCycles("--branches")[chain+"\x01"+cycle] {
		return
	}
	die("거부: " + chain + "/" + cycle + " 은 봉인된 사이클이다 — 봉인된 것은 자라지 않는다.\n" +
		"  append-only 는 '무엇이든 덧붙일 수 있다'가 아니라 '덮어쓸 수 없다'다.\n" +
		"  · 이어서 팔 것이 있으면 → 새 사이클:  gil open " + chain + "/<새사이클> --parent " + cycle +
		" --inherit <여기서 물려받는 것>\n" +
		"  · 이 사이클의 판정을 뒤집는 것이면 → 새 사이클에서 소급 반증:  gil open … --refutes " +
		chain + "/" + cycle + "/<verify 스텝>\n" +
		"  정정을 봉인 안에 밀어넣으면 '언제 무엇이 뒤집혔나'가 사라진다 — 간선으로 남겨라.")
}

// ── gil step ──
func cmdStep(args []string) {
	fs := newFlags("gil step")
	kind := fs.str("kind", "")
	outcome := fs.str("outcome", "")
	to := fs.str("to", "")
	title := fs.str("title", "")
	body := fs.str("body", "")
	bodyFile := fs.str("body-file", "")
	merge := fs.strList("merge")
	// 제안 2 (AIL #1): hypothesis 는 반증조건과 "반증 시 되돌아갈 조상 define"을 문법으로
	// 요구한다. 반증 불가능한 가설엔 fail 이 생길 수 없어 체인이 일자로만 흐른다 —
	// 반증조건을 필수 필드로 심으면 verify 실패가 자동으로 backtrack 경로를 갖는다.
	falsify := fs.str("falsify", "")       // 반증조건: 무엇이 관측되면 이 가설은 거짓인가
	falsifyTo := fs.str("falsify-to", "")  // 반증 시 되돌아갈 조상 define
	// 미종결 잎을 두고 새 가지로 떠나는 것을 막되, 벽이 되지 않게 탈출구(이슈 #78).
	leaveOpen := fs.boolFlag("leave-open")
	// --competing (이슈 #106·#107, 상현님: "세 축 다 병렬로 — 그러려고 gil 이 있는 거니까").
	//
	// 옛 문법에는 **경합 중인 형제 가설**이라는 상태가 없었다. 형제 가지는 앞 가지를 종결한
	// 뒤에만 낼 수 있었고, 동시에 띄우려면 --leave-open 뿐이었는데 그건 fsck 가 위반으로 짚는
	// 자리다. 그래서 실사용 7사이클·스텝 90여 개 동안 병렬 가지가 **0회**였다 — 도구가
	// "일자로 흐른다"고 경고하면서 정작 일자를 벗어나는 길에만 낙인을 찍어 둔 것이다.
	//
	// 경합은 미종결과 다르다. 매달린 잎은 **잊혀서** 남은 것이고, 경합 가지는 **겨루려고**
	// 열어 둔 것이다. 그 차이를 선언으로 받는다: 선언된 경합은 열린 사이클에서 위반이 아니고,
	// handoff 가 "경합 N개 미결"로 이름을 부른다. 대신 사이클을 닫을 때는 전부 종결돼야 한다
	// (close 의 미종결 잎 검사가 그대로 최종 방어선이다 — 경합은 유예지 면제가 아니다).
	competing := fs.boolFlag("competing")
	// 극성(AIL #13): "이 가설이 supported 면 사이클 목표(s1 purpose)가 달성인가 실패인가".
	// 가설 supported ≠ 목표 달성 — 부정적 발견("이 방향은 막혔다")도 supported 일 수 있고,
	// 그건 success 가 아니라 fail/backtrack 이다. falsify 가 "무엇이 이 가설을 깨나"를 가설
	// 세우는 순간 못박듯, 극성은 "이 가설이 맞으면 목표는?"을 그 순간 못박는다. 기본 goal-met
	// (비파괴 — 대부분 가설은 맞으면 목표 달성). goal-missed 면 verify=supported 라도 success 거부.
	ifSupported := fs.str("if-supported", "") // goal-met|goal-missed (hypothesis 전용, 빈값=goal-met)
	// 이슈 #76 본체 — **가설을 세우기 전에 설계를 고정한다**(상현님 승인, 2026-07-28).
	//
	// 실사용 실측이 이유다. 같은 사이클에서 네 번 가지를 냈는데 규모 예측이 3.3배·3.2배·8.2배로
	// 빗나가다 한 번만 맞았고, 맞은 그 한 번의 차이는 이것뿐이었다: **몇 개일지 추정하지 않고
	// 몇 개로 만들지 정했다**(읽기 경로 둘을 공용 함수 하나로 묶기로 먼저 결정). 세는 법을
	// 고치는 방법은 세는 정확도를 올리는 게 아니라 **세어야 할 것을 설계로 줄이는 것**이었다.
	//
	// 그래서 falsify 와 같은 자리에 둔다: 가설을 세우는 순간 "이번에 무엇을 몇 개 만들 것인가"를
	// 못박게 하고, verify 가 그 설계가 유지됐는지(held) 깨졌는지(broke)를 문법으로 답하게 한다.
	// 틀려도 손해가 아니다 — 깨진 설계는 되돌아갈 자리를 가리키는 가장 좋은 신호다(상현님).
	plan := fs.str("plan", "")            // hypothesis 전용: 이번에 만들 것을 수로 고정
	// 체인 목적을 매 스텝 각인한다(상현님, 2026-07-28). 사이클은 체인의 목적을 위해 존재하는데,
	// 스텝을 밟다 보면 사이클 안의 국소적 성패만 남고 "그래서 체인 목적에 다가섰나"가 사라진다.
	// 가설에서 **얼마나 다가설 것인가**를 선언하고, 종결에서 **얼마나 다가섰나 + 다음 설계는
	// 무엇인가**로 회고한다. 그 둘이 계보를 타고 다음 세대로 전파된다(gil context).
	advances := fs.str("advances", "")       // hypothesis 필수: 체인 목적에 어떻게·얼마나 다가서나
	toward := fs.str("toward", "")           // success/fail 필수: 그래서 얼마나 가까워졌나(회고)
	nextDesign := fs.str("next-design", "")  // success/fail 필수: 목적을 위한 다음 설계
	// verify 전용: **가설이 심어둔 반증조건에 답한다**(규칙 17, 상현님).
	//
	// 왜. 지금까지 verify 는 --verdict 만 받고 가설의 --falsify 와 **대조하지 않았다**.
	// AIL #1 이 falsify 를 필수화한 이유가 바로 여기서 샜다: 반증조건을 적게 만들어도
	// 판정이 그 조건을 안 보면, supported/refuted 는 결국 자의적이다. 판정 축이 조용히
	// 바뀌는 자리가 여기다 — --plan-held/--plan-broke 가 설계에 답하게 한 것과 같은 모양으로,
	// 반증조건에도 답하게 한다.
	falsifyMet := fs.str("falsify-met", "")   // 반증조건이 충족됐다(=가설이 틀렸다) + 무엇을 관측했나
	falsifyUnmet := fs.str("falsify-unmet", "") // 충족되지 않았다 + 무엇을 관측했나
	planHeld := fs.boolFlag("plan-held")  // verify 전용: 고정한 설계가 그대로 유지됐다
	planBroke := fs.str("plan-broke", "") // verify 전용: 깨졌다 + 무엇이 달랐나
	// 제안 1 (AIL #1): verify 는 판정을 문법으로 요구한다. supported=가설 지지, refuted=반증.
	verdict := fs.str("verdict", "") // verify 전용
	// 제안 B (AIL #1): 소급 반증 간선 — 이 스텝이 앞서 닫힌 supported verify 판정을 뒤늦게
	// 반증한다. verify 스텝에서 우회를 관측한 순간이 가장 정직한 자리라 step 도 받는다.
	refutes := fs.strList("refutes")
	// 약한 정정 간선(이슈 #42): 앞 verify/analyze 의 *해석*만 정밀화한다. verdict 는 불변.
	refines := fs.strList("refines")
	// --at <스텝>(이슈 #59): 종결(success/fail)을 **그 잎 자리에** 박는다. 기본은 현재 가지
	// tip 인데, HEAD 가 재분기로 떠나버리면 두고 온 가지를 영영 못 닫는다(append-only 라
	// 사후 수정 경로도 없다). 실사용에서 그 상태로 열 몇 스텝을 더 갔고, 뒤늦게 --to 로 닫으려
	// 하자 fail 이 **살아있는 success 잎 위에** 붙을 뻔했다(사본 레포에서 먼저 밟아 발견).
	at := fs.str("at", "")
	inherit := fs.str("inherit", "") // 물려받은 전수(AIL #3): 머지/refutes/refines 간선 생기면 필수
	// 스텝 정정(AIL #12): 같은 kind 의 앞선 스텝을 이 스텝이 대체한다. raw amend 로 옛 커밋을
	// 지우는 대신(trailer 소실·이력 은폐), 새 커밋으로 덮고 옛 것은 이력에 남긴다 — append-only
	// 보존. 뷰어가 옛 스텝에 "⤳정정됨"을 붙인다. --refutes 가 verdict 를 supersede 하지 않고
	// forward 간선으로 남기는 것과 동형(정정이 은폐 아니라 이력에 남는다, 이번 세션 #8 교훈).
	supersede := fs.str("supersede", "")
	// analyze 의 **결론**(상현님 실사용): 분석이 결론 없이 지나가고 곧장 define 으로 되돌아가는
	// 일이 실제로 났다. 해석 없는 해석 노드는 다음 판단의 근거가 되지 못한다 — 그 자리에서
	// 밝힌 것을 한 줄로 못박게 한다. 뒤이은 재분기가 딛는 것이 바로 이 문장이다.
	finding := fs.str("finding", "")
	// 벽의 지도를 벗어날 때의 이유(상현님 실사용): 죽은 잎이 "여기로 돌아가라"고 s4 를
	// 가리켰는데 새 가설은 s1 에서 갈라졌다. 기록과 행동이 어긋나도 도구가 몰랐다.
	despite := fs.str("despite", "")

	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil step <chain>/<cycle> --kind K [...]")
	}
	ref := pos[0]
	chain, cycle, _ := cut(ref, "/")
	steps := reachCycle(chain, cycle, ref) // 다른 브랜치에 서 있어도 찾아간다(이슈 #44)
	if len(steps) == 0 {
		die("거부: " + ref + " 없음 (먼저 gil open)")
	}
	sealGuard(chain, cycle)
	if !kinds[*kind] {
		msg := "거부: 알 수 없는 kind \"" + *kind + "\"\n" +
			"  쓸 수 있는 kind: " + strings.Join(sortedIDs(kinds), " · ")
		if g := nearestKind(*kind); g != "" {
			msg += "\n  혹시 --kind " + g + " 인가?"
		}
		if len(steps) > 0 {
			msg += "\n  지금 팁은 [" + steps[len(steps)-1].step + " " + steps[len(steps)-1].kind +
				"] 이다 — 순서(define→hypothesis→verify→analyze→종결)에 비추어 다음을 골라라."
		}
		die(msg)
	}
	// define 은 사이클의 뿌리 하나뿐 — open 이 만드는 s1 이 유일한 문제 정의다(상현님).
	// 첫 define 이 못 다룬 부분은 새 define 을 또 만드는 게 아니라, 다른 스텝(hypothesis 등)
	// 이나 새 사이클로 이어간다. 그래야 "사이클 = 하나의 문제 정의에서 뻗은 사고 나무"라는
	// 불변식이 서고, 뷰어에 define 이 둘씩 떠 사람이 "어느 게 진짜 정의?" 하고 헷갈리지 않는다.
	// 예외 하나: --supersede 로 **앞선 define 을 정정**하는 것은 새 define 이 아니라 같은
	// 자리를 다시 쓰는 것이다(상현님). 살아있는 define 은 여전히 하나 — 정정된 옛 define 은
	// 구버전 가지로 접힌다. 문제 정의가 틀렸을 때 유일한 길이 "새 사이클"이면, 사람은
	// raw amend 로 내려가거나 틀린 정의 위에 계속 쌓는다.
	if *kind == "define" && strings.TrimSpace(*supersede) == "" {
		die("거부: define 은 사이클의 뿌리 하나뿐(open 이 만드는 s1). 추가 문제 정의는 step 이 아니라 " +
			"다른 kind(hypothesis 등)나 새 사이클(gil open <chain>/<새사이클>)로 이어가라.\n" +
			"  이미 있는 문제 정의를 **다시 쓰는** 것이면 정정이다:\n" +
			"    gil step " + ref + " --kind define --supersede <그 define> --inherit <무엇을 바로잡나> --body …")
	}
	showPurposeContext(chain, cycle, "")
	// ── 스텝 정정 (AIL #12 → 정정은 분기다, 상현님) ────────────────────────────────
	// --supersede 대상은 (a)이 사이클에 실재하고 (b)이 스텝과 같은 kind 여야 한다.
	//
	// **모든 kind 가 정정 대상이다** — define 도, 종결 스텝(success/fail/pending)도. 옛
	// 문법은 종결을 뺐는데, 같은-kind 규칙이 이미 있으므로 **판정 뒤집기는 애초에 불가능**하다:
	// fail 은 fail 로만, success 는 success 로만 정정된다(판정은 그대로, 그 판정의 서술을 다시
	// 쓴다). 판정 자체를 뒤집는 일은 여전히 backtrack(hypothesis --to)·소급 반증(--refutes)의
	// 영역이다. 종결을 빼 두면 "fail 의 벽 서술이 틀렸다"를 고칠 길이 raw amend 밖에 없었다.
	//
	// 그리고 정정은 **그 자리에서 분기한다** — 새 스텝의 부모는 현재 tip 이 아니라 **정정
	// 대상의 부모**이고, 새 git 브랜치로 갈라진다. 옛 동작은 정정 커밋을 가지 끝에 매달아,
	// "s2 를 고쳤다"면서 s5 뒤에 붙었다(자리도 계보도 어긋난다). 분기로 두면 정정 대상과 그
	// 자손 전부가 **손대지 않은 구버전 가지로 통째 보존**된다(상현님 판단).
	var supTgt *node
	if strings.TrimSpace(*supersede) != "" {
		for i := range steps {
			if steps[i].step == *supersede {
				supTgt = &steps[i]
				break
			}
		}
		if supTgt == nil {
			// 다른 가지에 있는 스텝도 찾아본다 — 사이클 전체에서 없을 때만 거부한다.
			all := cycleAnywhere(chain, cycle)
			for i := range all {
				if all[i].step == *supersede {
					supTgt = &all[i]
					break
				}
			}
		}
		if supTgt == nil {
			die("거부: --supersede " + *supersede + " 는 이 사이클에 없는 스텝이다.")
		}
		if supTgt.kind != *kind {
			die("거부: --supersede 는 같은 kind 만 정정한다 — " + *supersede + " 는 " + supTgt.kind +
				", 이 스텝은 " + *kind + ". (다른 kind 로 바꾸려면 정정이 아니라 새 스텝/새 가지다.)\n" +
				"  판정을 뒤집으려면 정정이 아니다: backtrack(hypothesis --to) 이나 소급 반증(--refutes).")
		}
		// 정정도 계보 간선이다 — 간선이 생기면 --inherit 필수(AIL #3 의 일관 적용). 정정이야말로
		// "무엇을 바로잡고 무엇은 그대로 계승하나"가 남아야 하는 자리다. 없으면 뒤에 오는 존재는
		// 두 판본을 보고 어느 쪽이 왜 이겼는지 알 길이 없다.
		if strings.TrimSpace(*inherit) == "" {
			die("거부: --supersede 는 --inherit <전수> 필요 — 정정은 덮어쓰기가 아니라 분기다.\n" +
				"  담아라: 옛 " + *supersede + " 의 무엇이 틀렸고, 무엇은 그대로 계승하는가.\n" +
				"  (옛 " + *supersede + " 와 그 자손은 구버전 가지로 그대로 보존된다 — 지워지지 않는다.)")
		}
		// 자리는 정정이 스스로 정한다(=대상의 부모) — 자리를 고르는 다른 플래그와 겹칠 수 없다.
		// 단 fail 의 --to 는 자리가 아니라 **되돌아갈 곳의 기록**이라 그대로 필요하다(이슈 #59①).
		if strings.TrimSpace(*at) != "" || len(*merge) > 0 || (strings.TrimSpace(*to) != "" && *kind != "fail") {
			die("거부: --supersede 는 자리를 스스로 정한다(정정 대상의 부모) — --at/--merge/--to 와 함께 쓸 수 없다.\n" +
				"  (fail 의 --to 만 예외다 — 그건 자리가 아니라 '되돌아갈 곳'의 기록이다.)")
		}
	}
	// ── analyze 는 결론을 남긴다 (상현님 실사용) ────────────────────────────────
	// "분석에서 결론 없이 define 으로 백트랙하는 현상"이 실제로 관측됐다. analyze 는 순수
	// 분석이지만 **아무것도 밝히지 않은 분석**은 다음 스텝의 근거가 되지 못한다 — 그 위에 선
	// 재분기는 사실상 근거 없이 되돌아가는 것이고, 그러면 같은 벽을 다시 만난다.
	// 본문(보고서)은 얇아도 경고에 그쳤으니, **한 줄 결론만은 문법으로** 받는다.
	if *kind == "analyze" && strings.TrimSpace(*finding) == "" {
		die("거부: analyze 는 --finding <이 분석이 밝힌 것> 필요 — 결론 없는 분석은 다음 판단의 " +
			"근거가 되지 못한다.\n" +
			"  한 줄로 못박아라: 무엇이 원인인가 · 무엇이 이 가설을 막았나 · 그래서 어디로 돌아가야 하나.\n" +
			"  (본문은 근거 전문, --finding 은 그 전문에서 뽑은 결론이다. 뒤이은 재분기·종결이\n" +
			"   딛는 것이 바로 이 문장이고, 벽의 지도가 가리킬 자리도 여기서 정해진다.)")
	}
	// analyze 는 순수 분석 — 종결(성공/실패/대기)은 별도 스텝(success/fail/pending)으로(상현님).
	// 하위호환: analyze --outcome 도 여전히 허용(옛 데이터·간단 사용).
	if *kind == "analyze" && *outcome != "" && !outcomes[*outcome] {
		die("거부: analyze --outcome 은 success|backtrack|fail 중 하나(생략 가능)")
	}
	// fail 종결 스텝은 죽은 잎 — 되돌아갈 곳을 --to 로 기록(벽의 지도).
	//
	// **--to pending — 아직 모른다고 적을 자리**(이슈 #105, 실사용). 벽에 부딪힌 그 순간의
	// 진실이 "다음 갈 곳은 사람의 판정에 달렸다"인 경우가 실제로 있다(선택지 (a)(b)(c) 를
	// 본문에 적어 두고 사람을 기다리는 fail). 그런데 --to 는 단일 값을 **즉시** 요구했고,
	// 세션은 보수적 기본값(s1)을 적을 수밖에 없었다 — 그리고 나중에 실제 재분기가 s8 에서
	// 나면서 지도와 행동이 어긋나 보였다("뭐가 맞는 거냐"고 사람이 물었다).
	// 어휘가 부족하면 기록이 거짓말한다(#80 과 같은 축, 방향만 다르다).
	if *kind == "fail" && *to == "" {
		die("거부: fail 은 --to <조상 define|analyze> 필요 (되돌아갈 곳, 벽의 지도)\n" +
			"  아직 어디로 갈지 **모르면** 그렇게 적어라: --to pending\n" +
			"    (사람의 판정이나 다음 분석이 정할 자리다 — 지도는 그때 확정된다.\n" +
			"     본문·--next-design 에 후보를 적어 두면 그게 판정의 재료가 된다.)")
	}
	// 제안 1 (AIL #1) — verify 는 판정을 문법으로 요구한다. 지금까지 verify 는 반증을 본문
	// 산문에만 적고 곧장 success 로 흘렀다(gil 이 지지/반증을 몰랐다). --verdict 를 필수화하면
	// gil 이 verify 결과를 구조로 알고, refuted 뒤 success 를 거부할 수 있다(아래 success 가드).
	if *kind == "verify" {
		if *verdict == "" {
			die("거부: verify 는 --verdict supported|refuted 필요 — 이 검증이 가설을 지지했나 반증했나. " +
				"산문에만 적으면 gil 이 몰라 반증해도 success 로 흘러간다(AIL #1).")
		}
		if !verdicts[*verdict] {
			die("거부: --verdict 은 supported|refuted 중 하나")
		}
		if *planHeld && strings.TrimSpace(*planBroke) != "" {
			die("거부: --plan-held 와 --plan-broke 는 함께 쓸 수 없다 — 설계는 유지됐거나 깨졌거나 하나다.")
		}
	} else if *planHeld || strings.TrimSpace(*planBroke) != "" {
		die("거부: --plan-held/--plan-broke 는 verify 전용이다(고정한 설계가 실측에서 유지됐나, 이슈 #76).")
	}
	resolveRefutes(*refutes) // 소급 반증 대상 무결성(AIL #1 B)
	resolveRefines(*refines) // 정밀화 대상 무결성(이슈 #42)
	// 제안 A (AIL #3) — 머지/소급반증 간선이 새로 생기면 --inherit 필수. 같은 사이클 안
	// 선형 스텝(직전 Gil-Parent)은 전수랄 게 없어 면제 — 매 스텝 강제는 형해화만 낳는다
	// (clew@AIL 실사용: 같은 내용 복붙). 계보가 실제로 갈라지는 자리에만 요구한다.
	if (len(*merge) > 0 || len(*refutes) > 0 || len(*refines) > 0) && strings.TrimSpace(*inherit) == "" {
		die("거부: 계보 간선(--merge/--refutes/--refines)이 있으면 --inherit <전수> 필요 — 이 갈래에서 " +
			"무엇을 물려받았나(머지), 무엇을 뒤집고 무엇은 계승하나(refutes), 앞 해석의 어디까지가 " +
			"맞았나(refines)를 명시하라(AIL #3).")
	}
	// ── 벽의 지도를 따르라 (상현님 실사용) ──────────────────────────────────────
	// "실패 노드에서 분석 노드로 백트랙했는데 define 에서 새 가설을 만드는 현상"이 관측됐다.
	// 죽은 잎은 --to 로 **되돌아갈 자리**를 기록한다(벽의 지도). 그런데 그 다음 재분기가 그
	// 자리를 무시하고 다른 앵커에서 갈라져도 gil 이 몰랐다 — 기록과 행동이 어긋나는데 도구가
	// 침묵하면, 그 기록은 이내 빈 칸 채우기가 된다(#76 이 관찰 중인 형해화의 실제 사례).
	//
	// 규칙: 이 사이클에 아직 회수되지 않은 죽은 잎이 있고, 그 잎이 가리킨 자리와 다른 곳에서
	// 갈라지려 하면 거부한다. 벽의 지도가 틀렸을 수도 있으니 길은 연다 — --despite <이유>.
	// (지도를 고치는 것도 정당하다. 다만 말없이 어기는 것은 아니다.)
	if *kind == "hypothesis" && strings.TrimSpace(*to) != "" {
		var wall *node
		for i := range steps {
			if isDeadLeaf(steps[i]) && strings.TrimSpace(steps[i].backtrack) != "" {
				wall = &steps[i] // steps 는 old→new — 가장 최근 벽이 남는다
			}
		}
		// 지도가 pending 이면 벗어날 지도가 없다 — 확정은 지금 일어난다(이슈 #105).
		if wall != nil && wall.backtrack == "pending" {
			stderr("  ⌖ 벽의 지도(" + wall.step + ")는 **미정(pending)** 이었다 — 이 재분기가 그 자리를 확정한다: " + *to)
			wall = nil
		}
		if wall != nil && wall.backtrack != *to {
			if strings.TrimSpace(*despite) == "" {
				die("거부: 벽의 지도와 다른 자리에서 갈라진다 — " + wall.step + " [" + wall.kind +
					"] 는 **" + wall.backtrack + " 로 돌아가라**고 적었는데, 지금 --to " + *to + " 다.\n" +
					"  그 한 줄은 막혔을 때의 너 자신이 남긴 지도다. 말없이 어기면 그 기록은 빈 칸이 된다.\n" +
					"    ▸ 지도를 따른다  → --to " + wall.backtrack + "\n" +
					"    ▸ 지도가 틀렸다  → --despite \"<왜 " + wall.backtrack + " 가 아니라 " + *to + " 인가>\"\n" +
					"       (지도를 고치는 것도 정당하다 — 다만 그 판단이 기록에 남아야 한다.)")
			}
			stderr("  ⚠ 벽의 지도(" + wall.step + " → " + wall.backtrack + ")를 벗어나 " + *to + " 에서 갈라진다.")
			stderr("    이유: " + strings.TrimSpace(*despite))
		}
	}
	// backtrack 전수 강제 (AIL #13, 요구 5) — 조상 define 으로 되돌아가 새 형제 가지를 팔 때
	// (hypothesis --to <define>), 죽은 가지에서 얻은 "누적된 반성"을 --inherit 으로 잇게 한다.
	// backtrack 은 계보가 갈라지는 자리(머지·refutes 와 동급 간선)인데 지금껏 전수가 면제돼,
	// 죽은 가지의 교훈이 새 가지로 안 흘렀다. 판정 축이 은밀히 전환되던 근본(맥락 단절)을 친다.
	if *kind == "hypothesis" && *to != "" && strings.TrimSpace(*inherit) == "" {
		// 전수를 요구하면서 **앞선 전수를 안 보여주면** 매번 마지막 벽 하나만 적히고 앞의
		// 벽들은 사라진다(회고 거부문이 앞선 회고를 함께 주는 것과 같은 이유). 지금까지 민
		// 벽 전부를 거부문에 붙여, 새 --inherit 이 그 위에 **쌓이게** 한다.
		msg := "거부: backtrack(hypothesis --to " + *to + ")은 --inherit <전수> 필요 — 되돌아오게 만든 " +
			"죽은 가지에서 무엇을 배웠나(그 벽의 교훈)를 새 가지에 지고 가라. 맥락이 끊기면 같은 벽을 다시 민다(AIL #13)."
		if walls := deadAttempts(chain, cycle, "    "); len(walls) > 0 {
			msg += "\n  지금까지 이 사이클에서 민 벽 — 새 전수는 여기에 **쌓아라**(마지막 하나로 덮지 말고):\n" +
				strings.Join(walls, "\n")
		}
		die(msg)
	}

	tip := growingTip(steps)
	tipID := ""
	if tip != nil {
		tipID = tip.step
	}
	// --at <스텝>(이슈 #59): 두고 온 잎 자리에 종결을 박는 것이므로, 순서 강제·가드의 기준도
	// HEAD 팁이 아니라 **그 자리**여야 한다. 이걸 안 옮기면 "직전이 verify 인데 다음이 fail"
	// 같은 엉뚱한 거부가 나 두고 온 가지를 여전히 못 닫는다.
	// 대상은 HEAD 계보 밖에 있다 — 두고 온 형제 가지이기 때문이다. 그러니 사이클 전체
	// (모든 브랜치)에서 찾는다. cycleSteps 는 아래 가드들도 함께 쓴다.
	cycleSteps := steps
	if strings.TrimSpace(*at) != "" {
		cycleSteps = cycleAnywhere(chain, cycle)
		found := false
		for i := range cycleSteps {
			if cycleSteps[i].step == *at {
				tip = &cycleSteps[i]
				tipID = cycleSteps[i].step
				found = true
				break
			}
		}
		if !found {
			die("거부: --at " + *at + " 는 사이클 " + ref + " 에 없다 — gil fsck 가 매달린 잎을 짚어준다.")
		}
		// 자리가 유효한가를 순서 강제보다 **먼저** 묻는다 — 엉뚱한 자리를 골랐는데 "순서를
		// 건너뛴다"고 답하면 진짜 문제가 가려진다.
		if *kind != "fail" && *kind != "success" && *kind != "pending" {
			die("거부: --at 은 종결 스텝(fail|success|pending)에만 쓴다 — 받은 kind=" + *kind + "\n" +
				"  진행 스텝은 현재 가지 끝에 이어지고, 갈래를 새로 내려면 --to <조상 define|analyze> 다.")
		}
		if isLiveLeafKind(tip.kind) || tip.kind == "fail" {
			die("거부: --at " + *at + " 는 이미 종결 스텝이다(kind=" + tip.kind + ") — 종결에 종결을 겹치지 마라.")
		}
		for _, n := range cycleSteps {
			if n.parent == *at {
				die("거부: --at " + *at + " 는 잎이 아니다(자식 " + n.step + " 이 있다) — 종결은 매달린 잎 자리에만 박는다.\n" +
					"  gil fsck 가 매달린 미종결 잎을 짚어준다.")
			}
		}
	}
	// pending 가드(상현님): pending 스텝 뒤에는 사람의 명시적 승인/기각만 허용한다.
	// 서브에이전트가 pending 직후 스스로 analyze 로 넘어가던 것을 구조로 막는다.
	if tip != nil && tip.kind == "pending" {
		die("거부: " + ref + " 팁이 pending(" + tip.step + ") — 사람의 답을 먼저 받아야 한다. " +
			"승인: gil approve " + ref + "  |  기각: gil reject " + ref + " --to <조상 define>")
	}
	// ── 순서 체인 강제 (AIL #41, 상현님) ──
	// 사고의 골격을 문법으로 굳힌다: define→hypothesis→verify→analyze→종결(success/fail/pending),
	// 그리고 analyze 는 backtrack(→조상 define 으로 새 가설)도. 각 kind 는 '다음에 올 kind'가
	// 정해져 있고, 어긋나면 거부한다. "define 만 하고 밖에서 실험"(가설 건너뛰기)·"verify 없이
	// success"·"analyze 없이 종결" 같은 일자화 우회를 앞단에서 막는다.
	// 단 계보가 갈라지는 자리(형제분기 hypothesis --to / backtrack / merge)는 선형 규칙 면제 —
	// 그건 순서가 아니라 분기다(죽은 잎·success 가드가 따로 관장). 선형(직전 tip 위에 곧장)일
	// 때만 이 순서를 강제한다.
	// 정정(--supersede)도 순서 면제 — 정정은 '다음 스텝'이 아니라 '같은 자리 다시 쓰기'다.
	isBranching := (*kind == "hypothesis" && *to != "") || *outcome == "backtrack" ||
		len(*merge) > 0 || strings.TrimSpace(*supersede) != ""
	// **pending 은 어느 자리에서든 정당하다**(이슈 #115 후속). pending 은 사고의 다음 걸음이
	// 아니라 **사고를 멈추고 사람에게 넘기는 것**이다. 그런데 순서 검사가 define 뒤·hypothesis
	// 뒤의 pending 을 "순서를 건너뛴다"로 거부했다 — `human-in-the-loop.md` 가 "문제 정의가
	// 불명확하면 가설을 세우기 전에 먼저 사람에게 물어라"라고 권하는 바로 그 동작이 문법으로
	// 막혀 있었다. 그 결과 실사용에서 남은 선택은 셋뿐이었다: 없는 관측의 판정을 쓰거나
	// (날조), 사이클을 영구히 열어 두거나, 하려던 것과 다른 작업을 한 벌 더 하거나.
	// 어휘가 부족하면 기록이 거짓말한다(#80 과 같은 논거).
	if tip != nil && !isBranching && *kind != "pending" {
		// tip.kind 별로 선형 다음에 허용되는 kind 집합.
		allowedNext := map[string]map[string]bool{
			"define":     {"hypothesis": true},
			"hypothesis": {"verify": true},
			"verify":     {"analyze": true},
			"analyze":    {"success": true, "fail": true, "pending": true},
			// success/fail/pending(종결)·죽은 잎 위 선형은 아래 다른 가드가 이미 거부한다.
		}
		if nexts, governed := allowedNext[tip.kind]; governed && !nexts[*kind] {
			want := []string{}
			for k := range nexts {
				want = append(want, k)
			}
			sort.Strings(want)
			hint := map[string]string{
				"define":     "gil step " + ref + " --kind hypothesis --falsify <반증조건> --falsify-to s1  — 무엇을 세우고 무엇이 관측되면 틀리나. (define 다음은 반드시 가설 — 문제 정의만 하고 실험으로 새면 사고가 일자로 흐른다, AIL #41)",
				"hypothesis": "gil step " + ref + " --kind verify --verdict supported|refuted  — 가설을 실측으로 검증하라.",
				"verify":     "gil step " + ref + " --kind analyze  — 검증 결과가 무엇을 뜻하는지 해석하라(다음은 종결).",
				"analyze":    "gil step " + ref + " --kind success|fail|pending  — 산 잎/죽은 잎/사람대기로 종결. 또는 backtrack(--kind hypothesis --to <조상 define>)으로 같은 문제의 새 가지를. 분석하다 문제 정의 자체가 틀렸음을(새 define 을) 찾았다면 fail 로 닫고 새 사이클을 열어라: gil open <chain>/<새사이클> --refutes|--parent … --inherit '이 분석에서 진짜 문제는 …'.",
			}[tip.kind]
			die("거부: 직전이 " + tip.kind + "(" + tip.step + ")인데 다음이 " + *kind + " 다 — 순서를 건너뛴다. " +
				"다음은 " + strings.Join(want, "/") + " 여야 한다:\n  " + hint)
		}
	}
	// 제안 3 완화 (AIL #1) — fail 잎은 죽은 채로 지도에 남아야 한다. tip 이 죽은 잎(fail/
	// analyze-fail/backtrack)이면 그 위에 선형으로 잇지 못한다. 재가설은 반드시 새 가지 —
	// 형제분기(--kind hypothesis --to <define>) 나 backtrack(--outcome backtrack --to)로만.
	// "한 사이클 안 회수"를 막는 게 아니라, 회수하더라도 fail 잎이 물리적으로 남게 강제한다.
	if tip != nil && isDeadLeaf(*tip) {
		// 정정도 새 가지다 — 팁이 무엇이든 정정은 **대상의 부모** 자리에서 갈라지므로 죽은 잎
		// 위에 얹히지 않는다. 이 예외가 없으면 "fail 의 서술이 틀렸다"를 고칠 길이 raw amend 뿐이다.
		newBranch := (*kind == "hypothesis" && *to != "") || *outcome == "backtrack" ||
			len(*merge) > 0 || supTgt != nil
		if !newBranch {
			die("거부: " + ref + " 팁이 죽은 잎(" + tip.step + ", " + tip.kind + ") — 그 위에 선형으로 " +
				"이을 수 없다. 죽은 잎은 벽의 지도로 남는다. 재가설은 새 가지로: " +
				"gil step " + ref + " --kind hypothesis --to <조상 define> --falsify … --falsify-to …(AIL #1).")
		}
	}
	// 고정한 설계가 있으면 verify 는 그것에도 답해야 한다(이슈 #76). 판정을 verdict 하나로
	// 두면 "가설은 지지됐는데 설계는 세 배로 불었다"가 기록에서 사라진다 — 실사용에서
	// 빗나간 세 번이 정확히 그 모양이었다(계수는 맞고 세는 법이 틀렸다).
	if *kind == "verify" && !*planHeld && strings.TrimSpace(*planBroke) == "" && tip != nil {
		for _, st := range currentAttempt(steps, tip.step) {
			if st.kind == "hypothesis" && strings.TrimSpace(st.plan) != "" {
				die("거부: verify 는 --plan-held 또는 --plan-broke <무엇이 달랐나> 필요 — " +
					st.step + " 이 고정한 설계에 답하라(이슈 #76).\n" +
					"  고정된 설계: " + st.plan + "\n" +
					"  · 그대로 만들어졌으면 → --plan-held\n" +
					"  · 달라졌으면 → --plan-broke '신규 실행경로 3개(예상 1) — fs 쪽이 공용 함수로 안 묶였다'\n" +
					"  깨진 설계는 실패가 아니라 신호다: 되돌아갈 자리를 가장 잘 가리킨다.")
			}
		}
	}
	// 반증조건에 답하게 한다(규칙 17). 그리고 **모순은 거부한다**: 반증조건이 충족됐는데
	// verdict=supported 는 성립하지 않는다 — 그게 판정 축을 은밀히 바꾸는 정확한 동작이다.
	if *kind == "verify" && tip != nil {
		met, unmet := strings.TrimSpace(*falsifyMet), strings.TrimSpace(*falsifyUnmet)
		if met != "" && unmet != "" {
			die("거부: --falsify-met 과 --falsify-unmet 은 함께 못 선다 — 충족됐거나 아니거나 하나다.")
		}
		for _, st := range currentAttempt(steps, tip.step) {
			if st.kind != "hypothesis" || strings.TrimSpace(st.falsify) == "" {
				continue
			}
			if met == "" && unmet == "" {
				die("거부: verify 는 --falsify-met 또는 --falsify-unmet <무엇을 관측했나> 필요 — " +
					st.step + " 이 심은 반증조건에 답하라(규칙 17).\n" +
					"  반증조건: " + st.falsify + "\n" +
					"  · 그 조건이 관측됐다면 → --falsify-met '3회 평균 +0.4% — 개선 없음' (그러면 verdict 는 refuted)\n" +
					"  · 관측되지 않았다면 → --falsify-unmet '3회 평균 -31% — 조건 미달'\n" +
					"  반증조건을 안 보고 내리는 supported/refuted 는 결국 자의적이다 — 판정 축은 " +
					"가설을 세울 때 정한 그 조건이어야 한다(AIL #1).")
			}
			if met != "" && *verdict == "supported" {
				die("거부: 반증조건이 충족됐는데 verdict=supported 는 성립하지 않는다 — 판정 축을 바꾸는 것이다.\n" +
					"  " + st.step + " 의 반증조건: " + st.falsify + "\n" +
					"  관측: " + met + "\n" +
					"  · 이 가설은 틀렸다 → --verdict refuted (그리고 다음은 analyze → backtrack/fail)\n" +
					"  · 관측이 그 조건에 해당하지 않는다면 → --falsify-unmet 으로 적어라.\n" +
					"  · 조건 자체가 틀렸다고 판단되면 그건 verify 가 아니라 새 가설의 몫이다 — " +
					"지금 조건을 고쳐 쓰면 그래프가 사후에 유리해진다.")
			}
			break
		}
	}
	// 종결은 회고다(상현님). success/fail 은 이 가지의 끝이자 **다음 세대가 읽을 유일한 요약**이다.
	// 여기서 "체인 목적에 얼마나 가까워졌나"와 "목적을 이루기 위한 다음 설계는 무엇인가"를
	// 남기지 않으면, 다음 사이클은 조상의 결론이 아니라 조상의 제목만 물려받는다.
	if *kind == "success" || *kind == "fail" {
		cp := chainPurpose(chain, "--branches")
		if strings.TrimSpace(*toward) == "" {
			die("거부: " + *kind + " 은 --toward <체인 목적에 얼마나 가까워졌나> 필요 (종결=회고).\n" +
				"  체인 [" + chain + "] 목적: " + orDefault(cp, "(선언 없음)") + "\n" +
				lineageTowardLines(chain, cycle) +
				"  이 가지가 그 목적을 향해 실제로 얼마나 옮겨놨는지 적어라 — 사이클의 성패가 아니라 목적 기준으로.")
		}
		if strings.TrimSpace(*nextDesign) == "" {
			die("거부: " + *kind + " 은 --next-design <목적을 이루기 위한 다음 설계> 필요 (종결=회고).\n" +
				"  이 가지가 끝났다고 목적이 끝난 게 아니다. **다음에 무엇을 어떻게 만들 것인가**를 여기 적어라 —\n" +
				"  다음 세대(다음 가지·다음 사이클)가 물려받는 것이 바로 이 한 줄이다.\n" +
				"  추정이 아니라 설계다: '몇 개일지'가 아니라 '무엇을 몇 개로 만들지'(이슈 #76 과 같은 축).")
		}
	}
	// 제안 1 success 가드 (AIL #1) — 이 가지 계보에 refuted verify 가 있으면 success 거부.
	// 순서 강제(AIL #41)로 verify 다음은 analyze 라, success 는 analyze tip 위에서 찍힌다 —
	// 그래서 '직전 verify' 가 아니라 '계보에 refuted verify 가 있나'로 본다(analyze 를 거쳐도
	// 그 반증 판정은 유효하다). 마찰이 있는데 success 로 뭉개는 걸 구조로 막는다.
	if *kind == "success" && tip != nil {
		for _, s := range currentAttempt(steps, tip.step) {
			if s.kind == "verify" && s.verdict == "refuted" {
				die("거부: 이 가지의 verify(" + s.step + ")가 가설을 반증(refuted)했다 — success 로 닫을 수 없다. " +
					"fail(gil step … --kind fail --to <define>) 로 죽은 잎을 남기거나 " +
					"backtrack(gil step … --kind hypothesis --to <define>) 으로 새 가지를 파라(AIL #1).")
			}
		}
	}
	// 극성 success 가드 (AIL #13) — verify 가 supported 라도, 그 가설의 극성이 goal-missed 면
	// 그 supported 는 "목표 실패를 확인함"(부정적 발견)이다. 가설 supported ≠ 목표 달성 —
	// refuted 가드가 막는 병("마찰을 success 로 뭉갬")의 다른 얼굴이다. success 를 거부하고
	// fail(벽으로 못박음)/backtrack(다른 접근)을 요구한다. 부정적 발견은 그래프에서 가장 값진
	// 벽의 지도여야지 가짜 success 가 아니다.
	if *kind == "success" && tip != nil {
		lin := currentAttempt(steps, tip.step) // 앞 시도의 판정이 이 가지를 막지 않게(#78 곁다리)
		byID := map[string]node{}
		for _, s := range steps {
			byID[s.step] = s
		}
		for _, s := range lin {
			if s.kind == "verify" && s.verdict == "supported" {
				if hyp, ok := byID[s.parent]; ok && hyp.kind == "hypothesis" && hyp.polarity == "goal-missed" {
					die("거부: 이 가지의 verify(" + s.step + ")는 supported 지만, 그 가설(" + hyp.step + ")의 극성이 " +
						"goal-missed 다 — 가설이 맞았다는 건 사이클 목표의 '실패'를 확인한 것(부정적 발견)이다. " +
						"success 가 아니라:\n  fail(gil step … --kind fail --to <define>) 로 '이 방향은 막혔다'를 벽으로 못박거나\n" +
						"  backtrack(gil step … --kind hypothesis --to <define> --inherit <이 벽의 교훈>) 으로 다른 접근을 파라(AIL #13).")
				}
			}
		}
	}
	defineIDs := map[string]bool{}
	analyzeIDs := map[string]bool{} // 재분기 앵커 후보(이슈 #32) — 분석의 결론에서 갈라진다.
	liveLeaves := map[string]bool{}
	for _, s := range steps {
		if s.kind == "define" {
			defineIDs[s.step] = true
		}
		if s.kind == "analyze" {
			analyzeIDs[s.step] = true
		}
		if isLiveLeaf(s) {
			liveLeaves[s.step] = true
		}
	}

	// 제안 2 (AIL #1) — 반증 가능한 가설 강제. HEAAL: 규율은 안내가 아니라 문법의 거부로.
	// 모든 hypothesis 는 (1) 반증조건과 (2) 반증 시 되돌아갈 조상 define 을 미리 선언해야
	// 한다. 그래야 뒤이은 verify 가 반증했을 때 backtrack 경로가 이미 그래프에 심겨 있다.
	// 반증 불가능한(=사후에 성공을 알고 쓴) 가설을 문법으로 거부한다.
	if *kind == "hypothesis" {
		if *falsify == "" {
			die("거부: hypothesis 는 --falsify <반증조건> 필요 — '무엇이 관측되면 이 가설은 거짓인가'. " +
				"반증 불가능한 가설엔 fail 이 생길 수 없어 체인이 일자로만 흐른다(AIL #1).")
		}
		if *falsifyTo == "" {
			die("거부: hypothesis 는 --falsify-to <조상 define> 필요 — 반증되면 되돌아갈 곳. " +
				"이걸 미리 심어야 verify 반증이 자동으로 backtrack 경로를 갖는다(AIL #1).")
		}
		// 체인 목적 각인(상현님). 가설은 사이클 안에서만 서지 않는다 — 체인이 이루려는 것에
		// 어떻게 다가서는지를 세우는 순간 말해야, 종결에서 "얼마나 다가섰나"를 회고할 수 있다.
		if strings.TrimSpace(*advances) == "" {
			cp := chainPurpose(chain, "--branches")
			die("거부: hypothesis 는 --advances <체인 목적에 어떻게·얼마나 다가서나> 필요.\n" +
				"  체인 [" + chain + "] 목적: " + orDefault(cp, "(선언 없음)") + "\n" +
				"  이 가설이 그 목적에 다가서는 몫을 적어라 — 사이클 안의 성패가 아니라 **체인의 목적** 기준으로.\n" +
				"  예: --advances '전체 16지표 중 미달 4개 가운데 2개(토큰·지연)를 이 가설이 덮는다'\n" +
				"  종결(success/fail)에서 --toward 로 이것을 회고한다 — 선언이 없으면 회고할 것도 없다.")
		}
		// 설계 고정 강제(이슈 #76). 추정이 아니라 결정이다 — "몇 개일지"가 아니라 "몇 개로 만들지".
		if strings.TrimSpace(*plan) == "" {
			die("거부: hypothesis 는 --plan <이번에 만들 것> 필요 — 가설을 세우기 **전에** 설계를 고정하라(이슈 #76).\n" +
				"  추정이 아니라 결정이다: '몇 개일지 추정'이 아니라 **'몇 개로 만들지 결정'**.\n" +
				"  예: --plan '신규 실행경로 1개(net·fs 읽기를 공용 함수 하나로 묶는다) · 신규 파일 0'\n" +
				"  왜: 규모 예측이 빗나간 세 번은 전부 신규 실행경로를 적게 셌기 때문이었다. 세는 법을\n" +
				"      고치는 길은 세는 정확도를 올리는 게 아니라 **세어야 할 것을 설계로 줄이는 것**이다.\n" +
				"  틀려도 손해가 아니다 — 깨진 설계는 되돌아갈 자리를 가리키는 가장 좋은 신호다.")
		}
		// 관대한 입력(이슈 #47 G1): 사람도 LLM 도 "chain/cycle/s1" 이나 커밋 해시를 먼저
		// 시도한다(실측 3회 시행착오). 뜻이 명백하면 받아 정규화한다 — 형식을 못 맞춰서
		// 거부당하는 건 사고의 문제가 아니라 표기의 문제다.
		*falsifyTo = normalizeStepRef(*falsifyTo, chain, cycle, steps)
		// analyze 도 받는다(이슈 #67 곁다리). --to 와 같은 논거다: 가설 자체가 틀렸으면
		// define 으로 완전 회귀, 가설은 맞고 방법만 틀렸으면 그걸 밝힌 analyze 로 —
		// **반증 시 되돌아갈 자리**에도 그대로 적용된다. 두 플래그가 비대칭일 이유가 없다.
		if !defineIDs[*falsifyTo] && !analyzeIDs[*falsifyTo] {
			// 문구가 검사보다 옛것이면 사람은 없는 규칙을 상대로 싸운다(#67 곁다리). 검사는
			// analyze 도 받으니 문구도 그렇게 말하고, 형제 가지에 있어서 안 보이는 경우엔
			// 그 사실과 탈출로(goto)까지 준다.
			die("거부: --falsify-to \"" + *falsifyTo + "\" 는 이 사이클의 조상 define 또는 analyze 가 아니다.\n" +
				"  형식은 **짧은 스텝 이름**이다(예: s1). 경로형(" + chain + "/" + cycle +
				"/s1)이나 커밋 해시도 받아 정규화한다.\n" +
				"  이 사이클의 define: " + strings.Join(sortedIDs(defineIDs), " ") + "\n" +
				"  이 사이클의 analyze: " + strings.Join(sortedIDs(analyzeIDs), " ") +
				elsewhereHint(chain, cycle, *falsifyTo, steps) + "\n" +
				"  그중 하나를 골라라 — 이 가설이 반증되면 되돌아갈 자리다.")
		}
		// 제안 A (AIL #1) — 복합가설 열거 거부. 한 hypothesis 는 한 주장이어야 한다: verdict 는
		// 하나뿐이라, H1·H2·H3 를 한 가설에 담으면 H1만 반증돼도 정직하게 표현할 수 없다(반증
		// 은폐). --falsify 가 개행이나 세미콜론으로 명백히 열거되면 거부하고, 주장별 형제
		// hypothesis 로 갈라 부분반증을 "가지의 부분 생존"으로 표현하게 한다.
		if countClaims(*falsify) > 1 {
			die("거부: --falsify 가 여러 주장으로 열거됐다 — 한 가설=한 주장이어야 한다(verdict 는 하나뿐). " +
				"주장마다 형제 hypothesis 로 갈라라: gil step " + ref + " --kind hypothesis --to " + *falsifyTo +
				" --falsify <주장1> …  → H1은 죽은 잎, H2/H3은 산 잎으로 부분반증이 그래프에 정직히 남는다(AIL #1).")
		}
		// 극성 값 검사(AIL #13). 빈값=goal-met(기본, 비파괴).
		if *ifSupported != "" && *ifSupported != "goal-met" && *ifSupported != "goal-missed" {
			die("거부: --if-supported 는 goal-met|goal-missed 중 하나 — 이 가설이 supported 면 사이클 목표가 " +
				"달성(goal-met)인가 실패(goal-missed)인가. 부정적 발견(가설 맞음=목표 막힘)이면 goal-missed(AIL #13).")
		}
	} else if strings.TrimSpace(*plan) != "" {
		die("거부: --plan 은 hypothesis 전용이다(가설을 세우기 전에 고정하는 설계, 이슈 #76).")
	} else if *ifSupported != "" {
		die("거부: --if-supported 는 hypothesis 전용이다(가설의 극성).")
	}

	// stepSHA — 이 사이클에서 특정 스텝 id 의 커밋 sha(형제 가지 분기 지점).
	stepSHA := map[string]string{}
	// stepByID·hasChildIn·allStepIDs — 종결 부착 판정(이슈 #59·#60)에 쓴다: 부모가 될 자리가
	// 이미 종결인가, --at 대상이 진짜 매달린 잎인가.
	stepByID := map[string]node{}
	hasChildIn := map[string]bool{}
	allStepIDs := map[string]bool{}
	for _, s := range cycleSteps {
		stepSHA[s.step] = s.sha
		stepByID[s.step] = s
		allStepIDs[s.step] = true
		if s.parent != "" && s.parent != "null" {
			hasChildIn[s.parent] = true
		}
	}

	var parent string
	var mergeRest []string
	var branch, createFrom string // 분기할 때만 채움(진짜 git 브랜치)
	atReturnTo := ""              // --at 이 잠시 옮겨가기 전의 자리(이슈 #67)
	if strings.TrimSpace(*at) != "" {
		if cur, err := gitTry("symbolic-ref", "--quiet", "--short", "HEAD"); err == nil &&
			strings.TrimSpace(cur) != "" {
			atReturnTo = strings.TrimSpace(cur)
		} else {
			atReturnTo = strings.TrimSpace(git("rev-parse", "HEAD"))
		}
	}
	switch {
	case supTgt != nil:
		// 정정 = 그 자리에서 분기. 부모는 **정정 대상의 부모**이고, git 브랜치를 새로 판다 —
		// 그래야 옛 가지(대상 + 그 자손 전부)가 손대지 않은 채 남는다.
		parent = orNull(supTgt.parent)
		n := 1
		for gitOK("rev-parse", "--verify", "-q", "refs/heads/"+stepBranch(chain, cycle, supTgt.step, n)) {
			n++
		}
		branch = stepBranch(chain, cycle, supTgt.step, n)
		// 분기 지점 = 대상의 부모 커밋. 대상이 사이클의 뿌리(define s1)면 그 앞 커밋(사이클이
		// 열린 자리)에서 가른다 — 그래야 새 define 이 옛 define 의 자손이 되지 않는다.
		if p := strings.TrimSpace(supTgt.parent); p != "" && p != "null" {
			createFrom = stepSHA[p]
		}
		if createFrom == "" {
			if root, err := gitTry("rev-parse", "--verify", "-q", supTgt.sha+"^"); err == nil && strings.TrimSpace(root) != "" {
				createFrom = strings.TrimSpace(root)
			} else {
				createFrom = supTgt.sha // 그 앞이 없으면(루트 커밋) 대상 자리에서 가른다
			}
		}
	case len(*merge) > 0:
		// 스텝 머지: 한 사이클 안 산 잎들을 합류(역순 머지 맨 아래). 완성만 대상.
		for _, m := range *merge {
			if !liveLeaves[m] {
				die("거부: --merge " + m + "는 산 잎(analyze/success)이어야 함 (완성만 머지 대상, 죽은 잎은 벽의 지도)")
			}
		}
		parent = (*merge)[0]
		mergeRest = (*merge)[1:]
	case *kind == "hypothesis" && *to != "":
		// 형제 가지를 새로 내는 것도 **떠나는 것**이다(이슈 #78). 직전 자리가 미종결이면
		// 그 잎은 해석도 종결도 없이 매달린다 — goto 와 같은 검사를 여기서도 건다.
		if lv, blocked := leavingUnterminated(); blocked && !*leaveOpen && lv.step != *to {
			// 경합이면 막지 않는다(이슈 #106·#107). 떠나는 잎이 **같은 자리에서 겨루던 형제**이고
			// 새로 내는 것도 그 경합의 한 갈래면, 이건 잊고 떠나는 것이 아니라 나란히 세우는 것이다.
			if !*competing || !inCompetition(lv, *to) {
				extra := ""
				if *competing {
					extra = "\n  · 경합으로 나란히 세우려면 **첫 가지도** --competing 으로 선언돼 있어야 한다" +
						"(지금 " + lv.step + " 은 아니다)."
				} else {
					extra = "\n  · 동시에 겨루려는 것이면 그건 미종결이 아니다 — 두 가지 모두 --competing 으로 선언하라:" +
						"\n      gil step " + ref + " --kind hypothesis --to " + *to + " … --competing   (형제마다 반복)"
				}
				die(unterminatedRefusal(lv, "gil step "+ref+" --kind hypothesis --to "+*to+" … --leave-open") + extra)
			}
			stderr("  ⚖ 경합 — " + lv.step + " 을 열어 둔 채 " + *to + " 에서 형제 가지를 하나 더 낸다.")
			stderr("    경합은 유예지 면제가 아니다: 사이클을 닫으려면 모든 갈래가 success/fail 로 끝나야 한다.")
		}
		// analyze 를 두고 떠나는 백트랙은 막지 않는다(재분기의 뿌리일 수 있다) — 대신 그 잎이
		// 종결 없이 남는다는 사실을 그 자리에서 말한다(이슈 #86). 옛 안내는 backtrack 을 fail 과
		// **동급의 대안**으로 읽히게 했고, 실사용에서 두 번 다 그렇게 읽혔다.
		if tip != nil && tip.kind == "analyze" && tip.step != *to && tip.outcome == "" {
			stderr("  ⚠ " + tip.step + " [analyze] 를 두고 떠난다 — 이 잎은 종결 없이 남는다(이슈 #86).")
			stderr("    backtrack 은 fail 의 대안이 아니다. 이 가지를 접는 것이면 그 자리에 벽을 남겨라:")
			stderr("      gil step " + ref + " --kind fail --at " + tip.step + " --to <조상 define|analyze> --toward … --next-design …")
			stderr("    안 남기면 gil close 가 거부한다(닫힌 사이클의 모든 잎은 success/fail/pending).")
		}
		// 되돌아가 새 형제 가지 — 조상 define(또는 analyze) 커밋에서 진짜 git 브랜치를 분기.
		//
		// analyze 앵커(이슈 #32). 반증에는 두 층위가 있다: (1) 가설 자체가 틀림 — define 완전
		// 회귀가 옳다. (2) 가설은 맞고 구현·방법만 틀림 — 이때 define 까지 되돌리면 **그 사이
		// 밝혀낸 분석을 버리는 일**이 된다. 옛 문법은 앵커를 define 으로만 받아, analyze 가
		// "가설은 유효하고 방법이 틀렸다"를 밝혀도 새 가설은 define 에서만 갈라졌다 — 분석의
		// 결론이 재분기의 뿌리가 되지 못하는 병목. 그래서 조상 analyze 도 앵커로 받는다.
		// (analyze 는 원인을 밝힌 노드다 — 거기서 갈라지면 그 분석 위에 새 가설이 선다.)
		if !defineIDs[*to] && !analyzeIDs[*to] {
			die("거부: --to " + *to + "는 조상 define 또는 analyze 여야 함 (재분기의 뿌리)\n" +
				"  이 사이클의 define: " + strings.Join(sortedIDs(defineIDs), " ") + "\n" +
				"  이 사이클의 analyze: " + strings.Join(sortedIDs(analyzeIDs), " ") +
				elsewhereHint(chain, cycle, *to, steps) + "\n" +
				"  · 가설 자체가 틀렸다면 → define 으로 완전 회귀.\n" +
				"  · 가설은 맞고 방법만 틀렸다면 → 그걸 밝힌 analyze 로 (분석을 버리지 마라, 이슈 #32).")
		}
		parent = *to
		// 그 define 에서 이미 몇 개의 형제 가지가 났는지 세어 유일한 이름을 만든다.
		n := 1
		for gitOK("rev-parse", "--verify", "-q", "refs/heads/"+stepBranch(chain, cycle, *to, n)) {
			n++
		}
		branch = stepBranch(chain, cycle, *to, n)
		createFrom = stepSHA[*to]
	case *outcome == "backtrack":
		if *to == "" {
			die("거부: backtrack은 --to <조상 define|analyze> 필요 (되돌아갈 곳)")
		}
		// analyze 도 받는다(이슈 #76 후속). hypothesis 의 --to(#60)와 fail 의 --to(#76)는 이미
		// analyze 를 받는데 backtrack 만 define 을 고집했다 — 같은 뜻("되돌아갈 자리")을 세
		// 문법이 서로 다르게 받으면, 사람은 세 번 배우고 한 번은 틀린 자리를 적는다.
		if !defineIDs[*to] && !analyzeIDs[*to] {
			die("거부: --to " + *to + " 는 조상 define 또는 analyze 여야 함 (이 벽에서 되돌아갈 자리)\n" +
				"  이 사이클의 define: " + strings.Join(sortedIDs(defineIDs), " ") + "\n" +
				"  이 사이클의 analyze: " + strings.Join(sortedIDs(analyzeIDs), " ") +
				elsewhereHint(chain, cycle, *to, steps) + "\n" +
				"  · 문제 정의 자체로 돌아가야 하면 → define.\n" +
				"  · 문제 정의는 옳고 **거기서 내려진 결정**이 틀렸으면 → 그 결정이 선 analyze (이슈 #76).")
		}
		parent = orNull(tipID) // 죽은 잎은 현재 가지 tip 에 그대로 박는다(벽의 지도)
	case *kind == "fail" && strings.TrimSpace(*to) == "pending":
		// 지도를 **미정으로** 남긴다(이슈 #105). 다음 재분기(또는 사람의 판정)가 그 자리를
		// 확정한다. 빈 칸이 아니라 "아직 모른다"는 선언이라, 읽는 쪽은 이 벽을 근거로
		// 아무 자리나 고르지 않는다.
		parent = orNull(tipID)
	case *kind == "fail":
		// 종결 죽은 잎 — 현재 가지 tip(또는 --at 이 가리킨 잎)에 박고, 되돌아갈 자리를
		// --to 로 기록. --to 는 여기서 *부모를 바꾸지 않는다* — "되돌아갈 곳"의 기록일 뿐이다
		// (hypothesis 의 --to 와 뜻이 다르다, 이슈 #59①). 자리를 고르는 건 --at 이다.
		//
		// analyze 도 받는다(이슈 #76). #60 이 hypothesis 의 --to 를 analyze 까지 넓힌 논거가
		// 여기에도 그대로 선다 — 실사용 보고: 일곱 가지를 먹은 잘못된 전제가 심긴 자리는
		// s1(문제 정의)이 아니라 s4(analyze)였다. 문제 정의도 지표도 틀리지 않았는데 도구는
		// define 만 받아, 되돌아갈 곳의 기록이 **실제로 돌아가야 할 곳**을 가리키지 못했다.
		// 벽의 지도는 "어디로 돌아가야 하나"의 지도다 — 그 자리가 analyze 면 analyze 를 적어야 한다.
		if !defineIDs[*to] && !analyzeIDs[*to] {
			die("거부: --to " + *to + " 는 조상 define 또는 analyze 여야 함 (이 벽에서 되돌아갈 자리)\n" +
				"  이 사이클의 define: " + strings.Join(sortedIDs(defineIDs), " ") + "\n" +
				"  이 사이클의 analyze: " + strings.Join(sortedIDs(analyzeIDs), " ") +
				elsewhereHint(chain, cycle, *to, steps) + "\n" +
				"  · 문제 정의 자체로 돌아가야 하면 → define.\n" +
				"  · 문제 정의는 옳고 **거기서 내려진 결정**이 틀렸으면 → 그 결정이 선 analyze (이슈 #76).")
		}
		parent = orNull(tipID)
	default:
		// success·analyze·verify 등 선형 진행: 현재 가지 tip 에 이어서.
		parent = orNull(tipID)
	}

	// --at 의 자리 잡기는 위에서 이미 검증했다(이슈 #59) — 여기선 분기 지점만 정한다.
	//
	// 끝나면 **원래 서 있던 자리로 돌아온다**(이슈 #67). 종결을 박는 건 한 커밋짜리 일이고,
	// 사용자는 "두고 온 잎을 닫는다"고 했지 "그 가지로 옮겨간다"고 하지 않았다. 옛 동작은
	// 죽은 가지에 세워둔 채 끝나, 다음 재분기가 "조상이 아니다"로 거부당하고서야 위치가
	// 바뀐 걸 알게 했다 — 게다가 돌아올 gil 경로가 없어 raw git 으로 내려가야 했다.
	if strings.TrimSpace(*at) != "" {
		parent = *at
		n := 1
		for gitOK("rev-parse", "--verify", "-q", "refs/heads/"+stepBranch(chain, cycle, *at, n)) {
			n++
		}
		branch = stepBranch(chain, cycle, *at, n)
		createFrom = stepSHA[*at]
	}

	// 종결 스텝 뒤 부착 금지(이슈 #60①). success/fail 잎에 다음 스텝이 조용히 이어 붙으면
	// "이 가지는 여기서 끝났다"는 뜻이 사라지고, 뷰어에서도 잎으로 안 보인다. 이어갈 길은
	// 이미 있다 — 조상 define/analyze 에서 형제 가지를 내는 것(--to). 문제는 안 써도 조용히
	// 통과된다는 점이었다: 같은 상황에서 한 번은 --to 를 썼고 두 번은 빠뜨렸는데 도구가 두
	// 경우를 구분해 주지 않았다(상현님 실사용).
	if parent != "" && parent != "null" {
		if p, ok := stepByID[parent]; ok && (isLiveLeafKind(p.kind) || p.kind == "fail") {
			die("거부: " + parent + " 는 종결 스텝이다(kind=" + p.kind + ") — 그 뒤에 이어 붙일 수 없다.\n" +
				"  종결은 잎이다: 거기 이어 붙이면 '이 가지는 끝났다'는 뜻이 사라진다.\n" +
				"  이어가려면 갈래를 새로 내라(그러면 " + parent + " 는 진짜 잎으로 남는다):\n" +
				"    gil step " + ref + " --kind " + *kind + " --to <조상 define|analyze> --inherit <이 갈래의 교훈>\n" +
				"  이 사이클이 끝났으면 닫아라: gil close " + ref + " --verdict solved|dead")
		}
	}

	// 스텝 번호는 **사이클 전체**에서 매긴다(HEAD 계보가 아니라). 형제 가지가 있으면 HEAD
	// 계보에는 다른 가지의 스텝이 안 보여, 같은 번호가 두 번 발급된다 — 실제로 --at 으로
	// 두고 온 가지를 닫은 뒤 산 가지로 돌아와 재분기하니 s8 이 둘 생겼다(이슈 #67 수정 중 발견).
	// 번호는 사이클 안에서 유일해야 계보 참조(--to, Gil-Parent)가 뜻을 잃지 않는다.
	sid := nextStepID(cycleAnywhere(chain, cycle))
	stTitle := *title
	if stTitle == "" {
		stTitle = *kind
	}
	subject := "gil " + chain + "/" + cycle + "/" + sid + " " + *kind + ": " + stTitle
	stBody := resolveBody(*body, *bodyFile)
	if stBody == "" {
		stBody = orDefault(*title, *kind)
	}
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
		{"Gil-Step", sid}, {"Gil-Kind", *kind}, {"Gil-Parent", parent},
	}
	if *kind == "hypothesis" {
		tr = append(tr, [2]string{"Gil-Falsify", *falsify})       // 반증조건(벽의 지도의 씨앗)
		tr = append(tr, [2]string{"Gil-Falsify-To", *falsifyTo}) // 반증 시 되돌아갈 define
		pol := *ifSupported
		if pol == "" {
			pol = "goal-met" // 기본(비파괴) — 대부분 가설은 supported=목표 달성
		}
		tr = append(tr, [2]string{"Gil-Goal-Polarity", pol}) // 가설 극성(AIL #13)
	}
	if *kind == "hypothesis" {
		tr = append(tr, [2]string{"Gil-Plan", strings.TrimSpace(*plan)})         // 가설 전에 고정한 설계(이슈 #76)
		tr = append(tr, [2]string{"Gil-Advances", strings.TrimSpace(*advances)}) // 체인 목적에 다가서는 몫
	}
	if *kind == "success" || *kind == "fail" {
		tr = append(tr, [2]string{"Gil-Toward", strings.TrimSpace(*toward)})           // 얼마나 가까워졌나(회고)
		tr = append(tr, [2]string{"Gil-Next-Design", strings.TrimSpace(*nextDesign)}) // 다음 설계
	}
	if *kind == "verify" {
		tr = append(tr, [2]string{"Gil-Verdict", *verdict}) // supported|refuted (제안 1)
		if m := strings.TrimSpace(*falsifyMet); m != "" {
			tr = append(tr, [2]string{"Gil-Falsify-Outcome", "met"})
			tr = append(tr, [2]string{"Gil-Falsify-Observed", m})
		} else if u := strings.TrimSpace(*falsifyUnmet); u != "" {
			tr = append(tr, [2]string{"Gil-Falsify-Outcome", "unmet"})
			tr = append(tr, [2]string{"Gil-Falsify-Observed", u})
		}
		if *planHeld {
			tr = append(tr, [2]string{"Gil-Plan-Outcome", "held"})
		} else if b := strings.TrimSpace(*planBroke); b != "" {
			tr = append(tr, [2]string{"Gil-Plan-Outcome", "broke"})
			tr = append(tr, [2]string{"Gil-Plan-Diff", b}) // 무엇이 설계와 달랐나
		}
	}
	for _, rf := range *refutes {
		tr = append(tr, [2]string{"Gil-Refutes", rf}) // 소급 반증 간선(AIL #1 B)
	}
	for _, rf := range *refines {
		tr = append(tr, [2]string{"Gil-Refines", rf}) // 정밀화 간선(이슈 #42)
	}
	if strings.TrimSpace(*inherit) != "" {
		tr = append(tr, [2]string{"Gil-Inherit", *inherit}) // 물려받은 전수(AIL #3)
	}
	if strings.TrimSpace(*finding) != "" {
		tr = append(tr, [2]string{"Gil-Finding", strings.TrimSpace(*finding)}) // analyze 의 결론
	}
	if strings.TrimSpace(*despite) != "" {
		// 벽의 지도를 벗어난 재분기 — 그 판단을 그래프에 남긴다(어긴 것이 아니라 고친 것이다).
		tr = append(tr, [2]string{"Gil-Despite-Map", strings.TrimSpace(*despite)})
	}
	if *competing {
		// 경합의 뿌리 = 이 형제들이 함께 갈라진 자리(이슈 #106·#107). 선언이 있어야 fsck 가
		// "잊고 떠난 잎"과 "겨루는 중인 갈래"를 가른다.
		tr = append(tr, [2]string{"Gil-Competing", *to})
	}
	if strings.TrimSpace(*supersede) != "" {
		tr = append(tr, [2]string{"Gil-Supersedes", *supersede}) // 스텝 정정 간선(AIL #12)
	}
	if *outcome != "" {
		tr = append(tr, [2]string{"Gil-Outcome", *outcome})
	}
	if *outcome == "backtrack" || *kind == "fail" {
		tr = append(tr, [2]string{"Gil-Backtrack", *to}) // 되돌아갈 곳(벽의 지도)
	}
	for _, m := range mergeRest {
		tr = append(tr, [2]string{"Gil-Merge", m})
	}
	// 형제 가지면 새 브랜치 분기(createFrom), 아니면 현재 사이클 가지에 이어서.
	// 선형 append(분기 아님)은 HEAD 를 대상 사이클 팁으로 맞춘다 — 다른 사이클 브랜치가
	// 체크아웃된 상태에서 조작해도 옳은 계보에 얹히도록(이슈 #44). 분기(branch!="")는
	// commitOn 이 createFrom 에서 스스로 체크아웃하므로 건드리지 않는다.
	if branch == "" && tip != nil {
		alignHeadToTip(tip.sha, ref)
	}
	commitOn(branch, createFrom, subject, stBody, tr, true)

	tail := ""
	switch {
	case *outcome == "backtrack":
		tail = " ⤳backtrack→" + *to
	case *kind == "hypothesis" && *to != "":
		tail = " (형제 가지 ←" + *to + ")"
	case len(*merge) > 0:
		tail = " ⋈merge " + strings.Join(*merge, "+")
	}
	if strings.TrimSpace(*at) != "" && atReturnTo != "" {
		// 원래 자리로 복귀(이슈 #67). 분리 HEAD 였으면 그 커밋으로, 브랜치였으면 그 브랜치로.
		git("checkout", "-q", atReturnTo)
	}
	println2("step: " + ref + "/" + sid + " " + *kind + " ←" + parent + tail)
	if len(*refutes) > 0 {
		guideRefutes(*refutes)
	}
	if len(*refines) > 0 {
		guideRefines(*refines)
	}
	// 위치 카드 — 어디에 서 있고, 무슨 근거로, 실패하면 어디로 물러설 수 있나(상현님).
	// 옛 "◎ 체인 목적 / ◎ 다가서려는 몫" 되풀이를 **흡수한다**(순증이 아니라 재배치).
	if cp := chainPurpose(chain, "--branches"); cp != "" {
		stderr("  ◎ 체인 [" + chain + "] 목적: " + cp)
	}
	if tipNode, ok := justCommitted(chain, cycle, sid); ok {
		for _, ln := range whereCard(chain, cycle, tipNode) {
			stderr(ln)
		}
	}
	if *kind == "success" || *kind == "fail" {
		stderr("  ◎ 이 종결이 남긴 회고 — 목적에 다가선 정도: " + strings.TrimSpace(*toward))
		stderr("  ◎ 다음 설계(다음 세대가 물려받는다): " + strings.TrimSpace(*nextDesign))
		stderr("    누적 컨텍스트 전체는: gil context " + ref)
	}
	// 반증조건이 아닌 이유로 기각됐다 — 거부하지 않는다. 이건 **정보**다: 내가 정한 반증조건이
	// 틀렸다는 뜻이라, 다음 가설의 --falsify 를 고쳐야 한다는 신호다. 막으면 이 사실이 사라진다.
	if u := strings.TrimSpace(*falsifyUnmet); u != "" && *verdict == "refuted" {
		stderr("  ⚠ 반증조건은 충족되지 않았는데 refuted 다 — 이 가설은 **내가 정한 조건이 아닌 이유로** 틀렸다.")
		stderr("    그건 반증조건 자체가 잘못 잡혔다는 뜻이다. 다음 가설의 --falsify 를 그 실제 이유로 고쳐라.")
		stderr("    (이번 조건을 소급해 고치지는 마라 — 그러면 그래프가 사후에 유리해진다.)")
	}
	if b := strings.TrimSpace(*planBroke); b != "" {
		// 깨진 설계는 실패가 아니라 신호다 — 그 신호가 가리키는 자리를 그 자리에서 말한다(이슈 #76).
		stderr("  ⚙ 고정한 설계가 깨졌다: " + b)
		stderr("    이건 실패가 아니라 신호다 — 다음 analyze 에서 **왜 설계가 깨졌나**를 먼저 해석하라.")
		stderr("    설계가 깨진 자리가 곧 되돌아갈 자리다: 그 결정이 선 analyze/define 으로 --to 를 잡아라.")
		stderr("    다음 가설에서는 다시 **몇 개일지 추정하지 말고 몇 개로 만들지 정하라**(--plan).")
	}
	// 되돌아와 새로 판 가지에는 **묻지 않아도** 지금까지 민 벽 전부가 도착해야 한다.
	// 계보가 갈라지는 자리는 셋(open·backtrack·merge)인데 자동 브리핑은 open 에만 있었다 —
	// 실측으로 확인한 구멍이다. backtrack 은 정의상 "앞선 시도가 실패해서 여기 왔다"는
	// 자리라, 앞선 시도가 안 보이면 그 자리에 선 이유 자체가 안 보인다. 그리고 이 목록은
	// 되돌아올 때마다 쌓인다 — 세 번째 가지는 첫째·둘째 벽을 함께 본다.
	if *kind == "hypothesis" {
		// **가설을 세우는 자리에는 무조건 전문이 온다**(선형이든 재분기든, 상현님). 새 가설은
		// 정확히 "이미 민 벽"을 알아야 하는 자리다 — 여기서 안 보여주면 다음 가지가 같은 벽을
		// 다시 민다. 옛 코드는 재분기(--to)에만 줬다.
		for _, ln := range lineageBrief(chain, cycle) {
			stderr(ln)
		}
	} else if walls := deadAttempts(chain, cycle, ""); len(walls) > 0 {
		// 그 외 스텝에는 **한 줄 넛지**만. 매 커밋마다 벽 전문을 뿌리면 화면을 덮고, 덮으면
		// 읽히지 않는다(#85 의 교훈: 영구 패널이 지금 살아 있는 국면을 가린다). 그러나 침묵도
		// 답이 아니다 — 있다는 사실과 펼치는 법은 언제나 그 자리에 있어야 한다.
		n := 0
		for _, w := range walls {
			if strings.Contains(w, "✖ 접힌 시도") {
				n++
			}
		}
		if n > 0 {
			stderr("  ↺ 이 사이클에서 이미 민 벽 " + itoa(n) + "개 — 펼쳐라: gil context " + ref)
		}
	}
	reportGuide(*kind, bodyThin(stBody))
	guideNext(*kind) // 다음 강제 스텝을 무조건 각인 (AIL #41)
	// 결론이 선택지를 세었으면 **그 수를 그대로 되돌려준다**(이슈 #107 1b). 일반 안내는
	// 흘려 읽히지만 "선택지가 셋으로 읽힌다"는 자기 글을 인용당하는 것이라 잘 안 흘러간다.
	if *kind == "analyze" {
		if n := countedOptions(strings.TrimSpace(*finding) + "\n" + stBody); n >= 2 {
			stderr("  ⚖ 이 결론에서 선택지가 " + itoa(n) + "개로 읽힌다 — " + itoa(n) +
				"개를 형제 가설로 **동시에** 낼 수 있다(--competing).")
			stderr("    하나만 고르면 나머지 " + itoa(n-1) + "개는 검증되지 않은 채 남는다. 고르는 것은 측정 뒤의 일이다.")
		}
	}
}

// pendingTip — 이 사이클의 팁이 pending 이면 그 pending 노드를, 아니면 nil.
// approve/reject 는 pending 팁에서만 동작한다(사람의 답이 필요한 지점).
func pendingTip(chain, cycle string) *node {
	steps := currentCycle(chain, cycle)
	tip := growingTip(steps)
	if tip != nil && tip.kind == "pending" {
		return tip
	}
	return nil
}

// ── gil approve — pending 에 대한 사람의 명시적 승인. 승인=산 잎(analyze/success). ──
func cmdApprove(args []string) {
	fs := newFlags("gil approve")
	// --by <chain/cycle/step> (이슈 #85). pending 은 사람만 풀 수 있다(AIL #41) — 그 원칙은
	// 그대로다. 다만 사람이 승인하는 대상이 "이 물음에 지금 답하라"가 아니라 **"이 후속이
	// 답이 맞나"** 일 수 있다. 몇 달 전 물음을 사람이 맨손으로 판단하게 두지 않는다.
	by := fs.str("by", "")
	title := fs.str("title", "")
	body := fs.str("body", "")
	bodyFile := fs.str("body-file", "")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil approve <chain>/<cycle> [--title T]")
	}
	ref := pos[0]
	chain, cycle, _ := cut(ref, "/")
	tip := pendingTip(chain, cycle)
	if tip == nil {
		die("거부: " + ref + " 팁이 pending 이 아니다 — 승인할 대기가 없다")
	}
	sid := nextStepID(cycleAnywhere(chain, cycle))
	stTitle := orDefault(*title, "승인 — "+tip.step+" 의 대기를 사람이 승인")
	subject := "gil " + chain + "/" + cycle + "/" + sid + " success: " + stTitle
	stBody := resolveBody(*body, *bodyFile)
	if b := strings.TrimSpace(*by); b != "" {
		resolveAnsweredIn(b)
		if stBody == "" {
			stBody = "사람이 pending(" + tip.step + ")을 승인했다 — 이 가지는 산 잎.\n\n" +
				"근거: 이 물음의 답은 **" + b + "** 에서 이미 났다(이슈 #85). 사람은 '지금 답하라'가 아니라\n" +
				"'이 후속이 답이 맞나'를 판단해 승인했다."
		}
	}
	if stBody == "" {
		stBody = "사람이 pending(" + tip.step + ")을 승인했다 — 이 가지는 산 잎."
	}
	// pending 은 부모가 될 수 없다(AIL #41, 상현님) — pending 을 부모로 삼는 대신, pending 의
	// 부모를 이어받고 pending 자체는 Gil-Supersedes 로 대체(정정). pending 은 잎으로 남고
	// "⤳정정됨" 표시되며, 이 success 가 진짜 종결이 된다. 사람 답 없이 열린 채 두는 꼼수 차단.
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
		{"Gil-Step", sid}, {"Gil-Kind", "success"}, {"Gil-Parent", orNull(tip.parent)},
		{"Gil-Approval", "approved"}, {"Gil-Supersedes", tip.step},
	}
	if b := strings.TrimSpace(*by); b != "" {
		tr = append(tr, [2]string{"Gil-Answered-By", b}) // 무엇을 근거로 닫았나(이슈 #85)
	}
	alignHeadToTip(tip.sha, ref) // 대상 사이클 팁으로 HEAD 정합 — 승인 커밋이 옳은 계보에(이슈 #44)
	commit(subject, stBody, tr, true)
	println2("approve: " + ref + "/" + sid + " success (사람 승인 ⤳정정 " + tip.step + ")")
	reportGuide("success", bodyThin(stBody))
	guideNext("success")
}

// ── gil reject — pending 에 대한 사람의 명시적 기각. 기각=죽은 잎(analyze/backtrack). ──
func cmdReject(args []string) {
	fs := newFlags("gil reject")
	to := fs.str("to", "")
	title := fs.str("title", "")
	body := fs.str("body", "")
	bodyFile := fs.str("body-file", "")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil reject <chain>/<cycle> --to <조상 define> [--title T]")
	}
	ref := pos[0]
	chain, cycle, _ := cut(ref, "/")
	tip := pendingTip(chain, cycle)
	if tip == nil {
		die("거부: " + ref + " 팁이 pending 이 아니다 — 기각할 대기가 없다")
	}
	if *to == "" {
		die("거부: reject 는 --to <조상 define> 필요 (되돌아갈 곳)")
	}
	steps := currentCycle(chain, cycle)
	defineIDs, analyzeIDs := map[string]bool{}, map[string]bool{}
	for _, s := range steps {
		if s.kind == "define" {
			defineIDs[s.step] = true
		}
		if s.kind == "analyze" {
			analyzeIDs[s.step] = true
		}
	}
	if !defineIDs[*to] && !analyzeIDs[*to] {
		die("거부: --to " + *to + " 는 조상 define 또는 analyze 여야 함 (기각 뒤 되돌아갈 자리)\n" +
			"  이 사이클의 define: " + strings.Join(sortedIDs(defineIDs), " ") + "\n" +
			"  이 사이클의 analyze: " + strings.Join(sortedIDs(analyzeIDs), " ") + "\n" +
			"  · 문제 정의 자체로 돌아가야 하면 → define.\n" +
			"  · 문제 정의는 옳고 **거기서 내려진 결정**이 틀렸으면 → 그 결정이 선 analyze (이슈 #76).")
	}
	sid := nextStepID(cycleAnywhere(chain, cycle))
	stTitle := orDefault(*title, "기각 — "+tip.step+" 의 대기를 사람이 기각")
	subject := "gil " + chain + "/" + cycle + "/" + sid + " fail: " + stTitle
	stBody := resolveBody(*body, *bodyFile)
	if stBody == "" {
		stBody = "사람이 pending(" + tip.step + ")을 기각했다 — 죽은 잎. " + *to + " 로 되돌아간다."
	}
	// pending 은 부모가 될 수 없다(AIL #41) — pending 의 부모를 잇고 pending 은 supersede(정정).
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
		{"Gil-Step", sid}, {"Gil-Kind", "fail"}, {"Gil-Parent", orNull(tip.parent)},
		{"Gil-Backtrack", *to}, {"Gil-Approval", "rejected"}, {"Gil-Supersedes", tip.step},
	}
	alignHeadToTip(tip.sha, ref) // 대상 사이클 팁으로 HEAD 정합 — 기각 커밋이 옳은 계보에(이슈 #44)
	commit(subject, stBody, tr, true)
	println2("reject: " + ref + "/" + sid + " fail (사람 기각 ⤳정정 " + tip.step + " ⟶" + *to + ")")
	reportGuide("fail", bodyThin(stBody))
	guideNext("fail")
}

// ── gil close ──
func cmdClose(args []string) {
	fs := newFlags("gil close")
	verdict := fs.str("verdict", "supported")
	// --abandon: 산 잎 없이 fail 잎만 남은 사이클을 '죽은 사이클'로 봉인한다(이슈 #46).
	// fail = 이 가설의 죽음이지 사이클의 죽음이 아니다 — 기본은 define 의 답을 얻을 때까지
	// 재분기해야 한다(hypothesis --to <조상 define>). 하지만 사람이 그 define 을 포기하기로
	// 판단하면(막다른 길로 확인됨), 죽은 사이클도 종결의 한 형태다. 그 판단을 --abandon 으로
	// 명시적으로 받는다 — gil 이 자동으로 죽이지 않는다(정직: 없는 성공을 날조하지도, 정직한
	// 실패를 영구 미종결로 벌하지도 않는다). success=산 종결, fail-only+abandon=죽은 종결.
	abandon := fs.boolFlag("abandon")
	// --answered-in <chain/cycle/step> (이슈 #85, 상현님 실사용). 죽은 잎만 남았는데 그 물음의
	// **답이 다른 자리에서 난** 경우가 있다. 옛 어휘는 둘뿐이었다 — 재분기 아니면 --abandon(막다른
	// 길). 그래서 답이 옆 가지에서 난 사이클도 --abandon 으로 적혔고, 기록이 사실보다 어둡게
	// 남았다("도구가 보증하는 정보가 아니라 내가 성실했기를 바라는 정보다").
	// #80 이 목표 어휘에서 지적한 것과 같은 결핍이고 방향만 반대다: 거기선 성공을 부풀릴 압력,
	// 여기선 실패로 눌러 적을 압력. 답이 난 자리로 **선이 남는다**.
	answeredIn := fs.str("answered-in", "")
	// --goal-met (이슈 #62): 목표를 선언하고 연 사이클은, 닫을 때 그 목표에 **답해야** 한다.
	// 선언이 없으면 닫는 판단이 다시 자기확신으로 돌아간다 — 잎이 다 종결됐다는 사실만으로
	// "됐다"가 되던 자리를 이 한 마디가 막는다.
	goalMet := fs.boolFlag("goal-met")
	// 결말의 어휘를 넓힌다(이슈 #80). goal-met 과 abandon 사이가 비어 있어, "일부 달성 + 나머지는
	// 원리적 불가"를 적을 자리가 없었다 — 그 자리에서 **목표를 유리하게 재해석할 압력**이 생긴다.
	// 보고자는 정당한 독해로 빠져나왔지만 문구가 조금만 달랐으면 거짓 기록이 됐을 것이라고 적었다.
	// 어휘가 부족하면 기록이 거짓말한다.
	goalPartial := fs.str("goal-partial", "")       // 무엇을 못 했는지(필수 인자) — 그 조각이 그래프에 남는다
	goalImpossible := fs.str("goal-impossible", "") // 원리적 달성 불가를 **확인**했다 — 실패가 아니라 발견
	// --reason <왜 접나> (이슈 #115 후속): 죽은 잎 없이 --abandon 할 때 필수. 포기 선언 자체가
	// 종결이지만, **왜** 접는지가 없으면 나중에 그것이 판단이었는지 방치였는지 모른다.
	reason := fs.str("reason", "")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil close <chain>/<cycle> [--verdict V] [--goal-met|--goal-partial <못 한 것>|--goal-impossible <이유>] [--abandon]")
	}
	ref := pos[0]
	chain, cycle, _ := cut(ref, "/")
	steps := currentCycle(chain, cycle)
	if len(steps) == 0 {
		die("거부: " + ref + " 없음")
	}
	// **산 잎은 사이클 그래프 전체에 있다** — 지금 밟고 있는 가지에만 있는 게 아니다(이슈 #106 g).
	//
	// 형제 가설을 병렬로 내면 이긴 가지와 진 가지가 서로 다른 브랜치에 산다. 진 가지에 서서
	// 닫으려 하면 옛 코드는 "산 잎 없음"으로 거부했다 — 어디서 닫느냐에 따라 같은 사이클의
	// 판정이 달라진 것이다. 사이클의 상태는 무엇을 체크아웃했는지에 달린 것이 아니다(#44 가
	// step 에서 세운 원칙을 close 에도 세운다).
	if !anyLiveLeaf(steps) {
		if sha := liveLeafAnywhere(chain, cycle); sha != "" {
			stderr("  ▸ 이 가지엔 산 잎이 없다 — 산 잎은 형제 가지(" + first9(sha) + ")에 있다. 그 자리로 옮겨 닫는다.")
			alignHeadToTip(sha, ref)
			steps = currentCycle(chain, cycle)
		}
	}
	var live, dead []string
	for _, s := range steps {
		if isLiveLeaf(s) {
			live = append(live, s.step)
		} else if isDeadLeaf(s) {
			dead = append(dead, s.step)
		}
	}
	if len(live) == 0 {
		// 산 잎이 없다. --abandon 이면 죽은 사이클로 봉인(이슈 #46), 아니면 두 정직한 길을 안내.
		if ai := strings.TrimSpace(*answeredIn); ai != "" {
			if len(dead) == 0 {
				die("거부: 종결 잎(fail)이 하나도 없다 — 아직 닫을 가지가 없다. 먼저 analyze→fail 로 벽을 남겨라.")
			}
			resolveAnsweredIn(ai) // 그 자리가 실재하는지 — 없는 곳을 가리키는 선은 거짓말이다
			sort.Strings(dead)
			subject := "gil " + chain + "/" + cycle + " close: answered-elsewhere"
			body := "이 사이클의 물음은 여기서 못 풀렸다(죽은 잎 [" + strings.Join(dead, " ") + "]). " +
				"그러나 막다른 길이 아니다 — **그 답은 " + ai + " 에서 났다.**\n\n" +
				"막다른 길(--abandon)과 구별해 적는다: 이 define 은 답을 얻었고, 얻은 자리가 여기가 아닐 뿐이다.\n" +
				"읽는 쪽은 이 선을 따라 답으로 갈 수 있다(이슈 #85)."
			tr := [][2]string{
				{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
				{"Gil-Kind", "close"}, {"Gil-Verdict", orDefault(*verdict, "answered-elsewhere")},
				{"Gil-Answered-In", ai},
			}
			commit(subject, body, tr, true)
			println2("close: " + ref + " — answered-elsewhere (답이 난 자리: " + ai + ")")
			println2("  이 사이클은 막다른 길이 아니다 — 그래프에 답으로 가는 선이 남았다.")
			return
		}
		if *abandon {
			// **포기 선언 자체가 종결이다**(이슈 #115 후속). 옛 코드는 fail 잎을 또 요구했고,
			// 그 중복이 생애주기 한 바퀴(hypothesis→verify→analyze→fail)를 걷게 만들었다 —
			// verify 는 `--verdict` 를 요구하니 **하지 않은 측정의 판정**을 쓰라는 압력이 된다.
			// 실사용에서 정확히 그 벽에 부딪혔다: 잘못된 자리에서 열린 사이클(도구가 뒤처짐을
			// 안 짚어 준 탓에 생긴 것)을 정직하게 접을 문법이 없었다. 결함이 만든 쓰레기를
			// 결함이 못 치우게 막은 셈이다.
			//
			// 그래서 죽은 잎이 없어도 접는다 — 다만 **왜 접는지는 남는다**(--reason).
			// 그 이유가 벽의 지도다. 이유 없는 포기는 나중에 아무도 그것이 판단이었는지
			// 방치였는지 모른다(gil adopt --reason 과 같은 논거).
			folded := []string{} // 이 포기가 접는 미종결 잎들 — 없는 것과 안 적은 것은 다르다
			hasKid := map[string]bool{}
			for _, s := range steps {
				if s.parent != "" {
					hasKid[s.parent] = true
				}
			}
			for _, s := range steps {
				if !hasKid[s.step] && !isDeadLeaf(s) && !isLiveLeaf(s) && s.kind != "pending" {
					folded = append(folded, s.step)
				}
			}
			sort.Strings(dead)
			sort.Strings(folded)
			if len(dead) == 0 && strings.TrimSpace(*reason) == "" {
				die("거부: 죽은 잎이 하나도 없는 사이클을 접으려면 **왜 접는지**를 적어라 — --reason <왜 접나>\n" +
					"  gil close " + ref + " --abandon --reason \"<이 사이클을 여기서 접는 이유>\"\n" +
					"  (없는 관측의 판정을 만들어 fail 잎을 박지 마라 — 그건 기록을 밝게 위조하는 것이다.\n" +
					"   포기 선언 자체가 종결이고, 그 이유가 벽의 지도로 남는다.)")
			}
			subject := "gil " + chain + "/" + cycle + " close: " + orDefault(*verdict, "abandoned") + " (abandoned)"
			body := "죽은 사이클 봉인(abandoned)."
			if len(dead) > 0 {
				body += " 죽은 잎 [" + strings.Join(dead, " ") + "]."
			} else {
				body += " 죽은 잎 없음 — 포기 선언이 이 사이클의 종결이다."
			}
			if len(folded) > 0 {
				body += " 이 포기가 접는 미종결 잎 [" + strings.Join(folded, " ") + "]."
			}
			body += "\n\n이 define 은 막다른 길로 판단돼 사람이 포기했다 — 벽의 지도로 영원히 남는다(이슈 #46)."
			if r := strings.TrimSpace(*reason); r != "" {
				body += "\n\n왜 접나: " + r
			}
			tr := [][2]string{
				{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
				{"Gil-Kind", "close"}, {"Gil-Verdict", orDefault(*verdict, "abandoned")},
				{"Gil-Abandoned", "true"},
			}
			if r := strings.TrimSpace(*reason); r != "" {
				tr = append(tr, [2]string{"Gil-Abandon-Reason", foldTrailerValue(r)})
			}
			for _, f := range folded {
				tr = append(tr, [2]string{"Gil-Abandoned-Leaf", f})
			}
			commit(subject, body, tr, true)
			where := "죽은 잎 [" + strings.Join(dead, " ") + "]"
			if len(dead) == 0 {
				where = "죽은 잎 없음 — 포기 선언이 종결이다"
			}
			println2("close: " + ref + " — abandoned (죽은 사이클로 봉인, " + where + ")")
			if len(folded) > 0 {
				println2("  이 포기가 접은 미종결 잎: " + strings.Join(folded, " ") + " (fsck 가 다시 짚지 않는다)")
			}
			return
		}
		die("거부: 산 잎(success 스텝) 없음 — 닫을 수 없다.\n" +
			"  fail 은 이 가설의 죽음이지 사이클의 죽음이 아니다. 세 정직한 길:\n" +
			"    (1) 재분기 — gil step " + ref + " --kind hypothesis --to <조상 define> --inherit <교훈>\n" +
			"        (이 define 의 답을 아직 못 얻었다 — 새 가설로 다시 푼다)\n" +
			"    (2) 답이 옆에서 났다 — gil close " + ref + " --answered-in <chain/cycle/step>\n" +
			"        (여기선 못 풀렸지만 그 물음의 답이 다른 자리에서 났다 — 그 자리로 선이 남는다, 이슈 #85)\n" +
			"    (3) 포기 — gil close " + ref + " --abandon\n" +
			"        (이 define 이 **막다른 길로 확인**됐다 — 죽은 사이클로 봉인, 벽의 지도로 남긴다)\n" +
			"  (2)와 (3)을 구별해라. 답이 난 걸 포기로 적으면 기록이 사실보다 어둡게 남는다.")
	}
	// 미종결 잎 검사(이슈 #86) — fsck 가 잡던 것을 close 도 잡는다.
	//
	// 왜. 백트랙으로 떠난 가지의 analyze 잎이 종결 없이 남아도 close 가 조용히 통과했다.
	// 그러면 에이전트는 사이클이 끝났다고 인지하고, 결함은 누군가 fsck 를 돌릴 때까지 잠복한다.
	// **집행이 두 자리에서 갈리면 느슨한 쪽이 실질 규칙이 된다** — close 가 최종 방어선이다.
	{
		// **그래프 전체**를 본다(fsck 와 같은 범위). HEAD 계보만 보면 백트랙으로 떠난 형제
		// 가지의 매달린 잎이 통째로 안 보인다 — 이 이슈가 정확히 그 경우였다.
		all := cycleAnywhere(chain, cycle)
		hasChild := map[string]bool{}
		for _, n := range all {
			if n.parent != "" && n.parent != "null" {
				hasChild[n.parent] = true
			}
		}
		// 정정으로 대체된 구버전 가지(대상+자손)는 종결 요구 대상이 아니다 — 이미 갈아엎은
		// 가지의 잎을 닫으라고 요구하면 사람은 뜻 없는 fail 을 박게 된다.
		goneKeys := supersededSet(all)
		var hanging []node
		seenLeaf := map[string]bool{}
		for _, n := range all {
			if seenLeaf[n.step] {
				continue // 번호 중복(옛 그래프) — 같은 번호를 두 번 짚지 않는다
			}
			if hasChild[n.step] || goneKeys[stepKey(n.chain, n.cycle, n.step)] {
				continue
			}
			switch n.kind {
			case "success", "fail", "pending":
				continue
			}
			if isLiveLeaf(n) || isDeadLeaf(n) {
				continue // 옛 문법(analyze --outcome success/fail/backtrack)도 종결로 인정
			}
			seenLeaf[n.step] = true
			hanging = append(hanging, n)
		}
		if len(hanging) > 0 {
			var lines []string
			for _, n := range hanging {
				lines = append(lines, "    "+n.step+" ["+n.kind+"] "+n.subject)
			}
			sort.Strings(lines)
			first := hanging[0]
			die("거부: 미종결 잎이 남았다 — 닫힌 사이클의 모든 잎은 success/fail/pending 이어야 한다.\n" +
				strings.Join(lines, "\n") + "\n" +
				"  백트랙으로 떠난 가지가 대개 이렇다: 해석까지 하고 떠나면 그 자리엔 종결이 없다(이슈 #86).\n" +
				"  그 자리에 종결을 박아라(지금 서 있는 가지를 떠나지 않는다):\n" +
				"    gil step " + ref + " --kind fail --at " + first.step + " --to <조상 define|analyze> \\\n" +
				"      --toward <목적에 얼마나 다가섰나> --next-design <다음 설계>\n" +
				"  (이 검사는 gil fsck 와 같은 것이다 — 집행이 두 자리에서 갈리면 느슨한 쪽이 실질 규칙이 된다.)")
		}
	}
	// 극성 close 대면 (AIL #13, 옵션 B — success 가드의 이중 방어). 산 잎(success)이 딛은
	// verify 가 supported 인데 그 가설의 극성이 goal-missed 면, 이 사이클은 "목표 실패를 확인"한
	// 것이라 success 로 봉인하면 안 된다. success 가드(step 시점)를 우회했거나 옛 데이터라도
	// close 에서 한 번 더 잡는다. (가설 supported ≠ 사이클 목표 달성.)
	stepByID := map[string]*node{}
	for i := range steps {
		stepByID[steps[i].step] = &steps[i]
	}
	for _, lid := range live {
		leaf := stepByID[lid]
		if leaf == nil || leaf.kind != "success" {
			continue
		}
		vf := stepByID[leaf.parent] // success 의 부모 = verify
		if vf == nil || vf.kind != "verify" || vf.verdict != "supported" {
			continue
		}
		hyp := stepByID[vf.parent] // verify 의 부모 = hypothesis
		if hyp != nil && hyp.kind == "hypothesis" && hyp.polarity == "goal-missed" {
			die("거부: 산 잎 " + lid + " 는 goal-missed 가설(" + hyp.step + ")이 supported 된 위에 섰다 — " +
				"목표 실패를 확인한 걸 success 로 봉인할 수 없다. 그 잎을 fail 로 남기거나 backtrack 하라(AIL #13).")
		}
	}
	// 목표 대면(이슈 #62): 열 때 --goal 을 선언했다면 닫을 때 그 목표에 답해야 한다.
	// gil 은 목표 달성 여부를 알 수 없다 — 알 수 있는 건 "답했는가"뿐이고, 그것만 강제한다
	// (정직 강제 불가, 은폐 영속화만 차단). 목표에 못 닿았다면 닫지 말고 더 파거나,
	// 그 define 을 포기하는 것이면 --abandon 이 정직한 자리다.
	goalPartialTxt := strings.TrimSpace(*goalPartial)
	goalImpossibleTxt := strings.TrimSpace(*goalImpossible)
	answered := *goalMet || goalPartialTxt != "" || goalImpossibleTxt != ""
	// 자기모순 조합을 막는다(이슈 #80 제안 3): 하나의 결말만 고를 수 있다.
	if n := boolCount(*goalMet, goalPartialTxt != "", goalImpossibleTxt != ""); n > 1 {
		die("거부: 목표에 대한 답은 하나여야 한다 — --goal-met | --goal-partial | --goal-impossible 중 하나만.")
	}
	// verdict 와 목표 답을 맞춘다. 옛 게이트는 이분법이라 --goal-met --verdict partial 같은
	// **자기모순 조합이 통과했다**(보고자가 실제로 그렇게 닫았다). partial 은 partial 로 적어야 한다.
	if *goalMet && strings.TrimSpace(*verdict) == "partial" {
		die("거부: --goal-met 과 --verdict partial 은 같이 설 수 없다 — '다 달성했다'와 '일부만'이다.\n" +
			"  일부만 달성했다면 그렇게 적어라: gil close " + ref + " --goal-partial \"<무엇을 못 했는지>\" --verdict partial\n" +
			"  (결말의 어휘가 둘뿐이면 정직하지 않은 쪽으로 반올림된다 — 이슈 #80.)")
	}
	if g := cycleGoal(chain, cycle, "--branches"); g != "" && !answered {
		die("거부: 이 사이클은 열 때 목표를 선언했다 — 닫으려면 그 목표에 답해라.\n" +
			"    목표: " + g + "\n" +
			"  · 목표에 닿았다면:      gil close " + ref + " --goal-met\n" +
			"  · **일부만 닿았다면**:  gil close " + ref + " --goal-partial \"<무엇을 못 했는지>\" --verdict partial\n" +
			"      (달성과 포기 사이가 비어 있으면 목표를 유리하게 재해석할 압력이 생긴다 — 이슈 #80)\n" +
			"  · **원리적으로 불가함을 확인했다면**: gil close " + ref + " --goal-impossible \"<왜 불가한가>\"\n" +
			"      (이건 실패가 아니라 **발견**이다 — 다음 사이클의 근거가 된다. --abandon 으로 묻지 마라)\n" +
			"  · 아직 못 닿았고 더 팔 수 있다면 닫지 마라 — 갈래를 더 내라:\n" +
			"      gil step " + ref + " --kind hypothesis --to <조상 define|analyze> --inherit <여기까지의 교훈>\n" +
			"  · 이 define 자체가 막다른 길이었다면: gil close " + ref + " --abandon\n" +
			"  ('잎이 다 종결됐다'는 '목표가 달성됐다'와 다르다 — 이슈 #62.)")
	}
	sort.Strings(live)
	subject := "gil " + chain + "/" + cycle + " close: " + *verdict
	body := "사이클 봉인. 산 잎 [" + strings.Join(live, " ") + "]. 판정: " + *verdict + "."
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
		{"Gil-Kind", "close"}, {"Gil-Verdict", *verdict},
	}
	if g := cycleGoal(chain, cycle, "--branches"); g != "" {
		// 목표에 **어떻게** 답했는지를 그래프에 남긴다(이슈 #80). 못 한 조각·불가 사유가
		// 산문에 묻히면 다음 사이클이 그 값을 못 쓴다.
		switch {
		case goalPartialTxt != "":
			tr = append(tr, [2]string{"Gil-Goal-Met", "partial"}, [2]string{"Gil-Goal-Gap", goalPartialTxt})
			body += "\n목표(열 때 선언): " + g + "\n→ **일부 달성**으로 닫는다(--goal-partial).\n못 한 것: " + goalPartialTxt
		case goalImpossibleTxt != "":
			tr = append(tr, [2]string{"Gil-Goal-Met", "impossible"}, [2]string{"Gil-Goal-Gap", goalImpossibleTxt})
			body += "\n목표(열 때 선언): " + g + "\n→ **원리적 달성 불가를 확인**하고 닫는다(--goal-impossible).\n" +
				"이건 실패가 아니라 발견이다: " + goalImpossibleTxt
		default:
			tr = append(tr, [2]string{"Gil-Goal-Met", "true"}) // 목표에 답했다는 선언(이슈 #62)
			body += "\n목표(열 때 선언): " + g + "\n→ 달성했다고 선언하고 닫는다(--goal-met)."
		}
	}
	commit(subject, body, tr, true)
	println2("close: " + ref + " — " + *verdict)
	for _, ln := range mergeIntoChainHint(chain, cycle) {
		println2(ln)
	}
	// **다음이 하나여야 할 이유가 없다.** 닫힌 사이클은 자식을 여럿 낳을 수 있고(같은 --parent
	// 로 여러 번 연다), 그게 gil 이 그리려는 사고의 모양이다. 그런데 안내가 늘 한 갈래만
	// 가리켜서, 에이전트는 갈래가 여럿일 때 사람에게 "하나만 골라 달라"고 묻거나 일자로
	// 이어붙였다(상현님 실사용). 문법에 있는 것을 안내가 안 보여주면 없는 것과 같다.
	println2("NEXT 다음 사이클은 이 끝에서 난다 — **하나일 필요는 없다**:")
	println2("      gil open " + chain + "/<다음> --parent " + cycle + " --inherit <무엇을 물려받나> --purpose <작은 문제>")
	println2("    ▸ 이 결론에서 갈래가 둘 이상이면 **사람에게 '하나만 고르라'고 묻지 마라 — 다 밟아라.**")
	println2("      한 가지를 열어 끝까지 밟고 닫은 뒤 **같은 --parent " + cycle + " 로 다시 열면** 형제로 갈라진다.")
	println2("      한 번에 하나만 열리는 것은 제약이 아니라 원리다 — git 도 두 브랜치를 동시에 밟으려면")
	println2("      워크트리가 필요하다. **갈래는 동시가 아니라 차례로 낸다** — 갈래의 수는 제한이 없다.")
	println2("      그렇게 갈라 둔 뒤 살아남은 것들을 합치는 것이 이 도구가 그리려는 모양이다:")
	println2("        gil merge " + chain + "/<가지A> " + chain + "/<가지B> --into " + chain + " --reason <왜 한 줄기가 되나>")
}

// mergeIntoChainHint — 닫은 사이클의 **산출물 파일**이 체인 트리에 없으면, 합류 경로를 준다
// (이슈 #103, 에이전트 자기 분석).
//
// 실사용에서 에이전트는 앞 사이클의 산출물을 다음 사이클로 넘길 때 `git checkout <브랜치> --
// <경로>` **트리 복사**를 반복했다. 내용은 안 잃었지만 합류 간선이 안 남아 — *"지식과 코드를
// 이어받는다"는 gil 의 핵심이 파일 층위에서 사라졌다.*
//
// 왜 그렇게 됐나: 체인→dev 에는 합류 안내가 있는데 **사이클→체인에는 없었다.** 그리고
// 계보 브리핑(inherit·finding)은 자동으로 도착하니 "승계는 처리되고 있다"는 착시가 생긴다 —
// 파일이 조용히 빠진 것을 가린다. 결핍은 다음 사이클 **한복판에서** 발견되고, 그 자리에서
// 가장 싼 해결책이 트리 복사다.
//
// 그래서 **결핍이 생기는 순간에** 말한다. 그리고 조건 없이 늘 짖지 않는다 — 실제로 체인에
// 없는 파일이 있을 때만. 없으면 이 사이클은 문서만 남긴 것이고, 합류할 것이 없다.
func mergeIntoChainHint(chain, cycle string) []string {
	cyRef := chain + "-" + cycle
	if !gitOK("rev-parse", "--verify", "-q", "refs/heads/"+cyRef) {
		return nil
	}
	if !gitOK("rev-parse", "--verify", "-q", "refs/heads/"+chain) {
		return nil
	}
	// 이미 체인에 합류돼 있으면 할 말이 없다.
	if gitOK("merge-base", "--is-ancestor", cyRef, chain) {
		return nil
	}
	out, err := gitTry("diff", "--name-only", chain, cyRef)
	if err != nil {
		return nil
	}
	var files []string
	for _, f := range strings.Split(strings.TrimSpace(out), "\n") {
		if f = strings.TrimSpace(f); f != "" {
			files = append(files, f)
		}
	}
	if len(files) == 0 {
		return nil
	}
	sort.Strings(files)
	shown := files
	more := ""
	if len(shown) > 4 {
		more = "  … 그리고 " + itoa(len(shown)-4) + "개 더"
		shown = shown[:4]
	}
	L := []string{
		"  ⌂ 이 사이클의 산출물 " + itoa(len(files)) + "개가 **체인 트리에 없다** — 다음 사이클은 이 파일들을 못 본다:",
	}
	for _, f := range shown {
		L = append(L, "      " + f)
	}
	if more != "" {
		L = append(L, "    " + more)
	}
	return append(L,
		"NEXT 산출물을 체인 층으로 합류시켜라 — 그래야 다음 사이클이 **이어받는다**:",
		"      gil merge " + chain + "/" + cycle + " --into " + chain + " --reason <왜 이 산출물이 체인의 것인가>",
		"    (여기서 안 하면 다음 사이클 한복판에서 파일이 없는 걸 발견하고 트리 복사로 때우게 된다 —",
		"     내용은 옮겨지지만 합류 간선이 안 남아 그래프에서 승계가 사라진다.)")
}

// strandedCycles — 이 체인에서 '미해결로 방치된' 사이클들(이슈 #45). 정의: 산 잎(success)이
// 하나도 없고, 죽은 잎(fail)이 하나 이상이며, 아직 close 커밋이 없는 사이클. 그런 사이클의
// define 은 답을 못 얻은 채(fail 후 재분기도, abandon 봉인도 없이) 남아 있다. cmdOpen 이
// 새 사이클을 열 때 이걸 경고해 계보가 끊기는 걸 막는다. cmdClose 의 live/dead 판정과 대칭.
func strandedCycles(chain string) []string {
	closed := closedCycles("--branches")
	cyc, order := cyclesOf(chain)
	var out []string
	for _, id := range order {
		if closed[chain+"\x01"+id] {
			continue // 이미 닫힘(abandon 포함) — 방치 아님
		}
		c := cyc[id]
		hasLive, hasDead := false, false
		for _, s := range c.steps {
			if isLiveLeaf(s) {
				hasLive = true
			} else if isDeadLeaf(s) {
				hasDead = true
			}
		}
		if !hasLive && hasDead {
			out = append(out, id)
		}
	}
	return out
}

// inFlightCycles — 이 체인에서 **아직 밟고 있는 중인** 사이클들(상현님, 2026-07-28).
//
// 왜. 지금까지 gil 은 "fail 잎만 남은 미해결 사이클"(#45)만 막았다. 그래서 define·hypothesis·
// verify·analyze 어디서든 손을 놓고 다음 사이클을 열 수 있었다 — 사이클이 종결 잎 없이 허공에
// 매달린 채 남고, 그래프는 "여기서 무슨 생각을 하다 말았는지"를 영영 못 말한다. 사이클은
// **success/fail 로 끝나고 close 된 뒤**에만 다음이 열린다는 것이 gil 의 문법이다.
//
// pending(사람 대기)도 미종결이다 — 다만 나갈 길이 다르다(사람의 approve/reject).
// 반환: 사이클 id → 지금 서 있는 자리(스텝 id·kind).
func inFlightCycles(chain string) ([]string, map[string]node) {
	closed := closedCycles("--branches")
	_ = graphNodes() // 아래 cyclesOf 와 같은 그래프를 쓰도록 캐시를 데운다
	cyc, order := cyclesOf(chain)
	var out []string
	tips := map[string]node{}
	for _, id := range order {
		if closed[chain+"\x01"+id] {
			continue // 닫혔다(abandon 포함) — 이 사이클은 끝났다
		}
		c := cyc[id]
		// 잎(=자식 없는 스텝) 중 **종결이 아닌 것**이 하나라도 있으면 아직 밟는 중이다.
		// success/fail 은 끝난 잎이고(success 는 close 만 남았다 — 부모 닫힘 규칙이 지킨다),
		// 그 밖의 잎(define·hypothesis·verify·analyze·pending)은 손을 놓은 자리다.
		best := node{}
		for _, s := range cycleLeaves(c.steps) {
			if s.kind == "success" || isDeadLeaf(s) {
				continue
			}
			if best.step == "" || stepNum(s.step) > stepNum(best.step) {
				best = s
			}
		}
		if best.step != "" {
			out = append(out, id)
			tips[id] = best
		}
	}
	return out, tips
}

// resolveAnsweredIn — "답이 난 자리"가 실재하는지 확인한다(이슈 #85). 없는 곳을 가리키는
// 선은 산문보다 나쁘다 — 구조로 보증한다고 해놓고 거짓을 가리킨다.
func resolveAnsweredIn(ref string) {
	parts := strings.Split(strings.TrimSpace(ref), "/")
	if len(parts) != 3 {
		die("거부: 답이 난 자리는 <chain>/<cycle>/<step> 꼴이어야 한다 — 받음: " + ref)
	}
	for _, n := range collectNodes("--all") {
		if n.chain == parts[0] && n.cycle == parts[1] && n.step == parts[2] {
			return
		}
	}
	die("거부: " + ref + " 를 그래프에서 찾지 못했다 — 답이 난 자리는 실재해야 한다.\n" +
		"  (gil log --depth step " + parts[0] + " 로 스텝 이름을 확인하라.)")
}

// ── gil deploy — 배포(공개) 지점을 그래프의 1급 시민으로 (이슈 #34, 상현님) ──
//
// 사고 그래프는 "무엇을 생각했나"는 다 보여주지만 "무엇을 언제 세상에 내보냈나"는 안 보였다.
// 배포는 되돌리기 어려운 외부 행위이자 결정적 분기점인데 지도에 흔적이 없었다(v0.1.0·v0.2.0이
// 어느 스텝에서 나갔는지 그래프상 0). deploy 는 특정 스텝에 "여기서 배포됨" 마커를 얹는다 —
// 새 사고 노드가 아니라 기존 노드에 대한 주석이라, Gil-Step 을 달지 않고 Gil-Deploy 계열
// 트레일러만 실은 얇은 커밋으로 남긴다(추론 그래프 불변). 뷰어가 대상 노드에 🚀 배포 마커 +
// 태그 라벨을 렌더한다.
//
// 자동 감지(git tag→노드 매핑) 대신 명시적 명령을 택했다(상현님 선호): 배포는 의도적 행위라
// "언제 왜 배포했나"를 배포 시점에 스텝처럼 남기는 게 사고 그래프 정신에 맞다. 자동 감지는
// "왜"를 담지 못한다.
func cmdDeploy(args []string) {
	fs := newFlags("gil deploy")
	at := fs.str("at", "")
	tag := fs.str("tag", "")
	url := fs.str("url", "")
	// --target: **어디에** 올라갔나(서비스 엔드포인트·호스트·환경). 이슈 #56 의 v2 레지스터가
	// 갖고 있던 칸이 v3 마커엔 없었다 — 태그는 "무엇을"이고 target 은 "어디로"다. 둘이 있어야
	// "v2.1.0 이 어디로 갔나"가 그래프에서 읽힌다(#79·#81 이 측정에 한 것과 같은 모양).
	// 도달 확인(헬스체크)은 하지 않는다: gil 은 기록 도구지 외부를 찌르는 도구가 아니다.
	// 확인은 사람·CI 가 하고, 그 결과를 --promote 로 선언한다(근거는 --body-file 로 본문에).
	deployTarget := fs.str("target", "")
	title := fs.str("title", "")
	body := fs.str("body", "")
	bodyFile := fs.str("body-file", "")
	// --state staged|live (이슈 #56, 다른 레포 실사용). 배포 단위를 확정했는데 실제 롤아웃은
	// 조율 때문에 몇 주 뒤인 구간이 구조적으로 길다. 그 사이 "여기서 세상으로 나갔다"고 적으면
	// 기록이 거짓이 된다 — 보고자는 그래서 notes 에 rollout_state=staged 라는 필드를 손으로
	// 발명해 정정하고 있었다. 상태 필드가 거짓이라 자유서술로 덮는 건, 기계가 못 읽는다.
	state := fs.str("state", "live")
	// --promote: staged 로 찍어둔 배포가 실제로 올라갔음을 잇는다(append-only — 앞 마커를
	// 고치지 않고 새 마커로 승격을 남긴다. 언제 준비됐고 언제 올라갔나가 둘 다 남는다).
	promote := fs.boolFlag("promote")
	// --no-promote: 승격 없이 마커만. dev→main 이 CI·사람 손에 있는 저장소를 위한 자리다
	// (gil 은 기록 도구지 남의 배포 파이프라인을 빼앗는 도구가 아니다).
	noPromote := fs.boolFlag("no-promote")
	// 대문으로 건너기 전 확인(checks.go). SPEC 7 의 '엄밀한 테스트는 배포 앞에서' 자리다.
	skipCheck := fs.boolFlag("skip-check")
	skipReason := fs.str("skip-reason", "")
	// --force --reason: 산 잎 없는 배포의 정당한 예외(문서 전용 배포 등). 이슈 #108.
	// 이유는 배포 커밋 본문에 남는다 — 이유 없는 강행은 나중에 '산 잎이 있었다'와 구별되지 않는다.
	force := fs.boolFlag("force")
	forceReason := fs.str("reason", "")
	fs.parse(args)
	if *tag == "" {
		die("사용: gil deploy --tag <v0.2.0> [--at <chain>/<cycle>/<step>] [--state staged|live]\n" +
			"           [--promote] [--no-promote] [--target <host:port·환경>] [--url <릴리스URL>]\n" +
			"           [--force --reason <산 잎 없이 내보내는 이유>]\n" +
			"  배포 = dev 를 대문(main)에 올리는 일이다. --at 은 '어느 스텝에서 잘랐나'를 함께 남긴다.")
	}
	if *promote {
		*state = "live"
	}
	if *state != "staged" && *state != "live" {
		die("거부: --state 는 staged|live — 받음: \"" + *state + "\"\n" +
			"  staged = 배포 단위는 확정됐으나 아직 안 올라갔다(조율 대기).\n" +
			"  live   = 실제로 올라갔다. 나중에 올라가면: gil deploy --at … --tag " + *tag + " --promote")
	}
	// --at 파싱·검증: 주면 chain/cycle/step 세 조각이 다 있어야 하고 그 스텝이 실재해야 한다.
	// 안 주는 것도 정상이다 — 배포 단위가 여러 체인의 합류(dev)일 때는 가리킬 스텝 하나가 없다.
	if strings.TrimSpace(*at) != "" {
		chain, rest, ok := cut(*at, "/")
		if !ok {
			die("거부: --at 은 <chain>/<cycle>/<step> 형식 (받음: " + *at + ")")
		}
		cycle, step, ok := cut(rest, "/")
		if !ok || step == "" {
			die("거부: --at 은 <chain>/<cycle>/<step> 형식 — 스텝까지 지정하라 (받음: " + *at + ")")
		}
		var target *node
		for _, s := range currentCycle(chain, cycle) {
			if s.step == step {
				t := s
				target = &t
				break
			}
		}
		if target == nil {
			die("거부: --at " + *at + " 스텝이 없다 — 배포 마커는 실재하는 스텝에만 얹는다")
		}
	}
	// ── 산 잎 검사 (이슈 #108) ────────────────────────────────────────────────
	// close 가 집행하던 것을 배포도 집행한다. 두 자리에서 규칙이 갈리면 느슨한 쪽이 실질
	// 규칙이 되고, 병렬 형제 가지에서는 죽은 가지가 더 많은 게 정상이라 잘못 짚기 쉽다.
	// 판정은 이름이 아니라 사실로 — 머지의 둘째 부모까지 훑어 실제 산 잎을 찾는다.
	deployedLeaf, anyStep := deployLiveLeaf(*at)
	if deployedLeaf == "" && anyStep {
		if !*force {
			die("거부: 배포 계보에 산 잎(success 스텝)이 없다 — 내보낼 수 없다.\n" +
				"  죽은 잎만 있는 계보는 '무엇이 됐나'를 말하지 못한다. 어느 산 잎을 내보내려 했나?\n" +
				"    (1) 산 잎이 다른 가지에 있다 — 그 가지를 먼저 합류시켜라: gil merge <chain> --into " + devBranchName + "\n" +
				"    (2) 아직 산 잎이 없다 — 사이클을 success 로 종결하고 닫아라(gil close)\n" +
				"    (3) 잎이 필요 없는 배포다(문서·설정 전용) — gil deploy --tag " + *tag + " --force --reason <왜>\n" +
				"  (3)의 이유는 배포 커밋에 남는다 — 나중에 '산 잎이 있었다'와 구별되게.")
		}
		if strings.TrimSpace(*forceReason) == "" {
			die("거부: --force 에는 --reason <왜 산 잎 없이 내보내나> 가 필요하다.\n" +
				"  이유 없는 강행은 기록에서 정상 배포와 구별되지 않는다.")
		}
	}
	// --at 이 없으면 "어디서"는 층이다 — 여러 체인이 dev 에 모여 함께 나가는 게 기본형이다.
	where := strings.TrimSpace(*at)
	if where == "" {
		where = devBranchName
	}
	defTitle := "배포 " + *tag + " — " + where + " 에서 세상으로"
	if *state == "staged" {
		defTitle = "배포 준비 " + *tag + " — " + where + " (staged, 아직 안 올라감)"
	} else if *promote {
		defTitle = "배포 승격 " + *tag + " — staged 였던 것이 실제로 올라갔다"
	}
	stTitle := orDefault(*title, defTitle)
	subject := "gil deploy " + *tag + ": " + stTitle
	dBody := resolveBody(*body, *bodyFile)
	if dBody == "" {
		if *state == "staged" {
			dBody = "배포 단위 확정(staged): " + where + " 에서 " + *tag + " 를 자를 준비가 됐다. " +
				"아직 올라가지 않았다 — 실제 롤아웃 시 --promote 로 승격한다."
		} else if *promote {
			dBody = "배포 승격(live): " + *tag + " 가 실제로 올라갔다(앞서 staged 로 확정된 단위)."
		} else {
			dBody = "배포 지점: " + where + " 에서 " + *tag + " 를 공개했다."
		}
		if *url != "" {
			dBody += " (" + *url + ")"
		}
	}
	tr := [][2]string{
		{"Gil-Deploy", *tag},
		{"Gil-Deploy-State", *state}, // staged|live (이슈 #56) — 기계가 읽는 상태
	}
	if strings.TrimSpace(*at) != "" {
		tr = append(tr, [2]string{"Gil-Deploy-At", *at}) // 어느 스텝에서 잘랐나(있으면)
	}
	// 무엇을 내보냈나(이슈 #108). 배포 커밋만 봐서는 어느 잎의 결과물인지 알 수 없었다 —
	// 읽는 쪽이 조상을 뒤져 추측하게 두지 않고, 배포한 쪽이 아는 사실을 그대로 적는다.
	if deployedLeaf != "" {
		tr = append(tr, [2]string{"Gil-Deployed-Leaf", deployedLeaf})
	} else if r := strings.TrimSpace(*forceReason); r != "" {
		dBody += "\n\n산 잎 없이 강행(--force). 이유: " + r
	}
	if t := strings.TrimSpace(*deployTarget); t != "" {
		tr = append(tr, [2]string{"Gil-Deploy-Target", t}) // 어디로 나갔나(#56)
	}
	if *url != "" {
		tr = append(tr, [2]string{"Gil-Deploy-Url", *url})
	}
	// ── 대문으로 건너기 전 확인 ────────────────────────────────────────────────
	// 여기서 실패하면 마커도 안 새긴다. 배포는 되돌리기 어려운 외부 행위라, "확인 안 됐는데
	// 기록만 남은 상태"를 만들지 않는다(staged 는 예외 — 아직 안 올라간 것이니까).
	var checkNote string
	if *state == "live" && !*noPromote {
		if *skipCheck && strings.TrimSpace(*skipReason) == "" {
			die("거부: --skip-check 에는 --skip-reason <왜 확인 없이 배포하나> 가 필요하다.\n" +
				"  이유 없는 건너뜀은 나중에 '확인했다'와 구별되지 않는다.")
		}
		_, passed, note := runLayerCheck("main", *skipCheck, *skipReason)
		if !passed {
			die("거부: " + note + "\n  (배포 마커도 새기지 않았다 — 확인 안 된 배포를 기록으로 남기지 않는다.)")
		}
		checkNote = note
		for _, t := range checkTrailers("main", !*skipCheck, *skipCheck, *skipReason) {
			tr = append(tr, t)
		}
	}
	// 마커는 **배포되는 것 위에** 새긴다. 옛 동작은 그때 서 있던 브랜치(대개 작업 중이던
	// 체인)에 찍었는데, 그러면 승격된 대문에는 정작 "배포했다"는 기록이 없다 — 기록과 실재가
	// 또 갈린다. 층이 있으면 dev 에 새기고, 새긴 뒤 원래 자리로 돌아온다.
	backTo := ""
	if hasDevLayer() {
		if cur := strings.TrimSpace(git("rev-parse", "--abbrev-ref", "HEAD")); cur != devBranchName {
			backTo = cur
		}
		commitOn(devBranchName, "", subject, dBody, tr, true)
	} else {
		commit(subject, dBody, tr, true)
	}
	if *state == "staged" {
		println2("deploy: " + *tag + " @ " + where + " 📦 staged — 배포 단위는 확정, 아직 안 올라갔다.")
		println2("  ▸ 실제로 올라가면 승격하라: gil deploy --tag " + *tag + " --promote")
		println2("  ▸ 그 전까지 이 태그는 '배포됨'으로 읽히지 않는다 — 없는 배포를 주장하지 않는다.")
	} else {
		println2("deploy: " + *tag + " @ " + where + " 🚀 (뷰어에 배포 마커로 표시됨)")
		// ── 승격: dev → 대문 ────────────────────────────────────────────────────
		// 마커만 찍고 끝내면 "배포했다"고 적힌 저장소의 main 에는 아무것도 없다. 배포는
		// 기록이 아니라 **이동**이다 — 층과 층 사이의. 여기서 실제로 옮긴다.
		if *noPromote {
			println2("  ⌂ 승격은 건너뛴다(--no-promote) — dev → " + orDefault(homeBranch(), "main") +
				" 는 이 저장소의 CI·사람 손에 있다.")
		} else if ok, why := promoteDevToMain(*tag); ok {
			println2("  ⌂ 승격 완료: dev → " + homeBranch() + " (--no-ff 머지 커밋으로 남았다).")
			println2("     대문에는 배포된 것만 온다 — 이제 그 말이 이 저장소에서 참이다.")
			println2("     작업은 dev 에서 계속한다(HEAD 는 그대로).")
		} else {
			println2("  ⌂ 승격 못 함 — 마커는 새겨졌고 대문은 그대로다: " + why)
		}
	}
	if *url != "" {
		println2("  릴리스: " + *url)
	}
	if checkNote != "" {
		println2("  ⓘ " + checkNote)
	}
	if backTo != "" {
		// 배포했다고 사람을 층에 세워두지 않는다 — 하던 자리로 돌려놓는다.
		gitTry("checkout", "-q", backTo)
		println2("  ▸ 배포 기록은 " + devBranchName + " 에 남았다. 너는 [" + backTo + "] 로 돌아왔다.")
	}
}

// ── gil interview — 사람에게 설문 폼을 띄워 레퍼런스 트루스를 함께 만든다 (이슈 #33) ──
//
// LLM 이 인터뷰 질문 세트를 그래프에 심으면, 뷰어가 그걸 폼으로 렌더한다 — 사람이 문제 풀듯
// 답하고 [제출]을 누르면 답변이 reference-<chain>.md 로 저장되고 그 체인에 레퍼런스로
// 커밋된다(뷰어 서버 POST /interview → gil chain --reference). pending→approve 흐름의 거울:
// 인터뷰 요구 노드는 '사람 대기'이고, 제출이 그걸 해소한다.
//
// 질문은 JSON 으로 받는다(--ask <파일|->): [{"q":"...", "type":"text|radio|checkbox",
// "options":["..."]}]. 구조가 명확해 뷰어가 파싱해 textarea·라디오·체크박스를 그린다.

// interviewQ — 인터뷰 질문 하나. type: text(서술)·radio(택1)·checkbox(다중). options 는
// radio/checkbox 에서만.
type interviewQ struct {
	Q       string   `json:"q"`
	Type    string   `json:"type"`
	Options []string `json:"options,omitempty"`
}

func cmdInterview(args []string) {
	fs := newFlags("gil interview")
	ask := fs.str("ask", "")
	show := fs.boolFlag("show") // --status 에 기준 문서 전문까지(기본은 짧게, 이슈 #94)
	title := fs.str("title", "")
	// --resolve <ref파일>: 인터뷰를 해소한다(뷰어 서버가 사람 제출 후 호출). 답변으로 조립한
	// 레퍼런스 파일을 이 체인에 심고(Gil-Reference) 인터뷰를 done 으로 닫는다. 사람이 CLI 로 직접
	// 쓸 일은 드물다 — 보통 뷰어 폼이 대신 부른다.
	resolve := fs.str("resolve", "")
	// --status/--wait (이슈 #58): 사람이 뷰어 폼에 제출해도 에이전트는 그 사실을 알 방법이 없었다.
	// 유일한 확인 수단이 git show 로 커밋 본문을 읽는 것 — gil 의 추상을 뚫고 내려가는 일이라
	// 에이전트가 스스로 떠올리지 못한다. 그래서 "기다려라"는 안내가 기다릴 수단 없는 지시였고,
	// 바쁜대기(무의미한 git log 반복) 아니면 우회(내가 기준을 쓴다)로 밀었다.
	status := fs.boolFlag("status")
	wait := fs.boolFlag("wait")
	timeout := fs.str("timeout", "")
	// --then <명령>(이슈 #82 제안 3): 제출되는 순간 실행할 명령. 백그라운드 --wait 와 짝이다 —
	// 호스트가 프로세스 완료로 에이전트를 깨우지 못해도, 훅 하나는 확실히 걸린다.
	then := fs.str("then", "")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil interview <chain> --ask <질문JSON|-> [--title T]\n" +
			"  또는: gil interview <chain> --status            (pending|done 한 줄)\n" +
			"  또는: gil interview <chain> --wait [--timeout <초>]  (제출될 때까지 기다렸다 기준 문서를 뱉는다)\n" +
			"  또는: gil interview <chain> --resolve <레퍼런스파일>  (뷰어 제출이 호출)\n" +
			"  질문 형식: [{\"q\":\"질문\",\"type\":\"text|radio|checkbox\",\"options\":[\"...\"]}]")
	}
	chain := pos[0]
	if *resolve != "" {
		interviewResolve(chain, *resolve)
		return
	}
	if *status || *wait {
		if strings.TrimSpace(*then) != "" && !*wait {
			die("거부: --then 은 --wait 와 함께 쓴다 — 기다리지 않으면 이어서 실행할 순간이 없다.")
		}
		interviewWatchOpt(chain, *wait, *timeout, *then, *show)
		return
	}
	if strings.TrimSpace(*then) != "" {
		die("거부: --then 은 --wait 와 함께 쓴다: gil interview " + chain + " --wait --then '<명령>'")
	}
	if *ask == "" {
		die("사용: gil interview <chain> --ask <질문JSON|->  (또는 --resolve <파일>)")
	}
	if !idRe.MatchString(chain) {
		die("거부: 체인 이름 \"" + chain + "\"은 소문자·숫자·하이픈만")
	}
	if chainPurpose(chain, "--branches") == "" && intakeMode != chain {
		die("거부: 체인 \"" + chain + "\" 선언된 적 없음 — 먼저 gil chain 으로 열어라. " +
			"인터뷰는 그 체인의 레퍼런스 트루스를 만드는 과정이다(이슈 #33).\n" +
			"  체인을 **열기 전에** 물으려는 것이면 개시 인터뷰다: gil intake " + chain +
			" --ask <질문JSON>  (이슈 #90)")
	}
	// 인터뷰 pending 잠금(이슈 #33): 이미 사람 답을 기다리는 인터뷰가 있으면 새 인터뷰를 못 심는다.
	// LLM 이 사람 답을 안 기다린 채 "스스로 더 생각해 질문지를 또 만드는" 것을 막는다(상현님 실사용:
	// pending 인데 뷰어는 뷰어대로 pending 이고 LLM 은 또 질문지 만듦 — 두 대기가 따로 놀던 문제).
	if chainInterviewPending(chain, "--branches") {
		die("거부: \"" + chain + "\" 에 사람 답 대기 중인 인터뷰가 이미 있다 — 새 질문지를 또 만들지 마라.\n" +
			"  사람이 뷰어 폼으로 답할 때까지 기다려라(인터뷰=pending 잠금). 답이 오면 기준이 확정되고\n" +
			"  그제서야 다음으로 넘어간다. 스스로 더 생각해 진행하지 마라 — 사람의 답이 기준이다.")
	}
	interviewAsk(chain, *ask, *title, nil)
}


// lastCycleTipOfChain — 이 체인에서 **가장 나중에 열린 사이클**의 팁 커밋. 새 사이클이
// 갈라져 나올 자리다(선언한 --parent 가 없을 때). 사이클이 하나도 없으면 체인 루트,
// 그것도 없으면 "".
//
// "가장 나중"은 git log 순서로 본다 — 사이클 이름은 자유 문자열이라 c10 이 c9 뒤라는 보장이
// 없고, 이름 정렬로 고르면 문자열이 계보를 정하게 된다.
func lastCycleTipOfChain(chain string) string {
	fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Cycle") + fsep + trailer("Gil-Kind") + sep
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches"), sep) {
		ch, rest, ok := cut(strings.TrimSpace(rec), fsep)
		if !ok {
			continue
		}
		cy, kind, _ := cut(rest, fsep)
		if strings.TrimSpace(ch) != chain || strings.TrimSpace(kind) != "define" {
			continue
		}
		if tip := cycleTipSHA(chain, strings.TrimSpace(cy)); tip != "" {
			return tip
		}
	}
	if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+chain) {
		return strings.TrimSpace(git("rev-parse", "refs/heads/"+chain))
	}
	return ""
}

// cycleTipSHA — 그 사이클(또는 체인)의 팁 커밋. 되돌아가 분기를 칠 **실재하는 자리**다.
// 사이클 브랜치 <chain>-<cycle> 이 우선이고, 없으면 같은 이름의 체인 브랜치, 그것도 없으면
// 그 사이클의 마지막 스텝 커밋을 쓴다.
func cycleTipSHA(chain, parent string) string {
	p := strings.TrimSpace(parent)
	if p == "" {
		return ""
	}
	// **이름보다 사실이 먼저다.** 옛 코드는 <chain>-<cycle> 브랜치를 먼저 봤는데, 정정
	// (--supersede)이나 재분기(--to)를 거친 사이클은 척추와 종결이 **분기 브랜치**에 살고
	// 그 이름의 브랜치는 정정된 자리에 멈춰 있다. 그래서 `--parent a2` 로 연 사이클이
	// **버려진 가설 위에서** 갈라졌다 — 복잡한 나무를 지어 git 과 대조해서야 드러났다.
	// 종결(close)이 있으면 그것이 그 사이클의 끝이다.
	if end := cycleEndSHA(chain, p); end != "" {
		return end
	}
	for _, ref := range []string{"refs/heads/" + cycleBranch(chain, p), "refs/heads/" + p} {
		if gitOK("rev-parse", "--verify", "-q", ref) {
			return strings.TrimSpace(git("rev-parse", ref))
		}
	}
	best, bestN := "", -1
	for _, n := range cycleAnywhere(chain, p) {
		if k := stepNum(n.step); k > bestN {
			bestN, best = k, n.sha
		}
	}
	return best
}

// interviewAsk — 질문지를 검증해 심는다. gil interview(체인 인터뷰)와 gil intake
// (체인 앞 개시 인터뷰)가 같은 기계를 쓴다 — 뷰어·폴링·--wait 이 손 안 대고 동작하도록.
// extra 는 심는 커밋에 덧붙일 트레일러(개시 인터뷰의 Gil-Intake 등).
func interviewAsk(chain, ask, title string, extra [][2]string) {
	interviewAskOpt(chain, ask, title, extra, false)
}

// interviewAskOpt — toolAuthored 면 '첫 질문은 열린 질문' 규칙을 면제한다. gil 이 직접 만든
// 마지막 차수(뿌리 후보 선택)만 해당한다 — 후보가 그래프에서 나온 사실이라 앵커가 아니다.
func interviewAskOpt(chain, ask, title string, extra [][2]string, toolAuthored bool) {
	interviewAskCore(chain, resolveAskJSON(ask), title, extra, toolAuthored)
}

// interviewAskInline — 질문 JSON 을 **문자열 그대로** 받는다(파일 경로가 아니다).
// gil 이 직접 조립한 질문지를 심을 때 쓴다.
func interviewAskInline(chain, questionsJSON, title string, extra [][2]string, toolAuthored bool) {
	interviewAskCore(chain, questionsJSON, title, extra, toolAuthored)
}

func interviewAskCore(chain, raw, title string, extra [][2]string, toolAuthored bool) {
	// 질문 JSON 구조를 검증한다 — 빈 폼·잘못된 type 을 뷰어에 보내기 전에 여기서 거부.
	if strings.TrimSpace(raw) == "" {
		die("거부: --ask 질문이 비었다")
	}
	var qs []interviewQ
	if err := json.Unmarshal([]byte(raw), &qs); err != nil {
		die("거부: --ask 는 질문 배열 JSON 이어야 한다: " + err.Error() + "\n" +
			"  예: [{\"q\":\"무엇을 풀려는가\",\"type\":\"text\"}, " +
			"{\"q\":\"성공 기준\",\"type\":\"checkbox\",\"options\":[\"속도\",\"정확도\"]}]")
	}
	if len(qs) == 0 {
		die("거부: 질문이 하나도 없다")
	}
	for i, q := range qs {
		if strings.TrimSpace(q.Q) == "" {
			die("거부: 질문 " + strconv.Itoa(i+1) + " 의 q(질문 텍스트)가 비었다")
		}
		if q.Type != "text" && q.Type != "radio" && q.Type != "checkbox" {
			die("거부: 질문 " + strconv.Itoa(i+1) + " 의 type 은 text|radio|checkbox — 받음: \"" + q.Type + "\"")
		}
		if (q.Type == "radio" || q.Type == "checkbox") && len(q.Options) == 0 {
			die("거부: 질문 " + strconv.Itoa(i+1) + "(" + q.Type + ")은 options 가 필요하다")
		}
	}
	// **첫 질문은 열린 질문이어야 한다** (이슈 #90, 실사용 보고).
	//
	// 왜. 선택지로만 채운 질문지는 **에이전트의 가설 공간 안에서 사람을 고르게 만든다.**
	// 사람은 방향을 정하는 자리가 아니라 이미 정해진 방향을 승인하는 자리에 앉는다 —
	// 그러면 기준 문서는 "사람이 세운 자"가 아니라 "에이전트가 세운 자에 사람이 서명한 것"
	// 이 되고, 그 뒤의 모든 검증은 형식만 남는다(잣대를 재는 자가 잣대를 먼저 깎았으니까).
	//
	// 실사용에서 사람이 방향을 실제로 뒤집은 유일한 지점이 자유 서술 칸이었다:
	//   Q: "이 자율 에이전트는 무엇을 하는 에이전트인가요?"
	//   A: "그게 없는게 자율이야. 스스로 도구를 만들면서 진화할거야."
	// 에이전트가 준 선택지 어디에도 없던 답이고, 체인 전체의 의미를 바꿨다. 닫힌 질문만
	// 있었다면 이 답은 나올 수 없었다.
	openN := 0
	for _, q := range qs {
		if q.Type == "text" {
			openN++
		}
	}
	if (openN == 0 || qs[0].Type != "text") && !toolAuthored {
		die("거부: 인터뷰의 **첫 질문은 열린 질문(text)** 이어야 한다 — 선택지부터 내밀면 " +
			"사람은 네 가설 공간 안에서만 고르게 된다(이슈 #90).\n" +
			"  지금 첫 질문: " + qs[0].Q + "  (" + qs[0].Type + ")\n" +
			"  · 먼저 물어라: {\"q\":\"무엇을 하려고 하십니까? 지금 풀려는 문제를 그대로 적어 주세요\",\"type\":\"text\"}\n" +
			"  · 선택지 질문은 그 **다음**에 둔다 — 열린 답을 받고 나서 좁히는 것이 순서다.\n" +
			"  기준 문서는 '사람이 세운 자'여야 한다. 네가 세운 자에 사람이 서명한 것이 되면 " +
			"그 뒤의 판정은 전부 형식만 남는다.")
	}
	if openN*2 < len(qs) && len(qs) >= 4 && !toolAuthored {
		// 거부까지는 하지 않는다 — 좁혀 묻는 질문 자체가 나쁜 게 아니다. 다만 비율이 기울면
		// 질문지가 앵커로 작동하기 시작하므로 그 자리에서 말해 준다.
		stderr("  ⚠ 열린 질문이 " + itoa(openN) + "/" + itoa(len(qs)) + " 다 — 선택지가 과반이면 " +
			"질문지 자체가 앵커가 된다(이슈 #90). 사람이 네 안 밖으로 나갈 칸을 더 두어라.")
	}
	// JSON 을 정규화해(들여쓰기) 본문에 싣는다 — 뷰어가 펜스 블록에서 추출해 폼을 그린다.
	norm, _ := json.MarshalIndent(qs, "", "  ")
	stTitle := orDefault(title, "인터뷰 — "+chain+" 의 기준 문서를 사람과 함께 만든다")
	subject := "gil " + chain + " interview: " + stTitle
	// 본문: 사람이 읽을 질문 목록 + 뷰어가 파싱할 JSON 펜스. 뷰어가 없어도 사람이 읽을 수 있게.
	var b strings.Builder
	b.WriteString("이 체인의 레퍼런스 트루스(기준 문서)를 만들기 위한 인터뷰다. 뷰어에서 폼으로 답하고\n")
	b.WriteString("제출하면 답변이 reference-" + chain + ".md 로 저장되고 이 체인에 레퍼런스로 심긴다.\n\n")
	b.WriteString("── 질문 ──\n")
	for i, q := range qs {
		b.WriteString(strconv.Itoa(i+1) + ". " + q.Q + "  (" + q.Type + ")\n")
		for _, o := range q.Options {
			b.WriteString("   - " + o + "\n")
		}
	}
	b.WriteString("\n```gil-interview\n")
	b.Write(norm)
	b.WriteString("\n```\n")
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Kind", "interview"},
		{"Gil-Interview", "pending"},
	}
	tr = append(tr, extra...) // 개시 인터뷰면 Gil-Intake 가 여기 붙는다(이슈 #90)
	// 개시 인터뷰(gil intake)인가 — 체인별 인터뷰인가. 앞머리는 체인보다 **먼저** 있는 것이라
	// 어느 체인의 몸도 아니다(이슈 #102). 층이 있으면 dev 에 앉힌다.
	intake := false
	for _, kv := range extra {
		if kv[0] == "Gil-Intake" {
			intake = true
		}
	}
	if intake {
		commitOn(frontMatterBranch(), "", subject, b.String(), tr, true)
		println2("interview: " + chain + " — 질문 " + strconv.Itoa(len(qs)) + "개 심음. 뷰어에서 사람이 폼으로 답한다.")
		interviewAskTail(chain, qs)
		return
	}
	// 체인 브랜치 위에 심는다(레퍼런스가 그 체인에 커밋될 자리). HEAD 가 다른 데면 맞춘다.
	// gitTry 여야 한다: git() 은 실패에 죽고, "브랜치 없음"은 여기서 정상 흐름이다(이슈 #90).
	if raw, err := gitTry("rev-parse", "--verify", "-q", "refs/heads/"+chain); err == nil {
		if tip := strings.TrimSpace(raw); tip != "" {
			alignHeadToTip(first9(tip), chain)
		}
	}
	commit(subject, b.String(), tr, true)
	println2("interview: " + chain + " — 질문 " + strconv.Itoa(len(qs)) + "개 심음. 뷰어에서 사람이 폼으로 답한다.")
	interviewAskTail(chain, qs)
}

// interviewAskTail — 질문을 심은 뒤의 안내. 개시 인터뷰(dev 층)와 체인별 인터뷰가 **같은 말을
// 하도록** 한 자리에 둔다 — 갈라 두면 한쪽만 낡는다.
func interviewAskTail(chain string, qs []interviewQ) {
	println2("  ▸ 뷰어를 열어라(gil viewer serve / VS Code 패널). 사람이 제출하면 reference-" + chain +
		".md 로 저장되고 레퍼런스가 커밋된다 — 폴링이 곧 반영한다.")
	println2("  ▸ 사람 답 전엔 이 기준이 비어 있다 — 답을 기다려라(pending 처럼).")
	// "기다려라"만 말하고 기다릴 수단을 안 주면 바쁜대기 아니면 우회로 민다(이슈 #58). 그리고
	// 수단을 둘 다 나란히 놓으면 싼 쪽(--status 한 번)을 고른다 — 어느 것이 기본인지 못박는다(#77).
	println2("  ▸ **기본은 기다리는 것이다**: gil interview " + chain + " --wait [--timeout <초>]")
	// "말할 수 있는 유일한 길"로 보이는 --status 만 남겨두면 매번 그쪽으로 미끄러진다 —
	// 그리고 그 길은 사람이 한 번 더 말을 걸어야만 이어진다(이슈 #82). 제3의 형태를 먼저 놓는다.
	for _, ln := range backgroundWaitHint(chain) {
		println2(ln)
	}
	println2("  ▸ --status 는 확인용이다(pending|done 한 줄). 한 번 묻고 턴을 끝내는 것으로 갈음하지 마라.")
	println2("     (답이 도착해 있으면 gil 이 어느 명령에서든 맨 앞에 ⚡ 한 줄로 고지한다 — 그래도 네가 먼저 물어라.)")
}

// interviewWatch — 인터뷰가 사람 답을 받았는지 묻는다(--status), 또는 받을 때까지 기다린다(--wait).
//
// 왜 (이슈 #58, 상현님 실사용): 사람이 뷰어 폼에 제출해도 에이전트는 알 방법이 없었다. MCP 툴은
// 요청-응답이라 스스로 깨어나지 못하고, 사람이 말을 걸어주지 않으면 세션이 멈춘다. 그 상태는
// 에이전트를 둘 중 나쁜 쪽으로 민다 — 바쁜대기(무의미한 git log 반복)거나 우회(내가 기준을 쓴다).
// 레일이 사람의 응답을 전달하지 못하면 레일을 뚫는 게 합리적으로 보이기 시작한다. 그래서 기다림을
// 정직한 한 줄(--status)과 진짜 대기(--wait)로 만든다.
// statusCmdName — 이 이름이 개시 인터뷰 슬러그면 intake, 체인이면 interview.
func statusCmdName(name string) string {
	if chainPurpose(name, "--branches") == "" && intakeState(name) != "" {
		return "intake"
	}
	return "interview"
}

func interviewWatch(chain string, wait bool, timeoutS, then string) {
	interviewWatchOpt(chain, wait, timeoutS, then, false)
}

// interviewWatchOpt — showFull 이면 --status 도 기준 문서 전문을 함께 낸다(--show).
func interviewWatchOpt(chain string, wait bool, timeoutS, then string, showFull bool) {
	if chainPurpose(chain, "--branches") == "" && intakeState(chain) == "" {
		// 개시 인터뷰(gil intake)는 **체인보다 먼저** 서는 자리다 — 아직 아무것도 안 물은
		// 슬러그에 "체인이 없다"고 답하면, 정작 해야 할 다음 수(--ask)를 가린다.
		if intakeMode == chain {
			if wait {
				// 기다릴 것이 없는데 기다리게 두지 않는다 — 먼저 물어야 한다.
				die("거부: 개시 인터뷰 \"" + chain + "\" 에 아직 아무 질문도 없다 — 기다릴 것이 없다.\n" +
					"  먼저 물어라: gil intake " + chain + " --ask '[{\"q\":\"무엇을 하려고 하십니까\",\"type\":\"text\"}]'")
			}
			println2("intake: " + chain + " — none (아직 아무것도 묻지 않았다)")
			println2("  ▸ 첫 물음을 심어라(첫 질문은 열린 질문이어야 한다):")
			println2("      gil intake " + chain + " --ask '[{\"q\":\"무엇을 하려고 하십니까\",\"type\":\"text\"}]'")
			return
		}
		die("거부: 체인 \"" + chain + "\" 선언된 적 없음 — 먼저 gil chain 으로 열어라.")
	}
	// 재인터뷰가 열려 있으면 그게 지금 상태다 — 옛 done 을 보고하면 거짓말이 된다(이슈 #75).
	done := func() bool { return interviewState(chain) == "done" }
	report := func() {
		println2("interview: " + chain + " — done (사람이 제출해 기준 문서가 확정됐다)")
		// 전문은 **기다린 쪽에만** 준다(--wait). --status 는 확인용이라 도움말이 "한 줄"이라
		// 약속했는데 실제로는 수십 줄을 쏟아 컨텍스트를 크게 먹었다(이슈 #94 곁다리).
		// 확인하는 자리에 필요한 건 상태와 **인용할 번호**지 문서 전문이 아니다.
		if ref := chainReferenceText(chain, "--branches"); strings.TrimSpace(ref) != "" {
			if wait || showFull {
				println2("")
				println2("── 확정된 기준 문서 ──")
				println2(ref)
			} else {
				println2("  (전문은 길다 — 필요하면: gil " + statusCmdName(chain) + " " + chain + " --status --show)")
			}
		}
		// 개시 인터뷰(intake)의 다음 수는 사이클이 아니라 **체인**이다 — 아직 체인이 없다.
		if statusCmdName(chain) == "intake" {
			println2("▸ 이 답으로 체인을 연다(목적·기준은 인용된다):")
			println2("    gil chain <이름> --from-intake " + chain + " --purpose-from <n> --criterion-from <m>")
		} else {
			println2("▸ 이제 작업 사이클을 열 수 있다: gil open " + chain + "/<cycle> --author <a> --purpose <p>")
		}
	}
	if done() {
		report()
		markInterviewSeen(chain) // 이 세션이 답을 봤다 — 도착 고지를 끈다(#77)
		return
	}
	pending := interviewState(chain) == "pending"
	if !wait {
		if pending {
			println2("interview: " + chain + " — pending (사람 답 대기 중)")
			println2("▸ 사람에게 뷰어 폼 제출을 청하라. 답이 오면 이 명령이 done 으로 바뀐다.")
			// 뷰어가 죽었으면 **사람이 답할 창구 자체가 없다**(이슈 #93). 기다리는 자리에서
			// 그걸 모르면 에이전트도 사람도 "왜 아무 일이 없지"에서 멈춘다 — 실제로 그랬다.
			for _, ln := range viewerDeadNotice() {
				println2(ln)
			}
			if interviewWaiterActive(chain) {
				println2("▸ 지금 이 답을 **기다리는 프로세스가 살아 있다**(백그라운드 --wait). 제출되면 그쪽이 이어간다.")
			} else {
				println2("▸ 아무도 기다리고 있지 않다 — 지금 턴을 끝내면 사람이 다시 말을 걸 때까지 아무 일도 안 일어난다(이슈 #82).")
				for _, ln := range backgroundWaitHint(chain) {
					println2(ln)
				}
			}
		} else {
			println2("interview: " + chain + " — none (심어둔 인터뷰가 없다)")
			println2("▸ 먼저 질문을 심어라: gil interview " + chain + " --ask <질문JSON|->")
		}
		return
	}
	if !pending {
		die("거부: \"" + chain + "\" 에 기다릴 인터뷰가 없다 — 먼저 질문을 심어라:\n" +
			"    gil interview " + chain + " --ask <질문JSON|->")
	}
	secs := 600
	if strings.TrimSpace(timeoutS) != "" {
		n, err := strconv.Atoi(strings.TrimSpace(timeoutS))
		if err != nil || n <= 0 {
			die("거부: --timeout 은 양의 정수(초) — 받음: \"" + timeoutS + "\"")
		}
		secs = n
	}
	println2("interview: " + chain + " — 사람 답을 기다린다(최대 " + strconv.Itoa(secs) + "초). 뷰어 폼 제출을 청하라.")
	println2("  ▸ 뷰어가 이 대기를 사람에게 보여준다(\"에이전트가 이 답을 기다리는 중\") — 제출이 곧바로 이어진다는 걸 사람이 안다.")
	// 기다리기 **전에** 창구가 있는지 확인한다(이슈 #93) — 없으면 몇 분이든 헛되이 기다린다.
	for _, ln := range viewerDeadNotice() {
		println2(ln)
	}
	deadline := time.Now().Add(time.Duration(secs) * time.Second)
	// 대기 표식(이슈 #82): 기다리는 중임을 뷰어·handoff·--status 가 볼 수 있게 한다.
	// die 로 빠져나가도 표식을 남기지 않는다 — 유령이 "기다리는 중"이라 말하면 사람은 다시
	// 아무도 없는 곳에 제출한다.
	waiterBeat(chain, deadline)
	defer waiterClear(chain)
	dieHooks = append(dieHooks, func() { waiterClear(chain) })
	// **싸게 기다린다**(상현님 실사용: 노트북이 뜨거워졌다). done() 은 인터뷰 상태를 알려고
	// 저장소 전체를 두 번 훑는다(git log --branches ×2). 큰 저장소에서 그걸 2초마다 1시간
	// 돌리면 CPU 한 코어를 먹는다 — 실측 11.8%, 47분 경과. 기다림은 사람의 제출을 기다리는
	// 일이라 2초 정밀도가 필요 없다. 그래서 둘을 건다:
	//  (1) ref 서명이 그대로면 그래프는 안 바뀐 것이다 — 비싼 판정을 아예 건너뛴다(for-each-ref 한 번).
	//  (2) 간격을 2초에서 시작해 15초까지 늘린다 — 사람이 폼을 채우는 시간엔 그걸로 충분하다.
	refSig := func() string {
		out, err := gitTry("for-each-ref", "--format=%(objectname)", "refs/heads/")
		if err != nil {
			return ""
		}
		return out
	}
	// 폴링 루프는 오래 산다 — 사람의 제출이 밖에서 ref 를 바꾸므로, 캐시된 읽기는
	// 영원히 "아직 안 왔다"고 답한다(실제로 --wait 이 얼어붙었다).
	stopGitCache()
	lastSig := refSig()
	tick := 2 * time.Second
	const maxTick = 15 * time.Second
	for time.Now().Before(deadline) {
		time.Sleep(tick)
		if tick < maxTick {
			tick += 2 * time.Second
		}
		waiterBeat(chain, deadline) // 심장박동 — 끊기면 읽는 쪽이 죽은 표식으로 본다
		// **창구가 살아 있는지도 함께 본다**(이슈 #93). 실사용에서 정확히 이 일이 났다:
		// --wait 은 멀쩡히 기다리는데 뷰어만 조용히 죽어, 사람이 답을 낼 창구가 사라졌다.
		// 기다리는 쪽이 그걸 모르면 둘 다 "왜 아무 일이 없지"에서 멈춘다. 다시 띄운다 —
		// 관전 서버 기동은 싸고 멱등이며, 여기서 침묵할 이유가 없다.
		reviveViewerIfDead(chain)
		if sig := refSig(); sig == lastSig {
			continue // 커밋이 하나도 안 늘었다 — 제출이 있었을 리 없다
		} else {
			lastSig = sig
			tick = 2 * time.Second // 뭔가 움직였다 — 다시 촘촘히 본다
		}
		if done() {
			report()
			markInterviewSeen(chain) // 기다려서 봤다 — 도착 고지를 끈다(#77)
			runThen(chain, then)
			return
		}
	}
	// 시간초과는 실패가 아니다 — 사람이 아직 안 답했을 뿐이다. 지어내지 말고 그대로 알린다.
	die("시간초과: \"" + chain + "\" 인터뷰가 " + strconv.Itoa(secs) + "초 안에 제출되지 않았다 — 아직 pending 이다.\n" +
		"  기준을 대신 쓰지 마라. 사람에게 폼 제출을 청하고 다시 기다려라(백그라운드로 돌리면 그동안 말도 할 수 있다):\n" +
		"    gil interview " + chain + " --wait --timeout " + strconv.Itoa(secs) + " > /tmp/gil-" + chain + "-ref.md 2>&1 &")
}

// interviewResolve — 인터뷰를 해소한다(뷰어 제출이 호출). 답변으로 조립된 레퍼런스 파일을
// 이 체인에 심고(Gil-Reference), 인터뷰를 done 으로 닫는다. 이후 open 안내·chainHasReference 가
// 이 체인을 '기준 있음'으로 본다. 파일은 워킹트리에 그대로 남아 사람이 열어보고 편집할 수 있다.
func interviewResolve(chain, refFile string) {
	// 개시 인터뷰(gil intake)는 체인이 없는 상태에서 해소된다 — 뷰어 제출은 같은 경로를
	// 타므로(gil interview <슬러그> --resolve) 여기서 갈라 준다(이슈 #90).
	if chainPurpose(chain, "--branches") == "" {
		if intakeState(chain) != "" {
			intakeResolve(chain, refFile)
			return
		}
		die("거부: 체인 \"" + chain + "\" 없음")
	}
	refBody := resolveBody("", refFile)
	if strings.TrimSpace(refBody) == "" {
		die("거부: --resolve 레퍼런스 파일이 비었다")
	}
	// 심층 인터뷰(상현님): 인터뷰는 한 번으로 끝내지 않아도 된다 — 문제가 명확해질 때까지
	// 여러 차례 물을 수 있다. 그런데 옛 동작은 새 기준이 앞 기준을 **덮어써서**, 2차를 물으면
	// 1차에 사람이 답한 것이 기준에서 사라졌다. 기준은 사람의 답이므로 지워지면 안 된다 —
	// 차수를 쌓는다. 최신 기준 문서 하나를 읽으면 지금까지의 모든 답이 거기 있다.
	prev := chainReferenceText(chain, "--branches")
	round := 1
	if strings.TrimSpace(prev) != "" {
		round = strings.Count(prev, "## 인터뷰 ") + 2
	}
	combined := refBody
	if strings.TrimSpace(prev) != "" {
		pb := prev
		if i := strings.Index(pb, "── 기준 문서(레퍼런스 트루스) ──"); i >= 0 {
			pb = strings.TrimSpace(pb[i+len("── 기준 문서(레퍼런스 트루스) ──"):])
		}
		combined = pb + "\n\n---\n\n## 인터뷰 " + itoa(round) + "차 (심층)\n\n" + refBody
	}
	subject := "gil " + chain + " reference: 인터뷰로 기준 문서 확정"
	if round > 1 {
		subject = "gil " + chain + " reference: 심층 인터뷰 " + itoa(round) + "차로 기준 보강"
	}
	body := "체인 [" + chain + "]의 레퍼런스 트루스(기준 문서)를 사람과의 인터뷰로 확정했다(이슈 #33).\n" +
		"이후 사이클의 define·가설·성패판정이 이 기준에 비추어 선다.\n" +
		"인터뷰는 한 번으로 끝내지 않아도 된다 — 문제가 명확해질 때까지 차수를 더할 수 있고,\n" +
		"앞 차수의 답은 지워지지 않고 아래에 함께 쌓인다.\n\n" +
		"── 기준 문서(레퍼런스 트루스) ──\n\n" + combined
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Kind", "reference"},
		{"Gil-Reference", "true"}, {"Gil-Interview", "done"},
	}
	// 체인 브랜치 위에 심는다 — 그 체인의 계보에 기준이 얹히도록 HEAD 를 맞춘다(이슈 #44 정합).
	tip := strings.TrimSpace(git("rev-parse", "--verify", "-q", "refs/heads/"+chain))
	if tip != "" {
		alignHeadToTip(first9(tip), chain)
	}
	commit(subject, body, tr, true)
	if round > 1 {
		println2("interview: " + chain + " 기준 보강 — 심층 인터뷰 " + itoa(round) + "차(앞 차수 답도 그대로 남았다).")
	} else {
		println2("interview: " + chain + " 기준 문서 확정 — 레퍼런스 심음(인터뷰 done).")
	}
	println2("  ▸ 아직 문제가 흐릿하면 한 번 더 물어도 된다 — gil interview " + chain +
		" --ask <질문JSON|-> (차수가 쌓인다).")
}

// ── gil chain-close ──
//
// 체인을 완결로 봉인한다 (상현님 실사용: 체인을 닫는 명령이 없어 서브에이전트가
// 체인 전환을 못 하고 사이클만 계속 열었다). 사이클 close 와 체인 close 는 다르다:
// close 는 한 사이클을, chain-close 는 그 위 단계(배포 순환의 한 국면)를 닫는다.
// 완결의 정의 — 모든 사이클이 닫혀야 체인을 닫을 수 있다. 닫으면 handoff 가
// "새 체인을 gil chain 으로" 안내하고, 그 닫힌 끝에서 새 체인이 대문·교훈을 이어받는다.
func cmdChainClose(args []string) {
	fs := newFlags("gil chain-close")
	verdict := fs.str("verdict", "supported")
	// 회고와 시드(이슈 #33): 체인 생애주기의 닫는 쪽. 인터뷰가 "무엇을 기준으로 할 것인가"를
	// 열 때 사람에게 물었다면, 회고는 "그 기준에 얼마나 합당했나"를 닫을 때 답한다. 시드는
	// 그 회고에서 자라나는 다음 물음 — 다음 체인 인터뷰의 재료다(기준의 대체가 아니다).
	retro := fs.str("retro", "")
	seed := fs.str("seed", "")
	// --superseded-by <chain> (이슈 #85). 옛 체인의 결론이 뒤에서 뒤집히는 일이 실제로 일어난다
	// (실측: "토큰 2.5배 열위"가 다른 체인에서 0.55배로 뒤집혔다). 그걸 적을 구조적 자리가
	// 회고 본문밖에 없으면, 읽는 쪽은 **어느 결론이 아직 유효한지**를 알려고 26개 회고를 다 읽어야 한다.
	supersededBy := fs.str("superseded-by", "")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil chain-close <chain> [--verdict V] [--retro <회고파일|->] [--seed <시드파일|->]")
	}
	chain := pos[0]
	if !idRe.MatchString(chain) {
		die("거부: 체인 이름 \"" + chain + "\"은 소문자·숫자·하이픈만")
	}
	if chainPurpose(chain, "--branches") == "" {
		die("거부: 체인 \"" + chain + "\" 선언된 적 없음 (gil chain 으로 먼저 연다)")
	}
	if chainClosed(chain, "--branches") {
		die("거부: 체인 \"" + chain + "\" 이미 닫힘")
	}
	// 완결 가드: 모든 사이클에 close 커밋이 있어야 체인을 닫을 수 있다.
	// 산 잎(success 스텝) 존재만으로는 부족하다 — gil close 로 봉인돼야 닫힌 사이클이다.
	closed := closedCycles("--branches")
	_, order := cyclesOf(chain)
	var open []string
	for _, id := range order {
		if !closed[chain+"\x01"+id] {
			open = append(open, id)
		}
	}
	if len(open) > 0 {
		// 사이클마다 **왜 못 닫히는지와 갈 길**을 짚는다(이슈 #47 G7). 이름만 나열하면
		// 사용자는 gil close 를 시도했다가 또 거부당하고, 거부가 거부로 이어지면 우회하려 든다.
		msg := "거부: 아직 닫히지 않은 사이클이 " + itoa(len(open)) + "개 남았다 — 체인은 모든 " +
			"사이클이 닫혀야 닫힌다(완결의 정의).\n"
		for _, id := range open {
			msg += cycleCloseHint(chain, id) + "\n"
		}
		die(strings.TrimRight(msg, "\n"))
	}
	// 회고 강제(이슈 #33) — 단, **기준이 있는 체인에서만**. 사람이 인터뷰로 세운 기준이 있는
	// 체인은 그 기준 대비 달성도를 남기지 않고 닫을 수 없다. 기준 없이 닫히던 옛 체인까지
	// 소급해 막지는 않는다 — 없는 잣대에 대고 성적표를 요구하는 건 형식만 채우게 만든다.
	// 개시 인터뷰가 낳은 **성패 기준**을 닫는 자리에서 되읽는다(상현님). 필수로 받아놓고
	// 아무도 안 읽으면 그게 형해화다 — 기준은 닫을 때 쓰라고 세운 것이다.
	crit := chainTrailer(chain, "Gil-Chain-Criterion")
	if strings.TrimSpace(crit) != "" {
		println2("  ◎ 이 체인의 성패 기준(사람이 세운 자): " + crit)
		println2("    ▸ 회고는 **이 문장에 답해야 한다** — 충족됐나, 아니면 무엇이 모자랐나.")
	}
	refText := ""
	if chainReferenceApproved(chain, "--branches") {
		refText = chainReferenceText(chain, "--branches")
		if strings.TrimSpace(*retro) == "" {
			msg := "거부: 체인 \"" + chain + "\" 은 사람이 세운 기준이 있다 — 그 기준 대비 회고 없이 닫을 수 없다(이슈 #33).\n" +
				"  체인을 열 때 인터뷰로 '무엇을 기준으로 할 것인가'를 물었다면, 닫을 때는 '그 기준에\n" +
				"  얼마나 합당했나'를 답해야 생애주기가 닫힌다. 회고 없는 종결은 '됐다'는 자기확신이다.\n" +
				"    gil chain-close " + chain + " --retro <회고파일|-> [--seed <다음 물음 시드|->]\n" +
				"  회고에 담을 것: 기준의 각 항목을 달성했나·못 했나(정직하게), 무엇이 그렇게 만들었나,\n" +
				"  **반드시 분기했어야 할 지점**은 어디였나(돌아보면 보이는 갈림길).\n" +
				"  --seed 는 다음 체인 인터뷰의 재료다 — 남은 물음·새로 생긴 물음을 적어라."
			if strings.TrimSpace(crit) != "" {
				msg += "\n\n── 성패 기준(이 문장에 답해라) ──\n  " + crit
			}
			if refText != "" {
				msg += "\n\n── 이 체인의 기준(이것에 비추어 써라) ──\n" + refText
			}
			die(msg)
		}
	}
	retroBody := ""
	if strings.TrimSpace(*retro) != "" {
		retroBody = strings.TrimSpace(resolveBody("", *retro))
		if retroBody == "" {
			die("거부: --retro 회고 파일이 비었다 — 빈 회고는 회고가 아니다")
		}
	}
	seedBody := ""
	if strings.TrimSpace(*seed) != "" {
		seedBody = strings.TrimSpace(resolveBody("", *seed))
		if seedBody == "" {
			die("거부: --seed 시드 파일이 비었다")
		}
	}

	subject := "gil " + chain + " chain-close: " + *verdict
	body := "체인 [" + chain + "] 봉인. 판정: " + *verdict + ".\n\n" +
		"이 국면은 완결됐다. 다음은 이 닫힌 끝에서 새 체인을 연다 " +
		"(gil chain <name> --purpose ...) — 대문·존재·교훈이 체인을 넘어 이어진다."
	if retroBody != "" {
		body += "\n\n── 회고(기준 대비 달성도) ──\n\n" + retroBody
	}
	if seedBody != "" {
		body += "\n\n── 다음 체인의 시드 ──\n\n" + seedBody
	}
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Kind", "chain-close"}, {"Gil-Verdict", *verdict},
	}
	if retroBody != "" {
		tr = append(tr, [2]string{"Gil-Retro", "true"})
	}
	if seedBody != "" {
		tr = append(tr, [2]string{"Gil-Seed-Ref", "true"})
	}
	if sb := strings.TrimSpace(*supersededBy); sb != "" {
		if chainPurpose(sb, "--all") == "" {
			die("거부: --superseded-by \"" + sb + "\" 체인이 없다 — 뒤집은 쪽이 실재해야 선이 참이 된다.")
		}
		tr = append(tr, [2]string{"Gil-Superseded-By", sb}) // 이 체인의 결론은 저기서 뒤집혔다(이슈 #85)
	}
	// 봉인은 **그 체인의 끝**에 얹혀야 한다(이슈 #66, #44 계열). 옛 코드는 그때 체크아웃돼
	// 있던 브랜치에 커밋해, 체인 브랜치 ref 는 옛 팁(대개 체인 선언 커밋)에 멈춘 채였다.
	// 그러면 "닫힌 체인의 끝에서 새 체인을 연다"가 커밋 그래프에서는 성립해도 **그 체인의
	// 이름이 그 끝을 가리키지 않아** — 뷰어·계보 판정이 새 체인을 고아로 본다.
	//
	// 체인의 진짜 끝은 체인 브랜치가 아니라 그 체인의 마지막 작업(사이클 가지)일 수 있다.
	// 그래서 (a) 그 체인 소속 커밋 중 가장 최근 것으로 HEAD 를 맞추고 (b) 봉인을 얹은 뒤
	// (c) 체인 브랜치 ref 를 그 봉인으로 전진시킨다 — 이름이 끝을 가리키게.
	if tipSHA := chainLatestCommit(chain); tipSHA != "" {
		alignHeadToTip(first9(tipSHA), chain)
	}
	commit(subject, body, tr, true)
	// 체인 브랜치를 봉인 커밋으로 전진시킨다(fast-forward 만 — 앞선 이력을 잃지 않게).
	if head := strings.TrimSpace(git("rev-parse", "HEAD")); head != "" {
		if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+chain) {
			if gitOK("merge-base", "--is-ancestor", "refs/heads/"+chain, head) {
				git("update-ref", "refs/heads/"+chain, head)
			} else {
				stderr("  ⚠ 체인 브랜치 " + chain + " 를 봉인으로 전진시키지 못했다(빨리감기 불가) —")
				stderr("    그 ref 가 봉인과 갈라져 있다. 이름이 체인의 끝을 안 가리킨다: gil fsck 로 확인하라.")
			}
		}
	}
	println2("chain-close: " + chain + " — " + *verdict)
	if retroBody != "" {
		println2("  회고 심음(기준 대비 달성도) — 이 체인의 성적표가 그래프에 남았다.")
	}
	// **다음 국면은 목적을 창작하는 것으로 시작하지 않는다.** 옛 안내는 곧장
	// `gil chain <name> --purpose <목적>` 을 가리켰다 — 그러면 에이전트가 목적을 지어내고
	// 사람은 승인만 한다(이슈 #90 이 intake 를 만든 바로 그 이유인데, 정작 체인이 끝나는
	// 자리의 안내가 옛 순서를 계속 가르치고 있었다). 그리고 **어디서 이어받을지**도 그 답을
	// 보고 정해야 하는데, 그 물음 자체가 안내에 없었다(상현님 실사용: 체인이 끝나면 목적
	// 없이 인터뷰를 다시 시작해 계승이냐 시조냐를 정해야 하는데 그렇게 안 하더라).
	for _, ln := range afterChainCloseNext(chain) {
		println2(ln)
	}
	if seedBody != "" {
		println2("     시드를 남겼다 — 다음 체인의 인터뷰 질문을 이 시드에서 짜라(시드는 기준이 아니다.")
		println2("     기준은 언제나 사람의 답이다: gil interview <새체인> --ask ...).")
	}
	println2("     이전 체인의 교훈(gil memory read)을 새 체인 목적·첫 가설에 이어받아라.")
}

// chainCriterion·chainPlan — --from-intake 가 사람의 답에서 들어 올린 두 산출.
// 함수 지역이 아니라 여기 두는 건 트레일러 조립 지점이 멀리 있어서다.
var chainCriterion, chainPlan, chainIntakeRef string

// chainPlanItems — 체인에 각인된 사이클 분할을 항목으로 쪼갠다. 사람이 어떻게 적든
// (줄바꿈·번호·불릿·가운뎃점) 읽어낸다 — 형식을 사람에게 강요하지 않는다.
func chainPlanItems(chain string) []string {
	raw := chainTrailer(chain, "Gil-Chain-Plan")
	if strings.TrimSpace(raw) == "" {
		return nil
	}
	seps := func(r rune) bool { return r == '\n' || r == '·' || r == ';' }
	var out []string
	for _, p := range strings.FieldsFunc(raw, seps) {
		t := strings.TrimSpace(p)
		// "1." "1)" "-" "*" 같은 머리표를 떼되 내용은 그대로 둔다.
		t = strings.TrimLeft(t, "-*• \t")
		for i, r := range t {
			if r < '0' || r > '9' {
				if i > 0 && (r == '.' || r == ')') {
					t = strings.TrimSpace(t[i+1:])
				}
				break
			}
		}
		if t != "" {
			out = append(out, t)
		}
	}
	return out
}

// ── gil chain ──
func cmdChain(args []string) {
	fs := newFlags("gil chain")
	purpose := fs.str("purpose", "")
	inherit := fs.str("inherit", "") // 물려받은 전수(AIL #3). 체인 부모는 위상 유도라 선택.
	// --reference: 이 체인의 기준 문서(레퍼런스 트루스, 이슈 #33). 인터뷰로 문제를 명확히 한
	// 산출물 — 이후 사이클의 define·가설·성패판정·기각이 무엇에 비추어 합당한지의 잣대가 된다.
	// 최소 형태(이번 조각): '기준의 존재와 참조'만 심는다. 강제도 매 사이클 인용 강제도 아직 없다
	// — 형해화(빈 문서 양산) 위험을 관전한 뒤 강제 강도를 올린다(#33 논쟁점 1, falsify가 준 교훈).
	// purpose=한 줄 요약, reference=근거 전문(파일 또는 - stdin).
	reference := fs.str("reference", "")
	// --parallel-with <열린 체인> (이슈 #54): 병렬 트랙을 **선언**한다.
	//
	// gil help 는 "닫힌 체인 끝에서만"이라 적어놓고 실제로는 열린 체인 옆에서 새 체인을 여는
	// 걸 통과시켰다. 그래서 동시에 굴린 트랙이 git 조상관계로 "이어받음"이 됐다 — 선언된
	// 진실(--inherit 없음)과 그려지는 진실(이어받음)이 반대였다. 병렬을 막는 게 답이 아니다
	// (실사용에서 5개 트랙이 서로 다른 장비에서 동시에 돌았다). 표현할 수단을 주는 게 답이다.
	parallelWith := fs.strList("parallel-with")
	// 측정 체인의 합격선을 스스로 올린다(이슈 #79 제안 2, #81). 전면 강제는 과하다 —
	// 측정을 하는 체인만 "선언 없이는 사이클을 못 연다"를 문법으로 건다.
	requireDataset := fs.boolFlag("require-dataset")
	requireSubject := fs.boolFlag("require-subject")
	// --from <닫힌 체인> (이슈 #68): **어느 닫힌 체인을 이어받는지** 선언한다.
	//
	// --parallel-with 의 빈 짝이었다. 옛 동작은 새 체인을 HEAD 가 있던 곳에 붙였는데, HEAD 는
	// "마지막으로 닫은 체인"에 가 있다. 여러 체인을 닫고 새 체인을 열면 계보가 엉뚱한 체인으로
	// 그려졌다 — 같은 명령의 출력이 A 를 앞 체인이라 안내하면서 그래프는 B 에 붙는, 도구가
	// 스스로 모순되는 상태였다.
	// --from 은 **여럿을 받는다**(이슈 #107 3b). 다음 체인이 두 닫힌 체인의 지식을 함께
	// 물려받아야 하는 경우가 실사용에서 나왔는데(문법 실험 + 순수계산), 계승 부모를 하나만
	// 적을 수 있어 새 체인은 직전 체인 위에 얹히거나 무연고로 떴다. **여러 체인의 지식이
	// 하나로 모이는 그림**이야말로 gil 이 보여줘야 할 장면이다 — 선언만이 아니라 커밋
	// 그래프의 합류선으로 남긴다(첫 체인 끝에서 갈라지고, 나머지는 머지로 끌어온다).
	fromList := fs.strList("from")
	// --orphan <왜> — 이어받지 않고 새로 서는 것도 **정당한 선택이지만 기록돼야 한다**.
	orphanWhy := fs.str("orphan", "")
	// --from-intake <슬러그> / --purpose-from <질문번호> (이슈 #90): 체인의 목적을 **사람의
	// 답에서 그대로 들어 올린다.** 에이전트가 다시 쓰지 않는다 — 요약도 정제도 창작이고,
	// 창작하는 순간 기준 문서는 '사람이 세운 자'가 아니게 된다.
	fromIntake := fs.str("from-intake", "")
	purposeFrom := fs.str("purpose-from", "")
	// 심층 인터뷰의 나머지 두 산출(상현님): **풀었다/못 풀었다를 가르는 기준**과
	// **사이클 단위로 분할된 문제들**. 둘 다 사람의 답에서 인용한다.
	criterionFrom := fs.str("criterion-from", "")
	// --criterion: 개시 인터뷰 없이(사람이 기준 문서를 직접 준 경우) 판정 문장을 받는 자리.
	// --reference 와 짝이다 — 전문(문서)과 판정 문장(한 줄)이 함께 있어야 기준이 산다.
	criterion := fs.str("criterion", "")
	cyclesFrom := fs.str("cycles-from", "")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil chain <name> --from-intake <슬러그> --purpose-from <질문번호>   (권장 — 이슈 #90)\n" +
			"  또는: gil chain <name> --purpose <자연어> [--from <닫힌체인>] [--parallel-with <열린체인>...]\n" +
			"        [--reference <기준문서|->] [--inherit <전수>]")
	}
	name := pos[0]
	// 개시 인터뷰에서 목적을 인용한다 — 순환을 사람 쪽에서 끊는 경로.
	if si := strings.TrimSpace(*fromIntake); si != "" {
		if strings.TrimSpace(*purpose) != "" {
			die("거부: --from-intake 와 --purpose 는 함께 못 선다 — 목적은 사람의 답에서 **인용**된다.\n" +
				"  네가 쓴 목적을 얹으면 개시 인터뷰가 장식이 된다. 어느 답을 목적으로 삼을지만 골라라:\n" +
				"    --purpose-from <질문번호>")
		}
		st := intakeState(si)
		if st == "" {
			die("거부: 개시 인터뷰 \"" + si + "\" 가 없다 — 먼저: gil intake " + si + " --ask <질문JSON>")
		}
		if st != "done" {
			die("거부: 개시 인터뷰 \"" + si + "\" 가 아직 사람 답을 기다린다 — 답이 와야 목적이 선다.\n" +
				"  기다려라: gil intake " + si + " --wait")
		}
		n := atoiSafe(strings.TrimSpace(*purposeFrom))
		if n <= 0 {
			die("거부: --purpose-from <질문번호> 필요 — 사람의 어느 답을 이 체인의 목적으로 삼을지 골라라.\n" +
				"  답 전문: gil intake " + si + " --status")
		}
		lifted := intakeAnswerN(si, n)
		if strings.TrimSpace(lifted) == "" {
			die("거부: 개시 인터뷰 \"" + si + "\" 의 " + itoa(n) + "번 답이 비었다 — 그 답으로는 목적이 서지 않는다.\n" +
				"  답 전문을 보고 다시 고르거나, 더 물어라: gil intake " + si + " --ask <추가 질문>")
		}
		*purpose = lifted
		println2("  ◎ 목적을 사람의 답에서 인용했다(" + si + " 질문 " + itoa(n) + "): " + lifted)
		// 답이 **참조형**("2번", "②", "위의 두 번째")이면 그 자체로는 목적이 서지 않는다.
		// 이 문장은 이후 모든 스텝·사이클에서 되읽히는 판단 근거라, "2번 해보자"로 박히면
		// 매번 무엇의 2번인지 되짚어야 한다(이슈 #109). 막지는 않는다 — 인용은 인용이다.
		if referentialAnswer(lifted) {
			stderr("  ⚠ 이 답은 **참조형**이다 — 무엇의 몇 번인지 이 문장만으로는 서지 않는다.")
			stderr("    체인 목적은 이후 모든 스텝에서 되읽히는 판단 근거다. 사람에게 한 줄 더 물어")
			stderr("    그 선택지를 펼친 답을 받아라: gil intake " + si + " --ask '[{\"q\":\"고르신 것을 한 문장으로 적어 주세요\",\"type\":\"text\"}]'")
			stderr("    (선택지가 있는 질문은 애초에 type:\"radio\"/\"checkbox\" 로 물어라 — 답이 항목 그 자체가 된다.)")
		}
		// 성패 기준 — 체인을 **닫을 때 무엇에 비추어 판정하나**. 목적만 있고 기준이 없으면
		// '됐다'가 다시 자기확신이 된다(#33 이 기준 문서를 요구한 이유가 체인 층에도 선다).
		cn := atoiSafe(strings.TrimSpace(*criterionFrom))
		if cn <= 0 {
			die("거부: --criterion-from <질문번호> 필요 — **무엇이 관측되면 이 체인이 풀린 것인가**를\n" +
				"  사람의 답에서 인용하라. 목적만 있고 기준이 없으면 '됐다'가 다시 자기확신이 된다.\n" +
				"  아직 안 물었으면 차수를 더해라:\n" +
				"    gil intake " + si + " --ask '[{\"q\":\"무엇이 관측되면 이 문제가 풀린 것입니까? 풀리지 않았다고 판단할 조건도 함께 적어 주세요\",\"type\":\"text\"}]'\n" +
				"  답 전문: gil intake " + si + " --status")
		}
		crit := intakeAnswerN(si, cn)
		if strings.TrimSpace(crit) == "" {
			die("거부: " + si + " 의 " + itoa(cn) + "번 답이 비었다 — 그 답으로는 성패 기준이 서지 않는다.")
		}
		chainCriterion = crit
		// **개시 인터뷰가 곧 이 체인의 인터뷰다.** 사람이 이미 답했는데 체인을 열자마자
		// 또 물으라고 하면(#33 게이트) 같은 사람에게 같은 것을 두 번 묻는 꼴이고, 실제로
		// 사이클을 못 열었다. 그 답을 이 체인의 기준 문서로 그대로 얹는다.
		chainIntakeRef = stripTrailers(intakeAnswers(si))
		println2("  ◎ 성패 기준을 인용했다(질문 " + itoa(cn) + "): " + crit)
		// 사이클 분할 — 있으면 지고 간다. 없으면 강제하지 않는다: 분할은 문제를 충분히 본
		// 뒤에야 나오고, 처음부터 요구하면 빈 칸 채우기가 된다(#76 이 관찰 중인 위험).
		if k := atoiSafe(strings.TrimSpace(*cyclesFrom)); k > 0 {
			if plan := intakeAnswerN(si, k); strings.TrimSpace(plan) != "" {
				chainPlan = plan
				println2("  ◎ 사이클 분할을 인용했다(질문 " + itoa(k) + "): " + clip(plan, 100))
				println2("    ▸ 사이클을 열 때 이 목록에서 골라라: gil open <chain>/<cycle> --from-plan <번호>")
			}
		}
		println2("  ▸ 이제 **어디서 분기할지**를 그 답에 비추어 정하라 — --from(이어받음) / " +
			"--parallel-with(나란히) / 아무것도 없으면 대문에서 새 계보.")
	}
	if *purpose == "" {
		die("거부: --purpose 필요 — 또는 사람에게 먼저 물어 그 답을 인용하라(이슈 #90):\n" +
			"    gil intake <슬러그> --ask '[{\"q\":\"무엇을 하려고 하십니까\",\"type\":\"text\"}]'\n" +
			"    (답이 오면)  gil chain " + name + " --from-intake <슬러그> --purpose-from 1\n" +
			"  네가 목적을 창작해 체인을 열면 사람은 방향을 정하는 자리가 아니라 승인하는 자리에 앉는다.")
	}
	// ── 목적과 기준은 **쌍으로만 태어난다** (상현님) ──────────────────────────────
	// 옛 게이트는 기준 없는 체인을 만들게 두고 **사이클을 열 때** 막았다. 그 사이에 체인이
	// 이미 존재하니, 실사용에서는 늘 "체인부터 만들고 → 거부당하고 → 그제서야 인터뷰"가 됐다.
	// 순서가 뒤집힌 채로 굳은 것이다. 막을 자리는 사이클이 아니라 **체인의 탄생**이다:
	// 기준 없는 체인이 아예 존재하지 못하면, 인터뷰를 먼저 하는 것 말고 다른 길이 없다.
	// **한 번만 읽는다** — --reference - (stdin) 은 두 번 읽으면 두 번째가 빈 값이다.
	refGiven := resolveBody("", *reference)
	if strings.TrimSpace(chainCriterion) == "" {
		if strings.TrimSpace(refGiven) == "" {
			die("거부: 기준 문서 없이 체인을 열 수 없다 — 목적과 기준은 쌍으로만 태어난다.\n" +
				"  '됐다'를 무엇에 비추어 판정할지가 없으면, 체인을 닫을 때 그 판단은 다시 네 자기확신이 된다.\n" +
				"  두 길 중 하나로 열어라:\n" +
				"    (1) 사람에게 먼저 묻는다 — 권장(이슈 #90):\n" +
				"        gil intake <슬러그> --ask '[{\"q\":\"무엇을 하려고 하십니까\",\"type\":\"text\"}]'\n" +
				"        gil intake <슬러그> --ask '[{\"q\":\"무엇이 관측되면 풀린 것입니까\",\"type\":\"text\"}]'\n" +
				"        gil chain " + name + " --from-intake <슬러그> --purpose-from 1 --criterion-from 2\n" +
				"    (2) 사람이 기준 문서를 이미 줬다면 그 문서와 한 줄 기준을 함께:\n" +
				"        gil chain " + name + " --purpose <목적> --reference <기준문서|-> --criterion <무엇이 관측되면 풀린 것인가>\n" +
				"  네가 기준을 창작해 넣지 마라 — 그건 스스로 채점표를 쓰는 일이다.")
		}
		if strings.TrimSpace(*criterion) == "" {
			die("거부: --reference 를 줬으면 --criterion <무엇이 관측되면 풀린 것인가> 도 필요하다.\n" +
				"  기준 문서는 근거 전문이고, --criterion 은 그 문서에서 뽑은 **판정 문장**이다 —\n" +
				"  chain-close 가 이 문장을 되읽어 \"여기에 답하라\"고 요구한다. 전문만 있고 판정 문장이\n" +
				"  없으면 아무도 그 문서를 잣대로 쓰지 않는다(형해화).")
		}
		chainCriterion = strings.TrimSpace(*criterion)
	} else if strings.TrimSpace(*criterion) != "" {
		die("거부: --criterion 과 --criterion-from 은 함께 못 선다 — 기준은 인용이지 작문이 아니다.")
	}
	if !idRe.MatchString(name) {
		die("거부: 체인 이름 \"" + name + "\"은 소문자·숫자·하이픈만")
	}
	// 층의 이름은 체인이 쓸 수 없다(main-dev-chain). 옛 저장소에는 "dev" 라는 이름의 체인이
	// 흔했는데, 그 이름이 이제 층을 가리키므로 그대로 두면 체인이 층을 덮어쓴다. 이름이 무엇을
	// 가리키는지 하나로 정해야 한다 — 아니면 뷰어도 fsck 도 어느 dev 를 말하는지 모른다.
	if name == devBranchName {
		die("거부: \"" + devBranchName + "\" 은 층의 이름이다 — 모든 체인이 여기서 태어난다.\n" +
			"  체인에는 그 작업이 무엇인지 말하는 이름을 줘라(예: " + name + "-<하는 일>).\n" +
			"  층이 궁금하면: git log --oneline " + devBranchName)
	}
	// homeBranch 는 main/master 가 없으면 아무 브랜치나 되돌려준다 — 그 폴백으로 이름을 막으면
	// 알파벳 순 첫 체인이 자기 이름을 못 쓰게 된다. 대문이 확실할 때만 막는다.
	if h := homeBranch(); (h == "main" || h == "master") && name == h {
		die("거부: \"" + name + "\" 은 대문 브랜치다 — 배포된 것만 여기 온다(gil deploy).")
	}
	// 이미 있나는 **모든 가지**에서 본다 — HEAD 에서 닿는 것만 보면, 다른 체인에 서 있을 때
	// 같은 이름의 체인을 또 만들 수 있다(브랜치 이름 충돌로 걸리기 전까지는 조용하다).
	if chainPurpose(name, "--branches") != "" {
		die("거부: 체인 \"" + name + "\" 이미 목적 선언됨 (chain은 새 체인만)")
	}
	if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+name) {
		die("거부: 브랜치 " + name + " 이미 있음 (체인은 새 브랜치만)")
	}
	// --from 검증(이슈 #68): 이어받는다고 선언한 체인은 실재하고 **닫혀 있어야** 한다.
	// 그래야 "닫힌 체인 끝에서 연다"가 사실이 된다.
	var froms []string
	for _, f0 := range *fromList {
		f := strings.TrimSpace(f0)
		if f == "" {
			continue
		}
		if chainPurpose(f, "--branches") == "" {
			die("거부: --from \"" + f + "\" 체인이 없다.")
		}
		if !chainClosed(f, "--branches") {
			die("거부: --from \"" + f + "\" 은 아직 닫히지 않았다 — 이어받으려면 먼저 닫아라:\n" +
				"    gil chain-close " + f + " --retro <회고파일|->\n" +
				"  (동시에 굴리는 트랙이면 --parallel-with " + f + " 다.)")
		}
		froms = append(froms, f)
	}
	if len(froms) > 0 && strings.TrimSpace(*orphanWhy) != "" {
		die("거부: --from 과 --orphan 은 함께 못 선다 — 이어받거나 새로 서거나 하나다.")
	}
	// ── 계승 자리 게이트 (이슈 #111) ─────────────────────────────────────────────
	//
	// 문서는 "닫힌 체인 끝에서만 연다"고 약속하는데, 실제로는 **아무 자리에서나** 열렸다.
	// 배포까지 마친 대문(main) 끝에서 열어도 통과했고, 그 체인은 그래프에서 선 하나 없이
	// 떴다 — 사람이 인터뷰에서 계승을 명시적으로 골랐는데도. 체인은 계보의 최상위 단위라,
	// 여기서 끊기면 그 아래 사이클·스텝 전부가 지식의 강에서 떨어져 나간다.
	//
	// 막되 벽이 되지 않게 한다: 어디서 열어야 하는지를 **칠 수 있는 한 줄**로 준다.
	// (--from 은 이제 gil 이 직접 그 끝을 찾아 거기서 브랜치를 판다 — 사람이 git checkout
	//  으로 옳은 커밋을 찾아다닐 필요가 없다.)
	// **막는 자리는 대문 끝 하나다.** 닫힌 체인의 끝에 서 있는 것은 정당한 자리이고(그게
	// 규칙이 말하는 '닫힌 체인 끝'이다), 거기까지 막으면 정상 흐름이 벽에 부딪힌다.
	// 대문은 배포된 것만 오는 층이라, 거기서 난 체인은 앞선 체인 어느 것과도 안 이어진다.
	// 커밋이 하나도 없는 저장소에서는 HEAD 가 없다 — 물어보다 죽지 않는다(gitTry).
	curBranch := ""
	if out, err := gitTry("rev-parse", "--abbrev-ref", "HEAD"); err == nil {
		curBranch = strings.TrimSpace(out)
	}
	atGate := curBranch != "" && curBranch == homeBranch()
	if atGate && len(froms) == 0 && len(*parallelWith) == 0 && strings.TrimSpace(*orphanWhy) == "" && !hasDevLayer() {
		var closedOnes []string
		for c := range chainRoots("--branches") {
			if chainClosed(c, "--branches") {
				closedOnes = append(closedOnes, c)
			}
		}
		sort.Strings(closedOnes)
		if len(closedOnes) > 0 {
			die("거부: 닫힌 체인이 있는데 이 체인이 어디서 이어받는지 말하지 않았다 — 지금 자리(" +
				curBranch + ", 대문)에서 그냥 열면\n" +
				"  그래프에 선 하나 없이 뜬다(커밋 조상관계는 '이어받음'을 뜻하지 않는다).\n" +
				"  닫힌 체인: " + strings.Join(closedOnes, " ") + "\n" +
				"  셋 중 하나를 골라라:\n" +
				"    (1) 이어받는다 — gil chain " + name + " … --from " + closedOnes[len(closedOnes)-1] + "\n" +
				"        (gil 이 그 닫힌 끝을 찾아 **거기서** 판다. 여럿에서 받으면 --from 을 반복하라.)\n" +
				"    (2) 나란히 간다 — --parallel-with <열린 체인>\n" +
				"    (3) 앞선 체인 없이 새로 선다 — --orphan <왜 이어받지 않나>\n" +
				"  (층이 있는 저장소라면 시조는 dev 에서 나므로 이 물음이 뜨지 않는다:\n" +
				"   gil migrate --adopt-dev 로 층을 인정하면 자리가 저절로 정해진다.)")
		}
	}
	// ── 이 체인은 어느 자리에서 태어나나 ──────────────────────────────────────────
	// dev 층이 있으면(main-dev-chain 레이아웃), --from 으로 계승을 선언하지 않은 체인은
	// **dev 팁에서** 갈라진다 = 계보상 시조(orphan). 옛 문법에는 이 자리가 없어서 무관한
	// 탐색선도 앞 체인 위에 얹혔다 — 그게 drift 가 stacked 로 계속 짖던 것의 정체다.
	devRooted := hasDevLayer() && len(froms) == 0 && len(*parallelWith) == 0
	// 열린 체인이 있으면 — 이어받는 것이 아니라 나란히 여는 것이므로 — 선언을 요구한다.
	// gil 자신의 규칙("닫힌 체인 끝에서만")과 실동작의 어긋남을 여기서 없앤다.
	//
	// **dev 에서 나는 체인은 이 요구에서 빠진다.** 그건 열린 체인 옆에 얹히는 게 아니라
	// 층에서 새로 시작하는 것이라, 계승으로 그려질 위험 자체가 없다(진짜로 dev 에서 갈라진다).
	if open := openChains(); len(open) > 0 && !devRooted {
		declared := map[string]bool{}
		for _, p := range *parallelWith {
			declared[p] = true
		}
		var undeclared []string
		for _, oc := range open {
			if !declared[oc] {
				undeclared = append(undeclared, oc)
			}
		}
		if len(undeclared) > 0 {
			die("거부: 아직 열린 체인이 있다: " + strings.Join(undeclared, " ") + "\n" +
				"  체인은 닫힌 체인 끝에서 연다 — 그래야 '이어받음'이 사실이 된다.\n" +
				"  둘 중 하나를 골라라:\n" +
				"    (1) 이어받기 — 먼저 닫아라: gil chain-close " + undeclared[0] + " --retro <회고파일|->\n" +
				"        (그 끝에서 새 체인을 열면 계승이 진짜가 된다)\n" +
				"    (2) 병렬   — gil chain " + name + " --purpose <P> --parallel-with " +
				strings.Join(undeclared, " --parallel-with ") + "\n" +
				"        (동시에 굴리는 트랙이다 — 선언이 그래프에 남고, 계승으로 그리지 않는다)")
		}
	}
	subject := "gil " + name + " chain: " + *purpose
	body := "체인 [" + name + "] 개설. 목적: " + *purpose + "\n\n" +
		"이 목적은 이후 사이클·스텝 시작 때 떠올라, 그 작업이 이 체인에 정합하는지 판단하는 근거가 된다."
	// 기준 문서를 chain-root 커밋 본문에 통째로 담는다(뷰어가 마크다운으로 렌더). 트레일러엔
	// '기준 있음' 표식만 — 전문은 본문에, 참조는 트레일러로.
	refBody := refGiven
	if strings.TrimSpace(refBody) == "" && strings.TrimSpace(chainIntakeRef) != "" {
		refBody = chainIntakeRef // 개시 인터뷰의 답이 이 체인의 기준 문서다(이슈 #90)
	}
	if strings.TrimSpace(refBody) != "" {
		body += "\n\n── 기준 문서(레퍼런스 트루스, 이슈 #33) ──\n\n" + refBody
	}
	tr := [][2]string{
		{"Gil-Chain", name}, {"Gil-Kind", "chain-root"},
		{"Gil-Chain-Purpose", *purpose},
	}
	// 심층 인터뷰가 낳은 두 산출을 체인에 각인한다(상현님). 인용이지 창작이 아니다.
	if strings.TrimSpace(chainIntakeRef) != "" {
		// 사람이 승인한 기준(Gil-Interview: done) — 개시 인터뷰의 답이 그 자격을 갖는다.
		tr = append(tr, [2]string{"Gil-Reference", "true"}, [2]string{"Gil-Interview", "done"})
	}
	if strings.TrimSpace(chainCriterion) != "" {
		tr = append(tr, [2]string{"Gil-Chain-Criterion", chainCriterion}) // 풀었다/못 풀었다의 기준
	}
	if strings.TrimSpace(chainPlan) != "" {
		tr = append(tr, [2]string{"Gil-Chain-Plan", chainPlan}) // 사이클 단위로 분할된 문제들
	}
	if *requireDataset {
		tr = append(tr, [2]string{"Gil-Require-Dataset", "true"}) // 사이클마다 평가셋 선언 필수(#79)
	}
	if *requireSubject {
		tr = append(tr, [2]string{"Gil-Require-Subject", "true"}) // 사이클마다 측정 대상 선언 필수(#81)
	}
	if strings.TrimSpace(refBody) != "" && strings.TrimSpace(chainIntakeRef) == "" {
		// 기준 문서 있음(본문에 전문). **집행은 체인의 탄생 한 곳에서만** 한다 — 여기까지 왔다는
		// 것은 기준이 쌍으로 갖춰졌다는 뜻이므로, open 이 다시 인터뷰를 요구하지 않는다.
		// (판정이 두 자리에서 갈리면 느슨한 쪽이 실질 규칙이 된다 — 이 레포가 값을 치른 교훈.)
		tr = append(tr, [2]string{"Gil-Reference", "true"}, [2]string{"Gil-Interview", "done"})
	}
	if strings.TrimSpace(*inherit) != "" {
		tr = append(tr, [2]string{"Gil-Inherit", *inherit}) // 물려받은 전수(AIL #3)
	}
	for _, p := range *parallelWith {
		tr = append(tr, [2]string{"Gil-Parallel-With", p}) // 병렬 트랙 선언(이슈 #54)
	}
	for _, f := range froms {
		tr = append(tr, [2]string{"Gil-Chain-From", f}) // 이어받는 체인 선언(이슈 #68·#107)
	}
	if w := strings.TrimSpace(*orphanWhy); w != "" {
		// 독립도 판단이다 — 판단은 근거와 함께 남는다(그래야 나중에 '왜 안 이어받았나'를 묻지 않는다).
		tr = append(tr, [2]string{"Gil-Chain-Orphan-Reason", w})
	}
	if devRooted {
		// 계보상 시조 — 앞선 체인이 없다는 **선언**이다(대문은 물려받는다, layout.go).
		// 선언을 남겨야 drift·뷰어가 이걸 '끊긴 계보'가 아니라 '여기서 새로 시작'으로 읽는다.
		tr = append(tr, [2]string{"Gil-Chain-Orphan", "dev"})
	}
	// 체인 = git 브랜치. 현재 위치(대문/닫힌 체인 끝)에서 분기해 대문을 이어받는다(orphan 아님).
	//
	// 병렬이면 **그 체인이 시작한 자리와 같은 자리**에서 갈라진다(이슈 #54·#65). 선언만 하고
	// 위상은 적층으로 두면, 커밋 그래프는 여전히 "뒤에 왔으니 이어받았다"고 말한다 — 적층
	// 자체를 없애야 두 진실이 하나가 된다.
	base := "HEAD"
	if devRooted {
		// dev 팁 — 대문 갱신까지 물려받는 자리. HEAD 를 쓰면 "마지막으로 있던 곳"에 얹힌다.
		base = devTipSHA()
	}
	if len(froms) > 0 {
		// 선언한 그 체인의 **끝**에서 갈라진다(이슈 #68). 이름이 봉인을 가리키므로(이슈 #66)
		// 그 ref 가 곧 끝이다. 선언과 그래프가 같은 말을 하게 된다.
		// 둘 이상이면 첫 체인에서 갈라지고 나머지는 아래에서 **합류선**으로 끌어온다.
		base = froms[0]
	} else if len(*parallelWith) > 0 {
		if b := chainRootParent((*parallelWith)[0]); b != "" {
			base = b
		}
	}
	commitOn(name, base, subject, body, tr, true)
	println2("chain: " + name + " 개설 (브랜치 " + name + ") — 목적: " + *purpose)
	// 두 번째 이후의 계승은 **머지로** 끌어온다(이슈 #107 3b). 선언만 남기고 위상은 한 줄로
	// 두면, 커밋 그래프는 여전히 "첫 체인에서만 왔다"고 말한다 — 여러 갈래의 지식이 하나로
	// 모이는 장면은 선언이 아니라 합류선으로 그려져야 한다(#45·#53 과 같은 축: 선언과 실재).
	for i, f := range froms {
		if i == 0 {
			continue // 첫 계승은 갈라진 자리 그 자체다 — 머지가 아니다
		}
		msg := "gil merge: " + f + " → " + name + "\n\n" +
			"체인 [" + name + "] 은 닫힌 체인 여럿의 지식을 이어받는다 — 이 합류선이 그중 하나다.\n\n" +
			"Gil-Merge: " + f + "\nGil-Merge-Into: " + name + "\nGil-Merge-Reason: 체인 계승(--from " + f + ")"
		if _, err := gitTry("merge", "--no-ff", "-q", "-m", msg, f); err != nil {
			stderr("⚠ 충돌 — [" + f + "] 계승 합류에서 멈췄다. 해결한 뒤: git add <파일> && git commit")
			gilExit(2)
		}
		println2("  ⇉ 계승 합류: " + f + " → " + name)
	}
	if len(froms) > 1 {
		println2("  ⇉ 이 체인은 닫힌 체인 " + itoa(len(froms)) + "개에서 이어받는다: " + strings.Join(froms, " · "))
	}
	if len(froms) == 0 && strings.TrimSpace(*orphanWhy) == "" && len(*parallelWith) == 0 {
		// 계승 결정을 **빈칸으로 두지 않는다**(이슈 #107 3b). 막지는 않되, 아무 말도 없이
		// 시조로 심기면 "이어받을 것이 없었나 / 안 물어봤나"가 영영 구분되지 않는다.
		stderr("  ⌂ 이어받는다는 선언이 없다 — 이 체인은 앞선 체인 없는 **시조**로 선다.")
		stderr("    닫힌 체인의 지식을 물려받는 것이면 그렇게 말해라(여럿이어도 된다):")
		stderr("      gil chain " + name + " … --from <닫힌체인> --from <또 다른 닫힌체인>")
		stderr("    정말 새로 서는 것이면 이유와 함께: --orphan <왜 이어받지 않나>")
	}
	if devRooted {
		println2("  ⌂ dev 층에서 갈라졌다 — 계보상 시조(앞선 체인 없음). 대문은 그대로 물려받는다.")
	} else if !hasDevLayer() {
		devLayerNudge()
	}
	// **누가 이 목적을 지었나.** --from-intake 로 열면 목적은 사람의 답에서 **인용**된다.
	// 그 길을 안 탔으면 이 문장은 네가 지은 것이고, 사람은 승인만 하게 된다 — 이슈 #90 이
	// intake 를 만든 바로 그 모양이다. 막지는 않는다(기준을 이미 손에 쥔 정당한 경우가 있다).
	// 다만 **무슨 일이 일어났는지는 말한다** — 실사용에서 체인을 먼저 만들고 인터뷰를 나중에
	// 하는 순서가 계속 나왔고, 그 순서에서는 목적이 늘 에이전트의 창작이었다.
	if strings.TrimSpace(*fromIntake) == "" {
		stderr("  ⚠ 이 목적은 **네가 쓴 문장**이다 — 사람의 답에서 인용된 것이 아니다.")
		stderr("    정본은 체인보다 **먼저** 묻는 것이다(이슈 #90): 목적도, 어디서 갈라질지도 사람의 답에서 나온다.")
		stderr("      gil intake <슬러그> --ask <질문JSON>   →   gil intake <슬러그> --ask-root")
		stderr("      gil chain <이름> --from-intake <슬러그> --purpose-from <번호> --criterion-from <번호>")
		stderr("    체인을 먼저 만들고 나중에 gil interview 로 묻는 순서는 이 자리를 되돌리지 못한다 —")
		stderr("    목적은 이미 박혔고, 인터뷰는 그 목적을 승인받는 절차가 된다.")
	}
	if strings.TrimSpace(refBody) != "" {
		println2("  ✓ 기준 문서(레퍼런스 트루스) 심음 — 이후 사이클의 define·가설·성패판정이 이걸 잣대로 선다.")
	} else {
		// 강제 아닌 안내(#33 최소 형태) — 기준 없이 여는 체인은 "무엇에 비추어 성패인가"가 없어,
		// 사람이 봤을 때 미달을 짚을 근거도, LLM 이 스스로 방향을 잡을 잣대도 흐려진다.
		stderr("  ▸ 이 체인의 기준 문서가 있으면 --reference <파일|-> 로 심어라(이슈 #33) — 사람과의 인터뷰로")
		stderr("    문제를 명확히 한 산출물. 이후 사이클의 define·가설·성패판정이 무엇에 비추어 합당한지의")
		stderr("    잣대가 된다. 기준이 없으면 '됐다'는 판단이 LLM 자기확신에 그친다.")
	}
	// 체인은 거의 늘 앞 체인의 교훈 위에 선다 — 부모가 위상 유도라 강제는 안 하되 안내(AIL #3).
	if strings.TrimSpace(*inherit) == "" {
		stderr("  ▸ 이 체인이 앞 체인/사이클에서 물려받은 전제·교훈이 있으면 --inherit 로 명시하라(AIL #3) — 계보를 지식의 강으로.")
	}
	// 생애주기를 닫는 고리(이슈 #33): 앞 체인이 회고에서 시드를 남겼으면 여기서 건네준다.
	// 시드는 다음 인터뷰의 **재료**지 기준이 아니다 — 기준은 언제나 사람의 답이라, 시드를
	// 그대로 레퍼런스로 삼는 지름길은 열지 않는다(그건 사람 우회다).
	if seedChain, seed := chainSeed("--branches"); seed != "" {
		println2("")
		println2("  ▸ 앞 체인 [" + seedChain + "] 이 회고에서 다음 물음의 시드를 남겼다 —")
		println2("    이 시드에서 인터뷰 질문을 짜라: gil interview " + name + " --ask <질문JSON|->")
		println2("")
		println2(seed)
	}
}

// ── gil chain-merge ──

// topologicalLeaves — 팁 목록에서 위상적 끝단만 추린다. 참조: topological_leaves.
func topologicalLeaves(tips []string) []string {
	shas := map[string]string{}
	for _, t := range tips {
		shas[t] = strings.TrimSpace(git("rev-parse", t))
	}
	var leaves []string
	leafShas := map[string]bool{}
	for _, a := range tips {
		covered := false
		for _, b := range tips {
			if a == b {
				continue
			}
			if gitOK("merge-base", "--is-ancestor", shas[a], shas[b]) && shas[a] != shas[b] {
				covered = true
				break
			}
		}
		if !covered && !leafShas[shas[a]] {
			leaves = append(leaves, a)
			leafShas[shas[a]] = true
		}
	}
	return leaves
}

func cmdChainMerge(args []string) {
	fs := newFlags("gil chain-merge")
	purpose := fs.str("purpose", "")
	// --resume: 충돌로 멈춘 순차 병합을 **이어서** 끝낸다.
	//
	// 왜 있어야 하나. 충돌 안내가 `gil chain-merge-continue` 를 치라고 말해 왔는데 **그런
	// 명령은 없다.** 사람은 병합이 반쯤 된 저장소 앞에서 존재하지 않는 명령을 치고, 거기서
	// 막힌다 — 도구가 자기가 만든 상태에서 빠져나올 길을 자기가 안 준 것이다. 없는 길을
	// 가리키는 안내는 안내가 아니라 막다른 골목이다(#91 의 정리 사다리와 같은 병).
	resume := fs.boolFlag("resume")
	pos := fs.parse(args)
	if len(pos) < 1 || (len(pos) < 2 && !*resume) {
		die("사용: gil chain-merge <newchain> --purpose <P> <tip>...\n" +
			"  충돌로 멈춘 뒤 이어가려면: gil chain-merge <newchain> --resume [남은 tip]...")
	}
	name := pos[0]
	tips := pos[1:]
	if *purpose == "" && !*resume {
		die("거부: --purpose 필요")
	}
	if !idRe.MatchString(name) {
		die("거부: 체인 이름 \"" + name + "\"은 소문자·숫자·하이픈만")
	}
	if have := chainPurpose(name, "--branches"); have != "" && !*resume {
		die("거부: 체인 \"" + name + "\" 이미 존재\n" +
			"  충돌로 멈춘 병합을 이어가는 것이면: gil chain-merge " + name + " --resume <남은 tip>...")
	} else if *resume && have == "" {
		die("거부: 체인 \"" + name + "\" 이 아직 없다 — 이어갈 병합이 없다.\n" +
			"  처음 여는 것이면: gil chain-merge " + name + " --purpose <P> <tip>...")
	}
	if *resume {
		// 사람이 손으로 끝낸 그 머지 커밋에는 트레일러가 없다 — gil 이 만든 자리가 아니니까.
		// 여기서 얹지 않으면 그 갈래는 **어느 병합의 것도 아니게** 되고, 그 뒤 gil 이 세는
		// 모든 것이 실제와 갈린다(#116 이 막으려던 바로 그 모양이다).
		if n := strings.Fields(strings.TrimSpace(git("log", "-1", "--format=%P"))); len(n) > 1 &&
			strings.TrimSpace(git("log", "-1", "--format="+trailer("Gil-Merge"))) == "" {
			cur := strings.TrimRight(git("log", "-1", "--format=%B"), "\n \t")
			merged := first9(n[1])
			if nm := strings.TrimSpace(git("name-rev", "--name-only", n[1])); nm != "" && nm != "undefined" {
				merged = nm
			}
			gitInput(cur+"\n\nGil-Chain: "+name+"\nGil-Merge: "+merged+"\n",
				"commit", "--amend", "-q", "-F", "-")
			stderr("  ✓ 사람이 끝낸 병합에 표식을 얹었다 (" + merged + ") — 통로를 하나로 유지한다.")
		}
	}
	if strings.TrimSpace(git("status", "--porcelain", "-uno")) != "" {
		die("거부: 추적 파일에 미커밋 변경이 있다 — 머지 전 정리하라")
	}

	leaves := topologicalLeaves(tips)
	var dropped []string
	for _, t := range tips {
		if !contains(leaves, t) {
			dropped = append(dropped, t)
		}
	}
	stderr("위상적 끝단 " + strconv.Itoa(len(leaves)) + "개: " + strings.Join(leaves, ", "))
	if len(dropped) > 0 {
		stderr("조상이라 생략(자동 포함): " + strings.Join(dropped, ", "))
	}

	head := strings.TrimSpace(git("rev-parse", "HEAD"))
	var toMerge []string
	for _, lf := range leaves {
		s := strings.TrimSpace(git("rev-parse", lf))
		if !gitOK("merge-base", "--is-ancestor", s, head) {
			toMerge = append(toMerge, lf)
		}
	}
	if len(toMerge) == 0 {
		if *resume {
			// 마지막 충돌을 사람이 끝낸 자리다. 표식은 위에서 얹었으니 여기서 끝이다 —
			// 이어가라고 해 놓고 "머지할 끝단이 없다"로 거부하면, 문법이 제 안내를 배신한다.
			println2("chain-merge: " + name + " — 이어가기 완료. 남은 끝단이 없다.")
			return
		}
		die("거부: 머지할 끝단이 없다 — HEAD가 이미 모두 포함")
	}

	for i, lf := range toMerge {
		subject := "gil " + name + " chain-merge (" + strconv.Itoa(i+1) + "/" + strconv.Itoa(len(toMerge)) + "): " + lf + " 병합"
		if _, err := gitTry("merge", "--no-ff", "-m", subject, lf); err != nil {
			conflicts := strings.TrimSpace(git("diff", "--name-only", "--diff-filter=U"))
			rest := "(없음)"
			if i+1 < len(toMerge) {
				rest = strings.Join(toMerge[i+1:], ", ")
			}
			stderr("⚠ 충돌 — [" + lf + "] 병합에서 멈춤 (" + strconv.Itoa(i+1) + "/" + strconv.Itoa(len(toMerge)) + ").\n" +
				"충돌 파일:\n" + conflicts + "\n\n" +
				"충돌 해결 체인을 열어 사이클로 해결하라. 해결 후 두 줄이다:\n" +
				"  git add <해결한 파일> && git commit --no-edit    (이 병합을 사람이 끝낸다)\n" +
				"  gil chain-merge " + name + " --resume" + rest2(toMerge, i) + "\n" +
				"남은 끝단: " + rest)
			gilExit(2) // 2 = 충돌로 멈춤 (거부 1과 구분)
		}
		// 머지 성공 → Gil-* 트레일러 amend. 첫 머지 커밋이 통합 체인 루트(chain-root).
		tr := [][2]string{{"Gil-Chain", name}}
		if i == 0 {
			tr = append(tr, [2]string{"Gil-Kind", "chain-root"})
			tr = append(tr, [2]string{"Gil-Chain-Purpose", *purpose})
		}
		tr = append(tr, [2]string{"Gil-Merge", lf})
		cur := strings.TrimRight(git("log", "-1", "--format=%B"), "\n \t")
		var trs []string
		for _, t := range tr {
			trs = append(trs, t[0]+": "+t[1])
		}
		msg := cur + "\n\n" + strings.Join(trs, "\n")
		gitInput(msg, "commit", "--amend", "-q", "-F", "-")
		stderr("  ✓ " + lf + " 병합 (" + strconv.Itoa(i+1) + "/" + strconv.Itoa(len(toMerge)) + ")")
	}
	newHead := strings.TrimSpace(git("rev-parse", "HEAD"))
	println2("chain-merge: " + name + " 개설 — " + strconv.Itoa(len(toMerge)) + "갈래 순차 병합 완료 (커밋 " + first9(newHead) + ")")
}


// rest2 — 충돌로 멈춘 자리에서 **아직 안 합친 끝단들**. 안내가 사람이 그대로 칠 수 있는
// 줄이어야 한다 — "남은 끝단: a, b" 를 읽고 손으로 옮겨 적게 하면 거기서 한 번 더 틀린다.
func rest2(toMerge []string, i int) string {
	if i+1 >= len(toMerge) {
		return "" // 남은 끝단이 없다 — 이름만으로 이어간다(표식을 얹고 끝난다)
	}
	return " " + strings.Join(toMerge[i+1:], " ")
}

// ── 작은 헬퍼 ──

func resolveBody(body, bodyFile string) string {
	if bodyFile == "-" {
		// stdin 으로 본문을 받는다 — 임시 .md 파일을 만들지 않고 heredoc·파이프로 바로
		// 넘길 수 있게(잉여 파일 방지). 예: gil step … --body-file - <<'EOF' … EOF
		b, err := io.ReadAll(os.Stdin)
		if err != nil {
			die("거부: --body-file - (stdin) 읽기 실패: " + err.Error())
		}
		return strings.TrimSpace(string(b))
	}
	if bodyFile != "" {
		b, err := os.ReadFile(bodyFile)
		if err != nil {
			die("거부: --body-file 읽기 실패: " + err.Error())
		}
		return strings.TrimSpace(string(b))
	}
	return body
}

func orNull(s string) string {
	if s == "" {
		return "null"
	}
	return s
}

func orDefault(s, def string) string {
	if s == "" {
		return def
	}
	return s
}

// ── 거부를 "다음 한 수"로 바꾸는 작은 도구들 (이슈 #47) ──
//
// gil 의 거부 메시지는 LLM 이 읽는 프롬프트다. "하지 마"까지만 하고 "대신 이걸 해"를 안 주면,
// 전진 편향이 있는 사용자는 막힌 곳을 **우회**하려 들지 도구가 원하는 길로 가지 않는다.
// 그래서 모든 거부는 (a) 정답 형식 (b) 지금 고를 수 있는 실제 후보 (c) 다음 명령을 담는다.

// sortedIDs — map 의 키를 정렬해 낸다. 거부 메시지의 후보 목록이 호출마다 순서가 바뀌면
// 사람도 LLM 도 "다른 답이 왔다"고 오해한다.
func sortedIDs(m map[string]bool) []string {
	var out []string
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// normalizeStepRef — 스텝을 가리키는 여러 표기를 짧은 이름(s1)으로 모은다(이슈 #47 G1).
// 받아주는 형태: s1 · <chain>/<cycle>/s1 · 커밋 해시(그 사이클 안의 스텝이면).
// 뜻이 명백한데 표기가 다르다는 이유로 거부하는 건 사고가 아니라 형식의 문제다.
func normalizeStepRef(ref, chain, cycle string, steps []node) string {
	ref = strings.TrimSpace(ref)
	if ref == "" {
		return ref
	}
	// 경로형: 앞의 chain/cycle 을 떼고 마지막 조각만 쓴다.
	if strings.Contains(ref, "/") {
		parts := strings.Split(ref, "/")
		ref = parts[len(parts)-1]
	}
	// 해시형: 이 사이클 안의 스텝 커밋을 가리키면 그 스텝 이름으로 바꾼다.
	for _, n := range steps {
		if n.sha == ref || strings.HasPrefix(n.sha, ref) && len(ref) >= 4 {
			return n.step
		}
	}
	return ref
}

// nearestKind — 오타에 가장 가까운 유효 kind 하나(편집거리 2 이내). "hypthesis"→"hypothesis".
func nearestKind(bad string) string {
	best, bestD := "", 3
	for _, k := range sortedIDs(kinds) {
		if d := editDistance(strings.ToLower(bad), k); d < bestD {
			best, bestD = k, d
		}
	}
	return best
}

// editDistance — 레벤슈타인. 근접 제안 하나 띄우려는 용도라 단순 구현으로 충분하다.
func editDistance(a, b string) int {
	la, lb := len(a), len(b)
	prev := make([]int, lb+1)
	cur := make([]int, lb+1)
	for j := 0; j <= lb; j++ {
		prev[j] = j
	}
	for i := 1; i <= la; i++ {
		cur[0] = i
		for j := 1; j <= lb; j++ {
			cost := 1
			if a[i-1] == b[j-1] {
				cost = 0
			}
			cur[j] = minInt(minInt(cur[j-1]+1, prev[j]+1), prev[j-1]+cost)
		}
		prev, cur = cur, prev
	}
	return prev[lb]
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// cycleCloseHint — 이 사이클이 왜 못 닫히는지와 **다음 올바른 한 수**(이슈 #47 G7).
//
// chain-close 가 "c001 이 안 닫혔다"고만 하면, 사용자는 gil close 를 시도했다가 또 거부당한다
// (fail 잎만 있으면 close 도 거부한다). 거부가 거부로 이어지면 사람은 우회하려 든다 —
// 막힌 이유마다 갈 길이 다르니, 그 사이클을 실제로 들여다보고 갈 길을 짚어준다.
func cycleCloseHint(chain, cycle string) string {
	nodes := collectNodes("--branches")
	hasChild := map[string]bool{}
	var mine []node
	for _, n := range nodes {
		if n.chain != chain || n.cycle != cycle {
			continue
		}
		mine = append(mine, n)
		if n.parent != "" && n.parent != "null" {
			hasChild[n.parent] = true
		}
	}
	if len(mine) == 0 {
		return "  → 이 사이클의 스텝을 못 찾았다. gil log " + chain + " 로 상태를 먼저 확인하라."
	}
	var live, dead, pending, unfinished int
	for _, n := range mine {
		if hasChild[n.step] {
			continue // 잎이 아니다
		}
		switch {
		case n.kind == "pending":
			pending++
		case isLiveLeaf(n):
			live++
		case isDeadLeaf(n):
			dead++
		default:
			unfinished++
		}
	}
	t := chain + "/" + cycle
	switch {
	case pending > 0:
		return "  → [" + t + "] 사람의 승인을 기다리는 중이다(pending). 사람이 판단해야 넘어간다:\n" +
			"      gil approve " + t + "   또는   gil reject " + t + " --to s1"
	case unfinished > 0:
		return "  → [" + t + "] 아직 마감되지 않은 잎이 있다(진행 중). 그 가지를 끝까지 끌고 가라:\n" +
			"      verify 까지 갔으면 → gil step " + t + " --kind analyze  → 그다음 success/fail"
	case live > 0:
		return "  → [" + t + "] 산 잎이 있다 — 바로 닫을 수 있다:  gil close " + t
	case dead > 0:
		return "  → [" + t + "] fail 잎만 있다 = 아직 답을 못 찾았다. 두 정직한 길:\n" +
			"      (1) 재분기 — gil step " + t + " --kind hypothesis --to s1 --inherit <죽은 가지의 교훈>\n" +
			"      (2) 포기   — gil close " + t + " --abandon  (막다른 길로 확인됐을 때만)"
	default:
		return "  → [" + t + "] gil log " + chain + " 로 상태를 확인하라."
	}
}

// unmergedSiblingsHint — 이 체인의 **닫혔는데 합류하지 않은** 사이클들. 그 산출물은 체인
// 트리에 없으므로 새 사이클이 못 본다(이슈 #103).
func unmergedSiblingsHint(chain string) []string {
	if !gitOK("rev-parse", "--verify", "-q", "refs/heads/"+chain) {
		return nil
	}
	closed := closedCycles("--branches")
	_, order := cyclesOf(chain)
	var pend []string
	total := 0
	for _, id := range order {
		if !closed[chain+"\x01"+id] {
			continue // 아직 안 닫혔다 — 합류를 말할 자리가 아니다
		}
		cyRef := chain + "-" + id
		if !gitOK("rev-parse", "--verify", "-q", "refs/heads/"+cyRef) {
			continue
		}
		if gitOK("merge-base", "--is-ancestor", cyRef, chain) {
			continue // 이미 체인의 것이다
		}
		out, err := gitTry("diff", "--name-only", chain, cyRef)
		if err != nil || strings.TrimSpace(out) == "" {
			continue // 파일 산출물이 없다 — 문서만 남긴 사이클이면 합류할 것이 없다
		}
		n := len(strings.Fields(strings.TrimSpace(out)))
		total += n
		pend = append(pend, id+"("+itoa(n)+"개)")
	}
	if len(pend) == 0 {
		return nil
	}
	L := []string{
		"  ⌂ 닫혔는데 **체인에 합류하지 않은** 사이클이 있다 — 그 산출물 " + itoa(total) +
			"개는 이 트리에 없다: " + strings.Join(pend, " "),
		"    이어받으려면 먼저 합류시켜라(그래야 계보가 파일 층위에서도 이어진다):",
	}
	for _, p := range pend {
		id := p
		if i := strings.Index(id, "("); i > 0 {
			id = id[:i]
		}
		L = append(L, "      gil merge "+chain+"/"+id+" --into "+chain+" --reason <왜 체인의 것인가>")
	}
	return append(L, "    (트리 복사로 때우면 내용은 옮겨지지만 합류 간선이 안 남아 그래프에서 승계가 사라진다.)")
}

// afterChainCloseNext — 체인을 닫은 뒤의 정본 순서. 셋을 이 순서로 가리킨다:
// 합류(이 국면을 층으로) → **개시 인터뷰**(다음 목적은 사람의 답에서) → 뿌리 묻기(계승/시조).
//
// 그리고 **닫힌 체인이 여럿이면 합류를 권한다.** 여러 국면의 지식을 하나로 모으는 것은 문법에
// 있는데(gil merge a b --into c) 안내에 없어서 아무도 안 썼다 — 그래서 나무가 일자로만 자랐다.
func afterChainCloseNext(chain string) []string {
	var L []string
	if hasDevLayer() && !gitOK("merge-base", "--is-ancestor", chain, devBranchName) {
		L = append(L,
			"NEXT ① 이 국면을 층으로 합류시켜라 — 다음 체인이 여기서 갈라진다:",
			"      gil merge "+chain+" --into "+devBranchName+" --reason <왜 이 국면이 층의 것인가>")
	}
	// 닫혔는데 아직 dev 로 안 간 형제 체인들 — 여럿이면 **하나로 모으는 길**을 보여준다.
	var alone []string
	roots := chainRoots("--branches")
	for c := range roots {
		if c == chain || !chainClosed(c, "--branches") {
			continue
		}
		if hasDevLayer() && gitOK("merge-base", "--is-ancestor", c, devBranchName) {
			continue // 이미 층에 모였다
		}
		alone = append(alone, c)
	}
	if len(alone) > 0 {
		sort.Strings(alone)
		all := append([]string{chain}, alone...)
		L = append(L,
			"  ⌘ 닫힌 체인이 더 있다: "+strings.Join(alone, " ")+
				" — **여러 국면의 지식을 하나로 모을 수 있다**(일자로만 자랄 이유가 없다):",
			"      gil merge "+strings.Join(all, " ")+" --into <모으는 체인|"+devBranchName+"> --reason <왜 한 줄기가 되나>")
	}
	return append(L,
		"NEXT ② 다음 국면은 **개시 인터뷰부터**다 — 목적을 네가 짓지 마라(이슈 #90):",
		"      gil intake <슬러그> --ask <질문JSON>        사람에게 먼저 묻는다",
		"      gil intake <슬러그> --ask-root              **어디서 이어받을지**를 묻는다(후보는 그래프가 낸다)",
		"      gil chain <새이름> --from-intake <슬러그> --purpose-from <질문번호> --criterion-from <번호>",
		"    ▸ 이 체인("+chain+")을 이어받을지, 아무것도 안 이어받는 시조로 갈지는 **사람이 정한다**.",
		"      네가 고르지 말고 --ask-root 로 물어라 — 그 답이 곧 분기 자리다.",
		"    ▸ 계승은 **하나일 필요가 없다**(이슈 #107): 두 국면의 지식이 함께 필요하면 둘 다 적어라.",
		"        gil chain <새이름> … --from "+chain+" --from <또 다른 닫힌 체인>",
		"      선언마다 커밋 그래프에 합류선이 남는다 — 여러 갈래의 지식이 하나로 모이는 그림이다.",
		"    ▸ 정말 아무것도 안 이어받는 것이면 그 판단도 기록한다: --orphan <왜 이어받지 않나>")
}

// cycleParentOf — 그 사이클이 **선언한** 부모 사이클(Gil-Cycle-Parent). 없으면 "".
// 형제를 권할 때 쓴다: 부모를 알아야 "같은 부모로 다시 열어라"가 실제로 칠 수 있는 한 줄이 된다.
func cycleParentOf(chain, cycle string) string {
	fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Cycle") + fsep +
		trailer("Gil-Cycle-Parent") + sep
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches"), sep) {
		ch, r1, ok := cut(strings.TrimSpace(rec), fsep)
		if !ok {
			continue
		}
		cy, pp, _ := cut(r1, fsep)
		if strings.TrimSpace(ch) != chain || strings.TrimSpace(cy) != cycle {
			continue
		}
		if p := strings.TrimSpace(pp); p != "" && p != "null" {
			return p
		}
	}
	return ""
}
