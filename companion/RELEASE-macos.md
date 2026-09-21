# GIL Companion — macOS 배포

사람에게 줄 수 있는 것과 없는 것을 **이름으로** 가른다.

```text
development                make-app.sh            ad-hoc 서명 · 격리 표식을 손으로 뗌 · 배포 불가
release_unsigned           release-macos.sh       packaging 확인용 · 배포 불가
release_signed_unnotarized release-macos.sh       공증 전 · 배포 불가
release_signed_notarized   release-macos.sh       사용자에게 줄 수 있는 것
```

산출물은 `target/release-macos/<상태>/` 에 놓인다. 상태가 자리를 정하므로 `release_unsigned/`
안의 DMG 를 배포 경로에 옮기는 실수를 하지 않는다.

## 짓는 법

```sh
./companion/release-macos.sh
```

필요한 것이 없으면 **빠르고 구체적으로 실패한다.** 개발 빌드로 조용히 물러서지 않는다.

- macOS 가 아니면 멈춘다
- `cargo-tauri` 가 없으면 멈춘다 (`cargo install tauri-cli --version '^2' --locked`)
- 서명 identity 가 없으면 `release_unsigned` 까지만 가고 그렇게 적는다
- 공증 credential 이 없으면 공증을 건너뛰고 그렇게 적는다

## 비밀의 경계

identity 도 credential 도 저장소에 없다. 환경에서 받고 값은 어디에도 찍지 않는다.

| 이름 | 쓰임 |
|---|---|
| `APPLE_SIGNING_IDENTITY` | `Developer ID Application: …` — 서명 |
| `APPLE_API_KEY` | App Store Connect key id — **공증은 이쪽을 먼저 본다** |
| `APPLE_API_ISSUER` | issuer uuid |
| `APPLE_API_KEY_PATH` | `.p8` 파일 경로 — 저장소 **밖** |
| `APPLE_ID` / `APPLE_PASSWORD` / `APPLE_TEAM_ID` | API key 가 없을 때만 |

API key 를 먼저 쓰는 이유는 권한이 좁고, 회수와 교체가 사람 계정과 무관하기 때문이다.
`.p8` private key, 인증서, 비밀번호는 저장소·로그·산출물 어디에도 들어가지 않는다.

CI 에서는 위 이름을 secret 으로 주입한다. 값은 이 문서에도 저장소에도 없다.

## 무엇이 들어가는가

DMG 에는 `GIL Companion.app` 과 `Applications` 바로가기 둘뿐이다.

앱 안에는 제품 화면만 싣는다 — `index.html`, `companion.js`, `companion.css`, `layout.js`.
**selftest 와 fixture Host 는 싣지 않는다.** 그것은 개발 도구이고, 제품 안에 가짜 사실을
만들 수 있는 문이기 때문이다. 의존성 source 경로도 remap 해서 개발자의 home 이 binary 에
남지 않게 한다.

## hardened runtime 과 권한

hardened runtime 을 켜고 **권한은 하나도 요구하지 않는다**. `entitlements.plist` 에는
`get-task-allow = false` 한 줄뿐이다. App Sandbox 는 Developer ID 직접 배포에 필수가 아니므로
켜지 않는다 — Store 는 별개의 판단이고 그때 다시 정한다.

hardened runtime 아래에서 **실측한 것**:

| 기능 | 결과 |
|---|---|
| 앱 실행 | 동작 |
| WKWebView·창 | 동작 (WebKit content process 확인 · JIT 권한 불필요) |
| tray / menu bar | 동작 (기동 오류 없음) |
| Unix socket handshake | 동작 (`0600`, 새 challenge 응답) |

**실측하지 못한 것** — GUI 조작이 필요하다:

| 기능 | 상태 |
|---|---|
| 폴더 고르기 (NSOpenPanel) | 미실측. sandbox 밖이라 권한 불필요할 것으로 본다 |
| 선택한 Project 의 watcher | 미실측. FSEvents 는 권한 불필요 |
| 로그인 시 시작 | 미실측. 사용자의 로그인 항목을 건드리지 않으려 미룸 |

실측은 ad-hoc 서명 + `--options runtime` 으로 했다. 런타임 제약은 Developer ID 서명과 같지만,
**공증이 통과한다는 증거는 아니다.**

## architecture

지금 짓는 것은 **Apple Silicon(arm64) 전용**이다. 실측한 것이 그것뿐이다.

Intel 이나 universal 은 아직 **지원한다고 말하지 않는다.** 하려면 `x86_64-apple-darwin`
target 을 설치하고 universal 로 다시 지어 그 위에서 확인해야 한다.

`LSMinimumSystemVersion` 은 `10.15` 로 선언하지만 그 판에서 실행해 본 것은 아니다.

## 아직 하지 않은 것

- Developer ID 인증서 발급과 Apple Developer Program 가입
- 실제 서명·공증·staple·`spctl` 통과
- 공개 다운로드 자리
- Tauri Updater (업데이트는 장차 별도 서명 artifact)
- Mac App Store · PKG
- Windows

## 사람이 확인할 설치 절차

서명·공증된 DMG 가 생긴 뒤의 절차다. 지금 만들 수 있는 것은 `release_unsigned` 까지이므로
아래는 **credential 이 생긴 뒤** 밟는다.

1. `./companion/release-macos.sh` — receipt 가 `release_signed_notarized` 라고 적는지 본다
2. DMG 를 두 번 눌러 열고 앱을 `Applications` 로 끌어 놓는다
3. 앱을 처음 열 때 Gatekeeper 경고가 **뜨지 않아야** 한다
4. menu bar 에 자리가 생기는지 본다
5. 창에서 **폴더 열기** 로 Project 를 고른다
6. 그 Project 에 파일을 만들고 지워 `clean`·`dirty` 가 저절로 바뀌는지 본다
7. 앱을 지우고 Project 와 `.gil` 이 그대로인지 본다
