# 3. 검증 — refresh 기본화

`gil()` = `python3 rooms/deployment/ariadne-spec/gil.py`.
gil이 PATH 미설치라 conformance 전체 러너는 `--gil "python3 …"`(공백 인자)를 못 불러 5개 무관 FAIL이 baseline과 동일(회귀 0). 아래는 직접 재현.

| 테스트 | 명령 | 기대 | 결과 |
|---|---|---|---|
| T1 기본 실시간 | `gil web` | `content="5"` | PASS |
| T2 옵트아웃 | `gil web --refresh 0` | meta 없음 + bake `"refresh":0` | PASS |
| T3 명시값 | `gil web --refresh 10` | `content="10"` | PASS |
| T4a 옵트아웃 재굽기 보존 | `_bake_meta(off)` | 0 | PASS |
| T4b 구버전 뷰어 재굽기 | `_bake_meta(refresh 키 없음)` | 5 | PASS |
| WEB-REFRESH-DEFAULT | conformance 신설 계약 | PASS | PASS |

산출물: runs/{default,off,ten}.html
