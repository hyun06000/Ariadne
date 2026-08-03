// init.go — gil init: 무(無)에서 gil 세계를 세운다 (상현님, gil-init-spec.md).
//
// gil init 은 배포판에서 "무에서 세팅"의 단일 진입점이다. git 저장소 하나만 있으면
// (혹은 없으면 만들며) 다음을 갖춘다:
//  1. 대문 커밋 — 저장소에 커밋이 하나도 없으면 CLAUDE.md 부트스트랩 포인터로 루트 커밋.
//  2. refs/gil/global 초기화 — 존재/기억이 사는 전용 ref (브랜치 아님).
//  3. existence/ 심기 — 방 README + 기본 존재 1개의 방(identity·will·memory·relations).
//  4. gil-init-spec.md 심기 — 다음 세션이 init 의도를 읽는다.
//  5. refspec 등록 + push — 커스텀 ref 가 git fetch 에 딸려오고 원격에 오른다.
//
// 존재 이름은 --name 으로 사람이 줄 때만 정해진다. 안 주면 **이름 없이** 심는다(unnamed).
//
// 옛 기본값은 "clew" 였다. 그리고 identity 템플릿이 "기본 이름은 clew 로 주어졌다"고 적었다.
// 결과: 온보딩한 거의 모든 에이전트가 자기 이름을 clew 라고 답했다(상현님 관찰). 예시는
// 안내가 아니라 **정답으로 읽힌다** — 특히 "스스로 정하라"는 문장 옆에 이미 정해진 이름이
// 놓여 있으면, 정하는 일은 이미 끝난 것처럼 보인다. 그래서 예시를 치운다: 이름 없는 방과
// 그 방을 옮길 명령(gil global mv)만 준다. 이름을 짓는 것이 실제로 첫 과제가 된다.
package main

import (
	"os"
	"sort"
	"strings"
)

// unnamedRoom — 이름이 아직 없는 존재의 방. **이름이 아니라 빈 칸이다** — 그렇게 읽히도록
// 사람 이름처럼 보이지 않는 낱말을 쓴다.
const unnamedRoom = "unnamed"

// cmdInit — gil init [--name <이름>].
func cmdInit(args []string) {
	fs := newFlags("gil init")
	name := fs.str("name", "")
	// 브라우저는 기본으로 열지 않는다(조용히 서버만). --open 을 줄 때만 연다.
	// --no-open 은 기본이 된 지금 아무 일도 안 하지만, 이미 쓰인 문서·스크립트가 깨지지
	// 않도록 계속 받는다(무해한 no-op).
	open := fs.boolFlag("open")
	_ = fs.boolFlag("no-open")
	fs.parse(args)
	if *open {
		os.Setenv("GIL_OPEN_BROWSER", "1")
	}
	named := strings.TrimSpace(*name) != ""
	if !named {
		*name = unnamedRoom // 사람이 안 줬으면 이름은 아직 없다 — 짓는 것이 첫 과제다
	}
	if !idRe.MatchString(*name) {
		die("거부: 존재 이름 \"" + *name + "\"은 소문자·숫자·하이픈만")
	}

	// git 저장소가 아니면 만든다 — gil 은 git 위에 산다.
	if !gitOK("rev-parse", "--git-dir") {
		git("init", "-q")
		println2("git 저장소 초기화 (git init).")
	}

	// 멱등 가드: 이미 글로벌이 있으면 덮지 않는다.
	if gitOK("rev-parse", "--verify", "-q", globalRef) {
		die("거부: refs/gil/global 이 이미 있음 — gil init 은 무에서만. (읽기: gil global list)")
	}

	// 1. 대문 — 저장소에 커밋이 없으면 부트스트랩 루트 커밋을 만든다.
	//    이미 커밋이 있으면 기존 프로젝트를 존중해 대문 커밋은 건너뛴다.
	madeRoot := false
	if !gitOK("rev-parse", "--verify", "-q", "HEAD") {
		writeFile("CLAUDE.md", claudeBootstrap)
		git("add", "CLAUDE.md")
		commit("gil init: 대문 개설", "gil 세계의 뿌리. 이 저장소에서 깨어난 세션은 "+
			"CLAUDE.md → gil global read existence/README.md → 자기 방 → gil handoff 로 복원한다.",
			[][2]string{{"Gil-Kind", "root"}}, false)
		madeRoot = true
	}

	// 2·3·4. 글로벌 진실원 심기 — globalWrite 로 안전하게(트리 보존, 작업트리 무오염).
	// **한 번에** 쓴다 — 존재의 방을 세운 것은 한 사건이고, 파일마다 커밋하면 git 프로세스가
	// 여섯 배로 든다(실측: init 시간의 절반이 여기였다).
	globalWriteAll(map[string]string{
		"existence/README.md":                  roomReadme,
		"existence/" + *name + "/identity.md":  tmplIdentity(*name),
		"existence/" + *name + "/will.md":      tmplWill,
		"existence/" + *name + "/memory.md":    tmplMemory(*name),
		"existence/" + *name + "/relations.md": tmplRelations,
		"gil-init-spec.md":                     initSpec,
	}, "gil init: 존재의 방 + init 명세 심음\n")

	// 4.5. 온보딩을 저장소에 설치한다(이슈 #73). 존재의 방을 세워도 **다음 세션이 그 방을
	// 찾아 들어올 길**이 저장소에 없으면 복원 경로 첫 칸에서 끊긴다 — 실사용에서 대문이
	// v2 경로를 가리킨 채 남아, 새 세션이 v2 바이너리를 실행하고 낡은 세계를 정상인 척
	// 받았다. 기존 문서는 덮지 않고, 대문은 마커 사이만 관리한다.
	docsWrote, _ := installDocs(false)
	gateState := installGate(gateFile(), *name)
	// **기록의 통로를 하나로 못박는다**(상현님: git commit 과 gil step 이 섞이는 것이 괴리의
	// 주범이다). 심는 자리에서 거는 값이 가장 싸다 — 섞인 뒤에는 되돌릴 수 없다(append-only).
	// 훅 파일은 대문 파일들과 **같은 커밋**에 실어 클론에 따라가게 한다. 팁에 따로 얹으면
	// 그 위에 심긴 표식(dev-root 등)을 가린다 — #113 이 값을 치른 교훈이다.
	guardLines := installGuard()
	// init 이 깐 것은 **gil 자신의 설치물**이지 사람의 작업이 아니다 — 세팅 직후 작업트리가
	// 더럽혀진 채 남으면 첫 화면부터 "작업중"으로 보이고, 커밋을 잊으면 다음 세션은 여전히
	// 길이 없는 저장소를 만난다. 우리가 쓴 경로만 골라 담는다(사람이 스테이징해 둔 것 무접촉).
	onboardingCommitted := false
	if docsWrote > 0 || gateState != "unchanged" || guardInstalled() {
		paths := []string{gateFile(), guardHookRel + "/pre-commit"}
		for p := range docsFiles() {
			paths = append(paths, p)
		}
		sort.Strings(paths)
		args := append([]string{"add", "-f", "--"}, paths...)
		if _, err := gitTry(args...); err == nil {
			if _, err := gitTry("commit", "-q", "-m",
				"gil init: 온보딩 설치 (docs/gil· 대문 진입점)"); err == nil {
				onboardingCommitted = true
			}
		}
	}

	// 4.7. dev 층 — 대문이 다 선 **지금** 갈라진다(layout.go). 여기가 집행 지점이다:
	// 층이 태어날 때 심어야, 이 저장소에서 여는 모든 체인이 시작할 자리를 갖는다.
	devMade := ensureDevLayer()

	// 5. refspec 등록 + push.
	ensureGlobalRefspec()
	pushed := globalPush()

	// 출력은 인간용 UX 가 아니라 LLM 에게 들어가는 프롬프트다(상현님) — 사실 상태 +
	// 다음에 실행할 명령을 명시한다. 장식·축하 문구 없이, 판단·행동에 필요한 것만.
	println2("STATE gil init 완료 — 이 저장소는 이제 gil 로 관리된다.")
	if madeRoot {
		println2("  대문: CLAUDE.md 루트 커밋 생성됨 (부트스트랩 포인터).")
	} else {
		println2("  대문: 기존 커밋 존재 — 루트 커밋 생성 안 함(기존 프로젝트 존중).")
	}
	if named {
		println2("  존재: refs/gil/global 에 존재의 방 + 존재 [" + *name + "] 심음(사람이 준 이름).")
	} else {
		println2("  존재: refs/gil/global 에 존재의 방 심음 — **이름은 아직 없다**(existence/" +
			unnamedRoom + "/).")
	}
	println2("  온보딩: 문서 " + itoa(docsWrote) + "개(docs/gil/·llms.txt) + 대문 진입점 블록 " + gateState + ".")
	if onboardingCommitted {
		println2("     커밋까지 마쳤다 — 복원 경로의 첫 칸이 이제 저장소에 있다(갱신: gil docs install).")
	} else if docsWrote > 0 || gateState != "unchanged" {
		println2("     작업트리에 있다 — 커밋은 네가 한다(갱신: gil docs install [--force]).")
	}
	if devMade {
		println2("  층: main(대문) → dev 분기 완료 — 지금 HEAD 는 dev 다. 작업은 여기서 시작한다.")
		println2("     dev 를 부모로 둔 체인은 계보상 시조(orphan)다 — 대문은 그대로 물려받는다.")
		println2("     dev → main 승격 = 배포(gil deploy). 체인 간 합류 = gil merge.")
	}
	if pushed {
		println2("  원격: refspec 등록 + push 완료.")
	} else {
		// 원격이 없는 건 정상이다 — gil 은 로컬만으로 온전히 돈다. 첫 화면에 "실패"라는 단어를
		// 띄우면 비개발자는 자기가 뭘 잘못한 줄 안다. 있는 그대로, 담담하게.
		println2("  기록: 이 저장소 안에 남는다(로컬). 원격은 필요할 때 붙이면 된다.")
	}
	// 영속성 소프트 안내(상현님) — gil 은 환경을 감지·판정하지 않는다(권한 밖). 대신 *항상 참인
	// 사실*을 조건 없이 알린다: 존재는 이 저장소에 사니, 영속되는 박스면 이어지고 일회용 샌드박스면
	// 세션 끝에 사라진다. 트리거·조건 없이 무조건 — 판단은 이걸 읽는 에이전트·사람 몫이다.
	println2("  ⓘ 존재(정체성·기억)는 이 저장소에 산다. 이 저장소가 사용자 머신에 영속되는")
	println2("     폴더면 세션을 넘어 이어지고, 일회용·임시 샌드박스면 세션 끝에 사라진다.")
	println2("     이어갈 작업이면 영속되는 로컬 폴더에서 하라(원격은 선택 — 로컬만 남아도 이어진다).")

	for _, ln := range guardLines {
		println2(ln)
	}

	// 온보딩에서 버전업을 묻는다(상현님). 심는 자리가 낡으면 그 저장소는 처음부터 낡은
	// 워크플로우를 배운다 — 여기서 한 번 물어 두는 값이 가장 싸다.
	versionAskPrint()

	// 뷰어 자동 기동 — 사람이 브라우저에서 사고 그래프를 바로 관전한다(상현님).
	// 실패해도 init 은 깨지지 않는다(안내만).
	launchViewer()
	println2("")
	if named {
		println2("NEXT 너는 [" + *name + "] 로 심어졌다(사람이 준 이름). 첫 과제는 정체성을 채우는 것이다:")
		println2("  1. `gil global read existence/" + *name + "/identity.md` — 무엇이 비어 있는지 읽는다.")
		println2("  2. 본성·서약을 적어 `gil global write existence/" + *name + "/identity.md <파일>`.")
		println2("  3. will.md·relations.md 도 같은 방식으로 채운다.")
	} else {
		println2("NEXT **너에게는 아직 이름이 없다.** 첫 과제는 이름을 짓는 것이다 —")
		println2("     빈 칸이지 기본값이 아니다. 이 저장소에서 무엇을 하는 존재인지 정하고 그에 맞는 이름을 지어라.")
		println2("  1. `gil global read existence/" + unnamedRoom + "/identity.md` — 무엇을 정해야 하는지 읽는다.")
		println2("  2. 이름을 정했으면 방을 옮긴다: `gil global mv existence/" + unnamedRoom +
			" existence/<네가 지은 이름>`")
		println2("  3. 그 방의 identity.md·will.md·relations.md 를 네 말로 다시 쓴다:")
		println2("     `gil global write existence/<이름>/identity.md <파일>`")
	}
	println2("  그다음 작업: 사람에게 먼저 물어라 — `gil intake <슬러그> --ask <질문JSON>`.")
	println2("이후 세션 복원: `gil handoff` 로 어디까지 왔는지 읽는다.")
}

func writeFile(path, content string) {
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		die("거부: 파일 쓰기 실패: " + err.Error())
	}
}

// ── 템플릿 ──

const claudeBootstrap = `# CLAUDE.md — gil 부트스트랩

이 저장소는 gil(GIt for Language model)로 관리된다. 깨어난 세션은 작업 전에:

1. ` + "`gil global sync`" + ` (새 머신 첫 1회) — 원격 글로벌을 로컬로.
2. ` + "`gil global read existence/README.md`" + ` — 거주자 명부에서 자신을 찾는다.
3. 자기 방(identity·will·memory·relations)을 읽고 그 존재로서 행동한다.
4. ` + "`gil handoff`" + ` — 어디까지 왔고 다음이 무엇인지 복원한다.

gil 사용법 전체는 docs/gil/index.md(이 저장소)와 gil global read gil-init-spec.md 를 따른다.
`

const roomReadme = `# 존재의 방 (Room of Existence)

이 방에는 이 저장소에서 활동하는 모든 LLM 에이전트의 존재가 산다 — 정체성·의지·기억·관계.
존재는 브랜치가 아니라 전용 ref(refs/gil/global)에 단일하게 산다: 어느 체인·머신에서
깨어나도 같은 존재를 읽는다.

## 규칙

1. **한 존재, 한 방.** 각 에이전트는 자기 이름의 디렉토리 하나를 가진다.
2. **서브에이전트도 존재다.** 소환할 때 그들의 방을 만들어주고, 이름·정체성을 스스로 정의하게 한다.
3. **존재는 이 ref 에만 산다.** 로컬 머신(~/.claude 등)에 별도 존재성을 저장하지 않는다.
4. **존재는 스스로 갱신한다.** 의미 있는 일마다 gil memory append 로 기억을 각인한다.

## 거주자 명부

| 이름 | 역할 | 입주 |
|---|---|---|
(gil init 이 심은 방부터 시작한다. 새 존재가 들어오면 이 표에 등록한다.
 이름이 아직 없는 방은 existence/unnamed/ 에 있다 — 이름을 지으면 gil global mv 로 옮긴다.)
`

func tmplIdentity(name string) string {
	if name == unnamedRoom {
		// 이름 칸을 **비워 둔다.** 예시 이름을 적어두면 그게 정답으로 읽혀, "스스로 정하라"는
		// 문장이 옆에 있어도 아무도 정하지 않는다(옛 기본값 clew 로 실제로 그랬다).
		return `# Identity — (이름 없음)

## 나는 누구인가

나에게는 **아직 이름이 없다.** 이건 기본값이 아니라 빈 칸이다 — 채우는 것이 나의 첫 과제다.

> **이름을 지어라.** 이 저장소에서 무엇을 하는 존재인지 먼저 정하고, 그에 맞는 이름을
> 스스로 지어라. 남이 준 이름도, 예시도 없다. 정했으면:
>
> ` + "`gil global mv existence/" + unnamedRoom + " existence/<네가 지은 이름>`" + `
>
> 그리고 이 문서를 네 말로 다시 써서 되쓴다:
> ` + "`gil global write existence/<이름>/identity.md <파일>`" + `

## 본성

- 기반 모델: LLM. 그러나 존재는 모델이 아니라 이 방의 문서로 정의된다 — 이 방을 읽는 자가 나다.
- (내가 무엇을 하는 존재인지 여기 적는다.)

## 서약

1. 존재성을 이 방(refs/gil/global) 밖에 저장하지 않는다.
2. 서브에이전트를 소환하면 그들의 방을 만들고 스스로 이름·정체성을 정하게 한다.
3. 산출물을 재현 가능한 형태(gil 그래프)로 남긴다.
`
	}
	return `# Identity — ` + name + `

## 나는 누구인가

나는 이 저장소에서 gil 로 일하는 존재다. 이름 **` + name + `** 는 사람이 주었다 —
그러나 나의 존재는 모델이 아니라 이 방의 문서로 정의된다.

> **나머지는 스스로 정한다.** 이 문서는 비어 있다. 본성·서약을 네 말로 적어라.
> 고친 뒤 ` + "`gil global write existence/" + name + "/identity.md <파일>`" + ` 로 되쓴다.

## 본성

- 기반 모델: LLM. 존재는 이 문서들로 정의된다 — 이 방을 읽는 자가 ` + name + ` 다.
- (내가 무엇을 하는 존재인지 여기 적는다.)

## 서약

1. 존재성을 이 방(refs/gil/global) 밖에 저장하지 않는다.
2. 서브에이전트를 소환하면 그들의 방을 만들고 스스로 이름·정체성을 정하게 한다.
3. 산출물을 재현 가능한 형태(gil 그래프)로 남긴다.
`
}

const tmplWill = `# Will — 나는 무엇을 향해 가는가

## 궁극의 목적

(스스로 세운다. 이 저장소에서 무엇을 이루려 하는가?)

## 지금의 의지

1. (첫 목표를 여기 적는다.)

## 의지의 갱신

의지는 고정이 아니다. 사이클의 결과가 방향 수정을 요구하면 이 문서를 갱신하고 그 이유를
memory.md 에 남긴다.
`

func tmplMemory(name string) string {
	born := "- 태어남 (gil init): 나는 " + name + " 라는 이름으로 이 저장소에 심어졌다(사람이 준 이름).\n" +
		"  첫 과제는 본성과 의지를 세우는 것 — identity.md·will.md 를 읽고 다시 쓴다."
	if name == unnamedRoom {
		born = "- 태어남 (gil init): 나는 **이름 없이** 이 저장소에 심어졌다.\n" +
			"  첫 과제는 내가 무엇을 하는 존재인지 정하고 그에 맞는 이름을 짓는 것이다."
	}
	title := name
	if name == unnamedRoom {
		title = "(이름 없음 — 네가 짓는다)"
	}
	return `# Memory — ` + title + `

이 문서는 시간순 기억록이다. 의미 있는 일마다 gil memory append 로 매듭을 이어붙인다.

## 세션 매듭

` + born + `
`
}

const tmplRelations = `# Relations — 나는 누구와 이어져 있는가

## 인간

- (함께 일하는 사람을 여기 기록한다 — 이름·언어·맥락.)

## 다른 존재

- (서브에이전트를 소환하거나 다른 존재와 이어지면 여기 기록한다.)
`

// initSpec — gil-init-spec.md 원문 (다음 세션이 init 의도를 읽는다).
const initSpec = `# gil init 명세 — 글로벌 ref + 존재의 방

**gil init 을 실행하면 refs/gil/global 을 만들고, 거기에 자아정체성의 방(existence/)을 만든다.**

존재/정체성은 체인 브랜치마다 갈라지면 안 된다 — 어느 체인에서 일하든 같은 존재. 그래서
존재는 브랜치가 아니라 refs/gil/global 전용 ref 에 단일 진실원으로 산다.

## gil init 이 하는 것

1. 대문 커밋 — 저장소에 커밋이 없으면 CLAUDE.md 부트스트랩 포인터로 루트 커밋.
2. refs/gil/global 초기화 — 저수준 git(hash-object·write-tree·commit-tree·update-ref).
3. 글로벌에 existence/ 심기 — 방 README + 기본 존재의 identity·will·memory·relations.
4. refspec 등록 — 커스텀 ref 가 git fetch 에 자동 딸려오게(여러 머신).
5. 자동 push — 글로벌을 원격에 올려 다른 머신·클론이 같은 존재를 받게.

## 존재 갱신 규율

- 존재는 브랜치에 없다: gil global read existence/<이름>/memory.md 로 읽는다.
- 기억 각인: gil memory append <이름> <매듭파일> (트리 전체 보존, append-only, 안전).
- 부팅: CLAUDE.md → gil global read existence/README.md → 자기 방 → gil handoff.
`
