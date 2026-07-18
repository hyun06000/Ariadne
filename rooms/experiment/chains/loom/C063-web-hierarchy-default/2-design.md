# 2. 실험 설계

가설 하나만 검증한다: 기본값을 뒤집고 `--flat`을 신설해도 양 구현이 바이트 동일하고, 기존 WEB 계약이 보존되며, 새 판정기가 회귀를 격추한다.

## 절차

1. **gil.py (참조)**: `cmd_web`에서 `hierarchy = not getattr(args, "flat", False)`. argparse에 `--flat`(store_true) 추가, `--hierarchy`는 `help=argparse.SUPPRESS`로 하위호환 no-op 별칭화. 진행 메시지는 위계일 때 무표기·평면일 때 "· 평면". 위계/평면 푸터의 자기서술 문구(`gil web` / `gil web --flat`)를 실제 호출과 일치시킨다.
2. **go/main.go (이행자)**: 동일하게 `parseCLI`에 `flat`·`hierarchy` 플래그, `hierarchy: len(flags["flat"]) == 0`, 진행 메시지·usage·푸터를 gil.py와 **문자 단위 동형**으로 이식.
3. **conformance.py**: WEB-JSON 뒤에 `WEB-HIERARCHY-DEFAULT` 신설 — 무옵션 out의 `bake.hierarchy == true`, `--flat` out의 `bake.hierarchy` 부재, 둘 다 외부 리소스 0을 검사. 계약면은 렌더가 아니라 **`gil-data` bake 자기보고**.
4. **빌드·검증**: Go 툴체인(go1.26) 설치 → 양 구현 빌드 → conformance 양쪽 → 바이트 parity(기본·`--flat`) → `--hierarchy` 별칭이 기본과 동일한지 → 변이(변경 전 바이너리) 격추 확인.

## 준비물

- Python 3.9.6 (참조 구현 실행), Go 1.26.5 darwin/arm64 (`brew install go`로 조달).
- 대상: `rooms/deployment/ariadne-spec/{gil.py, go/main.go, conformance.py}`.
- 변이 대조군: 변경 전 v2.18.0 Go 바이너리(`/tmp/gil-baseline`, 기본=평면).
- 샌드박스: conformance.py가 자체 구축(lroot의 demo/C001·C002).

## 측정 방법

- **parity**: `diff -q` 로 gil.py 산출물 ↔ Go 산출물 바이트 동일(기본·`--flat` 각각). 불일치 = 기각.
- **conformance**: 참조·Go 각각 전 판정기 PASS(회귀 0). 하나라도 FAIL = 기각.
- **변이 격추**: 변경 전 바이너리에 conformance → WEB-HIERARCHY-DEFAULT가 FAIL이어야 판정기가 공허하지 않음.

## 사용자 컨펌

박상현과 두 결정 확정: (Q1) 평면 뷰어는 `--flat` **옵트아웃 유지**(제거 아님). (Q2) hierarchy 기본화 → **v2.19.0 릴리스** → 그 바이너리로 로컬(2ndRound) 최신화.

- [x] 컨펌 받음 (일자: 2026-07-19)
