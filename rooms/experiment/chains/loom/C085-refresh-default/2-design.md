# 2. 실험 설계 — refresh 기본화

## 절차

1. **상수 단일화**: `_WEB_DEFAULT_REFRESH = 5` 신설.
2. **argparse 기본값**: `--refresh`의 `default`를 `_WEB_DEFAULT_REFRESH`로. 옵션 무 → 5, `--refresh 0` → 옵트아웃.
3. **bake 옵트아웃 명시화**: 지금까지 bake는 `refresh` truthy일 때만 키를 넣었다(무리프레시 바이트 동일, C043). 기본이 실시간이 된 이상, "명시적 끔(0)"과 "말 안 함"을 구별해야 재굽기가 옵트아웃을 되돌리지 않는다. → bake 조건을 `refresh is not None`으로, 값도 `refresh` 그대로(0 포함) 기록.
4. **재굽기 fallback**: `_bake_meta`가 refresh 키를 못 찾으면(구버전 뷰어) `_WEB_DEFAULT_REFRESH`를 돌려준다 — 구버전 뷰어도 재굽으면 실시간이 된다. `refresh: 0`이 명시된 뷰어는 그 0을 존중.

## 준비물

- 정본 `rooms/deployment/ariadne-spec/gil.py` (Python 3), conformance.py.

## 측정 방법

- `gil web` (무옵션) → grep `meta http-equiv="refresh" content="5"` 존재.
- `gil web --refresh 0` → meta refresh 부재 + bake에 `"refresh": 0` 존재.
- `gil web --refresh 10` → content="10".
- refresh 0으로 구운 뒤 `_refresh_viewers` 재굽기 → 여전히 meta refresh 부재(옵트아웃 보존).
- 구버전 뷰어(bake에 refresh 키 없음) 재굽기 → content="5" 획득.
- conformance.py 전체 통과(회귀 0).

## 사용자 컨펌

- 발의자 박상현이 "실시간성이 디폴트가 아니라면 디폴트이게 해줘"로 직접 지시. 기본값 5초는 부모 C049의 --watch 기본 간격과 동일 — 선례 존중.

- [x] 컨펌 받음 (일자: 2026-07-20) — 발의 지시가 곧 컨펌
