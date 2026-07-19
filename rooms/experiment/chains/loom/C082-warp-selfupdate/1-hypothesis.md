# 1. 가설 수립

## 이전 사이클의 교훈

부모: **C081-close-seal-scope**. 그 사이클과 최근 계보에서 이어받은 교훈:

- **정답을 판정기에 먼저 못박는다.** 도구 구현보다 conformance 항목을 먼저 고정한다.
- **parity를 배신하지 않는다 (C077).** 참조 gil.py와 go/main.go를 동시에 고친다 — 참조만 앞서면 gil-gate가 깨진다.
- **자기보고 표면은 계약이다 (C038·C039).** `version`은 자기 버전을 거짓말할 수 없고, `help`의 `gil:commands` 훅이 나열한 능력은 실재해야 하며(정방향), 나열 안 한 능력은 미구현 신호(exit 3)로 답해야 한다(역방향).

## 문제 분할

이슈 #22 — gil 바이너리가 상위 릴리스에서 조용히 뒤처지는 드리프트를 바이너리 스스로 없애기. 가벼운 순서로 분할:

1. **`gil version --check`** — 상위 `releases/latest`와 대조해 "최신"/"N.N.N 사용 가능" 보고. **부작용 없음, 네트워크 조회.** ← 가장 작고 안전한 첫 카브.
2. **`gil version --update`** — 플랫폼 자산 다운로드 → SHA256SUMS 대조 → 검증 성공 시에만 제자리 교체.

두 카브를 이번 사이클에서 함께 정복하되, 안전 경계를 명확히 나눈다.

## 가설

> **가설**: 바이너리는 부작용 없이 자기 드리프트를 조회할 수 있고(`--check`), SHA256SUMS 대조에 성공할 때만 자기를 교체할 수 있다(`--update`). 이 두 행위를 gil.py와 go/main.go에 parity로 구현하고 conformance에 형태 계약으로 못박으면, 바이너리 드리프트는 바이너리 스스로 없앨 수 있다.

### 기대 행동 (정답, 구현보다 먼저 고정)

**`gil version --check`** (부작용 없음):
- `releases/latest` 리다이렉트 Location의 `tag/vX.Y.Z`에서 상위 최신 버전을 파싱.
- 로컬 `_GIL_VERSION`과 SemVer 비교 → 최신이면 `현재 최신`, 뒤처졌으면 `N.N.N 사용 가능` 취지 보고.
- 저장소를 변경하지 않는다 (HELP-SAFE와 같은 무해성).
- 네트워크 실패 시 exit≠0로 정직히 실패 (드리프트 상태를 지어내지 않는다).
- 기계 훅: `gil:version-check <local> <latest> <status>` (status ∈ {current, outdated}).

**`gil version --update`** (제자리 교체, 검증 게이트):
- 플랫폼 자산 `gil-<GOOS>-<GOARCH>`(windows `.exe`)를 받고, SHA256SUMS의 선언 해시와 실물 해시를 대조.
- 대조 성공 시에만 현재 바이너리를 원자적 제자리 교체(임시 → chmod +x → rename). 실패면 아무것도 안 바꾸고 exit≠0.
- 이미 최신이면 다운로드 없이 보고.

## 기각 조건

- `--check`가 저장소를 변경하면(스냅샷 차이) → 기각 (무해성 위반).
- 두 구현의 `--check` 출력/기계 훅이 갈리면 → 기각 (parity 위반).
- `--update`가 SHA256 불일치인데도 바이너리를 교체하면 → 기각 (검증 게이트 위반).
- 실제 `releases/latest` 조회로 상위 버전을 못 얻으면 → 조회 설계를 재검토.
