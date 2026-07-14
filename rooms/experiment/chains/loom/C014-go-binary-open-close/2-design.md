# 2. 실험 설계

오직 하나의 가설 — "Go 바이너리에 open·close를 더하면 무수정 conformance가 목표
17항목을 PASS로 판정한다" — 만을 검증한다.

## 절차

1. **계승**: 닫힌 사이클 C012의 `3-verification/gil-go/main.go`를 이 사이클의
   `3-verification/gil-go/main.go`로 복사한다 (닫힌 사이클은 손대지 않는다).
2. **이식**: 참조 구현(배포본 v0.5.0 `gil.py`)의 `cmd_open`·`cmd_close`를 Go로
   이식한다. 이식 기준은 스펙 §4(명령)·§5(쓰기 규율)와 참조 구현의 동작이다.
   - open: 슬러그 R1 검사 → 템플릿 존재 → `--new-chain` 규칙 → 사전 fsck →
     parent(R3·R6)/lineage(R3·R2) 사전 검사 → 번호 자동 증가 → 템플릿 복사 →
     cycle.yaml 재작성 → 사후 fsck (위반 시 생성물 제거 후 실패).
   - close: 사이클 존재 → 이중 닫기 거부 → 5-report.md 존재·템플릿 동일성 거부 →
     status/closed 행 치환 → 사후 fsck (위반 시 원본 복구 후 실패).
   - `--git` 플래그와 verify·web·release 명령은 범위 밖 — "미구현" 메시지 + exit 3.
     단, `close --git`은 **어떤 변경도 하기 전에** 거부해야 한다(무변화 보장).
   - 외부 의존성 0 유지: Go 표준 라이브러리만.
3. **빌드**: `go build -o gil main.go`, `file gil`로 단일 바이너리(Mach-O) 확인.
4. **판정 (run1)**: 레포 루트에서 배포된 무수정 스위트를 실행한다.
   `python3 rooms/deployment/ariadne-spec/conformance.py --gil "<빌드된 gil 절대경로>"`
   전체 22항목의 PASS/FAIL을 그대로 기록한다.
5. **회귀 (run2)**: 같은 스위트를 파이썬 참조 구현(`--gil "python3 …/gil.py"`)으로
   실행해 22/22를 확인한다 — 스위트·참조 구현이 이 시점에도 건강함을 고정한다.
6. **실데이터 교차 검증 (run3)**: 임시 복사본 레포(스크래치패드)에서 Go open →
   파이썬 fsck 판정, Go close → cycle.yaml 전이 diff, 파이썬 open과의 생성물 비교
   (cycle.yaml 필드 동일성)를 수행한다. 진짜 레포는 건드리지 않는다.
7. 모든 실행 로그를 `3-verification/runs/`에 저장한다.

## 준비물

- Go 1.26.2 (darwin/arm64), Python 3.9.6, macOS Darwin 25.2.0.
- 판정기: `rooms/deployment/ariadne-spec/conformance.py` (v0.5.0 배포본, **무수정**).
- 참조 구현: `rooms/deployment/ariadne-spec/gil.py` (v0.5.0).
- 계승 원본: `rooms/experiment/chains/loom/C012-go-binary-log-fsck/3-verification/gil-go/main.go`.

## 측정 방법

- **1차 판정**: run1에서 목표 17항목(FSCK-CLEAN·R1~R8, LOG-OK·LOG-BROKEN,
  OPEN-CREATE·INCREMENT·REJECT-SLUG, CLOSE-TEMPLATE-REJECT·OK·DOUBLE-REJECT)
  전부 PASS → 채택. 하나라도 FAIL → 기각.
- **2차 판정**: run3에서 Go와 파이썬의 open 생성물(cycle.yaml 내용)·close 전이
  (status/closed 행)가 동일 → 채택 유지. 다르면 기각.
- 범위 밖 항목의 FAIL 개수와 공허 통과는 수치로 기록만 한다.

## 사용자 컨펌

- 생략 — 소환자 Clew의 위임 프롬프트가 목표 항목·범위(깃 각인 제외 허용)·판정기
  (무수정 conformance)를 이미 특정했다. 설계는 그 위임의 구체화다.
