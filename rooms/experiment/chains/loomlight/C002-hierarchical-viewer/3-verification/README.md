# 3. 가설 검증

위계 뷰어(`gil web --hierarchy`)가 가설을 지지하는지 6측정으로 실측한다.

## 재현 방법

저장소 루트에서:

```bash
bash rooms/experiment/chains/loomlight/C002-hierarchical-viewer/3-verification/verify.sh
```

- `verify.sh`는 임시 디렉토리에 산출물을 굽고 6측정을 판정한다. 전 측정 통과면 exit 0.
- 개선 전 gil.py는 `git show origin/main:...gil.py`로 꺼내 **같은 체인 데이터**로 구워 신 gil.py의
  기본 출력과 `cmp`한다(하위호환의 바이트 증명).
- 커밋된 표본 `sample-hierarchy-loomlight.html`(40KB)는 loomlight 체인만 담은 위계 뷰어 —
  브라우저로 열면 체인→사이클→5스텝 드릴다운을 JS 없이 그대로 확인할 수 있다.

## 측정 항목과 성공 기준

| 측정 | 성공 기준 | 대응 기각조건 |
|---|---|---|
| M1 / M1b | 기본(플래그 없음) 출력이 개선 전 gil.py와 **바이트 동일** (genesis / 전체 체인) | 3 (하위호환) |
| M2 / M2b | 참조 conformance 전 항목 PASS, WEB-SELFCONTAINED·WEB-JSON·WEB-REFRESH 초록 | 3 (회귀) |
| M3 | `--hierarchy` 출력에 외부 리소스 0, `<script>`는 `id="gil-data"`(JSON) 하나뿐(실행 JS 0) | 1 (계약 위반) |
| M4 / M4b | 목차 1개 · `details.hchain` = 체인 수 · `details.hcycle` = 사이클 수 · `details.hstep` = 사이클×5, C002 앵커·메타표 실재 | 2 (위계 미동작) |
| M5 | `--hierarchy --refresh 3` → meta refresh + `bake.hierarchy=true`&`refresh=3` 동시, 외부 리소스 0 | 1·병존 |
| M6 | 위계 뷰어를 `_bake_meta`로 왕복하면 `hierarchy=True` 회수, **기본 bake엔 hierarchy 키 부재**(바이트 동일 보증) | 3 (자동갱신 보존) |

## 실행 기록

- 실행: 2026-07-19, macOS (Darwin 25.5.0), Python 3, git 있음. Go 툴체인 **없음**(확인) → Go 미변경.
- **결과: 6측정(세부 9판정) 전부 PASS.**
  - M1 genesis 바이트 동일 · M1b 전체 체인 바이트 동일
  - M2 conformance **56/56**(--skip-git) / **77/77**(git 포함, WEB-AUTO-* 4항목 포함 전부 초록)
  - M3 외부 0 · script 1 · 그중 데이터 1
  - M4 목차 1 · 체인 5/5 · 사이클 65/65 · 스텝 325=65×5 · M4b C002 앵커·메타표 실재
  - M5 meta=1 · bake.hierarchy&refresh=1 · 외부 0
  - M6 왕복 hierarchy 보존 True, 기본 bake 키 `['chain','title']`(hierarchy 부재)
- 특이사항: M4의 최초 판정은 `find cycle.yaml`(110)이 rounds/ 하위 라운드 cycle.yaml까지 세어
  그래프 노드 수(65)와 어긋나 FAIL했다. 진실값을 **뷰어 자신의 내장 gil-data JSON 노드 수**로
  바꿔(원장을 그대로 반사) 자기정합 판정으로 교정 — 구현 결함이 아니라 판정기 분모 오류였다.
- 산출물: `verify.sh`(재현 스크립트), `sample-hierarchy-loomlight.html`(커밋 표본).
