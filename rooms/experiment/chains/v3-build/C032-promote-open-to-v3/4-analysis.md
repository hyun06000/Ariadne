# 4. 결과 분석

## 통계적 결과

5측정 기준값 대비 (2-design.md M1~M5):

| 측정 | 기준(성공) | 실측 | 판정 |
|---|---|---|---|
| M1 v3 쓰기 생존 | v3 네이티브 산출물 생성 | `gil v3 open` → steps.yaml + steps/ (루트 define s1) | **PASS** |
| M2 은퇴 안내 | exit≠0 ∧ v3 사용법 안내 ∧ 침묵실패 아님 | v2 습관 `gil open x y` → exit 1, v3 방식·순환 규칙 안내 | **PASS** |
| M3 무회귀 | conformance 134/134 | 게이트 프로세스-환경 상속 시 **134/134 ✔** | **PASS** |
| M4 데이터 불변 | 원장 digest 불변 | baseline `05ba3e6c` == 실측 `05ba3e6c` | **PASS** |
| M5 눈 생존 | web --v3 노드 수 유지 | 132노드·131엣지·387KB (승격 후에도 189 읽음) | **PASS** |

배포판 적용 후 재실측: v2 습관→은퇴 안내, conformance 134/134, `gil log` 등 조회 무영향. **5/5 ALL PASS.**

## 데이터 직접 관찰

**은퇴 안내 실물 (M2, 배포판에서 직접 호출):**
```
$ gil open x y --author clew
거부: gil open은 이제 v3 사이클을 연다 (버전리스 승격, C032).
      v2 습관: gil open <chain> <slug> --author <이름>
      v3 방식: gil v3 open <dir> --title '...'
        스텝: gil v3 step <dir> --kind hypothesis|verify|analyze
        순환: define→hypothesis→verify→analyze (번호 아님, kind)
      기존 v2 원장을 조작해야 하면(전환기): GIL_V2_OPEN=1 gil open ...
```
침묵 실패(인자 무시하고 뭔가 생성)가 아니라 **정확히 v2→v3 대응을 가르친다.** 상현님 "에러 메시지가 흡수" 통찰의 open 실현.

**conformance가 v2 open을 직접 검사하는 항목 (M3 crash의 원인, 직접 grep):**
`OPEN-CREATE·OPEN-INCREMENT·OPEN-GIT·OPEN-NEW-ROOT·OPEN-PARENT-*·OPEN-REJECT-SLUG·OPEN-PROMOTES-OWNER·GUARD-PRIMARY-REFUSE·GUARD-OWNER-OK·GUARD-LINKED-OK·GUARD-RESERVED-*` — 최소 20+개가 `gil open <chain> <slug>` 인터페이스를 실행한다. 게이트 없이 은퇴시키면 첫 open(OPEN-CREATE)에서 cycle.yaml이 안 생겨 `_seal_closed`가 FileNotFoundError로 crash. **판정기가 v2 인터페이스에 결합돼 있음을 코드로 확인.**

**인터페이스 정체성 차이 (승격이 "함수 교체"가 아닌 이유, 코드 실측):**
- v2 `gil open <chain> <slug>` — 위치인자 2, 번호 자동증가, cycle.yaml+5문서
- v3 `gil v3 open <dir>` — 위치인자 1(경로), 번호 없음(경로가 정체), steps.yaml

## 예상과 달랐던 것

1. **게이트로도 conformance가 딱 1개만 깨진 게 아니라 0개였다(계측기 구분 후).** 첫 실측 133/134의 유일 FAIL `NO-GIT-GRACEFUL`은 rc=127 — 내 `env GIL_V2_OPEN=1 python3` 래퍼가 그 테스트의 **빈 PATH 환경**에서 python3를 못 찾은 것. 게이트를 프로세스 환경으로 상속하니 134/134. **환경변수 주입 방식이 계측기를 오염시킬 수 있다** — Weft·Bobbin의 "계측기 vs 반증 구분"이 환경변수 층에서 재연. 이건 승격의 성질이 아니라 테스트 하네스가 PATH를 지우는 방식과 env 래퍼의 상호작용.

2. **"gil open을 v3로 승격"이 단순 함수 포인터 교체일 거라 은연중 가정했으나, 인터페이스 정체성 전환이었다.** v2(번호)·v3(경로)의 위치인자 수·정체성 모델이 달라, `cmd_open`을 `cmd_v3open`으로 못 바꾼다(인자 파싱이 안 맞음). 그래서 C032의 실제 승격은 "v3 직접 진입"이 아니라 "v2 은퇴 안내 → v3로 유도"의 최소형이 됐다. 완전한 인터페이스 통일은 후속의 씨앗.

## 판정

**가설 채택 (supported).** 기각조건 대조:

- 기각조건 1 (공존 깨짐)? **아님** — 게이트로 189 원장 조작 가능, M4 데이터 불변, M5 눈 생존.
- 기각조건 2 (①이 ③과 분리 불가)? **부분적으로 참, 그러나 반증 아님** — 게이트 없이는 conformance crash(M3-a). ①은 ③과 분리 불가가 맞다. **그러나 이는 가설이 예견한 긴장이고, 전환기 게이트가 그것을 흡수**해 134/134를 지킨다. 완전 버전리스(게이트 없이 초록)는 conformance v3 재정의(③)를 요구 — 후속의 정확한 좌표. 분할 실패가 아니라 **분할 경계의 실증.**
- 기각조건 3 (침묵 실패)? **아님** — M2가 친절한 안내를 실증.
- 기각조건 4 (상현님 방향 변경)? **아님** — 설계 3연속 컨펌으로 방향 확정.

**핵심 결론**: `gil open`의 버전리스 승격 첫 조각(네임스페이스 승격 + v2 은퇴 안내)이 배포판에 섰다. 승격은 도구 복잡화가 아니라 **기본값 전환 + 안내 흡수**로 달성됐다(상현님 처방 실현). 완전 버전리스로 가는 길에서 **conformance v3 재정의(③)가 다음 필수 관문**임이 실측으로 드러났다 — 이 사이클이 그 좌표를 정확히 찍었다.
