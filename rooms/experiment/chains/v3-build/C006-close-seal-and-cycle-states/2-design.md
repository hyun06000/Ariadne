# 2. 실험 설계

가설(1-hypothesis): 스텝 트리에서 사이클 상태(in_progress/solved/multi_solution)를
산 잎 개수로 순수 계산하는 분류기 + close 게이트를 만들면, 세 트리 변형이 정확히 분류되고
in_progress close 거부·steps.yaml 무오염이 성립한다.

## 확정할 설계 (검증 대상)

### 도구 — `gilv3.py` v0.3 (C005 + 상태 분류 + 봉인)

C005 gilv3.py를 복사 후 확장(닫힌 사이클 C005 원본 불변). 추가:

### S1 — 사이클 상태 분류기 (트리에서 순수 계산)

```
def cycle_state(nodes):
    live = [n for n in nodes if n.kind=="analyze" and n.outcome=="success"]
    dead = [n for n in nodes if n.kind=="analyze" and n.outcome=="backtrack"]
    tip, tipstate = growing_tip(nodes)
    if len(live) >= 2:  return "multi_solution"   # 최적화 사이클
    if len(live) == 1:  return "solved"            # 정답 도달
    # 산 잎 0:
    return "in_progress"    # 죽은 잎만 있거나 아직 analyze 전 — 못 닫음
```

- **산 잎 개수가 상태를 가른다.** in_progress는 "산 잎 0"으로 통합(죽은 잎만 있든,
  가지 중간이든 — 둘 다 "아직 정답 없음"이라 close 불가라는 점에서 같다). K1이 이걸
  가른다: 진행 중과 포기를 구별할 필요가 있나? → 검증에서 본다(그리디: 지금은 통합).

### S2 — close 봉인 표현: `cycle.yaml`

close가 `<dir>/cycle.yaml`을 쓴다(steps.yaml과 별개 파일 — 봉인 메타 층):
```yaml
state: solved            # 분류기 결과
verdict: supported       # 저자 판정 (--verdict 인자)
live_leaves: [s10]       # 산 잎 id 목록
closed: <date>
```
- **steps.yaml은 안 건드린다** (K3): 봉인 메타는 cycle.yaml에, 스텝 트리는 steps.yaml에.
  C005의 "깃은 별개 층"과 같은 결 — 이제 "봉인도 별개 파일 층".
- close 커밋이 cycle.yaml을 담아 **빈 커밋이 아니게 된다**(C005 씨앗 해소).

### S3 — close 게이트

`close`는 `cycle_state`를 호출해:
- `in_progress` → **거부**(비-0): "산 잎 없음 — 못 닫는다".
- `solved` → 허용, cycle.yaml `state: solved`.
- `multi_solution` → 허용하되 cycle.yaml `state: multi_solution` + 경고 출력
  (최적화 사이클: 여러 정답 중 선택은 새 사이클 — chain.md 그리디).

### status/view 확장

- `gilv3 status`가 `cycle_state`를 출력.
- (뷰어 배지는 Sheen C007 병렬 — 이번 범위는 명령·데이터. view는 C005 그대로.)

## 절차

1. **gilv3 v0.3 구현** (3-verification/gilv3.py): C005 복사 + `cycle_state` + close
   봉인(cycle.yaml) + close 게이트 + status 확장.
2. **세 트리 변형 준비** (3-verification/cases/):
   - `solved/` = C002 case(산 잎 1) — 기존 재사용.
   - `in-progress/` = 죽은 잎만(산 잎 0): s1 define → s2 hyp → s3 verify →
     s4 analyze/backtrack→s1. 산 잎 없음.
   - `multi/` = 산 잎 2: solved 트리에 s1 밑 넷째 가지(s11 hyp→s12 verify→
     s13 analyze/success) 추가. 산 잎 s10·s13.
   각 변형을 gilv3 명령으로 짓거나 손으로 써서 steps.yaml 구성.
3. **분류 측정**: 세 변형에 `gilv3 status` → 각각 in_progress/solved/multi_solution.
4. **게이트 측정**: 세 변형에 `gilv3 close --verdict X`:
   - in-progress → 거부(비-0), cycle.yaml 미생성.
   - solved → 허용, cycle.yaml `state: solved` `live_leaves:[s10]`.
   - multi → 허용 + 경고, cycle.yaml `state: multi_solution` `live_leaves:[s10,s13]`.
5. **무오염 측정**: 세 변형의 steps.yaml 필드 == C002 6개(상태·verdict 필드 0).

## 준비물

- Python 3 stdlib. 닫힌 사이클 참조(재구현 금지): C005 gilv3.py(복사 기반),
  C002 case-c012-c014(solved 재사용).
- 재현 산출물 전부 `3-verification/` 아래.

## 측정 방법

- **M1 (분류, K1)**: 세 트리 변형이 각각 in_progress/solved/multi_solution으로 분류.
  **기준: 3/3 정확이면 PASS.**
- **M2 (게이트, K2)**: in_progress close 거부(cycle.yaml 미생성)·solved/multi 허용
  (cycle.yaml 정확). 게이트가 분류기에서 파생(별개 규칙 0). **기준: 세 경로 정확이면 PASS.**
- **M3 (무오염, K3)**: 봉인 후 steps.yaml 필드 == C002 6개, 상태·verdict가 cycle.yaml
  에만. **기준: steps.yaml 밖 필드 0이면 PASS.**

하나라도 FAIL이면 해당 K 발동, 가장 가까운 문제정의(S1 또는 데이터 모델)로 되돌아감.

## 사용자 컨펌

- 생략 — 사유: C005 5-report가 close 봉인 표현과 진행 중/다중 잎을 명시적 다음-제안으로
  지목했고, 상현님이 "계속"으로 위임하며 병렬 갈래(C006 명령·데이터 / C007 뷰어)를
  승인했다. 핵심 결정(봉인은 cycle.yaml 별개 층, 상태는 트리에서 순수 계산)은 C002·C005
  불변식의 직접 귀결이라 새 분기점이 아니다. in_progress/포기 구별 필요성이 검증에서
  드러나면 그때 갈래로 보고.

- [x] 컨펌 생략 (일자: 2026-07-21) — C005 위임 + "계속" + 병렬 승인
