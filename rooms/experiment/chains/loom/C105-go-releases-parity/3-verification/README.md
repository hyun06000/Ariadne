# 3. 가설 검증

이 디렉토리에 실험 실행에 사용된 **모든 것**이 저장된다: 코드, 스크립트, 입력 데이터(또는 그 출처와 해시), 실행 로그, 연산 결과, 생성된 아티팩트.

## 재현 방법

이식 대상은 워크트리의 `rooms/deployment/ariadne-spec/go/main.go`(cmdReleases 신설·clEntry.cycles·commandTable 등록·main dispatch), 판정기는 무수정 `conformance.py`, 계약은 `gil.py`.

```bash
SPEC=rooms/deployment/ariadne-spec

# 1) Go 빌드 (세션-로컬 격리 경로 — 공유 /tmp/gil-go 금지: 병렬 flaky, C060 함정)
( cd $SPEC/go && go build -o /tmp/gil-go-c105-weft main.go )

# 2) Go 판정 — DEPLOY-NAMESPACE PASS + RELEASE-LIST PASS + 회귀 0
python3 $SPEC/conformance.py --gil /tmp/gil-go-c105-weft        # → 116/117 (runs/go-conformance.txt)

# 3) 참조 무회귀 (releases는 참조에 이미 있으니 불변)
python3 $SPEC/conformance.py --gil "python3 $(pwd)/$SPEC/gil.py" # → 134/134 (runs/ref-conformance.txt)

# 4) 바이트 대조: 태그 v1.0.0(TC)·v1.1.0(T만)·cycle/*·deploy/art/1.0.0 + CHANGELOG(1.2.0 C만, 근거사이클) 심은 저장소
#    참조 vs Go의 releases stdout/stderr/exit 를 diff (runs/bytediff-*.stdout/.stderr)
#    git-부재 분기도 별도 대조 (runs/bytediff-nogit-*)
```

`runs/` 아티팩트:
- `go-conformance.txt` — Go 116/117 (DEPLOY-NAMESPACE·RELEASE-LIST PASS, WEB-DEPLOYMENTS만 FAIL — 선재·범위밖)
- `go-baseline-conformance.txt` — 이식 전 HEAD:main.go, 114/116 (DEPLOY-NAMESPACE FAIL, RELEASE-LIST는 help releases rc≠0로 미실행)
- `ref-conformance.txt` — 참조 134/134 (무회귀)
- `bytediff-{ref,go}.stdout|.stderr` — 태그+deploy태그+근거사이클 시나리오, stdout·stderr **바이트 동일**
- `bytediff-nogit-{ref,go}.stdout` — git 부재 분기, **바이트 동일**

## 실행 기록

- 실행 일시: 2026-07-21
- 환경: macOS Darwin 25.5.0, Go 1.26.5, Python 3.9+, git. 워크트리 `loom-go-releases-parity`, 브랜치 `weft/loom-go-releases-parity`.
- 특이사항:
  - **판정기가 걸어가 있었다(C017 재현)**: C103 시점 판정기는 115항목이었으나 현재는 116(Go 기준)/134(참조)로 성장. 총계 절대값이 아니라 회귀 0 + 목표 항목 PASS로 판정.
  - **RELEASE-LIST는 이식으로 새로 활성화됐다**: 판정기(line 1108)가 `impl.run("help","releases").returncode==0`을 게이트로 걸어, releases 미구현 바이너리에는 이 항목이 아예 실행되지 않는다. 이식 후 게이트가 열려 RELEASE-LIST가 나타나고 PASS — 그래서 Go 총계 분모가 116→117로 늘며 분자도 +2(DEPLOY-NAMESPACE + RELEASE-LIST). C050의 "gil:commands 훅에 등록해야 판정기가 본다"의 재현: 등록이 항목을 깨운다.
  - 첫 `gil step` push가 upstream 미설정으로 실패 → `--set-upstream`으로 해소(C046 선례: 권한 아닌 설정 누락). 이후 정상 push.
  - Go `parseChangelogReleases`에 `cycles`(근거 사이클) 필드가 빠져 있어 추가 — 이 델타 없이는 근거사이클이 있는 CHANGELOG에서 참조와 바이트 어긋남(근거사이클 줄이 note로 오분류)이 났을 것.
