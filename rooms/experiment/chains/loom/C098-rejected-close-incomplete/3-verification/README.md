# 3. 가설 검증

rejected close의 세 완화(step 보존·5-report 완화·R9 예외)를 참조 gil.py·Go main.go·conformance.py에 구현하고, 설계의 7측정을 실행했다.

## 구현 요약 (봉인 소스: rooms/deployment/ariadne-spec/)

- **gil.py `cmd_close`**: verdict 선검증(로직 앞으로 당김) + `is_rejected` 플래그. rejected면 ① 5-report 강제 대신 `_step_written(cycle_dir, cur_step)`(현재 step 문서 실질작성) 요구, ② `step: 5` 덮어쓰기 스킵(죽은 시점 보존). verdict 중복 검증 제거.
- **gil.py fsck R9**: `status=="closed" and step!=5 and verdict!="rejected"` → 위반. rejected면 step 1~5 허용.
- **go/main.go `cmdClose`·R9**: 동형 이식(`isRejected`, `stepWritten` 재사용, R9 동일 조건).
- **conformance.py**: 신규 3항목.
  - `CLOSE-REJECTED-INCOMPLETE`: step1 사이클 rejected close → 성공 + `step: 1` 보존 + closed + verdict rejected.
  - `CLOSE-REJECTED-NEEDS-REASON`: 스텁 step만 있으면 rejected close 거부 + 무변화.
  - `CLOSE-NORMAL-STILL-STRICT`: verdict≠rejected면 미완 close 여전히 거부(완화는 rejected 전용).

## 재현 방법

```bash
cd rooms/deployment/ariadne-spec

# M5 — 참조 conformance (기대: 128/128)
python3 conformance.py --gil "python3 $(pwd)/gil.py" | tail -1

# M6 — Go 빌드(세션-로컬 격리) + conformance (기대: 110/110)
BUILDDIR=/tmp/gil-go-c098; rm -rf $BUILDDIR; mkdir -p $BUILDDIR
cp go/main.go $BUILDDIR/; ( cd $BUILDDIR && go mod init gilgo >/dev/null 2>&1 && go build -o gil . )
python3 conformance.py --gil "$BUILDDIR/gil" | tail -1

# M1·M2·M4·M7 — 실 시나리오 (참조·Go 동일 행동)
SB=/tmp/c098-real; rm -rf $SB; ROOT=$SB/rooms/experiment/chains; mkdir -p $ROOT
python3 gil.py open demo doomed --new-chain --author fx --date 2026-01-01 --root $ROOT
# (M4) 스텁 1-hypothesis로 rejected close → 거부(죽은 이유 없음)
python3 gil.py close demo C001-doomed --verdict rejected --date 2026-01-02 --no-commit --root $ROOT
# 죽은 이유 작성 후 재시도 → 성공, step 1 보존
printf '# 1. 가설\n## 왜 죽었는가\n부모 전제가 틀려 죽인다.\n' > $ROOT/demo/C001-doomed/1-hypothesis.md
python3 gil.py close demo C001-doomed --verdict rejected --date 2026-01-02 --no-commit --root $ROOT
grep -E 'status|step|verdict' $ROOT/demo/C001-doomed/cycle.yaml   # step: 1, closed, rejected
python3 gil.py fsck $ROOT | tail -1                                # 위반 0
```

## 실행 기록

- 일시: 2026-07-20. 환경: darwin 25.5.0, Python 3, Go /opt/homebrew/bin/go.
- **M5 참조: 128/128 ✔** (baseline 125 → +3).
- **M6 Go: 110/110 ✔** (baseline 107 → +3), 회귀 0. 두 몸 한 계약.
- **M1·M2·M7 실증**: step1 미완 사이클 rejected close 성공 → `step: 1` 보존(5로 안 덮음)·status closed·verdict rejected, **fsck 위반 0**(R9 예외 작동). 참조↔Go 바이트 동일 행동.
- **M3 (CLOSE-NORMAL-STILL-STRICT)**: supported로 미완 close는 여전히 5-report 요구·거부·무변화 — 완화는 rejected에만.
- **M4 (CLOSE-REJECTED-NEEDS-REASON)**: 스텁 1-hypothesis만 있는 사이클의 rejected close는 `rejected로 닫으려면 마지막 스텝(1) 문서에 죽은 이유를 남겨야 한다`로 거부 + 무변화. 죽음도 이유는 남긴다.
- 특이사항: open이 스캐폴딩한 1-hypothesis는 스텁이라, 실제로 rejected close하려면 죽은 이유를 먼저 써야 한다 — 실 시나리오가 이 게이트를 그대로 실증(설계 의도대로).
