# 5. 결과 보고

## 요약

conformance의 v2 open 섹션을 실제로 제거했다(전진 삭제) — v2 open 10항목(OPEN-CREATE·INCREMENT·REJECT-SLUG·AUTHOR·PARENT·ROOT·GATE) + prov() 헬퍼를 삭제하고 v3 계약 3항목을 그 자리(초입)로 이동. 게이트 없이 crash하던 근원(line 330 `_seal_closed`)이 사라져 판정기가 open을 넘어 close까지 진행하고, **게이트 없이 40항목 PASS**(crash 때 0)·게이트 상속 시 **127/127**(137−10, 회귀 0). **가설 채택(supported)** — 버전리스의 실질 전진, 그리고 v2 결합이 두 겹(open 호출 + write_cycle 산출물)임이 드러나 다음 관문의 좌표가 찍혔다.

## 교훈

1. **⭐⭐ v2 결합은 두 겹이다 — open 호출 층 + write_cycle 산출물 층.** C033은 "v2 결합이 open보다 깊다"만 봤으나, C034가 그 깊이의 구조를 벗겼다: (1) **open 호출 층** — open 섹션이 `impl.run(..., "open", ...)` 후 파일 읽기(`_seal_closed`)로 crash. C034가 제거. (2) **write_cycle 산출물 층** — close 등이 write_cycle로 만든 v2 산출물(cycle.yaml·5-report)에 의존. 다음 crash원(line 619). **첫 겹을 벗기니 crash가 330→619로 밀렸다** — 전진 삭제는 겹을 하나씩 벗기는 것.

2. **⭐⭐ crash와 FAIL은 v2 결합의 강도 차이다.** 같은 v2 open 호출이라도 **결과를 파일 읽기로 바로 쓰면 crash**(open 섹션), **종료코드만 보면 FAIL**(예약·라운드 섹션). C034 후 게이트 없이 예약·라운드는 crash 아니라 정상 FAIL로 강등 — 판정기가 안 무너지고 진행하며 정직히 FAIL 보고. **게이트-독립 완성은 이 FAIL 항목들도 v3로 재작성**해야(crash 제거는 필요조건, 초록은 충분조건).

3. **⭐ 전진 삭제의 회계 정직 — 제거는 순감이 명시적이어야 회귀와 구별된다.** 137→127은 정확히 −10(제거한 v2 open 항목). v3 3항목은 이미 137에 셈됐고 이동만 했으니 순감 0. **"제거지 회귀 아님"을 명시적 회계로 증명** — 설명 안 되는 감소만 회귀다(C021 "잔여 정확한 회계 = 정합 증거"의 연장).

4. **⭐ 이동은 cut-paste가 아니라 재배선일 수 있다 — 그러나 여기선 경로 독립이라 공짜.** v3 3항목을 파일 끝(GUARD 뒤)에서 초입(open 자리)으로 옮겼는데 PASS 유지. v3 항목이 자기 `work` 하위 경로(`v3-write`·`v2-retire`)만 쓰고 앞 섹션 상태에 의존 안 해서 이동이 안전. C032·C033의 "판정 항목 독립"(loom/C012) 설계가 이동을 공짜로 만듦.

## 다음 사이클을 위한 제안

1. **⭐⭐ close 섹션 write_cycle 산출물 층 v3화 (다음 관문, C034가 찍은 좌표)** — line 619 crash원. close·step·verify 등이 write_cycle로 만드는 v2 산출물(cycle.yaml·5-report)을 v3 산출물(steps.yaml)로, 또는 그 섹션들을 v3 close/step 계약으로 재작성. v2 결합의 두 번째 겹.
2. **예약·라운드·open-git 섹션 v3 재작성** — 게이트 없이 FAIL인 항목들(OPEN-SKIPS-RESERVED·PROMOTES-OWNER·LAST-RESERVATION-GIT·ROUND-*·FSCK-R15). v2 open 호출을 v3로.
3. **GUARD 섹션 v3 이전** — C050 병렬 안전(v2 open 호출)을 v3 open에 guard 부착 + V3-GUARD-* 항목. 버전 무관 안전 존치.
4. **v3 쓰기 계약 확장** — step kind 순환·백트래킹·죽은 잎·close(산 잎 solved) 판정 항목. C032~C034는 open만.
5. **게이트 완전 제거 목표** — 위 2·3·4 완료 시 게이트 없이 초록 → GIL_V2_OPEN 게이트 자체를 제거해 완전 버전리스(gil open=v3, 은퇴 안내도 불요할 만큼 v2 흔적 소멸).

## 사이클 닫기

- [x] `cycle.yaml`의 `status: closed`, `closed: <일자>` 갱신 (gil close가 수행)
- [x] 존재의 방 `memory.md`에 이 사이클의 기억 기록
- [x] 커밋 및 퍼블리시
