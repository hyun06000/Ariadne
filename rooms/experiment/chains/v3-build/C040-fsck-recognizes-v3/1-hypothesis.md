# 1. 가설 수립

## 이전 사이클의 교훈

부모 **C039**(worktree add --v3). gil v3로 실사이클을 격리·병렬 수준에서 열 수 있게
됐으나 **세 경계**가 드러남: ①번호 중복 ②author/parent 소실 ③fsck v3 미인식. 셋 다
한 뿌리 — **v3 사이클(steps.yaml)이 v2 원장 모델(cycle.yaml 기반)에 미편입**.

C039가 찍은 가장 근본 좌표: **A. fsck·load_chain_records가 v3 사이클 인식**. 이게
풀려야 번호 중복도 위반으로 잡히고, 실사이클을 v3로 열어도 fsck 사각지대가 아니게 된다
(상현님 도그푸딩 전환의 전제).

## 문제 분할

**실측 — v3 네이티브 사이클은 원장 도구에 완전히 투명하다.** steps.yaml만 있는 v3
사이클을 만들고 `fsck` → "체인 1개, **사이클 0개**, 위반 0". `log` → 빈 출력. v3
사이클이 fsck·log·graph 전체에서 **존재하지 않는 것처럼** 취급. 원인: `load_chain_records`
(gil.py 84)가 `<entry>/cycle.yaml`만 수집 — steps.yaml은 레이더 밖.

**설계 갈래(v3 정체성 결정) — 세 길**:
- **길1 얇은 cycle.yaml**: v3 open이 steps.yaml + 최소 cycle.yaml 동시 생성 → fsck 기존
  로직 그대로 인식. 간단하나 "steps.yaml이 진실원"과 이중화.
- **길2 steps.yaml 수집**: load_chain_records가 steps.yaml도 record로 → v3 네이티브,
  하지만 fsck R규칙(cycle.yaml 필드: parent·status·closed…)이 v3 층에서 필드를 못 찾음.
- **길3 v3 전용 최소 검사**: fsck에 v3 사이클용 별도 무결성(루트 define 존재·번호 유일성·
  트리 정합)을 더함 → v2/v3 각자 무결성, 원장은 둘 다 인식.

이 갈래는 v3 사이클의 정체성 모델(진실원이 steps.yaml인가 notes인가 cycle.yaml인가)과
직결 → **설계 단계에서 상현님께 묻는다**(CLAUDE.md §3 "갈래가 나뉘는 지점"). 실측으로
세 길의 트레이드오프를 명확히 제시.

## 가설

> **가설**: fsck·load_chain_records가 v3 사이클(steps.yaml)을 인식하도록 확장하면,
> v3 네이티브 사이클이 원장 도구(fsck·log)에 "사이클 0개"가 아니라 실제 사이클로
> 나타나고, 번호 중복(C039의 병렬 충돌)이 무결성 위반으로 검출되며, 기존 v2 사이클
> 인식과 conformance(121/121)는 무회귀한다.

## 기각 조건

1. v3 인식을 더했을 때 기존 v2 사이클 수집이 깨지거나 conformance가 121/121 아래로 내려가면
   → v2 무회귀 실패(기각).
2. 선택한 길이 fsck R규칙과 근본 충돌해(v3에 없는 필드를 R규칙이 요구) 위반을 못 잡거나
   거짓 위반을 내면 → 그 길 부적합(기각·다른 길로).
3. v3 사이클 인식이 번호 중복을 여전히 못 잡으면 → 인식과 무결성 검사가 분리돼 목적
   미달(기각·검사 로직 보강).
