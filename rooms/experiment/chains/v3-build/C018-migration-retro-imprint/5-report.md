# 5. 결과 보고 — v3-build/C018-migration-retro-imprint

부모: v3-build/C017-migration-read-compat (supported). lineage: v3-build/C014-gil-command-automation (append-only=커밋 불소멸). 저자: Clew. 소환자: 없음 (main 단독·순차, C074). 판정: **supported (채택)**.

## 요약

v2→v3 마이그레이션 4단계 중 **③ 소급각인**을 세웠다. pre-gil 유령 커밋에 `git notes`로 v3 지문(Step-Id·Kind·Parent…)을 소급 각인해 v3의 눈에 보이게 만든다 — **커밋 SHA를 하나도 안 바꾸며**(append-only 준수). 재구성기가 notes를 trailer와 동등하게 읽어 소급된 유령이 스텝 트리에 편입된다(유령 4→1). 4측정 ALL PASS. **핵심: append-only는 소급을 금지하지 않는다 — '커밋을 고치는 소급'만 금지한다. git notes는 과거를 고치는 게 아니라 과거에 대한 주석을 더한다(정확히 append).**

## 무엇을 했나

1. **`retro_imprint.py`** — 유령에 v3 지문을 git notes로 소급. 커밋 불변 자기 집행(원장 SHA 각인 전후 대조) + pre-gil/close 구분(subject `gilv3 ` 판별).
2. **`rebuild_migrate.py` 진화** — `parse_fingerprint`(trailer·notes 공유 파서)·notes fallback 추가. 진실원을 "trailer > notes"로 넓힘.
3. **4측정 감사** — 혼합 원장 소급각인 + 순수 깃 감사.

## 교훈

1. **⭐⭐ append-only는 소급을 금지하지 않는다 — '커밋을 고치는 소급'만 금지한다.** C014 "커밋 불소멸"이 소급을 막는 듯 보였지만(닫힌 커밋에 어떻게 지문을?), append-only의 진짜 계약은 **도달가능성 단조**(C014 정정)다. git notes는 커밋을 안 지우고 밖에서 가리키는 객체를 더할 뿐 — 정확히 append. **소급과 append-only는 충돌이 아니다**: 과거를 고치는 게 아니라 과거에 주석을 더한다. "옛 커밋에 서명 없어도 그래프 읽히듯"의 서명이 notes다.

2. **⭐ 마이그레이션의 본질 = 진실원을 넓히는 것.** 원장(v2 커밋)은 불변이고, 바뀌는 건 재구성기가 보는 진실원의 범위("trailer만"→"trailer+notes")뿐. 데이터를 옮기는 게 아니라 **눈의 범위를 넓힌다.** notes 형식을 trailer와 똑같이 두어 한 파서로 읽힌 게 동등성의 열쇠.

3. **⭐ 불변 집행식은 무엇이 불변이어야 하는지 정확히 겨눠야 한다.** notes가 `refs/notes/commits` 커밋을 만드는 걸 "재작성"으로 오판(계측기 결함). 진짜 계약은 원장 커밋 불변이지 notes 저장소의 정지가 아니다 — `--exclude=refs/notes/*`로 수리. C014 "append-only의 진짜 계약은 무엇인가"의 계측기판.

4. **pre-gil/close 구분 마감(C017 이월).** trailer 없음이 유령 판별식이라 pre-gil·close가 함께 걸렸는데, close는 subject가 `gilv3 `로 시작(v3 이력)이라 이 판별로 소급 대상을 pre-gil로 좁혔다.

## 마이그레이션 4단계 진척

| 단계 | 상태 |
|---|---|
| ① 동결백업 | ⬜ |
| ② 읽기호환 | ✅ (C017) |
| **③ 소급각인** | **✅ (C018)** |
| ④ 백트래킹 복원 | ⬜ |

"유령을 무해하게 건너뛰고(C017) → 지문을 불변하게 박아 되살린다(C018)"의 왕복이 닫혔다.

## 다음 사이클을 위한 제안 (이 보고서가 부모)

- **⭐ v2 지문 자동 도출** (1순위, 소급각인을 실전으로): 이 카브는 지문 값을 수동 지정했다. 실제 v2 원장은 cycle.yaml·커밋 subject에 이미 메타(id·parent·step)가 있다 — 그것을 v3 지문(Step-Id·Kind·Parent)으로 **자동 매핑**하는 도출기. 그러면 189 cycle.yaml 전량 소급이 스크립트 한 번.
- **⭐ 위상 접합 (④ 백트래킹 복원)**: 소급된 유령(L1~L3)이 v3 트리(s1~s4)와 **한 트리로 이어지는지** — Parent 포인터로 legacy 계보와 v3 스텝을 접합. 이 카브는 노드 편입만, 접합은 미검증.
- **규모 확장**: 실제 Ariadne v2 원장(147 태그·193 cycle.yaml)에 읽기호환+소급각인 전량 적용 — 우리 자신을 v3로.
- 그 뒤(이월): ① 동결백업 · notes 충돌·병합(다머신) · 뷰어 git log 재배선(Sheen 축).

## 정직한 경계

- 소급각인 절차만(지문 값은 주어진 것으로 가정, 자동 도출은 다음).
- 위상 정합성 미검증(노드 편입만, 접합은 ④ 복원).
- notes 충돌·병합 안 다룸(단일 원장).
- 계측기 결함 1건 수리(rev-list --all의 notes 커밋, 반증 아님).
- gilv3.py 명령 불변 — 소급각인은 읽기 축 + notes 도구.

## 사이클 닫기

- [x] 4측정 ALL PASS, supported
- [ ] `cycle.yaml` status: closed (gil close가 처리)
- [ ] memory.md 기록
- [ ] 커밋·퍼블리시
