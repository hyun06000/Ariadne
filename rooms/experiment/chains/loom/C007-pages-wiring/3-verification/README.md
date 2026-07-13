# 3. 가설 검증

## 산출물

```
3-verification/
├── fixtures/expected-wiring.md  # 판정 T1~T4 — 워크플로 작성보다 먼저 고정
├── tests.py                     # 드라이버: 신선 클론 + 워크플로 run 블록 추출·실행
└── runs/
    ├── run0-self-open.txt       # 배포된 v0.1.0 도구가 연 사이클
    └── run1-tests.txt           # 4/4 통과
```

검증 대상 본체는 [.github/workflows/ariadne-pages.yml](../../../../../../.github/workflows/ariadne-pages.yml) (배선 커밋 `af12256`).
이 사이클은 도구를 수정하지 않았다 — 빌드·검증 모두 배포된 v0.1.0 ari.py를 사용.

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C007-pages-wiring/3-verification
python3 tests.py; echo "exit: $?"   # git clone → 워크플로 run 블록 추출 → 클론에서 실행
```

## 실행 기록

- 2026-07-14, macOS, Python 3 + git. run1: 4/4 첫 실행 통과.
- T1 세부: 클론(HEAD)의 사이클 7개(genesis 1 + loom 6)가 내장 JSON과 파일시스템 스캔에서 동일 집합으로 확인됨. C007 자신은 미커밋이라 클론에 없음 — 기대 문서에 명시된 정상 동작.
- **한계 (가설의 범위 밖)**: Actions 러너의 실제 실행과 Pages URL 확인은 GitHub 원격이 연결된 뒤 사용자 확인 사항. 원격 push 후 저장소 Settings → Pages → Source를 "GitHub Actions"로 설정해야 한다.
