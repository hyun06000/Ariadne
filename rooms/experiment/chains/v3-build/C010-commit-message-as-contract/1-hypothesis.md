# 1. 가설 수립

부모: v3-build/C009-reconstruct-tree-from-git-log (supported)

## 이전 사이클의 교훈

- **C009 (깃 로그로 트리 재구성)**: `git log`만으로 스텝 트리를 무손실 복원 가능 — 깃이 단일 진실원이 될 수 있고 steps.yaml은 파생 캐시. 그러나 복원(rebuild.py)이 **커밋 메시지의 자연어 서술**(`(backtrack to s1)`, `(new branch from s1 after backtrack)`)을 정규식으로 파싱하는 데 의존한다. C009 보고의 정직한 경계: *"서술 형식이 사실상 스키마다 — 서술 형식이 바뀌면 rebuild.py 정규식도 바뀌어야 한다."*
- **C008 (백트래킹=새 커밋)**: 깃=append-only 전진기록. 커밋 메시지가 각인의 표면.

## 문제 분할

"커밋 메시지를 계약면으로"를 가장 작은 단위로 분할하면:

1. **[이 사이클] 자연어 서술 → git trailer 스키마**: 되돌아감 정보를 subject 괄호 서술이 아니라 **git trailer**(`Backtrack-To: s1`·`Branch-From: s1`·`Kind: analyze`·`Outcome: backtrack`)로 각인한다. subject는 사람용으로 깨끗이 유지하고, 기계는 `git log --format=%(trailers:key=…)`로 파싱. 복원기가 정규식 대신 trailer 키를 읽으면 파싱이 견고해진다.
2. (이후) v3 fsck가 trailer를 계약으로 검증(필수 trailer 존재·값 정합) · trailer 스키마 문서화 · body까지 복원.

**첫 번째를 고른 이유**: 상현님이 지목했고, C009가 남긴 **정직한 경계를 갚는** 사이클이다. C009는 복원이 자연어에 결합돼 있음을 정직히 밝혔다. 이 사이클이 그 결합을 끊어 **계약면을 자연어에서 구조로 승격**한다 — 그래야 다음 v3 fsck가 "복원 트리 == 캐시"를 계약으로 검증할 수 있다(fsck의 선행 조건).

## 핵심 관찰 (재료 점검)

git 2.55에서 확인:
- `git commit -m "subject\n\nBacktrack-To: s1\nKind: analyze"` → trailer로 각인됨.
- `git log --format='%(trailers:key=Backtrack-To,valueonly)'` → `s1` 정확히 추출.
- `git log --format='%s'` → subject만(`gilv3 step: s7 analyze/backtrack`) 깨끗이.

즉 **한 커밋이 두 층을 담는다**: subject(사람용 서술) + trailer(기계용 계약). 이는 v2 원장이 커밋 메시지에 사이클 메타를 담던 것의 v3 스텝판이다.

## 가설

> **가설**: gilv3의 깃 각인을 확장해 스텝 메타(kind·outcome·parent·backtrack 목적지)를 **git trailer**로 각인하면 — subject는 사람용 서술로 유지한 채 — 복원기가 자연어 정규식이 아니라 `git log --format=%(trailers)`로 트리를 복원할 수 있고, 그 복원이 C009의 자연어 복원과 **동일한 트리**(위상 동형·왕복 바이트 동일)를 내면서 **파싱이 서술 문구 변화에 무관**해진다. 즉 계약면이 자연어에서 구조(trailer)로 승격되고, 복원의 견고성이 오른다.

## 기각 조건

- **K1**: trailer 기반 복원 트리가 원본 steps.yaml과 위상이 다르다 (계약 승격이 정보를 손실).
- **K2**: trailer 각인이 subject를 오염시킨다 — `%s`(subject)에 trailer가 새거나, 사람용 서술이 깨진다.
- **K3**: trailer 파싱이 자연어 정규식보다 견고하지 않다 — 서술 문구를 바꿔도 trailer 복원이 불변임을 보일 수 없다 (승격의 이득 없음).
- **K4**: trailer 각인이 C008의 append-only 계약을 깬다 — trailer를 넣느라 reset/amend/force가 필요하다.
