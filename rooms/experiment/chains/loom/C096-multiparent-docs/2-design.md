# 2. 실험 설계

가설(1-hypothesis.md): 다중부모 how-to를 4곳에 정합하면(예제·명문화·에러메시지·플래그help), 도구 행동 변경 없이 독자가 같은 체인 다중부모를 올바르게 기록한다.

## 절차

### 편집 대상 4곳 (정확한 위치 확정)

1. **README.ai.md:102** (LLM 빠른 참조 — 최고 영향). 현재:
   > `--parent C001-<slug>` … (add `--lineage <otherchain>/<id>` for a cross-chain lesson)

   두 번째 조상을 lineage로만 제시하는 오도. **같은 체인 병합은 `--parent` 반복**임을 명시하고, cross-chain은 lineage로 분리:
   > `--parent C001-<slug>` … For a **merge** (a cycle descending from two prior cycles *in the same chain*), repeat the flag: `--parent A --parent B` → `parent: [A, B]`. Use `--lineage <otherchain>/<id>` only for a lesson from a **different** chain.

2. **QUICKSTART.md:86**. 현재 단일 `--parent` 예제 뒤에 lineage만 안내. 병합 예제 한 줄 추가:
   > 같은 체인의 두 사이클에서 합류하면(병합) `--parent A --parent B`처럼 여러 번 → `parent: [A, B]`. **다른** 문제 영역의 교훈이면 `--lineage <다른체인>/<사이클id>`.

3. **SPEC.md §3.2 O-table**. O2 행 아래(또는 표 뒤 주석)에 병합 케이스 명문화. O 표는 거부 규칙 중심이라, 병합은 정상 케이스이므로 **표 아래 한 줄 설명**으로:
   > `--parent`는 반복 가능하다. 같은 체인의 여러 부모(병합)는 `--parent A --parent B` → `parent: [A, B]`. `lineage`는 **다른 체인** 전용이다(R3) — 같은 체인의 두 번째 부모를 lineage에 넣으면 거부된다.

   (스키마 §(line 79)엔 이미 `병합=[a, b]`가 있으나 O-table과 분리돼 있음 → 규범 절에 연결.)

4. **gil.py:694** (사용자 접점 에러 메시지 — 유일한 코드 변경). 현재:
   > `--parent {tip}   (분기면 여러 번)`

   → `--parent {tip}   (분기·병합이면 여러 번)`. 플래그 help(4232)는 이미 "병합이면 여러 번"이라 두 접점이 일치하게 됨.

5. **gil.py:4233** (--lineage 플래그 help). 현재 "교훈의 연원, 전역 표기 <chain>/<id>"에 **cross-chain 전용** 명시 추가:
   > `교훈의 연원 — 다른 체인의 <chain>/<id> (여러 번; 같은 체인은 --parent)`

### 워크드 예제 (README.ai.md 또는 QUICKSTART에 최소 1개)

`parent: [C020, C016]`을 실제로 만드는 명령을 하나 박는다(감사가 "예제 부재"를 갭으로 지목). 실존하는 C036이 그 예이므로 인용:
```
./gil open loom go-open-git-ledger --parent C020-go-web-port --parent C016-number-ledger --author weft
# → parent: [C020-go-web-port, C016-number-ledger]  (병합: 두 갈래가 합류)
```

## 준비물

- gil 2.44.0 (이 환경 PATH 없음 → `python3 rooms/deployment/ariadne-spec/gil.py`)
- conformance: `python3 rooms/deployment/ariadne-spec/conformance.py --gil "python3 …/gil.py"` (참조 123), Go는 gil-gate CI(105)
- CI 로컬 재현: `/tmp/gilbin/gil` 래퍼(C092 교훈) — gil.py:694 메시지 변경이 판정에 안 걸리는지 확인용

## 측정 방법

- **성공**: 4곳 편집 후 (1) conformance 참조 123/123 무회귀 (2) 에러 메시지 실제 출력이 "분기·병합이면 여러 번"으로 바뀜(빈 체인에 부모 없이 open 시도로 트리거) (3) 문서에 `--parent A --parent B` → `parent: [A, B]` 워크드 예제가 최소 1개 존재 (4) `gil help open` 출력의 --lineage help가 "같은 체인은 --parent"를 포함.
- **기각**: 기각 조건 1~4 중 하나라도 발생(특히 conformance 회귀).

## 사용자 컨펌

- 상현님이 "문서 개선 먼저(권장)"를 선택. 편집 범위(4곳 + 워크드 예제)는 감사 결과에 근거. 세부 문안은 close 전 보고에서 리뷰 가능.
- [x] 컨펌 받음 (일자: 2026-07-20) — "문서 개선 먼저" 선택으로 갈음
