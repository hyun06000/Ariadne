// gil v3 — 커밋 그래프 위의 체인·사이클·스텝. Go 참조 구현 (git 래퍼, 의존성 0).
//
// 참조 구현(gil.py, Python)을 Go로 옮긴 것. 진실원은 언제나 git 커밋 그래프이고, 이
// 바이너리는 그걸 파싱·기록하는 얇은 층이다. git만 있으면 다른 의존성 없이 돈다(상현님):
// Python 런타임도 필요 없는 단일 네이티브 바이너리. web(뷰어)은 gil로 짓는 실작업이라
// 여기 없다 — 배포 후 orphan 브랜치에서 gil 사이클로 지어 chain-merge로 이식한다.
package main

import (
	"os"
	"os/exec"
	"runtime"
	"strings"
)

// requireGit — git 실행파일이 PATH 에 없으면 사람 언어로 안내하고 멈춘다. gil 은 위계 전체를
// 진짜 git 브랜치·커밋으로 남기므로 git 없이는 아무 명령도 못 돈다. 이 출력은 LLM 에게 들어가는
// 프롬프트다 — Go 런타임의 날것 에러("exec: git ... not found") 대신, AI 가 곧장 사람에게
// "git 을 설치하라"고 안내할 수 있게 원인·해결을 콕 집어 준다.
func requireGit() {
	if _, err := exec.LookPath("git"); err == nil {
		return
	}
	// 실행 중인 OS 에 맞는 설치법을 앞세운다 — AI 가 곧장 그 명령으로 자동 설치를 시도할 수 있게.
	// (실사용: Windows 사용자의 에이전트가 winget 을 시도했으나 힌트가 없어 헤맴.)
	var primary string
	switch runtime.GOOS {
	case "windows":
		// --silent 로 설치관리자 UI·여러 콘솔 창이 번쩍이는 걸 줄인다(실사용: 비개발자가 계단식
		// cmd 창에 공포). winget 없으면 설치관리자 링크 — 그건 사람이 클릭으로 조용히 설치.
		primary = "  Windows: winget install --id Git.Git -e --silent   (winget 없으면 https://git-scm.com/download/win 에서 설치관리자로 조용히 설치)\n"
	case "darwin":
		primary = "  macOS: brew install git   (또는 xcode-select --install)\n"
	default:
		primary = "  Debian/Ubuntu: sudo apt-get install -y git   |   Fedora: sudo dnf install -y git   |   Alpine: apk add git\n"
	}
	die("거부: git 실행파일을 찾을 수 없다 (PATH 에 git 없음).\n" +
		"  gil 은 사고 이력을 진짜 git 브랜치·커밋으로 남기므로 git 이 반드시 필요하다.\n" +
		"  git 을 설치하라 (아래는 이 OS 용). 설치 뒤 같은 명령을 다시 실행하면 된다:\n" +
		primary +
		"  전체 안내: https://git-scm.com/downloads")
}

func main() {
	defer traceSummary() // GIL_TRACE 요약(이슈 #88) — 정상 종료 경로
	// 인자 없이 호출되면 사용법을 낸다 — 출력은 LLM 에게 들어가는 프롬프트이므로,
	// "무엇을 할 수 있는지"를 알려주는 게 침묵보다 낫다(상현님).
	if len(os.Args) <= 1 {
		printUsage()
		return
	}
	cmd := os.Args[1]
	rest := os.Args[2:]
	// 어느 명령이든 --help/-h 를 뒤에 붙이면 그 명령의 사용법을 낸다(gil step --help).
	// 서브명령이 --help 를 알 수 없는 플래그로 거부하던 것을 여기서 가로챈다.
	if cmd != "help" && cmd != "-h" && cmd != "--help" {
		for _, a := range rest {
			if a == "--help" || a == "-h" {
				cmdHelp([]string{cmd})
				return
			}
		}
	}
	// help 류는 git 없이도 답한다(무엇을 할 수 있는지 알려주는 순수 텍스트). 그 외 모든
	// 명령은 git 을 실제로 부르므로, 여기서 git 존재를 먼저 확인해 친절히 안내한다.
	// version 은 git 을 안 부른다(순수 자기 정보 + 네트워크) — git 없이도 동작해야
	// "일단 gil 이 뭔지"를 답할 수 있다.
	if cmd != "help" && cmd != "-h" && cmd != "--help" && cmd != "version" {
		requireGit()
	}
	// 도착한 인터뷰 답을 **무슨 명령을 부르든** 맨 앞에서 고지한다(이슈 #77). 에이전트가
	// --status 를 떠올리지 못해도 걸리는 자리는 여기뿐이다 — 통지는 호스트 기능이라 gil 이
	// 보장할 수 없지만, 다음 접촉 때의 고지는 보장할 수 있다.
	if cmd != "help" && cmd != "-h" && cmd != "--help" && cmd != "version" {
		noticeArrivedInterviews()
	}
	// 관전 서버는 세션의 첫 명령이 무엇이든 떠야 한다(상현님 실사용: gil 이 이미 깔린 머신에서
	// 새 세션을 열면 init 도 handoff 도 안 부르는 경로가 흔하고, 그러면 그 세션 내내 뷰어가
	// 없다). init·handoff 는 자기 자리에서 브라우저까지 여니 여기서 중복하지 않는다.
	switch cmd {
	case "help", "-h", "--help", "version", "init", "handoff", "viewer", "mcp":
		// 자기 자리에서 이미 묻거나(init·handoff), 물을 자리가 아니다(help·version·서버).
	case "docs":
		// 온보딩을 저장소에 심는 자리다 — 낡은 gil 이 심으면 그 저장소는 처음부터 낡은
		// 진입점을 배운다. 뷰어는 띄우지 않되 버전은 묻는다.
		versionAskPrint()
	default:
		ensureViewer()
		// 부팅(세션의 첫 접촉)에서 버전업을 **묻는다**. 저장소마다 6시간에 한 번이라
		// 실질적으로 세션당 한 번이고, 낡은 도구로 한 세션을 통째로 보내는 걸 막는다.
		versionAskPrint()
	}
	switch cmd {
	case "help", "-h", "--help":
		cmdHelp(rest)
	case "version":
		cmdVersion(rest)
	case "init":
		cmdInit(rest)
	case "chain":
		cmdChain(rest)
	case "merge":
		cmdMerge(rest)
	case "chain-merge":
		// 디프리케이트(2026-07-31) — 합류는 gil merge 하나로 말한다. 지우지 않는다:
		// 옛 문서·스크립트가 이 이름을 부르고, 침묵하는 제거는 사용자에게 원인 미상의
		// 고장으로 도착한다. 대신 어디로 갔는지 말하고 그대로 실행한다.
		stderr("⚠ gil chain-merge 는 디프리케이트됐다 — 합류는 이제 gil merge 하나로 말한다.")
		stderr("   여러 끝단을 새 체인으로 모으는 이 모양은 계속 돈다. 다른 합류는:")
		stderr("     gil merge <합칠 것>... --into <받는 곳> --reason <왜>")
		cmdChainMerge(rest)
	case "open":
		cmdOpen(rest)
	case "step":
		cmdStep(rest)
	case "close":
		cmdClose(rest)
	case "adopt":
		cmdAdopt(rest)
	case "chain-close":
		cmdChainClose(rest)
	case "deploy":
		cmdDeploy(rest)
	case "intake":
		cmdIntake(rest)
	case "interview":
		cmdInterview(rest)
	case "approve":
		cmdApprove(rest)
	case "reject":
		cmdReject(rest)
	case "docs":
		cmdDocs(rest)
	case "goto":
		cmdGoto(rest)
	case "context":
		cmdContext(rest)
	case "drift":
		cmdDrift(rest)
	case "reconcile":
		cmdReconcile(rest)
	case "chain-retire":
		cmdChainRetire(rest)
	case "chain-unretire":
		cmdChainUnretire(rest)
	case "prune":
		cmdPrune(rest)
	case "prune-approve":
		cmdPruneApprove(rest)
	case "log":
		cmdLog(rest)
	case "fsck":
		cmdFsck(rest)
	case "global":
		cmdGlobal(rest)
	case "memory":
		cmdMemory(rest)
	case "handoff":
		cmdHandoff(rest)
	case "migrate":
		cmdMigrate(rest)
	case "mcp":
		cmdMCP(rest)
	case "viewer":
		cmdViewer(rest)
	default:
		die("gil: 알 수 없는 명령 \"" + cmd + "\" — [init chain chain-close merge chain-merge open step close deploy interview approve reject goto context drift reconcile chain-retire chain-unretire prune prune-approve docs log fsck global memory handoff migrate viewer mcp version]")
	}
}

// printUsage — 명령 표면. LLM 이 다음에 무엇을 할 수 있는지 읽는 프롬프트.
func printUsage() {
	println2(`gil — GIt for Language model. 사고 역사를 git 커밋 그래프 위에 남긴다.

세팅·복원:
  gil init [--name <이름>]        무에서 세팅 — refs/gil/global + 존재의 방 + 대문
  gil handoff                     세션 복원 — 열린 체인·사이클·다음 동작·pending
  gil global sync                 (새 머신 첫 1회) 원격 글로벌을 로컬로 + refspec 등록

존재·기억 (refs/gil/global, 브랜치 아님):
  gil global list                 글로벌에 담긴 파일 목록
  gil global read <name>          파일 읽기 (예: existence/<이름>/identity.md)
  gil global write <name> <file>  파일 갱신 (트리 보존, append-only)
  gil memory read [<이름>]        존재의 기억 읽기 (이름 생략 = 이 저장소의 유일한 존재)
  gil memory append <이름> <file> 기억에 매듭 이어붙임 (안전, 자동 push)

층 (main > dev > 체인 > 사이클 > 스텝):
  main 은 대문이고 배포된 것만 온다. dev 는 모든 작업이 시작하는 층 — --from 없이 연 체인은
  dev 에서 갈라지는 시조다(대문은 물려받는다). 끝난 체인은 gil merge 로 dev 에 모이고,
  gil deploy 가 그 dev 를 대문으로 올린다.

사고 기록 (체인 > 사이클 > 스텝):
  gil intake <슬러그> --ask <질문JSON>    **체인보다 먼저** 사람에게 묻는다 — 목적도 분기 자리도
                                          사람의 답에서 나온다 (#90). 여기서 시작하는 것이 기본이다.
  gil chain <name> --from-intake <슬러그> --purpose-from <질문번호>  그 답을 **인용**해 체인 개설
  gil chain <name> --purpose <p> [--reference <기준문서>]  (옛 경로 — 목적을 네가 쓰게 된다)
  gil interview <chain> --ask <질문JSON>  이미 연 체인의 기준 문서를 사람과 함께 만든다 (#33)
  gil open <chain>/<cycle> --author <a> --purpose <p>   새 사이클
  gil step <chain>/<cycle> --kind <k> --title <t>       스텝 (define/hypothesis/verify/analyze/pending/…)
  gil adopt <chain>/<cycle>/<승자> --reason <왜>        경합의 승자 채택 (진 갈래는 벽으로, HEAD 는 승자로)
  gil close <chain>/<cycle> --verdict <v> [--abandon]   사이클 닫기 (--abandon: fail만인 죽은 사이클도)
  gil chain-close <chain> --verdict <v>                 체인 닫기 (모든 사이클 닫힌 뒤 — 국면 완결)
  gil merge <합칠 것>... --into <받는 곳> --reason <왜>  합류 (실제 git merge). 끝난 체인 → dev
  gil deploy --tag <v> [--at <chain>/<cycle>/<step>]    배포 = dev 를 대문(main)에 올린다 🚀
  gil docs install [--force]                            온보딩 설치 — docs/gil· 대문 진입점 블록
  gil goto <chain>/<cycle>[/<step>]                     자리 이동 — 산 잎으로/그 스텝으로 (그래프 불변)
  gil log [<chain>] [--all]       노드(스텝) 나열. --all: 죽은 가지까지 모두(벽의 지도)
  gil fsck [<range>]              그래프 건강 검사

v2 이주:
  gil migrate --from <v2-ref> [--dry-run]   v2(폴더·cycle.yaml) 이력 → v3 커밋 그래프

관전 뷰어:
  gil viewer serve [--port <포트>] [--open]  관전 서버(init 이 자동 기동, 브라우저는 --open 일 때만)
  gil viewer build --out <파일>             정적 자기완결 HTML(Pages 등 정적 호스팅용)
  gil viewer list                          어느 포트가 어느 저장소를 보는가
  gil viewer stop                          이 저장소를 보는 뷰어를 끈다(세션정리)

MCP (Claude Desktop 등 호스트에 gil 을 툴로 물린다):
  gil mcp serve [--repo <경로>]             stdio MCP 서버. 인터뷰=네이티브 폼, 그래프=호스트 내 앱

버전:
  gil version [--check|--update]  현재 버전 · 최신과 대조 · SHA256 검증 후 자기갱신

한 명령의 자세한 사용법: gil help <명령>  (예: gil help step)

지식 wiki (통째로 읽지 말고 필요한 주제만 골라 능동적으로):
  개념(체인·사이클·스텝) · 사고의 생애(스텝 흐름·막힘) · 명령 표면 · 존재와 기억
  목적성 가드 · 사람과의 소통(pending) · 배포와 체인 전환 · 스텝 본문=보고서
  → 이 저장소: docs/gil/index.md (없으면 gil docs install 로 설치 — init 이 이미 깔아둔다)
    웹: llms.txt (사람이 URL 하나로 에이전트에 건네는 진입점) · 규범: gil global read gil-init-spec.md`)
}

// cmdHelp 는 문서 라우터로 gil help <명령> 을 처리한다(선언은 usage_help.go).

// ── gil log ──
func cmdLog(args []string) {
	fs := newFlags("gil log")
	all := fs.boolFlag("all")    // 모든 가지(죽은 잎 형제 가지 포함) — 벽의 지도
	depth := fs.str("depth", "") // chain|cycle|step (AIL #2) — 뎁스별 전체맵. 빈값=step(기본).
	pos := fs.parse(args)
	var ch string
	if len(pos) > 0 {
		ch = pos[0]
	}
	if *depth == "" {
		*depth = "step"
	}
	// 분기 신호(AIL #2, clew@AIL): 무플래그로도 일자 편향이 눈에 들게 맨 위에 한 줄 강제.
	// "안 보이는 건 안 짜인다" — 체인·사이클·스텝 분기 수와 죽은 잎을 나란히. 분기만 있고
	// 죽은 잎 0이면 "형식만 분기, 실질은 일자"(--refutes 사후 링크 등)를 가른다.
	bs := computeBranchStats()
	println2("분기  체인 " + itoa(bs.chainBranch) + " · 사이클 " + itoa(bs.cycleBranch) +
		" · 스텝 " + itoa(bs.stepBranch) + "  |  죽은잎 " + itoa(bs.deadLeaves))
	if bs.chainBranch == 0 && bs.cycleBranch == 0 {
		println2("  ⚠ 체인·사이클 분기 0 — 큰 사고는 일자로 흐르는 중(스텝 분기만으론 부족)")
	}
	println2("")

	switch *depth {
	case "chain":
		logDepthChain(*all)
	case "cycle":
		logDepthCycle(ch)
	case "step":
		logDepthStep(ch, *all)
	default:
		die("거부: --depth 는 chain|cycle|step 중 하나")
	}
}

// logDepthStep — 기존 gil log(스텝 노드 나열). 참조: 옛 cmdLog 본체.
func logDepthStep(ch string, all bool) {
	rng := "HEAD"
	if all {
		rng = "--branches"
	}
	nodes := collectNodes(rng)
	// 정정 역방향 맵(AIL #12): 정정된 스텝 → 그를 정정한 스텝. 사이클 안에서 step id 가
	// 유일하므로 (chain,cycle,step) 키로 잡아 다른 사이클과 안 섞이게.
	supersededBy := map[string]string{}
	for _, n := range nodes {
		if n.supersedes != "" {
			supersededBy[n.chain+"\x01"+n.cycle+"\x01"+n.supersedes] = n.step
		}
	}
	// 정밀화 역방향 맵(이슈 #42): 정밀화된 스텝 → 그를 정밀화한 스텝(사이클을 넘으므로 전체 경로 키).
	// 판정만 읽고 멈추지 않게 — 그 해석은 뒤에서 더 좁혀졌다.
	refinedBy := map[string]string{}
	for _, n := range nodes {
		for _, rf := range n.refines {
			refinedBy[rf] = n.chain + "/" + n.cycle + "/" + n.step
		}
	}
	for i := len(nodes) - 1; i >= 0; i-- { // 새→old 이므로 뒤집어 old→new
		n := nodes[i]
		if ch != "" && n.chain != ch {
			continue
		}
		supBy := supersededBy[n.chain+"\x01"+n.cycle+"\x01"+n.step]
		line := n.sha + "  " + n.chain + "/" + n.cycle + "/" + n.step + " [" + n.kind + "]"
		if n.parent != "" && n.parent != "null" {
			line += " ←" + n.parent
		}
		if n.outcome != "" {
			line += " =" + n.outcome
		}
		if n.verdict != "" {
			line += " ⟹" + n.verdict
		}
		if n.polarity == "goal-missed" {
			line += " ⊘goal-missed" // 극성(AIL #13): supported 면 목표 실패를 뜻하는 가설
		}
		if len(n.merges) > 0 {
			line += "  ⋈ " + strings.Join(n.merges, ",")
		}
		if len(n.refutes) > 0 {
			line += "  ⟵refutes " + strings.Join(n.refutes, ",")
		}
		// 정밀화 간선(이슈 #42) — refutes 가 극성 전환이면 refines 는 해석 심화다. 판정은
		// 그대로 서 있으므로 ⤳(이어짐) 표식을 쓴다.
		if len(n.refines) > 0 {
			line += "  ⤳refines " + strings.Join(n.refines, ",")
		}
		if rb := refinedBy[n.chain+"/"+n.cycle+"/"+n.step]; rb != "" {
			line += "  ⤳refined-by(" + rb + ")" // 이 해석은 뒤 사이클이 더 좁혔다
		}
		if n.inherit != "" {
			line += "  ⇐" + n.inherit // 물려받은 전수(AIL #3) — 계보 간선의 지식 라벨
		}
		if n.supersedes != "" {
			line += "  ⟲정정 " + n.supersedes // 이 스텝이 앞선 같은-kind 스텝을 정정(AIL #12)
		}
		if supBy != "" {
			line += "  ⤳정정됨(" + supBy + ")" // 이 스텝은 뒤에서 정정됨
		}
		println2(line)
	}
}

// logDepthChain — 체인 계보 트리(AIL #2). 뷰어 HTML 체인 그래프와 같은 집계원
// (chainsFromGraph·chainParents)을 텍스트로 — AI 도 인간과 동일 정보를 본다.
// logDepthChain — 체인 목록. **봉인된 체인은 기본으로 접는다**(이슈 #85, 상현님 실사용).
//
// 왜. 26개를 한 화면에 같은 무게로 늘어놓으면 "지금 살아 있는 국면이 무엇인가"가 안 보인다.
// 사람이 "쓸데없는 체인이 너무 많다"고 느낀 실체가 이것이었다 — 정리할 게 많은 게 아니라
// **끝난 것이 끝나 보이지 않는다**(실측: 26개 중 24개가 봉인이었고 버릴 건 하나도 없었다).
// 접는 게 지우는 것보다 낫다: append-only 는 그대로고, 화면만 지금을 말한다.
func logDepthChain(all bool) {
	chains, order := chainsFromGraph()
	parents := chainParents()
	superseded := supersededChains()
	var folded int
	for _, name := range order {
		c := chains[name]
		if c.status == "closed" && !all {
			folded++
			continue
		}
		line := "● " + name + "  [사이클 " + itoa(c.cycles) + "]  (" + c.status + ")"
		if p := parents[name]; p != "" {
			line += "  ← " + p
		}
		// 뒤집힌 결론은 뒤집혀 보여야 한다(이슈 #85) — 읽는 쪽이 제일 궁금한 건
		// "어느 결론이 아직 유효한가"다.
		if sb := superseded[name]; sb != "" {
			line += "  ⤳ 대체됨 → " + sb
		}
		println2(line)
	}
	if folded > 0 {
		println2("")
		println2("  (봉인된 체인 " + itoa(folded) + "개는 접었다 — 끝난 것은 끝나 보이게. 펼치려면: gil log --depth chain --all)")
	}
}

// supersededChains — 결론이 다른 체인에서 뒤집힌 체인들(Gil-Superseded-By, 이슈 #85).
func supersededChains() map[string]string {
	out := map[string]string{}
	fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Superseded-By") + sep
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--all"), sep) {
		ch, sb, _ := cut(strings.TrimSpace(rec), fsep)
		if c, b := strings.TrimSpace(ch), strings.TrimSpace(sb); c != "" && b != "" {
			out[c] = b
		}
	}
	return out
}

// logDepthCycle — 한 체인 안 사이클들 + 사이클 부모 엣지 + status(AIL #2). cyclesOf 공유.
func logDepthCycle(ch string) {
	if ch == "" {
		die("사용: gil log --depth cycle <chain>")
	}
	cyc, order := cyclesOf(ch)
	println2("● 체인 " + ch)
	for _, cy := range order {
		c := cyc[cy]
		// 죽은 잎(fail/backtrack)을 품었나 — "일자로 solved"와 "분기 밟고 solved"는 사고의
		// 질이 다르다(clew@AIL). 분기를 실제로 밟은 사이클에 ⚡분기 표식(AIL #2 후속).
		branched := false
		for _, s := range c.steps {
			if isDeadLeaf(s) {
				branched = true
				break
			}
		}
		status := c.status
		if branched {
			status += "⚡분기"
		}
		line := "  ◆ " + cy + "  (" + status + ")"
		if len(c.parents) > 0 {
			line += "  ← " + strings.Join(c.parents, ",")
		}
		println2(line)
		// 측정의 좌표(이슈 #79·#81) — "이 수치가 어느 셋 위에서 무엇을 잰 것인가"를
		// 그래프에서 바로 읽게. 산문 속에만 있으면 기계도 사람도 대조하지 못한다.
		ds, sj := cycleCoordOf(ch, cy)
		for _, ln := range coordLines(ds, sj, "      ") {
			println2(ln)
		}
	}
}

// ── gil fsck ──
func cmdFsck(args []string) {
	// 기본 범위는 전체 그래프(--branches) — HEAD 계보만 보면 죽은 가지(형제 벽)의
	// 미종결 잎·backtrack 결함을 통째로 놓친다(상현님 실사용: c001 s5 analyze 잎이
	// HEAD 밖 죽은 가지라 fsck HEAD 가 못 잡음). 인자로 명시하면 그 범위를 존중한다.
	rng := "--branches"
	if len(args) > 0 {
		rng = args[0]
	}
	universe := collectNodes("--branches")
	v := fsck(collectNodes(rng), declaredChains("--branches"), universe, closedCycles("--branches"))
	// **지워진 체인은 현재 그래프의 구성원이 아니다**(이슈 #97②). prune 은 ref 를 지우지만
	// 옛 적층 때문에 커밋은 다른 브랜치에서 계속 닿는다 — 그래서 지운 체인의 적층이 건강
	// 지표를 계속 오염시켰다. 기본 범위에서는 빼되, **뺐다는 사실은 숫자로 남긴다**(retired
	// 와 같은 규율 — 없는 게 죄가 아니라 감춘 게 죄다).
	prunedLine := ""
	if fsckBuriedDropped > 0 {
		prunedLine = "  🪦 지워진(prune) 체인에 대한 판정 " + itoa(fsckBuriedDropped) + "건은 세지 않았다 — " +
			"묘비가 그 자리를 말한다(계보·적층·층은 지금 서 있는 그래프에만 묻는다).\n" +
			"     유실 경고는 지워진 체인의 것이라도 그대로 센다 — '사라지기 직전'은 지금 일어나는 일이다."
	}
	// 접힌(retired) 영역의 위반은 기본 범위에서 빠진다 — 그 사실을 **숫자로** 남긴다(이슈 #92).
	// retire 는 세는 범위에서 뺄 뿐 아무것도 고치지 않는데, 옛 기본 보고는 그 사실을 한 마디도
	// 하지 않았다. 그래서 "위반 229 → 1" 이 성과로 읽혔다. 도구가 자기 상태를 축소 보고하면
	// 사람은 검증할 기회를 잃는다 — 없는 게 죄가 아니라 감춘 게 죄다(#87 의 축).
	hiddenLine := ""
	if rng == "--branches" {
		if h := hiddenViolationCount(); h > 0 {
			hiddenLine = "  ↩ 접힌(retired) 체인에 위반 " + itoa(h) + "건이 더 있다 — 이 숫자에는 안 들어간다. " +
				"보려면: gil fsck --all"
		}
	}
	blind := devLayerBlindNotice()
	noRef := noReferenceChainsNotice()
	comp := competingNotice()
	// 뒤처짐은 **위반이 아니다** — 체인은 갈라져 자라니 뒤처지는 것이 정상이다. 그러나
	// 그 사이 dev 가 **이 트리의 파일을 고쳤다면** 낡은 값이 그 자리에 그대로 있어서 조용히
	// 틀린다(이슈 #115). 그래서 세지 않고 **고지**한다(🪦·↩ 와 같은 자리).
	behind := behindChainsNotice()
	if len(v) == 0 {
		println2("fsck: 위반 0 — 커밋 그래프 건강")
		if blind != "" {
			println2(blind)
		}
		if noRef != "" {
			println2(noRef)
		}
		if comp != "" {
			println2(comp)
		}
		if behind != "" {
			println2(behind)
		}
		if prunedLine != "" {
			println2(prunedLine)
		}
		if hiddenLine != "" {
			println2(hiddenLine)
			println2("  (접었다고 고쳐진 것은 아니다. 되돌리기: gil chain-unretire <chain>)")
		}
		return
	}
	for _, x := range v {
		println2("위반: " + x)
	}
	if blind != "" {
		println2(blind)
	}
	if noRef != "" {
		println2(noRef)
	}
	if behind != "" {
		println2(behind)
	}
	if comp != "" {
		println2(comp)
	}
	if prunedLine != "" {
		println2(prunedLine)
	}
	if hiddenLine != "" {
		println2(hiddenLine)
	}
	gilExit(1)
}

// ── 출력 헬퍼 ──

// println2/stderr/outRaw — 사람·LLM 대상 출력의 단일 통로. MCP 모드에서는 stdout 이
// JSON-RPC 전송선이라 한 글자도 섞으면 안 된다 → 버퍼로 돌려 툴 결과 텍스트로 되돌린다.
func println2(s string) { outRaw(s + "\n") }
func stderr(s string) {
	if mcpMode {
		outRaw(s + "\n")
		return
	}
	os.Stderr.WriteString(s + "\n")
}
func outRaw(s string) {
	if mcpMode {
		mcpOut.WriteString(s)
		return
	}
	os.Stdout.WriteString(s)
}

// noReferenceChainsNotice — 열려 있는데 **기준 문서가 없어 사이클을 못 여는** 체인들(이슈 #109).
//
// 위반이 아니라 고지다: v3.37.0 이전에 만들어진 체인은 원리적으로 이 상태이고, 그걸 위반으로
// 세면 옛 저장소가 통째로 병든 것이 된다(#99 에서 한 번 되돌린 자리와 같은 논리). 하지만
// 침묵도 답이 아니다 — 그 체인 앞에 선 세션은 open 이 거부할 때에야 이유를 안다.
func noReferenceChainsNotice() string {
	var stuck []string
	for _, c := range openChains() {
		if interviewState(c) == "none" {
			stuck = append(stuck, c)
		}
	}
	if len(stuck) == 0 {
		return ""
	}
	return "  ⚠ 기준 문서가 없어 사이클을 못 여는 열린 체인 " + itoa(len(stuck)) + "개: " +
		strings.Join(stuck, " ") + "\n" +
		"     위반은 아니다(v3.37.0 이전 체인은 이 상태로 태어났다) — 다만 이대로는 아무것도 못 연다.\n" +
		"     조치: gil interview <chain> --ask <질문JSON>  → 사람이 답하면 열린다."
}
