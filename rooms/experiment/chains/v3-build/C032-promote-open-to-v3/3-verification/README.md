# 3. 가설 검증

이 디렉토리에 실험 실행에 사용된 **모든 것**이 저장된다: 코드, 스크립트, 입력 데이터(또는 그 출처와 해시), 실행 로그, 연산 결과, 생성된 아티팩트.

## 대상

배포판 `gil.py` `cmd_open` 진입에 **v2 은퇴 안내**를 얹어 `gil open`을 버전리스 승격.
격리 복사본 `promoted/gil.py`에서 먼저 실측. 구현: `cmd_open` 최상단 게이트 —
`GIL_V2_OPEN != "1"`이면 v2 습관에 친절한 은퇴 안내(v3 방식·순환 규칙), `=1`이면 v2 유지.

## 재현 방법

```bash
D=rooms/experiment/chains/v3-build/C032-promote-open-to-v3/3-verification
G="$(pwd)/$D/promoted/gil.py"

# M1: v3 쓰기 생존
rm -rf /tmp/c032test && python3 $G v3 open /tmp/c032test --title "test"   # → steps.yaml 생성

# M2: v2 은퇴 안내 (침묵 실패 아님)
python3 $G open someChain some-slug --author clew ; echo "exit=$?"          # → 친절 에러, exit 1

# M3: conformance (게이트를 프로세스 환경 상속)
GIL_V2_OPEN=1 python3 $D/promoted/conformance.py --gil "python3 $G"         # → 134/134 ✔

# M4: 원장 digest 불변 (baseline 05ba3e6c)
git rev-list '--exclude=refs/notes/*' --all | sort | git hash-object --stdin

# M5: 눈 생존 — 승격된 gil이 189를 v3 눈으로
GIL_V2_OPEN=1 python3 $G web --v3 -o /tmp/c032-v3.html .                     # → 132노드·131엣지
```

## 실행 기록

- 실행: 2026-07-22, Darwin 25.5.0, Python3 stdlib.
- **5측정 ALL PASS** (상세·핵심 발견은 [4-analysis.md](../4-analysis.md)).
- baseline: conformance 134/134([baseline-conformance.txt](baseline-conformance.txt)), digest 05ba3e6c([baseline-digest.txt](baseline-digest.txt)).
- 계측기 구분 1건: M3 첫 실측 133/134는 `env` 래퍼가 빈-PATH 테스트에서 python3 못 찾은 rc=127 아티팩트. 게이트 프로세스-환경 상속으로 134/134 (승격 결함 아님).
