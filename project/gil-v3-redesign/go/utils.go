// utils.go — 작은 공용 유틸 (env를 실은 git 실행, 정렬, 정수 변환).
package main

import (
	"os/exec"
	"sort"
	"strconv"
	"strings"
)

// runEnv — 환경변수(GIT_INDEX_FILE 등)를 실어 git을 실행한다(글로벌 write-tree용).
func runEnv(env []string, args ...string) {
	cmd := exec.Command("git", args...)
	cmd.Env = env
	if err := cmd.Run(); err != nil {
		die("git " + strings.Join(args, " ") + " 실패: " + err.Error())
	}
}

// runEnvOut — runEnv와 같되 stdout을 반환한다(write-tree 결과).
func runEnvOut(env []string, args ...string) string {
	cmd := exec.Command("git", args...)
	cmd.Env = env
	var out strings.Builder
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		die("git " + strings.Join(args, " ") + " 실패: " + err.Error())
	}
	return out.String()
}

func sortStrings(xs []string) { sort.Strings(xs) }
func itoa(n int) string       { return strconv.Itoa(n) }
