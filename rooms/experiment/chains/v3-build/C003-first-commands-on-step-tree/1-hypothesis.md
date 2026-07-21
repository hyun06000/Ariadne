# 1. 가설 수립

## 이전 사이클의 교훈

부모: **v3-build/C002-design-v3-data-model** (supported). C002가 확정한 것:

- v3 스텝 노드 스키마 `STEP{id, kind, parent, outcome, backtrack, body}`. **불변식:
  `id`는 순수 시간순(커밋순), 트리는 오직 `parent`/`backtrack` 포인터가 담는다.**
- 디스크 표현: 사이클 디렉토리 안 `steps.yaml`(평면 인접 리스트) + `steps/<id>.md`.
- **명령이 관습 없이 파생됨** (C002 M3): kind 순환(define→hypothesis→verify→analyze)과
  analyze의 outcome(success/backtrack)이 다음 허용 행동(step/close/backtrack)을 유일하게
  결정한다. C002의 `roundtrip.py:derive_action`이 이걸 실제로 계산했다.
- C002는 **데이터를 손으로 써서** 검증했다(왕복). 실제 명령으로 트리를 짓는 것은 C003의 몫.

## 문제 분할

C003 "첫 명령 구현"을 가장 작은 단위로:

1. **E1 — `open`**: 빈 사이클을 만들고 루트 define(s1)을 심는다. steps.yaml 생성.
2. **E2 — `step`**: 현재 트리의 산 가지 끝에서 다음 허용 kind로 노드를 하나 잇는다.
   kind 순환을 강제(define→hypothesis→verify→analyze). analyze에서는 outcome 필요.
3. **E3 — `backtrack`**: analyze(outcome=backtrack)를 심고, 지정한 조상 define 밑에
   새 형제 가지가 자랄 수 있게 커서를 옮긴다. 죽은 잎을 남긴다.
4. **E4 — `close`**: 산 잎(analyze outcome=success)이 있으면 사이클을 닫는다.
5. **E5 — 명령이 스키마를 강제하는가**: 불법 전이(예: define 다음 바로 verify,
   analyze 없이 close)를 거부하는가.

**지금 정복할 첫 문제 = E1+E2+E4의 최소 골격 (open/step/close 직선 경로)**을 먼저.
이유: C002 M3가 이미 "트리→다음 행동"을 파생했으니, 그 역방향(명령→트리 생성)이
같은 상태기계를 쓰는지부터 확인해야 한다. backtrack(E3)은 직선이 서면 형제 가지로
확장하는 것이라, 직선 골격이 통과한 뒤에 붙인다(그리디). E5(강제)는 각 명령에
전이 가드로 자연히 들어간다.

## 가설

> **가설**: C002가 확정한 `steps.yaml` 표현 위에서 **`open`/`step`/`close` 세 명령을
> C002의 상태기계(kind 순환 + outcome 분기)를 전이 가드로 삼아 구현**하면, 그 명령들만으로
> 실사례 C012→C013→C014의 스텝 트리를 **처음부터 지을 수 있고**, 지어진 steps.yaml이
> C002의 `roundtrip.py`를 여전히 통과한다(왜곡 0·왕복 무손실·명령 파생).

## 기각 조건

- **K1**: 명령으로 지은 트리가 C002 손으로 쓴 트리와 다르다 — roundtrip.py가 FAIL하거나
  트리 위상이 어긋난다 (명령이 표현을 못 지킴 → E1/E2 재정의).
- **K2**: 상태기계를 전이 가드로 강제하려니 스키마 밖 추가 상태(예: 별도 커서 파일,
  명령 순서 관습)가 필요하다 — C002 M3의 "관습 0 파생"이 명령 층에서 깨진다
  (모델이 명령을 강제 못함 → 되돌아가 데이터 모델 재검토).
- **K3**: 직선(open/step/close)은 되나 backtrack 없이는 실사례를 못 담는다 — 직선 골격이
  실사례에 불충분 (E3를 이번 사이클에 끌어와야 → 범위 재정의).
