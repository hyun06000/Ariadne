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
