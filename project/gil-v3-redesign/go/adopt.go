// adopt.go — 경합의 승자를 채택한다 (이슈 #106 h · #107 2b, 실사용 보고).
//
// 병렬 형제 가설을 낼 수 있게 됐으면, **끝맺는 그림**도 있어야 한다. 실사용에서 세 축을
// 병렬로 돌린 세션은 승자를 정한 뒤 손으로 이 일들을 했다:
//
//   - 진 가지마다 fail 잎을 손수 박고(안 박으면 close 가 거부한다)
//   - 이긴 가지의 산출물을 `git checkout <형제브랜치> -- <경로>` 로 긁어 모으고
//   - "왜 이겼나"는 어디에도 안 남긴 채 다음으로 갔다
//
// 끝내는 동선이 안 그려지면 시작도 안 하게 된다 — 그래서 병렬이 7사이클 동안 0회였다.
// adopt 는 그 셋을 한 수로 만든다: **패자마다 벽을 남기고(승자를 가리키는 선과 함께),
// HEAD 를 승자 가지로 옮긴다.** 자산 통합은 브랜치를 옮기는 것으로 족하다 — 승자 가지가
// 곧 이 사이클이 이어갈 자리이고, 나중의 `gil merge <chain>/<cycle>` 이 거기서 합류한다.
//
// gil 은 누가 이겼는지 모른다. 그 판단은 사람·에이전트의 것이고, 도구는 **그 판단이
// 그래프에 남는지**만 보증한다 — 그래서 --reason 이 필수다.
package main

import (
	"sort"
	"strings"
)

func cmdAdopt(args []string) {
	fs := newFlags("gil adopt")
	over := fs.strList("over")   // 진 형제(스텝 id) — 생략하면 경합의 나머지 전부
	reason := fs.str("reason", "") // 왜 이 가지가 이겼나 — 비교의 근거
	pos := fs.parse(args)
	if len(pos) < 1 {
		die("사용: gil adopt <chain>/<cycle>/<승자스텝> --reason <왜 이 가지가 이겼나> [--over <진 형제> …]\n" +
			"  경합(--competing)으로 나란히 세운 형제 가설 중 하나를 채택한다:\n" +
			"    · 진 가지마다 벽(fail)을 남긴다 — 승자를 가리키는 선과 함께(Gil-Lost-To).\n" +
			"    · HEAD 를 승자 가지로 옮긴다 — 이 사이클은 거기서 이어간다(자산도 거기 있다).\n" +
			"  --over 를 생략하면 같은 경합의 **미종결 형제 전부**가 대상이다.")
	}
	ref := pos[0]
	parts := strings.Split(ref, "/")
	if len(parts) != 3 {
		die("거부: <chain>/<cycle>/<승자스텝> 형태여야 한다 (예: ail/stdlib/s15)")
	}
	chain, cycle, winner := parts[0], parts[1], parts[2]
	if strings.TrimSpace(*reason) == "" {
		die("거부: --reason 필요 — **왜 이 가지가 이겼나**.\n" +
			"  채택은 판단이다. 근거 없이 남으면 나중에 아무도 그것이 측정이었는지 취향이었는지 모른다.\n" +
			"  (수치가 있으면 수치로 적어라 — 경합의 값은 대개 거기서 나온다.)")
	}
	all := cycleAnywhere(chain, cycle)
	if len(all) == 0 {
		die("거부: " + chain + "/" + cycle + " 없음")
	}
	byStep := map[string]node{}
	for _, n := range all {
		byStep[n.step] = n
	}
	win, ok := byStep[winner]
	if !ok {
		die("거부: " + ref + " 없음 — 이 사이클에 그런 스텝이 없다.")
	}
	root := competitionRoot(win, all)
	if root == "" {
		die("거부: " + winner + " 은 경합의 갈래가 아니다 — 채택할 경합이 없다.\n" +
			"  경합은 선언으로 선다: gil step " + chain + "/" + cycle +
			" --kind hypothesis --to <analyze|define> --competing …\n" +
			"  (선언 없이 난 형제 가지는 그냥 재분기다 — 그건 채택이 아니라 그냥 이어가면 된다.)")
	}
	// 대상 = 같은 경합의 미종결 잎들 중 승자 가지가 아닌 것.
	winBranchRoot := competitionBranchRoot(win, byStep, root)
	var losers []node
	for _, l := range competingLeaves(chain, cycle) {
		if competitionRoot(l, all) != root {
			continue
		}
		if competitionBranchRoot(l, byStep, root) == winBranchRoot {
			continue // 승자와 같은 갈래(승자 자신 또는 그 뒤에 이어진 스텝)
		}
		losers = append(losers, l)
	}
	if len(*over) > 0 {
		want := map[string]bool{}
		for _, o := range *over {
			want[strings.TrimSpace(o)] = true
		}
		var filtered []node
		for _, l := range losers {
			if want[l.step] || want[competitionBranchRoot(l, byStep, root)] {
				filtered = append(filtered, l)
			}
		}
		losers = filtered
	}
	if len(losers) == 0 {
		die("거부: 접을 형제가 없다 — 이 경합(뿌리 " + root + ")에 미종결 갈래가 승자 말고는 없다.\n" +
			"  이미 다 종결됐으면 그냥 이어가면 된다: gil step " + chain + "/" + cycle + " --kind verify …")
	}
	sort.SliceStable(losers, func(i, j int) bool { return stepNum(losers[i].step) < stepNum(losers[j].step) })
	println2("⚖ 채택: " + ref + " — 접을 형제 " + itoa(len(losers)) + "개")
	for _, l := range losers {
		alignHeadToTip(l.sha, chain+"/"+cycle)
		sid := nextStepID(cycleAnywhere(chain, cycle))
		subject := "gil " + chain + "/" + cycle + "/" + sid + " fail: 경합에서 " + winner + " 에 졌다"
		body := "경합의 갈래 [" + l.step + "] 를 접는다 — 같은 자리(" + root + ")에서 나란히 겨룬 " +
			"형제 중 **" + winner + " 가 채택**됐다.\n\n" +
			"왜 그 가지였나: " + strings.TrimSpace(*reason) + "\n\n" +
			"이 가지는 실패가 아니라 **비교의 한쪽**이다. 대조가 없었으면 승자의 수치도 근거가 " +
			"되지 못한다 — 여기서 잰 것이 그 판단을 떠받친다. 벽의 지도로 남는다."
		tr := [][2]string{
			{"Gil-Chain", chain}, {"Gil-Cycle", cycle},
			{"Gil-Step", sid}, {"Gil-Kind", "fail"}, {"Gil-Parent", l.step},
			{"Gil-Backtrack", root},
			{"Gil-Lost-To", chain + "/" + cycle + "/" + winner},
			{"Gil-Competing", root},
			{"Gil-Toward", "경합의 대조군으로서 승자 판정을 떠받쳤다"},
			{"Gil-Next-Design", "채택된 " + winner + " 가지에서 이어간다"},
		}
		commit(subject, body, tr, true)
		println2("  ✖ " + l.step + " → " + sid + " fail (졌다: " + winner + " 에)")
	}
	// 승자 가지로 옮긴다 — 자산 통합은 이것으로 족하다. 손으로 파일을 긁어 오면 그 승계가
	// 그래프에 안 남는다(#103 이 사이클→체인에서 겪은 것과 같은 병).
	alignHeadToTip(win.sha, chain+"/"+cycle)
	println2("  ✓ HEAD 를 승자 가지로 옮겼다 — 이 사이클은 여기서 이어간다(승자의 산출물도 여기 있다).")
	println2("  ⟹ 다음: gil step " + chain + "/" + cycle + " --kind verify|analyze … → 종결(success) → gil close " + chain + "/" + cycle)
}

// competitionBranchRoot — 이 잎이 속한 **갈래의 뿌리**(경합 선언을 단 그 hypothesis).
// 경합 자체의 뿌리(root)는 형제들이 공유하지만, 갈래의 뿌리는 형제마다 다르다.
func competitionBranchRoot(leaf node, byStep map[string]node, root string) string {
	cur, seen := leaf, map[string]bool{}
	for i := 0; i < 200; i++ {
		if cur.step == "" || seen[cur.step] {
			return ""
		}
		seen[cur.step] = true
		if cur.competing == root {
			return cur.step
		}
		nxt, ok := byStep[cur.parent]
		if !ok {
			return ""
		}
		cur = nxt
	}
	return ""
}
