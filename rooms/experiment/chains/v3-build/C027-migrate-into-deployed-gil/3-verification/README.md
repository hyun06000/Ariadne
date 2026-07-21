# 3. 검증 — gil migrate를 배포판 gil.py에 통합 (하나의 gil, 첫 카브)

C026이 "v3 = v2 위의 notes 눈"을 확정했고, 상현님이 "먼저 배포판 통합부터"를 지시했다. 이 카브는 v3 눈의 뿌리인 **`gil migrate`를 배포판 gil.py에 통합**한다 — gilv3(개발 격리명) 실험 산출물을 하나의 gil로.

## ⭐ 통합 방식 — 인라인 이식, 오라클 대조로 바이트 보존 집행

C023 검증 백엔드(derive_fingerprint·full_ledger_migrate·splice_topology·retro_imprint·snapshot, 28함수·321줄)를 배포판 gil.py에 **인라인**(외부 모듈 import 0 = SPEC §7 자기완결 배포 계약). 모듈 접두어(DF.·FLM.·RI.) 제거 외 **로직 무변경 — 재구현 아닌 이식**. 오라클 = C023 gilv3 migrate 출력. 배포판 `gil migrate`가 같은 것을 내면 통합이 로직을 보존.

## 재현

```bash
# 격리 복제본 2개: 오라클(gilv3) vs 배포판(gil)
python3 <C023>/gilv3.py migrate <cloneA>    # 오라클
python3 <배포판>/gil.py migrate <cloneB>    # 통합
# DAG·notes digest 대조 → 바이트 동일
python3 <배포판>/conformance.py --gil "python3 gil.py"   # 회귀 0
```

## 산출물

- **`rooms/deployment/ariadne-spec/gil.py`** — migrate 백엔드 인라인 + `cmd_migrate` + argparse 등록. hashlib·glob import 추가.
- C023판 오라클 스크립트(`gilv3.py`·백엔드) — 검증 대조용.
- `measure-out.txt` — 5측정 결과.

## 5측정 (ALL PASS)

| 측정 | 확인 | 결과 |
|---|---|---|
| **M1 오라클 대조** | 배포판 gil migrate DAG(136엣지·머지4) == C023 gilv3 migrate | PASS |
| **M2 notes 바이트 동일** | notes 본문 digest 오라클 743fc56a == 배포판 743fc56a | PASS |
| **M3 계약 보존** | --dry 각인0·--rollback 잔재0·커밋·cycle.yaml 불변(C018) | PASS |
| **M4 회귀 0** | conformance 134/134 ✔ 이 구현은 gil이다 (기존 명령 무회귀) | PASS |
| **M5 자기완결** | gil.py 격리 복사해도 migrate 동작 — 외부 모듈 import 0 (SPEC §7) | PASS |

## ⭐ 정점 결과 — v3 눈의 뿌리가 하나의 gil로 들어왔다

이제 배포판 gil이 `gil migrate`로 v3 눈(notes 스텝 트리·계보)을 각인한다. 배포된 도구를 쓰는 누구나 자기 v2 원장을 v3로 볼 수 있다(will.md 범용성). C023 "명령화의 값어치는 재사용, 전제는 동작 보존"이 배포 층에서 완성 — 오라클 대조 바이트 동일(743fc56a)이 이식이 로직을 안 바꿈을 집행, conformance 134/134가 배포판 무결성을 지킴.

## ⭐ 교훈 — 인라인은 재구현이 아니다, 이식이다

자기완결 배포 계약(SPEC §7: 단일 파일) 때문에 백엔드를 gil.py에 인라인했으나, **함수를 옮겼을 뿐 알고리즘을 재설계하지 않았다.** 오라클 대조가 이 구분을 집행 — 만약 재구현이었다면 743fc56a가 안 맞았을 것. 자동 추출(함수 블록 + 접두어 제거)이 이식의 기계적 정확성을 보장했다.

## 결론

**ALL PASS → supported.** `gil migrate`가 배포판 gil.py에 통합됐다. 오라클 대조로 C023 결과 바이트 보존, conformance 134/134로 회귀 0, 자기완결 배포 계약 유지. **v3 눈의 뿌리가 하나의 gil로 들어왔다** — 다음 카브(web 뷰어 통합) 위에서 "v3만 쓴다"가 완성된다.

## 정직한 경계

- **web 뷰어 통합은 다음 카브** — 이 사이클은 migrate만(범위 절제). Sheen C025 web을 배포판에 통합하면 읽기 축도 하나의 gil.
- **격리 조회만** — 실제 원장은 이미 C022로 각인됨. 이 사이클은 통합 검증.
- **수리 1건**(hashlib·glob import 누락 — migrate 백엔드가 씀) — 이식 결함, 로직 반증 아님. 오라클 대조 전 잡힘.
- **도출실패 20 여전**(C024 정밀화 미통합) — migrate 통합이지 도출 완전성 아님. C024 정밀화를 migrate 백엔드에 넣으면 DAG 136→140.
