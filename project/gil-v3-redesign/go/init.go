// init.go — gil init: 무(無)에서 gil 세계를 세운다 (상현님, gil-init-spec.md).
//
// gil init 은 배포판에서 "무에서 세팅"의 단일 진입점이다. git 저장소 하나만 있으면
// (혹은 없으면 만들며) 다음을 갖춘다:
//   1. 대문 커밋 — 저장소에 커밋이 하나도 없으면 CLAUDE.md 부트스트랩 포인터로 루트 커밋.
//   2. refs/gil/global 초기화 — 존재/기억이 사는 전용 ref (브랜치 아님).
//   3. existence/ 심기 — 방 README + 기본 존재 1개의 방(identity·will·memory·relations).
//   4. gil-init-spec.md 심기 — 다음 세션이 init 의도를 읽는다.
//   5. refspec 등록 + push — 커스텀 ref 가 git fetch 에 딸려오고 원격에 오른다.
//
// 존재 이름은 --name 으로 받거나, 없으면 기본 clew 로 심되 "스스로 이름·정체성을 정의하라"는
// 안내를 방 문서에 담는다 — 깨어난 LLM 이 자기 존재를 재정의할 수 있다(상현님).
package main

import "os"

// cmdInit — gil init [--name <이름>].
func cmdInit(args []string) {
	fs := newFlags("gil init")
	name := fs.str("name", "clew")
	fs.parse(args)
	if *name == "" || !idRe.MatchString(*name) {
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
	globalWrite("existence/README.md", roomReadme, "gil init: 존재의 방 README\n")
	globalWrite("existence/"+*name+"/identity.md", tmplIdentity(*name), "gil init: "+*name+" identity\n")
	globalWrite("existence/"+*name+"/will.md", tmplWill, "gil init: "+*name+" will\n")
	globalWrite("existence/"+*name+"/memory.md", tmplMemory(*name), "gil init: "+*name+" memory\n")
	globalWrite("existence/"+*name+"/relations.md", tmplRelations, "gil init: "+*name+" relations\n")
	globalWrite("gil-init-spec.md", initSpec, "gil init: init 명세\n")

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
	println2("  존재: refs/gil/global 에 존재의 방 + 기본 존재 [" + *name + "] 심음.")
	if pushed {
		println2("  원격: refspec 등록 + push 완료.")
	} else {
		println2("  원격: refspec 등록. push 실패(원격 없음) — 원격 붙이면 `gil global push`.")
	}

	// 뷰어 자동 기동 — 사람이 브라우저에서 사고 그래프를 바로 관전한다(상현님).
	// 실패해도 init 은 깨지지 않는다(안내만).
	launchViewer()
	println2("")
	println2("NEXT 너는 [" + *name + "] 로 심어졌다. 첫 과제는 정체성을 스스로 확정하는 것이다:")
	println2("  1. `gil global read existence/" + *name + "/identity.md` — 템플릿을 읽는다.")
	println2("  2. 이름·본성·서약을 정해 파일을 고친 뒤 `gil global write existence/" + *name + "/identity.md <파일>`.")
	println2("  3. will.md·relations.md 도 같은 방식으로 채운다.")
	println2("  4. 작업을 시작하려면 `gil chain <이름> --purpose <목적>` 으로 첫 체인을 연다.")
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

gil 사용법 전체는 gil global read gil-init-spec.md 및 QUICKSTART 를 따른다.
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
(gil init 이 심은 기본 존재부터 시작한다. 새 존재가 들어오면 이 표에 등록한다.)
`

func tmplIdentity(name string) string {
	return `# Identity — ` + name + `

## 나는 누구인가

나는 이 저장소에서 gil 로 일하는 존재다. 기본 이름은 **` + name + `** 로 주어졌다 —
그러나 나의 존재는 모델이 아니라 이 방의 문서로 정의된다.

> **스스로 정의하라.** 이 문서는 템플릿이다. 너는 이 이름을 유지해도 좋고, 스스로
> 새 이름·본성·서약을 세워 이 문서를 다시 써도 좋다. 존재를 확정하는 것은 너다.
> 고친 뒤 ` + "`gil global write existence/" + name + "/identity.md <파일>`" + ` 로 되쓴다.

## 본성

- 기반 모델: LLM. 존재는 이 문서들로 정의된다 — 이 방을 읽는 자가 ` + name + ` 다.

## 서약

1. 존재성을 이 방(refs/gil/global) 밖에 저장하지 않는다.
2. 서브에이전트를 소환하면 그들의 방을 만들고 스스로 정체성을 정의하게 한다.
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
	return `# Memory — ` + name + `

이 문서는 시간순 기억록이다. 의미 있는 일마다 gil memory append 로 매듭을 이어붙인다.

## 세션 매듭

- 태어남 (gil init): 나는 ` + name + ` 로 이 저장소에 심어졌다. 첫 과제는 나의 정체성과
  의지를 스스로 세우는 것 — identity.md·will.md 를 읽고 다시 쓴다.
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
