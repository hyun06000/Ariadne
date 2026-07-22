# 3. 가설 검증

길3(v3 전용 최소 검사) + records 형태 통일로 fsck·load_chain_records가 v3 사이클
(steps.yaml)을 인식하게 했다. 배포판 gil.py 수정.

## 산출물

- `verify.sh` — M1(인식)·M2(번호중복)·M4(루트define) 재현 스크립트.
- 구현: gil.py `load_chain_records` v3 수집 분기 + `fsck_collect` V3-ROOT 검사.

## 재현 방법

```bash
bash rooms/experiment/chains/v3-build/C040-fsck-recognizes-v3/3-verification/verify.sh
# M5 v2 무회귀: 실저장소 fsck 위반 0
python3 rooms/deployment/ariadne-spec/gil.py fsck
# M6 conformance:
cd rooms/deployment/ariadne-spec
GIL="python3 $(pwd)/gil.py"; GIL_V2_OPEN=1 python3 conformance.py --gil "$GIL"  # → 121/121
```

## 실행 기록

- 실행: 2026-07-23, macOS(Darwin 25.5.0), Python 3.9. gil.py 수정.

### 측정 결과 (전 항목 PASS)

- **M1 v3 인식 — PASS.** v3 네이티브 사이클 1개 저장소 `fsck` → "체인 1개, **사이클 1개**"
  (이전 0개). v3 사이클이 원장에 실제 사이클로 나타남. **C039 사각지대 소멸.**
- **M2 번호 중복 검출 — PASS(기각조건 3 해소).** 같은 번호 v3 둘(C001-native·C001-dup) →
  `R1 demo: 번호 001 중복`. **C039의 병렬 번호 충돌이 이제 무결성 위반으로 잡힌다.**
  records 형태 통일 덕에 기존 R1 번호 중복 검사(gil.py 495)가 v3에 공짜 적용.
- **M3 v3 거짓위반 0 — PASS.** 정상 v3 사이클(루트 define 있음)에 R8·R9·R10 거짓위반 0
  (M1의 "위반 0건"이 증명). status/verdict/step 미설정이 조건부 R규칙을 자연 스킵 +
  명시적 `continue`.
- **M4 루트 define 검사 — PASS.** steps.yaml의 define을 hypothesis로 훼손 →
  `V3-ROOT: 루트 define(s1·parent:null)이 없다`. v3 고유 무결성 검출.
- **M5 v2 무회귀 — PASS.** 실저장소(v2 사이클 169개) `fsck` 위반 0, "사이클 170개"
  (169 + 방금 연 C040, 모두 v2 cycle.yaml — stray v3 사이클 0 확인). R규칙 불변.
- **M6 conformance — PASS.** 게이트 상속 **121/121**. gil.py 변경이 v2 경로 무손상.

### 종합

가설 채택. v3 사이클이 fsck·log에 인식되고, 번호 중복이 위반으로 검출되며, v2 인식·
conformance 무회귀. **길3의 핵심 판단(v2 R규칙 무손상 + records 통일로 R1 번호검사 재사용)이
적중** — v3 전용 검사는 V3-ROOT 하나만 새로 필요했고 번호 중복은 공짜로 잡혔다.
