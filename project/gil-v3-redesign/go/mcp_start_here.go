// mcp_start_here.go — **화면의 "여기에 시작한다" 버튼이 도는 자리.**
//
// 왜 `gil_start` 와 따로인가. 두 가지가 다르다.
//
// ① **승낙의 출처가 다르다.** `gil_start` 의 `confirmed` 는 *"에이전트가 사람에게 물어
//
//	승낙받았다"* 는 보고다 — 전해 들은 것이라 gil 은 그렇게 적는다. 여기 오는 것은
//	**사람이 화면에서 직접 누른 것**이다. 둘을 한 칸에 적으면 기록이 거짓이 된다
//	(이 저장소가 여러 번 값을 치른 규칙: 구분되는 것은 구분해서 적는다).
//
// ② **에이전트가 눌러서는 안 되는 버튼이다.** 그래서 `visibility: ["app"]` 로 앱 전용이다.
//
//	선언은 벽이 아니라 힌트지만(날 프로토콜엔 보인다), 얻는 것은 "못 한다"가 아니라
//	"무심코 부르지 않는다"이다 — guard 가 훅과 fsck 를 가른 것과 같은 모양.
//
// 그리고 여기서 **없는 폴더를 만든다.** 지금까지 gil 은 없는 경로를 절대 만들지 않았는데,
// 그 규칙의 이유는 "어디에 만들지는 언제나 사람이 정한 것이 되게"였지 폴더 생성이 위험해서가
// 아니었다. 사람이 이름을 적고 버튼을 눌렀으면 **그건 정한 것이다.** 대신 자리의 성질은
// 그대로 본다(start_place.go 의 safeToCreate).
package main

import (
	"context"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type inStartHere struct {
	Name  string `json:"name" jsonschema:"사람이 화면에 적은 이름. 이 이름으로 폴더가 생긴다"`
	Place string `json:"place,omitempty" jsonschema:"만들 자리(생략하면 기본 자리). 화면의 '다른 자리에 만들기'가 채운다"`
}

func registerStartHereTool(s *mcp.Server) {
	mcp.AddTool(s, &mcp.Tool{
		Name:        "gil_start_here",
		Annotations: toolAnn("gil_start_here"),
		Description: "앱 전용 — 화면의 '여기에 시작한다' 버튼이 도는 자리다. 사람이 이름을 적고 " +
			"직접 누른 것만 여기 온다(에이전트가 대신 부를 것이 아니다). 새 프로젝트를 시작하려면 " +
			"gil_start 를 불러라 — 그러면 이 화면이 뜬다.",
		Meta: mcp.Meta{"ui": map[string]any{"visibility": []string{"app"}}},
	}, func(ctx context.Context, req *mcp.CallToolRequest, in inStartHere) (*mcp.CallToolResult, any, error) {
		abs, err := placeFor(in.Name, in.Place)
		if err != nil {
			return nil, nil, err
		}
		// 이미 있는 자리면 만들지 않는다 — 있는 자리를 쓰는 것은 정당하고, 그때 이 검사는
		// 할 일이 없다. 없을 때만 "만들어도 되는 자리인가"를 묻는다.
		if _, statErr := os.Stat(abs); statErr != nil {
			if err := safeToCreate(abs); err != nil {
				return nil, nil, err
			}
			if err := os.MkdirAll(abs, 0o755); err != nil {
				return nil, nil, errString("거부: 폴더를 만들지 못했다 — " + shortenHome(abs) + "\n  " + err.Error())
			}
		}
		setRepoDir(abs)
		repoSource = repoSourceArg
		rememberUIRepo()
		startScreenOpen = false // 사람이 눌렀다 — 시작하는 화면의 일은 여기서 끝난다

		// **사람이 눌렀다는 사실을 그대로 싣는다.** startAdvance 가 이 문장을 기록에 적는다.
		startConfirmWorld = func() (bool, string) { return true, "사람이 화면에서 눌렀다" }
		defer func() { startConfirmWorld = nil }()
		defer dropTempFiles()
		interviewPlantQuiet = true
		defer func() { interviewPlantQuiet = false }()

		out, err := runGil(func() { cmdStart(nil) })
		if err != nil {
			return nil, nil, err
		}
		signalStartPressed() // 기다리는 gil_start_wait 가 있으면 그 자리에서 깨어난다
		head := "여기에 세웠다: " + shortenHome(abs) + "\n"
		return text(head + strings.TrimSpace(out)), nil, nil
	})
}

// registerStartWaitTool — **사람이 누를 때까지 기다리는 자리.**
//
// 화면을 여는 것(gil_start)과 기다리는 것을 가른 이유는 start_place.go 의 waitStartPressed
// 주석에 있다: 카드는 툴이 **반환될 때** 그려지므로, 여는 호출 안에서 기다리면 화면이 안 뜬다.
//
// **이 툴은 화면을 선언하지 않는다.** 선언하면 이 호출이 카드를 한 장 더 그리고, 그게 바로
// 없애려던 그것이다.
func registerStartWaitTool(s *mcp.Server) {
	mcp.AddTool(s, &mcp.Tool{
		Name:        "gil_start_wait",
		Annotations: toolAnn("gil_start_wait"),
		Description: "시작하는 화면에서 **사람이 [여기에 시작한다] 를 누를 때까지 기다린다.** " +
			"gil_start 로 화면을 연 직후에 이걸 불러라 — 그러면 사람이 누르는 순간 그 자리에서 " +
			"이어간다. **gil_start 를 다시 부르지 마라**: 부를 때마다 카드가 한 장씩 더 뜬다.",
	}, func(ctx context.Context, req *mcp.CallToolRequest, in inStartWait) (*mcp.CallToolResult, any, error) {
		secs := 300
		if n := strings.TrimSpace(in.Timeout); n != "" {
			if v, err := strconv.Atoi(n); err == nil && v > 0 {
				secs = v
			}
		}
		if !waitStartPressed(time.Duration(secs) * time.Second) {
			// **시간이 다 된 것은 거절이 아니다.** 사람이 아직 안 누른 것뿐이라, 화면은 그대로
			// 떠 있고 다시 기다리면 된다. 여기서 "안 하겠다는 뜻"이라 단정하면 없던 사람 의사를
			// 심는 것이고, 이 저장소가 #57 에서 값을 치른 그 자리다.
			return text("아직 안 눌렸다(" + strconv.Itoa(secs) + "초). 화면은 그대로 떠 있다.\n" +
				"  재촉하지 마라 — 이건 사람이 정하는 칸이다. 더 기다리려면 이 툴을 다시 불러라\n" +
				"  (gil_start 를 다시 부르면 카드가 한 장 더 뜬다)."), nil, nil
		}
		// 눌렸다 — 세계는 gil_start_here 가 이미 세웠다. 다음 칸이 무엇인지 그대로 돌려준다.
		out, err := runGil(func() { cmdStart(nil) })
		if err != nil {
			return nil, nil, err
		}
		return text("사람이 눌렀다 — 세계가 섰다.\n\n" + strings.TrimSpace(out)), nil, nil
	})
}

type inStartWait struct {
	Timeout string `json:"timeout,omitempty" jsonschema:"최대 대기 초(기본 300). 시간이 다 되면 '아직 안 눌렸다'로 정상 종료한다"`
}
