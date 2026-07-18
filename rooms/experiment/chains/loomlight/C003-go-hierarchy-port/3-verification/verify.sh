#!/usr/bin/env bash
# loomlight/C003 검증 — Go에 gil web --hierarchy 이식. 5측정을 재현 가능하게 실행한다.
# 재현: 저장소 루트에서  bash rooms/experiment/chains/loomlight/C003-go-hierarchy-port/3-verification/verify.sh
# 요구: Go 툴체인(go1.23+). $HOME/goroot/go/bin 또는 PATH의 go를 쓴다.
# 핵심 계약: 참조(gil.py)와 Go(main.go)의 `web --hierarchy` 산출물이 **바이트 동일**,
#            `--hierarchy` 없는 기본 출력·conformance는 회귀 0(opt-in).
# 종료 코드: 전 측정 통과 0, 하나라도 실패 1.
set -u
ROOT="$(cd "$(dirname "$0")/../../../../../.." && pwd)"   # 저장소 루트
SPEC="$ROOT/rooms/deployment/ariadne-spec"
GIL_PY="$SPEC/gil.py"
GO_SRC="$SPEC/go/main.go"
CHAINS="$ROOT/rooms/experiment/chains"
OUT="$(mktemp -d)"
FAIL=0
pass(){ echo "PASS $1"; }
fail(){ echo "FAIL $1: $2"; FAIL=1; }

# Go 탐색 — 없으면 정직히 스킵(C053: 흉내내지 않는다).
export PATH="$HOME/goroot/go/bin:$PATH"
if ! command -v go >/dev/null 2>&1; then
  echo "SKIP: Go 툴체인 없음 — 이 검증은 Go 빌드가 필요하다 (정직히 스킵)"; exit 2
fi
echo "== Go: $(go version) =="
echo "== 산출물: $OUT =="

# ---- Go 빌드 (실측: 정말 되는가) ----
if go build -o "$OUT/gil-go" "$GO_SRC" 2>"$OUT/build.err"; then
  pass "BUILD-go (go build main.go rc0)"
else
  fail "BUILD-go" "$(head -3 "$OUT/build.err")"; echo "== 빌드 실패로 중단 =="; exit 1
fi
GIL_GO="$OUT/gil-go"

# ---- M1: 위계 바이트 동일 (가설 본체) — 참조 vs Go ----
python3 "$GIL_PY" web "$CHAINS" --hierarchy -o "$OUT/py-hier.html" --title "cmp" >/dev/null 2>&1
"$GIL_GO"        web "$CHAINS" --hierarchy -o "$OUT/go-hier.html" --title "cmp" >/dev/null 2>&1
if cmp -s "$OUT/py-hier.html" "$OUT/go-hier.html"; then
  pass "M1-hierarchy-byte-identical (참조 == Go)"
else
  fail "M1-hierarchy-byte-identical" "$(cmp "$OUT/py-hier.html" "$OUT/go-hier.html" 2>&1 | head -1)"
fi

# ---- M2: 기본 바이트 동일 (회귀 0) — 같은 순간 참조 vs Go + 변경 전 Go와도 동일 ----
python3 "$GIL_PY" web "$CHAINS" -o "$OUT/py-def.html" --title "cmp" >/dev/null 2>&1
"$GIL_GO"        web "$CHAINS" -o "$OUT/go-def.html" --title "cmp" >/dev/null 2>&1
if cmp -s "$OUT/py-def.html" "$OUT/go-def.html"; then
  pass "M2-default-byte-identical (참조 == Go, opt-in 계약)"
else
  fail "M2-default-byte-identical" "$(cmp "$OUT/py-def.html" "$OUT/go-def.html" 2>&1 | head -1)"
fi
# 변경 전 Go(origin/main 또는 이 사이클 open 이전)와 기본 출력 바이트 동일 — 이 사이클이 기본을 안 건드림.
if git -C "$ROOT" show origin/main:rooms/deployment/ariadne-spec/go/main.go > "$OUT/main-old.go" 2>/dev/null && [ -s "$OUT/main-old.go" ]; then
  if go build -o "$OUT/gil-old" "$OUT/main-old.go" 2>/dev/null; then
    "$OUT/gil-old" web "$CHAINS" -o "$OUT/go-old-def.html" --title "cmp" >/dev/null 2>&1
    "$GIL_GO"      web "$CHAINS" -o "$OUT/go-new-def.html" --title "cmp" >/dev/null 2>&1
    if cmp -s "$OUT/go-old-def.html" "$OUT/go-new-def.html"; then
      pass "M2b-default-unchanged-by-cycle (변경 전 Go == 변경 후 Go 기본)"
    else
      fail "M2b-default-unchanged-by-cycle" "$(cmp "$OUT/go-old-def.html" "$OUT/go-new-def.html" 2>&1 | head -1) (열림 사이클 ago 분경계면 재실행)"
    fi
  else
    echo "note: 변경 전 Go 빌드 실패 — M2b 생략(참조 대조 M2로 갈음)"
  fi
else
  echo "note: origin/main Go 소스 없음 — M2b 생략(참조 대조 M2로 갈음)"
fi

# ---- M3: Go conformance 회귀 0 (절대 경로 — C028·C043·C045) ----
if python3 "$SPEC/conformance.py" --gil "$GIL_GO" > "$OUT/conf.txt" 2>&1; then
  pass "M3-go-conformance ($(grep -oE '[0-9]+/[0-9]+' "$OUT/conf.txt" | tail -1))"
else
  fail "M3-go-conformance" "$(grep '^FAIL' "$OUT/conf.txt" | head -3)"
fi

# ---- M4: 위계 계약 — 외부 리소스 0, 실행 JS 0, 3단 구조 참조와 동수 ----
EXT=$(grep -oE '(src=|href=|url\(|@import)[^">]*https?://' "$OUT/go-hier.html" | wc -l | tr -d ' ')
NSCRIPT=$(grep -oE '<script[^>]*>' "$OUT/go-hier.html" | wc -l | tr -d ' ')
NDATA=$(grep -oE '<script type="application/json" id="gil-data">' "$OUT/go-hier.html" | wc -l | tr -d ' ')
if [ "$EXT" = "0" ] && [ "$NSCRIPT" = "1" ] && [ "$NDATA" = "1" ]; then
  pass "M4-self-contained-no-js (외부 $EXT · script $NSCRIPT · 그중 데이터 $NDATA)"
else
  fail "M4-self-contained-no-js" "외부=$EXT script=$NSCRIPT data=$NDATA"
fi
# 구조 카운트가 참조와 Go에서 동수 (바이트 동일이면 자명하나 명시적 표식으로 남긴다).
for tag in 'class="hchain"' 'class="hcycle"' 'class="hstep"'; do
  P=$(grep -o "$tag" "$OUT/py-hier.html" | wc -l | tr -d ' ')
  G=$(grep -o "$tag" "$OUT/go-hier.html" | wc -l | tr -d ' ')
  [ "$P" = "$G" ] && pass "M4-count $tag (참조=$P Go=$G)" || fail "M4-count $tag" "참조=$P Go=$G"
done

# ---- M5: 자동 재굽기 위계 보존 (C042 확장) — Go가 bake.hierarchy를 왕복 보존 ----
M5DIR="$OUT/m5"; mkdir -p "$M5DIR/rooms/experiment/chains"
( cd "$M5DIR" && git init -q && git config user.email t@t && git config user.name t \
  && python3 "$GIL_PY" open demo first --new-chain --author t --title "데모" >/dev/null 2>&1 \
  && git add -A && git commit -qm init >/dev/null )
"$GIL_GO" web "$M5DIR/rooms/experiment/chains" -o "$M5DIR/viewer.html" --hierarchy >/dev/null 2>&1
BEFORE=$(grep -c 'class="hchain"' "$M5DIR/viewer.html")
( cd "$M5DIR" && "$GIL_GO" step demo C001-first 2 --no-commit >/dev/null 2>&1 )
AFTER=$(grep -c 'class="hchain"' "$M5DIR/viewer.html")
HKEY=$(python3 - "$M5DIR/viewer.html" <<'PY'
import re,json,sys
t=open(sys.argv[1],encoding="utf-8").read()
m=re.search(r'id="gil-data">(.*?)</script>',t,re.S)
b=json.loads(m.group(1)).get("bake",{}) if m else {}
print(1 if b.get("hierarchy") is True else 0)
PY
)
if [ "$BEFORE" = "1" ] && [ "$AFTER" = "1" ] && [ "$HKEY" = "1" ]; then
  pass "M5-go-rebake-preserves-hierarchy (step 후에도 위계·bake.hierarchy 보존)"
else
  fail "M5-go-rebake-preserves-hierarchy" "before=$BEFORE after=$AFTER bake.hierarchy=$HKEY"
fi

echo "== 산출물 보존: $OUT =="
# 커밋용 표본: loomlight 체인만 Go로 구운 위계 뷰어(작고 자기완결). 참조와 바이트 동일임은 M1이 담당.
"$GIL_GO" web "$CHAINS" --chain loomlight --hierarchy -o "$(dirname "$0")/sample-hierarchy-go-loomlight.html" \
  --title "Ariadne 위계 뷰어 — Go·loomlight (표본)" >/dev/null 2>&1 && echo "표본 저장: sample-hierarchy-go-loomlight.html"
[ "$FAIL" = "0" ] && echo "== 전 측정 통과 ==" || echo "== 실패 있음 =="
exit $FAIL
