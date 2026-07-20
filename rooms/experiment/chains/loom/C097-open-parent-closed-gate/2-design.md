# 2. 실험 설계

가설: `gil open`에 부모-닫힘 게이트를 넣으면 열린 부모 위 자식을 원천 차단하고 정상 흐름은 회귀 없이 통과한다.

## 절차

### 구현 (참조 gil.py)

1. `cmd_open`의 parent 검증 루프(현 gil.py:696~700)를 확장한다. 현재는 `ids`(id 집합)만으로 존재를 검사하므로, **id→status 맵**을 만든다:
   ```python
   status_by_id = {r.get("id"): r.get("status") for r in records}
   ```
2. 검증 루프에서 존재 검사 직후, 부모의 status가 `closed`가 아니면 거부하는 게이트를 추가한다:
   ```python
   for p in args.parent:
       if "/" in p:
           raise ChainError(f"parent '{p}'는 로컬 id여야 한다 (R3)")
       if p not in ids:
           raise ChainError(f"parent '{p}'가 체인 '{args.chain}'에 없다 (R6 위반 예정)")
       if status_by_id.get(p) != "closed":   # C097 — 열린 부모의 자식 차단
           raise ChainError(
               f"부모 '{p}'가 아직 닫히지 않았다 (status: {status_by_id.get(p)}) — "
               f"열린 부모 위에 자식을 열 수 없다.\n"
               f"      부모를 먼저 닫거나(gil close), 정말 갈래를 나누려면 이미 닫힌 사이클을 --parent로 지정하라.")
   ```
   - **위치의 정당성**: 이 루프는 이미 "사전 검증 — 저장소를 건드리기 전에 전부 확인" 블록 안에 있다(디렉토리 생성·번호 예약 소비 이전). 여기서 raise하면 거부가 **원자적**(kill 조건 3)이다.
   - **왜 `!= "closed"`이지 `== "open"`이 아닌가**: status가 open/closed 외의 값(rejected 등 향후)일 수도 있고, 파싱 실패로 None일 수도 있다. "닫힘만 부모 자격"이 안전한 화이트리스트다. rejected(죽은 가지)를 부모로 삼는 것도 막힌다 — 죽은 가지에서 자라면 안 되므로 옳다.

2. **에러 문안**은 원인(어느 부모가·왜=열림/현 status)과 대안 둘(부모를 닫아라 / 닫힌 사이클로 분기하라)을 함께 준다 (kill 조건 5, C003 "금지는 대안과 함께").

### Go parity (go/main.go)

3. 참조와 동형으로 `cmdOpen`의 parent 검증 루프에 같은 게이트를 이식한다. 부모 레코드의 status를 읽어 "closed"가 아니면 같은 취지의 에러로 거부. (C094 교훈 "parity 이월 금지" 실천 — 이 사이클 안에서 즉시.)

### conformance

4. `conformance.py`에 신규 판정 항목 **OPEN-PARENT-CLOSED-GATE**를 추가한다:
   - 픽스처: 체인에 열린 사이클 1개(open) + 닫힌 사이클 1개(closed) 준비.
   - PASS 기준: 열린 사이클을 `--parent`로 준 open이 **exit≠0 + 저장소 무변화**, 닫힌 사이클을 `--parent`로 준 open은 **성공**.
   - 종료 코드·파일·산출물만 관찰(§7 계약: 문면 아닌 행동).

## 준비물

- 참조 구현: `rooms/deployment/ariadne-spec/gil.py` (현 v2.44.0 기반). 이 환경 PATH에 gil 없음 → `python3 …/gil.py`로 호출.
- Go: `rooms/deployment/ariadne-spec/go/` — 세션-로컬 격리 빌드(공유 `/tmp/gil-go` 병렬 충돌 함정, loomlight/C003 교훈). `go build`.
- conformance: `rooms/deployment/ariadne-spec/conformance.py`, `--gil "python3 …/gil.py"` 주입.
- CI 재현: `/tmp/gilbin/gil`(python3 절대경로 래퍼)를 PATH·--gil로 (C092 교훈 — 로컬 통과≠CI 통과, gil 실제 실행 CI만 잡는 회귀 존재).

## 측정 방법

step 3에서 5측정 (kill 조건 1:1 대응):

| # | 측정 | 성공 기준 |
|---|---|---|
| M1 | 열린 부모로 open (직접 + conformance) | exit≠0, 저장소 무변화 |
| M2 | 정상 4흐름(닫힌 부모 자식·new-root·new-chain·다중부모 전부닫힘) | 전부 성공 |
| M3 | 거부 원자성 (스냅샷 해시 전후 대조) | 해시 동일 |
| M4 | 회귀 — 참조 conformance | ≥124 (기존 123 + OPEN-PARENT-CLOSED-GATE 1) |
| M5 | 거부 메시지 실출력 | 부모 id·현 status·대안 둘 포함 |
| M6 | Go parity — Go conformance + Go 게이트 실출력 | Go 총점 유지+1, Go도 열린부모 거부 |

## 사용자 컨펌

- 생략 — 상현님이 전권 위임(2026-07-14 "사이클을 멈추지 말고 계속") + 이번 세션 갈림길(A 범위: "A1만 먼저, 별도 사이클로")을 이미 AskUserQuestion으로 확정. 설계는 그 결정의 직접 실행이라 추가 컨펌 불필요.

- [x] 컨펌 받음 (일자: 2026-07-20, A 범위 분기 결정으로 갈음)
