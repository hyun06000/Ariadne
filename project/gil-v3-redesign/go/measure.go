// measure.go — 측정의 좌표: **어디서 쟀는가(dataset)** 와 **무엇을 쟀는가(subject)**.
//
// 이슈 #79·#81 (실사용, 체인 하나를 태우고 나서). gil 은 "닫힌 사이클 불변 · 사전 판정기준
// 고정 · 정직한 결말"을 보장한다. 그런데 **그 판정이 무엇에 대한 판정인지**는 보장 밖이었다.
// 판정 대상이 불명이면 불변성도 공허하다.
//
// 실제로 이렇게 탔다: "평가셋"이라 불리는 파일이 둘이었고, 어느 측정이 어느 것 위에 섰는지
// 아무 데도 없었다. 한 축에서 발견한 사실을 다른 축으로 옮겼고, 그 잘못된 사실로 사람에게
// 기준 문서를 세우게 했다. 체인 두 사이클이 통째로 무효가 됐다. 같은 저장소에서 행수·빈행·
// gold 합계까지 똑같고 sha 만 다른 평가셋 파일이 8개 나왔다 — 산문으로는 결정되지 않는다.
//
// 그래서 좌표를 **트레일러(필드)로** 받는다. 산문이 아니라 필드라야 기계가 대조한다:
//   Gil-Dataset: gold_eval_md.jsonl@sha256:013f5b73…   (어디서)
//   Gil-Subject: gemma-26b-awq@rev:abc123#adapter=none (무엇을)
package main

import (
	"regexp"
	"sort"
	"strings"
)

// datasetSpecRe — 권장 형식 <이름>@sha256:<hex>. 이름만 적으면 결정되지 않는다는 것이
// 이 이슈의 핵심이라, sha 가 붙었는지를 본다.
var datasetSpecRe = regexp.MustCompile(`@sha256:[0-9a-fA-F]{8,64}$`)

// hasDatasetDigest — 이 선언이 파일을 **결정**하는가(sha 가 붙었는가).
func hasDatasetDigest(spec string) bool { return datasetSpecRe.MatchString(strings.TrimSpace(spec)) }

// chainRequires — 체인 루트에 걸린 요구(Gil-Require-Dataset / Gil-Require-Subject).
// 전면 강제는 과하다 — 측정을 하는 체인만 스스로 합격선을 올린다(이슈 #79 제안 2).
func chainRequires(chain, trailerName string) bool {
	fmtStr := trailer("Gil-Chain") + fsep + trailer(trailerName) + sep
	out := gitlog("--format="+fmtStr, "--branches")
	for _, rec := range strings.Split(out, sep) {
		c, v, _ := cut(rec, fsep)
		if strings.TrimSpace(c) == chain && strings.TrimSpace(v) == "true" {
			return true
		}
	}
	return false
}

// cycleCoord — 한 사이클이 선언한 측정 좌표.
type cycleCoord struct {
	cycle    string
	datasets []string
	subjects []string
}

// coordsOf — 이 체인의 사이클별 좌표(오래된→새 순). 선언이 없는 사이클은 빈 슬라이스로 담긴다.
func coordsOf(chain string) []cycleCoord {
	fmtStr := trailer("Gil-Chain") + fsep + trailer("Gil-Cycle") + fsep +
		trailerMulti("Gil-Dataset") + fsep + trailerMulti("Gil-Subject") + fsep +
		trailer("Gil-Step") + sep
	out := gitlog("--format="+fmtStr, "--branches")
	seen := map[string]bool{}
	var res []cycleCoord
	recs := strings.Split(out, sep)
	for i := len(recs) - 1; i >= 0; i-- { // old→new
		f := strings.Split(strings.Trim(recs[i], "\n"), fsep)
		if len(f) < 5 || strings.TrimSpace(f[0]) != chain {
			continue
		}
		cy := strings.TrimSpace(f[1])
		if cy == "" || strings.TrimSpace(f[4]) != "s1" || seen[cy] {
			continue // 좌표는 사이클을 여는 s1 define 에 산다
		}
		seen[cy] = true
		res = append(res, cycleCoord{cycle: cy, datasets: splitMulti(f[2]), subjects: splitMulti(f[3])})
	}
	return res
}

// coordDriftLines — 같은 체인 안에서 좌표가 바뀌면 그 자리에서 알린다(이슈 #79 제안 4, #81).
//
// c001 은 A 로 재고 c002 는 B 로 쟀는데 둘을 비교하면 사고다 — 보고자가 정확히 그렇게
// 미끄러졌다. 막지는 않는다(축을 바꾸는 건 정당한 작업일 수 있다). 다만 **조용하지 않게**:
// 바뀌었다는 사실과 무엇에서 무엇으로인지를 말한다.
func coordDriftLines(chain string, newDatasets, newSubjects []string) []string {
	prev := coordsOf(chain)
	var lastD, lastS *cycleCoord
	for i := range prev {
		if len(prev[i].datasets) > 0 {
			lastD = &prev[i]
		}
		if len(prev[i].subjects) > 0 {
			lastS = &prev[i]
		}
	}
	var L []string
	cmp := func(old *cycleCoord, oldVals, newVals []string, what, flag string) {
		if old == nil || len(newVals) == 0 || len(oldVals) == 0 {
			return
		}
		a, b := append([]string{}, oldVals...), append([]string{}, newVals...)
		sort.Strings(a)
		sort.Strings(b)
		if strings.Join(a, "|") == strings.Join(b, "|") {
			return
		}
		L = append(L, "  ⚠ 이 체인의 "+what+"이 바뀐다 — 앞 사이클과 같은 축이 아니다:")
		L = append(L, "      "+old.cycle+": "+strings.Join(oldVals, ", "))
		L = append(L, "      "+"(지금)"+": "+strings.Join(newVals, ", "))
		L = append(L, "      두 사이클의 수치를 나란히 비교하지 마라 — 분모가 다르면 판정도 다르다.")
		L = append(L, "      같은 축으로 재려던 것이면 "+flag+" 를 앞 사이클과 맞춰라.")
	}
	if lastD != nil {
		cmp(lastD, lastD.datasets, newDatasets, "평가셋(dataset)", "--dataset")
	}
	if lastS != nil {
		cmp(lastS, lastS.subjects, newSubjects, "측정 대상(subject)", "--subject")
	}
	return L
}

// requireCoords — 체인이 요구하면 선언 없이 사이클을 못 연다(문법의 거부, HEAAL).
//
// 왜 거부인가. 보고자의 체인은 사람이 인터뷰에서 "새 사이클을 열 때 '어느 평가셋인가'를
// 답하지 않으면 진행이 막히면 됐다"를 **합격선으로 세웠다.** 도구가 그걸 표현하지 못하면
// 사람이 세운 기준을 지킬 수단이 없다 — 안내로는 부족하다.
func requireCoords(chain string, datasets, subjects, produces []string) {
	if chainRequires(chain, "Gil-Require-Dataset") && len(datasets) == 0 && len(produces) == 0 {
		die("거부: 체인 \"" + chain + "\" 은 사이클마다 평가셋 선언을 요구한다(--require-dataset 로 열린 체인).\n" +
			"  이 측정이 **어느 셋 위에 서는지** 적어라:\n" +
			"    gil open " + chain + "/<cycle> … --dataset <이름>@sha256:<hex>\n" +
			"  이 사이클이 셋을 **만드는** 설계 사이클이면 산출물로 선언하라(이슈 #119):\n" +
			"    gil open " + chain + "/<cycle> … --produces-dataset <이름>\n" +
			"    (여는 조건은 이름뿐이고, **닫을 때** 실제 sha 를 요구한다 — 없는 좌표를 지어내지 않게)\n" +
			"  이름만으로는 결정되지 않는다 — 같은 행수·같은 합계인데 내용이 다른 파일이 실제로 있었다(#79).")
	}
	if chainRequires(chain, "Gil-Require-Subject") && len(subjects) == 0 {
		die("거부: 체인 \"" + chain + "\" 은 사이클마다 측정 대상 선언을 요구한다(--require-subject 로 열린 체인).\n" +
			"  이 측정이 **무엇을 재는지** 적어라:\n" +
			"    gil open " + chain + "/<cycle> … --subject <이름>@rev:<커밋|체크포인트>#<옵션>\n" +
			"  별칭만으로는 재현되지 않는다 — 서빙 별칭 뒤의 가중치·어댑터·양자화가 기록에 없으면\n" +
			"  그 수치는 '무엇의 점수인지 모르는 점수'가 된다(#81).")
	}
	// 요구가 없어도 형식은 짚는다: sha 없는 dataset 은 결정되지 않는다.
	for _, d := range datasets {
		if !hasDatasetDigest(d) {
			stderr("  ⚠ --dataset \"" + d + "\" 에 sha256 이 없다 — 이름만으로는 파일이 결정되지 않는다.")
			stderr("     권장: <이름>@sha256:<hex>  (실사례: 행수·빈행·gold 합계까지 같고 sha 만 다른 평가셋 8개, #79)")
		}
	}
}

// coordLines — log·handoff·뷰어가 함께 쓰는 표시 줄(이 사이클이 선 좌표).
func coordLines(datasets, subjects []string, indent string) []string {
	var L []string
	for _, d := range datasets {
		L = append(L, indent+"📐 평가셋: "+d)
	}
	for _, s := range subjects {
		L = append(L, indent+"🎯 대상: "+s)
	}
	return L
}

// cycleCoordOf — 한 사이클의 좌표(없으면 빈 슬라이스). log·handoff 표시용.
func cycleCoordOf(chain, cycle string) ([]string, []string) {
	for _, c := range coordsOf(chain) {
		if c.cycle == cycle {
			return c.datasets, c.subjects
		}
	}
	return nil, nil
}

// requireProducedDatasets — 열 때 "만들겠다"고 선언한 셋(--produces-dataset)은 **닫을 때**
// 실물 좌표로 받는다(이슈 #119).
//
// 왜 여기인가. 여는 시점에 sha 를 요구하면 닭-달걀이 된다 — 셋은 이 사이클의 산출물이다.
// 그렇다고 요구를 없애면 "무엇의 점수인지 모르는 수"가 다시 생긴다(#79·#81 이 막으려던 것).
// 닫는 시점에는 셋이 실물로 있으므로, 그때 받으면 둘 다 지켜진다. 그리고 그 자리에 남은
// 간선이 "이 사이클이 그 셋을 만들었다"를 말한다.
func requireProducedDatasets(chain, cycle string, given []string) {
	var promised []string
	for _, n := range cycleAnywhere(chain, cycle) {
		if n.kind == "define" || n.step == "s1" {
			for _, p := range trailerAllOf(n.sha, "Gil-Produces-Dataset") {
				if p != "" {
					promised = append(promised, p)
				}
			}
		}
	}
	if len(promised) == 0 {
		return
	}
	var missing []string
	for _, want := range promised {
		found := false
		for _, g := range given {
			name, _, _ := cut(g, "@")
			if strings.TrimSpace(name) == want && hasDatasetDigest(g) {
				found = true
				break
			}
		}
		if !found {
			missing = append(missing, want)
		}
	}
	if len(missing) == 0 {
		return
	}
	msg := "거부: 이 사이클은 평가셋을 **만들겠다고** 선언하고 열렸다(--produces-dataset).\n" +
		"  닫을 때는 그것이 실물로 있어야 한다 — 실제 좌표를 적어라:\n"
	for _, m := range missing {
		msg += "    gil close " + chain + "/" + cycle + " … --dataset " + m + "@sha256:<hex>\n"
	}
	msg += "  (여는 시점에 sha 를 요구하면 닭-달걀이라 이름만 받았다. 닫는 시점에는 잴 수 있다 —\n" +
		"   그래서 요구를 없애지 않고 이 자리로 옮겼다. 이슈 #119.)"
	die(msg)
}

// trailerAllOf — 한 커밋의 그 키 트레일러 값 전부.
func trailerAllOf(sha, key string) []string {
	out := strings.TrimSpace(gitlog("-1", "--format=%(trailers:key="+key+",valueonly,unfold)", sha, "--"))
	if out == "" {
		return nil
	}
	var vals []string
	for _, ln := range strings.Split(out, "\n") {
		if v := strings.TrimSpace(ln); v != "" {
			vals = append(vals, v)
		}
	}
	return vals
}
