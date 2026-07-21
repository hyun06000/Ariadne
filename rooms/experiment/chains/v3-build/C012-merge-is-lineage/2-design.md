# 2. 검증 설계

## 접근

C011이 build_branches.sh로 **분기(백트래킹=checkout+detached)** 를 순수 깃으로 실증했다. C012는 그 짝 — **합류(머지=lineage)** 를 순수 깃으로 실증한다. 같은 규율: 도구(gilv3.py) 안 고침, 순수 깃 명령으로 원리만, 산출물 재현 가능하게 3-verification/에.

## 실증 표적: loom/C036의 축약 재현

실제 사례 loom/C036은 `parent: [C020-go-web-port, C016-number-ledger]` — 두 계보의 지식을 통합한 병합 노드다. `gil log`가 이미 `◀ 병합: C020 + C016`으로 그린다. 이 위상을 **순수 깃 머지 커밋**으로 재현한다:

```
        C016 (number-ledger 계보) ──┐
                                     ├──▶ C036 (머지 커밋, 다중 부모)
        C020 (go-web-port 계보) ─────┘
```

즉 두 갈래(각각 자기 스텝 커밋을 쌓은)를 `git merge`로 합쳐, 다중부모 커밋을 만든다. 각 갈래는 실제 gil 사이클처럼 코드 아티팩트(artifact 파일)를 다르게 발전시키고, 머지 커밋이 **두 갈래의 기여를 실제로 통합**함을 보인다(이름뿐인 합류가 아님 — M4).

## build_merge.sh 설계

C011 build_branches.sh의 헬퍼(step·trailer 지문·1스텝=1커밋)를 계승하되, 핵심은 **명시적 머지**:

1. **체인 루트 s0** → **사이클 A 루트**(number-ledger 계보) 스텝 몇 개, 브랜치 `lane-C016`.
2. `git checkout s0` (분기) → **사이클 B 루트**(go-web-port 계보) 스텝 몇 개, 브랜치 `lane-C020`. C011이 증명한 detached 분기.
3. **합류**: 한 갈래에서 `git merge --no-ff <다른갈래>` → **다중부모 머지 커밋 C036**. `--no-ff` 필수(fast-forward로 접히면 다중부모 커밋이 안 생김 — M4 기각 조건). 머지 커밋 지문 trailer에 `Parent: C020, C016`(gil의 `[A, B]` 순서 보존)·`Merge: lineage` 각인.
4. 머지 커밋에서 통합 이후 스텝 계속 → 산 잎 → 태그(C011 계승).

**핵심 대조 — gil의 두 lineage 표현이 동형**:
- gil v2 표현: cycle.yaml `parent: [C020, C016]` (별도 필드) — loom/C001이 이 필드로 재구성 증명
- 깃 네이티브 표현(이 사이클): 머지 커밋의 두 부모 (필드 0, 깃이 담음)

## 측정 (measure_merge.py — 순수 깃 감사)

- **M1 — 다중부모 담김**: `git cat-file -p <머지커밋>`이 `parent` 줄 2개를 담고, 그 두 부모가 각각 C016·C020 갈래의 팁이다. trailer `Parent: C020, C016`이 깃 부모 순서와 대응한다. gil `[A,B]` ≅ git parents.
- **M2 — 그래프가 합류로 그림**: `git log --all --graph`가 C036에서 두 입력 엣지가 합쳐지는 병합 노드를 그린다. gil log `◀ 병합:` 표현과 위상 동형(입력 2, 출력 1).
- **M3 — 부모 지문만으로 lineage 재구성**: `git log --format=%H %P`(부모 해시)만 읽어(cycle.yaml·diff·show 0) lineage DAG를 복원 → 실제 위상(C036이 C016·C020 두 부모)과 동형. cycle.yaml 안 봄을 정적 감사로. C009(분기 재구성)의 합류판.
- **M4 — 실제 통합(이름뿐 아님)**: ① `git merge-base C016갈래 C020갈래`가 공통 조상(s0/사이클 루트)을 찾는다. ② 머지 커밋이 **두 갈래의 코드 기여를 모두** 담는다(각 갈래가 다른 파일/영역 수정 → 머지 후 둘 다 존재). ③ fast-forward 아닌 진짜 머지 커밋임(parent 2개). ④ **음성 대조**: `--squash` 머지(다중부모 안 만듦)는 lineage를 잃는다 — 부모 지문에 C020이 안 남아 M3 재구성이 합류를 놓침. → 다중부모 커밋이어야 lineage가 보존됨의 실물.

## 재현성

- build_merge.sh는 메인 레포 **밖** 스크래치에 임시 저장소를 만든다(C011과 동일, 메인 원장 무오염).
- measure_merge.py는 순수 깃 명령만 subprocess 호출(파이썬 파싱은 로컬). 결정적.
- measure-out.txt에 4측정 출력을 재현 가능하게 저장, git-graph.txt에 그래프 스냅샷.

## 성공 기준

M1~M4 ALL PASS → supported: **깃 머지 커밋(다중부모)이 gil lineage와 동형**, 깃 ≅ gil이 합류까지 닫힘. 하나라도 기각 → 가설 수정.
