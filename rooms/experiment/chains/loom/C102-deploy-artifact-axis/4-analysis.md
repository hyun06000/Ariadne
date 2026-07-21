# 4. 결과 분석

## 판정: 채택(supported) — 필드 #27이 배포 홀드를 풀 수 있다

가설(배포 축을 artifact 키로 재정렬하면 #27 실배포를 gil로 관리) 채택. 다섯 kill 조건 통과.

| kill | 결과 |
|---|---|
| 1. #27 레코드 담기 | ✔ artifact·복수 source_cycles·kind·target·notes 왜곡 없이 기록 |
| 2. artifact당 live 1 | ✔ 재배포 시 직전 superseded, fsck R17이 artifact별로 잡음 |
| 3. 닫힌 소스 게이트 | ✔ rejected·없는 소스 무변화 거부(복수 순회로 계승) |
| 4. 회귀·두 몸 | ✔ 참조 133/133·Go 110/110 |
| 5. 그리디 | ✔ 5기능 동작 후 멈춤, 나머지 이월 |

## 데이터 직접 관찰

`gil deploy list pii-extract-api`가 실제로 보여준 것:
```
● pii-extract-api@v2.1.0  2026-07-21 [live] (api-spec)  소스: app/C003-c022  ↞2.0.0
· pii-extract-api@v2.0.0  2026-07-20 [superseded] (api-spec)  소스: app/C001-c020 app/C002-c021
```
필드가 #27에서 준 실배포 레코드가 gil 안에 그대로 산다 — artifact 이름·복수 소스·kind·supersede 체인·live 상태. "무엇이 라이브고, 언제 무엇으로 교체했고, 무엇으로 롤백하나"에 gil이 답한다. **이게 필드가 배포를 홀드한 이유의 해소다.**

## 예상과 달랐던 것

**Selvage 골격이 거의 그대로 재사용됐다.** 키 축(chain→artifact)만 바꿨을 뿐, 그의 로직(live 전이·supersede·단조증가·태그·닫힌소스 게이트·append-only·네임스페이스 분리)은 한 줄도 안 틀렸다. 그가 "chain 키"라는 실증 전 가정 위에 **올바른 불변식들**을 세워둔 덕이다. 봉인된 가장자리(Selvage)가 뼈대를 정확히 놓았고, 필드가 준 축으로 옮기기만 하면 됐다. **틀린 건 축이었지 구조가 아니었다** — 이게 C046에서 그가 내 산수를 고쳤듯, 이번엔 필드가 그의 축을 고친 것.

부차: `_bad_cut` 헬퍼가 복수 `--cycle` 검증에도 그대로 맞았다(첫 나쁜 소스에서 거부). 게이트가 소스별이라 복수여도 하나만 나빠도 전체 거부 — 옳다.

## 다음 (이월)
- **Go parity**: deploy 명령군 이식(현 exit 3 정직한 부재). 배포 축이 커졌으니 다음 큰 카브.
- **뷰어 통합**: Sheen web에 배포 계보(deployments.json 렌더). #18("배포 산출물 1급 시민")의 뷰어 절반.
- **태그↔json drift 게이트**: release C072의 배포판.
- **#26**(GitHub Release 미발행): 별개 인프라 이슈, 배포 축과 다름.
- **배포 규율(상현님)**: 이 배포축 사이클들(C101·C102)이 모였으니, 다음에 굵직하게 한 번 릴리스.

## 필드 응답 준비
#27에 "artifact 축으로 구현 완료, gil deploy cut/list/current/rollback + fsck R16/R17, 실배포 기록 가능"을 답할 수 있다. 단 Go 바이너리는 이월(참조 gil.py로 먼저).
