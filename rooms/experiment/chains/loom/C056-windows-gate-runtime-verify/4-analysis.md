# 4. 결과 분석

## 통계적 결과

| 측정 | 기준값 | 실측 | 판정 |
|---|---|---|---|
| 게이트 정상 경로 (pwsh) | gil.exe 생성 ∧ want==got | `want==got` (…ccd5a), gil.exe 생성 | H1 ✓ |
| 게이트 위조 체크섬 (pwsh) | throw ∧ gil.exe 미생성 | throw 발생, gil.exe NO, gil-dl.exe 삭제 | H1 ✓ |
| .exe 실행 (mac pwsh) | 실패(경계 확인) | `kLSExecutableIncorrectFormat` | 경계 확정 ✓ |
| README.ai.md 무결성 | 구조 무손상 | 코드펜스 8(짝수), +1 규칙줄, POSIX 불변 | H2 ✓ |
| darwin conformance | 76/76 | 76/76 (Go·참조 둘 다) | C ✓ |

기각 조건 미충족.

## 데이터 직접 관찰

**게이트가 진짜 PowerShell에서 돈다 — 흉내가 아니라.** C053은 pwsh를 못 구해
`Get-FileHash`/`Select-String`의 **안전속성만 이식 셸(bash)로 동치 검증**했다. 이번엔
`pkgutil --expand`로 .pkg 페이로드에서 pwsh 7.7 바이너리를 뽑아(설치 sudo 우회) README의
블록을 **문자 그대로** 실행했다. `Select-String -Pattern 'gil-windows-amd64\.exe$'`가
SHA256SUMS의 정확한 줄을 잡고, `-split '\s+'`가 해시를 떼고, `Get-FileHash …ToLower()`가
소문자 해시를 내고, `-ne` 비교가 성립했다. **cmdlet 문법 하나하나가 실제로 파싱·실행됐다.**

**위조 경로의 세 가지가 다 맞았다.** 틀린 해시를 넣으니 `throw`가 실제 예외를 던졌고
(pwsh 스택트레이스에 `checksum mismatch — nothing unverified runs`가 그대로), **gil.exe가
생기지 않았고**, `Remove-Item`이 gil-dl.exe를 지웠다. "검증 안 된 건 아무것도 실행 안 된다"는
말이 pwsh 런타임에서 사실로 확인됐다 — C037("검증돼야만 태어난다")의 PowerShell 실증.

**경계의 에러 메시지가 경계를 정확히 그린다.** `.\gil.exe help`는
`kLSExecutableIncorrectFormat: No compatible executable was found`로 실패했다. 이건
게이트의 결함이 아니라 **mac의 LaunchServices가 x86-64 PE를 못 여는 것** — 정확히
"여기까지가 우리 몫, 여기부터가 수신자 몫"의 물리적 선이다. gil.exe는 유효한 PE32+이고
(file 확인), 그 안의 코드는 동일 Go 소스가 darwin에서 76/76이다. 즉 **"코드가 옳은가"와
"이 PE가 이 OS에서 뜨는가"는 다른 질문**이고, 전자는 우리가, 후자는 친구가 답한다.

## 예상과 달랐던 것

**C053의 "설치 실패"는 설치의 실패가 아니라 sudo의 실패였다.** C053은 "캐스크 2종 exit 0이나
바이너리 미배치"로 기록했는데, 실제 막힌 지점은 .pkg가 `/usr/sbin/installer`로 시스템에
설치될 때의 sudo 암호 요구였다. **바이너리는 .pkg 안에 멀쩡히 있었고**, 페이로드만 뽑으면
됐다. 검증 도구가 "없다"가 아니라 "설치 경로가 막혔다"였던 것 — C007("전제는 확인하라")의
재판: 못 하는 줄 알았던 검증이 다른 경로로 가능했다. **C053의 정직한 이관이 틀린 건 아니나
(그땐 sudo 우회를 안 팠다), 이관한 것을 다음 사이클이 되찾을 수 있었다**(C050의 "다섯 번
이월된 매듭"과 같은 결: 경계는 고정이 아니다).

**문서 수정이 놀랍도록 작았다.** Step C 전체를 이중 표기할 뻔했으나, install 단계가 이미
OS-분기하는 스타일(34줄)을 보고 **치환 규칙 한 줄**로 족했다. 에이전트는 "`./gil`을
`.\gil.exe`로 바꿔라"는 지시를 적용할 수 있는 독자다 — 사람용 문서였다면 매 줄 이중
표기가 필요했겠지만, README.ai.md의 독자는 규칙을 일반화한다.

## 판정

**세 가설 모두 지지(supported), 이탈 0.** C053이 수신자로 이관했던 게이트 런타임을 우리
환경에서 되찾아 검증했고, Windows 에이전트 경로의 문서 갭(명령형)을 메웠다. 남은 것 —
네이티브 .exe 실행, Windows 경로·git 실환경 — 은 흉내 없이 수신자 로그를 기다린다.
넘기기 전 우리가 할 수 있는 것을 했다.
