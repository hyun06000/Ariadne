// status_strip.go — 카드 맨 위의 **사이클 띠**. 카드 종류와 무관하게 언제나 여기 있다 (상현님).
//
// 왜 kind 와 무관한가. 카드의 본문은 kind 마다 다르지만("지금 뭘 하나" vs "무엇을 남겼나"),
// **어디에 서 있나**는 어느 카드에서도 같은 질문이다. 띠가 kind 마다 나타나고 사라지면 사람은
// 매번 화면 구조를 다시 읽어야 하고, 그러면 카드가 한 종류의 물건으로 안 읽힌다.
//
// 배치는 손으로 박지 않는다 — `cycle.steps[]` 의 {id, kind, parent, back} 만 쓴다. 손으로
// 그리다 값을 치른 자리다(없는 간선을 지어내고 s9→s8, 있는 간선을 빠뜨리고 s12→s14, 브랜치
// **이름**을 분기로 읽었다). 규칙의 진실원은 docs/gil/status-card.md 다.
package main

import (
	"sort"
	"strings"
)

// stripKindColor — 일곱 kind 의 색. 종류만 말한다(위치는 링이 말한다).
//
// **죽은 잎은 코랄이지 빨강이 아니다.** 빨강은 오류의 색이라 그걸 쓰면 fail 이 잘못으로
// 읽히고, 사람은 되돌리기를 손실로 읽는다 — gil 이 막으려는 바로 그 압력이다.
// 중간 램프 값이라 라이트·다크 양쪽에서 읽힌다.
func stripKindColor(kind string) string {
	switch kind {
	case "define":
		return "#888780" // 회색
	case "hypothesis":
		return "#7F77DD" // 보라
	case "verify":
		return "#378ADD" // 파랑
	case "analyze":
		return "#1D9E75" // 청록
	case "pending":
		return "#EF9F27" // 앰버 — 사람 대기
	case "success":
		return "#639922" // 초록 — 산 잎
	case "fail":
		return "#D85A30" // 코랄 — 죽은 잎
	}
	return "#B4B2A9"
}

// statusKindLegend — 띠 아래 한 줄, **일곱 kind 의 색**(상현님: 캡션 자리에 색을).
//
// 왜 늘 일곱을 다 내나. 지금 사이클에 있는 것만 내면 범례가 사이클마다 달라지고, 그러면
// "이 색이 무엇인가"를 매번 다시 배워야 한다. 색의 뜻은 사이클의 사정과 무관하게 고정이다.
func statusKindLegend() string {
	var b strings.Builder
	b.WriteString(`<div class="legend">`)
	for _, k := range []string{"define", "hypothesis", "verify", "analyze", "pending", "success", "fail"} {
		b.WriteString(`<span><i style="background:` + stripKindColor(k) + `"></i>` + k + `</span>`)
	}
	b.WriteString(`</div>`)
	return b.String()
}

type stripPos struct {
	col, row int
}

// stripLayout — 스텝마다 (열, 행). 열은 부모로부터의 깊이, 행은 형제 순서.
//
// **첫 자식이 부모의 줄을 그대로 잇는다**(척추는 곧다). 둘째 자식부터 새 행으로 내려간다 —
// 꺾인 선은 곧 분기이므로, 분기가 아닌 간선을 꺾으면 없는 갈라짐을 그린 것이 된다.
func stripLayout(steps []statusStepNode) (map[string]stripPos, int, int) {
	kids := map[string][]string{}
	var roots []string
	known := map[string]bool{}
	for _, s := range steps {
		known[s.ID] = true
	}
	for _, s := range steps {
		if s.Parent == "" || !known[s.Parent] {
			roots = append(roots, s.ID) // 부모가 이 사이클 밖이면 여기서는 뿌리다
			continue
		}
		kids[s.Parent] = append(kids[s.Parent], s.ID)
	}
	byNum := func(ss []string) {
		sort.SliceStable(ss, func(i, j int) bool { return stepNum(ss[i]) < stepNum(ss[j]) })
	}
	byNum(roots)
	for k := range kids {
		byNum(kids[k])
	}
	pos, nextRow, maxCol := map[string]stripPos{}, 0, 0
	var place func(id string, col, row int)
	place = func(id string, col, row int) {
		if _, dup := pos[id]; dup {
			return // 사이클 방지 — 기록이 상해도 그림은 돈다
		}
		pos[id] = stripPos{col: col, row: row}
		if col > maxCol {
			maxCol = col
		}
		if row+1 > nextRow {
			nextRow = row + 1
		}
		for i, c := range kids[id] {
			if i == 0 {
				place(c, col+1, row) // 척추
				continue
			}
			place(c, col+1, nextRow) // 분기는 아래로만
		}
	}
	for _, r := range roots {
		place(r, 0, nextRow)
	}
	return pos, maxCol, nextRow
}

// statusStripSVG — 띠 한 장. 스텝이 없으면 빈 문자열(없는 것을 그리지 않는다).
func statusStripSVG(steps []statusStepNode, current string) string {
	if len(steps) == 0 {
		return ""
	}
	pos, maxCol, rows := stripLayout(steps)
	parent := map[string]string{}
	for _, s := range steps {
		parent[s.ID] = s.Parent
	}
	// 가로 간격은 **가용 폭에 맞춰** 계산한다 — 긴 사이클이 오른쪽으로 넘치지 않게.
	gap := 68
	if maxCol > 0 {
		if g := 620 / maxCol; g < gap {
			gap = g
		}
		// 노드가 아주 많은 사이클이 실제로 있다(상현님) — 그때는 촘촘하게라도 **다 그린다**.
		// 잘라내면 사람은 그 사이클을 다 본 줄 알고, 안 보이는 갈래가 잊힌다.
		if gap < 18 {
			gap = 18
		}
	}
	// 노드는 작다(상현님). 띠는 지금 자리를 말하는 물건이고, 크게 그리면 그것만으로 카드
	// 한 폭을 먹는다 — 아래 본문이 밀린다.
	const left, top, rowH, r = 22, 34, 28, 4
	x := func(id string) int { return left + pos[id].col*gap }
	y := func(id string) int { return top + pos[id].row*rowH }
	w, h := left+maxCol*gap+22, top+(rows-1)*rowH+12
	var b strings.Builder
	b.WriteString(`<svg class="strip" viewBox="0 0 ` + itoa(w) + ` ` + itoa(h) +
		`" width="` + itoa(w) + `" height="` + itoa(h) + `" xmlns="http://www.w3.org/2000/svg">`)

	// 간선. 부모와 같은 행이면 곧은 가로선, 다른 행이면 부모 자리에서 내려가 오른쪽으로 꺾는다.
	for _, s := range steps {
		p := s.Parent
		if p == "" {
			continue
		}
		if _, ok := pos[p]; !ok {
			continue // 부모가 이 사이클 밖 — 없는 선을 그리지 않는다
		}
		px, py, cx, cy := x(p), y(p), x(s.ID), y(s.ID)
		if py == cy {
			b.WriteString(`<line class="e" x1="` + itoa(px) + `" y1="` + itoa(py) +
				`" x2="` + itoa(cx) + `" y2="` + itoa(cy) + `"/>`)
			continue
		}
		b.WriteString(`<path class="e" d="M` + itoa(px) + ` ` + itoa(py) +
			` L` + itoa(px) + ` ` + itoa(cy) + ` L` + itoa(cx) + ` ` + itoa(cy) + `"/>`)
	}

	// 백트랙 — 붉은 점선. **간선을 되짚지 않고 두 점을 굴곡 하나로 잇는다**(상현님).
	//
	// 되짚는 그림을 먼저 만들어 보고 바꿨다: 지나온 경로를 따라 그으면 선이 실제 간선과
	// 나란히 겹쳐 달려서, **어디서 어디로 돌아갔는지가 안 보였다.** 되돌리기는 경로가 아니라
	// **두 자리의 관계**다 — 활처럼 한 번 굽혀 위로 빼면 시작과 끝이 바로 읽힌다.
	//
	// 여전히 부모 사슬로 대상에 닿는지는 확인한다. 못 닿으면 그리지 않는다 — 그림은 기록이
	// 말하는 것만 말해야 하고, 닿지 않는 백트랙은 기록이 상한 것이지 그릴 것이 아니다.
	for _, s := range steps {
		if s.Back == "" {
			continue
		}
		if _, ok := pos[s.Back]; !ok {
			continue
		}
		cur, hops, reached := s.ID, 0, false
		for cur != "" && hops < 200 {
			if cur == s.Back {
				reached = true
				break
			}
			cur, hops = parent[cur], hops+1
			if _, ok := pos[cur]; !ok {
				break
			}
		}
		if !reached {
			continue
		}
		x1, y1, x2, y2 := x(s.ID), y(s.ID), x(s.Back), y(s.Back)
		// 굽는 높이는 **제 행을 기준으로** 잡는다(둘 중 위쪽이 아니라). 전체의 맨 위를 기준으로
		// 잡으면 갈래가 여럿일 때 활 다섯이 같은 높이에 겹쳐 한 줄로 보인다 — 실측으로 봤다.
		// 제 행 위 빈 칸(행 간격의 절반쯤)에 얹으면 갈래마다 제 활을 갖는다.
		span := x1 - x2
		if span < 0 {
			span = -span
		}
		// 활은 **제 행의 kind 이름 위로** 넘어가야 한다. 이름이 노드 위에 있으니(cy-r-6),
		// 얕게 굽히면 활이 글자를 관통한다 — 실측으로 봤다. 3차 곡선의 실제 정점은 제어점의
		// 3/4 쯤이므로 그만큼 더 든다.
		lift := 28 + span/30
		if lift > 40 {
			lift = 40
		}
		peak := y1 - lift
		if peak < 3 {
			peak = 3
		}
		c1, c2 := x1-span/3, x2+span/3
		b.WriteString(`<path class="bt" d="M` + itoa(x1) + ` ` + itoa(y1) +
			` C` + itoa(c1) + ` ` + itoa(peak) + `, ` + itoa(c2) + ` ` + itoa(peak) +
			`, ` + itoa(x2) + ` ` + itoa(y2) + `"/>`)
	}

	// 노드. **크기·모양·선을 차별하지 않는다** — 죽은 잎도 같은 반지름, 같은 실선. 색만 다르다.
	for _, s := range steps {
		cx, cy := x(s.ID), y(s.ID)
		col := stripKindColor(s.Kind)
		if s.ID == current {
			// 지금 위치는 **바깥 링**. 색은 종류를, 링은 위치를 말한다.
			b.WriteString(`<circle class="ring" cx="` + itoa(cx) + `" cy="` + itoa(cy) +
				`" r="` + itoa(r+4) + `" stroke="` + col + `"/>`)
		}
		b.WriteString(`<circle cx="` + itoa(cx) + `" cy="` + itoa(cy) + `" r="` + itoa(r) +
			`" fill="` + col + `"><title>` + esc(s.ID+" "+s.Kind) + `</title></circle>`)
		// **kind 를 노드 위에 작게**(상현님). 색만으로 일곱을 가르라고 하면 색을 못 보는 사람
		// 앞에서 띠가 통째로 무의미해진다 — 색은 훑는 데 쓰고, 이름이 판정한다.
		// 다만 칸이 좁아 이름끼리 겹치면 안 쓴다(겹친 글자는 없는 글자보다 나쁘다).
		if gap >= 62 {
			b.WriteString(`<text class="knd" x="` + itoa(cx) + `" y="` + itoa(cy-r-6) +
				`">` + esc(s.Kind) + `</text>`)
		}
	}
	b.WriteString(`</svg>`)
	return b.String()
}
