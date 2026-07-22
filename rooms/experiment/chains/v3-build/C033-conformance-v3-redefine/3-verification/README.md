# 3. 가설 검증

이 디렉토리에 실험 실행에 사용된 **모든 것**이 저장된다: 코드, 스크립트, 입력 데이터(또는 그 출처와 해시), 실행 로그, 연산 결과, 생성된 아티팩트.

## 대상

배포판 `conformance.py`에 v3 쓰기 계약 3항목 신규(V3-OPEN-CREATE·V3-OPEN-REJECT-EXISTING·
V3-RETIRE-GUIDANCE). GUARD 블록 끝(line 2065)과 `shutil.rmtree` 사이 삽입. 격리 복사본
(`gil.py`·`conformance.py`)에서 먼저 실측 후 배포판 적용.

## 재현 방법

```bash
D=rooms/experiment/chains/v3-build/C033-conformance-v3-redefine/3-verification
G="$(pwd)/$D/gil.py"

# M1-M4: 게이트 상속 시 전체 (신규 3항목 PASS + 기존 134 무회귀 = 137/137)
GIL_V2_OPEN=1 python3 $D/conformance.py --gil "python3 $G" | grep -E "V3-|계약 준수"

# M5: 게이트 없이 — v3 항목 게이트-독립 검증 (핵심 발견: OPEN-CREATE서 crash)
python3 $D/conformance.py --gil "python3 $G"    # → FileNotFoundError (첫 v2 open 항목)
```

## 실행 기록

- 실행: 2026-07-22, Darwin 25.5.0, Python3 stdlib.
- **M1~M4 PASS** (게이트 상속 시 **137/137 ✔**, 신규 3항목 전부 PASS, 기존 134 무회귀).
- **M5 핵심 발견**: 게이트 없이 돌리면 **첫 v2 항목 OPEN-CREATE에서 crash**(`_seal_closed` cycle.yaml 부재 FileNotFoundError) — v3 항목(파일 끝)에 도달조차 못함. conformance.py는 순차 실행·예외 미처리라 첫 v2 open 실패가 전체를 무너뜨린다. **판정기의 v2 결합은 open보다 깊다** (기각조건 1 실증).
- 배포판 적용 후 재확인: 게이트 상속 시 137/137 ✔.
- 상세·매핑표·판정은 [4-analysis.md](../4-analysis.md).
