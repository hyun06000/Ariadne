// usage_help.go — gil help <명령> 문서 라우터.
//
// gil 문서는 LLM-wiki 다(상현님): 한 큰 덩어리를 통째로 주기보다, LLM 이 필요한 지식에
// 능동적으로 접근하게 한다. 그래서 help 도 계층적이다:
//
//	gil help          → 명령 표면 + wiki 인덱스(주제별 페이지 포인터)
//	gil help <명령>   → 그 명령의 사용법 + 관련 wiki 페이지
//	gil <명령> --help → 위와 같음(어느 명령이든 --help 를 가로챈다)
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
		"gil chain <name> --from-intake <슬러그> --purpose-from <n> --criterion-from <m>   (권장)\n" +
			"gil chain <name> --purpose <자연어> --reference <기준문서|-> --criterion <판정문장>\n" +
			"          [--parallel-with <열린체인>...] [--inherit <전수>] [--require-dataset] [--require-subject]\n" +
			"  새 체인(작업 큰 줄기)을 연다 — git 브랜치 <name> 을 판다.\n" +
			"  **목적과 기준은 쌍으로만 태어난다**(상현님): 기준 문서 없이는 체인이 만들어지지 않는다.\n" +
			"    옛 규칙은 기준 없는 체인을 만들게 두고 *사이클을 열 때* 막았고, 그래서 실사용은 늘\n" +
			"    '체인부터 만들고 → 거부당하고 → 그제서야 인터뷰'로 굳었다. 막을 자리는 체인의 탄생이다.\n" +
			"    ▸ 권장: gil intake 로 **체인보다 먼저** 사람에게 묻고 그 답을 인용한다(이슈 #90).\n" +
			"    ▸ 사람이 기준 문서를 이미 줬으면 --reference(전문) + --criterion(판정 문장) 을 함께.\n" +
			"  닫힌 체인 끝에서만(대문/이전 닫힌 체인 이어받음, orphan 아님) — 그래야 '이어받음'이\n" +
			"  사실이 된다. 열린 체인이 있는데 **동시에** 굴리는 트랙이면 --parallel-with <그 체인>\n" +
			"  으로 선언하라(이슈 #54): 선언 없이는 거부하고, 선언하면 계승으로 그리지 않는다.\n" +
			"  --reference: 이 체인의 기준 문서 전문(레퍼런스 트루스, 이슈 #33) — chain-root 본문에\n" +
			"    담기고, 이후 사이클의 define·가설·성패판정이 무엇에 비추어 합당한지의 잣대가 된다.\n" +
			"  --criterion: 그 문서에서 뽑은 **판정 문장**(무엇이 관측되면 풀린 것인가). chain-close 가\n" +
			"    이 문장을 되읽어 \"여기에 답하라\"고 요구한다 — 전문만 있고 판정 문장이 없으면 아무도\n" +
			"    그 문서를 잣대로 쓰지 않는다(형해화).\n" +
			"  --require-dataset / --require-subject: 이 체인의 사이클은 열 때 측정 좌표를 선언해야 한다\n" +
			"    (이슈 #79·#81). 측정 체인이 스스로 합격선을 올리는 문법 — 선언 없으면 open 이 거부된다.",
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
		"gil open <chain>/<cycle> --author <who> (--purpose <자연어> | --from-plan <n>) (--body B | --body-file F|- | --title T)\n" +
			"  --from-plan <n>  개시 인터뷰에서 **사람이 나눈 n번째 문제**를 이 사이클의 목적으로\n" +
			"    인용한다(이슈 #90 후속) — 작은 문제들로 사이클을 정복하는 자리다. 창작이 아니라\n" +
			"    인용이라 --purpose 와 함께 못 선다. 범위를 벗어나면 고를 수 있는 목록을 그 자리에\n" +
			"    보여준다. (분할은 gil chain … --cycles-from <질문번호> 로 체인에 각인돼 있어야 한다.)\n" +
			"           [--dataset <이름>@sha256:<hex>]... [--dataset-note <메모>] [--subject <이름>@rev:<체크포인트>#<옵션>]...\n" +
			"           [--parent <cyc>...] [--refutes <c>/<cy>/<step>...] [--refines <c>/<cy>/<step>...]\n" +
			"           [--inherit <전수>]\n" +
			"  새 사이클을 연다(s1 define 자동) — git 브랜치 <chain>-<cycle> 을 판다.\n" +
			"  ⚠ 기준 필수(이슈 #33): 기준은 이제 **체인이 태어날 때** 갖춰진다(gil chain 참조).\n" +
			"    그 체인에 새 인터뷰가 사람 답 대기(pending)면 답이 올 때까지 못 연다.\n" +
			"  ⚠ --fits 필수(상현님): 여는 자리에서 **체인의 목적을 다시 읽히고** 이 사이클이 거기\n" +
			"    속하는지 답하게 한다. 뿌린 글은 읽히지 않아도 통과되지만, 답을 문법으로 요구하면\n" +
			"    최소한 한 번은 비추어 본다. 남는 문장이라 나중에 '이 체인에 왜 이게 있나'를 되짚을 수 있다.\n" +
			"      --fits <이 사이클이 체인 목적에 어떻게 기여하는가>\n" +
			"      --misfit <왜 여기가 아닌가>   ← 아니라고 판단했으면 **열지 않는다.** 그 판단을\n" +
			"        존재의 기억(existence/<author>/memory.md)에 남기고 멈춘다 — 문제는 사라지지 않고\n" +
			"        제 자리를 기다린다. 그런 뒤 그 문제의 주인이 될 체인을 intake 부터 연다.\n" +
			"        (체인은 아무 사이클이나 담는 바구니가 아니라 목적 하나에서 뻗은 나무다.)\n" +
			"  본문 필수: --body/--body-file -(stdin)/--title 중 하나로 s1 define 의 문제 정의를 여는 순간 채운다.\n" +
			"    (빈 채로 열 수 없다 — raw git amend 로 채우던 우회를 문법으로 막는다. AIL #12)\n" +
			"  --dataset  이 측정이 **어디서** 서는가 — 평가셋 파일과 그 sha256(이슈 #79). 이름만으로는\n" +
			"             결정되지 않는다: 행수·빈행·합계까지 같고 sha 만 다른 평가셋이 실제로 8개 있었고,\n" +
			"             그걸 몰라 체인 하나가 통째로 무효가 됐다. 축이 둘이면 두 번 준다.\n" +
			"  --subject  이 측정이 **무엇을** 재는가 — 모델·체크포인트·어댑터·양자화(이슈 #81). 서빙\n" +
			"             별칭만 적으면 '무엇의 점수인지 모르는 점수'가 된다. 권장 <이름>@rev:<커밋>#<옵션>.\n" +
			"  --parent   이 사이클이 잇는 이전 사이클/체인(닫힌 것이어야).\n" +
			"  --goal     이 사이클이 **무엇이 되면 끝인가**(달성 판정 기준, 이슈 #62). purpose 가 '무엇을\n" +
			"             하려는가'라면 goal 은 '무엇이 되면 됐다고 할 것인가'다. 선언하면 gil close 가\n" +
			"             --goal-met 로 그 목표에 답할 것을 요구한다 — '잎이 다 종결됐다'가 '목표 달성'으로\n" +
			"             조용히 미끄러지지 않게.\n" +
			"  --refutes  이 사이클이 앞서 닫힌 supported verify 를 소급 반증한다(과거 불변, forward 간선). 재판정에 쓴다.\n" +
			"  --advances hypothesis 필수 — 이 가설이 **체인 전체의 목적**에 어떻게·얼마나 다가서나.\n" +
			"             사이클 안의 성패만 보면 목적이 사라진다. 여기 선언한 것을 종결에서 회고한다.\n" +
			"  --toward / --next-design  success·fail 필수 — 종결은 회고다. 그래서 목적에 얼마나\n" +
			"             가까워졌나, 그리고 목적을 이루기 위한 **다음 설계**는 무엇인가. 다음 세대\n" +
			"             (다음 가지·다음 사이클)가 물려받는 것이 이 두 줄이다. 누적본: gil context.\n" +
			"  --plan     hypothesis 필수 — 가설을 세우기 **전에** 고정하는 설계(이슈 #76). 추정이 아니라\n" +
			"             결정이다: '몇 개일지 추정'이 아니라 '몇 개로 만들지 결정'. 규모 예측이 빗나간\n" +
			"             실측 세 번은 전부 신규 실행경로를 적게 셌기 때문이었고, 맞은 한 번의 차이는\n" +
			"             구현 전에 읽기 경로를 세어 공용 함수 하나로 묶기로 **정한** 것뿐이었다.\n" +
			"             세는 법을 고치는 길은 세는 정확도가 아니라 세어야 할 것을 설계로 줄이는 것이다.\n" +
			"  --plan-held/--plan-broke <무엇이 달랐나>  verify 필수(고정한 설계가 있을 때) — 그 설계가\n" +
			"             유지됐나. 깨진 설계는 실패가 아니라 신호다: 되돌아갈 자리를 가장 잘 가리킨다.\n" +
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
			"  verify 는 **가설이 심은 반증조건에 답해야 한다**(규칙 17):\n" +
			"        --falsify-met <관측>    그 조건이 관측됐다 → 가설이 틀렸다(verdict 는 refuted)\n" +
			"        --falsify-unmet <관측>  관측되지 않았다\n" +
			"    충족됐는데 --verdict supported 는 **거부**된다 — 판정 축을 바꾸는 것이다.\n" +
			"    반대로 unmet + refuted 는 막지 않는다: '내가 정한 조건이 아닌 이유로 틀렸다'는 오류가\n" +
			"    아니라 정보다(조건이 잘못 잡혔다는 뜻 — 다음 가설의 --falsify 를 고쳐라).\n" +
			"  --to  kind 에 따라 뜻이 다르다(이슈 #59①·#76). 둘 다 조상 define 또는 analyze 를 받는다:\n" +
			"        hypothesis      → **형제 가지의 뿌리**. 부모를 바꾼다(거기서 새로 갈라진다).\n" +
			"        fail·backtrack  → **되돌아갈 곳의 기록**. 부모는 안 바뀐다(자리는 --at 이 고른다).\n" +
			"        문제 정의가 틀렸으면 define, 문제 정의는 옳고 거기서 내려진 결정이 틀렸으면 그 analyze.\n" +
			"    hypothesis 의 뿌리는 조상 define 또는 조상 analyze 다(이슈 #32): 가설 자체가 틀렸으면\n" +
			"    define 으로 완전 회귀, 가설은 맞고 방법만 틀렸으면 그걸 밝힌 analyze 로 — 분석을 버리지 마라.\n" +
			"    형식은 **짧은 스텝 이름**이다 — 예: --to s1 (경로형 <chain>/<cycle>/s1 이나 커밋\n" +
			"    해시도 받아 정규화한다. --falsify-to 도 같다.)\n" +
			"  --finding <결론>  **analyze 필수** — 이 분석이 밝힌 것 한 줄(상현님 실사용).\n" +
			"    결론 없는 분석은 다음 판단의 근거가 되지 못한다: 그 위에 선 재분기는 근거 없이\n" +
			"    되돌아가는 것이고, 그러면 같은 벽을 다시 만난다. 본문은 근거 전문, --finding 은\n" +
			"    거기서 뽑은 결론이다 — **지식 누적이 인용하는 문장이 바로 이것**이다.\n" +
			"  --despite <이유>  벽의 지도와 **다른 자리**에서 갈라질 때 필요(상현님 실사용).\n" +
			"    죽은 잎은 --to 로 되돌아갈 자리를 적는다(벽의 지도). 그런데 다음 재분기가 그 자리를\n" +
			"    무시하고 딴 데서 갈라져도 도구가 몰랐다 — 기록과 행동이 어긋나는데 침묵하면 그\n" +
			"    기록은 이내 빈 칸 채우기가 된다. 지도를 고치는 것도 정당하다: 다만 이유가 남는다.\n" +
			"  --title <요약>  --body <본문> | --body-file <경로>(마크다운·이미지, 뷰어 렌더)\n" +
			"    --body-file - 이면 stdin 에서 읽는다 — 임시 .md 파일 없이 heredoc·파이프로 바로 넘겨 잉여 파일을 안 남긴다.\n" +
			"  --merge <산잎 스텝id>...  (한 사이클 안 산 잎들 합류)\n" +
			"  --supersede <스텝id>  앞선 **같은 kind** 스텝을 이 스텝이 정정한다. --inherit 필수.\n" +
			"    **정정은 분기다** — 새 스텝은 정정 대상의 *부모* 자리에서 새 git 브랜치로 갈라진다.\n" +
			"    그래서 옛 스텝과 그 자손 전부가 손대지 않은 **구버전 가지**로 보존되고(지워지지 않는다),\n" +
			"    팁·fsck·close·뷰어는 새 가지만 따른다(뷰어는 구버전을 흐리게 + ⤳ 표식).\n" +
			"    모든 kind 가 대상이다 — define(문제 정의 다시 쓰기)도, 종결(fail/success/pending)도.\n" +
			"    같은 kind 로만 정정되므로 **판정 뒤집기는 불가능**하다(fail→success 는 정정이 아니라\n" +
			"    backtrack(hypothesis --to)·소급 반증(--refutes) 영역).\n" +
			"    (raw amend 로 옛 스텝을 지우지 마라 — 정정은 은폐가 아니라 이력에 남는다. AIL #12)\n" +
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
			"  pending 을 사람이 승인 → 산 잎(Gil-Approval: approved). pending 뒤엔 이것/reject 만 허용.\n" +
			"  사람이 뷰어에서 눌러도 된다 — 그러면 **다음에 무슨 명령을 부르든** gil 이 맨 앞에\n" +
			"  ⚡ 로 그 판정을 알린다(상현님 실사용: 눌렀는데 에이전트가 몰랐다). 읽는 명령\n" +
			"  (gil context·handoff)이 지나가면 고지는 꺼진다.",
		"docs/gil/human-in-the-loop.md",
	},
	"reject": {
		"gil reject <chain>/<cycle> --to <조상 define|analyze> [--title T]\n" +
			"  pending 을 사람이 기각 → 죽은 잎(backtrack, Gil-Approval: rejected). 되돌아갈 곳을 --to 로.",
		"docs/gil/human-in-the-loop.md",
	},
	"adopt": {
		"gil adopt <chain>/<cycle>/<승자스텝> --reason <왜 이 가지가 이겼나> [--over <진 형제>…]\n" +
			"  경합(--competing)으로 나란히 세운 형제 가설 중 하나를 채택한다(이슈 #106·#107):\n" +
			"    · 진 가지마다 벽(fail)을 남긴다 — 승자를 가리키는 선과 함께(Gil-Lost-To).\n" +
			"      진 가지는 실패가 아니라 **비교의 한쪽**이다 — 대조가 없으면 승자의 수치도 근거가 못 된다.\n" +
			"    · HEAD 를 승자 가지로 옮긴다 — 자산도 거기 있다(손으로 git checkout 해 오지 마라,\n" +
			"      그렇게 옮긴 승계는 그래프에 안 남는다).\n" +
			"  --over 생략 = 같은 경합의 미종결 형제 전부. --reason 은 필수다: 채택은 판단이고,\n" +
			"  근거가 없으면 나중에 아무도 그것이 측정이었는지 취향이었는지 모른다.",
		"docs/gil/parallel.md",
	},
	"close": {
		"gil close <chain>/<cycle> [--verdict supported|partial|rejected] [--abandon]\n" +
			"          [--goal-met | --goal-partial <못 한 것> | --goal-impossible <왜 불가한가>]\n" +
			"  산 잎(success)이 있는 사이클을 봉인한다. 산 잎 없으면 거부 —\n" +
			"  열 때 --goal 을 선언했으면 셋 중 하나로 그 목표에 답해야 한다(이슈 #62·#80):\n" +
			"    --goal-met         다 달성했다.\n" +
			"    --goal-partial     일부만 — 못 한 조각을 인자로 적는다(Gil-Goal-Gap 으로 남는다).\n" +
			"    --goal-impossible  원리적 달성 불가를 **확인**했다. 실패가 아니라 발견이라\n" +
			"                       --abandon 으로 묻지 않는다 — 다음 사이클의 근거가 된다.\n" +
			"  달성과 포기 사이가 비어 있으면 목표를 유리하게 재해석할 압력이 생긴다 —\n" +
			"  어휘가 부족하면 기록이 거짓말한다(#80). --goal-met 과 --verdict partial 은 함께 못 선다.\n" +
			"  단 --abandon 을 주면 fail 잎만 있는 '죽은 사이클'도 봉인한다(이슈 #46):\n" +
			"  fail=이 가설의 죽음이지 사이클의 죽음이 아니다. 그 define 을 사람이 막다른\n" +
			"  길로 판단해 포기할 때만 --abandon(정직: 없는 성공을 날조하지 않는다).",
		"docs/gil/lifecycle.md · docs/gil/deployment.md",
	},
	"intake": {
		"gil intake <슬러그> --ask <질문JSON 문자열|파일|->   (체인을 열기 **전에** 사람에게 묻는다)\n" +
			"  질문 스키마(type 필수: text|radio|checkbox — radio/checkbox 는 options 도):\n" +
			"      [{\"q\":\"무엇을 하려고 하십니까\",\"type\":\"text\"}]\n" +
			"    JSON 문자열을 그대로 줘도 되고(--ask '[...]'), 파일 경로나 - (stdin)도 받는다.\n" +
			"  gil 정문의 순환을 사람 쪽에서 끊는다(이슈 #90). 체인은 --purpose 가 필수인데\n" +
			"  인터뷰는 체인이 있어야 열렸다 — 그래서 에이전트가 목적을 창작하고 사람은 승인만 했다.\n" +
			"  그리고 **어디서 분기할지는 사람의 답을 보고 정해야 하는데**, 분기를 친 뒤에 물으면\n" +
			"  그 답이 갈 곳이 없다. intake 는 체인 없이 열리는 인터뷰다.\n" +
			"  gil intake <슬러그> --status | --wait [--timeout <초>] | --resolve <파일>  (인터뷰와 동일)\n" +
			"  답이 오면 그 답으로 체인을 연다 — 목적은 **인용**된다:\n" +
			"      gil chain <이름> --from-intake <슬러그> --purpose-from <질문번호>\n" +
			"  --from-intake 와 --purpose 는 함께 못 선다: 요약도 정제도 창작이고, 창작하는 순간\n" +
			"  기준 문서는 '사람이 세운 자'가 아니게 된다.\n" +
			"\n" +
			"  **심층 인터뷰** — 차수를 더하면 앞 답은 지워지지 않고 쌓인다. 셋을 낳게 물어라:\n" +
			"    1) 무엇을 풀려는가            → 체인 목적\n" +
			"    2) 무엇이 관측되면 풀린 것인가 → 성패 기준(chain-close 가 이 문장에 답할 것을 요구한다)\n" +
			"    3) 사이클 단위로 나눈다면      → 사이클 분할(작은 문제로 사이클을 정복한다)\n" +
			"  gil intake <슬러그> --ask-root  — **마지막 차수**. 어디서 분기할지를 묻되 질문을 gil 이\n" +
			"    만든다: 후보가 그래프에 실재하는 자리들(닫힌 체인·열린 체인·대문)이라 네 가설 공간이\n" +
			"    아니다. 뿌리를 먼저 박으면 사람의 답이 갈 곳이 없다.\n" +
			"  --status 는 **짧다**(상태 + 인용 번호 목록). 전문까지 보려면 --status --show —\n" +
			"    확인용 한 줄이라 믿고 불렀다가 수십 줄이 쏟아지는 일이 없게(이슈 #94).\n" +
			"  ⚠ **--wait 를 셸 `&` 로 떼어내지 마라**(이슈 #94). 대부분의 호스트에서 그 프로세스는\n" +
			"    추적 밖이라 **끝나도 네 턴이 열리지 않는다** — 답은 도착했는데 아무도 못 읽는다.\n" +
			"    네 런타임의 백그라운드 실행 기능을 쓰거나, MCP 라면 gil_interview_wait 툴을 써라\n" +
			"    (툴 호출의 완료는 호스트가 추적한다 — 이 구멍이 아예 없다).\n" +
			"  --status 가 답에 **누적 번호**를 매겨 보여준다 — 차수마다 1부터 다시 시작하므로 그\n" +
			"    번호로만 지목할 수 있다. 그 번호를 아래 셋에 쓴다:\n" +
			"      gil chain <이름> --from-intake <슬러그> --purpose-from <n> --criterion-from <m> [--cycles-from <k>]\n" +
			"    --criterion-from 필수: 목적만 있고 기준이 없으면 '됐다'가 다시 자기확신이 된다.\n" +
			"    --cycles-from 선택: 그 분할에서 사이클을 연다 → gil open <c>/<cy> --from-plan <n>",
		"docs/gil/concepts.md",
	},
	"interview": {
		"gil interview <chain> --ask <질문JSON|->  [--title T]\n" +
			"  이 체인의 기준 문서(레퍼런스 트루스, 이슈 #33)를 사람과의 인터뷰로 만든다. 질문 세트를\n" +
			"  그래프에 심으면 뷰어가 폼(서술 textarea·라디오·체크박스)으로 렌더한다 — 사람이 답하고\n" +
			"  제출하면 reference-<chain>.md 로 저장되고 레퍼런스가 커밋된다(pending→approve 의 거울).\n" +
			"  질문: [{\"q\":\"질문\",\"type\":\"text|radio|checkbox\",\"options\":[\"...\"]}]\n" +
			"  gil interview <chain> --status  — 사람이 제출했나 짧게(pending|done + 인용 번호).\n" +
			"    전문까지 보려면 --status --show (기본을 짧게 둔 이유: 확인용이라 믿고 불렀다가\n" +
			"    수십 줄이 쏟아지면 컨텍스트를 크게 먹는다 — 이슈 #94).\n" +
			"  gil interview <chain> --wait [--timeout <초>] [--then <명령>]  — 제출될 때까지 기다렸다\n" +
			"    기준 문서를 뱉는다. --then 은 제출되는 순간 그 명령을 실행한다(호스트 훅, 이슈 #82).\n" +
			"  ▸ 대화형 세션이면 --wait 를 **백그라운드**로 돌려라 — 말하는 것과 기다리는 것을 동시에 한다.\n" +
			"    ⚠ 단, **호스트가 추적하는 백그라운드 실행**이어야 한다(이슈 #94). 셸에서 `&` 로\n" +
			"      떼어내면 대부분의 호스트에서 그 프로세스는 추적 밖이라 **끝나도 네 턴이 열리지\n" +
			"      않는다** — 답은 도착했고 --wait 도 정상 해소됐는데 아무도 그 출력을 못 읽는다\n" +
			"      (실사용에서 네 번 반복됐다: #58 → #77 → #82 → #94).\n" +
			"      · 네 런타임에 백그라운드 실행 기능이 있으면 그것으로:\n" +
			"          gil interview <chain> --wait --timeout 3600 > /tmp/gil-ref.md 2>&1\n" +
			"      · MCP 호스트면 gil_interview_wait 툴을 써라 — 툴 호출의 완료는 호스트가\n" +
			"        스스로 추적하므로 이 구멍이 아예 없다.\n" +
			"    '다음 턴의 첫 명령으로 --status' 는 차선이다 — 그 다음 턴은 사람이 말을 걸어야 존재한다(#82).\n" +
			"    (제출은 자동 통지되지 않는다 — '기다려라'는 이 셋으로 실행한다. 기준을 대신 쓰지 마라.)\n" +
			"  gil interview <chain> --resolve <파일>  — 뷰어 제출이 호출(사람이 직접 쓸 일은 드묾).",
		"docs/gil/concepts.md",
	},
	"drift": {
		"gil drift [<chain>]\n" +
			"  gil 그래프와 git 그래프가 **다른 이야기를 하는 자리**를 짚는다(읽기 전용). gil 이 기준이다.\n" +
			"  종류: stacked(git 이 보는 부모 ≠ gil 이 인정한 계승) · orphan-root(대문 계보 밖 뿌리) ·\n" +
			"        ref-missing(gil 은 아는데 git 브랜치가 없다) · stray-branch(gil 이 모르는 브랜치) · retired.\n" +
			"  정리 단계: gil drift → gil reconcile(흡수·무손실) → gil chain-retire(폐기·가역) → gil prune(삭제·비가역).",
		"docs/gil/concepts.md",
	},
	"reconcile": {
		"gil reconcile <chain> --as orphan|parallel [--with <체인>] --reason <왜>\n" +
			"gil reconcile <chain> --restore-ref\n" +
			"  설명 가능한 괴리를 **선언으로 흡수**한다. 그래프는 바뀌지 않는다 — 바뀌는 건 읽는 법이다.\n" +
			"  orphan  = 의도된 조상 0(SPEC 의 orphan 실작업 체인). parallel = 얹혔지만 계승이 아니다.\n" +
			"  --restore-ref = gil 은 아는데 사라진 git 브랜치를 되살린다(gil 이 기준이니 git 을 맞춘다).\n" +
			"  괴리는 사라지지 않는다. 사라지는 것은 위반이다 — 역사는 그대로 남는다.",
		"docs/gil/concepts.md",
	},
	"chain-retire": {
		"gil chain-retire <chain> --reason <왜>   |   gil chain-unretire <chain>\n" +
			"  폐기를 커밋으로 선언하고 브랜치를 refs/gil/retired/ 로 옮긴다. **객체는 하나도 안 지운다** —\n" +
			"  기본 뷰에서 접힐 뿐이고 unretire 로 되돌아온다.\n" +
			"  **위반 없는 체인은 여기서 끝내라. 위반이 있으면 그건 정리가 아니라 은닉이다**(이슈 #92):\n" +
			"    · --dry-run 으로 먼저 봐라 — ref 수 · 사이클/스텝 수 · **함께 접히는 fsck 위반 수**.\n" +
			"    · 위반을 함께 접으려면 --confirm <chain> 이 필요하다(이름을 직접 타이핑하는 것이 그 게이트).\n" +
			"    · 접어도 위반은 안 사라진다 — gil fsck 가 집계로 한 줄, gil fsck --all 이 전부를 보고한다.\n" +
			"  되돌릴 수 있다는 것이 게이트를 면제하지 않는다 — **되돌릴 수 있는 것과 되돌릴 필요를\n" +
			"  알아차릴 수 있는 것은 다르다.**",
		"docs/gil/concepts.md",
	},
	"prune": {
		"gil prune <chain>|<chain>/<cycle>/<step> --dry-run\n" +
			"gil prune <대상> --request --reason <왜>              (사람 승인 요청 — 뷰어에 카드가 뜬다)\n" +
			"gil prune <대상> --withdraw --reason <왜>             (요청을 거둔다 — 뷰어 카드가 사라진다)\n" +
			"gil prune-approve <대상>                             (사람의 승인 — 뷰어 버튼과 같은 문)\n" +
			"gil prune <대상> --confirm <대상> --reason <왜>       (승인이 있을 때만 실제 삭제)\n" +
			"  **append-only 는 그래프 안의 규율이지 저장소의 물리 법칙이 아니다.** 스텝을 고치는 것은\n" +
			"  영원히 막지만, '폐기됐다'는 새 사실이라 append 로 표현된다. 삭제는 비가역이라 문(門)이 셋:\n" +
			"    (1) 사람의 승인 커밋(뷰어 카드, 또는 사람이 직접 치는 gil prune-approve) —\n" +
			"        에이전트 혼자 눌러선 안 되는 문이다. 그런데 **뷰어가 유일한 문이면 뷰어의 사고가\n" +
			"        곧 저장소의 마비**였다(이슈 #96: 브라우저 대화상자가 막히자 승인할 길이 없었다).\n" +
			"        문은 둘이되 무게는 같다 — 어느 쪽이든 사람이 한다.\n" +
			"    (2) CLI 확인 문구 — 대상 이름을 그대로 타이핑\n" +
			"    (3) 묘비와 번들 — **묘비 없는 삭제는 없다**. 계보가 '여기 무엇이 있었고 결론은 이랬다'를\n" +
			"        계속 말해야 한다. 그게 없으면 gil 이 지운 자리는 git 이 지운 자리와 같다.\n" +
			"  노드 삭제는 **잎만** 받는다 — 중간 노드를 지우면 후손을 다시 써야 하고, 그건 역사 재작성이다.\n" +
			"  객체 회수(git gc)는 gil 이 하지 않는다 — 되돌릴 수 없는 마지막 한 줄은 사람이 실행한다.\n" +
			"  **요청은 거둘 수 있다**(이슈 #91): --withdraw. 요청을 올린 순간 빠져나올 수 없으면\n" +
			"    그 문은 문이 아니라 덫이다 — 승인도 철회도 못 한 채 카드가 뷰어를 영구히 덮었다.\n" +
			"    철회도 append 다: 요청은 이력에 남고 그 위에 '더 이상 유효하지 않다'가 얹힌다.\n" +
			"    거둔 뒤 다시 올릴 수 있고, 그러면 카드도 다시 뜬다(결말은 시간 축의 마지막 사실이다).\n" +
			"    뷰어 카드에도 [요청 철회] 버튼이 있다 — 아무것도 지우지 않으므로 승인과 같은 무게의\n" +
			"    문을 달지 않는다.",
		"docs/gil/concepts.md",
	},
	"close-vocabulary": {
		"gil close <chain>/<cycle> --answered-in <chain/cycle/step>\n" +
			"gil approve <chain>/<cycle> --by <chain/cycle/step>\n" +
			"gil chain-close <chain> --superseded-by <chain>\n" +
			"  종결의 어휘(이슈 #85). 죽은 잎만 남았다고 다 막다른 길이 아니다 — 그 물음의 답이\n" +
			"  **다른 자리에서 났을 수 있다**. --abandon(막다른 길로 확인)과 구별해 적고, 그래프에\n" +
			"  답으로 가는 선을 남긴다. --by 는 pending 을 사람이 승인하되 무엇을 근거로 닫는지를\n" +
			"  남긴다(사람 승인 원칙은 그대로 — 판단 대상만 '지금 답하라'에서 '이 후속이 답이 맞나'로).\n" +
			"  --superseded-by 는 옛 체인의 결론이 뒤에서 뒤집혔음을 구조로 남긴다 — 읽는 쪽이 제일\n" +
			"  궁금한 건 '어느 결론이 아직 유효한가'인데, 회고 본문에만 있으면 전부 읽어야 안다.",
		"docs/gil/concepts.md",
	},
	"context": {
		"gil context <chain>[/<cycle>]\n" +
			"  이 자리에 **도착한 누적 컨텍스트**를 준다 — 체인 목적·기준에서 시작해 조상 사이클들이\n" +
			"  남긴 전수(--inherit)·설계(--plan)·회고(--toward/--next-design)를 오래된 것부터 쌓아\n" +
			"  보여준다(부모의 부모, 더 먼 조상까지). gil open 은 이 브리핑을 자동으로 읽어 준다 —\n" +
			"  묻지 않아도 도착해야 전파이지, 기록만으로는 전파가 아니다.",
		"docs/gil/concepts.md",
	},
	"deploy": {
		"gil deploy --at <chain>/<cycle>/<step> --tag <v0.2.0> [--state staged|live] [--promote]\n" +
			"           [--target <host:port·환경>] [--url <릴리스URL>] [--title T] [--body-file -]\n" +
			"  배포(공개) 지점을 그래프의 1급 시민으로. 특정 스텝에 '여기서 세상으로 나갔다' 마커를\n" +
			"  얹는다(Gil-Deploy 트레일러). 추론 노드가 아니라 주석이라 그래프 위상은 불변 —\n" +
			"  뷰어가 대상 노드에 🚀 배포 마커 + 태그 라벨을 렌더한다.\n" +
			"  --state staged  배포 단위는 확정됐으나 **아직 안 올라갔다**(이슈 #56). 조율 대기 구간이\n" +
			"                  구조적으로 길 때 — 안 자르면 계보가 끊기고, 자르면 없는 배포를 주장하게\n" +
			"                  되던 자리다. staged 는 뷰어에 📦 로 그려지고 '배포됨'으로 안 읽힌다.\n" +
			"  --target        **어디로** 나갔나 — 서비스 엔드포인트·호스트·환경(이슈 #56).\n" +
			"                  태그가 '무엇을'이면 target 은 '어디로'다. 둘이 있어야 v2.1.0 이 어디에\n" +
			"                  올라갔는지가 그래프에서 읽힌다. gil 은 그 주소에 **닿는지 확인하지 않는다** —\n" +
			"                  기록 도구지 외부를 찌르는 도구가 아니다. 확인은 사람·CI 가 하고 그 결과를\n" +
			"                  --promote 로 선언한다(헬스체크 출력은 --body-file 로 본문에 남겨라).\n" +
			"  --force         **산 잎(success) 없이** 내보낸다. --reason 필수 — 이유는 배포 커밋 본문에\n" +
			"                  남는다(이슈 #108). 기본은 거부다: close 가 집행하는 규칙을 배포도 집행한다.\n" +
			"                  두 자리에서 규칙이 갈리면 느슨한 쪽이 실질 규칙이 되고, 병렬 형제 가지에서는\n" +
			"                  죽은 가지가 더 많은 게 정상이라 잘못 짚기 쉽다. 내보낸 잎은 커밋에\n" +
			"                  Gil-Deployed-Leaf 로 적힌다 — 무엇의 결과물인지 배포 커밋만 봐도 안다.\n" +
			"  --skip-check    층 검사를 건너뛴다. --skip-reason 필수 — 건너뛴 사실이 커밋에 남는다\n" +
			"                  (Gil-Check-Skipped). 안 적으면 이 배포는 확인된 것과 구별되지 않는다.\n" +
			"  --promote       staged 로 찍어둔 것이 실제로 올라갔다. 앞 마커를 고치지 않고 새 마커로\n" +
			"                  승격을 남긴다(append-only) — 언제 준비됐고 언제 올라갔나가 둘 다 남는다.\n" +
			"  (기본은 --state live 라 옛 사용법은 그대로다.) 배포는 되돌리기 어려운\n" +
			"  의도적 외부 행위라 '언제 왜 배포했나'를 배포 시점에 남긴다(자동 tag 감지 대신 명시).",
		"docs/gil/deployment.md",
	},
	"guard": {
		"gil guard [install|uninstall|status]\n" +
			"  **git commit 과 gil step 이 섞이는 것을 막는다**(상현님: 괴리의 주범).\n" +
			"  체인/사이클 가지에 평범한 커밋이 끼면 그 변경은 **어느 스텝의 것도 아니게** 되고,\n" +
			"  그 뒤 gil 이 세는 모든 것(계보·적층·층·뒤처짐)이 실제와 갈린다. git log 는 멀쩡해\n" +
			"  보이므로 조용히 갈린다 — 성실히 일한 세션일수록 더 많이 섞는다.\n" +
			"  두 겹이다(한 겹으로는 원리적으로 부족하다):\n" +
			"    예방 — pre-commit 훅(.gil/hooks). gil init 이 기본으로 건다. 층(main·dev)은 예외다:\n" +
			"           대문 문서·배포 머지는 평범 커밋의 자리다. 충돌 해결 커밋도 통과시킨다.\n" +
			"    탐지 — gil fsck 가 '섞인 기록'을 늘 센다. 훅이 없는 클론에서도, 뚫린 뒤에도 짚는다.\n" +
			"  훅은 **벽이 아니다**: git commit --no-verify 는 언제나 뚫린다(git 의 설계 — 클라이언트\n" +
			"  훅은 강제될 수 없다). 그러니 예방은 미끄러짐을 막고, 판정은 탐지가 한다.\n" +
			"  예외 한 번: GIL_ALLOW_RAW=1 git commit …   (그 사실도 fsck 가 짚는다)\n" +
			"  ※ 새 클론에서는 한 번 더 걸어야 한다 — 훅 파일은 따라가지만 core.hooksPath 설정은\n" +
			"     로컬이다(git 은 클론 시 설정을 실행하지 않는다).",
		"docs/gil/commands.md",
	},
	"merge": {
		"gil merge <합칠 것>... --into <받는 곳> --reason <왜 합치나> [--allow-open]\n" +
			"        [--skip-check --skip-reason <왜 확인 없이 건너나>]\n" +
			"  둘 이상의 조상을 요구하는 모든 합류 — 실제 git merge(파일까지). 충돌 시 멈춤(사람이 해결).\n" +
			"  **두 자리에서 쓴다**(이슈 #103 — 예시가 하나뿐이라 아래쪽만 쓰이고 있었다):\n" +
			"    닫은 사이클을 체인으로: gil merge <chain>/<cycle> --into <chain> --reason <왜>\n" +
			"        → 그 사이클의 **산출물 파일**이 체인 트리에 올라와, 다음 사이클이 이어받는다.\n" +
			"          안 하면 다음 사이클은 그 파일을 못 보고, 결국 트리 복사(git checkout <브랜치> --\n" +
			"          <경로>)로 때우게 된다 — 내용은 옮겨지지만 **합류 간선이 안 남아 승계가 사라진다.**\n" +
			"    끝난 체인을 층으로: gil merge <chain> --into dev --reason <왜>\n" +
			"  완성만 머지 대상이다(SPEC 규칙 5) — 열린 체인은 --allow-open 없이는 거부하고,\n" +
			"  우회하면 그 사실이 머지 커밋 본문에 남는다.\n" +
			"  dev → main 은 머지가 아니라 **배포**다: gil deploy --tag <vX>. 대문으로 가는 통로는 하나다.\n" +
			"  **층은 아래로 흐르지 않는다**(이슈 #115): dev·main 을 체인/사이클로 합치는 것은 거부된다.\n" +
			"  체인이 dev 보다 뒤처져 정본이 트리에 없으면, 끌어오는 것이 아니라 **국면을 넘겨라** —\n" +
			"  chain-close → merge <chain> --into dev → intake → chain --from-intake --ask-root.\n" +
			"  (허용을 열거하기만 하면 없는 항목은 금지가 아니라 미기재로 읽힌다 — 그래서 금지를 적는다.)\n" +
			"  **층 검사**: .gil/checks 에 `dev: <명령>` 이 선언돼 있으면 dev 로 올릴 때 gil 이 직접\n" +
			"  돌리고 종료코드로 판정한다(통과 사실은 Gil-Checked 로 커밋에 남는다). 선언은 대문에서\n" +
			"  읽는다 — 정책은 가지의 사정이 아니다. 선언이 없으면 막지 않되 그 사실을 알린다.",
		"docs/gil/deployment.md",
	},
	"chain-merge": {
		"gil chain-merge <newchain> --purpose <P> <tip>...   (디프리케이트 — gil merge 를 써라)\n" +
			"  흩어진 체인을 하나로 묶어 **새 체인**을 만든다. 합류의 한 가지 모양일 뿐이라\n" +
			"  gil merge 로 넓혔다. 옛 문서·스크립트를 위해 계속 돈다(경고를 내며).",
		"docs/gil/deployment.md",
	},
	"docs": {
		"gil docs install [--force] [--no-gate] [--name <존재이름>]\n" +
			"  온보딩을 이 저장소에 설치한다 — docs/gil/ wiki · llms.txt · 대문(CLAUDE.md)의 진입점 블록.\n" +
			"  복원 경로의 첫 칸(대문)이 비어 있으면 사슬의 나머지가 튼튼해도 거기서 끊긴다(이슈 #73).\n" +
			"  기존 문서는 덮지 않는다(--force 로만 갱신). 대문은 마커 사이만 교체 — 사람이 쓴 나머지는 무접촉.",
		"docs/gil/index.md",
	},
	"goto": {
		"gil goto <chain>/<cycle>[/<step>]\n" +
			"  사고 나무 안에서 자리를 옮긴다 — 인자가 <chain>/<cycle> 이면 그 사이클의 산 잎으로,\n" +
			"  <step> 까지 주면 그 스텝 자리로 HEAD 를 옮긴다. 그래프는 바뀌지 않는다(커밋·브랜치 없음).\n" +
			"  형제 가지가 여럿인 사이클에서 가지 사이를 오가는 유일한 길이다 — 죽은 가지 끝에 서면\n" +
			"  --to·--falsify-to 가 산 가지의 스텝을 '조상이 아니다'로 거부한다(이슈 #67).",
		"docs/gil/lifecycle.md",
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
		"gil handoff [--end]\n" +
			"  세션 부활 정보 — 열린 체인·사이클, 각 팁, 다음 허용 동작, pending, 계보.\n" +
			"  '이어서' 한 마디로 복원할 때 이걸 읽는다.\n" +
			"  --end = 세션정리(떠나는 자리): 기억 매듭에 무엇을 남길지 짚고, 미커밋을 알리고,\n" +
			"          이 저장소를 보는 뷰어를 끈다. 사람에게 전할 문구도 함께 준다.",
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
			"  존재의 기억 읽기/각인. append 는 트리 보존·자동 push(안전).\n" +
			"  read 의 이름을 생략하면 이 저장소에 사는 유일한 존재를 읽는다(여럿이면 골라야 한다).",
		"docs/gil/existence.md",
	},
	"migrate": {
		"gil migrate --from <v2-ref> [--room <r>] [--exclude <조각>]... [--prefix <접두>] [--dry-run]\n" +
			"  v2(폴더·cycle.yaml) 이력 → v3 커밋 그래프. 단계 문서 원문을 실제로 싣는다(이슈 #87).\n" +
			"\n" +
			"gil migrate --adopt-dev [--dry-run]\n" +
			"  이미 옳게 선 dev 를 **표식만 심어 층으로 인정한다** — 다시 그리지 않는다(SHA 불변).\n" +
			"  층은 Gil-Kind: dev-root 표식으로 찾는데 그 표식은 init·--to-dev-layout 만 심는다.\n" +
			"  그래서 손으로 정본 모양을 세운 저장소는 구조는 맞는데 층으로 안 보인다: fsck 의 층\n" +
			"  판정이 꺼지고, merge --into dev 는 되는데 deploy 의 승격만 거부된다(같은 저장소를\n" +
			"  두 명령이 다르게 본다). 계보가 이미 옳으면 다시 그릴 값을 치를 이유가 없다.\n" +
			"  · **남의 브랜치는 삼키지 않는다** — 그 dev 가 이 저장소의 대문 계보에서 갈라진\n" +
			"    것일 때만 인정한다. 아니면 이름을 비켜 주고 --to-dev-layout 으로 새로 그려라.\n" +
			"  · 인정한 뒤 층 검사를 바로 돌려 결과를 보여준다 — 표식만 심고 '됐다'고 하지 않는다.\n" +
			"\n" +
			"gil migrate --to-dev-layout [--prefix <접두, 기본 dev->] [--dry-run] [--allow-dirty-tips]\n" +
			"  이미 v3 인 이 저장소를 **main-dev-chain 으로 다시 그린다**. 각 체인이 dev 에서\n" +
			"  갈라지게 새 브랜치로 옮겨 그린다 — 트리(파일 내용)와 메시지는 그대로, **부모만**\n" +
			"  새 자리로. 그래서 사고의 내용은 한 글자도 안 바뀌고 계보만 참이 된다.\n" +
			"  · 이어받음을 선언한 체인(--from)은 그 부모 체인의 끝에 붙어 계승이 유지된다.\n" +
			"  · 접두는 브랜치만이 아니라 **체인의 이름**을 바꾼다 — 안 그러면 옛 나무와 새 나무가\n" +
			"    같은 체인이 되어 한 사이클의 스텝이 두 벌씩 존재한다.\n" +
			"  · **옛 브랜치는 지우지 않는다.** 다시 그리면 모든 SHA 가 바뀌므로 돌아갈 곳이\n" +
			"    있어야 하고, 무손실인지는 두 나무를 나란히 놓고 세어서 확인한다.\n" +
			"  · **세는 것은 gil 이 한다**(이슈 #95): 끝에 체인별 옛/새 스텝 수를 대조해 보고하고,\n" +
			"    빠진 것은 (사이클, 스텝, kind)로 이름을 부른다. 유실이나 층 위반이 있으면 거부로\n" +
			"    끝난다(종료코드 1) — 사람이 스크립트를 짜야 아는 무손실은 무손실 안내가 아니다.\n" +
			"  · 체인 브랜치 **끝이 gil 커밋이 아니면 옮기기 전에 거부**한다. 그 상태로 옮기면 그\n" +
			"    사이클이 통째로, 아무 경고 없이 빠진다(실측 6개). --allow-dirty-tips 로 강행할 수\n" +
			"    있지만, 그때도 끝의 대조가 무엇이 빠졌는지 이름을 부른다.\n" +
			"  먼저 --dry-run 으로 무엇이 어디로 가는지 본 뒤에 실행하라.\n" +
			"\n" +
			"gil migrate --to-dev-layout --replace --confirm <저장소 이름>\n" +
			"  다시 그린 뒤 **옛 브랜치를 지우고 그 이름을 새 나무에 넘긴다**(이슈 #97). 접두는\n" +
			"  이주 중에만 사는 임시 이름이 되고, 끝나면 체인은 제 이름으로 돌아온다.\n" +
			"  · 무손실 대조와 층 검사를 **먼저** 통과해야 한다 — 하나라도 걸리면 옛 나무는 그대로다.\n" +
			"  · 지우기 전에 번들(--all)을 뜨고 묘비를 남긴다. 번들을 못 뜨면 지우지 않는다.\n" +
			"    묘비는 지운 브랜치와 그 끝(옛 sha → 새 sha)을 적는다 — 없는 게 죄가 아니라 감춘 게 죄다.\n" +
			"  · 문이 둘이다: 번들 강제 + **저장소 이름 타이핑**(--confirm). 비가역의 무게가 다르다 —\n" +
			"    모든 SHA 가 바뀌므로 옛 SHA 로 클론한 사람의 이력과 갈라진다.\n" +
			"  · 끝나면 옛 객체를 정리한다(reflog·gc). 안 그러면 fsck 가 방금 gil 이 정상 절차로\n" +
			"    치운 것을 '스텝 N개 유실 직전'이라 고발한다 — 탐지가 제 도구의 산물을 짚으면\n" +
			"    사람은 그 고지를 통째로 무시하게 된다. 되살릴 곳(번들)이 있을 때만 치운다.\n" +
			"  · 원격이 있으면 강제 push 가 필요하다. gil 은 하지 않는다 — 사람이 판단할 일이다.",
		"docs/gil/commands.md",
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
			"gil viewer open [--repo <경로>]                  **이 저장소의 관전 창을 연다**(없으면 띄워서)\n" +
			"gil viewer shortcut [--out <경로>]               그 한 줄을 부르는 **런처(버튼)** 를 만든다\n" +
			"gil viewer list                                 어느 포트가 어느 저장소를 보는가\n" +
			"gil viewer stop                                 이 저장소를 보는 뷰어를 끈다(세션정리)\n" +
			"  **주인을 본다**: 기본 포트를 남의 저장소가 쥐고 있으면 빈 포트로 비켜서 띄우고,\n" +
			"    이 저장소를 보는 뷰어가 이미 어디엔가 떠 있으면 새로 띄우지 않고 그 주소를 준다.\n" +
			"    포트가 열렸다는 사실은 주인을 말해 주지 않는다 — /whoami 가 말한다.\n" +
			"  사고 그래프(체인>사이클>스텝)를 읽어 그린다. gil init 이 serve 를 자동 기동한다.\n" +
			"  build 는 서버 없이 도는 정적 HTML(스텝 본문 인라인·폴링 없음) — 정적 호스팅용.\n" +
			"  **브라우저는 기본으로 안 연다** — 조용히 서버만 띄우고 주소를 출력한다(이슈 #48).\n" +
			"    자동으로 튀어나오는 창은 도움보다 방해였다: 에이전트가 인앱 패널에 띄우려는데 밖에\n" +
			"    창이 하나 더 뜨고, 반복 실행마다 브라우저가 쌓인다. 시스템 브라우저까지 열려면\n" +
			"    --open 을 명시하라(gil init 도 같다). --no-open 은 기본이 된 지금 no-op 이다.\n" +
			"  탭을 닫았으면 `gil viewer open` 한 줄이면 된다 — 포트를 사람이 외우지 않는다.\n" +
			"  자리를 고정하려면 `.gil/viewer-port` 에 포트 한 줄(주소가 세션마다 안 바뀌어 북마크가 산다).\n" +
			"  `gil viewer shortcut` 은 그 명령을 부르는 런처를 만든다 — mac 은 ~/Applications 의 .app\n" +
			"  (Dock 에 끌어다 두면 버튼), 윈도우는 바탕화면 .cmd, 리눅스는 .desktop. 새 바이너리가\n" +
			"  아니라 gil 이 그 자리에서 만드는 껍데기다.\n" +
			"  **뷰어는 로그를 남긴다** — `<레포>/.git/gil-viewer.log` 에 기동(pid·포트·레포·버전)과\n" +
			"    종료(신호·에러)가 적힌다(이슈 #93). 뷰어가 죽었으면 거기서 이유를 읽어라.\n" +
			"    죽어도 서버가 통째로 사라지지 않는다: 실패한 요청 하나만 500 으로 끝난다.\n" +
			"    관전 레포가 사라지면 스스로 물러난다(없는 그래프를 가리킨 채 포트를 쥐지 않는다).\n" +
			"  list 는 포트 폴백으로 겹겹이 쌓인 뷰어 중 **내 저장소를 보는 것**을 찾아준다.",
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
