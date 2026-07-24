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
	"strings"
)

// requireGit — git 실행파일이 PATH 에 없으면 사람 언어로 안내하고 멈춘다. gil 은 위계 전체를
// 진짜 git 브랜치·커밋으로 남기므로 git 없이는 아무 명령도 못 돈다. 이 출력은 LLM 에게 들어가는
// 프롬프트다 — Go 런타임의 날것 에러("exec: git ... not found") 대신, AI 가 곧장 사람에게
// "git 을 설치하라"고 안내할 수 있게 원인·해결을 콕 집어 준다.
func requireGit() {
	if _, err := exec.LookPath("git"); err != nil {
		die("거부: git 실행파일을 찾을 수 없다 (PATH 에 git 없음).\n" +
			"  gil 은 사고 이력을 진짜 git 브랜치·커밋으로 남기므로 git 이 반드시 필요하다.\n" +
			"  사람에게 git 설치를 안내하라: https://git-scm.com/downloads\n" +
			"    macOS: xcode-select --install (또는 brew install git)\n" +
			"    Debian/Ubuntu: sudo apt-get install git   |   Fedora: sudo dnf install git\n" +
			"  설치 뒤 같은 명령을 다시 실행하면 된다.")
	}
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
	if cmd != "help" && cmd != "-h" && cmd != "--help" {
		requireGit()
	}
	switch cmd {
	case "help", "-h", "--help":
		cmdHelp(rest)
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
	case "approve":
		cmdApprove(rest)
	case "reject":
		cmdReject(rest)
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
	default:
		die("gil: 알 수 없는 명령 \"" + cmd + "\" — [init chain chain-close chain-merge open step close approve reject log fsck global memory handoff migrate]")
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
  gil chain <name> --purpose <p>  새 체인 개설 (닫힌 체인 끝에서만)
  gil open <chain>/<cycle> --author <a> --purpose <p>   새 사이클
  gil step <chain>/<cycle> --kind <k> --title <t>       스텝 (define/hypothesis/verify/analyze/pending/…)
  gil close <chain>/<cycle> --verdict <v>               사이클 닫기
  gil chain-close <chain> --verdict <v>                 체인 닫기 (모든 사이클 닫힌 뒤 — 국면 완결)
  gil chain-merge <src>... --into <dst>                 완성 체인 병합 (실제 git merge)
  gil log [<chain>] [--all]       노드(스텝) 나열. --all: 죽은 가지까지 모두(벽의 지도)
  gil fsck [<range>]              그래프 건강 검사

v2 이주:
  gil migrate --from <v2-ref> [--dry-run]   v2(폴더·cycle.yaml) 이력 → v3 커밋 그래프

한 명령의 자세한 사용법: gil help <명령>  (예: gil help step)

지식 wiki (통째로 읽지 말고 필요한 주제만 골라 능동적으로):
  개념(체인·사이클·스텝) · 사고의 생애(스텝 흐름·막힘) · 명령 표면 · 존재와 기억
  목적성 가드 · 사람과의 소통(pending) · 배포와 체인 전환 · 스텝 본문=보고서
  → 레포: docs/gil/index.md   웹: <레포>/llms.txt (사람이 URL 하나로 에이전트에 건네는 진입점)
  단일 통독판: QUICKSTART.md · 규범 명세: gil global read gil-init-spec.md`)
}

// cmdHelp 는 문서 라우터로 gil help <명령> 을 처리한다(선언은 usage_help.go).

// ── gil log ──
func cmdLog(args []string) {
	fs := newFlags("gil log")
	all := fs.boolFlag("all") // 모든 가지(죽은 잎 형제 가지 포함) — 벽의 지도
	pos := fs.parse(args)
	var ch string
	if len(pos) > 0 {
		ch = pos[0]
	}
	// 기본은 HEAD 계보. --all 이면 모든 브랜치(죽은 가지도) — gil log 에서 벽의 지도를 본다.
	rng := "HEAD"
	if *all {
		rng = "--branches"
	}
	nodes := collectNodes(rng)
	// collectNodes는 새→old. 트리 순서(old→new)로 출력.
	for i := len(nodes) - 1; i >= 0; i-- {
		n := nodes[i]
		if ch != "" && n.chain != ch {
			continue
		}
		line := n.sha + "  " + n.chain + "/" + n.cycle + "/" + n.step + " [" + n.kind + "]"
		if n.parent != "" && n.parent != "null" {
			line += " ←" + n.parent
		}
		if n.outcome != "" {
			line += " =" + n.outcome
		}
		if len(n.merges) > 0 {
			line += "  ⋈ " + strings.Join(n.merges, ",")
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
	os.Exit(1)
}

// ── 출력 헬퍼 ──

func println2(s string) { os.Stdout.WriteString(s + "\n") }
func stderr(s string)   { os.Stderr.WriteString(s + "\n") }
