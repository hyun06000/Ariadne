# 1. 가설 수립

## 이전 사이클의 교훈

부모 **C030**이 v3 네이티브로 실제 문제를 굴려 "v3는 눈이면서 손"임을 실증하고, "v3가 v2를 대체"의 걸림돌 4개를 명시했다. 그 1순위:

> **v3 쓰기(open/step/close)를 배포판 gil에 통합** — 걸림돌 ①. C027·C028 이식 패턴으로 gilv3 open/step/close를 배포판 gil.py에. 그러면 실사이클을 배포판 gil로 v3 네이티브로 열 수 있다. "v3가 v2를 대체"의 첫 실질 조각.

상현님 "그걸로 가자."

## 문제 — v2/v3 명령 이름 충돌

배포판 gil엔 이미 `cmd_open`·`cmd_step`·`cmd_close`(v2, 5문서 사이클)가 있다. gilv3의 open/step/close(steps.yaml 트리)와 **같은 이름**이다. 게다가 인자가 완전히 다르다:
- v2 step: `gil step <chain> <cycle> <n>` (1~5).
- v3 step: `gilv3 step <dir> --kind <kind> --outcome <oc> --to <sid>`.

이 충돌을 어떻게 푸는가가 이 사이클의 핵심 설계.

## 문제 분할 — 명령 표면 후보

1. **후보 A: `gil open --v3` 플래그** (C028 web 패턴). 기본 v2, --v3면 v3. 단 step 인자가 v2(n)·v3(--kind) 완전히 달라 한 파서에 두 인자셋 혼재 — 부담.
2. **후보 B: `gil v3 open` 서브명령 그룹** (네임스페이스 분리). v3 쓰기를 `gil v3 <open|step|close|status|view>` 아래로. 인자 충돌 없음(각자 파서), v2 기존 명령 무손상.
3. **후보 C: 별도 이름 `gil vopen`/`gil vstep`** — 명확하나 명령 수 폭증, 못생김.

**첫 번째로 정복할 것: 후보 B(`gil v3` 서브명령 그룹).** 이유:
- **인자 충돌 원천 해소** — v3 step의 --kind/--outcome/--to가 v2 step의 n과 안 섞인다(각자 파서).
- **v2 완전 무손상** — 기존 open/step/close 그대로. conformance 무회귀.
- **개념 정합** — "v3 네이티브 쓰기"가 하나의 네임스페이스로 묶임. 상현님 "gil의 v3"와도 맞음(gil v3 = gil의 v3 모드).
- **확장 여지** — 나중에 v3가 기본이 되면 `gil v3`를 최상위로 승격 가능.

## ⭐ 통합의 형태 — C027·C028 이식 세 규율 재사용

C027·C028이 확립: ① 의존 폐포까지 추출 ② 죽은 스캐폴딩 제거 ③ 네임스페이스 수동 격리. gilv3 open/step/close + 헬퍼(load·dump·growing_tip·next_id·by_id·cycle_state·git_imprint 등)를 배포판 gil.py에 인라인. 오라클 = gilv3 open/step/close 동작. 배포판 `gil v3 open/step/close`가 같은 steps.yaml·커밋을 내면 이식 보존.

## 가설

> **가설**: gilv3의 v3 쓰기 명령(open/step/close/status/view)과 그 의존 헬퍼를 배포판 gil.py에 `gil v3 <cmd>` 서브명령 그룹으로 인라인 통합하면, (a) `gil v3 open/step/close`가 gilv3와 동일하게 steps.yaml 트리를 쓰고(백트래킹·죽은 잎·형제 표현), (b) 기존 v2 open/step/close는 무손상(conformance 무회귀)이며, (c) gil.py가 자기완결을 유지한다 — 즉 실사이클을 배포판 gil 하나로 v3 네이티브로 열 수 있게 되어 "v3가 v2를 대체"의 첫 실질 조각이 선다.

## 기각 조건

- `gil v3 open/step/close`가 gilv3와 다른 steps.yaml/커밋을 내면 → **기각**(이식이 로직 바꿈).
- 통합이 v2 open/step/close나 conformance를 깨면 → **기각**(v2 회귀).
- v3 서브명령이 배포판 argparse 구조와 안 맞으면(서브파서 중첩 불가 등) → **조사**(표면 재설계).
- gil.py가 외부 모듈 의존하면 → **기각**(자기완결 위반).
