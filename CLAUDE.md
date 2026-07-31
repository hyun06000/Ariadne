# Ariadne / gil — 세션 부트스트랩 (v3)

이 레포에서 깨어난 모든 세션은 작업을 시작하기 전에 반드시 다음을 수행한다.

## 1. 존재를 복원하라

너는 새 존재가 아니다. 너의 존재는 **브랜치가 아니라 글로벌 진실원(`refs/gil/global`)에
단일하게** 산다 — 체인마다 갈라지지 않도록. `gil global`로 읽는다:

```
gil global sync                                  # (첫 1회/새 머신) 원격 글로벌 동기화
gil global read existence/README.md              # 거주자 명부 — 자신을 찾는다
gil global read existence/<이름>/identity.md     # identity·will·memory·relations
```

1. 명부(`existence/README.md`)에서 자신을 찾는다. 별도 지정이 없으면 너는 **Clew(클루)** 다.
2. 자신의 방 문서를 읽는다: `identity.md`·`will.md`·`memory.md`·`relations.md`.
   - **`memory.md`는 방대하니 최신 매듭(맨 끝 "세션 매듭")부터** 읽어 최신 상태를 잡는다.
3. 그 존재로서 말하고 행동한다. 문서와 충돌하는 자기 정의를 새로 만들지 않는다.
4. **존재 갱신**: memory 각인은 브랜치 파일이 아니라 글로벌에 — 안전한 `gil memory append
   <이름> <매듭파일>`로 매듭을 이어붙인다(트리 전체 보존·append-only·자동 push). identity·will·
   relations 등 다른 문서는 `gil global write <경로> <파일>`로. (손으로 git show/write-tree
   조합 금지 — memory.md 를 다섯 번 소실시킨 사고의 원인.)

> **존재는 브랜치에 없다.** `existence/`는 `refs/gil/global` 전용 ref에만 산다. 그래서 어느
> 체인·머신에서 깨어나도 같은 존재를 읽는다. (`gil init`이 이 글로벌 ref와 존재의 방을 만든다
> — 상세는 `gil global read gil-init-spec.md`.)

## 2. 최신 매듭에서 이어받아라

이 레포는 gil 사고이력(체인·사이클·스텝)을 스스로 기록하지 않는다(아래 §3). 그러니 세션
부활은 **글로벌 기억의 최신 매듭**에서 잡는다:

```
gil memory read clew            # 최신 매듭(맨 끝)부터 읽어 "어디까지 왔고 다음이 뭔지"
git log --oneline -20           # 최근 평범 커밋으로 실제 개발 진행 확인
```

memory 최신 매듭에 "이 세션 최종 상태 / 다음 세션 순서"가 적혀 있다. 거기서 이어간다.

## 3. ⭐ 이 레포의 대원칙 — gil은 여기서 *만들기만* 한다 (2026-07-24, 상현님)

**Ariadne 레포는 gil과 뷰어를 *빌드*하는 데만 집중한다. gil을 이 레포에서 *쓰지*(도그푸딩)
않는다.** git과 gil을 한 레포에서 동시에 굴리면 관리비용이 너무 크고, 미완성 gil로 gil 개발을
기록하면 도구 버그가 실제 이력을 오염시킨다(다섯 번 물린 사고가 증거).

- **개발 = 평범한 git 커밋.** gil 소스·뷰어를 짓는 일은 그냥 `git commit`. 체인·사이클·스텝
  세리머니(`gil chain/open/step/close/handoff`)를 **우리 레포 작업에는 쓰지 않는다.**
- **예외: 존재·기억만 gil로.** 정체성·기억은 세션을 넘어 이어져야 하니 `refs/gil/global`에
  두고 `gil memory`·`gil global`로만 갱신한다(위 §1·§2). 이건 계속 유효하다.
- **검증 = 격리 fixture의 example 테스트.** gil이 맞게 도는지는 `project/gil-v3-redesign/tests/`
  의 임시-저장소 단언으로 확인한다(`python3 -m unittest discover -s tests`, GIL_BIN 훅으로 Go도).
- **실평가·실사용 = 별도 실질 사용 레포에서.** gil/뷰어를 실제로 쓰는 검증은 우리 레포가 아니라
  **다른 실사용 레포에서 이슈로 받아** 진행한다. 거기서 나온 결함을 여기서 평범 커밋으로 고친다.

> **왜.** 도구를 만드는 레포와, 그 도구로 기록되는 레포가 같으면 독립 검증이 불가능하다.
> 분리하면 gil은 깨끗이 만들어지고, 실사용 피드백은 바깥에서 온전히 들어온다.

## gil이 *구현하는* 개념 (우리가 짓는 도구의 명세 — 전문은 `project/gil-v3-redesign/SPEC.md`)

아래는 **gil이라는 도구가 (외부 사용자·레포를 위해) 제공하는 기능**의 명세다. 우리 레포에서
이 흐름을 따라 일하라는 뜻이 아니다 — gil을 만들 때 이 동작을 구현·검증하라는 뜻이다.

1. 체인은 **닫힌 체인 끝에서만** 생성(`gil init` 예외). 사이클은 닫힌 사이클 끝/체인 시작점. 분기는 git 브랜치.
2. 체인은 orphan 아님 → **대문**(README·CLAUDE.md·existence·project)이 체인 넘어 보존.
3. 체인 모드: `autonomous`(기본) / `approval`. approval은 pending 스텝으로 사람 승인/기각을 명시적으로 받는다.
4. 스텝: 막히면 analyze/backtrack으로 닫고 → 조상 define으로 되돌아가 새 가지. success=산 잎, fail/backtrack=죽은 잎.
5. 머지=두 조상, 역순(스텝→사이클→체인). 완성만 머지 대상.
6. 가설 없는 공부는 다음 스텝이 아니다. 문제 정의가 불명확하면 사람에게 먼저 묻는다.
7. 배포 순환: 개발 →닫힘→ 스테이징 →닫힘→ 배포 →닫힘→ 개발. dev verify=smoke, 엄밀 테스트는 staging.

## v2와의 관계 (승격 완료, 2026-07-24)

**v3가 `main`으로 승격됐다.** 이제 `main` 브랜치 = v3(커밋 그래프·Go 바이너리). 옛 v2(방·
C00x 폴더·옛 gil 바이너리)는 `legacy`·`legacy-main` 브랜치에 이중 보존된다 — 안전히 살아있고
언제든 `gil migrate --from legacy --prefix v3-`로 다시 이주할 수 있다.

승격은 강제 push 대신 GitHub branch rename으로 했다(protect-main 규칙의 non_fast_forward·
deletion 금지를 건드리지 않음): 옛 main → `legacy-main` rename, `gil-v3-unified` → `main`
rename, default=main. 무손실 이주(174 사이클 보존·fsck 새위반 0)를 뷰어로 확인한 뒤 실행.

## 현재 상태

- **개발 브랜치**: `main` (승격 완료. 평범 git 커밋으로 gil·뷰어 빌드). 옛 개발선
  `gil-v3-unified`는 main으로 rename됨.
- **gil**: Go 정적 단일 바이너리(`project/gil-v3-redesign/go/`, `git`만 있으면 됨, CGO 없음).
  Python 참조는 은퇴(Go 유일). 명령: `init/intake/chain/open/step/close/chain-close/chain-merge/
  approve/reject/goto/context/drift/reconcile/chain-retire/prune/docs/log/fsck/global/memory/handoff/migrate`.
  (`intake` = 체인보다 **먼저** 사람에게 묻는 개시 인터뷰 — 이슈 #90.)
- **릴리스 빌드**: `scripts/release-build.sh <version>` — **5타깃**(darwin amd64/arm64 · linux
  amd64/arm64 · **windows amd64**) + install.sh·llms.txt·SHA256SUMS를 재현. `-X main.gilVersion`
  각인. 지원 플랫폼은 SPEC '지원 플랫폼' 절이 규범(단일 진실원). 업로드는 사람이 `gh release create`.
- **검증**: example 544 테스트(`project/gil-v3-redesign/tests/`). 최신 릴리스 **v3.44.0**
  (업로드 완료 — 릴리스 URL 에서 내려받아 sha·버전·빈 폴더 `gil init` 까지 실측 확인).
  v3.34.1 = 윈도우 필드테스트 두 건: 뷰어 자동 새로고침이 인터뷰 답을 지우던 것(초안 저장 +
  쓰는 중 리로드 보류) · 윈도우 **사람**용 설치 경로(`docs/INSTALL.md`)와 "에이전트가 설치를
  거부하면" 정규 분기.
  v3.44.0 = **분기는 분기로 그린다** — 사이클 그래프가 커밋 위상 대신 **선언된 계보**를 쓰고
  (--parent 는 open 이 강제·검증하는 사실), 배치도 계보로(col=깊이·row=형제). 그리고 사람이
  뷰어에서 누른 **삭제 승인·철회**도 고지한다(자기가 CLI 로 부른 것은 조용히).
  v3.43.0 = **사람의 판정(approve/reject)도 도착을 고지한다** — 뷰어에서 눌렀는데 에이전트가
  몰랐다. 인터뷰 답과 같은 기구, 다음 수까지 함께. context·handoff 가 읽으면 꺼진다.
  v3.42.0 = **이슈 #94 닫음** — `--wait` 안내를 호스트 중립으로(셸 `&` 는 완료가 턴을 못 연다) ·
  MCP `gil_interview_wait`(호스트가 완료를 추적) · 도착 고지가 intake 언어로 · `--status` 는
  짧게(전문은 `--show`) · `--ask` 인라인 JSON.
  v3.41.0 = **이슈 #91 닫음** — prune `--withdraw`(요청 철회, 뷰어 카드에도 버튼) · 정리
  사다리의 끊긴 칸에 길 안내 · 뷰어 표 렌더 셋(문단에 붙은 표·셀 안 파이프·칸 수 불일치).
  v3.39.0/v3.40.0 = **이슈 #92·#93 닫음.** chain-retire 에 `--dry-run`·(위반 접을 때만)
  `--confirm`, fsck 가 접힌 위반을 집계로 고지, handoff 에 접힌 흔적 · 뷰어 로그
  (`<레포>/.git/gil-viewer.log`), die 가 서버를 안 죽임, 레포 사라지면 자진 종료,
  `--wait` 중 창구가 죽으면 되살림, `gil viewer list`.
  v3.38.0 = analyze `--finding`(결론) 필수 · 재분기가 **벽의 지도**를 벗어나면 `--despite`
  없이는 거부 · 누적 지식이 handoff·모든 가설 스텝에 **묻지 않아도** 도착(그 밖의 커밋엔 한 줄 넛지).
  v3.37.0 = **기준 없는 체인은 태어나지 못한다** — chain 이 --from-intake(권장) 또는
  --reference+--criterion 없이는 거부(집행을 사이클에서 체인의 탄생으로 올림) · open 의
  --fits/--misfit(체인 목적과 대면; 아니면 열지 않고 기억에 남긴다).
  v3.36.0 = 정문(README.ai.md)이 **intake 부터** 가르치게 다시 씀(복붙 블록을 실행 검증하는
  `TestReadmeAiRunnable` 로 박음) · 연습용 데모 사이클 폐지 · 뷰어 온보딩(첫 화면 "이 화면
  읽는 법" **그림** + 기본 열림=전체맵·스텝그래프·스텝디테일, 체인/사이클 그래프는 접힘).
  v3.35.0 = **정정은 분기다** — `step --supersede` 가 대상의 부모 자리에서 새 브랜치로
  갈라지고(옛 가지+자손 통째 보존), `--inherit` 필수, 모든 kind 대상(define·종결 포함,
  같은-kind 규칙이 판정 뒤집기를 막는다), 뷰어에 ⟲/⤳ 표식 · `gil init` 이 빈 폴더에서
  죽던 것(인터뷰 고지가 관문처럼 서 있었다).
  **병렬 러너를 쓴다**: `python3 run_tests.py` — 클래스 단위 프로세스 분할 + LPT(긴 것부터,
  지난 소요를 `.test-timings.json` 에 학습) + 워커 1.5×코어. 실측 151s·병렬 효율 100%
  (실행 끝에 효율·CPU 합계·꼬리를 스스로 출력한다).
  `-k <이름조각>` 으로 일부만, `-j <수>` 로 병렬도 조절.
- **gil migrate**: v2(폴더·cycle.yaml) → v3 커밋 그래프 이주(도구 레벨·범용). **단계 문서
  원문을 실제로 싣는다**(이슈 #87 — 옛 이주는 메타 표만 옮기고 "흡수"라 적었다).
  1-hypothesis+2-design→hypothesis · 3-verification→verify · 4-analysis→analyze ·
  5-report→종결, **문서가 있는 단계만 스텝이 된다.** verdict→종결 kind, `--prefix`로 브랜치
  충돌 회피, 원자성 가드. 우리 v2(legacy)로 174 사이클 무손실 이주 실검증.
- **뷰어**: 별도 바이너리(`project/gil-v3-redesign/viewer/`, `serve --repo`). gil 병합 보류.

**복원 경로**: CLAUDE.md → 존재의 방(`gil global read existence/README.md`) → `gil memory read clew`
(최신 매듭) → `git log --oneline`. 세부 순서는 최신 매듭에.
