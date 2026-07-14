# 3. 가설 검증

산출물: fixtures/chains/test-grammar(문법 전수 픽스처), runs/run1-crosscheck.txt, SPEC §3.1(v0.9.2 각인).

## 재현 방법

```bash
go build -o /tmp/gil-go rooms/experiment/chains/loom/C017-go-git-binding/3-verification/gil-go/main.go
FX=rooms/experiment/chains/loom/C021-parsing-contract/3-verification/fixtures/chains
python3 rooms/deployment/ariadne-spec/gil.py fsck "$FX" ; /tmp/gil-go fsck "$FX"   # 동일해야 함
```

## 실행 기록

- 2026-07-15. fsck 바이트 동일. log에서 요약 섹션 차이 발견(파이썬에만 root:/분기점 요약) → 파싱 유래 슬라이스(노드 줄+계보)는 바이트 동일로 확증. 문법 커버리지 6요소 전부 픽스처에 존재.
