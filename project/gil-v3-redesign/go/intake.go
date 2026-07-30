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
	"strconv"
	"strings"
)

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

// intakeAnswerN — 기준 문서에서 **n번 질문의 답을 그대로** 떼어 온다.
//
// 왜 인용인가. 목적을 에이전트가 다시 쓰면 그 순간 "사람이 세운 자"가 아니게 된다 — 요약도
// 정제도 창작이다. 도구는 진위를 못 재지만 **출처가 사람의 문장 그 자체인지**는 보증할 수
// 있다. 그래서 --purpose 를 받지 않고 --purpose-from <n> 으로 사람의 답을 들어 올린다.
func intakeAnswerN(slug string, n int) string {
	body := intakeAnswers(slug)
	if body == "" {
		return ""
	}
	// 기준 문서는 "## <n>. <질문>" 절로 조립된다(뷰어 assembleReference).
	head := "## " + itoa(n) + ". "
	i := strings.Index(body, head)
	if i < 0 {
		return ""
	}
	rest := body[i+len(head):]
	// 질문 줄 다음부터 다음 "## " 앞까지가 답이다.
	if j := strings.Index(rest, "\n"); j >= 0 {
		rest = rest[j+1:]
	}
	if j := strings.Index(rest, "\n## "); j >= 0 {
		rest = rest[:j]
	}
	// 리스트 답(- a / - b)은 한 줄로 잇는다 — 목적은 한 문장 자리다.
	var parts []string
	for _, ln := range strings.Split(rest, "\n") {
		t := strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(ln), "- "))
		if t == "" || t == "_(답 없음)_" {
			continue
		}
		parts = append(parts, t)
	}
	return strings.Join(parts, " · ")
}

// cmdIntake — gil intake <슬러그> --ask|--status|--wait|--resolve.
//
// 인터뷰 기계를 그대로 쓴다(뷰어·폴링·--wait 이 손 안 대고 동작하도록). 다른 점은 단 하나 —
// **체인이 없어도 된다**는 것이다.
func cmdIntake(args []string) {
	fs := newFlags("gil intake")
	ask := fs.str("ask", "")
	title := fs.str("title", "")
	resolve := fs.str("resolve", "")
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
		interviewWatch(slug, *wait, *timeout, *then)
		return
	}
	if *ask == "" {
		die("사용: gil intake " + slug + " --ask <질문JSON|->  (또는 --resolve <파일>)")
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
	subject := "gil intake " + slug + ": 개시 인터뷰로 방향 확정"
	full := "체인을 열기 **전에** 사람에게 물어 받은 답이다(이슈 #90).\n" +
		"이 답이 다음에 열릴 체인의 목적이 되고, **어디서 분기할지**의 근거가 된다.\n" +
		"목적은 여기서 그대로 인용된다 — 에이전트가 다시 쓰지 않는다.\n\n" +
		"── 개시 인터뷰 답(사람이 세운 자) ──\n\n" + body
	tr := [][2]string{
		{"Gil-Intake", slug}, {"Gil-Chain", slug}, {"Gil-Kind", "intake-reference"},
		{"Gil-Reference", "true"}, {"Gil-Interview", "done"},
	}
	commit(subject, full, tr, true)
	println2("intake: " + slug + " — 사람의 답이 확정됐다.")
	println2("  ▸ 이제 그 답으로 체인을 연다(목적은 인용된다):")
	println2("      gil chain <이름> --from-intake " + slug + " --purpose-from <질문번호>")
	println2("  ▸ 답 전문: gil intake " + slug + " --status")
}
