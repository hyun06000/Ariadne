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

// verify 판정 (제안 1, AIL #1): 검증이 가설을 지지했나 반증했나. gil 이 산문이 아니라
// 구조로 알아야 success 의 문을 좁힐 수 있다. refuted 면 success 를 문법으로 거부한다.
var verdicts = map[string]bool{"supported": true, "refuted": true}

// 종결 스텝(상현님, 2026-07-24): 분석(analyze) 다음에 성공/실패/대기를 *별도 스텝*으로
// 커밋한다. success=산 잎, fail=죽은 잎, pending=사람 대기. 이 종결 스텝의 본문이
// 문제정의부터 누적된 보고서를 담는다. (하위호환: 옛 analyze --outcome success/fail/backtrack
// 도 각각 산/죽은 잎으로 계속 인정한다.)
func isLiveLeaf(n node) bool {
	return n.kind == "success" || (n.kind == "analyze" && n.outcome == "success")
}
// isLiveLeafKind — kind 만으로 판정하는 산 잎(이슈 #59·#60의 부착 가드용). analyze 는
// outcome 에 따라 갈리므로 여기 넣지 않는다 — analyze 는 이어갈 수 있는 자리다.
func isLiveLeafKind(kind string) bool { return kind == "success" }

func isDeadLeaf(n node) bool {
	return n.kind == "fail" ||
		(n.kind == "analyze" && (n.outcome == "backtrack" || n.outcome == "fail"))
}

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

// chainTrailer — 이 체인의 chain-root 에 실린 임의 트레일러 값(없으면 "").
func chainTrailer(chain, key string) string {
	fmt := trailer("Gil-Chain") + fsep + trailer(key) + sep
	out := gitlog("--format="+fmt, "--branches")
	for _, rec := range strings.Split(out, sep) {
		c, v, _ := cut(rec, fsep)
		if strings.TrimSpace(c) == chain && strings.TrimSpace(v) != "" {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

// chainHasReference — 이 체인의 chain-root 에 기준 문서(Gil-Reference)가 심겨 있나(이슈 #33).
// 사이클을 열 때 "이 체인엔 기준이 있으니 읽고 그에 비추어 정의·판정하라"를 안내하는 데 쓴다.
func chainHasReference(chain, revRange string) bool {
	fmt := trailer("Gil-Chain") + fsep + trailer("Gil-Reference") + sep
	out := gitlog("--format="+fmt, revRange)
	for _, rec := range strings.Split(out, sep) {
		c, r, _ := cut(rec, fsep)
		if strings.TrimSpace(c) == chain && strings.TrimSpace(r) == "true" {
			return true
		}
	}
	return false
}

// interviewState — 이 체인 인터뷰의 **지금** 상태: pending|done|none (이슈 #75).
//
// 왜 필요한가. 확정(done) 뒤에 다시 물을 수 있어야 한다 — 전제가 반증되면 기준은 낡는다.
// 그런데 옛 판정들은 "done 마커가 하나라도 있으면 done" 이었고, 그래서 **재인터뷰가 조용히
// 삼켜졌다**: 커밋은 그래프에 있는데 --status 는 옛 문서를 done 이라 답하고, 뷰어엔 폼이
// 안 뜨고, handoff 도 모른다. 상태는 **최신 마커**가 정한다.
func interviewState(chain string) string {
	if chainInterviewPending(chain, "--branches") { // latest-wins 판정(아래 함수가 그렇게 돈다)
		return "pending"
	}
	if chainReferenceApproved(chain, "--branches") {
		return "done"
	}
	return "none"
}

// chainReferenceApproved — 이 체인의 기준이 '사람이 승인한' 것인가(이슈 #33). 인터뷰 제출로
// 확정된 레퍼런스만(Gil-Interview:done) 인정한다 — LLM 이 gil chain --reference 로 자기가 쓴
// 기준은 인정하지 않는다(상현님: '됐다'는 판단이 LLM 자기확신이 아니라 사람 기준에 비추어야).
// 작업 사이클 open 의 게이트가 이걸 본다: 사람 승인 기준 없으면 인터뷰가 먼저다.
func chainReferenceApproved(chain, revRange string) bool {
	fmt := trailer("Gil-Chain") + fsep + trailer("Gil-Interview") + sep
	out := gitlog("--format="+fmt, revRange)
	for _, rec := range strings.Split(out, sep) {
		c, iv, _ := cut(rec, fsep)
		if strings.TrimSpace(c) == chain && strings.TrimSpace(iv) == "done" {
			return true
		}
	}
	return false
}

// chainReferenceText — 이 체인의 기준 문서(레퍼런스 트루스) 전문(이슈 #33). 회고를 요구할 때
// "무엇에 비추어 쓰라는 건지"를 그 자리에서 보여주려고 읽는다 — 기준을 다시 찾아 헤매게
// 하지 않는다. 인터뷰로 확정된 레퍼런스 커밋의 본문이 곧 기준이다.
func chainReferenceText(chain, revRange string) string {
	fmt := "%H" + fsep + trailer("Gil-Chain") + fsep + trailer("Gil-Reference") + sep
	out := gitlog("--format="+fmt, revRange)
	for _, rec := range strings.Split(out, sep) {
		parts := strings.SplitN(strings.TrimSpace(rec), fsep, 3)
		if len(parts) < 3 {
			continue
		}
		if strings.TrimSpace(parts[1]) != chain || strings.TrimSpace(parts[2]) != "true" {
			continue
		}
		body := stripTrailers(gitlog("-1", "--format=%B", parts[0]))
		if i := strings.Index(body, "── 기준 문서(레퍼런스 트루스) ──"); i >= 0 {
			body = strings.TrimSpace(body[i:])
		}
		return body
	}
	return ""
}

// chainSeed — 닫힌 체인이 남긴 '다음 체인의 시드'(Gil-Seed-Ref, 이슈 #33). 회고가 "다음엔
// 무엇을 물어야 하는가"를 남기면, 그게 다음 체인 인터뷰의 출발 재료가 된다. 시드는 기준을
// **대체하지 않는다** — 기준은 언제나 사람의 답이고, 시드는 그 물음을 짜는 재료다.
func chainSeed(revRange string) (chain, seed string) {
	fmt := "%H" + fsep + trailer("Gil-Chain") + fsep + trailer("Gil-Seed-Ref") + sep
	out := gitlog("--format="+fmt, revRange)
	for _, rec := range strings.Split(out, sep) {
		parts := strings.SplitN(strings.TrimSpace(rec), fsep, 3)
		if len(parts) < 3 || strings.TrimSpace(parts[2]) != "true" {
			continue
		}
		body := stripTrailers(gitlog("-1", "--format=%B", parts[0]))
		if i := strings.Index(body, "── 다음 체인의 시드 ──"); i >= 0 {
			return strings.TrimSpace(parts[1]), strings.TrimSpace(body[i:])
		}
	}
	return "", ""
}

// chainInterviewPending — 이 체인에 아직 사람 답을 못 받은 인터뷰(Gil-Interview:pending)가
// 있나(이슈 #33). done 마커가 있으면 해소된 것. LLM 이 인터뷰를 심어 사람에게 물어놓고, 답을
// 안 기다린 채 스스로 진행하는 걸 막는 데 쓴다 — 인터뷰=pending 통합(상현님). pending 이면
// 그 체인의 다음 스텝(open·재-interview)을 거부한다: 사람이 뷰어 폼으로 답할 때까지 잠긴다.
func chainInterviewPending(chain, revRange string) bool {
	fmt := trailer("Gil-Chain") + fsep + trailer("Gil-Interview") + sep
	out := gitlog("--format="+fmt, revRange)
	// new→old 순회: 이 체인의 가장 최근 Gil-Interview 상태가 pending 이면 잠김, done 이면 해소.
	for _, rec := range strings.Split(out, sep) {
		c, iv, _ := cut(rec, fsep)
		if strings.TrimSpace(c) != chain {
			continue
		}
		switch strings.TrimSpace(iv) {
		case "pending":
			return true
		case "done":
			return false
		}
	}
	return false
}

// cycleGoal — 이 사이클의 달성 판정 기준(Gil-Cycle-Goal, 이슈 #62). 없으면 "".
// purpose("무엇을 하려는가")와 다르다 — goal 은 "무엇이 되면 됐다고 할 것인가"다.
func cycleGoal(chain, cycle, revRange string) string {
	fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Cycle") + fsep +
		trailer("Gil-Cycle-Goal") + sep
	out := gitlog("--format="+fmtStr, revRange)
	for _, rec := range strings.Split(out, sep) {
		c, rest, _ := cut(rec, fsep)
		cy, g, _ := cut(rest, fsep)
		if strings.TrimSpace(c) == chain && strings.TrimSpace(cy) == cycle && strings.TrimSpace(g) != "" {
			return strings.TrimSpace(g)
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
	// 이 체인에 기준 문서(레퍼런스 트루스)가 있으면 읽고 그에 비추어 정의·판정하라(이슈 #33).
	// chain-root 커밋 본문에 전문이 있다 — 사이클의 define·가설·성패판정의 잣대.
	if chainHasReference(chain, "HEAD") {
		stderr("─ 이 체인엔 기준 문서(레퍼런스 트루스)가 있다 — 읽어라: gil log " + chain +
			" (chain-root 본문) 또는 뷰어 체인 카드. 이 사이클의 정의·가설·성패를 그 기준에 비추어라.")
	}
	if cycle != "" {
		pu := cyclePurposeStr
		if pu == "" {
			pu = cyclePurpose(chain, cycle, "HEAD")
		}
		if pu != "" {
			stderr("─ 사이클 [" + cycle + "] 목적: " + pu)
		}
		// 목표(이슈 #62): "무엇이 되면 됐다고 할 것인가". 매 스텝 이 자리에서 보여야
		// 판단이 자기확신이 아니라 선언에 매인다.
		if g := cycleGoal(chain, cycle, "--branches"); g != "" {
			stderr("─ 사이클 [" + cycle + "] 목표: " + g + "  (닫으려면 이 목표에 답해야 한다)")
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

// closedCycles — Gil-Kind: close 커밋으로 봉인된 사이클들의 (chain,cycle) 키 집합.
// fsck 가 "닫힌 사이클은 모든 잎이 종결(산/죽은/pending)이어야" 를 강제하는 데 쓴다.
func closedCycles(revRange string) map[string]bool {
	fmt := trailer("Gil-Chain") + fsep + trailer("Gil-Cycle") + fsep + trailer("Gil-Kind") + sep
	out := gitlog("--format="+fmt, revRange)
	set := map[string]bool{}
	for _, rec := range strings.Split(out, sep) {
		parts := strings.SplitN(rec, fsep, 3)
		if len(parts) < 3 {
			continue
		}
		ch, cy, kind := strings.TrimSpace(parts[0]), strings.TrimSpace(parts[1]), strings.TrimSpace(parts[2])
		if kind == "close" && ch != "" && cy != "" {
			set[ch+"\x01"+cy] = true
		}
	}
	return set
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
func fsck(nodes []node, chainsKnown map[string]bool, universe []node, closed map[string]bool) []string {
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
	// workingTips — 각 열린 사이클의 살아있는 팁(지금 작업 중인 자리). 매달린 잎 검사에서
	// 이것만 뺀다 — 진행 중인 팁이 미종결인 건 정상이고, 나머지 미종결 잎은 버려진 것이다.
	// 판정은 **스텝 번호**로 한다 — 커밋 위상 순서가 아니라. 형제 가지가 나면 git 위상 순서가
	// 뒤집혀(s5 가 s4 보다 먼저 나온다) 위상 기반 팁 판정이 엉뚱한 잎을 "작업 중"이라 부른다.
	// gil 은 스텝 id 를 단조 증가로 매기므로, 가장 큰 번호가 지금 서 있는 자리다.
	workingTips := map[string]bool{}
	{
		best := map[string]node{}
		for _, n := range universe {
			if n.cycle == "" || closed[n.chain+"\x01"+n.cycle] || isDeadLeaf(n) {
				continue
			}
			k := n.chain + "\x01" + n.cycle
			if b, ok := best[k]; !ok || stepNum(n.step) > stepNum(b.step) {
				best[k] = n
			}
		}
		for _, t := range best {
			workingTips[stepKey(t.chain, t.cycle, t.step)] = true
		}
	}
	hasChild := map[string]bool{}       // 부모로 참조된 스텝키 — 잎 판정용(전체 그래프 기준)
	defineCount := map[string]int{}     // (chain,cycle) -> define 스텝 수. 사이클당 1개여야.
	defineSteps := map[string][]string{} // (chain,cycle) -> define 스텝 id 들(위반 메시지용)

	for _, n := range universe {
		if n.chain != "" {
			chains[n.chain] = true
		}
		stepKeys[stepKey(n.chain, n.cycle, n.step)] = true
		if n.cycle != "" && n.kind == "define" && (n.parent == "" || n.parent == "null") {
			cycles[n.cycle] = n.chain
		}
		if n.cycle != "" && n.kind == "define" {
			ck := n.chain + "\x01" + n.cycle
			defineCount[ck]++
			defineSteps[ck] = append(defineSteps[ck], n.step)
		}
		if p := n.parent; p != "" && p != "null" {
			hasChild[stepKey(n.chain, n.cycle, p)] = true
		}
	}

	dupDefineReported := map[string]bool{} // 사이클당 한 번만 보고
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
		// 1b. define 은 사이클의 뿌리 하나뿐(상현님). 첫 정의가 못 다룬 부분은 새 define 이
		//     아니라 다른 스텝·새 사이클로 이어간다. 여럿이면 "어느 게 진짜 문제 정의?"가 흐려진다.
		if ck := n.chain + "\x01" + n.cycle; n.cycle != "" && defineCount[ck] > 1 && !dupDefineReported[ck] {
			dupDefineReported[ck] = true
			violations = append(violations, "위계: "+n.chain+"/"+n.cycle+" — define 이 "+
				itoa(defineCount[ck])+"개 ("+strings.Join(defineSteps[ck], ",")+
				"). 사이클엔 문제 정의 하나(s1)만 — 나머지는 다른 kind나 새 사이클로 이어가라")
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
		// 5. analyze --outcome 은 주어졌으면 유효값이어야(생략은 허용 — 종결은 success/fail 스텝).
		if n.kind == "analyze" && n.outcome != "" && !outcomes[n.outcome] {
			violations = append(violations, "스텝순환: "+cc+" — analyze --outcome 은 success|backtrack|fail")
		}
		// 죽은 잎(backtrack outcome 또는 fail 종결 스텝)은 되돌아갈 곳(Gil-Backtrack)이 있어야.
		if (n.outcome == "backtrack" || n.kind == "fail") && n.backtrack == "" {
			violations = append(violations, "스텝순환: "+cc+" — 죽은 잎(backtrack/fail)은 Gil-Backtrack (조상 define|analyze) 필요")
		}
		// 5b. 미종결 매달린 잎 — 닫힌 사이클에서 잎(자식 없는 스텝)은 반드시 종결이어야
		//     (산 잎 success / 죽은 잎 fail·backtrack / pending). analyze·verify·hypothesis·
		//     define 로 매달려 끝나면 안 된다(상현님 실사용: analyze 뒤 종결 노드 없음).
		//     열린 사이클의 잎은 진행 중일 수 있어 검사에서 뺀다.
		if n.cycle != "" && closed[n.chain+"\x01"+n.cycle] &&
			!hasChild[stepKey(n.chain, n.cycle, n.step)] &&
			!isLiveLeaf(n) && !isDeadLeaf(n) && n.kind != "pending" {
			violations = append(violations, "스텝순환: "+cc+" — 미종결 잎 (kind="+n.kind+
				"). 닫힌 사이클의 잎은 success/fail/pending 으로 마감돼야 (analyze 로 끝내지 말 것)")
		}
		// 5c. 매달린 미종결 잎 — 열린 사이클에서도(이슈 #59, 상현님 실사용).
		//     옛 검사는 닫힌 사이클만 봤다. 그런데 실제 사고는 열린 사이클에서 났다: refuted 로
		//     죽은 가지에 fail 을 못 붙인 채 HEAD 가 재분기로 떠나버렸고, 그 뒤 열 몇 스텝을 더
		//     진행하는 동안 fsck 는 한 줄도 보고하지 않았다(help 는 "미종결 잎"을 검사한다고
		//     적어놓고서). append-only 라 나중에 알아채도 그 자리에 못 박는다 — 그러니 **지금**
		//     보여야 한다. 기준: 자식 없는 비종결 잎인데 이 사이클의 살아있는 팁도 아니다
		//     = HEAD 가 떠나 매달린 것. (현재 작업 중인 팁 하나는 당연히 미종결이라 제외한다.)
		if n.cycle != "" && !closed[n.chain+"\x01"+n.cycle] &&
			!hasChild[stepKey(n.chain, n.cycle, n.step)] &&
			!isLiveLeaf(n) && !isDeadLeaf(n) && n.kind != "pending" &&
			!workingTips[stepKey(n.chain, n.cycle, n.step)] {
			violations = append(violations, "스텝순환: "+cc+" — 매달린 미종결 잎 (kind="+n.kind+
				"). 이 가지는 종결 없이 버려졌다 — HEAD 는 딴 데로 갔다.\n"+
				"    그 자리에 종결을 박아라: gil step "+n.chain+"/"+n.cycle+
				" --kind fail --at "+n.step+" --to <조상 define> --title <왜 막혔나>")
		}
		// (체인 루트 적층 검사는 노드 루프 밖에서 한 번 — 아래 fsckChainStacking)

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
		// 6b. 소급 반증 간선 무결성(AIL #1 B) — Gil-Refutes 대상은 <chain>/<cycle>/<step> 스텝이
		//     실재해야 한다. (닫힘·verify·supported 조건은 open/step 시점에 강제됐고, 여기선
		//     dangling 만 잡는다 — Gil-Cycle-Parent 참조검사와 동형. 과거를 fail 로 바꾸라곤 안 한다.)
		for _, rf := range n.refutes {
			p := strings.Split(rf, "/")
			if len(p) != 3 || !stepKeys[stepKey(p[0], p[1], p[2])] {
				violations = append(violations, "계보: "+cc+" — 소급 반증 대상 \""+rf+"\" 실재 안 함 (dangling refutes)")
			}
		}
		// 6c. 스텝 정정 간선 무결성(AIL #12) — Gil-Supersedes 대상은 같은 사이클의 스텝으로 실재해야
		//     한다. (같은-kind·비종결 조건은 step 시점에 강제됐고, 여기선 dangling 만 잡는다.)
		if n.supersedes != "" && !stepKeys[stepKey(n.chain, n.cycle, n.supersedes)] {
			violations = append(violations, "계보: "+cc+" — 정정 대상 \""+n.supersedes+"\" 실재 안 함 (dangling supersedes)")
		}
	}
	// 스텝 번호 중복(이슈 #67 수정 중 발견): 같은 사이클에 같은 id 가 둘이면 --to·Gil-Parent
	// 참조가 어느 쪽을 가리키는지 알 수 없다. 형제 가지가 있을 때 HEAD 계보만 보고 번호를
	// 매기면 실제로 발생한다 — 문법으로 막았지만, 이미 그렇게 그려진 그래프는 여기서 짚는다.
	// (번호 중복은 fsckStepIdentity 가 **묶어서** 한 줄로 짚는다 — 쌍마다 한 줄씩 내면
	//  오염된 저장소에서 수십 줄이 되어 정작 다른 위반을 덮는다. 이슈 #84 에서 실측.)
	violations = append(violations, fsckChainStacking()...)
	violations = append(violations, fsckMigratedBodies()...)
	violations = append(violations, fsckMemoryLayer(nodes)...)
	violations = append(violations, fsckUnanchoredSteps()...)
	violations = append(violations, fsckStepIdentity(universe)...)
	return violations
}

// fsckMigratedBodies — 이주분 스텝의 **본문이 비었는지**를 짚는다(이슈 #87, 실사용 보고).
//
// 왜. fsck 는 형태(계보·위계·잎)를 검사하고 **본문의 존재는 검사하지 않았다.** 그래서
// 뼈대만 선 이주 그래프가 "위반 0 — 건강"으로 나왔고, 실사용 레포는 그걸 두 세션 동안
// 정본으로 취급했다. 회고를 쓰려다 그래프에 쓸 게 없어서야 발각됐다. 형태가 건강한 것과
// 내용이 있는 것은 다른 질문인데, 도구가 하나만 묻고 둘 다 답한 척했다.
//
// 범위를 **이주분(Gil-Migrate)** 으로 좁힌다: 손으로 쓴 스텝의 얇은 본문은 커밋 시점에
// 이미 경고하고 있고(bodyThin), 여기서까지 위반으로 올리면 정작 이 침묵이 묻힌다.
func fsckMigratedBodies() []string {
	out := gitlog("--format=%H"+fsep+trailer("Gil-Chain")+fsep+trailer("Gil-Cycle")+fsep+
		trailer("Gil-Step")+fsep+trailer("Gil-Migrate")+fsep+"%b"+sep, "--branches", "--")
	var v []string
	for _, rec := range strings.Split(out, sep) {
		rec = strings.Trim(rec, "\n")
		if rec == "" {
			continue
		}
		f := strings.Split(rec, fsep)
		if len(f) < 6 || strings.TrimSpace(f[4]) != "step" && strings.TrimSpace(f[4]) != "cycle" {
			continue // 이주 스텝만 본다
		}
		if strings.TrimSpace(f[3]) == "" {
			continue
		}
		// 원문이 없다고 **스스로 밝힌** 본문은 위반이 아니다. 위반은 "없는데 있다고 적은 것"
		// 이다 — 이 이슈의 병은 손실이 아니라 손실을 감춘 문구였다.
		if strings.Contains(f[5], "v2 원문 없음") {
			continue
		}
		if migratedProse(f[5]) == 0 {
			v = append(v, "이주본문: "+strings.TrimSpace(f[1])+"/"+strings.TrimSpace(f[2])+"/"+
				strings.TrimSpace(f[3])+" — 실질 본문 0 (v2 메타 표뿐, 원문이 안 실렸다). "+
				"원문은 v2 ref 에 남아 있다 — 다시 이주하라(gil migrate --from <v2-ref> --prefix …)")
		}
	}
	return v
}

// migratedProse — 이주 본문에서 **산문만** 센다: 표(|…)·인용(>)·트레일러·머리말을 걷어낸 뒤
// 남는 글자 수. 표만 있는 본문은 0 이 된다.
func migratedProse(body string) int {
	n := 0
	for _, ln := range strings.Split(body, "\n") {
		t := strings.TrimSpace(ln)
		switch {
		case t == "" || t == "---":
		case strings.HasPrefix(t, "|"), strings.HasPrefix(t, ">"), strings.HasPrefix(t, "[migrate]"):
		case isTrailerLine(t):
		default:
			n += len([]rune(t))
		}
	}
	return n
}

// isTrailerLine — "Gil-Xxx: 값" 꼴인가(본문 끝의 트레일러 블록을 산문으로 세지 않기 위해).
func isTrailerLine(t string) bool {
	k, _, ok := cut(t, ":")
	if !ok || strings.Contains(k, " ") {
		return false
	}
	return strings.HasPrefix(k, "Gil-")
}

// fsckStepIdentity — 번호 중복과 자기부모를 짚는다(이슈 #84, 상현님).
//
// 왜. 옛 gil(≤3.28)은 스텝 번호를 브랜치에서 계산해, 분리된 HEAD 위에서는 같은 번호를 여러
// 스텝에 찍었다(#83 의 곁다리). 그 저장소는 겉보기엔 멀쩡한데 뷰어가 사이클을 못 연다 —
// 같은 번호끼리 충돌해 **자기 자신이 부모인 노드**가 생기고 배치가 무한재귀에 빠진다.
// 진짜 손해는 크래시가 아니라 **오염된 걸 아무도 안 알려준 것**이었다("v3.24.0 구간 5개
// 사이클이 오염된 걸 이슈를 읽고서야 알았다"). 뷰어가 못 그리는 데이터를 fsck 가 먼저 짚는다.
//
// 고칠 수는 없다 — 번호를 다시 매기는 건 원장을 다시 쓰는 것이고, 그건 이력 위조다. 그래서
// 도구가 하는 일은 둘이다: 사실을 말하고(여기), 오염을 견디고(뷰어는 sha 를 정체성으로 쓴다).
func fsckStepIdentity(nodes []node) []string {
	type key struct{ chain, cycle, step string }
	count := map[key][]node{}
	var selfParent []node
	for _, n := range nodes {
		if n.cycle == "" || n.step == "" {
			continue
		}
		k := key{n.chain, n.cycle, n.step}
		count[k] = append(count[k], n)
		if n.parent == n.step {
			selfParent = append(selfParent, n)
		}
	}
	var dupLines []string
	for k, ns := range count {
		if len(ns) < 2 {
			continue
		}
		var shas []string
		for _, n := range ns {
			shas = append(shas, n.sha+"("+n.kind+")")
		}
		sort.Strings(shas)
		dupLines = append(dupLines, "    "+k.chain+"/"+k.cycle+"/"+k.step+" ×"+itoa(len(ns))+": "+strings.Join(shas, " "))
	}
	var out []string
	if len(dupLines) > 0 {
		sort.Strings(dupLines)
		out = append(out, "번호 중복: 같은 스텝 번호를 쓰는 커밋이 여럿이다(옛 gil ≤3.28 이 찍은 구간):\n"+
			strings.Join(dupLines, "\n")+"\n"+
			"    다시 번호를 매기지 않는다 — 원장을 고치는 건 이력 위조다. 뷰어는 커밋 sha 를 정체성으로\n"+
			"    삼아 이 구간도 그대로 그린다(이슈 #84). 새 스텝부터는 번호가 다시 단조 증가한다.")
	}
	if len(selfParent) > 0 {
		var lines []string
		for _, n := range selfParent {
			lines = append(lines, "    "+n.sha+" "+n.chain+"/"+n.cycle+"/"+n.step+" ["+n.kind+"] — 부모가 자기 자신")
		}
		sort.Strings(lines)
		out = append(out, "자기부모: 스텝이 자기 자신을 부모로 가리킨다(번호 중복의 후유증):\n"+
			strings.Join(lines, "\n")+"\n"+
			"    계보를 따라가면 제자리를 돈다. 뷰어는 순환 가드로 견디지만, 이 구간의 부모 관계는\n"+
			"    믿을 수 없다 — 그 자리의 계보는 커밋 그래프(gil log --depth step)로 읽어라.")
	}
	return out
}

// fsckUnanchoredSteps — 브랜치에서 안 닿는 스텝 커밋을 짚는다(이슈 #83 부수 제안).
//
// 두 종류를 본다. (1) HEAD 계보에는 있는데 어떤 브랜치에도 없는 스텝 — 분리된 HEAD 위에
// 쌓인 것으로, 다음 checkout 한 번에 통째로 손이 닿지 않는 곳으로 간다. (2) 이미 어디에서도
// 안 닿는 스텝 — GC 가 지우기 전의 마지막 신호다. 지금의 gil 은 커밋마다 닻을 내리지만
// (anchorHead), 옛 버전이 만든 저장소와 사람이 손으로 reset 한 자리는 여기서만 드러난다.
// 사람이 뷰어가 이상해 보일 때에야 알아차리던 것을 도구가 먼저 말한다.
func fsckUnanchoredSteps() []string {
	inBranch := map[string]bool{}
	for _, n := range collectNodes("--branches") {
		inBranch[n.sha] = true
	}
	var out []string
	var loose []node
	for _, n := range collectNodes("HEAD") {
		if !inBranch[n.sha] {
			loose = append(loose, n)
		}
	}
	if len(loose) > 0 {
		var lines []string
		for _, n := range loose {
			lines = append(lines, "    "+n.sha+" "+n.chain+"/"+n.cycle+"/"+n.step+" "+n.kind)
		}
		sort.Strings(lines)
		out = append(out, "닻 없음: 스텝 커밋 "+itoa(len(loose))+"개가 분리된 HEAD 에만 있다 — 어떤 브랜치도 이들을 가리키지 않는다:\n"+
			strings.Join(lines, "\n")+"\n"+
			"    지금 고정하라: git branch "+cycleBranch(loose[0].chain, loose[0].cycle)+"-rescue HEAD\n"+
			"    (gil 은 커밋마다 닻을 내린다 — 이 상태는 옛 버전이나 손으로 한 checkout 이 남긴 것이다)")
	}
	// 이미 어디에서도 안 닿는 스텝(dangling). fsck 가 실패하면 조용히 넘어간다 — 이 검사
	// 하나 때문에 나머지 진단을 잃지 않는다.
	if raw, err := gitTry("fsck", "--unreachable", "--no-reflogs", "--no-progress"); err == nil {
		var lost []string
		for _, ln := range strings.Split(raw, "\n") {
			f := strings.Fields(strings.TrimSpace(ln))
			if len(f) != 3 || f[0] != "unreachable" || f[1] != "commit" {
				continue
			}
			rec := strings.TrimSpace(gitlog("-1", "--format="+trailer("Gil-Chain")+fsep+trailer("Gil-Cycle")+fsep+trailer("Gil-Step")+fsep+trailer("Gil-Kind"), f[2], "--"))
			ch, rest, _ := cut(rec, fsep)
			cy, rest2, _ := cut(rest, fsep)
			st, kd, _ := cut(rest2, fsep)
			if strings.TrimSpace(st) == "" {
				continue // gil 스텝이 아니다 — 평범한 커밋의 잔해는 gil 이 말할 일이 아니다
			}
			lost = append(lost, "    "+first9(f[2])+" "+strings.TrimSpace(ch)+"/"+strings.TrimSpace(cy)+"/"+strings.TrimSpace(st)+" "+strings.TrimSpace(kd))
		}
		if len(lost) > 0 {
			sort.Strings(lost)
			out = append(out, "유실 직전: 스텝 커밋 "+itoa(len(lost))+"개가 어디에서도 안 닿는다(GC 대상):\n"+
				strings.Join(lost, "\n")+"\n"+
				"    건지려면 각각: git branch rescue-<이름> <sha>  (지운 뒤에는 되돌릴 수 없다)")
		}
	}
	return out
}

// fsckMemoryLayer — 기억 계층(refs/gil/global)이 통째로 빈 저장소를 짚는다(이슈 #69).
//
// 그래프 건강과는 다른 축이다. 그래도 fsck 가 맡는다: migrate 로만 온 저장소는 그래프가
// 완벽히 건강한 채 존재·기억이 통째로 없고, 그 사실을 알려주는 자리가 어디에도 없었다.
// 사이클을 쌓기 시작한 저장소에서만 짚는다 — 아직 아무 사고도 없는 빈 저장소에 위반을
// 띄우면 gil init 전의 정상 상태를 결함으로 부르게 된다.
func fsckMemoryLayer(nodes []node) []string {
	if globalExists() || len(nodes) == 0 {
		return nil
	}
	return []string{"기억계층: " + globalRef + " 없음 — 존재의 방·기억이 통째로 비었다. " +
		"세워라: gil init --name <이름> (커밋이 있으면 대문은 건드리지 않는다)"}
}

// chainLatestCommit — 이 체인 소속(Gil-Chain) 커밋 중 가장 최근 것의 sha(이슈 #66).
// 체인의 진짜 끝은 체인 브랜치 ref 가 아니라 그 체인이 마지막으로 자란 자리(사이클 가지)다 —
// chain-close 는 거기에 얹혀야 봉인이 계보의 끝이 된다.
func chainLatestCommit(chain string) string {
	// 커밋 위상·시간 순서에 기대지 않는다 — 형제 가지가 있으면 그 순서가 뒤집히고(이슈 #59
	// 에서 같은 함정을 밟았다), 테스트처럼 타임스탬프가 같으면 아예 무의미하다. 대신 이 체인
	// 소속 ref(<chain>, <chain>-*) 중 **가장 깊은 팁**을 고른다 — 사이클이 부모 사이클 위에
	// 자라므로(이슈 #61) 그 팁이 이 체인의 계보를 담는다.
	out, err := gitTry("for-each-ref", "--format=%(refname:short)", "refs/heads/")
	if err != nil {
		return ""
	}
	best, bestN := "", -1
	for _, ref := range strings.Fields(out) {
		if ref != chain && !strings.HasPrefix(ref, chain+"-") {
			continue
		}
		cnt, err := gitTry("rev-list", "--count", ref)
		if err != nil {
			continue
		}
		n := 0
		for _, c := range strings.TrimSpace(cnt) {
			if c < '0' || c > '9' {
				n = -1
				break
			}
			n = n*10 + int(c-'0')
		}
		if n > bestN {
			best, bestN = ref, n
		}
	}
	if best == "" {
		return ""
	}
	return strings.TrimSpace(git("rev-parse", best))
}

// openChains — 아직 chain-close 를 받지 않은 체인들(init 대문 제외). 이름순.
// 새 체인을 열 때 "이어받음인가 병렬인가"를 사람에게 묻는 근거다(이슈 #54).
func openChains() []string {
	fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Kind") + sep
	roots := map[string]bool{}
	closed := map[string]bool{}
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches"), sep) {
		ch, kind, _ := cut(rec, fsep)
		c, k := strings.TrimSpace(ch), strings.TrimSpace(kind)
		if c == "" {
			continue
		}
		switch k {
		case "chain-root":
			roots[c] = true
		case "chain-close":
			closed[c] = true
		}
	}
	var out []string
	for c := range roots {
		if !closed[c] {
			out = append(out, c)
		}
	}
	sort.Strings(out)
	return out
}

// chainRootParent — 그 체인의 chain-root 커밋의 첫 부모(= 그 체인이 갈라져 나온 자리).
// 병렬 체인을 **같은 자리**에서 내기 위해 쓴다(이슈 #54) — 뒤에 열렸다는 이유로 앞 체인의
// 자손이 되면, 커밋 그래프가 선언과 반대되는 말을 한다.
func chainRootParent(chain string) string {
	fmtStr := "%H" + fsep + trailer("Gil-Chain") + fsep + trailer("Gil-Kind") + sep
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches"), sep) {
		sha, rest, _ := cut(strings.TrimSpace(rec), fsep)
		ch, kind, _ := cut(rest, fsep)
		if strings.TrimSpace(ch) == chain && strings.TrimSpace(kind) == "chain-root" {
			root := strings.TrimSpace(sha)
			// 부모가 없을 수 있다 — 그 체인의 루트가 저장소의 첫 커밋인 경우(git 은 여기서
			// 죽으므로 gitTry 로 받는다). 그때는 그 루트 자체를 시작점으로 준다: 진짜 형제는
			// 못 되지만, 적어도 그 체인이 **그 뒤에 쌓은 작업 위에는** 얹히지 않는다.
			if p, err := gitTry("rev-parse", "--verify", "-q", root+"^"); err == nil {
				if v := strings.TrimSpace(p); v != "" {
					return v
				}
			}
			return root
		}
	}
	return ""
}

// fsckChainStacking — 체인 루트가 다른 체인의 커밋 위에 얹혀 있는데 그 체인이 닫히지 않은
// 경우를 보고한다(이슈 #65 제안 3).
//
// 왜 감추지 않고 보고하나. 전체맵은 커밋 조상관계를 날것으로 그리고, 체인 그래프는 "닫힌
// 끝에서 태어났을 때만 계승"(#53)이라는 엄격한 판정을 쓴다. 두 패널을 일치시키면 그 차이가
// 사라지는데 — 이 이상을 발견할 수 있었던 건 역설적으로 두 패널이 **달랐기 때문**이다.
// 그래서 그 신호를 여기로 옮긴다: 그래프는 일관되게 그리되, 이상은 fsck 가 말한다.
func fsckChainStacking() []string {
	parents := chainParents() // 진짜 계승(닫힌 끝에서 태어남)만 담긴 맵
	roots := map[string]string{}
	fmtStr := "%H" + fsep + trailer("Gil-Chain") + fsep + trailer("Gil-Kind") + sep
	for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches"), sep) {
		sha, rest, _ := cut(strings.TrimSpace(rec), fsep)
		ch, kind, _ := cut(rest, fsep)
		if strings.TrimSpace(kind) == "chain-root" && strings.TrimSpace(ch) != "" {
			roots[strings.TrimSpace(ch)] = strings.TrimSpace(sha)
		}
	}
	var names []string
	for ch := range roots {
		names = append(names, ch)
	}
	sort.Strings(names)
	var out []string
	declaredParallel := map[string]map[string]bool{} // 체인 → 선언된 병렬 상대들(이슈 #54)
	pf := trailer("Gil-Chain") + fsep + trailer("Gil-Parallel-With") + sep
	for _, rec := range strings.Split(gitlog("--format="+pf, "--branches"), sep) {
		ch, pw, _ := cut(rec, fsep)
		c, p := strings.TrimSpace(ch), strings.TrimSpace(pw)
		if c == "" || p == "" {
			continue
		}
		if declaredParallel[c] == nil {
			declaredParallel[c] = map[string]bool{}
		}
		declaredParallel[c][p] = true
	}
	for _, ch := range names {
		for _, other := range names {
			if ch == other || parents[ch] == other {
				continue // 자기 자신이거나, 이미 진짜 계승으로 인정된 관계
			}
			if declaredParallel[ch][other] || declaredParallel[other][ch] {
				continue // 사람이 병렬이라 선언했다 — 사고가 아니라 판단이다(이슈 #54)
			}
			if gitOK("merge-base", "--is-ancestor", roots[other], roots[ch]) {
				out = append(out, "계보: 체인 "+ch+" — 루트가 체인 "+other+
					" 위에 얹혀 있으나 계승이 아니다(그 체인은 닫힌 적 없다). 적층이다:\n"+
					"    커밋 조상관계는 '이어받음'을 뜻하지 않는다 — 그래프는 이 둘을 잇지 않는다.\n"+
					"    (이주 산물이면 최신 gil 로 다시 이주하라 — 체인 루트는 이주 시작점에서 갈라진다.)")
			}
		}
	}
	return out
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
	allNodes := graphNodes()
	// 봉인 집합은 **한 번만** 만든다. 브랜치마다 chainClosed 를 부르면 브랜치 수만큼 전체
	// 그래프를 다시 훑는다 — 130개 브랜치짜리 실사용 저장소에서 130번, 테스트가 3분에서
	// 14분으로 늘어 발각됐다(내가 #85 를 고치며 넣은 회귀). 판정은 하나여야 하지만,
	// 그 하나를 매번 다시 계산할 이유는 없다.
	closedSet := map[string]bool{}
	{
		fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Kind") + sep
		for _, rec := range strings.Split(gitlog("--format="+fmtStr, "--branches"), sep) {
			c, k, _ := cut(strings.TrimSpace(rec), fsep)
			if strings.TrimSpace(k) == "chain-close" {
				closedSet[strings.TrimSpace(c)] = true
			}
		}
	}
	chains := map[string]chainAgg{}
	var order []string
	for _, br := range branches() {
		shas := branchShas(br)
		// 이 브랜치가 어느 체인인가. **팁 하나만** 보면 안 된다(이슈 #74): 사이클·체인
		// 브랜치 끝에 gil 이 만들지 않은 평범한 커밋이 하나만 있어도 체인 이름을 못 읽어
		// 그 체인이 통째로 사라졌다 — 그리고 handoff 는 "열린 체인 없음 … 새 체인을 열 수
		// 있다"고 **적극적으로 잘못 안내했다**(중복 체인을 여는 방향). 평범한 커밋은 정당한
		// 작업이다. 팁부터 내려가며 처음 만나는 gil 커밋의 체인을 쓴다.
		var chainName string
		for _, sha := range shas {
			if h, ok := idx[sha]; ok && h.chain != "" {
				chainName = h.chain
				break
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
		// 사이클 수는 **그래프 전체**에서 센다(이슈 #63, 상현님 실사용).
		//
		// 옛 코드는 이 체인 브랜치 팁에서 도달 가능한 커밋(brShas)만 셌다. 그런데 사이클은
		// 각자 <chain>-<cycle> 브랜치에 살고 체인 팁으로 병합되지 않는다 — 그래서 병합 안 된
		// 사이클이 통째로 빠졌다(실측: 총 61개 중 28개 유실, 4개 체인은 실제로 사이클이 있는데
		// [사이클 0] 으로 나왔다). 한 바이너리 안에서 --depth chain 만 handoff·--depth cycle·
		// 뷰어와 다른 답을 냈다.
		//
		// --depth chain 은 계보를 조망하는 첫 화면이라, 여기서 "빈 껍데기"로 보이면 이미 있는
		// 작업을 못 보고 새로 판다 — 그래프를 보게 만든 이유(#55) 자체가 무너진다.
		cyc := map[string]bool{}
		for _, n := range allNodes {
			if n.chain == chainName && n.cycle != "" {
				cyc[n.cycle] = true
			}
		}
		// 봉인 판정은 **한 곳에서만** 나온다(이슈 #85, 상현님 실사용). 옛 코드는 이 브랜치가
		// 담은 커밋만 훑어 chain-close 를 찾았다. 그런데 한 체인은 브랜치 여럿(<chain>,
		// <chain>-<cycle>, 스텝 가지…)에 걸쳐 살고, 봉인 커밋은 그중 하나에만 있다. 그래서
		// 순회 순서에 따라 같은 체인이 (closed) 도 (open) 도 됐다 — 실측: 봉인 커밋이 체인
		// 브랜치에 있는데 (open) 인 체인 셋, 스텝 가지에만 있는데 (closed) 인 체인 하나.
		// "정리했는데 정리 안 된 것처럼 보인다"는 보고가 정확히 이것이었다.
		// chainClosed 는 chain-close·open 거부·handoff 가 이미 쓰는 판정이다 — 거기에 맞춘다.
		status := "open"
		if root.status == "init" {
			status = "init"
		} else if closed || closedSet[chainName] {
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

// liveTip — 사이클의 "살아있는 팁". 다중 브랜치(형제 가지)에서 죽은 잎(analyze/backtrack·
// analyze/fail)을 팁으로 잡던 결함 수정. 잎(다른 스텝의 부모로 안 쓰인 스텝) 중 죽은 잎이
// 아닌 마지막(가장 최근)을 고른다. 살아있는 잎이 없으면(전부 죽음) 마지막 스텝을 반환.
func (c *cycleAgg) liveTip() node {
	referenced := map[string]bool{}
	superseded := map[string]bool{}
	for _, s := range c.steps {
		if s.parent != "" && s.parent != "null" {
			referenced[s.parent] = true
		}
		// approve/reject 로 정정된 pending 은 Gil-Supersedes 로 대체되지 부모가 되지 않는다
		// (AIL #41) — 그래서 childless 로 남아 팁으로 오인되던 결함(이슈 #44). 정정된 스텝은
		// 팁이 아니다: 대체한 fail/success 가 진짜 종결이다.
		if s.supersedes != "" {
			superseded[s.supersedes] = true
		}
	}
	var best *node
	for i := range c.steps {
		s := c.steps[i]
		if referenced[s.step] || superseded[s.step] {
			continue // 잎 아님(자식이 있음) 또는 정정으로 대체됨
		}
		if isDeadLeaf(s) {
			continue // 죽은 잎은 팁 아님
		}
		best = &c.steps[i] // steps는 old→new, 뒤로 갈수록 최신 → 마지막 산 잎이 남는다
	}
	if best != nil {
		return *best
	}
	return c.steps[len(c.steps)-1] // 전부 죽었으면 마지막(벽)
}

// cyclesOf — 한 체인 안의 사이클 집계. 참조: gilweb.cycles_of.
func cyclesOf(chain string) (map[string]*cycleAgg, []string) {
	cyc := map[string]*cycleAgg{}
	var order []string
	// 체인 이름을 git ref(git log <chain>)로 쓰지 않는다 — 체인 이름이 브랜치 이름과
	// 다르거나 브랜치가 아직 없으면(격리 저장소·orphan) git log가 실패해 사이클을 통째로
	// 놓친다(handoff가 pending을 못 띄우던 결함). 전체 그래프(--branches)에서 chain으로
	// 필터링해 ref 존재에 의존하지 않는다.
	nodes := graphNodes()
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
		hasLive := false
		for _, s := range c.steps {
			if isLiveLeaf(s) {
				hasLive = true
			}
		}
		tip := c.liveTip()
		switch {
		case hasLive:
			c.status = "solved" // 산 잎이 하나라도 있으면 풀림
		case tip.kind == "pending":
			c.status = "pending" // 현재 팁이 대기(소비 후엔 팁이 아니므로 여기 안 걸림)
		case isDeadLeaf(tip):
			c.status = "dead" // 살아있는 팁 없고 마지막이 죽은 잎
		default:
			c.status = "in_progress"
		}
	}
	return cyc, order
}

// branchStats — 뎁스별 분기 수와 죽은 잎 수(AIL #2, clew@AIL). "안 보이는 건 안 짜인다":
// 체인·사이클·스텝 각 레벨에서 진짜 위상 분기가 몇인지, 죽은 잎(fail)이 몇인지 집계해
// gil log 가 일자 편향을 한눈에 드러내게 한다. 분기만 있고 죽은 잎 0이면 "형식만 분기,
// 실질은 일자"(예: --refutes 사후 링크) — 둘을 나란히 둬 진짜 분기와 사후 링크를 가른다.
type branchStats struct {
	chainBranch int // 자식 체인 2+ 를 가진 체인 수(체인 계보 분기)
	cycleBranch int // 자식 사이클 2+ 를 가진 사이클 수(사이클 계보 분기)
	stepBranch  int // 자식 스텝 2+ 를 가진 스텝 수(형제 가지 분기 — 진짜 위상 분기)
	deadLeaves  int // fail/analyze-fail/backtrack 죽은 잎 수(벽의 지도)
}

func computeBranchStats() branchStats {
	var bs branchStats
	// collectNodes("--branches")는 공유 커밋을 여러 브랜치에서 재출력할 수 있다(형제 가지의
	// 공통 조상 define 등) — sha 로 접어야 자식 수·죽은 잎이 부풀지 않는다(뷰어도 같은 dedup).
	seen := map[string]bool{}
	var nodes []node
	for _, n := range collectNodes("--branches") {
		if seen[n.sha] {
			continue
		}
		seen[n.sha] = true
		nodes = append(nodes, n)
	}

	// 스텝 분기: 같은 (chain,cycle) 안에서 한 스텝이 둘 이상의 자식 스텝의 부모인 경우.
	// (형제 hypothesis 가지 — 진짜 사고의 분기. --refutes 사후 링크는 여기 안 잡힘.)
	childSteps := map[string]map[string]bool{} // 부모키 → 자식 스텝 id 집합(중복 자식 제거)
	for _, n := range nodes {
		if n.parent != "" && n.parent != "null" {
			k := stepKey(n.chain, n.cycle, n.parent)
			if childSteps[k] == nil {
				childSteps[k] = map[string]bool{}
			}
			childSteps[k][n.step] = true
		}
		if isDeadLeaf(n) {
			bs.deadLeaves++
		}
	}
	for _, kids := range childSteps {
		if len(kids) >= 2 {
			bs.stepBranch++
		}
	}

	// 체인 분기: 한 체인을 부모로 선언한 자식 체인이 둘 이상. chainParents(): 체인→부모체인.
	chainChildren := map[string]int{}
	for _, parent := range chainParents() {
		if parent != "" {
			chainChildren[parent]++
		}
	}
	for _, c := range chainChildren {
		if c >= 2 {
			bs.chainBranch++
		}
	}

	// 사이클 분기: 한 사이클을 부모(Gil-Cycle-Parent)로 선언한 자식 사이클이 둘 이상.
	cycleChildren := map[string]int{}
	for _, n := range nodes {
		for _, p := range n.cycleParents {
			if p != n.chain { // 체인 참조 제외
				cycleChildren[n.chain+"\x01"+p]++
			}
		}
	}
	for _, c := range cycleChildren {
		if c >= 2 {
			bs.cycleBranch++
		}
	}
	return bs
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
