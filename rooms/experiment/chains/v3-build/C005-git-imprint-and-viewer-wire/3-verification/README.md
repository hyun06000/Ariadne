# 3. 검증 — v3 깃 각인(스텝=커밋) + 뷰어 배선

설계(2-design)의 `gilv3 v0.2`(깃 각인 + `view`)를 실사례로 검증한 산출물.

## 파일

- `gilv3.py` — v0.2. C003 명령(open/step/close/status) + **`--git` 스텝 각인** +
  **`view`** 서브명령. 뷰어는 C004 `steptree.py`를 **import 재사용**(재구현 금지),
  깃은 **별개 층**(steps.yaml에 깃 메타 0). 순수 stdlib + git.
- `rebuild-imprinted.sh <repo>` — 격리 임시 깃 저장소에서 `open --git`+9×`step --git`+
  `close --git`로 C012→C014 트리를 짓고 커밋 수를 관찰. **메인 레포 밖**(중첩 .git 방지).
- `measure.py <repo>` — G1(스텝=커밋)·G2(뷰어 배선)·M3(모델 무오염) 판정.

## 재현 방법

임시 저장소는 레포 밖(스크래치패드 등)에 만든다 — 중첩 `.git` 방지:

```bash
cd 3-verification
REPO="${TMPDIR:-/tmp}/gilv3-imprinted"
bash rebuild-imprinted.sh "$REPO"     # 각인 켠 재구성 → 11 커밋
python3 measure.py "$REPO"            # G1·G2·M3 판정
```

환경: Python 3 stdlib + git. macOS Darwin. 2026-07-21 실행, ALL PASS.

## 결과 (전부 PASS)

| 측정 | 기준 | 결과 |
|---|---|---|
| **G1** 스텝=커밋 (K1) | 커밋 11개(open+9step+close), 순서==시간순, 커밋당 스텝1 | ✅ |
| **G2** 뷰어 배선 (K2) | `gilv3 view` == C004 render **바이트 동일** + C004 measure ALL PASS | ✅ |
| **M3** 모델 무오염 (K3) | steps.yaml 필드 == C002 스키마 6개, 깃 메타 0 | ✅ |

## 실행 기록 — 커밋 로그 = 스텝 트리 (시간순)

```
461e133 gilv3 open: s1 define
00be299 gilv3 step: s2 hypothesis
7ad9f7a gilv3 step: s3 verify
917d95d gilv3 step: s4 analyze/backtrack   ← 되돌아감도 커밋 하나(선형 히스토리)
...
068acee gilv3 step: s10 analyze/success
3745829 gilv3 close: 산 잎 s10 (봉인)       ← 빈 커밋(--allow-empty), 의미만 각인
```

## 실행 중 발견

- **close는 파일을 안 써서 첫 시도 커밋 실패** — `close`가 봉인의 *의미*만 각인하고
  파일 변경이 없어 `git commit`이 "nothing to commit"으로 죽었다. 진단: close = 봉인
  마커(v2의 close 태그·커밋에 대응). `--allow-empty`로 **빈 봉인 커밋**을 냈다. 스텝=커밋
  1:1이 유지되되, close는 파일 없는 순수 의미 스텝임이 드러났다(씨앗: close에 verdict를
  파일로 남길지 vs 빈 커밋으로 둘지는 후속).
- **G2 바이트 동일이 배선의 강한 증명**: `gilv3 view`가 C004 render.py와 바이트 동일
  HTML을 냈다(cycle 라벨만 정규화). 배선이 뷰어를 재구현하지 않고 닫힌 사이클 C004의
  생성기를 그대로 호출함을 증명 — 한 생성기, 두 호출 지점.
