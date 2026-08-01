//go:build windows

// detach_windows.go — 윈도우판 세션 분리: 새 프로세스 그룹 + 콘솔 비부착으로
// 부모 콘솔이 닫혀도 뷰어가 산다(이슈 #30).
package main

import (
	"os"
	"os/exec"
	"syscall"
)

const (
	createNewProcessGroup = 0x00000200 // CREATE_NEW_PROCESS_GROUP
	detachedProcess       = 0x00000008 // DETACHED_PROCESS
	createNoWindow        = 0x08000000 // CREATE_NO_WINDOW — 콘솔 창을 아예 안 띄운다
)

func detachFromSession(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: createNewProcessGroup | detachedProcess}
}

// hideConsole — 자식 프로세스(git 등)가 새 콘솔 창을 번쩍 띄우지 않게 한다(윈도우). 콘솔
// 없는 부모(Claude Desktop·GUI 런처)가 gil 을 돌리면, git 호출마다 cmd 창이 계단식으로
// 뜨고 꺼져 비개발자에게 공포스럽다(실사용 피드백). CREATE_NO_WINDOW 로 조용히 돌린다.
// 뷰어 폴링이 1.5초마다 git 을 부르므로 이게 없으면 창이 깜빡임을 반복한다.
func hideConsole(cmd *exec.Cmd) {
	if cmd.SysProcAttr == nil {
		cmd.SysProcAttr = &syscall.SysProcAttr{}
	}
	cmd.SysProcAttr.CreationFlags |= createNoWindow
}

// terminateProcess — 윈도우에는 SIGTERM 이 없다(Signal 은 os.Kill 외에는 미구현). Kill 로
// 끊는다 — 로그 한 줄은 못 남지만, 끄는 일 자체가 안 되는 것보다 낫다.
func terminateProcess(p *os.Process) error { return p.Kill() }
