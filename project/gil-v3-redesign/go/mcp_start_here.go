// mcp_start_here.go — **화면의 "여기에 시작한다" 버튼이 도는 자리.**
//
// 왜 `gil_start` 와 따로인가. 두 가지가 다르다.
//
// ① **승낙의 출처가 다르다.** `gil_start` 의 `confirmed` 는 *"에이전트가 사람에게 물어
//    승낙받았다"* 는 보고다 — 전해 들은 것이라 gil 은 그렇게 적는다. 여기 오는 것은
//    **사람이 화면에서 직접 누른 것**이다. 둘을 한 칸에 적으면 기록이 거짓이 된다
//    (이 저장소가 여러 번 값을 치른 규칙: 구분되는 것은 구분해서 적는다).
//
// ② **에이전트가 눌러서는 안 되는 버튼이다.** 그래서 `visibility: ["app"]` 로 앱 전용이다.
//    선언은 벽이 아니라 힌트지만(날 프로토콜엔 보인다), 얻는 것은 "못 한다"가 아니라
//    "무심코 부르지 않는다"이다 — guard 가 훅과 fsck 를 가른 것과 같은 모양.
//
// 그리고 여기서 **없는 폴더를 만든다.** 지금까지 gil 은 없는 경로를 절대 만들지 않았는데,
// 그 규칙의 이유는 "어디에 만들지는 언제나 사람이 정한 것이 되게"였지 폴더 생성이 위험해서가
// 아니었다. 사람이 이름을 적고 버튼을 눌렀으면 **그건 정한 것이다.** 대신 자리의 성질은
// 그대로 본다(start_place.go 의 safeToCreate).
package main

import (
	"context"
	"os"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type inStartHere struct {
	Name  string `json:"name" jsonschema:"사람이 화면에 적은 이름. 이 이름으로 폴더가 생긴다"`
	Place string `json:"place,omitempty" jsonschema:"만들 자리(생략하면 기본 자리). 화면의 '다른 자리에 만들기'가 채운다"`
}

func registerStartHereTool(s *mcp.Server) {
	mcp.AddTool(s, &mcp.Tool{
		Name: "gil_start_here",
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
		head := "여기에 세웠다: " + shortenHome(abs) + "\n"
		return text(head + strings.TrimSpace(out)), nil, nil
	})
}
