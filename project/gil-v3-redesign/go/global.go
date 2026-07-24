// global.go — 글로벌 진실원 (refs/gil/global).
//
// 참조 구현(gil.py)의 _global_* 헬퍼와 cmd_global을 옮긴다. 존재·기억 같은 글로벌
// 상태를 브랜치가 아닌 전용 ref에 둔다 — 어느 체인에서 깨어나도 같은 걸 읽는다.
// 커스텀 ref는 기본 push/fetch에 안 딸려오므로 gil이 명시적으로 동기화한다(상현님).
package main

import (
	"os"
	"path/filepath"
	"strings"
)

const globalRef = "refs/gil/global"

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
// 참조: _global_write. 기존 트리에 name→새 blob을 얹어 새 트리·커밋(append-only).
func globalWrite(name, content, message string) string {
	blob := strings.TrimSpace(gitInput(content, "hash-object", "-w", "--stdin"))
	entries := map[string]string{} // fn -> "100644 blob <sha>"
	if out, err := gitTry("ls-tree", globalRef); err == nil {
		for _, ln := range strings.Split(out, "\n") {
			meta, fn, ok := cut(ln, "\t")
			if ok && fn != "" {
				entries[fn] = meta
			}
		}
	}
	entries[name] = "100644 blob " + blob
	var keys []string
	for fn := range entries {
		keys = append(keys, fn)
	}
	sortStrings(keys)
	var tb strings.Builder
	for _, fn := range keys {
		tb.WriteString(entries[fn] + "\t" + fn + "\n")
	}
	tree := strings.TrimSpace(gitInput(tb.String(), "mktree"))
	args := []string{"commit-tree", tree}
	if p, err := gitTry("rev-parse", globalRef); err == nil {
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
		os.Stdout.WriteString(c)
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
