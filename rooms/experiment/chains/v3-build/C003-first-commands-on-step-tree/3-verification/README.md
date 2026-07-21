# 3. 검증 — v3 첫 명령 (open/step/close)

설계(2-design)의 `gilv3` 명령 프로토타입을 실사례로 검증한 산출물.

## 파일

- `gilv3.py` — v3 명령 최소 프로토타입 (open/step/close/status). 순수 stdlib.
  **커서를 데이터에 저장하지 않고** 성장 팁을 트리에서 계산(C002 M3의 명령 층 실현).
- `rebuild-case.sh` — gilv3 명령만으로 C012→C013→C014 10노드 트리를 처음부터 짓는다.
- `guard-tests.sh` — 불법 전이 5종을 시도해 전부 거부되는지(양성 대조 1 포함).
- `built-case/` — rebuild-case.sh가 생성한 steps.yaml + steps/*.md (재현 산출물).

## 재현 방법

```bash
cd 3-verification
bash rebuild-case.sh            # 명령으로 트리 생성
# M1: C002 검증기 재사용
python3 ../../C002-design-v3-data-model/3-verification/roundtrip.py built-case/steps.yaml
bash guard-tests.sh            # M3: 전이 가드
```

환경: Python 3 stdlib만, bash. macOS Darwin. 2026-07-21 실행, 전부 PASS.

## 결과 (전부 PASS)

| 측정 | 기준 | 결과 |
|---|---|---|
| **M1** 명령 재현 (K1) | 명령이 지은 트리가 C002 roundtrip.py PASS | ✅ ALL PASS (왜곡0·무손실·파생) |
| **M1'** 위상 동형 | 명령생성 트리 == C002 손작성 트리 | ✅ 노드집합·엣지집합 동일 |
| **M2** 커서 무저장 (K2) | steps.yaml 필드 == C002 스키마 6개, 커서 0 | ✅ id·kind·parent·outcome·backtrack·body만 |
| **M3** 전이 강제 (E5) | 불법 전이 5종 전부 거부, 정상 1 허용 | ✅ PASS=6 FAIL=0 |

## 실행 기록

명령이 지은 트리:
```
s1(define) → s2·s3·s4(analyze/backtrack→s1)   가지1 C012 죽은 잎
           → s5·s6·s7(analyze/backtrack→s1)   가지2 C013 죽은 잎
           → s8·s9·s10(analyze/success)        가지3 C014 산 잎
```

**핵심 관찰**: `step` 명령은 어디에 이을지를 인자로 받지 않는다(직선 전이). 트리에서
성장 팁을 계산해 순환의 다음 kind만 허용한다. 죽은 잎 뒤에서만 `--to <ancestor-define>`로
새 형제 가지를 시작한다 — 이것이 backtrack이 명시적 데이터로 남는 유일한 지점. 세 kill
조건(K1·K2·K3) 미발동. C002의 "모델이 명령을 강제한다"가 **실제 실행 명령에서 성립**했다.
