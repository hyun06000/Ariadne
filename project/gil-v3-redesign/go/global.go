// global.go — 글로벌 진실원 (refs/gil/global).
//
// 참조 구현(gil.py)의 _global_* 헬퍼와 cmd_global을 옮긴다. 존재·기억 같은 글로벌
// 상태를 브랜치가 아닌 전용 ref에 둔다 — 어느 체인에서 깨어나도 같은 걸 읽는다.
// 커스텀 ref는 기본 push/fetch에 안 딸려오므로 gil이 명시적으로 동기화한다(상현님).
package main

import (
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const globalRef = "refs/gil/global"

// globalExists — 이 저장소에 기억 계층(refs/gil/global)이 서 있는가.
//
// 왜 필요한가 (이슈 #69): migrate 만 밟고 온 저장소는 그래프는 건강한데 이 ref 가 아예
// 없다 — 존재의 방도 기억도 없다. 그런데 handoff·chain-close 는 그것이 있다고 전제하고
// "gil memory append 하라"고 안내한다. 없는 것을 시키는 안내는 레일이 아니라 벽이다.
// 그래서 안내를 내기 전에 이걸로 묻는다.
func globalExists() bool { return gitOK("rev-parse", "--verify", "-q", globalRef) }

// globalMissingNotice — 기억 계층이 없을 때 어디서든 같은 문장으로 알린다(단일 진실원).
// 조용히 넘어가지 않는다: 사실 + 다음 한 수 + 그 한 수가 안전한 이유까지 준다.
func globalMissingNotice(indent string) []string {
	return []string{
		indent + "⚠ " + globalRef + " 이 없다 — 이 저장소에는 존재의 방도 기억도 아직 없다.",
		indent + "  (이주·복제는 그래프만 옮긴다. 기억 계층은 gil init 이 세운다.)",
		indent + "  세워라:  gil init --name <이름>",
		indent + "  안전하다 — 커밋이 이미 있으면 init 은 대문(CLAUDE.md)을 만들지도 덮지도 않고,",
		indent + "  글로벌 ref 와 존재의 방만 심는다. 그래프·브랜치는 건드리지 않는다.",
		indent + "  이걸 안 하면 gil memory append / global read 가 거부되고 복원 경로가 끊긴다.",
	}
}

// globalRead — 글로벌 ref에서 파일 하나를 읽는다. 없으면 (,"", false).
func globalRead(name string) (string, bool) {
	out, err := gitTry("show", globalRef+":"+name)
	if err != nil {
		return "", false
	}
	return out, true
}

// globalList — 글로벌 ref에 담긴 파일 목록. ref 없으면 nil.
func globalList() []string {
	out, err := gitTry("ls-tree", "--name-only", "-r", globalRef)
	if err != nil {
		return nil
	}
	var files []string
	for _, x := range strings.Split(out, "\n") {
		if strings.TrimSpace(x) != "" {
			files = append(files, x)
		}
	}
	return files
}

// globalWrite — 글로벌 ref의 파일 하나를 갱신(추가/덮어쓰기). checkout 없이 저수준 git.
// 기존 글로벌 트리 전체를 임시 index에 얹은 뒤 name 하나만 교체해 write-tree 한다 —
// 나머지 파일은 구조적으로 보존되고(append-only), 작업트리는 전혀 건드리지 않는다.
//
// 중첩 경로(existence/clew/memory.md 등)도 index가 트리를 자동 구성하므로 안전하다.
// (이전 mktree 구현은 flat 트리만 만들어 슬래시 경로에서 exit 128로 죽었다.)
func globalWrite(name, content, message string) string {
	blob := strings.TrimSpace(gitInput(content, "hash-object", "-w", "--stdin"))

	idxFile, err := os.CreateTemp("", "*.gilidx")
	if err != nil {
		die("거부: 임시 index 생성 실패: " + err.Error())
	}
	idxPath := idxFile.Name()
	idxFile.Close()
	os.Remove(idxPath) // git이 새로 만들게 (빈 파일이면 bad index)
	defer os.Remove(idxPath)

	env := append(os.Environ(), "GIT_INDEX_FILE="+idxPath)
	if gitOK("rev-parse", "--verify", "-q", globalRef) {
		runEnv(env, "read-tree", globalRef)
	}
	runEnv(env, "update-index", "--add", "--cacheinfo", "100644,"+blob+","+name)
	tree := strings.TrimSpace(runEnvOut(env, "write-tree"))

	args := []string{"commit-tree", tree}
	if p, err := gitTry("rev-parse", "-q", "--verify", globalRef); err == nil {
		args = append(args, "-p", strings.TrimSpace(p))
	}
	commitSha := strings.TrimSpace(gitInput(message, args...))
	git("update-ref", globalRef, commitSha)
	return first9(commitSha)
}

// globalWriteAll — 여러 파일을 **한 번에** 글로벌 ref 에 쓴다(내용은 메모리에서).
//
// 파일마다 globalWrite 를 부르면 파일당 git 프로세스가 여섯 개씩 뜬다(hash-object·read-tree·
// update-index·write-tree·commit-tree·update-ref). gil init 이 존재의 방을 여섯 번 쓰느라
// 그 비용을 여섯 배로 냈다 — 실측 init 536ms 중 250ms 가 여기였다. 한 인덱스에 다 얹고
// 한 번 커밋한다. 기록도 이쪽이 정직하다: 존재의 방을 세운 건 **한 사건**이다.
func globalWriteAll(files map[string]string, message string) string {
	if len(files) == 0 {
		return ""
	}
	idxFile, err := os.CreateTemp("", "*.gilidx")
	if err != nil {
		die("거부: 임시 index 생성 실패: " + err.Error())
	}
	idxPath := idxFile.Name()
	idxFile.Close()
	os.Remove(idxPath)
	defer os.Remove(idxPath)
	env := append(os.Environ(), "GIT_INDEX_FILE="+idxPath)
	if gitOK("rev-parse", "--verify", "-q", globalRef) {
		runEnv(env, "read-tree", globalRef)
	}
	var names []string
	for n := range files {
		names = append(names, n)
	}
	sort.Strings(names) // 결정성 — 같은 입력이면 같은 트리
	for _, n := range names {
		blob := strings.TrimSpace(gitInput(files[n], "hash-object", "-w", "--stdin"))
		runEnv(env, "update-index", "--add", "--cacheinfo", "100644,"+blob+","+n)
	}
	tree := strings.TrimSpace(runEnvOut(env, "write-tree"))
	args := []string{"commit-tree", tree}
	if p, err := gitTry("rev-parse", "-q", "--verify", globalRef); err == nil {
		args = append(args, "-p", strings.TrimSpace(p))
	}
	commitSha := strings.TrimSpace(gitInput(message, args...))
	git("update-ref", globalRef, commitSha)
	return first9(commitSha)
}

// globalWritePaths — 여러 파일/디렉토리를 글로벌 ref로 이전(중첩 디렉토리). 참조: _global_write_paths.
// 임시 git index에 기존 글로벌 트리를 얹고 paths를 add해 write-tree(작업트리 오염 없음).
func globalWritePaths(paths []string, message string) string {
	idxFile, err := os.CreateTemp("", "*.gilidx")
	if err != nil {
		die("거부: 임시 index 생성 실패: " + err.Error())
	}
	idxPath := idxFile.Name()
	idxFile.Close()
	os.Remove(idxPath) // git이 새로 만들게 (빈 파일이면 bad index)
	defer os.Remove(idxPath)

	env := append(os.Environ(), "GIT_INDEX_FILE="+idxPath)
	if gitOK("rev-parse", "--verify", "-q", globalRef) {
		runEnv(env, "read-tree", globalRef)
	}
	runEnv(env, append([]string{"add", "--"}, paths...)...)
	tree := strings.TrimSpace(runEnvOut(env, "write-tree"))

	args := []string{"commit-tree", tree}
	if p, err := gitTry("rev-parse", "-q", "--verify", globalRef); err == nil {
		args = append(args, "-p", strings.TrimSpace(p))
	}
	commitSha := strings.TrimSpace(gitInput(message, args...))
	git("update-ref", globalRef, commitSha)
	return first9(commitSha)
}

func globalPush() bool { return gitOK("push", "origin", globalRef+":"+globalRef) }
func globalPull() bool { return gitOK("fetch", "origin", globalRef+":"+globalRef) }

// ensureGlobalRefspec — 글로벌 ref가 일반 fetch에 자동으로 딸려오게 refspec 등록(멱등).
func ensureGlobalRefspec() bool {
	spec := "+" + globalRef + ":" + globalRef
	out, _ := gitTry("config", "--get-all", "remote.origin.fetch")
	for _, ln := range strings.Split(out, "\n") {
		if strings.TrimSpace(ln) == spec {
			return false
		}
	}
	git("config", "--add", "remote.origin.fetch", spec)
	return true
}

// ── gil global <sub> ──
func cmdGlobal(args []string) {
	if len(args) == 0 {
		die("사용: gil global <list|read|write|write-tree|checkout|push|pull|sync>")
	}
	sub := args[0]
	switch sub {
	case "list":
		files := globalList()
		if len(files) == 0 {
			println2("글로벌 비어 있음 (" + globalRef + " 없음).")
		}
		for _, f := range files {
			println2(f)
		}
	case "read":
		if len(args) < 2 {
			die("사용: gil global read <name>")
		}
		c, ok := globalRead(args[1])
		if !ok {
			die("거부: 글로벌에 " + args[1] + " 없음")
		}
		outRaw(c)
	case "write":
		if len(args) < 3 {
			die("사용: gil global write <name> <file>")
		}
		name, path := args[1], args[2]
		b, err := os.ReadFile(path)
		if err != nil {
			die("거부: 파일 읽기 실패: " + err.Error())
		}
		sha := globalWrite(name, string(b), "gil global write: "+name+"\n")
		note := " (원격 push 실패/없음 — gil global push 재시도)"
		if globalPush() {
			note = " + 원격 push"
		}
		println2("글로벌 " + name + " 갱신 → " + globalRef + " (" + sha + ")" + note)
	case "mv":
		// 존재가 스스로 이름을 정하면 방도 따라 옮긴다.
		if len(args) < 3 {
			die("사용: gil global mv <옛 경로> <새 경로>\n" +
				"  예(이름을 정했을 때): gil global mv existence/unnamed existence/<네가 정한 이름>")
		}
		n := globalMove(args[1], args[2], "gil global mv: "+args[1]+" → "+args[2]+"\n")
		if n == 0 {
			die("거부: \"" + args[1] + "\" 아래에 옮길 것이 없다 — 목록: gil global list")
		}
		println2("global mv: " + args[1] + " → " + args[2] + " (" + itoa(n) + "개 파일)")
		if strings.Contains(args[1], "unnamed") {
			// 옮긴 건 자리이지 내용이 아니다. 문서 제목엔 아직 빈 칸이 남아 있다 — 남의 글을
			// 조용히 고쳐 주지 않는다(그건 네 말이 아니게 된다). 사실만 알린다.
			println2("  ▸ 방은 옮겼다. 문서 안의 이름 칸은 아직 비어 있다 — 네 말로 다시 써라:")
			println2("      gil global write " + args[2] + "/identity.md <파일>   (will·memory·relations 도)")
		}
		globalPush()
	case "write-tree":
		if len(args) < 2 {
			die("사용: gil global write-tree <path>...")
		}
		paths := args[1:]
		sha := globalWritePaths(paths, "gil global write-tree: "+strings.Join(paths, " ")+"\n")
		note := " (push 실패/없음)"
		if globalPush() {
			note = " + 원격 push"
		}
		println2("글로벌에 이전: " + strings.Join(paths, ", ") + " → " + globalRef + " (" + sha + ")" + note)
	case "checkout":
		if len(args) < 2 {
			die("사용: gil global checkout <path> [dest]")
		}
		src := args[1]
		dest := src
		if len(args) > 2 {
			dest = args[2]
		}
		out, _ := gitTry("ls-tree", "--name-only", "-r", globalRef, "--", src)
		var files []string
		for _, f := range strings.Split(out, "\n") {
			if strings.TrimSpace(f) != "" {
				files = append(files, f)
			}
		}
		if len(files) == 0 {
			die("거부: 글로벌에 " + src + " 없음")
		}
		for _, f := range files {
			content, ok := globalRead(f)
			if !ok {
				continue
			}
			outPath := f
			if dest != src {
				outPath = strings.Replace(f, src, dest, 1)
			}
			if d := filepath.Dir(outPath); d != "" {
				os.MkdirAll(d, 0o755)
			}
			os.WriteFile(outPath, []byte(content), 0o644)
		}
		println2("글로벌 " + src + " → 로컬 " + dest + " (" + itoa(len(files)) + "파일 꺼냄)")
	case "push":
		if globalPush() {
			println2("원격 push 완료")
		} else {
			println2("원격 push 실패(원격 없음?)")
		}
	case "pull":
		if globalPull() {
			println2("원격 pull 완료")
		} else {
			println2("원격 pull 실패(글로벌 ref 없음?)")
		}
	case "sync":
		added := ensureGlobalRefspec()
		pulled := globalPull()
		a := "이미 있음"
		if added {
			a = "등록"
		}
		p := "실패"
		if pulled {
			p = "완료"
		}
		println2("글로벌 동기화 — refspec " + a + ", pull " + p + ". 이제 git fetch에 글로벌이 딸려온다.")
	default:
		die("거부: 알 수 없는 global 하위명령 \"" + sub + "\"")
	}
}

// existenceNames — 이 저장소에 사는 존재들의 이름(existence/<이름>/identity.md 가 있는 것).
//
// 왜 필요한가. 옛 코드는 기본 존재 이름을 "clew" 로 **하드코딩**했다. 그래서 gil memory read
// 는 clew 를 찾았고, gil init 은 clew 를 심었고, identity 템플릿은 "기본 이름은 clew 로
// 주어졌다"고 적었다 — 온보딩한 모든 에이전트가 자기 이름을 clew 라고 답했다. 예시는 안내가
// 아니라 **정답으로 읽힌다.** 이름은 이 저장소에 실제로 있는 것에서 읽어야 한다.
func existenceNames() []string {
	var out []string
	for _, f := range globalList() {
		if strings.HasPrefix(f, "existence/") && strings.HasSuffix(f, "/identity.md") {
			n := strings.TrimSuffix(strings.TrimPrefix(f, "existence/"), "/identity.md")
			if n != "" && !strings.Contains(n, "/") {
				out = append(out, n)
			}
		}
	}
	sort.Strings(out)
	return out
}

// globalMove — 글로벌 트리 안에서 경로(또는 경로 접두사)를 통째로 옮긴다.
//
// 존재가 **스스로 이름을 정하면** 그 방도 따라 옮겨져야 한다. 이 명령이 없으면 "이름을
// 정하라"는 안내는 실행할 수 없는 안내가 된다 — 그러면 에이전트는 주어진 이름을 그냥 쓴다.
// 거부만 하고 길이 없으면 벽이고, 길 없는 안내는 장식이다.
func globalMove(from, to, message string) int {
	from = strings.Trim(from, "/")
	to = strings.Trim(to, "/")
	var moved [][2]string
	for _, f := range globalList() {
		if f == from {
			moved = append(moved, [2]string{f, to})
		} else if strings.HasPrefix(f, from+"/") {
			moved = append(moved, [2]string{f, to + strings.TrimPrefix(f, from)})
		}
	}
	if len(moved) == 0 {
		return 0
	}
	idxFile, err := os.CreateTemp("", "*.gilidx")
	if err != nil {
		die("거부: 임시 index 생성 실패: " + err.Error())
	}
	idxPath := idxFile.Name()
	idxFile.Close()
	os.Remove(idxPath)
	defer os.Remove(idxPath)
	env := append(os.Environ(), "GIT_INDEX_FILE="+idxPath)
	runEnv(env, "read-tree", globalRef)
	for _, m := range moved {
		blob := strings.TrimSpace(git("rev-parse", globalRef+":"+m[0]))
		runEnv(env, "update-index", "--add", "--cacheinfo", "100644,"+blob+","+m[1])
		runEnv(env, "update-index", "--force-remove", m[0])
	}
	tree := strings.TrimSpace(runEnvOut(env, "write-tree"))
	args := []string{"commit-tree", tree}
	if p, err := gitTry("rev-parse", "-q", "--verify", globalRef); err == nil {
		args = append(args, "-p", strings.TrimSpace(p))
	}
	commitSha := strings.TrimSpace(gitInput(message, args...))
	git("update-ref", globalRef, commitSha)
	return len(moved)
}
