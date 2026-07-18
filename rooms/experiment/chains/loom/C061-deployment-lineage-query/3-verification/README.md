# 3. 가설 검증

`gil releases` — 배포 계보 조회 프리미티브의 검증. 전부 재현 가능하게 저장.

## 아티팩트

- `verify.sh` — 재현 스크립트 (저장소 어디서든 실행). 세 검증을 순서대로 수행.
- `output.txt` — `verify.sh`의 실제 출력 (이 커밋 시점).

## 재현 방법

```bash
bash verify.sh
```

환경: macOS(Darwin 25.5.0), Python 3.9, Go 1.23.4(`$HOME/goroot/go/bin`), GO111MODULE=off로 `go build main.go`.

## 검증 항목 (output.txt 대조)

1. **실저장소 스모크** — 이 저장소에서 `gil releases`가 48개 릴리스를 태그↔CHANGELOG 대조로 보고. `gil:releases 48 drift=0`(실저장소는 두 기록이 일치). `git status` 전후 동일 → **저장소 무변화(§7.2)**.
2. **drift 탐지** — 샌드박스에 v1.0.0(양쪽), v1.1.0(태그만), CHANGELOG-only v1.2.0, 그리고 `cycle/x/C001-y`(릴리스 아님)를 심음. 결과: 3릴리스, `drift=2`, `[·C]`/`[T·]`/`[TC]` 표식, cycle 태그 배제. `git tag -l`이 못 하는 대조.
3. **비-git/비저장소 우아화** — 저장소 아닌 디렉토리에서 exit 0, "태그 대조 생략 — CHANGELOG만" 안내. 크래시 없음(C052의 결).

## 회귀 (conformance, 절대경로 --gil)

- Python 참조: **79/79** (기존 78 + 신규 `RELEASE-LIST`).
- Go 바이너리: **78/78** (전 항목 PASS). `releases` 미이식이나 exit 3으로 정직히 부재 → `HELP-COMPLETE` PASS. 부분 구현은 합법, 거짓 보고만 불법(C043 리듬).
- FAIL 0. 회귀 0.

## 판정 근거 요약

H1 성립(두 기록 대조 조회·무변화·계보 무발명), H2 성립(`RELEASE-LIST` PASS·Go 정직한 부재). 기각 조건 어느 것도 발동하지 않음.
