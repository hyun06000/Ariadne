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
	cmd := "log"
	if len(os.Args) > 1 {
		cmd = os.Args[1]
	}
	rest := os.Args[2:]
	switch cmd {
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
		die("gil: 알 수 없는 명령 \"" + cmd + "\" — [chain chain-merge open step close log fsck global memory handoff]")
	}
}

// ── gil log ──
func cmdLog(args []string) {
	var ch string
	if len(args) > 0 {
		ch = args[0]
	}
	nodes := collectNodes("HEAD")
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
