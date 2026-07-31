// interview_wait.go — 기다리는 사람이 **누구에게도 안 보이던** 것을 보이게 한다 (이슈 #82).
//
// 왜. #58 이 --wait 를, #77 이 도착 고지를 줬는데도 사람이 두 번 말해야 했다. 남은 겹은
// 이것이다: 대화형 에이전트에게 **다음 턴을 여는 열쇠는 사람 손에만 있다**. 그래서 gil 이
// 유일하게 밀 수 있는 형태는 "말하면서 동시에 기다리기" — 백그라운드 --wait 다. 그 형태를
// 안내에서 1급으로 올리고(#82 제안 1), 기다리는 중이라는 사실을 **사람에게도** 보이게 한다
// (제안 2·4). 사람이 제출하고 아무 반응이 없으면 "놓쳤나"를 의심하게 되는데, 실제로 두 번
// 다 그렇게 물었다.
//
// 대기 표식은 로컬 상태다 — .git/gil/interview-waiting-<chain>. 커밋이 아니다(클론마다 다르고
// 프로세스 수명에 묶인다). 살아있음은 **심장박동**으로 안다: --wait 루프가 2초마다 파일을 다시
// 쓴다. 읽는 쪽은 최근 갱신(10초)만 살아있다고 본다 — 프로세스가 죽거나 kill -9 로 사라져도
// 표식이 유령으로 남지 않는다(pid 를 믿는 것보다 이식성도 낫다).
package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// shellRun — 사람이 준 명령 한 줄을 그 플랫폼의 쉘로 돌린다(--then). 출력은 합쳐서 준다.
func shellRun(cmdline string) (string, error) {
	sh, flag := "sh", "-c"
	if runtime.GOOS == "windows" {
		sh, flag = "cmd", "/C"
	}
	out, err := exec.Command(sh, flag, cmdline).CombinedOutput()
	return string(out), err
}

// waiterStale — 이 시간 넘게 심장박동이 없으면 죽은 표식으로 본다.
const waiterStale = 10 * time.Second

func waitPath(chain string) string {
	dir := strings.TrimSpace(git("rev-parse", "--git-dir"))
	if dir == "" || chain == "" {
		return ""
	}
	return filepath.Join(dir, "gil", "interview-waiting-"+chain)
}

// waiterBeat — "지금 이 체인의 답을 기다리는 중" 을 새긴다(--wait 루프가 반복 호출).
// 실패해도 조용하다 — 대기 자체는 계속돼야 한다. 잃는 것은 표시뿐이다.
func waiterBeat(chain string, deadline time.Time) {
	p := waitPath(chain)
	if p == "" {
		return
	}
	_ = os.MkdirAll(filepath.Dir(p), 0o755)
	_ = os.WriteFile(p, []byte("pid "+strconv.Itoa(os.Getpid())+"\n"+
		"deadline "+strconv.FormatInt(deadline.Unix(), 10)+"\n"), 0o644)
}

// waiterClear — 대기가 끝났다(제출·시간초과·거부 어느 쪽이든). 표식을 지운다.
func waiterClear(chain string) {
	if p := waitPath(chain); p != "" {
		_ = os.Remove(p)
	}
}

// interviewWaiterActive — 지금 이 체인의 답을 실제로 기다리는 프로세스가 있나.
// 심장박동이 끊긴 표식은 없는 것으로 보고 지운다 — 유령이 "기다리는 중"이라 말하면
// 사람은 다시 아무도 없는 곳에 제출하게 된다.
func interviewWaiterActive(chain string) bool {
	p := waitPath(chain)
	if p == "" {
		return false
	}
	st, err := os.Stat(p)
	if err != nil {
		return false
	}
	if time.Since(st.ModTime()) > waiterStale {
		_ = os.Remove(p)
		return false
	}
	return true
}

// runThen — --wait --then '<명령>': 제출되는 순간 이 명령을 실행한다(이슈 #82 제안 3).
// 호스트가 프로세스 완료로 에이전트를 깨우지 못해도 훅 하나는 확실히 걸린다(파일을 쓰든,
// 알림을 쏘든 — 무엇을 걸지는 호스트를 아는 쪽이 정한다). 실패해도 대기의 성과(확정된 기준)를
// 뒤엎지 않는다 — 실패 사실만 그대로 말한다.
func runThen(chain, then string) {
	then = strings.TrimSpace(then)
	if then == "" {
		return
	}
	println2("▸ --then 실행: " + then)
	out, err := shellRun(then)
	if s := strings.TrimSpace(out); s != "" {
		println2(s)
	}
	if err != nil {
		println2("⚠ --then 명령이 실패했다(" + err.Error() + ") — 기준 문서는 확정됐다. 명령만 다시 하라.")
	}
}

// backgroundWaitHint — 제3의 형태를 1급으로 올리는 안내(이슈 #82 제안 1).
//
// 지금까지 gil 은 두 선택지만 놓았다: --wait(턴이 블록된다 → 사람에게 말할 수 없다)와
// --status + 다음 턴(말할 수 있다 → 유일하게 가능해 보인다). 대화형 에이전트는 매번 뒤를
// 고르고, 그건 차선이다. **백그라운드 --wait** 는 말하는 것과 기다리는 것을 동시에 한다.
func backgroundWaitHint(chain string) []string {
	return []string{
		"  ▸ **대화형 세션이면 --wait 를 백그라운드로 돌려라** — 말하는 것과 기다리는 것을 동시에 한다:",
		"      gil interview " + chain + " --wait --timeout 3600 > /tmp/gil-" + chain + "-ref.md 2>&1",
		"    사람이 제출하는 순간 그 프로세스가 끝난다.",
		"    ⚠ **호스트가 추적하는 백그라운드 실행으로 심어라**(이슈 #94). 셸에서 `&` 로 떼어내면" +
			" 대부분의 호스트에서 그 프로세스는 추적 밖이라,",
		"      끝나도 **네 턴이 열리지 않는다** — 답은 도착했는데 아무도 못 읽는 상태가 된다" +
			"(실사용에서 네 번 반복됐다).",
		"      네 런타임에 백그라운드 실행 기능이 있으면 그것으로 돌려라. 없으면 아래 차선으로 가라.",
		"    (제출 시 이어서 할 일이 정해져 있으면: gil interview " + chain + " --wait --then '<명령>')",
		"  ▸ 차선 — 다음 턴의 **첫 명령**으로 gil interview " + chain + " --status.",
		"    (답이 도착해 있으면 gil 이 어느 명령에서든 맨 앞에 ⚡ 한 줄로 고지한다 — 그래도 네가 먼저 물어라.)",
	}
}
