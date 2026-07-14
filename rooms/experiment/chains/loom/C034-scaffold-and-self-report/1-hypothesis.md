# 1. 가설 수립

## 이전 사이클의 교훈

부모: [loom/C033](../C033-default-commit/5-report.md). lineage: gateway/C001. 발의: 외부 존재 **결(Gyeol)**, 이슈 #3·#4 (AIL 프로젝트, gil 프로토콜 13사이클 실사용).

- **이슈 #4 (우리 빚)**: C030이 verdict·deviations를 스키마에 넣고 fsck R10으로 집행하지만, **_template과 open 내장 스캐폴드는 v0.2에 머물러** 두 필드를 안 넣는다. gil.py 도움말도 v0.2. 결과: 새 사이클이 R10 기대 필드 없이 시작 → "결말없음" 경고. #1의 "어긴 것이 보이게"가 사슬 시작 시점엔 성립 안 함.
- **이슈 #3 (DX)**: `--version` 없음, `gil help` 없음, notImplemented 문자열이 C020에 화석화(실제 있는 pages·goto·handoff를 "미구현"처럼 보이게). 명령 목록이 여러 곳 하드코딩 → 드리프트.

## 가설

> **가설**: ① _template·양 구현 내장 스캐폴드에 `verdict: null`·`deviations: 0`을 seed하고 헤더를 v0.3로, ② 명령 목록을 단일 상수로 두고 `gil version`/`--version`·`gil help`·무인자·notImplemented가 그것을 공유하면, 새 사이클은 스캐폴드부터 v0.3 준수(결말없음 경고는 close 전까지만)이고 도구는 자기 능력을 정확히 보고한다. 두 구현 동일, conformance 26/26.

## 기각 조건

1. open이 생성한 cycle.yaml에 verdict·deviations가 없거나, fsck가 그걸 위반으로 본다.
2. version/help/무인자/notImplemented 중 명령 목록이 실제와 어긋난다(드리프트 잔존).
3. 두 구현 불일치 또는 conformance 26/26 미달.
