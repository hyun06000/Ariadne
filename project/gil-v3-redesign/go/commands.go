// commands.go — 쓰기 명령 (커밋 노드를 새긴다, 손 커밋의 코드화).
//
// 참조 구현(gil.py)의 cmd_open·cmd_step·cmd_close·cmd_chain·cmd_chain_merge를 옮긴다.
// 진실원은 커밋 그래프 — 모든 위계는 Gil-* 트레일러로, 본문은 커밋 로그로 산다.
package main

import (
	"io"
	"os"
	"sort"
	"strconv"
	"strings"
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
		"hypothesis": "이 스텝 본문 = 가설 보고서. 담아라: 세운 가설·그 근거(관찰/데이터)·검증 방법·기대 결과. (필수 플래그: --falsify 반증조건, --falsify-to 반증 시 되돌아갈 define.)",
		"verify":     "이 스텝 본문 = 검증 보고서. 담아라: 실행한 절차(코드/명령)·측정 수치(표·코드블록)·관찰. (필수 플래그: --verdict supported|refuted — refuted 면 success 불가, fail/backtrack 만.)",
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
		stderr("  ⚠ 본문이 얇다 — " + kind + " 스텝은 보고서여야 한다. 임시 .md 파일 만들지 말고 stdin 으로 바로 넘겨라:")
		stderr("      gil step … --body-file - <<'EOF'  …보고서…  EOF   (또는 파이프)")
		stderr("    스텝 본문은 커밋이라 나중에 못 고친다(append-only) — 지금 이 스텝을 만들 때 채워라. 얇게 두면 얇은 채로 영원히 남는다.")
	}
	stderr("  ▸ " + g)
	stderr("    (뷰어가 이 본문을 마크다운으로 렌더한다 — 표·코드블록·이미지 ![](data:...) 가능.)")
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

// currentCycle — 이 (chain,cycle)의 스텝들. 참조: _current_cycle. collectNodes는 새→old 순.
func currentCycle(chain, cycle string) []node {
	var out []node
	for _, n := range collectNodes("HEAD") {
		if n.chain == chain && n.cycle == cycle {
			out = append(out, n)
		}
	}
	return out
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
	inherit := fs.str("inherit", "") // 물려받은 지식·전제·교훈(AIL #3): 계보 간선 생기면 필수
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil open <chain>/<cycle> --author <who> --purpose <P> [--parent <cyc>...] [--refutes <c>/<cy>/<step>...] [--inherit <전수>] [--title T] [--body B | --body-file F|-]")
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
	if len(currentCycle(chain, cycle)) > 0 {
		die("거부: " + ref + " 이미 존재 (open은 새 사이클만)")
	}
	// 닫힌 부모 체인 사이클 금지 (dev/c002 죽은 잎이 가르친 규칙)
	if chainClosed(chain, "HEAD") {
		why := "닫힌 체인"
		if chainHasChildren(chain, "--all") {
			why = "자식 체인이 분기함"
		}
		die("거부: \"" + chain + "\"은 닫힌 부모 체인(" + why + ") — 그 안에 새 사이클을 열 수 없다. " +
			"새 자식 체인을 열어라 (gil chain <name> --purpose ...). 닫힌 부모에서 다시 자라면 배포 계보가 꼬인다.")
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
	// 제안 A (AIL #3) — 계보 간선이 새로 생기면 물려받은 지식·전제·교훈을 명시한다. 부모
	// 사이클(--parent)이나 소급 반증(--refutes) 간선이 있으면 --inherit 필수 — 간선의 존재는
	// 문법이, 내용의 진실성은 존재가 보증한다("정직 강제 불가, 은폐 영속화만 차단", AIL #1).
	if (len(*parents) > 0 || len(*refutes) > 0) && strings.TrimSpace(*inherit) == "" {
		die("거부: 계보 간선(--parent/--refutes)이 있으면 --inherit <전수> 필요 — 부모에게서 물려받은 " +
			"사전지식·전제·교훈을 명시하고 출발하라. 계보를 포인터 그물이 아니라 지식의 강으로(AIL #3).")
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
	if body == "" {
		body = "(문제 미기술 — 본문을 커밋 수정으로 채우라)"
	}
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
		{"Gil-Step", "s1"}, {"Gil-Kind", "define"}, {"Gil-Parent", "null"},
		{"Gil-Cycle-Author", *author}, {"Gil-Cycle-Purpose", *purpose},
	}
	for _, par := range *parents {
		tr = append(tr, [2]string{"Gil-Cycle-Parent", par})
	}
	for _, rf := range *refutes {
		tr = append(tr, [2]string{"Gil-Refutes", rf}) // 소급 반증 간선(AIL #1 B)
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
	reportGuide("define", bodyThin(body))
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
	// 제안 1 (AIL #1): verify 는 판정을 문법으로 요구한다. supported=가설 지지, refuted=반증.
	verdict := fs.str("verdict", "") // verify 전용
	// 제안 B (AIL #1): 소급 반증 간선 — 이 스텝이 앞서 닫힌 supported verify 판정을 뒤늦게
	// 반증한다. verify 스텝에서 우회를 관측한 순간이 가장 정직한 자리라 step 도 받는다.
	refutes := fs.strList("refutes")
	inherit := fs.str("inherit", "") // 물려받은 전수(AIL #3): 머지/refutes 간선 생기면 필수

	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil step <chain>/<cycle> --kind K [...]")
	}
	ref := pos[0]
	chain, cycle, _ := cut(ref, "/")
	steps := currentCycle(chain, cycle)
	if len(steps) == 0 {
		die("거부: " + ref + " 없음 (먼저 gil open)")
	}
	if !kinds[*kind] {
		die("거부: 알 수 없는 kind \"" + *kind + "\"")
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
	}
	resolveRefutes(*refutes) // 소급 반증 대상 무결성(AIL #1 B)
	// 제안 A (AIL #3) — 머지/소급반증 간선이 새로 생기면 --inherit 필수. 같은 사이클 안
	// 선형 스텝(직전 Gil-Parent)은 전수랄 게 없어 면제 — 매 스텝 강제는 형해화만 낳는다
	// (clew@AIL 실사용: 같은 내용 복붙). 계보가 실제로 갈라지는 자리에만 요구한다.
	if (len(*merge) > 0 || len(*refutes) > 0) && strings.TrimSpace(*inherit) == "" {
		die("거부: 계보 간선(--merge/--refutes)이 있으면 --inherit <전수> 필요 — 이 갈래에서 " +
			"무엇을 물려받았나(머지) 혹은 무엇을 뒤집고 무엇은 계승하나(refutes)를 명시하라(AIL #3).")
	}

	tip := growingTip(steps)
	tipID := ""
	if tip != nil {
		tipID = tip.step
	}
	// pending 가드(상현님): pending 스텝 뒤에는 사람의 명시적 승인/기각만 허용한다.
	// 서브에이전트가 pending 직후 스스로 analyze 로 넘어가던 것을 구조로 막는다.
	if tip != nil && tip.kind == "pending" {
		die("거부: " + ref + " 팁이 pending(" + tip.step + ") — 사람의 답을 먼저 받아야 한다. " +
			"승인: gil approve " + ref + "  |  기각: gil reject " + ref + " --to <조상 define>")
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
	// 제안 1 success 가드 (AIL #1) — 직전 verify 가 가설을 반증(refuted)했으면 success 를
	// 문법으로 거부한다. 반증 뒤에는 fail(죽은 잎) 이나 backtrack(새 가지)만 허용 — 마찰이
	// 있는데 success 로 뭉개고 앞으로 가던 길(체인 일자화의 핵심)을 구조로 막는다.
	if *kind == "success" && tip != nil && tip.kind == "verify" && tip.verdict == "refuted" {
		die("거부: 직전 verify(" + tip.step + ")가 가설을 반증(refuted)했다 — success 로 닫을 수 없다. " +
			"fail(gil step … --kind fail --to <define>) 로 죽은 잎을 남기거나 " +
			"backtrack(gil step … --kind hypothesis --to <define>) 으로 새 가지를 파라(AIL #1).")
	}
	defineIDs := map[string]bool{}
	liveLeaves := map[string]bool{}
	for _, s := range steps {
		if s.kind == "define" {
			defineIDs[s.step] = true
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
		if !defineIDs[*falsifyTo] {
			die("거부: --falsify-to " + *falsifyTo + "는 이 사이클의 조상 define이어야 함")
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
	}

	// stepSHA — 이 사이클에서 특정 스텝 id 의 커밋 sha(형제 가지 분기 지점).
	stepSHA := map[string]string{}
	for _, s := range steps {
		stepSHA[s.step] = s.sha
	}

	var parent string
	var mergeRest []string
	var branch, createFrom string // 분기할 때만 채움(진짜 git 브랜치)
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
		// 되돌아가 새 형제 가지 — 조상 define 커밋에서 진짜 git 브랜치를 분기.
		if !defineIDs[*to] {
			die("거부: --to " + *to + "는 조상 define이어야 함")
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
			die("거부: backtrack은 --to <조상 define> 필요 (되돌아갈 곳)")
		}
		if !defineIDs[*to] {
			die("거부: --to " + *to + "는 조상 define이어야 함")
		}
		parent = orNull(tipID) // 죽은 잎은 현재 가지 tip 에 그대로 박는다(벽의 지도)
	case *kind == "fail":
		// 종결 죽은 잎 — 현재 가지 tip 에 박고, 되돌아갈 조상 define 을 --to 로 기록.
		if !defineIDs[*to] {
			die("거부: --to " + *to + "는 조상 define이어야 함")
		}
		parent = orNull(tipID)
	default:
		// success·analyze·verify 등 선형 진행: 현재 가지 tip 에 이어서.
		parent = orNull(tipID)
	}

	sid := nextStepID(steps)
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
	}
	if *kind == "verify" {
		tr = append(tr, [2]string{"Gil-Verdict", *verdict}) // supported|refuted (제안 1)
	}
	for _, rf := range *refutes {
		tr = append(tr, [2]string{"Gil-Refutes", rf}) // 소급 반증 간선(AIL #1 B)
	}
	if strings.TrimSpace(*inherit) != "" {
		tr = append(tr, [2]string{"Gil-Inherit", *inherit}) // 물려받은 전수(AIL #3)
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
	println2("step: " + ref + "/" + sid + " " + *kind + " ←" + parent + tail)
	if len(*refutes) > 0 {
		guideRefutes(*refutes)
	}
	reportGuide(*kind, bodyThin(stBody))
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
	steps := currentCycle(chain, cycle)
	sid := nextStepID(steps)
	stTitle := orDefault(*title, "승인 — "+tip.step+" 의 대기를 사람이 승인")
	subject := "gil " + chain + "/" + cycle + "/" + sid + " success: " + stTitle
	stBody := resolveBody(*body, *bodyFile)
	if stBody == "" {
		stBody = "사람이 pending(" + tip.step + ")을 승인했다 — 이 가지는 산 잎."
	}
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
		{"Gil-Step", sid}, {"Gil-Kind", "success"}, {"Gil-Parent", tip.step},
		{"Gil-Approval", "approved"},
	}
	commit(subject, stBody, tr, true)
	println2("approve: " + ref + "/" + sid + " success (사람 승인 ←" + tip.step + ")")
	reportGuide("success", bodyThin(stBody))
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
	defineIDs := map[string]bool{}
	for _, s := range steps {
		if s.kind == "define" {
			defineIDs[s.step] = true
		}
	}
	if !defineIDs[*to] {
		die("거부: --to " + *to + "는 조상 define이어야 함")
	}
	sid := nextStepID(steps)
	stTitle := orDefault(*title, "기각 — "+tip.step+" 의 대기를 사람이 기각")
	subject := "gil " + chain + "/" + cycle + "/" + sid + " fail: " + stTitle
	stBody := resolveBody(*body, *bodyFile)
	if stBody == "" {
		stBody = "사람이 pending(" + tip.step + ")을 기각했다 — 죽은 잎. " + *to + " 로 되돌아간다."
	}
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
		{"Gil-Step", sid}, {"Gil-Kind", "fail"}, {"Gil-Parent", tip.step},
		{"Gil-Backtrack", *to}, {"Gil-Approval", "rejected"},
	}
	commit(subject, stBody, tr, true)
	println2("reject: " + ref + "/" + sid + " fail (사람 기각 ⤳" + *to + ")")
	reportGuide("fail", bodyThin(stBody))
}

// ── gil close ──
func cmdClose(args []string) {
	fs := newFlags("gil close")
	verdict := fs.str("verdict", "supported")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil close <chain>/<cycle> [--verdict V]")
	}
	ref := pos[0]
	chain, cycle, _ := cut(ref, "/")
	steps := currentCycle(chain, cycle)
	if len(steps) == 0 {
		die("거부: " + ref + " 없음")
	}
	var live []string
	for _, s := range steps {
		if isLiveLeaf(s) {
			live = append(live, s.step)
		}
	}
	if len(live) == 0 {
		die("거부: 산 잎(success 스텝) 없음 — 닫을 수 없다")
	}
	sort.Strings(live)
	subject := "gil " + chain + "/" + cycle + " close: " + *verdict
	body := "사이클 봉인. 산 잎 [" + strings.Join(live, " ") + "]. 판정: " + *verdict + "."
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
		{"Gil-Kind", "close"}, {"Gil-Verdict", *verdict},
	}
	commit(subject, body, tr, true)
	println2("close: " + ref + " — " + *verdict)
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
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil chain-close <chain> [--verdict V]")
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
		die("거부: 아직 닫히지 않은 사이클이 남음 — 먼저 gil close 로 닫아라: " +
			strings.Join(open, " ") + ". (완결의 정의: 모든 사이클이 닫혀야 체인을 닫는다.)")
	}
	subject := "gil " + chain + " chain-close: " + *verdict
	body := "체인 [" + chain + "] 봉인. 판정: " + *verdict + ".\n\n" +
		"이 국면은 완결됐다. 다음은 이 닫힌 끝에서 새 체인을 연다 " +
		"(gil chain <name> --purpose ...) — 대문·존재·교훈이 체인을 넘어 이어진다."
	tr := [][2]string{
		{"Gil-Chain", chain}, {"Gil-Kind", "chain-close"}, {"Gil-Verdict", *verdict},
	}
	commit(subject, body, tr, true)
	println2("chain-close: " + chain + " — " + *verdict)
	println2("NEXT 닫힌 체인의 끝에서 새 체인을 연다: gil chain <name> --purpose <다음 국면의 목적>")
	println2("     이전 체인의 교훈(gil memory read)을 새 체인 목적·첫 가설에 이어받아라.")
}

// ── gil chain ──
func cmdChain(args []string) {
	fs := newFlags("gil chain")
	purpose := fs.str("purpose", "")
	inherit := fs.str("inherit", "") // 물려받은 전수(AIL #3). 체인 부모는 위상 유도라 선택.
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil chain <name> --purpose <자연어> [--inherit <전수>]")
	}
	name := pos[0]
	if *purpose == "" {
		die("거부: --purpose 필요")
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
	subject := "gil " + name + " chain: " + *purpose
	body := "체인 [" + name + "] 개설. 목적: " + *purpose + "\n\n" +
		"이 목적은 이후 사이클·스텝 시작 때 떠올라, 그 작업이 이 체인에 정합하는지 판단하는 근거가 된다."
	tr := [][2]string{
		{"Gil-Chain", name}, {"Gil-Kind", "chain-root"},
		{"Gil-Chain-Purpose", *purpose},
	}
	if strings.TrimSpace(*inherit) != "" {
		tr = append(tr, [2]string{"Gil-Inherit", *inherit}) // 물려받은 전수(AIL #3)
	}
	// 체인 = git 브랜치. 현재 위치(대문/닫힌 체인 끝)에서 분기해 대문을 이어받는다(orphan 아님).
	commitOn(name, "HEAD", subject, body, tr, true)
	println2("chain: " + name + " 개설 (브랜치 " + name + ") — 목적: " + *purpose)
	// 체인은 거의 늘 앞 체인의 교훈 위에 선다 — 부모가 위상 유도라 강제는 안 하되 안내(AIL #3).
	if strings.TrimSpace(*inherit) == "" {
		stderr("  ▸ 이 체인이 앞 체인/사이클에서 물려받은 전제·교훈이 있으면 --inherit 로 명시하라(AIL #3) — 계보를 지식의 강으로.")
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
			os.Exit(2) // 2 = 충돌로 멈춤 (거부 1과 구분)
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
