# 2. 실험 설계

가설: `gil close`에 rejected 경로(step 보존·5-report 완화·R9 예외)를 두면 미완 가지를 진실 왜곡 없이 그래프에 각인하고, 정상 완주 강제는 회귀 없이 유지된다.

## 설계 판단 — rejected close의 세 완화

`verdict == "rejected"`일 때만 세 강제를 완화한다. 완화의 기준은 상현님 결정(1-hypothesis):

1. **step 보존**: rejected면 `step: 5` 덮어쓰기를 **건너뛴다**. cycle.yaml의 현재 step(죽은 시점)이 그대로 남는다.
2. **5-report 완화 → "마지막 작성 step 실질"**: rejected면 5-report.md 강제 대신 **마지막으로 작성된 step 문서가 실질 내용을 가질 것**을 요구한다. 이미 있는 헬퍼 `_step_written(cycle_dir, n)`를 재사용 — cycle.yaml의 현재 step 값 N에 대해 `_step_written(cycle_dir, N)`이 참이어야 한다. 죽은 이유가 그 문서(또는 --notes)에 있게 강제(kill 4).
3. **R9 예외**: fsck R9를 "closed면 step5, 단 verdict=rejected면 step 1~5 허용"으로 개정.

**verdict 검증을 앞으로 당김**: 현재 close는 verdict를 로직 뒤쪽에서 파싱한다. rejected 분기를 위해 verdict 유효성 검사(`_VERDICTS` 확인)를 5-report 검사 **이전**으로 옮긴다. `is_rejected = (args.verdict == "rejected")` 플래그로 세 완화를 게이트.

## 절차 (참조 gil.py cmd_close)

1. 함수 앞부분(deviations 게이트 직후)에서 verdict를 미리 검증하고 `is_rejected` 플래그 계산. 잘못된 verdict는 여기서 거부(기존 검증 이동).
2. **5-report 블록 완화**:
   ```python
   if is_rejected:
       # 죽은 가지: 완주 안 함이 정상. 마지막 작성된 step 문서가 실질 내용을 가질 것(죽은 이유).
       cur_step = _cur_step(data)  # cycle.yaml의 현재 step (1~5), 파싱 실패 시 1
       if not _step_written(cycle_dir, cur_step):
           raise ChainError(
               f"{...}: rejected로 닫으려면 마지막 스텝({cur_step}) 문서에 죽은 이유를 남겨야 한다 "
               f"(미완이어도 왜 죽었는지는 기록한다).")
   else:
       ... 기존 5-report.md 존재+비스텁 검사 ...
   ```
3. **step 덮어쓰기 완화**: `if is_rejected:` 면 step 재작성 스킵. 아니면 기존 `step: 5`.
4. verdict 기록(이미 앞에서 검증했으니 값만 씀).
5. 사후 `_fsck_or_report` — R9 개정이 rejected+미완을 통과시켜야 한다.

## 절차 (fsck R9 개정, 참조+Go)

6. gil.py:413 / main.go:300 —
   ```python
   elif status == "closed" and int(step) != 5 and r.get("verdict") != "rejected":
       violations.append(("R9", ...))
   ```
   즉 **닫혔고 step≠5인데 rejected가 아니면** 위반. rejected면 미완 step 허용.

## 절차 (Go main.go cmdClose)

7. 참조와 동형: verdict 선검증 + `isRejected` 플래그 + 5-report 완화(`stepWritten` 재사용) + step 덮어쓰기 스킵.

## 절차 (conformance)

8. 신규 항목:
   - **CLOSE-REJECTED-INCOMPLETE**: step 1 사이클(1-hypothesis 실질 작성)을 `--verdict rejected`로 close → 성공 + cycle.yaml `step: 1` 보존 + `status: closed` + fsck 통과.
   - **CLOSE-REJECTED-NEEDS-REASON**: step 1인데 1-hypothesis가 스텁(미작성)이면 `--verdict rejected` close 거부 + 무변화 (죽음도 이유는 남긴다).
   - **CLOSE-NORMAL-STILL-STRICT**: verdict≠rejected(supported)면 미완 step close가 여전히 거부(5-report 없음) — 완화는 rejected에만.

## 준비물

- 참조: `rooms/deployment/ariadne-spec/gil.py` (v2.45.0). `python3 …/gil.py`.
- Go: 세션-로컬 격리 빌드(`/tmp/gil-go-c098`, `go mod init`). loomlight/C003 공유경로 함정 회피.
- conformance: `--gil` 주입. CI 재현: `/tmp/gilbin/gil`(python3 **절대경로** 래퍼, C097 함정 4).
- **releases 등 repo_root 의존 명령은 저장소 루트에서** (C097 함정 3).

## 측정 방법

| # | 측정 | 기준 (kill 대응) |
|---|---|---|
| M1 | step1 사이클 rejected close | 성공 + fsck 통과 (kill 1) |
| M2 | close 후 step 값 | `step: 1` 보존, 5 아님 (kill 2) |
| M3 | supported로 미완 close | 거부(5-report 요구 유지) (kill 3) |
| M4 | 스텁 step으로 rejected close | 거부 + 무변화 (kill 4) |
| M5 | 참조 conformance | ≥128 (125+신규 3) (kill 5) |
| M6 | Go parity | Go 총점 유지+3, 동일 행동 (kill 6) |
| M7 | 실 시나리오 | 임시 저장소에서 step1 rejected close 실행→cycle.yaml·fsck 육안 |

## 사용자 컨펌

- **컨펌 받음** — 설계의 두 핵심 갈림길(R9 방향=죽은시점 보존, 5-report=유연하게)을 상현님이 AskUserQuestion으로 직접 확정(2026-07-20). 나머지는 그 결정의 직접 구현.

- [x] 컨펌 받음 (일자: 2026-07-20)
