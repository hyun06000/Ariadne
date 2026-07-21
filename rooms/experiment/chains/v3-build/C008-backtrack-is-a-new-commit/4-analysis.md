# 4. 결과 분석 — 백트래킹=새 커밋

## 통계적 결과

5측정 ALL PASS, 네 기각 조건(K1~K4) 전부 미발동.

| # | 기준값 | 실측 | 판정 |
|---|---|---|---|
| M1 | 금지 git 명령 0 | reset/checkout/revert/amend/force/rebase = 0 (add·commit만) | ✅ K1 미발동 |
| M2 | 11커밋·시간순·선형·되돌림0 | 11, s번호 단조, 부모체인 선형, reflog 되돌림 0 | ✅ K2·K4 미발동 |
| M3 | 죽은 가지 전부 보존 | s4·s7 커밋·s2·s3·s5·s6 스텝·body 전부 생존 | ✅ K2 미발동 |
| M4 | 깃 선형 ∧ steps.yaml 트리 | 깃 머지0, steps.yaml s1 세 자식 + backtrack 2 | ✅ K3 미발동 |
| M5 | 가드가 뒤로 간 HEAD 거부 | 거부·복원 모두 True | ✅ 가드 유효 |

## 데이터 직접 관찰

수치 뒤로 들어가 `git-log.txt`와 `built-steps.yaml`을 직접 봤다.

**1) 백트래킹이 깃에서 선형 전진 커밋이다.** git-log.txt는 11줄 전부 `*`가 한 열에 정렬된 **단일 선형 그래프**다. s4(첫 백트래킹)와 s7(둘째 백트래킹) 커밋은 `analyze/backtrack (backtrack to s1)`로 각인됐지만, 그 직후 s5·s8(새 형제 가지의 hypothesis)의 깃 **부모는 s1이 아니라 직전 커밋(s4·s7)**이다. 되돌아감의 목적지(s1)는 깃 커밋 부모에 전혀 반영되지 않았다 — 오직 커밋 메시지 서술("new branch from s1")과 steps.yaml 포인터에만.

**2) 되돌아감의 진실은 오직 steps.yaml에 산다.** built-steps.yaml에서:
```
- id: s4  … outcome: backtrack  backtrack: s1
- id: s5  … parent: s1          (되돌아가 s1에서 난 새 형제)
- id: s7  … outcome: backtrack  backtrack: s1
- id: s8  … parent: s1
```
`s5.parent=s1`·`s8.parent=s1`이 세 형제 가지를 만든다. 깃 커밋 부모는 s5→s4, s8→s7(시간순 직전)인데, steps.yaml parent는 s5→s1, s8→s1(논리 트리). **같은 스텝이 깃에선 선형 이웃, steps.yaml에선 형제** — 두 층이 서로 다른 관계를 담고 안 섞인다.

**3) 벽의 지도가 지워지지 않았다.** s4·s7 백트래킹 커밋과 그 죽은 가지 전체(s2·s3·s5·s6 커밋, steps/s4.md·s7.md body)가 close 후에도 히스토리·워킹트리에 그대로다. 만약 백트래킹이 `git reset`이었다면 이 커밋들이 사라졌을 것이다 — M5 음성 대조가 바로 그 상황을 시뮬레이션해 가드가 잡음을 확인했다.

## 예상과 달랐던 것

- **가설이 이미 코드에 잠재해 있었다.** `git_imprint`는 C005부터 add+commit만 했으므로 백트래킹은 **이미** 새 커밋이었다. 이 사이클이 한 일은 새 기능이 아니라 **잠재된 성질을 명시 계약으로 승격**(`_assert_forward_only` 가드 + 계약 주석)하고 **실증**한 것. → *상현님이 세운 정신(깃=append-only)은 발명이 아니라 이미 참인 것의 명명이었다.* v2 원장의 append-only 정신이 v3 스텝 층에서 저절로 성립했다.
- **커밋 메시지 서술이 "벽의 지도"를 사람 눈에 띄게 만든다.** "new branch from s1 after backtrack" 서술 덕에 `git log`만 봐도 어디서 되돌아가 새 가지가 났는지 읽힌다. 단 이는 서술일 뿐 진실원이 아니다(steps.yaml이 진실원). 다음 사이클 씨앗: *깃 로그만으로 트리를 재구성할 수 있는가*(가설의 역방향) — 서술이 파싱 가능하니 가능해 보이나, 이는 별도 검증거리.
- **가드는 "일어날 일 없는" 것을 지킨다.** M5가 없었다면 M2 PASS는 "애초에 뒤로 갈 코드가 없어서"로 공허할 뻔했다. 음성 대조가 가드를 의미 있게 만든다 — *방어 계약은 그것이 막는 위반을 실제로 재현해봐야 살아있다.*

## 판정

**supported (채택).** 네 기각 조건 전부 미발동, 5측정 ALL PASS. 백트래킹=새 커밋이 코드로 성립하고, 깃(append-only 전진기록)과 gil(백트래킹·분기 지능)의 역할 분리가 실증됐다. 산 잎(s10) 도달 → 그리디하게 닫는다.
