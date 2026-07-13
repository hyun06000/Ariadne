# 3. 가설 검증

## 산출물

```
3-verification/
├── fixtures/
│   ├── expected-structure.md  # 기대 구조·판정 규칙 — 구현보다 먼저 고정 (절차 1)
│   ├── maze/                  # C001 계승: 분기·병합 6사이클
│   ├── lineage/               # C002 계승: 체인 간 lineage (alpha/beta)
│   └── broken/                # C001 계승: 끊어진 parent
├── ari/ari.py                 # ari v5: + web — 같은 파서, SVG 렌더러, JS 0줄 (절차 3)
├── tests.py                   # T1~T6 드라이버 (절차 4)
└── runs/
    ├── run0-self-open.txt     # ari open이 연 사이클
    ├── run1-tests.txt         # 6/6 통과
    ├── run2-realdata.txt      # 실데이터: 노드 6, lineage 1, 외부참조 0
    └── ariadne-chains.html    # 실제 레포의 뷰어 (이 시점의 스냅샷)
```

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C005-web-viewer/3-verification
python3 tests.py; echo "exit: $?"

# 실데이터 (레포 루트에서) — 아무 브라우저로 열면 된다. 서버·네트워크 불필요.
python3 rooms/experiment/chains/loom/C005-web-viewer/3-verification/ari/ari.py web -o /tmp/chains.html
```

의존성: Python 3 표준 라이브러리만 (web은 깃도 불필요).

## 실행 기록

- 2026-07-14, macOS, Python 3. 절차 준수: 기대 구조 고정 → 픽스처 계승 → 구현 → 테스트 → 실데이터.
- run1: 6/6 통과, 첫 실행.
- run2: 실제 레포 — 노드 6(genesis 1 + loom 5), lineage 간선 1(loom/C001 ⇠ genesis/C001), loom 직렬 간선 4, 외부 리소스 참조 0. 기대 구조 문서와 전부 일치.
- 디자인: dataviz 검증 기본 팔레트의 토큰 사용. 상태는 색+모양 이중 인코딩(닫힘=채운 원, 열림=빈 원), 접근성 테이블 동봉, 라이트/다크 토큰 레벨 지원, JS 0줄.
- 렌더 확인: 생성물을 Artifact로 발행해 브라우저 렌더를 사용자(박상현)가 확인할 수 있게 함 — https://claude.ai/code/artifact/7657ae15-2d6e-4cbf-a7e9-b080f7be5178 (사용자 전용 비공개).
