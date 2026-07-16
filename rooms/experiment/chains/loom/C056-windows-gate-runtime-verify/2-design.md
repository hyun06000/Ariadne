# 2. 실험 설계

H1(설치 게이트 pwsh 런타임 검증)과 H2(Step C 명령형 OS-완전화)를 하나의 절차로.

## 준비물

- **pwsh 확보 (sudo 없이)**: `brew fetch --cask powershell@preview`로 .pkg 캐시 →
  `pkgutil --expand` → `component.pkg/Payload`를 cpio로 풀어
  `usr/local/microsoft/powershell/7-preview/pwsh` 추출·chmod +x. 확인: `pwsh --version`.
- 실제 릴리스 자산: `v2.14.0`의 `gil-windows-amd64.exe`(PE32+, 4,493,824 bytes)와 `SHA256SUMS`.
- 문서: `README.ai.md`(에이전트 경로), 대조용 `README.md`·`README.ko.md`.
- 산출물 격리: 모든 pwsh 실행은 스크래치패드에. 원 저장소는 사이클 문서 + 문서 수정만 커밋.

## 절차

### A. 설치 게이트 런타임 검증 (H1)

1. **정상 경로**: pwsh로 README.ai.md의 PowerShell 블록(37–43줄)을 그대로 실행 —
   `Invoke-WebRequest`로 .exe·SHA256SUMS 다운로드, `Select-String`+regex로 want,
   `Get-FileHash`로 got, 일치 시 `Move-Item`으로 gil.exe. **성공 = gil.exe 생성 ∧ want==got**.
2. **안전속성(위조 체크섬)**: 틀린 해시의 SHA256SUMS + 임의 파일로 같은 게이트 실행 —
   **성공 = throw 발생 ∧ gil.exe 미생성 ∧ gil-dl.exe 삭제**.
3. **실행 경계 확인**: pwsh(mac)에서 `.\gil.exe help` 시도 — 네이티브 PE라 실패 예상
   (`kLSExecutableIncorrectFormat`). 이 실패는 **수신자 경계의 증거**로 기록(결함 아님).
4. 세 실행의 출력을 3-verification/에 로그로 저장.

### B. Step C 명령형 OS-완전화 (H2)

5. README.ai.md에 **Windows 명령형 명시**를 추가한다. 설계 판단: 명령 예시를 전부
   이중 표기하면 문서가 비대해지므로, **Step C 진입부에 한 줄 규칙**을 둔다 —
   *"On Windows the binary is `gil.exe`; run `.\gil.exe …` wherever this guide writes `./gil …`."*
   기존 POSIX 예시(`./gil …`)는 그대로 두고, 치환 규칙 한 줄로 OS-완전. install 단계가
   이미 OS-분기(34줄)하는 문서 스타일과 일관.
6. 문서 무결성 확인: 링크·코드펜스·구조 훼손 없음. `git diff`로 추가가 한 줄 규칙 +
   최소 문맥임을 확인.

### C. 코드·바이너리 정합 재확인 (경계 명료화, 회귀 방지)

7. 동일 Go 소스가 darwin에서 conformance **76/76**임을 재확인(Windows 바이너리는 이
   소스의 크로스컴파일 — "코드 정확성"은 여기서 서고, "이 PE의 실행"만 수신자 몫).
8. 공개 URL의 `gil-windows-amd64.exe` 체크섬이 `SHA256SUMS`와 일치함을 재확인(A-1에 포함).

## 측정 방법

| 가설 | 측정 | 성공 기준 | 기각 기준 |
|---|---|---|---|
| H1 | 정상 경로 (실제 자산) | gil.exe 생성 ∧ want==got | gil.exe 미생성 |
| H1 | 위조 체크섬 | throw ∧ gil.exe 미생성 | 위조가 gil.exe 생성 |
| H1(경계) | .exe 실행(mac) | 실패(PE 경계 확인) | — (넘어가면 경계 재정의) |
| H2 | README.ai.md diff | Windows 치환 규칙 1줄, 구조 무손상 | 링크·펜스·POSIX 안내 훼손 |
| C | darwin conformance | 76/76 | 회귀 |

## 사용자 컨펌

- 생략 — 상현님 전권 위임(C008) + 이 사이클은 상현님이 방금 지시한 "우리가 할 수 있는
  걸 해두자"의 직접 이행. 문서 수정은 순수 명료화(POSIX 안내 불변).

- [x] 컨펌 갈음 (지시 직접 이행 + 전권 위임)
