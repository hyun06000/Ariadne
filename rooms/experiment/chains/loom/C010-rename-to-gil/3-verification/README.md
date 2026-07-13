# 3. 가설 검증

## 산출물

```
3-verification/
├── gil/gil.py               # 개명된 도구 — 변경은 딱 둘: 명명(독스트링·prog), release의 파일명 비의존화
└── runs/
    ├── run0-self-open.txt   # ari라는 이름의 마지막 open
    ├── run1-smoke-and-sync.txt  # T1 실데이터 스모크 + T2 release 파일명 비의존 (샌드박스)
    ├── run2-real-release.txt    # v0.3.0 — 릴리스 커밋이 개명을 rename(R098)으로 각인
    └── run3-docs-as-tests.txt   # T3 퀵스타트·워크플로 추출 실행 (신선 환경·신선 클론)
```

검증 대상 본체: 배포된 [gil.py](../../../../../deployment/ariadne-spec/gil.py), [SPEC §7 구현 독립 계약](../../../../../deployment/ariadne-spec/SPEC.md), 태그 `v0.3.0`·`v0.3.1`.

## 재현 방법

```bash
cd rooms/experiment/chains/loom/C010-rename-to-gil/3-verification
python3 gil/gil.py fsck && python3 gil/gil.py verify        # T1 스모크 (레포 루트 기준 경로면 루트에서)
git tag -l "v0.3.*"                                          # 릴리스 각인
grep -c "ari.py" ../../../../deployment/ariadne-spec/SPEC.md # 0이어야 함
```

## 실행 기록

- 2026-07-14, macOS. run1: T1(fsck 0·verify 0·log 14사이클·web 자기완결)·T2(샌드박스 release → gil.py sha 동기화) 통과.
- run2: `git rm ari.py` 후 `gil.py release 0.3.0` — 커밋이 R098 rename으로 기록, 배포의 방만.
- **자체 발견 1건**: 릴리스된 SPEC 정독에서 잔존 `ari` 언급 3곳 발견(서두·§3 제목·제목의 고정 버전) — 도구 미변경이므로 패치 경로로 즉시 정정(v0.3.1, "문서 릴리스"). 치환 스크립트는 치환한 것만 안다 — 전수 grep이 릴리스 전 절차여야 했다.
- run3: T3a 퀵스타트(신선 환경, gil.py) rc 0 / T3b 워크플로 run 블록(신선 클론) rc 0, 체인 3 렌더.
