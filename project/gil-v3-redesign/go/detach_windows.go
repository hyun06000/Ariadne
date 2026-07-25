//go:build windows

// detach_windows.go — 윈도우판 세션 분리: 새 프로세스 그룹 + 콘솔 비부착으로
// 부모 콘솔이 닫혀도 뷰어가 산다(이슈 #30).
package main

import (
	"os/exec"
	"syscall"
)

const (
	createNewProcessGroup = 0x00000200 // CREATE_NEW_PROCESS_GROUP
	detachedProcess       = 0x00000008 // DETACHED_PROCESS
)

func detachFromSession(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: createNewProcessGroup | detachedProcess}
}
