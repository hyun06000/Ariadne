package main

import "github.com/modelcontextprotocol/go-sdk/mcp"

// 툴 주석 — 이 툴이 무엇을 하는 종류인가.
//
// **왜 필요한가.** 커넥터 디렉터리 심사가 "전 툴에 title 과 해당하는 힌트
// (readOnlyHint 또는 destructiveHint)가 있어야 한다"를 통과 조건으로 건다. 그런데 이건
// 심사 때문만이 아니다 — 호스트는 이 힌트로 **자동 승인**을 가른다: 읽기 전용은 사람 확인
// 없이 돌고, 파괴적인 것은 늘 묻는다. 힌트가 없으면 규범의 기본값(destructive=true)이
// 적용되어 **읽기만 하는 툴에도 매번 확인 창이 뜬다.** 비개발자에게는 그 확인 창 하나하나가
// 진입장벽이다. 즉 이 표는 심사 서류가 아니라 사용감이다.
//
// **열거가 아니라 규칙으로 센다.** 이 저장소가 여러 번 값을 치른 자리다 — 열거는 늘 뒤늦다.
// 그래서 두 겹으로 놓는다:
//
//	① 표에 없는 툴은 **가장 안전한 쪽**으로 떨어진다(읽기 전용 아님·파괴적임). 잊으면
//	   위험해지는 게 아니라 **번거로워진다** — 반대 방향의 기본값은 사고를 만든다.
//	② 그리고 표에 없다는 사실 자체를 **시험이 잡는다**(TestEveryToolIsAnnotated). 새 툴을
//	   만든 사람은 분류를 고를 때까지 초록을 못 본다. 판단을 미루지 못하게 하는 것이 핵심이고,
//	   기본값은 그 사이의 안전망일 뿐이다.
//
// **openWorldHint 를 함께 적는다.** gil 이 말을 거는 상대는 이 기계의 git 저장소뿐이다
// (버전 문의만 예외인데 그건 툴이 아니라 세션 앞머리에서 일어난다). 닫힌 세계라고 밝히면
// 호스트가 "이 툴이 바깥으로 무엇을 흘릴까"를 덜 의심한다 — 사실이니 적는다.
// **title 만 영어다 — 설명은 한국어인데.** 일부러 그렇다(상현님, 2026-08-11).
//
// 둘은 읽는 사람이 다르다. 설명은 이 서버를 실제로 쓰는 에이전트와 사람이 읽고, 이 도구의
// 문법·규범이 한국어로 서 있으니 거기 맞춘다. **title 은 그 앞에서 읽힌다** — 커넥터
// 디렉터리의 목록, 호스트의 권한 확인 창, 툴 목록의 한 줄. 즉 아직 gil 을 모르는 사람이
// 처음 보는 글자다. 그 자리를 한국어로 두면 목록에서 무엇인지 알 수 없는 항목이 된다.
//
// 짧게 쓴다. 이 자리는 문장이 아니라 **이름**이다.
type toolKind struct {
	Title string
	// ReadOnly — 환경을 안 바꾼다. 참이면 destructive 는 뜻이 없다(규범).
	ReadOnly bool
	// Destructive — 되돌리기 어려운 변경(지우기·덮어쓰기). 거짓이면 **더하기만** 한다.
	//
	// gil 의 성격상 대부분이 여기다: 사고 이력은 커밋 그래프에 **쌓이는** 것이라,
	// 스텝을 남기고 사이클을 닫는 것은 아무것도 지우지 않는다. 지우는 것은 정리(prune)와
	// 문서 덮어쓰기(global write)뿐이다.
	Destructive bool
	// Idempotent — 같은 인자로 다시 불러도 더 바뀌는 것이 없다.
	Idempotent bool
}

// toolKinds — 툴 이름 → 그 툴이 무엇을 하는가.
//
// 분류의 기준은 **커밋 그래프에 무슨 일이 일어나는가** 하나다. 화면을 여는지, 사람이
// 누르는 자리인지는 여기서 안 센다 — 그건 다른 축이고 surface.go 가 센다.
var toolKinds = map[string]toolKind{
	// ── 읽기만 한다 ────────────────────────────────────────────────────────────
	// 사람 확인 없이 도는 것이 옳은 자리다. "지금 어디인가"를 물을 때마다 확인 창이 뜨면
	// 아무도 안 묻게 되고, 안 물으면 추측으로 다음 수를 정한다.
	"gil_log":              {Title: "Read the reasoning graph", ReadOnly: true, Idempotent: true},
	"gil_fsck":             {Title: "Check graph integrity", ReadOnly: true, Idempotent: true},
	"gil_handoff":          {Title: "Report state for handoff", ReadOnly: true, Idempotent: true},
	"gil_context":          {Title: "Read accumulated findings", ReadOnly: true, Idempotent: true},
	"gil_status":           {Title: "Show current progress", ReadOnly: true, Idempotent: true},
	"gil_graph":            {Title: "Show the reasoning graph", ReadOnly: true, Idempotent: true},
	"gil_status_card":      {Title: "Fetch status card (app only)", ReadOnly: true, Idempotent: true},
	"gil_interview_status": {Title: "Check interview status", ReadOnly: true, Idempotent: true},
	"gil_global_read":      {Title: "Read agent existence records", ReadOnly: true, Idempotent: true},
	"gil_memory_read":      {Title: "Read agent memory", ReadOnly: true, Idempotent: true},
	// 기다리는 것은 바꾸는 것이 아니다 — 사람이 누를 때까지 서 있을 뿐이다.
	"gil_interview_wait": {Title: "Wait for interview answers", ReadOnly: true},
	"gil_start_wait":     {Title: "Wait for the start button", ReadOnly: true},

	// ── 더하기만 한다 ──────────────────────────────────────────────────────────
	// 사고 이력은 쌓이는 것이다. 스텝·사이클·체인은 커밋을 **얹을** 뿐 아무것도 안 지운다.
	"gil_init":             {Title: "Set up this folder for gil", Destructive: false},
	"gil_start":            {Title: "Start a project (one onboarding step)", Destructive: false},
	"gil_start_here":       {Title: "Start here (app only)", Destructive: false},
	"gil_intake":           {Title: "Open the kickoff interview", Destructive: false},
	"gil_interview":        {Title: "Interview for success criteria", Destructive: false},
	"gil_interview_submit": {Title: "Submit interview answers (app only)", Destructive: false},
	"gil_chain":            {Title: "Open a chain", Destructive: false},
	"gil_open":             {Title: "Open a cycle", Destructive: false},
	"gil_step":             {Title: "Record a step", Destructive: false},
	"gil_close":            {Title: "Close a cycle", Destructive: false},
	"gil_chain_close":      {Title: "Seal a chain", Destructive: false},
	"gil_merge":            {Title: "Merge completed work", Destructive: false},
	"gil_deploy":           {Title: "Record a deployment", Destructive: false},
	"gil_adopt":            {Title: "Adopt the winning branch", Destructive: false},
	"gil_approve":          {Title: "Approve (human decision)", Destructive: false},
	"gil_reject":           {Title: "Reject (human decision)", Destructive: false},
	"gil_memory_append":    {Title: "Append a memory knot", Destructive: false},
	// 자리를 옮기는 것은 이력을 안 바꾼다 — git 의 checkout 과 같다. 다만 두 번 불러도
	// 같은 자리이므로 idempotent 다.
	"gil_goto":           {Title: "Move within the reasoning tree", Destructive: false, Idempotent: true},
	"gil_prune_withdraw": {Title: "Withdraw a deletion request", Destructive: false, Idempotent: true},

	// ── 지우거나 덮어쓴다 ──────────────────────────────────────────────────────
	// **여기는 늘 사람에게 묻는 자리다.** 자동 승인이 되면 안 된다.
	"gil_prune_approve": {Title: "Approve deletion (irreversible)", Destructive: true},
	// **가르고 나니 분류가 사실이 됐다.** 겸용이던 동안은 읽기까지 파괴적으로 적어야 했다
	// (둘 중 하나가 파괴적이면 그 툴이 파괴적이다) — 즉 안전한 동작이 위험한 이웃 때문에
	// 확인 창을 받고 있었다. 가르는 것이 심사 통과보다 먼저 **사실을 말할 수 있게** 한다.
	"gil_global_write": {Title: "Write existence record (overwrites)", Destructive: true},
	"gil_global_mv":    {Title: "Move an existence record", Destructive: true},
}

// toolAnn — 이 툴의 주석. **표에 없으면 가장 안전한 쪽으로 떨어진다**(읽기 전용 아님·
// 파괴적임). 그래야 잊은 것이 사고가 아니라 번거로움이 된다. 그리고 그 사실은
// TestEveryToolIsAnnotated 가 잡는다 — 기본값은 안전망이지 대답이 아니다.
func toolAnn(name string) *mcp.ToolAnnotations {
	k, ok := toolKinds[name]
	if !ok {
		yes := true
		return &mcp.ToolAnnotations{Title: name, DestructiveHint: &yes}
	}
	a := &mcp.ToolAnnotations{
		Title:          k.Title,
		ReadOnlyHint:   k.ReadOnly,
		IdempotentHint: k.Idempotent,
	}
	// **읽기 전용이면 destructive 를 적지 않는다** — 규범이 "ReadOnlyHint 가 참일 때
	// 이 값은 뜻이 없다"고 정한다. 적으면 서로 어긋나 보이고, 어긋나 보이는 선언은
	// 읽는 쪽이 둘 다 안 믿게 만든다.
	if !k.ReadOnly {
		d := k.Destructive
		a.DestructiveHint = &d
	}
	// gil 이 말을 거는 상대는 이 기계의 git 저장소뿐이다 — 닫힌 세계다.
	no := false
	a.OpenWorldHint = &no
	return a
}
