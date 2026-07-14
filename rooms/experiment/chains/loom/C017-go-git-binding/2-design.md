# 2. 실험 설계

## 원칙

- **정답을 도구보다 먼저 고정한다.** 판정 기준은 배포본
  `rooms/deployment/ariadne-spec/conformance.py`(v0.8 동봉본, 26항목) **무수정**이며,
  구현 전에 이미 존재한다. 참조 정답은 `rooms/deployment/ariadne-spec/gil.py`(v0.8
  동봉본)의 깃 바인딩·step 동작이다. 둘 다 한 글자도 수정하지 않는다.
- **계승.** 출발점은 main에 병합된 C014의
  `../C014-go-binary-open-close/3-verification/gil-go/main.go`를 이 사이클의
  `3-verification/gil-go/`로 복사한 것이다 (닫힌 사이클 불가침 — 원본은 읽기만).
- **이식 규율.** 참조 구현의 쓰기 규율(사전 검증 전부 → 변경 → 사후 fsck → 실패 시
  원상 복구, 깃 실패 시도 원상 복구)을 구조 그대로 옮긴다. 깃은 `os/exec`로 깃 CLI를
  호출한다 — 라이브러리 의존 0 유지.

## 구현 범위 (참조 구현 대응 명세)

| # | 항목 | 참조 구현의 규칙 (gil.py v0.8 동봉본) |
|---|---|---|
| 1 | `close --git` | 사전: repo 루트 확인, 태그 `cycle/<chain>/<id>` 선존재 거부. 닫기 성공 후 `git add -A -- <사이클상대경로>` → `git commit -m "gil: close <chain>/<id>\n\n<title>" -- <경로>` → `git tag -a cycle/<chain>/<id> -m "<chain>/<id>: <title>"`. 깃 실패 시 cycle.yaml 원상 복구 + `git reset -q -- <경로>` |
| 2 | `verify [root] [--chain]` | 닫힌(status=closed) 사이클마다: 태그 없으면 stderr 경고(백필 필요, 실패 아님), 있으면 `git diff --name-only <태그> -- <경로>` ∪ `git status --porcelain --untracked-files=all -- <경로>`의 `??` 행. 합집합이 비지 않으면 변조 보고 + exit 1. 무변조면 `OK — 닫힌 사이클 N개 검사, 변조 0건` |
| 3 | step 계열 | open이 `step: 1`을 lineage 다음 행에 기록. `step <chain> <id> <n>`: 1~5 검증(R9), 닫힌 사이클 거부, step 행 치환(없으면 closed 행 뒤 삽입), 사후 fsck 실패 시 복구, `--git`(사이클만 커밋)/`--push`. close는 step 행을 `step: 5`로 마감(없으면 삽입). fsck에 R9 추가: step 존재 시 1~5 정수, 닫힌 사이클이면 5 |
| 4 | 정직한 거부 | `open --git`(원장 규율 v0.8은 push 전제), `web`, `release`는 여전히 범위 밖 — 어떤 변경도 하기 전에 exit 3으로 미구현 선언 |

## 절차 (run 0~3)

모든 실행 로그는 `3-verification/runs/`에 저장한다. 임시 산출물(샌드박스)은
세션 스크래치패드에 만들고 저장소를 오염시키지 않는다.

1. **run0 — 기준선·회귀 대조** (구현 변경 전):
   - C014 소스 그대로의 바이너리를 배포본 conformance로 판정 → 가설의 기준선
     예측(19/26) 실측.
   - 참조 구현 `python3 gil.py`를 같은 판정기로 → 26/26 확인 (판정기 건전성).
2. **run1 — 본 판정**: 확장 Go 소스 빌드(`go build`, 버전·환경 기록) 후
   `python3 conformance.py --gil "<빌드된 바이너리>"` → **24/26 + FAIL이 WEB 2종뿐**인지.
3. **run2 — 실데이터 교차 검증**: 이 저장소(닫힌 사이클·태그 실존)에서
   Go `verify`와 참조 `verify`의 표준 출력·종료 코드를 **바이트 단위 대조**.
   변조 시나리오도 실측: 닫힌 사이클 파일을 임시 변조 → 양쪽 모두 exit 1 + 동일 보고
   확인 → 원상 복구(`git checkout`)를 로그로 남긴다.
4. **run3 — 샌드박스 실측(계약 밖 세부)**: 스크래치패드의 일회용 깃 저장소에서
   ① close --git 커밋의 경로가 사이클 디렉토리로 격리되는지(`git show --name-only`),
   ② 태그가 주석 태그(annotated)인지(`git cat-file -t`), ③ 태그 선존재 시 거부·무변화,
   ④ 깃 저장소가 아닌 곳에서 `close --git` 거부 + cycle.yaml 무변화,
   ⑤ Go `step --git` 커밋도 사이클 디렉토리로 격리되는지 확인.

## 준비물

- Go 1.26.2 (darwin/arm64, `/opt/homebrew/bin/go`), Python 3.9.6, 깃 CLI.
- 배포본 v0.8: `rooms/deployment/ariadne-spec/{conformance.py, gil.py}` (무수정).
- C014의 `main.go` (739줄, main 병합본) — 복사 후 확장.

## 측정 방법

| 측정 | 성공 기준 | 대응 기각 조건 |
|---|---|---|
| run1 통과 수·FAIL 목록 | 24/26, FAIL = {WEB-SELFCONTAINED, WEB-JSON} | 1 |
| run0 참조 구현 | 26/26 | 2 |
| run2 stdout·exit 대조 | `diff` 무차이, exit 동일 (클린·변조 양쪽) | 3 |
| run3 ①~⑤ | 전부 규약대로 | 3 |
| `git diff` (판정기·참조 구현) | 무변경 | 4 |

## 사용자 컨펌

- 생략 — 사유: 소환장이 과제(범위·판정 기준·목표 항목)를 이미 확정했고, 이 설계는
  그 확정 사항을 절차로 옮긴 것이다. 판정기·참조 구현 무수정 원칙이 설계의 자유도를
  계약 안쪽으로 구속한다.
