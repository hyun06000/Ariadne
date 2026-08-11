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
	"time"
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

// startNeedsPlace — 지금 세계를 세워야 하는데 **자리가 아직 안 정해졌나.**
//
// ① 아직 세계가 없다(stageNoWorld), 그리고 ② 둘 중 하나:
//
//	· 지금 선 자리가 세울 자리가 아니다(`/`·홈 자신) — 성질로 거부되는 자리.
//	· **아무도 이 자리를 고르지 않았다**(repoSourceUnchosen). 프로세스가 어쩌다 뜬 곳이다.
//
// 두 번째가 처음에 빠져 있어서 시험이 빨갰다. `/` 만 보면 좁다 — 프로세스가 멀쩡한 임시
// 폴더에서 떠도 그 자리를 **고른 사람은 없다.** 고르지 않은 자리에 남의 프로젝트를 세우는
// 것은 `/` 에 세우는 것과 종류가 다를 뿐 같은 실수다.
//
// 사람이 repo 로 자리를 줬거나 호스트가 roots 로 알려줬으면 여기 해당하지 않는다 —
// 그때는 자리가 이미 정해진 것이고 옛 길(승낙만 받는다)이 옳다.
func startNeedsPlace() bool {
	if startInspect().stage != stageNoWorld {
		return false
	}
	return chosenPlaceErr() != nil || repoSource == repoSourceUnchosen
}

// startPlaceOnScreenText — 화면으로 보내는 말.
//
// **잰 것은 응답, 정한 것은 instructions**(상현님 물음, 2026-08-10). "절대경로를 묻지
// 마라"·"git init 을 대신 치지 마라" 같은 **상시 규칙**은 호출 결과와 무관하니 연결마다
// 한 번 로드되는 `initialize.instructions` 에 산다(surface.go 의 mcpInstructions). 응답에
// 또 적으면 두 자리에 같은 것을 적는 것이고, 그러면 한쪽만 낡는다 — 이 저장소가 씨앗 표식
// 에서 이미 치른 값이다.
//
// 그리고 규칙을 응답에만 두면 **늦게 도착한다**: 에이전트는 이 글을 읽기 **전에** 이미
// 무엇을 할지 정했다(실측 — 세션이 먼저 경로를 묻고 그다음 이 글을 읽었다).
//
// 그래서 여기 남는 것은 **이 호출에서 잰 것**뿐이다: 화면이 떴다 · 사람에게 청할 문장 ·
// 기본 자리 · 사람이 누른 뒤의 다음 한 수.
func startPlaceOnScreenText() string {
	return "시작하는 화면을 열었다 — 사람이 거기서 정한다.\n\n" +
		"  \"위에 뜬 화면에서 이 기록에 붙일 이름을 적고 [여기에 시작한다] 를 눌러 주세요.\"\n" +
		"  gil 이 그 폴더를 만들고 세계를 세운다(기본 자리: " + shortenHome(defaultPlaceRoot()) + "/<이름>).\n\n" +
		"  **이제 gil_start_wait 를 불러 그 자리에서 기다려라.** 사람이 누르는 순간 이어진다.\n" +
		"  gil_start 를 다시 부르지 마라 — 부를 때마다 카드가 한 장씩 더 뜬다."
}

// startScreenOpen — 시작하는 화면을 **이미 열었나.** 에이전트가 gil_start 를 두 번 부르는
// 것은 정상이지만(레일이 반복해서 부르라고 가르친다) 그때마다 카드를 새로 열면 사람 앞에
// 같은 질문이 둘 선다. 어디에 적어야 할지 알 수 없고, 한쪽에 적은 것은 다른 쪽이 모른다.
// 세계가 서면 내린다 — 그 화면의 일이 끝났으니까.
var startScreenOpen bool

// ── 사람이 누를 때까지 기다린다 ──────────────────────────────────────────────
//
// 왜 기다리게 하나(상현님). 호스트는 **화면을 선언한 툴을 부를 때마다** 카드를 한 장 그린다.
// 서버가 그걸 막을 방법은 없다 — 그러니 지렛대는 "몇 번 부르나" 하나뿐이고, 기다리면 한 번으로
// 끝난다. 에이전트가 "아직인가?" 하고 다시 부르는 순간 카드가 또 한 장 서기 때문이다.
//
// **왜 gil_start 안에서 안 기다리나.** 카드는 툴이 **반환될 때** 그려진다. 그 안에서 기다리면
// 화면 자체가 안 뜨고, 그러면 사람은 누를 것이 없는데 도구는 눌리기를 기다린다 — 설계로 만든
// 교착이다. 그래서 여는 호출과 기다리는 호출을 가른다(인터뷰가 이미 그 모양이다).
//
// 그리고 **기다리는 툴은 화면을 선언하지 않는다** — 선언하면 그 호출이 또 한 장을 그린다.
var startPressed = make(chan struct{}, 1)

// signalStartPressed — 사람이 [여기에 시작한다] 를 눌렀다. 기다리는 쪽이 있으면 깨운다.
func signalStartPressed() {
	select {
	case startPressed <- struct{}{}:
	default: // 아무도 안 기다린다 — 신호를 쌓아 두지 않는다(다음 대기가 옛 신호에 속지 않게)
	}
}

// waitStartPressed — 눌릴 때까지 기다린다. true=눌렸다, false=시간이 다 됐다.
func waitStartPressed(d time.Duration) bool {
	// 묵은 신호를 먼저 버린다 — 앞선 판의 누름을 이번 누름으로 읽으면 안 된다.
	select {
	case <-startPressed:
	default:
	}
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-startPressed:
		return true
	case <-t.C:
		return false
	}
}
