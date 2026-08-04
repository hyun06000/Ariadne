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
			"  길 둘(API · releases/latest 리다이렉트)이 **다 막혔다**. 403 은 비인증 호출\n" +
			"  한도(시간당 60회)지만, 리다이렉트는 그 한도를 안 쓰므로 여기까지 왔다면 대개\n" +
			"  네트워크 자체가 막힌 것이다. 지금 갱신하려면 아래 둘 중 하나로 손수 가면 된다:\n" +
			"    (1) 설치 스크립트 — 플랫폼을 알아서 고르고 체크섬까지 검증한다:\n" +
			"        curl -fsSL https://github.com/hyun06000/Ariadne/releases/latest/download/install.sh | sh\n" +
			"    (2) gh 가 있으면 인증 호출로 자산을 직접 받는다(SHA256SUMS 대조 후 교체):\n" +
			"        gh release download -R hyun06000/Ariadne -p 'gil-*' -p 'SHA256SUMS'")
	}
	if latest == gilVersion {
		println2("최신이다 (" + latest + ").")
		return
	}
	if !versionNewer(latest, gilVersion) {
		// 다름이 곧 뒤처짐은 아니다 — 릴리스 직전의 바이너리는 아직 안 올라간 태그를 각인한다.
		println2("이 자리는 최신 릴리스(" + latest + ")보다 앞선다 — 갱신할 것이 없다.")
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

// 두 간격은 서로 다른 것을 막는다. **묻는 것**을 되풀이하면 잡음이 되니 6시간(사람이 이미
// "아니오"라 답했을 수 있다). **조회**는 조용해도 도장이 찍히던 것이 문제였다 — 최신이거나
// 오프라인이면 아무 말도 안 하면서 6시간을 태웠고, 그 사이 릴리스가 나면 세션은 끝까지 몰랐다.
// 조회는 값이 싸다(1.5초·캐시). 그러니 조용한 확인은 1시간이면 충분하다.
const versionAskInterval = 6 * time.Hour
const versionCheckInterval = time.Hour

// versionRetryInterval — 조회가 **실패**했을 때 다시 물어보기까지. 한 시간이 아니라 10분인
// 이유: 못 물어본 것은 소식이 없다는 뜻이 아니다(403 은 대개 몇 분이면 풀린다).
const versionRetryInterval = 10 * time.Minute

// versionAskStamp — 이 클론이 마지막으로 **물어본** 시각과 그때의 최신 태그(.git 안 — 커밋되지
// 않는다). 태그를 함께 적는 이유: 그 사이에 **더 새 릴리스**가 나오면 6시간을 기다리지 않고
// 다시 묻는다. 침묵의 목적은 같은 말을 반복하지 않는 것이지, 새 소식을 막는 것이 아니다.
func versionAskStamp() string { return versionStampPath("version-asked") }

// versionCheckStamp — 마지막으로 **조회한** 시각. 네트워크를 아끼는 자리일 뿐, 문의를 막지 않는다.
func versionCheckStamp() string { return versionStampPath("version-checked") }

func versionStampPath(name string) string {
	dir := strings.TrimSpace(git("rev-parse", "--git-dir"))
	if dir == "" {
		return ""
	}
	return filepath.Join(dir, "gil", name)
}

// versionAskLines — 최신이 더 높으면 사람에게 물을 줄들. 물을 것이 없으면 nil.
// 부작용(마지막 문의 시각 기록)은 실제로 물을 때만 남긴다.
func versionAskLines() []string {
	if os.Getenv("GIL_NO_VERSION_CHECK") != "" {
		return nil
	}
	latest := os.Getenv("GIL_VERSION_LATEST") // 시험용 주입(네트워크 없이 이 길을 밟는다)
	// 지금 이 자리의 버전. 시험은 GIL_VERSION_CURRENT 로 이 자리를 정한다 — 안 그러면
	// 소스 빌드(dev)로는 "더 높은가"의 두 방향(앞선다/뒤처진다)을 아예 밟을 수 없다.
	cur := os.Getenv("GIL_VERSION_CURRENT")
	if cur == "" {
		cur = gilVersion
	}
	// 소스 빌드는 릴리스와 대조할 대상이 아니다 — 조용히 넘어간다(개발·시험이 매번
	// 네트워크를 때리지 않게 하는 자리도 여기다).
	if latest == "" && cur == "dev" {
		return nil
	}
	// 조회 간격은 **네트워크를 아끼는 자리**일 뿐이다. 그러니 아낄 네트워크가 없는 길
	// (주입)에는 서지 않는다 — 여기에 세워 두면 문의 규칙이 아니라 조회 규칙을 시험하게 된다.
	if latest == "" {
		if !versionCheckDue() {
			return nil
		}
		var err error
		latest, err = latestTagTimeout(1500 * time.Millisecond)
		if err != nil {
			// **실패한 조회에 성공한 조회와 같은 침묵을 주지 않는다.** "최신이라 조용하다"와
			// "못 물어봐서 조용하다"는 다른 상태인데, 옛 코드는 둘 다 한 시간을 쉬었다 —
			// 일시적 403(한도) 한 번이 그 세션의 남은 시간을 통째로 삼켰다. 매 명령마다
			// 매달리지도 않는다(그건 잡음이다). 그 사이가 10분이다.
			markVersionCheckFailed()
			return nil
		}
		markVersionChecked()
	}
	// **뒤로 올리라고 물으면 안 된다.** 같은지 다른지가 아니라 **더 높은지**를 본다. 릴리스
	// 직전의 바이너리는 아직 안 올라간 태그를 각인하고 있어서, 다름만 보면 방금 구운 것을
	// 두고 "옛 버전으로 올릴까요"라고 묻는다(릴리스 자산 실측에서 잡혔다).
	if latest == "" || !versionNewer(latest, cur) {
		return nil // 조용히 지나간 자리에 **문의** 도장을 찍지 않는다
	}
	// 여기까지 왔으면 물을 것이 있다. 같은 버전을 이미 물었다면 6시간은 쉰다 — 그러나
	// **더 새 것이 나왔다면 그 침묵을 깬다.** 그러지 않으면 릴리스가 난 직후의 세션이 통째로
	// 침묵 구간에 갇힌다(구버전으로 한 세션을 다 보내는 실패의 절반이 여기였다).
	if latest == lastAskedVersion() && !versionAskDue() {
		return nil
	}
	markVersionAsked(latest)
	return []string{
		"  ⚠ 새 gil 버전이 있다: " + latest + " (지금 이 자리는 " + cur + ")",
		"    **사람에게 물어라**: \"gil " + latest + " 이 나왔습니다. 지금 올릴까요?\"",
		"    올린다면:  gil version --update   (SHA256 검증 후 제자리 교체)",
		"    올리지 않기로 하면 그대로 진행해도 된다 — 다만 새 명령·바뀐 워크플로우가 있을 수 있다.",
	}
}

// versionAskDue — 이 저장소에서 마지막 **문의**로부터 versionAskInterval 이 지났나.
func versionAskDue() bool { return stampDue(versionAskStamp(), versionAskInterval) }

// versionCheckDue — 마지막 **조회**로부터 versionCheckInterval 이 지났나.
// 지난 조회가 **실패**였으면 훨씬 짧게 — 모르는 상태를 오래 끌지 않는다.
func versionCheckDue() bool {
	d := versionCheckInterval
	if lastCheckFailed() {
		d = versionRetryInterval
	}
	return stampDue(versionCheckStamp(), d)
}

// lastCheckFailed — 마지막 조회가 실패로 끝났나(도장 둘째 칸이 "fail").
func lastCheckFailed() bool {
	p := versionCheckStamp()
	if p == "" {
		return false
	}
	b, err := os.ReadFile(p)
	if err != nil {
		return false
	}
	f := strings.SplitN(strings.TrimSpace(string(b)), "\t", 2)
	return len(f) > 1 && strings.TrimSpace(f[1]) == "fail"
}

func stampDue(p string, d time.Duration) bool {
	if p == "" {
		return false // git 저장소가 아니면 기록할 자리가 없다 — 묻지 않는다(매번 묻게 되므로)
	}
	b, err := os.ReadFile(p)
	if err != nil {
		return true
	}
	n := int64(0)
	fmt.Sscanf(strings.TrimSpace(strings.SplitN(string(b), "\t", 2)[0]), "%d", &n)
	return time.Since(time.Unix(n, 0)) >= d
}

// lastAskedVersion — 마지막으로 물었을 때의 최신 태그(없으면 "").
func lastAskedVersion() string {
	p := versionAskStamp()
	if p == "" {
		return ""
	}
	b, err := os.ReadFile(p)
	if err != nil {
		return ""
	}
	f := strings.SplitN(strings.TrimSpace(string(b)), "\t", 2)
	if len(f) < 2 {
		return ""
	}
	return strings.TrimSpace(f[1])
}

func markVersionAsked(latest string) {
	writeStamp(versionAskStamp(), fmt.Sprintf("%d\t%s\n", time.Now().Unix(), latest))
}

func markVersionChecked() {
	writeStamp(versionCheckStamp(), fmt.Sprintf("%d\n", time.Now().Unix()))
}

// markVersionCheckFailed — 조회는 했는데 답을 못 받았다. 성공과 같은 칸에 적되 **다르다고**
// 적는다 — 못 본 것과 볼 것이 없는 것을 가르는 것이 gil 이 여러 자리에서 지켜온 규율이다.
func markVersionCheckFailed() {
	writeStamp(versionCheckStamp(), fmt.Sprintf("%d\tfail\n", time.Now().Unix()))
}

func writeStamp(p, s string) {
	if p == "" {
		return
	}
	_ = os.MkdirAll(filepath.Dir(p), 0o755)
	_ = os.WriteFile(p, []byte(s), 0o644)
}

// versionAskPrint — 부팅·온보딩 자리에서 한 번 묻는다. 물을 것이 없으면 아무 말도 하지 않는다.
func versionAskPrint() {
	if s := versionAskBanner(); s != "" {
		outRaw(strings.TrimSuffix(s, "\n")) // 부팅 출력은 빈 줄 하나만 남긴다
	}
}

// versionAskBanner — 같은 문의를 **한 덩이 텍스트로**. MCP 응답 앞머리에 붙이려면 필요하다:
// MCP 툴은 cmd* 를 직접 불러 main 의 부팅 자리를 지나지 않으므로(mcp.go 의 tool 래퍼), 거기서만
// 버전 문의가 통째로 빠져 있었다 — 호스트가 MCP 를 쓰는 세션은 낡은 gil 을 쥔 줄 끝까지 몰랐다.
func versionAskBanner() string {
	L := versionAskLines()
	if len(L) == 0 {
		return ""
	}
	return "── gil 버전 ──\n" + strings.Join(L, "\n") + "\n\n"
}

// latestTag — GitHub releases/latest 의 tag_name (기본 타임아웃 httpc=15s).
func latestTag() (string, error) { return latestTagClient(httpc) }

// latestTagTimeout — 짧은 타임아웃으로 최신 태그 조회(handoff 현행성 배너용, 비차단).
func latestTagTimeout(d time.Duration) (string, error) {
	return latestTagClient(&http.Client{Timeout: d})
}

// latestTagClient — 최신 태그. **길이 둘이고, 하나가 막히면 다른 하나로 간다.**
//
// 비인증 GitHub API 는 시간당 60회다. 한 대의 개발 머신에서 여러 세션·여러 저장소가 도는
// 실사용에서 이 한도는 쉽게 찬다 — 그리고 그때 gil 은 조용히 물러났다. **버전 문의라는
// 기구 전체가 403 하나로 꺼진 것**이고, 그 사이 나온 릴리스를 세션은 끝까지 모른다
// (상현님 실측: "대부분 이렇게 실패하면서 새 버전이 있는지 모르고 지나간다").
//
// 그런데 릴리스의 최신 태그를 아는 데 API 가 꼭 필요하지는 않다:
// `github.com/<repo>/releases/latest` 는 최신 태그 주소로 **리다이렉트**하고, 이 길은
// API 한도를 안 쓴다. 그러니 API 가 막히면 리다이렉트가 답한다. 조회 하나가 죽었다고
// 기구가 죽으면, 그 기구는 있으나 마나다.
func latestTagClient(cl *http.Client) (string, error) {
	tag, err := latestTagAPI(cl)
	if err == nil {
		return tag, nil
	}
	if tag2, err2 := latestTagRedirect(cl); err2 == nil {
		return tag2, nil
	}
	return "", err // 첫 실패를 그대로 전한다 — 403 이면 그 사실이 사람에게 유용하다
}

// githubAPIBase·githubWebBase — 두 주소. 시험이 **한도에 걸린 상태를 실제로 밟을 수 있게**
// 갈아끼울 수 있다. 안 그러면 이 갈래는 "코드로만 있는 길"이 된다 — 소스 빌드가 버전 확인
// 자체를 건너뛰어 결함을 못 밟았던 v3.51.0 의 그 자리와 같은 모양이다.
func githubAPIBase() string {
	if v := strings.TrimSpace(os.Getenv("GIL_GITHUB_API")); v != "" {
		return v
	}
	return "https://api.github.com"
}

func githubWebBase() string {
	if v := strings.TrimSpace(os.Getenv("GIL_GITHUB_WEB")); v != "" {
		return v
	}
	return "https://github.com"
}

// latestTagRedirect — API 를 안 쓰는 길. releases/latest 가 가리키는 자리를 읽는다.
func latestTagRedirect(cl *http.Client) (string, error) {
	c := *cl
	c.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	resp, err := c.Get(githubWebBase() + "/" + releaseRepo + "/releases/latest")
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	loc := resp.Header.Get("Location")
	if loc == "" && resp.Request != nil && resp.Request.URL != nil {
		loc = resp.Request.URL.String()
	}
	_, tag, ok := strings.Cut(loc, "/releases/tag/")
	if !ok || strings.TrimSpace(tag) == "" {
		return "", fmt.Errorf("리다이렉트에서 태그를 못 읽었다: %q", loc)
	}
	return strings.TrimSpace(tag), nil
}

func latestTagAPI(cl *http.Client) (string, error) {
	resp, err := cl.Get(githubAPIBase() + "/repos/" + releaseRepo + "/releases/latest")
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

// versionNewer — a 가 b 보다 높은 릴리스인가(vX.Y.Z 세 칸 비교). 모르는 모양(dev·접미사)은
// **높지 않다**로 본다 — 확신 없는 비교로 사람을 움직이게 하느니 조용한 편이 낫다.
func versionNewer(a, b string) bool {
	pa, oka := parseSemver(a)
	pb, okb := parseSemver(b)
	if !oka || !okb {
		return false
	}
	for i := 0; i < 3; i++ {
		if pa[i] != pb[i] {
			return pa[i] > pb[i]
		}
	}
	return false
}

// parseSemver — "v3.48.0" → [3 48 0]. 접미사(-rc1 등)가 붙으면 모르는 모양으로 본다.
func parseSemver(v string) ([3]int, bool) {
	var out [3]int
	s := strings.TrimPrefix(strings.TrimSpace(v), "v")
	parts := strings.Split(s, ".")
	if len(parts) != 3 {
		return out, false
	}
	for i, p := range parts {
		if p == "" {
			return out, false
		}
		n := 0
		for _, c := range p {
			if c < '0' || c > '9' {
				return out, false
			}
			n = n*10 + int(c-'0')
		}
		out[i] = n
	}
	return out, true
}
