// MCP roots — 호스트가 연 폴더를 **규범대로** 물어본다.
//
// 왜. mcp.go 는 저장소를 `--repo > CLAUDE_PROJECT_DIR > 현재 위치` 로 찾았다. 그런데
// CLAUDE_PROJECT_DIR 은 **Claude Code 가 넣어주는 벤더 환경변수**다. Claude Desktop 은 그걸
// 안 넣는다 — 그래서 Desktop 에서는 target 이 비고, 프로세스가 뜬 자리(대개 저장소 밖)를
// 그대로 썼다. 결과는 조용한 실패가 아니라 **전면 불능**이었다: gil_graph 든 gil_log 든
// 첫 줄에서 `fatal: ... .git 저장소가 아닙니다` 로 죽었고, 사람은 그걸 렌더링 실패로 읽었다
// (실측: MCP Apps 위젯이 뜨려다 이 에러로 멈췄다 — 화면 문제가 아니라 저장소 실종이었다).
//
// MCP 에는 이걸 위한 표준 기구가 있다: **roots**. 호스트가 "지금 열린 워크스페이스는 여기"를
// 서버에 알려주는 규범이고, 벤더에 안 묶인다. mcp.go 주석이 약속한 "사람이 여는 폴더마다 gil
// 이 알아서 따라붙는다 — 등록은 한 번, 경로는 사람이 몰라도 된다"는 지금까지 Claude Code
// 에서만 지켜졌다. roots 를 읽으면 그 약속이 **호스트를 가리지 않고** 선다.
//
// 우선순위: --repo > roots > CLAUDE_PROJECT_DIR > 현재 위치.
// roots 를 환경변수보다 위에 두는 이유는 roots 가 **세션마다 갱신되는 지금의 사실**이기
// 때문이다. 환경변수는 프로세스가 뜰 때 한 번 박히고 그 뒤 사람이 폴더를 옮겨도 안 바뀐다.
package main

import (
	"context"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

var (
	rootsMu sync.Mutex
	// rootsSettled — 이 세션의 저장소를 roots 로 정했거나, 물어봤는데 못 얻는다고 판정했다.
	// 한 번 정해지면 다시 묻지 않는다(툴 호출마다 RPC 를 왕복하지 않게).
	rootsSettled bool
	// mcpRepoPinned — 설정에 --repo 가 박혀 있으면 그 절대경로. 비면 안 박은 것.
	mcpRepoPinned string
)

// ── 호출마다 오는 저장소 (roots 를 안 주는 호스트를 위한 길) ──
//
// 왜 필요한가. roots 는 규범이지만 **모든 호스트가 구현하지는 않는다**. 실측: Claude Desktop
// 이 띄운 gil 은 `/` 에 서 있었고 roots 를 선언하지 않아 우리가 물을 수조차 없었다. 그때
// 그 자리의 에이전트는 이렇게 답했다 — "이 툴은 인자를 받지 않아서 저장소 경로를 지정할 수
// 없습니다". **그 에이전트는 올바른 경로를 알고 있었다.** 아는 것을 전할 구멍이 없었을 뿐이다.
//
// 설정에 박는 --repo 와 다른 점이 핵심이다: --repo 는 한 번 박히면 이후 모든 프로젝트·모든
// 세션에 영원히 적용된다(#51 이 그래서 거부까지 올라갔다). repo 인자는 **그 호출 하나**에만
// 산다. 다음 호출이 다른 저장소를 말하면 그리로 간다 — 박히지 않으니 낡지도 않는다.
type inRepo struct {
	Repo string `json:"repo,omitempty" jsonschema:"이 명령을 적용할 저장소의 절대경로. 호스트가 연 폴더를 gil 이 스스로 알아내면(MCP roots) 비워 둬라 — 그게 기본이다. 다만 roots 를 안 주는 호스트에서는 gil 이 엉뚱한 폴더에 서고 '깃 저장소가 아닙니다'로 죽는다. 그럴 때 지금 사람이 보고 있는 저장소의 경로를 여기 적어라."`
}

func (r inRepo) repoArg() string { return r.Repo }

// hasRepo — 입력 구조체가 repo 인자를 실어 나르는가(embed 로 대부분이 그렇다).
type hasRepo interface{ repoArg() string }

// adoptCallRepo — 호출이 실어 온 저장소로 옮긴다. 이 호출에만 유효하다.
//
// roots 보다 **위**에 둔다. roots 는 호스트가 "워크스페이스는 여기"라고 말하는 것이고,
// repo 인자는 에이전트가 "지금 이 명령은 여기다"라고 말하는 것이다 — 더 구체적인 쪽이 이긴다.
// 멀티 루트 워크스페이스에서 다른 저장소를 만질 때도 이 길이 유일하다.
func adoptCallRepo(in any) {
	h, ok := in.(hasRepo)
	if !ok || strings.TrimSpace(h.repoArg()) == "" {
		return
	}
	abs, err := filepath.Abs(h.repoArg())
	if err != nil {
		die("거부: 저장소 경로를 해석하지 못했다: " + h.repoArg())
	}
	if _, err := gitTryIn(abs, "rev-parse", "--git-dir"); err != nil {
		die("거부: repo 로 준 경로가 git 저장소가 아니다: " + abs + "\n" +
			"  사람이 보고 있는 폴더의 **최상위**(.git 이 있는 자리)를 적어라.\n" +
			"  거기서 시작하는 것이라면 먼저 gil_init 을 그 경로로 불러라.")
	}
	if os.Chdir(abs) != nil {
		die("거부: 저장소 경로로 이동 못 함: " + abs)
	}
	repoSource = repoSourceArg
	stopGitCache() // 옮겼으니 앞서 읽어 둔 것은 다른 저장소의 것이다
}

// repoSource — 지금 선 자리를 **무엇이 정했나**. 진단에 쓴다.
//
// 왜 남기나. 이 결함을 쫓는 데 Claude 로그와 lsof 가 필요했다 — 도구가 "나는 누가 불렀고
// 어디에 서 있나"를 안 말했기 때문이다(#110 이 뷰어에서 고친 것과 같은 병: 화면에 정체가
// 없으면 사람은 남의 그래프를 보며 자기 것이 비었다고 오진한다). 도구가 스스로 밝히면
// 다음 어긋남은 한 줄로 끝난다.
var repoSource = repoSourceUnchosen

// 자리를 정한 것들. **문자열을 코드 여기저기에 흩지 않는다** — 이 값으로 판정하는 자리가
// 생겼기 때문이다(세계를 세워도 되는 자리인가: start.go 의 requireChosenPlace).
const (
	repoSourceUnchosen = "프로세스가 뜬 자리" // 아무도 고르지 않았다 — 프로세스가 어쩌다 뜬 곳
	repoSourceRoots    = "호스트가 준 roots"
	repoSourceArg      = "호출 인자(repo)"
	repoSourceFlag     = "설정의 --repo"
	repoSourceEnv      = "호스트가 준 CLAUDE_PROJECT_DIR"
)

// mcpClient — 초기화 때 호스트가 밝힌 자기 이름. 어느 호스트에서 어긋났는지가 곧 단서다.
var mcpClient string

// installRootsMiddleware — 모든 수신 요청 앞에 선다. 툴이든 리소스 읽기든, 실제 일을
// 하기 전에 저장소가 정해져 있게 한다. 핸들러마다 훅을 심으면 새 툴이 늘 때 빠뜨린다 —
// 빠뜨린 그 하나가 "어떤 명령은 되고 어떤 명령은 안 되는" 경로별 침묵을 만든다.
func installRootsMiddleware(s *mcp.Server) {
	s.AddReceivingMiddleware(func(next mcp.MethodHandler) mcp.MethodHandler {
		return func(ctx context.Context, method string, req mcp.Request) (mcp.Result, error) {
			if ss, ok := req.GetSession().(*mcp.ServerSession); ok {
				adoptHostRoot(ctx, ss)
			}
			return next(ctx, method, req)
		}
	})
}

// adoptHostRoot — 호스트에게 roots 를 물어 그 폴더로 옮긴다(한 세션에 한 번).
//
// 실패해도 죽이지 않는다. roots 를 안 내는 호스트가 있고(구버전·최소 구현), 그때는 옛 경로
// (환경변수 → 현재 위치)가 그대로 답이다. **없는 기구를 못 썼다고 되는 것까지 막지 않는다.**
func adoptHostRoot(ctx context.Context, ss *mcp.ServerSession) {
	rootsMu.Lock()
	defer rootsMu.Unlock()
	if rootsSettled {
		return
	}
	// initialize 가 끝나기 전에는 물을 수 없다(SDK 가 거부한다). 아직이면 다음 요청에 다시 온다.
	ip := ss.InitializeParams()
	if ip == nil {
		return
	}
	if ip.ClientInfo != nil {
		mcpClient = strings.TrimSpace(ip.ClientInfo.Name + " " + ip.ClientInfo.Version)
	}
	// 클라이언트가 roots 를 **선언하지 않았으면 묻지 않는다.** 물으면 답할 의무가 없는 쪽에
	// 요청을 보내는 것이고, 안 오는 답을 기다리다 세션이 통째로 멈춘다(전체 시험이 10분을
	// 넘겨 서는 것으로 실측했다 — 옛 MCP 시험의 클라이언트는 roots/list 에 답하지 않는다).
	// 규범이 준 신호가 있으면 그걸 읽는다. 짐작으로 물어보지 않는다.
	if ip.Capabilities == nil || ip.Capabilities.RootsV2 == nil {
		rootsSettled = true
		return
	}
	// 선언했더라도 답이 안 올 수 있다(선언과 구현이 갈리는 호스트). 기다림에 끝을 둔다 —
	// 저장소를 못 찾는 것보다 **영원히 안 돌아오는 것**이 나쁘다.
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	res, err := ss.ListRoots(ctx, nil)
	if err != nil || res == nil || len(res.Roots) == 0 {
		rootsSettled = true
		return
	}
	rootsSettled = true

	pick := pickRepoRoot(res.Roots)
	if pick == "" {
		return
	}
	// --repo 가 호스트의 정답을 덮으면 거부한다(이슈 #51 의 판정을 roots 로 확장).
	// 환경변수에 대해 이미 서 있던 문을 roots 에도 세운다 — 두 창구가 다른 규칙을 쓰면
	// 어느 쪽으로 들어왔느냐가 안전을 정하게 된다.
	if mcpRepoPinned != "" {
		if mcpRepoPinned != pick {
			mcpRepoMismatch = repoMismatchMessage(mcpRepoPinned, pick)
		}
		return // --repo 가 최우선 — 어긋남은 위에서 고지한다.
	}
	if os.Chdir(pick) != nil {
		return
	}
	repoSource = repoSourceRoots
	// 옮겼으니 앞서 읽어 둔 것은 다른 저장소의 것이다.
	stopGitCache()
}

// pickRepoRoot — roots 중 실제로 쓸 폴더 하나. **git 저장소인 것을 먼저** 고른다.
//
// 호스트는 워크스페이스를 여럿 열 수 있고(멀티 루트), 그중 git 저장소가 아닌 것도 섞인다.
// 첫 번째를 무조건 집으면 사람이 보는 저장소가 아닌 곳에 붙는다 — #51 이 환경변수에서 이미
// 겪은 그 사고다. git 저장소가 하나도 없으면 첫 루트를 돌려준다(그 자리에서 gil_init 을
// 부를 수 있게 — 빈 폴더에서 시작하는 것은 정당한 길이다).
func pickRepoRoot(roots []*mcp.Root) string {
	var first string
	for _, r := range roots {
		p := rootPath(r)
		if p == "" {
			continue
		}
		if first == "" {
			first = p
		}
		if _, err := gitTryIn(p, "rev-parse", "--git-dir"); err == nil {
			return p
		}
	}
	return first
}

// rootPath — file:// URI 를 로컬 절대경로로. 규범상 roots 는 file:// 만 온다.
func rootPath(r *mcp.Root) string {
	if r == nil || r.URI == "" {
		return ""
	}
	if !strings.HasPrefix(r.URI, "file://") {
		return ""
	}
	u, err := url.Parse(r.URI)
	if err != nil {
		return ""
	}
	// url.Parse 는 %20 등을 u.Path 에 이미 풀어 담는다.
	abs, err := filepath.Abs(u.Path)
	if err != nil {
		return ""
	}
	return abs
}

// repoMismatchMessage — mcp.go 가 환경변수용으로 쓰던 문안을 한 곳으로 모은다.
// 두 자리에서 따로 쓰면 한쪽만 고쳐지고, 그러면 같은 사고에 대해 도구가 두 말을 한다.
func repoMismatchMessage(pinned, host string) string {
	return "거부: 설정의 --repo 가 지금 열린 폴더를 덮어쓰고 있다.\n" +
		"  --repo(설정에 박힌 곳): " + pinned + "\n" +
		"  지금 열린 폴더:        " + host + "\n" +
		"  이대로 두면 사람이 보는 폴더가 아닌 곳에 기록이 쌓인다 — 아무 에러도 없이.\n" +
		"  (실측: 같은 폴더에서 사람은 체인 2개를, 에이전트는 0개를 봤다.)\n\n" +
		"  고치는 법 — MCP 설정에서 \"--repo\" 인자만 빼라. 그러면 gil 이 열린 폴더를\n" +
		"  자동으로 따라간다(세션마다 새로 해석한다). 보통 ~/.claude.json 에 있고,\n" +
		"  gil 을 처음 시험하던 폴더가 그대로 박혀 있는 경우가 대부분이다:\n" +
		"    \"args\": [\"mcp\", \"serve\"]      ← 이렇게 (--repo 없이)\n" +
		"  고친 뒤 앱을 완전히 종료했다 다시 켜라.\n\n" +
		"  사람에게는 이렇게 말해라: \"설정에 예전 테스트 폴더가 박혀 있어서, 지금 보고\n" +
		"  계신 폴더가 아닌 곳에 기록이 쌓이게 돼 있어요. 설정 한 줄만 지우면 됩니다.\""
}
