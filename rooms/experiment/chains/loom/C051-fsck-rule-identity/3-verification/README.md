# 3. 가설 검증

이 디렉토리에 실험 실행에 사용된 모든 것을 보존한다. `mutant.py`는 T4~T6에 쓴 fsck 변이 래퍼(참조 gil.py로 무손실 통과, fsck 위반 출력만 변조).

## 재현 방법

```bash
cd rooms/deployment/ariadne-spec
GO111MODULE=off go build -o /tmp/gil-go go/main.go        # go1.26

# T3: 두 구현이 R1~R8 stdout에 규칙 토큰 + 대상 cid를 싣는지 (강화 전제)
#   → 1-hypothesis 실측 + 아래 T1/T2가 통과하면 확증

# T1·T2: 강화된 판정기로 회귀 0 확인
python3 conformance.py --gil "python3 $(pwd)/gil.py"       # 73/73
python3 conformance.py --gil "/tmp/gil-go"                 # 73/73

# T4: 규칙 토큰 제거 변이 → FSCK 계열 격추
MUT=strip   python3 conformance.py --gil "python3 $(pwd)/../../experiment/chains/loom/C051-fsck-rule-identity/3-verification/mutant.py"
# T5: 모든 토큰을 R1로 치환 → 잘못된 규칙 격추 (R1만 생존)
MUT=rewrite python3 conformance.py --gil "python3 .../mutant.py"
# T6: 문면만 변경(접미사·표기) → 전부 생존 (렌더는 계약 아님)
MUT=render  python3 conformance.py --gil "python3 .../mutant.py"
```
(`--gil`은 반드시 절대 경로 — C028·C043·C045 함정.)

## 실행 기록

- 일시: 2026-07-15. 환경: darwin 25.2.0(arm64), go1.26.2, python3(CommandLineTools).
- **T3 (전제 실측)**: R1~R8 각 위반 픽스처를 두 구현에 넣고 fsck **stdout**에 `Rk` 토큰과 위반 대상 cid가 실리는지 확인 → **8/8 규칙 × 2 구현 = 전부 존재**. 문면만 다름(R1 형식 힌트, R3 `(전역 표기 금지)`, R6 `(끊어진 참조)`, R4 결측 `None`/`''`) — 전부 렌더.
- **T1·T2**: 강화된 판정기(규칙 토큰 + 대상 id 검사) × 참조·Go = **73/73 · 73/73, 회귀 0.** 두 구현이 fsck 계약면(위반 식별)에 이미 합의했음이 확증됨.
- **T4 (MUT=strip)**: **63/73** — `FSCK-R1~R8·R7·R14·R15` 10항목 격추. 구 판정기(rc만)는 만점을 줬을 출력이다. **판정기가 이제 본다.**
- **T5 (MUT=rewrite→R1)**: **64/73** — `R2~R8·R7·R14·R15` 격추, **`FSCK-R1`은 정당히 생존**(그 픽스처의 진짜 규칙이 R1이므로). 잘못된 규칙 발화를 정확히 호명.
- **T6 (MUT=render)**: **73/73** — `(끊어진 참조)` 제거·`None` 삭제·`≠`→`!=` 문면 변경에도 격추 0. **계약이 렌더로 넘치지 않는다**(C021 재확인).
- 판정: T1·T2 회귀 0 ∧ T4·T5 격추 ∧ T6 생존 — **채택**. 기각 조건 3개 모두 불성립.

### 부수 관찰
- T4·T5가 `FSCK-R14`·`FSCK-R15`도 격추했다 — 그 둘은 이미 토큰을 검사하고 있었으므로 토큰 파괴 변이에 함께 걸렸다. 규칙 식별이 이제 **모든 fsck 규칙에서 균일하게 계약**임을 방증.
- 변이 래퍼가 깨끗한 저장소(rc==0)를 보존한 덕에 `FSCK-CLEAN`·`RESERVE-NON-INVASIVE` 등 다른 fsck 의존 항목이 오염되지 않아, 격추가 규칙 식별 항목에만 국소화됐다(C040·C041의 "다른 방어선이 침묵하는 입력을 골라라"의 실천 — 변이가 겨눈 조항만 흔들리게).