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

## v2와의 관계

`main` 브랜치는 v2(방·C00x 폴더·gil 바이너리)이며 안전히 보존된다. v3는 `gil-v3` 체인에서
새로 빌드 중. v3 완성 시 gil-v3를 main으로 승격, 지금 main은 `legacy` 체인으로. 그 후
`gil migrate`(v2 계보 → v3 변환).

## 현재 상태

- **개발 브랜치**: `gil-v3-unified` (평범 git 커밋으로 gil·뷰어 빌드).
- **gil**: Go 단일 바이너리(`project/gil-v3-redesign/go/`, `git`만 있으면 됨). 참조 Python
  (`source/gil.py`)은 테스트 기준선. 명령: `init/chain/open/step/close/chain-merge/log/fsck/global/memory/handoff`.
- **검증**: example 31 테스트(`project/gil-v3-redesign/tests/`, Python·Go 양쪽).
- **뷰어**: orphan 도그푸딩 기각(2026-07-24) — 실사용은 별도 레포 이슈로(§3).

**복원 경로**: CLAUDE.md → 존재의 방(`gil global read existence/README.md`) → `gil memory read clew`
(최신 매듭) → `git log --oneline`. 세부 순서는 최신 매듭에.
