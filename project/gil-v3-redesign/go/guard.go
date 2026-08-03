// guard.go — **git commit 과 gil step 이 섞이는 것을 막는다** (상현님: "괴리의 주범").
//
// 왜 이게 필요한가. gil 의 약속은 "이 저장소의 사고이력이 커밋 그래프에 그대로 있다"는
// 것이다. 그런데 같은 나무에 평범한 `git commit` 이 섞이면 그 약속이 조용히 깨진다:
// 스텝 사이에 트레일러 없는 커밋이 끼고, 사이클의 산출물이 어느 스텝의 것인지 알 수 없게
// 되고, 나중에 세는 모든 것(계보·적층·층·뒤처짐)이 실제와 갈린다. 사람 눈에는 git log 가
// 멀쩡하니 조용하다 — 성실히 일한 세션일수록 더 많이 섞는다.
//
// 두 겹으로 막는다. 한 겹만으로는 원리적으로 부족하기 때문이다:
//
//	훅(예방)  — pre-commit 이 체인/사이클 브랜치의 평범 커밋을 거부한다. 실질적으로 가장
//	            강하지만 `git commit --no-verify` 로 언제나 뚫린다(git 의 설계다 — 클라이언트
//	            훅은 강제될 수 없다). 그러니 이걸 벽이라 부르면 안 된다.
//	fsck(탐지) — 뚫고 들어온 것을 **나중에라도 반드시** 짚는다. 훅이 없는 클론에서도 돈다.
//
// 예방만 두면 뚫린 것을 아무도 모르고, 탐지만 두면 이미 섞인 뒤에 안다. 둘 다 있어야 한다.
package main

import (
	"os"
	"path/filepath"
	"strings"
)

// guardHookRel — 훅이 사는 자리. `.git/hooks` 가 아니라 **작업 트리 안**이다: .git 안의 훅은
// 클론에 안 따라가서, 새 머신에서 저장소를 받은 사람은 아무 보호 없이 시작한다. 여기 두고
// core.hooksPath 로 가리키면 파일 자체는 저장소에 실려 간다(설정 한 줄은 여전히 로컬이라
// `gil guard install` 이 다시 필요하다 — git 이 클론 시 설정을 실행하지 않기 때문이다).
const guardHookRel = ".gil/hooks"

// guardHookScript — pre-commit 훅. POSIX sh 하나로 둔다(윈도우도 git 이 bash 를 들고 온다).
//
// 판정은 **선언으로** 한다: 지금 서 있는 자리가 gil 이 기록하는 가지인가(HEAD 커밋에
// Gil-Chain 트레일러가 있는가). 이름 규칙으로 때려잡지 않는 이유는, 체인 이름은 사람이
// 짓는 것이라 어떤 규칙도 언젠가 틀리기 때문이다.
const guardHookScript = `#!/bin/sh
# gil guard — 이 저장소의 사고이력은 gil 이 기록한다 (gil guard install 이 놓았다).
#
# 지우거나 끄려면:  gil guard uninstall
# 이 커밋 하나만 예외로:  GIL_ALLOW_RAW=1 git commit …   (또는 git commit --no-verify)
# 어느 쪽이든 fsck 가 나중에 그 커밋을 짚는다 — 감춰지지는 않는다.

# gil 자신이 만드는 커밋.
[ -n "$GIL_COMMIT" ] && exit 0
# 명시적 예외 — 사실이 셸 이력에 남는다.
[ -n "$GIL_ALLOW_RAW" ] && exit 0
# 충돌 해결 커밋(gil merge 가 멈춘 자리에서 사람이 손으로 맺는 것).
[ -e "$(git rev-parse --git-dir)/MERGE_HEAD" ] && exit 0

branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "")
case "$branch" in
	main|master|dev) exit 0 ;;   # 층은 평범 커밋의 자리다(대문 문서·배포 머지)
esac

# 여기가 gil 이 기록하는 가지인가 — HEAD 가 gil 커밋이면 그렇다.
gilchain=$(git log -1 --format='%(trailers:key=Gil-Chain,valueonly)' 2>/dev/null | tr -d '\n\r ')
[ -z "$gilchain" ] && exit 0

cat >&2 <<'MSG'
거부: 이 가지의 기록은 gil 이 만든다 — git commit 이 아니다.

  지금 자리는 gil 이 기록하는 체인/사이클 가지다. 여기에 평범한 커밋을 끼우면 그 변경은
  어느 스텝의 것도 아니게 되고, 이후 gil 이 세는 모든 것(계보·적층·층·뒤처짐)이 실제와
  갈린다. 사람 눈에는 git log 가 멀쩡하니 조용히 갈린다.

  ▸ 작업의 결과라면 스텝으로 새겨라:
      gil step <chain>/<cycle> --kind <define|hypothesis|verify|analyze|success|fail|pending> …
    (파일 변경은 그 스텝 커밋에 함께 실린다 — 따로 커밋하지 마라.)
  ▸ 이 가지의 일이 아니면 자리를 옮겨라:  gil goto <chain>/<cycle>  또는  git switch dev
  ▸ 정말 예외라면:  GIL_ALLOW_RAW=1 git commit …
    (막지는 않되 gil fsck 가 그 커밋을 '섞인 기록'으로 짚는다 — 감춰지지 않는다.)
MSG
exit 1
`

// guardHookDir — 이 저장소의 훅 디렉토리 절대경로("" = git 저장소가 아님).
func guardHookDir() string {
	top, err := gitTry("rev-parse", "--show-toplevel")
	if err != nil {
		return ""
	}
	return filepath.Join(strings.TrimSpace(top), filepath.FromSlash(guardHookRel))
}

// guardInstalled — 훅 파일이 있고 core.hooksPath 가 그걸 가리키는가.
func guardInstalled() bool {
	dir := guardHookDir()
	if dir == "" {
		return false
	}
	if _, err := os.Stat(filepath.Join(dir, "pre-commit")); err != nil {
		return false
	}
	p, err := gitTry("config", "--get", "core.hooksPath")
	if err != nil {
		return false
	}
	return strings.TrimSpace(p) == guardHookRel
}

// installGuard — 훅을 놓고 core.hooksPath 를 건다. 이미 있으면 덮어쓴다(갱신).
// 반환: 사람에게 보일 줄들.
func installGuard() []string {
	dir := guardHookDir()
	if dir == "" {
		return []string{"  ⚠ git 저장소가 아니다 — 훅을 놓을 자리가 없다."}
	}
	// 남의 hooksPath 를 말없이 빼앗지 않는다 — 이미 다른 자리를 쓰고 있으면 그 사실을 말한다.
	if p, err := gitTry("config", "--get", "core.hooksPath"); err == nil {
		if cur := strings.TrimSpace(p); cur != "" && cur != guardHookRel {
			return []string{
				"  ⚠ 이 저장소는 이미 다른 훅 경로를 쓴다: core.hooksPath = " + cur,
				"     덮어쓰지 않았다. 그쪽 pre-commit 에 gil guard 를 직접 얹거나, 비운 뒤 다시 걸어라:",
				"       git config --unset core.hooksPath && gil guard install",
			}
		}
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return []string{"  ⚠ 훅 디렉토리를 못 만들었다: " + err.Error()}
	}
	hook := filepath.Join(dir, "pre-commit")
	if err := os.WriteFile(hook, []byte(guardHookScript), 0o755); err != nil {
		return []string{"  ⚠ 훅을 못 썼다: " + err.Error()}
	}
	if _, err := gitTry("config", "core.hooksPath", guardHookRel); err != nil {
		return []string{"  ⚠ core.hooksPath 설정 실패: " + err.Error()}
	}
	return []string{
		"  🛡 gil guard 설치됨 — 체인/사이클 가지의 평범한 git commit 을 막는다(" + guardHookRel + "/pre-commit).",
		"     훅 파일은 저장소에 실려 클론에 따라간다. 다만 **설정 한 줄은 로컬**이라, 새 클론에서는",
		"     한 번 더 걸어야 한다: gil guard install   (git 은 클론 시 설정을 실행하지 않는다)",
		"     예외: GIL_ALLOW_RAW=1 git commit …  ·  끄기: gil guard uninstall",
		"     훅은 뚫릴 수 있다(git commit --no-verify) — 그래서 gil fsck 가 섞인 커밋을 따로 센다.",
	}
}

// cmdGuard — gil guard [install|uninstall|status].
func cmdGuard(args []string) {
	sub := "status"
	if len(args) > 0 && !strings.HasPrefix(args[0], "-") {
		sub = args[0]
	}
	switch sub {
	case "install":
		for _, ln := range installGuard() {
			println2(ln)
		}
	case "uninstall":
		dir := guardHookDir()
		if dir != "" {
			_ = os.Remove(filepath.Join(dir, "pre-commit"))
		}
		_, _ = gitTry("config", "--unset", "core.hooksPath")
		println2("  gil guard 껐다 — 이제 이 저장소에서 평범한 git commit 이 막히지 않는다.")
		println2("  (섞인 커밋은 여전히 gil fsck 가 짚는다 — 탐지는 끄지 않는다.)")
	case "status":
		if guardInstalled() {
			println2("gil guard: 켜져 있다 (" + guardHookRel + "/pre-commit)")
		} else {
			println2("gil guard: 꺼져 있다 — 켜려면: gil guard install")
			println2("  체인/사이클 가지에 평범한 git commit 이 섞이면 gil 이 세는 모든 것이 실제와 갈린다.")
		}
		if raw := rawCommitsOnGilBranches(); len(raw) > 0 {
			println2("  ⚠ 이미 섞인 커밋이 " + itoa(len(raw)) + "개 있다 — gil fsck 가 자리를 짚는다.")
		}
	default:
		die("gil guard: 알 수 없는 서브명령 \"" + sub + "\" — [install uninstall status]")
	}
}

// rawCommitsOnGilBranches — **섞인 기록을 탐지한다**(훅이 없거나 뚫린 뒤에도 돈다).
//
// 판정: 체인/사이클 브랜치에서 첫-부모로 거슬러 오르며, gil 커밋들 **사이에** 낀 트레일러
// 없는 커밋. 브랜치의 시작 이전(체인이 갈라져 나온 자리보다 아래)은 이 체인의 일이 아니므로
// 세지 않는다 — 그래서 "gil 커밋을 한 번이라도 만난 뒤"부터 센다.
// 반환: "<브랜치> <sha> <제목>" 줄들.
func rawCommitsOnGilBranches() []string {
	out, err := gitTry("for-each-ref", "--format=%(refname:short)", "refs/heads/")
	if err != nil {
		return nil
	}
	var found []string
	seen := map[string]bool{}
	for _, br := range strings.Fields(out) {
		if isLayerBranch(br) {
			continue
		}
		log, err := gitTry("log", "--first-parent", "-n", "400",
			"--format=%h"+fsep+"%s"+fsep+"%(trailers:key=Gil-Chain,valueonly,unfold=true)", br)
		if err != nil {
			continue
		}
		lines := strings.Split(strings.TrimSpace(log), "\n")
		hitGil := false
		var pending []string
		// 최신 → 과거 순. gil 커밋을 만난 **뒤**(즉 그보다 위에 쌓인) 평범 커밋만 센다.
		for _, ln := range lines {
			f := strings.SplitN(ln, fsep, 3)
			if len(f) < 3 {
				continue
			}
			sha, subj, chain := strings.TrimSpace(f[0]), strings.TrimSpace(f[1]), strings.TrimSpace(f[2])
			if chain != "" {
				hitGil = true
				// 이 gil 커밋 위에 쌓여 있던 평범 커밋들은 **가지 안에 낀 것**이다.
				for _, p := range pending {
					if !seen[p] {
						seen[p] = true
						found = append(found, p)
					}
				}
				pending = nil
				continue
			}
			if !hitGil {
				pending = append(pending, br+" "+sha+" "+clipLine(subj, 60))
				continue
			}
			// gil 커밋 아래(더 과거)의 평범 커밋 = 이 가지가 시작되기 전 — 이 체인의 일이 아니다.
			break
		}
	}
	return found
}

// rawCommitNotice — fsck 가 내는 '섞인 기록' 고지. 위반으로 세는 대신 고지인 이유:
// 이미 벌어진 일이고, append-only 라 되돌릴 수 없으며, 무엇보다 **어느 스텝의 것인지 사람만
// 안다**. 다만 감추지는 않는다 — 없는 게 죄가 아니라 감춘 게 죄다.
func rawCommitNotice() string {
	raw := rawCommitsOnGilBranches()
	if len(raw) == 0 {
		return ""
	}
	L := []string{"  ⚑ 섞인 기록: 체인/사이클 가지에 gil 이 만들지 않은 커밋이 " + itoa(len(raw)) + "개 있다 —"}
	for i, r := range raw {
		if i >= 5 {
			L = append(L, "       … 그 밖에 "+itoa(len(raw)-5)+"개")
			break
		}
		L = append(L, "       "+r)
	}
	L = append(L, "     이 변경들은 어느 스텝의 것도 아니다 — gil 이 세는 계보·적층·층이 실제와 갈린다.")
	if !guardInstalled() {
		L = append(L, "     다시 섞이지 않게: gil guard install  (체인 가지의 평범 커밋을 막는다)")
	}
	return strings.Join(L, "\n")
}
