# 3. 가설 검증

산출물: gil pages(참조·Go), repo-root 유추 버그 수정, QUICKSTART 실전 재작성, 뷰어 선택지 문서, runs/ 4건. 릴리스 v1.2.0(pages)·v1.2.1(문서 교정).

## 실행 기록 (2026-07-15)

- run2: pages 11/11 (양 구현 T1~T4 + T2 빌드 로직 + T5 conformance 26/26).
- run3: QUICKSTART 데모 블록 실행 PASS.
- run4 (수신자 관점): latest 바이너리로 실전 경로 밟다가 **두 결함 발견** — ① open --git 바이너리 미구현(문서가 첫 명령으로 안내), ② 뷰어가 github.io로만 안내(로컬 깃 사용자 배제). 둘 다 교정 후 재검증: open(--git 없이)→step --git→close --git→pages→fsck→verify 전체 완주, 로컬 web 뷰어 GitHub 없이 생성.
