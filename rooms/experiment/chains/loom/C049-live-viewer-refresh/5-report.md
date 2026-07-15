# 5. 결과 보고 — 새로고침 없는 실시간 관찰 (발의: 박상현)

## 요약
`gil web --refresh N`을 신설해 뷰어에 `<meta http-equiv="refresh">`(JS 아닌 HTML 표준)를 넣고 bake에 기록했다. 이로써 C042 자동 재굽기(gil step마다 파일 갱신)와 맞물려 **새로고침 없는 실시간 관찰**이 완성된다. `--watch`(원장 감시 재생성)는 gil을 안 거치는 외부 변경용 별도 층. 양 구현, 참조 73/73·Go 65/65 회귀 0, 두 구현 바이트 동일, 하위호환. **채택(supported).**

## 교훈
1. **실시간은 있던 두 기능을 잇는 한 줄이었다.** 파일 갱신(C042)은 이미 있었고 빠진 건 브라우저 반영뿐. `--refresh`(meta) + **bake.refresh 기록**이 핵심 — bake가 없으면 gil step 재굽기가 meta를 잃어 실시간이 두 번째 리로드부터 죽는다. C042의 "산출물이 자기 생성 조건을 말한다"가 refresh에도 참(refresh도 생성 조건).
2. **JS 0줄 계약이 설계를 정제했다.** 실시간의 상식(폴링/WebSocket)을 계약이 막자, `<meta http-equiv="refresh">`라는 더 단순하고 자기완결적인 답이 나왔다. 제약이 답을 좁혀 줬다 — C005의 재현.
3. **핵심 계약과 편의를 분리했다.** `--refresh`(양 구현, conformance WEB-REFRESH)와 `--watch`(장기 실행, 편의)를 나눴다. 상현님 시나리오는 C042+--refresh로 충분하고, --watch는 외부 변경(병합·pull) 관찰용 추가 층.

## 다음 사이클을 위한 제안
- **(A) Go reserve/unreserve 이식(Weft) → 72/72(그쪽 계약면) 완성** — C046이 남긴 목표.
- **(B) 판정기가 안 보는 계약 일괄** — fsck 문면(C044·C046) + Go log summarize(C046).
- **(C) 레인 가로 압축** — C048이 형제를 260px 벌렸으니, 형제 많으면 가로가 길다. 죽은 레인 col 재사용.
- **(D) 이슈 #9·#10 답글**(승인 대기).

## 사이클 닫기
- [x] --refresh/--watch 양 구현, WEB-REFRESH, H1~H4, 회귀 0, 두 구현 동일
- [ ] close --verdict supported / 릴리스(마이너) / memory
