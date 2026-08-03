// intake.go — **체인보다 먼저 사람에게 묻는다** (이슈 #90, 상현님).
//
// 왜. gil 의 정문에 순환이 있었다:
//
//	체인 생성 --purpose 필요--> 목적
//	   ^                          |
//	   +------- 인터뷰 <----------+   인터뷰는 체인이 있어야 열린다
//
// 목적 ⇐ 인터뷰 ⇐ 체인 ⇐ 목적. 이 순환을 지금까지는 **에이전트의 추측으로 끊어** 왔다:
// 에이전트가 목적을 창작해 체인을 열고, 그 다음에 사람에게 물었다. 그러면 사람은 방향을
// 정하는 자리가 아니라 이미 정해진 방향을 승인하는 자리에 앉는다. 기준 문서는 "사람이 세운
// 자"가 아니라 "에이전트가 세운 자에 사람이 서명한 것"이 되고, 그 뒤의 판정은 형식만 남는다.
//
// 그리고 상현님이 짚은 더 실질적인 손해: **어디서부터 분기할지를 인터뷰 내용을 보고 파악해야
// 하는데, 분기를 쳐 버리고 인터뷰를 하면 그 정보가 무용지물이 된다.** 뿌리를 정하는 근거가
// 뿌리를 정한 뒤에 도착한다.
//
// 그래서 체인 **앞에** 한 칸을 둔다. intake 는 체인 없이 열리는 인터뷰다. 사람이 답하면
// 그 답이 (1) 체인의 목적이 되고 — 에이전트가 고쳐 쓰지 않고 **그대로 인용**한다 —
// (2) 어디서 분기할지의 근거가 된다.
package main

import (
	"encoding/json"
	"sort"
	"strconv"
	"strings"
)

// jsonQuote — 문자열을 JSON 리터럴로. 도구가 질문지를 조립할 때 쓴다.
func jsonQuote(s string) string {
	b, err := json.Marshal(s)
	if err != nil {
		return "\"\""
	}
	return string(b)
}

// intakePlant — gil 이 직접 만든 질문지를 심는다(열린 질문 규칙 면제).
func intakePlant(slug, questionsJSON, title string) {
	intakeMode = slug
	interviewAskInline(slug, questionsJSON, title, [][2]string{{"Gil-Intake", slug}}, true)
}

// isIntakeSlug — 이 이름이 개시 인터뷰 슬러그인가. intake 커밋은 뷰어가 폼을 그리도록
// Gil-Chain 을 함께 달기 때문에, 걸러 주지 않으면 **아직 체인이 아닌 것이 체인 목록에**
// 섞인다(뿌리 후보에 자기 자신이 뜨는 것을 실측으로 잡았다).
func isIntakeSlug(name string) bool {
	return intakeState(name) != "" && chainPurpose(name, "--branches") == ""
}

// atoiSafe — 실패하면 0. 질문 번호처럼 "없으면 없는 것"인 자리에 쓴다.
func atoiSafe(s string) int {
	n, err := strconv.Atoi(strings.TrimSpace(s))
	if err != nil {
		return 0
	}
	return n
}

// intakeMode — gil intake 로 들어왔을 때의 슬러그. 인터뷰 기계의 '체인이 있어야 한다'
// 검사를 이 슬러그에 한해 면제한다(개시 인터뷰는 정의상 체인보다 먼저다).
var intakeMode string

// intakeState — 이 슬러그의 개시 인터뷰 상태: "" (없음) · "pending" · "done".
// 최신 마커가 상태를 정한다(#75 와 같은 규칙 — 옛 done 을 보고 재인터뷰를 못 보면 안 된다).
func intakeState(slug string) string {
	out := gitlog("--format="+trailer("Gil-Intake")+fsep+trailer("Gil-Interview")+sep,
		"--branches", "--")
	for _, rec := range strings.Split(out, sep) {
		rec = strings.Trim(rec, "\n")
		if rec == "" {
			continue
		}
		s, iv, _ := cut(rec, fsep)
		if strings.TrimSpace(s) != slug {
			continue
		}
		if st := strings.TrimSpace(iv); st != "" {
			return st // git log 는 새→옛 — 처음 만난 것이 최신이다
		}
	}
	return ""
}

// intakeAnswers — 확정된 개시 인터뷰의 기준 문서 본문(사람이 답한 것). 없으면 "".
func intakeAnswers(slug string) string {
	out := gitlog("--format="+trailer("Gil-Intake")+fsep+trailer("Gil-Interview")+fsep+"%B"+sep,
		"--branches", "--")
	for _, rec := range strings.Split(out, sep) {
		rec = strings.Trim(rec, "\n")
		if rec == "" {
			continue
		}
		f := strings.SplitN(rec, fsep, 3)
		if len(f) < 3 || strings.TrimSpace(f[0]) != slug || strings.TrimSpace(f[1]) != "done" {
			continue
		}
		return f[2]
	}
	return ""
}

// intakeAnswerN — 누적 문서에서 **n번째 답**을 그대로 떼어 온다(1부터).
//
// 왜 '몇 번째 답'인가. 심층 인터뷰는 차수를 쌓으므로 각 차수의 질문 번호가 1부터 다시
// 시작한다 — 그대로 지목하면 2차의 1번과 1차의 1번이 구분되지 않는다. 그래서 **등장 순서**로
// 센다. gil intake --status 가 이 번호를 그대로 보여준다.
//
// 왜 인용인가. 목적을 에이전트가 다시 쓰면 그 순간 "사람이 세운 자"가 아니게 된다 — 요약도
// 정제도 창작이다. 도구는 진위를 못 재지만 **출처가 사람의 문장 그 자체인지**는 보증한다.
func intakeAnswerN(slug string, n int) string {
	secs := intakeSections(slug)
	if n < 1 || n > len(secs) {
		return ""
	}
	return secs[n-1].answer
}

type intakeSec struct{ q, answer string }

// intakeSections — 누적 문서를 (질문, 답) 목록으로. 트레일러·구분선은 걷어낸다.
func intakeSections(slug string) []intakeSec {
	body := stripTrailers(intakeAnswers(slug))
	var out []intakeSec
	var curQ string
	var buf []string
	flush := func() {
		if curQ == "" {
			return
		}
		var parts []string
		for _, ln := range buf {
			t := strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(ln), "- "))
			if t == "" || t == "_(답 없음)_" || t == "---" || strings.HasPrefix(t, "\u2500\u2500 ") {
				continue
			}
			// \uc778\uc6a9(`> `)\uc740 **\uc9c8\ubb38\uc758 \uc774\uc5b4\uc9c0\ub294 \uc904**\uc774\uc9c0 \uc0ac\ub78c\uc758 \ub2f5\uc774 \uc544\ub2c8\ub2e4(\uc774\uc288 #109). \uae34 \uc9c8\ubb38\uc758
			// \ud6c4\ubcf4 \ubaa9\ub85d\uc774 \ub2f5\uc73c\ub85c \uc11e\uc5ec \ub4e4\uc5b4\uac00 \uccb4\uc778 \ubaa9\uc801\uc5d0 \ud1b5\uc9f8\ub85c \ubc15\ud788\ub358 \uc790\ub9ac\ub2e4.
			if strings.HasPrefix(t, ">") {
				continue
			}
			parts = append(parts, t)
		}
		out = append(out, intakeSec{q: curQ, answer: strings.Join(parts, " \u00b7 ")})
		buf = nil
	}
	for _, ln := range strings.Split(body, "\n") {
		t := strings.TrimSpace(ln)
		if strings.HasPrefix(t, "## ") {
			flush()
			q := strings.TrimSpace(strings.TrimPrefix(t, "## "))
			if i := strings.Index(q, ". "); i > 0 && i <= 3 {
				q = strings.TrimSpace(q[i+2:])
			}
			if strings.HasPrefix(q, "\uc778\ud130\ubdf0 ") && strings.Contains(q, "\ucc28") {
				curQ = "" // 차수 구분 제목은 질문이 아니다
				continue
			}
			curQ = q
			continue
		}
		if curQ != "" {
			buf = append(buf, ln)
		}
	}
	flush()
	return out
}

// resolveAskJSON — --ask 인자를 질문 JSON 으로 푼다.
//
// 도움말은 `--ask <질문JSON|->` 이라고 적어 놓고 실제로는 **경로 또는 '-' 만** 받았다.
// JSON 을 그대로 주면 "file name too long" 으로 죽는다(이슈 #94 곁다리) — 도움말이 약속한 것을
// 도구가 안 지키면, 그 약속을 믿은 쪽이 죽는다. 이제 '[' 나 '{' 로 시작하면 그 자체를 JSON 으로
// 읽는다(파일 경로가 '[' 로 시작하는 일은 없다).
func resolveAskJSON(arg string) string {
	t := strings.TrimSpace(arg)
	if strings.HasPrefix(t, "[") || strings.HasPrefix(t, "{") {
		return t
	}
	return resolveBody("", arg)
}

// cmdIntake — gil intake <슬러그> --ask|--status|--wait|--resolve.
//
// 인터뷰 기계를 그대로 쓴다(뷰어·폴링·--wait 이 손 안 대고 동작하도록). 다른 점은 단 하나 —
// **체인이 없어도 된다**는 것이다.
func cmdIntake(args []string) {
	fs := newFlags("gil intake")
	ask := fs.str("ask", "")
	show := fs.boolFlag("show") // --status 에 답 전문까지(기본은 짧게, 이슈 #94)
	title := fs.str("title", "")
	resolve := fs.str("resolve", "")
	askRoot := fs.boolFlag("ask-root") // 마지막 차수 — 질문을 gil 이 만든다(후보=그래프의 사실)
	status := fs.boolFlag("status")
	wait := fs.boolFlag("wait")
	timeout := fs.str("timeout", "")
	then := fs.str("then", "")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil intake <슬러그> --ask <질문JSON|->   (체인을 열기 **전에** 사람에게 묻는다)\n" +
			"  또는: gil intake <슬러그> --status | --wait [--timeout <초>] | --resolve <파일>\n" +
			"\n" +
			"  왜 체인보다 먼저인가(이슈 #90): 체인은 --purpose 가 필수인데 인터뷰는 체인이\n" +
			"  있어야 열렸다. 그래서 에이전트가 목적을 창작하고 사람은 승인만 하게 됐다.\n" +
			"  그리고 **어디서 분기할지는 사람의 답을 보고 정해야 하는데**, 분기를 친 뒤에\n" +
			"  물으면 그 답이 갈 곳이 없다.\n" +
			"\n" +
			"  답이 확정되면 그 답으로 체인을 연다:\n" +
			"    gil chain <이름> --from-intake <슬러그> --purpose-from <질문번호>\n" +
			"  (목적은 사람의 문장을 **그대로** 들어 올린다 — 네가 다시 쓰지 않는다.)")
	}
	slug := pos[0]
	if !idRe.MatchString(slug) {
		die("거부: 슬러그 \"" + slug + "\" 은 소문자·숫자·하이픈만")
	}
	intakeMode = slug // 인터뷰 기계의 '체인 존재' 검사를 이 슬러그에 한해 면제한다
	if *resolve != "" {
		interviewResolve(slug, *resolve)
		return
	}
	if *status || *wait {
		interviewWatchOpt(slug, *wait, *timeout, *then, *show)
		// 어느 답을 인용할지 고르려면 **번호가 보여야 한다.** 차수마다 1부터 다시 시작하는
		// 원문 번호로는 지목할 수 없으니, 누적 순서로 다시 매겨 함께 낸다.
		if secs := intakeSections(slug); len(secs) > 0 {
			println2("")
			println2("── 인용 가능한 답 (--purpose-from / --criterion-from / --cycles-from 에 이 번호를) ──")
			for i, sc := range secs {
				println2("  " + itoa(i+1) + ") " + clip(sc.q, 60))
				println2("       → " + clip(sc.answer, 100))
			}
		}
		return
	}
	if *askRoot {
		if intakeState(slug) == "pending" {
			die("거부: \"" + slug + "\" 가 이미 사람 답을 기다린다 — 앞 차수의 답부터 받아라.")
		}
		intakeAskRoot(slug)
		return
	}
	if *ask == "" {
		die("사용: gil intake " + slug + " --ask <질문JSON|->  (또는 --ask-root / --resolve <파일>)")
	}
	if st := intakeState(slug); st == "pending" {
		die("거부: \"" + slug + "\" 개시 인터뷰가 이미 사람 답을 기다린다 — 새 질문지를 또 만들지 마라.\n" +
			"  기다려라: gil intake " + slug + " --wait")
	}
	interviewAsk(slug, *ask, *title, [][2]string{{"Gil-Intake", slug}})
	println2("")
	println2("  ▸ 이건 **체인보다 먼저** 묻는 자리다. 사람의 답이 오면 그 답으로 체인을 연다:")
	println2("      gil chain <이름> --from-intake " + slug + " --purpose-from <질문번호>")
	println2("  ▸ 그리고 **어디서 분기할지**를 그 답을 읽고 정하라 — 뿌리를 먼저 박으면 답이 갈 곳이 없다.")
}

// rootCandidates — **어디서 분기할지**의 후보를 그래프에서 계산한다(상현님).
//
// 왜 도구가 만드나. 이 질문만은 선택지가 정당하다 — 후보가 에이전트의 가설 공간이 아니라
// **그래프에 실재하는 사실**이기 때문이다. 닫힌 체인·열린 체인·대문은 gil 이 이미 안다.
// 사람은 사실 위에서 고른다. 열린 질문으로 열고 **닫힌 선택으로 닫는** 것이 심층 인터뷰의
// 모양이다(첫 질문 열린 질문 강제와 부딪히지 않는다 — 이건 마지막 차수다).
//
// 그리고 순서가 중요하다: 후보를 **문제를 정의한 뒤에** 보여야 사람이 판단할 수 있다.
// 분기를 먼저 쳐 버리면 이 답이 갈 곳이 없다.
func rootCandidates() []string {
	var out []string
	closed, open := []string{}, []string{}
	for c := range declaredChains("--branches") {
		if c == "" || isIntakeSlug(c) {
			continue // 개시 인터뷰 슬러그는 아직 체인이 아니다 — 후보가 될 수 없다
		}
		if chainClosed(c, "--branches") {
			closed = append(closed, c)
		} else {
			open = append(open, c)
		}
	}
	sort.Strings(closed)
	sort.Strings(open)
	for _, c := range closed {
		out = append(out, "["+c+"] 를 이어받는다 — 닫힌 체인의 끝에서 (그 교훈을 물려받는다)")
	}
	for _, c := range open {
		out = append(out, "["+c+"] 와 나란히 간다 — 병렬 트랙 (이어받는 것이 아니다)")
	}
	out = append(out, "대문에서 새로 시작한다 — 앞의 어느 것도 이어받지 않는 새 계보")
	return out
}

// intakeAskRoot — 마지막 차수: 뿌리 자리를 묻는다. 질문은 **gil 이 만든다.**
func intakeAskRoot(slug string) {
	if intakeState(slug) == "" {
		die("거부: 개시 인터뷰 \"" + slug + "\" 가 없다 — 먼저 무엇을 풀지부터 물어라:\n" +
			"    gil intake " + slug + " --ask '[{\"q\":\"무엇을 하려고 하십니까\",\"type\":\"text\"}]'")
	}
	cands := rootCandidates()
	var b strings.Builder
	b.WriteString(`[{"q":"이 일을 어디서 시작할까요? (아래는 지금 그래프에 실재하는 자리들입니다)","type":"radio","options":[`)
	for i, c := range cands {
		if i > 0 {
			b.WriteString(",")
		}
		b.WriteString(jsonQuote(c))
	}
	b.WriteString(`]},{"q":"그렇게 고른 이유가 있으면 적어 주세요 (없으면 비워 두세요)","type":"text"}]`)
	// 질문 검증은 '첫 질문 열린 질문' 규칙을 건다 — 이 차수는 도구가 만든 마지막 선택이라
	// 그 규칙의 예외다(앵커 방지는 앞 차수들이 이미 했다). interviewAsk 를 우회해 직접 심는다.
	intakePlant(slug, b.String(), "어디서 시작할까 — 후보는 그래프가 계산했다")
	println2("  ▸ 후보 " + itoa(len(cands)) + "개를 그래프에서 계산해 물었다 — 네가 지어낸 선택지가 아니다.")
	println2("  ▸ 사람이 고르면 그 자리로 체인을 연다: --from / --parallel-with / (없으면 대문).")
}

// intakeResolve — 개시 인터뷰의 답을 확정한다. 체인이 아직 없으므로 기준 문서는 대문 위에
// 슬러그로 심긴다. 그 답이 곧 다음에 열릴 체인의 목적이자 뿌리를 정하는 근거가 된다.
func intakeResolve(slug, refFile string) {
	body := resolveBody("", refFile)
	if strings.TrimSpace(body) == "" {
		die("거부: --resolve 파일이 비었다")
	}
	if intakeState(slug) == "" {
		die("거부: 개시 인터뷰 \"" + slug + "\" 가 없다 — 먼저 gil intake " + slug + " --ask <질문JSON>")
	}
	// **차수를 쌓는다.** 심층 인터뷰는 한 번으로 끝나지 않는다(상현님) — 무엇을 풀지,
	// 무엇이 관측되면 풀린 것인지, 어떤 작은 문제들로 나눌지를 차례로 묻는다. 새 답이 앞
	// 답을 덮으면 1차에 사람이 말한 것이 사라진다. 기준은 사람의 답이므로 지워지면 안 된다.
	// 앞 차수 본문을 그대로 이어 붙이면 그 커밋의 트레일러(Gil-…)까지 산문에 섞인다 —
	// 실측으로 답 안에 "Gil-Intake: deep · Gil-Chain: …" 이 딸려 들어왔다.
	prev := stripTrailers(intakeAnswers(slug))
	round := 1
	if strings.TrimSpace(prev) != "" {
		round = strings.Count(prev, "## 인터뷰 ") + 2
	}
	combined := body
	if strings.TrimSpace(prev) != "" {
		pb := prev
		if i := strings.Index(pb, "── 개시 인터뷰 답(사람이 세운 자) ──"); i >= 0 {
			pb = strings.TrimSpace(pb[i+len("── 개시 인터뷰 답(사람이 세운 자) ──"):])
		}
		combined = pb + "\n\n---\n\n## 인터뷰 " + itoa(round) + "차 (심층)\n\n" + body
	}
	subject := "gil intake " + slug + ": 개시 인터뷰로 방향 확정"
	if round > 1 {
		subject = "gil intake " + slug + ": 심층 인터뷰 " + itoa(round) + "차"
	}
	full := "체인을 열기 **전에** 사람에게 물어 받은 답이다(이슈 #90).\n" +
		"이 답이 다음에 열릴 체인의 목적·성패 기준·사이클 분할이 되고, **어디서 분기할지**의\n" +
		"근거가 된다. 전부 여기서 그대로 인용된다 — 에이전트가 다시 쓰지 않는다.\n" +
		"심층 인터뷰는 차수를 더할 수 있고, 앞 차수의 답은 지워지지 않고 아래에 쌓인다.\n\n" +
		"── 개시 인터뷰 답(사람이 세운 자) ──\n\n" + combined
	tr := [][2]string{
		{"Gil-Intake", slug}, {"Gil-Chain", slug}, {"Gil-Kind", "intake-reference"},
		{"Gil-Reference", "true"}, {"Gil-Interview", "done"},
	}
	// 확정된 답도 앞머리다 — 질문을 심은 자리와 **같은 층**에 앉아야 한 줄로 읽힌다.
	// (질문은 dev 에, 답은 그때 서 있던 브랜치에 앉으면 앞머리가 두 곳으로 찢어진다.)
	commitOn(frontMatterBranch(), "", subject, full, tr, true)
	println2("intake: " + slug + " — 사람의 답이 확정됐다(" + itoa(round) + "차).")
	println2("  ▸ 더 물을 것이 남았으면 차수를 더해라 — 앞 답은 지워지지 않고 쌓인다:")
	println2("      gil intake " + slug + " --ask <질문JSON>")
	println2("  ▸ **어디서 분기할지**는 마지막에 묻는다(후보는 그래프가 계산한다):")
	println2("      gil intake " + slug + " --ask-root")
	println2("  ▸ 준비되면 그 답으로 체인을 연다(전부 인용된다):")
	println2("      gil chain <이름> --from-intake " + slug + " --purpose-from <n> --criterion-from <m>")
	println2("  ▸ 답 전문: gil intake " + slug + " --status")
}

// referentialAnswer — 답이 "2번", "②", "위의 두 번째" 처럼 **다른 곳을 가리키기만 하는가**
// (이슈 #109). 짧고 지시어뿐인 답은 인용해도 목적이 서지 않는다 — 판정이 아니라 고지에 쓴다.
func referentialAnswer(s string) bool {
	t := strings.TrimSpace(s)
	if len([]rune(t)) > 24 {
		return false // 길면 스스로 말한다 — 참조가 섞여 있어도 목적은 선다
	}
	for _, m := range []string{"번", "번째", "①", "②", "③", "④", "⑤", "위의", "아래", "그거", "그것", "저것"} {
		if strings.Contains(t, m) {
			return true
		}
	}
	return false
}
