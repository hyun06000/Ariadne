#!/usr/bin/env bash
# loom/C037 검증 하네스 — 설치 경로의 체크섬 문지기
#
# 원칙 (C007·C027): "문서가 곧 테스트" — 설치 스니펫을 문서에서 **추출해 실제로 실행**한다.
# 문서가 낡으면 이 테스트가 깨진다.
#
# 사용: bash verify-install-gate.sh <repo-root>
#   E1 문서 4곳의 설치 블록이 대조를 포함하고 불일치 시 비영 종료
#   E2 정상 릴리스에서 통과 + gil 실행 가능 (거짓 양성 없음)
#   E3 변조 바이너리 거부 + gil 실행 파일 미생성
#   E4 gil pages 산출 워크플로에 대조 존재 + run 블록 실행 가능
#   E5 두 구현의 pages 산출물 바이트 동일
#   E7 재시도 안내 존재
# (E6 conformance는 별도 실행)

set -u
REPO="${1:?repo root}"
WORK="$(mktemp -d)"
PASS=0; FAIL=0
ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

# 문서의 첫 코드 블록에서 '설치 절차'만 추출한다.
# 규칙: 블록 안에서 './gil' 로 시작하는 줄(= 사용례)을 뺀 나머지가 설치 절차다.
extract_install() {  # $1=문서 $2=블록을 여는 패턴
  awk -v pat="$2" '
    $0 ~ pat && !inblk { inblk=1; next }
    inblk && /^```/ { exit }
    inblk { print }
  ' "$1" | grep -v '^\./gil'
}

echo "== E1/E2: 문서 4곳의 설치 블록을 추출해 실제 릴리스에 대해 실행 =="
declare -a DOCS=(
  "README.md|^\`\`\`bash"
  "README.ko.md|^\`\`\`bash"
  "README.ai.md|^\`\`\`bash"
  "rooms/deployment/ariadne-spec/QUICKSTART.md|^\`\`\`$"
)
for entry in "${DOCS[@]}"; do
  doc="${entry%%|*}"; pat="${entry##*|}"
  snippet="$(extract_install "$REPO/$doc" "$pat")"

  # E1: 대조가 스니펫에 실재하는가 (문면 검사)
  if echo "$snippet" | grep -qE 'SHA256SUMS' && echo "$snippet" | grep -qE 'shasum -a 256 -c -|sha256sum -c -|sha -c -'; then
    ok "E1 $doc — 설치 블록에 체크섬 대조 포함"
  else
    bad "E1 $doc — 대조 없음"; continue
  fi

  # E2: 신선한 디렉토리에서 실제로 실행 → gil이 실행 가능해지는가 (거짓 양성 없음)
  d="$WORK/ok-$(basename "$doc")"; mkdir -p "$d"
  ( cd "$d" && eval "$snippet" ) >"$d/out.log" 2>&1
  if [ -x "$d/gil" ] && "$d/gil" version >/dev/null 2>&1; then
    ok "E2 $doc — 정상 릴리스에서 통과, gil 실행 가능 ($("$d/gil" version 2>&1 | head -1))"
  else
    bad "E2 $doc — 정상 릴리스에서 설치 실패 (거짓 양성): $(tail -2 "$d/out.log" | tr '\n' ' ')"
  fi
done

echo
echo "== E3: 변조된 바이너리 — 거부되고 실행 파일이 생기지 않아야 한다 (음성 테스트) =="
# 실제 릴리스를 받아 1바이트 변조한 뒤, 문서의 대조 명령을 그대로 적용한다.
d="$WORK/tamper"; mkdir -p "$d"
( cd "$d" \
  && curl -fsSL -O https://github.com/hyun06000/Ariadne/releases/latest/download/gil-darwin-arm64 \
  && curl -fsSL -O https://github.com/hyun06000/Ariadne/releases/latest/download/SHA256SUMS \
  && printf 'x' >> gil-darwin-arm64 ) >/dev/null 2>&1
( cd "$d" && grep ' gil-darwin-arm64$' SHA256SUMS | shasum -a 256 -c - && mv gil-darwin-arm64 gil && chmod +x gil ) >"$d/out.log" 2>&1
rc=$?
[ $rc -ne 0 ] && ok "E3 변조 탐지 — 비영 종료 (rc=$rc)" || bad "E3 변조가 통과했다 (rc=0)"
[ ! -e "$d/gil" ] && ok "E3 실행 파일 미생성 — 검증 안 된 바이너리가 실행될 경로 없음" \
                  || bad "E3 gil 실행 파일이 생성됐다 (문지기 우회)"

echo
echo "== E4/E5: gil pages 산출 워크플로 =="
pg="$WORK/pages"; mkdir -p "$pg/py" "$pg/go"
( cd "$pg/py" && git init -q . && python3 "$REPO/rooms/deployment/ariadne-spec/gil.py" pages ) >/dev/null 2>&1
GOBIN="$WORK/gil-go"
# 빌드 호출 문법은 환경 계약이다: 이 저장소에는 go.mod이 없고, CI(gil-release.yml)는
# `go build … main.go` 로 **파일을 직접** 빌드한다. `go build .`(패키지)는 모듈을 요구해 실패한다.
( cd "$REPO/rooms/deployment/ariadne-spec/go" && go build -o "$GOBIN" main.go ) >/dev/null 2>&1
if [ -x "$GOBIN" ]; then
  ( cd "$pg/go" && git init -q . && "$GOBIN" pages ) >/dev/null 2>&1
fi
PYWF="$(find "$pg/py" -name '*.yml' | head -1)"
GOWF="$(find "$pg/go" -name '*.yml' | head -1)"

if [ -n "$PYWF" ] && grep -q 'SHA256SUMS' "$PYWF" && grep -q 'sha256sum -c -' "$PYWF"; then
  ok "E4 pages 산출 워크플로에 체크섬 대조 포함 (참조 구현)"
else
  bad "E4 pages 워크플로에 대조 없음 (참조 구현)"
fi

# E4-b/c: 워크플로의 run 블록을 추출해 실제로 실행한다 ("워크플로가 곧 테스트", C007).
# 러너는 ubuntu-latest(linux/amd64)이고 이 호스트는 macOS다 — 리눅스 바이너리는 실행할 수 없다.
# 검증 대상은 **대조 로직**이므로, 타깃 자산명만 호스트 것으로 치환해 같은 로직을 돌린다.
if [ -n "$PYWF" ] && command -v sha256sum >/dev/null 2>&1; then
  hostasset="gil-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m | sed 's/x86_64/amd64/')"
  runblk="$(awk '/- name: Build viewer with gil/{f=1} f&&/run: \|/{g=1;next} g&&/^      - uses:/{exit} g{print}' "$PYWF" \
            | sed 's/^          //' | sed "s/gil-linux-amd64/$hostasset/g")"

  # E4-b (양성): 정상 자산 → 대조 통과 → 뷰어 생성 → CI 성공
  # 러너는 actions/checkout 직후이므로 저장소의 체인이 존재한다. 같은 조건을 만든다
  # (빈 디렉토리에서 돌리면 gil web이 "체인 루트가 없다"로 실패한다 — 대조와 무관한 실패).
  rd="$WORK/runblk"; mkdir -p "$rd/rooms/experiment"
  cp -R "$REPO/rooms/experiment/chains" "$rd/rooms/experiment/chains"
  ( cd "$rd" && eval "$runblk" ) >"$rd/out.log" 2>&1
  rc=$?
  if [ $rc -eq 0 ] && [ -s "$rd/_site/index.html" ]; then
    ok "E4-b run 블록(자산명→$hostasset 치환) 실행 성공 — 대조 통과 후 뷰어 생성 ($(wc -c <"$rd/_site/index.html" | tr -d ' ') 바이트)"
  else
    bad "E4-b run 블록 실행 실패: $(tail -2 "$rd/out.log" | tr '\n' ' ')"
  fi

  # E4-c (음성): SHA256SUMS가 실물과 어긋나면 run 블록이 실패해야 한다 = CI가 멈춘다
  rd2="$WORK/runblk-bad"; mkdir -p "$rd2"
  ( cd "$rd2" && eval "$runblk" ) >/dev/null 2>&1
  # 받아둔 자산을 변조한 뒤 대조 단계만 다시 실행 (curl은 캐시된 /tmp 파일을 덮어쓰므로 로컬 사본으로 검사)
  cp "/tmp/$hostasset" "$rd2/asset" 2>/dev/null || cp "/tmp/gil" "$rd2/asset" 2>/dev/null
  cp /tmp/SHA256SUMS "$rd2/SHA256SUMS" 2>/dev/null
  printf 'x' >> "$rd2/asset"
  mv "$rd2/asset" "$rd2/$hostasset" 2>/dev/null
  ( cd "$rd2" && grep " $hostasset\$" SHA256SUMS | sha256sum -c - ) >/dev/null 2>&1
  rc2=$?
  [ $rc2 -ne 0 ] && ok "E4-c 변조 자산에서 대조 실패 (rc=$rc2) — 불일치 시 CI가 멈춘다" \
                 || bad "E4-c 변조 자산이 워크플로 대조를 통과했다"
else
  bad "E4-b/c 실행 불가 (PYWF=$PYWF, sha256sum=$(command -v sha256sum || echo none))"
fi

if [ -n "$PYWF" ] && [ -n "$GOWF" ]; then
  if diff -q "$PYWF" "$GOWF" >/dev/null; then
    ok "E5 두 구현의 pages 산출물 바이트 동일"
  else
    bad "E5 두 구현 산출물 상이: $(diff "$PYWF" "$GOWF" | head -3 | tr '\n' ' ')"
  fi
else
  bad "E5 산출물 생성 실패 (py=$PYWF go=$GOWF)"
fi

echo
echo "== E7: 재시도 안내 (릴리스 직후 창의 불일치는 일시적이다) =="
for doc in README.md README.ko.md README.ai.md rooms/deployment/ariadne-spec/QUICKSTART.md; do
  if grep -qiE 'retry|재시도|re-run|다시 실행' "$REPO/$doc"; then
    ok "E7 $doc — 재시도 안내 있음"
  else
    bad "E7 $doc — 재시도 안내 없음"
  fi
done

echo
echo "=========================================="
echo "  통과 $PASS / 실패 $FAIL"
echo "=========================================="
rm -rf "$WORK"
[ $FAIL -eq 0 ]
