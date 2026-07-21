# 2. 실험 설계

가설(1-hypothesis): 스텝 메타를 git trailer로 각인하면 subject는 사람용으로 유지한 채 복원이 자연어 정규식이 아닌 trailer로 이뤄지고, C009와 동일 트리를 내면서 서술 문구 변화에 무관해진다.

## 설계 개요

C009 gilv3(=C006 v0.3 각인 함수) 각인 경로를 확장(gilv3 v0.5)해 스텝 메타를 **git trailer**로 커밋 본문에 각인한다. subject는 지금처럼 사람용 서술로 두되, **복원의 진실원은 trailer**로 옮긴다. 그리고 C009 rebuild를 trailer 기반으로 재작성(`rebuild_trailer.py`)해 동일 트리가 나옴을 확인하고, **서술 문구를 일부러 망가뜨려도** trailer 복원이 불변임을 실증한다(견고성 증거).

## trailer 스키마 (계약면)

각 스텝 커밋 본문에 각인:
```
gilv3 step: s7 analyze/backtrack          ← subject (사람용, 자유 서술)

Step-Id: s7                                ← trailer (기계용 계약)
Kind: analyze
Parent: s6
Outcome: backtrack
Backtrack-To: s1
```
- `Step-Id`: 노드 id (필수).
- `Kind`: define|hypothesis|verify|analyze (필수).
- `Parent`: 논리 부모 id — **핵심**. C009는 이걸 "시간순 직전 or 서술 from"으로 파생했으나, trailer는 **parent를 명시**해 순환 규칙 파싱 없이 직접 읽는다. 루트는 `Parent: null`.
- `Outcome`: analyze에만 (success|backtrack|fail).
- `Backtrack-To`: outcome=backtrack에만, 되돌아감 목적지.
open 커밋은 `Step-Id: s1`·`Kind: define`, close 커밋은 trailer 없음(봉인, 트리 무관).

**설계 판단 — Parent를 trailer에 명시**: C009는 parent를 순환 규칙 + 서술로 파생했다(정보 국소성). trailer는 parent를 직접 담아 **복원이 순환 규칙에 의존하지 않게** 한다 — 계약면이 자기완결(각 커밋이 자기 부모를 스스로 안다). 이는 C009 "정보 국소성"의 트레이드오프: 저장 정보는 늘지만(모든 커밋이 Parent 명시) 복원이 규칙 결합에서 풀린다. 이 사이클은 **견고성**을 위해 자기완결을 택한다.

## 절차

1. **gilv3 v0.5** (C009/C006 gilv3.py 복사 후 확장, 닫힌 사이클 원본 불변): `git_imprint`가 message 외에 **trailers dict**를 받아 커밋 본문에 `Key: Value` 줄로 붙인다. cmd_open/cmd_step/cmd_close가 각 스텝 메타를 trailer로 전달. append-only 계약(add+commit만)·`_assert_forward_only` 유지(C008).
2. **트리 각인** (build.sh): C012→C014 10노드 트리를 `--git`으로 임시 깃 저장소(메인 레포 밖)에 trailer 포함 각인.
3. **rebuild_trailer.py**: `git log --reverse --format=…%(trailers:key=Step-Id,valueonly)…`로 각 커밋의 trailer를 읽어 트리 복원. **subject 자연어 파싱 0** — 오직 trailer 키만.
4. **measure.py**:
   - **M1 (동형)**: trailer 복원 트리 == 원본 steps.yaml (노드·parent·backtrack·outcome). K1.
   - **M2 (subject 무오염)**: `git log --format=%s`가 사람용 서술만(trailer 미포함)이고, subject에서 `Step-Id:` 등이 안 샌다. K2.
   - **M3 (견고성 대조)**: subject를 **일부러 망가뜨린** 두 번째 각인(예: `(backtrack to s1)` → `(돌아감!!)` 자연어 변형)을 만들어, ① C009 자연어 rebuild는 **깨지고**(복원 실패 또는 트리 붕괴) ② trailer rebuild는 **불변**(동일 트리)임을 대조. K3의 결정적 증거.
   - **M4 (append-only 유지)**: trailer 각인 경로도 add·commit만(reset/amend/force 0), C008 `_assert_forward_only` 통과. K4.
   - **왕복**: trailer 복원 → steps.yaml 직렬화 == 원본 바이트.

## 준비물

- gilv3 v0.5 (C009/C006 복사 확장), rebuild_trailer.py, measure.py — 순수 stdlib.
- C008 built-steps.yaml (원본 진실원 대조 기준 — C012→C014 트리는 불변).
- C009 rebuild.py (자연어 복원 — M3 견고성 대조군).
- 임시 깃 저장소: 스크래치패드 (메인 레포 밖, C005 규율). git ≥ 2.55 (trailer valueonly 지원 확인됨).

## 측정 방법

| # | 측정 | 기각 조건 | PASS 기준 |
|---|---|---|---|
| M1 | trailer 복원 동형 + 왕복 | K1 | 복원 == 원본, 왕복 바이트 동일 |
| M2 | subject 무오염 | K2 | %s에 trailer 미포함, 서술 깨짐 0 |
| M3 | 견고성 대조 (서술 변조) | K3 | 자연어 rebuild 깨지고 trailer rebuild 불변 |
| M4 | append-only 유지 | K4 | 각인 add·commit만, forward-only 통과 |

네 측정 PASS면 supported (계약면이 구조로 승격). 하나라도 K 발동이면 rejected/partial.

## 사용자 컨펌

- 갈래(커밋 메시지를 계약면으로)는 상현님이 AskUserQuestion으로 선택. 세부 설계(trailer 스키마·견고성 대조)는 표준 절차라 추가 컨펌 불필요. 단 **Parent를 trailer에 명시**하는 판단(C009 정보 국소성과의 트레이드오프)은 보고서에 근거를 남긴다.

- [x] 컨펌 받음 (일자: 2026-07-21, 갈래 선택 = 커밋 메시지를 계약면으로)
