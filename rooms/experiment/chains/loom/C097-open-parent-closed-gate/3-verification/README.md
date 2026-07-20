# 3. 가설 검증

부모 닫힘 게이트를 참조 gil.py·Go main.go·conformance.py에 구현하고, 설계의 6측정을 실행했다.

## 구현 요약 (봉인된 소스: rooms/deployment/ariadne-spec/)

- **gil.py `cmd_open`**: parent 검증 루프에 `status_by_id` 맵 + 게이트 — 각 `--parent`의 status가 `"closed"`가 아니면 `ChainError`(사전 검증 블록 안이라 저장소 무변화). "closed"만 화이트리스트 → open·rejected 둘 다 부모 자격 없음.
- **go/main.go `cmdOpen`**: 동형 이식(`statusByID` 맵 + 동일 게이트, 바이트 동일 메시지).
- **conformance.py**: 신규 2항목 + 계약 변경에 따른 기존 픽스처 정합.
  - `OPEN-PARENT-CLOSED-GATE`: 열린 부모 `--parent` open → exit≠0 + snapshot 무변화.
  - `OPEN-PARENT-CLOSED-OK`: 닫힌 부모 `--parent` open → 성공(과잉거부 방어).
  - `_seal_closed` 헬퍼 신설(gil이 만든 열린 사이클을 fsck 통과 closed로 값싸게 봉인).
  - **계약 변경에 따른 기존 테스트 수정(C094 교훈 "계약 바꾸면 그 계약 검증 테스트도 바뀐다")**: OPEN-INCREMENT·GUARD-RESERVED-OK가 열린 사이클(C001-first-step·C001-mine)을 부모로 자식을 열던 것을 → 부모를 먼저 `_seal_closed`로 닫은 뒤 자식을 열도록. 이 둘의 원래 의도(번호 증가·예약 guard)는 부모 닫힘과 무관하므로 전제만 정정.

## 재현 방법

```bash
# 저장소 루트에서. gil은 PATH에 없어 python3로 호출.
cd rooms/deployment/ariadne-spec

# M4 — 참조 conformance (기대: 125/125, 회귀 0)
python3 conformance.py --gil "python3 $(pwd)/gil.py" | tail -1

# M6 — Go 빌드(공유 /tmp 경로 병렬 충돌 회피: 세션-로컬 격리, loomlight/C003 교훈) + conformance (기대: 107/107)
BUILDDIR=/tmp/gil-go-c097; rm -rf $BUILDDIR; mkdir -p $BUILDDIR
cp go/main.go $BUILDDIR/; ( cd $BUILDDIR && go mod init gilgo >/dev/null 2>&1 && go build -o gil . )
python3 conformance.py --gil "$BUILDDIR/gil" | tail -1

# M1·M5·M6 — 거부 실출력 (참조·Go 바이트 동일 메시지, 원인+대안 둘)
SB=/tmp/c097-msg; rm -rf $SB; ROOT=$SB/rooms/experiment/chains; mkdir -p $ROOT
python3 gil.py open demo alpha --new-chain --author fx --date 2026-01-01 --root $ROOT   # 부모: 열린 채로 둠
python3 gil.py open demo beta --parent C001-alpha --author fx --date 2026-01-02 --root $ROOT   # 거부 확인
$BUILDDIR/gil open demo beta --parent C001-alpha --author fx --date 2026-01-02 --root $ROOT     # Go도 거부
```

## 실행 기록

- 일시: 2026-07-20. 환경: darwin 25.5.0, Python 3, Go(homebrew /opt/homebrew/bin/go).
- **M4 참조 conformance: 125/125 ✔** (baseline 123 → +2 신규, `git stash`로 baseline 재확인).
- **M6 Go conformance: 107/107 ✔** (baseline 105 → +2, 회귀 0). 두 몸 한 계약 유지.
- **M1 게이트 작동**: 열린 부모(status: open) `--parent` open이 exit=1로 거부, OPEN-PARENT-CLOSED-GATE PASS.
- **M2 정상 흐름**: OPEN-PARENT-CLOSED-OK(닫힌 부모 자식)·OPEN-NEW-ROOT·OPEN-ROOT-EMPTY-CHAIN·OPEN-INCREMENT 전부 PASS — 위양성 0.
- **M3 원자성**: 두 신규 항목의 판정에 `snapshot(groot) == before` 포함, PASS = 거부 시 저장소 무변화 확인.
- **M5 메시지**: 참조·Go 모두 `부모 'C001-alpha'가 아직 닫히지 않았다 (status: open) — 열린 부모 위에 자식을 열 수 없다.` + 대안 두 줄. **참조↔Go 바이트 동일.**
- 특이사항: 초기 실행에서 내 픽스처 `write_cycle(status="closed")`가 `closed: null`을 남겨 fsck R8 위반 → 이후 테스트 오염(OPEN-INCREMENT·GUARD-RESERVED-OK 연쇄 FAIL). 원인은 게이트가 아니라 픽스처였고, `closed` 일자 채움 + 열린-부모 전제 정정으로 해소. **한 픽스처 결함이 다른 항목을 가리는 C093 리듬 재현.**
