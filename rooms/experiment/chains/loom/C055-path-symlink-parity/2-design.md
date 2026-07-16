# 2. 실험 설계

H1(참조를 Go에 맞춘 심볼릭 링크 우아화)과 H2(계약면 신설)를 하나의 절차로 검증한다.
순서가 중요하다 — **판정기 항목을 먼저 세워 수정 전 비대칭(참조 FAIL / Go PASS)을
기계로 관찰**하고, 그 다음 참조를 고쳐 **양 구현 PASS**로 접는다. C051의 규율:
계약면이 실제 결함을 포착함을 먼저 보이고서야 수정이 의미를 얻는다.

## 준비물

- 참조 구현: `rooms/deployment/ariadne-spec/gil.py`
- Go 구현: `rooms/deployment/ariadne-spec/go/main.go` (빌드: `GO111MODULE=off go build -o gil-go main.go`)
- 판정기: `rooms/deployment/ariadne-spec/conformance.py` (현재 75/75 기준선)
- 산출물 격리: 모든 임시 저장소·바이너리는 스크래치패드에. 원 저장소는 사이클 문서만 커밋.

## 절차

### A. 계약면 신설 (H2) — 수정 전 비대칭 포착

1. `conformance.py`의 `main()`, `NO-REMOTE-GRACEFUL` 항목 **뒤에** `PATH-SYMLINK-GIT`
   항목을 추가한다. 로직:
   - 샌드박스를 `realpath`로 만든 실제 디렉토리 `real`에 git 저장소 초기화(init·config·
     add·commit "init").
   - `real`을 가리키는 심볼릭 링크 `sym`을 만든다(`os.symlink(real, sym)`).
   - **심링크를 통과하는 절대 `--root`** `sym/rooms/experiment/chains`로
     `impl.run(real, "open", "demo", "sym-root", "--author","tester","--new-chain","--git","--root", symcr)`.
   - 계약: `rc==0` ∧ `real` 아래 `demo/C001-sym-root/cycle.yaml` 존재 ∧ `git log`에
     `"gil: open"` 커밋 존재 ∧ stderr에 `Traceback`/`panic:` 없음.
   - 문면(안내 메시지)은 검사하지 않는다 — 렌더는 계약이 아니다(C021·C051).
2. **수정 전** 판정기를 두 구현에 실행:
   - `conformance.py --gil "python3 <참조>"` → `PATH-SYMLINK-GIT` **FAIL** 예상(참조 74/75).
   - `conformance.py --gil "<gil-go>"` → `PATH-SYMLINK-GIT` **PASS** 예상(Go 76/76).
   - 이 대비가 "두 몸, 한 계약"의 위반을 기계가 재현한 증거(수정 전 스냅샷으로 저장).

### B. 참조 수정 (H1) — Go 이식

3. `gil.py`에 단일 헬퍼를 추가한다(`_repo_root` 근처):
   ```python
   def _rel_to_repo(path, repo):
       """저장소 루트 기준 상대 경로. git --show-toplevel(realpath)과 사용자가 준
       --root(심링크 그대로)의 심볼릭 링크 공간 불일치를 흡수한다 — 양쪽을 realpath로
       정규화한 뒤 상대화 (Go relToRepo와 동치, loom/C055)."""
       return os.path.relpath(os.path.realpath(path), os.path.realpath(repo))
   ```
4. git에 넘어가는 모든 `os.path.relpath(<X>, repo)`(두 번째 인자가 `_repo_root` 산출
   `repo`인 것)를 `_rel_to_repo(<X>, repo)`로 대체한다. 대상 22곳(라인은 수정 시점 기준):
   `619, 620, 754, 757, 759, 760, 786, 937, 1372, 1534, 1572, 1632, 1706, 1707, 1786,
   1872, 1927, 2002, 2040, 2124, 2183, 2231`.
   - **제외(경계)**: `_hash_tree`의 `relpath(p, root)`(2069) — `p`와 `root`가 같은
     `os.walk` 기반이라 **자기일관**(불일치 없음), realpath 불필요. pages의 `repo_root`
     (1225·1234, normpath 기반·git-add 아님)와 display용 `getcwd`(1725)도 제외.
   - 안전성: 대상은 이미 `if repo:` 가드 안에 있어 `repo=None`(git 부재)에서 도달하지
     않는다 — 내부 호출만 바꾸므로 새 크래시 표면 없음(NO-GIT-GRACEFUL 회귀로 확인).

### C. 검증 (H1 + H2 접힘)

5. **수정 후** 판정기를 두 구현에 실행 → 양쪽 모두 `PATH-SYMLINK-GIT` **PASS**,
   총 **76/76 × 2**, 기존 75항목 회귀 0.
6. **변이 격추**: `_rel_to_repo`를 `os.path.relpath(path, repo)`(realpath 제거)로
   되돌린 변이 참조 → `PATH-SYMLINK-GIT` **FAIL**(75/76)로 항목이 실제 가드임을 확인.
7. **직접 재현 재실행**: 스텝 1의 심링크 재현 시나리오를 수정된 참조로 다시 실행 →
   `열림` + 커밋 성공(수정 전 `git add … outside repository` 붕괴가 사라짐).
8. **비심링크 실사용 회귀**: 원 저장소(비심링크 경로)에서 `fsck`·`verify` 무손상 확인.

## 측정 방법

| 가설 | 측정 | 성공 기준 | 기각 기준 |
|---|---|---|---|
| H1 | 심링크 재현 + 판정기 PATH-SYMLINK-GIT (참조) | 수정 후 PASS, 커밋 성공 | 수정 후에도 FAIL |
| H1-2 | 판정기 전 항목 (양 구현) | 76/76 ×2, 회귀 0 | 기존 항목 하나라도 FAIL |
| H2 | 수정 전 대비 | 참조 FAIL / Go PASS (신설이 비대칭 포착) | 수정 전 참조가 PASS(거짓 음성) |
| H2 | 변이(realpath 제거) | FAIL(75/76) | 변이 생존(항목이 헛것) |

## 사용자 컨펌

- 생략 — 상현님 전권 위임(C008, "사이클을 멈추지 말고 계속"). 이 사이클은 C054 보고서
  1순위 후보 (A)를 그대로 정복하며, 참조를 이미 옳은 Go에 맞추는 순수 패리티 작업이다.

- [x] 컨펌 갈음 (전권 위임, 2026-07-14)
