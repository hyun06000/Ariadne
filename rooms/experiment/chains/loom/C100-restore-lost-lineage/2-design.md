# 2. 실험 설계

가설: 봉인 문서가 증언하는 잃은 부모를 `gil correct`로 병합 부모 리스트로 복원한다.

## 사전 조사 결과 — 값 매칭 가능성 (설계를 가른 발견)

correct C5는 새 값(로컬 id 풀슬러그)이 evidence에 **문자 그대로** 있어야 통과한다. 각 대상의 풀슬러그가 문서에 부분문자열로 존재하는지 실측:

| 사이클 | 복원값 | evidence 후보 | 풀슬러그 존재? | 판정 |
|---|---|---|---|---|
| C018 | `[C016-number-ledger, C012-go-binary-log-fsck]` | 1-hypothesis.md:5 (한 줄) | 둘 다 있음(경로 `../C016-number-ledger/`·`../C012-go-binary-log-fsck/`) | **복원** |
| C057 | `[C056-windows-gate-runtime-verify, C053-windows-entry]` | 1-hypothesis.md (파일 전체) | 둘 다 있음 | **복원** |
| C041 | `[C040-…, C029-time-machine, C035-superseded-pointer]` | 2-design.md | **C029만** 풀슬러그, C040·C035는 `C040`·`C035` 번호만 | **이월** |

**C041은 이번에 못 한다**: 문서가 C035·C040을 번호(`C035`·`C040`)로만 적어 correct의 풀슬러그 문자 매칭이 안 된다. 이는 memory가 예견한 제약("번호접두 vs 풀슬러그 매칭 미검")의 실물이다. correct에 번호접두 매칭이나 다중 evidence를 더해야 하는데 **gil.py 수정 → Sheen 병렬 land와 충돌** → 정직히 이월(C036·C046 절제 리듬). 이번은 **C018·C057 2건만** 복원한다.

## 절차

각 사이클마다 correct C1(봉인)·C6(무결) 전제를 확인 후 정정. **--no-web**(뷰어 자동갱신 끔 — Sheen이 뷰어 코드 병렬수정 중이라 굽기 회피).

1. **C018 복원** (evidence = 한 줄):
   ```bash
   python3 gil.py correct loom/C018-release-baseline \
     --field parent --to C016-number-ledger \
     --field parent --to C012-go-binary-log-fsck \
     --evidence 1-hypothesis.md:5 \
     --author clew --reason "C012 근원이 문서에 명시됐으나 단일부모로 봉인됨 (다중부모 미사용, C096③)" \
     --date 2026-07-20 --no-web --push
   ```
   기대: `parent: [C016-number-ledger, C012-go-binary-log-fsck]`, 태그 이동, corrections.yaml 기록.

2. **C057 복원** (evidence = 파일 전체, 줄번호 생략):
   ```bash
   python3 gil.py correct loom/C057-deviations-count-reconcile \
     --field parent --to C056-windows-gate-runtime-verify \
     --field parent --to C053-windows-entry \
     --evidence 1-hypothesis.md \
     --author clew --reason "C053 기원이 문서에 명시됐으나 단일부모로 봉인됨 (C096③)" \
     --date 2026-07-20 --no-web --push
   ```

3. **각 정정 후 fsck** — R6(부모 존재)·R3(로컬 id)·전체 위반 0 확인.

4. **그래프 확인** — `gil log loom`에서 C018·C057이 병합점(`◀ 병합`)으로 나타나는지.

## 준비물

- gil v2.46.0. `python3 rooms/deployment/ariadne-spec/gil.py`. 저장소 루트에서 실행.
- correct는 봉인(태그)·무결을 요구 → 이 실저장소에서 실행(임시 재현 불가, 실제 태그 필요).
- **되돌림 안전장치**: 각 correct 전 `git rev-parse cycle/loom/<id>`로 태그 기록. 문제 시 되돌릴 수 있게.

## 측정 방법

| # | 측정 | 기준 |
|---|---|---|
| M1 | C018·C057 correct 성공 | exit 0, parent가 `[A, B]`로 (kill 1) |
| M2 | C5 증거 검사 통과 | 우회 없이 봉인본에서 값 대조 성공 (kill 1) |
| M3 | fsck | 정정 후 위반 0 (kill 2) |
| M4 | 그래프 | C018·C057이 병합점으로 렌더 |
| M5 | C043 불변 | 안 건드림 (kill 4) |
| M6 | Sheen 무충돌 | gil.py 변경 0, 원장·corrections만 (kill 5) |
| M7 | conformance | 128 유지 (도구 무변경) |

## 사용자 컨펌

- **복원 기준은 상현님이 C096에서 확정**("문서가 부모/근원/만난다로 명시한 것만"). C041 이월과 C043 제외는 그 기준의 직접 적용. C018·C057 2건 복원은 기준에 정확히 부합 → 추가 컨펌 불요(전권 위임 + "나머지 이어가자").

- [x] 컨펌 받음 (일자: 2026-07-20, C096 복원기준 + "이어가자"로 갈음)
