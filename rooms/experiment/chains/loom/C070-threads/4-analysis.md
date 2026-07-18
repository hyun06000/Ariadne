# 4. 결과 분석

## 통계적 결과

| 측정 | 기준 | 결과 | 판정 |
|---|---|---|---|
| 참조 conformance | THREADS-\* 전부 PASS, 회귀 0 | 96/96 (90 기존 + 6) | ✔ |
| THREADS-JSON-SHAPE | 유효 JSON·키·exit0 | PASS | ✔ |
| THREADS-RESERVED | 미소비 예약 정확 | PASS | ✔ |
| THREADS-CONSUMED-EXCLUDED | 소비 예약 제외 | PASS | ✔ |
| THREADS-OPEN | open만, closed 제외 | PASS | ✔ |
| THREADS-OPEN-MATCHES-SCAN | threads==직접 스캔 | PASS | ✔ |
| THREADS-EMPTY | 빈 상태 정직 | PASS | ✔ |
| 변이(소비 필터 제거) | CONSUMED-EXCLUDED FAIL | 95/96 격추 | ✔ |
| fsck 회귀 | 위반 0 | 위반 0 | ✔ |

기각 조건 5건 전부 불성립: (1) 불일치 없음(OPEN-MATCHES-SCAN PASS), (2) 지어냄 없음(CONSUMED-EXCLUDED PASS), (3) 계약면 있음(JSON-SHAPE + 판정기가 집합을 봄), (4) 전체 스캔 강제 안 함(한 명령으로 반환), (5) 회귀 0.

## 데이터 직접 관찰

수치 뒤로 들어가 실제 출력을 봤다. 이 워크트리(clew/loom-threads)에서 `gil threads`:

```
⟳ 진행 중 병렬 사이클 (예약, 아직 안 거둬짐): 2
    loom/C071  → weft  (parallel-usage-proof)
    loom/C072  → selvage  (release-drift-gate)
◐ 열린 사이클 (진행 중, 이 체크아웃): 1
    loom/C070-threads  · clew  2/5
```

이 출력이 **세 가지를 동시에 실증**한다:
1. **소비 필터가 산다** — C070은 이 브랜치에서 open됐고(예약 소비), 그래서 `reserved`에 C070이 없다. 지어냄 방지가 실데이터에서 작동.
2. **병렬 가시성** — C071(weft)·C072(selvage)가 브랜치를 체크아웃하지 않고도 "진행 중 병렬"로 보인다. 상현님 요청("뭐가 병렬로 도나")의 직접 응답.
3. **관점 상대성** — 이 브랜치에선 C070이 open이지만, main에선 C070·C071·C072가 전부 미소비 예약으로 뜬다(main엔 open된 게 없으니). 즉 threads는 "이 체크아웃 기준 loose end"를 정직히 비춘다 — 오케스트레이터(main)와 작업자(워크트리)가 각자 맞는 그림을 본다.

`--json` 계약면도 같은 데이터를 `reserved`/`open`/`*_count`로 반환해 LLM이 파싱 없이 소비 가능.

## 예상과 달랐던 것

- **SPEC 표에 `show`가 없었다.** threads 행을 넣으려 §5 명령 표를 열었더니 부모 C059의 `show`도, `handoff`도 표에 없었다. 발견 경로(SPEC)에 문장이 없으면 기능이 잊힌다는 C069의 교훈이 바로 여기서 재연됐다 — 그래서 threads뿐 아니라 `show`도 같은 커밋에 넣어 짝을 복원했다. **판정기(HELP-COMPLETE)는 명령을 등록했지만 사람·LLM의 발견 경로(SPEC)는 뒤처졌다** — 계약과 온보딩은 다른 표면이고 둘 다 갱신해야 한다.
- **예약 원장이 병렬 관측성의 공짜 기반**이라는 점. 설계 때는 "reservations를 읽는다" 정도였는데, 실증에서 이것이 상현님의 "뷰어에 병렬이 안 잡힌다" 문제의 데이터 층 해답임이 분명해졌다 — 워크트리가 .git을 공유하기에 예약이 main에 살아 브랜치 없이 보인다.

## 판정

**채택 (supported).** 가설의 (a)~(d) 전부 충족: 한 명령으로 진행 중 병렬 + 열린 사이클을 전체 스캔 없이 얻고(a·d), 이 세션의 실제 병렬 상태를 정확히 비추며(b), open 집합이 직접 스캔과 일치하고(c), 판정기가 계약면을 관측·판정한다(회귀 0). 기각 조건 5건 전부 불성립.
