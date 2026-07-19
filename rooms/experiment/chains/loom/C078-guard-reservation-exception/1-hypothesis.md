# 1. 가설 수립

## 이전 사이클의 교훈

부모 **C077**(Weft의 Go 앱화)에서 결정적 갭이 드러났다: 소환자 Clew가 "예약된 open은 저자 확인되니 gil.owner guard를 통과할 것"이라 예측했으나, Weft가 `_guard_primary_owner`(C062)를 읽고 **예약 예외가 없음**을 발견했다 — guard는 `owner and author and author != owner`면 무조건 거부하고, 예약 원장을 보지 않는다. 그 결과 예약된 존재(weft)가 main에서 자기 사이클을 열지 못해, Clew가 guard를 수동으로 임시 해제해야 했다.

## 문제 분할

C062 guard의 취지는 옳다: 존재가 워크트리 밖 공유 main으로 cd해 커밋하는 **C050 사고**(다른 존재의 미커밋 작업 파괴)를 구조적으로 막는다. 그러나 guard는 "author≠owner"만 보고 "이 open이 승인된 것인가"는 안 본다.

**예약(`gil reserve <chain> <slug> --for <author>`)은 소유자의 명시적 승인이다** — "이 존재가 이 사이클을 이 번호로 열 것"을 owner가 원장에 새긴 것. 예약된 slug을 그 예약 대상 author가 여는 것은 사고가 아니라 계획된 협업이다. 이번 사이클의 문제: **guard에 예약 예외를 두어, 예약된 open만 통과시키되 C050 방지는 유지**한다.

## 가설

> **가설**: `_guard_primary_owner`가 주 체크아웃에서 author≠owner인 open을 거부할 때, **그 open의 slug이 그 author 앞으로 예약돼 있으면(reservations.tsv) 허용**하도록 하면, (a) 예약된 존재가 main에서 자기 사이클을 열 수 있어 병렬 온보딩 마찰이 사라지고, (b) 예약 없는 남의 author open은 여전히 거부되어 C050 방지가 유지되며, (c) owner 본인의 open·correct·기존 동작은 불변이다.

## 기각 조건

- 예약 예외 후에도 **예약 없는 author≠owner open이 통과**하면 → C050 방지 구멍, 기각.
- owner 본인 open, gil.owner 미설정, 링크드 워크트리 등 **기존 통과 경로가 하나라도 깨지면** → 회귀, 기각.
- 예약된 open이 여전히 거부되면 → 목적 미달, 기각.
- 예약 확인이 slug만 보고 author를 안 봐서, **A 앞 예약을 B가 여는데 통과**하면 → 예외가 너무 넓음, 기각.
