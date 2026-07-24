// gil 그래프 뷰어 — 다른 레포의 gil 그래프를 읽어 그린다(읽기 전용).
//
// 서브에이전트가 실사용 레포에서 gil 로 만드는 사고이력(체인>사이클>스텝)을 밖에서 관전
// 한다. git 명령은 -C <repo> 로 대상 레포에서 돈다 — 뷰어를 그 레포 안에 두지 않아 작업과
// 충돌 없음. stdlib 만, 외부 의존 0.
//
//   gilviewer --repo <경로>            텍스트 트리 1회 출력
//   gilviewer serve --repo <경로>      브라우저 관전 서버(자동 새로고침)
package main

import (
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strings"
)

var repoDir = "." // --repo 로 지정. git 을 이 레포에서 실행.

func git(args ...string) ([]byte, error) {
	full := append([]string{"-C", repoDir}, args...)
	return exec.Command("git", full...).Output()
}

type node struct {
	sha, full, subject       string
	chain, cycle, step, kind string
	outcome, verdict         string
	parent, backtrack        string // Gil-Parent(부모 스텝), Gil-Backtrack(되돌아간 목표)
}

func collectNodes() []node {
	const rs = "\x1e"
	const fs = "\x1f"
	format := "%H" + fs + "%s" + fs + "%(trailers:only=true,unfold=true)" + rs
	out, err := git("log", "--branches", "--format="+format)
	if err != nil {
		fmt.Fprintln(os.Stderr, "거부: git log 실패(레포 경로·gil 그래프 확인) —", err)
		return nil
	}
	var nodes []node
	for _, rec := range strings.Split(string(out), rs) {
		rec = strings.TrimLeft(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		parts := strings.SplitN(rec, fs, 3)
		if len(parts) < 3 {
			continue
		}
		tr := parseTrailers(parts[2])
		if tr["Gil-Step"] == "" {
			continue
		}
		nodes = append(nodes, node{
			sha: parts[0][:9], full: parts[0], subject: parts[1],
			chain: tr["Gil-Chain"], cycle: tr["Gil-Cycle"], step: tr["Gil-Step"],
			kind: tr["Gil-Kind"], outcome: tr["Gil-Outcome"], verdict: tr["Gil-Verdict"],
			parent: tr["Gil-Parent"], backtrack: tr["Gil-Backtrack"],
		})
	}
	return nodes
}

func parseTrailers(s string) map[string]string {
	m := map[string]string{}
	for _, ln := range strings.Split(s, "\n") {
		k, v, ok := strings.Cut(ln, ":")
		if ok {
			m[strings.TrimSpace(k)] = strings.TrimSpace(v)
		}
	}
	return m
}

func tipSHAs() map[string]string {
	const fs = "\x1f"
	out, err := git("for-each-ref", "--format=%(refname:short)"+fs+"%(objectname)", "refs/heads/")
	if err != nil {
		return nil
	}
	tips := map[string]string{}
	for _, ln := range strings.Split(strings.TrimSpace(string(out)), "\n") {
		br, sha, ok := strings.Cut(ln, fs)
		if ok {
			tips[br] = sha
		}
	}
	return tips
}

// chainParent — 각 체인이 어느 체인에서 갈라졌나(계보 엣지). 자식→부모.
// chain-root 커밋의 첫 부모가 속한 Gil-Chain 이 부모 체인. 부모 없으면 "".
func chainParents() map[string]string {
	const rs = "\x1e"
	const fs = "\x1f"
	// 모든 chain-root 커밋: sha, 이 커밋의 체인, 첫 부모 sha.
	// 레코드 구분자는 rs(\x1e) — trailer 값(Gil-Chain-Purpose 등)에 개행이 들어가면
	// "\n" split 이 한 레코드를 쪼개 chain 필드가 빈 값이 된다(상현님: 새 체인 hackathon-a
	// 가 뷰어에 안 뜸 — Gil-Chain-Purpose 가 길어 파싱이 밀렸다). valueonly 대신 -z 대체로
	// rs 로 확정한다.
	out, err := git("log", "--branches", "--format=%H"+fs+"%(trailers:key=Gil-Kind,valueonly,unfold=true)"+fs+
		"%(trailers:key=Gil-Chain,valueonly,unfold=true)"+fs+"%P"+rs)
	if err != nil {
		return nil
	}
	// 커밋 sha → 그 커밋이 속한 체인 (부모 커밋의 체인을 찾기 위해).
	shaChain := map[string]string{}
	type rootRec struct{ chain, firstParent string }
	var roots []rootRec
	for _, rec := range strings.Split(string(out), rs) {
		rec = strings.Trim(rec, "\n")
		if rec == "" {
			continue
		}
		f := strings.Split(rec, fs)
		if len(f) < 4 {
			continue
		}
		sha := strings.TrimSpace(f[0])
		kind := strings.TrimSpace(f[1])
		chain := strings.TrimSpace(f[2])
		parents := strings.TrimSpace(f[3])
		if chain != "" {
			shaChain[sha] = chain
		}
		if kind == "chain-root" {
			fp := ""
			if ps := strings.Fields(parents); len(ps) > 0 {
				fp = ps[0]
			}
			roots = append(roots, rootRec{chain, fp})
		}
	}
	parent := map[string]string{}
	for _, r := range roots {
		parent[r.chain] = shaChain[r.firstParent] // 없으면 ""
	}
	return parent
}

type cycleView struct {
	name  string
	steps []node
}
type chainView struct {
	name   string
	cycles []cycleView
}
type graphView struct {
	chains              []chainView
	here                map[string]string // "chain/cycle/step" → HEAD 스텝 위치
	hereCyc             map[string]string // "chain/cycle" → HEAD 가 이 사이클(스텝 팁 아닐 때)
	parents             map[string]string // 체인 계보 엣지: 자식→부모
	nodeCount, tipCount int
}

// hereChains — 현재위치가 있는 체인 이름 집합(스텝 또는 사이클 레벨).
func (g graphView) hereChains() map[string]bool {
	m := map[string]bool{}
	for k := range g.here {
		if i := strings.IndexByte(k, '/'); i > 0 {
			m[k[:i]] = true
		}
	}
	for k := range g.hereCyc {
		if i := strings.IndexByte(k, '/'); i > 0 {
			m[k[:i]] = true
		}
	}
	return m
}

func posKey(n node) string { return n.chain + "/" + n.cycle + "/" + n.step }

// status — 사이클의 결말 요약. 마지막 analyze 의 outcome, 또는 pending/열림.
func (cy cycleView) status() string {
	last := ""
	for _, n := range cy.steps {
		switch {
		case n.kind == "analyze" && n.outcome == "success":
			last = "success"
		case n.kind == "analyze" && (n.outcome == "backtrack" || n.outcome == "fail"):
			if last != "success" {
				last = "dead"
			}
		case n.kind == "pending" && last == "":
			last = "pending"
		}
	}
	if last == "" {
		return "open"
	}
	return last
}

// currentBranch — HEAD 가 가리키는 브랜치(현재 작업위치). detached 면 "".
func currentBranch() string {
	out, err := git("symbolic-ref", "--quiet", "--short", "HEAD")
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

// headChainCycle — HEAD 커밋의 Gil-Chain/Gil-Cycle 트레일러(팁이 스텝이 아닐 때 현재 사이클).
func headChainCycle() (string, string) {
	const fs = "\x1f"
	out, err := git("log", "-1", "HEAD",
		"--format=%(trailers:key=Gil-Chain,valueonly)"+fs+"%(trailers:key=Gil-Cycle,valueonly)")
	if err != nil {
		return "", ""
	}
	ch, cy, _ := strings.Cut(strings.TrimSpace(string(out)), fs)
	return strings.TrimSpace(ch), strings.TrimSpace(cy)
}

func buildGraph() graphView {
	nodes := collectNodes()
	tips := tipSHAs()
	posBySHA := map[string]string{}
	for _, n := range nodes {
		posBySHA[n.full] = posKey(n)
	}
	// 현재위치 = HEAD 가 가리키는 브랜치 하나(피드백 3). 모든 브랜치 팁을 현재위치로
	// 표시하면 브랜치가 많을 때 여러 개 떠 혼란. HEAD 브랜치만 "현재위치"로 강조하고,
	// 나머지 브랜치 팁은 그냥 가지 끝일 뿐이다. (여러 에이전트=여러 워킹트리면 각자 HEAD.)
	head := currentBranch()
	here := map[string]string{}   // "chain/cycle/step" → 현재 스텝 위치
	hereCyc := map[string]string{} // "chain/cycle" → HEAD 가 이 사이클에 있음(스텝 팁 아닐 때)
	tipCount := 0
	if sha, ok := tips[head]; ok {
		if p, ok := posBySHA[sha]; ok {
			here[p] = head
			tipCount = 1
		} else {
			// HEAD 팁이 스텝이 아님(close 등) — 그 커밋의 chain/cycle 을 현재 사이클로.
			if ch, cy := headChainCycle(); ch != "" {
				hereCyc[ch+"/"+cy] = head
				tipCount = 1
			}
		}
	}
	chainParent := chainParents()
	chainOrder := []string{}
	seenChain := map[string]bool{}
	byChain := map[string][]node{}
	for i := len(nodes) - 1; i >= 0; i-- {
		n := nodes[i]
		if !seenChain[n.chain] {
			seenChain[n.chain] = true
			chainOrder = append(chainOrder, n.chain)
		}
		byChain[n.chain] = append(byChain[n.chain], n)
	}
	// 스텝(사이클)이 아직 없는 빈 체인도 그린다 — chain-root 만 있는 새로 발의된 체인이
	// 그래프에서 사라지면 "체인이 열렸다"는 신호가 안 보인다(상현님: chain-close 후 새 체인
	// hackathon-a 를 발의했는데 뷰어에 아무 변화가 없었다). chainParents 가 선언된 모든
	// 체인을 key 로 가지므로 노드 없는 체인을 뒤에 덧붙인다.
	declared := make([]string, 0, len(chainParent))
	for ch := range chainParent {
		declared = append(declared, ch)
	}
	sort.Strings(declared) // 결정적 순서
	for _, ch := range declared {
		if ch != "" && !seenChain[ch] {
			seenChain[ch] = true
			chainOrder = append(chainOrder, ch)
		}
	}
	g := graphView{here: here, hereCyc: hereCyc, parents: chainParent, nodeCount: len(nodes), tipCount: tipCount}
	for _, ch := range chainOrder {
		cv := chainView{name: ch}
		cycOrder := []string{}
		seenCyc := map[string]bool{}
		byCyc := map[string][]node{}
		for _, n := range byChain[ch] {
			if !seenCyc[n.cycle] {
				seenCyc[n.cycle] = true
				cycOrder = append(cycOrder, n.cycle)
			}
			byCyc[n.cycle] = append(byCyc[n.cycle], n)
		}
		for _, cy := range cycOrder {
			steps := byCyc[cy]
			sort.SliceStable(steps, func(i, j int) bool { return stepNum(steps[i].step) < stepNum(steps[j].step) })
			cv.cycles = append(cv.cycles, cycleView{name: cy, steps: steps})
		}
		g.chains = append(g.chains, cv)
	}
	return g
}

func main() {
	args := os.Args[1:]
	serveMode := false
	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "serve":
			serveMode = true
		case "--repo":
			if i+1 < len(args) {
				repoDir = args[i+1]
				i++
			}
		}
	}
	if serveMode {
		serve(args)
		return
	}
	renderText(buildGraph())
}

func renderText(g graphView) {
	fmt.Println("═══ gil 그래프 뷰어 — 체인 > 사이클 > 스텝 ═══")
	fmt.Printf("(스텝 노드 %d개, 현재위치 팁 %d개 · ▶=현재위치)\n\n", g.nodeCount, g.tipCount)
	for _, ch := range g.chains {
		fmt.Printf("● 체인 %s\n", ch.name)
		for _, cy := range ch.cycles {
			fmt.Printf("  ◆ 사이클 %s\n", cy.name)
			for _, n := range cy.steps {
				marker := "  "
				if _, ok := g.here[posKey(n)]; ok {
					marker = "▶ "
				}
				line := fmt.Sprintf("    %s%s [%s]", marker, n.step, n.kind)
				if n.outcome != "" {
					line += " =" + n.outcome
				}
				if n.verdict != "" {
					line += " ⟹" + n.verdict
				}
				if br, ok := g.here[posKey(n)]; ok {
					line += "   ← 현재위치 (" + br + ")"
				}
				fmt.Println(line)
			}
		}
		fmt.Println()
	}
}

func stepNum(s string) int {
	if len(s) < 2 {
		return 0
	}
	n := 0
	for _, c := range s[1:] {
		if c < '0' || c > '9' {
			return 0
		}
		n = n*10 + int(c-'0')
	}
	return n
}
