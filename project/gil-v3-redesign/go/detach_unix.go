//go:build !windows

// detach_unix.go — 뷰어 백그라운드 프로세스를 부모 셸 세션에서 완전히 떼어낸다.
// Setsid 없이는 자식이 부모 세션 그룹에 남아, 셸이 닫힐 때 SIGHUP 으로 함께 죽는다
// (이슈 #30: 긴 관전 중 뷰어가 소리 없이 죽음). 새 세션 리더로 만들어 살린다.
package main

import (
	"os/exec"
	"syscall"
)

func detachFromSession(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
}

// hideConsole — 유닉스엔 콘솔 창 개념이 없어 no-op. 윈도우판이 CREATE_NO_WINDOW 를 붙인다
// (콘솔 없는 부모가 gil 을 돌릴 때 git 호출마다 cmd 창이 번쩍이는 것 방지, 실사용 피드백).
func hideConsole(cmd *exec.Cmd) {}
