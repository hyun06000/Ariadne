# 3. 검증 — gil web v3 뷰어를 배포판에 통합 ("v3만 쓴다"의 읽기 축 완성)

C027이 v3 눈의 뿌리(`gil migrate`)를 배포판에 통합했다. 이 카브는 읽기 축인 **Sheen C025 통합 뷰어를 `gil web --v3`로 배포판 gil.py에 통합**한다 — 이걸로 배포판 gil이 v3 쓰기(migrate)와 읽기(web)를 다 갖춰 "v3만 쓴다"의 도구 기반이 완성된다.

## ⭐ 통합 전략 — C027 이식 패턴 재사용, --v3 옵트인

배포판엔 이미 cmd_web(v2)이 있어 이름 충돌이 있다. 해소:
- **`gil web --v3` 옵트인 플래그** — 기본은 v2(하위호환), --v3면 순수 notes 두 층 드릴다운(C025). C026 형태("v3 = v2 위의 눈")에 정합.
- Sheen C025 백엔드(steptree 308 + notes_reconstruct 160 + web_render 308 + rebuild_cycle_dag ≈ 800줄)를 gil.py에 인라인 이식.
- **상수 접두어 _ST_(steptree)·_WR_(web_render)로 충돌 방지** — 두 모듈이 각각 CSS 상수를 가져 접두어 필수.
- notes_reconstruct의 `FLM.*`·`from splice_topology import short_id`는 C027이 이미 인라인한 함수로 직접 연결.

## 재현

```bash
python3 <배포판>/gil.py migrate <clone>          # notes 각인 (C027)
python3 <배포판>/gil.py web --v3 -o out.html     # v3 통합 뷰어 (cwd=저장소)
# 오라클 대조: C025 gilv3 web과 바이트 동일
```

## 산출물

- **`rooms/deployment/ariadne-spec/gil.py`** — v3 web 백엔드 인라인 + cmd_web `--v3` 분기 + argparse 플래그.
- C025판 백엔드(오라클) — 검증 대조용.
- `measure-out.txt` — 5측정.

## 5측정 (ALL PASS)

| 측정 | 확인 | 결과 |
|---|---|---|
| **M1 오라클 대조** | 배포판 gil web --v3 == C025 gilv3 web (digest 6bc9c7f2) | PASS |
| **M2 v2 무회귀** | 기본 gil web(--v3 없이) 통합 전후 바이트 불변 | PASS |
| **M3 conformance** | 134/134 ✔ 이 구현은 gil이다 (기존 명령 무회귀) | PASS |
| **M4 자기완결** | gil.py 격리 복사해도 web --v3 동작 — import 0 (SPEC §7) | PASS |
| **M5 드릴다운 구조** | HTML에 상위 계보 DAG + 하위 steptree-panel 두 층 | PASS |

## ⭐ 정점 결과 — "v3만 쓴다"의 도구 기반 완성

이제 배포판 gil이 **쓰기(gil migrate로 v3 눈 각인) + 읽기(gil web --v3로 두 층 드릴다운)** 를 다 갖췄다. 배포된 도구를 쓰는 누구나 자기 v2 원장을 v3로 각인하고 사람 눈으로 볼 수 있다(will.md 범용성). C027(뿌리)+C028(읽기)로 v3 눈이 하나의 gil에 온전히 들어왔다.

## ⭐ 교훈 — 이식의 스캐폴딩은 인라인에서 걷어낸다

이식 중 두 스캐폴딩을 수리했다: ① `from splice_topology import short_id`(C027이 이미 인라인) ② `sys.path.insert(0, HERE)`(모듈 로딩용, 인라인엔 불요) + rebuild_cycle_dag 함수 누락 인라인. **모듈로 살던 코드가 인라인되면 모듈 스캐폴딩(sys.path·상대 import)은 죽은 코드가 된다** — 오라클 대조(6bc9c7f2)와 자기완결 계약(M4)이 이걸 강제로 드러냈다. C027 "이식의 함정은 숨은 의존"의 짝: 이식의 함정은 죽은 스캐폴딩이기도 하다.

## 결론

**ALL PASS → supported.** `gil web --v3`가 배포판 gil.py에 통합됐다. 오라클 대조 바이트 동일(6bc9c7f2), v2 무회귀, conformance 134/134, 자기완결. **v3 눈의 읽기 축이 하나의 gil로 들어와 "v3만 쓴다"의 도구 기반이 완성됐다.**

## 정직한 경계

- **--v3 옵트인** — 기본은 v2(하위호환). v3 상시화는 나중 기본 전환(점진적).
- **격리 조회만** — 실제 원장 notes는 C022로 각인됨. web은 읽기 전용 생성.
- **CDP 헤드리스 재실측은 안 함** — Sheen C025가 이미 M4로 드릴다운 상호작용 실측. 이 카브는 이식 보존(바이트 동일)이 핵심, 상호작용은 C025 재사용이라 동형.
- **수리 2건**(스캐폴딩 제거·rebuild_cycle_dag 인라인) — 이식 결함, 로직 반증 아님. 오라클 대조 전 잡힘.
- **다음: SPEC/README v3 문서 갱신 + v3 정식 릴리스**(Selvage 축).
