# 3. 가설 검증

가설: deployments.json을 gil-data top-level `deployments` 키로 굽고 아티팩트별 배포 계보 카드를
릴리스 패널과 **별개로** 렌더하면, 뷰어가 사용자 산출물 배포를 정직히 비추면서도 배포 안 쓰는
저장소엔 렌더 콘텐츠가 안 늘고 폴링에 열린 상태가 안 깨진다.

이 디렉토리의 산출물: `cdp.py`(raw-WS CDP 드라이버, C013서 재사용), `cdp-steps.json`(CDP 스텝),
`sandbox-deployments.json`(실 배포 레코드), `rendered-deploy-panel.png`(헤드리스 렌더 스크린샷).

## 재현 방법

```bash
GILPY=<repo>/rooms/deployment/ariadne-spec/gil.py
SB=$(mktemp -d)/sandbox; mkdir -p "$SB/rooms/experiment/chains" "$SB/rooms/deployment"
CR="$SB/rooms/experiment/chains"; cd "$SB"; git init -q
git config user.email t@t; git config user.name t
# 실 사이클 2개 열고 닫기 (각 스텝 doc 채우고 gil step → gil close)
python3 "$GILPY" open alpha first-thing --title X --author Tester --new-chain --new-root --root "$CR"
#  ... (각 스텝 doc 작성 후) gil step alpha C001-first-thing {2..5}; gil close alpha C001-first-thing
#  ... C002도 동일 (--parent C001-first-thing)
# 실 배포 레코드 (세 status 커버)
python3 "$GILPY" deploy cut churn-model 1.9.0 --cycle alpha/C001-first-thing --kind model --date 2026-07-02 --root "$CR"
python3 "$GILPY" deploy cut churn-model 2.0.0 --cycle alpha/C001-first-thing --cycle alpha/C002-second-thing --date 2026-07-10 --root "$CR"
python3 "$GILPY" deploy rollback churn-model --root "$CR"        # → 2.0.0 rolled-back, 1.9.0 live
python3 "$GILPY" deploy cut landing-page 1.0.0 --cycle alpha/C002-second-thing --date 2026-07-19 --root "$CR"
python3 "$GILPY" deploy cut landing-page 1.1.0 --cycle alpha/C002-second-thing --date 2026-07-20 --root "$CR"  # → 1.0.0 superseded
# 렌더 + 스크린샷
python3 "$GILPY" web "$CR" -o "$SB/view.html" --refresh 0
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --screenshot="$SB/view.png" --window-size=1000,1400 "file://$SB/view.html"
# 폴링·상호작용 CDP 실측
python3 "$GILPY" web "$CR" -o "$SB/serve/index.html" --refresh 2
(cd "$SB/serve" && python3 -m http.server 8765 &)
python3 cdp.py "http://127.0.0.1:8765/index.html" cdp-steps.json
# conformance
python3 <repo>/rooms/deployment/ariadne-spec/conformance.py --gil "python3 $GILPY"
```

## 측정 결과 (2026-07-21, macOS Darwin 25.5.0, Python3 stdlib, Chrome headless)

- **M1 구조 (통과)**: 배포 카드 1개 · 릴리스 카드 0개(무CHANGELOG → 두 축 분리 실증) ·
  depcyc 앵커 `#cycdoc-alpha-C001/C002`가 실 cycdoc 마운트 id와 일치 ·
  status 마크 3종(live ● / superseded · / rolled-back ↩) · live 배지 정확.
- **M2 하위호환 (통과)**: deployments.json 제거 시 배포 카드·`deployments` 키 부재. 변경 전 gil.py(HEAD)
  출력과 tag-split diff → 차이가 **CSS 블록 + POLL_SEL 상수 1줄에 국한**, HTML 본문 콘텐츠 차이 0.
  (릴리스 패널 C006도 CSS는 항상 인라인되는 확립된 계약 — 렌더 카드/데이터가 안 늘면 하위호환.)
- **M3 상호작용 (통과, CDP)**: depcyc 링크 클릭 → hash 설정, 대상 cycdoc `visible:true`·`bodyFilled:true`
  (JS가 5스텝 문서를 그 자리에 구축). 배포→근거사이클 링크 end-to-end 작동.
- **M4 폴링 상태보존 (통과, CDP)**: 폴링 1주기(2.6s>2s) 통과 후 — 배포 패널 잔존 · 패널 텍스트 불변 ·
  열린 대상 유지 · hash 보존. C014 회귀 0(패널에 중첩 details 없고, 열린 cycdoc 마운트는 기존 detKey 가드가 보존).
- **M5 conformance (통과)**: WEB-DEPLOYMENTS 신규 판정 추가 → **참조 134/134**(직전 133/133, 회귀 0).

CDP 원시 반환:
`[1, 4, "#cycdoc-alpha-C001-first-thing", {"visible":true,"bodyFilled":true},
 <before>, {"deployPanelStillThere":true,"panelTextSame":true,"targetStillOpen":true,"hash":"#cycdoc-alpha-C001-first-thing"}]`

## 두 몸 한 계약 — Go 이식 이월 (정직)

이 워크트리엔 `go/` 트리가 없다 — Go web 렌더 이식은 병렬 세션 Weft가 별도 워크트리에서 진행 중
(deploy 명령군 이식). 배포 패널 렌더는 렌더면(§3.1, 바이트 계약 아님)이고, WEB-DEPLOYMENTS 판정은
`impl`에 무관하게 작성됐다 — Weft가 Go 렌더를 랜드하면 같은 판정이 Go에도 적용된다. 참조 먼저 완성,
Go 렌더는 정직히 이월(HELP-COMPLETE/WEB 이월 정당).

## 판정

가설 지지 — M1~M5 전부 통과. 기각 조건 3개(하위호환 위반·축 혼합·링크/폴링 파손) 모두 미발동.
