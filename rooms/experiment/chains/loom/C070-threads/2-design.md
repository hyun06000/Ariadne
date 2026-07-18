# 2. 실험 설계

## 절차

1. **참조 구현 — `cmd_threads(args)` in `gil.py`**:
   - `_scan_chains(chains_root, args.chain)`로 전 체인(또는 `--chain` 하나)의 레코드를 읽는다.
   - **열린 사이클**: 각 체인에서 `status == "open"` 이고 `id`가 있는 레코드를 수집 → `{chain, id, author, step, opened}`. id 오름차순.
   - **미소비 예약**: 각 체인 디렉토리에서 `_load_reservations(chain_dir)`를 읽고, **그 트리에 이미 `C{num:03d}-*` 사이클로 존재하지 않는** 예약만 수집 → `{chain, num, ref, for, slug, date}`. (num, chain) 오름차순. 이중계상 방지(가설 설계 선분).
   - `--json`이면 `{"reserved": [...], "open": [...], "reserved_count": N, "open_count": M}`를 `json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)`로. 아니면 사람용 렌더(계약 아님).
   - 종료 코드 0(조회는 부재도 정상). 루트 부재만 `_scan_chains`가 `ChainError`.
2. **argparse**: `sub.add_parser("threads", ...)` — 위치 인자 `chains_root`(기본 `rooms/experiment/chains`), `--chain`, `--json`. `set_defaults(func=cmd_threads)`. (log·fsck와 동형.)
3. **판정기 — `conformance.py`에 THREADS-\* 항목**(아래 측정 방법).
4. **SPEC §5 명령 표에 `threads` 행** 추가(문서 계약).
5. **회귀 확인**: 참조 구현 전체 conformance, `gil web` 바이트 동일(threads는 web 무관), fsck 위반 0.
6. **Go**: 정직한 부재 — Go에 threads 미구현. HELP-COMPLETE가 이를 판정(참조엔 있고 Go엔 없음 → Go 쪽 해당 항목 정직한 부재로 이월). C043 리듬.

## 준비물

- gil.py (참조 구현, 이 워크트리 브랜치 clew/loom-threads), Python 3.
- conformance.py (판정기).
- 실데이터: 이 저장소의 chains(genesis·loom·tapestry·loomlight·gateway 등) + `reservations.tsv`(현재 loom에 C070·C071·C072 = 이 세션 병렬 3트랙).
- 픽스처: 소비/미소비 예약과 열린/닫힌 사이클이 섞인 임시 체인 루트(판정기 결정론용).

## 측정 방법

판정기 THREADS-\* (종료 코드 + JSON 반환 집합만 관찰 — 렌더 무관, §7):

- **THREADS-JSON-SHAPE**: `gil threads --json`이 `reserved`·`open`·`*_count` 키를 가진 유효 JSON, 종료 0.
- **THREADS-RESERVED**: 미소비 예약이 있는 픽스처에서 그 예약이 `reserved`에 정확히(num·for·slug) 나온다.
- **THREADS-CONSUMED-EXCLUDED**: 예약 번호가 사이클로 존재하는(소비된) 픽스처에서 그 예약이 `reserved`에 **없다**(지어냄 방지, 기각조건 2).
- **THREADS-OPEN**: status=open 사이클이 `open`에 나오고, status=closed 사이클은 안 나온다.
- **THREADS-OPEN-MATCHES-SCAN**: threads의 `open` 집합 = 같은 트리에서 `_scan_chains`로 직접 센 open 집합(불일치 기각, 기각조건 1). 검증 산출물에서 대조.
- **THREADS-EMPTY**: 예약·열린 사이클이 0인 픽스처에서 `reserved==[]`·`open==[]`, 종료 0(빈 상태 정직).

기준값: 참조 구현이 THREADS-\* **전부 PASS**, 기존 항목 **회귀 0**(분모 증가는 회귀 아님). 변이(threads의 소비 필터 제거 → THREADS-CONSUMED-EXCLUDED FAIL) 격추로 판정기가 계약을 실제로 본다는 것 확인.

실증(계약 아닌 시연): 이 저장소 main에서 `gil threads`가 C070·C071·C072 예약을 "진행 중 병렬"로 반환 → 상현님 요청("뭐가 병렬로 도나")의 직접 응답을 스크린샷/출력으로 산출물에 보존.

## 사용자 컨펌

생략 — 상현님이 이번 세션 4트랙 병렬을 승인했고, threads는 그중 Clew 갈래로 전권 위임 범위. 단, 상현님의 이번 세션 요청("병렬 진행을 알 수 있게")을 헤드라인 유스케이스로 반영했고, 뷰어 배너는 별도 후속 스텝으로 명시(범위 밖).

- [x] 컨펌 받음 (일자: 2026-07-19, 4트랙 병렬 승인 + 병렬 가시성 요청 반영)
