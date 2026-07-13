# 기대 행동 목록 (정답 고정)

> ⚠️ 이 문서는 **구현 전**에 고정되었다 (2026-07-14). 도구 행동에 맞춰 수정 금지.
> 샌드박스: `sandbox/rooms/experiment/` — `_template/` + `chains/seed/C001-origin`(닫힌 사이클, lineage 대상용).

## 정상 계열 — 성공해야 한다 (exit 0)

| id | 명령 | 기대 결과 |
|---|---|---|
| T1 | `open weave first-step --new-chain` | 체인 `weave` 생성 + `C001-first-step` 생성: cycle.yaml(v0.2 준수, parent null, opened=지정일, status open) + 템플릿 5스텝 문서 복사. 직후 fsck OK |
| T2 | `open weave second-step --parent C001-first-step` | `C002-second-step` 생성 — **번호 자동 증가**, parent 기록. fsck OK |
| T3 | `open weave with-roots --lineage seed/C001-origin` | `C003-with-roots` 생성, lineage 전역 참조 해소·기록. fsck OK |
| T4 | (T1의 5-report.md에 실제 내용 작성 후) `close weave C001-first-step` | status closed + closed 일자 기록, 나머지 필드·주석 보존. fsck OK |

## 거부 계열 — 거부해야 한다 (exit ≠ 0, **저장소 무변화**: 부분 생성물·파일 수정 없음)

| id | 명령 | 거부 사유 |
|---|---|---|
| T5 | `open weave v0.2` | 슬러그에 마침표 — R1 위반 예정 (C002에서 사람이 저지른 바로 그 실수) |
| T6 | `open weave x --parent C099-nope` | 유령 parent — R6 위반 예정 |
| T7 | `open weave y --lineage nowhere/C001-x` | 유령 lineage — R2 위반 예정 |
| T8 | `open ghost-chain z` (--new-chain 없이) | 존재하지 않는 체인 |
| T9 | `close weave C002-second-step` (보고서가 템플릿 그대로) | 미완성 사이클 — 보고서 없이 닫기 금지 |
| T10 | `close seed C001-origin` | 이미 닫힌 사이클 |
| T11 | `open weave w --lineage weave/C001-first-step` | 같은 체인 lineage — R3 위반 예정 |

## 판정 규칙

- 정상 계열: 명령 성공 + 명시된 산출물 확인 + 직후 fsck 위반 0건.
- 거부 계열: exit ≠ 0 + 명령 전후 저장소 파일 트리·내용 동일 (T9는 cycle.yaml 무변경 확인).
- 테스트는 각각 독립된 샌드박스 사본에서 실행한다.
