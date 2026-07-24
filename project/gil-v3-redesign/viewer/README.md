# gil 뷰어 (gilviewer) — 별도 바이너리

gil 사고 그래프를 브라우저에서 보는 뷰어. gil 본체와 **당분간 별도 바이너리**로 유지한다
(상현님, 2026-07-24) — 뷰어가 빠르게 반복 개선 중이라 gil 본체에 묶으면 느려진다. gil 이
안정되면 `gil viewer serve` 로 병합 예정.

## 빌드·실행

```
cd project/gil-v3-redesign/viewer && go build -o gilviewer .
./gilviewer --repo <gil저장소경로>            # 텍스트 트리 1회 출력
./gilviewer serve --repo <경로> --port 8791   # 브라우저 관전 서버(자동 새로고침)
```

읽기 전용(`git -C <repo> log`)이라 대상 저장소 작업과 충돌하지 않는다. stdlib 만, 외부 의존 0.

## 기능 (4단 드릴다운)

1. **체인 그래프** — 동그라미 노드 + 계보 엣지 + 라벨(사이클 수). 현재위치(HEAD) 강조.
2. **체인 클릭 → 사이클 카드** — 사이클 노드-엣지 그래프(상태색: success/dead/pending/open).
3. **사이클 클릭 → 스텝 그래프** — 부모-자식 트리 레이아웃(형제 가지 세로 분기),
   backtrack 파선(위로), 종결 스텝(success/fail/pending)이 일반 스텝 노드로.
4. **스텝 클릭 → 상세 보고서 카드** — 커밋 본문을 마크다운 렌더(제목·표·코드블록·인용·
   **이미지 data URI**·`<br>`). 메타 배지. `/step?sha=` 로 원문 fetch(sha 16진수 가드).

1.5초 폴링 자동 새로고침, 라이트/다크 테마, 리로드 후 열린 카드 복원(sessionStorage).
