# 3. 검증 — v3 사이클 상태 분류 + close 봉인

설계(2-design)의 `gilv3 v0.3`(cycle_state 분류기 + close 게이트 + cycle.yaml 봉인)을
세 트리 변형으로 검증한 산출물.

## 파일

- `gilv3.py` — v0.3. C005 복사 + `cycle_state`(in_progress/solved/multi_solution,
  산 잎 개수로 순수 계산) + close 게이트 + **cycle.yaml 봉인**(steps.yaml과 별개 층) +
  status 확장. `--verdict`/`--date`.
- `build-cases.sh` — 세 트리 변형(in-progress·solved·multi)을 gilv3 명령으로 생성.
- `measure.py` — M1(분류)·M2(게이트+봉인)·M3(무오염) 판정.
- `cases/` — 생성된 세 변형 (재현 산출물).

## 재현 방법

```bash
cd 3-verification
bash build-cases.sh      # 세 변형 생성
python3 measure.py       # M1·M2·M3
```

환경: Python 3 stdlib. macOS Darwin. 2026-07-21 실행, ALL PASS.

## 결과 (전부 PASS)

| 측정 | 기준 | 결과 |
|---|---|---|
| **M1** 상태 분류 (K1) | 세 변형이 in_progress/solved/multi_solution으로 정확 분류 | ✅ 3/3 |
| **M2** 게이트+봉인 (K2) | in_progress close 거부·cycle.yaml 미생성 / solved·multi 봉인 정확·multi 경고 | ✅ |
| **M3** 무오염 (K3) | 봉인 후 steps.yaml 필드 == C002 6개, 상태·verdict는 cycle.yaml에만 | ✅ |

## 실측 — 봉인 산출

```
solved/cycle.yaml:              multi/cycle.yaml:
  state: solved                   state: multi_solution
  verdict: supported              verdict: supported
  live_leaves: [s7]               live_leaves: [s4, s7]
  closed: 2026-07-21              closed: 2026-07-21
```
- `in-progress`는 close가 거부돼 cycle.yaml이 **안 생겼다**(게이트가 봉인을 막음).
- `multi_solution`은 닫히되 stderr 경고("여러 정답 중 선택은 새 사이클, 그리디").
- 세 변형 모두 steps.yaml은 6필드 그대로 — 봉인 메타는 cycle.yaml 별개 파일 층(K3 미발동).

## 핵심

**상태 분류기가 뿌리다**: `cycle_state`(산 잎 개수)가 close 게이트를 파생한다 — 별개
규칙 0. C002의 "모델이 명령을 강제한다"가 close 층에서도 성립. 봉인은 cycle.yaml 별개
층으로, C005의 "깃은 별개 층"에 "봉인도 별개 파일 층"을 더한다 — steps.yaml(논리 트리)은
어느 층도 안 오염시킨다.
