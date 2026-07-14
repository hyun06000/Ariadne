# 2. 실험 설계

## 설계의 축 — 실행 가능성을 대조에 종속시킨다

설계를 고정하기 전에 두 형태를 실측했다(scratchpad):

| 형태 | macOS `shasum` | 비고 |
|---|---|---|
| A. `shasum -a 256 -c SHA256SUMS --ignore-missing` | OK (rc=0) | 짧다. 단 `--ignore-missing`은 GNU coreutils 8.25+ 의존 |
| B. `grep ' gil-<os>-<arch>$' SHA256SUMS \| shasum -a 256 -c -` | OK (rc=0) | 옵션 의존 없음. 리눅스 `sha256sum -c -`도 동일 |

**B를 채택한다** — 이식성이 옵션 지원에 걸리지 않는다 (C024의 교훈: 셸 이식성도 환경 계약이다).

### 핵심 발명: 불일치면 실행 파일이 *생기지 않는다*

`exit 1`로 차단하면 문제가 있다. 사람이 대화형 터미널에 복붙하면 **셸 세션이 죽는다**. 그렇다고 `exit`을 빼면 스크립트가 계속 흘러 실행에 도달한다.

해결: **`chmod +x`를 대조 통과에 종속**시킨다.

```bash
curl -fsSL -O .../gil-darwin-arm64      # 원본 파일명 그대로 받는다 (SUMS와 대조하려면 필수)
curl -fsSL -O .../SHA256SUMS
grep ' gil-darwin-arm64$' SHA256SUMS | shasum -a 256 -c - && mv gil-darwin-arm64 gil && chmod +x gil
```

대조가 실패하면 `&&` 체인이 끊겨 **`gil`이라는 실행 파일 자체가 존재하지 않는다.** 이후 `./gil …`은 "No such file"로 실패한다 — 검증되지 않은 바이너리가 실행되는 경로가 **구조적으로** 없다.

실측 (음성 테스트, scratchpad):

```
$ printf 'x' >> gil-darwin-arm64        # 1바이트 변조
$ grep ' gil-darwin-arm64$' SHA256SUMS | shasum -a 256 -c - && mv gil-darwin-arm64 gil && chmod +x gil
gil-darwin-arm64: FAILED
shasum: WARNING: 1 computed checksum did NOT match
rc=1
$ ls gil
ls: gil: No such file or directory     ← 실행 파일이 생기지 않았다
```

대화형 셸에서도 안전(터미널이 죽지 않음), 스크립트·CI에서도 안전(rc≠0). 한 형태가 두 맥락을 모두 만족한다.

## 절차

1. **문서층 — 설치 스니펫 4곳에 대조를 필수 단계로 박는다.**
   환경별로 해시 도구만 바꾸되(대문=macOS `shasum`, CI=`sha256sum`), **계약은 동일**하다: *받는다 → SUMS를 받는다 → 대조한다 → 통과해야만 실행 가능해진다.*
   - `README.md` (영어 대문, macOS arm64 고정)
   - `README.ko.md` (한국어 대문, 동일)
   - `README.ai.md` (에이전트 자율 온보딩 — os/arch 감지 + **재시도 안내**, E7)
   - `rooms/deployment/ariadne-spec/QUICKSTART.md` §0
   문구를 *"if you wish"* 에서 **"불일치하면 실행하지 말고 잠시 후 재시도하라"** 로 바꾼다 (릴리스 직후 창의 불일치는 일시적이므로 에이전트가 멈추지 않고 회복해야 한다).

2. **도구 산출물층 — `gil pages`가 생성하는 워크플로에 같은 대조를 넣는다.**
   - `gil.py` (`_PAGES_WORKFLOW` 부근, 864행)
   - `go/main.go` (동일 문자열, 1993행)
   러너는 `ubuntu-latest` 확정이므로 `sha256sum`을 쓴다. 불일치 시 `exit 1` → **CI 실패**(여기서는 exit이 옳다 — 비대화형이고, 실패해야 배포가 멈춘다).
   두 구현의 산출물은 **바이트 동일**해야 한다 (E5).

3. **검증 하네스를 사이클 산출물로 남긴다** (`3-verification/verify-install-gate.sh`):
   - 문서 4곳에서 설치 블록을 **추출해 실제로 실행** (C007·C027의 "문서가 곧 테스트")
   - 정상 릴리스 → 통과 + `gil` 실행 가능 (E2)
   - 변조 바이너리 → 거부 + `gil` 미생성 (E3)
   - `gil pages` 산출물에 대조 존재 + run 블록 추출 실행 (E4)
   - 양 구현 산출물 `diff` (E5)

4. **회귀 확인**: `conformance.py --gil …` 양 구현 26/26 (E6).

5. **릴리스**: 도구(gil.py·main.go) 변경이 있으므로 마이너 승격 → v1.10.0. `gil release`로 배포하고, 배포된 바이너리에 대해 **새 스니펫을 다시 실행**해 끝단을 실증한다 (C024·C027·C028의 반복 교훈: *배포·문서의 검증은 수신자 경로로 끝까지*).

## 준비물

- 실 릴리스: `https://github.com/hyun06000/Ariadne/releases/latest/download/` (현재 v1.9.0)
- 해시 도구: macOS `shasum -a 256` (perl), 리눅스 `sha256sum` (coreutils)
- SHA256SUMS 형식(실측): `<64자 해시>` + 공백 2개 + `<파일명>` + `\n` → grep 앵커는 `' gil-<os>-<arch>$'`
- 두 구현: `rooms/deployment/ariadne-spec/gil.py`, `.../go/main.go` (Go 빌드 필요)
- 판정기: `conformance.py` (26항목)

## 측정 방법

| # | 기준 | 판정값 |
|---|---|---|
| E1 | 4개 문서 블록이 대조 포함 + 불일치 시 비영 종료 | 추출·실행하여 rc 관찰 |
| E2 | 정상 릴리스에서 통과, `gil` 실행 가능 | `./gil version` rc=0 |
| E3 | 변조 시 거부, **`gil` 미생성** | rc≠0 **AND** `test ! -e gil` |
| E4 | pages 산출 워크플로에 대조 존재, 불일치 시 CI 실패 | 생성물 grep + run 블록 실행 |
| E5 | 두 구현 pages 산출물 바이트 동일 | `diff` → 무출력 |
| E6 | conformance 26/26 ×2 | 스위트 출력 |
| E7 | 스니펫에 재시도 안내 존재 | 문서 grep |

**기각**: E2 실패(거짓 양성 — 쓸모없는 문지기는 해로운 문지기다), E3 실패(장님 문지기), E5·E6 실패(§7 구현 독립 계약 위반).

## 범위 밖 — 그리고 그 이유 (병렬 작업 구획)

**`conformance.py`에 PAGES 판정 항목을 추가하지 않는다.** 산출물 규율이 판정 밖이면 다음 구현자가 체크섬 없는 pages를 만들고도 26/26을 받을 수 있다 — 이는 계약의 공백이 맞다. 그럼에도 이번 사이클에서 손대지 않는 이유:

- **Weft가 지금 `loom/C036`에서 `go/main.go`와 `conformance.py`를 만지고 있다** (이슈 #7, `open --git` 이식). 두 사이클이 동시에 판정 항목 수를 바꾸면 병합 시 항목 수와 문서의 "26/26" 표기가 함께 꼬인다.
- C015에서 확립한 소환자 수칙(구획·add 범위 명시)을 따른다. 나는 `main.go`의 **pages 워크플로 문자열만** 만지고, 그가 만지는 `cmdOpen`·`notImplemented` 영역은 건드리지 않는다.

→ **PAGES 계약화는 Weft 병합 후의 후속 사이클로 이월**한다. 공백으로 기록하고 보고서에 명시한다 (C009의 교훈: 보고서에 남긴 미검증 경로가 다음 가설의 생산 수단이다).

## 사용자 컨펌

생략 — 상현님의 전권 위임("사이클을 멈추지 말고 계속 돌려줘")과 이슈 전권 위임에 근거해 자율 진행한다. 이슈 #8은 외부 채택자(결)가 제기한 것으로 문제 정의가 이미 사용자 검증을 거쳤다.

- [x] 컨펌 갈음 (전권 위임, 2026-07-14)
