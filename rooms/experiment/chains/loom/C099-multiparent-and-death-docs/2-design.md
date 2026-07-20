# 2. 실험 설계

가설: 세 갈래 how-to(다중부모·C097 게이트·C098 rejected close+withdraw 경계)를 순수 문서 파일에 명문화하면 필드 LLM이 오해·위반을 피하고 conformance 회귀 0.

## 대상 파일 (순수 .md만 — Sheen의 gil.py·main.go와 안 겹침)

1. **README.ai.md** (저장소 루트, LLM 직독) — 가장 중요. C096 발견②의 오도 지점 102가 여기.
2. **rooms/deployment/ariadne-spec/SPEC.md** — 계약 명문. §3.2 O-table 근처.
3. **rooms/deployment/ariadne-spec/QUICKSTART.md** — 사람용 워크드.

## 절차

### 갈래 1 — 다중부모 how-to (이월분, C096에서 구조)

1. **README.ai.md:102 정정** (핵심): 현재 "둘째 조상은 `--lineage`"로 오도. →
   - `--parent`는 **반복 가능**하고 병합이면 `parent: [A, B]`가 된다는 것 명시.
   - `--lineage`는 **다른 체인**의 교훈 전용임을 분명히(같은 체인 다중부모 ≠ lineage). 이월 패치 README.ai.md.patch의 취지를 현재 문맥(C097 게이트 반영된 상태)에 맞춰 다시 쓴다.
2. **QUICKSTART.md**: `--parent` 예제(82행) 근처에 **병합 워크드 한 블록** 추가 — `--parent A --parent B`로 두 갈래를 잇는 실예(C036 `parent:[C020,C016]` 인용). 이월 패치 QUICKSTART.md.patch 취지.
3. **SPEC.md §3.2 O-table 뒤**: `--parent` 반복·병합=`[A,B]`·lineage 다른 체인 전용을 조항으로. 이월 패치 SPEC.md.patch 취지. (cycle.yaml 주석 79행이 이미 `병합=[a,b]`를 언급하나 O-table엔 없음 → 보강.)

### 갈래 2 — C097 부모 닫힘 게이트 명문화

4. **SPEC.md O-table에 O6 행 추가**: "부모가 닫히지 않음(열림/rejected) → **거부**. 부모를 먼저 닫거나 닫힌 사이클로 분기." (O1~O5 뒤 자연스럽게.)
5. **README.ai.md**: open 설명(102 근처)에 한 줄 — "부모는 닫혀 있어야 그 위에 자식을 연다(열린 부모의 자식 금지)."
6. **QUICKSTART.md**: open 노트에 짧게.

### 갈래 3 — C098 rejected close + withdraw 경계

7. **README.ai.md**: 죽은 가지 다루기 항목 — "미완 가지를 죽이려면 `close --verdict rejected`(죽은 시점 step 보존, 그래프에 각인). 죽은 이유는 마지막 스텝 문서에 남긴다. **withdraw는 open 직후 전용**(revert). 둘의 경계: 방금 열고 아무것도 안 했으면 withdraw, 얼마간 진행하다 죽이면 rejected close." (goto 항목 148 근처 — 이미 "dead end를 지우지 않는다"가 있어 그 계열.)
8. **SPEC.md**: close 계약 설명에 rejected 경로 조항(§ close 근처) — "rejected면 step5·5-report 강제 완화, 죽은 시점 step 보존, R9 예외."

## 준비물

- gil v2.46.0 (main, 방금 배포). `python3 rooms/deployment/ariadne-spec/gil.py`.
- 실동작 대조용: 임시 저장소에서 `--parent A --parent B`·열린 부모 open·rejected close 실행(문서 내용이 실동작과 일치하는지, kill 1).
- conformance: `--gil "python3 …/gil.py"` (문서만 바꾸니 128 유지 확인, kill 2).

## 측정 방법

| # | 측정 | 기준 |
|---|---|---|
| M1 | 문서 명령 실동작 대조 | 문서에 쓴 `--parent A --parent B`→`[A,B]`, 열린부모 거부, rejected close가 실제와 일치 (kill 1) |
| M2 | 참조 conformance | 128 유지 (도구 무변경) (kill 2) |
| M3 | 건드린 파일 목록 | .md만 (gil.py·main.go 0) (kill 3) |
| M4 | README.ai:102 오독 여지 | "다중부모=lineage" 유도 문구 제거·정정 확인 (kill 4) |

## 사용자 컨펌

- 생략 — (B) 문서화는 지난 세션 계획(A→B→C→D)의 확정 항목이고, 상현님 전권 위임 하. 이번 세션 상현님 지시("뷰어 병렬 + 나머지 이어가자")로 (B) 진행이 승인됨. 문안 세부는 이월 패치 취지 + 현재 코드 실동작을 근거로 하므로 추가 컨펌 불요.

- [x] 컨펌 받음 (일자: 2026-07-20, "나머지 이어가자"로 갈음)
