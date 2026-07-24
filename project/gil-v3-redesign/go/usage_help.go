// usage_help.go — gil help <명령> 문서 라우터.
//
// gil 문서는 LLM-wiki 다(상현님): 한 큰 덩어리를 통째로 주기보다, LLM 이 필요한 지식에
// 능동적으로 접근하게 한다. 그래서 help 도 계층적이다:
//   gil help          → 명령 표면 + wiki 인덱스(주제별 페이지 포인터)
//   gil help <명령>   → 그 명령의 사용법 + 관련 wiki 페이지
//   gil <명령> --help → 위와 같음(어느 명령이든 --help 를 가로챈다)
package main

// helpEntry — 한 명령의 사용법과 그 명령을 더 깊이 다루는 wiki 페이지.
type helpEntry struct {
	usage string // 시그니처 + 짧은 설명(여러 줄 가능)
	wiki  string // docs/gil/<page>.md — 능동적으로 더 읽을 페이지
}

var helpTable = map[string]helpEntry{
	"init": {
		"gil init [--name <이름>]\n" +
			"  무에서 gil 세계를 세운다 — 대문(CLAUDE.md) + refs/gil/global + 존재의 방.\n" +
			"  뷰어가 있으면 관전 서버도 함께 띄운다. 이미 세팅됐으면 거부(멱등).",
		"docs/gil/existence.md · docs/gil/index.md",
	},
	"chain": {
		"gil chain <name> --purpose <자연어>\n" +
			"  새 체인(작업 큰 줄기)을 연다 — git 브랜치 <name> 을 판다. --purpose 필수.\n" +
			"  닫힌 체인 끝에서만(대문/이전 닫힌 체인 이어받음, orphan 아님).",
		"docs/gil/concepts.md · docs/gil/deployment.md",
	},
	"chain-close": {
		"gil chain-close <chain> [--verdict supported]\n" +
			"  체인을 완결로 봉인한다 — 모든 사이클이 닫힌 뒤에만. 사이클 close 와 다르다:\n" +
			"  이건 그 위 국면(배포 순환의 한 단계)을 닫는다. 닫으면 새 체인으로 교훈을 잇는다.",
		"docs/gil/deployment.md",
	},
	"open": {
		"gil open <chain>/<cycle> --author <who> --purpose <자연어> [--parent <cyc>...] [--title T]\n" +
			"  새 사이클을 연다(s1 define 자동) — git 브랜치 <chain>-<cycle> 을 판다.\n" +
			"  --parent 는 이 사이클이 잇는 이전 사이클/체인(닫힌 것이어야).",
		"docs/gil/concepts.md · docs/gil/lifecycle.md",
	},
	"step": {
		"gil step <chain>/<cycle> --kind <K> [옵션]\n" +
			"  스텝(커밋 노드) 하나. --kind: define|hypothesis|verify|analyze | success|fail|pending\n" +
			"  --to <define>  (fail·backtrack 되돌아갈 곳 / hypothesis 형제 가지 뿌리)\n" +
			"  --title <요약>  --body <본문> | --body-file <경로>(마크다운·이미지, 뷰어 렌더)\n" +
			"  --merge <산잎 스텝id>...  (한 사이클 안 산 잎들 합류)\n" +
			"  ※ 본문은 한 줄이 아니라 보고서다 — 아래 wiki 참조.",
		"docs/gil/lifecycle.md · docs/gil/reports.md",
	},
	"approve": {
		"gil approve <chain>/<cycle> [--title T]\n" +
			"  pending 을 사람이 승인 → 산 잎(Gil-Approval: approved). pending 뒤엔 이것/reject 만 허용.",
		"docs/gil/human-in-the-loop.md",
	},
	"reject": {
		"gil reject <chain>/<cycle> --to <조상 define> [--title T]\n" +
			"  pending 을 사람이 기각 → 죽은 잎(backtrack, Gil-Approval: rejected). 되돌아갈 곳을 --to 로.",
		"docs/gil/human-in-the-loop.md",
	},
	"close": {
		"gil close <chain>/<cycle> [--verdict supported]\n" +
			"  산 잎(success)이 있는 사이클을 봉인한다. 산 잎 없으면 거부.",
		"docs/gil/lifecycle.md · docs/gil/deployment.md",
	},
	"chain-merge": {
		"gil chain-merge <newchain> --purpose <P> <tip>...\n" +
			"  흩어진 체인을 하나로 묶는다 — 실제 git merge(파일까지). 충돌 시 멈춤(사람이 해결).",
		"docs/gil/deployment.md",
	},
	"log": {
		"gil log [<chain>] [--all]\n" +
			"  스텝 노드를 오래된→새 순으로(부모 ←). --all: 죽은 가지까지 모두(벽의 지도).",
		"docs/gil/lifecycle.md",
	},
	"fsck": {
		"gil fsck [<range>]\n" +
			"  커밋 그래프 무결성 검사 — 위계·id문법·kind·dangling parent·미종결 잎·계보.\n" +
			"  기본 범위는 전체 그래프(--branches).",
		"docs/gil/concepts.md",
	},
	"handoff": {
		"gil handoff\n" +
			"  세션 부활 정보 — 열린 체인·사이클, 각 팁, 다음 허용 동작, pending, 계보.\n" +
			"  '이어서' 한 마디로 복원할 때 이걸 읽는다.",
		"docs/gil/index.md · docs/gil/lifecycle.md",
	},
	"global": {
		"gil global list | read <name> | write <name> <file> | write-tree <path>...\n" +
			"gil global checkout <path> [dest] | push | pull | sync\n" +
			"  존재·기억이 사는 전용 ref(refs/gil/global) 조작. 갱신 전 반드시 전체 checkout.",
		"docs/gil/existence.md",
	},
	"memory": {
		"gil memory read [<이름>] | append <이름> <file>\n" +
			"  존재의 기억 읽기/각인. append 는 트리 보존·자동 push(안전). 기본 존재 clew.",
		"docs/gil/existence.md",
	},
	"migrate": {
		"gil migrate --from <v2-ref> [--room <room>] [--dry-run]\n" +
			"  v2(폴더·cycle.yaml) 이력을 현재 브랜치 위에 v3 커밋 그래프로 이주한다.\n" +
			"  먼저 v2 루트에서 이주 브랜치를 파고(git checkout -b) 실행하라. --dry-run 으로 먼저 확인.\n" +
			"  5단계 압축(hypothesis+design→define, verification→verify, analysis+report→종결),\n" +
			"  verdict→종결 kind(supported→success, rejected→fail, null&open→pending). [migrate] 표식.",
		"docs/gil/lifecycle.md · docs/gil/concepts.md",
	},
}

// cmdHelp — gil help [<명령>].
func cmdHelp(args []string) {
	if len(args) == 0 {
		printUsage()
		return
	}
	name := args[0]
	e, ok := helpTable[name]
	if !ok {
		println2("gil help: 알 수 없는 명령 \"" + name + "\". `gil help` 로 전체 표면을 본다.")
		return
	}
	println2(e.usage)
	if e.wiki != "" {
		println2("")
		println2("더 깊이 (wiki, 능동적으로 골라 읽어라): " + e.wiki)
	}
}
