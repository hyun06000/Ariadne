// start_place.go — **어디에 만들까.** 이 제품에서 제일 비싼 질문이다.
//
// 왜 이게 제일 비싼가. MVP 표면(Claude Desktop 일반 채팅)은 **roots 를 주지 않는다**(실측
// 2026-08-10). 그래서 지금까지 "어느 폴더냐"가 통째로 에이전트에게 떠넘겨져 있었고, 그
// 결과 gil 이 `/` 에 서서 "여기에 저장소를 세우게 된다: /" 라고 태연히 말한 적이 있다
// (사람이 "네" 했으면 그렇게 됐다 — 에이전트가 되물어 준 덕에 안 났을 뿐이다).
//
// 그리고 그 자리를 **비개발자에게 물으면 흐름이 거기서 끝난다.** "저장소 최상위의 절대
// 경로를 알려주세요"는 이 사람들이 답할 수 있는 질문이 아니다.
//
// 그래서 도구가 **자리를 제안하고 사람은 이름만 정한다.** 경로는 아무도 치지 않는다.
// 문법이 지켜 온 "어디에 만들지는 언제나 사람이 정한 것이 되게"는 그대로다 — 사람이 화면에서
// 이름을 적고 버튼을 누르는 것이 곧 정하는 것이다. 도구가 대신 정하는 것은 **기본값의 자리**
// 뿐이고, 그건 언제나 눈에 보이고 바꿀 수 있다.
package main

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"unicode"
)

// defaultPlaceRoot — 새 프로젝트를 담을 기본 자리.
//
// `~/Documents/gil` 을 먼저 본다 — 사람이 자기 파일이 어디 있는지 아는 자리이기 때문이다
// (숨김 폴더에 두면 "내 기록이 어디 있냐"에 답할 수 없다). Documents 가 없는 구성이면
// 홈 아래로 내려온다.
func defaultPlaceRoot() string {
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		return ""
	}
	if st, err := os.Stat(filepath.Join(home, "Documents")); err == nil && st.IsDir() {
		return filepath.Join(home, "Documents", "gil")
	}
	return filepath.Join(home, "gil")
}

// placeSlug — 사람이 적은 이름을 폴더 이름으로. **사람의 문장을 고치지 않는다** — 이건
// 기준이 아니라 파일 이름이라, 파일시스템이 받는 모양으로 옮기는 것이 정직하다.
// 공백은 하이픈으로, 경로 구분자와 제어문자는 버린다(한글·숫자는 그대로 남는다).
func placeSlug(name string) string {
	var b strings.Builder
	for _, r := range strings.TrimSpace(name) {
		switch {
		case r == '/' || r == '\\' || r == ':' || r == 0:
			// 경로를 벗어나게 하는 글자는 지운다 — 이름 칸으로 자리를 바꾸게 두지 않는다.
		case unicode.IsSpace(r):
			b.WriteRune('-')
		case unicode.IsControl(r):
		default:
			b.WriteRune(r)
		}
	}
	s := strings.Trim(b.String(), "-.")
	// `..` 로만 이루어진 이름 같은 것이 남지 않게.
	if s == "" || strings.Trim(s, ".") == "" {
		return ""
	}
	return s
}

// placeFor — 이름 하나로 만들 자리를 정한다. root 가 비면 기본 자리를 쓴다.
func placeFor(name, root string) (string, error) {
	slug := placeSlug(name)
	if slug == "" {
		return "", errors.New("거부: 이름이 비었다 — 그 이름으로 폴더가 생기므로 한 줄은 있어야 한다.")
	}
	if strings.TrimSpace(root) == "" {
		root = defaultPlaceRoot()
	}
	root = expandHome(root)
	if root == "" {
		return "", errors.New("거부: 홈 폴더를 알 수 없어 자리를 제안하지 못한다.")
	}
	abs, err := filepath.Abs(root)
	if err != nil {
		return "", errors.New("거부: 자리를 해석하지 못했다: " + root)
	}
	return filepath.Join(abs, slug), nil
}

// expandHome — 화면이 사람에게 `~/Documents/gil` 로 보여주므로, 그 모양 그대로 돌아올 수 있다.
func expandHome(p string) string {
	p = strings.TrimSpace(p)
	if p != "~" && !strings.HasPrefix(p, "~/") {
		return p
	}
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		return p
	}
	if p == "~" {
		return home
	}
	return filepath.Join(home, p[2:])
}

// shortenHome — 사람에게 보여줄 때는 홈을 `~` 로 접는다(경로가 길면 아무도 안 읽는다).
func shortenHome(p string) string {
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		return p
	}
	if p == home {
		return "~"
	}
	if strings.HasPrefix(p, home+string(filepath.Separator)) {
		return "~" + p[len(home):]
	}
	return p
}

// safeToCreate — **없는 폴더를 만들어도 되는 자리인가.**
//
// 지금까지 gil 은 없는 경로를 절대 만들지 않았다. 그 규칙의 이유는 "어디에 만들지는 언제나
// 사람이 정한 것이 되게"였지, 폴더 생성 자체가 위험해서가 아니다. **사람이 화면에서 이름을
// 적고 버튼을 눌렀으면 그건 정한 것이다** — 그러니 그 자리에서는 만든다.
//
// 대신 자리의 성질은 그대로 본다(requireChosenPlace 와 같은 판정):
//   - `/` 와 홈 자신은 프로젝트를 **담는** 자리다. 거기에 세우면 그 아래 전부가 한 저장소가 된다.
//   - 홈 바깥은 만들지 않는다. 남의 디스크에 폴더를 만드는 일이라, 사람이 사는 자리 안으로 둔다
//     (밖에 만들려면 그 경로를 직접 실어 부르는 길이 따로 있다 — 그건 사람이 명시한 것이다).
//   - 이미 있으면 만들지 않는다(그건 이 함수의 일이 아니다 — 있는 자리를 쓰는 것은 정당하다).
func safeToCreate(abs string) error {
	if !filepath.IsAbs(abs) {
		return errors.New("거부: 절대경로가 아니다: " + abs)
	}
	clean := filepath.Clean(abs)
	if clean == string(filepath.Separator) {
		return errors.New("거부: `/` 는 프로젝트를 담는 자리지 프로젝트가 아니다.")
	}
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		return errors.New("거부: 홈 폴더를 알 수 없다 — 만들 자리를 판정할 수 없다.")
	}
	home = filepath.Clean(home)
	if clean == home {
		return errors.New("거부: 홈 폴더 자신은 프로젝트를 담는 자리지 프로젝트가 아니다 — " +
			"거기에 세우면 그 아래 전부가 한 저장소가 된다.")
	}
	if !strings.HasPrefix(clean, home+string(filepath.Separator)) {
		return errors.New("거부: 화면에서 만드는 자리는 홈 폴더 안이어야 한다 — " +
			shortenHome(clean) + "\n" +
			"  바깥에 만들려면 그 절대경로를 repo 인자에 실어 부른다(그건 사람이 명시한 것이다).")
	}
	return nil
}
