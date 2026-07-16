# 3. 가설 검증 — 산출물과 재현 절차

설계 A·B·C 실행 기록. 환경: macOS(darwin 25.2.0, arm64), Python 3, Go(표준 라이브러리),
pwsh 7.7.0-preview.2(sudo 없이 .pkg 페이로드 추출), 2026-07-16.

## 파일

| 파일 | 내용 |
|---|---|
| `env.txt` | pwsh 버전 |
| `gate-normal.txt` | [A-1] 정상 경로 — 실제 v2.14.0 자산으로 `want==got`, **gil.exe 생성** |
| `gate-mismatch.txt` | [A-2] 위조 체크섬 — `throw` + gil.exe 미생성 + gil-dl.exe 삭제 |
| `exec-boundary.txt` | [A-3] 실행 경계 — mac pwsh가 네이티브 PE 실행 불가(`kLSExecutableIncorrectFormat`) |
| `doc-fix.txt` | [B] README.ai.md diff — Windows 치환 규칙 1줄 |
| `darwin-conformance.txt` | [C] 동일 Go 소스 darwin conformance 76/76 |

## pwsh 확보 (sudo 없이 — C053의 "설치 실패"를 우회)

```sh
brew fetch --cask powershell@preview          # .pkg를 캐시에 다운로드 (설치 아님)
PKG=~/Library/Caches/Homebrew/Cask/powershell@preview--*.pkg
pkgutil --expand "$PKG" expanded
mkdir payload && (cd payload && cat ../expanded/component.pkg/Payload | gunzip -dc | cpio -id)
PWSH=payload/usr/local/microsoft/powershell/7-preview/pwsh
chmod +x "$PWSH" && "$PWSH" --version   # PowerShell 7.7.0-preview.2
```

## 게이트 재현 (README.ai.md 37–43줄 그대로, 실제 릴리스 자산 대상)

```powershell
Invoke-WebRequest https://github.com/hyun06000/Ariadne/releases/latest/download/gil-windows-amd64.exe -OutFile gil-dl.exe
Invoke-WebRequest https://github.com/hyun06000/Ariadne/releases/latest/download/SHA256SUMS -OutFile SHA256SUMS
$want = ((Select-String -Path SHA256SUMS -Pattern 'gil-windows-amd64\.exe$').Line -split '\s+')[0]
$got  = (Get-FileHash gil-dl.exe -Algorithm SHA256).Hash.ToLower()
if ($got -ne $want) { Remove-Item gil-dl.exe; throw "checksum mismatch" }
Move-Item -Force gil-dl.exe gil.exe    # 여기까지 진짜 pwsh에서 작동 확인
.\gil.exe help                          # ← 이 줄만 수신자(진짜 Windows) 몫
```

## 판정

| 가설 | 결과 |
|---|---|
| H1 (게이트 pwsh 런타임) | **지지** — 정상 경로 gil.exe 생성(want==got), 위조 throw+미생성. C053의 "이식 셸 동치"를 pwsh 실런타임으로 승격 |
| H2 (Step C 명령형) | **지지** — README.ai.md에 Windows 치환 규칙 1줄, 코드펜스 8(짝수)·구조 무손상, POSIX 안내 불변 |
| C (코드 정합) | **지지** — 동일 소스 darwin 76/76, 참조 76/76. Windows 바이너리는 이 소스의 크로스컴파일 |

**경계(수신자 몫, 흉내 금지)**: 네이티브 `gil.exe`의 실제 실행 — mac pwsh는 PE를 못 돌린다
(`kLSExecutableIncorrectFormat`). Windows 경로(`\`)·git 탐지 실환경 동작도 수신자 로그 대기.

이탈 0.
