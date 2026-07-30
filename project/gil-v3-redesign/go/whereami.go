// whereami.go — **지금 어디에 서 있는가**를 매 스텝 다시 각인한다 (상현님).
//
// 왜. gil 의 묘미는 앞으로만 가려는 LLM 의 성질을 도구로 눌러, 교훈을 지고 **뒤로 돌아가
// 분기를 치게** 만드는 것이다. 그런데 지금까지 gil 의 매 스텝 출력은 전부 앞을 봤다 —
// 목적 · 다음 강제 kind · 다음 설계. 뒤를 보는 줄이 한 줄도 없었다.
//
// 되돌아갈 주소(--falsify-to)는 가설 시점에 심어지는데, gil 이 그걸 입 밖에 내는 건 verify 가
// 반증된 뒤다. 하필 그 순간은 실패를 인정하기 싫은 순간이다. **퇴로를 막다른 곳에서
// 알려주면 늦다** — 잘 되고 있을 때 미리, 반복해서 보여야 문턱이 낮아진다.
//
// 그래서 네 칸을 매번 같은 형식으로 준다: 어디 · 무엇을 어떤 근거로 · 무엇으로 판정되나 ·
// 어디로 물러설 수 있나. 그리고 이건 **출력 추가가 아니라 재배치**다 — 이 카드가 옛
// "◎ 체인 목적 / ◎ 이 가설이 다가서려는 몫" 되풀이를 흡수한다. 순증이면 안 읽히고,
// 안 읽히는 규율은 없는 규율이다(#85 에서 값을 치른 교훈).
package main

import (
	"sort"
	"strings"
)

// whereCard — 방금 선 자리(tip)의 위치 카드. 없으면 빈 슬라이스.
func whereCard(chain, cycle string, tip node) []string {
	all := cycleNodesOf(chain, cycle)
	byID := map[string]node{}
	for _, n := range all {
		byID[n.step] = n
	}

	L := []string{"┌ 지금 여기 ─────────────────────────────────────────"}
	L = append(L, "│ "+chain+"/"+cycle+"/"+tip.step+" "+tip.kind+spineNote(all, byID, tip))

	// 근거 — 이 가지가 무엇을 지고 무슨 설계로 여기 왔나. 가장 가까운 조상 hypothesis 가 답이다.
	if h, ok := nearestKindUp(byID, tip, "hypothesis"); ok {
		if h.inherit != "" {
			L = append(L, "│ 근거   물려받음: "+clip(h.inherit, 90))
		}
		if h.plan != "" {
			L = append(L, "│        고정한 설계: "+clip(h.plan, 90))
		}
		if h.advances != "" {
			L = append(L, "│        다가서려는 몫: "+clip(h.advances, 90))
		}
		// 판정 — 무엇이 관측되면 이 가설이 틀리나. verify 를 서기 **전에** 눈앞에 있어야 한다.
		if h.falsify != "" {
			mark := ""
			if tip.kind == "hypothesis" || tip.kind == "verify" {
				mark = "   ← 지금 이걸 재는 중이다"
			}
			L = append(L, "│ 판정   반증조건: "+clip(h.falsify, 80)+mark)
		}
	}

	// 퇴로 — 심어둔 자리와, 그 밖에 실제로 갈 수 있는 자리들. 문장이 아니라 붙여넣을 한 줄로.
	L = append(L, retreatLines(chain, cycle, all, byID, tip)...)

	// 이미 민 벽 — 개수와 한 줄 요약. 전문은 분기할 때(계보 브리핑).
	if walls := deadAttemptTitles(all); len(walls) > 0 {
		L = append(L, "│ 이미 민 벽 "+itoa(len(walls))+": "+clip(strings.Join(walls, " · "), 90))
	}
	return append(L, "└────────────────────────────────────────────────────")
}

// justCommitted — 방금 새긴 스텝 노드를 그래프에서 되찾는다(캐시는 커밋 시 무효화됐다).
func justCommitted(chain, cycle, step string) (node, bool) {
	for _, n := range cycleNodesOf(chain, cycle) {
		if n.step == step {
			return n, true
		}
	}
	return node{}, false
}

// cycleNodesOf — 이 사이클의 모든 스텝(형제 가지 포함), 번호 오름차순.
func cycleNodesOf(chain, cycle string) []node {
	var out []node
	for _, n := range graphNodes() {
		if n.chain == chain && n.cycle == cycle {
			out = append(out, n)
		}
	}
	sort.Slice(out, func(i, j int) bool { return stepNum(out[i].step) < stepNum(out[j].step) })
	return out
}

// nearestKindUp — 이 자리에서 조상 쪽으로 거슬러 가장 가까운 특정 kind 의 스텝.
func nearestKindUp(byID map[string]node, from node, kind string) (node, bool) {
	cur := from
	for hops := 0; hops < 64; hops++ {
		if cur.kind == kind {
			return cur, true
		}
		p, ok := byID[cur.parent]
		if !ok {
			return node{}, false
		}
		cur = p
	}
	return node{}, false
}

// spineNote — 지금 선 자리가 **척추인가 곁가지인가**. 곁가지에서 본류인 척 밀고 나가는 것이
// 정확히 이 정보의 부재다 — 몇 번째 시도인지 모르면 자기가 헤매는 줄도 모른다.
func spineNote(all []node, byID map[string]node, tip node) string {
	// 이 가지의 뿌리 = 조상 쪽으로 올라가다 만나는 첫 '분기점'(자식이 둘 이상인 스텝).
	kids := map[string]int{}
	for _, n := range all {
		if n.parent != "" && n.parent != "null" {
			kids[n.parent]++
		}
	}
	cur := tip
	for hops := 0; hops < 64; hops++ {
		p, ok := byID[cur.parent]
		if !ok {
			break
		}
		if kids[p.step] > 1 {
			// 이 분기점의 자식들 중 지금 가지가 몇 번째인가(생성 순 = 스텝 번호 순).
			var sibs []node
			for _, n := range all {
				if n.parent == p.step {
					sibs = append(sibs, n)
				}
			}
			sort.Slice(sibs, func(i, j int) bool { return stepNum(sibs[i].step) < stepNum(sibs[j].step) })
			for i, s := range sibs {
				if s.step == cur.step {
					return "   (곁가지 " + itoa(i+1) + "/" + itoa(len(sibs)) + " — " +
						p.step + " 에서 " + itoa(i+1) + "번째로 판 가지다)"
				}
			}
			break
		}
		cur = p
	}
	return "   (척추 — 이 사이클의 본류)"
}

// retreatLines — 퇴로 칸. 심어둔 자리(--falsify-to)를 먼저, 그 밖의 조상 define/analyze 를
// 다음에. 마지막 줄은 **그대로 붙여넣을 수 있는 명령**이다 — 문턱을 낮추는 건 설명이 아니다.
func retreatLines(chain, cycle string, all []node, byID map[string]node, tip node) []string {
	planted := ""
	if h, ok := nearestKindUp(byID, tip, "hypothesis"); ok {
		planted = h.falsifyTo
	}
	// 조상 쪽으로 거슬러 만나는 define·analyze 가 실제로 갈 수 있는 자리다.
	var anc []node
	cur := tip
	for hops := 0; hops < 64; hops++ {
		p, ok := byID[cur.parent]
		if !ok {
			break
		}
		if p.kind == "define" || p.kind == "analyze" {
			anc = append(anc, p)
		}
		cur = p
	}
	if planted == "" && len(anc) == 0 {
		return nil
	}
	var L []string
	if planted != "" {
		what := ""
		if n, ok := byID[planted]; ok {
			what = "(" + n.kind + ")"
		}
		L = append(L, "│ 퇴로   반증되면 → "+planted+what+"   [가설 세울 때 미리 심어둔 자리]")
	} else {
		L = append(L, "│ 퇴로")
	}
	var others []string
	for _, a := range anc {
		if a.step == planted {
			continue
		}
		others = append(others, a.step+"("+a.kind+")")
	}
	if len(others) > 0 {
		L = append(L, "│        그 밖에 물러설 수 있는 자리: "+strings.Join(others, " · "))
	}
	to := planted
	if to == "" && len(anc) > 0 {
		to = anc[0].step
	}
	L = append(L, "│        gil step "+chain+"/"+cycle+" --kind hypothesis --to "+to+
		" --inherit <이 벽의 교훈>")
	return L
}

// deadAttemptTitles — 접힌 시도들의 짧은 이름(카드용 한 줄 요약).
func deadAttemptTitles(all []node) []string {
	byID := map[string]node{}
	for _, n := range all {
		byID[n.step] = n
	}
	var out []string
	for _, end := range all {
		if !(end.outcome == "backtrack" || end.kind == "fail") {
			continue
		}
		name := end.step
		if h, ok := nearestKindUp(byID, end, "hypothesis"); ok {
			name = clip(stepHeadline(h), 28) + "(" + h.step + "→" + end.step + ")"
		}
		out = append(out, name)
	}
	return out
}

// clip — 카드 한 줄이 넘치지 않게. 자를 때는 잘랐다고 표시한다.
func clip(s string, n int) string {
	s = strings.TrimSpace(s)
	r := []rune(s)
	if len(r) <= n {
		return s
	}
	return string(r[:n]) + "…"
}
