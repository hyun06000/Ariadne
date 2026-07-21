# 3. 검증 — 머지 = lineage = 지식 통합

순수 깃으로 loom/C036(`parent: [C020, C016]` 병합 노드)을 축약 재현해, **깃 머지 커밋(다중 부모)이 gil lineage와 동형**임을 4측정으로 판정한다. C011(분기)의 짝(합류).

## 재현

```bash
bash build_merge.sh        # 순수 깃으로 두 갈래 + --no-ff 머지 실사례 구성 (메인 레포 밖 스크래치)
python3 measure_merge.py   # 4측정 감사 (순수 깃 subprocess만)
```

기본 스크래치 경로는 세션 스크래치. 인자로 다른 경로 지정 가능(두 스크립트 동일 경로 써야 함).

## 산출물

- `build_merge.sh` — 실사례 빌더. 갈래 A(C016/ledger.py)·갈래 B(C020/web.py)를 s0에서 분기(C011 계승)해 각자 스텝 쌓고, `git merge --no-ff`로 다중부모 머지 커밋 C036 생성 → 통합 이후 스텝 → 산 잎 → 태그.
- `measure_merge.py` — 4측정 감사기.
- `measure-out.txt` — 측정 출력 (ALL PASS 4/4).
- `git-graph.txt` — `git log --all --graph` 스냅샷 (뷰어가 보는 것 — 합류 `|/` 실물).
- `example-merge-commit.txt` — 머지 커밋 `git cat-file -p` (부모 2줄 담김의 실물).
- `commit-index.txt` — 갈래 팁·머지 커밋 해시 기록.

## 4측정 (ALL PASS)

| 측정 | 무엇을 확인 | 결과 |
|---|---|---|
| **M1 다중부모 담김** | 머지 커밋이 부모 2개(=C016·C020 갈래 팁)를 담고, trailer `Parent: C020, C016`이 깃 부모 순서(첫 부모=C020=HEAD)와 대응. gil `[C020,C016]` ≅ git parents | PASS |
| **M2 그래프가 합류로 그림** | `git log --all --graph`가 머지 노드를 in-degree 2로 그림(전체 머지노드 1개). gil log `◀ 병합:`과 위상 동형. 뷰어 재구현 0 | PASS |
| **M3 부모 지문만으로 재구성** | `git log --format=%H %P`(부모 해시)만 읽어 lineage DAG 복원 → C036이 C016·C020 두 부모. cycle.yaml·diff·show 안 봄(정적 감사). C009(분기 재구성)의 합류판 | PASS |
| **M4 실제 통합(이름뿐 아님)** | ① merge-base가 공통조상 s0 찾음 ② 산 잎에 두 갈래 코드(ledger.py·web.py) 모두 존재 ③ 진짜 머지(부모2, ff 아님) ④ **음성대조: squash 머지는 부모 1개라 lineage 잃음** → 다중부모여야 통합 보존 | PASS |

## 계측기 결함 수리 (1건)

- **M4 음성대조 오염**: 초기 measure는 squash 대조 저장소를 `cp -r`로 만들어 **원본의 머지 커밋(cb05164)이 딸려와** squash 저장소에도 다중부모 커밋이 남았다(음성대조 무효, False). → 깨끗한 새 저장소에 두 갈래 팁만 `git fetch`(머지 커밋 미도달)해 squash하도록 수리. 이후 squash 커밋 부모=1, lineage 소실이 정확히 드러남. **가설 반증 아님 — 대조군 구성 버그였다.**

## 결론

**ALL PASS → supported.** 깃 머지 커밋의 다중 부모가 gil의 다중부모 lineage와 동형이다. 별도 lineage 필드 없이 깃이 지식 통합을 담고, 그래프가 그리며, 부모 지문만으로 재구성되고, 두 계보가 실제로 합류한다(squash로는 안 됨). **깃 ≅ gil이 분기(C011)·합류(C012) 양방향으로 닫혔다.**
