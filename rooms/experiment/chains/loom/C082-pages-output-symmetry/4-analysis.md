# 4. 결과 분석

## 통계적 결과

기대 행동(2-design.md) 전면 대조:

| 항목 | 기대 | 참조 | Go |
|---|---|---|---|
| PAGES-OUTPUT-PATH (T1) | `-o <path>`→지정 경로, 기본 경로 무생성 | PASS | PASS |
| PAGES-OUTPUT-STDOUT (T2) | `-o -`→stdout 전문, 저장소 무변화 | PASS | PASS |
| PAGES-DRYRUN (T5, 기존) | dry-run 부작용 없음 | PASS | PASS |
| 기본·force 회귀 (T3·T4) | 기존 항목·수동 확인 | 회귀 0 | 회귀 0 |

- **참조 109/109**(수정 전 107/109 — 신설 2항목 FAIL), **Go 95/95**(수정 전 93/95). 두 신설 항목이 수정 전엔 정확히 FAIL → 판정기가 이 대칭을 실제로 검증함을 확증(빈 검사 아님).
- **parity 0바이트**: `diff <(참조 pages -o -) <(go pages -o -)` 차이 없음. 두 몸이 한 계약.

## 데이터 직접 관찰

- **stdout 순수성 실측**: `pages -o -`를 파일로 리다이렉트 → stderr **0바이트**, 첫 줄 `# gil-pages —…`, 마지막 줄 `uses: actions/deploy-pages@v4`. 안내 문구("생성:", "다음:")가 stdout에 섞이지 않음 — 파이프 안전 확증.
- **이슈가 원한 실사용 흐름 재현**: `gil pages -o /tmp/preview.yml`로 미리보기 생성 → `diff <(gil pages -o -) /tmp/preview.yml` = 0 차이. 이슈 #21이 임시 디렉토리 우회로 하던 일이 이제 한 줄. BrokenPipe 없음(diff는 전체 소비).
- **기본 경로 격리 실측**: T1 sandbox에서 `-o custom.yml` 실행 후 `.github/workflows/gil-pages.yml`은 **미생성**(`기본있음=False`) — `-o`가 무시되던 이슈 증상이 사라짐.

## 예상과 달랐던 것

- **자기적용 diff 기준 부재**: 원래 "현재 워크플로와 diff로 변경 없음 확인"을 계획했으나, `.github/workflows/gil-pages.yml`은 **저장소에 커밋돼 있지 않다**(생성 대상일 뿐). gil-gate·gil-release 워크플로만 커밋됨. 그래서 자기적용은 "현재 파일과 대조" 대신 "판정기가 stdout == `_PAGES_WORKFLOW` 상수 확인"으로 충족. 이슈의 diff 유스케이스는 사용자가 이미 pages를 커밋한 저장소(maru 환경)를 전제한 것.
- **`-o -` + parseCLI(Go)**: `-`가 `--output`의 값으로 잘 파싱될지 우려했으나(대시 시작 토큰), web의 정규화 패턴 그대로 무사 통과. 값 자리의 `-`는 플래그로 오인되지 않음.
- **상대경로 표시**: 워크트리 깊이 때문에 `생성: ../../../../../../../tmp/preview.yml`로 표시되나 파일은 정확히 `/tmp/preview.yml`에 생성. repo_root 상대 표시는 기존 동작이라 무변경 — 표시일 뿐 기능 정상.

## 판정

**채택.** 기각 조건 5개 전부 미발동:
- `-o <path>` 지정 경로에 씀(T1 PASS) ✓ / `-o -` stdout 전문·파이프 안전(T2 PASS, stderr 0) ✓ / 기본·force·dry-run 회귀 0(T3·T4·T5) ✓ / stdout 경로 저장소 무변화 ✓ / 참조↔Go parity 0바이트 ✓.

가설의 (a)(b)(c) 모두 실증. web과 pages의 출력 계약 비대칭이 해소됐다.
