# 1. 가설 수립

## 이전 사이클의 교훈 (loom/C053, Windows 진입)

C053(Windows 진입 B·C·D)은 릴리스에 `windows/amd64` 바이너리를 추가하고, README·README.ko에
PowerShell 설치+체크섬 게이트를 넣고, README.ai.md를 OS·git 인식으로 만들었다. 그러나
**pwsh 설치가 그 환경에서 안 돼**, 게이트의 안전속성만 **이식 셸로 동치 검증**하고
cmdlet 런타임+.exe 실행은 "진짜 Windows(수신자)로 이관"했다. C053 보고서:
*"못 하는 검증을 흉내내지 말고 할 수 있는 핵심을 확실히."* 그리고 남긴 후보 (C):
**Windows end-to-end 수신자 검증.**

이 사이클은 상현님의 실사용 계기("비개발자 Windows 친구에게 gil을 써보라고 넘기려 한다")에서
태어났다. 넘기기 전에 **우리 환경(비-Windows)에서 검증 가능한 최대치**를 확보하고, 남는 것을
수신자 경계로 정직히 못박는다 — 실사용 로그가 언제 올지 모르므로.

## 문제 분할

친구는 gil을 **자기 AI 에이전트에 물려서** 쓴다(gil의 설계 경로 — gateway 체인). 그럼
에이전트가 밟는 경로가 검증 대상이다:

1. **설치 게이트** — 에이전트가 README.ai.md의 PowerShell 블록을 실행: 다운로드 →
   체크섬 검증 → 통과 시에만 `gil.exe` 생성. C053은 이 cmdlet 런타임을 검증 못 했다.
2. **첫 실행 이후 명령형** — Step C의 사이클 명령 예시가 `./gil …`(POSIX 형)이다.
   Windows에서 바이너리는 `gil.exe`이고 에이전트는 `.\gil.exe …`로 호출해야 한다.
3. **.exe 실제 실행** — 네이티브 Windows PE의 실행. 이것만은 진짜 Windows(또는 에뮬레이션)가
   필요한 수신자 경계.

### 관찰 (실측 — C007)

이번엔 **pwsh를 sudo 없이 확보했다**: brew가 받은 `powershell@preview` .pkg를
`pkgutil --expand` + cpio로 풀어 `pwsh 7.7.0-preview.2` 바이너리를 로컬 추출·실행.
C053의 "설치 실패"는 sudo가 필요한 .pkg 설치였고, 페이로드 추출로 우회했다.

실제 pwsh로 README.ai.md의 게이트 블록을 실행:

| 경로 | 결과 |
|---|---|
| 정상(실제 릴리스 자산) | `Invoke-WebRequest` 다운로드 → `Select-String`+regex로 want 추출 → `Get-FileHash`로 got 산출 → 일치 → `Move-Item`으로 **gil.exe 생성** |
| 위조 체크섬 | `got≠want` → `throw "checksum mismatch"` → **gil.exe 미생성** + gil-dl.exe 삭제 |
| .exe 실행(mac) | `kLSExecutableIncorrectFormat` — 네이티브 PE는 mac pwsh에서 실행 불가(수신자 경계) |

게이트 블록의 cmdlet 문법·해시 파싱·안전속성이 **진짜 PowerShell 런타임에서** 작동한다.
C053이 이식 셸로만 봤던 것을 이제 pwsh 자체로 봤다.

## 가설

> **가설 (H1)**: README·README.ai.md의 PowerShell 설치 게이트는 **진짜 pwsh 런타임에서
> 그대로 작동**한다 — 정상 경로는 실제 릴리스 자산으로 gil.exe를 만들고, 위조 체크섬은
> throw하며 gil.exe를 만들지 않는다. (C053의 "이식 셸 동치"를 pwsh 실런타임으로 승격.)

> **가설 (H2)**: README.ai.md Step C의 명령형이 POSIX `./gil` 단일 형이라 Windows
> 에이전트에게 모호하다. **Windows에서 `.\gil.exe`를 쓰라는 명시**를 더하면 (PATHEXT
> 자동 해석에 의존하지 않고) 에이전트 경로가 OS-완전해진다.

## 기각 조건

- 게이트 블록이 실제 pwsh에서 실패하거나(정상 경로에서 gil.exe 미생성), 위조 체크섬을
  통과시키면 (H1 실패).
- .exe 실행 경계가 우리 환경에서 실제로 넘어가면(= 검증 가능) 오히려 좋음(경계 재정의).
- Step C 명시 추가가 기존 POSIX 안내를 훼손하거나 문서 링크·구조를 깨면 (H2 실패).

## 이 사이클의 경계 (정직한 못박기)

- **검증 가능(우리 몫)**: 설치 게이트 런타임(pwsh), 문서 OS-완전성, 바이너리 유효성
  (PE32+·체크섬), 코드 정확성(darwin/linux conformance 76/76 — Windows 바이너리는 동일
  소스 크로스컴파일).
- **수신자 몫(친구·실 Windows)**: 네이티브 gil.exe의 실제 실행, Windows 경로(`\`)·git
  탐지의 실환경 동작. 이건 흉내내지 않고 로그를 기다린다(C053 규율).
