# 1. 가설 — lineage = 머지 = git merge --no-ff 를 도구가 강제한다

부모: v3-build/C014-gil-command-automation (supported — 백트래킹=checkout이 도구 동작이 됨).
lineage: v3-build/C012-merge-is-lineage (순수 깃으로 머지=lineage 원리 증명, 도구 미수정).

## 이전 사이클의 교훈

C012가 순수 깃(build_merge.sh)으로 증명한 명제: **lineage는 별도 필드가 아니라 깃 머지 커밋이다.** `parent: [C020, C016]`이 `git merge --no-ff`의 다중 부모와 동형. 그러나 C012는 gilv3.py를 안 고쳤다 — 원리만 증명하고 도구화는 "1순위 이월"로 넘겼다.

C014가 백트래킹=checkout을 도구 동작으로 만들며 **원리를 도구가 강제하는 첫 조각**을 세웠고, 정점 교훈으로 append-only의 진짜 계약이 "커밋 불소멸"(`_assert_append_only`)임을 확립했다. 머지도 커밋을 안 지우므로 이 집행기를 그대로 통과해야 한다.

## 문제 분할

C011 분기와 C012 합류는 한 커밋 DAG의 두 방향. C014가 분기(백트래킹=checkout)를 도구화했으니, 그 짝인 **합류(lineage=머지)** 를 도구화하는 것이 가장 작은 다음 단위다. 도구화 진척표: 스텝종결·위계 ✅ / 백트래킹=checkout ✅ / 잎=태그 ◐ / **lineage=머지 ⬜** / 뷰어 ⬜. lineage를 세우면 깃 ≅ gil의 도구 강제가 양방향으로 닫힌다. 잎=태그 정식화보다 lineage를 먼저 잡는 이유: 마이그레이션의 마지막 단계(백트래킹 복원 후 재합류)가 lineage 도구화를 선행조건으로 요구한다.

## 가설

> **가설(H1)**: `gilv3 close --lineage <sidA>,<sidB> --git` 이 각 산 잎 sid의 커밋을 부모로 하는 `git merge --no-ff` 다중부모 커밋을 각인하면, C012가 순수 깃으로 만든 병합 노드를 **생 git merge 호출 0으로** 도구가 재현한다.

- **H1a 다중부모:** 도구가 만든 close 머지 커밋의 깃 부모가 정확히 지정한 산 잎들(≥2). 부모 1개면 기각.
- **H1b trailer 계약:** 머지 커밋에 `Parent: <sidA>, <sidB>` · `Merge: lineage` · `Kind: merge` trailer가 각인돼, C010 복원이 lineage를 부모 지문만으로 읽는다.
- **H1c append-only 무위반:** 머지는 커밋을 안 지운다 → `_assert_append_only`(C014) 통과. 두 갈래 커밋 전부 도달가능 유지.
- **H3 회귀:** `--lineage` 없는 기존 `close`(단일 산 잎 봉인)는 C014와 완전히 동일.

## 기각 조건

- 도구가 만든 close 머지 커밋의 부모가 1개다(다중부모 실패 → lineage 안 담김). → H1a 기각.
- trailer 없이 머지되어 C010 rebuild가 두 계보를 못 읽는다. → H1b 기각.
- 머지가 `_assert_append_only`에 막히거나 두 갈래 커밋 중 하나라도 소멸. → H1c 기각.
- `--lineage` 없는 close 출력이 C014와 달라진다(회귀). → H3 기각.

## 검증 설계 (다음 스텝)

C012 build_merge.sh의 실증 표적(loom/C036 축약: 두 갈래 C016·C020 → 다중부모 C036)을 **gilv3 명령만으로** 재현. 두 갈래를 백트래킹 분기(C014)로 만들고 `close --lineage`로 합류.

- M1 다중부모 (H1a): close 머지 커밋 `%P`가 두 산 잎 커밋.
- M2 trailer 복원 (H1b): trailer가 lineage 담고 C010 rebuild가 읽음.
- M3 append-only (H1c): 머지 후 두 갈래 커밋 전부 생존, `_assert_append_only` 통과.
- M4 squash 음성대조 (H2): --squash 경로는 부모 1개 → 다중부모 실패(도구가 --no-ff 강제).
- M5 회귀 (H3): --lineage 없는 close가 C014와 바이트 동형.

## 정직한 범위 (선긋기)

- 2부모 머지 중심(C012 규모). 3+ 부모·중첩 머지·체인 간 머지는 이월.
- 머지 충돌 해소의 각인(C012 제안 "충돌=지식통합 판단면")은 밖 — 자동 병합되는 독립 파일 갈래로 한정.
- 잎=태그 정식화(브랜치 못→태그)는 C014의 ◐ 유지 — 이 사이클은 lineage에 집중(그리디).
