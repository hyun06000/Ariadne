#!/usr/bin/env bash
# C044 변이 격추 — 각 계약을 하나씩 제거하면 정확히 대응 항목만 FAIL하는가 (C040 샌드박스 독립).
# M1 파이썬 커밋 chain.md 제거 → OPEN-NEWCHAIN-COMMIT
# M2 파이썬 fsck R14 제거     → FSCK-R14
# M3 Go 커밋 chain.md 제거    → OPEN-NEWCHAIN-COMMIT
# M4 Go fsck R14 제거         → FSCK-R14
set -uo pipefail
SPEC="$(cd "$(dirname "$0")/../../../../../deployment/ariadne-spec" && pwd)"
CONF="$SPEC/conformance.py"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

fails() { python3 "$CONF" --gil "$1" 2>&1 | grep '^FAIL' | sed -E 's/^FAIL ([A-Z0-9-]+):.*/\1/' | sort | tr '\n' ' '; echo; }

# ---------- M1: 파이썬 커밋에서 chain.md 제거 ----------
python3 - "$SPEC/gil.py" "$TMP/m1.py" <<'PY'
import sys; src=open(sys.argv[1]).read()
old='''        if new_chain:  # chain.md는 사이클 디렉토리 밖(체인 최상위)이라 별도 경로다 (이슈 #14, loom/C044)
            paths.append(os.path.relpath(os.path.join(chain_dir, "chain.md"), repo))
'''
assert old in src, "M1 패턴 불일치"; open(sys.argv[2],"w").write(src.replace(old,""))
PY
echo "### M1 파이썬 커밋 chain.md 제거 → 기대: OPEN-NEWCHAIN-COMMIT"
echo "  실제 FAIL: $(fails "python3 $TMP/m1.py")"

# ---------- M2: 파이썬 fsck R14 제거 ----------
python3 - "$SPEC/gil.py" "$TMP/m2.py" <<'PY'
import sys; src=open(sys.argv[1]).read()
old='''        if chains_root and not os.path.isfile(os.path.join(chains_root, ch, "chain.md")):
            violations.append(("R14", ch, "chain.md가 없다 — 체인의 문제 정의 문서가 커밋되지 않았다"))
'''
assert old in src, "M2 패턴 불일치"; open(sys.argv[2],"w").write(src.replace(old,""))
PY
echo "### M2 파이썬 fsck R14 제거 → 기대: FSCK-R14"
echo "  실제 FAIL: $(fails "python3 $TMP/m2.py")"

# ---------- Go 변이: main.go 복사본 빌드 ----------
mkdir -p "$TMP/go"
# M3: Go 커밋에서 chain.md 제거
python3 - "$SPEC/go/main.go" "$TMP/go/main.go" <<'PY'
import sys; src=open(sys.argv[1]).read()
old='''		paths := []string{rel}
		if newChain { // chain.md는 사이클 디렉토리 밖(체인 최상위)이라 별도 경로다 (이슈 #14, loom/C044)
			if cmRel, cerr2 := relToRepo(repo, filepath.Join(chainDir, "chain.md")); cerr2 == nil {
				paths = append(paths, cmRel)
			}
		}
		if _, err := gitChecked(repo, append([]string{"add", "-A", "--"}, paths...)...); err != nil {
			return err
		}
		if _, err := gitChecked(repo, append([]string{"commit", "-m",
			fmt.Sprintf("gil: open %s/%s — 1/5 %s\\n\\n%s", a.chain, cid, stepNames[1], title),
			"--"}, paths...)...); err != nil {
			return err
		}'''
new='''		if _, err := gitChecked(repo, "add", "-A", "--", rel); err != nil {
			return err
		}
		if _, err := gitChecked(repo, "commit", "-m",
			fmt.Sprintf("gil: open %s/%s — 1/5 %s\\n\\n%s", a.chain, cid, stepNames[1], title),
			"--", rel); err != nil {
			return err
		}'''
assert old in src, "M3 패턴 불일치"; open(sys.argv[2],"w").write(src.replace(old,new))
PY
(cd "$TMP/go" && go build -o "$TMP/gil-m3" main.go 2>&1 | head)
echo "### M3 Go 커밋 chain.md 제거 → 기대: OPEN-NEWCHAIN-COMMIT"
echo "  실제 FAIL: $(fails "$TMP/gil-m3")"

# M4: Go fsck R14 제거
python3 - "$SPEC/go/main.go" "$TMP/go/main.go" <<'PY'
import sys; src=open(sys.argv[1]).read()
old='''		// R14 (v0.6): 체인 디렉토리는 chain.md를 가져야 한다 — open --new-chain이 놓치던 표면 (이슈 #14).
		// 위반인 이유: R12(경고)와 달리 정당한 탈출구가 없다 — open --new-chain이 항상 chain.md를 만든다.
		if _, e := os.Stat(filepath.Join(root, ch, "chain.md")); e != nil {
			add("R14", ch, "chain.md가 없다 — 체인의 문제 정의 문서가 커밋되지 않았다")
		}
'''
assert old in src, "M4 패턴 불일치"; open(sys.argv[2],"w").write(src.replace(old,""))
PY
(cd "$TMP/go" && go build -o "$TMP/gil-m4" main.go 2>&1 | head)
echo "### M4 Go fsck R14 제거 → 기대: FSCK-R14"
echo "  실제 FAIL: $(fails "$TMP/gil-m4")"
