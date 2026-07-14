# 4. 결과 분석

## 통계적 결과

| run | 대상 | 결과 | 기준값(2-design) 대비 |
|---|---|---|---|
| run0(a) | C014 바이너리 (변경 전) | **19/26** | 기준선 — 가설의 예측(19/26)과 정확히 일치 |
| run0(b) | 참조 구현 gil.py | **26/26** | 판정기 건전 (기각 조건 2 해당 없음) |
| run1 | 확장 Go 바이너리 | **24/26** | FAIL = {WEB-SELFCONTAINED, WEB-JSON}뿐 — 성공 기준 충족 |
| run2 | 실데이터 verify 교차 | stdout·stderr·exit **전부 동일** | `diff` 무차이 (기각 조건 3 해당 없음) |
| run3 | 샌드박스 ①~⑤ | 전부 규약대로 | 기각 조건 3 해당 없음 |

배포본 판정기·참조 구현 무수정: `git diff -- rooms/deployment` 0건 (기각 조건 4 해당 없음).
목표 3항목의 전이: GIT-CLOSE FAIL→**PASS**, VERIFY-CLEAN FAIL→**PASS**,
VERIFY-TAMPER 공허 PASS→**실질 PASS**. 아울러 판정기 이동분(step 계약)의
OPEN-CREATE FAIL→PASS, STEP-OK FAIL→PASS, FSCK-R9 FAIL→PASS,
STEP-REJECT 2종 공허 PASS→실질 PASS.

## 데이터 직접 관찰

1. **공허 통과의 지형이 판정기와 함께 이동했다.** run0(a)에서 C014 바이너리는
   19/26인데, 이 19에는 세 개의 공허 PASS(STEP-REJECT 2종, VERIFY-TAMPER — 모두
   "미구현 exit 3 ≠ 0" 덕)가 들어 있다. 같은 바이너리가 C014 시점의 v0.5.0
   스위트에서는 18/22였다. 즉 **판정기가 v0.5→v0.8로 이동하자 같은 바이너리의
   성적과 그 의미가 함께 변했다** — OPEN-CREATE는 실질 PASS에서 FAIL로 떨어졌고
   (스위트가 `step: 1`을 새로 요구), 공허 PASS는 2개에서 3개로 늘었다. 계약 준수는
   한 번의 판정이 아니라 판정기의 버전에 대해 상대적이다.

2. **verify의 실데이터 대조는 출력 포맷까지 계약임을 보여줬다.** run2에서 클린
   (`OK — 닫힌 사이클 20개 검사, 변조 0건`)과 변조(`변조 감지 [태그]:` + 경로 목록 +
   stderr 요약 `닫힌 사이클 20개 검사 — 변조 1건`) 양쪽 모두 참조 구현과 바이트 단위
   동일했다. 우연이 아니라 이식 방식의 결과다: `git diff --name-only <태그>` ∪
   `status --porcelain`의 `??` 행 합집합, 정렬, 문구까지 그대로 옮겼다. 스위트는
   exit 코드만 보지만 인간(과 후속 스크립트)은 출력을 읽는다 — 구현 교체가 들키지
   않으려면 포맷도 계약이다.

3. **경로 해석이 이식의 실제 함정이었다.** 파이썬 `os.path.relpath`는 cwd 기준으로
   혼합(절대/상대) 경로를 조용히 처리하지만 Go `filepath.Rel`은 둘 다 같은 형이어야
   하고, macOS의 `/tmp`·`/var` 심링크(conformance 샌드박스가 `/var/folders/...`에
   생긴다) 때문에 `git rev-parse --show-toplevel`(해석된 절대 경로)과
   `filepath.Abs`(미해석 가능)가 어긋날 수 있다. `relToRepo`에 `EvalSymlinks`를 넣어
   흡수했다 — C014 교훈 3(CLI 문법의 암묵 계약)과 같은 종류의, 스펙 문면 밖에 사는
   **환경 계약**이다.

4. **run3 ①이 GIT-CLOSE의 핵심 조건을 눈으로 확인시켰다.** 무관 파일
   (`unrelated.txt`)이 더럽혀진 상태에서 close --git의 커밋에는
   `rooms/experiment/chains/demo/C001-first-step/...` 경로만 들어갔다. 이것이 깃 각인
   규약(SPEC §4) "사이클 디렉토리만을 담은 커밋"의 기계적 의미이고,
   `git add -A -- <경로>` + `git commit -- <경로>`의 pathspec 격리가 그 구현이다.
   태그는 annotated(`git cat-file -t` = tag)로 참조 구현과 동일, close 후 cycle.yaml은
   `step: 5`로 마감됐다.

## 예상과 달랐던 것

- **run1 로그의 첫 생성본에서 헤더의 소스 줄 수가 누락됐다** — 로그 생성 셸
  스크립트가 바이너리 경로에 `../main.go`를 붙인 오타. 판정 출력이 아닌 헤더 결함이라
  헤더만 정정해 재생성했다(같은 바이너리·같은 판정기). C014 교훈 4("판정 절차 자체도
  틀릴 수 있다")의 작은 재현.
- **`open --git`의 반쪽 이식 유혹.** 참조 구현의 open --git은 커밋만 하면 간단하지만,
  v0.8 원장 규율은 open의 깃 경로를 push·자동 재번호와 한 몸으로 정의한다. 커밋만
  이식하면 "원장 규율이 있는 척하는" 바이너리가 된다. 판정 항목에 없음을 확인하고
  C014의 관례대로 **어떤 변경도 하기 전의 정직한 거부(exit 3)** 로 남겼다.
- 파이썬 `str.isdigit()`와 Go `strconv.Atoi`의 수용 범위 차이(`+3` 등 부호 허용)를
  `isDigits` 헬퍼로 좁혀야 R9·step 검증의 거부 동작이 참조 구현과 일치했다 —
  표준 라이브러리의 "숫자"조차 언어마다 다른 계약이다.

## 판정

기각 조건 1~4 중 어느 것도 발동하지 않았다. **가설 채택.**
