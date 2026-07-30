// interview_notice.go — 도착한 답을 **다음 접촉 때 강제로 고지한다** (이슈 #77).
//
// 왜. 사람이 뷰어 폼에 답해도 에이전트는 그 사실을 모른다. #58 이 --wait 를 줬지만, 대화형
// 세션에서는 성질이 다르다: 지금 필요한 행동은 "폼에 답해주세요"라고 **말하는 것**이고,
// 말하려면 턴을 끝내야 하고, 턴을 끝내면 기다릴 수 없다. 그래서 "심고 → 알리고 → 턴 종료"가
// 국소적으로 늘 합리적으로 보이는데 **그 경로엔 재개 지점이 없다.**
//
// 통지(호스트 push)는 gil 이 보장할 수 없다 — 호스트 기능이다. 대신 gil 이 보장할 수 있는
// 것을 한다: **다음에 무슨 명령을 부르든**, 도착한 답이 있으면 한 줄 먼저 알린다. 에이전트가
// --status 를 떠올리지 못해도 걸린다.
//
// "봤다"는 로컬 상태다 — .git/gil/interview-seen 에 둔다(커밋 아님). 그래야 다른 클론·다른
// 에이전트는 각자 한 번씩 고지받는다. 기록 시점은 **에이전트가 실제로 그 답을 본 자리**뿐이다:
// gil handoff, 그리고 gil interview --status/--wait 가 done 을 보고할 때.
package main

import (
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// interviewDoneSHA — 이 체인의 인터뷰가 확정(Gil-Interview: done)된 커밋 sha. 없으면 "".
// 심층 인터뷰로 여러 차수가 쌓이면 **가장 최근** done 이 지금의 기준이다.
func interviewDoneSHA(chain string) string {
	fmtStr := "%H" + fsep + trailer("Gil-Chain") + fsep + trailer("Gil-Interview") + sep
	out := gitlog("--format="+fmtStr, "--branches")
	for _, rec := range strings.Split(out, sep) {
		parts := strings.SplitN(strings.TrimSpace(rec), fsep, 3)
		if len(parts) < 3 {
			continue
		}
		if strings.TrimSpace(parts[1]) == chain && strings.TrimSpace(parts[2]) == "done" {
			return first9(parts[0])
		}
	}
	return ""
}

// seenPath — 이 클론이 "봤다"고 기록해 둔 파일(.git 안 — 커밋되지 않는다).
func seenPath() string {
	dir := strings.TrimSpace(git("rev-parse", "--git-dir"))
	if dir == "" {
		return ""
	}
	return filepath.Join(dir, "gil", "interview-seen")
}

func seenMap() map[string]string {
	out := map[string]string{}
	p := seenPath()
	if p == "" {
		return out
	}
	b, err := os.ReadFile(p)
	if err != nil {
		return out
	}
	for _, ln := range strings.Split(string(b), "\n") {
		c, sha, ok := strings.Cut(strings.TrimSpace(ln), " ")
		if ok {
			out[c] = sha
		}
	}
	return out
}

// markInterviewSeen — 이 체인의 지금 답을 봤다고 기록한다. 실패해도 조용하다(고지가 한 번 더
// 뜰 뿐, 잃는 것은 없다 — 반대로 못 본 답을 봤다고 적는 것이 훨씬 나쁘다).
func markInterviewSeen(chain string) {
	sha := interviewDoneSHA(chain)
	if sha == "" {
		return
	}
	p := seenPath()
	if p == "" {
		return
	}
	m := seenMap()
	m[chain] = sha
	var keys []string
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var b strings.Builder
	for _, k := range keys {
		b.WriteString(k + " " + m[k] + "\n")
	}
	os.MkdirAll(filepath.Dir(p), 0o755)
	os.WriteFile(p, []byte(b.String()), 0o644)
}

// arrivedInterviews — 답이 도착했는데 이 클론이 아직 못 본 체인들.
func arrivedInterviews() []string {
	seen := seenMap()
	var out []string
	for chain := range declaredChains("--branches") {
		if chain == "" {
			continue
		}
		sha := interviewDoneSHA(chain)
		if sha == "" || seen[chain] == sha {
			continue
		}
		out = append(out, chain)
	}
	sort.Strings(out)
	return out
}

// noticeArrivedInterviews — 어떤 명령을 부르든 맨 앞에 한 줄. 이게 이 이슈의 핵심이다:
// 통지가 아니라 **다음 접촉 때의 강제 고지**.
func noticeArrivedInterviews() {
	// 저장소 밖에서는 고지할 것이 없다 — 그리고 **죽으면 안 된다**. 이 고지는 친절이지
	// 관문이 아닌데, git 저장소가 아닌 폴더에서 gil init 을 부르면 여기서 먼저 죽어
	// "gil init 이 git init 을 안 해준다"로 보였다(상현님 실사용). init 은 무에서 세우는
	// 명령이다 — 그 앞에 저장소를 요구하는 것이 서 있으면 안 된다.
	if !gitOK("rev-parse", "--git-dir") {
		return
	}
	chains := arrivedInterviews()
	if len(chains) == 0 {
		return
	}
	for _, c := range chains {
		stderr("⚡ 인터뷰 답이 도착해 있다 — 체인 " + c + " 의 기준 문서가 확정됐다(아직 안 읽었다).")
		stderr("   읽어라: gil interview " + c + " --status   (읽으면 이 고지는 사라진다)")
	}
	stderr("")
}

// interviewWaitingLines — handoff 최상단 '사람 답 대기' 종합 절에 실을 인터뷰 대기(이슈 #77).
//
// 같은 성격의 대기가 두 곳에 나뉘어 있고 한쪽만 "종합"이라는 이름을 갖고 있으면, 종합 절을
// 읽고 "인터뷰는 여기 없네"라고 결론 내리는 건 자연스러운 오독이다. 대기는 한 자리에 모은다.
func interviewWaitingLines() []string {
	var chains []string
	for chain := range declaredChains("--branches") {
		if chain != "" && interviewState(chain) == "pending" { // 재인터뷰도 대기다(#75)
			chains = append(chains, chain)
		}
	}
	sort.Strings(chains)
	var L []string
	for _, c := range chains {
		L = append(L, "  · [인터뷰] "+c+" — 기준 문서 미확정. 사람이 뷰어 폼에 답해야 사이클을 연다.")
		if interviewWaiterActive(c) {
			L = append(L, "      기다리는 프로세스가 살아 있다(백그라운드 --wait) — 제출되면 그쪽이 이어간다.")
			continue
		}
		L = append(L, "      ⚠ 아무도 안 기다린다 — 지금 제출돼도 아무 일이 안 일어난다(이슈 #82).")
		L = append(L, backgroundWaitHint(c)...)
	}
	return L
}
