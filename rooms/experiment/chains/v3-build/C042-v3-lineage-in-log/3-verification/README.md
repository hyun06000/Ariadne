# 3. 가설 검증

load_chain_records의 v3 분기가 계보 trailer(Cycle-Parent·Cycle-Author)를 git으로 읽어
record의 parents·author를 채우게 했다. 배포판 gil.py 수정(`_v3_lineage` 헬퍼 추가).

## 산출물

- `verify.sh` — M1(log 계보)·M4(비-git 폴백) 재현 스크립트.
- 구현: gil.py `_v3_lineage` + `load_chain_records` v3 분기 계보 채움.

## 재현 방법

```bash
bash rooms/experiment/chains/v3-build/C042-v3-lineage-in-log/3-verification/verify.sh
# M5 conformance:
cd rooms/deployment/ariadne-spec
GIL="python3 $(pwd)/gil.py"; GIL_V2_OPEN=1 python3 conformance.py --gil "$GIL"  # → 121/121
```

## 실행 기록

- 실행: 2026-07-23, macOS(Darwin 25.5.0), Python 3.9. gil.py 수정.

### 측정 결과 (전 항목 PASS)

- **M1 log v3 계보 표현 — PASS.** v3 사이클 C001-root·C002-child(--parent C001-root) →
  `gil log` 계보 `C002-child ← C001-root`(이전 (root)). root 목록도 `C001-root`만 정확
  (이전 둘 다 root). **계보가 trailer에서 복원돼 그래프에 그려진다.**
- **M2 그래프 노드 — PASS.** build_graph가 채워진 parents로 토폴로지·계보 섹션 정확 반영.
- **M3 author 복원 — PASS.** load_chain_records record에 author 채워짐(C001-root=clew,
  C002-child=weft), parents=['C001-root']. 직접 확인.
- **M4 비-git 폴백 — PASS.** .git 없는 복사본에서 `gil log`가 crash 없이 (root)로 폴백
  (계보 못 읽지만 안전). rc=0. `_v3_lineage`의 try/except + rc 체크가 안정성 보장.
- **M5 v2 무회귀 — PASS.** 실저장소 fsck 위반 0(172개), 게이트 상속 conformance 121/121,
  게이트 없이 109. C040 v3 번호중복(R1)도 여전히 검출(`R1: 번호 001 중복`) — v3 인식
  회귀 없음.

### 종합

가설 채택. v3 계보가 trailer에서 복원돼 log 그래프에 부모로 그려지고, author도 복원,
v2·v3·conformance 무회귀. **도그푸딩 전환의 "눈"이 생겼다** — 관전자가 gil log로 v3
사이클 계보를 본다. C041 이월(계보 표현)이 해소.
