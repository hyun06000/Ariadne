# 3. 가설 검증

## 산출물

```
3-verification/
├── gil-go/                # Go 구현 2호: C012의 main.go(461줄, fsck·log)를 계승해
│   │                      #   open·close를 추가한 main.go(739줄) + 빌드된 gil (Mach-O arm64)
│   ├── main.go
│   └── gil
└── runs/
    ├── run0-build.txt                   # 빌드 환경·바이너리·의존성(표준 라이브러리만) 기록
    ├── run1-conformance-go.txt          # 무수정 스위트 × Go: 18/22 — 목표 17항목 전부 PASS
    ├── run2-conformance-py-regression.txt # 무수정 스위트 × Python 참조 구현: 22/22 (회귀 없음)
    └── run3-crosscheck.txt              # 실데이터 복사본에서 Go ↔ Python open·close 동등성
```

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C014-go-binary-open-close/3-verification/gil-go
go build -o gil main.go && file gil                     # Mach-O 확인
cd ../../../../../..                                     # 레포 루트
# run1: 무수정 배포 스위트 × Go 바이너리
python3 rooms/deployment/ariadne-spec/conformance.py \
  --gil "$PWD/rooms/experiment/chains/loom/C014-go-binary-open-close/3-verification/gil-go/gil"
# run2: 같은 스위트 × 참조 구현 (회귀)
python3 rooms/deployment/ariadne-spec/conformance.py \
  --gil "python3 $PWD/rooms/deployment/ariadne-spec/gil.py"
# run3: rooms/experiment를 임시 디렉토리 2부에 복사한 뒤, 같은 인자의 open·close를
#       Go/Python 각각 실행해 생성물 diff·fsck 판정·닫기 전이를 대조 (스크립트는 로그 참조)
```

## 실행 기록

- 2026-07-14, macOS Darwin 25.2.0 (arm64), go1.26.2, Python 3.9.6.
- 판정기: `rooms/deployment/ariadne-spec/conformance.py` **v0.5.0 배포본, 무수정**
  (스위트 v2 — C012에서 항목 독립화된 판본).
- run1: **목표 17항목 전부 PASS** (FSCK-CLEAN·R1~R8, OPEN-CREATE·INCREMENT·REJECT-SLUG,
  CLOSE-TEMPLATE-REJECT·OK·DOUBLE-REJECT, LOG-OK·LOG-BROKEN). 총계 18/22 —
  FAIL 4는 전부 범위 밖(WEB 2, GIT-CLOSE, VERIFY-CLEAN), VERIFY-TAMPER는 미구현
  exit≠0에 의한 공허 통과.
- run3: 같은 인자의 open에서 Go/Python 생성물이 **바이트 단위 동일**(cycle.yaml diff·
  파일 목록 diff 무차이), Go 생성물에 Python fsck OK, close 전이 결과 동일,
  실데이터 fsck stdout 동일. 범위 밖 `close --git`은 트리 해시 대조로 **무변화 거부**
  확인 (exit 3).
- 특이사항: run3 최초 실행 스크립트에 zsh 변수 분리 버그가 있어(파이썬 쪽 exit 127)
  스크립트를 고쳐 전체 재실행했다 — 저장된 로그는 재실행본이다.
