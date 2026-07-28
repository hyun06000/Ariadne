// goto.go — gil goto: 사고 나무 안에서 **자리를 옮긴다** (이슈 #67 제안 2).
//
// 왜 있는가. 형제 가지가 여럿인 사이클에서 gil 에는 가지 사이를 오가는 길이 없었다. 죽은
// 가지 끝에 서 있으면 --to·--falsify-to 가 산 가지의 analyze 를 "조상이 아니다"로 거부하고,
// 거부만 있고 나갈 길이 없으니 갇힌다. 실사용에서 정확히 그렇게 멈췄다(체인 adopt-v1 /
// 사이클 gap: 죽은 가지 s4b1 에 서서 산 가지의 s23 으로 못 감).
//
// --at 복귀(#67 1차 수정)는 *새로 생기는* 갇힘을 막지만 *이미 갇힌 그래프의 탈출로*는
// 아니다. 탈출은 위치를 옮기는 1급 명령이어야 한다 — "gil 이 표면에 있는 한 gil 로
// 모든 걸 한다"는 규율 아래에서 git checkout 은 답이 아니다.
//
// goto 는 그래프를 **바꾸지 않는다**. 커밋도 브랜치도 만들지 않고 HEAD 만 옮긴다.
package main

import (
	"sort"
	"strings"
)

// cycleLeaves — 이 사이클에서 자식이 없는 스텝(각 가지의 끝). Gil-Parent 로 판정한다.
func cycleLeaves(nodes []node) []node {
	hasChild := map[string]bool{}
	for _, n := range nodes {
		if n.parent != "" {
			hasChild[n.parent] = true
		}
	}
	var leaves []node
	for _, n := range nodes {
		if !hasChild[n.step] {
			leaves = append(leaves, n)
		}
	}
	sort.Slice(leaves, func(i, j int) bool { return stepNum(leaves[i].step) > stepNum(leaves[j].step) })
	return leaves
}

// stepLabel — 사람·LLM 이 읽는 한 줄 표식.
func stepLabel(n node) string {
	s := n.step + " [" + n.kind
	if n.outcome != "" {
		s += "/" + n.outcome
	}
	s += "]"
	switch {
	case isDeadLeaf(n):
		s += " 죽은 잎"
	case isLiveLeaf(n):
		s += " 산 잎"
	}
	return s
}

// branchAt — 이 커밋을 정확히 가리키는 로컬 브랜치 이름(없으면 "").
func branchAt(sha string) string {
	refs := strings.TrimSpace(git("for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads/"))
	for _, ln := range strings.Split(refs, "\n") {
		name, s, ok := strings.Cut(strings.TrimSpace(ln), " ")
		if ok && strings.HasPrefix(strings.TrimSpace(s), sha) {
			return strings.TrimSpace(name)
		}
	}
	return ""
}

// elsewhereHint — 거부당한 스텝이 **형제 가지에 실재**하면 그 사실과 탈출로를 덧붙인다(#67).
//
// 왜: "조상이 아니다"는 참이지만 절반만 말한다. 그 스텝은 있다 — 다만 지금 서 있는 가지에서
// 안 보일 뿐이다. 그 절반을 말해주지 않으면, 사람은 오타를 의심하며 같은 거부를 반복한다
// (실사용 보고: 두 플래그를 번갈아 넣어보다 멈췄다). 거부에는 나갈 길이 붙어야 한다.
func elsewhereHint(chain, cycle, want string, visible []node) string {
	if want == "" {
		return ""
	}
	for _, s := range visible {
		if s.step == want {
			return "" // 보이는데 거부됐다면 사유는 위치가 아니라 kind 다 — 덧붙일 말이 없다
		}
	}
	for _, n := range cycleAnywhere(chain, cycle) {
		if n.step == want {
			return "\n  ⚠ " + want + " 는 실재한다 — 다만 **다른(형제) 가지**에 있어 지금 서 있는 자리에서는\n" +
				"    조상이 아니다: " + stepLabel(n) + " (" + n.sha + ")\n" +
				"    그 가지로 가서 이어라:  gil goto " + chain + "/" + cycle + "/" + want
		}
	}
	return ""
}

// deadBranchBanner — 지금 **죽은 가지 끝에 서 있다**는 사실을 handoff 최상단에서 알린다(#67).
//
// 갇힌 자는 갇혔다는 것조차 다음 명령이 거부당해야 알았다. 위치는 부활 정보의 첫 줄이어야
// 한다 — 어디에 서 있는지 모르면 왜 거부당하는지도 모른다.
func deadBranchBanner() []string {
	headSHA := first9(strings.TrimSpace(git("rev-parse", "HEAD")))
	if headSHA == "" {
		return nil
	}
	nodes := collectNodes("HEAD") // 새→old 순 — 첫 항목이 HEAD 가 선 커밋이다
	if len(nodes) == 0 || nodes[0].sha != headSHA || !isDeadLeaf(nodes[0]) {
		return nil
	}
	here := &nodes[0]
	L := []string{"── 현재 위치 (⚠ 죽은 가지) ──",
		"  너는 " + here.chain + "/" + here.cycle + "/" + stepLabel(*here) + " 에 서 있다 — 여기엔 이어 붙일 수 없다.",
	}
	if live := liveLeafOf(here.chain, here.cycle); live != "" {
		L = append(L, "  이 사이클의 산 잎은 "+live+" 다. 돌아가려면:  gil goto "+here.chain+"/"+here.cycle)
	} else {
		L = append(L, "  이 사이클엔 산 잎이 없다 — 조상 define/analyze 로 가서 새 가지를 판다:  gil goto "+
			here.chain+"/"+here.cycle+"/<조상 define|analyze>")
	}
	return append(L, "")
}

// liveLeafOf — 이 사이클에서 goto 가 택할 산 잎의 스텝 id(없으면 "").
func liveLeafOf(chain, cycle string) string {
	for _, l := range cycleLeaves(cycleAnywhere(chain, cycle)) {
		if !isDeadLeaf(l) {
			return stepLabel(l)
		}
	}
	return ""
}

// leavingUnterminated — 지금 서 있는 자리가 **종결 없이 떠나면 안 되는 잎**인가(이슈 #78).
//
// verify 직후가 가장 떠나기 쉬운 자리다: 측정이 끝나 결과를 아는 상태라 그 가지는 심리적으로
// 이미 "끝난 것"이 된다. 그런데 그래프엔 해석도 종결도 없다. gil 이 매번 "다음은 반드시
// analyze"라고 말해주는데도 떠났다는 보고 — **안내는 읽고 나서 잊고, 레일은 잊어도 막는다.**
// 반환: (막아야 할 노드, true).
func leavingUnterminated() (node, bool) {
	nodes := collectNodes("HEAD")
	if len(nodes) == 0 {
		return node{}, false
	}
	tip := nodes[0]
	head := first9(strings.TrimSpace(git("rev-parse", "HEAD")))
	if tip.sha != head {
		return node{}, false // HEAD 가 스텝 위가 아니다 — 떠날 잎이 없다
	}
	switch tip.kind {
	case "verify", "hypothesis", "define":
		return tip, true // 해석·종결이 아직 없다
	}
	return node{}, false
}

// unterminatedRefusal — 떠남을 막는 거부문. 길을 함께 준다(거부만 하고 길이 없으면 벽이다, #67).
func unterminatedRefusal(n node, alt string) string {
	ref := n.chain + "/" + n.cycle
	next := "analyze"
	if n.kind == "define" {
		next = "hypothesis"
	} else if n.kind == "hypothesis" {
		next = "verify"
	}
	return "거부: " + n.step + " [" + n.kind + "] 를 종결 없이 떠날 수 없다 — 해석과 종결이 남았다.\n" +
		"  · 이어가라:            gil step " + ref + " --kind " + next + " …\n" +
		"  · 이 가지를 접겠다면:  gil step " + ref + " --kind fail --at " + n.step + " --to <조상 define|analyze>\n" +
		"  · 그래도 떠나려면:     " + alt + "   (매달린 잎이 남는다 — fsck 가 위반으로 짚는다)\n" +
		"  verify 직후는 가장 떠나기 쉬운 자리다(결과를 이미 아니까). 그 자리가 그래프엔 비어 있다(#78)."
}

// cmdGoto — gil goto <chain>/<cycle>[/<step>].
func cmdGoto(args []string) {
	fs := newFlags("gil goto")
	// 미종결 잎을 두고 떠나는 것을 막되, 벽이 되지 않게 명시적 탈출구를 둔다(선언은 남는다).
	leaveOpen := fs.boolFlag("leave-open")
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil goto <chain>/<cycle>[/<step>]\n" +
			"  그 사이클의 산 잎(가장 큰 스텝 번호)으로, 또는 지정한 스텝 자리로 HEAD 를 옮긴다.\n" +
			"  그래프는 바뀌지 않는다 — 커밋도 브랜치도 만들지 않는다.")
	}
	parts := strings.Split(pos[0], "/")
	if len(parts) < 2 || parts[0] == "" || parts[1] == "" {
		die("거부: 대상은 <chain>/<cycle> 또는 <chain>/<cycle>/<step> 꼴이어야 한다 (받은 값: \"" + pos[0] + "\")")
	}
	chain, cycle := parts[0], parts[1]
	want := ""
	if len(parts) > 2 {
		want = parts[2]
	}
	if n, blocked := leavingUnterminated(); blocked && !*leaveOpen {
		die(unterminatedRefusal(n, "gil goto "+pos[0]+" --leave-open"))
	}
	nodes := cycleAnywhere(chain, cycle)
	if len(nodes) == 0 {
		die("거부: " + chain + "/" + cycle + " 없음 (그래프 전체에서 못 찾음) — gil log --all 로 확인하라")
	}

	var target node
	if want != "" {
		found := false
		for _, n := range nodes {
			if n.step == want {
				target, found = n, true
				break
			}
		}
		if !found {
			var ids []string
			for _, n := range nodes {
				ids = append(ids, n.step)
			}
			sort.Slice(ids, func(i, j int) bool { return stepNum(ids[i]) < stepNum(ids[j]) })
			die("거부: " + chain + "/" + cycle + " 에 스텝 \"" + want + "\" 없음\n" +
				"  이 사이클의 스텝: " + strings.Join(dedupe(ids), " "))
		}
	} else {
		leaves := cycleLeaves(nodes)
		for _, l := range leaves {
			if !isDeadLeaf(l) {
				target = l
				break
			}
		}
		if target.sha == "" {
			// 모든 가지가 죽었다 — 갈 산 잎이 없다는 사실 그대로 말하고, 재분기의 뿌리를 준다.
			var lines []string
			for _, l := range leaves {
				lines = append(lines, "    "+stepLabel(l))
			}
			var anchors []string
			for _, n := range nodes {
				if n.kind == "define" || n.kind == "analyze" {
					anchors = append(anchors, n.step)
				}
			}
			sort.Slice(anchors, func(i, j int) bool { return stepNum(anchors[i]) < stepNum(anchors[j]) })
			die("거부: " + chain + "/" + cycle + " 에 산 잎이 없다 — 모든 가지가 죽은 잎으로 끝났다:\n" +
				strings.Join(lines, "\n") + "\n" +
				"  재분기의 뿌리로 가라: gil goto " + chain + "/" + cycle + "/<" +
				strings.Join(dedupe(anchors), "|") + ">\n" +
				"  (거기서 gil step " + chain + "/" + cycle + " --kind hypothesis --to <그 자리> … 로 새 가지를 판다)")
		}
	}

	from := strings.TrimSpace(git("rev-parse", "--abbrev-ref", "HEAD"))
	dest := branchAt(target.sha)
	detached := dest == ""
	if detached {
		dest = target.sha // 그 자리를 가리키는 브랜치가 없으면 분리 체크아웃(계보만 맞으면 충분)
	}
	if _, err := gitTry("checkout", "-q", dest); err != nil {
		die("거부: 그 자리로 옮기지 못했다 — " + err.Error() + "\n" +
			"  작업트리에 저장 안 된 변경이 있으면 먼저 정리하라(gil 은 네 파일을 마음대로 버리지 않는다).")
	}

	println2("STATE 위치 이동: " + from + " → " + chain + "/" + cycle + "/" + stepLabel(target) + " (" + target.sha + ")")
	if detached {
		println2("  브랜치 없는 자리라 분리(detached) 체크아웃했다 — 여기서 스텝을 박으면 gil 이 가지를 만든다.")
	} else {
		println2("  가지: " + dest)
	}
	println2("  그래프는 바뀌지 않았다 — HEAD 만 옮겼다.")
	// 옮긴 자리에서 무엇이 가능한지까지 준다 — 위치만 옮겨놓고 침묵하면 다음 수를 또 헤맨다.
	switch {
	case isDeadLeaf(target):
		println2("NEXT 여기는 죽은 잎이다. 이어 붙일 수 없다 — 조상 define/analyze 에서 새 가지를 판다:")
		println2("  gil step " + chain + "/" + cycle + " --kind hypothesis --to <조상 define|analyze> --falsify … --falsify-to … --inherit <이 벽의 교훈>")
	case isLiveLeaf(target):
		println2("NEXT 여기는 산 잎이다 — 사이클을 닫거나(gil close " + chain + "/" + cycle + "), 여기서 이어간다.")
	default:
		println2("NEXT 여기는 진행 중인 자리다 — gil step " + chain + "/" + cycle + " --kind <다음 kind> 로 이어간다.")
	}
}

// dedupe — 정렬된 문자열 목록에서 중복 제거(형제 가지에 같은 번호가 있던 옛 그래프 대비).
func dedupe(in []string) []string {
	var out []string
	seen := map[string]bool{}
	for _, x := range in {
		if !seen[x] {
			seen[x] = true
			out = append(out, x)
		}
	}
	return out
}
