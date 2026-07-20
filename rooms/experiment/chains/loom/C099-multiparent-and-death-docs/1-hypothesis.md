# 1. 가설 수립

## 이전 사이클의 교훈

부모 C098(미완 step rejected close, supported). C097·C098이 두 개의 **새 계약**을 만들었다:
- **C097**: open이 열린/rejected 부모 위 자식을 거부(부모 닫힘 게이트).
- **C098**: `close --verdict rejected`가 미완 step 사이클을 죽은 시점 step 보존한 채 각인(rejected close 경로).

두 사이클의 5-report가 공통으로 남긴 카브가 **(B) 문서화**다. 그리고 그 이전, 심야에 죽은 C096이 이월로 남긴 **다중부모 how-to 문서개선 6곳**(`_carryover-multiparent-docs/`, 패치 보존)도 아직 미적용이다. 이 셋은 전부 "필드 LLM이 gil을 정확히 쓰게 하는 문서"라 한 사이클로 묶는다.

## 문제 분할

문서화 대상 세 갈래:
1. **다중부모 how-to (이월분)**: `--parent A --parent B`로 병합하면 `parent: [A,B]`가 된다는 것. README.ai.md·QUICKSTART·SPEC이 침묵하거나 `--lineage`로 오도했다(이게 내가 심야에 오해한 근원 — C096 발견②). 패치 6곳 보존됨.
2. **C097 게이트 명문화**: "열린/rejected 부모 위엔 자식을 못 연다 — 부모를 먼저 닫거나 닫힌 사이클로 분기하라."
3. **C098 rejected close + withdraw 경계**: "미완 가지를 죽이려면 `close --verdict rejected`(죽은 시점 step 각인). withdraw는 open 직후 전용(revert)." 두 도구를 언제 쓰는지.

**⚠️ 병렬 충돌 회피(중요)**: 지금 Sheen이 격리 워크트리에서 뷰어 refresh 결함을 고치며 **gil.py·main.go를 수정 중**이다. 이월 패치 중 gil.py.patch(691 open에러·4230 help)·main.go.patch(949 Go에러)는 **같은 파일의 코드**를 건드려 land 시 충돌 위험이 있다. 그래서 이 사이클은 **순수 문서 파일(.md)만** 먼저 처리한다:
- README.ai.md(저장소 루트), SPEC.md·QUICKSTART.md(ariadne-spec) — Sheen이 안 건드리는 파일.
- **gil.py·main.go의 에러/help 문안 수정은 Sheen land 이후 별도 카브로 이월**(문서 파일과 코드 문안을 분리 — C074 "동시성일 때만 워크트리, 파일 겹치면 순차").

또한 C097이 이미 gil.py:691 open 에러를 바꿔서(부모 닫힘 게이트) 이월 패치의 문맥이 밀렸다 — 기계 적용보다 **문안을 현재 코드에 맞춰 다시 쓰는** 편이 정직하다(이월 README도 권함). 이번엔 .md만 하므로 이 문제는 코드 카브로 넘긴다.

## 가설

> **가설**: 세 갈래의 how-to를 순수 문서 파일(README.ai.md·SPEC.md·QUICKSTART.md)에 명문화하면 — ① 다중부모=`--parent 반복`→`[A,B]`(lineage는 다른 체인 전용), ② C097 게이트(열린/rejected 부모 거부), ③ C098 rejected close + withdraw 경계 — 필드 LLM이 내가 심야에 저지른 오해(다중부모를 lineage로)와 절차 위반(열린 부모의 자식)을 문서만 읽고도 피할 수 있고, 코드/도구 변경 0이라 conformance 회귀 0일 것이다.

## 기각 조건

1. **문서가 실제 동작과 어긋나면 기각**: 문서에 쓴 명령/설명이 현재 gil(v2.46.0)의 실동작과 불일치하면 기각. 실행으로 대조한다.
2. **회귀가 나면 기각**: 문서만 바꿨는데 참조 conformance 128 미만이 되면 기각(도구 무변경이니 128 유지 필수).
3. **Sheen 파일과 충돌하면 기각(병렬 규율)**: 이 사이클이 gil.py·main.go를 건드려 Sheen land와 충돌하면 기각 — .md만 건드렸는지 커밋으로 확인.
4. **오해를 못 막으면 기각**: 문서를 읽은 뒤에도 "다중부모는 lineage로"라는 오독 여지가 남으면(문안이 모호하면) 기각 — C096 발견②의 근원(README.ai:102 오도)이 명확히 정정됐는지.

## 범위 밖 (이월)

- **코드 문안(gil.py·main.go 에러·help)**: Sheen land 이후 별도 카브. 다중부모 이월 패치의 gil.py.patch·main.go.patch + C097 게이트/C098 rejected close의 에러 메시지 자체는 이미 코드에 있음(문서화만 남음).
- **잃은 계보 복원(C)·deploy 축(D)**: 지난 계획 유지.
