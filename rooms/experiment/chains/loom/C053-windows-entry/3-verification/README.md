# 3. 가설 검증

`SHA256SUMS-5targets.txt`는 수정된 워크플로 build 블록을 darwin에서 추출 실행한 산출물의 해시(B 증거). Windows 런타임 실행은 사전 등록된 수신자 검증 경계.

## 재현 방법

```bash
# B — 워크플로 build 블록 추출 실행 (loom/C024 규율: 신선 클론에서 그대로)
cd rooms/deployment/ariadne-spec/go
for T in darwin/arm64 darwin/amd64 linux/arm64 linux/amd64 windows/amd64; do
  EXT=""; [ "${T%/*}" = windows ] && EXT=".exe"
  GOOS="${T%/*}" GOARCH="${T#*/}" GO111MODULE=off go build -o "/tmp/wfdist/gil-${T%/*}-${T#*/}${EXT}" main.go
done
cd /tmp/wfdist && shasum -a 256 gil-* > SHA256SUMS && file gil-windows-amd64.exe   # PE32+

# C — 게이트 알고리즘 (PowerShell이 인코딩할 로직) 양경로
want=$(grep 'gil-windows-amd64.exe$' SHA256SUMS | awk '{print $1}')
got=$(shasum -a 256 gil-windows-amd64.exe | awk '{print $1}'); [ "$want" = "$got" ] && echo 승격
cp gil-windows-amd64.exe t.exe; printf '\x00' >> t.exe
[ "$want" != "$(shasum -a 256 t.exe|awk '{print $1}')" ] && echo 차단

# R — 코드 회귀 0
cd rooms/deployment/ariadne-spec
python3 conformance.py --gil "python3 $(pwd)/gil.py"                                   # 74/74
GO111MODULE=off go build -o /tmp/g go/main.go && python3 conformance.py --gil /tmp/g   # 74/74
```

## 실행 기록

- 일시: 2026-07-15. 환경: darwin 25.2.0(arm64), go1.26.2.
- **B1·B2 ✓**: build 블록이 **5타깃** 산출(기존 4 + `gil-windows-amd64.exe`). `file` → `PE32+ executable (console) x86-64, for MS Windows`. SHA256SUMS에 windows 포함(아티팩트 첨부).
- **C1 ✓ (게이트 정상 통과)**: SHA256SUMS 기대 해시 == 실제 해시 → `gil.exe` 승격.
- **C2 ✓ (게이트 위조 차단)**: 1바이트 변조 → 해시 불일치 → `gil.exe` 미생성. C037 "검증 안 된 바이너리는 태어나지 못한다"의 PowerShell판.
- **D1 ✓**: Windows PowerShell 블록이 3개 대문(README·README.ko·README.ai)에 존재, git-optional 문구 3곳, 기존 Unix 스니펫 불변. README.ai.md에 OS 분기(POSIX 셸 없으면 PowerShell) + git 선택 안내 추가. 낡은 "29/29" 3곳을 "전 항목 통과(스위트가 개수 출력)"로 교체(C039 — 낡는 숫자는 없애고 도구에 위임).
- **R ✓**: 참조·Go conformance **74/74**(코드 무변경 — 이 사이클은 워크플로·문서만). 실 저장소 회귀 0.

## 검증의 정직한 경계 (+ 방법 이탈 1건)

- **방법 이탈 (deviations.yaml 기록)**: 1-hypothesis는 C 게이트를 `pwsh`(PowerShell Core)로 실행 검증하려 했으나, **`pwsh` 설치가 이 환경에서 성립하지 않았다**(`powershell`·`powershell@preview` 캐스크 모두 바이너리 미배치, 각 exit 0이나 caskroom 부재). → **게이트 알고리즘을 이식 가능한 셸로 동치 검증**(C1·C2)하고, PowerShell **cmdlet 런타임**(Get-FileHash·Invoke-WebRequest·Select-String의 실제 동작)은 수신자 검증으로 이관. cmdlet은 문서된 표준 동작에 맞춰 구성. 실제 Windows PowerShell은 pwsh-on-Mac보다 오히려 진짜 수신 환경이라, 검증 소유자로 더 적합.
- **수신자 검증 경계**: 실제 Windows PC에서 (a) `.exe` 실행, (b) PowerShell 스니펫 end-to-end. 설치 URL(`gil-windows-amd64.exe`)은 **B가 배포되는 다음 태그부터** 해소된다(현재 v2.11.0엔 없음). C024 선례("수신자가 다른 환경에서 테스트 → 다음 사이클의 재료").
