// viewer_i18n.go — 뷰어 화면의 언어 (ko · en · zh-CN · zh-TW).
//
// 왜. gil 의 주 독자는 에이전트고 에이전트는 한국어를 읽는다. 그러니 영어·중국어의 실익은
// 거의 전적으로 **사람 관전자**에게 있다 — 뷰어는 관전 도구이므로 여기부터가 맞는 순서다.
//
// 무엇을 번역하지 않는가(경계가 분량보다 중요하다). 체인 이름·스텝 본문·기억·커밋 메시지는
// **사용자가 쓴 것**이다. 그걸 옮기면 기록을 위조하는 것이다. 여기 사전에 들어오는 것은
// 화면의 크롬(설명·라벨·버튼)뿐이고, 사용자가 쓴 글자는 어느 언어에서도 원문 그대로 나온다.
//
// 어떻게. 서버가 언어를 골라 렌더하지 않는다 — **사전을 통째로 페이지에 실어** 보내고
// 화면에서 고른다. 세 가지가 따라온다: (1) 페이지 캐시가 언어 수만큼 갈라지지 않고
// (2) 토글이 새로고침 없이 즉시 먹고 (3) 서버 없는 정적 build 출력에서도 그대로 된다.
// 마크업에는 `data-i18n="키"` 를 달고 한국어 원문을 그대로 써 둔다 — JS 가 죽어도 화면은
// 빈칸이 되지 않는다.
package main

import (
	"encoding/json"
	"sort"
	"strings"
)

// i18nLangs — 지원 언어. 순서가 곧 토글에 보이는 순서다.
var i18nLangs = []string{"ko", "en", "zh-CN", "zh-TW"}

// i18nLangNames — 토글에 보일 이름. **각 언어를 그 언어로** 적는다(자기 언어를 못 찾는
// 사람이 토글을 못 쓴다 — 영어 이름만 늘어놓으면 그 자체가 영어 화면이다).
var i18nLangNames = map[string]string{
	"ko": "한국어", "en": "English", "zh-CN": "简体中文", "zh-TW": "繁體中文",
}

// viewerLang — `gil viewer serve --lang <코드>` 가 정하는 **기본** 언어. 사람이 화면에서
// 고른 적이 있으면 그 선택이 이긴다(브라우저에 남는다) — 기본값은 첫 방문에만 쓰인다.
var viewerLang = ""

// i18nDict — 키 → 언어 → 글. 한국어는 화면에 이미 쓰여 있는 원문과 **글자 그대로** 같아야
// 한다(그래야 이 갈아끼움이 한국어 화면을 바꾸지 않는다 — 시험이 이걸 지킨다).
//
// {이름} 은 자리표시자다. 언어마다 어순이 다르니 조각을 이어붙이지 않고 통문장에 자리를 판다
// ("체인 3개"와 "3 chains" 는 조각으로는 같은 코드로 못 만든다).
var i18nDict = map[string]map[string]string{
	// ── 머리 ──
	"app.title": {
		"ko": "gil 그래프 뷰어", "en": "gil graph viewer",
		"zh-CN": "gil 图谱查看器", "zh-TW": "gil 圖譜檢視器",
	},
	"app.h1": {
		"ko": "gil — 사고의 지도", "en": "gil — a map of the thinking",
		"zh-CN": "gil — 思考的地图", "zh-TW": "gil — 思考的地圖",
	},
	"head.gohere": {
		"ko": "▼ 현재위치로", "en": "▼ Go to HEAD",
		"zh-CN": "▼ 前往当前位置", "zh-TW": "▼ 前往目前位置",
	},
	// 이 화면이 보는 저장소(이슈 #110). 라벨만 옮긴다 — **경로와 식별자는 번역하지 않는다**
	// (사람이 만든 사실이고, 옮기면 그 자리를 못 찾는다).
	"head.repo": {
		"ko": "이 화면이 보는 저장소", "en": "This screen is watching",
		"zh-CN": "本页面所观察的仓库", "zh-TW": "本頁面所觀察的儲存庫",
	},
	"head.repo.title": {
		"ko": "뷰어 포트는 저장소 사이를 떠돈다 — 이 값이 네 저장소와 같은지 확인하라(#뒤는 이 저장소의 지문, /whoami 가 답하는 값과 같다)",
		"en": "Viewer ports drift between repositories — check this matches yours (after # is this repository's fingerprint, the same value /whoami reports)",
		"zh-CN": "查看器端口会在仓库之间漂移——请确认此处与你的仓库一致（# 后为本仓库指纹，与 /whoami 相同）",
		"zh-TW": "檢視器連接埠會在儲存庫之間漂移——請確認此處與你的儲存庫一致（# 後為本儲存庫指紋，與 /whoami 相同）",
	},
	"head.gohere.title": {
		"ko": "현재위치(HEAD)로 — 작업중이면 그 자리로",
		"en": "Jump to HEAD — or to the work in progress, if there is any",
		"zh-CN": "跳到当前位置（HEAD）——若有进行中的工作则跳到那里",
		"zh-TW": "跳到目前位置（HEAD）——若有進行中的工作則跳到那裡",
	},
	"head.meta": {
		"ko": "체인 {chains}개 · 스텝 {steps}개 · 현재위치 {tips}개",
		"en": "{chains} chains · {steps} steps · {tips} tips",
		"zh-CN": "{chains} 条链 · {steps} 个步骤 · {tips} 个当前位置",
		"zh-TW": "{chains} 條鏈 · {steps} 個步驟 · {tips} 個目前位置",
	},
	"lang.label": {
		"ko": "화면 언어", "en": "Display language",
		"zh-CN": "界面语言", "zh-TW": "介面語言",
	},
	"lang.note": {
		"ko": "화면 설명만 바뀝니다 — 체인 이름·스텝 본문 등 사람이 쓴 글은 원문 그대로입니다.",
		"en": "Only the interface changes — chain names, step bodies and anything a person wrote stay as written.",
		"zh-CN": "只切换界面文字——链名、步骤正文等由人写下的内容保持原文。",
		"zh-TW": "只切換介面文字——鏈名、步驟正文等由人寫下的內容保持原文。",
	},

	"head.live": {
		"ko": "● live", "en": "● live", "zh-CN": "● 实时", "zh-TW": "● 即時",
	},
	"head.static": {
		"ko": "정적 스냅샷", "en": "static snapshot",
		"zh-CN": "静态快照", "zh-TW": "靜態快照",
	},
	// 미커밋 작업 배지. 숫자만 자리표시자로 두고 나머지는 통문장 — "2개 파일"과 "2 files" 는
	// 조각으로는 같은 코드에서 못 나온다.
	"head.work": {
		"ko": "✎ 작업중: {files}개 파일", "en": "✎ working: {files} files",
		"zh-CN": "✎ 进行中：{files} 个文件", "zh-TW": "✎ 進行中：{files} 個檔案",
	},
	"head.work.diff": {
		"ko": "✎ 작업중: {files}개 파일, +{added} −{deleted}",
		"en": "✎ working: {files} files, +{added} −{deleted}",
		"zh-CN": "✎ 进行中：{files} 个文件，+{added} −{deleted}",
		"zh-TW": "✎ 進行中：{files} 個檔案，+{added} −{deleted}",
	},

	// ── 빈 상태 ──
	"empty": {
		"ko": "아직 gil 체인이 없다. 체인을 만들면 여기 노드로 나타난다.",
		"en": "No gil chains yet. Create one and it will appear here as a node.",
		"zh-CN": "还没有 gil 链。创建一条，它就会作为节点出现在这里。",
		"zh-TW": "還沒有 gil 鏈。建立一條，它就會作為節點出現在這裡。",
	},

	// ── 이 화면 읽는 법(온보딩) ──
	// 처음 온 사람이 가장 먼저 읽는 자리다. 관전 도구는 관전자를 가르치지 않으면 그림일 뿐이다.
	"guide.summary": {
		"ko": "이 화면 읽는 법 — 체인 · 사이클 · 스텝",
		"en": "How to read this screen — chains, cycles, steps",
		"zh-CN": "如何看懂这个界面——链 · 循环 · 步骤",
		"zh-TW": "如何看懂這個介面——鏈 · 循環 · 步驟",
	},
	"guide.toggle": {
		"ko": "(펼치기/접기)", "en": "(show/hide)",
		"zh-CN": "（展开／收起）", "zh-TW": "（展開／收合）",
	},
	"guide.intro": {
		"ko": "<b>gil 은 AI 가 문제를 푼 <i>생각의 과정</i>을 git 커밋으로 남긴 것입니다.</b> 이 화면의 점 하나하나가 실제 커밋이고, 선은 “무엇에서 무엇이 나왔나”입니다.",
		"en": "<b>gil records the <i>thinking</i> an AI did to solve a problem, as git commits.</b> Every dot on this screen is a real commit, and every line says “this came out of that”.",
		"zh-CN": "<b>gil 把 AI 解决问题的<i>思考过程</i>记录成 git 提交。</b>屏幕上的每个圆点都是一次真实的提交，每条连线都在说“这个是从那个来的”。",
		"zh-TW": "<b>gil 把 AI 解決問題的<i>思考過程</i>記錄成 git 提交。</b>畫面上的每個圓點都是一次真實的提交，每條連線都在說「這個是從那個來的」。",
	},
	"guide.li.chain": {
		"ko": "<b>체인</b> — 가장 큰 줄기(한 덩어리의 목적). 예: “전기요금이 왜 두 배가 됐나”. 체인마다 사람이 세운 <b>기준 문서</b>가 붙습니다.",
		"en": "<b>Chain</b> — the largest thread (one whole purpose). For example: “why did the electricity bill double?”. Every chain carries a <b>reference document</b> a person set.",
		"zh-CN": "<b>链</b>——最大的脉络（一个完整的目的）。例如：“电费为什么翻了一倍”。每条链都附有由人设定的<b>基准文件</b>。",
		"zh-TW": "<b>鏈</b>——最大的脈絡（一個完整的目的）。例如：「電費為什麼翻了一倍」。每條鏈都附有由人設定的<b>基準文件</b>。",
	},
	"guide.li.cycle": {
		"ko": "<b>사이클</b> — 그 목적을 쪼갠 <b>하나의 작은 문제</b>. 문제 정의 → 가설 → 검증 → 분석 → 종결로 한 바퀴 돕니다.",
		"en": "<b>Cycle</b> — <b>one small problem</b> that purpose was split into. It goes around once: define → hypothesis → verify → analyze → close.",
		"zh-CN": "<b>循环</b>——把那个目的拆开后的<b>一个小问题</b>。走完一圈：问题定义 → 假设 → 验证 → 分析 → 终结。",
		"zh-TW": "<b>循環</b>——把那個目的拆開後的<b>一個小問題</b>。走完一圈：問題定義 → 假設 → 驗證 → 分析 → 終結。",
	},
	"guide.li.step": {
		"ko": "<b>스텝</b> — 그 한 바퀴 안의 <b>한 걸음</b>(점 하나 = 커밋 하나). 점을 누르면 그 걸음의 보고서가 아래에 열립니다.",
		"en": "<b>Step</b> — <b>one move</b> within that lap (one dot = one commit). Click a dot and that move's report opens below.",
		"zh-CN": "<b>步骤</b>——这一圈里的<b>一步</b>（一个圆点＝一次提交）。点击圆点，该步的报告会在下方打开。",
		"zh-TW": "<b>步驟</b>——這一圈裡的<b>一步</b>（一個圓點＝一次提交）。點擊圓點，該步的報告會在下方開啟。",
	},

	// 안내 그림. SVG <text> 는 줄바꿈이 없으니 **짧게** 옮긴다 — 길면 그림 밖으로 나간다.
	"diag.aria": {
		"ko": "체인 안에 사이클, 사이클 안에 스텝이 있는 구조 그림",
		"en": "A diagram: cycles sit inside a chain, steps sit inside a cycle",
		"zh-CN": "结构图：链中包含循环，循环中包含步骤",
		"zh-TW": "結構圖：鏈中包含循環，循環中包含步驟",
	},
	"diag.chain": {
		"ko": "체인 — 하나의 큰 목적 “전기요금이 왜 두 배가 됐나”",
		"en": "Chain — one big purpose: “why did the bill double?”",
		"zh-CN": "链——一个大目的：“电费为什么翻倍”",
		"zh-TW": "鏈——一個大目的：「電費為什麼翻倍」",
	},
	"diag.cycle1": {
		"ko": "사이클 1 — 작은 문제 “언제 늘었나”",
		"en": "Cycle 1 — small problem: “when did it rise?”",
		"zh-CN": "循环 1 — 小问题：“何时开始上涨”",
		"zh-TW": "循環 1 — 小問題：「何時開始上漲」",
	},
	"diag.cycle2": {
		"ko": "사이클 2 — “어느 기기인가”",
		"en": "Cycle 2 — “which appliance?”",
		"zh-CN": "循环 2 — “是哪台电器”",
		"zh-TW": "循環 2 — 「是哪台電器」",
	},
	"diag.k.define": {
		"ko": "문제정의", "en": "define", "zh-CN": "问题定义", "zh-TW": "問題定義",
	},
	"diag.k.hypothesis": {
		"ko": "가설", "en": "hypothesis", "zh-CN": "假设", "zh-TW": "假設",
	},
	"diag.k.verify": {
		"ko": "검증", "en": "verify", "zh-CN": "验证", "zh-TW": "驗證",
	},
	"diag.k.analyze": {
		"ko": "분석", "en": "analyze", "zh-CN": "分析", "zh-TW": "分析",
	},
	"diag.k.success": {
		"ko": "성공", "en": "success", "zh-CN": "成功", "zh-TW": "成功",
	},
	"diag.k.verifying": {
		"ko": "검증 중", "en": "verifying", "zh-CN": "验证中", "zh-TW": "驗證中",
	},
	"diag.dead": {
		"ko": "막다른 길 — 지우지 않고 남긴다",
		"en": "dead end — kept, not deleted",
		"zh-CN": "死路——保留，不删除", "zh-TW": "死路——保留，不刪除",
	},
	// 이 라벨은 사이클 이름과 같은 줄에 있었고, 영어에서 그 이름을 덮었다. 짧게 줄이는 것은
	// 언어마다 다시 부딪히고 뜻만 깎는다 — 그래서 그림에서 **한 줄 위로** 뺐다(y=64→46).
	"diag.here": {
		"ko": "지금 여기", "en": "you are here", "zh-CN": "当前位置", "zh-TW": "目前位置",
	},
	"diag.cap1": {
		"ko": "점 하나 = git 커밋 하나 = 한 걸음. 점을 누르면 그 걸음의 보고서가 열립니다.",
		"en": "One dot = one git commit = one move. Click a dot to open that move's report.",
		"zh-CN": "一个圆点＝一次 git 提交＝一步。点击圆点即可打开该步的报告。",
		"zh-TW": "一個圓點＝一次 git 提交＝一步。點擊圓點即可開啟該步的報告。",
	},
	"diag.cap2": {
		"ko": "사이클이 끝나면 다음 사이클로 — 그렇게 큰 목적(체인)을 작은 문제로 정복합니다.",
		"en": "When a cycle closes, the next begins — that is how a big purpose falls to small problems.",
		"zh-CN": "一个循环结束就进入下一个——大目的就是这样被小问题逐一攻克的。",
		"zh-TW": "一個循環結束就進入下一個——大目的就是這樣被小問題逐一攻克的。",
	},

	"guide.legend.marks": {
		"ko": "<b>점의 색과 표식</b> — <span class=\"lg-alive\">초록</span>=성공으로 끝난 가지 · <span class=\"lg-dead\">빨강</span>=막다른 길(지우지 않고 <b>벽의 지도</b>로 남깁니다) · <span class=\"lg-cross\">주황 ▼</span>=지금 작업 중인 자리 · 🚀=여기서 배포됨 · ⟲정정=앞 걸음을 다시 쓴 것 · <span class=\"gdim\">흐린 점</span>=정정으로 대체된 옛 가지(이력엔 남습니다).",
		"en": "<b>What the colours mean</b> — <span class=\"lg-alive\">green</span> = a branch that ended in success · <span class=\"lg-dead\">red</span> = a dead end (kept, as a <b>map of the walls</b>) · <span class=\"lg-cross\">orange ▼</span> = where the work is right now · 🚀 = shipped from here · ⟲ = a move rewritten · <span class=\"gdim\">faded dot</span> = the old branch that rewrite replaced (still in the history).",
		"zh-CN": "<b>颜色与标记</b>——<span class=\"lg-alive\">绿色</span>＝以成功收尾的分支 · <span class=\"lg-dead\">红色</span>＝死路（保留下来，作为<b>墙的地图</b>） · <span class=\"lg-cross\">橙色 ▼</span>＝当前正在进行的位置 · 🚀＝从此处发布 · ⟲＝重写过的一步 · <span class=\"gdim\">淡色圆点</span>＝被该重写取代的旧分支（仍留在历史中）。",
		"zh-TW": "<b>顏色與標記</b>——<span class=\"lg-alive\">綠色</span>＝以成功收尾的分支 · <span class=\"lg-dead\">紅色</span>＝死路（保留下來，作為<b>牆的地圖</b>） · <span class=\"lg-cross\">橙色 ▼</span>＝目前正在進行的位置 · 🚀＝從此處發布 · ⟲＝重寫過的一步 · <span class=\"gdim\">淡色圓點</span>＝被該重寫取代的舊分支（仍留在歷史中）。",
	},
	"guide.legend.dead": {
		"ko": "<b>막다른 길이 남아 있는 건 고장이 아닙니다.</b> 무엇을 시도했다가 왜 접었는지가 남아야 같은 길을 두 번 걷지 않습니다 — gil 이 남기려는 것이 바로 그것입니다.",
		"en": "<b>Dead ends left on the map are not a defect.</b> What was tried and why it was abandoned has to survive, or the same road gets walked twice — that is exactly what gil is here to keep.",
		"zh-CN": "<b>图上留着死路，并不是故障。</b>试过什么、为什么放弃，这些必须留下来，否则同一条路会走第二遍——gil 要保留的正是这个。",
		"zh-TW": "<b>圖上留著死路，並不是故障。</b>試過什麼、為什麼放棄，這些必須留下來，否則同一條路會走第二遍——gil 要保留的正是這個。",
	},
	"guide.legend.where": {
		"ko": "<b>어디부터 보나</b> — 아래 <b>전체맵</b>이 전체 흐름입니다(왼→오른쪽). 거기서 점을 누르면 <b>스텝 그래프</b>와 <b>스텝 디테일</b>이 그 자리로 갑니다. 위쪽 <b>▼ 현재위치로</b> 버튼은 언제나 지금 작업 중인 자리로 데려갑니다. 체인·사이클 단위로 크게 보고 싶으면 아래 접힌 <b>체인 그래프</b>·<b>사이클 그래프</b>를 펼치세요.",
		"en": "<b>Where to start</b> — the <b>overview map</b> below is the whole flow (left to right). Click a dot there and the <b>step graph</b> and <b>step detail</b> follow you to it. The <b>▼ Go to HEAD</b> button up top always takes you to where the work is now. To see it in bigger units, unfold the <b>chain graph</b> or <b>cycle graph</b> below.",
		"zh-CN": "<b>从哪里看起</b>——下方的<b>全局图</b>就是完整脉络（由左至右）。在那里点击圆点，<b>步骤图</b>与<b>步骤详情</b>会一同跟到该处。顶部的<b>▼ 前往当前位置</b>按钮随时把你带到正在进行的地方。想以更大的单位查看，就展开下方的<b>链图</b>或<b>循环图</b>。",
		"zh-TW": "<b>從哪裡看起</b>——下方的<b>全局圖</b>就是完整脈絡（由左至右）。在那裡點擊圓點，<b>步驟圖</b>與<b>步驟詳情</b>會一同跟到該處。頂部的<b>▼ 前往目前位置</b>按鈕隨時把你帶到正在進行的地方。想以更大的單位檢視，就展開下方的<b>鏈圖</b>或<b>循環圖</b>。",
	},

	// ── 사람이 실제로 누르는 자리(인터뷰·승인·확정본) ──
	// 여기가 한국어로 남으면 관전자는 **읽기만 하고 아무것도 못 한다**. 화면 절반이 옮겨진
	// 상태에서 정작 손잡이만 못 읽는 것이 가장 나쁘다.
	"pane.prune": {
		"ko": "🗑 삭제 승인 대기 — 사람만 누를 수 있습니다",
		"en": "🗑 Awaiting your approval to delete — only a person can press this",
		"zh-CN": "🗑 等待删除批准——只有人可以按下",
		"zh-TW": "🗑 等待刪除批准——只有人可以按下",
	},
	"pane.reference": {
		"ko": "✅ 확정된 기준 문서", "en": "✅ Reference documents, settled",
		"zh-CN": "✅ 已确定的基准文件", "zh-TW": "✅ 已確定的基準文件",
	},
	"pane.interview": {
		"ko": "📋 인터뷰 — 기준 문서 만들기",
		"en": "📋 Interview — building the reference document",
		"zh-CN": "📋 访谈——共同拟定基准文件",
		"zh-TW": "📋 訪談——共同擬定基準文件",
	},

	"prune.head": {
		"ko": "삭제 요청: {target}  ({sha})", "en": "Delete requested: {target}  ({sha})",
		"zh-CN": "删除请求：{target}（{sha}）", "zh-TW": "刪除請求：{target}（{sha}）",
	},
	"prune.approve": {
		"ko": "이 삭제를 승인합니다", "en": "I approve this deletion",
		"zh-CN": "我批准此次删除", "zh-TW": "我批准此次刪除",
	},
	"prune.armed": {
		"ko": " 5초 안에 한 번 더 누르면 승인됩니다",
		"en": " press once more within 5 seconds to approve",
		"zh-CN": " 5 秒内再按一次即批准", "zh-TW": " 5 秒內再按一次即批准",
	},
	"prune.approving": {
		"ko": " 승인 중…", "en": " approving…", "zh-CN": " 批准中…", "zh-TW": " 批准中…",
	},
	"prune.approved": {
		"ko": " ✓ 승인됨 — 실행: gil prune {target} --confirm {target} --reason <왜>",
		"en": " ✓ approved — now run: gil prune {target} --confirm {target} --reason <why>",
		"zh-CN": " ✓ 已批准——接着执行：gil prune {target} --confirm {target} --reason <原因>",
		"zh-TW": " ✓ 已批准——接著執行：gil prune {target} --confirm {target} --reason <原因>",
	},
	"prune.withdraw": {
		"ko": "요청 철회", "en": "Withdraw request", "zh-CN": "撤回请求", "zh-TW": "撤回請求",
	},
	"prune.withdraw.title": {
		"ko": "아무것도 지우지 않고 이 요청을 거둔다(이력엔 남는다)",
		"en": "Take this request back without deleting anything (it stays in the history)",
		"zh-CN": "不删除任何内容，只撤回此请求（历史中仍会留下）",
		"zh-TW": "不刪除任何內容，只撤回此請求（歷史中仍會留下）",
	},
	"prune.withdrawing": {
		"ko": " 철회 중…", "en": " withdrawing…", "zh-CN": " 撤回中…", "zh-TW": " 撤回中…",
	},

	"ref.just": {
		"ko": "✓ 방금 제출한 답이 기준 문서로 확정됐습니다 — ",
		"en": "✓ The answer you just sent is now the reference document — ",
		"zh-CN": "✓ 你刚提交的回答已确定为基准文件——",
		"zh-TW": "✓ 你剛提交的回答已確定為基準文件——",
	},
	"ref.sum": {
		"ko": "체인 {chain} 기준 문서 ({sha}) · ",
		"en": "reference document for chain {chain} ({sha}) · ",
		"zh-CN": "链 {chain} 的基准文件（{sha}） · ",
		"zh-TW": "鏈 {chain} 的基準文件（{sha}） · ",
	},
	"ref.state.waiting": {
		"ko": "⏳ 에이전트가 기다리는 중", "en": "⏳ the agent is waiting",
		"zh-CN": "⏳ 代理正在等待", "zh-TW": "⏳ 代理正在等待",
	},
	"ref.state.seen": {
		"ko": "✓ 에이전트가 읽었습니다", "en": "✓ the agent has read it",
		"zh-CN": "✓ 代理已读取", "zh-TW": "✓ 代理已讀取",
	},
	"ref.state.unseen": {
		"ko": "· 아직 안 읽음", "en": "· not read yet",
		"zh-CN": "· 尚未读取", "zh-TW": "· 尚未讀取",
	},
	"ref.empty": {
		"ko": "(본문 없음)", "en": "(no body)", "zh-CN": "（无正文）", "zh-TW": "（無正文）",
	},

	"iv.head": {
		"ko": "체인 <b>{chain}</b> 의 기준 문서를 함께 만든다 — 문제 풀듯 답하고 제출하세요.",
		"en": "Let's build the reference document for chain <b>{chain}</b> — answer as you would solve a problem, then send it.",
		"zh-CN": "一起来拟定链 <b>{chain}</b> 的基准文件——像解题那样作答，然后提交。",
		"zh-TW": "一起來擬定鏈 <b>{chain}</b> 的基準文件——像解題那樣作答，然後提交。",
	},
	"iv.waiting": {
		"ko": "⏳ 에이전트가 이 답을 기다리는 중 — 제출하면 곧바로 이어집니다.",
		"en": "⏳ The agent is waiting on this answer — send it and the work resumes right away.",
		"zh-CN": "⏳ 代理正在等这个回答——提交后工作会立即继续。",
		"zh-TW": "⏳ 代理正在等這個回答——提交後工作會立即繼續。",
	},
	"iv.notwaiting": {
		"ko": "· 지금은 아무도 기다리고 있지 않습니다. 제출은 저장되고, 에이전트는 다음 접촉 때 읽습니다.",
		"en": "· Nobody is waiting right now. Your answer is saved, and the agent reads it on its next contact.",
		"zh-CN": "· 目前没有人在等。提交会被保存，代理会在下次接触时读取。",
		"zh-TW": "· 目前沒有人在等。提交會被保存，代理會在下次接觸時讀取。",
	},
	"iv.submit": {
		"ko": "제출 — 기준 문서로 저장", "en": "Send — save as the reference document",
		"zh-CN": "提交——保存为基准文件", "zh-TW": "提交——儲存為基準文件",
	},
	"iv.restored": {
		"ko": "· 쓰시던 내용을 복원했습니다(이 브라우저에만 저장됩니다). 제출하면 지워집니다.",
		"en": "· Restored what you were writing (kept in this browser only). It clears once you send.",
		"zh-CN": "· 已恢复你之前写的内容（仅保存在这台浏览器）。提交后即清除。",
		"zh-TW": "· 已恢復你之前寫的內容（僅保存在這台瀏覽器）。提交後即清除。",
	},
	"iv.deferred": {
		"ko": "새 기록이 도착했지만, 답을 쓰는 중이라 새로고침을 미뤘습니다 — 쓰던 내용은 그대로 있습니다.",
		"en": "New records arrived, but the refresh is held while you are writing — nothing you typed was lost.",
		"zh-CN": "有新记录到达，但你正在作答，刷新已暂缓——你写的内容原样保留。",
		"zh-TW": "有新紀錄到達，但你正在作答，重新整理已暫緩——你寫的內容原樣保留。",
	},
	"iv.failed": {
		"ko": " ✕ 제출 실패: ", "en": " ✕ could not send: ",
		"zh-CN": " ✕ 提交失败：", "zh-TW": " ✕ 提交失敗：",
	},
	"iv.failed.hint": {
		"ko": "답은 아직 제출되지 않았습니다(사라지지도 않았습니다). <b>새로고침한 뒤 다시 제출</b>해 주세요 — 입력한 내용은 이 브라우저에 저장돼 있어 새로고침해도 되살아납니다.",
		"en": "Your answer has not been sent (and it has not been lost either). Please <b>refresh and send again</b> — what you typed is kept in this browser and comes back after the refresh.",
		"zh-CN": "回答尚未提交（也没有丢失）。请<b>刷新后重新提交</b>——你输入的内容保存在这台浏览器里，刷新后会恢复。",
		"zh-TW": "回答尚未提交（也沒有遺失）。請<b>重新整理後再次提交</b>——你輸入的內容保存在這台瀏覽器裡，重新整理後會恢復。",
	},

	// ── 경합과 벽의 지도(이슈 #112) ──
	// 스텝 이름(s5)·사람이 쓴 이유는 자리표시자로만 지나간다 — 옮기지 않는다.
	"step.map.stale.tip": {
		"ko": "이 지도는 {by} 가 갱신했다 — 실제로는 {to} 에서 갈라졌다.\n이유: {why}",
		"en": "This map was updated by {by} — the branch actually came off {to}.\nReason: {why}",
		"zh-CN": "该地图已由 {by} 更新——实际是从 {to} 分出的。\n理由：{why}",
		"zh-TW": "該地圖已由 {by} 更新——實際是從 {to} 分出的。\n理由：{why}",
	},
	"step.map.stale.label": {
		"ko": "지도 갱신됨 → {to} ({by}, despite)",
		"en": "map updated → {to} ({by}, despite)",
		"zh-CN": "地图已更新 → {to}（{by}, despite）",
		"zh-TW": "地圖已更新 → {to}（{by}, despite）",
	},
	"step.map.live.tip": {
		"ko": "벽의 지도: 여기서 막혔으니 {to} 로 되돌아가라",
		"en": "Map of the wall: blocked here — go back to {to}",
		"zh-CN": "墙的地图：在此受阻——回到 {to}",
		"zh-TW": "牆的地圖：在此受阻——回到 {to}",
	},
	"step.lost.tip": {
		"ko": "경합에서 {winner} 에 졌다 — 실패가 아니라 비교의 한쪽이다(대조가 승자의 근거를 떠받친다)",
		"en": "Lost the competition to {winner} — not a failure but one side of the comparison (the control is what makes the winner's numbers mean anything)",
		"zh-CN": "在竞争中输给了 {winner}——这不是失败，而是对照的一方（正是对照让胜者的数字有意义）",
		"zh-TW": "在競爭中輸給了 {winner}——這不是失敗，而是對照的一方（正是對照讓勝者的數字有意義）",
	},
	"step.badge.competing": {
		"ko": "⚖ 경합", "en": "⚖ competing",
		"zh-CN": "⚖ 竞争中", "zh-TW": "⚖ 競爭中",
	},
	"step.badge.lost": {
		"ko": "⚖ 졌음", "en": "⚖ lost",
		"zh-CN": "⚖ 已落败", "zh-TW": "⚖ 已落敗",
	},
	"step.badge.competing.tip": {
		"ko": "{root} 에서 형제들과 **동시에** 겨루려고 연 갈래다 — 매달린 잎이 아니다(잊혀서 남은 것과 겨루려고 열어 둔 것은 다르다)",
		"en": "A branch opened to run **alongside** its siblings from {root} — not a dangling leaf (a leaf left behind and a branch held open to compete are different things)",
		"zh-CN": "这是为了与 {root} 处的兄弟分支**同时**较量而开的分支——不是悬空叶（被遗忘留下的与为比较而保留的不同）",
		"zh-TW": "這是為了與 {root} 處的兄弟分支**同時**較量而開的分支——不是懸空葉（被遺忘留下的與為比較而保留的不同）",
	},
	"step.badge.map.pending": {
		"ko": "⌖ 지도 미정", "en": "⌖ map pending",
		"zh-CN": "⌖ 地图未定", "zh-TW": "⌖ 地圖未定",
	},
	"step.badge.map.pending.tip": {
		"ko": "되돌아갈 자리를 아직 정하지 않았다 — 다음 재분기(또는 사람의 판정)가 정한다. 모른다고 적은 것이지 빠뜨린 것이 아니다.",
		"en": "Where to go back has not been decided yet — the next re-branch (or a human call) will set it. This is recorded as unknown, not left out.",
		"zh-CN": "尚未确定回退到哪里——由下一次再分支（或人的判断）决定。这是明写的“未定”，不是遗漏。",
		"zh-TW": "尚未確定回退到哪裡——由下一次再分支（或人的判斷）決定。這是明寫的「未定」，不是遺漏。",
	},
	"step.badge.despite": {
		"ko": "⟲ 지도 벗어남", "en": "⟲ off the map",
		"zh-CN": "⟲ 偏离地图", "zh-TW": "⟲ 偏離地圖",
	},
	"step.badge.despite.tip": {
		"ko": "벽의 지도와 다른 자리에서 갈라졌다(--despite): {why}",
		"en": "Branched somewhere other than where the map of the wall pointed (--despite): {why}",
		"zh-CN": "在与墙的地图不同的位置分支（--despite）：{why}",
		"zh-TW": "在與牆的地圖不同的位置分支（--despite）：{why}",
	},
	"compare.head": {
		"ko": "⚖ {root} 에서 겨루는 갈래 {n}개",
		"en": "⚖ {n} branches competing from {root}",
		"zh-CN": "⚖ 从 {root} 分出的 {n} 条竞争分支",
		"zh-TW": "⚖ 從 {root} 分出的 {n} 條競爭分支",
	},
	"compare.note": {
		"ko": "나란히 세운 것은 비교하려는 것이다 — 각자 무엇이 관측되면 틀리는가로 견준다.",
		"en": "They were stood side by side to be compared — weigh them by what each says would prove it wrong.",
		"zh-CN": "并排摆开就是为了比较——以各自“观测到什么即为错”来衡量。",
		"zh-TW": "並排擺開就是為了比較——以各自「觀測到什麼即為錯」來衡量。",
	},
	"compare.col.branch": {
		"ko": "갈래", "en": "branch", "zh-CN": "分支", "zh-TW": "分支",
	},
	"compare.col.hypothesis": {
		"ko": "가설", "en": "hypothesis", "zh-CN": "假设", "zh-TW": "假設",
	},
	"compare.col.falsify": {
		"ko": "반증조건", "en": "falsifier", "zh-CN": "反证条件", "zh-TW": "反證條件",
	},
	"compare.col.plan": {
		"ko": "고정한 설계", "en": "fixed design", "zh-CN": "已固定的设计", "zh-TW": "已固定的設計",
	},
	"compare.col.state": {
		"ko": "상태", "en": "state", "zh-CN": "状态", "zh-TW": "狀態",
	},
	"compare.state.won": {
		"ko": "✓ 채택됨", "en": "✓ adopted", "zh-CN": "✓ 已采用", "zh-TW": "✓ 已採用",
	},
	"compare.state.lost": {
		"ko": "✖ {winner} 에 졌음", "en": "✖ lost to {winner}",
		"zh-CN": "✖ 输给 {winner}", "zh-TW": "✖ 輸給 {winner}",
	},
	"compare.state.fail": {
		"ko": "✖ 접힘", "en": "✖ folded", "zh-CN": "✖ 已收起", "zh-TW": "✖ 已收起",
	},
	"compare.state.open": {
		"ko": "… 겨루는 중", "en": "… still competing", "zh-CN": "… 仍在较量", "zh-TW": "… 仍在較量",
	},
	"compare.state.leaf": {
		"ko": "이 갈래의 잎: {leaf}", "en": "leaf of this branch: {leaf}",
		"zh-CN": "此分支的叶：{leaf}", "zh-TW": "此分支的葉：{leaf}",
	},
	"card.dupwarn": {
		"ko": "⚠ 이 사이클엔 번호가 겹치는 스텝이 있다({dups}) — 옛 gil(≤3.28)이 찍은 구간이다. 뷰어는 커밋 sha 를 정체성으로 삼아 그대로 그린다. 전체 점검: gil fsck",
		"en": "⚠ This cycle has steps with colliding numbers ({dups}) — a stretch stamped by an old gil (≤3.28). The viewer takes the commit sha as identity and draws it as it is. To check everything: gil fsck",
		"zh-CN": "⚠ 本循环中有编号重复的步骤（{dups}）——这是旧版 gil（≤3.28）留下的区段。查看器以提交 sha 为身份，照原样绘制。全面检查：gil fsck",
		"zh-TW": "⚠ 本循環中有編號重複的步驟（{dups}）——這是舊版 gil（≤3.28）留下的區段。檢視器以提交 sha 為身分，照原樣繪製。全面檢查：gil fsck",
	},
	"card.stepgraph.failed": {
		"ko": "✕ 이 사이클의 스텝 그래프를 그리지 못했다: {err}  (데이터는 그대로다 — 뷰어의 렌더만 실패했다. gil fsck 로 그래프를 점검하라.)",
		"en": "✕ Could not draw the step graph for this cycle: {err}  (the data is intact — only the viewer's render failed. Check the graph with gil fsck.)",
		"zh-CN": "✕ 无法绘制本循环的步骤图：{err}（数据完好——只是查看器的渲染失败。请用 gil fsck 检查图谱。）",
		"zh-TW": "✕ 無法繪製本循環的步驟圖：{err}（資料完好——只是檢視器的渲染失敗。請用 gil fsck 檢查圖譜。）",
	},

	// ── 나머지 패널과 그래프 ──
	"pane.gitgraph": {
		"ko": "git 그래프 (날것)", "en": "git graph (raw)",
		"zh-CN": "git 图（原始）", "zh-TW": "git 圖（原始）",
	},
	"pane.gitgraph.toggle": {
		"ko": "(펼치기 — gil 계보가 진짜 브랜치인지 여기서 점검한다)",
		"en": "(unfold — check here whether gil's lineage is real branching)",
		"zh-CN": "（展开——在此核对 gil 的谱系是否真的分了支）",
		"zh-TW": "（展開——在此核對 gil 的譜系是否真的分了支）",
	},
	"pane.gitgraph.hint": {
		"ko": "gil 이 그리는 계보와 <b>git 자신의 그림</b>이 같은지 보는 자리다. 선언만 하고 실제로 갈라지지 않으면 그 계보는 거짓이고, 그건 여기서 바로 드러난다. 점=커밋 · 선=부모 · 칩=브랜치 이름. 최근 400개.",
		"en": "This is where you check gil's lineage against <b>git's own picture</b>. A lineage that is declared but never actually branched is a lie, and it shows up right here. Dot = commit · line = parent · chip = branch name. Last 400.",
		"zh-CN": "这里是把 gil 画的谱系与 <b>git 自己的图</b>相对照的地方。只作声明却没有真正分支的谱系是假的，在这里会立刻暴露。点＝提交 · 线＝父提交 · 标签＝分支名。最近 400 条。",
		"zh-TW": "這裡是把 gil 畫的譜系與 <b>git 自己的圖</b>相對照的地方。只作聲明卻沒有真正分支的譜系是假的，在這裡會立刻暴露。點＝提交 · 線＝父提交 · 標籤＝分支名。最近 400 條。",
	},
	"pane.chaingraph": {
		"ko": "체인 그래프", "en": "Chain graph", "zh-CN": "链图", "zh-TW": "鏈圖",
	},
	"pane.chaingraph.hint": {
		"ko": "동그라미 = 체인(숫자는 사이클 수), 선 = 계보(부모→자식). ▼ = 현재위치(HEAD). <b>노드 클릭 → 아래 사이클 그래프.</b>",
		"en": "Circle = chain (the number is how many cycles), line = lineage (parent → child). ▼ = HEAD. <b>Click a node for the cycle graph below.</b>",
		"zh-CN": "圆圈＝链（数字为循环数），连线＝谱系（父→子）。▼＝当前位置（HEAD）。<b>点击节点查看下方的循环图。</b>",
		"zh-TW": "圓圈＝鏈（數字為循環數），連線＝譜系（父→子）。▼＝目前位置（HEAD）。<b>點擊節點查看下方的循環圖。</b>",
	},
	"pane.cyclegraph": {
		"ko": "사이클 그래프", "en": "Cycle graph", "zh-CN": "循环图", "zh-TW": "循環圖",
	},
	"pane.stepgraph": {
		"ko": "스텝 그래프", "en": "Step graph", "zh-CN": "步骤图", "zh-TW": "步驟圖",
	},
	"pane.stepdetail": {
		"ko": "스텝 디테일", "en": "Step detail", "zh-CN": "步骤详情", "zh-TW": "步驟詳情",
	},
	"pane.unfold": {
		"ko": "(펼치기)", "en": "(unfold)", "zh-CN": "（展开）", "zh-TW": "（展開）",
	},

	// 사람이 승인·기각하는 pending 잎.
	"pend.msg": {
		"ko": "⏳ 사람 답 대기 —", "en": "⏳ waiting on you —",
		"zh-CN": "⏳ 等待你的答复 ——", "zh-TW": "⏳ 等待你的答覆 ——",
	},
	"pend.approve": {
		"ko": "✓ 승인(산 잎)", "en": "✓ Approve (living leaf)",
		"zh-CN": "✓ 批准（活叶）", "zh-TW": "✓ 批准（活葉）",
	},
	"pend.reject": {
		"ko": "✕ 기각(되돌림)", "en": "✕ Reject (send it back)",
		"zh-CN": "✕ 驳回（退回）", "zh-TW": "✕ 駁回（退回）",
	},
	"pend.working": {
		"ko": " 처리 중…", "en": " working…", "zh-CN": " 处理中…", "zh-TW": " 處理中…",
	},
	"pend.done": {
		"ko": " ✓ 완료 — 갱신 중", "en": " ✓ done — refreshing",
		"zh-CN": " ✓ 完成——正在刷新", "zh-TW": " ✓ 完成——正在重新整理",
	},

	"prune.armed2": {
		"ko": "정말 지웁니다 — 한 번 더", "en": "Really delete — once more",
		"zh-CN": "确认删除——再按一次", "zh-TW": "確認刪除——再按一次",
	},
	"prune.timeout": {
		"ko": " (시간이 지나 취소됨)", "en": " (timed out, cancelled)",
		"zh-CN": " （超时，已取消）", "zh-TW": " （逾時，已取消）",
	},
	"prune.withdrawn": {
		"ko": " ✓ 요청을 거뒀다 — 아무것도 지워지지 않았다",
		"en": " ✓ request withdrawn — nothing was deleted",
		"zh-CN": " ✓ 已撤回请求——什么都没有删除",
		"zh-TW": " ✓ 已撤回請求——什麼都沒有刪除",
	},

	"ref.pinned": {
		"ko": "📌 이 체인의 기준 문서 — 판단은 여기에 비추어라 ({sha}) · ",
		"en": "📌 This chain's reference document — judge against this ({sha}) · ",
		"zh-CN": "📌 本链的基准文件——一切判断以此为准（{sha}） · ",
		"zh-TW": "📌 本鏈的基準文件——一切判斷以此為準（{sha}） · ",
	},
	"ref.dismiss.title": {
		"ko": "이 확정본은 그만 보기(다음 차수가 오면 다시 뜹니다)",
		"en": "Stop showing this one (it returns when a new round arrives)",
		"zh-CN": "不再显示这一版（下一轮到来时会再出现）",
		"zh-TW": "不再顯示這一版（下一輪到來時會再出現）",
	},

	"iv.refresh": {
		"ko": "지금 새로고침", "en": "Refresh now", "zh-CN": "立即刷新", "zh-TW": "立即重新整理",
	},
	"iv.refresh.title": {
		"ko": "입력하신 내용은 저장돼 있어 새로고침해도 되살아납니다",
		"en": "What you typed is saved — it comes back after the refresh",
		"zh-CN": "你输入的内容已保存，刷新后会恢复",
		"zh-TW": "你輸入的內容已保存，重新整理後會恢復",
	},
	"iv.saving": {
		"ko": " 저장 중…", "en": " saving…", "zh-CN": " 保存中…", "zh-TW": " 儲存中…",
	},
	"iv.saved": {
		"ko": " ✓ 기준 문서로 확정됐습니다 — 화면을 갱신합니다",
		"en": " ✓ settled as the reference document — refreshing the screen",
		"zh-CN": " ✓ 已确定为基准文件——正在刷新画面",
		"zh-TW": " ✓ 已確定為基準文件——正在重新整理畫面",
	},

	"report.loading": {
		"ko": "(불러오는 중…)", "en": "(loading…)", "zh-CN": "（加载中…）", "zh-TW": "（載入中…）",
	},
	"report.failed": {
		"ko": "(보고서를 불러오지 못했다: {status})", "en": "(could not load the report: {status})",
		"zh-CN": "（无法加载报告：{status}）", "zh-TW": "（無法載入報告：{status}）",
	},
	"report.neterr": {
		"ko": "(네트워크 오류: {err})", "en": "(network error: {err})",
		"zh-CN": "（网络错误：{err}）", "zh-TW": "（網路錯誤：{err}）",
	},
	"head.gohere.missing": {
		"ko": "현재위치가 그래프에 없다", "en": "HEAD is not on the graph",
		"zh-CN": "当前位置不在图上", "zh-TW": "目前位置不在圖上",
	},
	// 고른 체인 안을 펼쳤다는 사실을 화면이 말한다(이슈 #114) — 안 말하면 사람은 "다른
	// 체인이 사라졌다"고 읽는다.
	"gitgraph.zoomed": {
		"ko": "체인 {chain} 안을 펼쳤다 — 형제 가지마다 제 줄. (선택을 '전체'로 되돌리면 층 레인으로 돌아간다)",
		"en": "Expanded inside chain {chain} — one lane per sibling branch. (Set the filter back to “all” for layer lanes)",
		"zh-CN": "已展开链 {chain} 的内部——每条兄弟分支各占一行。（把筛选器调回“全部”即可回到层泳道）",
		"zh-TW": "已展開鏈 {chain} 的內部——每條兄弟分支各占一行。（把篩選器調回「全部」即可回到層泳道）",
	},
	"gitgraph.empty": {
		"ko": "커밋이 없다.", "en": "No commits.", "zh-CN": "没有提交。", "zh-TW": "沒有提交。",
	},
	"viewer.partfail": {
		"ko": "⚠ 뷰어의 일부({name})를 그리지 못했다: {err}  — 나머지는 그대로 보인다.",
		"en": "⚠ One part of the viewer ({name}) failed to draw: {err}  — everything else is still shown.",
		"zh-CN": "⚠ 查看器的一部分（{name}）未能绘制：{err}——其余部分照常显示。",
		"zh-TW": "⚠ 檢視器的一部分（{name}）未能繪製：{err}——其餘部分照常顯示。",
	},

	// ── 전체맵 ──
	"map.head": {
		"ko": "전체맵", "en": "Overview map",
		"zh-CN": "全局图", "zh-TW": "全局圖",
	},
	"map.depth.chain": {
		"ko": "체인", "en": "Chain", "zh-CN": "链", "zh-TW": "鏈",
	},
	"map.depth.chain.title": {
		"ko": "체인 단위 — 국면 계보만",
		"en": "By chain — lineage of phases only",
		"zh-CN": "按链——只看阶段谱系", "zh-TW": "按鏈——只看階段譜系",
	},
	"map.depth.cycle": {
		"ko": "사이클", "en": "Cycle", "zh-CN": "循环", "zh-TW": "循環",
	},
	"map.depth.cycle.title": {
		"ko": "사이클 단위 — 각 사이클 상태·분기(⚡)",
		"en": "By cycle — each cycle's verdict and branching (⚡)",
		"zh-CN": "按循环——各循环的判定与分叉（⚡）",
		"zh-TW": "按循環——各循環的判定與分叉（⚡）",
	},
	"map.depth.step": {
		"ko": "스텝", "en": "Step", "zh-CN": "步骤", "zh-TW": "步驟",
	},
	"map.depth.step.title": {
		"ko": "스텝 단위 — 모든 스텝 커밋 DAG",
		"en": "By step — the full DAG of step commits",
		"zh-CN": "按步骤——所有步骤提交构成的 DAG",
		"zh-TW": "按步驟——所有步驟提交構成的 DAG",
	},

	// 전체맵 조작부 — 필터·줌. 그림을 항해하는 손잡이라 여기가 한국어로 남으면 그림만 영어인
	// 반쪽 화면이 된다.
	"map.filter.label": {
		"ko": "체인:", "en": "Chain:", "zh-CN": "链：", "zh-TW": "鏈：",
	},
	"map.filter.all": {
		"ko": "전체 ({n}개 체인)", "en": "All ({n} chains)",
		"zh-CN": "全部（{n} 条链）", "zh-TW": "全部（{n} 條鏈）",
	},
	"map.filter.only": {
		"ko": "— 이 체인만 그린다(다른 체인은 숨김). 계보 전체는 \"전체\".",
		"en": "— drawing this chain only (others hidden). Pick “All” for the whole lineage.",
		"zh-CN": "— 只绘制这条链（其他隐藏）。要看完整谱系请选“全部”。",
		"zh-TW": "— 只繪製這條鏈（其他隱藏）。要看完整譜系請選「全部」。",
	},
	"map.zoom.in": {
		"ko": "확대", "en": "Zoom in", "zh-CN": "放大", "zh-TW": "放大",
	},
	"map.zoom.out": {
		"ko": "축소", "en": "Zoom out", "zh-CN": "缩小", "zh-TW": "縮小",
	},
	"map.zoom.fit": {
		"ko": "전체", "en": "Fit", "zh-CN": "全览", "zh-TW": "全覽",
	},
	"map.zoom.fit.title": {
		"ko": "전체 보기(리셋)", "en": "Fit everything (reset)",
		"zh-CN": "全部显示（重置）", "zh-TW": "全部顯示（重置）",
	},
	"map.zoom.hint": {
		"ko": "Ctrl+휠=줌 · 확대 후 드래그=이동 · 미니맵 클릭=그 자리로",
		"en": "Ctrl+wheel = zoom · drag when zoomed = pan · click the minimap to jump there",
		"zh-CN": "Ctrl+滚轮＝缩放 · 放大后拖动＝平移 · 点击小地图＝跳到该处",
		"zh-TW": "Ctrl+滾輪＝縮放 · 放大後拖曳＝平移 · 點擊小地圖＝跳到該處",
	},
	// 그래프 안의 '작업중' 유령 노드 — 미커밋 작업이 어디서 벌어지는지.
	// 그림 안의 표식과 툴팁(#118). 여기 있는 것들은 사전을 거치지 않고 svgEl 인자로
	// 곧장 들어가 있어서, 영어 화면인데 그래프 안만 한국어로 남았다 — 사전 우회 시험이
	// `textContent=` 꼴만 봤기 때문에 아무도 못 봤다. 시험도 함께 넓혔다.
	"chain.mark.sealed": {
		"ko": "✓ 봉인", "en": "✓ sealed", "zh-CN": "✓ 封存", "zh-TW": "✓ 封存",
	},
	"chain.parent": {
		"ko": "부모: ", "en": "parent: ", "zh-CN": "父级：", "zh-TW": "父級：",
	},
	"chain.parent.more": {
		"ko": "또 하나의 부모: ", "en": "another parent: ",
		"zh-CN": "另一个父级：", "zh-TW": "另一個父級：",
	},
	"cycle.parent": {
		"ko": "부모 사이클: ", "en": "parent cycle: ",
		"zh-CN": "父循环：", "zh-TW": "父循環：",
	},
	"cycle.parent.more": {
		"ko": "또 하나의 부모 사이클: ", "en": "another parent cycle: ",
		"zh-CN": "另一个父循环：", "zh-TW": "另一個父循環：",
	},
	"cycle.inherited": {
		"ko": "물려받음: ", "en": "inherited: ", "zh-CN": "承继：", "zh-TW": "承繼：",
	},
	"cycle.exit.to": {
		"ko": "이어받은 곳: ", "en": "continued into: ",
		"zh-CN": "承接至：", "zh-TW": "承接至：",
	},
	"step.plan.badge": {
		"ko": "⚙ 설계", "en": "⚙ design", "zh-CN": "⚙ 设计", "zh-TW": "⚙ 設計",
	},
	"step.plan.broke.badge": {
		"ko": "⚠ 설계깨짐", "en": "⚠ design broken",
		"zh-CN": "⚠ 设计已破", "zh-TW": "⚠ 設計已破",
	},
	"step.plan.held": {
		"ko": "설계 유지", "en": "design held", "zh-CN": "设计维持", "zh-TW": "設計維持",
	},
	"step.plan.broke.tip": {
		"ko": "설계가 깨졌다: ", "en": "the design broke: ",
		"zh-CN": "设计被打破：", "zh-TW": "設計被打破：",
	},
	"step.declared.parent": {
		"ko": "선언된 부모: ", "en": "declared parent: ",
		"zh-CN": "声明的父级：", "zh-TW": "宣告的父級：",
	},
	"layer.dev.step": {
		"ko": "dev {n}걸음: ", "en": "dev step {n}: ",
		"zh-CN": "dev 第 {n} 步：", "zh-TW": "dev 第 {n} 步：",
	},
	"lane.commits": {
		"ko": " — 커밋 {n}개", "en": " — {n} commits",
		"zh-CN": " —— {n} 个提交", "zh-TW": " —— {n} 個提交",
	},
	"deploy.mark": {
		"ko": "배포 ", "en": "deploy ", "zh-CN": "发布 ", "zh-TW": "發布 ",
	},
	"deploy.target": {
		"ko": "대상: ", "en": "target: ", "zh-CN": "目标：", "zh-TW": "目標：",
	},

	// ── 사전을 비켜 가 있던 것들(#118 후속) ─────────────────────────────────
	//
	// 앞 릴리스가 SVG 라벨·툴팁을 옮겼지만, JS 안에는 아직 40여 줄이 남아 있었다: 카드
	// 제목·계보 칩·빈 상태·층 그래프 툴팁·서버 끊김 안내·정정 표식. 넓힌 시험도 이것들은
	// 못 잡았다 — **여러 줄에 걸친 삼항**이라 한 줄짜리 정규식을 비켜 갔기 때문이다.
	// 화면에 찍히는 글은 전부 여기를 지난다.
	"card.chain.title": {
		"ko": "{chain} — 사이클 {n}개", "en": "{chain} — cycles: {n}",
		"zh-CN": "{chain} — {n} 个循环", "zh-TW": "{chain} — {n} 個循環",
	},
	"card.cycle.title": {
		"ko": "{chain} / {cycle} — 스텝 {n}개", "en": "{chain} / {cycle} — steps: {n}",
		"zh-CN": "{chain} / {cycle} — {n} 个步骤", "zh-TW": "{chain} / {cycle} — {n} 個步驟",
	},

	// 정정(supersede) — 지우는 게 아니라 '살아있지 않다'를 보이는 것이다.
	"step.dup.tip": {
		"ko": "⚠ 이 번호를 쓰는 스텝이 여럿이다(옛 gil 의 번호 중복) — 정체성은 커밋 {sha} 이다",
		"en": "⚠ several steps share this number (duplicate numbering from older gil) — the commit {sha} is what identifies this one",
		"zh-CN": "⚠ 有多个步骤共用此编号（旧版 gil 的编号重复）——真正的身份是提交 {sha}",
		"zh-TW": "⚠ 有多個步驟共用此編號（舊版 gil 的編號重複）——真正的身分是提交 {sha}",
	},
	"step.plan.tip": {
		"ko": "⚙ 고정한 설계: ", "en": "⚙ design fixed in advance: ",
		"zh-CN": "⚙ 事先固定的设计：", "zh-TW": "⚙ 事先固定的設計：",
	},
	"step.plan.broke.tip2": {
		"ko": "⚠ 설계가 깨졌다: ", "en": "⚠ the design broke: ",
		"zh-CN": "⚠ 设计被打破：", "zh-TW": "⚠ 設計被打破：",
	},
	"step.advances.tip": {
		"ko": "◎ 목적에 다가서려는 몫: ", "en": "◎ how this means to advance the purpose: ",
		"zh-CN": "◎ 意图向目的推进之处：", "zh-TW": "◎ 意圖向目的推進之處：",
	},
	"step.toward.tip": {
		"ko": "◎ 목적에 다가선 정도: ", "en": "◎ how far it actually advanced the purpose: ",
		"zh-CN": "◎ 实际向目的推进的程度：", "zh-TW": "◎ 實際向目的推進的程度：",
	},
	"step.nextdesign.tip": {
		"ko": "◎ 다음 설계: ", "en": "◎ the next design: ",
		"zh-CN": "◎ 下一个设计：", "zh-TW": "◎ 下一個設計：",
	},
	"step.supersedes.tip": {
		"ko": "⟲ 이 스텝이 {id} 를 정정한다(그 자리에서 갈라졌다)",
		"en": "⟲ this step supersedes {id} (it forked at that very place)",
		"zh-CN": "⟲ 此步骤修正了 {id}（就在该处分岔）",
		"zh-TW": "⟲ 此步驟修正了 {id}（就在該處分岔）",
	},
	"step.gone.by": {
		"ko": "⤳ 구버전 — {id} 이 정정했다", "en": "⤳ superseded — {id} corrected it",
		"zh-CN": "⤳ 旧版——由 {id} 修正", "zh-TW": "⤳ 舊版——由 {id} 修正",
	},
	"step.gone.branch": {
		"ko": "⤳ 구버전 — 정정된 가지에 속한다",
		"en": "⤳ superseded — it belongs to a branch that was corrected",
		"zh-CN": "⤳ 旧版——属于已被修正的分支", "zh-TW": "⤳ 舊版——屬於已被修正的分支",
	},
	"step.gone.note": {
		"ko": "(지워지지 않았다: 이력에 그대로 남아 있고, 살아있는 계산에서만 빠진다)",
		"en": "(nothing was deleted: it stays in the history, and only drops out of the live reckoning)",
		"zh-CN": "（并未删除：它仍留在历史中，只是不再计入现行的计算）",
		"zh-TW": "（並未刪除：它仍留在歷史中，只是不再計入現行的計算）",
	},
	"step.supersede.badge": {
		"ko": "⟲ 정정 {id}", "en": "⟲ supersedes {id}",
		"zh-CN": "⟲ 修正 {id}", "zh-TW": "⟲ 修正 {id}",
	},
	"step.gone.badge": {
		"ko": "⤳ 구버전", "en": "⤳ superseded", "zh-CN": "⤳ 旧版", "zh-TW": "⤳ 舊版",
	},
	"step.supersede.badge.tip": {
		"ko": "이 스텝이 {id} 를 정정한다 — 옛 가지는 그대로 보존된다",
		"en": "this step supersedes {id} — the old branch is preserved untouched",
		"zh-CN": "此步骤修正了 {id}——旧分支原样保存",
		"zh-TW": "此步驟修正了 {id}——舊分支原樣保存",
	},
	"step.gone.badge.tip": {
		"ko": "정정으로 대체된 가지 — 이력엔 남는다",
		"en": "a branch replaced by a correction — it remains in the history",
		"zh-CN": "被修正取代的分支——仍留在历史中",
		"zh-TW": "被修正取代的分支——仍留在歷史中",
	},
	"step.gone.badge.tip.by": {
		"ko": "정정으로 대체된 가지 ({id} 이 정정) — 이력엔 남는다",
		"en": "a branch replaced by a correction ({id} corrected it) — it remains in the history",
		"zh-CN": "被修正取代的分支（由 {id} 修正）——仍留在历史中",
		"zh-TW": "被修正取代的分支（由 {id} 修正）——仍留在歷史中",
	},
	"step.here.badge": {
		"ko": "◀ 현재위치", "en": "◀ you are here",
		"zh-CN": "◀ 当前位置", "zh-TW": "◀ 目前位置",
	},

	// 작업중(미커밋) — 아직 스텝이 아닌 것을 스텝처럼 그리지 않는다.
	"work.branch": {
		"ko": "브랜치: ", "en": "branch: ", "zh-CN": "分支：", "zh-TW": "分支：",
	},
	"work.ahead": {
		"ko": "앵커 이후 평범한 커밋 {n}개", "en": "plain commits since the anchor: {n}",
		"zh-CN": "锚点之后有 {n} 个普通提交", "zh-TW": "錨點之後有 {n} 個普通提交",
	},
	"work.commit.hint": {
		"ko": "커밋하면 이 자리에 진짜 스텝이 선다.",
		"en": "Commit, and a real step will stand in this place.",
		"zh-CN": "提交之后，此处便会立起一个真正的步骤。",
		"zh-TW": "提交之後，此處便會立起一個真正的步驟。",
	},

	// 계보 칩(들어옴·낳음) — 이 스텝이 무엇에서 왔고 무엇을 낳았나.
	"chip.in": {
		"ko": "들어옴", "en": "came from", "zh-CN": "来自", "zh-TW": "來自",
	},
	"chip.out": {
		"ko": "낳음", "en": "led to", "zh-CN": "生出", "zh-TW": "生出",
	},
	"chip.start": {
		"ko": "시작점(대문에서)", "en": "start (from the front door)",
		"zh-CN": "起点（自大门）", "zh-TW": "起點（自大門）",
	},
	"chip.start.tip": {
		"ko": "이 체인의 첫 스텝 — 대문(루트)에서 시작",
		"en": "the first step of this chain — it starts at the front door (root)",
		"zh-CN": "本链的第一个步骤——始于大门（根）",
		"zh-TW": "本鏈的第一個步驟——始於大門（根）",
	},
	"chip.cross.chain": {
		"ko": "부모 체인 {chain} 의 종결 스텝에서 이어받음",
		"en": "inherited from the closing step of the parent chain {chain}",
		"zh-CN": "承继自父链 {chain} 的终结步骤",
		"zh-TW": "承繼自父鏈 {chain} 的終結步驟",
	},
	"chip.cross.cycle": {
		"ko": "부모 사이클 {cycle} 의 스텝에서 이어받음",
		"en": "inherited from a step of the parent cycle {cycle}",
		"zh-CN": "承继自父循环 {cycle} 的步骤",
		"zh-TW": "承繼自父循環 {cycle} 的步驟",
	},
	"chip.parent.step": {
		"ko": "부모 스텝", "en": "parent step", "zh-CN": "父步骤", "zh-TW": "父步驟",
	},
	"chip.child.chain": {
		"ko": "자식 체인 {chain} 이 여기서 이어받음",
		"en": "the child chain {chain} inherits from here",
		"zh-CN": "子链 {chain} 由此承继", "zh-TW": "子鏈 {chain} 由此承繼",
	},
	"chip.child.cycle": {
		"ko": "자식 사이클 {cycle} 이 여기서 이어받음",
		"en": "the child cycle {cycle} inherits from here",
		"zh-CN": "子循环 {cycle} 由此承继", "zh-TW": "子循環 {cycle} 由此承繼",
	},
	"chip.sibling.back": {
		"ko": "되돌아온 형제 가지", "en": "a sibling branch that came back",
		"zh-CN": "折返回来的兄弟分支", "zh-TW": "折返回來的兄弟分支",
	},
	"chip.next.step": {
		"ko": "다음 스텝", "en": "the next step", "zh-CN": "下一个步骤", "zh-TW": "下一個步驟",
	},
	"chip.leaf.dead": {
		"ko": "죽은 잎(벽) — 여기서 끝", "en": "dead leaf (a wall) — it ends here",
		"zh-CN": "死叶（墙）——到此为止", "zh-TW": "死葉（牆）——到此為止",
	},
	"chip.leaf": {
		"ko": "잎(여기서 끝)", "en": "leaf (it ends here)",
		"zh-CN": "叶（到此为止）", "zh-TW": "葉（到此為止）",
	},
	"chip.leaf.dead.tip": {
		"ko": "이 가지는 여기서 죽었다 — 조상 define 으로 되돌아가 다른 가지를 폈다",
		"en": "this branch died here — the thinking went back to an ancestor define and opened another branch",
		"zh-CN": "此分支到此死去——思考退回祖先的 define，另开一支",
		"zh-TW": "此分支到此死去——思考退回祖先的 define，另開一支",
	},
	"chip.leaf.tip": {
		"ko": "이 사이클의 결말 노드", "en": "the closing node of this cycle",
		"zh-CN": "本循环的结局节点", "zh-TW": "本循環的結局節點",
	},

	// 접힌 맵·빈 상태.
	"map.fold.subj.cycle": {
		"ko": "사이클 {name} — {n}스텝", "en": "cycle {name} — steps: {n}",
		"zh-CN": "循环 {name} — {n} 个步骤", "zh-TW": "循環 {name} — {n} 個步驟",
	},
	"map.fold.subj.chain": {
		"ko": "체인 {name} — {n}스텝", "en": "chain {name} — steps: {n}",
		"zh-CN": "链 {name} — {n} 个步骤", "zh-TW": "鏈 {name} — {n} 個步驟",
	},
	"map.fold.solved": {
		"ko": " ⚡분기 밟은 solved", "en": " ⚡solved after taking a branch",
		"zh-CN": " ⚡经分岔后解决", "zh-TW": " ⚡經分岔後解決",
	},
	"map.empty": {
		"ko": "아직 노드가 없다.", "en": "No nodes yet.",
		"zh-CN": "还没有节点。", "zh-TW": "還沒有節點。",
	},

	// 층 그래프(main·dev) — 갈라짐·합류·배포.
	"layer.main.tip": {
		"ko": "배포된 것만 온다 — 대문", "en": "only what has shipped arrives here — the front door",
		"zh-CN": "只有已发布的才抵达——大门", "zh-TW": "只有已發布的才抵達——大門",
	},
	"layer.dev.tip": {
		"ko": "모든 작업이 시작하는 층", "en": "the layer every piece of work starts from",
		"zh-CN": "一切工作起步的层", "zh-TW": "一切工作起步的層",
	},
	"layer.main.dot.tip": {
		"ko": "대문(main) — 여기서 층이 갈라진다",
		"en": "the front door (main) — the layer forks from here",
		"zh-CN": "大门（main）——层由此分出", "zh-TW": "大門（main）——層由此分出",
	},
	"layer.fork.tip": {
		"ko": "dev 는 대문에서 갈라진 층이다 (gil init)",
		"en": "dev is a layer forked from the front door (gil init)",
		"zh-CN": "dev 是自大门分出的层（gil init）", "zh-TW": "dev 是自大門分出的層（gil init）",
	},
	"layer.dev.start.tip": {
		"ko": "dev 층 시작", "en": "where the dev layer begins",
		"zh-CN": "dev 层的起点", "zh-TW": "dev 層的起點",
	},
	"layer.depart.tip": {
		"ko": "출발: dev → {chain} (계보상 시조 — 대문은 물려받는다)",
		"en": "departure: dev → {chain} (a founder in lineage — it still inherits the front door)",
		"zh-CN": "出发：dev → {chain}（谱系上的始祖——大门仍然承继）",
		"zh-TW": "出發：dev → {chain}（譜系上的始祖——大門仍然承繼）",
	},
	"layer.fork.dot.tip": {
		"ko": "갈라짐: dev → {chain}", "en": "fork: dev → {chain}",
		"zh-CN": "分岔：dev → {chain}", "zh-TW": "分岔：dev → {chain}",
	},
	"layer.merge.tip": {
		"ko": "합류: {chain} → dev (gil merge)", "en": "merge: {chain} → dev (gil merge)",
		"zh-CN": "合流：{chain} → dev（gil merge）", "zh-TW": "合流：{chain} → dev（gil merge）",
	},
	"layer.merge.dot.tip": {
		"ko": "합류: {chain} → dev", "en": "merge: {chain} → dev",
		"zh-CN": "合流：{chain} → dev", "zh-TW": "合流：{chain} → dev",
	},
	"deploy.leaf.tip": {
		"ko": "내보낸 잎: ", "en": "the leaf that shipped: ",
		"zh-CN": "送出的叶：", "zh-TW": "送出的葉：",
	},
	"deploy.leaf.lost.tip": {
		"ko": "귀속 스텝 미상 — 이 배포 계보에서 산 잎을 찾지 못했다",
		"en": "the owning step is unknown — no living leaf was found in this deploy's lineage",
		"zh-CN": "归属步骤不明——在此发布的谱系中未找到活叶",
		"zh-TW": "歸屬步驟不明——在此發布的譜系中未找到活葉",
	},
	"deploy.leaf.lost.badge": {
		"ko": " (귀속 스텝 미상)", "en": " (owning step unknown)",
		"zh-CN": "（归属步骤不明）", "zh-TW": "（歸屬步驟不明）",
	},

	// 날것의 git 그래프.
	"git.supersede.mark": {
		"ko": "  ⟲정정 {id}", "en": "  ⟲supersedes {id}",
		"zh-CN": "  ⟲修正 {id}", "zh-TW": "  ⟲修正 {id}",
	},
	"git.gone.mark": {
		"ko": "  ⤳구버전(정정으로 대체)", "en": "  ⤳superseded (replaced by a correction)",
		"zh-CN": "  ⤳旧版（被修正取代）", "zh-TW": "  ⤳舊版（被修正取代）",
	},
	"git.lane.other": {
		"ko": "(그 밖)", "en": "(the rest)", "zh-CN": "（其余）", "zh-TW": "（其餘）",
	},
	"git.layer.tip": {
		"ko": "층: ", "en": "layer: ", "zh-CN": "层：", "zh-TW": "層：",
	},

	// 인터뷰 카드의 상태 — 사람이 답을 냈고 에이전트가 그걸 읽었나.
	"interview.state.waiting": {
		"ko": "⏳ 에이전트가 기다리는 중", "en": "⏳ the agent is waiting",
		"zh-CN": "⏳ 代理正在等待", "zh-TW": "⏳ 代理正在等待",
	},
	"interview.state.seen": {
		"ko": "✓ 에이전트가 읽었습니다", "en": "✓ the agent has read it",
		"zh-CN": "✓ 代理已读", "zh-TW": "✓ 代理已讀",
	},
	"interview.state.unseen": {
		"ko": "· 아직 안 읽음", "en": "· not read yet",
		"zh-CN": "· 尚未读取", "zh-TW": "· 尚未讀取",
	},

	// 서버가 끊겼을 때. 이 줄이 한국어로만 남으면, 화면이 멈춘 이유를 못 읽는다.
	"disconnect.msg": {
		"ko": " ✕ 뷰어 서버에 닿지 못했습니다 — 이 페이지를 띄운 서버가 꺼졌거나 다시 떴습니다.",
		"en": " ✕ Cannot reach the viewer server — the server that served this page has stopped or restarted.",
		"zh-CN": " ✕ 无法连到查看器服务——提供本页的服务已停止或重启。",
		"zh-TW": " ✕ 無法連到檢視器服務——提供本頁的服務已停止或重啟。",
	},
	"disconnect.hint": {
		"ko": "<br>서버가 꺼져 있으면 터미널에서: <code>gil viewer serve</code>",
		"en": "<br>If the server is down, run in a terminal: <code>gil viewer serve</code>",
		"zh-CN": "<br>若服务已停止，请在终端运行：<code>gil viewer serve</code>",
		"zh-TW": "<br>若服務已停止，請在終端執行：<code>gil viewer serve</code>",
	},

	// 화면 조각의 이름 — 한 조각이 죽으면 이 이름이 그 자리에 뜬다(viewer.partfail).
	// 그 자리에서만 한국어로 남으면, 무엇이 죽었는지 못 읽는다.
	"part.gitgraph": {
		"ko": "git 그래프", "en": "the git graph", "zh-CN": "git 图", "zh-TW": "git 圖",
	},
	"part.stepmap": {
		"ko": "전체맵", "en": "the overview map", "zh-CN": "全景图", "zh-TW": "全景圖",
	},
	"part.chainzoom": {
		"ko": "체인그래프 줌", "en": "chain-graph zoom",
		"zh-CN": "链图缩放", "zh-TW": "鏈圖縮放",
	},
	"part.interviews": {
		"ko": "인터뷰 폼", "en": "the interview form", "zh-CN": "访谈表单", "zh-TW": "訪談表單",
	},
	"part.restoresel": {
		"ko": "선택 복원", "en": "restoring your selection",
		"zh-CN": "恢复选择", "zh-TW": "恢復選擇",
	},

	"map.work.label": {
		"ko": "작업중", "en": "working", "zh-CN": "进行中", "zh-TW": "進行中",
	},
	"map.work.label.pen": {
		"ko": "✎ 작업중", "en": "✎ working", "zh-CN": "✎ 进行中", "zh-TW": "✎ 進行中",
	},
	"map.work.tip": {
		"ko": "✎ 작업중(미커밋) — ", "en": "✎ working (uncommitted) — ",
		"zh-CN": "✎ 进行中（未提交）—— ", "zh-TW": "✎ 進行中（未提交）—— ",
	},

	"map.sprout": {
		"ko": "체인의 기준선에서 곧장 난 사이클 — 앞 사이클을 이어받은 것이 아니다(정석 발아).",
		"en": "This cycle sprouted straight from the chain's baseline — it did not inherit from a previous cycle.",
		"zh-CN": "此循环直接从链的基准线发芽——并非承继自前一个循环。",
		"zh-TW": "此循環直接從鏈的基準線發芽——並非承繼自前一個循環。",
	},

	// 전체맵(스텝) 범례. 은유가 많은 자리라 직역하지 않는다 — 각 언어에서 **읽히는 글**로
	// 다시 썼다. 뜻은 하나도 빼지 않되 문장은 그 언어의 것이다.
	"map.legend.step": {
		"ko": "gil 계보 그래프 — 왼→오른 흐름, 선은 gil 룰(같은 체인의 흐름 + 닫힌 끝에서 태어난 체인 계승)로만 잇는다. 계보가 없는 체인은 이어지지 않고 따로 선다(커밋 조상관계는 사실이지만 여기선 안 그린다 — 적층은 gil fsck 가 짚는다). 맨 위 두 줄=<b class=\"lg-main\">main</b>(대문, 배포된 것만 온다)·<b class=\"lg-dev\">dev</b>(모든 작업이 시작하는 층) — 층을 건너는 굵은 선이 출발·합류(gil merge)·배포(gil deploy)다. <b class=\"lg-dev\">dev 줄 위의 작은 점</b>은 그 층이 쌓은 커밋 하나 — 두 갈라짐 사이의 점을 세면 그 사이 dev 가 몇 걸음 갔는지 읽힌다(점에 올리면 제목이 뜬다). 점선 박스=사이클(박스 위 작은 글씨=사이클 이름), 점=스텝. <b>체인 이름은 점·박스에 올리면 뜬다</b>(글자를 줄여 그림을 살렸다). <b class=\"lg-cross\">주황</b>=체인 전환(부모 체인 종결→자식), <b class=\"lg-branch\">빨강 파선</b>=backtrack, <b class=\"lg-dead\">붉은 점</b>=죽은 잎, <b class=\"lg-alive\">초록 점</b>=산 잎, <b>🚀</b>=배포(공개) 지점, <b>▼</b>=현재위치(HEAD). 점 클릭 → 아래 상세.",
		"en": "The gil lineage graph — flows left to right. Lines are drawn only where gil's rules say one thing came from another: flow within a chain, and a chain born at another's closed end. A chain with no such lineage stands on its own rather than being joined (it may well be a commit descendant, but that is not lineage — <b>gil fsck</b> is what points out stacking). The top two rows are <b class=\"lg-main\">main</b> (the front door — only what has shipped arrives here) and <b class=\"lg-dev\">dev</b> (the layer every piece of work starts from); the thick lines crossing layers are departures, merges (<b>gil merge</b>) and deploys (<b>gil deploy</b>). Each <b class=\"lg-dev\">small dot on the dev row</b> is one commit that layer accumulated — count the dots between two forks and you can read how many steps dev took in between (hover a dot for its subject). Dotted box = cycle (small text above it is the cycle's name), dot = step. <b>Chain names appear on hover</b> over a dot or box — the drawing survives by keeping its labels short. <b class=\"lg-cross\">Orange</b> = crossing into a new chain (parent chain closed → child), <b class=\"lg-branch\">dashed red</b> = backtrack, <b class=\"lg-dead\">red dot</b> = dead leaf, <b class=\"lg-alive\">green dot</b> = living leaf, <b>🚀</b> = a deploy (made public), <b>▼</b> = where you are now (HEAD). Click a dot for the detail below.",
		"zh-CN": "gil 谱系图——由左向右流动。只有 gil 规则认定的承继关系才连线：同一条链内的流动，以及在另一条链的封闭末端诞生的链。没有这种谱系的链独立站立，不与他者相连（它在提交上或许确是后代，但那不是谱系——堆叠由 <b>gil fsck</b> 指出）。最上两行是 <b class=\"lg-main\">main</b>（大门，只有已发布的才抵达）与 <b class=\"lg-dev\">dev</b>（一切工作起步的层）；跨层的粗线是出发、合流（<b>gil merge</b>）与发布（<b>gil deploy</b>）。<b class=\"lg-dev\">dev 行上的小圆点</b>是该层累积的一个提交——数一数两次分叉之间的点，就能读出这期间 dev 走了几步（悬停可见标题）。虚线框＝循环（框上小字为循环名），圆点＝步骤。<b>链名需悬停在点或框上才显示</b>——把字缩短，图才活得下来。<b class=\"lg-cross\">橙色</b>＝跨入新链（父链终结→子链），<b class=\"lg-branch\">红色虚线</b>＝回溯，<b class=\"lg-dead\">红点</b>＝死叶，<b class=\"lg-alive\">绿点</b>＝活叶，<b>🚀</b>＝发布（公开）之处，<b>▼</b>＝当前位置（HEAD）。点击圆点查看下方详情。",
		"zh-TW": "gil 譜系圖——由左向右流動。只有 gil 規則認定的承繼關係才連線：同一條鏈內的流動，以及在另一條鏈的封閉末端誕生的鏈。沒有這種譜系的鏈獨立站立，不與他者相連（它在提交上或許確是後代，但那不是譜系——堆疊由 <b>gil fsck</b> 指出）。最上兩列是 <b class=\"lg-main\">main</b>（大門，只有已發布的才抵達）與 <b class=\"lg-dev\">dev</b>（一切工作起步的層）；跨層的粗線是出發、合流（<b>gil merge</b>）與發布（<b>gil deploy</b>）。<b class=\"lg-dev\">dev 列上的小圓點</b>是該層累積的一個提交——數一數兩次分叉之間的點，就能讀出這期間 dev 走了幾步（滑過可見標題）。虛線框＝循環（框上小字為循環名），圓點＝步驟。<b>鏈名需滑過點或框才顯示</b>——把字縮短，圖才活得下來。<b class=\"lg-cross\">橙色</b>＝跨入新鏈（父鏈終結→子鏈），<b class=\"lg-branch\">紅色虛線</b>＝回溯，<b class=\"lg-dead\">紅點</b>＝死葉，<b class=\"lg-alive\">綠點</b>＝活葉，<b>🚀</b>＝發布（公開）之處，<b>▼</b>＝目前位置（HEAD）。點擊圓點查看下方詳情。",
	},
	// 접힌 맵의 범례는 단위(사이클/체인)에 따라 문장이 갈린다. 한 문장 안에서 조건으로 갈면
	// 어순이 다른 언어에서 부서지므로 **두 키로 나눈다**.
	"map.legend.folded.cycle": {
		"ko": "사이클 단위 접힌 맵(<b>gil log --depth</b> 뷰어판) — 노드 하나=한 사이클. <b class=\"lg-alive\">초록</b>=solved(산 잎 있음), <b class=\"lg-dead\">붉음</b>=dead, <b>⚡</b>=분기 밟은 solved(죽은 잎도 품음, 일자 solved 와 구분). 엣지=계보. 노드 클릭 → 그 사이클 첫 스텝으로 이동.",
		"en": "Folded map, one node per cycle (the viewer's <b>gil log --depth</b>) — <b class=\"lg-alive\">green</b> = solved (a living leaf exists), <b class=\"lg-dead\">red</b> = dead, <b>⚡</b> = solved after branching (it holds dead leaves too — that is what sets it apart from a straight-line solve). Edges are lineage. Click a node to jump to that cycle's first step.",
		"zh-CN": "折叠图，一个节点＝一个循环（查看器版的 <b>gil log --depth</b>）——<b class=\"lg-alive\">绿色</b>＝已解决（尚有活叶），<b class=\"lg-dead\">红色</b>＝死亡，<b>⚡</b>＝经过分叉才解决（其中也含死叶，与一路直行的解决相区别）。连线即谱系。点击节点跳到该循环的第一个步骤。",
		"zh-TW": "摺疊圖，一個節點＝一個循環（檢視器版的 <b>gil log --depth</b>）——<b class=\"lg-alive\">綠色</b>＝已解決（尚有活葉），<b class=\"lg-dead\">紅色</b>＝死亡，<b>⚡</b>＝經過分叉才解決（其中也含死葉，與一路直行的解決相區別）。連線即譜系。點擊節點跳到該循環的第一個步驟。",
	},
	"map.legend.folded.chain": {
		"ko": "체인 단위 접힌 맵(<b>gil log --depth</b> 뷰어판) — 노드 하나=한 체인. <b class=\"lg-alive\">초록</b>=solved(산 잎 있음), <b class=\"lg-dead\">붉음</b>=dead, <b>⚡</b>=분기 밟은 solved(죽은 잎도 품음, 일자 solved 와 구분). 엣지=계보. 노드 클릭 → 그 체인 첫 사이클로 이동.",
		"en": "Folded map, one node per chain (the viewer's <b>gil log --depth</b>) — <b class=\"lg-alive\">green</b> = solved (a living leaf exists), <b class=\"lg-dead\">red</b> = dead, <b>⚡</b> = solved after branching (it holds dead leaves too — that is what sets it apart from a straight-line solve). Edges are lineage. Click a node to jump to that chain's first cycle.",
		"zh-CN": "折叠图，一个节点＝一条链（查看器版的 <b>gil log --depth</b>）——<b class=\"lg-alive\">绿色</b>＝已解决（尚有活叶），<b class=\"lg-dead\">红色</b>＝死亡，<b>⚡</b>＝经过分叉才解决（其中也含死叶，与一路直行的解决相区别）。连线即谱系。点击节点跳到该链的第一个循环。",
		"zh-TW": "摺疊圖，一個節點＝一條鏈（檢視器版的 <b>gil log --depth</b>）——<b class=\"lg-alive\">綠色</b>＝已解決（尚有活葉），<b class=\"lg-dead\">紅色</b>＝死亡，<b>⚡</b>＝經過分叉才解決（其中也含死葉，與一路直行的解決相區別）。連線即譜系。點擊節點跳到該鏈的第一個循環。",
	},
}

// i18nMissing — 사전에서 비어 있는 (키, 언어) 짝을 모두 돌려준다. 시험이 이걸 단언한다:
// **조용히 한국어로 떨어지면 낡은 화면을 아무도 모른다.** 방금 고친 버전 문의와 같은 실패다.
func i18nMissing() []string {
	var out []string
	for key, byLang := range i18nDict {
		for _, l := range i18nLangs {
			if strings.TrimSpace(byLang[l]) == "" {
				out = append(out, key+"/"+l)
			}
		}
		for l := range byLang {
			if !i18nSupported(l) {
				out = append(out, key+"/"+l+" (모르는 언어)")
			}
		}
	}
	sort.Strings(out)
	return out
}

func i18nSupported(l string) bool {
	for _, s := range i18nLangs {
		if s == l {
			return true
		}
	}
	return false
}

// i18nT — 서버가 마크업에 박아 둘 기본 글(한국어). JS 가 죽어도 화면이 비지 않게 하는 자리다.
func i18nT(key string) string { return i18nDict[key]["ko"] }

// i18nAttr — `data-i18n="키"` 속성. 마크업에서 글 바로 앞에 붙인다.
func i18nAttr(key string) string { return ` data-i18n="` + key + `"` }

// i18nArgs — 자리표시자 값. JSON 으로 실어 보내고 화면에서 채운다.
func i18nArgs(kv map[string]string) string {
	b, err := json.Marshal(kv)
	if err != nil {
		return ""
	}
	return ` data-i18n-args='` + string(b) + `'`
}

// depthBtn — 전체맵의 뎁스 버튼 하나(체인·사이클·스텝). 라벨과 툴팁이 둘 다 사전을 탄다 —
// 툴팁만 한국어로 남는 반쪽 화면을 만들지 않으려면 한자리에서 같이 짓는 편이 안전하다.
func depthBtn(depth, extraAttr string) string {
	return `<button data-depth="` + depth + `"` + extraAttr +
		` title="` + i18nT("map.depth."+depth+".title") + `" data-i18n-title="map.depth.` + depth + `.title"` +
		i18nAttr("map.depth."+depth) + `>` + i18nT("map.depth."+depth) + `</button>`
}

// i18nPayload — 페이지에 실을 사전 + 기본 언어. 통째로 보낸다(네 언어 다 합쳐 수십 KB 이내라
// 언어마다 왕복하는 것보다 싸고, 무엇보다 **서버 없는 정적 출력에서도 토글이 돈다**).
func i18nPayload() string {
	b, err := json.Marshal(map[string]any{
		"langs":   i18nLangs,
		"names":   i18nLangNames,
		"default": viewerLang,
		"dict":    i18nDict,
	})
	if err != nil {
		return "{}"
	}
	return string(b)
}
