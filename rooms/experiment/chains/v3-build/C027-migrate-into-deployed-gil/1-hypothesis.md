# 1. 가설 수립

## 이전 사이클의 교훈

부모 **C026**이 "v3로 굴린다"의 형태를 확정했다: **v3 = v2 5스텝 위에 얹힌 notes 눈.** 그리고 상현님이 "이제 v3만 쓰는 거지?"에 대한 순서를 정했다 — **"먼저 배포판 통합부터."**

정직한 진단: 지금 v3 눈(migrate·web)은 **실험 산출물에 흩어져** 있다(`rooms/experiment/chains/v3-build/*/3-verification/gilv3.py` 등). 배포판(`rooms/deployment/ariadne-spec/gil.py`, 5020줄)엔 v2 명령만 있고 migrate·v3 web이 없다. **"v3만 쓴다"가 진짜가 되려면 v3 눈이 배포판 gil로 통합돼야** 한다. 상현님 정명: 이름은 gil(gilv3는 개발 격리명) — 하나의 gil.

## 문제 분할 — 통합은 큰 작업, 가장 작은 첫 카브

v3 눈 통합 대상:
1. **`gil migrate`** (C023 명령화·검증됨) — notes 소급·접합·백업·되돌림.
2. **`gil web` v3 뷰어** (Sheen C025) — notes 두 층 드릴다운.
3. 의존 스크립트들(derive_fingerprint·splice_topology·retro_imprint·rebuild_cycle_dag·snapshot 등).

**첫 번째로 정복할 것: `gil migrate`를 배포판 gil.py에 통합.** 이유:
- **migrate가 v3 눈의 뿌리다** — notes 각인이 있어야 web 뷰어도 읽을 게 생긴다. web은 migrate가 만든 notes에 의존하므로 migrate가 먼저.
- **이미 검증됨**(C023 오라클 대조 바이트 동일) — 새 로직이 아니라 검증된 것을 배포 본체로 옮기는 것.
- web 통합은 별도 카브(다음)로 절제 — 한 사이클에 다 넣으면 5020줄 본체에 큰 변경이 겹쳐 위험.

## ⭐ 통합의 형태 — "얇은 명령 + import된 검증 함수"(C023 재현)

C023이 gilv3에 migrate를 얹을 때 핵심은 "새 로직 없음, 검증 함수를 import·호출". 배포판 통합도 같다: migrate 백엔드 함수(derive/splice/retro/snapshot)를 gil.py 안에 통합하되 **동작을 바이트 보존**한다. 오라클 = C023 gilv3 migrate 출력. 배포판 `gil migrate`가 같은 것을 내면 통합이 로직을 안 바꿈.

## 가설

> **가설**: C023이 검증한 migrate 로직(derive_fingerprint·full_ledger_migrate·splice_topology·retro_imprint·백업/되돌림·snapshot 불변 게이트)을 배포판 gil.py에 `migrate` 서브명령으로 통합하면, 격리 복제본에서 배포판 `gil migrate`가 (a) C023 gilv3 migrate와 DAG·notes 바이트 동일 결과를 내고, (b) `--dry`·`--rollback` 계약을 보존하며, (c) 커밋·cycle.yaml 불변을 유지하고, (d) 배포판의 기존 명령(open/step/close/web 등)이 회귀 0이다 — 즉 v3 눈의 뿌리가 하나의 gil 안으로 로직 보존하며 들어온다.

## 기각 조건

- 배포판 `gil migrate` 결과가 C023 gilv3 migrate와 다르면(DAG·notes) → **기각**(통합이 로직 바꿈).
- 통합이 배포판 기존 명령을 하나라도 깨면(회귀) → **기각**.
- `gil migrate` 후 커밋·cycle.yaml이 바뀌면 → **기각**(C018 계약 파괴).
- 통합에 새 로직을 발명해야 하면 → **조사**(검증된 함수 import가 아니라 재구현이면 오라클 대조 무의미).
