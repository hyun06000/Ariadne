// gil v3 — 커밋 그래프 위의 체인·사이클·스텝. Go 참조 구현 (git 래퍼, 의존성 0).
//
// 참조 구현(gil.py, Python)을 Go로 옮긴 것. 진실원은 언제나 git 커밋 그래프이고, 이
// 바이너리는 그걸 파싱·기록하는 얇은 층이다. git만 있으면 다른 의존성 없이 돈다(상현님):
// Python 런타임도 필요 없는 단일 네이티브 바이너리. web(뷰어)은 gil로 짓는 실작업이라
// 여기 없다 — 배포 후 orphan 브랜치에서 gil 사이클로 지어 chain-merge로 이식한다.
package main

import (
	"os"
	"strings"
)

func main() {
	// 인자 없이 호출되면 사용법을 낸다 — 출력은 LLM 에게 들어가는 프롬프트이므로,
	// "무엇을 할 수 있는지"를 알려주는 게 침묵보다 낫다(상현님).
	if len(os.Args) <= 1 {
		printUsage()
		return
	}
	cmd := os.Args[1]
	rest := os.Args[2:]
	switch cmd {
	case "help", "-h", "--help":
		printUsage()
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
	default:
		die("gil: 알 수 없는 명령 \"" + cmd + "\" — [init chain chain-merge open step close approve reject log fsck global memory handoff]")
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
  gil chain-merge <src>... --into <dst>                 완성 체인 병합 (실제 git merge)
  gil log [<chain>] [--all]       노드(스텝) 나열. --all: 죽은 가지까지 모두(벽의 지도)
  gil fsck [<range>]              그래프 건강 검사

자세히: gil global read gil-init-spec.md, QUICKSTART.md`)
}

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
	rng := "HEAD"
	if len(args) > 0 {
		rng = args[0]
	}
	v := fsck(collectNodes(rng), declaredChains("HEAD"), collectNodes("HEAD"))
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
