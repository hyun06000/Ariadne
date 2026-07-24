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
//                        partial→success(+주석), (verdict 없음 & closed)→success,
//                        (null & status:open)→pending.
//   구조: chain→Gil-Chain, C0xx-slug→Gil-Cycle(소문자화), parent→--parent(같은 체인),
//         lineage→교훈계승(목적문·트레일러), title/author/opened/closed→메타.
//   이주 표식: 커밋 subject 에 [migrate], Gil-Kind: migrate(체인·사이클 루트),
//             Gil-Migrated-From: <v2 id> (v2 SPEC 이주 규정 계승).
package main

import (
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

// ── verdict → v3 종결 kind (상현님 확정) ──
func verdictToClosureKind(c v2cycle) string {
	v := strings.ToLower(strings.TrimSpace(c.verdict))
	switch v {
	case "rejected":
		return "fail"
	case "supported", "success", "partial":
		return "success"
	case "", "null", "~":
		// verdict 없음: 닫힌 사이클이면 완결로 보고 success, 열려 있으면 사람 대기(pending).
		if strings.TrimSpace(c.status) == "open" {
			return "pending"
		}
		return "success"
	default:
		// 알 수 없는 verdict 값 — 보수적으로 success(닫힘)/pending(열림).
		if strings.TrimSpace(c.status) == "open" {
			return "pending"
		}
		return "success"
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
		cycles = append(cycles, c)
	}
	return cycles
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
func cmdMigrate(args []string) {
	fs := newFlags("gil migrate")
	from := fs.str("from", "")
	room := fs.str("room", "")
	prefix := fs.str("prefix", "")
	dryRun := fs.boolFlag("dry-run")
	pos := fs.parse(args)
	_ = pos
	if *from == "" {
		die("사용: gil migrate --from <v2-ref> [--room <room>] [--prefix <접두>] [--dry-run]\n" +
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
		stderr("dry-run: 커밋하지 않음. 실제 이주는 --dry-run 없이.")
		return
	}

	// ── 원자성 pre-flight: 만들 브랜치가 하나라도 이미 있으면 *아무것도 만들기 전에* 거부한다.
	// (부분 실패로 브랜치 잔재가 남던 실사용 결함. --prefix 로 네임스페이스 주면 회피된다.)
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
		migrateChainRoot(v3chain, chain, chainPurposeText)

		closedInChain := map[string]bool{}
		for _, c := range sorted {
			migrateCycle(v3chain, c, closedInChain)
			closedInChain[v2ToV3ID(c.id)] = true
			migrated++
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
	commitOn(v3chain, "HEAD", subject, body, tr, true)
}

// migrateCycle — v2 사이클 하나를 v3 사이클(define→verify→종결→close)로 이주한다.
//
// 압축 매핑: hypothesis+design→define(s1, open이 새김), verification→verify(s2),
// analysis+report+verdict→종결 스텝(success/fail/pending, s3). 그 뒤 close(fail·pending 제외).
func migrateCycle(v3chain string, c v2cycle, closedInChain map[string]bool) {
	v3cyc := v2ToV3ID(c.id)
	cb := cycleBranch(v3chain, v3cyc)

	// s1 define — v2 hypothesis(+design 흡수). open 대신 직접 커밋(가드 우회: 이주는 v2 순서를
	// 이미 위상정렬로 보장한다). 하지만 부모 사이클 닫힘·목적 등 v3 의미는 트레일러로 싣는다.
	// 부모(들): 같은 체인에서 이미 이주·닫힌 부모만 Gil-Cycle-Parent 로 기록(머지=여러 부모).
	var v3parents []string
	for _, p := range c.parents {
		if closedInChain[v2ToV3ID(p)] {
			v3parents = append(v3parents, v2ToV3ID(p))
		}
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
	// 사이클 = 체인 안 git 가지. 체인 팁(또는 닫힌 부모 사이클 끝)에서 분기.
	commitOn(cb, v3chain, defineSubj, defineBody, dtr, true)

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
		return "사람 대기. v2 status=open·verdict 미정 — 미종결 사이클을 이주(사람 판단 대기)."
	default: // success
		note := "산 잎. v2 사이클 " + c.id + " 종결(누적 종합)."
		if strings.ToLower(strings.TrimSpace(c.verdict)) == "partial" {
			note = "산 잎(부분 지지). v2 verdict=partial — 조건부 성공으로 이주. v2: " + c.id + "."
		}
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
