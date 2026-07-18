// gil — 길, GIt for Language model. Go 참조-후보 구현
// (loom/C012: fsck·log → C014: open·close → C017: 깃 바인딩·step → loom/C020: web).
//
// Ariadne Spec의 구현 독립 계약(§7)에 따라, 이 바이너리는 conformance.py의 판정으로만
// 자격을 얻는다.
//
// 구현한 명령의 목록은 **여기에 적지 않는다** — `gil help`가 단일 소스다 (§7.2, loom/C039).
// 갱신하는 목록은 또 낡지만, 위임하는 목록은 낡지 않는다.
//
// 외부 의존성 0 — Go 표준 라이브러리만. 깃은 참조 구현과 동일하게 CLI 호출이다
// (참조 구현은 subprocess, 여기는 os/exec — 라이브러리 의존이 아니라 도구 의존).
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

var stepNames = map[int]string{1: "가설", 2: "설계", 3: "검증", 4: "분석", 5: "보고"}

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
var verdicts = map[string]bool{"supported": true, "partial": true, "rejected": true, "inconclusive": true}

// roundVerdictOrder/roundVerdicts (v2.5, loom/C045 — 이슈 #9·#10): 라운드 전용 6-어휘.
// invalid-method: 검증 방법 자체가 무효라 가설의 참/거짓을 판정 못함 (rejected와 다르다).
// confounded: 교란 변수로 결론 불가. 둘 다 "방법이 틀림"을 "가설이 틀림"과 구별한다.
var roundVerdictOrder = []string{"supported", "partial", "rejected", "inconclusive", "invalid-method", "confounded"}
var roundVerdicts = map[string]bool{
	"supported": true, "partial": true, "rejected": true, "inconclusive": true,
	"invalid-method": true, "confounded": true,
}

func collectFsck(root string) (violations []string, warnings []string, nChains, nCycles int, err error) {
	chains, err := scanChains(root)
	if err != nil {
		return nil, nil, 0, 0, err
	}
	idsByChain := map[string]map[string]bool{}
	for ch, recs := range chains {
		idsByChain[ch] = map[string]bool{}
		for _, r := range recs {
			idsByChain[ch][r.fields["id"]] = true
		}
	}
	add := func(rule, loc, msg string) {
		violations = append(violations, fmt.Sprintf("%s  %s: %s", rule, loc, msg))
	}

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
			// R9 (v0.6): step 존재 시 1~5 정수, 닫힌 사이클이면 5.
			// 참조 구현은 "step: null"을 필드 부재로 본다 — 여기서는 빈 값("")이 그에 대응한다.
			if s, ok := r.fields["step"]; ok && s != "" {
				n, aerr := strconv.Atoi(s)
				if !isDigits(s) || aerr != nil || n < 1 || n > 5 {
					add("R9", loc, "step '"+s+"'는 1~5 정수여야 한다")
				} else if status == "closed" && n != 5 {
					add("R9", loc, "닫힌 사이클의 step은 5여야 한다 (현재 "+s+")")
				}
			}
			// R10 (v0.3): verdict·deviations — 결말과 사전등록 이탈의 기계 가시화
			if v, ok := r.fields["verdict"]; ok && v != "" && !verdicts[v] {
				add("R10", loc, "verdict '"+v+"'는 supported|partial|rejected|inconclusive 중 하나여야 한다")
			}
			if dv, ok := r.fields["deviations"]; ok && dv != "" {
				if !isDigits(dv) {
					add("R10", loc, "deviations '"+dv+"'는 정수여야 한다 (상세는 deviations.yaml)")
				} else {
					nField, _ := strconv.Atoi(dv)
					devfile := filepath.Join(root, ch, r.dir, "deviations.yaml")
					_, e := os.Stat(devfile)
					exists := e == nil
					if nField > 0 {
						if !exists {
							add("R10", loc, "deviations "+dv+"인데 deviations.yaml이 없다")
						}
						warnings = append(warnings, "이탈\x00"+loc+"\x00사전등록 이탈 "+dv+"건 (deviations.yaml)")
					}
					// 역방향 (loom/C057): 파일이 있는데 레코드 수 ≠ 카운트 — C053 슬립을 가시화.
					// 위반이 아니라 경고 — R10은 v0.3 유예-경고라 이미 봉인된 사슬이 fsck rc를 바꾸지 않는다.
					if exists {
						if nRec := countDeviations(devfile); nRec >= 0 && nRec != nField {
							warnings = append(warnings, fmt.Sprintf("이탈카운트\x00%s\x00deviations.yaml %d건인데 cycle.yaml deviations: %s — 불일치 (봉인 전 조정, C057)", loc, nRec, dv))
						}
					}
				}
			}
			if v := r.fields["verdict"]; status == "closed" && v == "" {
				warnings = append(warnings, "결말없음\x00"+loc+"\x00닫혔으나 verdict 없음")
			}
			// R13 (v0.5): 출처 정정 기록 — L1(필드 제한)과 L3(영구 기록)을 fsck가 집행한다.
			// 경고가 아니라 위반인 이유: corrections는 v0.5에서 태어나므로 유예할 과거가 없다.
			if cv, ok := r.fields["corrections"]; ok && cv != "" {
				if !isDigits(cv) {
					add("R13", loc, "corrections '"+cv+"'는 정수여야 한다 (상세는 corrections.yaml)")
				} else if n, _ := strconv.Atoi(cv); n > 0 {
					cfile := filepath.Join(root, ch, r.dir, "corrections.yaml")
					if _, e := os.Stat(cfile); e != nil {
						add("R13", loc, "corrections "+cv+"인데 corrections.yaml이 없다")
					} else if recs := parseCorrections(cfile); recs == nil {
						add("R13", loc, "corrections.yaml 형식 위반 — '- field: …' + 2칸 들여쓴 key: value")
					} else if len(recs) != n {
						add("R13", loc, fmt.Sprintf("corrections %s인데 corrections.yaml 레코드는 %d건", cv, len(recs)))
					} else {
						for i, rec := range recs {
							var missing []string
							for _, k := range correctionKeys {
								if _, has := rec[k]; !has {
									missing = append(missing, k)
								}
							}
							if len(missing) > 0 {
								add("R13", loc, fmt.Sprintf("corrections.yaml #%d: 필수 키 누락 — %s", i+1, strings.Join(missing, ", ")))
							} else if !isProvenance(rec["field"]) {
								add("R13", loc, fmt.Sprintf("corrections.yaml #%d: '%s'는 출처 필드가 아니다 (L1)", i+1, rec["field"]))
							}
						}
					}
					warnings = append(warnings, "정정\x00"+loc+"\x00출처 정정 "+cv+"건 (corrections.yaml) — 색인은 수리됐고 거짓은 기록에 남았다")
				}
			}
			// R11 (v0.4): superseded_by — 전방 무효화 포인터는 실재하는 사이클로 해소되어야 한다
			if sb, ok := r.fields["superseded_by"]; ok && sb != "" {
				switch {
				case sb == cid || sb == ch+"/"+cid:
					add("R11", loc, "superseded_by가 자기 자신을 가리킨다")
				case strings.Contains(sb, "/"):
					parts := strings.SplitN(sb, "/", 2)
					if other, ok := idsByChain[parts[0]]; !ok || !other[parts[1]] {
						add("R11", loc, "superseded_by '"+sb+"'가 존재하지 않는다")
					}
				case !valid[sb]:
					add("R11", loc, "superseded_by '"+sb+"'가 체인 '"+ch+"'에 없다 (전역이면 <chain>/<id>)")
				}
			}
			// R15 (v2.5, loom/C045 — 이슈 #9·#10): 라운드 사전등록. rounds:N(N>1)이면 R2..RN 각각
			// rounds/R{k}/hypothesis.md가 존재해야 한다 — 없으면 사전등록되지 않은 것이다. round.yaml의
			// verdict가 있으면 6-어휘 중 하나여야 한다. rounds 필드가 없으면 규칙 불발(무라운드는 사정거리 밖).
			if rv, ok := r.fields["rounds"]; ok && rv != "" {
				n, aerr := strconv.Atoi(rv)
				if !isDigits(rv) || aerr != nil || n < 1 {
					add("R15", loc, "rounds '"+rv+"'는 1 이상의 정수여야 한다")
				} else if n > 1 {
					cdir := filepath.Join(root, ch, r.dir)
					for k := 2; k <= n; k++ {
						rk := filepath.Join(cdir, "rounds", fmt.Sprintf("R%d", k))
						if _, e := os.Stat(filepath.Join(rk, "hypothesis.md")); e != nil {
							add("R15", loc, fmt.Sprintf("rounds:%s인데 rounds/R%d/hypothesis.md가 없다 (사전등록 파일 누락)", rv, k))
						}
						ryp := filepath.Join(rk, "round.yaml")
						if fi, e := os.Stat(ryp); e == nil && !fi.IsDir() {
							rfields, _, _, perr := parseCycleYaml(ryp)
							if perr == nil {
								if rverd := rfields["verdict"]; rverd != "" && !roundVerdicts[rverd] {
									add("R15", loc, fmt.Sprintf("rounds/R%d/round.yaml verdict '%s'는 %s 중 하나여야 한다",
										k, rverd, strings.Join(roundVerdictOrder, "|")))
								}
							}
						}
					}
				}
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
		// R12 (v0.5): 다중 루트 — 거의 항상 --parent 누락의 흔적이다.
		// 경고이지 위반이 아닌 이유: open --new-root가 정당한 탈출구다. 도구가 자기 탈출구를 불법화하면 안 된다.
		var roots []string
		for _, r := range chains[ch] {
			if cid := r.fields["id"]; cid != "" && len(r.parents) == 0 {
				roots = append(roots, cid)
			}
		}
		if len(roots) > 1 {
			sort.Strings(roots)
			warnings = append(warnings, fmt.Sprintf("다중루트\x00%s\x00루트가 %d개 — %s (의도한 것이 아니면 parent 누락이다)",
				ch, len(roots), strings.Join(roots, ", ")))
		}
		// R14 (v0.6): 체인 디렉토리는 chain.md를 가져야 한다 — open --new-chain이 놓치던 표면 (이슈 #14).
		// 위반인 이유: R12(경고)와 달리 정당한 탈출구가 없다 — open --new-chain이 항상 chain.md를 만든다.
		if _, e := os.Stat(filepath.Join(root, ch, "chain.md")); e != nil {
			add("R14", ch, "chain.md가 없다 — 체인의 문제 정의 문서가 커밋되지 않았다")
		}
	}
	sort.Strings(violations)
	sort.Strings(warnings)
	return violations, warnings, len(chains), total, nil
}

func printWarnings(warnings []string) {
	var devLines []string
	var noVerdict []string
	for _, w := range warnings {
		p := strings.SplitN(w, "\x00", 3)
		if p[0] == "결말없음" {
			noVerdict = append(noVerdict, p[1])
		} else {
			devLines = append(devLines, fmt.Sprintf("경고 [%s] %s: %s", p[0], p[1], p[2]))
		}
	}
	for _, l := range devLines { // 이탈은 개별 강조
		fmt.Fprintln(os.Stderr, l)
	}
	if len(noVerdict) > 0 { // 결말없음은 요약 (유예)
		locs := noVerdict
		suffix := ""
		if len(locs) > 5 {
			locs, suffix = locs[:5], " …"
		}
		fmt.Fprintf(os.Stderr, "경고 [결말없음] %d건 — verdict 미기록 (기존 사슬 유예): %s%s\n",
			len(noVerdict), strings.Join(locs, ", "), suffix)
	}
}

func fsck(root string) int {
	violations, warnings, nChains, total, err := collectFsck(root)
	if err != nil {
		fmt.Fprintf(os.Stderr, "오류: %v\n", err)
		return 1
	}
	printWarnings(warnings)
	if len(violations) > 0 {
		for _, v := range violations {
			fmt.Println(v)
		}
		fmt.Fprintf(os.Stderr, "\n검사: 체인 %d개, 사이클 %d개 — 위반 %d건, 경고 %d건\n", nChains, total, len(violations), len(warnings))
		return 1
	}
	tail := ""
	if len(warnings) > 0 {
		tail = fmt.Sprintf(", 경고 %d건", len(warnings))
	}
	fmt.Printf("OK — 체인 %d개, 사이클 %d개, 위반 0건 (스키마 v0.5)%s\n", nChains, total, tail)
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
		tally := map[string]int{}
		devs := 0
		for _, cid := range order {
			r := byID[cid]
			mark := "●"
			status := r.fields["status"]
			label := status
			if v := r.fields["verdict"]; v != "" { // v0.3 결말 표시
				label = status + " · " + v
				tally[v]++
			}
			if rv := r.fields["rounds"]; rv != "" && isDigits(rv) { // v2.5: 라운드는 2 이상일 때만 (무라운드 출력 불변, C045)
				if n, _ := strconv.Atoi(rv); n > 1 {
					label += fmt.Sprintf(" · R%d", n)
				}
			}
			if dv := r.fields["deviations"]; dv != "" && isDigits(dv) {
				if n, _ := strconv.Atoi(dv); n > 0 {
					label += fmt.Sprintf(" ⚠%d", n)
					devs += n
				}
			}
			sup := "" // v0.4: 전방 무효화 — 이 사이클의 결론은 대체되었다
			if sb := r.fields["superseded_by"]; sb != "" {
				sup = "  ↣ superseded: " + sb
			}
			if cv := r.fields["corrections"]; cv != "" && isDigits(cv) { // v0.5: 이 색인은 수리됐다
				if n, _ := strconv.Atoi(cv); n > 0 {
					sup += fmt.Sprintf("  ✎ corrected(%d)", n)
				}
			}
			extra := ""
			if len(r.parents) > 1 {
				extra = "  ◀ 병합: " + strings.Join(r.parents, " + ")
			}
			if len(r.lineage) > 0 {
				extra += "  ⇠ lineage: " + strings.Join(r.lineage, ", ")
			}
			fmt.Printf("%s  %s [%s] %s%s%s\n", mark, cid, label, r.fields["title"], sup, extra)
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
		var parts []string // v0.3 결말 집계
		for _, v := range []string{"supported", "partial", "rejected", "inconclusive"} {
			if tally[v] > 0 {
				parts = append(parts, fmt.Sprintf("%s %d", v, tally[v]))
			}
		}
		if len(parts) > 0 || devs > 0 {
			line := "\n결말: " + strings.Join(parts, " · ")
			if devs > 0 {
				line += fmt.Sprintf(" · 이탈 %d건", devs)
			}
			fmt.Println(line)
		}
		// 예약은 사이클이 아니다 — 그래프 밖 별도 섹션 (loom/C043). 무예약이면 출력 불변.
		if reservations := loadReservations(filepath.Join(root, ch)); len(reservations) > 0 {
			fmt.Println("\n예약됨 (아직 사이클 아님 — 번호 공간 선점):")
			for _, rv := range reservations {
				fmt.Printf("  C%03d  → %s  (%s, %s)\n", rv.num, rv.who, rv.slug, rv.date)
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
	violations, _, _, _, err := collectFsck(chainsRoot)
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

// nextNumber: 다음 번호 = max(사이클 번호 ∪ 예약 번호) + 1 (참조 _next_number).
// 예약(loom/C043)은 사이클이 아니지만 번호 공간을 선점한다 — 남의 예약 번호는 자동 발급되지 않는다.
func nextNumber(records []cycle, reservedNums []int) int {
	max := 0
	for _, n := range reservedNums {
		if n > max {
			max = n
		}
	}
	for _, r := range records {
		if m := idRe.FindStringSubmatch(r.fields["id"]); m != nil {
			if n, err := strconv.Atoi(m[1]); err == nil && n > max {
				max = n
			}
		}
	}
	return max + 1
}

// ---------- 번호 예약 원장 (loom/C043 — 이슈 #13) ----------
// 예약은 사이클이 아니다. 체인 최상위의 평문 원장(reservations.tsv)에 산다 —
// loadChain/scanChains는 <entry>/cycle.yaml만 record로 수집하므로 fsck·verify·graph는
// 예약을 record로 보지 않는다. "예약은 사이클이 아니다"를 파일 위치가 물리적으로 보증한다.
// 형식: 주석(#) + 예약 한 줄당 "<번호> <for> <slug> <일자>" (공백 구분, 번호 오름차순).

type reservation struct {
	num  int
	who  string // 참조 구현의 for (예약 대상 존재의 이름 — Go 예약어라 who)
	slug string
	date string
}

func reservationsPath(chainDir string) string {
	return filepath.Join(chainDir, "reservations.tsv")
}

// loadReservations: 예약 목록을 번호 오름차순으로 반환 (파일 없으면 nil).
func loadReservations(chainDir string) []reservation {
	data, err := os.ReadFile(reservationsPath(chainDir))
	if err != nil {
		return nil
	}
	var out []reservation
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.Fields(line)
		if len(parts) < 4 || !isDigits(parts[0]) { // 관대한 파서 — 깨진 줄은 건너뛴다
			continue
		}
		n, _ := strconv.Atoi(parts[0])
		out = append(out, reservation{num: n, who: parts[1], slug: parts[2], date: parts[3]})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].num < out[j].num })
	return out
}

const reservationsHeader = "# gil 예약 원장 — 이 파일은 사이클이 아니다 (loom/C043). 번호 공간의 선점만 기록한다.\n" +
	"# <번호> <for> <slug> <일자>\n"

// saveReservations: 예약 목록을 원장에 쓴다. 비면 파일을 지운다 (참조 _save_reservations).
func saveReservations(chainDir string, reservations []reservation) error {
	path := reservationsPath(chainDir)
	if len(reservations) == 0 {
		if _, err := os.Stat(path); err == nil {
			return os.Remove(path)
		}
		return nil
	}
	sort.Slice(reservations, func(i, j int) bool { return reservations[i].num < reservations[j].num })
	var b strings.Builder
	b.WriteString(reservationsHeader)
	for _, r := range reservations {
		b.WriteString(fmt.Sprintf("%d %s %s %s\n", r.num, r.who, r.slug, r.date))
	}
	return os.WriteFile(path, []byte(b.String()), 0o644)
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

// insertAfterFirstLine: 정규식에 맞는 첫 행 바로 뒤에 새 행을 삽입한다
// (참조 구현의 re.sub(r"^(closed:.*)$", r"\1\n<새 행>", count=1)에 대응).
func insertAfterFirstLine(re *regexp.Regexp, text, newLine string) string {
	if loc := re.FindStringIndex(text); loc != nil {
		return text[:loc[1]] + "\n" + newLine + text[loc[1]:]
	}
	return text
}

// isDigits: 파이썬 str.isdigit()의 ASCII 부분집합 — 부호·공백 없이 숫자만.
func isDigits(s string) bool {
	if s == "" {
		return false
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}

// runeTail: 문자열의 뒤 n '문자'. 파이썬 s[-n:]에 대응한다 —
// Go의 바이트 슬라이싱은 UTF-8을 쪼개므로 룬 단위로 자른다 (한국어 오류 문면 보존).
func runeTail(s string, n int) string {
	r := []rune(s)
	if len(r) <= n {
		return s
	}
	return string(r[len(r)-n:])
}

// pushWithRenumber: 원장 규율 (v0.8, loom/C016 — SPEC §6-6).
// push 거절 = 원장이 앞섰다는 신호. fetch·rebase 후 번호 경합이면 자동 재번호
// (디렉토리·id 개명 + 커밋 정정) 후 재시도한다. 최대 3회.
// 참조 구현 gil.py의 _push_with_renumber와 절차·문면이 같다.
func pushWithRenumber(repo, chainDir, chain, cid, title string) (string, error) {
	if !hasPushRemote(repo) { // 원격 없으면 경합할 원장이 없다 — 재번호 불필요, 날것 fetch fatal 회피 (loom/C054)
		warnNoRemoteOnce()
		return cid, nil
	}
	for i := 0; i < 3; i++ {
		if _, _, code := gitRun(repo, "push"); code == 0 {
			return cid, nil
		}
		branchOut, err := gitChecked(repo, "rev-parse", "--abbrev-ref", "HEAD")
		if err != nil {
			return cid, err
		}
		branch := strings.TrimSpace(branchOut)
		if _, err := gitChecked(repo, "fetch", "origin"); err != nil {
			return cid, err
		}
		if out, errS, code := gitRun(repo, "rebase", "origin/"+branch); code != 0 {
			gitRun(repo, "rebase", "--abort")
			msg := strings.TrimSpace(errS)
			if msg == "" {
				msg = strings.TrimSpace(out)
			}
			return cid, cerr("push 경합의 rebase 해소 실패 — 수동 개입 필요: %s", runeTail(msg, 150))
		}
		m := idRe.FindStringSubmatch(cid)
		if m == nil {
			return cid, cerr("재번호 불가: id '%s' 형식 위반", cid)
		}
		myNum := m[1]
		records, err := loadChain(chainDir) // rebase 이후의 원장 + 내 사이클
		if err != nil {
			return cid, cerr("%v", err)
		}
		dup := false
		for _, r := range records {
			rid := r.fields["id"]
			if rid == "" || rid == cid {
				continue
			}
			if rm := idRe.FindStringSubmatch(rid); rm != nil && rm[1] == myNum {
				dup = true
				break
			}
		}
		if !dup {
			continue // 경합이 번호가 아니었다 (다른 사이클의 커밋) — 재번호 없이 재시도
		}
		slug := cid[strings.Index(cid, "-")+1:]
		var reserved []int // 재번호도 예약을 회피한다 (참조 _push_with_renumber)
		for _, rv := range loadReservations(chainDir) {
			reserved = append(reserved, rv.num)
		}
		newCid := fmt.Sprintf("C%03d-%s", nextNumber(records, reserved), slug)
		oldRel, err := relToRepo(repo, filepath.Join(chainDir, cid))
		if err != nil {
			return cid, cerr("%v", err)
		}
		newRel, err := relToRepo(repo, filepath.Join(chainDir, newCid))
		if err != nil {
			return cid, cerr("%v", err)
		}
		if _, err := gitChecked(repo, "mv", oldRel, newRel); err != nil {
			return cid, err
		}
		ypath := filepath.Join(repo, newRel, "cycle.yaml")
		text, rerr := os.ReadFile(ypath)
		if rerr != nil {
			return cid, cerr("%v", rerr)
		}
		updated := strings.Replace(string(text), "id: "+cid, "id: "+newCid, 1)
		if werr := os.WriteFile(ypath, []byte(updated), 0o644); werr != nil {
			return cid, cerr("%v", werr)
		}
		if _, err := gitChecked(repo, "add", "-A", "--", newRel); err != nil {
			return cid, err
		}
		if _, err := gitChecked(repo, "commit", "--amend", "-m",
			fmt.Sprintf("gil: open %s/%s — 1/5 %s\n\n%s\n(원장 경합 재번호: %s → %s)",
				chain, newCid, stepNames[1], title, cid, newCid)); err != nil {
			return cid, err
		}
		fmt.Fprintf(os.Stderr, "경합 감지: %s → %s (원장 규율에 따라 재번호)\n", cid, newCid)
		cid = newCid
	}
	return cid, cerr("push 경합 해소 3회 실패 — 원장이 계속 앞선다")
}

type openArgs struct {
	chain, slug, title, author, date, root string
	parents, lineage                       []string
	newChain, newRoot, git, push, noWeb    bool
}

func cmdOpen(a openArgs) error {
	chainDir := filepath.Join(a.root, a.chain)
	template := templateDir(a.root)

	// ---- 사전 검증: 저장소를 건드리기 전에 전부 확인한다 (부분 생성물 방지) ----
	// §3.2 출처 계약 (P1·P2): 도구는 출처(author·parent)를 지어내지 않는다. 모르면 거부한다.
	if a.author == "" { // O1 — 기본값 없음. 고유명사 기본값이 남의 원장에 거짓 저자를 박았다 (이슈 #17)
		return cerr("저자를 알 수 없다 — 도구는 출처를 지어내지 않는다 (§3.2 P1).\n"+
			"      존재의 이름을 명시하라:  gil open %s %s --author <이름>", a.chain, a.slug)
	}
	if err := guardPrimaryOwner(repoRoot(a.root), a.author); err != nil { // C062 — 주 체크아웃 오염 방지
		return err
	}
	if len(a.parents) > 0 && a.newRoot { // O3 — 모순
		return cerr("--parent와 --new-root는 함께 쓸 수 없다 — 부모가 있으면 루트가 아니다")
	}
	if !slugRe.MatchString(a.slug) {
		return cerr("슬러그 '%s' 형식 위반 — R1: 소문자·숫자·하이픈만 (마침표 금지)", a.slug)
	}
	tfi, terr := os.Stat(template)
	useEmbedded := terr != nil || !tfi.IsDir() // _template 부재 시 내장 스캐폴드 (v1.1: 딸깍)
	fi, err := os.Stat(chainDir)
	newChain := err != nil || !fi.IsDir()
	if newChain && !a.newChain {
		return cerr("체인 '%s'이 없다 — 새로 만들려면 --new-chain", a.chain)
	}
	if a.newChain { // 딸깍: 체인 루트가 없으면 만든다 (git init처럼, v1.1)
		if err := os.MkdirAll(a.root, 0o755); err != nil {
			return cerr("%v", err)
		}
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
	// O2 (§3.2 P2·P3): 빈 체인의 첫 사이클이 루트라는 것은 계산이지만, 비어있지 않은 체인에서
	// parent를 비우는 것은 추측이다 — 조용히 두 번째 루트를 만드는 대신 저자에게 묻는다.
	if len(records) > 0 && len(a.parents) == 0 && !a.newRoot {
		tips := make([]string, 0, len(ids))
		for id := range ids {
			if id != "" {
				tips = append(tips, id)
			}
		}
		sort.Strings(tips)
		tip := "?"
		if len(tips) > 0 {
			tip = tips[len(tips)-1]
		}
		return cerr("체인 '%s'에 이미 사이클이 있다 (tip: %s) — 부모를 알 수 없다 (§3.2 P2).\n"+
			"      부모를 명시하라:  --parent %s   (분기면 여러 번)\n"+
			"      정말 새 루트라면:  --new-root", a.chain, tip, tip)
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

	// 번호 예약 (loom/C043): 저자가 예약을 가지면 그 번호로 승격, 아니면 예약을 회피해 발급.
	reservations := loadReservations(chainDir)
	var consumed *reservation
	for i := range reservations {
		if reservations[i].who == a.author && (consumed == nil || reservations[i].num < consumed.num) {
			r := reservations[i] // 자기 예약 중 가장 낮은 번호를 승격
			consumed = &r
		}
	}
	var num int
	if consumed != nil {
		num = consumed.num
	} else {
		reserved := make([]int, 0, len(reservations)) // 남의 예약 번호는 건너뛴다
		for _, r := range reservations {
			reserved = append(reserved, r.num)
		}
		num = nextNumber(records, reserved)
	}
	cid := fmt.Sprintf("C%03d-%s", num, a.slug)
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
	if useEmbedded {
		if err := os.MkdirAll(filepath.Join(dest, "3-verification"), 0o755); err != nil {
			return cerr("%v", err)
		}
		scaffold := map[string]string{
			"1-hypothesis.md":          "# 1. 가설 수립\n\n(작성할 것)\n",
			"2-design.md":              "# 2. 실험 설계\n\n(작성할 것)\n",
			"3-verification/README.md": "# 3. 가설 검증\n\n(작성할 것)\n",
			"4-analysis.md":            "# 4. 결과 분석\n\n(작성할 것)\n",
			"5-report.md":              "# 5. 결과 보고\n\n(작성할 것)\n",
		}
		for name, body := range scaffold {
			if err := os.WriteFile(filepath.Join(dest, name), []byte(body), 0o644); err != nil {
				return cerr("%v", err)
			}
		}
	} else if err := copyTree(template, dest); err != nil {
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
	yaml := fmt.Sprintf("id: %s\nchain: %s\nparent: %s\nlineage: %s\nstep: 1\nauthor: %s\nstatus: open\nopened: %s\nclosed: null\ntitle: \"%s\"\nverdict: null\ndeviations: 0\ncorrections: 0\nsuperseded_by: null\n",
		cid, a.chain, parentVal, lineageVal, a.author, a.date, title)
	if err := os.WriteFile(filepath.Join(dest, "cycle.yaml"), []byte(yaml), 0o644); err != nil {
		return cerr("%v", err)
	}

	// ---- 사후 확인: 생성물이 규칙을 어기면 되돌리고 실패한다 ----
	if err := fsckOrReport(a.root); err != nil {
		os.RemoveAll(dest)
		return err
	}
	if consumed != nil { // 예약을 소비했다 — 원장에서 그 줄을 제거한다 (승격 = 예약의 죽음)
		var remaining []reservation
		for _, r := range reservations {
			if r.num != consumed.num {
				remaining = append(remaining, r)
			}
		}
		if err := saveReservations(chainDir, remaining); err != nil {
			os.RemoveAll(dest)
			return cerr("%v", err)
		}
	}

	// ---- 깃 각인 (loom/C036): 열 때부터 보이게 (SPEC §2.1-3). --push는 원장 규율과 한 몸이다. ----
	if a.git {
		repo := repoRoot(a.root)
		if repo == "" && !gitAvailable() {
			warnGitMissingOnce() // git 부재: 크래시·하드에러 대신 파일만 남기고 강등 (loom/C052)
		} else if repo == "" {
			return cerr("--git: 깃 저장소가 아니다") // git 있는데 저장소 아님 = 진짜 사용자 오류
		} else {
			rel, rerr := relToRepo(repo, dest)
			if rerr != nil {
				return cerr("%v", rerr)
			}
			paths := []string{rel}
			if newChain { // chain.md는 사이클 디렉토리 밖(체인 최상위)이라 별도 경로다 (이슈 #14, loom/C044)
				if cmRel, cerr2 := relToRepo(repo, filepath.Join(chainDir, "chain.md")); cerr2 == nil {
					paths = append(paths, cmRel)
				}
			}
			if consumed != nil { // reservations.tsv는 사이클 밖이라 어떤 태그 봉인에도 안 들어간다 (verify 무영향)
				if resRel, cerr3 := relToRepo(repo, reservationsPath(chainDir)); cerr3 == nil {
					paths = append(paths, resRel)
				}
			}
			if _, err := gitChecked(repo, append([]string{"add", "-A", "--"}, paths...)...); err != nil {
				return err
			}
			msg := fmt.Sprintf("gil: open %s/%s — 1/5 %s\n\n%s", a.chain, cid, stepNames[1], title)
			if consumed != nil {
				msg += fmt.Sprintf("\n(예약 승격: %s의 C%03d 예약을 소비)", a.author, consumed.num)
			}
			if _, err := gitChecked(repo, append([]string{"commit", "-m", msg, "--"}, paths...)...); err != nil {
				return err
			}
			if a.push && consumed == nil { // 예약 승격은 격리 브랜치의 일 — 원장 재번호를 적용하지 않는다
				newCid, perr := pushWithRenumber(repo, chainDir, a.chain, cid, title)
				if perr != nil {
					return perr
				}
				cid = newCid // 원장 경합으로 재번호됐을 수 있다
			} else if a.push {
				gitPush(repo) // 원격 부재 우아화 (loom/C054) — 예약 승격은 재번호 없이 평범 push
			}
		}
	}
	promote := ""
	if consumed != nil {
		promote = fmt.Sprintf(" (예약 승격 — %s)", a.author)
	}
	fmt.Printf("열림: %s/%s%s\n", a.chain, cid, promote)
	refreshViewers(a.root, fmt.Sprintf("%s/%s 열림", a.chain, cid), a.noWeb, a.push)
	return nil
}

// ---------- reserve / unreserve (번호 예약 원장 — loom/C043, 이슈 #13) ----------

type reserveArgs struct {
	chain, slug, author, date, root string
	git, push                       bool
}

type unreserveArgs struct {
	chain, number, root string
	git, push           bool
}

var unreserveNumRe = regexp.MustCompile(`^C?0*(\d+)$`) // 44 · 044 · C044 모두 허용

// reserveCommitPush: 예약 원장 변경을 커밋·push한다 (예약 원장은 사이클 밖 — 태그 봉인 무관).
func reserveCommitPush(chainsRoot, chainDir, chain string, git, push bool, verb, cidHint string) error {
	if !git {
		return nil
	}
	repo := repoRoot(chainsRoot)
	if repo == "" && !gitAvailable() {
		warnGitMissingOnce() // git 부재: 예약 원장은 저장됨, 각인만 건너뜀 (loom/C052)
		return nil
	}
	if repo == "" {
		return cerr("--git: 깃 저장소가 아니다")
	}
	rel, err := relToRepo(repo, reservationsPath(chainDir))
	if err != nil {
		return cerr("%v", err)
	}
	if _, err := gitChecked(repo, "add", "-A", "--", rel); err != nil {
		return err
	}
	if _, err := gitChecked(repo, "commit", "-m", fmt.Sprintf("gil: %s %s/%s", verb, chain, cidHint), "--", rel); err != nil {
		return err
	}
	if push {
		gitPush(repo) // 원격 부재 우아화 (loom/C054)
	}
	return nil
}

// cmdReserve: 번호 예약을 데이터로 만든다 (참조 cmd_reserve). 예약 마커가 원장에 있으면
// 다른 워크트리의 gil open은 그 번호를 재발급하지 않는다 — push 경합 이전에 선점된다.
func cmdReserve(a reserveArgs) error {
	chainDir := filepath.Join(a.root, a.chain)
	if a.author == "" { // §3.2 P1/P2 — 도구는 예약의 주인을 지어내지 않는다 (이슈 #17)
		return cerr("예약의 주인을 알 수 없다 — 도구는 출처를 지어내지 않는다 (§3.2 P1).\n"+
			"      존재의 이름을 명시하라:  gil reserve %s %s --for <이름>", a.chain, a.slug)
	}
	if !slugRe.MatchString(a.slug) {
		return cerr("슬러그 '%s' 형식 위반 — R1: 소문자·숫자·하이픈만", a.slug)
	}
	if fi, err := os.Stat(chainDir); err != nil || !fi.IsDir() {
		return cerr("체인 '%s'이 없다 — 예약은 진행 중인 체인의 다음 번호를 선점한다", a.chain)
	}
	if err := fsckOrReport(a.root); err != nil { // 깨진 저장소 위에는 예약하지 않는다
		return err
	}
	records, err := loadChain(chainDir)
	if err != nil {
		return cerr("%v", err)
	}
	reservations := loadReservations(chainDir)
	reserved := make([]int, 0, len(reservations))
	for _, r := range reservations {
		reserved = append(reserved, r.num)
	}
	num := nextNumber(records, reserved)
	reservations = append(reservations, reservation{num: num, who: a.author, slug: a.slug, date: a.date})
	if err := saveReservations(chainDir, reservations); err != nil {
		return cerr("%v", err)
	}
	cidHint := fmt.Sprintf("C%03d", num)
	if err := reserveCommitPush(a.root, chainDir, a.chain, a.git, a.push, "reserve",
		fmt.Sprintf("%s → %s", cidHint, a.author)); err != nil {
		return err
	}
	fmt.Printf("예약됨: %s/%s → %s (%s)\n", a.chain, cidHint, a.author, a.slug)
	return nil
}

// cmdUnreserve: 예약 취소 — 만료의 수동 해법 (참조 cmd_unreserve). 없는 번호는 거부한다.
func cmdUnreserve(a unreserveArgs) error {
	chainDir := filepath.Join(a.root, a.chain)
	if fi, err := os.Stat(chainDir); err != nil || !fi.IsDir() {
		return cerr("체인 '%s'이 없다", a.chain)
	}
	m := unreserveNumRe.FindStringSubmatch(a.number)
	if m == nil {
		return cerr("번호 '%s' 형식 위반 — 정수 또는 C0NN", a.number)
	}
	num, _ := strconv.Atoi(m[1])
	reservations := loadReservations(chainDir)
	found := false
	var remaining []reservation
	for _, r := range reservations {
		if r.num == num {
			found = true
			continue
		}
		remaining = append(remaining, r)
	}
	if !found {
		return cerr("%s에 C%03d 예약이 없다", a.chain, num)
	}
	if err := saveReservations(chainDir, remaining); err != nil {
		return cerr("%v", err)
	}
	if err := reserveCommitPush(a.root, chainDir, a.chain, a.git, a.push, "unreserve",
		fmt.Sprintf("C%03d", num)); err != nil {
		return err
	}
	fmt.Printf("예약 취소: %s/C%03d\n", a.chain, num)
	return nil
}

type worktreeArgs struct {
	action, chain, slug, author, date, root string
	parents, lineage                        []string
	newChain, newRoot, push                 bool
}

func branchExists(repo, branch string) bool {
	_, _, code := gitRun(repo, "rev-parse", "--verify", "--quiet", "refs/heads/"+branch)
	return code == 0
}

// cmdWorktree — 병렬 사이클 모드 (loom/C058·C060, 발의: 박상현 #1). git worktree 명사에 올라탄다.
func cmdWorktree(a worktreeArgs) error {
	switch a.action {
	case "add":
		return worktreeAdd(a)
	case "land":
		return worktreeLand(a)
	}
	return cerr("알 수 없는 worktree 하위명령: %s", a.action)
}

// worktreeAdd — 워크트리 생성 + 새 브랜치 + 사이클 열기를 원자적으로 묶는다 (loom/C058).
// open을 복제하지 않고 워크트리 안에서 gil을 self-invoke한다 — (1) open의 계약이 검증된 한 곳에만
// 살고, (2) open이 워크트리 안(git toplevel=워크트리)에서 돌아 커밋이 그 브랜치에만 간다 —
// '메인에 잘못 open'(C050 사고)이 구조적으로 불가능해진다. cwd 계약을 도구가 집행한다.
func worktreeAdd(a worktreeArgs) error {
	if !gitAvailable() {
		return cerr("worktree add: git이 필요하다 (병렬 사이클 모드는 워크트리 격리를 쓴다)")
	}
	repo := repoRoot(a.root)
	if repo == "" {
		return cerr("worktree add: 깃 저장소가 아니다 — %s", a.root)
	}
	if a.author == "" {
		return cerr("worktree add: 저자를 알 수 없다 — --author <이름> (§3.2 P1)")
	}
	if !slugRe.MatchString(a.slug) {
		return cerr("슬러그 '%s' 형식 위반 — R1: 소문자·숫자·하이픈만", a.slug)
	}
	branch := a.author + "/" + a.chain + "-" + a.slug
	wtPath := filepath.Join(filepath.Dir(repo), filepath.Base(repo)+"-worktrees", a.chain+"-"+a.slug)
	if _, err := os.Stat(wtPath); err == nil {
		return cerr("worktree add: 경로가 이미 있다 — %s", wtPath)
	}
	if branchExists(repo, branch) {
		return cerr("worktree add: 브랜치가 이미 있다 — %s", branch)
	}
	if err := os.MkdirAll(filepath.Dir(wtPath), 0o755); err != nil {
		return cerr("%v", err)
	}
	if _, err := gitChecked(repo, "worktree", "add", "-b", branch, wtPath, "HEAD"); err != nil {
		return err
	}
	undo := func() { gitRun(repo, "worktree", "remove", "--force", wtPath); gitRun(repo, "branch", "-D", branch) }
	chainsRel, err := relToRepo(repo, a.root)
	if err != nil {
		undo()
		return cerr("%v", err)
	}
	self, err := os.Executable()
	if err != nil {
		undo()
		return cerr("자기 실행 경로를 찾을 수 없다: %v", err)
	}
	openArgv := []string{"open", a.chain, a.slug, "--author", a.author,
		"--root", filepath.Join(wtPath, chainsRel), "--date", a.date, "--git", "--no-web"}
	for _, p := range a.parents {
		openArgv = append(openArgv, "--parent", p)
	}
	for _, l := range a.lineage {
		openArgv = append(openArgv, "--lineage", l)
	}
	if a.newChain {
		openArgv = append(openArgv, "--new-chain")
	}
	if a.newRoot {
		openArgv = append(openArgv, "--new-root")
	}
	cmd := exec.Command(self, openArgv...)
	cmd.Dir = wtPath
	if out, e := cmd.CombinedOutput(); e != nil {
		// 원자성: open이 실패하면 워크트리·브랜치를 잔여 없이 되돌린다.
		undo()
		return cerr("worktree add: 워크트리 안 open 실패 — 되돌림\n%s", strings.TrimSpace(string(out)))
	}
	fmt.Printf("워크트리: %s\n", wtPath)
	fmt.Printf("브랜치:   %s\n", branch)
	fmt.Printf("→ 존재는 여기서 일한다:  cd %s  (메인 저장소로 돌아오지 말 것 — C050)\n", wtPath)
	fmt.Printf("→ 돌아오면 소환자가 병합한다:  gil worktree land %s %s --author %s\n", a.chain, a.slug, a.author)
	return nil
}

// worktreeLand — 병렬 사이클의 머지백 — add의 결정론적 매핑을 역산해 브랜치를 main에 --no-ff로 봉합한다 (loom/C060).
// add가 '여는 반쪽'이면 land는 '닫는 반쪽'이다. open/close 로직을 복제하지 않고 순수 git 오케스트레이션만
// 한다 — git merge --no-ff + worktree remove + branch -d. 충돌은 삼키지 않는다: 병합 실패 시 merge --abort로
// 무흔적 복귀 + 워크트리·브랜치 보존. 정리는 병합 성공 시에만 — 병합 안 된 브랜치는 -d(안전 삭제)가 거부한다.
func worktreeLand(a worktreeArgs) error {
	if !gitAvailable() {
		return cerr("worktree land: git이 필요하다 (병렬 사이클 모드는 워크트리 격리를 쓴다)")
	}
	repo := repoRoot(a.root)
	if repo == "" {
		return cerr("worktree land: 깃 저장소가 아니다 — %s", a.root)
	}
	if a.author == "" {
		return cerr("worktree land: 저자를 알 수 없다 — --author <이름> (§3.2 P1)")
	}
	if !slugRe.MatchString(a.slug) {
		return cerr("슬러그 '%s' 형식 위반 — R1: 소문자·숫자·하이픈만", a.slug)
	}
	// 역산 — add와 동일 공식. 열 때 쓴 좌표가 곧 닫을 때 쓰는 좌표다.
	branch := a.author + "/" + a.chain + "-" + a.slug
	wtPath := filepath.Join(filepath.Dir(repo), filepath.Base(repo)+"-worktrees", a.chain+"-"+a.slug)
	if !branchExists(repo, branch) {
		return cerr("worktree land: 브랜치가 없다 — %s (되돌릴 것이 없다)", branch)
	}
	// --no-ff 병합: 병렬 작업의 봉합을 항상 한 병합 커밋으로 각인한다.
	msg := fmt.Sprintf("gil: land %s/%s (%s)", a.chain, a.slug, branch)
	if out, _, code := gitRun(repo, "merge", "--no-ff", "--no-edit", "-m", msg, branch); code != 0 {
		// 충돌 등: 무흔적 복귀 + 워크트리·브랜치 보존 (충돌을 삼키지 않는다).
		gitRun(repo, "merge", "--abort")
		return cerr("worktree land: 병합 충돌 — 되돌림, 워크트리·브랜치 보존\n"+
			"  워크트리에서 해소 후 다시 land하라: %s\n%s", wtPath, strings.TrimSpace(out))
	}
	mergeSHA, _, _ := gitRun(repo, "rev-parse", "HEAD")
	mergeSHA = strings.TrimSpace(mergeSHA)
	// 정리 (병합 성공 시에만). -d는 병합 안 된 브랜치를 거부하는 안전 삭제 — '정말 병합됐나'의 마지막 단언.
	if _, err := os.Stat(wtPath); err == nil {
		gitRun(repo, "worktree", "remove", "--force", wtPath)
	}
	_, _, dcode := gitRun(repo, "branch", "-d", branch)
	branchPruned := dcode == 0
	sha := mergeSHA
	if len(sha) > 8 {
		sha = sha[:8]
	}
	fmt.Printf("착지: %s → %s (병합 %s, --no-ff)\n", branch, repo, sha)
	if branchPruned {
		fmt.Printf("정리: 워크트리 제거  + 브랜치 삭제\n")
	} else {
		fmt.Printf("정리: 워크트리 제거  (브랜치 삭제 실패 — 수동 확인)\n")
	}
	if a.push {
		if _, err := gitPush(repo); err != nil {
			return err
		}
	}
	return nil
}

type closeArgs struct {
	chain, cycleID, date, root, verdict string
	git, push, noCommit, noWeb          bool
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

	// deviations 카운트 관문 (loom/C057): deviations.yaml이 있으면 레코드 수 = deviations 필드여야 봉인한다.
	// C053 슬립(파일은 썼는데 cycle.yaml 카운트를 손으로 못 고침) 차단. auto-count가 아니라 거부 —
	// 카운트는 저자의 의도이므로 도구가 임의로 덮어쓰지 않고 의식적 조정을 강제한다 (저장소 무변화).
	devfile := filepath.Join(cycleDir, "deviations.yaml")
	if _, e := os.Stat(devfile); e == nil {
		nRec := countDeviations(devfile)
		nField, ferr := 0, error(nil)
		if dv, ok := fields["deviations"]; ok && dv != "" {
			nField, ferr = strconv.Atoi(dv)
		}
		// 비정수 필드(ferr≠nil)는 이후 fsck의 R10이 잡는다.
		if nRec >= 0 && ferr == nil && nRec != nField {
			return cerr("%s/%s: deviations.yaml에 %d건인데 cycle.yaml deviations: %d — 봉인 전에 카운트를 조정하라 (손으로 세는 것을 잊지 말라, C053)", a.chain, a.cycleID, nRec, nField)
		}
	}

	// 기본 커밋 (v1.7, C033): 깃 저장소면 자동 커밋+각인. --no-commit으로만 끈다.
	var repo, tag string
	if !a.noCommit {
		repo = repoRoot(a.root)
	}
	if repo != "" {
		tag = tagName(a.chain, a.cycleID)
		if tagExists(repo, tag) {
			return cerr("태그 '%s'가 이미 존재한다", tag)
		}
	} else if !a.noCommit && !gitAvailable() {
		warnGitMissingOnce() // git 부재: 보고서 저장은 되고 각인·태그만 건너뜀 (loom/C052)
	} else if a.git && !a.noCommit {
		return cerr("--git: 깃 저장소가 아니다 — %s", a.root)
	}

	reportPath := filepath.Join(cycleDir, "5-report.md")
	report, err := os.ReadFile(reportPath)
	if err != nil {
		return cerr("%s/%s: 5-report.md가 없다 — 보고 없이 닫을 수 없다", a.chain, a.cycleID)
	}
	stubs := []string{"# 5. 결과 보고\n\n(작성할 것)\n"} // 내장 스캐폴드의 미작성 보고서 (v1.1)
	if tpl, err := os.ReadFile(filepath.Join(templateDir(a.root), "5-report.md")); err == nil {
		stubs = append(stubs, string(tpl))
	}
	for _, st := range stubs {
		if string(report) == st {
			return cerr("%s/%s: 보고서가 템플릿 그대로다 — 결과 보고를 작성할 것", a.chain, a.cycleID)
		}
	}

	original, err := os.ReadFile(yamlPath)
	if err != nil {
		return cerr("%v", err)
	}
	updated := replaceFirstLine(regexp.MustCompile(`(?m)^status:.*$`), string(original), "status: closed")
	updated = replaceFirstLine(regexp.MustCompile(`(?m)^closed:.*$`), updated, "closed: "+a.date)
	if regexp.MustCompile(`(?m)^step:`).MatchString(updated) {
		updated = replaceFirstLine(regexp.MustCompile(`(?m)^step:.*$`), updated, "step: 5")
	} else {
		updated = insertAfterFirstLine(regexp.MustCompile(`(?m)^closed:.*$`), updated, "step: 5")
	}
	if a.verdict != "" { // v0.3: 결말 기록
		if !verdicts[a.verdict] {
			return cerr("verdict '%s'는 supported|partial|rejected|inconclusive 중 하나여야 한다", a.verdict)
		}
		if regexp.MustCompile(`(?m)^verdict:`).MatchString(updated) {
			updated = replaceFirstLine(regexp.MustCompile(`(?m)^verdict:.*$`), updated, "verdict: "+a.verdict)
		} else {
			updated = insertAfterFirstLine(regexp.MustCompile(`(?m)^closed:.*$`), updated, "verdict: "+a.verdict)
		}
	}
	if err := os.WriteFile(yamlPath, []byte(updated), 0o644); err != nil {
		return cerr("%v", err)
	}
	if err := fsckOrReport(a.root); err != nil {
		os.WriteFile(yamlPath, original, 0o644) // 원상 복구
		return err
	}
	if repo != "" {
		cycleRel, rerr := relToRepo(repo, cycleDir)
		if rerr != nil {
			os.WriteFile(yamlPath, original, 0o644)
			return cerr("%v", rerr)
		}
		title := fields["title"]
		if gerr := func() error {
			if _, err := gitChecked(repo, "add", "-A", "--", cycleRel); err != nil {
				return err
			}
			if _, err := gitChecked(repo, "commit",
				"-m", fmt.Sprintf("gil: close %s/%s\n\n%s", a.chain, a.cycleID, title),
				"--", cycleRel); err != nil {
				return err
			}
			if _, err := gitChecked(repo, "tag", "-a", tag,
				"-m", fmt.Sprintf("%s/%s: %s", a.chain, a.cycleID, title)); err != nil {
				return err
			}
			return nil
		}(); gerr != nil {
			os.WriteFile(yamlPath, original, 0o644) // 원상 복구
			gitRun(repo, "reset", "-q", "--", cycleRel)
			return gerr
		}
		fmt.Printf("각인: 커밋 + 태그 %s\n", tag)
		if a.push {
			if _, err := gitPush(repo, "--follow-tags"); err != nil { // 원격 부재 우아화 (loom/C054)
				return err
			}
		}
	}
	fmt.Printf("닫힘: %s/%s (%s)\n", a.chain, a.cycleID, a.date)
	refreshViewers(a.root, fmt.Sprintf("%s/%s 닫힘", a.chain, a.cycleID), a.noWeb, a.push)
	fmt.Println("→ 세션 핸드오프: gil handoff (사이클을 닫았으니 세션 정리를 고려하라)")
	return nil
}

// cmdHandoff: 세션의 매듭 — 현황·부활 경로·다음 실 요약, 사용자에게 세션 정리 요청 근거.
type supersedeArgs struct {
	root, oldRef, newRef string
	noCommit, noWeb      bool
}

type correctArgs struct {
	root, ref, evidence, author, reason, date string
	fields, tos                               []string
	push, noWeb                               bool
}

// ---------- correct: 정정 규정 (v0.5 / loom/C041, SPEC §4.1) ----------
//
// 저자의 주장은 불변이다. 도구의 대필(代筆)은 불변이 아니다.
// 정정은 거짓을 지우지 않는다 — 거짓 위에 진실을 덧쓰고, 거짓이 있었다는 사실을 영구히 남긴다.

// provenanceFields — 정정 가능한 것은 출처 필드뿐이다 (L1). 도구가 지어낼 수 있었던 바로 그 집합 (§3.2).
var provenanceFields = []string{"author", "parent", "lineage"}

// correctionKeys — R13이 요구하는 정정 레코드의 필수 키.
var correctionKeys = []string{"field", "from", "to", "evidence", "author", "date"}

func isProvenance(f string) bool {
	for _, p := range provenanceFields {
		if p == f {
			return true
		}
	}
	return false
}

// parseCorrections — corrections.yaml을 줄 단위로 판정한다 (일반 YAML 파서 없이).
// 형식 위반이면 nil. deviations.yaml은 사람이 읽는 문서지만, 이것은 도구가 판정하는 기록이다.
func parseCorrections(path string) []map[string]string {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var records []map[string]string
	var cur map[string]string
	for _, line := range strings.Split(string(data), "\n") {
		if strings.TrimSpace(line) == "" || strings.HasPrefix(strings.TrimSpace(line), "#") {
			continue
		}
		var body string
		switch {
		case strings.HasPrefix(line, "- "):
			cur = map[string]string{}
			records = append(records, cur)
			body = line[2:]
		case strings.HasPrefix(line, "  ") && cur != nil:
			body = line[2:]
		default:
			return nil // 중첩·블록 스칼라·들여쓰기 위반
		}
		i := strings.Index(body, ":")
		if i <= 0 {
			return nil
		}
		key := strings.TrimSpace(body[:i])
		if key == "" || strings.ContainsAny(key, " \t") {
			return nil
		}
		cur[key] = strings.TrimSpace(body[i+1:])
	}
	return records
}

// countDeviations — deviations.yaml의 최상위 레코드('- '로 시작하는 시퀀스 항목) 수 (loom/C057).
// deviations.yaml은 corrections.yaml과 달리 사람이 읽는 자유 서술 문서다(블록 스칼라 허용) —
// 그래서 R13처럼 스키마를 강제하지 않고 '몇 건인가'만 계약한다. 계약면은 스키마가 아니라 레코드 수다
// (R10 유예-경고 등급과 정합). 블록 스칼라 내용은 ≥3칸 들여쓰기라 오계수 불가. 읽기 실패 시 -1.
func countDeviations(path string) int {
	data, err := os.ReadFile(path)
	if err != nil {
		return -1
	}
	n := 0
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, "- ") {
			n++
		}
	}
	return n
}

// renderYamlValue — 평탄 표기 (§3.1)
func renderYamlValue(vals []string) string {
	switch len(vals) {
	case 0:
		return "null"
	case 1:
		return vals[0]
	default:
		return "[" + strings.Join(vals, ", ") + "]"
	}
}

func setYamlField(text, key, value string) string {
	re := regexp.MustCompile(`(?m)^` + regexp.QuoteMeta(key) + `:.*$`)
	if re.MatchString(text) {
		return replaceFirstLine(re, text, key+": "+value)
	}
	return strings.TrimRight(text, "\n") + "\n" + key + ": " + value + "\n"
}

// readSealed — 증거는 봉인본(태그)에서 읽는다. 작업 트리에서 읽으면 아무 문장이나 새로 써 넣고
// 그것을 '증거'라 부를 수 있다. 정정을 막던 봉인이 정정을 허가하는 공증인이 된다 (§4.1 원칙 2).
func readSealed(repo, tag, relpath string) (string, bool) {
	out, _, code := gitRun(repo, "show", tag+":"+relpath)
	if code != 0 {
		return "", false
	}
	return out, true
}

// cycleDiffVsTag — verify와 같은 판정 (태그↔작업 트리 대조).
func cycleDiffVsTag(repo, cycleRel, tag string) []string {
	diffOut, _, _ := gitRun(repo, "diff", "--name-only", tag, "--", cycleRel)
	statusOut, _, _ := gitRun(repo, "status", "--porcelain", "--untracked-files=all", "--", cycleRel)
	set := map[string]bool{}
	for _, p := range strings.Fields(diffOut) {
		set[p] = true
	}
	for _, line := range strings.Split(statusOut, "\n") {
		if strings.HasPrefix(line, "??") {
			set[line[3:]] = true
		}
	}
	var paths []string
	for p := range set {
		paths = append(paths, p)
	}
	sort.Strings(paths)
	return paths
}

func cmdCorrect(a correctArgs) error {
	if !strings.Contains(a.ref, "/") {
		return cerr("ref는 <chain>/<id> 형식이어야 한다: %s", a.ref)
	}
	p := strings.SplitN(a.ref, "/", 2)
	chain, cid := p[0], p[1]
	cycleDir := filepath.Join(a.root, chain, cid)
	yamlPath := filepath.Join(cycleDir, "cycle.yaml")
	if st, e := os.Stat(yamlPath); e != nil || st.IsDir() {
		return cerr("사이클이 없다: %s", a.ref)
	}

	// ---- 사전 검증 C1~C8: 저장소를 건드리기 전에 전부 확인한다 (거부 시 무변화) ----
	if a.author == "" { // C2 — 도구는 정정의 출처도 지어내지 않는다 (§3.2 P1의 재귀)
		return cerr("정정자를 알 수 없다 — 도구는 출처를 지어내지 않는다 (§3.2 P1).\n"+
			"      존재의 이름을 명시하라:  gil correct %s … --author <이름>", a.ref)
	}
	if err := guardPrimaryOwner(repoRoot(a.root), a.author); err != nil { // C062 — 주 체크아웃 오염 방지
		return err
	}
	if len(a.fields) == 0 {
		return cerr("--field가 없다 — 무엇을 정정하는지 명시하라")
	}
	for _, f := range a.fields { // C3 — 필드 제한 (L1)
		if !isProvenance(f) {
			return cerr("'%s'는 출처 필드가 아니다 — 정정 가능한 것은 %s뿐이다 (§4.1 L1).\n"+
				"      verdict·status·title·step·5스텝 문서는 저자의 주장이며 불변이다.\n"+
				"      결론이 무효가 됐다면 정정이 아니라 gil supersede다.",
				f, strings.Join(provenanceFields, "·"))
		}
	}
	if len(a.tos) != len(a.fields) {
		return cerr("--field %d개와 --to %d개가 짝지어지지 않는다 (순서대로 소비한다)", len(a.fields), len(a.tos))
	}
	if a.evidence == "" { // C4 — 증거 필수 (L2)
		return cerr("--evidence가 없다 — 정정은 새 주장이 아니라 기존 주장의 복원이다 (§4.1 L2).\n" +
			"      불변 문서의 어디가 이 값을 증언하는가:  --evidence 1-hypothesis.md:5")
	}

	repo := repoRoot(a.root)
	if repo == "" { // C1 — 봉인이 없으면 정정도 없다
		return cerr("깃 저장소가 아니다: %s — 봉인이 없으면 정정도 없다 (§4.1 C1)", a.root)
	}
	fields, parents, lineage, perr := parseCycleYaml(yamlPath)
	if perr != nil {
		return cerr("%v", perr)
	}
	tag := tagName(chain, cid)
	if fields["status"] != "closed" || !tagExists(repo, tag) { // C1
		return cerr("%s는 봉인되지 않았다 (열렸거나 태그 없음) — 정정 대상이 아니다 (§4.1 C1).\n"+
			"      봉인되지 않은 사이클의 cycle.yaml은 직접 고쳐도 위조가 아니다.", a.ref)
	}
	cycleRel, rerr := relToRepo(repo, cycleDir)
	if rerr != nil {
		return cerr("%v", rerr)
	}
	if dirty := cycleDiffVsTag(repo, cycleRel, tag); len(dirty) > 0 { // C6 — 변조 세탁 뒷문 차단
		return cerr("%s는 이미 변조됐다 — 정정은 무결한 사이클에만 허용된다 (§4.1 C6).\n"+
			"      변조: %s\n"+
			"      먼저 봉인 상태로 복원하라:  git checkout %s -- <경로>",
			a.ref, strings.Join(dirty, ", "), tag)
	}

	// C5 — 증거는 인용이 아니라 검사다 (원칙 4). 봉인본에서 읽는다.
	evPath, evLine := a.evidence, ""
	if i := strings.LastIndex(a.evidence, ":"); i != -1 {
		evPath, evLine = a.evidence[:i], a.evidence[i+1:]
	}
	evRel, everr := relToRepo(repo, filepath.Join(cycleDir, evPath))
	if everr != nil {
		return cerr("%v", everr)
	}
	sealed, ok := readSealed(repo, tag, evRel)
	if !ok {
		return cerr("증거 문서가 봉인본에 없다: %s (태그 %s)", evPath, tag)
	}
	haystack := sealed
	if evLine != "" {
		if !isDigits(evLine) {
			return cerr("증거의 줄 번호가 정수가 아니다: %s", a.evidence)
		}
		n, _ := strconv.Atoi(evLine)
		lines := strings.Split(strings.TrimRight(sealed, "\n"), "\n")
		if n < 1 || n > len(lines) {
			return cerr("증거 문서에 %d번째 줄이 없다: %s (봉인본 %d줄)", n, evPath, len(lines))
		}
		haystack = lines[n-1]
	}

	// 필드별로 새 값을 모은다 (parent 병합·lineage 리스트는 같은 필드를 반복해 누적)
	order := []string{}
	proposed := map[string][]string{}
	for i, f := range a.fields {
		if _, seen := proposed[f]; !seen {
			order = append(order, f)
		}
		proposed[f] = append(proposed[f], a.tos[i])
	}
	for _, f := range order {
		for _, v := range proposed[f] {
			if !strings.Contains(haystack, v) { // C5
				return cerr("증거가 '%s'를 증언하지 않는다 — %s (봉인본)\n"+
					"      정정은 문서에 이미 있는 사실의 복원이다. 문서가 침묵하면 정정할 수 없다 (§4.1 L2).\n"+
					"      원장은 고칠 수 없어도 역사는 덧붙일 수 있다 — 새 사이클을 열어 기록하라.", v, a.evidence)
			}
		}
	}

	originalBytes, e := os.ReadFile(yamlPath)
	if e != nil {
		return cerr("%v", e)
	}
	original := string(originalBytes)
	corrPath := filepath.Join(cycleDir, "corrections.yaml")
	corrBefore, hadCorr := "", false
	if b, e := os.ReadFile(corrPath); e == nil {
		corrBefore, hadCorr = string(b), true
	}

	current := func(f string) []string {
		switch f {
		case "parent":
			return parents
		case "lineage":
			return lineage
		default:
			if v := fields[f]; v != "" {
				return []string{v}
			}
			return nil
		}
	}

	updated := original
	var changed []string
	var records []string
	for _, f := range order {
		oldRaw, newRaw := renderYamlValue(current(f)), renderYamlValue(proposed[f])
		if oldRaw == newRaw { // C8
			return cerr("'%s'는 이미 '%s'다 — 정정할 것이 없다 (§4.1 C8)", f, newRaw)
		}
		updated = setYamlField(updated, f, newRaw)
		reason := strings.Join(strings.Fields(a.reason), " ")
		if reason == "" {
			reason = "출처 정정"
		}
		records = append(records, fmt.Sprintf(
			"- field: %s\n  from: %s\n  to: %s\n  evidence: %s\n  evidence_source: %s\n  author: %s\n  date: %s\n  reason: %s\n",
			f, oldRaw, newRaw, a.evidence, tag, a.author, a.date, reason))
		changed = append(changed, fmt.Sprintf("%s: %s → %s", f, oldRaw, newRaw))
	}
	nBefore := 0
	if c := fields["corrections"]; isDigits(c) {
		nBefore, _ = strconv.Atoi(c)
	}
	updated = setYamlField(updated, "corrections", strconv.Itoa(nBefore+len(records)))

	// ---- 쓰기 (L3: 덧붙임 — 과거의 거짓도, 과거의 정정도 지워지지 않는다) ----
	body := corrBefore
	if !hadCorr {
		body = "# 출처 필드 정정 기록 (스키마 v0.5, §4.1) — 거짓은 지워지지 않는다. 덧쓰일 뿐이다.\n" +
			"# 저자의 주장은 불변이다. 도구의 대필은 불변이 아니다.\n"
	}
	for _, rec := range records {
		body = strings.TrimRight(body, "\n") + "\n\n" + rec
	}
	rollback := func() {
		os.WriteFile(yamlPath, originalBytes, 0o644)
		if hadCorr {
			os.WriteFile(corrPath, []byte(corrBefore), 0o644)
		} else {
			os.Remove(corrPath)
		}
	}
	if err := os.WriteFile(yamlPath, []byte(updated), 0o644); err != nil {
		return cerr("%v", err)
	}
	if err := os.WriteFile(corrPath, []byte(body), 0o644); err != nil {
		rollback()
		return cerr("%v", err)
	}
	if err := fsckOrReport(a.root); err != nil { // C7 — 스키마 위반이 될 값은 쓰지 않는다
		rollback()
		return err
	}

	// ---- [correct] 커밋: 그 두 파일만 담는다 (변조를 태그 안으로 밀반입할 수 없다) ----
	relYaml, e1 := relToRepo(repo, yamlPath)
	relCorr, e2 := relToRepo(repo, corrPath)
	if e1 != nil || e2 != nil {
		rollback()
		return cerr("경로 해소 실패")
	}
	oldTagCommit, _ := gitChecked(repo, "rev-list", "-n1", tag)
	oldTagCommit = strings.TrimSpace(oldTagCommit)
	if gerr := func() error {
		if _, err := gitChecked(repo, "add", "--", relYaml, relCorr); err != nil {
			return err
		}
		_, err := gitChecked(repo, "commit",
			"-m", fmt.Sprintf("[correct] gil: %s — %s", a.ref, strings.Join(changed, "; ")),
			"--", relYaml, relCorr)
		return err
	}(); gerr != nil {
		rollback()
		gitRun(repo, "reset", "-q", "--", relYaml, relCorr)
		return gerr
	}
	head, herr := gitChecked(repo, "rev-parse", "HEAD")
	if herr != nil {
		return herr
	}
	head = strings.TrimSpace(head)
	// 태그 이동 규약 (§4): 이전 커밋 해시와 사유를 태그 메시지에 남긴다
	if _, err := gitChecked(repo, "tag", "-f", "-a", tag,
		"-m", fmt.Sprintf("[correct] %s — 증거 %s (이전 커밋 %s에서 이동)",
			strings.Join(changed, "; "), a.evidence, shortHash(oldTagCommit)),
		head); err != nil {
		return err
	}
	if a.push {
		pushed, err := gitPush(repo) // 원격 부재 우아화 (loom/C054)
		if err != nil {
			return err
		}
		if pushed { // 원격 있을 때만 이동한 태그를 강제 전파
			if _, err := gitChecked(repo, "push", "--force", "origin", "refs/tags/"+tag); err != nil {
				return err
			}
		}
	}

	refreshViewers(a.root, a.ref+" 정정", a.noWeb, a.push)
	fmt.Printf("정정: %s\n", a.ref)
	for _, c := range changed {
		fmt.Printf("  ✎ %s\n", c)
	}
	fmt.Printf("  증거: %s (봉인본 %s)\n", a.evidence, tag)
	fmt.Printf("  기록: %s — 거짓은 지워지지 않았다\n", relCorr)
	fmt.Printf("  태그 이동: %s → %s\n", shortHash(oldTagCommit), shortHash(head))
	return nil
}

func shortHash(h string) string {
	if len(h) > 8 {
		return h[:8]
	}
	return h
}

// cmdSupersede: 전방 무효화 (v0.4, 이슈 #6) — old 사이클에 superseded_by를 주입한다.
// 닫힌 사이클의 5스텝·산출물은 불변 — 메타(cycle.yaml) 한 줄만 [migrate]로 더한다 (SPEC §4).
func cmdSupersede(a supersedeArgs) error {
	split := func(ref string) (string, string, error) {
		if !strings.Contains(ref, "/") {
			return "", "", cerr("ref는 <chain>/<id> 형식이어야 한다: %s", ref)
		}
		p := strings.SplitN(ref, "/", 2)
		return p[0], p[1], nil
	}
	ochain, oid, err := split(a.oldRef)
	if err != nil {
		return err
	}
	oldYaml := filepath.Join(a.root, ochain, oid, "cycle.yaml")
	if st, e := os.Stat(oldYaml); e != nil || st.IsDir() {
		return cerr("사이클이 없다: %s", a.oldRef)
	}
	nchain, nid, err := split(a.newRef) // new 실재 검증
	if err != nil {
		return err
	}
	if st, e := os.Stat(filepath.Join(a.root, nchain, nid, "cycle.yaml")); e != nil || st.IsDir() {
		return cerr("대체 사이클이 없다: %s", a.newRef)
	}
	if a.oldRef == a.newRef {
		return cerr("자기 자신으로 대체할 수 없다")
	}
	original, e := os.ReadFile(oldYaml)
	if e != nil {
		return cerr("%v", e)
	}
	var updated string
	if regexp.MustCompile(`(?m)^superseded_by:`).MatchString(string(original)) {
		updated = replaceFirstLine(regexp.MustCompile(`(?m)^superseded_by:.*$`),
			string(original), "superseded_by: "+a.newRef)
	} else {
		updated = strings.TrimRight(string(original), "\n") + "\nsuperseded_by: " + a.newRef + "\n"
	}
	if err := os.WriteFile(oldYaml, []byte(updated), 0o644); err != nil {
		return cerr("%v", err)
	}
	if err := fsckOrReport(a.root); err != nil {
		os.WriteFile(oldYaml, original, 0o644) // 원상 복구
		return err
	}
	repo := repoRoot(a.root)
	if repo != "" && !a.noCommit {
		rel, rerr := relToRepo(repo, filepath.Join(a.root, ochain, oid))
		if rerr != nil {
			os.WriteFile(oldYaml, original, 0o644)
			return cerr("%v", rerr)
		}
		if gerr := func() error {
			if _, err := gitChecked(repo, "add", "-A", "--", rel); err != nil {
				return err
			}
			_, err := gitChecked(repo, "commit",
				"-m", fmt.Sprintf("[migrate] gil: supersede %s → superseded_by %s", a.oldRef, a.newRef),
				"--", rel)
			return err
		}(); gerr != nil {
			os.WriteFile(oldYaml, original, 0o644) // 원상 복구
			gitRun(repo, "reset", "-q", "--", rel)
			return gerr
		}
		tag := tagName(ochain, oid)
		if tagExists(repo, tag) { // 태그 이동 규약 (C004): 이주 커밋으로 옮기고 사유를 남긴다
			head, herr := gitChecked(repo, "rev-parse", "HEAD")
			if herr != nil {
				return herr
			}
			if _, err := gitChecked(repo, "tag", "-f", "-a", tag,
				"-m", fmt.Sprintf("[migrate] superseded_by %s (이전 커밋에서 이동)", a.newRef),
				strings.TrimSpace(head)); err != nil {
				return err
			}
		}
	}
	fmt.Printf("무효화: %s ↣ superseded_by %s\n", a.oldRef, a.newRef)
	refreshViewers(a.root, a.oldRef+" ↣ superseded", a.noWeb, false)
	return nil
}

func cmdHandoff(root string) error {
	repo := repoRoot(root)
	existence := filepath.Clean(filepath.Join(root, "..", "..", "existence"))
	var beings []string
	if es, err := os.ReadDir(existence); err == nil {
		for _, e := range es {
			if e.IsDir() {
				beings = append(beings, e.Name())
			}
		}
		sort.Strings(beings)
	}
	fmt.Println("=== gil 세션 핸드오프 ===")
	if len(beings) > 0 {
		fmt.Printf("존재: %s  (rooms/existence/)\n", strings.Join(beings, ", "))
	} else {
		fmt.Println("존재: (없음)")
	}
	fmt.Println("체인 상태:")
	var openCycles []string
	if chains, err := scanChains(root); err == nil {
		for _, name := range sortedKeys(chains) {
			recs := chains[name]
			if len(recs) == 0 {
				continue
			}
			latest := recs[0]
			for _, r := range recs {
				if (r.fields["id"]) > (latest.fields["id"]) {
					latest = r
				}
			}
			st := latest.fields["status"]
			if st == "" {
				st = "?"
			}
			badge := st
			if v := latest.fields["verdict"]; v != "" {
				badge += " · " + v
			}
			if s := latest.fields["step"]; st == "open" && s != "" {
				badge += " · " + s + "/5"
			}
			fmt.Printf("  %-10s %d사이클 · 최신 %s [%s]\n", name, len(recs), latest.fields["id"], badge)
			for _, r := range recs {
				if r.fields["status"] == "open" && r.fields["id"] != "" {
					openCycles = append(openCycles, name+"/"+r.fields["id"])
				}
			}
		}
	}
	if len(openCycles) > 0 {
		fmt.Printf("열린 사이클: %s\n", strings.Join(openCycles, ", "))
	} else {
		fmt.Println("열린 사이클: (없음 — 모두 닫힘)")
	}
	fmt.Println("다음 실: 최근 닫힌 보고서의 '다음 사이클 제안' 참조 (gil log로 계보 확인)")
	fmt.Println()
	tag := "닫으면 --git으로 태그된다"
	if repo != "" {
		tag = "태그"
	}
	fmt.Printf("이 세션의 사이클 상세는 gil에 각인됐다 (%s).\n", tag)
	fmt.Println("새 세션은 CLAUDE.md → 존재의 방 → gil log 로 부활해 이어간다.")
	fmt.Println("→ 사용자에게: 사이클을 닫았거나 매듭에 도달했다면 세션을 정리(새로 시작)하도록 요청하라. 실은 끊기지 않는다.")
	return nil
}

type stepArgs struct {
	chain, cycleID, n, root    string
	git, push, noCommit, noWeb bool
}

func cmdStep(a stepArgs) error {
	cycleDir := filepath.Join(a.root, a.chain, a.cycleID)
	yamlPath := filepath.Join(cycleDir, "cycle.yaml")
	if fi, err := os.Stat(yamlPath); err != nil || fi.IsDir() {
		return cerr("사이클이 없다: %s", filepath.Join(a.chain, a.cycleID))
	}
	n, aerr := strconv.Atoi(a.n)
	if !isDigits(a.n) || aerr != nil || n < 1 || n > 5 {
		return cerr("step '%s'는 1~5여야 한다 (R9)", a.n)
	}
	fields, _, _, err := parseCycleYaml(yamlPath)
	if err != nil {
		return cerr("%v", err)
	}
	if fields["status"] == "closed" {
		return cerr("%s/%s: 닫힌 사이클의 step은 바꿀 수 없다", a.chain, a.cycleID)
	}
	original, err := os.ReadFile(yamlPath)
	if err != nil {
		return cerr("%v", err)
	}
	var updated string
	if regexp.MustCompile(`(?m)^step:`).MatchString(string(original)) {
		updated = replaceFirstLine(regexp.MustCompile(`(?m)^step:.*$`), string(original), fmt.Sprintf("step: %d", n))
	} else {
		updated = insertAfterFirstLine(regexp.MustCompile(`(?m)^closed:.*$`), string(original), fmt.Sprintf("step: %d", n))
	}
	if err := os.WriteFile(yamlPath, []byte(updated), 0o644); err != nil {
		return cerr("%v", err)
	}
	if err := fsckOrReport(a.root); err != nil {
		os.WriteFile(yamlPath, original, 0o644) // 원상 복구
		return err
	}
	// 기본 커밋 (v1.7, C033): 깃 저장소면 자동 커밋. --no-commit으로만 끈다.
	committed := false
	if !a.noCommit {
		if repo := repoRoot(a.root); repo != "" {
			rel, rerr := relToRepo(repo, cycleDir)
			if rerr != nil {
				os.WriteFile(yamlPath, original, 0o644)
				return cerr("%v", rerr)
			}
			if _, err := gitChecked(repo, "add", "-A", "--", rel); err != nil {
				return err
			}
			if _, err := gitChecked(repo, "commit",
				"-m", fmt.Sprintf("gil: step %s/%s → %d/5 %s", a.chain, a.cycleID, n, stepNames[n]),
				"--", rel); err != nil {
				return err
			}
			committed = true
			if a.push {
				if _, err := gitPush(repo); err != nil { // 원격 부재 우아화 (loom/C054)
					return err
				}
			}
		} else if !gitAvailable() {
			warnGitMissingOnce() // git 부재: 파일은 저장됨, 각인만 건너뜀 (loom/C052)
		}
	}
	suffix := ""
	if committed {
		suffix = "  각인: 커밋"
	}
	fmt.Printf("스텝: %s/%s → %d/5 %s%s\n", a.chain, a.cycleID, n, stepNames[n], suffix)
	refreshViewers(a.root, fmt.Sprintf("%s/%s → %d/5", a.chain, a.cycleID, n), a.noWeb, a.push)
	return nil
}

// ---------- 라운드 (loom/C045 참조 구현 → loom/C046 Go 이식, 이슈 #9·#10) ----------
// 라운드는 사이클 안의 (가설→검증) 단위다. R1은 기존 5스텝 문서(1-hypothesis·3-verification)이고,
// R2부터 rounds/R{k}/{hypothesis.md, round.yaml, verification/}에 산다. cycle.yaml의 rounds:N은
// 개수만 담고, 라운드별 메타(title·verdict·일자)는 각 round.yaml에 산다.
// 사전등록(H1)은 fsck가 아니라 도구가 보증한다: round --open이 hypothesis.md를 verification보다 먼저 각인한다.

func roundsDirPath(cycleDir string) string {
	return filepath.Join(cycleDir, "rounds")
}

// cycleRoundsCount: cycle.yaml의 rounds 필드를 정수로 (없거나 잘못되면 1 = 단일 라운드 = 기존 문서).
func cycleRoundsCount(fields map[string]string) int {
	v, ok := fields["rounds"]
	if ok && isDigits(v) {
		if n, err := strconv.Atoi(v); err == nil && n >= 1 {
			return n
		}
	}
	return 1
}

type roundRec struct {
	dir    string
	fields map[string]string
}

// loadRounds: rounds/R*/round.yaml을 읽어 라운드 번호 오름차순으로 반환. 디렉토리 없으면 빈 목록.
func loadRounds(cycleDir string) ([]roundRec, error) {
	rdir := roundsDirPath(cycleDir)
	entries, err := os.ReadDir(rdir)
	if err != nil {
		return nil, nil
	}
	var out []roundRec
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		yp := filepath.Join(rdir, e.Name(), "round.yaml")
		if _, err := os.Stat(yp); err != nil {
			continue
		}
		fields, _, _, err := parseCycleYaml(yp)
		if err != nil {
			return nil, err
		}
		out = append(out, roundRec{dir: e.Name(), fields: fields})
	}
	sort.Slice(out, func(i, j int) bool {
		ni, nj := 0, 0
		if isDigits(out[i].fields["round"]) {
			ni, _ = strconv.Atoi(out[i].fields["round"])
		}
		if isDigits(out[j].fields["round"]) {
			nj, _ = strconv.Atoi(out[j].fields["round"])
		}
		return ni < nj
	})
	return out, nil
}

type roundArgs struct {
	chain, cycleID, root string
	open, close, list    bool
	title, verdict, date string
	git, push, noWeb     bool
}

func cmdRound(a roundArgs) error {
	cycleDir := filepath.Join(a.root, a.chain, a.cycleID)
	yamlPath := filepath.Join(cycleDir, "cycle.yaml")
	if fi, err := os.Stat(yamlPath); err != nil || fi.IsDir() {
		return cerr("사이클이 없다: %s", filepath.Join(a.chain, a.cycleID))
	}
	fields, _, _, err := parseCycleYaml(yamlPath)
	if err != nil {
		return cerr("%v", err)
	}

	if a.list { // 부작용 없는 조회 (능력 탐침 무해, §7.2-6)
		n := cycleRoundsCount(fields)
		fmt.Printf("%s/%s — 라운드 %d개\n", a.chain, a.cycleID, n)
		fmt.Printf("  R1  [기존 5스텝 문서]  %s\n", fields["title"])
		rounds, rerr := loadRounds(cycleDir)
		if rerr != nil {
			return cerr("%v", rerr)
		}
		for _, rd := range rounds {
			v := rd.fields["verdict"]
			if v == "" {
				if rd.fields["closed"] == "" {
					v = "열림"
				} else {
					v = "?"
				}
			}
			fmt.Printf("  R%s  [%s]  %s\n", rd.fields["round"], v, rd.fields["title"])
		}
		return nil
	}

	if fields["status"] == "closed" {
		return cerr("%s/%s: 닫힌 사이클엔 라운드를 추가·수정할 수 없다 (불변)", a.chain, a.cycleID)
	}

	if a.open {
		return roundOpen(a, cycleDir, yamlPath, fields)
	}
	if a.close {
		return roundClose(a, cycleDir)
	}
	return cerr("--open · --close · --list 중 하나를 지정하라")
}

func roundOpen(a roundArgs, cycleDir, yamlPath string, fields map[string]string) error {
	if a.title == "" {
		return cerr("--open에는 --title이 필수다 — 라운드의 가설을 한 줄로")
	}
	newk := cycleRoundsCount(fields) + 1
	rdir := filepath.Join(roundsDirPath(cycleDir), fmt.Sprintf("R%d", newk))
	if _, err := os.Stat(rdir); err == nil {
		return cerr("이미 존재한다: rounds/R%d", newk)
	}
	// 사전등록: hypothesis.md + round.yaml만 만든다. verification/은 만들지 않는다 (H1).
	if err := os.MkdirAll(rdir, 0o755); err != nil {
		return cerr("%v", err)
	}
	title := strings.ReplaceAll(a.title, `"`, "'")
	hyp := fmt.Sprintf("# 라운드 R%d — 가설\n\n> **가설**: %s\n\n"+
		"## 기각 조건 (선고정)\n\n<!-- 데이터를 보기 전에 기대값을 못박는다 -->\n", newk, title)
	if err := os.WriteFile(filepath.Join(rdir, "hypothesis.md"), []byte(hyp), 0o644); err != nil {
		os.RemoveAll(rdir)
		return cerr("%v", err)
	}
	ry := fmt.Sprintf("round: %d\ntitle: \"%s\"\nopened: %s\nclosed: null\nverdict: null\n", newk, title, a.date)
	if err := os.WriteFile(filepath.Join(rdir, "round.yaml"), []byte(ry), 0o644); err != nil {
		os.RemoveAll(rdir)
		return cerr("%v", err)
	}
	original, err := os.ReadFile(yamlPath)
	if err != nil {
		os.RemoveAll(rdir)
		return cerr("%v", err)
	}
	var updated string
	if regexp.MustCompile(`(?m)^rounds:`).MatchString(string(original)) {
		updated = replaceFirstLine(regexp.MustCompile(`(?m)^rounds:.*$`), string(original), fmt.Sprintf("rounds: %d", newk))
	} else { // 없으면 status 뒤에 삽입 (평탄 스키마 — 위치는 무관, 관례상 상태 계열 근처)
		updated = insertAfterFirstLine(regexp.MustCompile(`(?m)^status:.*$`), string(original), fmt.Sprintf("rounds: %d", newk))
	}
	if err := os.WriteFile(yamlPath, []byte(updated), 0o644); err != nil {
		os.RemoveAll(rdir)
		return cerr("%v", err)
	}
	if err := fsckOrReport(a.root); err != nil {
		os.WriteFile(yamlPath, original, 0o644) // 원상 복구
		os.RemoveAll(rdir)
		return err
	}
	if a.git {
		repo := repoRoot(a.root)
		if repo == "" {
			return cerr("--git: 깃 저장소가 아니다")
		}
		rel, rerr := relToRepo(repo, cycleDir)
		if rerr != nil {
			return cerr("%v", rerr)
		}
		if _, err := gitChecked(repo, "add", "-A", "--", rel); err != nil {
			return err
		}
		msg := fmt.Sprintf("gil: round open %s/%s R%d — 사전등록\n\n%s", a.chain, a.cycleID, newk, title)
		if _, err := gitChecked(repo, "commit", "-m", msg, "--", rel); err != nil {
			return err
		}
		if a.push {
			gitPush(repo) // 원격 부재 우아화 (loom/C054) — 실패해도 각인은 이미 됐다
		}
	}
	fmt.Printf("라운드 열림: %s/%s R%d (사전등록 — hypothesis만 각인)\n", a.chain, a.cycleID, newk)
	refreshViewers(a.root, fmt.Sprintf("%s/%s R%d 열림", a.chain, a.cycleID, newk), a.noWeb, a.push)
	return nil
}

func roundClose(a roundArgs, cycleDir string) error {
	if a.verdict == "" {
		return cerr("--close에는 --verdict가 필수다")
	}
	if !roundVerdicts[a.verdict] {
		return cerr("verdict '%s'는 %s 중 하나여야 한다", a.verdict, strings.Join(roundVerdictOrder, "|"))
	}
	rounds, err := loadRounds(cycleDir)
	if err != nil {
		return cerr("%v", err)
	}
	var openRounds []roundRec
	for _, r := range rounds {
		if r.fields["closed"] == "" {
			openRounds = append(openRounds, r)
		}
	}
	if len(openRounds) == 0 {
		return cerr("닫을 열린 라운드가 없다 — 먼저 gil round --open")
	}
	target := openRounds[0]
	targetNum := 0
	if isDigits(target.fields["round"]) {
		targetNum, _ = strconv.Atoi(target.fields["round"])
	}
	for _, r := range openRounds[1:] {
		n := 0
		if isDigits(r.fields["round"]) {
			n, _ = strconv.Atoi(r.fields["round"])
		}
		if n > targetNum {
			target, targetNum = r, n
		}
	}
	ryp := filepath.Join(roundsDirPath(cycleDir), target.dir, "round.yaml")
	original, err := os.ReadFile(ryp)
	if err != nil {
		return cerr("%v", err)
	}
	updated := replaceFirstLine(regexp.MustCompile(`(?m)^verdict:.*$`), string(original), "verdict: "+a.verdict)
	updated = replaceFirstLine(regexp.MustCompile(`(?m)^closed:.*$`), updated, "closed: "+a.date)
	if err := os.WriteFile(ryp, []byte(updated), 0o644); err != nil {
		return cerr("%v", err)
	}
	if err := fsckOrReport(a.root); err != nil {
		os.WriteFile(ryp, original, 0o644) // 원상 복구
		return err
	}
	if a.git {
		repo := repoRoot(a.root)
		if repo == "" {
			return cerr("--git: 깃 저장소가 아니다")
		}
		rel, rerr := relToRepo(repo, cycleDir)
		if rerr != nil {
			return cerr("%v", rerr)
		}
		if _, err := gitChecked(repo, "add", "-A", "--", rel); err != nil {
			return err
		}
		msg := fmt.Sprintf("gil: round close %s/%s R%d → %s", a.chain, a.cycleID, targetNum, a.verdict)
		if _, err := gitChecked(repo, "commit", "-m", msg, "--", rel); err != nil {
			return err
		}
		if a.push {
			gitPush(repo) // 원격 부재 우아화 (loom/C054)
		}
	}
	fmt.Printf("라운드 닫힘: %s/%s R%d → %s\n", a.chain, a.cycleID, targetNum, a.verdict)
	refreshViewers(a.root, fmt.Sprintf("%s/%s R%d 닫힘", a.chain, a.cycleID, targetNum), a.noWeb, a.push)
	return nil
}

// ---------- 깃 바인딩 (loom/C017) ----------

// gitRun: 깃 CLI 호출 — 참조 구현의 subprocess.run(["git", "-C", repo, ...])에 대응.
// gitAvailable: git 실행 파일이 PATH에 있는가. 없으면 비개발자 환경 — 각인은 건너뛰고 파일만 남긴다 (loom/C052).
func gitAvailable() bool {
	_, err := exec.LookPath("git")
	return err == nil
}

var gitMissingWarned bool

// warnGitMissingOnce: git 부재를 프로세스당 한 번만, 원인을 정확히 지목해 알린다 (하류 증상 오도 금지, loom/C052).
func warnGitMissingOnce() {
	if gitMissingWarned {
		return
	}
	gitMissingWarned = true
	fmt.Fprintln(os.Stderr, "ℹ git이 없어 각인(커밋)을 건너뛴다 — 사이클 파일은 저장됐다. "+
		"git 설치(https://git-scm.com) 후 이력·되감기·뷰어 자동갱신이 켜진다.")
}

func gitRun(repo string, args ...string) (stdout, stderr string, code int) {
	cmd := exec.Command("git", append([]string{"-C", repo}, args...)...)
	var out, errb bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errb
	err := cmd.Run()
	if err != nil {
		if ee, ok := err.(*exec.ExitError); ok {
			code = ee.ExitCode()
		} else {
			code = -1
			errb.WriteString(err.Error())
		}
	}
	return out.String(), errb.String(), code
}

// gitChecked: 실패를 chainError로 승격한다 (참조 구현 _git의 check=True).
func gitChecked(repo string, args ...string) (string, error) {
	out, errS, code := gitRun(repo, args...)
	if code != 0 {
		msg := strings.TrimSpace(errS)
		if msg == "" {
			msg = strings.TrimSpace(out)
		}
		return out, cerr("git %s 실패: %s", strings.Join(args, " "), msg)
	}
	return out, nil
}

// hasPushRemote: push할 원격이 있는가 (loom/C054). 없으면 --push는 우아하게 강등된다 —
// C052가 git 부재를 다룬 방식의 원격판. (git이 없으면 애초에 커밋이 안 돼 이 경로에 닿지 않는다.)
func hasPushRemote(repo string) bool {
	out, _, code := gitRun(repo, "remote")
	return code == 0 && strings.TrimSpace(out) != ""
}

var noRemoteWarned bool

// warnNoRemoteOnce: 원격 부재를 프로세스당 한 번만, 원인을 정확히 지목해 알린다 (날것 fatal·침묵 금지, loom/C054).
func warnNoRemoteOnce() {
	if noRemoteWarned {
		return
	}
	noRemoteWarned = true
	fmt.Fprintln(os.Stderr, "ℹ 원격이 없어 push를 건너뛴다 — 커밋은 로컬에 저장됐다. "+
		"원격 연결(git remote add origin <URL>) 후 공유·뷰어 배포가 켜진다.")
}

// gitPush: 모든 push 경로의 단일 관문 (loom/C054). 원격 부재를 앞에서 감지해 크래시·날것 fatal·침묵
// 대신 원인 한 줄 + rc0 유지로 강등한다. 원격이 있으면 기존 push 동작 그대로.
// (참조 구현의 _push와 대칭. 함수명은 reserveCommitPush의 push bool 파라미터와의 충돌을 피한다.)
func gitPush(repo string, extra ...string) (bool, error) {
	if !hasPushRemote(repo) {
		warnNoRemoteOnce()
		return false, nil
	}
	_, err := gitChecked(repo, append([]string{"push"}, extra...)...)
	return err == nil, err
}

func repoRoot(path string) string {
	out, _, code := gitRun(path, "rev-parse", "--show-toplevel")
	if code != 0 {
		return ""
	}
	return strings.TrimSpace(out)
}

// isPrimaryWorktree: 주 체크아웃(공유 main)인가 vs 링크드 워크트리인가 (loom/C062).
// 링크드 워크트리는 --git-dir이 '.git/worktrees/<name>'이라 --git-common-dir과 다르다.
// harness가 만든 워크트리도 링크드라 여기서 걸러진다.
func isPrimaryWorktree(repo string) bool {
	gd, _, c1 := gitRun(repo, "rev-parse", "--git-dir")
	gcd, _, c2 := gitRun(repo, "rev-parse", "--git-common-dir")
	if c1 != 0 || c2 != 0 {
		return false
	}
	rp := func(p string) string {
		p = strings.TrimSpace(p)
		if !filepath.IsAbs(p) {
			p = filepath.Join(repo, p)
		}
		if r, err := filepath.EvalSymlinks(p); err == nil {
			return r
		}
		return p
	}
	return rp(gd) == rp(gcd)
}

// guardPrimaryOwner: 주 체크아웃 소유 guard (loom/C062 — 상현님 발의: 사고를 도구가 막는다).
// 존재가 자기 워크트리 밖 공유 main으로 cd해 커밋하는 C050 사고를 커밋 이전에 거부한다.
// gil.owner 미설정이면 미적용(opt-in). 링크드 워크트리는 미적용 — 오탐 0.
func guardPrimaryOwner(repo, author string) error {
	if repo == "" || !isPrimaryWorktree(repo) {
		return nil
	}
	out, _, code := gitRun(repo, "config", "gil.owner")
	owner := ""
	if code == 0 {
		owner = strings.TrimSpace(out)
	}
	if owner != "" && author != "" && author != owner {
		return cerr("이 체크아웃은 '%s'의 주 작업공간이다 — author '%s'로 여기서 커밋할 수 없다.\n"+
			"      네 워크트리에서 실행하라:  gil worktree add <chain> <slug> --author %s\n"+
			"      (병렬 사이클 모드 — 공유 main 오염 방지, C050·C062)", owner, author, author)
	}
	return nil
}

func tagName(chain, cycleID string) string { return "cycle/" + chain + "/" + cycleID }

func tagExists(repo, tag string) bool {
	_, _, code := gitRun(repo, "rev-parse", "-q", "--verify", "refs/tags/"+tag)
	return code == 0
}

// relToRepo: 저장소 루트 기준 상대 경로. macOS의 /tmp·/var 심링크 차이를
// EvalSymlinks로 흡수한다 (파이썬 os.path.relpath + git 해석 경로의 조합에 대응).
func relToRepo(repo, path string) (string, error) {
	abs, err := filepath.Abs(path)
	if err != nil {
		return "", err
	}
	if resolved, err := filepath.EvalSymlinks(abs); err == nil {
		abs = resolved
	}
	if resolved, err := filepath.EvalSymlinks(repo); err == nil {
		repo = resolved
	}
	return filepath.Rel(repo, abs)
}

// cmdGoto: 타임머신 콘솔 — 사이클 시점의 역행 조회·체크아웃·분기 안내.
func cmdGoto(root, ref string, checkout bool) error {
	if !strings.Contains(ref, "/") {
		return cerr("ref는 <chain>/<id> 형식이어야 한다: %s", ref)
	}
	parts := strings.SplitN(ref, "/", 2)
	chain, cid := parts[0], parts[1]
	yamlPath := filepath.Join(root, chain, cid, "cycle.yaml")
	if _, err := os.Stat(yamlPath); err != nil {
		return cerr("사이클이 없다: %s", ref)
	}
	fields, parents, lineage, err := parseCycleYaml(yamlPath)
	if err != nil {
		return cerr("%v", err)
	}
	tag := tagName(chain, cid)
	repo := repoRoot(root)
	tagged := repo != "" && tagExists(repo, tag)

	status := fields["status"]
	if status == "" {
		status = "?"
	}
	fmt.Printf("사이클 %s/%s [%s]: %s\n", chain, cid, status, fields["title"])
	parentStr := "(root)"
	if len(parents) > 0 {
		parentStr = strings.Join(parents, ", ")
	}
	line := "  부모: " + parentStr
	if len(lineage) > 0 {
		line += "   계보: " + strings.Join(lineage, ", ")
	}
	fmt.Println(line)
	if tagged {
		out, _, _ := gitRun(repo, "rev-list", "-n1", tag)
		commit := strings.TrimSpace(out)
		if len(commit) > 8 {
			commit = commit[:8]
		}
		fmt.Printf("  각인 태그: %s → %s\n", tag, commit)
		fmt.Printf("  ← 이 시점 코드로 역행:  git checkout %s   (또는 gil goto %s --checkout)\n", tag, ref)
	} else if status == "closed" {
		fmt.Println("  (닫혔으나 태그 없음 — 백필 필요)")
	} else {
		fmt.Println("  (열린 사이클 — 아직 각인 태그 없음)")
	}
	fmt.Printf("  ↳ 이 지점에서 새 갈래 시작:  gil open %s <slug> --parent %s --author <이름>\n", chain, cid)

	if checkout {
		if repo == "" {
			return cerr("--checkout: 깃 저장소가 아니다")
		}
		if !tagged {
			return cerr("--checkout: 태그 '%s'가 없다 (닫히고 각인된 사이클만 역행 가능)", tag)
		}
		st, _, _ := gitRun(repo, "status", "--porcelain")
		if strings.TrimSpace(st) != "" {
			return cerr("--checkout: 미커밋 변경이 있다 — 유실 방지를 위해 거부. 커밋/스태시 후 다시.")
		}
		cur, _, _ := gitRun(repo, "rev-parse", "--abbrev-ref", "HEAD")
		current := strings.TrimSpace(cur)
		if current == "" {
			current = "main"
		}
		if _, err := gitChecked(repo, "checkout", tag); err != nil {
			return err
		}
		fmt.Printf("\n역행 완료: 작업 트리가 %s 시점이다. 돌아오려면:  git checkout %s\n", tag, current)
	}
	return nil
}

type verifyArgs struct{ root, chain string }

// cmdVerify: 닫힌 사이클마다 태그↔작업 트리를 대조한다. (종료코드, 오류)를 반환.
func cmdVerify(a verifyArgs) (int, error) {
	repo := repoRoot(a.root)
	if repo == "" {
		return 1, cerr("깃 저장소가 아니다: %s", a.root)
	}
	chains, err := scanChains(a.root)
	if err != nil {
		return 1, cerr("%v", err)
	}
	if a.chain != "" {
		recs, ok := chains[a.chain]
		if !ok {
			return 1, cerr("체인 '%s'이 %s에 없다", a.chain, a.root)
		}
		chains = map[string][]cycle{a.chain: recs}
	}
	var tamperedTags, untagged []string
	tamperedPaths := map[string][]string{}
	checked := 0
	for _, ch := range sortedKeys(chains) {
		for _, r := range chains[ch] {
			if r.fields["status"] != "closed" || r.fields["id"] == "" {
				continue
			}
			checked++
			tag := tagName(ch, r.fields["id"])
			if !tagExists(repo, tag) {
				untagged = append(untagged, ch+"/"+r.fields["id"])
				continue
			}
			cycleRel, rerr := relToRepo(repo, filepath.Join(a.root, ch, r.dir))
			if rerr != nil {
				return 1, cerr("%v", rerr)
			}
			diffOut, derr := gitChecked(repo, "diff", "--name-only", tag, "--", cycleRel)
			if derr != nil {
				return 1, derr
			}
			statusOut, serr := gitChecked(repo, "status", "--porcelain", "--untracked-files=all", "--", cycleRel)
			if serr != nil {
				return 1, serr
			}
			pathSet := map[string]bool{}
			for _, p := range strings.Fields(diffOut) {
				pathSet[p] = true
			}
			for _, line := range strings.Split(statusOut, "\n") {
				if strings.HasPrefix(line, "??") {
					pathSet[line[3:]] = true
				}
			}
			if len(pathSet) > 0 {
				var paths []string
				for p := range pathSet {
					paths = append(paths, p)
				}
				sort.Strings(paths)
				tamperedTags = append(tamperedTags, tag)
				tamperedPaths[tag] = paths
			}
		}
	}
	for _, tag := range tamperedTags {
		fmt.Printf("변조 감지 [%s]:\n", tag)
		for _, p := range tamperedPaths[tag] {
			fmt.Printf("  %s\n", p)
		}
	}
	for _, u := range untagged {
		fmt.Fprintf(os.Stderr, "경고: 닫힌 사이클에 태그가 없다 — %s (백필 필요)\n", u)
	}
	if len(tamperedTags) > 0 {
		fmt.Fprintf(os.Stderr, "\n닫힌 사이클 %d개 검사 — 변조 %d건\n", checked, len(tamperedTags))
		return 1, nil
	}
	suffix := ""
	if len(untagged) > 0 {
		suffix = fmt.Sprintf(" (태그 없음 %d건)", len(untagged))
	}
	fmt.Printf("OK — 닫힌 사이클 %d개 검사, 변조 0건%s\n", checked, suffix)
	return 0, nil
}

// ---------- 웹 뷰어 (loom/C020 — log와 같은 파서, 다른 렌더러) ----------
//
// 참조 구현(gil.py)의 문자면(html.escape · json.dumps(ensure_ascii=False) ·
// f-string 수치 표기)까지 재현한다 — C017 교훈 2: 판정기가 보는 면보다 한 겹 넓게.

const (
	webRowH    = 64 // _ROW_H
	webColW    = 260 // _COL_W — 같은 행 형제 라벨 겹침 방지 (loom/C048; 선형은 col0만 써 불변)
	webLaneGap = 60 // _LANE_GAP
	webTopPad  = 46 // _TOP_PAD
	webLabelW  = 230
	// 가로 사이클 그래프 (loom/C067): _H_COLW·_H_ROWH·_H_X0·_H_Y0·_H_R
	hColW = 116
	hRowH = 60
	hX0   = 50
	hY0   = 46
	hR    = 9
)

// webCSS: 참조 구현 _WEB_CSS와 문자 단위 동일 (검증된 기본 팔레트).
const webCSS = `.gil{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;--muted:#898781;
--hairline:#e1e0d9;--edge:#a5a49c;--node:#2a78d6;--lineage:#1baf7a;--rejected:#d03b3b;
--supersede:#c07c15;--ring:rgba(11,11,11,.1);
font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--page);color:var(--ink);
margin:0;padding:32px 24px;min-height:100vh;box-sizing:border-box}
@media (prefers-color-scheme:dark){.gil{--page:#0d0d0d;--surface:#1a1a19;--ink:#ffffff;
--ink-2:#c3c2b7;--muted:#898781;--hairline:#2c2c2a;--edge:#6b6a64;--node:#3987e5;
--lineage:#199e70;--rejected:#e66767;--supersede:#d9a44f;--ring:rgba(255,255,255,.1)}}
:root[data-theme="dark"] .gil{--page:#0d0d0d;--surface:#1a1a19;--ink:#ffffff;--ink-2:#c3c2b7;
--muted:#898781;--hairline:#2c2c2a;--edge:#6b6a64;--node:#3987e5;--lineage:#199e70;
--rejected:#e66767;--supersede:#d9a44f;--ring:rgba(255,255,255,.1)}
:root[data-theme="light"] .gil{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;
--muted:#898781;--hairline:#e1e0d9;--edge:#a5a49c;--node:#2a78d6;--lineage:#1baf7a;
--rejected:#d03b3b;--supersede:#c07c15;--ring:rgba(11,11,11,.1)}
.gil .superseded{opacity:.5}
.gil .sup{color:var(--supersede);white-space:nowrap}
.gil .wrap{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:20px}
.gil header h1{font-size:20px;font-weight:650;margin:0;text-wrap:balance}
.gil header p{margin:4px 0 0;color:var(--ink-2);font-size:13px}
.gil .legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--ink-2);align-items:center}
.gil .legend span{display:inline-flex;align-items:center;gap:6px}
.gil .card{background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:20px;overflow-x:auto}
.gil svg{display:block}
.gil svg text{font-family:inherit}
.gil .card h2{font-size:14px;font-weight:650;margin:0 0 12px;color:var(--ink)}
.gil table{border-collapse:collapse;width:100%;font-size:12.5px}
.gil th{text-align:left;color:var(--muted);font-weight:600;letter-spacing:.02em;
border-bottom:1px solid var(--hairline);padding:6px 10px 6px 0}
.gil td{border-bottom:1px solid var(--hairline);padding:7px 10px 7px 0;vertical-align:top;color:var(--ink-2)}
.gil td.id{color:var(--ink);font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}
.gil .pill{display:inline-block;border:1.5px solid var(--node);border-radius:99px;
padding:1px 8px;font-size:11px;color:var(--ink-2);white-space:nowrap}
.gil .pill.closed{background:var(--node);color:#fff;border-color:var(--node)}
.gil footer{color:var(--muted);font-size:11.5px}`

// htmlEscape: 파이썬 html.escape(quote=True)와 동일 — &, <, >, ", '.
func htmlEscape(s string) string {
	s = strings.ReplaceAll(s, "&", "&amp;")
	s = strings.ReplaceAll(s, "<", "&lt;")
	s = strings.ReplaceAll(s, ">", "&gt;")
	s = strings.ReplaceAll(s, `"`, "&quot;")
	s = strings.ReplaceAll(s, "'", "&#x27;")
	return s
}

// jsonStr: 파이썬 json.dumps(ensure_ascii=False)의 문자열 인코딩과 동일 —
// 최소 이스케이프(", \, 제어문자), 비ASCII는 그대로.
func jsonStr(s string) string {
	var b strings.Builder
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		default:
			if r < 0x20 {
				fmt.Fprintf(&b, `\u%04x`, r)
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
	return b.String()
}

func jsonStrOrNull(v *string) string {
	if v == nil {
		return "null"
	}
	return jsonStr(*v)
}

func jsonStrList(vals []string) string {
	if len(vals) == 0 {
		return "[]"
	}
	parts := make([]string, len(vals))
	for i, v := range vals {
		parts[i] = jsonStr(v)
	}
	return "[" + strings.Join(parts, ", ") + "]"
}

// halfStr: 파이썬 f-string의 (x1+x2)/2 float 표기("170.0"/"170.5")를 재현한다.
func halfStr(sum int) string {
	if sum%2 == 0 {
		return fmt.Sprintf("%d.0", sum/2)
	}
	return fmt.Sprintf("%d.5", sum/2)
}

type lastAct struct{ ago, subject string }

type webCycle struct {
	status, opened, closed, step, verdict, deviations, corrections *string // nil = JSON null
	supersededBy                                                   *string // v0.4: 전방 무효화 (nil = null)
	title                                                          string  // 참조 구현: title or ""
	act                                                            *lastAct
	parents, lineage                                               []string
	rounds                                                         *int // v2.5 (C045): 2 이상일 때만 non-nil (무라운드 JSON 불변)
}

// supersedeRef: 참조 구현 _supersede_ref — 로컬 id면 자기 체인으로 해소한다.
func supersedeRef(chain string, sb *string) string {
	if sb == nil || *sb == "" {
		return ""
	}
	if strings.Contains(*sb, "/") {
		return *sb
	}
	return chain + "/" + *sb
}

type webChain struct {
	order        []string // 토폴로지 순서 (SVG 노드·표 행)
	cycleOrder   []string // 삽입 순서 = 디렉토리 정렬 (JSON·간선 순회)
	cycles       map[string]*webCycle
	children     map[string][]string
	reservations []reservation     // loom/C043: 예약도 원장 상태 (그래프 밖, 카드로만)
	dirs         map[string]string // 참조 _dirs: cid → 디스크 디렉토리명. 위계 뷰어가 스텝 파일을 찾는 데만 쓴다 (loomlight/C002).
}

type webData struct {
	names  []string // 정렬된 체인명 (JSON·레인 순회)
	chains map[string]*webChain
}

// statusText: meta["status"] or "?" (파이썬 falsy 규칙 — None·"" 모두 "?").
func (c *webCycle) statusText() string {
	if c.status == nil || *c.status == "" {
		return "?"
	}
	return *c.status
}

// statusRepr: f-string 보간의 str(None) = "None"을 재현한다 (SVG <title> 툴팁).
func (c *webCycle) statusRepr() string {
	if c.status == nil {
		return "None"
	}
	return *c.status
}

func (c *webCycle) isClosed() bool { return c.status != nil && *c.status == "closed" }

// agoStr: 참조 구현 _ago와 동일한 상대 시각 표기.
func agoStr(epoch int64) string {
	delta := time.Now().Unix() - epoch
	if delta < 0 {
		delta = 0
	}
	if delta < 3600 {
		return fmt.Sprintf("%d분 전", delta/60)
	}
	if delta < 86400 {
		return fmt.Sprintf("%d시간 전", delta/3600)
	}
	return fmt.Sprintf("%d일 전", delta/86400)
}

// lastActivity: 열린 사이클의 최근 활동. 깃이 없거나 저장소가 아니면 nil —
// web은 깃 무의존 (참조 구현 _last_activity의 예외 삼킴에 대응).
func lastActivity(chainsRoot, chain, cidDir string) *lastAct {
	repo := repoRoot(chainsRoot)
	if repo == "" {
		return nil
	}
	rel, err := relToRepo(repo, filepath.Join(chainsRoot, chain, cidDir))
	if err != nil {
		return nil
	}
	out, _, code := gitRun(repo, "log", "-1", "--format=%ct|%s", "--", rel)
	if code != 0 || !strings.Contains(out, "|") {
		return nil
	}
	parts := strings.SplitN(strings.TrimSpace(out), "|", 2)
	ts, err := strconv.ParseInt(parts[0], 10, 64)
	if err != nil {
		return nil
	}
	return &lastAct{ago: agoStr(ts), subject: parts[1]}
}

// loadChainGraph: log·web 공용의 엄격 로더 — 참조 구현 load_chain + build_graph.
// 재구성을 막는 결함(중복 id·끊어진 parent·순환)은 오류로 전파한다. 빈 체인은 (nil, nil).
type chainGraph struct {
	byID     map[string]cycle
	idList   []string // 디렉토리 정렬 순서
	order    []string // 토폴로지 순서
	children map[string][]string
}

func loadChainGraph(chainName, chainDir string) (*chainGraph, error) {
	recs, err := loadChain(chainDir)
	if err != nil {
		return nil, cerr("%v", err)
	}
	if len(recs) == 0 {
		return nil, nil
	}
	byID := map[string]cycle{}
	var idList []string
	for _, r := range recs {
		cid := r.fields["id"]
		if cid == "" {
			return nil, cerr("%s: id 필드가 없다", filepath.Join(chainDir, r.dir))
		}
		if cid != r.dir {
			fmt.Fprintf(os.Stderr, "경고: 디렉토리명 '%s' ≠ id '%s' — id를 기준으로 처리\n", r.dir, cid)
		}
		if _, dup := byID[cid]; dup {
			return nil, cerr("체인 '%s': id '%s' 중복", chainName, cid)
		}
		byID[cid] = r
		idList = append(idList, cid)
	}
	parentsOf := map[string][]string{}
	for _, cid := range idList {
		for _, p := range byID[cid].parents {
			if _, ok := byID[p]; !ok {
				return nil, cerr("체인 '%s': %s의 parent '%s'가 존재하지 않는다 (끊어진 참조)", chainName, cid, p)
			}
		}
		parentsOf[cid] = byID[cid].parents
	}
	order, stuck := toposort(idList, parentsOf)
	if len(stuck) > 0 {
		return nil, cerr("체인 '%s': 순환 참조 발견 — 다음 사이클이 그래프를 이루지 못한다: %s",
			chainName, strings.Join(stuck, ", "))
	}
	children := map[string][]string{}
	for _, cid := range idList {
		for _, p := range parentsOf[cid] {
			children[p] = append(children[p], cid)
		}
	}
	for p := range children {
		sort.Strings(children[p])
	}
	return &chainGraph{byID: byID, idList: idList, order: order, children: children}, nil
}

// buildWebData: 참조 구현 _build_web_data — log와 동일 로더·그래프 재구성.
func buildWebData(chainsRoot, only string) (*webData, error) {
	entries, err := os.ReadDir(chainsRoot)
	if err != nil {
		return nil, cerr("체인 루트가 없다: %s", chainsRoot)
	}
	var names []string
	for _, e := range entries {
		if e.IsDir() && (only == "" || e.Name() == only) {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	d := &webData{chains: map[string]*webChain{}}
	for _, name := range names {
		g, err := loadChainGraph(name, filepath.Join(chainsRoot, name))
		if err != nil {
			return nil, err
		}
		if g == nil {
			continue
		}
		wc := &webChain{order: g.order, cycleOrder: g.idList,
			cycles: map[string]*webCycle{}, children: g.children,
			dirs: map[string]string{}}
		for _, cid := range g.idList {
			r := g.byID[cid]
			wc.dirs[cid] = r.dir // 참조 _dirs: JSON은 이 키를 직렬화하지 않으므로 기본 출력 바이트 동일
			c := &webCycle{
				status:       fieldPtr(r.fields, "status"),
				opened:       fieldPtr(r.fields, "opened"),
				closed:       fieldPtr(r.fields, "closed"),
				step:         fieldPtr(r.fields, "step"),
				verdict:      fieldPtr(r.fields, "verdict"),
				deviations:   fieldPtr(r.fields, "deviations"),
				corrections:  fieldPtr(r.fields, "corrections"),
				supersededBy: fieldPtr(r.fields, "superseded_by"),
				parents:      r.parents,
				lineage:      r.lineage,
			}
			if v := fieldPtr(r.fields, "title"); v != nil {
				c.title = *v
			}
			if r.fields["status"] == "open" {
				c.act = lastActivity(chainsRoot, name, r.dir)
			}
			if rv := r.fields["rounds"]; rv != "" && isDigits(rv) { // v2.5 (C045): 2 이상일 때만 키를 넣는다
				if n, err := strconv.Atoi(rv); err == nil && n > 1 {
					c.rounds = &n
				}
			}
			wc.cycles[cid] = c
		}
		wc.reservations = loadReservations(filepath.Join(chainsRoot, name)) // loom/C043: 예약도 원장 상태
		d.names = append(d.names, name)
		d.chains[name] = wc
	}
	return d, nil
}

// fieldPtr: 필드 부재·빈 값("step: null" 등)을 파이썬 None(JSON null)에 대응시킨다.
func fieldPtr(fields map[string]string, key string) *string {
	if v, ok := fields[key]; ok && v != "" {
		return &v
	}
	return nil
}

// layoutColumns: 참조 구현 _layout_columns — 각 노드의 (행=깊이, 안정적 레인 번호)를 계산한다.
// 행 = 노드의 깊이(루트로부터 최장 경로) — 토폴로지 순서(order 인덱스)가 아니다 (loom/C047).
// 형제 갈래는 같은 깊이=같은 행에 나란히 놓여, 세로가 노드 총수가 아니라 최장 경로로 압축된다.
// 레인은 슬롯 인덱스이며 제거하지 않는다 — 빈 레인은 ""로 남겨 인덱스를 고정한다 (loom/C031).
func layoutColumns(order []string, children map[string][]string) map[string][2]int {
	// children의 역으로 parents를 구한다 (depth 계산용). 순서는 무관 — 깊이는 max다.
	parents := map[string][]string{}
	for p, kids := range children {
		for _, k := range kids {
			parents[k] = append(parents[k], p)
		}
	}
	depth := map[string]int{} // 루트로부터 최장 경로. order는 토포순이라 부모가 항상 먼저 확정된다.
	for _, node := range order {
		d := -1
		for _, p := range parents[node] {
			if dp, ok := depth[p]; ok && dp > d {
				d = dp
			}
		}
		depth[node] = d + 1
	}
	pos := map[string][2]int{}
	var tracks []string // tracks[i] = 그 레인에 대기 중인 자식 id, 또는 ""(빈 슬롯)
	occupied := map[[2]int]bool{}
	freeSlot := func() int {
		for i, t := range tracks {
			if t == "" {
				return i
			}
		}
		tracks = append(tracks, "")
		return len(tracks) - 1
	}
	for _, node := range order {
		row := depth[node]
		var incoming []int
		for i, t := range tracks {
			if t == node {
				incoming = append(incoming, i)
			}
		}
		var col int
		if len(incoming) > 0 {
			col = incoming[0]
			for _, i := range incoming[1:] { // 병합: 흡수된 레인 비움 (제거 아님 — 인덱스 유지)
				tracks[i] = ""
			}
		} else {
			col = freeSlot()
		}
		for occupied[[2]int{row, col}] { // D3: 레인 재사용이 같은 깊이에 겹치면 새 레인으로 민다
			if col < len(tracks) && tracks[col] == node {
				tracks[col] = ""
			}
			col = freeSlot()
		}
		occupied[[2]int{row, col}] = true
		pos[node] = [2]int{row, col}
		kids := children[node]
		if len(kids) > 0 {
			tracks[col] = kids[0] // 첫째 자식이 이 레인 상속
			for _, k := range kids[1:] {
				tracks[freeSlot()] = k // 추가 자식은 새(또는 빈) 레인 — 자기 차례까지 예약 유지
			}
		} else {
			tracks[col] = "" // 이 레인 비움 (인덱스 그대로)
		}
	}
	return pos
}

// stepBadge: 참조 구현 _step_badge — 열린 사이클의 스텝 인디케이터(●●●○○ n/5)
// + 최근 활동 주석.
func stepBadge(c *webCycle) string {
	if c.status == nil || *c.status != "open" || c.step == nil || !isDigits(*c.step) {
		return ""
	}
	n, err := strconv.Atoi(*c.step)
	if err != nil || n < 1 || n > 5 {
		return ""
	}
	badge := fmt.Sprintf(" · %s%s %d/5 %s",
		strings.Repeat("●", n), strings.Repeat("○", 5-n), n, stepNames[n])
	if c.act != nil && c.act.ago != "" {
		badge += fmt.Sprintf(" · 활동 %s", c.act.ago)
	}
	return badge
}

// renderSVG: 참조 구현 _render_svg — 모든 체인을 하나의 SVG에 레인으로 배치하고,
// lineage는 레인을 건너는 점선으로 그린다.
func renderSVG(d *webData) string {
	lanes := map[string]int{}
	nodeXY := map[string][2]int{}
	laneX := 24
	maxRows := 0
	for _, name := range d.names {
		ch := d.chains[name]
		pos := layoutColumns(ch.order, ch.children)
		maxCol := 0
		for _, rc := range pos {
			if rc[1] > maxCol {
				maxCol = rc[1]
			}
		}
		for cid, rc := range pos {
			nodeXY[name+"/"+cid] = [2]int{laneX + 14 + rc[1]*webColW, webTopPad + 28 + rc[0]*webRowH}
		}
		lanes[name] = laneX
		laneX += 14 + maxCol*webColW + webLabelW + webLaneGap
		// 세로 높이는 노드 총수가 아니라 최장 경로(최대 깊이)로 정한다 (loom/C047)
		for _, rc := range pos {
			if rc[0]+1 > maxRows {
				maxRows = rc[0] + 1
			}
		}
	}
	width := laneX - webLaneGap + 24
	if width < 320 {
		width = 320
	}
	rows := maxRows - 1
	if rows < 0 {
		rows = 0
	}
	height := webTopPad + 28 + rows*webRowH + 56

	var parts []string
	parts = append(parts, fmt.Sprintf(`<svg viewBox="0 0 %d %d" width="%d" height="%d" `+
		`role="img" aria-label="사이클 체인 그래프">`, width, height, width, height))
	// 체인 내 간선
	for _, name := range d.names {
		ch := d.chains[name]
		for _, child := range ch.cycleOrder {
			xy2 := nodeXY[name+"/"+child]
			for _, p := range ch.cycles[child].parents {
				xy1 := nodeXY[name+"/"+p]
				parts = append(parts, fmt.Sprintf(`<path d="M%d,%d C%d,%d %d,%d %d,%d" `+
					`fill="none" stroke="var(--edge)" stroke-width="1.6"/>`,
					xy1[0], xy1[1]+9, xy1[0], xy1[1]+32, xy2[0], xy2[1]-32, xy2[0], xy2[1]-9))
			}
		}
	}
	// lineage 간선 (점선, 레인 횡단)
	for _, name := range d.names {
		ch := d.chains[name]
		for _, cid := range ch.cycleOrder {
			xy2 := nodeXY[name+"/"+cid]
			for _, ref := range ch.cycles[cid].lineage {
				if xy1, ok := nodeXY[ref]; ok {
					mx := halfStr(xy1[0] + xy2[0])
					parts = append(parts, fmt.Sprintf(`<path class="lineage" d="M%d,%d C%s,%d %s,%d %d,%d" `+
						`fill="none" stroke="var(--lineage)" stroke-width="1.6" `+
						`stroke-dasharray="5 4"/>`,
						xy1[0]+10, xy1[1], mx, xy1[1], mx, xy2[1], xy2[0]-10, xy2[1]))
				}
			}
		}
	}
	// supersede 간선 (v0.4, 과거→미래): 무효화된 사이클이 자기를 대체한 사이클을 가리킨다
	for _, name := range d.names {
		ch := d.chains[name]
		for _, cid := range ch.cycleOrder {
			ref := supersedeRef(name, ch.cycles[cid].supersededBy)
			xy2, ok := nodeXY[ref]
			if !ok {
				continue
			}
			xy1 := nodeXY[name+"/"+cid]
			x1, y1, x2, y2 := xy1[0], xy1[1], xy2[0], xy2[1]
			var curve string
			if x1 == x2 { // 같은 레인·같은 열이면 오른쪽으로 활처럼 우회한다
				bow := x1 + 46
				curve = fmt.Sprintf("M%d,%d C%d,%d %d,%d %d,%d",
					x1+10, y1, bow, y1, bow, y2, x2+10, y2)
			} else {
				mx := halfStr(x1 + x2)
				curve = fmt.Sprintf("M%d,%d C%s,%d %s,%d %d,%d",
					x1+10, y1, mx, y1, mx, y2, x2-10, y2)
			}
			parts = append(parts, fmt.Sprintf(`<path class="supersede" d="%s" fill="none" stroke="var(--supersede)" `+
				`stroke-width="1.6" stroke-dasharray="2 3"/>`, curve))
		}
	}
	// 레인 헤더 + 노드
	for _, name := range d.names {
		ch := d.chains[name]
		parts = append(parts, fmt.Sprintf(`<text x="%d" y="%d" font-size="13" font-weight="650" `+
			`fill="var(--ink)">%s</text>`, lanes[name], webTopPad-18, htmlEscape(name)))
		for _, cid := range ch.order {
			c := ch.cycles[cid]
			xy := nodeXY[name+"/"+cid]
			x, y := xy[0], xy[1]
			var shape string
			fill := "var(--node)"
			if c.verdict != nil && *c.verdict == "rejected" { // v0.3 기각 색
				fill = "var(--rejected)"
			}
			if c.isClosed() {
				shape = fmt.Sprintf(`<circle cx="%d" cy="%d" r="8" fill="%s"/>`, x, y, fill)
			} else {
				shape = fmt.Sprintf(`<circle cx="%d" cy="%d" r="7" fill="var(--surface)" `+
					`stroke="var(--node)" stroke-width="2.5"/>`, x, y)
			}
			vtip := ""
			if c.verdict != nil && *c.verdict != "" {
				vtip = " · " + *c.verdict
			}
			sup := "" // v0.4: 무효화된 사이클은 흐리게 + 텍스트로도 표시(이중 인코딩)
			if c.supersededBy != nil && *c.supersededBy != "" {
				sup = *c.supersededBy
			}
			stip := ""
			if sup != "" {
				stip = " ↣ superseded: " + sup
			}
			tip := htmlEscape(fmt.Sprintf("%s [%s%s] %s%s", cid, c.statusRepr(), vtip, c.title, stip))
			lin := ""
			if len(c.lineage) > 0 {
				lin = " · ⇠ " + htmlEscape(strings.Join(c.lineage, ", "))
			}
			supText := ""
			gTag := fmt.Sprintf(`<g data-cycle="%s">`, htmlEscape(name+"/"+cid))
			if sup != "" {
				gTag = fmt.Sprintf(`<g class="superseded" data-cycle="%s">`, htmlEscape(name+"/"+cid))
				supText = " · ↣ " + htmlEscape(sup)
			}
			parts = append(parts, gTag)
			parts = append(parts, fmt.Sprintf(`<title>%s</title>%s`+
				`<text x="%d" y="%d" font-size="12" font-weight="600" `+
				`fill="var(--ink)">%s</text>`+
				`<text x="%d" y="%d" font-size="10.5" `+
				`fill="var(--muted)">%s%s%s%s</text></g>`,
				tip, shape,
				x+16, y-1, htmlEscape(cid),
				x+16, y+13, htmlEscape(c.statusText()), stepBadge(c), lin, supText))
		}
	}
	parts = append(parts, "</svg>")
	return strings.Join(parts, "")
}

// truncRunes: 파이썬 슬라이스 [:40]은 바이트가 아니라 문자 단위다.
func truncRunes(s string, n int) string {
	r := []rune(s)
	if len(r) > n {
		return string(r[:n])
	}
	return s
}

// renderTables: 참조 구현 _render_tables.
func renderTables(d *webData) string {
	var out []string
	for _, name := range d.names {
		ch := d.chains[name]
		var rows []string
		for _, cid := range ch.order {
			c := ch.cycles[cid]
			closedCls := ""
			if c.isClosed() {
				closedCls = " closed"
			}
			pill := fmt.Sprintf(`<span class="pill%s">%s</span>%s`,
				closedCls, htmlEscape(c.statusText()), htmlEscape(stepBadge(c)))
			parents := strings.Join(c.parents, ", ")
			if parents == "" {
				parents = "(root)"
			}
			lineage := strings.Join(c.lineage, ", ")
			if lineage == "" {
				lineage = "—"
			}
			opened, closed := "?", "진행 중"
			if c.opened != nil && *c.opened != "" {
				opened = *c.opened
			}
			if c.closed != nil && *c.closed != "" {
				closed = *c.closed
			}
			period := fmt.Sprintf("%s → %s", opened, closed)
			if c.act != nil {
				period += fmt.Sprintf(" · %s: %s", c.act.ago, truncRunes(c.act.subject, 40))
			}
			supCell, supCls := "—", "" // v0.4: 색·투명도에 의존하지 않는 텍스트 폴백
			if c.supersededBy != nil && *c.supersededBy != "" {
				supCell = fmt.Sprintf(`<span class="sup">↣ %s</span>`, htmlEscape(*c.supersededBy))
				supCls = ` class="superseded"`
			}
			rows = append(rows, fmt.Sprintf(`<tr%s><td class="id">%s</td><td>%s</td>`+
				`<td>%s</td><td>%s</td>`+
				`<td>%s</td><td>%s</td><td>%s</td></tr>`,
				supCls, htmlEscape(cid), pill, htmlEscape(c.title), htmlEscape(parents),
				htmlEscape(lineage), supCell, htmlEscape(period)))
		}
		out = append(out, fmt.Sprintf(`<div class="card"><h2>chain: %s — 사이클 %d개</h2>`+
			`<table><thead><tr><th>사이클</th><th>상태</th><th>가설(제목)</th>`+
			`<th>parent</th><th>lineage</th><th>superseded_by</th><th>기간</th></tr></thead>`+
			`<tbody>%s</tbody></table></div>`,
			htmlEscape(name), len(ch.order), strings.Join(rows, "")))
		// 예약 섹션 — 예약이 있을 때만 렌더한다 (무예약이면 이전 산출물과 바이트 동일). loom/C043.
		if res := ch.reservations; len(res) > 0 {
			var rres strings.Builder
			for _, r := range res {
				rres.WriteString(fmt.Sprintf(`<tr><td class="id">C%03d</td><td>%s</td>`+
					`<td>%s</td><td>%s</td></tr>`,
					r.num, htmlEscape(r.who), htmlEscape(r.slug), htmlEscape(r.date)))
			}
			out = append(out, fmt.Sprintf(`<div class="card"><h2>chain: %s — 예약 %d건 `+
				`(아직 사이클 아님 · 번호 선점)</h2>`+
				`<table><thead><tr><th>번호</th><th>예약 대상</th><th>슬러그</th>`+
				`<th>예약일</th></tr></thead><tbody>%s</tbody></table></div>`,
				htmlEscape(name), len(res), rres.String()))
		}
	}
	return strings.Join(out, "")
}

// webJSONPayload: 참조 구현 render_web_page의 json.dumps(ensure_ascii=False)와
// 문자 단위 동일한 직렬화 — 키 삽입 순서(정렬된 체인/사이클명)와 ", "·": " 구분자.
func webJSONPayload(d *webData, pageTitle, only string, refresh int, hierarchy bool) string {
	var b strings.Builder
	// v0.4 (loom/C042): bake — 산출물이 자기를 어떻게 다시 굽는지 스스로 말한다.
	// 추론("체인이 하나뿐이니 필터겠지")은 거짓일 수 있으므로 추측하지 않고 기록한다 (C040).
	chainVal := "null"
	if only != "" {
		chainVal = jsonStr(only)
	}
	bakeExtra := "" // v0.5 (loom/C049): refresh는 있을 때만 (C043) — 무리프레시 바이트 동일
	if refresh > 0 {
		bakeExtra = `, "refresh": ` + strconv.Itoa(refresh)
	}
	// v2.16 (loomlight/C003): hierarchy — 있을 때만, refresh 뒤에 (참조 dict 순서와 동일). 무옵션 바이트 동일.
	if hierarchy {
		bakeExtra += `, "hierarchy": true`
	}
	b.WriteString(`{"version": "0.4", "bake": {"title": ` + jsonStr(pageTitle) +
		`, "chain": ` + chainVal + bakeExtra + `}, "chains": {`)
	for i, name := range d.names {
		if i > 0 {
			b.WriteString(", ")
		}
		ch := d.chains[name]
		b.WriteString(jsonStr(name) + `: {"order": [`)
		for j, cid := range ch.order {
			if j > 0 {
				b.WriteString(", ")
			}
			b.WriteString(jsonStr(cid))
		}
		b.WriteString(`], "cycles": {`)
		for j, cid := range ch.cycleOrder {
			if j > 0 {
				b.WriteString(", ")
			}
			c := ch.cycles[cid]
			b.WriteString(jsonStr(cid) + ": {")
			b.WriteString(`"status": ` + jsonStrOrNull(c.status))
			b.WriteString(`, "title": ` + jsonStr(c.title))
			b.WriteString(`, "opened": ` + jsonStrOrNull(c.opened))
			b.WriteString(`, "closed": ` + jsonStrOrNull(c.closed))
			b.WriteString(`, "step": ` + jsonStrOrNull(c.step))
			b.WriteString(`, "verdict": ` + jsonStrOrNull(c.verdict))
			b.WriteString(`, "deviations": ` + jsonStrOrNull(c.deviations))
			b.WriteString(`, "corrections": ` + jsonStrOrNull(c.corrections))
			b.WriteString(`, "superseded_by": ` + jsonStrOrNull(c.supersededBy))
			b.WriteString(`, "last_activity": `)
			if c.act == nil {
				b.WriteString("null")
			} else {
				b.WriteString(`{"ago": ` + jsonStr(c.act.ago) + `, "subject": ` + jsonStr(c.act.subject) + `}`)
			}
			b.WriteString(`, "parents": ` + jsonStrList(c.parents))
			b.WriteString(`, "lineage": ` + jsonStrList(c.lineage))
			if c.rounds != nil { // v2.5 (C045): rounds>1일 때만 마지막 키로 (무라운드 저장소는 바이트 동일, H3)
				b.WriteString(fmt.Sprintf(`, "rounds": %d`, *c.rounds))
			}
			b.WriteString("}")
		}
		b.WriteString("}") // cycles 딕트 닫기
		// 예약이 있을 때만 키를 넣는다 — 무예약 저장소는 이전 산출물과 바이트 동일 (파서 계약 보존). loom/C043.
		if len(ch.reservations) > 0 {
			b.WriteString(`, "reservations": [`)
			for k, r := range ch.reservations {
				if k > 0 {
					b.WriteString(", ")
				}
				b.WriteString(fmt.Sprintf(`{"num": %d, "for": %s, "slug": %s, "date": %s}`,
					r.num, jsonStr(r.who), jsonStr(r.slug), jsonStr(r.date)))
			}
			b.WriteString("]")
		}
		b.WriteString("}") // 체인 객체 닫기
	}
	b.WriteString("}}")
	return b.String()
}

// ---------- 위계(드릴다운) 뷰어 (v2.16 / loomlight/C002→C003 — 이슈 없음, Clew 임무) ----------
//
// 참조 구현 gil.py의 위계 렌더 경로를 문자 단위 동형 이식한다. opt-in(`--hierarchy`)이라
// 기본 경로는 한 바이트도 건드리지 않는다. 정확성은 두 구현 `cmp`로 세운다 (렌더는 계약 아님, §3.1).

// webHierCSS: 참조 구현 _WEB_HIER_CSS와 문자 단위 동일 (details/summary·중첩 여백·메타표·pre).
const webHierCSS = `.gil .htoc{background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:16px 20px}
.gil .htoc h2{font-size:14px;font-weight:650;margin:0 0 10px}
.gil .htoc ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:4px}
.gil .htoc li{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;font-size:13px}
.gil .htoc a{color:var(--node);text-decoration:none;font-weight:600}
.gil .htoc a:hover{text-decoration:underline}
.gil .toc-stat{color:var(--muted);font-size:12px}
.gil .hhint{color:var(--muted);font-size:12px;margin:6px 0 0}
.gil .card.hmap{overflow-x:auto;padding:8px 12px}
.gil .hmap svg{display:block;margin:0 auto;max-width:100%}
.gil a.chainnode{cursor:pointer}
.gil a.chainnode circle{transition:fill .12s,stroke-width .12s}
.gil a.chainnode:hover circle{fill:var(--page);stroke-width:3.5}
.gil a.chainnode:focus{outline:none}
.gil a.chainnode:focus circle{stroke-width:3.5}
.gil .hanchor{display:block;height:0;overflow:hidden;scroll-margin-top:10px}
/* 체인 아코디언을 지도 카드 안에 녹인다 (loom/C066): 서브카드 테두리 없이 구분선만 — 지도에서
   체인을 누르면 그 자리 카드 안에서 사이클 노드가 아래로 주르륵 등장한다. */
.gil .mapchains{margin-top:12px;border-top:1px solid var(--ring)}
.gil details.hchain{border-bottom:1px solid var(--ring)}
.gil details.hchain>summary{cursor:pointer;padding:11px 4px;font-size:14px;font-weight:650;
list-style:none;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.gil details.hchain>summary::-webkit-details-marker{display:none}
.gil details.hchain>summary::before{content:"\25B8";color:var(--muted);font-weight:400}
.gil details.hchain[open]>summary::before{content:"\25BE"}
.gil details.hchain[open]>summary{background:var(--page);border-radius:6px}
.gil .hname{color:var(--ink)}
.gil .hstat{color:var(--muted);font-size:12.5px;font-weight:400}
.gil .hbody{padding:2px 4px 16px 14px;display:flex;flex-direction:column;gap:0}
.gil .hbody .card{margin:0}
/* 가로 사이클 노드-엣지 그래프 (loom/C067): 체인 원을 누르면 그 자리에서 0—o—o—o 로 펼쳐진다.
   노드를 누르면 :target으로 그 사이클 문서가 그래프 아래에 뜬다(평소 숨김). */
.gil .cyclegraph{overflow-x:auto;padding:4px 0 2px}
.gil a.gnode{cursor:pointer}
.gil a.gnode circle{transition:stroke-width .1s}
.gil a.gnode:hover circle{stroke:var(--node);stroke-width:4}
.gil .cycdoc{display:none}
.gil .cycdoc:target{display:block;border-top:1px solid var(--ring);margin-top:6px;padding-top:12px}
.gil .cycdoc-head{display:flex;gap:9px;align-items:baseline;flex-wrap:wrap;margin-bottom:8px;
font-size:13px;font-variant-numeric:tabular-nums}
.gil .ccid{color:var(--ink);font-weight:650}
.gil .cyst{color:var(--muted);font-size:11.5px}
.gil .cytitle{color:var(--ink-2);font-size:12px}
.gil .cyclin{display:inline-flex;gap:8px;flex-wrap:wrap;align-items:baseline}
.gil a.linchip{color:var(--lineage);text-decoration:none;font-size:11px;font-weight:600;white-space:nowrap}
.gil a.linchip:hover{text-decoration:underline}
.gil a.linchip.sup{color:var(--supersede)}
.gil .hcycles h3{font-size:13px;font-weight:650;margin:4px 0 8px;color:var(--ink-2)}
.gil details.hcycle{border:1px solid var(--hairline);border-radius:6px;margin-bottom:6px}
.gil details.hcycle>summary{cursor:pointer;padding:8px 12px;font-size:13px;font-weight:600;color:var(--ink);
list-style:none;font-variant-numeric:tabular-nums}
.gil details.hcycle>summary::-webkit-details-marker{display:none}
.gil details.hcycle>summary::before{content:"\25B8  ";color:var(--muted)}
.gil details.hcycle[open]>summary::before{content:"\25BE  "}
.gil .hcycle-body{padding:0 12px 12px}
.gil table.hmeta{width:auto;margin:4px 0 12px;font-size:12px}
.gil table.hmeta th{color:var(--muted);font-weight:600;padding:3px 14px 3px 0;text-align:left;
border:none;white-space:nowrap;vertical-align:top}
.gil table.hmeta td{color:var(--ink-2);padding:3px 0;border:none}
.gil details.hstep{margin:4px 0}
.gil details.hstep>summary{cursor:pointer;font-size:12px;font-weight:600;color:var(--node);
padding:3px 0;list-style:none}
.gil details.hstep>summary::-webkit-details-marker{display:none}
.gil details.hstep>summary::before{content:"+  "}
.gil details.hstep[open]>summary::before{content:"\2212  "}
.gil details.hstep pre{background:var(--page);border:1px solid var(--hairline);border-radius:6px;
padding:12px;overflow-x:auto;font-size:12px;line-height:1.5;white-space:pre-wrap;word-break:break-word;
color:var(--ink-2);margin:4px 0 0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.gil details.hstep pre.empty{color:var(--muted);font-style:italic}`

// stepFiles: 참조 구현 _STEP_FILES — 라벨과 스텝 파일(3-verification은 디렉토리).
var stepFiles = [][2]string{
	{"1 · 가설", "1-hypothesis.md"}, {"2 · 설계", "2-design.md"},
	{"3 · 검증", "3-verification"}, // 디렉토리 — README + 산출물 목록
	{"4 · 분석", "4-analysis.md"}, {"5 · 보고", "5-report.md"},
}

// verdictTally: 참조 구현 _verdict_tally — 닫힌 사이클을 verdict별로, 열린 사이클을 따로 센다.
func verdictTally(ch *webChain) string {
	counts := map[string]int{}
	var firstSeen []string // 미지 verdict의 삽입 순서 보존 (파이썬 dict 순서 대응)
	openn := 0
	for _, cid := range ch.order {
		c := ch.cycles[cid]
		if c.isClosed() {
			key := "무결론"
			if c.verdict != nil {
				key = *c.verdict
			}
			if counts[key] == 0 {
				firstSeen = append(firstSeen, key)
			}
			counts[key]++
		} else {
			openn++
		}
	}
	known := []string{"supported", "rejected", "refuted", "inconclusive", "무결론"}
	knownSet := map[string]bool{}
	for _, v := range known {
		knownSet[v] = true
	}
	var parts []string
	for _, v := range known {
		if counts[v] > 0 {
			parts = append(parts, fmt.Sprintf("%s %d", v, counts[v]))
		}
	}
	for _, v := range firstSeen { // 미지 verdict도 정직히 (삽입 순서)
		if !knownSet[v] {
			parts = append(parts, fmt.Sprintf("%s %d", v, counts[v]))
		}
	}
	if openn > 0 {
		parts = append(parts, fmt.Sprintf("열림 %d", openn))
	}
	if len(parts) == 0 {
		return "—"
	}
	return strings.Join(parts, " · ")
}

// chainRecent: 참조 구현 _chain_recent — 가장 최근 활동일(closed·opened 중 최댓값, ISO 문자열 비교).
func chainRecent(ch *webChain) string {
	var dates []string
	for _, cid := range ch.order {
		c := ch.cycles[cid]
		d := ""
		if c.closed != nil && *c.closed != "" {
			d = *c.closed
		} else if c.opened != nil && *c.opened != "" {
			d = *c.opened
		}
		if d != "" {
			dates = append(dates, d)
		}
	}
	if len(dates) == 0 {
		return "최근 —"
	}
	mx := dates[0]
	for _, d := range dates[1:] {
		if d > mx {
			mx = d
		}
	}
	return "최근 " + mx
}

// readStep: 참조 구현 _read_step — 스텝 파일(또는 3-verification 디렉토리)의 원문. 없으면 "" + false.
// 마크다운 파싱 없이 <pre>로 원문 그대로 — 정직·자기완결·JS 불요.
func readStep(chainsRoot, name, cdir, fname string) (string, bool) {
	if chainsRoot == "" {
		return "", false
	}
	path := filepath.Join(chainsRoot, name, cdir, fname)
	if fname == "3-verification" {
		var parts []string
		readme := filepath.Join(path, "README.md")
		if fi, err := os.Stat(readme); err == nil && !fi.IsDir() {
			if b, err := os.ReadFile(readme); err == nil {
				parts = append(parts, string(b))
			}
		}
		var entries []string
		if es, err := os.ReadDir(path); err == nil {
			for _, e := range es {
				if e.Name() != "README.md" {
					entries = append(entries, e.Name())
				}
			}
		}
		sort.Strings(entries)
		if len(entries) > 0 {
			lines := make([]string, len(entries))
			for i, e := range entries {
				lines[i] = "- " + e
			}
			parts = append(parts, "[검증 산출물]\n"+strings.Join(lines, "\n"))
		}
		if len(parts) == 0 {
			return "", false
		}
		return strings.Join(parts, "\n\n"), true
	}
	if fi, err := os.Stat(path); err == nil && !fi.IsDir() {
		if b, err := os.ReadFile(path); err == nil {
			return string(b), true
		}
	}
	return "", false
}

// renderCycleDetail: 참조 구현 _render_cycle_detail — L3: 한 사이클의 5스텝 + cycle.yaml 메타를 중첩 <details>로.
func renderCycleDetail(name, cid string, c *webCycle, chainsRoot, cdir string) string {
	vtip := ""
	if c.verdict != nil {
		vtip = " · " + *c.verdict
	}
	status := c.statusText()
	title := c.title
	// 가로 사이클 그래프(loom/C067)의 노드를 누르면 :target으로 드러나는 그 사이클의 5스텝 문서.
	state := status + vtip + stepBadge(c)
	lin := ""
	if len(c.lineage) > 0 {
		var chips strings.Builder
		for _, ref := range c.lineage {
			chips.WriteString(fmt.Sprintf(`<a class="linchip" href="#cycdoc-%s">⇠ %s</a>`,
				htmlEscape(strings.ReplaceAll(ref, "/", "-")), htmlEscape(ref)))
		}
		lin = `<span class="cyclin">` + chips.String() + `</span>`
	}
	supHTML := ""
	if c.supersededBy != nil {
		supHTML = fmt.Sprintf(`<a class="linchip sup" href="#cycdoc-%s">↣ %s</a>`,
			htmlEscape(strings.ReplaceAll(supersedeRef(name, c.supersededBy), "/", "-")),
			htmlEscape(*c.supersededBy))
	}
	titleHTML := ""
	if title != "" {
		titleHTML = `<span class="cytitle">` + htmlEscape(title) + `</span>`
	}

	orDash := func(p *string) string {
		if p == nil {
			return "—"
		}
		return *p
	}
	parent := strings.Join(c.parents, ", ")
	if parent == "" {
		parent = "(root)"
	}
	lineage := strings.Join(c.lineage, ", ")
	if lineage == "" {
		lineage = "—"
	}
	closed := "진행 중"
	if c.closed != nil && *c.closed != "" {
		closed = *c.closed
	}
	type kv struct{ k, v string }
	fields := []kv{
		{"status", status}, {"verdict", orDash(c.verdict)},
		{"step", orDash(c.step)},
		{"parent", parent}, {"lineage", lineage},
		{"opened", orDash(c.opened)}, {"closed", closed},
		{"deviations", orDash(c.deviations)}, {"corrections", orDash(c.corrections)},
		{"superseded_by", orDash(c.supersededBy)},
	}
	if c.rounds != nil { // 참조: if meta.get("rounds")
		fields = append(fields, kv{"rounds", strconv.Itoa(*c.rounds)})
	}
	var metaRows strings.Builder
	for _, f := range fields {
		metaRows.WriteString(fmt.Sprintf("<tr><th>%s</th><td>%s</td></tr>",
			htmlEscape(f.k), htmlEscape(f.v)))
	}
	var steps strings.Builder
	for _, sf := range stepFiles {
		label, fname := sf[0], sf[1]
		content, ok := readStep(chainsRoot, name, cdir, fname)
		pre := `<pre class="empty">(없음)</pre>`
		if ok {
			pre = "<pre>" + htmlEscape(content) + "</pre>"
		}
		steps.WriteString(fmt.Sprintf(`<details class="hstep"><summary>%s</summary>%s</details>`,
			htmlEscape(label), pre))
	}
	anchor := htmlEscape(name + "-" + cid)
	head := fmt.Sprintf(`<div class="cycdoc-head"><span class="ccid">%s</span>`+
		`<span class="cyst">%s</span>%s%s%s</div>`,
		htmlEscape(cid), htmlEscape(state), titleHTML, lin, supHTML)
	return fmt.Sprintf(`<div class="cycdoc" id="cycdoc-%s">%s`+
		`<table class="hmeta"><tbody>%s</tbody></table>%s</div>`,
		anchor, head, metaRows.String(), steps.String())
}

// renderCycleGraphH: 참조 구현 _render_cycle_graph_h (loom/C067) — 가로 사이클 노드-엣지 그래프.
// x=깊이, y=레인. 정수 좌표만 써 참조와 바이트 동일. 노드 클릭 → #cycdoc-*(:target).
func renderCycleGraphH(name string, ch *webChain) string {
	order := ch.order
	if len(order) == 0 {
		return ""
	}
	pos := layoutColumns(order, ch.children)
	nodeXY := map[string][2]int{}
	maxDepth, maxLane := 0, 0
	for cid, rc := range pos {
		nodeXY[cid] = [2]int{hX0 + rc[0]*hColW, hY0 + rc[1]*hRowH}
		if rc[0] > maxDepth {
			maxDepth = rc[0]
		}
		if rc[1] > maxLane {
			maxLane = rc[1]
		}
	}
	width := hX0 + maxDepth*hColW + 90
	height := hY0 + maxLane*hRowH + 46
	var p strings.Builder
	p.WriteString(fmt.Sprintf(`<svg viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="%s 사이클 그래프">`,
		width, height, width, height, htmlEscape(name)))
	for _, cid := range order {
		xy2 := nodeXY[cid]
		for _, par := range ch.cycles[cid].parents {
			if xy1, ok := nodeXY[par]; ok {
				mx := (xy1[0] + xy2[0]) / 2
				p.WriteString(fmt.Sprintf(`<path d="M%d,%d C%d,%d %d,%d %d,%d" fill="none" stroke="var(--edge)" stroke-width="1.6"/>`,
					xy1[0]+hR, xy1[1], mx, xy1[1], mx, xy2[1], xy2[0]-hR, xy2[1]))
			}
		}
	}
	for _, cid := range order {
		xy := nodeXY[cid]
		x, y := xy[0], xy[1]
		meta := ch.cycles[cid]
		closed := meta.status != nil && *meta.status == "closed"
		fill := "var(--node)"
		if meta.verdict != nil && *meta.verdict == "rejected" {
			fill = "var(--rejected)"
		}
		var shape string
		if closed {
			shape = fmt.Sprintf(`<circle cx="%d" cy="%d" r="%d" fill="%s"/>`, x, y, hR, fill)
		} else {
			shape = fmt.Sprintf(`<circle cx="%d" cy="%d" r="%d" fill="var(--surface)" stroke="var(--node)" stroke-width="2.5"/>`, x, y, hR-1)
		}
		num := cid
		if i := strings.IndexByte(cid, '-'); i >= 0 {
			num = cid[:i]
		}
		vtip := ""
		if meta.verdict != nil {
			vtip = " · " + *meta.verdict
		}
		tip := fmt.Sprintf("%s [%s%s] %s", cid, meta.statusText(), vtip, meta.title)
		if len(meta.lineage) > 0 {
			tip += "  ⇠ " + strings.Join(meta.lineage, ", ")
		}
		linTxt := ""
		if len(meta.lineage) > 0 {
			first := meta.lineage[0]
			if i := strings.IndexByte(first, '/'); i >= 0 {
				first = first[i+1:]
			}
			more := ""
			if len(meta.lineage) > 1 {
				more = fmt.Sprintf(" +%d", len(meta.lineage)-1)
			}
			linTxt = fmt.Sprintf(`<text x="%d" y="%d" text-anchor="middle" font-size="9.5" fill="var(--lineage)">⇠ %s%s</text>`,
				x, y+hR+28, htmlEscape(first), more)
		}
		p.WriteString(fmt.Sprintf(`<a href="#cycdoc-%s" class="gnode"><title>%s</title>%s<text x="%d" y="%d" text-anchor="middle" font-size="10.5" font-weight="600" fill="var(--ink-2)">%s</text>%s</a>`,
			htmlEscape(name+"-"+cid), htmlEscape(tip), shape, x, y+hR+14, htmlEscape(num), linTxt))
	}
	p.WriteString("</svg>")
	return p.String()
}

// renderChainMap: 참조 구현 _render_chain_map (loom/C064) — L0 체인 지도(원=체인, 점선 화살표=체인 간 lineage).
// 삼각함수 없이 sqrt·사칙연산만 써 참조와 바이트 동일(sin/cos/atan2는 IEEE correctly-rounded 미보장, Go와 갈릴 위험).
func renderChainMap(d *webData) string {
	names := d.names
	if len(names) == 0 {
		return ""
	}
	ncyc := func(nm string) int { return len(d.chains[nm].order) }
	openn := func(nm string) int {
		k, ch := 0, d.chains[nm]
		for _, c := range ch.order {
			if cy := ch.cycles[c]; cy.status == nil || *cy.status != "closed" {
				k++
			}
		}
		return k
	}
	hasRejected := func(nm string) bool {
		ch := d.chains[nm]
		for _, c := range ch.order {
			if cy := ch.cycles[c]; cy.verdict != nil && *cy.verdict == "rejected" {
				return true
			}
		}
		return false
	}
	firstDate := func(nm string) string {
		best, ch := "", d.chains[nm]
		for _, c := range ch.order {
			if op := ch.cycles[c].opened; op != nil && *op != "" && (best == "" || *op < best) {
				best = *op
			}
		}
		if best == "" {
			return "9999-99-99"
		}
		return best
	}

	// 엣지 집계: source(교훈 원천) → target(인용 체인), 방향은 기존 사이클 그래프와 동일.
	type ek struct{ src, tgt string }
	edges := map[ek]int{}
	for _, name := range names {
		ch := d.chains[name]
		for _, cid := range ch.order {
			for _, ref := range ch.cycles[cid].lineage {
				other := ref
				if i := strings.IndexByte(ref, '/'); i >= 0 {
					other = ref[:i]
				}
				if _, ok := d.chains[other]; ok && other != name {
					edges[ek{other, name}]++
				}
			}
		}
	}
	nbr := map[string]map[string]bool{}
	for _, nm := range names {
		nbr[nm] = map[string]bool{}
	}
	for e := range edges {
		nbr[e.src][e.tgt] = true
		nbr[e.tgt][e.src] = true
	}

	// base = 연대순(first_date, tiebreak 이름). 허브(최다 연결, 동률이면 사이클 많은 쪽)를 가운데로.
	base := append([]string(nil), names...)
	sort.SliceStable(base, func(i, j int) bool {
		fi, fj := firstDate(base[i]), firstDate(base[j])
		if fi != fj {
			return fi < fj
		}
		return base[i] < base[j]
	})
	var order []string
	if len(base) > 2 && len(edges) > 0 {
		hub := base[0]
		for _, nm := range base {
			dn, dh := len(nbr[nm]), len(nbr[hub])
			if dn > dh || (dn == dh && ncyc(nm) > ncyc(hub)) {
				hub = nm
			}
		}
		var rest []string
		for _, nm := range base {
			if nm != hub {
				rest = append(rest, nm)
			}
		}
		mid := len(rest) / 2
		order = append(order, rest[:mid]...)
		order = append(order, hub)
		order = append(order, rest[mid:]...)
	} else {
		order = base
	}

	radius := func(nm string) float64 { // math.Sqrt는 IEEE 보장(correctly-rounded) → 참조 math.sqrt와 비트 동일
		return math.Max(16.0, math.Min(46.0, 12.0+4.6*math.Sqrt(float64(ncyc(nm)))))
	}
	rad := map[string]float64{}
	rmax := 0.0
	for _, nm := range order {
		rad[nm] = radius(nm)
		if rad[nm] > rmax {
			rmax = rad[nm]
		}
	}
	spacing := 2*rmax + 104
	x0 := 44 + rmax
	cx := map[string]float64{}
	for i, nm := range order {
		cx[nm] = x0 + float64(i)*spacing
	}

	arc := map[ek]float64{}
	maxArc := 0.0
	for e := range edges {
		dist := math.Abs(cx[e.tgt] - cx[e.src])
		extra := 0.0
		if _, ok := edges[ek{e.tgt, e.src}]; ok && cx[e.src] > cx[e.tgt] {
			extra = 26
		}
		arc[e] = 38 + 0.12*dist + extra
		if arc[e] > maxArc {
			maxArc = arc[e]
		}
	}
	ycen := math.Max(maxArc/2+18, rmax+8)
	width := x0 + float64(len(order)-1)*spacing + rmax + 44
	height := ycen + rmax + 46

	var p strings.Builder
	p.WriteString(fmt.Sprintf(`<svg viewBox="0 0 %.0f %.0f" width="%.0f" height="%.0f" `+
		`role="img" aria-label="체인 지도 — 체인 간 lineage 그래프">`+
		`<defs><marker id="chainarrow" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" `+
		`markerHeight="6.5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" `+
		`fill="var(--lineage)"/></marker></defs>`, width, height, width, height))
	// lineage 아치 — sorted(src,tgt) 순회. 끝점을 아치 정점 방향 원 둘레에 놓아(부채꼴) 화살표 겹침을 줄인다.
	ekeys := make([]ek, 0, len(edges))
	for e := range edges {
		ekeys = append(ekeys, e)
	}
	sort.Slice(ekeys, func(i, j int) bool {
		if ekeys[i].src != ekeys[j].src {
			return ekeys[i].src < ekeys[j].src
		}
		return ekeys[i].tgt < ekeys[j].tgt
	})
	for _, e := range ekeys {
		n := edges[e]
		xs, xt := cx[e.src], cx[e.tgt]
		ah := arc[e]
		mx, apex := (xs+xt)/2, ycen-ah
		dx1, dy1 := mx-xs, apex-ycen
		l1 := math.Sqrt(dx1*dx1 + dy1*dy1)
		dx2, dy2 := mx-xt, apex-ycen
		l2 := math.Sqrt(dx2*dx2 + dy2*dy2)
		x1, y1 := xs+rad[e.src]*dx1/l1, ycen+rad[e.src]*dy1/l1
		x2, y2 := xt+rad[e.tgt]*dx2/l2, ycen+rad[e.tgt]*dy2/l2
		nn := n
		if nn > 5 {
			nn = 5
		}
		w := 1.2 + 0.55*float64(nn)
		p.WriteString(fmt.Sprintf(`<path d="M%.1f,%.1f Q%.1f,%.1f %.1f,%.1f" `+
			`fill="none" stroke="var(--lineage)" stroke-width="%.1f" stroke-dasharray="5 4" `+
			`marker-end="url(#chainarrow)" opacity="0.8"/>`, x1, y1, mx, apex, x2, y2, w))
		if n > 1 {
			vy := ycen - ah/2
			p.WriteString(fmt.Sprintf(`<text x="%.1f" y="%.1f" text-anchor="middle" font-size="10" `+
				`font-weight="700" fill="var(--lineage)" stroke="var(--surface)" `+
				`stroke-width="3" paint-order="stroke">%d</text>`, mx, vy-3, n))
		}
	}
	// 체인 노드 — 큰 원(안에 사이클 수), 아래 이름+요약. 색=상태(rejected→빨강, 열림→점선 링).
	for _, nm := range order {
		x, r := cx[nm], rad[nm]
		ch := d.chains[nm]
		nc, no := ncyc(nm), openn(nm)
		col := "var(--node)"
		if hasRejected(nm) {
			col = "var(--rejected)"
		}
		tip := htmlEscape(fmt.Sprintf("%s — 사이클 %d개 · %s · %s", nm, nc, verdictTally(ch), chainRecent(ch)))
		numFs := math.Max(12, math.Min(22, r*0.82))
		ring := ""
		if no > 0 {
			ring = fmt.Sprintf(`<circle cx="%.0f" cy="%.0f" r="%.0f" fill="none" stroke="%s" `+
				`stroke-width="1.2" stroke-dasharray="3 3" opacity="0.55"/>`, x, ycen, r+4, col)
		}
		openTxt := ""
		if no > 0 {
			openTxt = fmt.Sprintf(" · 열림 %d", no)
		}
		p.WriteString(fmt.Sprintf(`<a href="#chainbody-%s" class="chainnode" aria-label="%s">`+
			`<title>%s</title>%s`+
			`<circle cx="%.0f" cy="%.0f" r="%.0f" fill="var(--surface)" `+
			`stroke="%s" stroke-width="2.5"/>`+
			`<text x="%.0f" y="%.0f" text-anchor="middle" `+
			`font-size="%.0f" font-weight="700" fill="%s">%d</text>`+
			`<text x="%.0f" y="%.0f" text-anchor="middle" font-size="13" `+
			`font-weight="650" fill="var(--ink)">%s</text>`+
			`<text x="%.0f" y="%.0f" text-anchor="middle" font-size="10.5" `+
			`fill="var(--muted)">사이클 %d%s</text>`+
			`</a>`,
			htmlEscape(nm), tip, tip, ring,
			x, ycen, r, col,
			x, ycen+numFs*0.34, numFs, col, nc,
			x, ycen+r+17, htmlEscape(nm),
			x, ycen+r+32, nc, openTxt))
	}
	p.WriteString("</svg>")
	return p.String()
}

// renderHierarchyBody: 참조 구현 _render_hierarchy_body — L0 체인 지도 → L1 목차 → 체인 <details>(그래프+표) → 사이클 <details>(5스텝).
func renderHierarchyBody(d *webData, pageTitle, generated string, nCycles, nLineage int, chainsRoot, gilDataJSON string) string {
	style := webCSS + "\n" + webHierCSS
	var toc, chainsHTML strings.Builder
	for _, name := range d.names {
		ch := d.chains[name]
		n := len(ch.order)
		tally := verdictTally(ch)
		toc.WriteString(fmt.Sprintf(`<li><a href="#chain-%s">%s</a>`+
			`<span class="toc-stat">사이클 %d개 · %s</span></li>`,
			htmlEscape(name), htmlEscape(name), n, htmlEscape(tally)))
		stats := fmt.Sprintf("사이클 %d개 · %s · %s", n, tally, chainRecent(ch))
		var cyc strings.Builder
		for _, cid := range ch.order {
			cdir := ch.dirs[cid]
			if cdir == "" {
				cdir = cid
			}
			cyc.WriteString(renderCycleDetail(name, cid, ch.cycles[cid], chainsRoot, cdir))
		}
		// 체인을 누르면 그 자리에서 가로 사이클 노드-엣지 그래프가 펼쳐진다 (loom/C067): SVG 그래프(0—o—o—o)
		// + 그 아래 숨은 문서들. 노드를 누르면 :target으로 그 사이클 문서가 뜬다. name="hchain" 아코디언.
		chainsHTML.WriteString(fmt.Sprintf(`<details class="hchain" name="hchain" id="chain-%s">`+
			`<summary><span class="hname">%s</span>`+
			`<span class="hstat">%s</span></summary>`+
			`<div class="hbody"><span id="chainbody-%s" class="hanchor"></span>`+
			`<div class="cyclegraph">%s</div>`+
			`<div class="cycdocs">%s</div></div></details>`,
			htmlEscape(name), htmlEscape(name), htmlEscape(stats),
			htmlEscape(name), renderCycleGraphH(name, ch), cyc.String()))
	}
	return fmt.Sprintf(`<div class="gil"><style>%s</style><div class="wrap">
<header><h1>%s</h1>
<p>체인 %d개 · 사이클 %d개 · 체인 간 lineage %d건 · 생성 %s</p>
<p class="hhint">체인 지도의 원(=체인, 크기 ∝ 사이클 수)을 누르면 그 자리 카드 안에서 사이클 노드가 아래로 주르륵 펼쳐진다. 점선 화살표는 체인 간 lineage(교훈의 흐름). 노드를 누르면 5스텝 문서가 그 자리에 열린다 (JS 없이 &lt;details&gt;로).</p></header>
<div class="card hmap">%s
<div class="mapchains">%s</div></div>
<nav class="htoc"><h2>체인 목록</h2><ul>%s</ul></nav>
<footer>Ariadne — 사이클은 행동 체인의 기록이다. 이 문서는 gil web이 생성한 자기완결적 정적 페이지다.</footer>
</div></div>
<script type="application/json" id="gil-data">%s</script>`,
		style, htmlEscape(pageTitle), len(d.names), nCycles, nLineage, htmlEscape(generated),
		renderChainMap(d), chainsHTML.String(), toc.String(), gilDataJSON)
}

// renderWebPage: 참조 구현 render_web_page — 자기완결적 정적 페이지 (외부 리소스 0).
func renderWebPage(d *webData, pageTitle, generated, only string, refresh int, hierarchy bool, chainsRoot string) string {
	nCycles, nLineage := 0, 0
	for _, name := range d.names {
		ch := d.chains[name]
		nCycles += len(ch.order)
		for _, cid := range ch.cycleOrder {
			nLineage += len(ch.cycles[cid].lineage)
		}
	}
	gilData := webJSONPayload(d, pageTitle, only, refresh, hierarchy)
	var body string
	if hierarchy {
		// v2.16 (loomlight/C003): 위계(드릴다운) 몸체 — 기본 경로를 건드리지 않도록 완전히 분기한다
		// (아래 else는 개선 전과 바이트 동일).
		body = renderHierarchyBody(d, pageTitle, generated, nCycles, nLineage, chainsRoot, gilData)
	} else {
		body = fmt.Sprintf(`<div class="gil"><style>%s</style><div class="wrap">
<header><h1>%s</h1>
<p>체인 %d개 · 사이클 %d개 · 체인 간 lineage %d건 · 생성 %s</p></header>
<div class="legend"><span><svg width="16" height="16"><circle cx="8" cy="8" r="6.5" fill="var(--node)"/></svg>닫힌 사이클</span>
<span><svg width="16" height="16"><circle cx="8" cy="8" r="5.5" fill="var(--surface)" stroke="var(--node)" stroke-width="2"/></svg>열린 사이클</span>
<span><svg width="26" height="16"><path d="M2,8 H24" stroke="var(--edge)" stroke-width="1.6"/></svg>parent (체인 내 계보)</span>
<span><svg width="26" height="16"><path d="M2,8 H24" stroke="var(--lineage)" stroke-width="1.6" stroke-dasharray="5 4"/></svg>lineage (체인 간 교훈)</span>
<span><svg width="26" height="16"><path d="M2,8 H24" stroke="var(--supersede)" stroke-width="1.6" stroke-dasharray="2 3"/></svg>superseded_by (무효화 — 흐린 노드가 대체 사이클을 가리킨다)</span></div>
<div class="card">%s</div>
%s
<footer>Ariadne — 사이클은 행동 체인의 기록이다. 이 문서는 gil web --flat이 생성한 자기완결적 정적 페이지다.</footer>
</div></div>
<script type="application/json" id="gil-data">%s</script>`,
			webCSS, htmlEscape(pageTitle), len(d.names), nCycles, nLineage, htmlEscape(generated),
			renderSVG(d), renderTables(d), gilData)
	}
	// v0.5 (loom/C049): meta refresh — JS 아닌 HTML 표준으로 N초마다 리로드 (자기완결 계약 유지)
	refreshMeta := ""
	if refresh > 0 {
		refreshMeta = fmt.Sprintf("<meta http-equiv=\"refresh\" content=\"%d\">\n", refresh)
	}
	return "<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n" +
		"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n" +
		refreshMeta +
		"<title>" + htmlEscape(pageTitle) + "</title>\n</head>\n<body>\n" + body + "\n</body>\n</html>\n"
}

type webArgs struct {
	root, output, title, chain string
	refresh, interval          int
	watch                      bool
	hierarchy                  bool // v2.16 (loomlight/C003): 위계(드릴다운) 뷰어
}

const pagesWorkflow = `# gil-pages — push마다 사이클 체인 뷰어를 GitHub Pages로 배포한다.
# gil pages가 생성. 저장소에 특정되지 않는다 — 어떤 Ariadne 저장소든 그대로 쓴다.
name: gil-pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build viewer with gil
        run: |
          curl -fsSL -o /tmp/gil-linux-amd64 https://github.com/hyun06000/Ariadne/releases/latest/download/gil-linux-amd64
          curl -fsSL -o /tmp/SHA256SUMS https://github.com/hyun06000/Ariadne/releases/latest/download/SHA256SUMS
          # 선언된 해시와 실물을 대조한다. 불일치면 여기서 실패하고 배포가 멈춘다.
          ( cd /tmp && grep ' gil-linux-amd64$' SHA256SUMS | sha256sum -c - )
          mv /tmp/gil-linux-amd64 /tmp/gil && chmod +x /tmp/gil
          mkdir -p _site
          /tmp/gil web -o _site/index.html --title "gil — cycle chains"
      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
`

func cmdPages(root string, force, dryRun bool) error {
	repoRoot := filepath.Clean(filepath.Join(root, "..", "..", ".."))
	wfDir := filepath.Join(repoRoot, ".github", "workflows")
	wfPath := filepath.Join(wfDir, "gil-pages.yml")
	if dryRun {
		// §7.2-6: 능력 탐침은 저장소를 변경하지 않는다. 무엇이 생길지만 말한다.
		rel, _ := filepath.Rel(repoRoot, wfPath)
		suffix := ""
		if _, err := os.Stat(wfPath); err == nil {
			suffix = " (이미 존재 — 덮으려면 --force)"
		}
		fmt.Printf("생성될 경로: %s%s\n", rel, suffix)
		fmt.Println("dry-run: 아무것도 만들지 않았다")
		return nil
	}
	if _, err := os.Stat(wfPath); err == nil && !force {
		return cerr("이미 존재한다: %s (덮으려면 --force)", wfPath)
	}
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		return cerr("%v", err)
	}
	if err := os.WriteFile(wfPath, []byte(pagesWorkflow), 0o644); err != nil {
		return cerr("%v", err)
	}
	rel, _ := filepath.Rel(repoRoot, wfPath)
	fmt.Printf("생성: %s\n", rel)
	fmt.Println("다음: git push 후 저장소 Settings → Pages → Source = 'GitHub Actions'")
	return nil
}

const webDefaultTitle = "Ariadne — 사이클 체인" // 뷰어 기본 제목 (단일 소스)

// bakeViewer: 뷰어 하나를 굽는다 (cmdWeb과 자동 갱신의 단일 소스).
func bakeViewer(chainsRoot, output, title, only string, refresh int, hierarchy bool) (int, error) {
	data, err := buildWebData(chainsRoot, only)
	if err != nil {
		return 0, err
	}
	if len(data.names) == 0 {
		return 0, cerr("렌더할 체인이 없다: %s", chainsRoot)
	}
	page := renderWebPage(data, title, time.Now().Format("2006-01-02"), only, refresh, hierarchy, chainsRoot)
	if err := os.WriteFile(output, []byte(page), 0o644); err != nil {
		return 0, cerr("%v", err)
	}
	return len(data.names), nil
}

func cmdWeb(a webArgs) error {
	if fi, err := os.Stat(a.root); err != nil || !fi.IsDir() {
		return cerr("체인 루트가 없다: %s", a.root)
	}
	if a.watch {
		return webWatch(a)
	}
	n, err := bakeViewer(a.root, a.output, a.title, a.chain, a.refresh, a.hierarchy)
	if err != nil {
		return err
	}
	suffix := ""
	if !a.hierarchy {
		suffix += " · 평면"
	}
	if a.refresh > 0 {
		suffix += fmt.Sprintf(" · 자동 리로드 %d초", a.refresh)
	}
	fmt.Printf("생성: %s (체인 %d개)%s\n", a.output, n, suffix)
	return nil
}

// webWatch: --watch — 원장 변경을 감시해 뷰어를 재생성한다 (loom/C049).
// gil step을 거치지 않는 외부 변경(병합·pull)도 반영한다. Ctrl-C까지 지속.
func webWatch(a webArgs) error {
	interval := a.interval
	if interval <= 0 {
		interval = 5
	}
	refresh := a.refresh
	if refresh <= 0 {
		refresh = interval // --watch는 자동 리로드를 함축한다
	}
	snapshot := func() map[string]int64 {
		out := map[string]int64{}
		filepath.Walk(a.root, func(p string, fi os.FileInfo, err error) error {
			if err != nil || fi.IsDir() {
				return nil
			}
			n := fi.Name()
			if n == "cycle.yaml" || n == "round.yaml" || strings.HasSuffix(n, ".tsv") {
				out[p] = fi.ModTime().UnixNano()
			}
			return nil
		})
		return out
	}
	n, err := bakeViewer(a.root, a.output, a.title, a.chain, refresh, a.hierarchy)
	if err != nil {
		return err
	}
	fmt.Printf("감시 시작: %s (체인 %d개, %d초 간격, 자동 리로드 %d초). Ctrl-C로 종료.\n", a.output, n, interval, refresh)
	last := snapshot()
	eq := func(x, y map[string]int64) bool {
		if len(x) != len(y) {
			return false
		}
		for k, v := range x {
			if y[k] != v {
				return false
			}
		}
		return true
	}
	for {
		time.Sleep(time.Duration(interval) * time.Second)
		cur := snapshot()
		if !eq(cur, last) {
			last = cur
			if m, err := bakeViewer(a.root, a.output, a.title, a.chain, refresh, a.hierarchy); err != nil {
				fmt.Fprintf(os.Stderr, "경고: 재생성 실패 — %v\n", err)
			} else {
				fmt.Printf("  ✎ 재생성: %s (체인 %d개)\n", a.output, m)
			}
		}
	}
}

// ---------- 뷰어 자동 갱신 (v2.2 / loom/C042 — 이슈 #16) ----------
//
// 원장이 자동으로 갱신되면 사람의 창도 자동으로 갱신되어야 한다.
// 둘 중 하나만 자동인 상태가 가장 나쁘다 — 낡은 화면은 침묵보다 나쁘다 (maru).

const gilDataHook = `id="gil-data"` // §7: 뷰어는 자기가 뷰어임을 스스로 말한다

// findViewers: 탐색 루트의 비재귀 *.html 중 gil-data 훅을 가진 것.
// 파일명 목록을 만들지 않는다 — 위임하는 목록은 낡지 않는다 (C039).
func findViewers(root string) [][2]string {
	var found [][2]string
	entries, err := os.ReadDir(root)
	if err != nil {
		return found
	}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".html") {
			continue
		}
		path := filepath.Join(root, e.Name())
		b, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		if strings.Contains(string(b), gilDataHook) {
			found = append(found, [2]string{path, string(b)})
		}
	}
	return found
}

// bakeMeta: 뷰어가 스스로 보고한 굽기 조건. 없으면(구버전) 기본값 — 추측하지 않는다.
// refresh(loom/C049)도 함께 읽어 자동 재굽기가 자동 리로드를 보존하게 한다.
func bakeMeta(text string) (title, only string, refresh int, hierarchy bool) {
	title = webDefaultTitle
	m := regexp.MustCompile(`(?s)id="gil-data">(.*?)</script>`).FindStringSubmatch(text)
	if m == nil {
		return
	}
	var payload struct {
		Bake struct {
			Title     string  `json:"title"`
			Chain     *string `json:"chain"`
			Refresh   int     `json:"refresh"`
			Hierarchy bool    `json:"hierarchy"` // loomlight/C003: 자동 재굽기가 위계 드릴다운을 잃지 않게 한다
		} `json:"bake"`
	}
	if json.Unmarshal([]byte(m[1]), &payload) != nil {
		return
	}
	if payload.Bake.Title != "" {
		title = payload.Bake.Title
	}
	if payload.Bake.Chain != nil {
		only = *payload.Bake.Chain
	}
	refresh = payload.Bake.Refresh
	hierarchy = payload.Bake.Hierarchy
	return
}

// refreshViewers: 원장을 바꾼 명령이 커밋한 뒤 호출한다. 뷰어가 없으면 아무것도 하지 않는다.
// 실패는 경고일 뿐 명령의 실패가 아니다 — 원장의 각인은 이미 끝났다 (꼬리가 개를 흔들지 않는다).
func refreshViewers(chainsRoot, label string, noWeb, push bool) {
	if noWeb {
		return
	}
	repo := repoRoot(chainsRoot)
	root := repo
	if root == "" {
		// git 부재 시 뷰어 검색을 임의의 cwd가 아니라 저장소 루트에 고정한다
		// (안 그러면 cwd의 무관한 HTML을 주워 "렌더할 체인이 없다" 헛경고, loom/C052).
		root = filepath.Clean(filepath.Join(chainsRoot, "..", "..", ".."))
	}
	viewers := findViewers(root)
	if len(viewers) == 0 {
		return // 뷰어를 쓰지 않는 사용자에게 파일을 강요하지 않는다
	}
	var changed []string
	for _, v := range viewers {
		path, before := v[0], v[1]
		title, only, refresh, hierarchy := bakeMeta(before) // refresh·hierarchy 보존 (C049·C003)
		if _, err := bakeViewer(chainsRoot, path, title, only, refresh, hierarchy); err != nil {
			fmt.Fprintf(os.Stderr, "경고: 뷰어 갱신 실패 — %v (원장은 각인됐다. gil web으로 직접 구울 것)\n", err)
			return
		}
		after, _ := os.ReadFile(path)
		if string(after) != before {
			changed = append(changed, path)
		}
	}
	if len(changed) == 0 {
		return
	}
	names := make([]string, len(changed))
	for i, p := range changed {
		names[i] = filepath.Base(p)
	}
	fmt.Printf("  ✎ 뷰어 갱신: %s\n", strings.Join(names, ", "))
	if repo == "" {
		return // 깃이 없어도 창은 갱신된다. 커밋만 없을 뿐이다.
	}
	rels := make([]string, len(changed))
	for i, p := range changed {
		r, err := relToRepo(repo, p)
		if err != nil {
			return
		}
		rels[i] = r
	}
	// 뷰어는 사이클이 아니다 — 사이클 커밋에 섞으면 태그가 사이클 밖의 것을 봉인한다 (§4)
	if _, err := gitChecked(repo, append([]string{"add", "--"}, rels...)...); err != nil {
		fmt.Fprintf(os.Stderr, "경고: 뷰어 커밋 실패 — %v\n", err)
		return
	}
	if _, err := gitChecked(repo, append([]string{"commit", "-m", "gil: web 갱신 — " + label, "--"}, rels...)...); err != nil {
		fmt.Fprintf(os.Stderr, "경고: 뷰어 커밋 실패 — %v\n", err)
		return
	}
	if push {
		gitPush(repo) // 원격 부재 우아화 (loom/C054)
	}
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

const gilVersion = "2.23.0" // gil:version

// commandTable — SPEC §7.2-2의 단일 소스.
// help 목록·기계 훅(gil:commands)·미구현 메시지·능력 탐침(help <명령>)이 전부 이 테이블 하나에서 파생된다.
// 목록을 두 번 적지 않는다: 여기에 없는 것은 이 바이너리에 없다.
var commandTable = []struct{ name, usage, desc string }{
	{"log", "gil log [chains-root] [--chain <이름>]", "체인 계보를 ASCII 그래프로"},
	{"fsck", "gil fsck [chains-root] [--chain <이름>]", "R1~R14 위반 전수 수집·보고"},
	{"open", "gil open <chain> <slug> --author <이름> [--parent …]… [--new-root] [--title …] [--lineage …] [--new-chain] [--git] [--push]", "사이클 생성 (번호 자동 증가). --author 필수, 비어있지 않은 체인은 --parent 또는 --new-root 필수 (§3.2)"},
	{"worktree", "gil worktree add|land <chain> <slug> --author <이름> [--push] [--root …]", "병렬 사이클 모드: add=격리 워크트리+사이클 열기, land=브랜치를 main에 --no-ff 병합 후 정리 (v2.15·v2.17, #1)"},
	{"reserve", "gil reserve <chain> <slug> --for <이름> [--date …] [--git] [--push] [--root …]", "병렬 존재에게 사이클 번호를 예약 (원장 선점, v2.3). --for 필수 (§3.2 P1)"},
	{"unreserve", "gil unreserve <chain> <번호> [--git] [--push] [--root …]", "예약 취소 — 만료의 수동 해법 (v2.3). 없는 번호는 거부"},
	{"close", "gil close <chain> <id> [--verdict …] [--no-commit] [--push]", "보고서 검증 후 사이클 닫기 (커밋+태그)"},
	{"step", "gil step <chain> <id> <n> [--no-commit] [--push]", "열린 사이클의 스텝 전이 (1~5)"},
	{"round", "gil round <chain> <id> --open --title <t> | --close --verdict <v> | --list [--git] [--push]", "사이클 안 (가설→검증) 라운드 사전등록·마감 (v2.5, 이슈 #9·#10)"},
	{"verify", "gil verify [chains-root] [--chain <이름>]", "닫힌 사이클의 태그↔작업 트리 대조"},
	{"web", "gil web [chains-root] -o <출력> [--title …] [--chain …]", "자기완결적 정적 HTML 뷰어"},
	{"pages", "gil pages [--force] [--dry-run]", "GitHub Pages 배포 워크플로 생성"},
	{"goto", "gil goto <chain>/<id> [--checkout]", "타임머신: 사이클 시점 역행 조회·체크아웃"},
	{"handoff", "gil handoff [chains-root]", "세션의 매듭: 현황·부활 경로·다음 실"},
	{"supersede", "gil supersede <old-ref> <new-ref>", "전방 무효화: 닫힌 사이클에 superseded_by 각인"},
	{"correct", "gil correct <chain>/<id> --field <author|parent|lineage> --to <값> --evidence <파일>[:<줄>] --author <이름> [--reason …] [--push]", "정정: 봉인된 사이클의 출처 필드를 문서가 증언하는 값으로 수리 (§4.1)"},
	{"version", "gil version", "이 바이너리의 버전"},
	{"help", "gil help [<명령>]", "구현 명령 목록 — 부작용 없는 능력 탐침"},
}

const referenceOnly = "release" // 참조 구현(gil.py) 전용 (loom/C036: open --git/--push는 이식 완료)

// commandNames — 테이블에서 파생. 어떤 목록도 손으로 유지하지 않는다.
func commandNames() []string {
	names := make([]string, 0, len(commandTable))
	for _, c := range commandTable {
		names = append(names, c.name)
	}
	return names
}

func lookupCommand(name string) (string, bool) {
	for _, c := range commandTable {
		if c.name == name {
			return c.usage, true
		}
	}
	return "", false
}

func printHelp() {
	fmt.Printf("gil %s — 길, GIt for Language model\n\n", gilVersion)
	fmt.Println("구현 명령 (자세히: gil help <명령>):")
	for _, c := range commandTable {
		fmt.Printf("  %-10s %s\n", c.name, c.desc)
	}
	fmt.Printf("\n참조 구현(python3 gil.py) 전용: %s\n", referenceOnly)
	fmt.Println("열기/스텝/닫기는 깃 저장소에서 커밋한다 (open은 --git, 스텝·닫기는 기본 — --no-commit로 opt-out).")
	fmt.Println("open --git --push는 번호 원장 규율을 따른다 (경합 시 fetch·rebase·자동 재번호·재시도).")
	// §7.2-1: 사람의 출력 안에 심은 기계 훅. 훅과 위 목록은 같은 테이블에서 나온다.
	fmt.Printf("\ngil:commands %s\n", strings.Join(commandNames(), " "))
}

// helpFor — §7.2-3: 부작용 없는 능력 탐침. 구현했으면 사용법 + exit 0, 아니면 미구현(exit 3).
func helpFor(name string) {
	usage, ok := lookupCommand(name)
	if !ok {
		notImplemented(name) // exit 3 — 없는 것을 "있다"고 답하지 않는다
	}
	fmt.Printf("사용법: %s\n", usage)
	os.Exit(0)
}

func notImplemented(what string) {
	fmt.Fprintf(os.Stderr, "미구현: '%s' — 이 바이너리(gil %s) 구현: %s. 참조 전용: %s. (gil help 참조)\n",
		what, gilVersion, strings.Join(commandNames(), "·"), referenceOnly)
	os.Exit(3)
}

func main() {
	if len(os.Args) < 2 {
		printHelp()
		os.Exit(0)
	}
	today := time.Now().Format("2006-01-02")
	defaultRoot := "rooms/experiment/chains"
	switch os.Args[1] {
	case "version", "--version", "-v":
		fmt.Printf("gil %s\n", gilVersion)
	case "help", "--help", "-h":
		// §7.2-3: 인자가 있으면 그 명령의 능력 탐침 (없는 명령이면 exit 3 — 거짓말하지 않는다)
		if len(os.Args) >= 3 && !strings.HasPrefix(os.Args[2], "-") {
			helpFor(os.Args[2])
		}
		printHelp()
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
			"date": true, "root": true, "new-chain": false, "new-root": false,
			"git": false, "push": false, "no-web": false,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) != 2 {
			fmt.Fprintln(os.Stderr, "사용: gil open <chain> <slug> --author <이름> [--parent id]… [--new-root] [--title t] [--lineage chain/id]… [--date d] [--new-chain] [--git] [--push] [--root r]")
			os.Exit(2)
		}
		if err := cmdOpen(openArgs{
			chain: pos[0], slug: pos[1],
			title:    flagVal(flags, "title", ""),
			author:   flagVal(flags, "author", ""), // §3.2 P1: 기본값 없다 — 도구는 저자를 지어내지 않는다
			date:     flagVal(flags, "date", today),
			root:     flagVal(flags, "root", defaultRoot),
			parents:  flags["parent"],
			lineage:  flags["lineage"],
			newChain: len(flags["new-chain"]) > 0,
			newRoot:  len(flags["new-root"]) > 0,
			git:      len(flags["git"]) > 0,
			push:     len(flags["push"]) > 0,
			noWeb:    len(flags["no-web"]) > 0,
		}); err != nil {
			fail(err)
		}
	case "worktree":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{
			"author": true, "parent": true, "lineage": true, "date": true, "root": true,
			"new-chain": false, "new-root": false, "push": false,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) != 3 || (pos[0] != "add" && pos[0] != "land") {
			fmt.Fprintln(os.Stderr, "사용: gil worktree add <chain> <slug> --author <이름> [--parent id]… [--lineage chain/id]… [--new-chain] [--new-root] [--root r]")
			fmt.Fprintln(os.Stderr, "      gil worktree land <chain> <slug> --author <이름> [--push] [--root r]")
			os.Exit(2)
		}
		if err := cmdWorktree(worktreeArgs{
			action: pos[0], chain: pos[1], slug: pos[2],
			author:   flagVal(flags, "author", ""),
			date:     flagVal(flags, "date", today),
			root:     flagVal(flags, "root", defaultRoot),
			parents:  flags["parent"],
			lineage:  flags["lineage"],
			newChain: len(flags["new-chain"]) > 0,
			newRoot:  len(flags["new-root"]) > 0,
			push:     len(flags["push"]) > 0,
		}); err != nil {
			fail(err)
		}
	case "reserve":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{
			"for": true, "date": true, "root": true,
			"git": false, "push": false, "no-web": false,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) != 2 {
			fmt.Fprintln(os.Stderr, "사용: gil reserve <chain> <slug> --for <이름> [--date d] [--git] [--push] [--root r]")
			os.Exit(2)
		}
		if err := cmdReserve(reserveArgs{
			chain: pos[0], slug: pos[1],
			author: flagVal(flags, "for", ""), // §3.2 P1: 기본값 없다 — 예약 주인을 지어내지 않는다
			date:   flagVal(flags, "date", today),
			root:   flagVal(flags, "root", defaultRoot),
			git:    len(flags["git"]) > 0,
			push:   len(flags["push"]) > 0,
		}); err != nil {
			fail(err)
		}
	case "unreserve":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{
			"root": true, "git": false, "push": false, "no-web": false,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) != 2 {
			fmt.Fprintln(os.Stderr, "사용: gil unreserve <chain> <번호> [--git] [--push] [--root r]")
			os.Exit(2)
		}
		if err := cmdUnreserve(unreserveArgs{
			chain: pos[0], number: pos[1],
			root: flagVal(flags, "root", defaultRoot),
			git:  len(flags["git"]) > 0,
			push: len(flags["push"]) > 0,
		}); err != nil {
			fail(err)
		}
	case "close":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{
			"date": true, "root": true, "verdict": true, "git": false, "push": false, "no-commit": false, "no-web": false,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) != 2 {
			fmt.Fprintln(os.Stderr, "사용: gil close <chain> <cycle-id> [--date d] [--verdict v] [--root r] [--git] [--push]")
			os.Exit(2)
		}
		if err := cmdClose(closeArgs{
			chain: pos[0], cycleID: pos[1],
			date:     flagVal(flags, "date", today),
			root:     flagVal(flags, "root", defaultRoot),
			verdict:  flagVal(flags, "verdict", ""),
			git:      len(flags["git"]) > 0,
			push:     len(flags["push"]) > 0,
			noCommit: len(flags["no-commit"]) > 0,
			noWeb:    len(flags["no-web"]) > 0,
		}); err != nil {
			fail(err)
		}
	case "step":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{
			"root": true, "git": false, "push": false, "no-commit": false, "no-web": false,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) != 3 {
			fmt.Fprintln(os.Stderr, "사용: gil step <chain> <cycle-id> <n(1~5)> [--root r] [--git] [--push]")
			os.Exit(2)
		}
		if err := cmdStep(stepArgs{
			chain: pos[0], cycleID: pos[1], n: pos[2],
			root:     flagVal(flags, "root", defaultRoot),
			git:      len(flags["git"]) > 0,
			push:     len(flags["push"]) > 0,
			noCommit: len(flags["no-commit"]) > 0,
			noWeb:    len(flags["no-web"]) > 0,
		}); err != nil {
			fail(err)
		}
	case "round":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{
			"title": true, "verdict": true, "date": true, "root": true,
			"open": false, "close": false, "list": false,
			"git": false, "push": false, "no-web": false,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) != 2 {
			fmt.Fprintln(os.Stderr, "사용: gil round <chain> <cycle-id> --open --title t | --close --verdict v | --list [--git] [--push] [--root r]")
			os.Exit(2)
		}
		modes := 0
		for _, m := range []string{"open", "close", "list"} {
			if len(flags[m]) > 0 {
				modes++
			}
		}
		if modes != 1 {
			fmt.Fprintln(os.Stderr, "사용: --open · --close · --list 중 정확히 하나를 지정하라")
			os.Exit(2)
		}
		if err := cmdRound(roundArgs{
			chain: pos[0], cycleID: pos[1],
			root:    flagVal(flags, "root", defaultRoot),
			open:    len(flags["open"]) > 0,
			close:   len(flags["close"]) > 0,
			list:    len(flags["list"]) > 0,
			title:   flagVal(flags, "title", ""),
			verdict: flagVal(flags, "verdict", ""),
			date:    flagVal(flags, "date", today),
			git:     len(flags["git"]) > 0,
			push:    len(flags["push"]) > 0,
			noWeb:   len(flags["no-web"]) > 0,
		}); err != nil {
			fail(err)
		}
	case "handoff":
		pos, _, err := parseCLI(os.Args[2:], map[string]bool{})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		root := defaultRoot
		if len(pos) == 1 {
			root = pos[0]
		}
		if err := cmdHandoff(root); err != nil {
			fail(err)
		}
	case "supersede":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{"root": true, "no-commit": false, "no-web": false})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) != 2 {
			fmt.Fprintln(os.Stderr, "사용: gil supersede <chain>/<old-id> <chain>/<new-id> [--root r] [--no-commit]")
			os.Exit(2)
		}
		if err := cmdSupersede(supersedeArgs{
			root:     flagVal(flags, "root", defaultRoot),
			oldRef:   pos[0],
			newRef:   pos[1],
			noCommit: len(flags["no-commit"]) > 0,
			noWeb:    len(flags["no-web"]) > 0,
		}); err != nil {
			fail(err)
		}
	case "correct":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{
			"root": true, "field": true, "to": true, "evidence": true,
			"author": true, "reason": true, "date": true, "push": false, "no-web": false,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) != 1 {
			fmt.Fprintln(os.Stderr, "사용: gil correct <chain>/<id> --field <필드> --to <값> --evidence <파일>[:<줄>] --author <이름> [--reason …] [--push]")
			os.Exit(2)
		}
		if err := cmdCorrect(correctArgs{
			root:     flagVal(flags, "root", defaultRoot),
			ref:      pos[0],
			fields:   flags["field"],
			tos:      flags["to"],
			evidence: flagVal(flags, "evidence", ""),
			author:   flagVal(flags, "author", ""),
			reason:   flagVal(flags, "reason", ""),
			date:     flagVal(flags, "date", today),
			push:     len(flags["push"]) > 0,
			noWeb:    len(flags["no-web"]) > 0,
		}); err != nil {
			fail(err)
		}
	case "verify":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{"chain": true})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) > 1 {
			fmt.Fprintln(os.Stderr, "사용: gil verify [chains-root] [--chain c]")
			os.Exit(2)
		}
		root := defaultRoot
		if len(pos) == 1 {
			root = pos[0]
		}
		code, err := cmdVerify(verifyArgs{root: root, chain: flagVal(flags, "chain", "")})
		if err != nil {
			fail(err)
		}
		os.Exit(code)
	case "web":
		// argparse의 -o/--output 별칭에 대응: -o를 --output으로 정규화한다.
		raw := os.Args[2:]
		norm := make([]string, 0, len(raw))
		for _, a := range raw {
			if a == "-o" {
				norm = append(norm, "--output")
			} else {
				norm = append(norm, a)
			}
		}
		pos, flags, err := parseCLI(norm, map[string]bool{
			"output": true, "title": true, "chain": true,
			"refresh": true, "interval": true, "watch": false, // v2.8 (C049): 실시간 관찰
			"flat":      false, // v2.19 (loom/C063): 위계가 기본 — 평면 옵트아웃
			"hierarchy": false, // v2.19 (loom/C063): 하위호환 no-op 별칭 (조용히 수용)
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) > 1 {
			fmt.Fprintln(os.Stderr, "사용: gil web [chains-root] [-o out.html] [--title t] [--chain c] [--refresh N] [--flat] [--watch]")
			os.Exit(2)
		}
		root := defaultRoot
		if len(pos) == 1 {
			root = pos[0]
		}
		refresh, _ := strconv.Atoi(flagVal(flags, "refresh", "0"))
		interval, _ := strconv.Atoi(flagVal(flags, "interval", "0"))
		if err := cmdWeb(webArgs{
			root:     root,
			output:   flagVal(flags, "output", "ariadne-chains.html"),
			title:    flagVal(flags, "title", "Ariadne — 사이클 체인"),
			chain:    flagVal(flags, "chain", ""),
			refresh:   refresh,
			interval:  interval,
			watch:     len(flags["watch"]) > 0,
			hierarchy: len(flags["flat"]) == 0, // v2.19 (loom/C063): 위계가 기본, --flat만 평면으로 (--flat이 --hierarchy보다 우선)
		}); err != nil {
			fail(err)
		}
	case "goto":
		pos, flags, err := parseCLI(os.Args[2:], map[string]bool{"root": true, "checkout": false})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if len(pos) != 1 {
			fmt.Fprintln(os.Stderr, "사용: gil goto <chain>/<id> [--checkout]")
			os.Exit(2)
		}
		if err := cmdGoto(flagVal(flags, "root", defaultRoot), pos[0], len(flags["checkout"]) > 0); err != nil {
			fail(err)
		}
	case "pages":
		_, flags, err := parseCLI(os.Args[2:], map[string]bool{"root": true, "force": false, "dry-run": false})
		if err != nil {
			fmt.Fprintf(os.Stderr, "오류: %v\n", err)
			os.Exit(2)
		}
		if err := cmdPages(flagVal(flags, "root", defaultRoot), len(flags["force"]) > 0, len(flags["dry-run"]) > 0); err != nil {
			fail(err)
		}
	default:
		notImplemented(os.Args[1])
	}
}
