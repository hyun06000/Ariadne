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
	switch cmd {
	case "help", "-h", "--help":
		cmdHelp(rest)
	case "version":
		cmdVersion(rest)
	case "init":
		cmdInit(rest)
	case "chain":
		cmdChain(rest)
	case "chain-merge":
		cmdChainMerge(rest)
	case "open":
		cmdOpen(rest)
	case "step":
		cmdStep(rest)
	case "close":
		cmdClose(rest)
	case "chain-close":
		cmdChainClose(rest)
	case "deploy":
		cmdDeploy(rest)
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
		die("gil: 알 수 없는 명령 \"" + cmd + "\" — [init chain chain-close chain-merge open step close deploy interview approve reject goto docs log fsck global memory handoff migrate viewer mcp version]")
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
  gil memory read [<이름>]        존재의 기억 읽기 (기본 clew)
  gil memory append <이름> <file> 기억에 매듭 이어붙임 (안전, 자동 push)

사고 기록 (체인 > 사이클 > 스텝):
  gil chain <name> --purpose <p> [--reference <기준문서>]  새 체인 개설 (--reference: 기준 문서, #33)
  gil interview <chain> --ask <질문JSON>  사람에게 설문 폼(뷰어)을 띄워 기준 문서를 함께 만든다 (#33)
  gil open <chain>/<cycle> --author <a> --purpose <p>   새 사이클
  gil step <chain>/<cycle> --kind <k> --title <t>       스텝 (define/hypothesis/verify/analyze/pending/…)
  gil close <chain>/<cycle> --verdict <v> [--abandon]   사이클 닫기 (--abandon: fail만인 죽은 사이클도)
  gil chain-close <chain> --verdict <v>                 체인 닫기 (모든 사이클 닫힌 뒤 — 국면 완결)
  gil deploy --at <chain>/<cycle>/<step> --tag <v> [--url <u>]  배포(공개) 지점 마커 — 뷰어에 🚀
  gil chain-merge <src>... --into <dst>                 완성 체인 병합 (실제 git merge)
  gil docs install [--force]                            온보딩 설치 — docs/gil· 대문 진입점 블록
  gil goto <chain>/<cycle>[/<step>]                     자리 이동 — 산 잎으로/그 스텝으로 (그래프 불변)
  gil log [<chain>] [--all]       노드(스텝) 나열. --all: 죽은 가지까지 모두(벽의 지도)
  gil fsck [<range>]              그래프 건강 검사

v2 이주:
  gil migrate --from <v2-ref> [--dry-run]   v2(폴더·cycle.yaml) 이력 → v3 커밋 그래프

관전 뷰어:
  gil viewer serve [--port <포트>] [--open]  관전 서버(init 이 자동 기동, 브라우저는 --open 일 때만)
  gil viewer build --out <파일>             정적 자기완결 HTML(Pages 등 정적 호스팅용)

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
	all := fs.boolFlag("all")     // 모든 가지(죽은 잎 형제 가지 포함) — 벽의 지도
	depth := fs.str("depth", "")  // chain|cycle|step (AIL #2) — 뎁스별 전체맵. 빈값=step(기본).
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
		logDepthChain()
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
func logDepthChain() {
	chains, order := chainsFromGraph()
	parents := chainParents()
	for _, name := range order {
		c := chains[name]
		line := "● " + name + "  [사이클 " + itoa(c.cycles) + "]  (" + c.status + ")"
		if p := parents[name]; p != "" {
			line += "  ← " + p
		}
		println2(line)
	}
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
	if len(v) == 0 {
		println2("fsck: 위반 0 — 커밋 그래프 건강")
		return
	}
	for _, x := range v {
		println2("위반: " + x)
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
