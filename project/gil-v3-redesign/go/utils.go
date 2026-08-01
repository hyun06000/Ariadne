// utils.go — 작은 공용 유틸 (env를 실은 git 실행, 정렬, 정수 변환).
package main

import (
	"sort"
	"strconv"
	"strings"
)

// runEnv — 환경변수(GIT_INDEX_FILE 등)를 실어 git을 실행한다(글로벌 write-tree용).
func runEnv(env []string, args ...string) {
	cmd := gitCommand(args...)
	cmd.Env = env
	if err := cmd.Run(); err != nil {
		die("git " + strings.Join(args, " ") + " 실패: " + err.Error())
	}
}

// runEnvOut — runEnv와 같되 stdout을 반환한다(write-tree 결과).
func runEnvOut(env []string, args ...string) string {
	cmd := gitCommand(args...)
	cmd.Env = env
	var out strings.Builder
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		die("git " + strings.Join(args, " ") + " 실패: " + err.Error())
	}
	return out.String()
}

// gitInputEnv — 환경변수와 stdin 을 함께 실어 git 을 실행한다(commit-tree 로 커밋을 다시
// 그릴 때: 메시지는 stdin, 저자·날짜는 환경변수로 보존한다). 이주는 저자를 바꾸지 않는다.
func gitInputEnv(env []string, in string, args ...string) string {
	gitReadCache = map[string]gitCached{} // 쓰기 통로 — 캐시는 쓰기를 놓치는 순간 거짓말이 된다
	cmd := gitCommand(args...)
	cmd.Env = env
	cmd.Stdin = strings.NewReader(in)
	var out, errOut strings.Builder
	cmd.Stdout = &out
	cmd.Stderr = &errOut
	if err := cmd.Run(); err != nil {
		die("git " + strings.Join(args, " ") + " 실패: " + err.Error() + " — " + errOut.String())
	}
	return out.String()
}

func sortStrings(xs []string) { sort.Strings(xs) }
func itoa(n int) string       { return strconv.Itoa(n) }

// boolCount — 참인 것의 개수. 상호배타 플래그 검사에 쓴다(이슈 #80).
func boolCount(bs ...bool) int {
	n := 0
	for _, b := range bs {
		if b {
			n++
		}
	}
	return n
}
