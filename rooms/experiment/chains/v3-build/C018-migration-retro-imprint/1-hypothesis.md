# 1. 가설 — git notes로 유령에 지문을 소급 각인한다 (커밋 불변)

부모: v3-build/C017-migration-read-compat (supported — v3의 눈이 유령을 무해·가시적으로 건너뜀).
lineage: v3-build/C014-gil-command-automation (append-only=커밋 불소멸 계약).

## 이전 사이클의 교훈

C017이 마이그레이션 4단계 중 **② 읽기호환**을 세웠다: v3 재구성기가 지문 없는 pre-gil 유령을 파괴 없이 건너뛰고, `--report`로 유령 수를 보고한다. 남은 유령을 0으로 만들려면 **③ 소급각인** — 유령에 v3 지문을 박아 v3의 눈에 보이게 — 이 다음이다.

C017이 봐둔 핵심 난점과 해법:
- **난점:** 닫힌 커밋은 불변이다. 커밋 메시지에 trailer를 넣으려면 amend/rebase가 필요한데 그건 **히스토리 재작성 = append-only 위반**(C014 `_assert_append_only`가 거부). 마이그레이션이 자기 원리에 자기가 막힌다.
- **해법 후보:** `git notes` — 커밋을 안 건드리고 별도 ref(`refs/notes/*`)에 메타를 첨부. 커밋 SHA 불변, append-only 완벽 준수.

## 문제 분할

마이그레이션 4단계: ①동결백업 → ②읽기호환(✅ C017) → **③소급각인** → ④백트래킹 복원.

**이번 카브 = 소급각인.** 가장 작은 단위로 더 쪼개면:
- (a) **각인 수단**: git notes가 커밋 불변으로 지문을 첨부하는가.
- (b) **재구성기 통합**: 재구성기가 trailer(v3 네이티브) + notes(소급된 유령) 둘 다 읽어, 소급된 유령이 더 이상 유령이 아니게 되는가.
- (c) **pre-gil vs close 구분**(C017 이월): close 커밋은 이미 v3라 소급 대상이 아니다 — pre-gil만 지문을 받는다.

세 조각이 한 카브다 — (a) 없이 (b)는 무의미하고, (b) 없이 (a)는 눈에 안 보이며, (c)는 무엇에 각인할지의 판별이다.

## 가설

> **가설(H1)**: 유령(pre-gil) 커밋에 `git notes`로 v3 지문(Step-Id·Kind·Parent…)을 소급 각인하고 재구성기가 notes를 trailer와 동등하게 읽으면, **커밋 SHA를 하나도 안 바꾸며(append-only 준수)** 소급된 유령이 v3 스텝 트리에 편입된다 — 유령 수가 소급한 만큼 줄어든다.

- **H1a 커밋 불변:** notes 각인 전후 모든 커밋 SHA가 동일. `rev-list --all` 불변. 히스토리 재작성 0(C014 계약 준수).
- **H1b notes=trailer 동등:** 재구성기가 notes의 지문을 커밋 trailer와 동등하게 읽어, 소급된 유령이 스텝 노드로 복원된다.
- **H1c 유령 감소:** 소급각인 후 `--report`의 유령 수가 소급한 pre-gil 수만큼 감소(전부 소급하면 pre-gil 유령 0, close 유령만 남음).
- **H1d pre-gil/close 구분:** close 커밋은 이미 v3(trailer 있음)라 소급 대상이 아님 — 소급각인이 close를 안 건드린다.

## 기각 조건

- notes 각인이 커밋 SHA를 바꾼다(= 히스토리 재작성). → H1a 기각(append-only 위반, 마이그레이션 실패).
- 재구성기가 notes를 못 읽어 소급 유령이 여전히 안 보인다. → H1b 기각.
- 소급각인 후에도 유령 수가 안 준다. → H1c 기각.
- 소급각인이 close(이미 v3) 커밋에 지문을 덮어써 오염. → H1d 기각.

## 검증 설계 (다음 스텝)

C017 혼합 원장(pre-gil 유령 3 + v3 트리)을 재사용. pre-gil 3개에 notes로 지문을 소급 각인 → 재구성기가 notes+trailer로 읽음.
- M1 커밋 불변(H1a): notes 각인 전후 rev-list --all·모든 SHA 동일.
- M2 notes=trailer(H1b): 소급된 유령이 스텝 노드로 복원, 지문 값이 notes와 일치.
- M3 유령 감소(H1c): 소급 후 `--report` 유령 수 = (원래 유령 − 소급 pre-gil). 전부 소급하면 close만 남음.
- M4 pre-gil/close 구분(H1d): 소급각인이 pre-gil만 대상, close 커밋 notes 없음(이미 v3).

## 정직한 범위 (선긋기)

- **소급각인만.** ④ 백트래킹 복원·①동결백업은 다음. 이 카브는 "notes로 지문을 불변하게 박고 재구성기가 읽는가".
- pre-gil 3개에 **수동/스크립트 소급**(각인 절차 실증). 실제 189 전량·지문 값을 어떻게 추론하는지(v2 cycle.yaml → v3 steps 매핑)는 규모 확장/별도 카브.
- notes 지문 값은 이 카브에서 **주어진 것으로 가정**(합리적 v3 지문 수동 지정). v2 메타에서 자동 도출은 다음.
- gilv3.py 명령 불변 — 소급각인은 재구성(읽기) 축 + notes 각인 도구. `git notes`는 깃 네이티브라 새 명령 최소.
