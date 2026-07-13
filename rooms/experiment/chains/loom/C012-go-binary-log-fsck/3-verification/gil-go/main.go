// gil — 길, GIt for Language model. Go 참조-후보 구현 (loom/C012: 계약 부분집합 fsck·log).
//
// Ariadne Spec의 구현 독립 계약(§7)에 따라, 이 바이너리는 conformance.py의 판정으로만
// 자격을 얻는다. 이 사이클의 범위: fsck(R1~R8)·log. 나머지 명령은 정직하게 "미구현"을 알린다.
//
// 외부 의존성 0 — Go 표준 라이브러리만.
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
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

func fsck(root string) int {
	chains, err := scanChains(root)
	if err != nil {
		fmt.Fprintf(os.Stderr, "오류: %v\n", err)
		return 1
	}
	idsByChain := map[string]map[string]bool{}
	for ch, recs := range chains {
		idsByChain[ch] = map[string]bool{}
		for _, r := range recs {
			idsByChain[ch][r.fields["id"]] = true
		}
	}
	var violations []string
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
	if len(violations) > 0 {
		sort.Strings(violations)
		for _, v := range violations {
			fmt.Println(v)
		}
		fmt.Fprintf(os.Stderr, "\n검사: 체인 %d개, 사이클 %d개 — 위반 %d건\n", len(chains), total, len(violations))
		return 1
	}
	fmt.Printf("OK — 체인 %d개, 사이클 %d개, 위반 0건 (스키마 v0.2)\n", len(chains), total)
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

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "사용: gil <log|fsck> [chains-root]")
		os.Exit(2)
	}
	root := "rooms/experiment/chains"
	if len(os.Args) >= 3 && !strings.HasPrefix(os.Args[2], "-") {
		root = os.Args[2]
	}
	switch os.Args[1] {
	case "fsck":
		os.Exit(fsck(root))
	case "log":
		os.Exit(logCmd(root))
	default:
		fmt.Fprintf(os.Stderr, "미구현: '%s' — 이 바이너리(loom/C012)는 계약 부분집합(log·fsck)만 구현한다\n", os.Args[1])
		os.Exit(3)
	}
}
