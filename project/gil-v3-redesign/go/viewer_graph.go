// gil 그래프 뷰어 — 다른 레포의 gil 그래프를 읽어 그린다(읽기 전용).
//
// 서브에이전트가 실사용 레포에서 gil 로 만드는 사고이력(체인>사이클>스텝)을 밖에서 관전
// 한다. git 명령은 -C <repo> 로 대상 레포에서 돈다 — 뷰어를 그 레포 안에 두지 않아 작업과
// 충돌 없음. stdlib 만, 외부 의존 0.
//
//   gil viewer text                    텍스트 트리 1회 출력
//   gil viewer serve [--port <포트>]   브라우저 관전 서버(자동 새로고침)
//   gil viewer build --out <파일>      정적 자기완결 HTML
// (옛 별도 바이너리 gilviewer 는 폐지되고 gil 에 통합됐다.)
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

var viewerRepoDir = "." // --repo 로 지정. git 을 이 레포에서 실행.

func viewerGit(args ...string) ([]byte, error) {
	// --no-optional-locks (이슈 #64①): 뷰어는 **관전자**다 — 저장소를 읽기만 해야 한다.
	// 그런데 폴링이 1.5초마다 도는 git status 는 인덱스를 갱신하며 .git/index.lock 을 잡는다.
	// 그 사이 같은 저장소에서 커밋하는 쪽(migrate 처럼 수십~수백 커밋을 연달아 치는 명령)은
	// 락 경합으로 exit 128 로 죽는다 — 매번 다른 지점에서, 원인을 가리키지 않는 메시지로.
	// 뷰어는 온보딩·handoff 가 "띄우라"고 지시하는 것이라, 지시대로 띄운 사람이 정확히 이
	// 함정을 밟았다. git 에는 이걸 위한 스위치가 있다: 선택적 락을 아예 잡지 않는다.
	full := append([]string{"--no-optional-locks", "-C", viewerRepoDir}, args...)
	// gitCommand 로 콘솔 숨김(윈도우). 뷰어 폴링이 1.5초마다 이걸 부르므로, 이게 없으면
	// 콘솔 없는 부모에서 cmd 창이 깜빡임을 반복한다(실사용 피드백, 결함 A).
	return gitCommand(full...).Output()
}

// allRefs — 뷰어가 훑는 커밋 범위. 로컬 브랜치(--branches)뿐 아니라 원격 추적
// 브랜치(--remotes)까지 본다. 신선한 클론은 로컬에 기본 브랜치 하나뿐이고 gil
// 그래프는 refs/remotes/origin/* 에만 있어, --branches 만이면 그래프를 통째로
// 놓쳤다(상현님: example 을 clone 하니 스텝 0개). 로컬·원격이 같은 커밋을 겹쳐
// 내도 viewerCollectNodes 의 SHA dedup 이 접는다.
var allRefs = []string{"--branches", "--remotes"}

// viewerLog — git log 를 allRefs(로컬+원격) 범위로 돌린다. extra 는 --format 등.
func viewerLog(extra ...string) ([]byte, error) {
	args := append([]string{"log"}, allRefs...)
	args = append(args, extra...)
	return viewerGit(args...)
}

type viewerNode struct {
	sha, full, subject       string
	chain, cycle, step, kind string
	outcome, verdict         string
	advances, toward         string // 체인 목적에 다가서려는 몫 / 다가선 정도(회고)
	nextDesign               string // 목적을 위한 다음 설계 — 다음 세대가 물려받는다
	plan, planOutcome        string // 가설 전에 고정한 설계와 그 결과(held|broke) — 이슈 #76
	planDiff                 string // 깨졌으면 무엇이 달랐나
	parent, backtrack        string   // Gil-Parent(부모 스텝), Gil-Backtrack(되돌아간 목표)
	refutes                  []string // Gil-Refutes: 이 스텝/사이클이 소급 반증하는 verify 스텝들(AIL #1 B)
	refutedBy                []string // 역인덱스: 이 스텝을 반증한 스텝들(뷰어가 ⚠refuted-by 표시)
	refines                  []string // Gil-Refines: 이 스텝/사이클이 해석을 정밀화하는 대상들(이슈 #42)
	refinedBy                []string // 역인덱스: 이 스텝의 해석을 정밀화한 스텝들(뷰어가 ⤳refined-by 표시)
	cycleParents             []string // Gil-Cycle-Parent: 사이클 계보 부모(경계 stub 엣지용, AIL #7)
	inherit                  string   // Gil-Inherit: 부모에게서 물려받은 전수(경계 라벨용, AIL #3·#7)
	gitParents               []string // 실제 커밋 부모 SHA(9자) — 진짜 DAG 그래프용(%P).
	body                     string   // 커밋 본문 전체(%B) — 정적 build 시 스텝 보고서를 인라인 임베드.
	deployTag                string   // Gil-Deploy: 이 스텝에서 배포된 태그(예 v0.2.0). 이슈 #34.
	deployState              string   // Gil-Deploy-State: staged|live (이슈 #56). staged 는 아직 안 올라갔다.
	deployURL                string   // Gil-Deploy-Url: 릴리스 URL(있으면).
	deployTarget             string   // Gil-Deploy-Target: 어디로 나갔나(host:port·환경). 이슈 #56.
}

func viewerCollectNodes() []viewerNode {
	const rs = "\x1e"
	const fs = "\x1f"
	// 필드: sha · subject · 커밋부모(%P) · trailers · body(%B). %P 는 진짜 DAG 그래프용
	// (스텝을 커밋 부모로 연결). body 는 정적 build 시 스텝 보고서를 인라인 임베드하려고
	// 싣는다. %B 가 여러 줄·trailers 포함이라 마지막 필드에 두고 SplitN(…,5).
	format := "%H" + fs + "%s" + fs + "%P" + fs + "%(trailers:only=true,unfold=true)" + fs + "%B" + rs
	out, err := viewerLog("--format=" + format)
	if err != nil {
		fmt.Fprintln(os.Stderr, "거부: git log 실패(레포 경로·gil 그래프 확인) —", err)
		return nil
	}
	var nodes []viewerNode
	// 배포 마커(이슈 #34): Gil-Deploy 를 실은 얇은 커밋은 Gil-Step 이 없어 노드 루프가 건너뛴다.
	// 대상 스텝(Gil-Deploy-At = chain/cycle/step)에 태그·URL 을 매핑해 두고, 노드 수집 뒤 얹는다.
	type deployMark struct{ tag, url, state, target string }
	deploys := map[string]deployMark{}
	// 커밋 하나 = 노드 하나. git log --branches 는 보통 공유 커밋을 접어 주지만 그건
	// git 이 보증하는 불변식이 아니다(여러 워킹트리·특정 ref 배치에서 같은 SHA 재출력).
	// 조상 define 에서 형제 가지를 분기하면 그 define 커밋이 여러 브랜치 공통조상이 되는데,
	// 만약 재출력되면 스택·사이클 뷰에 define 이 두 번 뜬다(상현님이 본 "define 두 개").
	// dagJSON 은 자체 SHA dedup 이 있었지만 buildGraph 소스인 여기엔 없었다 —
	// 최상류에서 한 번 접어 buildGraph·stackJSON·dagJSON 을 모두 깨끗하게 한다.
	seenSHA := map[string]bool{}
	for _, rec := range strings.Split(string(out), rs) {
		rec = strings.TrimLeft(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		parts := strings.SplitN(rec, fs, 5)
		if len(parts) < 5 {
			continue
		}
		tr := parseTrailers(parts[3])
		if tr["Gil-Step"] == "" {
			// 배포 마커: Gil-Step 없이 Gil-Deploy 만 실은 얇은 커밋. 대상 스텝에 얹으려 모은다.
			if at := tr["Gil-Deploy-At"]; at != "" && !seenSHA[parts[0]] {
				deploys[at] = deployMark{tag: tr["Gil-Deploy"], url: tr["Gil-Deploy-Url"],
					state: tr["Gil-Deploy-State"], target: tr["Gil-Deploy-Target"]}
			}
			continue
		}
		if seenSHA[parts[0]] {
			continue // 같은 커밋 재출력 — 노드 중복 방지
		}
		seenSHA[parts[0]] = true
		// %P = 공백구분 커밋 부모 SHA(40자) → 9자로 줄여 노드 sha 와 맞춘다.
		var gp []string
		for _, p := range strings.Fields(parts[2]) {
			if len(p) >= 9 {
				gp = append(gp, p[:9])
			}
		}
		nodes = append(nodes, viewerNode{
			sha: parts[0][:9], full: parts[0], subject: parts[1],
			chain: tr["Gil-Chain"], cycle: tr["Gil-Cycle"], step: tr["Gil-Step"],
			kind: tr["Gil-Kind"], outcome: tr["Gil-Outcome"], verdict: tr["Gil-Verdict"],
			plan: tr["Gil-Plan"], planOutcome: tr["Gil-Plan-Outcome"], planDiff: tr["Gil-Plan-Diff"],
			advances: tr["Gil-Advances"], toward: tr["Gil-Toward"], nextDesign: tr["Gil-Next-Design"],
			parent: tr["Gil-Parent"], backtrack: tr["Gil-Backtrack"],
			refutes:      trailerAll(parts[3], "Gil-Refutes"), // multi-value(map은 마지막만 남아 직접 파싱)
			refines:      trailerAll(parts[3], "Gil-Refines"), // 정밀화 간선(이슈 #42)
			cycleParents: trailerAll(parts[3], "Gil-Cycle-Parent"),
			inherit:      tr["Gil-Inherit"],
			gitParents:   gp,
			body:         strings.TrimRight(parts[4], "\n"),
		})
	}
	// 소급 반증 역인덱스(AIL #1 B): refutes 대상에게 "너는 누구에게 반증됐다"를 달아준다.
	// 뷰어가 반증된 supported verify 에 ⚠refuted-by 를 붙여 "흠 없는 success" 착시를 깬다.
	idx := map[string]int{}
	for i, n := range nodes {
		idx[n.chain+"/"+n.cycle+"/"+n.step] = i
	}
	for _, n := range nodes {
		for _, rf := range n.refutes {
			if j, ok := idx[rf]; ok {
				src := n.chain + "/" + n.cycle + "/" + n.step
				nodes[j].refutedBy = append(nodes[j].refutedBy, src)
			}
		}
	}
	// 정밀화 역인덱스(이슈 #42): 대상에게 "너의 해석은 뒤에 더 좁혀졌다"를 달아준다. 판정은
	// 그대로 서 있으므로 ⚠(반증)가 아니라 ⤳(이어짐) 표식이다 — 앞 사이클의 성과를 부정하지
	// 않으면서, 그 결론만 읽고 멈추는 걸 막는다.
	for _, n := range nodes {
		for _, rf := range n.refines {
			if j, ok := idx[rf]; ok {
				src := n.chain + "/" + n.cycle + "/" + n.step
				nodes[j].refinedBy = append(nodes[j].refinedBy, src)
			}
		}
	}
	// 배포 마커(이슈 #34)를 대상 스텝에 얹는다. 한 스텝에 여러 배포가 얹히면(재배포) 마지막을 쓴다.
	for at, dm := range deploys {
		if j, ok := idx[at]; ok {
			nodes[j].deployTag = dm.tag
			nodes[j].deployURL = dm.url
			nodes[j].deployState = dm.state
			nodes[j].deployTarget = dm.target
		}
	}
	return nodes
}

// trailerAll — 한 커밋 trailer 블록에서 특정 키의 모든 값(multi-value). parseTrailers 맵은
// 같은 키를 마지막 값으로 덮어써서 Gil-Refutes 같은 다중 간선을 못 담는다.
func trailerAll(block, key string) []string {
	var out []string
	for _, ln := range strings.Split(block, "\n") {
		k, v, ok := strings.Cut(ln, ":")
		if ok && strings.TrimSpace(k) == key {
			if val := strings.TrimSpace(v); val != "" {
				out = append(out, val)
			}
		}
	}
	return out
}

// commitParentMap — 모든 커밋(gil 스텝이든 아니든)의 부모 사슬(9자 SHA). dagJSON 이
// 비-gil 커밋(chain/close/chain-close/init)을 건너뛰어 조상 gil 스텝을 찾을 때 쓴다.
func commitParentMap() map[string][]string {
	const fs = "\x1f"
	const rs = "\x1e"
	out, err := viewerLog("--format=%H" + fs + "%P" + rs)
	if err != nil {
		return nil
	}
	m := map[string][]string{}
	for _, rec := range strings.Split(string(out), rs) {
		rec = strings.TrimSpace(rec)
		if rec == "" {
			continue
		}
		sha, parents, ok := strings.Cut(rec, fs)
		if !ok || len(sha) < 9 {
			continue
		}
		var ps []string
		for _, p := range strings.Fields(parents) {
			if len(p) >= 9 {
				ps = append(ps, p[:9])
			}
		}
		m[sha[:9]] = ps
	}
	return m
}

func parseTrailers(s string) map[string]string {
	m := map[string]string{}
	for _, ln := range strings.Split(s, "\n") {
		k, v, ok := strings.Cut(ln, ":")
		if ok {
			m[strings.TrimSpace(k)] = strings.TrimSpace(v)
		}
	}
	return m
}

func tipSHAs() map[string]string {
	const fs = "\x1f"
	out, err := viewerGit("for-each-ref", "--format=%(refname:short)"+fs+"%(objectname)", "refs/heads/")
	if err != nil {
		return nil
	}
	tips := map[string]string{}
	for _, ln := range strings.Split(strings.TrimSpace(string(out)), "\n") {
		br, sha, ok := strings.Cut(ln, fs)
		if ok {
			tips[br] = sha
		}
	}
	return tips
}

// chainParent — 각 체인이 어느 체인에서 갈라졌나(계보 엣지). 자식→부모.
// chain-root 에서 첫 부모 사슬을 거슬러 올라가 처음 만나는 Gil-Chain 이 부모 체인.
// 한 칸만 보면 안 된다 — 체인을 닫고 평범 커밋(트레일러 없음)을 쌓은 뒤 다음 체인을
// 열면 첫 부모가 비-gil 커밋이라 계보가 끊겨, 체인 그래프가 고아 노드가 되고 전체맵
// (dagJSON 은 비-gil 을 건너뜀)과 안 맞았다(상현님: AIL 레포 관전). 부모 없으면 "".
func chainParents() map[string]string {
	const rs = "\x1e"
	const fs = "\x1f"
	// 모든 chain-root 커밋: sha, 이 커밋의 체인, 첫 부모 sha.
	// 레코드 구분자는 rs(\x1e) — trailer 값(Gil-Chain-Purpose 등)에 개행이 들어가면
	// "\n" split 이 한 레코드를 쪼개 chain 필드가 빈 값이 된다(상현님: 새 체인 hackathon-a
	// 가 뷰어에 안 뜸 — Gil-Chain-Purpose 가 길어 파싱이 밀렸다). valueonly 대신 -z 대체로
	// rs 로 확정한다.
	out, err := viewerLog("--format=%H" + fs + "%(trailers:key=Gil-Kind,valueonly,unfold=true)" + fs +
		"%(trailers:key=Gil-Chain,valueonly,unfold=true)" + fs + "%P" + rs)
	if err != nil {
		return nil
	}
	// 커밋 sha → 그 커밋이 속한 체인 (부모 커밋의 체인을 찾기 위해).
	shaChain := map[string]string{}
	// 커밋 sha → Gil-Kind. "이 조상이 chain-close 였나"를 보려면 필요하다(아래 계승 판정).
	shaKind := map[string]string{}
	// 커밋 sha → 첫 부모 sha — 비-gil 커밋을 건너 조상 체인까지 거슬러 올라가는 사슬.
	firstParent := map[string]string{}
	type rootRec struct{ chain, firstParent string }
	var roots []rootRec
	for _, rec := range strings.Split(string(out), rs) {
		rec = strings.Trim(rec, "\n")
		if rec == "" {
			continue
		}
		f := strings.Split(rec, fs)
		if len(f) < 4 {
			continue
		}
		sha := strings.TrimSpace(f[0])
		kind := strings.TrimSpace(f[1])
		chain := strings.TrimSpace(f[2])
		parents := strings.TrimSpace(f[3])
		if chain != "" {
			shaChain[sha] = chain
		}
		shaKind[sha] = kind
		fp := ""
		if ps := strings.Fields(parents); len(ps) > 0 {
			fp = ps[0]
		}
		firstParent[sha] = fp
		if kind == "chain-root" {
			roots = append(roots, rootRec{chain, fp})
		}
	}
	// **"이어받음"은 부모 체인이 닫혀 있을 때만 성립한다**(이슈 #53·#54).
	//
	// 계보를 git 조상관계에서 읽는 건 맞지만, 조상관계만으로는 두 가지가 구분되지 않는다:
	//   (가) 진짜 계승 — 앞 체인을 chain-close 로 닫고 그 끝에서 새 체인을 연다(배포 순환).
	//   (나) 병렬 작업 — 앞 체인이 아직 열려 있는데 옆에서 다른 줄기를 시작한다.
	// 둘 다 git 에서는 "새 브랜치가 HEAD 에서 갈라진" 같은 모양이라, 옛 코드는 (나)까지
	// "부모 체인 X 에서 이어받음"이라고 **단언**했다. 실측: v2 에서 `parent: null` 인 독립
	// 체인 5개가 이주 뒤 한 줄로 이어졌고, 같은 기간에 서로 다른 장비에서 동시에 굴리던
	// 트랙들이 "이어받음"으로 각인됐다. **그런 이어받음은 없었다.**
	//
	// 닫힘을 기준으로 삼는 근거는 gil 자신의 규칙이다 — 체인은 "닫힌 체인 끝에서만" 이어받는다
	// (SPEC 체인 원칙). 부모가 아직 열려 있다면 그건 이어받은 게 아니라 나란히 간 것이다.
	// 없는 계보를 그리느니 안 그린다 — 없는 성공을 날조하지 않는 것과 같은 원칙이다.
	// 판정은 **만들어진 순간** 기준이다. "부모가 지금 닫혀 있나"로 보면, 나란히 시작한 체인도
	// 나중에 앞 체인이 닫히는 순간 소급해서 자식이 되어버린다(실측으로 확인).
	//
	// 그래서 이렇게 본다: 자식 루트에서 첫 부모를 거슬러 올라가다 **처음 만나는 다른 체인의
	// 커밋이 그 체인의 chain-close 인가**. 그렇다면 그 닫힌 끝에서 태어난 것이니 진짜 계승이다.
	// 열린 사이클의 스텝 위에서 태어났다면 그건 나란히 간 줄기다 — 그 순간 그 체인은 진행
	// 중이었다.
	parent := map[string]string{}
	for _, r := range roots {
		parent[r.chain] = "" // 기본: 뿌리 체인(독립)
		seen := map[string]bool{}
		for fp := r.firstParent; fp != "" && !seen[fp]; fp = firstParent[fp] {
			seen[fp] = true
			ch, ok := shaChain[fp]
			if !ok || ch == r.chain {
				continue // 비-gil 커밋이거나 아직 자기 체인 — 계속 거슬러 올라간다
			}
			if shaKind[fp] == "chain-close" {
				parent[r.chain] = ch // 닫힌 끝에서 태어났다 — 진짜 계승
			}
			// 아니면 계보를 안 그린다: 그 순간 저 체인은 진행 중이었다(병렬).
			break
		}
	}
	return parent
}

type cycleView struct {
	name  string
	steps []viewerNode
}
type chainView struct {
	name   string
	cycles []cycleView
}
type graphView struct {
	chains              []chainView
	here                map[string]string // "chain/cycle/step" → HEAD 스텝 위치
	hereCyc             map[string]string // "chain/cycle" → HEAD 가 이 사이클(스텝 팁 아닐 때)
	parents             map[string]string // 체인 계보 엣지: 자식→부모
	allNodes            []viewerNode      // 전체 스텝 노드(진짜 커밋 DAG 그래프용)
	nodeCount, tipCount int
	work                workStatus       // 현재 HEAD 워킹트리의 미커밋 작업 상태(진행 라이브 표시)
	anchor              workAnchorInfo   // 그 작업이 **어디서** 벌어지고 있나(#79 후속)
	interviews          []interviewReq   // 아직 답 안 된 인터뷰 요구(사람 폼 대기, 이슈 #33)
	references          []referenceCard  // 사람이 제출해 확정된 기준 문서들(상현님: 제출의 결과가 보여야 한다)
	prunes              []pruneReq       // 사람의 승인을 기다리는 삭제 요청(상현님: 승인 없인 아무것도 안 지운다)
}

// interviewReq — 사람의 답을 기다리는 인터뷰 요구(gil interview 로 심긴 것). 뷰어가 이걸
// 폼으로 렌더한다. questions 는 gil-interview 펜스에서 뽑은 원본 JSON 문자열.
type interviewReq struct {
	chain     string
	sha       string
	questions string // gil-interview 펜스 안의 질문 배열 JSON
	waiting   bool   // 지금 이 답을 기다리는 프로세스가 살아 있나(백그라운드 --wait, 이슈 #82)
}

// chainClosedViewer / supersededByViewer — 관전 레포에서 이 체인이 봉인됐나, 결론이 다른
// 체인에서 뒤집혔나(이슈 #85). 판정은 CLI 와 같은 트레일러를 본다 — 두 표면이 다른 답을
// 하면 사람은 어느 쪽을 믿을지 모른다.
func chainClosedViewer(chain string) bool {
	return viewerChainTrailer(chain, "Gil-Kind") == "chain-close" ||
		viewerHasKind(chain, "chain-close")
}

func supersededByViewer(chain string) string {
	return viewerChainTrailer(chain, "Gil-Superseded-By")
}

// viewerHasKind — 이 체인에 그 kind 의 커밋이 하나라도 있나.
func viewerHasKind(chain, kind string) bool {
	const rs = "\x1e"
	const fs = "\x1f"
	out, err := viewerLog("--format=%(trailers:key=Gil-Chain,valueonly)" + fs +
		"%(trailers:key=Gil-Kind,valueonly)" + rs)
	if err != nil {
		return false
	}
	for _, rec := range strings.Split(string(out), rs) {
		c, k, _ := strings.Cut(strings.TrimLeft(rec, "\n"), fs)
		if strings.TrimSpace(c) == chain && strings.TrimSpace(k) == kind {
			return true
		}
	}
	return false
}

// viewerChainTrailer — 이 체인 커밋들 중 그 트레일러의 최신 값.
func viewerChainTrailer(chain, key string) string {
	const rs = "\x1e"
	const fs = "\x1f"
	out, err := viewerLog("--format=%(trailers:key=Gil-Chain,valueonly)" + fs +
		"%(trailers:key=" + key + ",valueonly)" + rs)
	if err != nil {
		return ""
	}
	for _, rec := range strings.Split(string(out), rs) {
		c, v, _ := strings.Cut(strings.TrimLeft(rec, "\n"), fs)
		if strings.TrimSpace(c) == chain && strings.TrimSpace(v) != "" {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

// viewerGitDir — 관전 중인 저장소의 .git 디렉토리(절대경로). 뷰어는 다른 작업 디렉토리에서
// 도는 별도 프로세스라, 로컬 상태 파일(.git/gil/*)을 읽으려면 이걸 먼저 풀어야 한다.
func viewerGitDir() string {
	out, err := viewerGit("rev-parse", "--absolute-git-dir")
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

// referenceCard — 사람이 제출해 **확정된** 기준 문서 하나(상현님: 제출해도 아무 일도 안
// 일어나 보인다). 제출의 결과가 화면에 남아야 사람이 자기 답이 도착했음을 안다.
type referenceCard struct {
	chain string
	sha   string
	text  string
	seen  bool // 에이전트가 이 답을 읽었나(.git/gil/interview-seen)
	wait  bool // 지금 이 체인의 답을 기다리는 프로세스가 있나
}

// resolvedInterviews — 확정된 기준 문서들(최신 차수 하나씩). 뷰어가 "제출 → 무슨 일이
// 일어났나"를 지속적으로 보여주는 근거다.
func resolvedInterviews() []referenceCard {
	const rs = "\x1e"
	const fs = "\x1f"
	format := "%H" + fs + "%(trailers:key=Gil-Chain,valueonly)" + fs +
		"%(trailers:key=Gil-Reference,valueonly)" + fs + "%B" + rs
	out, err := viewerLog("--format=" + format)
	if err != nil {
		return nil
	}
	seenMap := map[string]string{}
	if dir := viewerGitDir(); dir != "" {
		if b, err := os.ReadFile(filepath.Join(dir, "gil", "interview-seen")); err == nil {
			for _, ln := range strings.Split(string(b), "\n") {
				c, sha, ok := strings.Cut(strings.TrimSpace(ln), " ")
				if ok {
					seenMap[c] = sha
				}
			}
		}
	}
	var cards []referenceCard
	done := map[string]bool{}
	for _, rec := range strings.Split(string(out), rs) { // new→old: 체인당 최신 하나
		rec = strings.TrimLeft(rec, "\n")
		parts := strings.SplitN(rec, fs, 4)
		if len(parts) < 4 || strings.TrimSpace(parts[2]) != "true" {
			continue
		}
		chain := strings.TrimSpace(parts[1])
		if chain == "" || done[chain] {
			continue
		}
		done[chain] = true
		body := parts[3]
		if i := strings.Index(body, "── 기준 문서(레퍼런스 트루스) ──"); i >= 0 {
			body = body[i:]
		}
		sha := parts[0][:9]
		cards = append(cards, referenceCard{
			chain: chain, sha: sha, text: strings.TrimSpace(stripTrailers(body)),
			seen: strings.HasPrefix(seenMap[chain], sha) || strings.HasPrefix(sha, seenMap[chain]) && seenMap[chain] != "",
			wait: viewerWaiterActive(chain),
		})
	}
	sort.Slice(cards, func(i, j int) bool { return cards[i].chain < cards[j].chain })
	return cards
}

// pruneReq — 사람의 승인을 기다리는 삭제 요청. 삭제는 비가역이라 **사람 손에서만** 눌린다.
type pruneReq struct {
	target string
	sha    string
	body   string
}

// pendingPrunes — prune-request 중 아직 승인·실행되지 않은 것들.
func pendingPrunes() []pruneReq {
	const rs = "\x1e"
	const fs = "\x1f"
	format := "%H" + fs + "%(trailers:key=Gil-Kind,valueonly)" + fs +
		"%(trailers:key=Gil-Prune-Target,valueonly)" + fs + "%B" + rs
	out, err := viewerLog("--format=" + format)
	if err != nil {
		return nil
	}
	settled := map[string]bool{} // 승인되었거나 이미 실행된 대상
	var reqs []pruneReq
	seen := map[string]bool{}
	for _, rec := range strings.Split(string(out), rs) { // new→old
		parts := strings.SplitN(strings.TrimLeft(rec, "\n"), fs, 4)
		if len(parts) < 4 {
			continue
		}
		kind, target := strings.TrimSpace(parts[1]), strings.TrimSpace(parts[2])
		if target == "" {
			continue
		}
		switch kind {
		case "prune-approve", "prune":
			settled[target] = true
		case "prune-request":
			if !seen[target] {
				seen[target] = true
				reqs = append(reqs, pruneReq{target: target, sha: parts[0][:9], body: strings.TrimSpace(stripTrailers(parts[3]))})
			}
		}
	}
	var open []pruneReq
	for _, r := range reqs {
		if !settled[r.target] {
			open = append(open, r)
		}
	}
	return open
}

// viewerWaiterActive — 관전 중인 저장소에서 이 체인의 대기 표식이 살아있나(이슈 #82).
// interviewWaiterActive 와 같은 판정이되 git-dir 을 관전 레포 기준으로 푼다 — 뷰어는 다른
// 작업 디렉토리에서 도는 별도 프로세스다.
func viewerWaiterActive(chain string) bool {
	dir := viewerGitDir()
	if dir == "" {
		return false
	}
	p := filepath.Join(dir, "gil", "interview-waiting-"+chain)
	st, err := os.Stat(p)
	if err != nil {
		return false
	}
	return time.Since(st.ModTime()) <= waiterStale
}

// pendingInterviews — Gil-Interview:pending 커밋 중 아직 done 으로 해소 안 된 것들. 같은
// 체인에 done 마커가 있으면(제출됨) 뺀다. 질문 JSON 은 본문의 ```gil-interview 펜스에서 추출.
func pendingInterviews() []interviewReq {
	const rs = "\x1e"
	const fs = "\x1f"
	format := "%H" + fs + "%(trailers:key=Gil-Chain,valueonly)" + fs +
		"%(trailers:key=Gil-Interview,valueonly)" + fs + "%B" + rs
	out, err := viewerLog("--format=" + format)
	if err != nil {
		return nil
	}
	// **최신 마커가 상태를 정한다**(이슈 #75). 옛 코드는 done 이 하나라도 있으면 그 체인의
	// pending 을 전부 걸러, 확정 뒤의 재인터뷰가 뷰어에서 통째로 사라졌다 — 커밋은 있는데
	// 폼이 안 뜨고, 아무도 그 사실을 모른다. 체인별로 **처음 만난**(=가장 최신) 마커만 본다.
	settled := map[string]bool{}      // 이 체인의 최신 마커를 이미 봤다
	done := map[string]bool{}         // 최신 마커가 done 인 체인
	var reqs []interviewReq           // pending 요구(최신 우선 — viewerLog 는 new→old)
	seenChain := map[string]bool{}    // 체인당 최신 pending 하나만
	for _, rec := range strings.Split(string(out), rs) {
		rec = strings.TrimLeft(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		parts := strings.SplitN(rec, fs, 4)
		if len(parts) < 4 {
			continue
		}
		sha, chain, iv, body := parts[0], strings.TrimSpace(parts[1]), strings.TrimSpace(parts[2]), parts[3]
		if iv == "done" {
			if !settled[chain] {
				settled[chain] = true
				done[chain] = true
			}
			continue
		}
		if iv == "pending" && !seenChain[chain] {
			settled[chain] = true
			seenChain[chain] = true
			reqs = append(reqs, interviewReq{chain: chain, sha: sha[:9], questions: extractInterviewJSON(body),
				waiting: viewerWaiterActive(chain)})
		}
	}
	var open []interviewReq
	for _, r := range reqs {
		if !done[r.chain] { // 그 체인이 아직 제출 안 됐으면 폼을 띄운다
			open = append(open, r)
		}
	}
	return open
}

// extractInterviewJSON — 커밋 본문의 ```gil-interview … ``` 펜스 안 JSON 을 뽑는다.
func extractInterviewJSON(body string) string {
	const open = "```gil-interview"
	i := strings.Index(body, open)
	if i < 0 {
		return ""
	}
	rest := body[i+len(open):]
	j := strings.Index(rest, "```")
	if j < 0 {
		return strings.TrimSpace(rest)
	}
	return strings.TrimSpace(rest[:j])
}

// workStatus — 대상 레포 워킹트리의 미커밋 변경 요약. gil 그래프에 커밋으로 박지 않고
// (커밋=완결 사고단위 불변식 유지) 뷰어가 현재 스텝 위에 오버레이로만 그린다. 이래야
// 마지막 커밋 이후 작업이 살아있어도 "멈춘 듯" 보이지 않는다(상현님).
// workAnchorInfo — **어디서** 작업 중인가(이슈 #79 후속, 상현님). 미커밋 변경은 아직 노드가
// 아니라서, 커밋하기 전까지 그래프 어디에도 "지금 여기서 손대고 있다"가 없다. HEAD 계보에서
// 가장 가까운 gil 스텝을 앵커로 잡아, 뷰어가 그 옆에 '작업중' 유령 노드를 그리게 한다.
// HEAD 가 gil 커밋 위가 아니어도(평범한 브랜치여도) 조상으로 거슬러 찾으므로 늘 자리가 있다.
type workAnchorInfo struct {
	sha    string // 앵커 스텝 커밋(9자). 없으면 ""
	chain  string
	cycle  string
	step   string
	branch string // 지금 HEAD 브랜치(분리면 "")
	ahead  int    // 앵커 이후 이 브랜치에 쌓인 gil 아닌 커밋 수(문서 커밋 등)
}

type workStatus struct {
	dirty      bool     // 미커밋 변경이 있는가
	files      int      // 변경된 경로 수(staged+unstaged+untracked, 중복 제거)
	added      int      // git diff --shortstat insertions (staged+unstaged 합산)
	deleted    int      // 〃 deletions
	sample     []string // 변경 경로 샘플(최대 몇 개, 앞에 상태문자)
}

// summary — "N개 파일" 뒤에 라인 증감이 있을 때만 ", +A −D" 를 덧붙인다.
// untracked 신규 파일만 있으면 git diff 가 라인을 안 세므로 +0 −0 을 감춘다(오해 방지).
func (w workStatus) summary() string {
	s := fmt.Sprintf("%d개 파일", w.files)
	if w.added > 0 || w.deleted > 0 {
		s += fmt.Sprintf(", +%d −%d", w.added, w.deleted)
	}
	return s
}

// workAnchor — HEAD 에서 조상으로 거슬러 처음 만나는 gil 스텝. 그 사이의 평범한 커밋 수도 센다.
func workAnchor() workAnchorInfo {
	info := workAnchorInfo{branch: currentBranch()}
	if info.branch == "HEAD" {
		info.branch = ""
	}
	fmtStr := "%H" + "\x1f" + trailer("Gil-Chain") + "\x1f" + trailer("Gil-Cycle") +
		"\x1f" + trailer("Gil-Step") + "\x1e"
	raw, err := viewerGit("log", "--format="+fmtStr, "HEAD")
	if err != nil {
		return info
	}
	for _, rec := range strings.Split(string(raw), "\x1e") {
		rec = strings.Trim(rec, "\n")
		if strings.TrimSpace(rec) == "" {
			continue
		}
		f := strings.Split(rec, "\x1f")
		if len(f) < 4 || strings.TrimSpace(f[3]) == "" {
			info.ahead++ // gil 이 만들지 않은 커밋 — 앵커 위에 얹힌 것
			continue
		}
		info.sha = f[0][:9]
		info.chain, info.cycle, info.step = strings.TrimSpace(f[1]), strings.TrimSpace(f[2]), strings.TrimSpace(f[3])
		return info
	}
	return info
}

// workingStatus — 대상 레포의 미커밋 상태를 읽는다. 실패/클린이면 dirty=false.
func workingStatus() workStatus {
	var w workStatus
	// --porcelain: 경로별 상태(XY path). untracked 포함. 경로 수·샘플용.
	out, err := viewerGit("status", "--porcelain")
	if err != nil {
		return w
	}
	for _, ln := range strings.Split(strings.TrimRight(string(out), "\n"), "\n") {
		if strings.TrimSpace(ln) == "" {
			continue
		}
		w.files++
		if len(w.sample) < 5 && len(ln) > 3 {
			w.sample = append(w.sample, strings.TrimSpace(ln[:2])+" "+strings.TrimSpace(ln[3:]))
		}
	}
	w.dirty = w.files > 0
	if !w.dirty {
		return w
	}
	// 라인 증감: staged(--cached)와 unstaged 를 합산. untracked 는 diff 에 안 잡히나
	// files 카운트엔 이미 포함됐다(대략치로 충분 — 정확한 신규파일 라인수는 목적 밖).
	w.added, w.deleted = diffLines()
	return w
}

// diffLines — git diff --shortstat 의 insertions/deletions 합(staged+unstaged).
func diffLines() (add, del int) {
	for _, args := range [][]string{
		{"diff", "--shortstat"},          // unstaged
		{"diff", "--shortstat", "--cached"}, // staged
	} {
		out, err := viewerGit(args...)
		if err != nil {
			continue
		}
		a, d := parseShortstat(string(out))
		add += a
		del += d
	}
	return
}

// parseShortstat — " N files changed, A insertions(+), D deletions(-)" 파싱.
func parseShortstat(s string) (add, del int) {
	for _, seg := range strings.Split(s, ",") {
		seg = strings.TrimSpace(seg)
		var n int
		if _, e := fmt.Sscanf(seg, "%d", &n); e != nil {
			continue
		}
		if strings.Contains(seg, "insertion") {
			add = n
		} else if strings.Contains(seg, "deletion") {
			del = n
		}
	}
	return
}

// hereChains — 현재위치가 있는 체인 이름 집합(스텝 또는 사이클 레벨).
func (g graphView) hereChains() map[string]bool {
	m := map[string]bool{}
	for k := range g.here {
		if i := strings.IndexByte(k, '/'); i > 0 {
			m[k[:i]] = true
		}
	}
	for k := range g.hereCyc {
		if i := strings.IndexByte(k, '/'); i > 0 {
			m[k[:i]] = true
		}
	}
	return m
}

func posKey(n viewerNode) string { return n.chain + "/" + n.cycle + "/" + n.step }

// status — 사이클의 결말 요약. 마지막 analyze 의 outcome, 또는 pending/열림.
func (cy cycleView) status() string {
	last := ""
	for _, n := range cy.steps {
		switch {
		// 종결 스텝 모델(2026-07-24): success/fail/pending 은 독립 kind.
		case n.kind == "success":
			last = "success"
		case n.kind == "fail":
			if last != "success" {
				last = "dead"
			}
		case n.kind == "pending":
			if last != "success" {
				last = "pending"
			}
		// 하위호환: 옛 모델(analyze --outcome …).
		case n.kind == "analyze" && n.outcome == "success":
			last = "success"
		case n.kind == "analyze" && (n.outcome == "backtrack" || n.outcome == "fail"):
			if last != "success" {
				last = "dead"
			}
		}
	}
	if last == "" {
		return "open"
	}
	return last
}

// currentBranch — HEAD 가 가리키는 브랜치(현재 작업위치). detached 면 "".
func currentBranch() string {
	out, err := viewerGit("symbolic-ref", "--quiet", "--short", "HEAD")
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

// headChainCycle — HEAD 커밋의 Gil-Chain/Gil-Cycle 트레일러(팁이 스텝이 아닐 때 현재 사이클).
func headChainCycle() (string, string) {
	const fs = "\x1f"
	out, err := viewerGit("log", "-1", "HEAD",
		"--format=%(trailers:key=Gil-Chain,valueonly)"+fs+"%(trailers:key=Gil-Cycle,valueonly)")
	if err != nil {
		return "", ""
	}
	ch, cy, _ := strings.Cut(strings.TrimSpace(string(out)), fs)
	return strings.TrimSpace(ch), strings.TrimSpace(cy)
}

func buildGraph() graphView {
	nodes := viewerCollectNodes()
	tips := tipSHAs()
	posBySHA := map[string]string{}
	for _, n := range nodes {
		posBySHA[n.full] = posKey(n)
	}
	// 현재위치 = HEAD 가 가리키는 브랜치 하나(피드백 3). 모든 브랜치 팁을 현재위치로
	// 표시하면 브랜치가 많을 때 여러 개 떠 혼란. HEAD 브랜치만 "현재위치"로 강조하고,
	// 나머지 브랜치 팁은 그냥 가지 끝일 뿐이다. (여러 에이전트=여러 워킹트리면 각자 HEAD.)
	head := currentBranch()
	here := map[string]string{}   // "chain/cycle/step" → 현재 스텝 위치
	hereCyc := map[string]string{} // "chain/cycle" → HEAD 가 이 사이클에 있음(스텝 팁 아닐 때)
	tipCount := 0
	if sha, ok := tips[head]; ok {
		if p, ok := posBySHA[sha]; ok {
			here[p] = head
			tipCount = 1
		} else {
			// HEAD 팁이 스텝이 아님(close 등) — 그 커밋의 chain/cycle 을 현재 사이클로.
			if ch, cy := headChainCycle(); ch != "" {
				hereCyc[ch+"/"+cy] = head
				tipCount = 1
			}
		}
	}
	chainParent := chainParents()
	chainOrder := []string{}
	seenChain := map[string]bool{}
	byChain := map[string][]viewerNode{}
	for i := len(nodes) - 1; i >= 0; i-- {
		n := nodes[i]
		if !seenChain[n.chain] {
			seenChain[n.chain] = true
			chainOrder = append(chainOrder, n.chain)
		}
		byChain[n.chain] = append(byChain[n.chain], n)
	}
	// 스텝(사이클)이 아직 없는 빈 체인도 그린다 — chain-root 만 있는 새로 발의된 체인이
	// 그래프에서 사라지면 "체인이 열렸다"는 신호가 안 보인다(상현님: chain-close 후 새 체인
	// hackathon-a 를 발의했는데 뷰어에 아무 변화가 없었다). chainParents 가 선언된 모든
	// 체인을 key 로 가지므로 노드 없는 체인을 뒤에 덧붙인다.
	declared := make([]string, 0, len(chainParent))
	for ch := range chainParent {
		declared = append(declared, ch)
	}
	sort.Strings(declared) // 결정적 순서
	for _, ch := range declared {
		if ch != "" && !seenChain[ch] {
			seenChain[ch] = true
			chainOrder = append(chainOrder, ch)
		}
	}
	g := graphView{here: here, hereCyc: hereCyc, parents: chainParent, allNodes: nodes, nodeCount: len(nodes), tipCount: tipCount, work: workingStatus(), anchor: workAnchor(), interviews: pendingInterviews(), references: resolvedInterviews(), prunes: pendingPrunes()}
	for _, ch := range chainOrder {
		cv := chainView{name: ch}
		cycOrder := []string{}
		seenCyc := map[string]bool{}
		byCyc := map[string][]viewerNode{}
		for _, n := range byChain[ch] {
			if !seenCyc[n.cycle] {
				seenCyc[n.cycle] = true
				cycOrder = append(cycOrder, n.cycle)
			}
			byCyc[n.cycle] = append(byCyc[n.cycle], n)
		}
		for _, cy := range cycOrder {
			steps := byCyc[cy]
			sort.SliceStable(steps, func(i, j int) bool { return stepNum(steps[i].step) < stepNum(steps[j].step) })
			cv.cycles = append(cv.cycles, cycleView{name: cy, steps: steps})
		}
		g.chains = append(g.chains, cv)
	}
	return g
}

// cmdViewer — gil viewer <serve|build|text> 디스패치. gil main.go 의 case "viewer" 에서 불린다.
// 뷰어는 격리 유지를 위해 gil flags 대신 자체 수동 파서를 쓴다(의존성 0).
func cmdViewer(args []string) {
	sub := ""
	out := ""
	port := "8790"
	rest := args
	if len(rest) > 0 && !strings.HasPrefix(rest[0], "-") {
		sub = rest[0]
		rest = rest[1:]
	}
	for i := 0; i < len(rest); i++ {
		switch rest[i] {
		case "--repo":
			if i+1 < len(rest) {
				viewerRepoDir = rest[i+1]
				i++
			}
		case "--port":
			if i+1 < len(rest) {
				port = rest[i+1]
				i++
			}
		case "--out":
			if i+1 < len(rest) {
				out = rest[i+1]
				i++
			}
		// --open: 시스템 브라우저까지 연다. **기본은 조용히 서버만 띄우는 것**이다 — 자동으로
		// 튀어나오는 창은 도움보다 방해였다(이슈 #48). 주소는 stdout 에 그대로 나온다.
		case "--open":
			os.Setenv("GIL_OPEN_BROWSER", "1")
		case "--no-open":
			// 이제 기본이라 아무 일도 안 한다. 이미 쓰인 문서·스크립트 호환용.
		}
	}
	switch sub {
	case "serve":
		serve([]string{"--port", port})
	case "build":
		if out == "" {
			die("사용: gil viewer build --out <파일> [--repo <경로>]")
		}
		runViewerBuild(out)
	case "", "text":
		renderText(buildGraph())
	default:
		die("gil viewer: 알 수 없는 서브명령 \"" + sub + "\" — [serve build text]")
	}
}

// runViewerBuild — 정적 HTML 을 파일 하나로 굳힌다(서버 없이 자기완결). Pages 등 정적 호스팅용.
func runViewerBuild(out string) {
	html := renderHTML(buildGraph(), true)
	if err := os.WriteFile(out, []byte(html), 0644); err != nil {
		die("거부: 정적 HTML 쓰기 실패: " + err.Error())
	}
	println2("viewer build → " + out + " (정적 자기완결 HTML)")
}

func renderText(g graphView) {
	fmt.Println("═══ gil 그래프 뷰어 — 체인 > 사이클 > 스텝 ═══")
	work := "작업 없음(클린)"
	if g.work.dirty {
		work = "✎ 작업중 — " + g.work.summary() + " (미커밋)"
	}
	fmt.Printf("(스텝 노드 %d개, 현재위치 팁 %d개 · ▶=현재위치 · %s)\n\n", g.nodeCount, g.tipCount, work)
	for _, ch := range g.chains {
		fmt.Printf("● 체인 %s\n", ch.name)
		for _, cy := range ch.cycles {
			fmt.Printf("  ◆ 사이클 %s\n", cy.name)
			prevStep := ""
			for _, n := range cy.steps {
				marker := "  "
				if _, ok := g.here[posKey(n)]; ok {
					marker = "▶ "
				}
				line := fmt.Sprintf("    %s%s [%s]", marker, n.step, n.kind)
				// 부모가 직전 스텝이 아니면(=분기·backtrack) 부모를 표기한다 —
				// 죽은 잎(fail)과 조상 define 으로 되돌아간 형제 가지가 드러나게.
				if n.parent != "" && n.parent != "null" && n.parent != prevStep {
					line += " ←" + n.parent
				}
				prevStep = n.step
				if n.outcome != "" {
					line += " =" + n.outcome
				}
				if n.plan != "" {
					line += " ⚙plan:" + n.plan
				}
				if n.planOutcome == "broke" {
					line += " ⚠설계깨짐(" + n.planDiff + ")"
				} else if n.planOutcome == "held" {
					line += " ⚙설계유지"
				}
				if n.verdict != "" {
					line += " ⟹" + n.verdict
					// 소급 반증됨(AIL #1 B): supported 판정이 후속 사이클에 뒤집혔다.
					// 취소선 대신(터미널 폭 안정) ⚠refuted-by 배지로 "흠 없는 success" 착시를 깬다.
					if len(n.refinedBy) > 0 {
						line += " ⤳refined-by " + strings.Join(n.refinedBy, ",")
					}
					if len(n.refutedBy) > 0 {
						line += " ⚠refuted-by " + strings.Join(n.refutedBy, ",")
					}
				}
				if len(n.refines) > 0 {
					line += " ⤳refines " + strings.Join(n.refines, ",")
				}
				if len(n.refutes) > 0 {
					line += " ⟵refutes " + strings.Join(n.refutes, ",")
				}
				if br, ok := g.here[posKey(n)]; ok {
					line += "   ← 현재위치 (" + br + ")"
				}
				fmt.Println(line)
				// 현재위치 스텝 아래에만 미커밋 작업 오버레이 — 마지막 커밋 이후 작업이
				// 살아있음을 보여 "멈춘 듯" 오해를 없앤다(그래프엔 커밋으로 안 박음).
				if _, ok := g.here[posKey(n)]; ok && g.work.dirty {
					fmt.Printf("       └─ ✎ 작업중: %s (미커밋)\n", g.work.summary())
					for _, s := range g.work.sample {
						fmt.Printf("          %s\n", s)
					}
					if g.work.files > len(g.work.sample) {
						fmt.Printf("          … 외 %d개\n", g.work.files-len(g.work.sample))
					}
				}
			}
		}
		fmt.Println()
	}
}

func stepNum(s string) int {
	if len(s) < 2 {
		return 0
	}
	n := 0
	for _, c := range s[1:] {
		if c < '0' || c > '9' {
			return 0
		}
		n = n*10 + int(c-'0')
	}
	return n
}
