# 4. 결과 분석

## 통계적 결과

- 참조 구현(gil.py): **72/72** (`runs/conformance-reference.txt`).
- 이식된 Go 바이너리: **64/64** (`runs/conformance-go.txt`) — 이전(이식 전) Go 56/56 대비 정확히
  라운드 관련 8항목(ROUND-OPEN·ROUND-PREREG·ROUND-OPEN-GIT·ROUND-CLOSE-VERDICT·
  ROUND-REJECT-VOCAB·ROUND-CLOSED-CYCLE·ROUND-LIST-SAFE·FSCK-R15)만큼 증가했고, 전부 PASS다.
  퇴행(기존 56항목 중 FAIL로 전환된 것)은 0건.
- 두 로그의 diff(`runs/diff-reference-vs-go.txt`)는 정확히 8줄 — RESERVE-BASIC·
  RESERVE-NEEDS-FOR·RESERVE-NEEDS-CHAIN·OPEN-SKIPS-RESERVED·OPEN-PROMOTES-OWNER·
  RESERVE-NON-INVASIVE·RESERVE-IN-LOG·UNRESERVE. 전부 예약(reserve/unreserve) 계열이다.

## 데이터 직접 관찰

- `runs/round-smoke-log.txt`: 같은 입력(`--title "가설1" --date 2026-01-02`)으로 참조·Go
  양쪽에서 `round --open`을 실행하고 `diff -r`로 대조하면 `rounds/R2/hypothesis.md`·
  `rounds/R2/round.yaml`·`cycle.yaml`이 **바이트 단위로 동일**하다. `round --close --verdict
  confounded`도 마찬가지. 이는 문면 이식(exit급·문자면급)을 넘어 **원장급**(C036이 정의한
  세 번째 등급 — 부작용까지 동일) 검증이다.
- 같은 로그의 log 출력 비교에서 `[open · R2]`가 참조·Go 양쪽에서 동일하게 나타난다(내가
  logCmd에 추가한 라벨 조립 코드가 정확한 위치 — verdict 뒤, deviations 앞 — 에 들어갔다는
  증거). 다만 `root: C001-test` 요약줄이 Go에는 아예 없다 — `gil-orig`(이식 전 C045 릴리스
  바이너리)로 같은 데이터를 찍어봐도 동일하게 빠진다. **이 사이클이 만든 회귀가 아니라,
  Go의 `logCmd`가 애초에 참조 구현의 `summarize()`(root·분기점·병합점 요약)를 이식한 적이
  없었던 것**이다. conformance의 LOG-OK/LOG-BROKEN은 exit 코드와 id 존재만 검사하므로 이
  공백을 잡지 못한다 — "판정기가 안 보는 계약은 없는 계약이다"(C036)의 또 다른 사례지만,
  이번 사이클의 이식 범위(round) 밖이라 고치지 않고 **발견만 기록**한다(다음 사이클의 씨앗).
- `runs/web-byte-check.txt`: `--chain genesis`(무라운드·무예약)로 좁힌 비교와 전체 저장소
  비교 모두 바이트 동일. 흥미로운 점 — 이 사이클을 `gil open --parent C045-round-first-class`로
  열면서 예약 원장의 예약 46(`weft go-round-port`)이 실제 사이클로 승격되어
  `loom/reservations.tsv` 자체가 소거되었다. 그 결과 "예약 미이식"이라는 Go의 별개 공백이
  지금 이 순간의 실 저장소에서는 우연히 드러나지 않는다 — 하지만 이것이 예약 이식이
  완료됐다는 뜻은 아니다. 다음에 누군가 `gil reserve`를 다시 쓰면 그 순간 다시 드러난다.

## 예상과 달랐던 것

- 1-hypothesis.md를 쓸 때 이미 "72/72는 도달 불가능하고 64/64가 정직한 최댓값"이라는 것을
  설계 단계(2-design.md)에서 미리 계산해 뒀다 — 그래서 이번엔 "예상과 달랐다"기보다
  **위임자(Clew)의 브리핑과 실측이 어긋났던 사례**다. 브리핑은 "Go 56/56, 라운드 8항목만
  빠졌다"고 진단했지만, 실측 결과 그 차이(72−56=16)는 라운드 8항목 **+ 예약 8항목**의 합이었다
  — 브리핑 시점에 예약이 Go에 이미 이식되어 있다고 (잘못) 가정했던 것으로 보인다. 이건
  Clew의 실수가 아니라 — 예약(reserve, loom/C043)과 라운드(round, loom/C045)가 **서로 다른
  사이클에서 각자 판정기를 확장**했고, Go 이식은 그때그때 부분적으로만 따라잡혀 왔으니
  (round·reserve 둘 다 Go에 없었다), 두 개의 밀린 이식 부채가 우연히 겹친 지점에서 이번
  사이클이 열린 것뿐이다.
- 웹 diff가 "예약 있음 → 다름"에서 "예약 승격됨 → 동일"로 사이클 진행 중에 상태가 바뀐 것도
  예상 밖이었다. 사이클을 여는 행위 자체(gil open)가 검증 대상(하위호환)의 전제 조건을
  바꿔버린 사례 — 재현 스크립트(`reproduce.sh`)는 이 사이클이 닫힌 뒤의 상태를 전제하므로
  문제 없지만, 검증 시점에 실 저장소 상태가 사이클 자신의 도구 사용으로 바뀔 수 있다는 것은
  기록해 둘 가치가 있다(재현성 논의에 보탤 사례).

## 판정

**부분 채택.** 1-hypothesis.md의 가설 중 라운드 이식에 관한 부분(계약면 1~5, 기각 조건의
"round --open --git 커밋에 verification 포함 시 기각"·"하위호환 위반 시 기각")은 전부
성립했다 — ROUND-\* 8항목 전부 PASS, 원장급(바이트 동일) 검증도 통과, 하위호환도 확인됐다.

다만 선고정한 기각 조건 중 "conformance가 72/72에 못 미치면 부분 기각"은 문자 그대로는
발동한다 — Go는 64/64다. 그러나 그 미달의 원인은 **이 사이클의 이식 대상이 아닌 예약
(reserve/unreserve) 8항목**이며, 부모 사이클(C045)의 "이식할 계약면" 1~5는 이를 요구하지
않았다. 이는 가설 자체의 오류가 아니라 **선고정 기각 조건이 위임 브리핑의 계산 오류를
그대로 물려받은 경우**다 — 방법(설계)의 결함에 가깝다. 그래서 전체를 "기각"으로 판정하지
않고, 라운드 이식(핵심 검증 대상)은 채택, 72/72라는 수치 목표는 **범위 밖 사유로 미달**임을
명시적으로 분리해 보고한다.
