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

// ensureViewer — **세션의 첫 gil 명령이 무엇이든** 관전 서버가 있게 한다 (상현님 실사용).
//
// 왜. 지금까지 뷰어를 띄우는 자리는 gil init 과 gil handoff 둘뿐이었다. 그런데 gil 이 이미
// 깔린 머신에서 새로 깨어난 세션은 init 을 부를 일이 없고, 복원을 memory read·log·interview
// --status 로 시작하는 경우가 흔하다 — 그러면 그 세션 내내 뷰어가 없다. "에이전트가 알아서
// handoff 를 먼저 부른다"는 자기규율이고, 자기규율은 원리적으로 불충분하다(#55 와 같은 논거).
// 그래서 레일을 도구 쪽에 깐다: 포트가 비어 있으면 어느 명령에서든 띄운다.
//
// 이미 떠 있으면 **아무 말도 하지 않는다** — 명령마다 브라우저를 다시 열거나 한 줄씩 더
// 붙이면, 정작 중요한 출력이 잡음에 묻힌다(뜰 때 한 번만 말한다).
func ensureViewer() {
	if os.Getenv("GIL_NO_VIEWER") != "" {
		return
	}
	if !gitOK("rev-parse", "--git-dir") {
		return // git 저장소가 아니다 — 관전할 그래프가 없다
	}
	// **주인을 본다**(상현님). 옛 코드는 기본 포트가 열려 있으면 그냥 돌아갔다 — 그 뷰어가
	// 남의 저장소 것이어도. 그러면 이 세션은 뷰어가 없는데 있는 줄 알고, 사람은 남의 그래프를
	// 자기 것으로 읽는다. 포트가 열렸다는 사실은 주인을 말해 주지 않는다.
	if viewerPortForThisRepo() != "" {
		return // 내 저장소를 보는 뷰어가 이미 있다 — 조용히 그대로 쓴다
	}
	launchViewer()
}

// viewerPortForThisRepo — 이 저장소를 보고 있는 살아있는 뷰어의 포트("" = 없음).
func viewerPortForThisRepo() string {
	for _, v := range viewerScan() {
		if mine, _ := viewerServesThisRepo(v.Port); mine {
			return v.Port
		}
	}
	return ""
}

// freeViewerPort — 기본 포트부터 훑어 아무도 안 쥔 첫 포트. 열 자리가 없으면 "".
// 남의 저장소를 밀어내지 않고 **비켜서 띄우기** 위한 자리다.
func freeViewerPort() string {
	base := atoiSafe(viewerPortNum())
	if base <= 0 {
		base = 8790
	}
	for i := 0; i < 10; i++ {
		p := itoa(base + i)
		if !portOpen(p) {
			return p
		}
	}
	return ""
}

// launchViewer — gil 자기 자신을 `gil viewer serve` 로 관전 서버를 백그라운드로 띄운다.
// 실패는 치명적이지 않다: 이미 떠 있으면 URL 만 알린다.
func launchViewer() {
	// 억제 훅: 테스트·CI·헤드리스에서 관전 서버를 띄우면 포트 점유·프로세스 잔존이
	// 격리를 깬다. GIL_NO_VIEWER 가 설정되면 조용히 건너뛴다.
	if os.Getenv("GIL_NO_VIEWER") != "" {
		return
	}
	// 내 저장소를 보는 뷰어가 이미 있으면 그걸 쓴다 — 기본 포트가 아니어도(포트 폴백으로
	// 다른 자리에 떠 있을 수 있다). 중복 기동하지 않고 주소만 준다.
	if mineport := viewerPortForThisRepo(); mineport != "" {
		u := "http://127.0.0.1:" + mineport
		if openBrowser(u) {
			println2("  뷰어: 이미 관전 중 — 브라우저로 열었다. (" + u + ")")
		} else {
			println2("  뷰어: 이미 관전 중 → 브라우저에서 열어라 → " + u)
		}
		return
	}

	// 기본 포트를 **남이 쥐고 있으면 비켜서 띄운다**(상현님). 옛 코드는 여기서 손을 놓고
	// "다른 포트로 띄워라"라고 사람에게 시켰다 — 길 없는 안내가 아니라 길 있는 안내지만,
	// 도구가 할 수 있는 일을 사람에게 미룬 것이다. 남의 뷰어는 건드리지 않는다.
	port := viewerPortNum()
	if portOpen(port) {
		_, other := viewerServesThisRepo(port)
		who := other
		if who == "" {
			who = "(뷰어가 아닌 무언가)"
		}
		alt := freeViewerPort()
		if alt == "" {
			println2("  ⚠ 뷰어: 포트 " + port + " 는 다른 저장소가 쓰고 있다 → " + who)
			println2("     비켜 띄울 빈 포트가 없다(" + port + "부터 10개 모두 사용 중) — 정리: gil viewer list / gil viewer stop")
			return
		}
		println2("  ⓘ 뷰어: 포트 " + port + " 는 다른 저장소가 쓰고 있다 → " + who)
		println2("     이 저장소는 " + alt + " 로 비켜서 띄운다(남의 뷰어는 건드리지 않는다).")
		port = alt
	}
	url := "http://127.0.0.1:" + port

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

	cmd := exec.Command(self, "viewer", "serve", "--repo", repo, "--port", port)
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
	// 옛 코드는 stdout/stderr 을 통째로 버렸다(nil = /dev/null). 그래서 자동 기동된 뷰어가
	// 죽으면 **한 글자도 안 남았다** — 패닉이든 git 실패든 사후 진단이 원리적으로 불가능했다
	// (상현님 실사용: "인터뷰 진행하다가 갑자기 서버가 죽었어" → 왜인지 알 방법이 없었다).
	// 이제 저장소의 .git/gil-viewer.log 로 흘린다. 열지 못하면 옛 동작(버림)으로 물러난다 —
	// 로그 때문에 뷰어가 안 뜨는 일은 없어야 한다.
	if lf, lerr := os.OpenFile(viewerLogPathFor(repo), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644); lerr == nil {
		cmd.Stdout = lf
		cmd.Stderr = lf
		defer lf.Close() // 자식이 fd 를 물려받은 뒤 부모 쪽은 닫는다
	} else {
		cmd.Stdout = nil
		cmd.Stderr = nil
	}
	if err := cmd.Start(); err != nil {
		println2("  뷰어: 기동 실패(" + err.Error() + ") — 수동: `gil viewer serve --repo . --port " + port + "`.")
		return
	}
	// 프로세스를 놓아준다(reap 하지 않음) — gil 종료 후에도 관전 서버가 산다.
	_ = cmd.Process.Release()

	// 포트가 실제로 열릴 때까지 잠깐 기다려 "떴다"를 사실로 확인한다.
	if waitPort(port, 2*time.Second) {
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

// viewerScan — 8790..8799 를 훑어 **어느 포트가 어느 저장소를 보는지** 알아낸다(이슈 #93 곁다리).
// 포트 폴백 때문에 뷰어가 세션마다 겹겹이 쌓이는데, 어느 것이 내 저장소인지 알 방법이 없었다.
func viewerScan() []struct{ Port, Repo string } {
	var out []struct{ Port, Repo string }
	base := 8790
	if p := os.Getenv("GIL_VIEWER_PORT"); p != "" {
		if n := atoiSafe(p); n > 0 {
			base = n
		}
	}
	for i := 0; i < 10; i++ {
		port := itoa(base + i)
		if !portOpen(port) {
			continue
		}
		_, repo := viewerServesThisRepo(port)
		if repo == "" {
			repo = "(gil 뷰어가 아니거나 응답 없음)"
		}
		out = append(out, struct{ Port, Repo string }{port, repo})
	}
	return out
}

// viewerPidAt — 그 포트의 뷰어 프로세스 pid(0 = 모름). /whoami 가 밝힌다.
func viewerPidAt(port string) int {
	c := &http.Client{Timeout: 400 * time.Millisecond}
	resp, err := c.Get("http://127.0.0.1:" + port + "/whoami")
	if err != nil {
		return 0
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(io.LimitReader(resp.Body, 4096))
	if err != nil {
		return 0
	}
	var got struct {
		Pid int `json:"pid"`
	}
	if json.Unmarshal(b, &got) != nil {
		return 0
	}
	return got.Pid
}

// stopMyViewers — **이 저장소를 보는** 뷰어를 끈다(상현님: 세션이 끝나면 자기가 켠 것을 끈다).
//
// 왜 여기까지 오나. 세션마다 뷰어가 하나씩 뜨고 아무도 끄지 않으니 포트가 겹겹이 쌓였고,
// 다음 세션은 비켜 띄우다 자리가 없어졌다. 켜는 레일을 깔았으면 끄는 레일도 깔아야 한다 —
// 안 그러면 정리는 사람의 기억력에 맡겨진다.
//
// 남의 저장소 뷰어는 **절대** 건드리지 않는다: /whoami 로 레포가 나와 일치하는 것만 끈다.
func stopMyViewers() []string {
	var L []string
	for _, v := range viewerScan() {
		mine, _ := viewerServesThisRepo(v.Port)
		if !mine {
			continue
		}
		pid := viewerPidAt(v.Port)
		if pid <= 0 {
			L = append(L, "  ⚠ 뷰어 "+v.Port+" : pid 를 못 알아냈다(옛 버전 뷰어일 수 있다) — 손으로 끄거나 그대로 둬라.")
			continue
		}
		p, err := os.FindProcess(pid)
		if err != nil {
			L = append(L, "  ⚠ 뷰어 "+v.Port+" (pid "+itoa(pid)+"): 프로세스를 못 찾음")
			continue
		}
		if err := terminateProcess(p); err != nil {
			L = append(L, "  ⚠ 뷰어 "+v.Port+" (pid "+itoa(pid)+"): 종료 실패 — "+err.Error())
			continue
		}
		L = append(L, "  뷰어 껐다: 127.0.0.1:"+v.Port+" (pid "+itoa(pid)+")")
	}
	if len(L) == 0 {
		L = append(L, "  이 저장소를 보는 뷰어가 없다 — 끌 것이 없다.")
	}
	return L
}

// viewerAliveForThisRepo — 이 저장소를 보는 살아있는 뷰어가 있나(이슈 #93 제안 3).
// 뷰어가 죽으면 **사람이 인터뷰 폼을 제출할 수단이 사라진다** — 답을 기다리는 자리에서
// 그 사실을 모르면 에이전트도 사람도 "왜 아무 일이 없지"에서 멈춘다.
func viewerAliveForThisRepo() bool {
	for _, v := range viewerScan() {
		if mine, _ := viewerServesThisRepo(v.Port); mine {
			return true
		}
	}
	return false
}

// viewerDeadNotice — 사람의 답을 기다리는 자리에서 뷰어가 없으면 그 자리에서 알린다.
func viewerDeadNotice() []string {
	if os.Getenv("GIL_NO_VIEWER") != "" || viewerAliveForThisRepo() {
		return nil
	}
	return []string{
		"  ⚠ 이 저장소를 보는 뷰어가 없다 — **사람이 폼을 제출할 창구가 없다.** 기다려도 답은 안 온다.",
		"    다시 띄워라: gil viewer serve   (죽은 이유는 <레포>/.git/gil-viewer.log 에 남아 있다)",
	}
}

// reviveViewerIfDead — 사람의 답을 기다리는 동안 창구(뷰어)가 죽으면 다시 띄운다(이슈 #93).
// 조용히 되살리지 않는다 — 죽었다는 사실 자체가 알아야 할 정보다(로그에 이유가 남아 있다).
func reviveViewerIfDead(chain string) {
	if os.Getenv("GIL_NO_VIEWER") != "" || viewerAliveForThisRepo() {
		return
	}
	println2("  ⚠ 이 저장소를 보는 뷰어가 사라졌다 — 사람이 답할 창구가 없어졌다. 다시 띄운다.")
	println2("    (죽은 이유: <레포>/.git/gil-viewer.log 를 읽어라.)")
	launchViewer()
	if viewerAliveForThisRepo() {
		println2("  ✓ 뷰어를 다시 띄웠다 — 사람에게 " + chain + " 인터뷰 폼 제출을 다시 청하라.")
	} else {
		println2("  ✗ 다시 띄우지 못했다 — 사람에게 직접 청하라: gil viewer serve")
	}
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
