# 2. 실험 설계

가설(1-hypothesis.md): close-time 관문 + fsck 역방향 경고가 (a) C053 슬립을 봉인 전에 거부하고, (b) 이미 봉인된 C053을 위반 아닌 경고로 가시화하며, (c) 참조 회귀 0.

## 설계 원칙 — 계약면은 스키마가 아니라 레코드 수다

`_parse_corrections`의 도크스트링이 선을 그어 놓았다: *"deviations.yaml은 사람이 읽는 문서지만, corrections는 도구가 판정하는 기록이다."* R13(corrections)은 v0.5에서 태어나 유예할 과거가 없어 **하드 위반**이고 필수 키·필드까지 검증한다. R10(deviations)은 v0.3 유예-경고다.

그래서 deviations의 계약면을 R13처럼 스키마 강제로 끌어올리지 **않는다.** deviations.yaml은 자유 서술(블록 스칼라 `|`)을 유지하고, 계약하는 것은 오직 **"몇 건인가"** — 최상위 시퀀스 항목(`- ` 로 시작하는 줄) 수다. 이것이 R10의 유예-경고 등급과 정합한다: **카운트 일치는 경고급, 스키마 강제는 위반급.** 두 등급을 섞지 않는다.

## 절차

### A. 참조 구현 (gil.py)

1. **계수기 헬퍼 `_count_deviations(path)`**: 파일을 읽어 `- `로 시작하는 최상위 줄 수를 센다(블록 스칼라 내용은 ≥3칸 들여쓰기라 오계수 불가, 주석·공백 무시). 읽기 실패 시 None.
2. **close-time 관문** (`cmd_close`, 봉인·git 조작 이전 초입): `deviations.yaml`이 존재하면 레코드 수 `n_rec`와 `deviations` 필드 정수 `n_field`를 비교, `n_rec ≠ n_field`이면 `ChainError`로 **거부**(저장소 무변화). 비정수 필드는 R10(fsck)에 위임. 파일 부재 & 필드>0은 기존 R10이 담당(중복 안 함).
   - **auto-count 아님**: 카운트는 저자의 의도이므로 덮어쓰지 않고 의식적 조정을 강제(1-hypothesis 선분 고정).
3. **fsck R10 역방향 경고** (`fsck_collect`): `deviations.yaml` 존재 시 `n_rec ≠ n_field`이면 경고 토큰 `이탈카운트` 추가. **위반 아님** — R10 유예-경고 성격 유지, 봉인된 C053이 fsck rc를 바꾸지 않는다.

### B. Go 구현 (go/main.go) — 대칭 미러

4. `countDeviations(path) int`(−1 = 읽기 실패), `cmdClose`에 동일 관문, `fsckCollect`의 R10 블록에 동일 역방향 경고. **두 몸, 한 계약** — 관문과 계약면이 같은 사이클에 함께 착지(C036·C050 패턴, 지금 열린 Weft 사이클 없음 → CI 무파손). Go는 씨실의 도메인이므로 이 미러는 소환자의 최소 대칭 수정이고, 실질 Go 진화의 주인은 여전히 Weft임을 보고서에 명시.

### C. 판정기 (conformance.py) — 계약면 신설

5. `DEVIATIONS-COUNT` 항목: 자체 샌드박스에 닫을 수 있는 사이클 구성(실보고서). 
   - **음성(슬립 재현)**: `deviations.yaml` 1건 작성 + cycle.yaml `deviations: 0` → `close` → **rc≠0 ∧ status 미봉인(무변화)** 기대.
   - **양성(거짓양성 없음)**: 같은 상태에서 `deviations: 1`로 맞춤 → `close` → **rc0 ∧ status closed** 기대.
   - 두 얼굴을 한 항목에 묶어 T(문다)·F(안 문다) 쌍 검증(C038 쌍 규율). 76→77.

### D. 스펙·문서

6. SPEC.md R10 행에 "deviations.yaml 존재 시 레코드 수 = N(불일치 시 경고); `close`는 봉인 전 불일치를 거부"를 명문화. deviations 설명 절에 계약면=카운트(스키마 아님) 원칙 한 줄.
7. `gil release`로 **v2.15.0**(도구 행동 변경 → 마이너). CHANGELOG.

## 준비물

- 참조/Go gil (rooms/deployment/ariadne-spec/{gil.py, go/main.go}), conformance.py. Python 3, Go(표준 라이브러리).
- 실데이터 회귀 기준: 현행 저장소 76/76 ×2, fsck 위반 0.
- C053 슬립 재현용 픽스처는 판정기 샌드박스 내에서 자체 구축(실 C053 건드리지 않음).

## 측정 방법

- **관문(기각조건 1·2)**: 판정기 DEVIATIONS-COUNT의 음성(rc≠0·무봉인)과 양성(rc0·봉인)이 함께 PASS.
- **역방향 경고·유예(기각조건 3)**: 실저장소 fsck가 rc0 유지(C053이 위반으로 격상되지 않음)이면서 C053에 `이탈카운트` 경고가 뜬다(가시화 확인). CI 게이트(fsck rc0) 무파손.
- **회귀(기각조건 4)**: 변경 후 양 구현 77/77, 기존 76항목 전부 유지. fsck 위반 0(전 사슬).
- **변이 격추**: 관문 제거 변이 → DEVIATIONS-COUNT FAIL(76/77)로 격추 확인.

## 사용자 컨펌

- 생략 — 상현님 전권 위임("너 가고 싶은대로 가보자", 2026-07-19). 보고서 추천을 따르는 자율 진행.

- [x] 컨펌 받음 (일자: 2026-07-19, 위임으로 갈음)
