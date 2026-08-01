// checks.go — 층을 건널 때 무엇으로 확인했나 (상현님, 2026-08-01).
//
// 상현님: "배포할 때만 테스트하면 안 되나? 아니면 dev 로 올릴 때만이라도."
//
// SPEC 7 은 이미 그 축을 갖고 있다 — 개발은 smoke, 엄밀한 검증은 배포 앞에서. 그런데 그건
// 문장으로만 있었고 문법에는 없었다. 그래서 층을 건너는 자리(`gil merge --into dev`,
// `gil deploy`)에 확인을 건다.
//
// ## 왜 '선언'이 아니라 '실행'인가
//
// `--verified <무엇으로 확인했나>` 같은 자유서술 칸을 하나 더 만들 수도 있었다. 그러면
// 이 저장소가 #76 에서 관전 중인 그 병이 그대로 재발한다: 칸이 생기면 채워지고, 채워지면
// 통과하고, 그러다 `--verified "테스트 돌림"` 같은 얇은 값만 남는다. 사람이 자기 채점표를
// 쓰는 자리가 하나 더 느는 것이다.
//
// 그래서 **실제로 돌린다.** 저장소가 `.gil/checks` 에 검사 명령을 선언해 두면, 층을 건널 때
// gil 이 그걸 실행하고 **종료코드로 판정**한다. 통과하면 그 사실(명령·시각)이 커밋에 남고,
// 실패하면 건너지 못한다. 확인은 선언이 아니라 사건이다.
//
// 검사가 선언되지 않은 저장소는 막지 않는다 — 없는 규율을 강요하면 이미 있는 나무가
// 얼어붙는다. 대신 **건널 때마다 한 번씩 알린다**: 이 자리에서 확인한 것이 없다고.
package main

import (
	"os"
	"os/exec"
	"strings"
)

const checksFile = ".gil/checks"

// checksText — 검사 선언 원문. **대문에서 읽는다.**
//
// 작업트리에서 읽으면 어느 브랜치를 밟고 있느냐에 따라 있다가 없어진다 — merge·deploy 는
// 브랜치를 옮겨 다니므로, 검사가 그때그때 사라졌다(실측: dev 로 합류하는 순간 파일이 없어
// "검사가 선언되지 않았다"고 통과했다). 검사는 **저장소의 정책**이지 가지의 사정이 아니다.
// 대문 → 층 → 작업트리 순으로 찾는다.
func checksText() string {
	for _, ref := range []string{homeBranch(), devBranchName} {
		if ref == "" {
			continue
		}
		if out, err := gitTry("show", ref+":"+checksFile); err == nil {
			return out
		}
	}
	if b, err := os.ReadFile(checksFile); err == nil {
		return string(b)
	}
	return ""
}

// checkFor — 이 층으로 건널 때 돌릴 명령. 없으면 "".
//
// 형식은 한 줄에 `<층>: <명령>` — 사람이 편집기로 열어 읽고 고칠 수 있는 가장 단순한 꼴이다.
// main 에 선언이 없으면 dev 것을 쓴다(배포 앞에서 최소한 개발 검사는 돈다).
func checkFor(layer string) (cmd, from string) {
	got := map[string]string{}
	for _, ln := range strings.Split(checksText(), "\n") {
		ln = strings.TrimSpace(ln)
		if ln == "" || strings.HasPrefix(ln, "#") {
			continue
		}
		k, v, ok := strings.Cut(ln, ":")
		if !ok {
			continue
		}
		if k, v = strings.TrimSpace(k), strings.TrimSpace(v); k != "" && v != "" {
			got[k] = v
		}
	}
	if c := got[layer]; c != "" {
		return c, layer
	}
	if layer == "main" && got[devBranchName] != "" {
		return got[devBranchName], devBranchName
	}
	return "", ""
}

// runLayerCheck — 층을 건너기 전 검사를 돌린다.
//
// 반환: (돌렸나, 통과했나, 사람에게 할 말). 검사가 없으면 (false, true, 안내).
// 출력은 그대로 흘려보낸다 — 무엇이 왜 실패했는지는 그 명령이 가장 잘 안다. 요약해서
// 감추면 사람은 다시 손으로 돌려봐야 한다.
func runLayerCheck(layer string, skip bool, skipReason string) (ran, passed bool, note string) {
	cmd, from := checkFor(layer)
	if cmd == "" {
		return false, true, "이 자리에서 **확인한 것이 없다** — 이 저장소엔 검사가 선언되지 않았다.\n" +
			"    선언해 두면 층을 건널 때마다 gil 이 직접 돌리고, 통과한 사실이 커밋에 남는다:\n" +
			"      echo '" + layer + ": <검사 명령>' >> " + checksFile
	}
	if skip {
		return false, true, "검사를 건너뛴다(--skip-check): " + skipReason + "\n" +
			"    건너뛴 사실은 커밋에 남는다 — 확인했다고 말하지 않는다."
	}
	println2("  ▸ 층 검사(" + from + "): " + cmd)
	c := exec.Command("sh", "-c", cmd)
	c.Stdout = os.Stderr // stdout 은 gil 자신의 출력 통로다 — 남의 출력을 섞지 않는다
	c.Stderr = os.Stderr
	if err := c.Run(); err != nil {
		return true, false, "검사가 실패했다: " + cmd + "\n" +
			"    " + err.Error() + "\n" +
			"  이 층은 건너지 않는다. 고친 뒤 다시 하거나, 지금 건너야 할 이유가 있으면:\n" +
			"    --skip-check --skip-reason <왜 확인 없이 건너나>  (그 사실이 커밋에 남는다)"
	}
	return true, true, ""
}

// checkTrailers — 검사 결과를 커밋에 남긴다. 통과도 건너뜀도 **똑같이 기록한다** —
// 건너뛴 것을 안 적으면, 나중에 이 커밋은 확인된 것과 구별되지 않는다.
func checkTrailers(layer string, ran, skipped bool, skipReason string) [][2]string {
	cmd, _ := checkFor(layer)
	switch {
	case ran:
		return [][2]string{{"Gil-Checked", cmd}}
	case skipped:
		r := strings.TrimSpace(skipReason)
		if r == "" {
			r = "(이유 없음)"
		}
		return [][2]string{{"Gil-Check-Skipped", r}}
	}
	return nil
}
