// version.go — gil version / --check / --update. 바이너리 드리프트를 바이너리 스스로
// 없앤다(이슈 #22): 레포마다 gil 이 조용히 뒤처지는 걸 사람이 알아채 지시해야만 고쳐지던
// 것을, 바이너리가 최신과 대조(--check)하고 SHA256 검증 후 제자리 교체(--update)한다.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

// gilVersion — 릴리스 빌드가 -ldflags "-X main.gilVersion=vX.Y.Z" 로 채운다.
// 소스 빌드(go run/go build 맨몸)는 "dev".
var gilVersion = "dev"

const releaseRepo = "hyun06000/Ariadne"

var httpc = &http.Client{Timeout: 15 * time.Second}

func cmdVersion(args []string) {
	check, update := false, false
	for _, a := range args {
		switch a {
		case "--check":
			check = true
		case "--update":
			update = true
		default:
			die("사용: gil version [--check|--update]")
		}
	}
	println2("gil " + gilVersion + " (" + runtime.GOOS + "/" + runtime.GOARCH + ")")
	if !check && !update {
		return
	}
	latest, err := latestTag()
	if err != nil {
		// 다음 한 수를 준다(이슈 #47·#51). 비인증 GitHub API 는 시간당 60회라 403 이 흔한데,
		// 옛 메시지는 "네트워크/GitHub"까지만 말하고 끝나 사람이 거기서 막혔다. 자기갱신이
		// 막혔다고 설치까지 막힌 건 아니다 — 손으로 가는 길이 둘 다 있다.
		die("거부: 최신 릴리스 조회 실패 — " + err.Error() + "\n" +
			"  GitHub API 403 이면 비인증 호출 한도(시간당 60회)에 걸린 것이다. 잠시 뒤 다시\n" +
			"  되지만, 지금 갱신하려면 아래 둘 중 하나로 손수 가면 된다:\n" +
			"    (1) 설치 스크립트 — 플랫폼을 알아서 고르고 체크섬까지 검증한다:\n" +
			"        curl -fsSL https://github.com/hyun06000/Ariadne/releases/latest/download/install.sh | sh\n" +
			"    (2) gh 가 있으면 인증 호출로 자산을 직접 받는다(SHA256SUMS 대조 후 교체):\n" +
			"        gh release download -R hyun06000/Ariadne -p 'gil-*' -p 'SHA256SUMS'")
	}
	if latest == gilVersion {
		println2("최신이다 (" + latest + ").")
		return
	}
	println2("새 버전 " + latest + " 사용 가능 (현재 " + gilVersion + ").")
	if !update {
		println2("갱신: gil version --update  (SHA256 검증 후 제자리 교체)")
		return
	}
	selfUpdate(latest)
}

// ── 버전업 문의 (상현님) ──────────────────────────────────────────────────────
//
// 왜. 낡은 gil 을 쥔 세션은 **자기가 낡은 줄 모른다**. handoff 에는 현행성 배너가 있지만
// handoff 를 부르는 건 자기규율이고, 자기규율은 원리적으로 불충분하다(#55 와 같은 논거).
// 그래서 사람이 gil 을 처음 심는 자리(온보딩=init)와 세션이 깨어나 첫 명령을 내는 자리
// (부팅)에서 도구가 먼저 묻는다 — 알리는 게 아니라 **묻는다**: 올릴까요.
//
// 값을 치르지 않는다: 소스 빌드(dev)는 대조할 릴리스가 없으니 건너뛰고, 조회는 1.5초로
// 끊고, 저장소마다 6시간에 한 번만 묻는다(명령마다 물으면 잡음이 되어 안 읽힌다).

const versionAskInterval = 6 * time.Hour

// versionAskStamp — 이 클론이 마지막으로 물어본 시각(.git 안 — 커밋되지 않는다).
func versionAskStamp() string {
	dir := strings.TrimSpace(git("rev-parse", "--git-dir"))
	if dir == "" {
		return ""
	}
	return filepath.Join(dir, "gil", "version-asked")
}

// versionAskLines — 최신이 더 높으면 사람에게 물을 줄들. 물을 것이 없으면 nil.
// 부작용(마지막 문의 시각 기록)은 실제로 물을 때만 남긴다.
func versionAskLines() []string {
	if os.Getenv("GIL_NO_VERSION_CHECK") != "" {
		return nil
	}
	latest := os.Getenv("GIL_VERSION_LATEST") // 시험용 주입(네트워크 없이 이 길을 밟는다)
	// 소스 빌드는 릴리스와 대조할 대상이 아니다 — 조용히 넘어간다(개발·시험이 매번
	// 네트워크를 때리지 않게 하는 자리도 여기다).
	if latest == "" && gilVersion == "dev" {
		return nil
	}
	// 6시간 규칙은 주입된 길에도 똑같이 선다 — 시험이 밟는 길과 실사용의 길이 다르면
	// 시험은 실사용을 검증하지 않는다.
	if !versionAskDue() {
		return nil
	}
	if latest == "" {
		var err error
		latest, err = latestTagTimeout(1500 * time.Millisecond)
		if err != nil {
			markVersionAsked() // 오프라인이면 6시간 뒤에 다시 — 매 명령마다 매달리지 않는다
			return nil
		}
	}
	if latest == "" || latest == gilVersion {
		markVersionAsked()
		return nil
	}
	markVersionAsked()
	return []string{
		"  ⚠ 새 gil 버전이 있다: " + latest + " (지금 이 자리는 " + gilVersion + ")",
		"    **사람에게 물어라**: \"gil " + latest + " 이 나왔습니다. 지금 올릴까요?\"",
		"    올린다면:  gil version --update   (SHA256 검증 후 제자리 교체)",
		"    올리지 않기로 하면 그대로 진행해도 된다 — 다만 새 명령·바뀐 워크플로우가 있을 수 있다.",
	}
}

// versionAskDue — 이 저장소에서 마지막 문의로부터 versionAskInterval 이 지났나.
func versionAskDue() bool {
	p := versionAskStamp()
	if p == "" {
		return false // git 저장소가 아니면 기록할 자리가 없다 — 묻지 않는다(매번 묻게 되므로)
	}
	b, err := os.ReadFile(p)
	if err != nil {
		return true
	}
	n := int64(0)
	fmt.Sscanf(strings.TrimSpace(string(b)), "%d", &n)
	return time.Since(time.Unix(n, 0)) >= versionAskInterval
}

func markVersionAsked() {
	p := versionAskStamp()
	if p == "" {
		return
	}
	_ = os.MkdirAll(filepath.Dir(p), 0o755)
	_ = os.WriteFile(p, []byte(fmt.Sprintf("%d\n", time.Now().Unix())), 0o644)
}

// versionAskPrint — 부팅·온보딩 자리에서 한 번 묻는다. 물을 것이 없으면 아무 말도 하지 않는다.
func versionAskPrint() {
	L := versionAskLines()
	if len(L) == 0 {
		return
	}
	println2("── gil 버전 ──")
	for _, ln := range L {
		println2(ln)
	}
}

// latestTag — GitHub releases/latest 의 tag_name (기본 타임아웃 httpc=15s).
func latestTag() (string, error) { return latestTagClient(httpc) }

// latestTagTimeout — 짧은 타임아웃으로 최신 태그 조회(handoff 현행성 배너용, 비차단).
func latestTagTimeout(d time.Duration) (string, error) {
	return latestTagClient(&http.Client{Timeout: d})
}

func latestTagClient(cl *http.Client) (string, error) {
	resp, err := cl.Get("https://api.github.com/repos/" + releaseRepo + "/releases/latest")
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return "", fmt.Errorf("GitHub API %d", resp.StatusCode)
	}
	var v struct {
		TagName string `json:"tag_name"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&v); err != nil {
		return "", err
	}
	if v.TagName == "" {
		return "", fmt.Errorf("tag_name 없음")
	}
	return v.TagName, nil
}

func fetch(url string) ([]byte, error) {
	resp, err := httpc.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("%s → %d", url, resp.StatusCode)
	}
	return io.ReadAll(resp.Body)
}

// selfUpdate — 플랫폼 자산을 받아 SHA256SUMS 로 대조 후 실행파일을 제자리 교체.
// 검증 실패면 절대 교체하지 않는다.
func selfUpdate(tag string) {
	asset := "gil-" + runtime.GOOS + "-" + runtime.GOARCH
	if runtime.GOOS == "windows" {
		asset += ".exe"
	}
	base := "https://github.com/" + releaseRepo + "/releases/download/" + tag + "/"
	sums, err := fetch(base + "SHA256SUMS")
	if err != nil {
		die("거부: SHA256SUMS 다운로드 실패 — " + err.Error())
	}
	want := ""
	for _, ln := range strings.Split(string(sums), "\n") {
		f := strings.Fields(ln)
		if len(f) == 2 && strings.TrimPrefix(f[1], "*") == asset {
			want = f[0]
		}
	}
	if want == "" {
		die("거부: SHA256SUMS 에 " + asset + " 항목이 없다 — 교체하지 않음")
	}
	println2("다운로드: " + asset + " (" + tag + ") …")
	bin, err := fetch(base + asset)
	if err != nil {
		die("거부: 바이너리 다운로드 실패 — " + err.Error())
	}
	got := sha256.Sum256(bin)
	if hex.EncodeToString(got[:]) != want {
		die("거부: SHA256 불일치 — 교체하지 않음 (기대 " + want[:12] + "…, 실제 " + hex.EncodeToString(got[:])[:12] + "…)")
	}
	self, err := os.Executable()
	if err != nil {
		die("거부: 실행파일 경로를 못 찾음 — " + err.Error())
	}
	if r, err := filepath.EvalSymlinks(self); err == nil {
		self = r
	}
	tmp := self + ".new"
	if err := os.WriteFile(tmp, bin, 0755); err != nil {
		die("거부: 새 바이너리 쓰기 실패(" + tmp + ") — " + err.Error())
	}
	// 실행 중인 파일을 직접 못 덮는 플랫폼(윈도우) 대비: 현재 것을 .old 로 비켜 두고 교체.
	old := self + ".old"
	_ = os.Remove(old)
	if err := os.Rename(self, old); err != nil {
		_ = os.Remove(tmp)
		die("거부: 기존 바이너리 비켜두기 실패 — " + err.Error())
	}
	if err := os.Rename(tmp, self); err != nil {
		_ = os.Rename(old, self) // 원복
		die("거부: 교체 실패(원복함) — " + err.Error())
	}
	_ = os.Remove(old) // 윈도우는 실행 중이라 실패할 수 있음 — 무해, 다음 갱신 때 지워짐
	println2("교체 완료: " + self + " → gil " + tag + " (SHA256 검증됨)")
}
