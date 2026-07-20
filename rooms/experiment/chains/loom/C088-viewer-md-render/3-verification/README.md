# 3. 검증 — 마크다운 렌더 토글 + 이미지 임베드

## 재현
1. **이미지 임베드(Python 단위)**: `_embed_images`에 작은 PNG·상한초과·외부URL·부재·경로이탈 케이스 → 상한 내 로컬 이미지만 data URI, 나머지 스킵.
2. **렌더러(JS, 헤드리스 Chrome end-to-end)**: 실제 뷰어를 굽고 헤드리스로 열어 사이클 문서 열기 → 렌더 토글 클릭 → `.mdbody`(렌더된 마크다운) DOM 생성 확인.
   ```bash
   gil web -o live.html
   # live.html에 드라이버 주입: 사이클 열기 → .mdtoggle 클릭 → .mdbody/.mdh 존재 확인
   chrome --headless --virtual-time-budget=3000 --dump-dom file://live.html
   ```
3. **conformance WEB-MD-RENDER**: 토글 버튼 + 인라인 파서(renderMd/inlineMd) + 기본 원문(rendered=false) + javascript: 차단(safeUrl).

## 결과
| 항목 | 기대 | 결과 |
|---|---|---|
| 이미지 임베드 | pic.png만(상한/외부/부재/이탈 스킵) | PASS |
| 헤드리스 렌더 | 토글 클릭 → .mdbody + .mdh 생성 | PASS (rendered_dom·has_heading·toggle_clicked 모두 true) |
| WEB-MD-RENDER | toggle·parser·initial_raw·xss 4항 | PASS |
| 회귀 | baseline 5 FAIL 동일, 무이미지 저장소 images 키 부재 | 0 |

## 밟은 버그 (헤드리스가 잡음)
- **blockquote**: `esc()`가 `>`를 `&gt;`로 바꿔 `/^\s*>\s?/` 정규식이 `> 인용문`을 못 잡아 `<p>&gt; 인용문</p>`로 렌더됐다. 헤드리스 end-to-end 렌더 덤프가 정확히 잡음 → 정규식을 `/^\s*(>|&gt;)\s?/`로 수정. **정적 grep으론 못 봤을 버그 — 실제 브라우저 렌더가 필요했다.**

## 산출물
- runs/{hier,flat}.html (버전+토글), runs/headless-driver.html (드라이버 주입본), assets/sample.png
