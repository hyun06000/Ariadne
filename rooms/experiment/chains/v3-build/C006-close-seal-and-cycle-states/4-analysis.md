# 4. 결과 분석

## 통계적 결과

| 측정 | 기준 (2-design) | 결과 | 판정 |
|---|---|---|---|
| M1 상태 분류 (K1) | 세 변형 → in_progress/solved/multi_solution | 3/3 정확 | PASS |
| M2 게이트+봉인 (K2) | in_progress 거부·미봉인 / solved·multi 봉인·multi 경고 | 세 경로 정확 | PASS |
| M3 무오염 (K3) | steps.yaml 6필드, 상태·verdict는 cycle.yaml | 밖 필드 0 | PASS |

세 kill 조건(K1·K2·K3) 미발동.

## 데이터 직접 관찰

- **분류가 산 잎 개수 하나로 갈렸다**: multi 변형의 status가 `산 잎 ['s4', 's7']`을
  뱉고 상태를 `multi_solution`으로 판정했다. s4·s7 둘 다 `outcome=success`이고, 분류기는
  그 개수(2)만 봤다 — 트리 위상을 안 봐도 됐다. solved는 산 잎 1(s7), in-progress는 0.
  **상태는 "몇 개의 정답에 닿았나"의 순수 함수.**
- **게이트가 분류에서 그대로 나왔다**: `cmd_close`가 `cycle_state`를 부르고
  `in_progress`면 거부한다 — close 전용 규칙이 따로 없다. in-progress 케이스에서 rc≠0이고
  **cycle.yaml이 안 생겼다**(봉인 자체가 게이트 뒤에 있음). C005 M3("모델이 명령을
  강제")가 close 층에서 재확인.
- **봉인이 steps.yaml을 안 건드렸다**: solved/steps.yaml 첫 노드를 직접 보면 여전히
  6필드(id·kind·parent·outcome·backtrack·body). 상태·verdict·closed는 전부 cycle.yaml에.
  **두 파일이 두 층** — 논리 트리(steps.yaml) vs 봉인 메타(cycle.yaml). C005가 깃을 별개
  층으로 뒀듯, C006은 봉인을 별개 파일 층으로 뒀다.

## 예상과 달랐던 것

- **close가 이제 빈 커밋이 아니다**: C005에서 close는 `--allow-empty` 빈 봉인 커밋이었다.
  C006에서 close가 cycle.yaml을 쓰니 **각인할 내용이 생겨** `--allow-empty`가 불필요해졌다
  (git_imprint 호출에서 뺐다). C005의 씨앗("verdict를 파일로 남기면 빈 커밋 탈피")이 그대로
  해소됐다 — close는 이제 v2 gil의 close(cycle.yaml 갱신)와 같은 방향.
- **in_progress가 "죽은 잎만"과 "analyze 전"을 통합해도 문제없었다**(K1 우려 해소): 둘
  다 "산 잎 0 → 못 닫음"이라 close 게이트 관점에서 구별할 필요가 없었다. 포기(abandon)와
  진행 중을 나눌 필요는 이 검증에선 안 나왔다 — 나중에 "포기 상태"를 명시적으로 표시하고
  싶으면 그때 새 상태(씨앗). 지금은 그리디하게 통합.

## 판정

**채택 (supported).** 가설대로 산 잎 개수로 사이클 상태를 순수 계산하는 분류기 + close
게이트를 만드니, 세 트리 변형이 정확히 세 상태로 분류되고(M1), in_progress close가
거부되며(M2), 봉인이 cycle.yaml 별개 층으로 steps.yaml을 안 오염시켰다(M3). 세 kill
조건 미발동, 산 잎(이 사이클 자체가 solved) 도달 → 닫는다. 포기 상태·close 태그·다중
정답 선택 알고리즘은 정직히 이월.
