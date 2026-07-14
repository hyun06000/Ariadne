# 5. 결과 보고

## 요약

maru의 이슈 #1(verdict·deviations)을 스키마 v0.3으로 구현했다 — 결말과 사전등록 이탈이 이제 기계에 보인다. `gil close --verdict`, fsck R10(경고·유예), log 표시·집계, web 색. 참조 8/8 + Go 미러링(노드·집계 동일) + conformance 26/26 — **채택**. pre-registration의 가치("어긴 것이 보이게")가 도구에 새겨졌다.

## 교훈

1. **감사 가능성은 결말과 이탈의 구조화에서 온다**: [closed]만으로는 기각이 안 보이고, 산문 이탈은 fsck가 못 본다. verdict·deviations가 gil을 기록 도구에서 감사 가능한 기록 도구로 만들었다 — maru의 문장 그대로.
2. **평탄 계약을 지키는 분리**: 중첩 데이터(deviations 상세)는 별도 파일로, cycle.yaml엔 개수만. v0.2 파서 계약을 안 깨고 v0.3을 얹었다.
3. **경고의 신호/잡음 분리**: 이탈은 개별 강조, 결말없음은 요약 — 유예하면서도 감사 신호를 살렸다.
4. 외부 사용자(maru)의 실사용이 우리 체인의 부모가 됐다 — gateway가 연 관문의 첫 열매가 loom을 성장시켰다.

## 다음 사이클을 위한 제안

- **(A) 이슈 #2 — web 레인 레이아웃** (추천, 즉시): 형제 갈래를 세로 레인으로 분리 + rejected 흐리게. #1의 --rejected 색과 합류해 "뷰어가 서사를 말하게".
- (B) 우리 34사이클에 verdict 소급 이주 ([migrate], 대부분 supported, genesis/C001 rejected).
- (C) Go 단독 완결(open --git·release) — 이월.

## 사이클 닫기

- [x] 기억 기록, `gil close --git --verdict supported`
