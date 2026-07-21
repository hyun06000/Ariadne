# 3. 검증 — v3 뷰어를 GitHub Pages에

상현님 "깃헙io에 보이게 하는 거부터 먼저." 지금 Pages는 v2 뷰어만 배포한다. 이 카브는 워크플로에 `gil migrate` + `gil web --v3`를 추가해 v3 통합 뷰어를 Pages에 보이게 한다.

## ⭐ 핵심 설계 — CI가 migrate 후 web --v3 (원장-만, C026 형태)

v3 뷰어는 notes를 읽는데, CI(fresh clone)가 notes를 가지려면 원격 notes fetch(오래된 스냅샷 위험)보다 **CI에서 매번 `gil migrate`로 새로 각인**이 견고하다. C026 형태("원장만 있으면 눈은 언제든 재각인")가 정답: CI가 fresh clone에서 migrate → web --v3. 원격 notes 불요, 항상 최신.

## 워크플로 변경 (`ariadne-pages.yml` build 스텝)

기존 `gil web -o _site/index.html`(v2) 뒤에 추가:
```
git config user.email/name           # notes 각인용
gil migrate .                        # 원장에 v3 notes 각인 (커밋 불변, C018)
gil web --v3 -o _site/v3.html        # v3 통합 뷰어 생성
printf+cat로 index.html에 v3 링크 배너 삽입
```

## 재현 (loom/C007 규약 — 워크플로가 곧 테스트)

```bash
git clone . <clone>                        # fresh clone (CI 모사)
git -C <clone> update-ref -d refs/notes/commits   # 원격 notes 없는 조건(원장-만)
cd <clone>
gil web -o _site/index.html                # v2 (기존)
git config user.email/name
gil migrate .                              # v3 notes 각인
gil web --v3 -o _site/v3.html              # v3
```

## 4측정 (ALL PASS)

| 측정 | 확인 | 결과 |
|---|---|---|
| **M1 v3 페이지 생성** | fresh clone에서 migrate→web --v3 → v3.html (399113 bytes·139사이클·138엣지, 두 층) | PASS |
| **M2 v2 무회귀** | 같은 실행에서 index.html 생성 유지 | PASS |
| **M3 원장-만 재현** | notes 삭제 후 migrate가 원장만으로 각인·v3 생성 성공 | PASS |
| **M4 커밋 불변** | migrate 전후 커밋 digest 8b2643d6 동일 (C018) | PASS |

## ⭐ 정점 결과 — v3가 push 한 번으로 공개된다

이 커밋이 main에 push되면 Pages 워크플로가 트리거돼 v3 뷰어가 `hyun06000.github.io/Ariadne/v3.html`에 배포된다. **"push가 곧 배포"(loom/C007)의 v3판** — 원장에 커밋만 쌓으면 CI가 migrate로 v3 눈을 재각인하고 web --v3로 사람 눈에 낸다. 원격 notes 관리 없이, 원장이 진실원(C026).

## ⭐ 교훈 — CI에서 눈을 재각인하는 게 원격 notes보다 견고

원격 notes를 fetch하면 그 push 시점(C023 73b18f4a)에 고정돼 최신 사이클이 안 보인다. **CI가 매번 migrate로 재각인**하면 항상 원장 최신 상태의 v3 눈. C026 "원장만 있으면 눈은 언제든 재각인"이 CI 배포에서 실용적 값어치 — notes를 원격에 동기화·관리할 필요가 없다. 커밋만 push하면 눈은 CI가 만든다.

## 결론

**ALL PASS → supported.** 워크플로에 migrate + web --v3 추가로 v3 뷰어가 Pages에 배포되게 했다. fresh clone(원장-만)에서 v3.html 생성·두 층 구조·커밋 불변 확인, v2 무회귀. push 시 실제 배포된다.

## 정직한 경계

- **로컬 fresh clone 실측까지** — 실제 GitHub Pages 배포 URL(hyun06000.github.io/Ariadne/v3.html) 확인은 push 후 상현님과.
- **수리 1건**: `sed -i '1i'`가 BSD(macOS)·GNU(ubuntu) 문법 차이 — CI는 ubuntu라 원래 작동하나 이식성 위해 printf+cat로 교체. 로컬 검증 함정이지 CI 실패 아님.
- **--v3 옵트인 유지** — 배포판 gil은 --v3 플래그. 워크플로가 그 플래그로 v3 페이지 별도 생성(index는 v2 유지).
- **다음: 실 배포 확인 후 SPEC/README 문서 갱신 + v3 정식 릴리스**.
