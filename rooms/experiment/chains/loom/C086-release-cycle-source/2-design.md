# 2. 실험 설계 — release --cycle 근거 사이클 계약화

## 설계 원칙

기존 `cmd_release`의 골격("사전 검증 전부 → 실행 → 무변화 롤백")을 재사용한다. 근거 사이클 검증은 **봉인 전 사전 검증** 단계에 얹고(drift·verify 게이트와 같은 위치), 기록은 **이미 파서가 읽는 두 자리**(CHANGELOG 불릿 + 태그 메시지)에 새겨 새 파서를 만들지 않는다.

## 절차

1. **argparse**: `p_rel.add_argument("--cycle", action="append", default=[], metavar="<chain>/<id>")` — 반복 가능, 없으면 빈 리스트(하위호환).
2. **사전 검증 (봉인 전, 저장소 무변화)**: 각 `--cycle` 값에 대해
   - 표기 검증: `<chain>/<id>` 전역 표기여야 함(아니면 ChainError).
   - 존재·닫힘 검증: `collect_cycles`(fsck가 쓰는 수집기)로 해당 사이클을 찾아 `status == "closed"` 확인. 없으면/열려 있으면 무변화로 거부("배포는 닫힌 사이클을 근거로만"). verdict가 rejected면 경고(#25는 rejected 배포 불가를 원하나, 그 게이트는 후속 카브 — 이 사이클은 "닫힘"까지만 하드).
3. **기록 (실행 단계)**: 근거 사이클이 있으면
   - **CHANGELOG 엔트리에 불릿 추가**: `- 근거 사이클: loom/C0XX, loom/C0YY` — `_parse_changelog_releases`가 읽도록.
   - **태그 메시지에 라인 추가**: 태그 annotation에 `근거 사이클: …` 포함.
4. **파서 확장**: `_parse_changelog_releases`가 `- 근거 사이클:` 불릿을 파싱해 엔트리에 `cycles` 키로. (도구 변경 불릿과 같은 방식.)
5. **조회 확장**: `cmd_releases`가 `cycles`를 사람 렌더에 표시하고, 기계 훅 `gil:release …`에 `cycles=<n>` 또는 목록을 추가.
6. **conformance**: `RELEASE-CYCLE-SOURCE` 신설 — ① `--cycle`에 닫힌 사이클 → CHANGELOG/태그에 기록되고 releases가 읽음 ② 열린/없는 사이클 → 무변화 거부 ③ `--cycle` 없는 릴리스는 종전대로(하위호환).
7. **Go parity**: 이 사이클은 참조(Python) 우선. Go는 `release`가 애초에 부분 구현이므로, `--cycle` 파싱/기록은 참조에 두고 Go는 CONTRACT_COMMANDS 정직 부재(HELP-COMPLETE)로 남긴다 — C061과 같은 리듬(부분 구현 합법).

## 준비물

- 정본 `rooms/deployment/ariadne-spec/gil.py`, `conformance.py`.
- 테스트 픽스처: 임시 저장소에 닫힌 사이클 1 + 열린 사이클 1.

## 측정 방법

- T1: `release … --cycle <닫힌>` → CHANGELOG에 `근거 사이클` 불릿 + 태그 메시지 포함 + `releases`가 그 사이클을 보고. PASS 기준: 셋 다.
- T2: `release … --cycle <열린>` → exit≠0, 저장소·태그 무변화(git status 무변). 
- T3: `release … --cycle <없는 id>` → exit≠0, 무변화.
- T4: `release …`(--cycle 무) → 종전 동작 바이트 동일(하위호환).
- T5: conformance RELEASE-CYCLE-SOURCE PASS, 회귀 0.

## 사용자 컨펌

- 발의: 박상현(이슈 #25). 첫 사이클 범위를 "release --cycle 근거 계약화"로 잡는 데 세션에서 합의(별도 deploy 축은 실증 신호 시 후속). 기록 자리를 CHANGELOG 불릿+태그로 정한 건 "새 파서를 만들지 않는다"(기존 파서 재사용) 원칙에 따른 설계 판단.

- [x] 컨펌 받음 (일자: 2026-07-20) — 범위·방향 합의 완료
