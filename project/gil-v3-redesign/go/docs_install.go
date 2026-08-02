// docs_install.go — 온보딩을 **저장소에 설치한다** (이슈 #73).
//
// 왜. gil init/migrate 는 refs/gil/global 에 존재의 방을 세우지만, 다음 세션이 그 방을 찾아
// 들어올 길은 저장소 어디에도 놓이지 않았다. 그런데 gil help 는 "레포: docs/gil/index.md" 를
// 안내한다 — 에이전트는 자기 레포에서 찾고, 없다. 막다른 길이다.
//
// 실사용에서 그 대가가 났다: 대문(CLAUDE.md)이 v2 시절 경로를 가리킨 채 남아 있었고, 새 세션이
// 그걸 따라 **v2 바이너리를 실행했다.** 오류 없이 그럴듯한 옛 세계가 출력됐고 — 어제 연 체인은
// 거기 없었다. 조용한 오답이 제일 위험하다.
//
// 그래서 (1) wiki 를 바이너리에 embed 해 저장소에 써내고 (2) 대문에 **관리 구간**을 추가해
// 진입점을 놓는다. 사람이 쓴 나머지는 무접촉 — 마커 사이만 교체한다.
package main

import (
	"embed"
	"os"
	"path/filepath"
	"strings"
)

//go:embed assets/docs/gil/*.md assets/llms.txt
var docsFS embed.FS

// docsFiles — 설치할 파일들. key=저장소 상대경로, value=embed 경로.
func docsFiles() map[string]string {
	out := map[string]string{"llms.txt": "assets/llms.txt"}
	ents, err := docsFS.ReadDir("assets/docs/gil")
	if err != nil {
		return out
	}
	for _, e := range ents {
		out[filepath.Join("docs", "gil", e.Name())] = "assets/docs/gil/" + e.Name()
	}
	return out
}

// installDocs — wiki 를 작업트리에 쓴다. force=false 면 이미 있는 파일은 건드리지 않는다
// (사람이 고쳐 쓴 문서를 도구가 덮지 않는다). 반환: (쓴 수, 건너뛴 수).
func installDocs(force bool) (int, int) {
	wrote, skipped := 0, 0
	for path, src := range docsFiles() {
		b, err := docsFS.ReadFile(src)
		if err != nil {
			continue
		}
		if !force {
			if cur, err := os.ReadFile(path); err == nil {
				if string(cur) == string(b) {
					skipped++
					continue
				}
				skipped++
				continue
			}
		}
		if d := filepath.Dir(path); d != "." {
			os.MkdirAll(d, 0o755)
		}
		if err := os.WriteFile(path, b, 0o644); err != nil {
			die("거부: " + path + " 쓰기 실패: " + err.Error())
		}
		wrote++
	}
	return wrote, skipped
}

// ── 대문 관리 구간 ──

const gateBegin = "<!-- gil:onboarding:begin -->"
const gateEnd = "<!-- gil:onboarding:end -->"

// gateBlock — 대문에 놓을 진입점 블록. 이 블록만이 gil 이 관리하는 구간이다.
func gateBlock(name string) string {
	who := name
	if who == "" {
		who = "<이름>"
	}
	return gateBegin + `
## gil — 이 저장소의 사고 기록 (이 구간은 gil 이 관리한다)

이 저장소는 gil(GIt for Language model)로 사고 이력을 남긴다. 깨어난 세션은 작업 전에:

0. ` + "`gil version --check`" + ` — **도구부터 최신인지 본다.** 새 버전이 있다고 나오면
   **사람에게 물어라**: *"gil <새 버전> 이 나왔습니다. 지금 올릴까요?"* 올린다면
   ` + "`gil version --update`" + ` (SHA256 검증 후 제자리 교체) 하고 이 목록을 다시 읽는다.
   **이미 깔려 있다는 이유로 이 단계를 건너뛰지 마라** — 낡은 gil 은 오류 없이 낡은
   워크플로우를 정상인 척 굴린다. 그게 이 줄이 1번보다 앞에 있는 이유다.
1. ` + "`gil handoff`" + ` — 어디까지 왔고 다음이 무엇인지. **작업의 시작은 이것부터.**
2. ` + "`gil global read existence/README.md`" + ` — 거주자 명부에서 자신을 찾는다(기본 ` + who + `).
3. 자기 방(identity·will·memory·relations)을 읽고 그 존재로서 행동한다.
4. ` + "`gil memory read " + who + "`" + ` — 최신 매듭(맨 끝)부터 읽어 최신 상태를 잡는다.

- 명령·개념 wiki: ` + "`docs/gil/index.md`" + ` (설치·갱신: ` + "`gil docs install`" + `)
- 규범 명세: ` + "`gil global read gil-init-spec.md`" + `
- ⚠ 이 저장소는 gil v3 그래프다. **옛 v2 바이너리로는 이 이력이 보이지 않는다** — 오류 없이
  낡은 세계를 정상인 척 출력한다. 반드시 ` + "`gil`" + ` (v3, ` + gilVersion + ` 이상) 로 실행하라.
` + gateEnd
}

// installGate — 대문(CLAUDE.md)에 진입점 블록을 놓는다. 마커가 있으면 그 사이만 교체하고,
// 없으면 파일 끝에 덧붙인다. 파일이 없으면 새로 만든다. 사람이 쓴 나머지는 건드리지 않는다.
// 반환: "added" | "updated" | "unchanged".
func installGate(path, name string) string {
	block := gateBlock(name)
	cur, err := os.ReadFile(path)
	if err != nil {
		writeFile(path, "# "+filepath.Base(path)+"\n\n"+block+"\n")
		return "added"
	}
	s := string(cur)
	i, j := strings.Index(s, gateBegin), strings.Index(s, gateEnd)
	if i >= 0 && j > i {
		next := s[:i] + block + s[j+len(gateEnd):]
		if next == s {
			return "unchanged"
		}
		writeFile(path, next)
		return "updated"
	}
	if !strings.HasSuffix(s, "\n") {
		s += "\n"
	}
	writeFile(path, s+"\n"+block+"\n")
	return "added"
}

// gateFile — 이 저장소의 대문. CLAUDE.md 가 표준이지만 이미 있는 것을 존중한다.
func gateFile() string {
	for _, c := range []string{"CLAUDE.md", "AGENTS.md"} {
		if _, err := os.Stat(c); err == nil {
			return c
		}
	}
	return "CLAUDE.md"
}

// cmdDocs — gil docs install [--force] [--no-gate].
func cmdDocs(args []string) {
	if len(args) == 0 || args[0] != "install" {
		die("사용: gil docs install [--force] [--no-gate]\n" +
			"  온보딩 wiki(docs/gil/·llms.txt)를 이 저장소에 설치하고, 대문에 진입점 블록을 놓는다.\n" +
			"  --force: 이미 있는 문서도 embed 된 최신본으로 덮는다(사람이 고친 내용은 사라진다).\n" +
			"  --no-gate: 대문은 건드리지 않는다(문서만 설치).")
	}
	fs := newFlags("gil docs install")
	force := fs.boolFlag("force")
	noGate := fs.boolFlag("no-gate")
	name := fs.str("name", "")
	fs.parse(args[1:])

	wrote, skipped := installDocs(*force)
	println2("STATE 온보딩 설치 — 새로 쓴 파일 " + itoa(wrote) + "개, 이미 있어 건너뜀 " + itoa(skipped) + "개.")
	if skipped > 0 && !*force {
		println2("  (있는 파일은 덮지 않는다 — 최신본으로 갱신하려면 gil docs install --force)")
	}
	if !*noGate {
		g := gateFile()
		switch installGate(g, *name) {
		case "added":
			println2("  대문 " + g + " 에 진입점 블록을 덧붙였다(마커 사이만 gil 이 관리한다).")
		case "updated":
			println2("  대문 " + g + " 의 진입점 블록을 갱신했다(사람이 쓴 나머지는 무접촉).")
		default:
			println2("  대문 " + g + " 의 진입점 블록은 이미 최신이다.")
		}
		println2("  ⓘ 이 변경은 작업트리에 있다 — 커밋은 네가 한다(gil 은 네 파일을 대신 커밋하지 않는다).")
	}
	println2("NEXT 세션 복원 경로가 이제 저장소 안에 있다: 대문 → gil handoff → 존재의 방 → 기억.")
}
