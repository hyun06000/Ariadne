# 3. 검증 — 헤더 gil 버전

## 재현
```bash
gil web -o hier.html && gil web --flat -o flat.html
grep -o 'gil v[0-9.]*' hier.html   # → gil v<현재버전>
grep -o 'gil v[0-9.]*' flat.html   # → 동일
grep -c 'gilver{' hier.html flat.html   # 둘 다 1
```

## 결과
| 측정 | 기대 | 결과 |
|---|---|---|
| M1 두 몸 버전 표시 | hier·flat 모두 `gil v2.38.0` | PASS |
| M2 CSS 공용 | 두 몸 모두 `.gilver{` | PASS |
| M3 회귀 | baseline 5 FAIL 동일, 문법 OK | PASS(0) |

## 밟은 함정
- `.gilver`를 처음 `_WEB_HIER_CSS`(`.rcurrent` 옆)에 넣어 flat엔 스타일 미적용(버전 텍스트는 나오나 색·굵기 없음). `_WEB_CSS`의 `.gil header p` 옆으로 옮겨 해소 — **flat/hierarchy 공용 스타일은 _WEB_CSS에.**

산출물: runs/{hier,flat}.html
