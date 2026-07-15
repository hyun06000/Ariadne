# 3. 가설 검증 — 라운드를 1급 시민으로

두 구현(참조 `gil.py`, Go `go/main.go`)과 판정기 `conformance.py`에 대해 검증한다.
재현 스크립트는 `reproduce.sh` (이 디렉토리).

## 재현 방법

### 불변 기준 (시점 무관 — 바이트 대조 가능)

판정기는 자기 샌드박스를 스스로 만들므로 저장소 성장과 무관하다. 아래는 **항상** 같은 결과여야 한다:

```bash
cd rooms/deployment/ariadne-spec
GIL=$(pwd)/gil.py                        # ★ 절대 경로 — --gil 상대 경로는 각 샌드박스 cwd에서 깨진다 (C028·C043)
python3 conformance.py --gil "python3 $GIL"    # 참조: 72/72
go build -o /tmp/gil-go go/main.go
python3 conformance.py --gil "/tmp/gil-go"     # Go: 56/56 (round 미구현 — HELP-COMPLETE가 정직한 부재를 판정)
```

- **참조 구현 72/72** (기존 64 + 라운드 8: ROUND-OPEN·ROUND-PREREG·ROUND-OPEN-GIT·ROUND-CLOSE-VERDICT·ROUND-REJECT-VOCAB·ROUND-CLOSED-CYCLE·ROUND-LIST-SAFE·FSCK-R15). 회귀 0.
- **Go 56/56** — `round`를 구현하지 않지만 `gil:commands`에 나열하지 않아 정직하다. `HELP-COMPLETE`가 Go가 `round`에 exit 3을 내는지 판정한다. Weft가 이식하면 목표 72/72가 데이터로 서 있다 (C043 패턴: 새 표면을 계약에 적는 같은 커밋에서 판정기에도).

### 변이 격추 (각 조항을 다른 방어선이 침묵하는 입력으로 — C011·C041)

| 변이 | 내용 | 잡는 항목 | 결과 |
|---|---|---|---|
| M1 | `round --open`이 `verification/`도 생성 (사전등록 위반) | ROUND-PREREG | 격추 ✔ |
| M2 | close의 verdict 어휘 검사 제거 | ROUND-REJECT-VOCAB | **생존** (심층 방어: fsck R15가 대신 집행) |
| M2-both | close 검사 **+** R15 verdict 검사 **둘 다** 제거 | ROUND-REJECT-VOCAB | 격추 ✔ — 계약이 실제로 판정됨이 증명 |
| M3 | fsck R15의 hypothesis.md 존재 검사 제거 | FSCK-R15 | 격추 ✔ |
| M4 | 무라운드에도 web JSON에 `rounds:1` 무조건 삽입 | 두 구현 cross-check | 격추 ✔ (무라운드 산출물이 Go와 갈라짐) |

**M2의 생존은 결함이 아니라 C011의 동등 변이 재현이다** — close의 어휘 검사를 지워도 `_fsck_or_report`가 R15로 잡아 롤백하므로 최종 행동(거부+무변화)이 보존된다. 판정기는 구현이 아니라 **행동**을 판정한다(§7). M2-both가 두 방어선을 다 지우면 ROUND-REJECT-VOCAB이 FAIL(bogus 수용)하여, 계약이 진짜로 판정됨을 증명한다.

### 가변 확인 (실 저장소 — 시점 의존)

우리 저장소는 라운드를 쓰지 않는다(무라운드). H3(하위호환)의 실증:

```bash
ROOT=$(pwd)/../../experiment/chains   # 절대 경로
python3 gil.py web "$ROOT" -o /tmp/ref.html --title T
/tmp/gil-go   web "$ROOT" -o /tmp/go.html  --title T
cmp /tmp/ref.html /tmp/go.html        # 바이트 동일 — rounds 필드가 무라운드 산출물을 안 건드린다
```

- **무라운드 web 바이트 동일** ✔ (참조 = Go). `rounds` 키는 `rounds>1`일 때만 JSON에 들어간다(C043 "낡을 수 있는 것은 있을 때만").
- **선재 드리프트(C045 무관)**: `fsck` stdout에서 경고 요약의 위치가 두 구현 간 다르다(참조는 위, Go는 아래). C045 이전 참조(HEAD~2)에서도 그랬다 — **렌더 차이이지 계약 위반이 아니다**(C021, §3.1: 계약면은 exit code·web JSON). C044가 남긴 이슈 후보 (B)와 같은 계열.

## 실행 기록

- 환경: macOS(darwin 25.2.0), Python 3, Go(표준 라이브러리), 2026-07-15.
- 결과: 참조 72/72, Go 56/56, 변이 M1·M3·M4 격추 + M2 심층방어 생존(M2-both로 계약 판정 증명), 무라운드 web 바이트 동일.
- 특이사항: 첫 conformance 실행이 대량 FAIL — 범인은 `--gil "python3 gil.py"`의 **상대 경로**(각 샌드박스 cwd에서 gil.py 못 찾음). C028·C043이 이미 문서화한 함정. 절대 경로로 전량 통과. **여섯 번째 "테스트를 먼저 의심하라"**(C016·C021·C029·C035·C036 계열).
