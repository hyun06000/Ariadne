// viewer_launch.go — gil init 이 뷰어를 자동으로 함께 띄운다 (상현님).
//
// 뷰어는 이제 gil 에 통합됐다(gil viewer serve). gil init 직후 **gil 자기 자신**을
// 관전 서버로 백그라운드에 올려, 사람이 브라우저에서 사고 그래프가 자라는 걸 바로 본다.
// 못 띄워도 init 자체는 절대 깨지지 않는다 — 안내만 하고 넘어간다.
package main

import (
	"path/filepath"
	"net/http"
	"io"
	"encoding/json"
	"net"
	"os"
	"os/exec"
	"runtime"
	"time"
)

const viewerPortDefault = "8790" // 뷰어 serve 기본 포트와 일치.

// viewerPortNum — 뷰어 포트. GIL_VIEWER_PORT 로 바꿀 수 있다(한 머신에서 여러 레포를
// 관전하거나, 테스트가 실포트와 충돌 없이 격리 검증할 때).
func viewerPortNum() string {
	if p := os.Getenv("GIL_VIEWER_PORT"); p != "" {
		return p
	}
	return viewerPortDefault
}

// launchViewer — gil 자기 자신을 `gil viewer serve` 로 관전 서버를 백그라운드로 띄운다.
// 실패는 치명적이지 않다: 이미 떠 있으면 URL 만 알린다.
func launchViewer() {
	// 억제 훅: 테스트·CI·헤드리스에서 관전 서버를 띄우면 포트 점유·프로세스 잔존이
	// 격리를 깬다. GIL_NO_VIEWER 가 설정되면 조용히 건너뛴다.
	if os.Getenv("GIL_NO_VIEWER") != "" {
		return
	}
	url := "http://127.0.0.1:" + viewerPortNum()

	// 이미 그 포트가 열려 있으면(뷰어가 이미 떠 있으면) 중복 기동하지 않는다 — 대신 브라우저를
	// 연다(실사용 피드백: 이미 떠 있을 때 아무 일도 안 하면 사람이 뷰어를 못 찾는다).
	if portOpen(viewerPortNum()) {
		mine, other := viewerServesThisRepo(viewerPortNum())
		if !mine {
			// 남의 저장소(또는 뷰어가 아닌 것)가 이 포트를 쥐고 있다 — 그 주소를 "관전 중"
			// 이라 부르면 사람이 남의 그래프를 자기 것으로 읽는다(온보딩 실측).
			who := other
			if who == "" {
				who = "(뷰어가 아닌 무언가)"
			}
			println2("  ⚠ 뷰어: 포트 " + viewerPortNum() + " 는 다른 저장소가 쓰고 있다 → " + who)
			println2("     이 저장소를 보려면 다른 포트로 띄워라: gil viewer serve --port <다른포트>")
			return
		}
		if openBrowser(url) {
			println2("  뷰어: 이미 관전 중 — 브라우저로 열었다. (" + url + ")")
		} else {
			println2("  뷰어: 이미 관전 중 → 브라우저에서 열어라 → " + url)
		}
		return
	}

	// gil 자기 자신을 뷰어로 재기동한다(뷰어가 gil 에 통합됨). 심링크·PATH 여도 안전하게 절대경로.
	self, err := os.Executable()
	if err != nil || self == "" {
		self = os.Args[0]
	}

	// 대상 레포 = 현재 작업 디렉토리(방금 init 한 곳). 절대경로로 넘겨 detach 후에도 안전.
	repo, err := os.Getwd()
	if err != nil || repo == "" {
		repo = "."
	}

	cmd := exec.Command(self, "viewer", "serve", "--repo", repo, "--port", viewerPortNum())
	// 자식 서버는 브라우저를 열지 않는다 — 부모(여기)가 아래에서 한 번만 연다(이중 실행 방지).
	cmd.Env = append(os.Environ(), "GIL_NO_BROWSER=1")
	// 부모(gil)가 끝나도 살아 있도록 stdio 를 분리하고 백그라운드로 기동한다.
	// 셸 세션에서도 떼어낸다(Setsid/새 프로세스 그룹) — 안 그러면 gil init 을 돌린
	// 셸이 닫힐 때 SIGHUP 으로 뷰어가 소리 없이 죽는다(이슈 #30).
	detachFromSession(cmd)
	devnull, _ := os.Open(os.DevNull)
	if devnull != nil {
		cmd.Stdin = devnull
	}
	cmd.Stdout = nil
	cmd.Stderr = nil
	if err := cmd.Start(); err != nil {
		println2("  뷰어: 기동 실패(" + err.Error() + ") — 수동: `gil viewer serve --repo . --port " + viewerPortNum() + "`.")
		return
	}
	// 프로세스를 놓아준다(reap 하지 않음) — gil 종료 후에도 관전 서버가 산다.
	_ = cmd.Process.Release()

	// 포트가 실제로 열릴 때까지 잠깐 기다려 "떴다"를 사실로 확인한다.
	if waitPort(viewerPortNum(), 2*time.Second) {
		// 브라우저를 자동으로 연다(실사용 피드백: 비개발자는 127.0.0.1 날 주소를 보고 뭔지 몰라
		// 그냥 넘어간다). 로컬 기본 브라우저로 URL 을 띄워, 클릭 없이 바로 사고 그래프를 본다.
		opened := openBrowser(url)
		if opened {
			println2("  뷰어: 브라우저로 열었다 — 사고 그래프가 자라는 걸 본다. (주소: " + url + ")")
		} else {
			println2("  뷰어: 관전 준비됨. 브라우저에서 이 주소를 열어라 → " + url)
		}
	} else {
		println2("  뷰어: 기동 신호는 보냄 — 곧 브라우저에서 열 수 있다 → " + url)
	}
}

// openBrowser — 로컬 기본 브라우저로 url 을 연다(성공하면 true). 플랫폼별 런처를 콘솔 없이
// 돌린다(윈도우에서 cmd 창 번쩍임 방지). 실패해도 치명적이지 않다 — 호출자가 주소를 안내한다.
// 윈도우: cmd /c start(빈 제목 인자 "" 필요). mac: open. 리눅스: xdg-open.
func openBrowser(url string) bool {
	// **기본은 열지 않는다.** 자동으로 튀어나오는 창은 도움보다 방해였다: 에이전트가 인앱
	// 패널에 띄우려는데 밖에 창이 하나 더 뜨고(이슈 #48), 테스트·반복 실행마다 브라우저가
	// 쌓인다. 주소는 언제나 출력에 나오므로 사람도 에이전트도 여는 데 지장이 없다.
	// 여는 건 명시적 요청(--open)일 때만 — 문(門)을 여기 하나로 둔다.
	if os.Getenv("GIL_OPEN_BROWSER") == "" {
		return false
	}
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("cmd", "/c", "start", "", url)
	case "darwin":
		cmd = exec.Command("open", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	hideConsole(cmd) // 윈도우: start 를 띄우는 cmd 창이 번쩍이지 않게
	if err := cmd.Start(); err != nil {
		return false
	}
	_ = cmd.Process.Release()
	return true
}

// portOpen — 로컬 포트에 이미 누가 듣고 있으면 true.
func portOpen(port string) bool {
	c, err := net.DialTimeout("tcp", "127.0.0.1:"+port, 200*time.Millisecond)
	if err != nil {
		return false
	}
	_ = c.Close()
	return true
}

// viewerServesThisRepo — 그 포트의 뷰어가 **이 저장소**를 보고 있나(온보딩 실측).
// 포트가 열려 있다는 사실만으로는 부족하다: 다른 프로젝트의 뷰어가 같은 기본 포트를 쥐고
// 있으면, "이 주소를 열어라"는 지시가 사람을 남의 그래프로 보낸다. /whoami 로 되묻는다.
// (뷰어가 아닌 무언가가 포트를 쥐고 있어도 여기서 걸러진다.)
func viewerServesThisRepo(port string) (bool, string) {
	c := &http.Client{Timeout: 400 * time.Millisecond}
	resp, err := c.Get("http://127.0.0.1:" + port + "/whoami")
	if err != nil {
		return false, ""
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(io.LimitReader(resp.Body, 4096))
	if err != nil {
		return false, ""
	}
	var got struct {
		Repo string `json:"repo"`
	}
	if json.Unmarshal(b, &got) != nil || got.Repo == "" {
		return false, ""
	}
	mine, err := filepath.Abs(".")
	if err != nil {
		return false, got.Repo
	}
	a, err1 := filepath.EvalSymlinks(got.Repo)
	b2, err2 := filepath.EvalSymlinks(mine)
	if err1 == nil && err2 == nil {
		return a == b2, got.Repo
	}
	return got.Repo == mine, got.Repo
}

// waitPort — deadline 안에 포트가 열리면 true.
func waitPort(port string, d time.Duration) bool {
	deadline := time.Now().Add(d)
	for time.Now().Before(deadline) {
		if portOpen(port) {
			return true
		}
		time.Sleep(50 * time.Millisecond)
	}
	return false
}
