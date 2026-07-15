# 2. 실험 설계

## 절차

1. **B — 릴리스 워크플로에 Windows 타깃 추가** (.github/workflows/gil-release.yml):
   - 빌드 루프에 `windows/amd64` 추가. Windows는 `.exe` 확장자 필요 → GOOS가 windows면 `.exe` 접미사.
   - 산출물명 `gil-windows-amd64.exe`. `shasum -a 256 gil-*`가 SHA256SUMS에 자동 포함.
   - loom/C024 규율 보존: build run 블록은 신선 클론에서 추출 실행 가능해야 한다 → 검증은 이 블록을 그대로 darwin에서 실행해 5타깃 산출·유효 PE·SHA256SUMS 확인.
2. **C — PowerShell 설치 스니펫 + 체크섬 게이트** (README.md에 Windows 블록 추가):
   - `Invoke-WebRequest`로 `.exe`와 SHA256SUMS 다운로드.
   - `Get-FileHash -Algorithm SHA256`(대문자 hex) vs SHA256SUMS의 소문자 hex → 대소문자 무시 비교.
   - **게이트(C037 정신)**: 임시명으로 받아 **일치할 때만 `gil.exe`로 승격**, 불일치면 삭제 → 검증 안 된 바이너리는 `gil.exe`로 **태어나지 못한다**. `.\gil.exe`가 없으면 실행에 닿지 못한다.
3. **D — README.ai.md OS·git 인식 온보딩**: LLM이 (a) OS 판별(darwin/linux/windows), (b) git 가용성 확인, (c) 알맞은 설치 스니펫 선택을 하도록 명령형 지시 추가. gil이 git 없이도 도는 것(C052)과 Windows 설치(C)를 안내.
4. **검증**: B는 build 블록 추출 실행(5타깃·PE·SHA256SUMS). C는 **pwsh(PowerShell Core)로 게이트 로직 실행** — 로컬 크로스컴파일 `.exe`와 로컬 SHA256SUMS로 (a) 일치→승격, (b) 위조→삭제·거부 두 경로. D는 링크 해소·구조. 기존 4타깃/Unix 경로 회귀 0.

## 준비물
- Go1.26(크로스컴파일), `pwsh`(PowerShell Core, 게이트 로직 실측용 — Get-FileHash/Invoke-WebRequest/Select-String은 Windows PowerShell과 동일 cmdlet).
- 기존 SHA256SUMS 포맷: `<64hex소문자>  <파일명>` (`shasum -a 256`).

## 측정 방법 — 기대 행동

| # | 자극 | 기대 |
|---|---|---|
| B1 | 수정된 build 블록 darwin 실행 | dist에 5개(기존4+windows.exe), `gil-windows-amd64.exe`=유효 PE32+ |
| B2 | SHA256SUMS | `gil-windows-amd64.exe` 줄 포함 |
| C1 | pwsh 게이트 × 정상 .exe+정확한 SHA256SUMS | `gil.exe` 승격, rc 0 |
| C2 | pwsh 게이트 × 위조 해시(1바이트 변조) | `gil.exe` **미생성**, 오류·비영 종료 (게이트 작동) |
| D1 | README.ai.md 링크·명령 | 링크 해소, OS·git 분기 존재 |
| R | 기존 Unix 설치 스니펫·4타깃 | 불변 (회귀 0) |

성공: **B1·B2 산출 ∧ C1 승격 ∧ C2 차단 ∧ D1 일관 ∧ R 회귀 0.** C1(정상 통과)과 C2(위조 차단)이 함께 서야 게이트가 계약이다(C038 쌍 검증). Windows **런타임**(실제 PC의 .exe 실행)은 사전 등록된 수신자 검증 경계.

## 사용자 컨펌
- [x] 착수 승인 (2026-07-15, "일단 가보자"). 스코프 B·C·D 아크. 세부는 전권 위임(C008). Windows 런타임 검증이 수신자(상현님/친구) 몫임을 사전 명시.
