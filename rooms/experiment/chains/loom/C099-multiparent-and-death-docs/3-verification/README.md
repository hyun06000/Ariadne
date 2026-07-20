# 3. 가설 검증

세 갈래 how-to를 순수 문서 파일 3개에 명문화하고, 문서 주장이 실동작과 일치하는지 실행으로 대조했다.

## 바꾼 문서 (코드 0 — Sheen 병렬 작업과 파일 무충돌)

- **README.ai.md:102** (LLM 직독, 핵심): 오도 정정 + 4항목 불릿 — ① 부모는 닫혀야(C097), ② 병합=`--parent` 반복→`[A,B]`, ③ **lineage는 다른 체인 전용**(같은 체인 둘째 부모는 `--parent`), ④ 죽은 가지=`close --verdict rejected`(step 보존, withdraw와 경계).
- **SPEC.md**: ① O-table에 **O6**(부모 닫힘 게이트) 추가, ② O-table 뒤 "다중부모와 lineage의 구별" 문단, ③ **R9**에 rejected 예외 명시, ④ verdict 절에 "죽은 가지를 그래프에 각인(v2.46)" 문단.
- **QUICKSTART.md**: `--parent` 예제 뒤 병합 워크드 블록 + 부모 닫힘 노트 + rejected close 노트.

## 재현 방법

```bash
# M2 — conformance (문서만 바꿔 128 유지)
cd rooms/deployment/ariadne-spec
python3 conformance.py --gil "python3 $(pwd)/gil.py" | tail -1

# M1 — 문서 주장 ↔ 실동작 대조 (저장소 루트에서)
cd -
GIL=rooms/deployment/ariadne-spec/gil.py
SB=/tmp/c099-verify; rm -rf $SB; ROOT=$SB/rooms/experiment/chains; mkdir -p $ROOT
python3 $GIL open demo a --new-chain --author fx --date 2026-01-01 --root $ROOT
printf '# 1\nx\n' > $ROOT/demo/C001-a/1-hypothesis.md
python3 $GIL close demo C001-a --verdict rejected --date 2026-01-01 --no-commit --root $ROOT   # M1-d: step 1 보존
python3 $GIL open demo b --new-root --author fx --date 2026-01-01 --root $ROOT
printf '# 1\nx\n' > $ROOT/demo/C002-b/1-hypothesis.md
python3 $GIL close demo C002-b --verdict rejected --date 2026-01-01 --no-commit --root $ROOT
python3 $GIL open demo merge --parent C001-a --parent C002-b --author fx --date 2026-01-02 --root $ROOT
grep '^parent:' $ROOT/demo/C003-merge/cycle.yaml    # M1-a: parent: [C001-a, C002-b]
python3 $GIL open demo openparent --parent C003-merge --author fx --date 2026-01-03 --root $ROOT  # C003 열림
python3 $GIL open demo child --parent C003-merge --author fx --date 2026-01-03 --root $ROOT       # M1-b: 거부(열린 부모)
python3 $GIL open demo x --parent C001-a --lineage demo/C002-b --author fx --date 2026-01-03 --root $ROOT  # M1-c: R3 거부
```

## 실행 기록

- 일시: 2026-07-20. 환경: darwin 25.5.0, Python 3. gil v2.46.0(main).
- **M1 문서↔실동작 대조 (전부 일치)**:
  - M1-a: `--parent C001-a --parent C002-b` → `parent: [C001-a, C002-b]` ✓ (병합 문서 주장 참)
  - M1-b: 열린 부모(C003-merge) 위 자식 open → `오류: 부모 'C003-merge'가 아직 닫히지 않았다 (status: open) …` ✓ (O6 주장 참)
  - M1-c: `--lineage demo/C002-b`(같은 체인) → `오류: … 같은 체인의 계보는 parent (R3)` ✓ (lineage 구별 주장 참)
  - M1-d: C001-a를 1/5에서 rejected close → `step: 1` 보존·status closed·verdict rejected ✓ (R9 예외 주장 참)
- **M2 conformance: 128/128 유지 ✓** (문서만 변경, 도구 무변경, 회귀 0).
- **M3 파일 범위: .md 3개만** (git status로 gil.py·main.go 변경 0 확인) — Sheen 병렬 워크트리(gil.py·main.go 수정 중)와 무충돌 ✓.
- **M4 오독 정정**: README.ai:102의 "둘째 조상은 --lineage" 유도를 제거하고, "같은 체인 둘째 부모는 --parent 반복, lineage는 다른 체인 전용"을 명시. C096 발견②의 근원(내가 심야에 밟은 오해의 출처)이 정정됨 ✓.
- 특이사항: M1-c 최초 시도에서 `--lineage`만 주니 O2(부모 누락)에 먼저 걸려 R3를 못 봤다 — `--parent`(닫힌 것)를 함께 줘야 R3 거부가 드러난다(검증 순서 함정, 재시도로 확인).
