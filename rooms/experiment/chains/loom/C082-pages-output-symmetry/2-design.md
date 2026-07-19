# 2. 실험 설계

## 정답 먼저: 기대 행동 (판정 항목)

도구를 고치기 전에 "고쳐진 pages는 무엇을 하는가"를 고정한다. 각 항목은 종료 코드·파일·stdout만 관찰한다(§7 계약면).

| # | 판정 항목 | 준비 | 기대 |
|---|---|---|---|
| T1 | **PAGES-OUTPUT-PATH** | 빈 저장소, `pages -o <tmp>/custom.yml` | exit 0. `<tmp>/custom.yml` 생성, 내용 = `_PAGES_WORKFLOW`. 기본 경로 `.github/workflows/gil-pages.yml`는 **안 생김**. |
| T2 | **PAGES-OUTPUT-STDOUT** | `pages -o -` | exit 0. **stdout = 워크플로 전문** (안내 문구 없음, 파이프 안전). 저장소 파일 **무변화**. |
| T3 | **PAGES-DEFAULT-UNCHANGED** (회귀 가드) | 무 `-o`, 기본 경로 없음 | exit 0. `.github/workflows/gil-pages.yml` 생성 = `_PAGES_WORKFLOW`. |
| T4 | **PAGES-FORCE-UNCHANGED** (회귀 가드) | 기본 경로 이미 존재, 무 `--force` | exit≠0. 파일 무변화. `--force`면 덮어씀 exit 0. |
| T5 | **PAGES-DRYRUN-UNCHANGED** (회귀 가드) | `--dry-run` | exit 0. 아무 파일도 안 생김. |

기존 판정기에 pages 항목이 있으면 회귀 가드로 재사용/보강, 새 T1·T2 신설.

## 절차

1. 참조 conformance.py에서 기존 pages 판정 항목 조사 → T3·T4·T5 커버 여부 확인.
2. T1·T2(및 미비 시 T3~T5) 판정 항목 신설 — 참조·Go 양쪽 `--gil` 주입 동일 판정.
3. 참조 `cmd_pages`에 `-o/--output` 이식 (D1~D4). Go `cmdPages`도 **동시** 동형 이식.
4. argparse/flag 등록: `p_pages.add_argument("-o","--output", default=None)`. Go도 `-o` string 플래그(기본 "").
5. 판정기 재실행 (참조·Go 각각 전체) → 100% 확인, 수정 전 스냅샷과 대조(신설 항목이 수정 전엔 FAIL이어야 유효).
6. 실데이터 parity: `diff <(참조 pages -o -) <(go pages -o -)` 바이트 동일.
7. 자기적용: `pages -o -`로 뽑은 워크플로를 현재 `.github/workflows/gil-pages.yml`과 diff (워크플로 소스 불변이므로 "변경 없음" 기대).

## 준비물

- 참조 gil.py (2.32.0), go/main.go (Go 구현). conformance.py 판정기.
- 임시 sandbox 디렉토리(git init) — pages는 저장소 상대 경로를 계산하므로.
- Go 빌드 툴체인 (go build).

## 측정 방법

- **성공**: 참조·Go 판정기 각각 전체 PASS(신설 T1·T2 포함), 수정 전엔 신설 항목 FAIL. parity diff 0바이트. 자기적용 diff "변경 없음".
- **기각**(1-hypothesis 기각 조건): `-o`가 무시/고정경로行, `-o -`가 stdout 미출력 또는 파이프 오염, 기본·force·dry-run 회귀, stdout 경로가 저장소 변경, 참조↔Go parity 깨짐.

## 설계 결정 (구현 규약)

- **D1 `-o -` (stdout)**: 워크플로 전문을 stdout에 그대로, 안내 문구 0(파이프 안전). 저장소 무변화(force·존재검사·makedirs 건너뜀).
- **D2 `-o <path>` (파일)**: 경로 불문 동일 규칙 — 존재+무force = 거부, dry-run 반영. 기본 경로 특별대우 없음. makedirs는 부모 디렉토리.
- **D3 dry-run 우위**: `--dry-run`은 어떤 `-o`와도 부작용 없음. `-o -`+dry-run이면 dry-run 우선(탐침 우위).
- **D4 default=None 센티넬**: `-o` 미지정(None) = 기존 고정 경로 폴백 → T3 회귀 0. web은 기본 파일명이지만 pages는 기본 경로 폴백이 있어 None을 씀.

## 사용자 컨펌

생략 — 상현님 "둘 다 병렬로" 위임 + 자율 위임("하고 싶은 걸 하렴"). 이슈 #21이 제안까지 명시(`-o` 추가, `-o -` stdout). 설계가 이슈 제안을 그대로 따르므로 별도 컨펌 불요.

- [x] 컨펌 받음 (일자: 2026-07-19, 이슈 #21 제안 + 병렬 위임으로 갈음)
