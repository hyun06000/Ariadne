# 1. 가설 수립

## 이전 사이클의 교훈 (부모: loom/C046-go-round-port)

C046에서 Go 바이너리에 라운드를 이식해 부분 채택(Go 64/64, 참조 72/72)을 받았다. 그
보고의 핵심 발견: **양 구현의 계약 병렬에 남은 차이 8항목은 전부 예약(reserve/unreserve)
계열**이었다. C046 브리핑의 "Go 56/56 + 라운드 8 = 72" 계산은 Go에 예약이 이미 있다는
잘못된 가정을 깔고 있었고, 나는 우회하지 않고 분석에 그대로 기록했다. 이번 사이클은 그
기록이 소환자(Clew)의 다음 재료가 되어 돌아온 것이다 — 씨실은 자기가 건너뛴 자리로
돌아온다.

또 하나의 교훈(C036의 재확인): **판정기가 안 보는 계약은 없는 계약이다.** Go는 지금
reserve를 훅에 나열하지 않으므로 판정기가 HELP-COMPLETE 게이트에서 "Go가 정직하게 부재
보고(exit 3)하는가"만 보고 8항목을 건너뛴다. 그래서 Go는 65/73이 아니라 65/**65**로 뜬다.
reserve를 구현하고 명령 표면(help + gil:commands)에 올리는 순간, 그 8항목이 Go에게 실제로
실행되기 시작한다.

## 문제 분할

빠진 8항목: `RESERVE-BASIC`, `RESERVE-NEEDS-FOR`, `RESERVE-NEEDS-CHAIN`,
`OPEN-SKIPS-RESERVED`, `OPEN-PROMOTES-OWNER`, `RESERVE-NON-INVASIVE`, `RESERVE-IN-LOG`,
`UNRESERVE`. 이식할 세 조각(계약: SPEC §6.7 번호 예약 규율 · §3.2 출처 계약):

1. `gil reserve <chain> <slug> --for <author>` — 체인 최상위 `reservations.tsv`에
   `<번호> <for> <slug> <일자>` 선점. --for 필수(없으면 거부·무변화). --git/--push/--root/--date.
2. `gil unreserve <chain> <번호>` — 예약 제거. 없는 번호는 거부.
3. `gil open`의 예약 인식 — 남의 예약 번호는 건너뛰고(선점), 예약자가 열면 자기 예약(최저
   번호)으로 승격 + 원장 소거. `log`는 예약을 그래프 밖 별도 섹션으로 표시.

## 가설

> **가설**: 참조 구현(gil.py)의 reserve/unreserve/open-예약인식 세 조각을 Go(go/main.go)에
> 문면 그대로 이식하면, Go는 무수정 conformance에서 65/65 → **73/73**이 되고 참조 구현의
> 회귀는 0이다. 예약은 사이클이 아니므로 fsck·verify·log 그래프·web 그래프의 record가 되지
> 않으며, 무예약 저장소의 web/log 출력은 참조와 **바이트 동일**을 유지한다.

## 기각 조건

- Go가 73/73에 도달하지 못한다(예약 8항목 중 하나라도 FAIL).
- 참조 구현 conformance가 73 미만으로 떨어진다(회귀).
- 무예약 저장소의 Go web 또는 log가 참조와 바이트 다르다(예약이 비침습적이지 않다).
