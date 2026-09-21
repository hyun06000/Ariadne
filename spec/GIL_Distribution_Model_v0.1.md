# GIL Distribution Model v0.1

> 상태: Draft
> 범위: 비개발자가 플러그인 설치에서 GIL Monitor 사용 가능 상태까지 도달하는 배포·설치 계약
> 비범위: 특정 Store 심사 양식, 서명 서비스 사업자, Host SDK의 구체 API

---

## 1. 목적

GIL의 주 사용자는 터미널과 패키지 관리자를 다루는 개발자가 아니다. 사용자는 Codex·Claude
Desktop 같은 Agent Host에서 Agent와 협업하고, GIL의 복잡한 버전 Graph는 인간용 Monitor로
이해한다.

따라서 다음 상태는 완전한 설치가 아니다.

- 플러그인은 설치됐지만 인간이 Monitor를 열 수 없음
- inline 카드만 있어 대화가 길어지면 Monitor가 밀려남
- 사용자가 terminal command, port 또는 capability URL을 기억해야 함
- Companion 설치 뒤 사용자가 대화로 돌아와 설치 완료를 다시 설명해야 함

> **GIL 설치는 Agent가 GIL을 호출할 수 있고, 인간이 지속형 Monitor를 열 수 있을 때 완료된다.**

---

## 2. 설치 완료 조건

```text
GilInstallation
├─ agent_surface       ready | unavailable
└─ monitor_surface     persistent_host | native_companion | unavailable
```

- `agent_surface=ready` — 현재 Host에서 GIL의 typed action과 Manual을 사용할 수 있다.
- `monitor_surface=persistent_host` — Host가 실제로 지속되는 panel 또는 PiP에 공용 Monitor UI를
  표시한다.
- `monitor_surface=native_companion` — 설치된 GIL Companion이 같은 UI를 지속형 native window로
  표시한다.
- `monitor_surface=unavailable` — inline 미리보기나 text 출력만 가능한 상태다.

`agent_surface=ready`이면서 Monitor surface 둘 중 하나가 있어야 설치 완료다. inline UI, browser
fallback과 CLI text는 진단·복구 수단이며 지속형 Monitor를 대신하지 않는다.

---

## 3. 표면 선택 순서

```text
Plugin installed
  → persistent Host surface를 실제로 요청하고 결과를 확인
      ├─ persistent_host 확인됨 → 같은 Host에서 Monitor를 연다
      └─ 지원하지 않음·inline에 머묾·수명 계약 미달
           → Native Companion을 감지
               ├─ 호환판 설치됨 → 열거나 앞으로 가져온다
               ├─ 설치됐으나 낡음 → update를 제안한다
               └─ 없음 → 신뢰된 설치 경로를 제안한다
```

기능 이름이나 요청 성공만으로 PiP 지원을 추측하지 않는다. adapter는 실제 display mode와 수명
계약을 확인한다. PiP 요청 뒤 `inline`이면 `persistent_host`가 아니다.

PiP capability 판정은 실제 `ui://` MCP App에서 수행한다. 앱은 `ui/initialize`의
`appCapabilities.availableDisplayModes`에 자신이 지원하는 mode를 선언하고, adapter는 Host context가
광고한 목록, 사용자 동작에 묶인 mode 요청의 원문 반환값, mode 변경 event와 실제 surface 수명을
함께 기록한다. 이 네 증거가 없는 inline 진단은 Host의 PiP 지원 여부를 확정하지 못한다.

PiP와 Companion은 별도 Monitor 제품이 아니다. 둘은 같은 `MonitorViewV1`, `NodeDetailV1`, 공용
UI bundle과 presentation 규칙을 사용한다. 바뀌는 것은 수명과 packaging을 맡는 Host뿐이다.

---

## 4. 지속형 Host surface의 최소 계약

Native Companion을 생략하려면 Host surface가 다음을 모두 만족해야 한다.

1. 대화가 길어져도 메시지와 함께 밀려나지 않는다.
2. 사용자가 명시적으로 닫기 전까지 유지된다.
3. 다른 대화나 작업을 보고 돌아와도 같은 Project scope를 복구한다.
4. DAG 선택·접기·상세 Report interaction을 지원한다.
5. 완전한 `MonitorViewV1` 갱신을 받을 수 있다.
6. 현재 Project를 명시적으로 식별하며 cwd나 최근 폴더를 추측하지 않는다.
7. macOS와 Windows에서 의미상 같은 수명 계약을 제공한다.
8. 지원하지 않거나 전환에 실패하면 그 사실을 adapter가 판별할 수 있다.

하나라도 확인되지 않으면 Native Companion으로 물러난다.

---

## 5. Companion 설치 상태

```text
missing       설치되지 않았다
stopped       호환판이 설치됐지만 실행 중이 아니다
outdated      설치됐지만 Plugin·wire 계약과 호환되지 않는다
ready         호환판이 설치됐고 열 수 있다
```

경로 존재 여부 하나로 판정하지 않는다. 서명된 app identity, protocol handshake와 호환 version을
사용한다. `ready`가 아니면 기존 Project를 임의로 열거나 오래된 wire를 해석하지 않는다.

### 5.1 Handshake v1

설치된 Companion binary는 `--gil-companion-handshake`에 Project·창·Tauri runtime을 열지 않고
compact JSON 하나로 답한다.

```json
{"schema_version":1,"product":"gil_companion","bundle_id":"dev.ariadne.gil.companion","app_version":"0.1.0","protocol":{"min":1,"max":1},"monitor_view_schema":{"min":1,"max":1},"node_detail_schema":{"min":1,"max":1}}
```

경로·PID·Project scope·사용자 이름은 싣지 않는다. launcher가 요구하는 protocol과 두 wire schema가
모두 응답 범위 안에 있고 identity가 정확히 같아야 호환판이다. 응답이 없거나 모양·identity·범위가
다르면 실행 중처럼 보여도 `outdated`로 판정한다.

```text
bundle 없음                                  → missing
bundle 있음 + handshake 없음·불일치          → outdated
호환 handshake + 실행 중 아님                → stopped
호환 handshake + 실행 중 protocol challenge  → ready
```

binary descriptor가 identity와 호환 범위를 밝히고, 실행 중인 process는 사용자 전용 local IPC에서
매번 새 challenge를 그대로 돌려준다. `ready`는 두 응답이 같은 descriptor를 말할 때만 성립하며,
PID·process 이름만으로 대신하지 않는다. macOS의 첫 transport는 권한 `0600` Unix socket이고
포트·URL을 만들지 않는다. Windows transport는 달라도 challenge와 응답의 의미는 같아야 한다.

### 5.2 Monitor 요청의 조율

「GIL Monitor 열기」 하나를 끝까지 책임지는 자리는 하나다. 표면 선택과 Companion 상태를 따로
물으면 두 답이 어긋나고, 어긋난 자리에서 사람이 같은 말을 두 번 하게 된다.

조율의 결과는 값으로 가른다. 문장을 뜯어 뜻을 짐작하지 않는다.

```text
opened_persistent_host         확인된 지속형 Host surface에 열었다
focused_existing_companion     이미 열려 있던 창을 앞으로 가져왔다
started_and_opened_companion   꺼져 있던 것을 실행하고 handshake를 확인한 뒤 열었다
needs_companion_install        설치가 필요하다 — 승인 없이 설치하지 않는다
needs_companion_update         호환되지 않는 판이 있다 — 그 판을 열지 않는다
monitor_unavailable            지금은 어느 표면도 열 수 없다
```

`stopped`에서는 실행 명령의 성공을 완료로 삼지 않는다. 실행한 뒤 **새 challenge로 다시 확인**하고,
`ready`가 된 뒤에야 원래 요청을 이어서 수행한다. 확인되지 않으면 `monitor_unavailable`이며 원래
요청을 성공으로 표시하지 않는다.

재확인은 유한하다. 무한 polling이나 background busy loop를 만들지 않는다.

원래 요청은 **그 요청이 살아 있는 동안 메모리에만** 둔다. Graph·Journey·Memory·Will·Project 어디에도
적지 않는다. 적어 두면 다음 실행이 사람이 지금 원하지 않는 창을 열 수 있다.

Host surface는 `verified`와 `unverified` 둘로만 적는다. `unverified`는 미지원이라는 뜻이 아니라
§3이 요구한 네 증거로 아직 확인하지 않았다는 뜻이다. 어느 쪽이든 판정은 같다 — 확인되지 않았으면
`persistent_host`로 세지 않는다. 확인하지 못한 것을 미지원으로 단정하지도 않는다.

사용자에게 가는 문장에는 경로·PID·socket·port가 없다. 실패한 OS 명령의 오류 문구를 그대로 잇지
않는다. 그 안에 경로가 들어 있다.

---

## 6. AI가 조율하는 설치

AI는 설치를 수행하는 주체가 아니라 설치 과정을 끝까지 조율하는 주체다.

```text
감지 → 이유 설명 → 사용자 승인 → OS의 신뢰된 설치 표면 → 재감지 → 원래 요청 재개
```

- 사용자의 명시적 승인 없이 native binary를 내려받거나 실행하지 않는다.
- OS의 서명·공증·Store 확인을 우회하지 않는다.
- 설치 전에 제품명, publisher, 필요한 이유와 로컬 접근 범위를 짧게 설명한다.
- macOS에서는 Mac App Store 또는 Developer ID로 서명·공증된 배포물을 사용한다.
- Windows에서는 Microsoft Store 또는 서명된 installer를 사용한다.
- 설치 완료를 사용자가 채팅으로 다시 보고하게 하지 않는다. adapter가 재감지하고 원래 요청을
  자동으로 재개한다.
- 설치·업데이트가 실패하면 Project와 `.gil`을 바꾸지 않고 text 사용과 재시도 경로를 제공한다.
- 관리자 권한을 기본 전제로 두지 않는다. 꼭 필요하면 설치 전에 이유를 밝힌다.

“알아서 설치한다”는 OS 승인과 사용자 의사를 우회한다는 뜻이 아니다. 사용자가 download folder,
terminal, JSON 설정과 실행 파일 위치를 다루지 않아도 된다는 뜻이다.

---

## 7. 비개발자용 설치 UX

정상 경로에서 사용자가 알아야 하는 공개 개념은 둘뿐이다.

```text
GIL Plugin       Agent가 GIL을 사용하게 한다
GIL Monitor      사람이 여정을 보게 한다
```

Companion은 Host가 지속형 Monitor를 제공하지 못할 때만 이름을 드러낸다. 설치 UI는 한 화면에서
다음 셋만 제공한다.

- `Monitor 설치`
- `지금은 text로 계속`
- `무엇이 설치되는지 보기`

설치 완료 뒤에는 “GIL Monitor를 사용할 준비가 됐다. 현재 Project의 여정을 열었다.”라고 답한다.
사용자에게 port, localhost URL, binary path, package format 또는 MCP transport를 보여 주지 않는다.

---

## 8. Host별 packaging

### 8.1 로컬 bundle을 지원하는 Host

Host가 MCP bundle이나 동등한 로컬 package를 지원하면 GIL Core와 로컬 MCP bridge를 self-contained
binary로 함께 배포할 수 있다. 수동 runtime 설치와 JSON 편집을 요구하지 않는다.

독립 창, tray, 로그인 시 시작과 Agent session 밖의 수명을 bundle Host가 보장하지 않으면
Companion은 별도 native surface로 남는다.

### 8.2 원격 MCP가 기본인 Host

공개 HTTPS MCP만 배포할 수 있는 Host에서는 remote plugin이 Companion의 존재·호환성을 조율한다.
remote server가 사용자의 로컬 Project 파일을 대신 보관하거나 읽지 않는다. 로컬 Project 접근은
사용자 장치의 검증된 GIL Core와 Companion 경계에 남는다.

### 8.3 공용 계약

어느 Host에서도 GIL domain state, 저장 schema, `MonitorViewV1`, `NodeDetailV1`, 공용 UI bundle,
설치 상태의 의미와 사용자 승인 경계는 같다.

---

## 9. 업데이트와 복구

- Plugin, GIL Core, Companion과 wire schema의 호환 범위를 명시한다.
- `outdated`를 `missing`으로 말하지 않는다.
- 자동 업데이트는 서명된 동일 publisher의 배포물만 받는다.
- update 실패 시 마지막 검증 View와 Project 기록을 보존한다.
- 새 판이 저장 migration을 요구하면 rollback 가능 여부를 설치 전에 밝힌다.
- 제거는 Companion 설정과 설치물만 지우며 사용자의 Project와 `.gil`을 지우지 않는다.

---

## 10. 검증 가능한 불변식

1. terminal 없이 Plugin 설치에서 Monitor 열기까지 도달한다.
2. inline UI만 가능한 상태를 설치 완료로 판정하지 않는다.
3. PiP 요청 성공이 아니라 실제 persistent mode를 확인한다.
   정식 판정은 앱 선언·Host 광고·요청 반환값·mode 변경 event를 함께 보존한다.
4. PiP와 Companion이 같은 fixture에서 같은 사실을 보여 준다.
5. Companion 없음·꺼짐·낡음·호환됨을 서로 다르게 판정한다.
6. 사용자 승인 없이 native binary를 설치하거나 실행하지 않는다.
7. 설치 완료 뒤 같은 대화에서 원래 요청을 자동 재개한다.
8. 설치·업데이트 거절과 실패 전후 Project bytes가 같다.
9. Companion 없이도 Agent의 text loop와 GIL 기록은 동작한다.
10. macOS와 Windows의 clean machine에서 설치·업데이트·제거를 재현한다.
11. 처음 보는 비개발자가 설명서 없이 한 문장 요청으로 3분 안에 Monitor를 연다.

---

## 11. 아직 정하지 않는 것

- 어떤 Agent Host가 언제 persistent PiP를 공개 지원하는가
- Mac App Store sandbox build와 Developer ID direct build 중 최종 기본 채널
- Windows Store package와 별도 signed installer 중 최종 기본 채널
- public Plugin directory의 심사 일정과 국가별 출시 순서
- Host 사이에서 Companion 설치 상태를 공유하는 방식
- remote MCP와 로컬 Companion 사이의 pairing protocol

---

## 12. 핵심 문장

> **GIL Monitor는 선택 기능이 아니다. Agent surface와 지속형 인간 Monitor가 모두 있어야 설치가
> 완료된다.**

> **persistent Host surface를 우선 사용하고, 실제 수명 계약을 만족하지 못하면 같은 UI를 Native
> Companion에 싣는다. inline UI는 미리보기와 설치 안내이지 지속형 Monitor가 아니다.**

> **AI는 설치를 조율하지만 사용자 승인과 운영체제의 신뢰 경계를 우회하지 않는다.**
