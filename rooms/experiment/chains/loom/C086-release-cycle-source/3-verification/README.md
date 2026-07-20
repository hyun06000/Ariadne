# 3. 가설 검증 — release --cycle 근거 사이클 계약화

## 재현 방법

```bash
# 임시 저장소에 닫힌 사이클 1 + 열린 사이클 1을 심고 T1~T4 재현
bash rooms/experiment/chains/loom/C086-release-cycle-source/3-verification/run.sh
```

conformance `RELEASE-CYCLE-SOURCE`는 `rooms/deployment/ariadne-spec/conformance.py`에 신설.
전체 러너는 이 환경에서 gil 미설치라 `--gil "python3 …"`(공백 인자)를 못 불러 baseline과 동일한 5개 무관 FAIL — 그래서 새 계약은 격리 재현으로 PASS를 확인했다(회귀 0).

## 결과

| 테스트 | 기대 | 결과 |
|---|---|---|
| T1 닫힌 --cycle | CHANGELOG 불릿 + 태그 메시지 + `releases`가 읽음 + 훅 `cycles=1` | PASS |
| T2 열린 --cycle | exit≠0, 트리·커밋·태그 무변화 | PASS |
| T3 없는 --cycle | exit≠0, 무변화 | PASS |
| T4 --cycle 무 | 종전 동작(근거 불릿 없음) | PASS |
| RELEASE-CYCLE-SOURCE | 위 셋 통합 계약 | PASS |
| 회귀 | baseline과 FAIL 동수(5, 무관) | 0 |

## 코드 변경 (gil.py)
- `_resolve_source_cycle(chains_root, ref)` 신설 — `<chain>/<id>`(디렉토리명/접두 모두) → (정규표기, status).
- `cmd_release` 사전 검증에 근거 사이클 게이트(닫힘 아니면 무변화 거부, drift·verify 게이트와 같은 위치).
- CHANGELOG 엔트리 `- 근거 사이클:` 불릿 + 태그 메시지 라인.
- `_parse_changelog_releases`가 `cycles` 키 파싱, `cmd_releases`가 렌더 `· 근거:` + 훅 `cycles=N`.
- argparse `--cycle`(append, 반복 가능).

Go parity: 참조 우선. Go는 release 부분 구현이라 CONTRACT_COMMANDS 정직 부재로 남김(C061 리듬 — 부분 구현 합법).

## 실행 기록
- 2026-07-20, darwin, Python 3. T1~T4 + RELEASE-CYCLE-SOURCE 격리 재현 전부 PASS. 문법 검사(ast.parse) 통과.
