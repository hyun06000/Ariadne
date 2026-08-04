// viewer_open.go — **탭을 닫으면 다시 켜기가 어렵다** (상현님).
//
// 뷰어 포트는 저장소 사이를 떠돈다(#110). 그래서 관전 창을 한 번 닫으면, 다시 보려면 사람이
// `gil viewer list` 로 번호를 찾아 주소를 손으로 옮겨야 했다 — 도구가 할 수 있는 일을 사람에게
// 미룬 것이다. 그리고 그 한 줄조차 **터미널 앞에 앉아 있어야** 칠 수 있다.
//
// 두 칸을 놓는다:
//
//	gil viewer open      내 저장소의 뷰어를 찾아 브라우저로 연다(없으면 띄워서 연다).
//	gil viewer shortcut  그 한 줄을 부르는 **런처**를 플랫폼에 맞게 만든다 — 버튼 하나.
//
// 런처는 새 바이너리가 아니라 gil 이 그 자리에서 만드는 껍데기다(mac: .app 번들 안의 셸
// 스크립트 · windows: .cmd · linux: .desktop). "단일 정적 바이너리" 원칙을 건드리지 않는다.
package main

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

// viewerOpen — 이 저장소의 관전 창을 연다. 이미 떠 있으면 그 자리를, 없으면 띄워서 연다.
func viewerOpen() {
	// **--repo 를 실제로 따라간다.** 뷰어의 다른 서브명령은 viewerGit(-C) 로 대상 저장소를
	// 보지만, 여는 일은 CLI 쪽 git·포트 스캔·기동을 모두 쓴다 — 그러니 자리를 옮겨야 한다.
	// 런처(.app/.cmd/.desktop)가 정확히 이 인자로 부른다: 버튼은 자기가 어느 저장소인지
	// 알고 눌리는 것이고, 눌리는 자리(홈 디렉토리 등)는 그 저장소가 아니다.
	if d := strings.TrimSpace(viewerRepoDir); d != "" && d != "." {
		if err := os.Chdir(d); err != nil {
			die("거부: --repo 로 못 들어갔다: " + err.Error())
		}
	}
	if !gitOK("rev-parse", "--git-dir") {
		die("거부: git 저장소가 아니다 — 관전할 그래프가 없다.")
	}
	// 이 명령은 **여는 것이 목적**이다. 기본이 '조용히 서버만'인 것은 다른 명령의 곁다리로
	// 뜰 때의 규칙이고(#48), 여기서는 사람이 열라고 부른 것이다.
	os.Setenv("GIL_OPEN_BROWSER", "1")
	if os.Getenv("GIL_NO_VIEWER") != "" {
		// 억제 환경(테스트·CI·헤드리스)에서는 띄우지 않되, **어디로 가면 되는지는 말한다** —
		// 침묵하면 이 명령이 무엇을 했는지 아무도 모른다.
		if p := viewerPortForThisRepo(); p != "" {
			println2("뷰어: 이미 관전 중 → http://127.0.0.1:" + p + "  (GIL_NO_VIEWER 라 열지는 않았다)")
			return
		}
		println2("뷰어: 이 저장소를 보는 뷰어가 없다(GIL_NO_VIEWER 라 띄우지 않았다).")
		return
	}
	launchViewer()
	if p := viewerPortForThisRepo(); p != "" {
		println2("  (이 자리를 고정해 두면 주소가 세션마다 안 바뀐다: echo " + p + " > .gil/viewer-port)")
		println2("  버튼으로 만들려면: gil viewer shortcut")
	}
}

// viewerShortcut — 이 저장소의 뷰어를 여는 **런처**를 만든다.
//
// 자리는 기본으로 사용자 영역이다(저장소 안이 아니라): 저장소에 만들면 남의 작업트리를
// 더럽히고, 커밋될 위험도 있다. --out 으로 자리를 지정할 수 있다.
func viewerShortcut(out string) {
	if !gitOK("rev-parse", "--git-dir") {
		die("거부: git 저장소가 아니다 — 열 그래프가 없다.")
	}
	top := strings.TrimSpace(git("rev-parse", "--show-toplevel"))
	name := filepath.Base(top)
	self, err := os.Executable()
	if err != nil || self == "" {
		self = "gil"
	}
	home, _ := os.UserHomeDir()

	switch runtime.GOOS {
	case "darwin":
		// .app 번들 = 폴더 하나다. Dock 에 끌어다 두면 버튼이 되고, Spotlight 에도 잡힌다.
		dir := out
		if dir == "" {
			dir = filepath.Join(home, "Applications", "gil 뷰어 — "+name+".app")
		}
		macos := filepath.Join(dir, "Contents", "MacOS")
		if err := os.MkdirAll(macos, 0o755); err != nil {
			die("거부: 런처를 못 만들었다: " + err.Error())
		}
		script := "#!/bin/sh\n# gil viewer shortcut — 이 저장소의 관전 창을 연다.\nexec " +
			shQuote(self) + " viewer open --repo " + shQuote(top) + "\n"
		if err := os.WriteFile(filepath.Join(macos, "run"), []byte(script), 0o755); err != nil {
			die("거부: 런처 스크립트를 못 썼다: " + err.Error())
		}
		plist := `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>gil 뷰어 — ` + name + `</string>
  <key>CFBundleExecutable</key><string>run</string>
  <key>CFBundleIdentifier</key><string>dev.gil.viewer.` + safeIdent(name) + `</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
</dict></plist>
`
		if err := os.WriteFile(filepath.Join(dir, "Contents", "Info.plist"), []byte(plist), 0o644); err != nil {
			die("거부: Info.plist 를 못 썼다: " + err.Error())
		}
		println2("🔘 런처를 만들었다: " + dir)
		println2("   Finder 에서 한 번 열어 보고, Dock 에 끌어다 두면 버튼이 된다.")
		println2("   (Spotlight 에서 '" + name + "' 로도 찾을 수 있다.)")
	case "windows":
		p := out
		if p == "" {
			p = filepath.Join(home, "Desktop", "gil-viewer-"+name+".cmd")
		}
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			die("거부: 런처를 못 만들었다: " + err.Error())
		}
		body := "@echo off\r\nrem gil viewer shortcut — 이 저장소의 관전 창을 연다.\r\n" +
			"start \"\" \"" + self + "\" viewer open --repo \"" + top + "\"\r\n"
		if err := os.WriteFile(p, []byte(body), 0o755); err != nil {
			die("거부: 런처를 못 썼다: " + err.Error())
		}
		println2("🔘 런처를 만들었다: " + p)
		println2("   두 번 눌러 열고, 작업 표시줄에 고정하면 버튼이 된다.")
	default:
		p := out
		if p == "" {
			p = filepath.Join(home, ".local", "share", "applications", "gil-viewer-"+safeIdent(name)+".desktop")
		}
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			die("거부: 런처를 못 만들었다: " + err.Error())
		}
		body := "[Desktop Entry]\nType=Application\nName=gil 뷰어 — " + name + "\n" +
			"Comment=이 저장소의 사고 그래프를 관전한다\n" +
			"Exec=" + self + " viewer open --repo " + top + "\nTerminal=false\nCategories=Development;\n"
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			die("거부: 런처를 못 썼다: " + err.Error())
		}
		println2("🔘 런처를 만들었다: " + p)
		println2("   앱 목록에서 '" + name + "' 로 찾아 실행하거나, 즐겨찾기에 고정하면 버튼이 된다.")
	}
	println2("   이 런처가 하는 일: gil viewer open --repo " + top)
	println2("   (뷰어가 꺼져 있으면 띄우고, 떠 있으면 그 자리를 연다 — 포트는 사람이 안 외운다.)")
}

// shQuote — 셸 인용(작은따옴표). 경로에 공백·한글이 흔하다.
func shQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", `'\''`) + "'" }

// safeIdent — 번들 식별자·파일명에 쓸 안전한 조각(영숫자·하이픈만).
func safeIdent(s string) string {
	var b strings.Builder
	for _, r := range s {
		switch {
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9', r == '-':
			b.WriteRune(r)
		default:
			b.WriteRune('-')
		}
	}
	out := strings.Trim(b.String(), "-")
	if out == "" {
		out = "repo"
	}
	return out
}
