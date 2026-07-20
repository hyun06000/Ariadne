# 1. 가설 수립 — Go 이식으로 gil-gate 완전 녹색 (발의: 상현님 "정공법")

## 이전 사이클의 교훈

C085~C093에서 참조 구현(Python)에 뷰어·강제 기능을 넣고 **conformance 122/122 "이 구현은 gil이다"**를 달성했다. 그러나 매번 "Go parity 이월"로 미뤄, gil-gate의 **Go 구현 검사에서 4항목 FAIL**(100/104): OPEN-CREATE·WEB-REFRESH-DEFAULT·WEB-MD-RENDER·STEP-GATE. 계약은 구현을 정의하며, 두 구현이 같은 계약을 통과해야 gil이다 — Go도 따라와야 한다.

## 문제 분할

4개는 이번 세션 참조 구현 변경의 Go 미이식분:
- **OPEN-CREATE·STEP-GATE (C090)**: Go cmdOpen이 5스텝 다 스캐폴딩, cmdStep에 전이 가드 없음.
- **WEB-REFRESH-DEFAULT (C085)**: Go web의 refresh 기본값 없음.
- **WEB-MD-RENDER (C088)**: Go web에 마크다운 렌더 토글·인라인 파서·이미지 임베드 없음.

## 가설

> **가설**: 참조 구현(gil.py)을 정본으로, Go(main.go)에 ① open 1스텝 스캐폴딩 + step 전이 가드(C090) ② refresh 기본 5초 + `--refresh 0` 옵트아웃(C085) ③ 마크다운 렌더 토글·esc 기반 파서·이미지 base64 임베드(C088)를 이식하면, Go conformance가 104/104가 되어 gil-gate가 참조·Go 양쪽 완전 녹색이 된다.

## 기각 조건

- 이식 후에도 Go 4항목 중 남는 게 있으면 부분 기각(개별 재조사).
- Go 이식이 기존 Go 통과 항목을 깨면(회귀) 기각.
- 참조·Go 산출물 바이트가 무의미하게 갈라지면(가능한 범위에서 동형 아님) 주의 기록.
