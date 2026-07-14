# 3. 가설 검증

## 산출물

```
3-verification/
├── gil/gil.py            # v0.6.0: step 필드·R9·gil step·open/close --git/--push·뷰어 인디케이터
└── runs/
    ├── run0-self-open.txt
    ├── run1-conformance.txt        # 확장 스위트(26항목) × v0.6.0 = 26/26
    └── run2-viewer-and-release.txt # 뷰어 배지(●●●○○ 3/5)·JSON step 확인 + v0.6.0 릴리스
```

## 재현 방법

```bash
python3 rooms/deployment/ariadne-spec/conformance.py --gil "python3 rooms/deployment/ariadne-spec/gil.py"
git log --oneline --grep="loom/C013" | cat    # 시연: open → step 1..5 → close가 독립 커밋으로
```

## 실행 기록

- 2026-07-14. 스위트 확장 중 자체 결함 1건(write_cycle이 step 키 미기록 → R9 픽스처 무효) 수정.
- 시연은 이 사이클 자신: 열림·가설·설계는 수동 커밋(도구 탄생 전), 3/5부터는 **새 도구의 gil step --git --push가 직접** 각인·전파했다. 사용자 박상현이 뷰어를 실시간 관전.
