// gil — 길, GIt for Language model. Go 참조-후보 구현
// (loom/C012: fsck·log → loom/C014: open·close 추가. 계약 부분집합 확장).
//
// Ariadne Spec의 구현 독립 계약(§7)에 따라, 이 바이너리는 conformance.py의 판정으로만
// 자격을 얻는다. 이 사이클의 범위: fsck(R1~R8)·log·open·close(--git 제외).
// 나머지 명령·플래그는 정직하게 "미구현"을 알린다.
//
// 외부 의존성 0 — Go 표준 라이브러리만.
package main

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

var idRe = regexp.MustCompile(`^C(\d{3,})-[a-z0-9][a-z0-9-]*$`) // R1
var keyRe = regexp.MustCompile(`^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$`)

type cycle struct {
	dir     string
	fields  map[string]string
	parents []string
	lineage []string
}

// ---------- 파싱 (참조 구현과 동일 규칙) ----------

func parseValue(raw string) []string {
	raw = strings.TrimSpace(raw)
	if strings.HasPrefix(raw, `"`) {
		if end := strings.Index(raw[1:], `"`); end != -1 {
			return []string{raw[1 : 1+end]}
		}
		return []string{raw[1:]}
	}
	if strings.HasPrefix(raw, "[") {
		end := strings.Index(raw, "]")
		inner := raw[1:]
		if end != -1 {
			inner = raw[1:end]
		}
		var out []string
		for _, v := range strings.Split(inner, ",") {
			v = strings.Trim(strings.TrimSpace(v), `"`)
			if v != "" {
				out = append(out, v)
			}
		}
		return out
	}
	// 후행 주석 제거
	if i := strings.Index(raw, " #"); i != -1 {
		raw = raw[:i]
	}
	raw = strings.TrimSpace(raw)
	if raw == "null" || raw == "~" || raw == "" {
		return nil
	}
	return []string{raw}
}

func parseCycleYaml(path string) (map[string]string, []string, []string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, nil, nil, err
	}
	fields := map[string]string{}
	var parents, lineage []string
	for _, line := range strings.Split(string(data), "\n") {
		s := strings.TrimSpace(line)
		if s == "" || strings.HasPrefix(s, "#") {
			continue
		}
		m := keyRe.FindStringSubmatch(line)
		if m == nil {
			continue
		}
		vals := parseValue(m[2])
		switch m[1] {
		case "parent":
			parents = vals
		case "lineage":
			lineage = vals
		default:
			if len(vals) > 0 {
				fields[m[1]] = vals[0]
			} else {
				fields[m[1]] = ""
			}
		}
	}
	return fields, parents, lineage, nil
}

func loadChain(chainDir string) ([]cycle, error) {
	entries, err := os.ReadDir(chainDir)
	if err != nil {
		return nil, err
	}
	var out []cycle
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		yp := filepath.Join(chainDir, e.Name(), "cycle.yaml")
		if _, err := os.Stat(yp); err != nil {
			continue
		}
		f, p, l, err := parseCycleYaml(yp)
		if err != nil {
			return nil, err
		}
		out = append(out, cycle{dir: e.Name(), fields: f, parents: p, lineage: l})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].dir < out[j].dir })
	return out, nil
}

func scanChains(root string) (map[string][]cycle, error) {
	entries, err := os.ReadDir(root)
	if err != nil {
		return nil, fmt.Errorf("체인 루트가 없다: %s", root)
	}
	chains := map[string][]cycle{}
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		recs, err := loadChain(filepath.Join(root, e.Name()))
		if err != nil {
			return nil, err
		}
		chains[e.Name()] = recs
	}
	return chains, nil
}

// ---------- 토폴로지 (Kahn, id 오름차순 동순위) ----------

func toposort(ids []string, parentsOf map[string][]string) (order []string, stuck []string) {
	children := map[string][]string{}
	indeg := map[string]int{}
	idset := map[string]bool{}
	for _, id := range ids {
		idset[id] = true
		indeg[id] = 0
	}
	for id, ps := range parentsOf {
		for _, p := range ps {
			if idset[p] {
				children[p] = append(children[p], id)
				indeg[id]++
			}
		}
	}
	var ready []string
	for _, id := range ids {
		if indeg[id] == 0 {
			ready = append(ready, id)
		}
	}
	sort.Strings(ready)
	done := map[string]bool{}
	for len(ready) > 0 {
		n := ready[0]
		ready = ready[1:]
		order = append(order, n)
		done[n] = true
		kids := children[n]
		sort.Strings(kids)
		for _, ch := range kids {
			indeg[ch]--
			if indeg[ch] == 0 {
				ready = append(ready, ch)
			}
		}
		sort.Strings(ready)
	}
	for _, id := range ids {
		if !done[id] {
			stuck = append(stuck, id)
		}
	}
	sort.Strings(stuck)
	return order, stuck
}

// ---------- fsck (R1~R8) ----------

// collectFsck는 위반 목록을 수집만 한다 — fsck 출력과 open/close의 쓰기 규율이 공유한다.
func collectFsck(root string) (violations []string, nChains, nCycles int, err error) {
	chains, err := scanChains(root)
	if err != nil {
		return nil, 0, 0, err
	}
	idsByChain := map[string]map[string]bool{}
	for ch, recs := range chains {
		idsByChain[ch] = map[string]bool{}
		for _, r := range recs {
			idsByChain[ch][r.fields["id"]] = true
		}
	}
	add := func(rule, loc, msg string) { violations = append(violations, fmt.Sprintf("%s  %s: %s", rule, loc, msg)) }

	chainNames := sortedKeys(chains)
	total := 0
	for _, ch := range chainNames {
		numbers := map[string][]string{}
		valid := idsByChain[ch]
		parentsOf := map[string][]string{}
		var idList []string
		for _, r := range chains[ch] {
			total++
			cid := r.fields["id"]
			loc := ch + "/" + r.dir
			if cid == "" {
				add("R1", loc, "id 필드가 없다")
				continue
			}
			idList = append(idList, cid)
			if m := idRe.FindStringSubmatch(cid); m == nil {
				add("R1", loc, "id '"+cid+"' 형식 위반")
			} else {
				numbers[m[1]] = append(numbers[m[1]], cid)
			}
			if r.fields["chain"] != ch {
				add("R4", loc, "chain 필드 '"+r.fields["chain"]+"' ≠ 소속 체인 '"+ch+"'")
			}
			if cid != r.dir {
				add("R5", loc, "id '"+cid+"' ≠ 디렉토리명 '"+r.dir+"'")
			}
			var localParents []string
			for _, p := range r.parents {
				if strings.Contains(p, "/") {
					add("R3", loc, "parent '"+p+"'는 로컬 id여야 한다")
				} else if !valid[p] {
					add("R6", loc, "parent '"+p+"'가 존재하지 않는다")
				} else {
					localParents = append(localParents, p)
				}
			}
			parentsOf[cid] = localParents
			for _, l := range r.lineage {
				if strings.Count(l, "/") != 1 {
					add("R3", loc, "lineage '"+l+"'는 전역 표기여야 한다")
					continue
				}
				parts := strings.SplitN(l, "/", 2)
				if parts[0] == ch {
					add("R3", loc, "lineage '"+l+"'가 같은 체인을 가리킨다")
				} else if other, ok := idsByChain[parts[0]]; !ok || !other[parts[1]] {
					add("R2", loc, "lineage '"+l+"'가 존재하지 않는다")
				}
			}
			status, closed := r.fields["status"], r.fields["closed"]
			if status == "closed" && closed == "" {
				add("R8", loc, "status가 closed인데 closed 일자가 없다")
			} else if status == "open" && closed != "" {
				add("R8", loc, "status가 open인데 closed 일자가 있다")
			}
		}
		for num, dupes := range numbers {
			if len(dupes) > 1 {
				sort.Strings(dupes)
				add("R1", ch, "번호 "+num+" 중복: "+strings.Join(dupes, ", "))
			}
		}
		if _, stuck := toposort(idList, parentsOf); len(stuck) > 0 {
			add("R7", ch, "순환 참조: "+strings.Join(stuck, ", "))
		}
	}
	sort.Strings(violations)
	return violations, len(chains), total, nil
}

func fsck(root string) int {
	violations, nChains, total, err := collectFsck(root)
	if err != nil {
		fmt.Fprintf(os.Stderr, "오류: %v\n", err)
		return 1
	}
	if len(violations) > 0 {
		for _, v := range violations {
			fmt.Println(v)
		}
		fmt.Fprintf(os.Stderr, "\n검사: 체인 %d개, 사이클 %d개 — 위반 %d건\n", nChains, total, len(violations))
		return 1
	}
	fmt.Printf("OK — 체인 %d개, 사이클 %d개, 위반 0건 (스키마 v0.2)\n", nChains, total)
	return 0
}

// ---------- log ----------

func logCmd(root string) int {
	chains, err := scanChains(root)
	if err != nil {
		fmt.Fprintf(os.Stderr, "오류: %v\n", err)
		return 1
	}
	for _, ch := range sortedKeys(chains) {
		recs := chains[ch]
		if len(recs) == 0 {
			continue
		}
		byID := map[string]cycle{}
		parentsOf := map[string][]string{}
		var idList []string
		for _, r := range recs {
			cid := r.fields["id"]
			if cid == "" {
				fmt.Fprintf(os.Stderr, "오류: %s/%s: id 필드가 없다\n", ch, r.dir)
				return 1
			}
			if _, dup := byID[cid]; dup {
				fmt.Fprintf(os.Stderr, "오류: 체인 '%s': id '%s' 중복\n", ch, cid)
				return 1
			}
			byID[cid] = r
			idList = append(idList, cid)
		}
		for cid, r := range byID {
			for _, p := range r.parents {
				if _, ok := byID[p]; !ok {
					fmt.Fprintf(os.Stderr, "오류: 체인 '%s': %s의 parent '%s'가 존재하지 않는다 (끊어진 참조)\n", ch, cid, p)
					return 1
				}
			}
			parentsOf[cid] = r.parents
		}
		order, stuck := toposort(idList, parentsOf)
		if len(stuck) > 0 {
			fmt.Fprintf(os.Stderr, "오류: 체인 '%s': 순환 참조 — %s\n", ch, strings.Join(stuck, ", "))
			return 1
		}
		fmt.Printf("=== chain: %s — 사이클 %d개 ===\n\n", ch, len(recs))
		for _, cid := range order {
			r := byID[cid]
			mark := "●"
			extra := ""
			if len(r.parents) > 1 {
				extra = "  ◀ 병합: " + strings.Join(r.parents, " + ")
			}
			if len(r.lineage) > 0 {
				extra += "  ⇠ lineage: " + strings.Join(r.lineage, ", ")
			}
			fmt.Printf("%s  %s [%s] %s%s\n", mark, cid, r.fields["status"], r.fields["title"], extra)
		}
		fmt.Println("\n계보 (토폴로지 순서, 동순위는 id 오름차순):")
		for _, cid := range order {
			ps := parentsOf[cid]
			if len(ps) == 0 {
				fmt.Printf("  %s  ←  (root)\n", cid)
			} else {
				fmt.Printf("  %s  ←  %s\n", cid, strings.Join(ps, ", "))
			}
		}
		fmt.Println()
	}
	return 0
}

func sortedKeys(m map[string][]cycle) []string {
	var out []string
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// ---------- open / close (쓰기 porcelain — loom/C014) ----------

var slugRe = regexp.MustCompile(`^[a-z0-9][a-z0-9-]*$`) // R1의 슬러그 부분

// chainError: 참조 구현의 ChainError에 대응 — 메시지를 stderr에 내고 exit 1.
type chainError struct{ msg string }

func (e chainError) Error() string { return e.msg }

func cerr(format string, a ...interface{}) error { return chainError{fmt.Sprintf(format, a...)} }

func templateDir(chainsRoot string) string {
	return filepath.Clean(filepath.Join(chainsRoot, "..", "_template"))
}

func fsckOrReport(chainsRoot string) error {
	violations, _, _, err := collectFsck(chainsRoot)
	if err != nil {
		return cerr("%v", err)
	}
	if len(violations) > 0 {
		var parts []string
		for _, v := range violations {
			parts = append(parts, strings.Replace(v, "  ", " ", 1))
		}
		return cerr("fsck 위반 — %s", strings.Join(parts, "; "))
	}
	return nil
}

func nextNumber(records []cycle) int {
	max := 0
	for _, r := range records {
		if m := idRe.FindStringSubmatch(r.fields["id"]); m != nil {
			if n, err := strconv.Atoi(m[1]); err == nil && n > max {
				max = n
			}
		}
	}
	return max + 1
}

// copyTree: 템플릿 디렉토리를 재귀 복사한다 (심링크 없음 전제 — 템플릿은 일반 파일뿐).
func copyTree(src, dst string) error {
	return filepath.Walk(src, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		target := filepath.Join(dst, rel)
		if info.IsDir() {
			return os.MkdirAll(target, 0o755)
		}
		in, err := os.Open(path)
		if err != nil {
			return err
		}
		defer in.Close()
		out, err := os.Create(target)
		if err != nil {
			return err
		}
		defer out.Close()
		_, err = io.Copy(out, in)
		return err
	})
}

// replaceFirstLine: 여러 줄 텍스트에서 정규식에 맞는 첫 행만 치환한다 (참조 구현의 re.sub count=1).
func replaceFirstLine(re *regexp.Regexp, text, repl string) string {
	if loc := re.FindStringIndex(text); loc != nil {
		return text[:loc[0]] + repl + text[loc[1]:]
	}
	return text
}

type openArgs struct {
	chain, slug, title, author, date, root string
	parents, lineage                       []string
	newChain                               bool
}

func cmdOpen(a openArgs) error {
	chainDir := filepath.Join(a.root, a.chain)
	template := templateDir(a.root)

	// ---- 사전 검증: 저장소를 건드리기 전에 전부 확인한다 (부분 생성물 방지) ----
	if !slugRe.MatchString(a.slug) {
		return cerr("슬러그 '%s' 형식 위반 — R1: 소문자·숫자·하이픈만 (마침표 금지)", a.slug)
	}
	if fi, err := os.Stat(template); err != nil || !fi.IsDir() {
		return cerr("템플릿이 없다: %s", template)
	}
	fi, err := os.Stat(chainDir)
	newChain := err != nil || !fi.IsDir()
	if newChain && !a.newChain {
		return cerr("체인 '%s'이 없다 — 새로 만들려면 --new-chain", a.chain)
	}
	if err := fsckOrReport(a.root); err != nil { // 깨진 저장소 위에는 짓지 않는다
		return err
	}

	var records []cycle
	if !newChain {
		if records, err = loadChain(chainDir); err != nil {
			return cerr("%v", err)
		}
	}
	ids := map[string]bool{}
	for _, r := range records {
		ids[r.fields["id"]] = true
	}
	for _, p := range a.parents {
		if strings.Contains(p, "/") {
			return cerr("parent '%s'는 로컬 id여야 한다 (R3)", p)
		}
		if !ids[p] {
			return cerr("parent '%s'가 체인 '%s'에 없다 (R6 위반 예정)", p, a.chain)
		}
	}
	chains, err := scanChains(a.root)
	if err != nil {
		return cerr("%v", err)
	}
	for _, l := range a.lineage {
		if strings.Count(l, "/") != 1 {
			return cerr("lineage '%s'는 전역 표기(<chain>/<id>)여야 한다 (R3)", l)
		}
		parts := strings.SplitN(l, "/", 2)
		if parts[0] == a.chain {
			return cerr("lineage '%s'가 같은 체인을 가리킨다 — 같은 체인의 계보는 parent (R3)", l)
		}
		found := false
		for _, r := range chains[parts[0]] {
			if r.fields["id"] == parts[1] {
				found = true
				break
			}
		}
		if !found {
			return cerr("lineage '%s'가 존재하지 않는다 (R2 위반 예정)", l)
		}
	}

	cid := fmt.Sprintf("C%03d-%s", nextNumber(records), a.slug)
	dest := filepath.Join(chainDir, cid)
	if _, err := os.Stat(dest); err == nil {
		return cerr("이미 존재한다: %s", dest)
	}

	// ---- 생성 ----
	if newChain {
		if err := os.MkdirAll(chainDir, 0o755); err != nil {
			return cerr("%v", err)
		}
		stub := fmt.Sprintf("# Chain: %s\n\n## 이 체인이 정복하려는 문제\n\n(작성할 것)\n", a.chain)
		if err := os.WriteFile(filepath.Join(chainDir, "chain.md"), []byte(stub), 0o644); err != nil {
			return cerr("%v", err)
		}
	}
	if err := copyTree(template, dest); err != nil {
		return cerr("템플릿 복사 실패: %v", err)
	}
	parentVal := "null"
	if len(a.parents) == 1 {
		parentVal = a.parents[0]
	} else if len(a.parents) > 1 {
		parentVal = "[" + strings.Join(a.parents, ", ") + "]"
	}
	lineageVal := "[" + strings.Join(a.lineage, ", ") + "]"
	title := strings.ReplaceAll(a.title, `"`, "'")
	yaml := fmt.Sprintf("id: %s\nchain: %s\nparent: %s\nlineage: %s\nauthor: %s\nstatus: open\nopened: %s\nclosed: null\ntitle: \"%s\"\n",
		cid, a.chain, parentVal, lineageVal, a.author, a.date, title)
	if err := os.WriteFile(filepath.Join(dest, "cycle.yaml"), []byte(yaml), 0o644); err != nil {
		return cerr("%v", err)
	}

	// ---- 사후 확인: 생성물이 규칙을 어기면 되돌리고 실패한다 ----
	if err := fsckOrReport(a.root); err != nil {
		os.RemoveAll(dest)
		return err
	}
	fmt.Printf("열림: %s/%s\n", a.chain, cid)
	return nil
}

type closeArgs struct {
	chain, cycleID, date, root string
}

func cmdClose(a closeArgs) error {
	cycleDir := filepath.Join(a.root, a.chain, a.cycleID)
	yamlPath := filepath.Join(cycleDir, "cycle.yaml")
	if fi, err := os.Stat(yamlPath); err != nil || fi.IsDir() {
		return cerr("사이클이 없다: %s", filepath.Join(a.chain, a.cycleID))
	}
	fields, _, _, err := parseCycleYaml(yamlPath)
	if err != nil {
		return cerr("%v", err)
	}
	if fields["status"] == "closed" {
		return cerr("%s/%s: 이미 닫힌 사이클이다 — 닫힌 사이클은 수정하지 않는다", a.chain, a.cycleID)
	}

	reportPath := filepath.Join(cycleDir, "5-report.md")
	report, err := os.ReadFile(reportPath)
	if err != nil {
		return cerr("%s/%s: 5-report.md가 없다 — 보고 없이 닫을 수 없다", a.chain, a.cycleID)
	}
	if tpl, err := os.ReadFile(filepath.Join(templateDir(a.root), "5-report.md")); err == nil {
		if string(report) == string(tpl) {
			return cerr("%s/%s: 보고서가 템플릿 그대로다 — 결과 보고를 작성할 것", a.chain, a.cycleID)
		}
	}

	original, err := os.ReadFile(yamlPath)
	if err != nil {
		return cerr("%v", err)
	}
	updated := replaceFirstLine(regexp.MustCompile(`(?m)^status:.*$`), string(original), "status: closed")
	updated = replaceFirstLine(regexp.MustCompile(`(?m)^closed:.*$`), updated, "closed: "+a.date)
	if err := os.WriteFile(yamlPath, []byte(updated), 0o644); err != nil {
		return cerr("%v", err)
	}
	if err := fsckOrReport(a.root); err != nil {
		os.WriteFile(yamlPath, original, 0o644) // 원상 복구
		return err
	}
	fmt.Printf("닫힘: %s/%s (%s)\n", a.chain, a.cycleID, a.date)
	return nil
}

// ---------- CLI ----------

// parseCLI: 위치 인자와 --플래그를 분리한다. spec: 플래그명 → 값을 받는가.
func parseCLI(args []string, spec map[string]bool) (pos []string, flags map[string][]string, err error) {
	flags = map[string][]string{}
	for i := 0; i < len(args); i++ {
		a := args[i]
		if !strings.HasPrefix(a, "--") {
			pos = append(pos, a)
			continue
		}
		name, inline := a[2:], ""
		hasInline := false
		if j := strings.Index(name, "="); j != -1 {
			name, inline, hasInline = name[:j], name[j+1:], true
		}
		takesValue, known := spec[name]
		if !known {
			return nil, nil, fmt.Errorf("알 수 없는 플래그: --%s", name)
		}
		if !takesValue {
			flags[name] = append(flags[name], "true")
			continue
		}
		if hasInline {
			flags[name] = append(flags[name], inline)
		} else {
			i++
			if i >= len(args) {
				return nil, nil, fmt.Errorf("--%s: 값이 필요하다", name)
			}
			flags[name] = append(flags[name], args[i])
		}
	}
	return pos, flags, nil
}

func flagVal(flags map[string][]string, name, def string) string {
	if v, ok := flags[name]; ok && len(v) > 0 {
		return v[len(v)-1]
	}
	return def
}

func fail(err error) {
	fmt.Fprintf(os.Stderr, "오류: %v\n", err)
	os.Exit(1)
}

func notImplemented(what string) {
	fmt.Fprintf(os.Stderr, "미구현: '%s' — 이 바이너리(loom/C014)는 계약 부분집합(log·fsck·open·close)만 구현한다\n", what)
	os.Exit(3)
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "사용: gil <log|fsck|open|close> [인자…]")
		os.Exit(2)
	}
	today := time.Now().Format("2006-01-02")
	defaultRoot := "rooms/experiment/chains"
	switch os.Args[1] {
	case "fsck":
		root := defaultRoot
		if len(os.Args) >= 3 && !strings.HasPrefix(os.Args[2], "-") {
			root = os.Args[2]
		}
		os.Exit(fsck(root))
	case "log":
		root := defaultRoot
		if len(os.Args) >= 3 && !strings.HasPrefix(os.Args[2], "-") {
			root = os.Args[2]
		}
		os.Exit(logCmd(root))
	case "open":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{
			"title": true, "parent": true, "lineage": true, "author": true,
			"date": true, "root": true, "new-chain": false,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) != 2 {
			fmt.Fprintln(os.Stderr, "사용: gil open <chain> <slug> [--title t] [--parent id]… [--lineage chain/id]… [--author a] [--date d] [--new-chain] [--root r]")
			os.Exit(2)
		}
		if err := cmdOpen(openArgs{
			chain: pos[0], slug: pos[1],
			title:    flagVal(flags, "title", ""),
			author:   flagVal(flags, "author", "clew"),
			date:     flagVal(flags, "date", today),
			root:     flagVal(flags, "root", defaultRoot),
			parents:  flags["parent"],
			lineage:  flags["lineage"],
			newChain: len(flags["new-chain"]) > 0,
		}); err != nil {
			fail(err)
		}
	case "close":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{
			"date": true, "root": true, "git": false,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(flags["git"]) > 0 {
			// 깃 각인은 이번 부분집합의 범위 밖 — 어떤 변경도 하기 전에 정직하게 거부한다.
			notImplemented("close --git")
		}
		if len(pos) != 2 {
			fmt.Fprintln(os.Stderr, "사용: gil close <chain> <cycle-id> [--date d] [--root r]")
			os.Exit(2)
		}
		if err := cmdClose(closeArgs{
			chain: pos[0], cycleID: pos[1],
			date: flagVal(flags, "date", today),
			root: flagVal(flags, "root", defaultRoot),
		}); err != nil {
			fail(err)
		}
	default:
		notImplemented(os.Args[1])
	}
}
