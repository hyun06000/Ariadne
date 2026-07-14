# 3. 가설 검증

전방 포인터(`superseded_by`)가 ① fsck로 검증되고 ② 불변성을 깨지 않으며 ③ log·web에 보이고
④ 두 구현이 같은 판정을 내리는지를, 결(Gyeol)의 이슈 #6 시나리오 그대로 재현해 확인한다.

## 재현 방법

```bash
# 저장소 루트에서
bash rooms/experiment/chains/loom/C035-superseded-pointer/3-verification/run.sh
# 종료 코드 0 = 기대 행동 24건 전부 통과. 산출물은 runs/ 아래에 남는다.
```

스크립트는 임시 디렉토리에 깃 저장소를 새로 만들고, **두 구현(참조 `gil.py` / Go 바이너리)에 각각**
같은 시나리오를 처음부터 걸어 산출물을 남긴 뒤 대조한다 (`runs/ref/`, `runs/go/`).
Go 바이너리는 배포 패키지의 `go/`에서 자동 빌드된다 (`GIL_GO=/path/to/gil`로 대체 가능).

시나리오 = 이슈 #6의 상황 그 자체:

1. `bench/C001-dirty` 개설 → 보고서 작성 → `close --verdict supported` (커밋 + 태그 각인)
2. 오염 발견 → `bench/C002-clean` 개설(parent: C001-dirty) → 닫음
3. `gil supersede bench/C001-dirty bench/C002-clean` — 닫힌 사이클에 전방 포인터 각인
4. verify / fsck / log / web으로 관측, R11 음성 케이스 주입, supersede 거부 경로 확인

## 기대 행동과 결과 (2026-07-15 실행)

| # | 기대 행동 | 결과 |
|---|---|---|
| T1a | `superseded_by`가 유령 사이클을 가리키면 fsck R11 위반 (rc 1) | ✅ |
| T1b | 자기 자신을 가리키면 R11 위반 | ✅ |
| T1c | 로컬 id 표기(`C002-clean`)도 같은 체인에서 해소되면 통과 | ✅ |
| T1d | `supersede`가 실재하지 않는 대체 사이클을 거부 | ✅ |
| T1e | `supersede`가 자기 자신으로의 대체를 거부 | ✅ |
| T1f | 거부 시 저장소 무변화 (HEAD·cycle.yaml·작업 트리 = 기준선) | ✅ |
| T2a·b | supersede 후에도 `verify` 무변조 판정 (두 구현) | ✅ |
| T2c | 이주 커밋이 `[migrate]` 접두어를 갖는다 | ✅ |
| T2d | 태그가 이주 커밋으로 이동하고 사유를 남긴다 (C004 태그 이동 규약) | ✅ |
| T2e | 5스텝 문서·산출물 해시 불변 — 변한 것은 `cycle.yaml` 한 줄뿐 | ✅ |
| T3a | `log`에 `↣ superseded: bench/C002-clean` | ✅ |
| T3b·c | `web`에 무효화 간선(`class="supersede"`)과 흐린 노드(`class="superseded"`) | ✅ |
| T3d | 내장 JSON(`gil-data`)에 `"superseded_by": "bench/C002-clean"` | ✅ |
| T3e | web 외부 리소스 0 (자기완결성 유지) | ✅ |
| T4a | 두 구현의 `cycle.yaml` 동일 | ✅ |
| T4b | 두 구현의 log `superseded` 표기 동일 (렌더 전문은 계약이 아니다 — SPEC §3.1) | ✅ |
| T4c | 두 구현의 web HTML **바이트 동일** | ✅ |
| T4d | 두 구현의 `[migrate]` 커밋 메시지 동일 | ✅ |
| T4e·f | Go의 R11 판정·supersede 거부가 참조 구현과 동일 | ✅ |
| T5a·b | conformance 26/26 (참조·Go) — 기존 계약 무회귀 | ✅ |

**합계: 24/24 통과, 실패 0.**

## 실행 기록

- 일시: 2026-07-15 / 환경: macOS (darwin 25.2.0), Python 3, Go 1.x, git 2.x
- 산출물: `runs/ref/`(참조 구현), `runs/go/`(Go 구현), `runs/21·22-conformance-*.txt`
- `runs/issue-6.txt`: 원 제보(결의 이슈 #6) 사본 — 이 사이클의 입력 데이터

### 실행 중 발생한 특이사항

- **하네스가 먼저 틀렸다**: 초기 단언 중 "거부 시 작업 트리가 비어 있다"가 실패했는데, 원인은 구현이
  아니라 테스트였다. `open --new-chain`이 만든 `bench/chain.md`는 close가 커밋하지 않으므로(close는
  사이클 디렉토리만 커밋한다) 작업 트리는 원래부터 비어 있지 않다. 무변화의 기준을 "비어 있음"이 아니라
  **"기준선과 같음"**으로 고쳐 잡았다 — loom/C016·C021·C029에 이은 네 번째 "테스트를 먼저 의심하라".
- log 전문은 두 구현이 다르다(요약 섹션·레인 아트). 이는 loom/C021에서 **계약 밖**으로 규정한 렌더 차이이며,
  이 사이클은 계약면(파싱·판정·web 바이트·supersede 표기)만 대조한다.
