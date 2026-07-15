# 2. 실험 설계 — 실시간 관찰

## 설계 결정

### D1 — `--refresh N`: meta 삽입 + bake 기록
- `render_web_page(..., refresh=None)`: `refresh`가 있으면 `<head>`에 `<meta http-equiv="refresh" content="{N}">`. JSON `bake`에 `"refresh": N`을 **있을 때만** 넣는다(C043 "있을 때만 내보내라" → 하위호환 바이트 동일).
- meta refresh는 HTML 표준 태그(JS 아님, 같은 URL 리로드 = 외부 리소스 아님) → 자기완결 계약 유지.

### D2 — 자동 재굽기가 refresh를 보존 (C042 통합, H2의 핵심)
- `_bake_meta(text)`가 bake에서 `title, chain, refresh`를 읽는다.
- `_refresh_viewers`가 재굽기 시 refresh를 `_bake_viewer`에 전달 → 재생성된 HTML도 meta 유지.
- 이로써 gil step이 원장을 바꿀 때마다 파일이 갱신되고, meta refresh가 브라우저를 리로드한다 = **실시간**.

### D3 — `--watch [--interval N]` (선택, 참조만)
- `--refresh`를 함축 + 원장 스냅샷을 감시하는 루프. 변경 시 재생성. gil step을 안 거치는 외부 변경(병합·pull)도 반영.
- 장기 실행(데몬)이라 conformance 부적합 — refresh 부분만 계약·판정. Go 미구현이면 정직(참조만).

## 기대 행동

| # | 항목 | 기대 |
|---|---|---|
| T1 | WEB-REFRESH | `gil web --refresh 3` → HTML `<head>`에 `meta http-equiv="refresh" content="3"`, 외부 리소스 0 유지 |
| T2 | WEB-REFRESH-BAKE | `--refresh 3` 산출물의 bake JSON에 `"refresh": 3` |
| T3 | REFRESH-PRESERVE | `--refresh`로 구운 뷰어를 gil step 자동 재굽기 후에도 meta refresh **유지** (bake 보존) |
| T4 | 하위호환 | `--refresh` 없으면 meta 없음·bake refresh 키 없음 → 기존과 바이트 동일 (WEB-JSON/SELFCONTAINED가 커버) |
| T5 | 두 구현 동일 | `--refresh` 유/무 모두 참조=Go 바이트 동일 |

**측정**: meta 태그 존재/부재, bake.refresh, step 후 meta 유지, 두 구현 cmp. conformance 회귀 0.

## 사용자 컨펌
- 상현님 발의가 곧 승인. [x] (2026-07-15)
