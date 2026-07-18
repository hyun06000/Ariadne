# 3. 가설 검증

Go에 `gil web --hierarchy`를 이식한 뒤, 참조(gil.py)와 Go(main.go)의 위계 출력이
**바이트 동일**이고 기본 출력·conformance가 **회귀 0**임을 재현 가능하게 측정한다.

## 재현 방법

저장소 루트에서 (Go 툴체인 필요 — `$HOME/goroot/go/bin` 또는 PATH의 go1.23+):

```bash
bash rooms/experiment/chains/loomlight/C003-go-hierarchy-port/3-verification/verify.sh
# 전 측정 통과 시 종료 코드 0. Go 부재 시 종료 코드 2로 정직히 SKIP.
```

`verify.sh`가 하는 일: ① `go build -o gil-go main.go`(실측 빌드), ② 참조·Go의
`web --hierarchy` 산출물 `cmp`(M1), ③ 기본 출력 `cmp`(참조==Go, 그리고 변경 전 Go==변경 후 Go)(M2·M2b),
④ Go conformance(M3), ⑤ 위계 계약(외부 리소스 0·실행 JS 0·3단 구조 카운트 참조와 동수)(M4),
⑥ 임시 저장소에서 Go가 step 후 bake.hierarchy를 왕복 보존하는지(M5).

## 산출물

- `verify.sh` — 위 6측정을 실행하는 재현 스크립트.
- `sample-hierarchy-go-loomlight.html` — **Go 바이너리가 구운** loomlight 체인의 위계 뷰어 표본
  (작고 자기완결·JS 0). 참조가 구운 것과 바이트 동일함은 M1이 증명한다.

## 실행 기록

- 일시: 2026-07-19 · 환경: darwin/arm64(macOS), go1.23.4, Python 3.
- 결과(verify.sh 전체 통과):
  - BUILD-go: `go build main.go` rc0 (이 워크트리에서 실제로 빌드됨 — C002의 이월 사유 해소).
  - M1-hierarchy-byte-identical: 참조 == Go (전체 저장소 5체인·67사이클).
  - M2-default-byte-identical: 참조 == Go / M2b: 변경 전 Go == 변경 후 Go 기본 출력.
  - M3-go-conformance: 78/78 (변경 전과 동수 — 회귀 0).
  - M4: 외부 리소스 0 · script 1(application/json gil-data) · hchain 5=5 · hcycle 67=67 · hstep 335=335.
  - M5: 임시 저장소에서 Go `step` 후에도 위계 유지 + bake.hierarchy 보존.
- 특이사항: 검증 도중 공유 `/tmp/gil-go` 경로가 병렬 세션과 충돌해 스테일 바이너리를 잡는 사고를
  겪어, 세션-로컬 산출물 경로로 옮겨 재현성을 확보했다(verify.sh는 `mktemp -d`로 격리한다).
