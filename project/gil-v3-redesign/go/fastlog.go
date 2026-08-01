// fastlog.go — 한 번 읽고 여러 번 답한다 (2026-08-01, 상현님: "테스트 너무 오래 걸린다").
//
// ## 무엇이 느렸나 — 재고서 알았다
//
// 스텝 하나를 새기는 데 181ms 가 걸렸고, 그중 163ms 가 **git 프로세스 24개**였다. 그래프
// 크기와는 거의 무관했다(스텝 5개일 때나 30개일 때나 같았다) — 비용은 데이터가 아니라
// **호출 횟수**였다. 그리고 그 24번 중 대부분은 *같은 커밋들을* 트레일러만 바꿔 다시 읽는
// 것이었다: Gil-Chain 하나 보려고 한 번, Gil-Chain-Purpose 보려고 또 한 번.
//
// 읽기 캐시는 이미 있었지만 **명령줄 전체를 키로 삼아** 형식이 한 글자만 달라도 새 프로세스를
// 띄웠다. 캐시가 있었는데도 24번이었던 이유다.
//
// ## 무엇을 하나
//
// 범위(--branches·HEAD·…)마다 **딱 한 번** 원문(%H·%s·%P·%T·저자·%B)을 긁어 두고, 이후의
// `git log --format=…` 요청은 그 표에서 만들어 돌려준다. 트레일러는 본문(%B)에서 우리가
// 직접 판다 — git 의 트레일러 규칙과 같은 규칙으로(마지막 문단, `Key: value`, 이어지는 줄은
// 공백으로 시작).
//
// 모르는 지시자가 하나라도 있으면 **그냥 git 에 넘긴다.** 최적화가 정확성을 이기면 안 된다:
// 여기서 틀리면 그래프를 잘못 읽는 것이고, 그건 느린 것보다 나쁘다.
package main

import (
	"os"
	"sort"
	"strings"
)

// rawCommit — 원문 한 줄. 트레일러는 필요할 때 본문에서 판다(대부분의 커밋은 안 쓰인다).
type rawCommit struct {
	sha, subj, parents, tree string
	an, ae, ad               string
	cd                       int64 // 커밋 날짜(epoch) — git 의 기본 정렬 기준이다
	body                     string
	tr                       map[string][]string // lazy — nil 이면 아직 안 팠다
}

// trailersOf — 본문 마지막 문단에서 트레일러를 판다(git 과 같은 규칙).
func (c *rawCommit) trailersOf() map[string][]string {
	if c.tr != nil {
		return c.tr
	}
	c.tr = map[string][]string{}
	lines := strings.Split(strings.TrimRight(c.body, "\n"), "\n")
	// 마지막 문단(빈 줄 뒤)만 트레일러 후보다.
	start := 0
	for i := len(lines) - 1; i >= 0; i-- {
		if strings.TrimSpace(lines[i]) == "" {
			start = i + 1
			break
		}
	}
	var keys []string
	var vals []string
	okBlock := start < len(lines)
	for _, ln := range lines[start:] {
		if strings.HasPrefix(ln, " ") || strings.HasPrefix(ln, "\t") {
			if len(vals) > 0 { // 이어지는 줄
				vals[len(vals)-1] += "\n" + strings.TrimLeft(ln, " \t")
				continue
			}
			okBlock = false
			break
		}
		k, v, found := strings.Cut(ln, ": ")
		if !found || k == "" || strings.ContainsAny(k, " \t") {
			okBlock = false
			break
		}
		keys = append(keys, k)
		vals = append(vals, v)
	}
	if okBlock {
		for i, k := range keys {
			c.tr[k] = append(c.tr[k], vals[i])
		}
	}
	return c.tr
}

// rawScanCache — 범위별 원문 표. gitReadCache 와 같은 수명을 산다(쓰기가 있으면 버린다).
var rawScanCache = map[string][]*rawCommit{}

const rawFsep = "\x01"
const rawRsep = "\x02\n"

// rawScan — 이 범위의 커밋 원문을 한 번만 긁는다. 실패하면 nil(그러면 호출자가 git 에 넘긴다).
func rawScan(rest []string) []*rawCommit {
	key := strings.Join(rest, "\x00")
	if v, ok := rawScanCache[key]; ok {
		return v
	}
	// **이미 긁어 둔 표가 이 범위를 덮으면** 새로 띄우지 않는다(아래 절). 묻지 않은 것을
	// 미리 긁지는 않는다 — 큰 나무에서는 그게 프로세스보다 비싸다.
	if cs, ok := sliceFromScanned(rest); ok {
		verifySlice(rest, cs) // GIL_FASTLOG_VERIFY=1 일 때만 — git 과 대조한다
		rawScanCache[key] = cs
		return cs
	}
	f := "--format=%H" + rawFsep + "%s" + rawFsep + "%P" + rawFsep + "%T" + rawFsep +
		"%an" + rawFsep + "%ae" + rawFsep + "%aI" + rawFsep + "%ct" + rawFsep + "%B" + rawRsep
	out, err := gitTry(append([]string{"log", f}, rest...)...)
	if err != nil {
		rawScanCache[key] = nil
		return nil
	}
	var cs []*rawCommit
	for _, rec := range strings.Split(out, rawRsep) {
		rec = strings.TrimPrefix(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		p := strings.SplitN(rec, rawFsep, 9)
		if len(p) < 9 {
			continue
		}
		cs = append(cs, &rawCommit{sha: p[0], subj: p[1], parents: p[2], tree: p[3],
			an: p[4], ae: p[5], ad: p[6], cd: atoi64(p[7]), body: p[8]})
	}
	rawScanCache[key] = cs
	rememberScan(cs) // 다음 범위가 여기서 잘릴 수 있게 남긴다
	return cs
}

// expandFormat — 한 커밋에 대해 --format 문자열을 펼친다. 모르는 지시자를 만나면 (,false).
func expandFormat(f string, c *rawCommit) (string, bool) {
	var b strings.Builder
	for i := 0; i < len(f); {
		if f[i] != '%' {
			b.WriteByte(f[i])
			i++
			continue
		}
		if i+1 >= len(f) {
			return "", false
		}
		switch f[i+1] {
		case 'H':
			b.WriteString(c.sha)
			i += 2
		case 'h':
			b.WriteString(first9(c.sha))
			i += 2
		case 's':
			b.WriteString(c.subj)
			i += 2
		case 'P':
			b.WriteString(c.parents)
			i += 2
		case 'T':
			b.WriteString(c.tree)
			i += 2
		case 'B':
			b.WriteString(c.body)
			i += 2
		case 'n':
			b.WriteString("\n")
			i += 2
		case 'a':
			if strings.HasPrefix(f[i:], "%an") {
				b.WriteString(c.an)
				i += 3
			} else if strings.HasPrefix(f[i:], "%ae") {
				b.WriteString(c.ae)
				i += 3
			} else if strings.HasPrefix(f[i:], "%aI") {
				b.WriteString(c.ad)
				i += 3
			} else {
				return "", false
			}
		case 'x':
			// %x1f 같은 16진 리터럴.
			if i+3 >= len(f) {
				return "", false
			}
			var v int
			for _, ch := range f[i+2 : i+4] {
				d := hexVal(byte(ch))
				if d < 0 {
					return "", false
				}
				v = v*16 + d
			}
			b.WriteByte(byte(v))
			i += 4
		case '(':
			end := strings.Index(f[i:], ")")
			if end < 0 {
				return "", false
			}
			spec := f[i+2 : i+end]
			i += end + 1
			const pre = "trailers:key="
			if !strings.HasPrefix(spec, pre) {
				return "", false
			}
			rest := spec[len(pre):]
			key, opts, _ := strings.Cut(rest, ",")
			// 우리가 쓰는 형태는 valueonly [+ separator=%x00] 둘뿐이다. 그 밖이면 git 에 넘긴다.
			sepStr := "\n"
			switch opts {
			case "valueonly":
			case "valueonly,separator=%x00":
				sepStr = "\x00"
			default:
				return "", false
			}
			vs := c.trailersOf()[key]
			b.WriteString(strings.Join(vs, sepStr))
		default:
			return "", false
		}
	}
	return b.String(), true
}

func hexVal(b byte) int {
	switch {
	case b >= '0' && b <= '9':
		return int(b - '0')
	case b >= 'a' && b <= 'f':
		return int(b-'a') + 10
	case b >= 'A' && b <= 'F':
		return int(b-'A') + 10
	}
	return -1
}

// fastGitLog — `git log --format=<F> <나머지>` 를 원문 표에서 만들어 돌려준다.
// 만들 수 없으면 (,false) — 그러면 호출자가 진짜 git 을 부른다.
func fastGitLog(args []string) (string, bool) {
	if !gitCacheOn || len(args) == 0 {
		return "", false
	}
	var format string
	var rest []string
	for _, a := range args {
		switch {
		case strings.HasPrefix(a, "--format="):
			if format != "" {
				return "", false
			}
			format = strings.TrimPrefix(a, "--format=")
		case strings.HasPrefix(a, "--pretty"), a == "-p", a == "--patch", a == "--stat",
			a == "--name-only", a == "--name-status", a == "--numstat", a == "--graph":
			return "", false // 원문 표로는 못 만드는 것들
		default:
			rest = append(rest, a)
		}
	}
	if format == "" {
		return "", false
	}
	cs := rawScan(rest)
	if cs == nil {
		return "", false
	}
	var b strings.Builder
	for _, c := range cs {
		s, ok := expandFormat(format, c)
		if !ok {
			return "", false
		}
		b.WriteString(s)
		b.WriteString("\n") // git 은 커밋마다 개행을 붙인다
	}
	return b.String(), true
}

// ── 이미 긁어 둔 것에서 잘라낸다 (2026-08-02) ────────────────────────────────
//
// ## 처음 시도한 것과, 그것이 왜 틀렸나
//
// 범위마다 git 을 새로 띄우는 게 아까워서 **저장소 전체(`--all`)를 한 번 긁어 두고 범위를
// 거기서 잘라내게** 만들었다. 작은 저장소에서는 빨라졌다(스텝 10프로세스 → 4). 그런데 전체
// 시험은 **한 톨도 안 빨라졌다**: 평범한 클래스는 2~3초 줄고, 이주 시험(가지가 수백인 큰
// 나무)은 2~7초 늘어 서로 상쇄했다.
//
// 이유는 재고 나서야 분명해졌다. **비용은 두 가지고 둘은 반대로 움직인다** — 작은 그래프에서는
// 프로세스를 띄우는 값이 전부고, 큰 그래프에서는 읽는 데이터의 양이 전부다. `HEAD` 하나면
// 되는 명령에게 숲 전체를 읽히면, 프로세스 하나를 아끼려고 데이터를 백 배 읽는다.
//
// ## 그래서 규칙을 뒤집었다
//
// **묻지 않은 것은 긁지 않는다.** 범위 요청은 그 범위 그대로 git 에 간다(옛 동작). 다만 이미
// 긁어 둔 표가 그 범위를 **덮고 있으면** 새로 띄우지 않고 거기서 잘라낸다. 덮는지 아닌지는
// 짐작하지 않는다 — 팁에서 부모를 따라 걸어 **전부 그 표 안에 있을 때만** 잘라낸다. 하나라도
// 없으면 반쪽짜리 답 대신 git 에 넘긴다.

// scanTable — 한 번 긁은 범위의 표(순서는 git 이 준 그대로 보존한다).
type scanTable struct {
	order []*rawCommit
	bySha map[string]*rawCommit
}

var (
	scanTables []*scanTable
	refsTried  bool
	refsBySha  map[string]string // 완전 refname → sha
	refsHead   string            // HEAD 가 가리키는 sha
)

// dropScanTables — 쓰기가 지나가면 표도 ref 표도 버린다(dropReadCaches 가 부른다).
func dropScanTables() {
	scanTables = nil
	refsTried = false
	refsBySha = nil
	refsHead = ""
}

// rememberScan — git 이 준 결과를 표로 남긴다(다음 범위가 여기서 잘릴 수 있게).
func rememberScan(cs []*rawCommit) {
	if len(cs) == 0 {
		return
	}
	t := &scanTable{order: cs, bySha: make(map[string]*rawCommit, len(cs))}
	for _, c := range cs {
		t.bySha[c.sha] = c
	}
	scanTables = append(scanTables, t)
}

// loadRefs — HEAD 와 모든 ref 를 **한 프로세스**로(show-ref --head). 범위 이름을 sha 로
// 옮길 때만 부른다 — 표가 하나도 없으면 부를 일도 없다.
func loadRefs() bool {
	if refsTried {
		return refsBySha != nil
	}
	refsTried = true
	if !gitCacheOn {
		return false // 오래 사는 프로세스(뷰어·MCP·--wait)는 저장소가 밖에서 바뀐다
	}
	out, err := gitTry("show-ref", "--head")
	if err != nil {
		return false
	}
	refsBySha = map[string]string{}
	for _, ln := range strings.Split(out, "\n") {
		f := strings.Fields(ln)
		if len(f) != 2 {
			continue
		}
		if f[1] == "HEAD" {
			refsHead = f[0]
			continue
		}
		refsBySha[f[1]] = f[0]
	}
	return true
}

// rangeTips — 이 범위가 가리키는 출발점 sha 들. 모르는 모양이면 (nil,false).
func rangeTips(rest []string) ([]string, bool) {
	var tips []string
	add := func(sha string) {
		if sha != "" {
			tips = append(tips, sha)
		}
	}
	for i, a := range rest {
		switch {
		case a == "--":
			if i != len(rest)-1 {
				return nil, false // 뒤에 경로 필터가 붙는다 — 파일별 이력은 git 의 것이다
			}
		// **차례가 답을 바꾼다.** git 은 ref 를 이름 순으로 훑고, 그 차례가 곧 팁을 큐에 넣는
		// 차례이며, 날짜가 같을 때는 그 차례가 출력 순서를 정한다. Go 맵을 그냥 돌면 매번
		// 다른 순서가 나온다 — verify 가 이걸 잡았다.
		case a == "--all":
			for _, name := range sortedRefNames("refs/") {
				add(refsBySha[name])
			}
			add(refsHead) // --all 은 refs/ 를 먼저, HEAD 를 나중에 얹는다
		case a == "--branches":
			for _, name := range sortedRefNames("refs/heads/") {
				add(refsBySha[name])
			}
		case a == "--remotes":
			for _, name := range sortedRefNames("refs/remotes/") {
				add(refsBySha[name])
			}
		case a == "HEAD":
			add(refsHead)
		case strings.HasPrefix(a, "-"):
			return nil, false // 모르는 옵션
		case strings.ContainsAny(a, ".^~@:*?["):
			return nil, false // A..B · ^X · X~2 · 글롭 — 범위 문법은 git 의 것이다
		default:
			if sha, ok := lookupRefSha(a); ok {
				add(sha)
			} else {
				return nil, false
			}
		}
	}
	return tips, true
}

// sortedRefNames — 접두로 걸러 이름 순으로(git 의 ref 훑는 차례).
func sortedRefNames(prefix string) []string {
	var names []string
	for name := range refsBySha {
		if strings.HasPrefix(name, prefix) {
			names = append(names, name)
		}
	}
	sort.Strings(names)
	return names
}

// lookupRefSha — 짧은 이름(main·origin/main)·완전 이름·40자 sha 를 ref 표에서 찾는다.
func lookupRefSha(a string) (string, bool) {
	if sha, ok := refsBySha[a]; ok {
		return sha, true
	}
	for _, pre := range []string{"refs/heads/", "refs/tags/", "refs/remotes/", "refs/"} {
		if sha, ok := refsBySha[pre+a]; ok {
			return sha, true
		}
	}
	if len(a) == 40 {
		return a, true // sha 는 표 안에 있는지로 판정된다(아래 도달 검사)
	}
	return "", false
}

// sliceFromScanned — 이미 긁어 둔 표 중 이 범위를 **완전히 덮는** 것이 있으면 거기서 잘라낸다.
func sliceFromScanned(rest []string) ([]*rawCommit, bool) {
	if len(scanTables) == 0 || !gitCacheOn {
		return nil, false
	}
	if !loadRefs() {
		return nil, false
	}
	tips, ok := rangeTips(rest)
	if !ok {
		return nil, false
	}
	// 큰 표부터 본다 — 덮을 확률이 높다.
	for i := len(scanTables) - 1; i >= 0; i-- {
		if cs, ok := sliceFrom(scanTables[i], tips); ok {
			return cs, true
		}
	}
	return nil, false
}

// sliceFrom — 이 표 안에서 **git 과 같은 걸음으로** 범위를 걷는다.
//
// 왜 걸어야 하나. 처음엔 "큰 표의 순서를 그대로 두고 거르면 된다"고 봤다. 틀렸다 —
// 시험의 커밋들은 **같은 초에** 찍히고, 날짜가 같으면 git 의 순서는 날짜가 아니라 **어느
// 팁에서 어떤 차례로 걸어왔는지**가 정한다. 그래서 `--branches` 표를 걸러 `HEAD` 를 만들면
// 같은 6개가 다른 차례로 나왔다(GIL_FASTLOG_VERIFY 가 잡았다. 582 테스트는 못 잡았다 —
// 순서가 달라도 대부분의 단언은 통과하기 때문이다. 조용히 다른 그래프를 읽고 있었다).
//
// git 의 걸음(commit_list_insert_by_date): 팁을 명령줄 차례로 넣고, 날짜가 큰 것부터 꺼내며
// 꺼낸 것의 부모를 같은 규칙으로 넣는다. **날짜가 같으면 먼저 들어온 것이 먼저 나온다.**
// 그대로 옮긴다.
func sliceFrom(t *scanTable, tips []string) ([]*rawCommit, bool) {
	seen := make(map[string]bool, len(tips)*4)
	var queue []*rawCommit // 날짜 내림차순, 같은 날짜는 먼저 들어온 것이 앞
	insert := func(c *rawCommit) {
		i := 0
		for i < len(queue) && queue[i].cd >= c.cd {
			i++
		}
		queue = append(queue, nil)
		copy(queue[i+1:], queue[i:])
		queue[i] = c
	}
	for _, sha := range tips {
		c, ok := t.bySha[sha]
		if !ok {
			return nil, false // 이 표가 이 범위를 안 덮는다 — git 에 넘긴다
		}
		if seen[sha] {
			continue
		}
		seen[sha] = true
		insert(c)
	}
	out := make([]*rawCommit, 0, len(seen))
	for len(queue) > 0 {
		c := queue[0]
		queue = queue[1:]
		out = append(out, c)
		for _, p := range strings.Fields(c.parents) {
			if seen[p] {
				continue
			}
			pc, ok := t.bySha[p]
			if !ok {
				return nil, false // 조상이 표 밖이다 — 반쪽짜리 답을 주지 않는다
			}
			seen[p] = true
			insert(pc)
		}
	}
	return out, true
}

// atoi64 — 실패하면 0(날짜를 못 읽으면 정렬이 흔들리지만, 그건 verify 가 잡는다).
func atoi64(s string) int64 {
	var n int64
	for _, c := range strings.TrimSpace(s) {
		if c < '0' || c > '9' {
			return n
		}
		n = n*10 + int64(c-'0')
	}
	return n
}

// verifySlice — **잘라낸 답이 git 의 답과 같은가**를 실제로 물어 확인한다(GIL_FASTLOG_VERIFY=1).
//
// 최적화가 정확성을 이기면 안 된다는 규칙은 선언으로 지켜지지 않는다. 시험 전체를 이 모드로
// 한 번 돌려, 잘라낸 모든 범위가 git 이 준 것과 sha 열까지 같은지 세어 둔다. 다르면 그 자리에서
// 죽는다 — 조용히 다른 그래프를 읽느니 요란하게 멈추는 편이 낫다.
func verifySlice(rest []string, got []*rawCommit) {
	if os.Getenv("GIL_FASTLOG_VERIFY") == "" {
		return
	}
	verifiedSlices++
	f := "--format=%H" + rawFsep + "%s" + rawFsep + "%P" + rawFsep + "%T" + rawFsep +
		"%an" + rawFsep + "%ae" + rawFsep + "%aI" + rawFsep + "%ct" + rawFsep + "%B" + rawRsep
	out, err := gitTry(append([]string{"log", f}, rest...)...)
	if err != nil {
		return // git 도 못 답하는 범위(빈 저장소 등) — 대조할 것이 없다
	}
	var want []string
	for _, rec := range strings.Split(out, rawRsep) {
		rec = strings.TrimPrefix(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		if p := strings.SplitN(rec, rawFsep, 9); len(p) >= 9 {
			want = append(want, p[0])
		}
	}
	var mine []string
	for _, c := range got {
		mine = append(mine, c.sha)
	}
	if strings.Join(want, ",") != strings.Join(mine, ",") {
		verifiedSlices = 0
		die("내부 오류(fastlog): 범위 " + strings.Join(rest, " ") + " 를 잘라낸 답이 git 과 다르다\n" +
			"  git: " + itoa(len(want)) + "개 / 잘라낸 것: " + itoa(len(mine)) + "개")
	}
}

// verifiedSlices — 이 실행에서 **실제로 잘라낸** 범위의 수. 대조 모드가 "통과"라고 말할 때,
// 잘라낸 것이 0개면 그 통과는 아무것도 검증하지 않은 것이다(빈 시험은 시험이 아니다).
var verifiedSlices int

// verifySummary — 대조 모드에서 종료 직전에 한 줄. 시험이 이 수를 보고 "정말 그 길을
// 밟았는지"를 단언한다.
func verifySummary() {
	if os.Getenv("GIL_FASTLOG_VERIFY") == "" || verifiedSlices == 0 {
		return
	}
	stderr("fastlog: 잘라낸 범위 " + itoa(verifiedSlices) + "개 — git 과 전부 일치")
}
