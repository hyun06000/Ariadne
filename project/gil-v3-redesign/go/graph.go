// graph.go — 커밋 그래프 조회·집계 헬퍼 + fsck.
//
// 참조 구현(gil.py)의 declared_chains·*_purpose·chain_closed·chain_has_children·fsck와
// gilweb.py의 chains_from_graph·cycles_of(순수 그래프 파싱 — 렌더 무관)를 옮긴다.
// 렌더링(md_to_html·render_*)은 web 실작업으로 남기고, handoff가 쓰는 파싱만 가져온다.
package main

import (
	"regexp"
	"sort"
	"strings"
)

var idRe = regexp.MustCompile(`^[a-z0-9-]+$`) // 옛 R1: 소문자·숫자·하이픈만 (git ref 안전)

var kinds = map[string]bool{
	"define": true, "hypothesis": true, "verify": true, "analyze": true,
	"success": true, "fail": true, "pending": true,
}
var outcomes = map[string]bool{"success": true, "backtrack": true, "fail": true}

// declaredChains — Gil-Chain 트레일러를 가진 모든 커밋의 체인 이름(루트 포함).
// 참조: declared_chains. 체인 루트는 Gil-Step이 없어 collectNodes가 안 잡으므로 따로.
func declaredChains(revRange string) map[string]bool {
	out := gitlog("--format="+trailer("Gil-Chain"), revRange)
	set := map[string]bool{}
	for _, ln := range strings.Split(out, "\n") {
		if s := strings.TrimSpace(ln); s != "" {
			set[s] = true
		}
	}
	return set
}

// chainPurpose — 체인 목적성(자연어)을 커밋 그래프에서 읽는다. 없으면 "".
// 참조: chain_purpose. 같은 Gil-Chain 커밋 중 Gil-Chain-Purpose가 있는 첫(최신) 값.
func chainPurpose(chain, revRange string) string {
	fmt := trailer("Gil-Chain") + fsep + trailer("Gil-Chain-Purpose") + sep
	out := gitlog("--format="+fmt, revRange)
	for _, rec := range strings.Split(out, sep) {
		c, k, _ := cut(rec, fsep)
		if strings.TrimSpace(c) == chain && strings.TrimSpace(k) != "" {
			return strings.TrimSpace(k)
		}
	}
	return ""
}

// cyclePurpose — 사이클 목적성. 참조: cycle_purpose.
func cyclePurpose(chain, cycle, revRange string) string {
	fmt := trailer("Gil-Chain") + fsep + trailer("Gil-Cycle") + fsep +
		trailer("Gil-Cycle-Purpose") + sep
	out := gitlog("--format="+fmt, revRange)
	for _, rec := range strings.Split(out, sep) {
		c, rest, _ := cut(rec, fsep)
		cy, pu, _ := cut(rest, fsep)
		if strings.TrimSpace(c) == chain && strings.TrimSpace(cy) == cycle && strings.TrimSpace(pu) != "" {
			return strings.TrimSpace(pu)
		}
	}
	return ""
}

// showPurposeContext — 시작 지점에서 목적성을 stderr에 띄운다(정합은 AI가 판단).
// 참조: _show_purpose_context.
func showPurposeContext(chain, cycle, cyclePurposeStr string) {
	cp := chainPurpose(chain, "HEAD")
	if cp != "" {
		stderr("─ 체인 [" + chain + "] 목적: " + cp)
	}
	if cycle != "" {
		pu := cyclePurposeStr
		if pu == "" {
			pu = cyclePurpose(chain, cycle, "HEAD")
		}
		if pu != "" {
			stderr("─ 사이클 [" + cycle + "] 목적: " + pu)
		}
	}
	if cp != "" || cycle != "" {
		stderr("─ 지금 하려는 일이 위 목적에 정합하는지 판단하고, 어긋나면 멈춰라.")
	}
}

// chainClosed — Gil-Kind: chain-close 커밋이 이 체인에 있으면 true.
// 참조: chain_closed. 사이클 close와 체인 close는 다르다(도그푸딩이 잡은 버그).
func chainClosed(chain, revRange string) bool {
	fmt := trailer("Gil-Chain") + fsep + trailer("Gil-Kind") + sep
	out := gitlog("--format="+fmt, revRange)
	for _, rec := range strings.Split(out, sep) {
		c, k, _ := cut(rec, fsep)
		if strings.TrimSpace(c) == chain && strings.TrimSpace(k) == "chain-close" {
			return true
		}
	}
	return false
}

// chainHasChildren — 이 체인을 부모로 선언한 다른 체인이 있는가. 참조: chain_has_children.
func chainHasChildren(chain, revRange string) bool {
	out := gitlog("--format="+trailer("Gil-Chain-Parent"), revRange)
	for _, ln := range strings.Split(out, "\n") {
		if strings.TrimSpace(ln) == chain {
			return true
		}
	}
	return false
}

// stepKey — (chain,cycle,step) 조합키.
func stepKey(c, cy, s string) string { return c + "\x01" + cy + "\x01" + s }

// fsck — SPEC §3 무결성 검사. 위반 문자열 리스트(빈=건강). 참조: fsck.
// nodes=검사 대상, universe=참조 실재 확인용 전체(부모가 범위 밖이어도 실재하면 통과).
func fsck(nodes []node, chainsKnown map[string]bool, universe []node) []string {
	var violations []string
	if universe == nil {
		universe = nodes
	}
	chains := map[string]bool{}
	for c := range chainsKnown {
		chains[c] = true
	}
	cycles := map[string]string{} // cycle id -> chain
	stepKeys := map[string]bool{}

	for _, n := range universe {
		if n.chain != "" {
			chains[n.chain] = true
		}
		stepKeys[stepKey(n.chain, n.cycle, n.step)] = true
		if n.cycle != "" && n.kind == "define" && (n.parent == "" || n.parent == "null") {
			cycles[n.cycle] = n.chain
		}
	}

	for _, n := range nodes {
		cc := n.chain + "/" + n.cycle + "/" + n.step
		// 1. 위계 무결성
		if n.chain == "" {
			violations = append(violations, "위계: "+cc+" — Gil-Chain 없음 (체인 없는 스텝 금지)")
		} else if !chains[n.chain] {
			violations = append(violations, "위계: "+cc+" — 미선언 체인 "+n.chain)
		}
		if n.cycle == "" {
			violations = append(violations, "위계: "+cc+" — Gil-Cycle 없음 (사이클 없는 스텝 금지)")
		}
		// 2. id 문법 (옛 R1)
		for _, kv := range [][2]string{{"chain", n.chain}, {"cycle", n.cycle}, {"step", n.step}} {
			if kv[1] != "" && !idRe.MatchString(kv[1]) {
				violations = append(violations, "id문법: "+cc+" — "+kv[0]+" id \""+kv[1]+"\" 는 소문자·숫자·하이픈만 (마침표 금지)")
			}
		}
		// 3. kind 유효
		if n.kind != "" && !kinds[n.kind] {
			violations = append(violations, "kind: "+cc+" — 알 수 없는 kind \""+n.kind+"\"")
		}
		// 4. dangling parent (전체 그래프 기준)
		if p := n.parent; p != "" && p != "null" {
			if !stepKeys[stepKey(n.chain, n.cycle, p)] {
				violations = append(violations, "위계: "+cc+" — 부모 스텝 "+p+" 실재 안 함 (dangling parent)")
			}
		}
		// 5. analyze는 outcome 강제
		if n.kind == "analyze" && !outcomes[n.outcome] {
			violations = append(violations, "스텝순환: "+cc+" — analyze는 Gil-Outcome (success|backtrack|fail) 필요")
		}
		if n.outcome == "backtrack" && n.backtrack == "" {
			violations = append(violations, "스텝순환: "+cc+" — backtrack은 Gil-Backtrack (조상 define) 필요")
		}
		// 6. 계보 참조 무결성 — 스텝 머지(같은 사이클 산 잎)는 실재로 이미 확인, 나머지가 체인/사이클 머지.
		var cycChainMerges []string
		for _, ref := range n.merges {
			if !stepKeys[stepKey(n.chain, n.cycle, ref)] {
				cycChainMerges = append(cycChainMerges, ref)
			}
		}
		refs := append([]string{}, n.cycleParents...)
		refs = append(refs, cycChainMerges...)
		for _, ref := range refs {
			if chains[ref] {
				continue // 체인 부모/머지
			}
			if strings.Contains(ref, "/") {
				continue // 외부 참조 — 실재 미검사
			}
			if _, ok := cycles[ref]; !ok {
				violations = append(violations, "계보: "+cc+" — 같은 체인 참조 \""+ref+"\" 실재 안 함")
			}
		}
	}
	return violations
}

// ── 체인·사이클 집계 (handoff가 쓰는 파싱 — gilweb.py에서 렌더 제외하고 가져옴) ──

// branches — 로컬 브랜치 목록. 참조: gilweb._branches.
func branches() []string {
	out := git("for-each-ref", "--format=%(refname:short)", "refs/heads/")
	var bs []string
	for _, b := range strings.Split(out, "\n") {
		if s := strings.TrimSpace(b); s != "" {
			bs = append(bs, s)
		}
	}
	return bs
}

// commitInfo — commit_index의 값. 참조: gilweb.commit_index.
type commitInfo struct {
	subject      string
	chain        string
	kind         string
	mode         string
	cycleParents []string
	merges       []string
}

var idxKeys = []string{"Gil-Chain", "Gil-Kind", "Gil-Mode", "Gil-Cycle-Parent", "Gil-Merge"}

// commitIndex — 단일 git log --branches로 모든 커밋의 subject·주요 트레일러 인덱스.
// 참조: gilweb.commit_index.
func commitIndex() map[string]commitInfo {
	parts := []string{"%H", "%s"}
	for _, k := range idxKeys[:3] {
		parts = append(parts, trailer(k))
	}
	for _, k := range idxKeys[3:] {
		parts = append(parts, trailerMulti(k))
	}
	fmt := strings.Join(parts, fsep) + sep
	out := git("log", "--branches", "--format="+fmt)
	idx := map[string]commitInfo{}
	for _, rec := range strings.Split(out, sep) {
		rec = strings.Trim(rec, "\n")
		if rec == "" {
			continue
		}
		f := strings.Split(rec, fsep)
		if len(f) < 7 {
			continue
		}
		idx[first9(f[0])] = commitInfo{
			subject:      f[1],
			chain:        strings.TrimSpace(f[2]),
			kind:         strings.TrimSpace(f[3]),
			mode:         strings.TrimSpace(f[4]),
			cycleParents: splitMulti(f[5]),
			merges:       splitMulti(f[6]),
		}
	}
	return idx
}

// branchShas — 한 브랜치의 커밋 sha(9자). 참조: gilweb._branch_shas.
func branchShas(br string) []string {
	var shas []string
	for _, s := range strings.Fields(git("log", "--format=%H", br, "--")) { // "--": br 을 revision 으로 확정
		shas = append(shas, first9(s))
	}
	return shas
}

// chainAgg — chains_from_graph의 값.
type chainAgg struct {
	parents []string
	mode    string
	status  string
	cycles  int
	subject string
}

// chainsFromGraph — 커밋 그래프에서 체인 단위 집계. 참조: gilweb.chains_from_graph.
// 순서 보존을 위해 (map, 순서 슬라이스)를 함께 반환한다(Go map은 무순서, Python dict는 삽입순).
func chainsFromGraph() (map[string]chainAgg, []string) {
	idx := commitIndex()
	allNodes := collectNodes("--branches")
	chains := map[string]chainAgg{}
	var order []string
	for _, br := range branches() {
		shas := branchShas(br)
		var chainName string
		if len(shas) > 0 {
			if h, ok := idx[shas[0]]; ok {
				chainName = h.chain
			}
		}
		var root *chainAgg
		closed := false
		for _, sha := range shas {
			info, ok := idx[sha]
			if !ok {
				continue
			}
			if (info.kind == "init" || info.kind == "chain-root") && info.chain == chainName && root == nil {
				parents := info.cycleParents
				if len(parents) == 0 {
					parents = info.merges
				}
				mode := info.mode
				if mode == "" {
					mode = "autonomous"
				}
				root = &chainAgg{parents: parents, mode: mode, status: info.kind, subject: info.subject}
			}
			if info.kind == "chain-close" && info.chain == chainName {
				closed = true
			}
		}
		if chainName == "" || root == nil {
			continue
		}
		brShas := map[string]bool{}
		for _, s := range shas {
			brShas[s] = true
		}
		cyc := map[string]bool{}
		for _, n := range allNodes {
			if n.chain == chainName && n.cycle != "" && brShas[n.sha] {
				cyc[n.cycle] = true
			}
		}
		status := "open"
		if root.status == "init" {
			status = "init"
		} else if closed {
			status = "closed"
		}
		if _, seen := chains[chainName]; !seen {
			order = append(order, chainName)
		}
		chains[chainName] = chainAgg{
			parents: root.parents, mode: root.mode, status: status,
			cycles: len(cyc), subject: root.subject,
		}
	}
	sort.Strings(order) // 참조는 브랜치 순회순이나, 결정성을 위해 정렬(핸드오프 계보 목록)
	return chains, order
}

// cycleAgg — cycles_of의 값.
type cycleAgg struct {
	parents []string
	status  string
	steps   []node
}

// cyclesOf — 한 체인 안의 사이클 집계. 참조: gilweb.cycles_of.
func cyclesOf(chain string) (map[string]*cycleAgg, []string) {
	cyc := map[string]*cycleAgg{}
	var order []string
	// 체인 이름을 git ref(git log <chain>)로 쓰지 않는다 — 체인 이름이 브랜치 이름과
	// 다르거나 브랜치가 아직 없으면(격리 저장소·orphan) git log가 실패해 사이클을 통째로
	// 놓친다(handoff가 pending을 못 띄우던 결함). 전체 그래프(--branches)에서 chain으로
	// 필터링해 ref 존재에 의존하지 않는다.
	nodes := collectNodes("--branches")
	for i := len(nodes) - 1; i >= 0; i-- { // old→new
		n := nodes[i]
		if n.chain != chain || n.cycle == "" {
			continue
		}
		c, ok := cyc[n.cycle]
		if !ok {
			c = &cycleAgg{}
			cyc[n.cycle] = c
			order = append(order, n.cycle)
		}
		c.steps = append(c.steps, n)
		for _, p := range n.cycleParents {
			if p != chain && !contains(c.parents, p) {
				c.parents = append(c.parents, p)
			}
		}
	}
	for _, c := range cyc {
		hasSuccess, hasFail, hasPending := false, false, false
		for _, s := range c.steps {
			if s.kind == "analyze" && s.outcome == "success" {
				hasSuccess = true
			}
			if s.kind == "analyze" && s.outcome == "fail" {
				hasFail = true
			}
			if s.kind == "pending" {
				hasPending = true
			}
		}
		switch {
		case hasSuccess:
			c.status = "solved"
		case hasFail:
			c.status = "dead"
		case hasPending:
			c.status = "pending"
		default:
			c.status = "in_progress"
		}
	}
	return cyc, order
}

// ── 작은 헬퍼 ──

func cut(s, sep string) (before, after string, found bool) {
	if i := strings.Index(s, sep); i >= 0 {
		return s[:i], s[i+len(sep):], true
	}
	return s, "", false
}

func contains(xs []string, v string) bool {
	for _, x := range xs {
		if x == v {
			return true
		}
	}
	return false
}
