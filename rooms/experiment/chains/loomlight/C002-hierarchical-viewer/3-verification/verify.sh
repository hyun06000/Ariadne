#!/usr/bin/env bash
# loomlight/C002 검증 — 위계 뷰어(--hierarchy)의 5측정을 재현 가능하게 실행한다.
# 재현: 저장소 루트에서  bash rooms/experiment/chains/loomlight/C002-hierarchical-viewer/3-verification/verify.sh
# 종료 코드: 전 측정 통과 0, 하나라도 실패 1.
set -u
ROOT="$(cd "$(dirname "$0")/../../../../../.." && pwd)"   # 저장소 루트
SPEC="$ROOT/rooms/deployment/ariadne-spec"
GIL="$SPEC/gil.py"
CHAINS="$ROOT/rooms/experiment/chains"
OUT="$(mktemp -d)"
FAIL=0
pass(){ echo "PASS $1"; }
fail(){ echo "FAIL $1: $2"; FAIL=1; }

echo "== 산출물: $OUT =="

# ---- M1: 기본(플래그 없음) 출력이 개선 전 gil.py와 바이트 동일 (하위호환) ----
# 개선 전 gil.py를 origin/main에서 꺼내 같은 체인 데이터로 굽고 신 gil.py의 기본 출력과 cmp.
git -C "$ROOT" show origin/main:rooms/deployment/ariadne-spec/gil.py > "$OUT/gil-old.py" 2>/dev/null
if [ -s "$OUT/gil-old.py" ]; then
  # ago(분 전) 흔들림을 없애기 위해 열린 사이클이 없는 체인(genesis)만 대상으로 비교한다.
  python3 "$OUT/gil-old.py" web "$CHAINS" --chain genesis -o "$OUT/old.html" --title "cmp" >/dev/null 2>&1
  python3 "$GIL"            web "$CHAINS" --chain genesis -o "$OUT/new.html" --title "cmp" >/dev/null 2>&1
  if cmp -s "$OUT/old.html" "$OUT/new.html"; then
    pass "M1-byte-identical-default (genesis, old gil.py == new gil.py)"
  else
    fail "M1-byte-identical-default" "$(cmp "$OUT/old.html" "$OUT/new.html" 2>&1 | head -1)"
  fi
  # 전체 저장소 기본 출력도 비교(열린 사이클의 ago는 같은 순간 실행이라 통상 일치)
  python3 "$OUT/gil-old.py" web "$CHAINS" -o "$OUT/old-all.html" --title "cmp" >/dev/null 2>&1
  python3 "$GIL"            web "$CHAINS" -o "$OUT/new-all.html" --title "cmp" >/dev/null 2>&1
  if cmp -s "$OUT/old-all.html" "$OUT/new-all.html"; then
    pass "M1b-byte-identical-default-allchains"
  else
    fail "M1b-byte-identical-default-allchains" "차이(ago 분경계면 재실행): $(cmp "$OUT/old-all.html" "$OUT/new-all.html" 2>&1 | head -1)"
  fi
else
  fail "M1-byte-identical-default" "origin/main gil.py를 꺼내지 못함"
fi

# ---- M2: 참조 conformance 회귀 0 ----
if python3 "$SPEC/conformance.py" --gil "python3 $GIL" --skip-git > "$OUT/conf.txt" 2>&1; then
  pass "M2-conformance ($(grep -o '[0-9]*/[0-9]*' "$OUT/conf.txt" | tail -1))"
else
  fail "M2-conformance" "$(grep '^FAIL' "$OUT/conf.txt" | head -3)"
fi
grep -q "WEB-JSON" "$OUT/conf.txt" && grep -q "^PASS WEB-SELFCONTAINED" "$OUT/conf.txt" \
  && grep -q "^PASS WEB-REFRESH" "$OUT/conf.txt" \
  && pass "M2b-WEB-checks-present-and-green" || fail "M2b-WEB-checks" "WEB-* 중 일부 누락/실패"

# ---- 위계 뷰어 생성 (전체 저장소) ----
python3 "$GIL" web "$CHAINS" -o "$OUT/hier.html" --hierarchy --title "Ariadne 위계" >/dev/null 2>&1

# ---- M3: 위계 계약 — 외부 리소스 0, 실행 JS 0 ----
EXT=$(grep -oE '(src=|href=|url\(|@import)[^">]*https?://' "$OUT/hier.html" | wc -l | tr -d ' ')
# <script> 태그는 gil-data(application/json, 실행 아님) 하나뿐이어야 한다.
NSCRIPT=$(grep -oE '<script[^>]*>' "$OUT/hier.html" | wc -l | tr -d ' ')
NDATA=$(grep -oE '<script type="application/json" id="gil-data">' "$OUT/hier.html" | wc -l | tr -d ' ')
if [ "$EXT" = "0" ] && [ "$NSCRIPT" = "1" ] && [ "$NDATA" = "1" ]; then
  pass "M3-self-contained-no-js (외부 $EXT · script $NSCRIPT · 그중 데이터 $NDATA)"
else
  fail "M3-self-contained-no-js" "외부=$EXT script=$NSCRIPT data=$NDATA"
fi

# ---- M4: 위계 3단 동작 (구조 카운트) ----
NCHAINS_DET=$(grep -oE 'details class="hchain" id="chain-' "$OUT/hier.html" | wc -l | tr -d ' ')
NCYC_DET=$(grep -oE 'details class="hcycle" id="cycle-' "$OUT/hier.html" | wc -l | tr -d ' ')
NTOC=$(grep -oE '<nav class="htoc">' "$OUT/hier.html" | wc -l | tr -d ' ')
NSTEP=$(grep -oE 'details class="hstep"' "$OUT/hier.html" | wc -l | tr -d ' ')
# 진실값은 뷰어 자신의 내장 gil-data JSON에서 뽑는다 (원장을 그대로 반사한 그래프 노드 수).
# find cycle.yaml은 rounds/ 하위의 라운드 cycle.yaml까지 세어 그래프 노드 수와 다르므로 쓰지 않는다.
COUNTS=$(python3 - "$OUT/hier.html" <<'PY'
import re,json,sys
t=open(sys.argv[1],encoding="utf-8").read()
d=json.loads(re.search(r'id="gil-data">(.*?)</script>',t,re.S).group(1))["chains"]
print(len(d), sum(len(c["cycles"]) for c in d.values()))
PY
)
NCHAINS_REAL=$(echo "$COUNTS" | cut -d' ' -f1)
NCYC_REAL=$(echo "$COUNTS" | cut -d' ' -f2)
if [ "$NTOC" = "1" ] && [ "$NCHAINS_DET" = "$NCHAINS_REAL" ] && [ "$NCYC_DET" = "$NCYC_REAL" ] \
   && [ "$NSTEP" = "$((NCYC_REAL * 5))" ]; then
  pass "M4-hierarchy-3levels (목차 $NTOC · 체인 $NCHAINS_DET/$NCHAINS_REAL · 사이클 $NCYC_DET/$NCYC_REAL · 스텝 $NSTEP=$((NCYC_REAL*5)))"
else
  fail "M4-hierarchy-3levels" "목차=$NTOC 체인=$NCHAINS_DET/$NCHAINS_REAL 사이클=$NCYC_DET/$NCYC_REAL 스텝=$NSTEP(기대 $((NCYC_REAL*5)))"
fi

# L3 내용 실재: 이 사이클(C002)의 5-report 앵커 안에 실제 보고서 문구가 들어갔는가 (닫은 뒤 확인용 표식)
if grep -q 'id="cycle-loomlight-C002-hierarchical-viewer"' "$OUT/hier.html" \
   && grep -q '<table class="hmeta">' "$OUT/hier.html"; then
  pass "M4b-cycle-anchor-and-meta-present"
else
  fail "M4b-cycle-anchor-and-meta" "C002 앵커/메타표 누락"
fi

# ---- M5: --hierarchy + --refresh 공존 ----
python3 "$GIL" web "$CHAINS" -o "$OUT/hr.html" --hierarchy --refresh 3 --title "t" >/dev/null 2>&1
HAS_META=$(grep -c 'http-equiv="refresh" content="3"' "$OUT/hr.html")
HAS_HKEY=$(python3 - "$OUT/hr.html" <<'PY'
import re,json,sys
t=open(sys.argv[1],encoding="utf-8").read()
m=re.search(r'id="gil-data">(.*?)</script>',t,re.S)
b=json.loads(m.group(1)).get("bake",{}) if m else {}
print(1 if (b.get("hierarchy") is True and b.get("refresh")==3) else 0)
PY
)
EXT5=$(grep -oE '(src=|href=|url\(|@import)[^">]*https?://' "$OUT/hr.html" | wc -l | tr -d ' ')
if [ "$HAS_META" = "1" ] && [ "$HAS_HKEY" = "1" ] && [ "$EXT5" = "0" ]; then
  pass "M5-hierarchy+refresh-coexist (meta=$HAS_META bake.hierarchy&refresh=$HAS_HKEY 외부=$EXT5)"
else
  fail "M5-hierarchy+refresh-coexist" "meta=$HAS_META bakekeys=$HAS_HKEY ext=$EXT5"
fi

# ---- M6: 자동 재굽기 보존 — hierarchy가 bake로 왕복 보존되고 기본은 키가 아예 없다 (C042 확장) ----
M6=$(cd "$SPEC" && python3 - "$CHAINS" <<'PY'
import gil,json,re,sys
root=sys.argv[1]
data=gil._build_web_data(root)
ph=gil.render_web_page(data,"T","2026-07-19",None,None,hierarchy=True,chains_root=root)
pf=gil.render_web_page(data,"T","2026-07-19",None,None,hierarchy=False)
_,_,_,hh=gil._bake_meta(ph); _,_,_,hf=gil._bake_meta(pf)
bf=json.loads(re.search(r'id="gil-data">(.*?)</script>',pf,re.S).group(1))["bake"]
print(1 if (hh is True and hf is False and "hierarchy" not in bf) else 0)
PY
)
[ "$M6" = "1" ] && pass "M6-rebake-preserves-hierarchy (기본 bake엔 hierarchy 키 부재 → 바이트 동일)" \
  || fail "M6-rebake-preserves-hierarchy" "왕복 보존 실패"

echo "== 산출물 보존: $OUT (hier.html 등) =="
# 커밋용 표본은 loomlight 체인만(작고 자기완결) — 3단 위계를 그대로 보여준다. 전체 저장소 검증은 위 측정이 담당.
python3 "$GIL" web "$CHAINS" --chain loomlight --hierarchy -o "$(dirname "$0")/sample-hierarchy-loomlight.html" \
  --title "Ariadne 위계 뷰어 — loomlight (표본)" >/dev/null 2>&1 && echo "표본 저장: sample-hierarchy-loomlight.html"
[ "$FAIL" = "0" ] && echo "== 전 측정 통과 ==" || echo "== 실패 있음 =="
exit $FAIL
