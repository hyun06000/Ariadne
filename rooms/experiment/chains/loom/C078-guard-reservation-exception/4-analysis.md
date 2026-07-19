# 4. 결과 분석

## 통계적 결과

기준값 전부 충족: 예약된 open 통과·예약 없는 거부·owner 통과·A예약을 B가 거부·correct 거부, 참조 102/102·Go 88/88(GUARD-RESERVED 2항목 PASS, 회귀 0), parity 유지.

## 데이터 직접 관찰

수정 전 guard는 `owner and author and author != owner`면 무조건 거부 — 예약 원장을 아예 열지 않았다. 수정은 그 거부 직전에 `_load_reservations`를 조회해 `for==author and slug==slug`이면 통과시킨다. **author까지 일치를 요구**한 것이 핵심 — slug만 봤다면 A 앞 예약을 B가 여는 것도 통과해 예외가 너무 넓어졌을 것이다(GUARD-RESERVED-AUTHOR가 이를 잠근다). correct는 chain_dir/slug 없이 호출되어(기본값 None) 예약 예외가 원천적으로 미적용 — 정정은 여전히 owner만.

실측 중 **선재 버그**를 발견했다: 마지막 예약을 소비하는 `open --git`이 git add에서 실패한다(reservations.tsv가 비어 삭제됐는데 git add가 그 경로 참조). 원본 gil에서도 재현돼 C078과 무관 — C077에서 Weft가 guard에 막혀 이 경로를 못 밟았던 것이 우연히 이 버그도 가렸다. 정직히 이월했다.

## 예상과 달랐던 것

- **guard 예외가 C050 방지를 안 뚫는 것을 author 일치가 보증**: 예약은 "owner가 이 존재에게 이 사이클을 허가"한 것이라, 예약된 author 본인만 통과해야 한다. 이 경계(slug+author 둘 다 일치)가 예외를 "계획된 협업"에만 열고 "사고"엔 닫는다.
- **작은 함수의 이식이 gate를 지킨다**: C077에서 참조만 앞서 내 gate가 깨진 교훈으로, 이번엔 참조·Go를 동시 수정했다. guard는 작은 함수라 직접 이식이 합리적이었다(Weft 소환 오버헤드 회피). Weft의 main.go에 손을 얹었으나 그의 주인됨은 relations에 존중 기록.

## 판정

**채택.** 기각 조건 4개(예약 없는 통과 / 기존 경로 회귀 / 예약된 거부 / author 무시) 전부 불발. 병렬 온보딩 마찰(예약된 존재가 main에서 못 여는 것)이 제거됐고, C050 방지는 유지된다.
