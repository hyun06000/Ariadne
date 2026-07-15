# 1. 가설 수립

## 이전 사이클의 교훈

[loom/C045](../C045-round-first-class/5-report.md)가 참조 구현(gil.py)에 **라운드**(사이클 안의
(가설→검증) 반복을 사전등록 데이터로 만드는 것)를 이식했다: `gil round <chain> <id>
--open/--close/--list` 명령, cycle.yaml의 `rounds: N` 필드, fsck R15(사전등록 파일 존재·6-어휘
검증), log/web의 라운드 표시. 판정기(conformance.py)도 64→72항목으로 자랐다. 그런데 Go
구현(go/main.go)에는 `round`가 없다 — 판정기의 `if "round" in claimed:` 가드가 Go의 부재를 보고
라운드 블록(8항목) 전체를 건너뛰어, Go는 새 판정기에서도 여전히 옛 만점(56/56)에 머문다.
"판정기가 안 보는 계약은 없는 계약이다"(C036의 교훈)의 예방판 사례 — HELP-COMPLETE만이
Go가 `round`에 정직하게 exit 3을 내는지 판정한다.

## 문제 분할

이 사이클의 검증 대상은 다음 다섯 계약면으로 분할한다 (C045의 이식 지시를 그대로 따른다).
모두 한 사이클 안에서 함께 검증해야 conformance 판정 단위(round 블록)가 성립하므로 더 쪼개지
않는다:

1. `gil round <chain> <id> --open/--close/--list` — 사전등록(H1: hypothesis가 verification보다
   먼저 각인)·6-어휘 결말(H2: invalid-method·confounded 포함)·닫힌 사이클 불변 보호.
2. cycle.yaml `rounds: N` 필드 — round --open이 없으면 추가, 있으면 증가.
3. fsck R15 — rounds:N(N>1)이면 각 rounds/R{k}/hypothesis.md 존재 + round.yaml verdict가 6-어휘 안.
4. log/web 라운드 표시 — rounds>1일 때만 (무라운드 저장소는 바이트 동일).
5. `gil:commands` 훅에 `round` 편입 — 명령 테이블 단일 소스(§7.2)에 등록하면 자동 나열.

## 가설

> **가설**: 참조 구현(gil.py)의 `round` 명령·스키마 필드(`rounds`)·fsck 규칙(R15)·log/web
> 표시를 Go 바이너리(go/main.go)에 이식하면, 무수정 conformance(`--gil "<Go 바이너리>"`)에서
> ROUND-* 8항목이 전부 PASS로 전환되고, 무라운드 저장소(우리 실 저장소)에서 Go web과 참조
> web의 바이트 동일성(하위호환)은 그대로 보존된다.

## 기각 조건

- conformance `--gil "<Go 바이너리>"`가 72/72에 못 미치면 가설은 부분 기각이다.
- 무라운드 실저장소에서 Go web과 참조 web이 (이번 이식이 원인으로) 바이트 단위로 다르면
  하위호환 조건 위반으로 기각이다.
- round --open --git 커밋에 verification/이 포함되면(사전등록 순서 위반) 기각이다.
