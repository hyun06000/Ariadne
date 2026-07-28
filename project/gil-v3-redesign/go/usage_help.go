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
		"gil init [--name <이름>] [--open]\n" +
			"  무에서 gil 세계를 세운다 — 대문(CLAUDE.md) + refs/gil/global + 존재의 방.\n" +
			"  뷰어가 있으면 관전 서버도 함께 띄운다. 이미 세팅됐으면 거부(멱등).",
		"docs/gil/existence.md · docs/gil/index.md",
	},
	"chain": {
		"gil chain <name> --purpose <자연어> [--parallel-with <열린체인>...] [--reference <기준문서|->] [--inherit <전수>]\n" +
			"  새 체인(작업 큰 줄기)을 연다 — git 브랜치 <name> 을 판다. --purpose 필수.\n" +
			"  닫힌 체인 끝에서만(대문/이전 닫힌 체인 이어받음, orphan 아님) — 그래야 '이어받음'이\n" +
			"  사실이 된다. 열린 체인이 있는데 **동시에** 굴리는 트랙이면 --parallel-with <그 체인>\n" +
			"  으로 선언하라(이슈 #54): 선언 없이는 거부하고, 선언하면 계승으로 그리지 않는다.\n" +
			"  --reference: 이 체인의 기준 문서(레퍼런스 트루스, 이슈 #33) — 사람과의 인터뷰로\n" +
			"    문제를 명확히 한 산출물. chain-root 본문에 전문이 담기고, 이후 사이클의 define·\n" +
			"    가설·성패판정이 무엇에 비추어 합당한지의 잣대가 된다. 아직 강제 아님(존재·참조만).",
		"docs/gil/concepts.md · docs/gil/deployment.md",
	},
	"chain-close": {
		"gil chain-close <chain> [--verdict supported] [--retro <회고파일|->] [--seed <시드파일|->]\n" +
			"  체인을 완결로 봉인한다 — 모든 사이클이 닫힌 뒤에만. 사이클 close 와 다르다:\n" +
			"  이건 그 위 국면(배포 순환의 한 단계)을 닫는다. 닫으면 새 체인으로 교훈을 잇는다.\n" +
			"  --retro: 기준(인터뷰로 선 레퍼런스) 대비 달성도 회고. **기준이 있는 체인은 필수**(이슈 #33) —\n" +
			"    열 때 사람에게 '무엇을 기준으로 할 것인가'를 물었으면 닫을 때 '얼마나 합당했나'를 답해야\n" +
			"    생애주기가 닫힌다. 담을 것: 기준 항목별 달성/미달(정직하게), 그렇게 만든 원인,\n" +
			"    **반드시 분기했어야 할 지점**(돌아보면 보이는 갈림길).\n" +
			"  --seed: 다음 체인 인터뷰의 재료(남은 물음·새 물음). 다음 gil chain 이 이걸 건네준다.\n" +
			"    시드는 기준이 아니다 — 기준은 언제나 사람의 답이라 인터뷰를 대신하지 못한다.",
		"docs/gil/deployment.md",
	},
	"open": {
		"gil open <chain>/<cycle> --author <who> --purpose <자연어> (--body B | --body-file F|- | --title T)\n" +
			"           [--parent <cyc>...] [--refutes <c>/<cy>/<step>...] [--refines <c>/<cy>/<step>...]\n" +
			"           [--inherit <전수>]\n" +
			"  새 사이클을 연다(s1 define 자동) — git 브랜치 <chain>-<cycle> 을 판다.\n" +
			"  ⚠ 기준 필수(이슈 #33): 체인을 열면 인터뷰가 먼저다. 사람이 승인한 기준 문서(gil interview\n" +
			"    제출)가 없으면 거부한다 — LLM 이 스스로 기준을 정하지 말고 사람에게 물어라. 인터뷰가\n" +
			"    사람 답 대기(pending)면 답이 올 때까지 못 연다.\n" +
			"  본문 필수: --body/--body-file -(stdin)/--title 중 하나로 s1 define 의 문제 정의를 여는 순간 채운다.\n" +
			"    (빈 채로 열 수 없다 — raw git amend 로 채우던 우회를 문법으로 막는다. AIL #12)\n" +
			"  --parent   이 사이클이 잇는 이전 사이클/체인(닫힌 것이어야).\n" +
			"  --goal     이 사이클이 **무엇이 되면 끝인가**(달성 판정 기준, 이슈 #62). purpose 가 '무엇을\n" +
			"             하려는가'라면 goal 은 '무엇이 되면 됐다고 할 것인가'다. 선언하면 gil close 가\n" +
			"             --goal-met 로 그 목표에 답할 것을 요구한다 — '잎이 다 종결됐다'가 '목표 달성'으로\n" +
			"             조용히 미끄러지지 않게.\n" +
			"  --refutes  이 사이클이 앞서 닫힌 supported verify 를 소급 반증한다(과거 불변, forward 간선). 재판정에 쓴다.\n" +
			"  --refines  앞서 닫힌 verify·analyze 의 *해석*만 정밀화한다(이슈 #42) — 판정(verdict)은 그대로 선다.\n" +
			"             refutes 가 극성 전환이면 refines 는 해석 심화다. \"원인을 더 좁혔다\"에 쓰고,\n" +
			"             판정 자체가 틀렸으면 refutes 를 써라(약한 refutes 로 오용하면 정직화가 무뎌진다).\n" +
			"  --inherit  --parent/--refutes/--refines 간선이 있으면 필수 — 무엇을 물려받거나, 무엇을 뒤집고\n" +
			"             무엇은 계승하나, 앞 해석의 어디까지가 맞았나.",
		"docs/gil/concepts.md · docs/gil/lifecycle.md",
	},
	"step": {
		"gil step <chain>/<cycle> --kind <K> [옵션]\n" +
			"  스텝(커밋 노드) 하나. --kind: define|hypothesis|verify|analyze | success|fail|pending\n" +
			"  --to <define|analyze>  (fail·backtrack 되돌아갈 곳 / hypothesis 형제 가지 뿌리)\n" +
			"    hypothesis 의 뿌리는 조상 define 또는 조상 analyze 다(이슈 #32): 가설 자체가 틀렸으면\n" +
			"    define 으로 완전 회귀, 가설은 맞고 방법만 틀렸으면 그걸 밝힌 analyze 로 — 분석을 버리지 마라.\n" +
			"    형식은 **짧은 스텝 이름**이다 — 예: --to s1 (경로형 <chain>/<cycle>/s1 이나 커밋\n" +
			"    해시도 받아 정규화한다. --falsify-to 도 같다.)\n" +
			"  --title <요약>  --body <본문> | --body-file <경로>(마크다운·이미지, 뷰어 렌더)\n" +
			"    --body-file - 이면 stdin 에서 읽는다 — 임시 .md 파일 없이 heredoc·파이프로 바로 넘겨 잉여 파일을 안 남긴다.\n" +
			"  --merge <산잎 스텝id>...  (한 사이클 안 산 잎들 합류)\n" +
			"  --supersede <스텝id>  같은 kind 앞선 스텝을 이 스텝이 정정(새 커밋으로 덮되 옛 것은 이력 보존).\n" +
			"    (raw amend 로 옛 스텝을 지우지 마라 — 정정은 은폐가 아니라 이력에 남는다. 종결 스텝은 대상 아님. AIL #12)\n" +
			"  --if-supported goal-met|goal-missed  (hypothesis) 이 가설이 supported 면 사이클 목표가 달성인가 실패인가.\n" +
			"    기본 goal-met. 부정적 발견(가설 맞음=목표 막힘)이면 goal-missed — 그땐 verify supported 라도 success 거부(fail/backtrack). AIL #13\n" +
			"  --refines <c>/<cy>/<step>  앞 verify·analyze 의 해석만 정밀화(판정 불변, 이슈 #42). --inherit 필수.\n" +
			"  --at <스텝>    종결(fail|success|pending)을 **그 잎 자리에** 박는다(이슈 #59). HEAD 가 재분기로\n" +
			"                 떠나 두고 온 가지를 닫을 때 — 안 그러면 그 가지는 영구 미종결이고 append-only 라\n" +
			"                 사후 경로가 없다. 대상은 자식 없는 비종결 잎이어야(gil fsck 가 짚어준다).\n" +
			"  ※ 종결(success/fail) 잎 뒤에는 이어 붙지 못한다(이슈 #60) — 잎의 뜻이 사라진다.\n" +
			"     이어가려면 갈래를 내라: --to <조상 define|analyze>. 사이클이 끝났으면 gil close.\n" +
			"  ※ backtrack(hypothesis --to <define>)은 --inherit <전수> 필수 — 죽은 가지의 교훈을 새 가지에 지고 가라. AIL #13\n" +
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
		"gil close <chain>/<cycle> [--verdict supported] [--abandon]\n" +
			"  산 잎(success)이 있는 사이클을 봉인한다. 산 잎 없으면 거부 —\n" +
			"  단 --abandon 을 주면 fail 잎만 있는 '죽은 사이클'도 봉인한다(이슈 #46):\n" +
			"  fail=이 가설의 죽음이지 사이클의 죽음이 아니다. 그 define 을 사람이 막다른\n" +
			"  길로 판단해 포기할 때만 --abandon(정직: 없는 성공을 날조하지 않는다).",
		"docs/gil/lifecycle.md · docs/gil/deployment.md",
	},
	"interview": {
		"gil interview <chain> --ask <질문JSON|->  [--title T]\n" +
			"  이 체인의 기준 문서(레퍼런스 트루스, 이슈 #33)를 사람과의 인터뷰로 만든다. 질문 세트를\n" +
			"  그래프에 심으면 뷰어가 폼(서술 textarea·라디오·체크박스)으로 렌더한다 — 사람이 답하고\n" +
			"  제출하면 reference-<chain>.md 로 저장되고 레퍼런스가 커밋된다(pending→approve 의 거울).\n" +
			"  질문: [{\"q\":\"질문\",\"type\":\"text|radio|checkbox\",\"options\":[\"...\"]}]\n" +
			"  gil interview <chain> --status  — 사람이 제출했나 한 줄로(pending|done, 이슈 #58).\n" +
			"  gil interview <chain> --wait [--timeout <초>]  — 제출될 때까지 기다렸다 기준 문서를 뱉는다.\n" +
			"    (제출은 자동 통지되지 않는다 — '기다려라'는 이 둘로 실행한다. 기준을 대신 쓰지 마라.)\n" +
			"  gil interview <chain> --resolve <파일>  — 뷰어 제출이 호출(사람이 직접 쓸 일은 드묾).",
		"docs/gil/concepts.md",
	},
	"deploy": {
		"gil deploy --at <chain>/<cycle>/<step> --tag <v0.2.0> [--state staged|live] [--promote]\n" +
			"           [--url <릴리스URL>] [--title T] [--body-file -]\n" +
			"  배포(공개) 지점을 그래프의 1급 시민으로. 특정 스텝에 '여기서 세상으로 나갔다' 마커를\n" +
			"  얹는다(Gil-Deploy 트레일러). 추론 노드가 아니라 주석이라 그래프 위상은 불변 —\n" +
			"  뷰어가 대상 노드에 🚀 배포 마커 + 태그 라벨을 렌더한다.\n" +
			"  --state staged  배포 단위는 확정됐으나 **아직 안 올라갔다**(이슈 #56). 조율 대기 구간이\n" +
			"                  구조적으로 길 때 — 안 자르면 계보가 끊기고, 자르면 없는 배포를 주장하게\n" +
			"                  되던 자리다. staged 는 뷰어에 📦 로 그려지고 '배포됨'으로 안 읽힌다.\n" +
			"  --promote       staged 로 찍어둔 것이 실제로 올라갔다. 앞 마커를 고치지 않고 새 마커로\n" +
			"                  승격을 남긴다(append-only) — 언제 준비됐고 언제 올라갔나가 둘 다 남는다.\n" +
			"  (기본은 --state live 라 옛 사용법은 그대로다.) 배포는 되돌리기 어려운\n" +
			"  의도적 외부 행위라 '언제 왜 배포했나'를 배포 시점에 남긴다(자동 tag 감지 대신 명시).",
		"docs/gil/deployment.md",
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
		"gil migrate --from <v2-ref> [--room <room>] [--exclude <경로조각>]... [--prefix <접두>] [--dry-run]\n" +
			"  v2(폴더·cycle.yaml) 이력을 현재 브랜치 위에 v3 커밋 그래프로 이주한다.\n" +
			"  먼저 v2 루트에서 이주 브랜치를 파고(git checkout -b) 실행하라. --dry-run 으로 먼저 확인.\n" +
			"  --prefix: 이주 브랜치에 접두(예 v3-)를 붙여 기존 브랜치와 충돌 회피. 충돌 시 아무것도\n" +
			"  만들지 않고 거부(원자성) — --prefix 로 다시 돌려라.\n" +
			"  5단계 압축(hypothesis+design→define, verification→verify, analysis+report→종결),\n" +
			"  verdict→종결 kind: supported/success→success, rejected→fail, **그 밖의 전부**\n" +
			"  (partial·inconclusive·verdict 없음)→pending. 없는 성공을 날조하지 않는다(이슈 #50) —\n" +
			"  결론이 아닌 것을 산 잎으로 접으면 이주된 이력이 원본보다 낙관적인 거짓말이 된다.\n" +
			"  원 verdict 는 Gil-V2-Verdict 트레일러에 무손실 보존된다(정책이 바뀌어도 복구 가능).\n" +
			"  --exclude <경로조각>: 그 조각이 경로에 든 사이클을 뺀다(여러 번 가능) — 동결해 둔\n" +
			"    옛 체인(legacy/archived-chains/…)처럼 v2 fsck 는 안 세는데 migrate 는 끌어오던 것.\n" +
			"  --dry-run 이 '어디서 몇 개를 가져왔는지'·'무엇을 제외했는지'·'사람 판단 대기'를\n" +
			"    모두 먼저 보여준다. [migrate] 표식.",
		"docs/gil/lifecycle.md · docs/gil/concepts.md",
	},
	"mcp": {
		"gil mcp serve [--repo <경로>]   gil 을 stdio MCP 서버로 연다\n" +
			"  --repo 는 보통 필요 없다 — 호스트가 알려주는 프로젝트 루트(CLAUDE_PROJECT_DIR)를 따라가므로\n" +
			"  등록은 한 번, 폴더는 사람이 여는 대로 따라붙는다. 한 폴더에 고정할 때만 --repo 를 쓴다.\n" +
			"\nClaude Desktop 같은 MCP 호스트가 gil 명령을 툴(gil_chain·gil_open·gil_step…)로 직접\n" +
			"부른다. 인터뷰(gil_interview)는 호스트의 네이티브 폼(Elicitation)으로 사람에게 그 자리에서\n" +
			"묻고 답을 받아 기준 문서를 확정한다 — 뷰어 폼·localhost 링크를 거치지 않아 대기가 하나뿐이다.\n" +
			"그래프 관전은 MCP Apps(SEP-1865)로 호스트 안 iframe 에 뜬다 — gil_graph 툴이\n" +
			"ui://gil/graph 리소스를 가리키므로 localhost 주소·포트 충돌·브라우저가 필요 없다.\n" +
			"기존 CLI 는 그대로다(터미널·다른 에이전트용). 호스트 설정 예:\n" +
			"  { \"mcpServers\": { \"gil\": { \"command\": \"gil\", \"args\": [\"mcp\", \"serve\", \"--repo\", \"/경로/내레포\"] } } }",
		"docs/gil/human-in-the-loop.md",
	},
	"viewer": {
		"gil viewer serve [--repo <경로>] [--port <포트>] [--open]   관전 서버(자동 새로고침)\n" +
			"gil viewer build --out <파일> [--repo <경로>]     정적 자기완결 HTML 1회 출력(Pages 등)\n" +
			"gil viewer [text] [--repo <경로>]                텍스트 트리 1회 출력\n" +
			"  사고 그래프(체인>사이클>스텝)를 읽어 그린다. gil init 이 serve 를 자동 기동한다.\n" +
			"  build 는 서버 없이 도는 정적 HTML(스텝 본문 인라인·폴링 없음) — 정적 호스팅용.\n" +
			"  **브라우저는 기본으로 안 연다** — 조용히 서버만 띄우고 주소를 출력한다(이슈 #48).\n" +
			"    자동으로 튀어나오는 창은 도움보다 방해였다: 에이전트가 인앱 패널에 띄우려는데 밖에\n" +
			"    창이 하나 더 뜨고, 반복 실행마다 브라우저가 쌓인다. 시스템 브라우저까지 열려면\n" +
			"    --open 을 명시하라(gil init 도 같다). --no-open 은 기본이 된 지금 no-op 이다.",
		"docs/gil/reports.md",
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
