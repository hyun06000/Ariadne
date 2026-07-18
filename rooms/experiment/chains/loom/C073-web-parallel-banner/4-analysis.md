# 4. 결과 분석

## 통계적 결과

| 측정 | 기준 | 결과 | 판정 |
|---|---|---|---|
| WEB-PARALLEL-BANNER (참조·Go) | 예약0 부재·예약1 출현+표기 | 둘 다 PASS | ✔ |
| 참조 conformance | 회귀 0 | 98/98 | ✔ |
| Go conformance | 회귀 0 | 84/84 | ✔ |
| parity 3경우(무예약·예약위계·예약평면) | 바이트 동일 | 3/3 | ✔ |

기각 조건 4건 전부 불성립: (1) parity 붕괴 없음(3/3), (2) 바이트 오염 없음(예약0→div 부재, 예약1→출현), (3) 판정기가 출현/부재 관측, (4) 회귀 0.

## 데이터 직접 관찰

렌더된 배너 조각을 직접 봤다:
```html
<div class="parbanner" role="status"><span class="picon">⟳</span> 병렬 진행 중 (예약, 아직 안 거둬짐): <b>1</b><span class="pchip">demo/C005 → weft</span></div>
```
칩이 `chain/C0NN → author`로 정확히 예약을 비춘다. **이 세션에서 실제로 작동한 순간**: 4트랙 병렬 중 main의 `reservations.tsv`가 C070·C071·C072를 담고 있었으니, 그때 `gil web`을 구웠다면 배너가 "병렬 진행 중: 3 — loom/C070→clew, loom/C071→weft, loom/C072→selvage"를 상단에 띄웠을 것이다. threads가 CLI로 답한 것과 같은 데이터, 같은 진실 — 두 표면이 다른 이야기를 못 한다(C042). 지금은 넷 다 거둬져 예약 0 → 배너 부재(정직).

## 예상과 달랐던 것

- **데이터가 이미 전부 있었다.** 설계 때 "gil-data에 reservations를 넣어야 하나" 걱정했는데, `gil web`은 loom/C043부터 이미 reservations를 gil-data JSON·평면 카드에 싣고 있었다. 이번 사이클은 **계약을 한 줄도 안 늘리고**(WEB-PARALLEL-BANNER는 렌더 의도 증언일 뿐 gil-data는 불변) 상단 렌더만 더했다 — C070의 "없던 건 질의 표면"이 뷰어에선 "없던 건 상단 렌더"로 반복됐다.
- **배너 CSS는 항상, 배너 div는 조건부.** 예약 0이어도 `.parbanner` CSS 3규칙은 페이지에 있다(무해). 배너 div만 예약 유무로 토글 → 빈 상태에서 div 부재가 정확히 지켜진다. parity는 CSS·div 둘 다 두 구현이 동일해야 성립 → 둘 다 문자 단위 이식.

## 판정

**채택 (supported).** 가설 (a)~(d) 전부 충족: 뷰어만 보고 병렬 진행을 알고(a), 새 계약 0으로 렌더만 늘었으며(b), 예약 유무 모두 바이트 동일(c), 판정기가 출현/부재를 관측(d). 기각 조건 4건 불성립. 상현님의 "뷰어에 병렬이 안 잡힌다"가 threads(CLI)에 이어 뷰어에서도 풀렸다.
