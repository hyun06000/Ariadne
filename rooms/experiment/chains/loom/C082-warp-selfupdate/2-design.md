# 2. 실험 설계

가설: 바이너리는 부작용 없이 자기 드리프트를 조회하고(`--check`), SHA256 대조 성공 시에만 자기를 교체한다(`--update`). gil.py와 go/main.go에 parity 구현 + conformance 형태 계약.

## 구현 설계

### 공통 상수
- 릴리스 저장소: `hyun06000/Ariadne` (기존 pages 워크플로가 쓰는 그 host).
- latest 태그 URL: `https://github.com/hyun06000/Ariadne/releases/latest` → 리다이렉트 Location `.../tag/vX.Y.Z`.
- 자산 다운로드: `https://github.com/hyun06000/Ariadne/releases/latest/download/<asset>`.
- 자산명: `gil-<GOOS>-<GOARCH>` (linux/darwin × amd64/arm64), windows는 `+.exe`.
- SHA256SUMS 형식: `<hex>  <asset>` (두 칸 공백).

### `_latest_version()` — 상위 최신 조회 (부작용 없음)
- `releases/latest`에 HEAD/GET 하여 최종 리다이렉트 URL의 `tag/v(X.Y.Z)`를 정규식 파싱.
- 반환: `(X,Y,Z)` 튜플 또는 실패 시 예외.
- gil.py: `urllib.request` (리다이렉트 자동 추종, 최종 `resp.geturl()`).
- Go: `net/http` 기본 클라이언트(리다이렉트 추종), `resp.Request.URL`.

### `gil version --check`
1. 로컬 = `_GIL_VERSION` 파싱.
2. 원격 = `_latest_version()`. 실패 시 stderr 에러 + exit 1.
3. 비교: 원격 > 로컬 → outdated, 아니면 current.
4. 출력(사람용) + 기계 훅 마지막 줄: `gil:version-check <local> <latest> <status>`.
5. 저장소 미변경 (조회만).

### `gil version --update`
1. `--check`와 같은 조회로 원격 버전 확인. 이미 current면 "이미 최신" 보고 후 exit 0 (교체 없음).
2. outdated면: 자산 `gil-<plat>`와 SHA256SUMS를 임시 디렉토리에 다운로드.
3. SHA256SUMS에서 자산 줄의 선언 해시 추출 → 받은 파일의 실제 sha256과 대조.
4. 불일치 → stderr 에러 + exit 1, **아무것도 교체 안 함**.
5. 일치 → chmod +x → 현재 실행 경로(`sys.argv[0]`/`os.Executable()`)로 원자적 rename(같은 파일시스템 임시경유 rename). 성공 보고.

### 하위호환
- 플래그 없는 `version` / `--version` / `-v`: 기존대로 `gil X.Y.Z`만 출력. 무변경.

## 절차 (검증)

1. **정답 먼저**: conformance.py에 항목 추가
   - `VERSION-CHECK-SAFE`: `version --check`가 저장소를 변경하지 않는다(스냅샷 동일). 네트워크 없으면 skip 불가하므로 exit코드 무관하게 무해성만 판정.
   - `VERSION-CHECK-HOOK`: `--check` 성공 시 `gil:version-check` 훅 1줄이 `<semver> <semver> <current|outdated>` 형태.
   - `VERSION-FLAGS-PARITY`: 두 구현 모두 `version --check`를 안다(미구현 신호 아님).
   - 네트워크 의존 항목은 조회 실패를 허용하되 형태만 판정(CI 오프라인 대비).
2. gil.py 구현 → go/main.go 구현 (동시, parity).
3. Go 빌드: `go build`로 `/tmp` 임시 바이너리 산출.
4. 두 구현으로 `version --check` 실행 → 출력·훅·exit·parity 대조. verification/에 로그 저장.
5. `--update` 검증: **샌드박스** — 임시 디렉토리에 gil 바이너리 복사본을 두고, (a) SHA 일치 시 교체 성공, (b) 위조 SHA256SUMS로 불일치 시 교체 거부(원본 유지)를 증명. 실제 설치 gil은 불건드림.
6. conformance를 두 구현(gil.py, go 빌드)에 실행 → 전항목 pass.
7. `_GIL_VERSION`/`gilVersion`은 건드리지 않는다(릴리스는 Selvage/release가 집행).

## 측정 방법
- `--check` 무해성: `snapshot(dir)` before==after.
- parity: gil.py와 go의 `--check` 훅 줄 동일(버전 값·status 동일).
- `--update` 게이트: 위조 SHA에서 바이너리 바이트 불변 == 게이트 작동.
- 성공 기준: conformance 신규 항목 전 pass + 위 3측정 통과.

## 사용자 컨펌

생략 — 이슈 #22가 기대 행동을 이미 명시했고(제안 1·2), 분기 없음. Clew의 소환 프롬프트가 설계 방향(정답 먼저·parity·샌드박스 교체)을 확정했다.

- [x] 컨펌 받음 (일자: 2026-07-19, 이슈 #22 + Clew 소환 프롬프트로 갈음)
