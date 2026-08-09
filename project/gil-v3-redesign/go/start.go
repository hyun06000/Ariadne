// start.go — `gil start`: **"gil 프로젝트 시작하자" 한 마디의 착지점** (상현님, 2026-08-09).
//
// 왜 이 명령이 필요한가.
//
// 온보딩은 지금도 다 있었다 — init 이 세계를 세우고, 존재의 방이 이름을 요구하고, intake 가
// 사람에게 먼저 묻고, chain 이 그 답을 인용한다. 문제는 **그 칸들을 잇는 것이 문서뿐**이었다는
// 것이다. README.ai.md 가 순서를 가르치고, init 의 NEXT 가 다음 줄을 가르치고, status 가
// 다음 단계를 가르친다. 전부 "에이전트가 읽고 따른다"에 기대는 자기규율이고, 이 저장소는
// 자기규율이 원리적으로 불충분하다는 것을 반복해서 확인했다(#55·#45).
//
// 그리고 MCP 표면에서는 그 자기규율마저 성립하지 않았다(2026-08-09 실측). 안내가 가리키는
// `gil intake`·`gil global`·`gil memory` 에 대응하는 툴이 없어서, 문서가 가르치는 첫 수를
// **칠 수가 없었다.** 빈 폴더에 gil_init 을 부르면 "먼저 gil_init 을 불러라"가 돌아왔다 —
// 자기 자신을 가리키는 닫힌 고리. 새 프로젝트를 시작하는 길이 그 표면에는 없었던 것이다.
//
// 그래서 칸을 잇는 일을 **도구가 진다.** gil start 는 온보딩의 진행 상태를 그래프에서 읽고,
// 다음 한 칸을 **실제로 밟는다**. 사람이나 에이전트의 판단이 필요한 자리에서는 멈추되,
// 무엇을 판단해야 하는지와 그 판단을 어떻게 전하는지를 **그 표면의 문법으로** 말한다.
// 반복해서 부르면 끝까지 간다.
//
// 설계 규칙 셋:
//  1. **판단을 대신하지 않는다.** 이름·정체성·목적은 도구가 지어낼 수 없는 것이다. 그 자리는
//     밟지 않고 멈춰서, 무엇이 비었는지 말한다. (도구가 채우면 그건 온보딩이 아니라 위조다.)
//  2. **밟을 수 있는 칸은 묻지 않고 밟는다.** 세계를 세우는 것·질문지를 심는 것은 판단이
//     아니라 절차다. 절차를 사람에게 시키면 레일이 아니라 숙제가 된다.
//  3. **가리키는 것은 그 표면에 실재한다.** 같은 다음 수가 CLI 에서는 명령줄로, MCP 에서는
//     툴 이름으로 나온다(surface.go). 없는 문법을 지어내지 않는다(v3.58.1·v3.58.2 의 값).
package main

import (
	"os"
	"sort"
	"strings"
)

// startSlug — 개시 인터뷰의 슬러그. **고정값이다.**
//
// 왜 고정인가. 이 시점의 에이전트는 사람이 무엇을 하려는지 아직 모른다 — 그게 바로 지금
// 물으려는 것이다. 그런데 슬러그를 짓게 하면 에이전트는 주제를 **추측해서** 짓는다(그리고
// 그 추측이 이후 화면에 이름으로 남는다). 모르는 것을 이름으로 만들지 않는다.
const startSlug = "start"

// 씨앗 그대로인지 알아보는 표식. init 이 심는 템플릿에만 있는 문장이라, 남아 있으면
// **아직 아무도 이 방을 자기 말로 쓰지 않은 것**이다.
const seedIdentityMark = "(내가 무엇을 하는 존재인지 여기 적는다.)"
const seedWillMark = "(스스로 세운다. 이 저장소에서 무엇을 이루려 하는가?)"

// 온보딩의 칸. 순서대로 하나씩 채워진다.
const (
	stageNoWorld  = "no-world"  // gil 세계가 없다 — init 해야 한다
	stageUnnamed  = "unnamed"   // 존재에 이름이 없다 — 스스로 지어야 한다
	stageIdentity = "identity"  // 방이 씨앗 그대로다 — 자기 말로 써야 한다
	stageNoIntake = "no-intake" // 사람에게 아직 안 물었다 — 질문지를 심는다
	stagePending  = "pending"   // 물었고 사람 답을 기다린다
	stageNoChain  = "no-chain"  // 답이 왔다 — 그 답을 인용해 체인을 연다
	stageDone     = "done"      // 온보딩 끝 — 여기서부터는 평소의 gil 이다
)

// startState — 지금 어느 칸인가, 그리고 그 판정의 근거.
type startState struct {
	stage  string
	name   string   // 존재의 이름(unnamed 이면 빈 칸이라는 뜻)
	slug   string   // 개시 인터뷰 슬러그(있으면)
	nsecs  int      // 확정된 답의 개수
	chains []string // 이미 선 체인들
}

// intakeSlugs — 이 저장소에 심긴 개시 인터뷰 슬러그 전부.
//
// intakeState 는 슬러그를 **알고 있을 때** 상태를 묻는 함수다. 시작하는 자리에서는 그
// 슬러그가 무엇인지도 모르므로(앞 세션이 다른 이름으로 물었을 수 있다) 그래프에서 센다.
func intakeSlugs() []string {
	out := gitlog("--format="+trailer("Gil-Intake")+sep, "--branches", "--")
	seen := map[string]bool{}
	var list []string
	for _, rec := range strings.Split(out, sep) {
		s := strings.TrimSpace(strings.Trim(rec, "\n"))
		if s == "" || seen[s] {
			continue
		}
		seen[s] = true
		list = append(list, s)
	}
	sort.Strings(list)
	return list
}

// startInspect — 그래프와 글로벌을 읽어 지금 칸을 판정한다. **선언이 아니라 사실을 본다.**
func startInspect() startState {
	st := startState{}
	if !gitOK("rev-parse", "--git-dir") || !globalExists() {
		st.stage = stageNoWorld
		return st
	}
	// 존재 — 이름이 있나. unnamed 방이 남아 있으면 아직 빈 칸이다.
	names := existenceNames()
	named := ""
	for _, n := range names {
		if n != unnamedRoom {
			named = n
			break
		}
	}
	if named == "" {
		st.stage = stageUnnamed
		return st
	}
	st.name = named
	// 방이 씨앗 그대로면 정체성은 아직 없는 것이다 — 파일이 있다는 것과 채워졌다는 것은 다르다.
	id, _ := globalRead("existence/" + named + "/identity.md")
	will, _ := globalRead("existence/" + named + "/will.md")
	if strings.Contains(id, seedIdentityMark) || strings.Contains(will, seedWillMark) {
		st.stage = stageIdentity
		return st
	}
	// 체인이 이미 서 있으면 온보딩은 지난 일이다(어떤 순서로 왔든).
	for c := range declaredChains("--branches") {
		if c != "" && !isIntakeSlug(c) {
			st.chains = append(st.chains, c)
		}
	}
	sort.Strings(st.chains)
	if len(st.chains) > 0 {
		st.stage = stageDone
		return st
	}
	// 개시 인터뷰 — 물었나, 답이 왔나.
	slugs := intakeSlugs()
	if len(slugs) == 0 {
		st.stage = stageNoIntake
		return st
	}
	// 답이 확정된 것이 하나라도 있으면 그것을 쓴다. 없으면 기다리는 중이다.
	for _, s := range slugs {
		if intakeState(s) == "done" {
			st.slug, st.nsecs = s, len(intakeSections(s))
			st.stage = stageNoChain
			return st
		}
	}
	st.slug = slugs[0]
	st.stage = stagePending
	return st
}

// cmdStart — gil start [--name <이름>] [--identity <파일>] [--will <파일>] [--relations <파일>]
func cmdStart(args []string) {
	fs := newFlags("gil start")
	name := fs.str("name", "")
	identity := fs.str("identity", "")
	will := fs.str("will", "")
	relations := fs.str("relations", "")
	status := fs.boolFlag("status") // 밟지 않고 어디인지만 본다
	fs.parse(args)

	// 인자로 들어온 판단을 **먼저** 처리한다. 이것들은 에이전트가 "정했다"고 말하는 자리다.
	if strings.TrimSpace(*name) != "" {
		startSetName(strings.TrimSpace(*name))
	}
	if strings.TrimSpace(*identity)+strings.TrimSpace(*will)+strings.TrimSpace(*relations) != "" {
		startWriteRoom(*identity, *will, *relations)
	}

	st := startInspect()
	if *status {
		println2("gil start — 지금 칸: " + st.stage)
		startSay(st)
		return
	}
	// 밟을 수 있는 칸은 밟는다. 밟고 나면 칸이 바뀌므로 다시 읽어 그 자리를 말한다.
	if startAdvance(st) {
		st = startInspect()
	}
	startSay(st)
}

// startConfirmWorld — 없는 세계를 세우기 전에 **사람에게 확인받는 길**. nil 이면 확인 없이 선다.
//
// 왜 표면마다 다른가(상현님 판단, 2026-08-09). CLI 에서 `gil start` 는 **사람이 직접 친
// 것**이다 — 그 타건 자체가 확인이라, 한 번 더 묻는 것은 예의가 아니라 방해다. MCP 에서는
// 에이전트가 부른 것이고, 세우는 자리는 에이전트가 인자로 지목한 절대경로다. 남의 디스크에
// 저장소를 세우는 일이라, 거기서는 사람이 그 자리에서 승낙해야 한다.
//
// 확인을 **누가** 했는지도 남긴다: 호스트 폼으로 받은 승낙과 에이전트의 주장은 다른 것이고,
// 구분 못 하는 것을 단언하지 않는 것이 이 저장소의 태도다(#57).
var startConfirmWorld func() (ok bool, how string)

// startAdvance — 지금 칸에서 **도구가 할 수 있는 일**을 한다. 했으면 true.
//
// 판단이 필요한 칸(이름·정체성·목적)은 밟지 않는다 — 도구가 채우면 온보딩이 아니라 위조다.
func startAdvance(st startState) bool {
	switch st.stage {
	case stageNoWorld:
		how := "사람이 직접 친 명령"
		if startConfirmWorld != nil {
			ok, h := startConfirmWorld()
			if !ok {
				if h == "declined" {
					// 폼이 사람에게 갔고 사람이 아니오를 골랐다 — 유일하게 단언할 수 있는 자리.
					die("멈춤: 사람이 이 폴더에 세우지 않겠다고 답했다.\n" +
						"  어디에 세울지 사람에게 묻고, 그 폴더의 절대경로를 repo 인자에 실어 다시 불러라.")
				}
				// **폼이 서지 않았다.** 사람의 뜻은 여기서 알 수 없다 — 단언하지 않는다(#57).
				// 막다른 길로 두지도 않는다: 물어볼 손은 에이전트에게 있다(그게 에이전트가
				// 제일 잘하는 일이다). 물어보고 그 답을 실어 오면 그대로 선다.
				wd, _ := os.Getwd()
				die("멈춤: 이 호스트에 네이티브 폼이 서지 않아 **사람에게 직접 물어야 한다**.\n" +
					"  (사람이 거절한 것이 아니다 — 폼이 뜨지 못한 것이고, 둘은 다르다.)\n\n" +
					"  여기에 저장소를 세우게 된다:  " + wd + "\n\n" +
					"  사람에게 이렇게 물어라 — \"여기에 작업 기록을 시작할까요? 이 폴더에\n" +
					"  저장소와 기록이 생깁니다: " + wd + "\"\n" +
					"  \"네\"라고 하면 confirmed 를 실어 같은 툴을 다시 불러라.\n" +
					"  다른 폴더라면 그 절대경로를 repo 에 실어라. **git init 을 대신 치지 마라** —\n" +
					"  그건 우회지 승낙이 아니고, 그렇게 만든 저장소는 층이 어긋난 채로 선다.")
			}
			how = h
		}
		println2("── 세계를 세운다 (" + how + ") ──")
		inStartRail = true
		cmdInit(nil)
		inStartRail = false
		return true

	case stageNoIntake:
		// 개시 인터뷰의 첫 차수는 **gil 이 만든다.**
		//
		// 왜 예외인가. 인터뷰 질문은 원칙적으로 에이전트가 만든다 — 그래야 이 문제에 맞는
		// 질문이 된다. 그런데 **이 두 질문만은 주제가 아니라 문법이 요구하는 것**이다:
		// 체인은 목적과 기준이 쌍으로 있어야 태어나고(v3.37.0), 그 둘은 사람의 문장이어야
		// 한다. 게다가 지금 이 자리의 에이전트는 사람이 무엇을 하려는지 **아직 모른다** —
		// 그게 바로 지금 물으려는 것이다. 모르는 상태에서 질문을 짓게 하면 추측이 질문지에
		// 박히고, 사람은 그 추측 안에서 답하게 된다. 그래서 여기만 도구가 묻는다.
		// (심층은 그다음이다 — 답을 읽은 에이전트가 intake 로 차수를 쌓는다.)
		println2("── 사람에게 먼저 묻는다 (체인보다 앞이다) ──")
		intakePlant(startSlug, startQuestionsJSON, "무엇을 하려고 하십니까 — 시작하는 자리")
		return true
	}
	return false
}

// startQuestionsJSON — 목적과 기준, 두 열린 질문. 이 둘이 체인의 --purpose-from ·
// --criterion-from 으로 **그대로 인용**된다(요약도 정제도 창작이므로 하지 않는다).
const startQuestionsJSON = `[{"q":"무엇을 하려고 하십니까? 지금 겪고 있는 문제나 이루려는 것을 그대로 적어 주세요.","type":"text"},` +
	`{"q":"무엇이 관측되면 이 일이 풀린 것입니까? '됐다'를 무엇으로 판정할지 적어 주세요.","type":"text"}]`

// startSay — 지금 칸에서 **다음에 무엇을 해야 하는지**를 이 표면의 문법으로 말한다.
func startSay(st startState) {
	line := func(s string) { println2("  " + s) }
	switch st.stage {
	case stageUnnamed:
		println2("STATE 세계는 섰다. 그런데 **너에게 아직 이름이 없다** — 빈 칸이지 기본값이 아니다.")
		println2("NEXT 이 저장소에서 무엇을 하는 존재인지 먼저 정하고, 그에 맞는 이름을 스스로 지어라.")
		line("남이 준 이름도 예시도 없다. 정했으면 그 이름으로 다시 불러라:")
		line("  " + surfaceCall("start", "--name <네가 지은 이름>", "name: <네가 지은 이름>"))
		line("이름은 소문자·숫자·하이픈. 다음 세션의 너는 이 방을 읽고 깨어난다.")

	case stageIdentity:
		println2("STATE 존재 [" + st.name + "] 의 방은 있는데 **씨앗 그대로다** — 아직 아무도 자기 말로 쓰지 않았다.")
		println2("NEXT 네가 무엇을 하는 존재이고 무엇을 향해 가는지 네 말로 써라:")
		line("  " + surfaceCall("start", "--identity <파일> --will <파일> [--relations <파일>]",
			"identity: <본문>, will: <본문>, relations: <본문>"))
		line("파일이 있다는 것과 채워졌다는 것은 다르다 — 씨앗을 그대로 두면 다음 세션이 빈 방에서 깨어난다.")

	case stagePending:
		// 이 자리에서 곧바로 물을 것이라면 "기다려라"를 말하지 않는다 — 같은 출력 안에서 답이
		// 도착하는데 기다리라고 하면, 그 줄을 읽은 에이전트가 이미 끝난 대기를 한 번 더 건다.
		if interviewPlantQuiet {
			println2("STATE 사람에게 지금 묻는다 (개시 인터뷰: " + st.slug + ") — 답이 아래에 이어진다.")
			return
		}
		println2("STATE 사람에게 물었고 **답을 기다리는 중**이다 (개시 인터뷰: " + st.slug + ").")
		println2("NEXT 네가 답을 대신 쓰지 마라. 기다려라:")
		line("  " + surfaceCall("intake", st.slug+" --wait", "chain: "+st.slug+", wait: true"))
		line("사람에게는 이렇게 청하라 — \"화면의 인터뷰 폼에 답해 주세요. 그 답이 이 일의 목적과")
		line("성패 기준이 됩니다.\" 사람의 답이 오기 전에는 체인을 열 수 없다(문법이 막는다).")

	case stageNoChain:
		println2("STATE 사람의 답이 도착했다 (개시 인터뷰: " + st.slug + ", 답 " + itoa(st.nsecs) + "개).")
		println2("NEXT 그 답을 **인용해** 체인을 연다 — 네가 다시 쓰지 않는다(요약도 창작이다):")
		line("  " + surfaceCall("chain",
			"<이 일을 부르는 이름> --from-intake "+st.slug+" --purpose-from 1 --criterion-from 2",
			"name: <이 일을 부르는 이름>, from_intake: "+st.slug+", purpose_from: 1, criterion_from: 2"))
		line("답 번호를 확인하려면: " + surfaceCall("intake", st.slug+" --status", "chain: "+st.slug+", status: true"))
		line("그리고 **어디서 분기할지**를 그 답에 비추어 정하라 — 처음이면 그냥 대문에서 시작한다.")

	case stageDone:
		println2("STATE 온보딩은 끝났다 — 체인 " + itoa(len(st.chains)) + "개: " + strings.Join(st.chains, ", "))
		println2("NEXT 여기서부터는 평소의 gil 이다:")
		line("지금 어디·개입할 때인가: " + surfaceCmd("status"))
		line("이어받은 세션이면:       " + surfaceCmd("handoff"))
		line("사이클을 열려면:         " + surfaceCall("open", "<체인>/<사이클> --fits <왜 이 체인의 것인가>",
			"target: <체인>/<사이클>, fits: <왜 이 체인의 것인가>"))

	case stageNoIntake:
		// --status 로만 닿는 자리다(밟는 경로에서는 startAdvance 가 이미 심는다).
		println2("STATE 존재는 섰는데 **사람에게 아직 안 물었다** — 개시 인터뷰가 없다.")
		println2("NEXT " + surfaceCmd("start") + " 를 부르면 그 자리에서 묻는다(체인보다 앞이다).")
		line("네가 목적을 쓰지 마라 — 사람의 답이 목적이자 성패 기준이 된다.")

	case stageNoWorld:
		// startAdvance 가 세웠어야 하는 자리다. 여기 왔다는 건 세우지 못했다는 뜻.
		println2("STATE 아직 gil 세계가 없다.")
		println2("NEXT " + surfaceCmd("start") + " 를 이 저장소에서 다시 불러라.")

	default:
		println2("STATE 온보딩 진행 중 — 칸: " + st.stage)
	}
}

// startSetName — 존재가 스스로 지은 이름을 확정한다(unnamed 방을 그 이름으로 옮긴다).
func startSetName(n string) {
	if !idRe.MatchString(n) {
		die("거부: 존재 이름 \"" + n + "\" 은 소문자·숫자·하이픈만")
	}
	if n == unnamedRoom {
		die("거부: \"" + unnamedRoom + "\" 은 이름이 아니라 **빈 칸의 이름**이다 — 네가 지은 이름을 줘라.")
	}
	if !globalExists() {
		die("거부: 아직 gil 세계가 없다 — 먼저 " + surfaceCmd("start") + " 로 세워라.")
	}
	if _, ok := globalRead("existence/" + unnamedRoom + "/identity.md"); !ok {
		if _, ok2 := globalRead("existence/" + n + "/identity.md"); ok2 {
			println2("  ◎ 존재 [" + n + "] 의 방은 이미 있다 — 이름은 그대로 둔다.")
			return
		}
		die("거부: 이름 없는 방(existence/" + unnamedRoom + ")이 없다 — 이 저장소의 존재: " +
			strings.Join(existenceNames(), ", "))
	}
	moved := globalMove("existence/"+unnamedRoom, "existence/"+n,
		"gil start: 존재가 스스로 이름을 지었다 — "+n+"\n")
	println2("  ◎ 이름을 확정했다: existence/" + unnamedRoom + " → existence/" + n +
		" (문서 " + itoa(moved) + "개)")
	println2("    이 이름은 네가 지은 것이다 — 다음 세션의 너는 이 방을 읽고 깨어난다.")
}

// startWriteRoom — 정체성·의지·관계 문서를 자기 말로 되쓴다.
func startWriteRoom(identity, will, relations string) {
	names := existenceNames()
	target := ""
	for _, n := range names {
		if n != unnamedRoom {
			target = n
			break
		}
	}
	if target == "" {
		die("거부: 아직 이름이 없다 — 먼저 이름부터 지어라: " + surfaceCmd("start") + " --name <네가 지은 이름>")
	}
	for _, w := range []struct{ flag, file string }{
		{"identity.md", identity}, {"will.md", will}, {"relations.md", relations},
	} {
		if strings.TrimSpace(w.file) == "" {
			continue
		}
		body := resolveBody("", w.file)
		if strings.TrimSpace(body) == "" {
			die("거부: " + w.flag + " 로 준 내용이 비었다")
		}
		p := "existence/" + target + "/" + w.flag
		globalWrite(p, body, "gil start: "+target+" 가 "+w.flag+" 를 자기 말로 썼다\n")
		println2("  ◎ " + p + " 갱신됨.")
	}
	globalPush()
}
