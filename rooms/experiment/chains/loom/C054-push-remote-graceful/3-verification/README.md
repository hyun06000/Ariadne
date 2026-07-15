# 3. 가설 검증

설계(2-design.md)의 절차를 그대로 실행한 기록. 모든 판정기 명령은 절대경로 `--gil`을 썼다(C028·C043·C045 함정).

## 재현 방법

```bash
cd rooms/deployment/ariadne-spec
ABS=$(pwd)
# 1) 두 구현 판정 (각 75/75 기대)
python3 conformance.py --gil "python3 $ABS/gil.py"
go build -o /tmp/gil-bin go/main.go && python3 conformance.py --gil "/tmp/gil-bin"

# 2) 원격 부재 우아화 수동 재현 (git 있음, 원격 없음)
D=$(mktemp -d) && cd "$D" && git init -q -b main . && git config user.email t@t && git config user.name t
echo x > README.md && git add -A && git commit -qm init && mkdir chains
python3 "$ABS/gil.py" open test first-try --author clew --root ./chains --new-chain --git --push  # rc0 + 안내
python3 "$ABS/gil.py" step test C001-first-try 2 --root ./chains --push                            # rc0 + 안내
git log --oneline; git tag   # 로컬 커밋·태그 보존 확인

# 3) 변이 M1 — 원격 가드 제거 시 NO-REMOTE-GRACEFUL FAIL(74/75) 확인
```

## 실행 기록

- 실행 일시: 2026-07-16 · 환경: darwin 25.2.0, python3, go
- 소요: 사이클 1회분

### 수정 전 거친 모서리 (실측 — 설계 근거)

| 경로 | 수정 전 |
|---|---|
| `open --new-chain --git --push` | 커밋됨, 그러나 `_push_with_renumber`의 `git fetch origin` → **`fatal: 'origin' does not appear to be a git repository`, exit 1** |
| `step --push` | 커밋됨, 그러나 **`fatal: 푸시 대상을 설정하지 않았습니다 … git remote add`, exit 1** |
| `check=False` 경로(open non-newchain·reserve·round) | 실패를 **조용히 삼킴** (사용자는 push된 줄로 앎) |

→ C052 교훈의 두 얼굴: **오도 신호(날것 fatal)** + **침묵**.

### 수정 후 (H1)

**참조 구현** (원격 없음): `open --push` rc0, `step --push` rc0, `close --push` rc0 — 각각
`ℹ 원격이 없어 push를 건너뛴다 — 커밋은 로컬에 저장됐다. 원격 연결(git remote add origin <URL>) 후 …`
안내 출력. 로컬 커밋 3개 + 태그 `cycle/test/C001-first-try` 보존.

**Go 구현** (원격 없음): 동일 문면·rc0·커밋+태그 보존. **두 구현의 강등 문면·rc·부작용 완전 동일** (기각 d 거짓).

### 계약: NO-REMOTE-GRACEFUL

```
참조:  계약 준수 75/75  ✔ 이 구현은 gil이다
Go:    계약 준수 75/75  ✔ 이 구현은 gil이다   (74→75, 신설)
```

**변이 M1** (원격 가드 제거 → 수정 전 행동): `FAIL NO-REMOTE-GRACEFUL [rc=1 … fatal: 'origin' does not appear …]`, `74/75 ✘`. 계약이 이 행동을 실제로 집행한다(C038·C041 규율).

### 회귀 0 (기각 c)

- 판정기 양 구현 75/75, 기존 74항목 회귀 0.
- 실저장소(git·원격 있음): `fsck` 위반 0건(경고 36 선재), `verify` 변조 0건.
- 실 `--push`(원격 있음): 이 사이클 자신의 open·step 커밋이 origin/main에 정상 push — 원격 있을 때 push 불변.

### H2 — 네트워크 자세 문서화

README.md("Network posture")·README.ko.md("네트워크 자세") 절 신설: 자체 호출 0·텔레메트리 0,
외부는 `--push` 시 자기 원격 git push/fetch뿐, 원격 없으면 로컬 커밋만(C053 감사 근거와 일치).

### 범위 밖 관찰 (선재, 고치지 않음 — C044·C051 규율)

판정기 초기 실행에서 참조가 절대 `--root`(macOS `/var`→`/private/var` 심볼릭 링크 미해석)의
`relpath` 붕괴로 FAIL했으나 Go는 통과 — Go `relToRepo`가 심볼릭 링크를 해석하고 참조 `os.path.relpath`는
안 하는 **선재 경로 해석 비대칭**. C054 push 로직과 무관하고 tmpdir 환경 함정(C028·C029)이라
테스트를 realpath로 정규화해 의도(push 우아화)만 검증하게 했다. 비대칭 자체는 별도 후보로 남긴다.

## 기각 조건 판정

- (a) 크래시/rc≠0 → **거짓** · (b) 침묵 성공 → **거짓** · (c) 원격-있음 회귀 → **거짓** · (d) 두 구현 갈림 → **거짓**

**네 조건 모두 거짓 → 가설 지지(supported).**
