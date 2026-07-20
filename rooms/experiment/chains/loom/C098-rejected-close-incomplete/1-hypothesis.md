# 1. 가설 수립

## 이전 사이클의 교훈

부모는 C097(open 부모-닫힘 게이트, supported). C097은 잘못된 open을 **예방**했다 — 열린/rejected 부모 위에 자식을 못 열게. 그 5-report가 남긴 짝 카브가 이 사이클이다:

> (A2) 미완 step 사이클의 rejected close — 이번 게이트는 잘못된 open의 *예방*이고, A2는 정당히 죽일 미완 가지를 그래프에 남기는 *사후 기제*다. 이번 세션 C095를 "5/5 형식 진행 후 rejected close"로 우회했던 그 근본. R9 계약 변경이라 참조+Go+conformance+fsck 파급 — 상현님이 별도 사이클로 결정.

즉 이번 세션 심야에 C095(open, 1/5)를 죽일 때, `gil close`가 **닫힘=step5를 강제**해서(fsck R9 + close가 step을 5로 덮음 + 5-report.md 요구) "5/5 형식 진행 후 rejected close"라는 **우회**를 써야 했다. step 필드가 "1/5에서 죽었다"는 진실 대신 "5/5"라는 거짓을 담게 됐다. 이 우회의 근본을 없앤다.

## 문제 분할

죽은 가지를 그래프에 정직하게 남기려면 세 강제를 풀어야 한다(전부 "닫힘=완주=step5" 가정에 묶여 있다):

1. **fsck R9**: `status==closed and step!=5` → 위반. (gil.py 413)
2. **cmd_close의 step 덮어쓰기**: close가 `step: 5`를 강제로 씀. (gil.py ~3419)
3. **cmd_close의 5-report.md 요구**: 비어있지 않은 5-report.md가 없으면 거부. (gil.py ~3398)

셋 다 "정상적으로 완주해 채택되는 사이클"엔 옳다. 문제는 **rejected(죽은 가지)** 다 — 완주하지 못하고 죽는 게 정상인데, 완주를 강제당한다. 그래서 갈래는 **verdict**로 가른다: `rejected`일 때만 세 강제를 완화한다.

**상현님 결정(2026-07-20, AskUserQuestion)**:
- **R9 방향**: 죽은 시점 step **보존** — close가 rejected면 step을 5로 안 덮고, R9는 "closed+rejected면 step≠5 허용" 예외. C095는 "1/5에서 죽음"이 그래프에 남는다.
- **보고서**: 죽은 이유는 쓰게 하되 **유연하게** — rejected close는 5-report 강제를 풀되, "왜 죽었는가"를 어딘가(마지막 작성된 step 문서 or `--notes`) 남기게 한다.

## 가설

> **가설**: `gil close`에 `--verdict rejected` 경로를 두어 — ① step을 5로 덮지 않고 현재 값을 보존, ② 5-report.md 강제를 "마지막 작성된 step 문서가 실질 내용을 가질 것"으로 완화, ③ fsck R9를 "closed면 step5, 단 verdict=rejected면 1~5 허용"으로 개정 — 하면, 미완 step 사이클(예: 1/5)을 **step 진실을 왜곡하지 않고** rejected로 닫아 죽은 가지를 그래프에 각인할 수 있고, 정상(채택) 사이클의 완주 강제는 회귀 없이 유지될 것이다.

## 기각 조건

사전등록 kill 조건:

1. **미완 rejected close가 안 되면 기각**: step 1(또는 2~4) 사이클을 `--verdict rejected`로 닫는 것이 실패하거나, 닫은 뒤 fsck가 위반을 내면 기각.
2. **step 진실이 왜곡되면 기각**: rejected close 후 cycle.yaml의 step이 죽은 시점 값이 아니라 5로 바뀌면 기각.
3. **정상 완주 강제가 풀리면 기각(위양성 반대 방향)**: verdict가 rejected가 **아닌**(supported/partial/inconclusive) close가 step5·5-report 강제를 여전히 받지 않으면 기각. 즉 완화는 오직 rejected에만.
4. **죽은 이유가 아무데도 없이 닫히면 기각**: 5-report도 없고 마지막 step 문서도 스텁(미작성)인데 rejected close가 성공하면 기각 — 죽음도 이유는 남겨야 한다.
5. **회귀가 나면 기각**: 참조 conformance 총점이 현재(125) 미만이 되면 기각. (신규 항목이므로 총점 유지/증가.)
6. **두 몸 불일치면 기각**: Go parity 미달(Go 총점 유지+신규, 동일 행동) 시 기각.

## 범위 밖

- **C095·C096 재봉인 안 함**: 이미 rejected로 봉인됐고 닫힌 사이클은 불변(R4·R5). 이 기제는 **미래의** 미완 rejected close를 위한 것. C095의 "5/5 우회"는 역사로 남긴다.
- **withdraw와의 관계**: withdraw는 open 직후 전용(revert 충돌, C094 실증). rejected close는 임의 step에서 죽은 가지를 **각인**(그래프 보존). 둘은 다른 도구 — 이 사이클은 close만 건드린다.
