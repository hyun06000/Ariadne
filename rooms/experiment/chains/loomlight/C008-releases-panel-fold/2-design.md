# 2. 실험 설계

## 정답 먼저: 기대 행동

렌더 변경(데이터 불변)이라 계약면은 gil-data가 아니라 **렌더 구조 + 회귀**. 기존 WEB-RELEASES는 데이터(releases 키)를 검사하므로 이 렌더 변경에 불변 → **회귀 가드로 충분**. 새 판정은 렌더 구조를 최소 확인.

| # | 확인 | 기대 |
|---|---|---|
| T1 | 최신 N개 항상 표시 | 릴리스 >5면 최신 5개는 `<details>` 밖(요약), 현재 버전 즉시 보임 |
| T2 | 나머지 접기 | 릴리스 >5면 나머지가 `<details>` 안, `<summary>`에 "이전 N개" |
| T3 | 소수 저장소 | 릴리스 ≤5면 details 없음(전부 보임) |
| T4 | 회귀 | WEB-RELEASES(데이터)·WEB-CYCLE-RELEASE·BEINGS 불변. JS 0(자기완결). |

conformance는 T4(WEB-RELEASES 데이터 불변)로 커버되고, T1~T3은 렌더라 "렌더는 계약 아님"(§7). 다만 상현님 피드백의 핵심(무거움 해소)이 실현됐는지 **실렌더 확인**으로 검증(65개 중 5개만 초기 표시).

## 설계 결정

### D1. N=5, `<details>`로 접기
- `_render_releases_panel`에서 entries를 최신순(이미 그러함)으로 받아 앞 5개는 `<li>` 직접, 나머지가 있으면 `<details class="relmore"><summary>이전 N개 릴리스</summary><ul>…</ul></details>`.
- 나머지 0개(≤5)면 details 안 냄 → 소수 저장소 기존과 동일.

### D2. JS 0 — 네이티브 `<details>`
- C065 아코디언과 같은 네이티브 HTML. 자기완결 계약(§7) 유지.

### D3. parity — Go 동형
- Go `renderReleasesPanel` 동형 수정. 정적 문자열이라 parity 공짜.

## 절차

1. 참조 `_render_releases_panel`: 앞 5 + 나머지 details. CSS(.relmore).
2. Go `renderReleasesPanel` 동형.
3. conformance: 기존 WEB-RELEASES 여전히 PASS(데이터 불변) 확인. 필요시 T1~T3 렌더 확인 추가(sandbox에 릴리스 6개 심어 details 출현/미출현).
4. 실렌더: 실저장소(65릴리스) → 초기 5개 + details. `--flat`·무릴리스 무영향. parity 바이트 동일.

## 측정 방법

- **성공**: 실저장소서 초기 표시 릴리스 5개(65 아님) + details 존재, 현재 버전 즉시 보임. 참조·Go 바이트 동일. WEB-RELEASES 등 회귀 0. JS 0.
- **기각**(1-hypothesis): 최신 가림 / 소수 저장소 details / JS 사용 / parity 깨짐 / 데이터 변경.

## 사용자 컨펌

상현님 피드백 + "접기/펼치기" 선택(AskUserQuestion).

- [x] 컨펌 받음 (일자: 2026-07-19)
