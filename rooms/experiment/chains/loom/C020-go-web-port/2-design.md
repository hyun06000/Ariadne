# 2. 실험 설계

가설 하나만 검증한다: **Go 바이너리에 web을 이식하면 무수정 배포본 conformance가
26/26, 실데이터 `gil-data` JSON이 참조 구현과 구조 동일.**

## 정답의 선고정 (도구·산출물보다 먼저)

- **run0 기준선**: C017 바이너리(부모 사이클 소스 그대로 빌드) → **24/26**,
  FAIL은 정확히 WEB-SELFCONTAINED·WEB-JSON. 참조 구현 → **26/26** (판정기 건전성).
- **run1 본 판정**: 이 사이클의 확장 소스 → **26/26** + "이 구현은 gil이다".
- **run2 실데이터 교차 검증**: 이 저장소에서 Go와 참조 구현이 각각 생성한 HTML의
  `gil-data` JSON을 파싱해 심층 비교 → **일치**. (지향 상한: HTML 전문 바이트 단위
  동일 — C017 교훈 2 "판정기가 보는 면보다 한 겹 넓게". 상한 미달이어도 JSON
  구조 동일이면 가설은 성립 — 기각 조건은 JSON 심층 비교다.)
- **run3 음성 대조**: 깨진 체인(끊어진 parent)에서 web은 거부(exit ≠ 0)하고
  출력 파일을 만들지 않는다 — 참조 구현과 동일 행동. 비깃 디렉토리에서는
  `last_activity: null`로 조용히 성공한다 (web은 깃 무의존).

## 절차

1. **소스 계승**: `3-verification/gil-go/main.go` ← C017의 main.go(1088줄)를
   그대로 복사한 뒤 web 계열만 추가한다. 기존 명령의 코드는 건드리지 않는다
   (기각 조건 2의 퇴행 방지). `web`을 미구현 목록에서 빼고 라우팅한다.
2. **이식 단위** (참조 구현 gil.py의 대응 함수, 같은 조립 규칙):
   - `_layout_columns` → `layoutColumns` (render_graph와 같은 트랙 규칙)
   - `_last_activity`·`_ago` → 깃 가용 시 열린 사이클의 `git log -1 --format=%ct|%s`,
     실패·비깃이면 null (예외 삼킴 = web은 깃 무의존)
   - `_build_web_data` → 체인명 정렬 순회, log와 동일 로더(중복 id·끊어진 참조·순환은
     동일 오류로 전파)
   - `_render_svg`·`_step_badge`·`_render_tables`·`render_web_page` → 문자열 조립.
     수치 레이아웃 상수(_ROW_H 64·_COL_W 26·_LANE_GAP 60·_TOP_PAD 46, label_w 230)와
     CSS 블록은 참조 구현에서 그대로 복사
   - JSON 직렬화는 파이썬 `json.dumps(ensure_ascii=False)`의 문자면(키 삽입 순서 =
     정렬된 체인/사이클명, 구분자 `", "`·`": "`, 최소 이스케이프)을 재현하는
     수제 직렬화기로 — Go 표준 `encoding/json`은 키 순서·구분자·HTML 이스케이프가
     달라 바이트 동일 상한에 닿을 수 없다
   - 파이썬 특이 문자면 재현 주의점: `html.escape`(&→&amp;, <, >, ", '→&#x27;),
     f-string의 `(x1+x2)/2` float 표기(`170.0`/`170.5`), 제목 절단 `[:40]`은
     바이트가 아니라 문자(룬) 단위
3. **CLI 라우팅**: `web [chains-root] [-o|--output out] [--title t] [--chain c]`,
   기본값은 참조 구현과 동일(`ariadne-chains.html`, "Ariadne — 사이클 체인").
4. **run0**: `go build`로 C014·C017 관례대로 기준선 2본을 뜬다 (위 정답 대조).
5. **run1**: 확장 소스를 빌드해 `python3 rooms/deployment/ariadne-spec/conformance.py
   --gil "<바이너리>"` — 26/26 확인. 판정기·참조 구현 무수정은
   `git diff -- rooms/deployment` 0건으로 증명.
6. **run2**: 같은 시각(동일 분)에 두 구현으로 이 저장소의 web을 생성,
   ① `gil-data` JSON 추출·파싱·심층 비교, ② HTML 전문 diff (상한 확인).
   산출물 HTML은 3-verification/runs/에 저장하지 않고 로그만 남긴다
   (수백 KB 반복 산출물 — 재현 명령이 곧 산출물이다).
7. **run3**: 스크래치 샌드박스에서 음성 대조 2종 (깨진 체인 거부 + 파일 무생성,
   비깃 디렉토리 성공 + `last_activity: null`).
8. 실행 로그를 `3-verification/runs/run{0..3}-*.txt`로 저장하고 README에 재현
   방법을 불변 기준/가변 확인으로 나눠 적는다 (v0.9.1 재현 문서 규약).

## 준비물

- Go 1.26.2 (darwin/arm64), Python 3.9.6, git 2.x — C017과 동일 환경
- 배포본 v0.9.1 무수정: `rooms/deployment/ariadne-spec/{gil.py, conformance.py}`
- 부모 소스: `../C017-go-git-binding/3-verification/gil-go/main.go` (1088줄)
- 실데이터: 이 저장소의 `rooms/experiment/chains` (체인 3개, 열린 사이클 포함)

## 측정 방법

| 측정 | 도구 | 성공 기준 |
|---|---|---|
| 계약 준수 | 무수정 conformance.py | run1 = 26/26 (기각 1·2) |
| 판정기 건전성 | 〃 | 참조 구현 = 26/26 (기각 4) |
| JSON 구조 동일 | 파이썬 json 파싱 + `==` 심층 비교 | run2 ① 일치 (기각 3) |
| 바이트 상한 | `diff` HTML 전문 | 참고 지표 (미달이어도 기각 아님) |
| 음성 대조 | exit 코드 + 파일 존재 관찰 | run3 거부·무생성 / 성공·null |

## 사용자 컨펌

- 생략 — 소환자 Clew가 과제·계약·판정 기준(무수정 26/26 + JSON 구조 동일)을
  소환 프롬프트에 명시했고, 설계는 그 범위를 벗어나지 않는다.
