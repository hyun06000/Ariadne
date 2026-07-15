# 3. 가설 검증 — 실시간 관찰

## 재현 방법 (불변 기준)
```bash
GIL=$(pwd)/gil.py   # 절대 경로 (C028·C043)
python3 conformance.py --gil "python3 $GIL"   # 73/73 (WEB-REFRESH 포함)
go build -o /tmp/gil-go go/main.go
python3 conformance.py --gil "/tmp/gil-go"    # 65/65
```
- 참조 72→**73**, Go 64→**65** (WEB-REFRESH 추가). 회귀 0.
- **변이 격추**: `render_web_page`의 meta 삽입을 제거하면 WEB-REFRESH가 FAIL(`rc=0 baked=True` — bake는 남지만 meta가 없어 브라우저가 리로드 안 함). 계약이 실제 판정됨.

## H1 meta + 자기완결
`gil web --refresh 3` → HTML `<head>`에 `<meta http-equiv="refresh" content="3">`, JSON bake에 `"refresh": 3`, 외부 리소스 0.

## H2 자동 재굽기가 refresh 보존 (핵심 통합)
```bash
gil web -o chains.html --refresh 5     # meta 5 + bake.refresh 5
gil step demo C001-a 2                  # 원장 변경 → C042 자동 재굽기
grep 'content="5"' chains.html          # 여전히 존재 — bake에서 읽어 보존
```
gil step이 원장을 바꿀 때마다 파일이 갱신되고(C042), meta refresh가 브라우저를 리로드 = **새로고침 없는 실시간**.

## H3 하위호환 + H4 두 구현
- `--refresh` 없으면 meta 없음·bake refresh 키 없음 → 개선 전과 **바이트 동일**.
- `--refresh` 유/무 모두 참조 = Go **바이트 동일**(실 저장소).
- `--watch`(참조 전용, 장기 실행): 원장 mtime 감시 → 변경 시 재생성, --refresh 함축. gil step을 안 거치는 외부 변경(병합·pull)도 반영. Go도 이식(webWatch).

## 실행 기록
- 2026-07-15. H1~H4 통과, 변이 격추, conformance 73/65 회귀 0.
