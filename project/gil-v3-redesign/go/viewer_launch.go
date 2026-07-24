// viewer_launch.go — gil init 이 뷰어를 자동으로 함께 띄운다 (상현님).
//
// 뷰어는 이제 gil 에 통합됐다(gil viewer serve). gil init 직후 **gil 자기 자신**을
// 관전 서버로 백그라운드에 올려, 사람이 브라우저에서 사고 그래프가 자라는 걸 바로 본다.
// 못 띄워도 init 자체는 절대 깨지지 않는다 — 안내만 하고 넘어간다.
package main

import (
	"net"
	"os"
	"os/exec"
	"time"
)

const viewerPort = "8790" // 뷰어 serve 기본 포트와 일치.

// launchViewer — gil 자기 자신을 `gil viewer serve` 로 관전 서버를 백그라운드로 띄운다.
// 실패는 치명적이지 않다: 이미 떠 있으면 URL 만 알린다.
func launchViewer() {
	// 억제 훅: 테스트·CI·헤드리스에서 관전 서버를 띄우면 포트 점유·프로세스 잔존이
	// 격리를 깬다. GIL_NO_VIEWER 가 설정되면 조용히 건너뛴다.
	if os.Getenv("GIL_NO_VIEWER") != "" {
		return
	}
	url := "http://127.0.0.1:" + viewerPort

	// 이미 그 포트가 열려 있으면(뷰어가 이미 떠 있으면) 중복 기동하지 않는다.
	if portOpen(viewerPort) {
		println2("  뷰어: 이미 " + url + " 에서 관전 중.")
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

	cmd := exec.Command(self, "viewer", "serve", "--repo", repo, "--port", viewerPort)
	// 부모(gil)가 끝나도 살아 있도록 stdio 를 분리하고 백그라운드로 기동한다.
	devnull, _ := os.Open(os.DevNull)
	if devnull != nil {
		cmd.Stdin = devnull
	}
	cmd.Stdout = nil
	cmd.Stderr = nil
	if err := cmd.Start(); err != nil {
		println2("  뷰어: 기동 실패(" + err.Error() + ") — 수동: `gil viewer serve --repo . --port " + viewerPort + "`.")
		return
	}
	// 프로세스를 놓아준다(reap 하지 않음) — gil 종료 후에도 관전 서버가 산다.
	_ = cmd.Process.Release()

	// 포트가 실제로 열릴 때까지 잠깐 기다려 "떴다"를 사실로 확인한다.
	if waitPort(viewerPort, 2*time.Second) {
		println2("  뷰어: " + url + " 에서 관전 중 (백그라운드). 브라우저로 열어 사고 그래프를 본다.")
	} else {
		println2("  뷰어: 기동 신호는 보냄 — 곧 " + url + " 에서 관전 가능.")
	}
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
