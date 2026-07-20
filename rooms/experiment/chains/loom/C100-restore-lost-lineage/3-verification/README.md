# 3. 가설 검증

`gil correct`로 C018·C057의 잃은 부모를 병합 리스트로 복원했다. C041은 값 매칭 제약으로 이월.

## 실행 요약

- **C018** → `parent: [C016-number-ledger, C012-go-binary-log-fsck]` (evidence: 1-hypothesis.md:5 한 줄, 둘 다 대조).
- **C057** → `parent: [C056-windows-gate-runtime-verify, C053-windows-entry]` (evidence: 1-hypothesis.md 파일 전체).
- **C041 이월**: 2-design.md가 C035·C040을 번호(`C035`·`C040`)로만 적어 correct의 풀슬러그 문자 매칭 실패(C029만 풀슬러그). correct 확장(번호접두 매칭/다중 evidence)은 gil.py 수정 → Sheen 병렬 land 충돌 → 이월.
- **C043 제외**: 문서가 부모를 C042로만 명시(C015·C018·C037은 재발이력). 상현님 기준으로 불변.

## 재현 방법

```bash
# 저장소 루트. correct는 봉인(태그)·무결을 요구 → 실저장소에서 실행.
GIL=rooms/deployment/ariadne-spec/gil.py

# 안전: 복원 전 태그 기록
git rev-parse cycle/loom/C018-release-baseline cycle/loom/C057-deviations-count-reconcile

# C018 (한 줄 evidence)
python3 $GIL correct loom/C018-release-baseline \
  --field parent --to C016-number-ledger \
  --field parent --to C012-go-binary-log-fsck \
  --evidence 1-hypothesis.md:5 \
  --author clew --reason "C012 근원이 문서에 명시됐으나 단일부모로 봉인됨 (C096③)" \
  --date 2026-07-20 --no-web --push

# C057 (파일 전체 evidence)
python3 $GIL correct loom/C057-deviations-count-reconcile \
  --field parent --to C056-windows-gate-runtime-verify \
  --field parent --to C053-windows-entry \
  --evidence 1-hypothesis.md \
  --author clew --reason "C053 기원이 문서에 명시됐으나 단일부모로 봉인됨 (C096③)" \
  --date 2026-07-20 --no-web --push

python3 $GIL fsck rooms/experiment/chains | tail -2
python3 $GIL log rooms/experiment/chains --chain loom | grep -E "병합점|C018|C057"
```

## 실행 기록

- 일시: 2026-07-20. 환경: darwin 25.5.0, Python 3, gil v2.46.0(main).
- **M1·M2 복원 성공**: 두 correct 모두 exit 0, C5 증거 검사 통과(우회 없이 봉인본에서 값 문자 대조). parent가 `[A, B]`로. corrections.yaml 기록("거짓은 지워지지 않았다"), 태그 이동.
  - 값 매칭 관찰: parent 풀슬러그(`C016-number-ledger`)가 문서의 **경로**(`../C016-number-ledger/`) 안에 부분문자열로 존재해 C5 통과. memory의 "번호접두 vs 풀슬러그 미검"이 여기서 **풀슬러그는 경로 덕에 매칭됨**으로 판명 — 단 번호만 적힌 C041은 실패(제약 확인).
- **M3 fsck: 위반 0** (정정 경고 2건은 정상 — "색인은 수리됐고 거짓은 기록에 남았다").
- **M4 그래프**: `gil log`가 C018·C057을 `◀ 병합`으로, 새 병합점·분기점(C012→C018, C016→C018, C053→C057)을 렌더. `✎ corrected(1)` 표시. 잃은 계보가 그래프에 되살아남.
- **M5 C043 불변**: `parent: C042-viewer-follows-ledger` 그대로.
- **M6 Sheen 무충돌**: gil.py·main.go 변경 0 (원장 cycle.yaml + corrections.yaml만). 병렬 land 안전.
- **M7 conformance: 128/128 유지** (도구 무변경).
- 특이사항: `gil log`가 cwd 의존적이라 저장소 루트에서 `chains_root` 인자(또는 기본) + `--chain loom`으로 호출해야 함(C097 함정3 재현).
