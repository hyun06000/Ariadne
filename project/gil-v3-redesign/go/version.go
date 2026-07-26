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
		die("거부: 최신 릴리스 조회 실패(네트워크/GitHub) — " + err.Error())
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
