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
		"verify":     "이 스텝 본문 = 검증 보고서. 담아라: 실행한 절차(코드/명령)·측정 수치(표·코드블록)·관찰. (필수 플래그: --verdict supported|refuted — refuted 면 success 불가, fail/backtrack 만. 고정한 설계가 있으면 --plan-held|--plan-broke 로 그것에도 답한다.)",
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
		trs = append(trs, t[0]+": "+t[1])
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
	// 측정의 좌표(이슈 #79·#81): --dataset = 어디서 쟀나, --subject = 무엇을 쟀나.
	// 산문이 아니라 필드라야 기계가 대조한다. 여러 축이면 여러 번.
	datasets := fs.strList("dataset")
	datasetNote := fs.str("dataset-note", "")
	subjects := fs.strList("subject")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil open <chain>/<cycle> --author <who> --purpose <P> [--parent <cyc>...] [--refutes <c>/<cy>/<step>...] [--refines <c>/<cy>/<step>...] [--goal <달성 기준>] [--inherit <전수>] [--title T] [--body B | --body-file F|-]")
	}
	if *author == "" {
		die("거부: --author 필요")
	}
	if *purpose == "" {
		die("거부: --purpose 필요")
	}
	ref := pos[0]
	if !strings.Contains(ref, "/") {
		die("거부: <chain>/<cycle> 꼴이어야 함")
	}
	chain, cycle, _ := cut(ref, "/")
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
			"  열기 전에 인터뷰가 먼저다(이슈 #33, 상현님). 체인을 열면 인터뷰 사이클이 필수로 돈다.\n" +
			"  '됐다'는 판단이 LLM 자기확신이 아니라 사람이 세운 기준에 비추어 내려지도록 — 네가 기준을\n" +
			"  스스로 쓰지 말고 사람에게 물어라:\n" +
			"    1) 인터뷰 질문을 짜서 심어라: gil interview " + chain + " --ask <질문JSON|->\n" +
			"    2) 사람이 뷰어 폼으로 답하고 제출하면 기준이 확정된다.\n" +
			"    3) 그제서야 gil open " + ref + " 로 작업 사이클을 연다.")
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
	// 사이클 = 체인 안의 git 가지. 현재 위치(체인 팁/닫힌 사이클 끝)에서 분기.
	cb := cycleBranch(chain, cycle)
	commitOn(cb, "HEAD", subject, body, tr, true)
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
			"  이어갈 것이 있으면 닫힌 끝에서 새 체인을 연다:  gil chain <새체인> --parent " + chain + " --inherit <전수>")
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
	if *kind == "define" {
		die("거부: define 은 사이클의 뿌리 하나뿐(open 이 만드는 s1). 추가 문제 정의는 step 이 아니라 " +
			"다른 kind(hypothesis 등)나 새 사이클(gil open <chain>/<새사이클>)로 이어가라.")
	}
	showPurposeContext(chain, cycle, "")
	// 스텝 정정 무결성(AIL #12) — --supersede 대상은 (a)이 사이클에 실재하고 (b)이 스텝과 같은
	// kind 여야 하며 (c)종결 스텝(success/fail/pending)이 아니어야 한다. 종결의 정정은 정정이
	// 아니라 판정 번복이라 backtrack/refutes 영역이다(반증은 뒤집지 말고 새 간선으로 — #1·#2).
	if strings.TrimSpace(*supersede) != "" {
		var tgt *node
		for i := range steps {
			if steps[i].step == *supersede {
				tgt = &steps[i]
				break
			}
		}
		if tgt == nil {
			die("거부: --supersede " + *supersede + " 는 이 사이클에 없는 스텝이다.")
		}
		if tgt.kind != *kind {
			die("거부: --supersede 는 같은 kind 만 정정한다 — " + *supersede + " 는 " + tgt.kind +
				", 이 스텝은 " + *kind + ". (다른 kind 로 바꾸려면 정정이 아니라 새 스텝/새 가지다.)")
		}
		if tgt.kind == "success" || tgt.kind == "fail" || tgt.kind == "pending" {
			die("거부: 종결 스텝(" + tgt.kind + ")은 정정 대상이 아니다 — 판정을 뒤집으려면 " +
				"backtrack(hypothesis --to) 이나 소급 반증(--refutes)으로. 정정은 은폐가 아니라 이력에 남는다.")
		}
	}
	// analyze 는 순수 분석 — 종결(성공/실패/대기)은 별도 스텝(success/fail/pending)으로(상현님).
	// 하위호환: analyze --outcome 도 여전히 허용(옛 데이터·간단 사용).
	if *kind == "analyze" && *outcome != "" && !outcomes[*outcome] {
		die("거부: analyze --outcome 은 success|backtrack|fail 중 하나(생략 가능)")
	}
	// fail 종결 스텝은 죽은 잎 — 되돌아갈 곳을 --to 로 기록(벽의 지도).
	if *kind == "fail" && *to == "" {
		die("거부: fail 은 --to <조상 define> 필요 (되돌아갈 곳, 벽의 지도)")
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
	if tip != nil && !isBranching {
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
		newBranch := (*kind == "hypothesis" && *to != "") || *outcome == "backtrack" || len(*merge) > 0
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
			die(unterminatedRefusal(lv, "gil step "+ref+" --kind hypothesis --to "+*to+" … --leave-open"))
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
	if *kind == "hypothesis" && *to != "" {
		for _, ln := range lineageBrief(chain, cycle) {
			stderr(ln)
		}
	}
	reportGuide(*kind, bodyThin(stBody))
	guideNext(*kind) // 다음 강제 스텝을 무조건 각인 (AIL #41)
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
			if len(dead) == 0 {
				die("거부: 종결 잎(fail)이 하나도 없다 — 봉인할 죽은 가지가 없다. 먼저 analyze→fail 로 벽을 남겨라.")
			}
			sort.Strings(dead)
			subject := "gil " + chain + "/" + cycle + " close: " + orDefault(*verdict, "abandoned") + " (abandoned)"
			body := "죽은 사이클 봉인(abandoned). 죽은 잎 [" + strings.Join(dead, " ") + "]. " +
				"이 define 은 막다른 길로 판단돼 사람이 포기했다 — 벽의 지도로 영원히 남는다(이슈 #46)."
			tr := [][2]string{
				{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
				{"Gil-Kind", "close"}, {"Gil-Verdict", orDefault(*verdict, "abandoned")},
				{"Gil-Abandoned", "true"},
			}
			commit(subject, body, tr, true)
			println2("close: " + ref + " — abandoned (죽은 사이클로 봉인, 죽은 잎 [" + strings.Join(dead, " ") + "])")
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
		var hanging []node
		seenLeaf := map[string]bool{}
		for _, n := range all {
			if seenLeaf[n.step] {
				continue // 번호 중복(옛 그래프) — 같은 번호를 두 번 짚지 않는다
			}
			if hasChild[n.step] {
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
	fs.parse(args)
	if *at == "" || *tag == "" {
		die("사용: gil deploy --at <chain>/<cycle>/<step> --tag <v0.2.0> [--state staged|live] [--promote]\n" +
			"           [--target <배포 대상: host:port·환경>] [--url <릴리스URL>] [--title T]")
	}
	if *promote {
		*state = "live"
	}
	if *state != "staged" && *state != "live" {
		die("거부: --state 는 staged|live — 받음: \"" + *state + "\"\n" +
			"  staged = 배포 단위는 확정됐으나 아직 안 올라갔다(조율 대기).\n" +
			"  live   = 실제로 올라갔다. 나중에 올라가면: gil deploy --at … --tag " + *tag + " --promote")
	}
	// --at 파싱·검증: chain/cycle/step 세 조각이 다 있어야 하고 그 스텝이 실재해야 한다.
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
	defTitle := "배포 " + *tag + " — " + *at + " 에서 세상으로"
	if *state == "staged" {
		defTitle = "배포 준비 " + *tag + " — " + *at + " (staged, 아직 안 올라감)"
	} else if *promote {
		defTitle = "배포 승격 " + *tag + " — staged 였던 것이 실제로 올라갔다"
	}
	stTitle := orDefault(*title, defTitle)
	subject := "gil deploy " + *tag + ": " + stTitle
	dBody := resolveBody(*body, *bodyFile)
	if dBody == "" {
		if *state == "staged" {
			dBody = "배포 단위 확정(staged): " + *at + " 에서 " + *tag + " 를 자를 준비가 됐다. " +
				"아직 올라가지 않았다 — 실제 롤아웃 시 --promote 로 승격한다."
		} else if *promote {
			dBody = "배포 승격(live): " + *tag + " 가 실제로 올라갔다(앞서 staged 로 확정된 단위)."
		} else {
			dBody = "배포 지점: " + *at + " 에서 " + *tag + " 를 공개했다."
		}
		if *url != "" {
			dBody += " (" + *url + ")"
		}
	}
	tr := [][2]string{
		{"Gil-Deploy", *tag},
		{"Gil-Deploy-At", *at},
		{"Gil-Deploy-State", *state}, // staged|live (이슈 #56) — 기계가 읽는 상태
	}
	if t := strings.TrimSpace(*deployTarget); t != "" {
		tr = append(tr, [2]string{"Gil-Deploy-Target", t}) // 어디로 나갔나(#56)
	}
	if *url != "" {
		tr = append(tr, [2]string{"Gil-Deploy-Url", *url})
	}
	commit(subject, dBody, tr, true)
	if *state == "staged" {
		println2("deploy: " + *tag + " @ " + *at + " 📦 staged — 배포 단위는 확정, 아직 안 올라갔다.")
		println2("  ▸ 실제로 올라가면 승격하라: gil deploy --at " + *at + " --tag " + *tag + " --promote")
		println2("  ▸ 그 전까지 이 태그는 '배포됨'으로 읽히지 않는다 — 없는 배포를 주장하지 않는다.")
	} else {
		println2("deploy: " + *tag + " @ " + *at + " 🚀 (뷰어에 배포 마커로 표시됨)")
	}
	if *url != "" {
		println2("  릴리스: " + *url)
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
		interviewWatch(chain, *wait, *timeout, *then)
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

// interviewAsk — 질문지를 검증해 심는다. gil interview(체인 인터뷰)와 gil intake
// (체인 앞 개시 인터뷰)가 같은 기계를 쓴다 — 뷰어·폴링·--wait 이 손 안 대고 동작하도록.
// extra 는 심는 커밋에 덧붙일 트레일러(개시 인터뷰의 Gil-Intake 등).
func interviewAsk(chain, ask, title string, extra [][2]string) {
	// 질문 JSON 을 읽고 구조를 검증한다 — 빈 폼·잘못된 type 을 뷰어에 보내기 전에 여기서 거부.
	raw := resolveBody("", ask)
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
	if openN == 0 || qs[0].Type != "text" {
		die("거부: 인터뷰의 **첫 질문은 열린 질문(text)** 이어야 한다 — 선택지부터 내밀면 " +
			"사람은 네 가설 공간 안에서만 고르게 된다(이슈 #90).\n" +
			"  지금 첫 질문: " + qs[0].Q + "  (" + qs[0].Type + ")\n" +
			"  · 먼저 물어라: {\"q\":\"무엇을 하려고 하십니까? 지금 풀려는 문제를 그대로 적어 주세요\",\"type\":\"text\"}\n" +
			"  · 선택지 질문은 그 **다음**에 둔다 — 열린 답을 받고 나서 좁히는 것이 순서다.\n" +
			"  기준 문서는 '사람이 세운 자'여야 한다. 네가 세운 자에 사람이 서명한 것이 되면 " +
			"그 뒤의 판정은 전부 형식만 남는다.")
	}
	if openN*2 < len(qs) && len(qs) >= 4 {
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
	// 체인 브랜치 위에 심는다(레퍼런스가 그 체인에 커밋될 자리). HEAD 가 다른 데면 맞춘다.
	// 개시 인터뷰(gil intake)는 아직 브랜치가 없다 — 없으면 대문(HEAD) 위에 심는다.
	// gitTry 여야 한다: git() 은 실패에 죽고, "브랜치 없음"은 여기서 정상 흐름이다(이슈 #90).
	if raw, err := gitTry("rev-parse", "--verify", "-q", "refs/heads/"+chain); err == nil {
		if tip := strings.TrimSpace(raw); tip != "" {
			alignHeadToTip(first9(tip), chain)
		}
	}
	commit(subject, b.String(), tr, true)
	println2("interview: " + chain + " — 질문 " + strconv.Itoa(len(qs)) + "개 심음. 뷰어에서 사람이 폼으로 답한다.")
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
func interviewWatch(chain string, wait bool, timeoutS, then string) {
	if chainPurpose(chain, "--branches") == "" && intakeState(chain) == "" {
		die("거부: 체인 \"" + chain + "\" 선언된 적 없음 — 먼저 gil chain 으로 열어라.")
	}
	// 재인터뷰가 열려 있으면 그게 지금 상태다 — 옛 done 을 보고하면 거짓말이 된다(이슈 #75).
	done := func() bool { return interviewState(chain) == "done" }
	report := func() {
		println2("interview: " + chain + " — done (사람이 제출해 기준 문서가 확정됐다)")
		if ref := chainReferenceText(chain, "--branches"); strings.TrimSpace(ref) != "" {
			println2("")
			println2("── 확정된 기준 문서 ──")
			println2(ref)
		}
		println2("▸ 이제 작업 사이클을 열 수 있다: gil open " + chain + "/<cycle> --author <a> --purpose <p>")
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
	println2("NEXT 닫힌 체인의 끝에서 새 체인을 연다: gil chain <name> --purpose <다음 국면의 목적>")
	if seedBody != "" {
		println2("     시드를 남겼다 — 다음 체인의 인터뷰 질문을 이 시드에서 짜라(시드는 기준이 아니다.")
		println2("     기준은 언제나 사람의 답이다: gil interview <새체인> --ask ...).")
	}
	println2("     이전 체인의 교훈(gil memory read)을 새 체인 목적·첫 가설에 이어받아라.")
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
	from := fs.str("from", "")
	// --from-intake <슬러그> / --purpose-from <질문번호> (이슈 #90): 체인의 목적을 **사람의
	// 답에서 그대로 들어 올린다.** 에이전트가 다시 쓰지 않는다 — 요약도 정제도 창작이고,
	// 창작하는 순간 기준 문서는 '사람이 세운 자'가 아니게 된다.
	fromIntake := fs.str("from-intake", "")
	purposeFrom := fs.str("purpose-from", "")
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
		println2("  ▸ 이제 **어디서 분기할지**를 그 답에 비추어 정하라 — --from(이어받음) / " +
			"--parallel-with(나란히) / 아무것도 없으면 대문에서 새 계보.")
	}
	if *purpose == "" {
		die("거부: --purpose 필요 — 또는 사람에게 먼저 물어 그 답을 인용하라(이슈 #90):\n" +
			"    gil intake <슬러그> --ask '[{\"q\":\"무엇을 하려고 하십니까\",\"type\":\"text\"}]'\n" +
			"    (답이 오면)  gil chain " + name + " --from-intake <슬러그> --purpose-from 1\n" +
			"  네가 목적을 창작해 체인을 열면 사람은 방향을 정하는 자리가 아니라 승인하는 자리에 앉는다.")
	}
	if !idRe.MatchString(name) {
		die("거부: 체인 이름 \"" + name + "\"은 소문자·숫자·하이픈만")
	}
	if chainPurpose(name, "HEAD") != "" {
		die("거부: 체인 \"" + name + "\" 이미 목적 선언됨 (chain은 새 체인만)")
	}
	if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+name) {
		die("거부: 브랜치 " + name + " 이미 있음 (체인은 새 브랜치만)")
	}
	// --from 검증(이슈 #68): 이어받는다고 선언한 체인은 실재하고 **닫혀 있어야** 한다.
	// 그래야 "닫힌 체인 끝에서 연다"가 사실이 된다.
	if f := strings.TrimSpace(*from); f != "" {
		if chainPurpose(f, "--branches") == "" {
			die("거부: --from \"" + f + "\" 체인이 없다.")
		}
		if !chainClosed(f, "--branches") {
			die("거부: --from \"" + f + "\" 은 아직 닫히지 않았다 — 이어받으려면 먼저 닫아라:\n" +
				"    gil chain-close " + f + " --retro <회고파일|->\n" +
				"  (동시에 굴리는 트랙이면 --parallel-with " + f + " 다.)")
		}
	}
	// 열린 체인이 있으면 — 이어받는 것이 아니라 나란히 여는 것이므로 — 선언을 요구한다.
	// gil 자신의 규칙("닫힌 체인 끝에서만")과 실동작의 어긋남을 여기서 없앤다.
	if open := openChains(); len(open) > 0 {
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
	refBody := resolveBody("", *reference)
	if strings.TrimSpace(refBody) != "" {
		body += "\n\n── 기준 문서(레퍼런스 트루스, 이슈 #33) ──\n\n" + refBody
	}
	tr := [][2]string{
		{"Gil-Chain", name}, {"Gil-Kind", "chain-root"},
		{"Gil-Chain-Purpose", *purpose},
	}
	if *requireDataset {
		tr = append(tr, [2]string{"Gil-Require-Dataset", "true"}) // 사이클마다 평가셋 선언 필수(#79)
	}
	if *requireSubject {
		tr = append(tr, [2]string{"Gil-Require-Subject", "true"}) // 사이클마다 측정 대상 선언 필수(#81)
	}
	if strings.TrimSpace(refBody) != "" {
		tr = append(tr, [2]string{"Gil-Reference", "true"}) // 기준 문서 있음(본문에 전문)
	}
	if strings.TrimSpace(*inherit) != "" {
		tr = append(tr, [2]string{"Gil-Inherit", *inherit}) // 물려받은 전수(AIL #3)
	}
	for _, p := range *parallelWith {
		tr = append(tr, [2]string{"Gil-Parallel-With", p}) // 병렬 트랙 선언(이슈 #54)
	}
	if f := strings.TrimSpace(*from); f != "" {
		tr = append(tr, [2]string{"Gil-Chain-From", f}) // 이어받는 체인 선언(이슈 #68)
	}
	// 체인 = git 브랜치. 현재 위치(대문/닫힌 체인 끝)에서 분기해 대문을 이어받는다(orphan 아님).
	//
	// 병렬이면 **그 체인이 시작한 자리와 같은 자리**에서 갈라진다(이슈 #54·#65). 선언만 하고
	// 위상은 적층으로 두면, 커밋 그래프는 여전히 "뒤에 왔으니 이어받았다"고 말한다 — 적층
	// 자체를 없애야 두 진실이 하나가 된다.
	base := "HEAD"
	if f := strings.TrimSpace(*from); f != "" {
		// 선언한 그 체인의 **끝**에서 갈라진다(이슈 #68). 이름이 봉인을 가리키므로(이슈 #66)
		// 그 ref 가 곧 끝이다. 선언과 그래프가 같은 말을 하게 된다.
		base = f
	} else if len(*parallelWith) > 0 {
		if b := chainRootParent((*parallelWith)[0]); b != "" {
			base = b
		}
	}
	commitOn(name, base, subject, body, tr, true)
	println2("chain: " + name + " 개설 (브랜치 " + name + ") — 목적: " + *purpose)
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
	pos := fs.parse(args)
	if len(pos) < 2 {
		die("사용: gil chain-merge <newchain> --purpose <P> <tip>...")
	}
	name := pos[0]
	tips := pos[1:]
	if *purpose == "" {
		die("거부: --purpose 필요")
	}
	if !idRe.MatchString(name) {
		die("거부: 체인 이름 \"" + name + "\"은 소문자·숫자·하이픈만")
	}
	if chainPurpose(name, "HEAD") != "" {
		die("거부: 체인 \"" + name + "\" 이미 존재")
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
				"충돌 해결 체인을 열어 사이클로 해결하라. 해결 후:\n" +
				"  git add <해결한 파일> && gil chain-merge-continue " + name + " " + lf + "\n" +
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
