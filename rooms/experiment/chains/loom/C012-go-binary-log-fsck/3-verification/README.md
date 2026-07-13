# 3. 가설 검증

## 산출물

```
3-verification/
├── gil-go/               # Go 구현 1호: main.go (표준 라이브러리만) + 빌드된 gil (Mach-O arm64)
├── gil-py-fix/gil.py     # 참조 구현 결함(release 자기 실행 SameFileError) 수정본 → v0.5.0으로 배포
└── runs/
    ├── run0-self-open.txt
    ├── run1-conformance.txt     # 스위트 v1 × Go: FSCK 9종 PASS 후 스위트가 죽음 — C012의 첫 발견
    ├── run2-conformance-v2.txt  # 스위트 v2(항목 독립) × Go: 15 PASS / 7 FAIL(전부 미구현 명령)
    ├── run3-crosscheck.txt      # 실데이터: Go fsck = Python fsck (문장 단위 동일), 16사이클 렌더
    └── run4-suite-v2-release.txt# 회귀 22/22 + v0.5.0 릴리스
```

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C012-go-binary-log-fsck/3-verification/gil-go
go build -o gil main.go && file gil                     # Mach-O 확인
cd ../../../../../..                                     # 레포 루트
python3 rooms/deployment/ariadne-spec/conformance.py \
  --gil "$PWD/rooms/experiment/chains/loom/C012-go-binary-log-fsck/3-verification/gil-go/gil"
./rooms/experiment/chains/loom/C012-go-binary-log-fsck/3-verification/gil-go/gil fsck  # 실데이터
```

## 실행 기록

- 2026-07-14, macOS arm64, go1.26.2. 외부 Go 모듈 0, 소스 내 파이썬 호출 0.
- run1 (발견 1): 스위트 v1이 부분 구현에서 죽었다 — OPEN 실패 산출물에 의존 + log 검사가 impl의 open에 의존. → **스위트 v2: 판정 항목 간 독립** (상태는 스위트가 write_cycle로 직접 구축).
- run2: 목표 부분집합 11항목(FSCK-CLEAN·R1~R8·LOG-OK·LOG-BROKEN) 전부 PASS. 추가로 거부형 4항목(OPEN-REJECT-SLUG 등)이 미구현의 exit≠0로 **공허 통과** — 거부형 검사는 수락형과 짝일 때만 의미가 있다는 관찰. FAIL 7은 전부 미구현 명령의 수락형 검사.
- run3: 실제 레포(체인 3, 사이클 16)에서 Go fsck와 Python fsck의 출력 문장·exit 동일.
- run4 (발견 2): v0.4.1 릴리스 시도 중 참조 구현의 SameFileError 결함 발견(패키지 도구 자신으로 릴리스 시) — 수정은 도구 변경이므로 규칙대로 v0.5.0 마이너 승격. 승격 규칙의 공백 2건도 RELEASE.md에 기록.
