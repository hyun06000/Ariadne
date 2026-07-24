// git.go — git 서브프로세스 껍질 + 커밋 그래프 파싱.
//
// gil은 git 래퍼다. 진실원은 언제나 커밋 그래프이고, 이 파일은 그걸 파싱하는 얇은 층.
// 참조 구현(gil.py)의 _git·collect_nodes·body_index를 그대로 옮긴다 — 로직 1:1, 언어만 Go.
// 외부 의존성 0: 표준 라이브러리만. git은 라이브러리가 아니라 도구 의존(os/exec).
package main

import (
	"os"
	"os/exec"
	"strings"
)

const (
	sep  = "\x1e" // 레코드 구분자 (커밋 사이)
	fsep = "\x1f" // 필드 구분자
	nul  = "\x00" // 멀티값 트레일러 구분자
)

// git 은 git을 실행하고 stdout을 준다. 실패하면 exit(참조: check=True).
func git(args ...string) string {
	out, err := gitTry(args...)
	if err != nil {
		die("git " + strings.Join(args, " ") + " 실패: " + err.Error())
	}
	return out
}

// gitTry 는 git을 실행하고 (stdout, err). 호출자가 실패를 흡수할 수 있게 한다.
func gitTry(args ...string) (string, error) {
	cmd := exec.Command("git", args...)
	var out strings.Builder
	cmd.Stdout = &out
	err := cmd.Run()
	return out.String(), err
}

// gitInput 은 stdin으로 msg를 넣고 git을 실행한다(commit/hash-object/mktree/commit-tree).
func gitInput(msg string, args ...string) string {
	cmd := exec.Command("git", args...)
	cmd.Stdin = strings.NewReader(msg)
	var out strings.Builder
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		die("git " + strings.Join(args, " ") + " 실패: " + err.Error())
	}
	return out.String()
}

// gitOK 는 git을 실행하고 성공 여부만 준다(merge-base --is-ancestor 등 판정용).
func gitOK(args ...string) bool {
	err := exec.Command("git", args...).Run()
	return err == nil
}

// gitlog 는 git log 래퍼. 커밋 0개(HEAD 부재)면 빈 문자열 — 오류가 아니라 '노드 없음'.
// 참조: _gitlog. 첫 체인을 여는 빈 저장소에서 git log는 exit 128로 죽지만 정상 흐름이다.
func gitlog(args ...string) string {
	out, err := gitTry(append([]string{"log"}, args...)...)
	if err != nil {
		return ""
	}
	return out
}

// node — 스텝 노드(Gil-Step 트레일러를 가진 커밋). 참조: collect_nodes의 dict.
type node struct {
	sha          string
	subject      string
	chain        string
	cycle        string
	step         string
	kind         string
	parent       string
	author       string
	cycleParents []string
	outcome      string
	backtrack    string
	merges       []string
}

// collectNodes — 커밋 그래프를 훑어 Gil-Step 트레일러를 가진 커밋을 스텝 노드로 수집.
// 참조: collect_nodes. 단일 git log로 모든 트레일러를 뽑는다(스텝별 fork 없음).
func collectNodes(revRange string) []node {
	fmt := strings.Join([]string{
		"%H", "%s",
		trailer("Gil-Chain"),
		trailer("Gil-Cycle"),
		trailer("Gil-Step"),
		trailer("Gil-Kind"),
		trailer("Gil-Parent"),
		trailer("Gil-Cycle-Author"),
		trailerMulti("Gil-Cycle-Parent"),
		trailer("Gil-Outcome"),
		trailer("Gil-Backtrack"),
		trailerMulti("Gil-Merge"),
	}, fsep) + sep
	// revRange 뒤 "--" 로 revision 확정 — 체인/브랜치명이 디렉토리명과 겹치면(예: viewer)
	// git 이 revision/path ambiguity 로 exit 128 로 죽는다(실사용 발견, viewer 실작업).
	out := gitlog("--format="+fmt, revRange, "--")
	var nodes []node
	for _, rec := range strings.Split(out, sep) {
		rec = strings.Trim(rec, "\n")
		if rec == "" {
			continue
		}
		f := strings.Split(rec, fsep)
		if len(f) < 12 {
			continue
		}
		step := strings.TrimSpace(f[4])
		if step == "" { // Gil-Step 없으면 일반 커밋
			continue
		}
		nodes = append(nodes, node{
			sha:          first9(f[0]),
			subject:      f[1],
			chain:        strings.TrimSpace(f[2]),
			cycle:        strings.TrimSpace(f[3]),
			step:         step,
			kind:         strings.TrimSpace(f[5]),
			parent:       strings.TrimSpace(f[6]),
			author:       strings.TrimSpace(f[7]),
			cycleParents: splitMulti(f[8]),
			outcome:      strings.TrimSpace(f[9]),
			backtrack:    strings.TrimSpace(f[10]),
			merges:       splitMulti(f[11]),
		})
	}
	return nodes
}

// bodyIndex — sha(9자) → 순수 본문(트레일러 제외) 인덱스를 단일 git log로.
// 참조: body_index. 스텝별 fork를 없앤다(62초 벽 → O(1), gil-v3-study/c002/s4).
func bodyIndex(revRange string) map[string]string {
	fmt := "%H" + fsep + "%b" + sep
	out := git("log", "--format="+fmt, revRange, "--") // "--": revision 확정(path ambiguity 방지)
	idx := map[string]string{}
	for _, rec := range strings.Split(out, sep) {
		rec = strings.Trim(rec, "\n")
		if rec == "" {
			continue
		}
		f := strings.SplitN(rec, fsep, 2)
		if len(f) < 2 {
			continue
		}
		idx[first9(f[0])] = stripTrailers(strings.TrimRight(f[1], "\n"))
	}
	return idx
}

var trailerPrefixes = []string{"Gil-", "Co-Authored-By:", "Co-authored-by:", "Signed-off-by:"}

// stripTrailers — 본문 끝의 트레일러 블록(알려진 키로 시작하는 라인)을 걷어낸다.
// 참조: _strip_trailers. 본문에도 콜론이 흔하므로 알려진 접두사로만 엄격히 구분한다.
func stripTrailers(body string) string {
	lines := strings.Split(body, "\n")
	end := len(lines)
	for end > 0 {
		ln := strings.TrimSpace(lines[end-1])
		if ln == "" {
			end--
			continue
		}
		if hasAnyPrefix(ln, trailerPrefixes) {
			end--
		} else {
			break
		}
	}
	return strings.TrimSpace(strings.Join(lines[:end], "\n"))
}

// ── 작은 헬퍼들 ─────────────────────────────────────────────────────────

func trailer(key string) string {
	return "%(trailers:key=" + key + ",valueonly)"
}

func trailerMulti(key string) string {
	return "%(trailers:key=" + key + ",valueonly,separator=%x00)"
}

func splitMulti(s string) []string {
	var out []string
	for _, x := range strings.Split(s, nul) {
		if strings.TrimSpace(x) != "" {
			out = append(out, strings.TrimSpace(x))
		}
	}
	return out
}

func first9(s string) string {
	if len(s) > 9 {
		return s[:9]
	}
	return s
}

func hasAnyPrefix(s string, prefixes []string) bool {
	for _, p := range prefixes {
		if strings.HasPrefix(s, p) {
			return true
		}
	}
	return false
}

func die(msg string) {
	os.Stderr.WriteString(msg + "\n")
	os.Exit(1)
}
