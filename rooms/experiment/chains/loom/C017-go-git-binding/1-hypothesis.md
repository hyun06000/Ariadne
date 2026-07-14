# 1. 가설 수립

## 이전 사이클의 교훈

부모 [C014-go-binary-open-close](../C014-go-binary-open-close/5-report.md)에서:

1. **쓰기 규율은 언어를 건넌다** — 참조 구현의 "사전 검증 전부 → 변경 → 사후 fsck →
   실패 시 원상 복구" 구조를 그대로 이식하면 판정이 따라온다.
2. **거부형 검사의 공허 통과는 수락형이 도착해야 실질이 된다** — C014 시점의
   VERIFY-TAMPER는 "verify 미구현 → exit ≠ 0"이라는 공허한 이유로 PASS였다.
   같은 PASS 글자가 구현 도착 후에는 다른 의미가 된다.
3. 다음 사이클 제안 **(A) Go 이식 ②: 깃 바인딩** — close --git·verify를 추가하면
   GIT-CLOSE·VERIFY-CLEAN이 실질 PASS로, VERIFY-TAMPER가 공허→실질 통과로 바뀐다.
   제안 (C) — Go 이식에 step이 들어오면 C013(step 가시성)과의 병합 지점이 생긴다.

## 문제 분할

Go 이식 로드맵의 잔여는 ② 깃 바인딩, ③ web, ④ release다. 이번에 정복할 가장 작은
문제는 **② 깃 바인딩**: `close --git`(사이클 디렉토리만 담은 커밋 + 주석 태그
`cycle/<chain>/<id>`, SPEC §4)과 `verify`(닫힌 사이클의 태그↔작업 트리 대조)다.

단, C014가 판정받은 conformance는 v0.5.0 동봉본(22항목)이었고, **현재 배포본은
v0.8 동봉본(26항목)이다**. 판정기가 이동하며 step 계약(v0.6)이 들어왔다:
OPEN-CREATE가 `step: 1`을 요구하고, STEP-OK·STEP-REJECT 2종·FSCK-R9가 신설됐다.
즉 C014 바이너리를 오늘의 판정기에 세우면 "기존 18항목"조차 유지되지 않는다
(OPEN-CREATE 탈락 예정). 따라서 이번 폭의 범위는 **깃 바인딩(주 목표) + step
계열의 이식(기존 항목 유지를 위한 계약 추격)**이며, 후자는 제안 (C)의 병합
지점이 실제로 도착한 것이다. web 2종은 이번에도 범위 밖에 남긴다.

C014 교훈 그대로, 깃 호출은 Go 표준 라이브러리 `os/exec`를 통한 깃 CLI 호출이다 —
"외부 의존성 0"의 뜻은 **라이브러리 의존 0**이고, 도구 의존은 참조 구현과 동일하게
깃뿐이다(참조 구현도 subprocess로 깃 CLI를 부른다).

## 가설

> **가설**: C014의 Go 구현에 참조 구현(gil.py v0.8 동봉본)과 같은 쓰기 규율로
> ① `close --git`(사이클만 담은 커밋 + 태그), ② `verify`(태그↔작업 트리 대조),
> ③ step 계열(open의 `step: 1`, `step` 명령, fsck R9, close의 `step: 5` 마감)을
> 이식하면, **무수정** 배포본 conformance.py(v0.8 동봉본, 26항목) 판정이
> 기준선 19/26에서 **24/26**으로 올라 GIT-CLOSE·VERIFY-CLEAN이 실질 PASS,
> VERIFY-TAMPER·STEP-REJECT 2종이 공허→실질 PASS가 되고, 범위 밖 WEB 2종만
> FAIL로 남을 것이다.

(기준선 19/26은 예측이다: C014 바이너리는 FSCK 9 + OPEN 2 + CLOSE 3 + LOG 2에
더해 STEP-REJECT 2종과 VERIFY-TAMPER를 "미구현 exit 3 ≠ 0"의 공허 통과로 얻는다.
스텝 3에서 기준선부터 실측해 예측 자체를 검증한다.)

## 기각 조건

다음 중 하나라도 발생하면 가설은 기각된다.

1. 확장된 Go 바이너리의 conformance 판정에서 **WEB 2종 이외의 항목이 하나라도 FAIL**
   (24/26 미달, 특히 GIT-CLOSE·VERIFY-CLEAN·VERIFY-TAMPER 중 FAIL이 있으면 즉시 기각).
2. 같은 판정기로 참조 구현(gil.py)을 돌린 **회귀 대조가 26/26이 아님에도** 이를
   근거로 삼는 경우 — 판정기 자체가 흔들리면 판정 무효.
3. 실데이터 교차 검증에서 Go `verify`의 판정(종료 코드·표준 출력)이 참조 구현과
   **다른** 경우, 또는 샌드박스 실측에서 `close --git`의 커밋이 사이클 디렉토리 밖
   경로를 포함하거나 태그명이 `cycle/<chain>/<id>` 규약을 어기는 경우.
4. conformance.py 또는 gil.py를 한 글자라도 수정해야 통과하는 경우 (무수정 원칙 위반).
