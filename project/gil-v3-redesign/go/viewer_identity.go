package main

import (
	"crypto/sha256"
	"encoding/hex"
	"path/filepath"
	"strings"
)

// ── 이 화면은 어느 저장소인가 (이슈 #110) ──────────────────────────────────────
//
// 여러 저장소에서 gil 을 쓰면 뷰어 포트가 저장소 사이를 **떠돈다**. 같은 번호가 어느 순간
// 다른 저장소를 서비스하는데, 화면 어디에도 정체가 없었다 — 제목은 어느 저장소든 "gil —
// 사고의 지도"다. 그래서 사람이 남의 그래프를 보며 "내 인터뷰가 안 보인다, 많이 망가졌나
// 보네"라고 판단했다. **도구는 정상이었고 화면만 남의 것이었다.**
//
// 에이전트도 같이 속았다. curl 로 체인 이름(ail-runtime)을 확인하고 "우리 것이 맞다"고
// 오판했는데, 그 저장소에도 우연히 같은 이름의 체인이 있었다. 이름은 저장소마다 겹칠 수
// 있으니 정체의 근거가 못 된다 — **겹칠 수 없는 값**이 필요하다.
//
// 그래서 뿌리 커밋이다. 저장소가 태어난 순간의 sha 는 그 저장소 말고는 가질 수 없고, 작업이
// 쌓여도 변하지 않는다(브랜치·체인·팁은 다 변한다). 화면과 /whoami 가 **같은 값**을 말하게
// 두면, 사람은 눈으로 대조하고 자동화는 문자열로 대조한다.

// repoIdentity — 이 저장소의 안정된 고유 식별자(7자). 못 구하면 "".
//
// **뿌리 커밋만으로는 부족하다.** 같은 초에 `gil init` 한 저장소 둘은 트리·메시지·작성자·
// 시각이 모두 같아 뿌리 sha 까지 같아진다(실측: 갓 만든 fixture 둘이 같은 값을 답했다).
// 정체를 말하라고 만든 값이 정체를 못 가르는 것이다. 그래서 **뿌리 커밋과 저장소의 실제
// 자리(git 최상위 경로)를 함께** 지문으로 접는다 — 같은 저장소는 언제 물어도 같은 값이고,
// 다른 저장소는 갓 태어난 쌍둥이라도 갈린다. 경로를 쓰되 화면의 경로 표시를 대신하지는
// 않는다: 사람은 경로를 읽고, 자동화는 이 한 덩어리를 대조한다.
//
// run 은 호출자의 git 실행기다 — 뷰어(viewerGit)와 CLI(gitTry)가 같은 값을 답해야 한다.
// 값이 갈리면 대조라는 행위 자체가 성립하지 않는다. 그래서 자리도 cwd 가 아니라 git 이
// 말하는 최상위로 잡는다(어느 하위 폴더에서 물어도 같은 답).
func repoIdentity(run func(...string) ([]byte, error)) string {
	out, err := run("rev-list", "--max-parents=0", "HEAD")
	if err != nil {
		return ""
	}
	lines := strings.Fields(string(out))
	if len(lines) == 0 {
		return ""
	}
	// 뿌리가 여럿이면(고아 브랜치를 합친 이력) **가장 오래된 것** — rev-list 는 최신부터 준다.
	root := lines[len(lines)-1]
	top, err := run("rev-parse", "--show-toplevel")
	where := ""
	if err == nil {
		where = strings.TrimSpace(string(top))
		if resolved, e := filepath.EvalSymlinks(where); e == nil {
			where = resolved
		}
	}
	sum := sha256.Sum256([]byte(root + "\n" + where))
	return hex.EncodeToString(sum[:])[:7]
}

// repoIdentityCLI — CLI 쪽에서 부르는 자리(handoff 안내 등).
func repoIdentityCLI() string {
	return repoIdentity(func(a ...string) ([]byte, error) {
		s, err := gitTry(a...)
		return []byte(s), err
	})
}

// viewerRepoAbs — 뷰어가 보고 있는 저장소의 절대경로. 화면 상단과 /whoami 가 같은 값을 쓴다.
func viewerRepoAbs() string {
	abs, err := filepath.Abs(viewerRepoDir)
	if err != nil {
		return viewerRepoDir
	}
	return abs
}

// repoStamp — 사람과 자동화가 같이 읽는 한 줄: "<절대경로> #<뿌리7자>".
// 경로만으로는 부족한 자리가 있다(심링크·같은 이름의 클론 둘). 둘을 함께 적는다.
func repoStamp(path, id string) string {
	if id == "" {
		return path
	}
	return path + " #" + id
}
