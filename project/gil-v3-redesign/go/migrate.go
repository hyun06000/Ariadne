// migrate.go — gil migrate: v2(폴더·cycle.yaml 기반) 이력을 v3(커밋 그래프) 로 이주한다.
//
// ⭐ 도구 레벨·범용 (상현님, 2026-07-24): 우리 레포 전용 스크립트가 아니라, 임의의 v2 필드
// 저장소가 쓸 수 있는 gil 내장 명령이다. 우리 v2(main)를 첫 실검증 대상으로 삼되, 어떤
// v2 rooms 트리든(하드코딩 없이) 파싱해 v3 커밋 그래프로 변환한다.
//
// v2 스키마(폴더 기반): rooms/<room>/chains/<chain>/C0xx-<slug>/cycle.yaml
//   cycle.yaml: id · chain · parent · lineage[] · author · status · opened · closed ·
//               title · verdict · superseded_by · step ...
//
// v2→v3 매핑 (상현님 확정, 실데이터 182 사이클 커버):
//   5단계 → kind (압축): hypothesis(+design 흡수)→define, verification→verify,
//                        analysis+report+verdict→종결 스텝.
//   verdict → 종결 kind: supported/success→success(산 잎), rejected→fail(죽은 잎),
//                        **그 밖의 전부**(partial·inconclusive·verdict 없음·미지의 값)→pending.
//                        없는 성공을 날조하지 않는다(이슈 #50) — 결론이 아닌 것을 산 잎으로
//                        접으면 이주된 이력이 원본보다 낙관적인 거짓말이 된다.
//   구조: chain→Gil-Chain, C0xx-slug→Gil-Cycle(소문자화), parent→--parent(같은 체인),
//         lineage→교훈계승(목적문·트레일러), title/author/opened/closed→메타.
//   이주 표식: 커밋 subject 에 [migrate], Gil-Kind: migrate(체인·사이클 루트),
//             Gil-Migrated-From: <v2 id> (v2 SPEC 이주 규정 계승).
package main

import (
	"sync"
	"sort"
	"strings"
)

// ── v2 cycle.yaml 파싱 (의존성 0: Go 표준만, 최소 YAML 리더) ──
//
// v2 cycle.yaml 은 스칼라 + 짧은 인라인 리스트뿐이라 완전한 YAML 엔진이 필요없다.
// 라인 단위로 `key: value` 를 읽고, 주석(#)·따옴표·인라인 리스트([a, b])를 처리한다.
type v2cycle struct {
	path     string // 저장소 상대 경로 (진단·정렬용)
	id       string   // C0xx-slug
	chain    string
	parents  []string // 부모 사이클(들). v2 parent 는 보통 스칼라지만 인라인 리스트(머지)도 있다.
	lineage  []string // 다른 체인 교훈 (chain/C0xx...)
	author   string
	status   string // closed | open
	opened   string
	closed   string
	title    string
	verdict  string // supported|success|rejected|partial|null|""
	superBy  string // superseded_by (무효화 후속) 또는 ""
}

// parseV2Cycle — cycle.yaml 본문을 v2cycle 로. 우리가 쓰는 필드만 취한다(나머지 무시).
func parseV2Cycle(path, text string) v2cycle {
	c := v2cycle{path: path}
	for _, raw := range strings.Split(text, "\n") {
		line := stripYAMLComment(raw)
		key, val, ok := cut(line, ":")
		if !ok {
			continue
		}
		key = strings.TrimSpace(key)
		val = strings.TrimSpace(val)
		val = unquoteYAML(val)
		switch key {
		case "id":
			c.id = val
		case "chain":
			c.chain = val
		case "parent":
			// 스칼라(C0xx) 또는 인라인 리스트([C0xx, C0yy] — v2 머지 사이클)를 모두 받는다.
			if strings.HasPrefix(strings.TrimSpace(val), "[") {
				c.parents = parseInlineList(val)
			} else if !isYAMLNull(val) {
				c.parents = []string{val}
			}
		case "lineage":
			c.lineage = parseInlineList(val)
		case "author":
			c.author = val
		case "status":
			c.status = val
		case "opened":
			c.opened = val
		case "closed":
			c.closed = val
		case "title":
			c.title = val
		case "verdict":
			c.verdict = val
		case "superseded_by":
			if !isYAMLNull(val) {
				c.superBy = val
			}
		}
	}
	return c
}

// primaryParent — 위상정렬·분기 지점으로 쓸 첫 부모(없으면 ""). 나머지 부모는 트레일러로만.
func (c v2cycle) primaryParent() string {
	if len(c.parents) > 0 {
		return c.parents[0]
	}
	return ""
}

// deriveFromPath — id·chain 필드가 없는 v2 스키마 변종(state/verdict만 있는 뒤늦은 cycle.yaml)을
// 위해 경로 rooms/.../chains/<chain>/<C0xx-slug>/cycle.yaml 에서 id·chain 을 복원한다.
func (c *v2cycle) deriveFromPath() {
	parts := strings.Split(c.path, "/")
	for i := 0; i+2 < len(parts); i++ {
		if parts[i] == "chains" {
			if c.chain == "" {
				c.chain = parts[i+1]
			}
			if c.id == "" {
				c.id = parts[i+2] // C0xx-slug 디렉토리명
			}
			return
		}
	}
}

// stripYAMLComment — 값 뒤 " # 주석" 을 떼되, 따옴표 안 #는 보존한다.
func stripYAMLComment(line string) string {
	inS, inD := false, false
	for i, r := range line {
		switch r {
		case '\'':
			if !inD {
				inS = !inS
			}
		case '"':
			if !inS {
				inD = !inD
			}
		case '#':
			if !inS && !inD {
				// 앞이 공백이거나 줄 시작일 때만 주석으로 본다(값 안 # 회피는 위 따옴표로).
				if i == 0 || line[i-1] == ' ' || line[i-1] == '\t' {
					return line[:i]
				}
			}
		}
	}
	return line
}

// unquoteYAML — 감싼 따옴표 한 겹을 벗긴다.
func unquoteYAML(s string) string {
	if len(s) >= 2 {
		if (s[0] == '"' && s[len(s)-1] == '"') || (s[0] == '\'' && s[len(s)-1] == '\'') {
			return s[1 : len(s)-1]
		}
	}
	return s
}

func isYAMLNull(s string) bool {
	s = strings.TrimSpace(s)
	return s == "" || s == "null" || s == "~"
}

// parseInlineList — "[a, b]" 또는 "" → []string. v2 lineage 는 항상 인라인 리스트.
func parseInlineList(s string) []string {
	s = strings.TrimSpace(s)
	s = strings.TrimPrefix(s, "[")
	s = strings.TrimSuffix(s, "]")
	var out []string
	for _, p := range strings.Split(s, ",") {
		p = strings.TrimSpace(unquoteYAML(strings.TrimSpace(p)))
		if p != "" && !isYAMLNull(p) {
			out = append(out, p)
		}
	}
	return out
}

// ── v2 슬러그 → v3 id (소문자·숫자·하이픈만) ──
//
// v2 id 는 "C001-existence-in-repo" 꼴(대문자 C). v3 id 규칙(idRe: 소문자·숫자·하이픈)에
// 맞춰 소문자화한다: C001-existence-in-repo → c001-existence-in-repo.
func v2ToV3ID(id string) string {
	return strings.ToLower(strings.TrimSpace(id))
}

// ── verdict → v3 종결 kind ──
//
// **없는 성공을 날조하지 않는다**(이슈 #50). 옛 매핑은 partial·inconclusive·verdict 없음을
// 전부 success 로 접었다 — 실사용 저장소에서 71 사이클 중 18개(25%)가 "산 잎"으로 둔갑했다.
// 그 순간 이주된 이력은 원본보다 **낙관적인 거짓말**이 된다. gil 이 close --abandon 에서
// 지킨 원칙("없는 성공을 날조하지 않는다")이 이주에서 깨지면 안 된다.
//
// v3 어휘는 셋뿐이다: success(산 잎) · fail(죽은 잎) · pending(사람 판단 대기). 그래서
// **명확히 지지된 것만 success, 명확히 기각된 것만 fail, 나머지는 전부 pending** 이다.
// pending 은 "모른다"가 아니라 "이건 사람이 봐야 한다"는 정직한 표식이다 — 결론이 없던
// 사이클에 딱 맞는다. 원본 verdict 문자열은 종결 스텝 본문에 그대로 보존되므로 잃지 않는다.
func verdictToClosureKind(c v2cycle) string {
	switch strings.ToLower(strings.TrimSpace(c.verdict)) {
	case "rejected":
		return "fail"
	case "supported", "success":
		return "success"
	default:
		// partial · inconclusive · verdict 없음 · 알 수 없는 값 — 결론이 아니다.
		// 사람이 그 사이클을 다시 보고 approve/reject 로 결말을 지어야 한다.
		return "pending"
	}
}

// ── v2 실사이클 수집 (fixture·template 제외) ──
//
// 진짜 이력만 이주 대상이다. v2 트리엔 3-verification/ 안의 테스트 fixture 와 _template,
// 검증 실행 산출물(runs/)이 섞여 있는데 이건 실이력이 아니다. 경로로 걸러낸다.
func isRealV2CyclePath(path string) bool {
	if !strings.HasSuffix(path, "/cycle.yaml") && path != "cycle.yaml" {
		return false
	}
	skip := []string{"3-verification/", "/fixtures/", "/runs/", "_template/", "/template/"}
	for _, s := range skip {
		if strings.Contains(path, s) {
			return false
		}
	}
	return true
}

// migrateExcludes — --exclude 로 받은 경로 조각들. 경로에 이 문자열이 들어가면 이주에서
// 뺀다(이슈 #50 ②). 왜 필요한가: v2 fsck 는 동결해 둔 옛 체인(legacy/archived-chains/…)을
// 세지 않는데 migrate 는 끌어와 라이브 v3 체인으로 만든다. 동작이 틀린 게 아니라 **제어가
// 없던 것**이 문제다 — 보존하고 싶은 사람도, 빼고 싶은 사람도 있다.
var migrateExcludes []string

// collectV2Cycles — v2 ref 트리에서 실사이클 cycle.yaml 들을 읽어 파싱한다.
func collectV2Cycles(ref, roomFilter string) []v2cycle {
	out, err := gitTry("ls-tree", "-r", "--name-only", ref)
	if err != nil {
		die("거부: v2 ref \"" + ref + "\" 를 읽을 수 없다 — " + err.Error())
	}
	var cycles []v2cycle
	for _, path := range strings.Split(out, "\n") {
		path = strings.TrimSpace(path)
		if !isRealV2CyclePath(path) {
			continue
		}
		blob, err := gitTry("show", ref+":"+path)
		if err != nil {
			continue
		}
		c := parseV2Cycle(path, blob)
		if c.id == "" || c.chain == "" {
			c.deriveFromPath() // 필드 없는 변종은 경로에서 복원
		}
		if c.id == "" || c.chain == "" {
			continue // 경로로도 복원 불가 — 사이클로 안 본다
		}
		if roomFilter != "" && !strings.Contains(path, "/"+roomFilter+"/") &&
			!strings.HasPrefix(path, "rooms/"+roomFilter+"/") {
			continue
		}
		if excluded := matchExclude(path); excluded != "" {
			migrateExcluded = append(migrateExcluded, path+"  (--exclude "+excluded+")")
			continue
		}
		cycles = append(cycles, c)
	}
	return cycles
}

// migrateExcluded — --exclude 로 빠진 경로들. dry-run 이 "무엇을 안 가져왔는지"를 밝힌다.
// 조용히 빼면 사람은 빠진 걸 모른다 — 조용한 누락도 조용한 실패다.
var migrateExcluded []string

func matchExclude(path string) string {
	for _, ex := range migrateExcludes {
		if ex != "" && strings.Contains(path, ex) {
			return ex
		}
	}
	return ""
}

// migrateScanReport — 어디서 몇 개를 가져왔는지 밝힌다(이슈 #50 ②). v2 fsck 가 세는 수와
// migrate 가 가져오는 수가 다를 수 있어서(동결 체인 등), 사람이 그 차이를 눈으로 확인할
// 수 있어야 한다.
func migrateScanReport(cycles []v2cycle) {
	// 사이클 폴더의 **부모**로 묶는다: <어딘가>/<C0xx-slug>/cycle.yaml → <어딘가>.
	// v2 트리면 rooms/<room>/chains/<chain>, 평평한 배치면 cycles, 동결분이면
	// legacy/archived-chains 로 잡힌다 — 사람이 "어디서 몇 개"를 한눈에 본다.
	roots := map[string]int{}
	for _, c := range cycles {
		parts := strings.Split(c.path, "/")
		root := "(최상위)"
		if len(parts) > 2 {
			root = strings.Join(parts[:len(parts)-2], "/")
		}
		roots[root]++
	}
	stderr("")
	stderr("스캔한 곳(가져온 사이클 수):")
	for _, r := range sortedKeys(roots) {
		stderr("  " + r + "  → " + itoa(roots[r]) + "개")
	}
	if len(migrateExcluded) > 0 {
		stderr("제외됨(--exclude) " + itoa(len(migrateExcluded)) + "개:")
		for _, p := range migrateExcluded {
			stderr("  " + p)
		}
	} else {
		stderr("  (제외 없음 — 동결해 둔 옛 체인 등을 빼려면 --exclude <경로조각> 을 쓴다. 여러 번 가능)")
	}
}

func sortedKeys(m map[string]int) []string {
	var ks []string
	for k := range m {
		ks = append(ks, k)
	}
	sort.Strings(ks)
	return ks
}

// ── 체인별 사이클 위상정렬 (parent 는 반드시 자식보다 먼저 이주) ──
//
// v3 는 부모 사이클이 닫혀 있어야 자식을 연다(gil open 가드). 그러니 parent 를 먼저 심고
// close 한 뒤 자식을 열어야 한다. 같은 체인 안에서 parent 의존을 위상정렬한다.
func topoSortCycles(cycles []v2cycle) ([]v2cycle, bool) {
	byID := map[string]v2cycle{}
	for _, c := range cycles {
		byID[c.id] = c
	}
	visited := map[string]int{} // 0=미방문 1=방문중 2=완료
	var order []v2cycle
	ok := true
	var visit func(id string)
	visit = func(id string) {
		switch visited[id] {
		case 2:
			return
		case 1:
			ok = false // 순환 — v2 데이터 결함. 그래도 진행(부모 못 심으면 루트로).
			return
		}
		visited[id] = 1
		c, exists := byID[id]
		if exists {
			for _, p := range c.parents {
				if _, has := byID[p]; has {
					visit(p)
				}
			}
		}
		visited[id] = 2
		if exists {
			order = append(order, c)
		}
	}
	// 결정성: id 정렬 순으로 방문
	ids := make([]string, 0, len(byID))
	for id := range byID {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		visit(id)
	}
	return order, ok
}

// ── gil migrate ──
// migrateCreated — 이번 실행에서 만든 브랜치들(이슈 #64②). 실행 중 실패하면 여기까지
// 만들어진 것이 남는데, 옛 코드는 말없이 죽었다. 다음 실행은 그 잔여물 때문에 이름 충돌로
// 거부돼, 사람이 손으로 git branch -D 하기 전엔 재시도가 막혔다("원자성"이라 적어둔 것과
// 실제가 어긋난 자리다 — 이름 충돌은 깨끗이 거부하지만 실행 중 실패는 그렇지 않았다).
var migrateCreated []string
var migrateOnce sync.Once

// migrateBase — 이주가 시작된 커밋(이슈 #65). 옛 코드는 체인 루트를 그때그때의 HEAD 에서
// 팠는데, HEAD 는 직전 체인의 마지막 사이클 가지에 가 있다. 그래서 이주된 체인들이 처리
// 순서(알파벳순)대로 **일렬로 적층**됐다 — v2 에서는 서로 독립이던 체인들이다.
//
// 이 적층이 #65 의 뿌리다: 전체맵은 그 조상관계를 날것으로 그려 "없던 이어받음"을 보이고,
// 체인 그래프는 #53 의 엄격한 해석으로 안 그려 "적층이 있다는 사실"을 감춘다. 적층을 없애면
// 두 패널이 자연히 일치하고, 그게 사실과도 맞는다.
var migrateBase string

func cmdMigrate(args []string) {
	fs := newFlags("gil migrate")
	from := fs.str("from", "")
	room := fs.str("room", "")
	excludes := fs.strList("exclude") // 경로 조각(여러 번 가능) — 동결 체인 등을 뺀다
	prefix := fs.str("prefix", "")
	dryRun := fs.boolFlag("dry-run")
	pos := fs.parse(args)
	_ = pos
	if *from == "" {
		die("사용: gil migrate --from <v2-ref> [--room <room>] [--exclude <경로조각>]... [--prefix <접두>] [--dry-run]\n" +
			"  v2(폴더·cycle.yaml) 이력을 현재 브랜치 위에 v3 커밋 그래프로 이주한다.\n" +
			"  먼저 v2 루트에서 이주 브랜치를 파고(git checkout -b) 실행하라 — 대문·존재는 이어받되\n" +
			"  v2 계보 조상 위에 v3 그래프를 새로 자란다.\n" +
			"  --prefix: 이주 브랜치에 접두를 붙여 기존 브랜치와 충돌 회피(예 --prefix v3- → v3-loom).")
	}
	// 접두 검증: 붙는다면 git ref 안전(소문자·숫자·하이픈)해야 한다. 빈 접두는 허용(하위호환).
	if *prefix != "" && !idRe.MatchString(strings.TrimRight(*prefix, "-")) {
		die("거부: --prefix \"" + *prefix + "\"는 소문자·숫자·하이픈만 (git ref 안전)")
	}
	if !gitOK("rev-parse", "--verify", "-q", *from) {
		die("거부: v2 ref \"" + *from + "\" 없음")
	}

	migrateExcludes = *excludes
	cycles := collectV2Cycles(*from, *room)
	if len(cycles) == 0 {
		die("거부: \"" + *from + "\" 에서 이주할 v2 사이클(cycle.yaml)을 찾지 못했다. " +
			"경로가 rooms/<room>/chains/<chain>/C0xx/cycle.yaml 꼴인지 확인하라.")
	}

	// 체인별로 묶는다.
	byChain := map[string][]v2cycle{}
	var chainOrder []string
	for _, c := range cycles {
		if _, seen := byChain[c.chain]; !seen {
			chainOrder = append(chainOrder, c.chain)
		}
		byChain[c.chain] = append(byChain[c.chain], c)
	}
	sort.Strings(chainOrder) // 결정성

	stderr("migrate: v2 ref " + *from + " → v3. 실사이클 " + itoa(len(cycles)) +
		"개 / 체인 " + itoa(len(chainOrder)) + "개.")

	if *dryRun {
		for _, chain := range chainOrder {
			sorted, ok := topoSortCycles(byChain[chain])
			warn := ""
			if !ok {
				warn = "  ⚠ parent 순환 감지(v2 결함) — 일부 루트化"
			}
			stderr("  체인 " + chain + ": " + itoa(len(sorted)) + " 사이클" + warn)
			for _, c := range sorted {
				stderr("    " + v2ToV3ID(c.id) + " parent=" + orNull(v2ToV3ID(c.primaryParent())) +
					" verdict=" + orDefault(c.verdict, "-") + " → " + verdictToClosureKind(c))
			}
		}
		if *prefix != "" {
			stderr("  (접두 " + *prefix + " → 브랜치 " + *prefix + "<chain>)")
		}
		migrateScanReport(cycles)
		migrateVerdictSummary(byChain)
		stderr("dry-run: 커밋하지 않음. 실제 이주는 --dry-run 없이.")
		return
	}

	// ── 원자성 pre-flight: 만들 브랜치가 하나라도 이미 있으면 *아무것도 만들기 전에* 거부한다.
	// (부분 실패로 브랜치 잔재가 남던 실사용 결함. --prefix 로 네임스페이스 주면 회피된다.)
	// 이름이 v3 에서 유효한지도 *미리* 본다(이슈 #64② 계열). v2 폴더 이름은 공백 등 git ref
	// 로 못 쓰는 글자를 담을 수 있는데, 그걸 실행 중에 만나면 이미 만든 브랜치를 남긴 채
	// 죽는다 — 검사할 수 있는 걸 실행 중까지 미루지 않는다.
	var badNames []string
	for _, chain := range chainOrder {
		v3chain := *prefix + v2ToV3ID(chain)
		if !idRe.MatchString(v3chain) {
			badNames = append(badNames, "체인 \""+chain+"\" → \""+v3chain+"\"")
		}
		for _, c := range byChain[chain] {
			if cy := v2ToV3ID(c.id); !idRe.MatchString(cy) {
				badNames = append(badNames, "사이클 \""+c.id+"\" → \""+cy+"\"")
			}
		}
	}
	if len(badNames) > 0 {
		die("거부: v3 이름으로 못 쓰는 것이 있다(소문자·숫자·하이픈만) — 아무것도 만들지 않았다:\n" +
			"    " + strings.Join(badNames, "\n    ") + "\n" +
			"  v2 폴더 이름을 고치거나, 그 체인을 --exclude 로 빼고 이주하라.")
	}

	var collide []string
	for _, chain := range chainOrder {
		v3chain := *prefix + v2ToV3ID(chain)
		if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+v3chain) {
			collide = append(collide, v3chain)
		}
		for _, c := range byChain[chain] {
			cb := cycleBranch(v3chain, v2ToV3ID(c.id))
			if gitOK("rev-parse", "--verify", "-q", "refs/heads/"+cb) {
				collide = append(collide, cb)
			}
		}
	}
	if len(collide) > 0 {
		show := collide
		if len(show) > 8 {
			show = append(show[:8], "…("+itoa(len(collide))+"개)")
		}
		die("거부: 이주 브랜치가 기존 브랜치와 충돌한다: " + strings.Join(show, " ") + "\n" +
			"  --prefix <접두>(예 --prefix v3-)로 네임스페이스를 줘 충돌을 피하라. " +
			"아무 커밋도 만들지 않았다(원자성).")
	}

	migrated := 0
	for _, chain := range chainOrder {
		v3chain := *prefix + v2ToV3ID(chain)
		sorted, cyclesOK := topoSortCycles(byChain[chain])
		if !cyclesOK {
			stderr("  ⚠ 체인 " + chain + ": parent 순환 — 일부 사이클을 루트로 이주한다.")
		}

		// 체인 루트: v2 chain.md 목적을 못 읽는 환경도 있으니, 첫 사이클 title 로 목적을 채운다.
		chainPurposeText := "[migrate] v2 체인 " + chain + " 이주"
		if p := v2ChainPurpose(*from, chain); p != "" {
			chainPurposeText = "[migrate] " + p
		}
		if migrateBase == "" {
			// 이주 시작 지점을 한 번만 붙잡는다(이슈 #65). 모든 체인 루트는 **여기서** 갈라진다.
			migrateBase = strings.TrimSpace(git("rev-parse", "HEAD"))
		}
		migrateOnce.Do(func() {
			onDie(func() {
				if len(migrateCreated) == 0 {
					return
				}
				stderr("")
				stderr("⚠ 이주가 중간에 멈췄다 — 여기까지 만들어진 것이 남아 있다(" +
					itoa(len(migrateCreated)) + "개 브랜치):")
				stderr("    " + strings.Join(migrateCreated, " "))
				stderr("  다시 돌리기 전에 지워라(안 지우면 이름 충돌로 거부된다):")
				stderr("    git branch -D " + strings.Join(migrateCreated, " "))
				stderr("  (지우는 건 사람의 판단으로 남긴다 — 이주 산물이라도 말없이 지우지 않는다.)")
			})
		})
		migrateChainRoot(v3chain, chain, chainPurposeText)
		migrateCreated = append(migrateCreated, v3chain)

		// migratedInChain — 이 체인에서 이미 이주된 사이클(위상정렬이 부모 먼저를 보장한다).
		// 옛 코드는 "닫힌 부모"만 계보로 인정해, v2 에서 pending 으로 남은 부모의 계보를 통째로
		// 버렸다(이슈 #61: 우리 경우 16건). v2 가 기록한 parent 는 "여기서 이어 열었다"는
		// 사실이지 "부모가 닫혔다"는 주장이 아니다 — 사실을 버리지 않는다.
		migratedInChain := map[string]bool{}
		openParents := map[string]string{} // 자식 → pending 으로 끝난 부모(보고용)
		for _, c := range sorted {
			migrateCycle(v3chain, c, migratedInChain, openParents)
			migrateCreated = append(migrateCreated, cycleBranch(v3chain, v2ToV3ID(c.id)))
			migratedInChain[v2ToV3ID(c.id)] = true
			migrated++
		}
		// 부모가 닫히지 않은 채 이어진 사이클을 그 자리에서 알린다(이슈 #61 제안 3). 조용하면
		// 이주본을 "계보 보존됨"으로 읽게 된다 — 실제로 그렇게 읽혔다.
		if len(openParents) > 0 {
			stderr("  ⚠ 체인 " + chain + ": 부모가 닫히지 않은 채 이어진 사이클 " + itoa(len(openParents)) + "건 —")
			stderr("    v2 에서 그렇게 열렸다는 사실 그대로 계보를 심는다(v3 의 '닫힌 끝에서만' 규칙과는 다르다).")
			for k, v := range openParents {
				stderr("      " + k + " ← " + v + " (부모 종결=pending)")
			}
		}
	}

	stderr("migrate: 완료 — " + itoa(migrated) + " 사이클을 v3 그래프로 이주.")
	stderr("검증: gil fsck --all  |  gil log --all  |  뷰어로 그래프 확인.")
	if migrated != len(cycles) {
		stderr("  ⚠ 이주 수(" + itoa(migrated) + ") ≠ 수집 수(" + itoa(len(cycles)) + ") — 확인 요망.")
	}
}

// v2ChainPurpose — v2 chain.md 첫 목적 줄을 최선노력으로 읽는다(없으면 "").
func v2ChainPurpose(ref, chain string) string {
	// v2 트리에서 이 체인의 chain.md 경로를 찾는다.
	out, err := gitTry("ls-tree", "-r", "--name-only", ref)
	if err != nil {
		return ""
	}
	for _, path := range strings.Split(out, "\n") {
		path = strings.TrimSpace(path)
		if strings.HasSuffix(path, "/chains/"+chain+"/chain.md") {
			blob, err := gitTry("show", ref+":"+path)
			if err != nil {
				return ""
			}
			return firstMeaningfulLine(blob)
		}
	}
	return ""
}

// firstMeaningfulLine — 마크다운에서 헤더(#)·빈 줄을 건너뛴 첫 실질 줄.
func firstMeaningfulLine(text string) string {
	for _, line := range strings.Split(text, "\n") {
		t := strings.TrimSpace(line)
		if t == "" || strings.HasPrefix(t, "#") {
			continue
		}
		return t
	}
	return ""
}

// migrateChainRoot — v3 체인 루트 커밋([migrate] 표식). 현재 위치(대문/v2 조상)에서 분기.
func migrateChainRoot(v3chain, v2chain, purpose string) {
	subject := "gil " + v3chain + " chain: " + purpose + " [migrate]"
	body := "체인 [" + v3chain + "] 을 v2 체인 \"" + v2chain + "\" 에서 이주(migrate).\n\n" +
		"목적: " + purpose + "\n\n" +
		"이 커밋은 v2→v3 이주 산물이다(v2 SPEC 이주 규정 계승). 이후 사이클·스텝이 이 루트에서 자란다."
	tr := [][2]string{
		{"Gil-Chain", v3chain}, {"Gil-Kind", "chain-root"},
		{"Gil-Chain-Purpose", purpose},
		{"Gil-Migrate", "chain"}, {"Gil-Migrated-From", v2chain},
	}
	// 체인 루트는 이주 시작점에서 갈라진다 — 앞 체인 위에 쌓지 않는다(이슈 #65).
	commitOn(v3chain, orDefault(migrateBase, "HEAD"), subject, body, tr, true)
}

// migrateCycle — v2 사이클 하나를 v3 사이클(define→verify→종결→close)로 이주한다.
//
// 압축 매핑: hypothesis+design→define(s1, open이 새김), verification→verify(s2),
// analysis+report+verdict→종결 스텝(success/fail/pending, s3). 그 뒤 close(fail·pending 제외).
// migrateClosedCycle — 이미 이주된 사이클이 close 로 봉인됐나. pending 종결(사람 대기)로
// 끝난 v2 사이클은 닫히지 않는다 — 그 위에 이어 연 자식을 "닫힌 끝에서의 계승"이라 부를 수
// 없어, 사실대로 보고만 하고 계보는 심는다(이슈 #61 제안 2).
func migrateClosedCycle(v3chain, v3cyc string) bool {
	fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Cycle") + fsep + trailer("Gil-Kind") + sep
	out := gitlog("--format="+fmtStr, "refs/heads/"+cycleBranch(v3chain, v3cyc))
	for _, rec := range strings.Split(out, sep) {
		ch, rest, _ := cut(rec, fsep)
		cy, kind, _ := cut(rest, fsep)
		if strings.TrimSpace(ch) == v3chain && strings.TrimSpace(cy) == v3cyc &&
			strings.TrimSpace(kind) == "close" {
			return true
		}
	}
	return false
}

func migrateCycle(v3chain string, c v2cycle, migratedInChain map[string]bool, openParents map[string]string) {
	v3cyc := v2ToV3ID(c.id)
	cb := cycleBranch(v3chain, v3cyc)

	// s1 define — v2 hypothesis(+design 흡수). open 대신 직접 커밋(가드 우회: 이주는 v2 순서를
	// 이미 위상정렬로 보장한다). 하지만 부모 사이클 닫힘·목적 등 v3 의미는 트레일러로 싣는다.
	// 부모(들): 같은 체인에서 이미 이주·닫힌 부모만 Gil-Cycle-Parent 로 기록(머지=여러 부모).
	// 부모(들): 이 체인에서 이미 이주된 부모를 모두 계보로 남긴다(이슈 #61). 닫힘 여부로
	// 거르지 않는다 — v2 의 parent 는 "여기서 이어 열었다"는 사실이고, 그 사실을 버리면
	// 남는 건 "같은 체인에 속한 N개 사이클"이라는 집합뿐이라 어느 결론이 어느 결론 위에
	// 서 있는지를 잃는다. 이주 범위 밖(--only/--exclude)이라 없는 부모만 빠진다.
	var v3parents []string
	var missing []string
	for _, p := range c.parents {
		pv3 := v2ToV3ID(p)
		if migratedInChain[pv3] {
			v3parents = append(v3parents, pv3)
		} else if strings.TrimSpace(p) != "" {
			missing = append(missing, pv3)
		}
	}
	if len(missing) > 0 {
		// 조용히 빠지면 "계보 보존됨"으로 읽힌다(이슈 #61 제안 3).
		stderr("    ⚠ " + v2ToV3ID(c.id) + ": 부모 " + strings.Join(missing, ",") +
			" 가 이주 범위 밖이라 계보를 못 심는다(--only/--exclude 확인).")
	}
	author := orDefault(c.author, "migrate")
	purpose := orDefault(c.title, "(v2 "+c.id+" 이주 — 목적 미기재)")

	defineSubj := "gil " + v3chain + "/" + v3cyc + "/s1 define: " + purpose + " [migrate]"
	defineBody := migrateStepBody("define", c,
		"문제 정의(v2 hypothesis+design 흡수). v2 사이클 "+c.id+" 의 목적/가설을 이주.")
	dtr := [][2]string{
		{"Gil-Chain", v3chain}, {"Gil-Cycle", v3cyc},
		{"Gil-Step", "s1"}, {"Gil-Kind", "define"}, {"Gil-Parent", "null"},
		{"Gil-Cycle-Author", author}, {"Gil-Cycle-Purpose", purpose},
		{"Gil-Migrate", "cycle"}, {"Gil-Migrated-From", c.id},
	}
	for _, p := range v3parents {
		dtr = append(dtr, [2]string{"Gil-Cycle-Parent", p})
	}
	for _, ln := range c.lineage {
		dtr = append(dtr, [2]string{"Gil-Cycle-Lineage", ln}) // 교훈계승(다른 체인)
	}
	// 사이클 = 체인 안 git 가지. **부모 사이클의 끝에서** 분기한다(이슈 #61).
	//
	// 옛 코드는 언제나 체인 루트에서 팠다. 그래서 트레일러에 부모를 적어도 커밋 그래프에서는
	// 모든 사이클이 체인 루트의 형제였고 — 실사용 실측: 인접쌍 37개 전부 독립, merge-base 가
	// 예외 없이 체인 루트 — 계보를 위상에서 읽는 뷰어·#53 판정에는 통째로 안 보였다.
	// #53 이 "없던 이어받음이 생긴다"였다면 이건 그 짝인 "있던 이어받음이 사라진다"다.
	from := v3chain
	if len(v3parents) > 0 {
		// 여러 부모(v2 머지)면 첫 부모 위에 얹고 나머지는 Gil-Cycle-Parent 트레일러로 남는다.
		if tip := cycleBranch(v3chain, v3parents[0]); gitOK("rev-parse", "--verify", "-q", "refs/heads/"+tip) {
			from = tip
			if openParents != nil && !migrateClosedCycle(v3chain, v3parents[0]) {
				openParents[v3cyc] = v3parents[0]
			}
		}
	}
	commitOn(cb, from, defineSubj, defineBody, dtr, true)

	// s2 verify — v2 verification.
	verifySubj := "gil " + v3chain + "/" + v3cyc + "/s2 verify: 검증 [migrate]"
	verifyBody := migrateStepBody("verify", c,
		"검증(v2 verification 이주). v2 사이클 "+c.id+" 의 검증 단계.")
	vtr := [][2]string{
		{"Gil-Chain", v3chain}, {"Gil-Cycle", v3cyc},
		{"Gil-Step", "s2"}, {"Gil-Kind", "verify"}, {"Gil-Parent", "s1"},
		{"Gil-Migrate", "step"}, {"Gil-Migrated-From", c.id},
	}
	commitOn(cb, "", verifySubj, verifyBody, vtr, true)

	// s3 종결 — verdict → success/fail/pending.
	kind := verdictToClosureKind(c)
	closureSubj := "gil " + v3chain + "/" + v3cyc + "/s3 " + kind + ": 종결 [migrate]"
	closureBody := migrateStepBody(kind, c, migrateClosureNote(c, kind))
	ctr := [][2]string{
		{"Gil-Chain", v3chain}, {"Gil-Cycle", v3cyc},
		{"Gil-Step", "s3"}, {"Gil-Kind", kind}, {"Gil-Parent", "s2"},
		{"Gil-Migrate", "step"}, {"Gil-Migrated-From", c.id},
	}
	// 원 verdict 를 **무손실로** 보존한다(이슈 #50). 매핑 정책이 뒤에 바뀌어도 여기서 복구할
	// 수 있고, inconclusive 와 partial 이 그래프 위에서 구분된다 — 본문 산문은 기계가 못 읽는다.
	ctr = append(ctr, [2]string{"Gil-V2-Verdict", orDefault(strings.TrimSpace(c.verdict), "(없음)")})
	if kind == "fail" {
		// 죽은 잎은 되돌아갈 조상 define 을 기록(벽의 지도). 이주에선 자기 s1 로.
		ctr = append(ctr, [2]string{"Gil-Backtrack", "s1"})
	}
	if kind == "success" && c.superBy != "" {
		// 무효화된 성공(superseded_by) — 후속을 가리키는 포인터를 보존한다.
		ctr = append(ctr, [2]string{"Gil-Superseded-By", v2ToV3ID(c.superBy)})
	}
	commitOn(cb, "", closureSubj, closureBody, ctr, true)

	// close — 닫힌 사이클만 봉인한다. fail·pending 종결은 close 하지 않는다:
	//   fail=죽은 잎(닫을 산 잎 없음), pending=사람 대기(아직 미종결).
	//   v3 close 는 산 잎(success)을 요구하므로 success 종결만 봉인 가능하다.
	if kind == "success" && strings.TrimSpace(c.status) != "open" {
		verdict := orDefault(c.verdict, "supported")
		closeSubj := "gil " + v3chain + "/" + v3cyc + " close: " + verdict + " [migrate]"
		closeBody := "사이클 봉인(v2 이주). 산 잎 [s3]. 판정: " + verdict + ". v2: " + c.id + "."
		cltr := [][2]string{
			{"Gil-Chain", v3chain}, {"Gil-Cycle", v3cyc},
			{"Gil-Kind", "close"}, {"Gil-Verdict", verdict},
			{"Gil-Migrate", "close"}, {"Gil-Migrated-From", c.id},
		}
		commitOn(cb, "", closeSubj, closeBody, cltr, true)
	}
}

// migrateClosureNote — 종결 스텝 본문 머리말(verdict 의미를 사람이 읽게).
func migrateClosureNote(c v2cycle, kind string) string {
	switch kind {
	case "fail":
		return "벽(죽은 잎). v2 verdict=rejected — 이 가설은 기각됐다. v2 사이클 " + c.id + " 이주."
	case "pending":
		v := strings.TrimSpace(c.verdict)
		if v == "" {
			return "사람 대기. v2 에 판정(verdict)이 없다 — 성공으로 단정하지 않고 사람 판단을 " +
				"기다린다(이슈 #50: 없는 성공을 날조하지 않는다). v2 사이클 " + c.id + " 이주."
		}
		return "사람 대기. v2 verdict=" + v + " — 지지도 기각도 아닌 결말이라 success/fail 중 " +
			"어느 쪽으로도 접지 않았다(그렇게 접으면 이력이 원본보다 낙관적인 거짓말이 된다). " +
			"사람이 다시 보고 approve/reject 로 결말을 지어라. v2 사이클 " + c.id + " 이주."
	default: // success
		note := "산 잎. v2 verdict=" + orDefault(c.verdict, "supported") + " — 명확히 지지된 결말. v2 사이클 " + c.id + " 종결."
		if c.superBy != "" {
			note += " ⚠ 이 결론은 이후 " + c.superBy + " 로 무효화(superseded)됐다."
		}
		return note
	}
}

// migrateStepBody — 이주 스텝 본문. v2 메타를 사람이 읽을 보고서 머리말로 싣는다.
// (v2 단계별 md 원문 전체 이주는 향후 확장; 지금은 cycle.yaml 무손실 + 메타 표.)
func migrateStepBody(kind string, c v2cycle, note string) string {
	var b strings.Builder
	b.WriteString("[migrate] ")
	b.WriteString(note)
	b.WriteString("\n\n")
	b.WriteString("| v2 필드 | 값 |\n|---|---|\n")
	b.WriteString("| id | " + c.id + " |\n")
	b.WriteString("| chain | " + c.chain + " |\n")
	b.WriteString("| parent | " + orDefault(strings.Join(c.parents, ", "), "null") + " |\n")
	b.WriteString("| status | " + orDefault(c.status, "-") + " |\n")
	b.WriteString("| verdict | " + orDefault(c.verdict, "-") + " |\n")
	b.WriteString("| opened | " + orDefault(c.opened, "-") + " |\n")
	b.WriteString("| closed | " + orDefault(c.closed, "-") + " |\n")
	b.WriteString("| author | " + orDefault(c.author, "-") + " |\n")
	if len(c.lineage) > 0 {
		b.WriteString("| lineage | " + strings.Join(c.lineage, ", ") + " |\n")
	}
	if c.superBy != "" {
		b.WriteString("| superseded_by | " + c.superBy + " |\n")
	}
	b.WriteString("\n> **title**: " + orDefault(c.title, "(없음)") + "\n")
	return b.String()
}

// migrateVerdictSummary — 이주가 결말을 어떻게 접었는지 먼저 밝힌다(이슈 #50).
//
// 사람이 알아야 할 건 "몇 개가 사람 판단으로 남는가"다. 그걸 이주 **뒤에** 알면 이미 71개
// 브랜치가 생긴 뒤라 되돌리기 번거롭다. dry-run 에서 미리 세어 보여주고, 다음 한 수까지 준다.
func migrateVerdictSummary(byChain map[string][]v2cycle) {
	n := map[string]int{}
	var needHuman []string
	for _, cs := range byChain {
		for _, c := range cs {
			k := verdictToClosureKind(c)
			n[k]++
			if k == "pending" {
				needHuman = append(needHuman,
					v2ToV3ID(c.id)+"(verdict="+orDefault(c.verdict, "없음")+")")
			}
		}
	}
	stderr("")
	stderr("결말 매핑: 산 잎 " + itoa(n["success"]) + " · 죽은 잎 " + itoa(n["fail"]) +
		" · 사람 판단 대기 " + itoa(n["pending"]))
	if len(needHuman) == 0 {
		return
	}
	stderr("  ▸ 아래 " + itoa(len(needHuman)) + " 개는 v2 에서 지지도 기각도 아닌 결말이라 " +
		"success 로 접지 않았다(이슈 #50).")
	stderr("    그렇게 접으면 이주된 이력이 원본보다 낙관적인 거짓말이 된다 — 없는 성공을 " +
		"날조하지 않는다.")
	stderr("    이주 뒤 사람이 다시 보고 결말을 지어라: gil approve <chain>/<cycle>  또는  " +
		"gil reject <chain>/<cycle> --to s1")
	for _, x := range needHuman {
		stderr("      " + x)
	}
}
