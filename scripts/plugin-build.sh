#!/bin/sh
# plugin-build.sh — 배포 저장소를 **조립한다**(Ariadne 이 진실원, 저쪽은 산물).
#
# 왜 있나. 비개발자가 gil 을 쓰려면 지금은 ① 바이너리를 손으로 받아 깔고 ② MCP 설정 파일을
# 손으로 고치고 ③ 앱을 재시작해야 한다. 셋 다 실사용에서 막힌 자리다. 플러그인은 그 셋을
# Customize → Plugins → Install 로 접는다. 그리고 `.mcp.json` 이 `${CLAUDE_PLUGIN_ROOT}` 로
# 자기 안의 바이너리를 가리키므로 **설정에 절대경로가 안 박힌다** — #51 이 값을 치른 사고가
# 원리적으로 안 난다.
#
# 왜 저장소를 가르나. 마켓플레이스 원본은 **git 저장소여야 하고**(Desktop·Cowork 의 Add
# marketplace UI 는 로컬 경로를 안 받는다), 그러려면 15MB 바이너리가 git 안에 있어야 한다.
# 그걸 개발 저장소에 넣으면 릴리스마다 이력이 부푼다. 그래서 배포용 저장소를 따로 둔다:
# 매니페스트는 여기(Ariadne)가 원본이고, 저쪽은 매번 이 스크립트가 다시 조립한다.
#
# 쓰는 법:
#   scripts/plugin-build.sh                      (기본 대상: ../gil-plugin-local)
#   scripts/plugin-build.sh 3.59.0               (버전 지정)
#   scripts/plugin-build.sh 3.59.0 /다른/경로     (대상 지정)
#
# **`go/gil` 은 건드리지 않는다.** 처음엔 거기 굽고 복사했는데, 그 한 줄이 시험 러너가 집어
# 가는 바이너리를 릴리스 각인본으로 덮어 전체 판이 6개 빨개졌다 — 코드는 하나도 안 바뀐 채로.
# 도구가 다른 도구의 산물을 조용히 바꾸면 그 뒤의 모든 판정이 남의 상태 위에서 난다.
set -e
here=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$here/.." && pwd)
GO="$REPO/project/gil-v3-redesign/go"
SRC="$REPO/project/gil-v3-redesign/plugin"   # 매니페스트 원본
DIST=${2:-$(dirname "$REPO")/gil-plugin-local}

# **버전은 손으로 안 적는다.** 매니페스트에 박아 두면 릴리스마다 한쪽이 낡는다(이 저장소가
# 여러 번 물린 자리다). 인자로 주거나, 없으면 최근 태그에서 읽는다. 같은 값 하나가 바이너리
# 각인과 매니페스트 양쪽에 간다.
# **같은 값인데 형식이 둘이다.** 바이너리 각인은 릴리스와 같은 `v` 붙은 태그여야 하고
# (scripts/release-build.sh 가 `v` 를 강제한다 — 버전 문의가 그 형식으로 비교한다),
# plugin.json 의 version 은 semver 라 `v` 가 없다. 처음엔 하나로 뭉쳐 `v` 를 떼었더니
# 각인이 `3.58.3` 이 되어 `latest`(v3.58.3)와 문자열이 달라졌고, handoff 가 태연히
# **"이 자리는 최신 릴리스보다 앞선다"** 고 답했다. 같은 사실을 두 형식으로 낼 때는
# 두 형식을 **한 값에서** 만든다 — 그래야 한쪽만 낡지 않는다.
TAG=${1:-$(git -C "$REPO" describe --tags --abbrev=0 2>/dev/null)}
TAG=${TAG:-v0.0.0}
case "$TAG" in v*) ;; *) TAG="v$TAG" ;; esac
VERSION=${TAG#v}

# **낡은 것을 남기지 않는다.** cp 만 하면 이름을 바꾼 뒤에도 옛 파일이 그대로 실려 나간다 —
# 실제로 `bin/` 을 `servers/` 로 옮기는 이 변경에서 그 자리가 났다. 조립은 매번 처음부터.
rm -rf "$DIST/gil"
mkdir -p "$DIST/gil/servers"
echo "→ 매니페스트를 옮긴다: $SRC → $DIST"
cp "$SRC/.claude-plugin/marketplace.json" "$DIST/.claude-plugin/marketplace.json" 2>/dev/null || {
  mkdir -p "$DIST/.claude-plugin"; cp "$SRC/.claude-plugin/marketplace.json" "$DIST/.claude-plugin/marketplace.json"; }
mkdir -p "$DIST/gil/.claude-plugin"
cp "$SRC/gil/.claude-plugin/plugin.json" "$DIST/gil/.claude-plugin/plugin.json"
cp "$SRC/gil/.mcp.json" "$DIST/gil/.mcp.json"

# **`bin/` 이 아니다.** 실측(상현님, 2026-08-10): Cowork(claude.ai 호스팅)가 거부한다 —
#   "Plugin contains a top-level bin/ directory. claude.ai-hosted plugins may not ship bin/
#    executables because they are added to PATH on the CLI but are not shown on the admin
#    approval surface. Declare executable entry points via hooks, commands, or mcpServers instead."
# `bin/` 은 예약 자리다(플러그인이 켜져 있는 동안 그 안의 것이 Bash 툴의 PATH 에 올라간다).
# 우리는 그걸 원한 적이 없다 — 우리 진입점은 `.mcp.json` 하나다. 그래서 이름을 옮긴다.
# **Claude Code 는 통과시켰다** — 표면마다 검사가 다르다는 것을 여기서 처음 봤다.
echo "→ 바이너리를 굽는다 → $DIST/gil/servers/gil  (각인 $TAG · 매니페스트 $VERSION)"
(cd "$GO" && go build -ldflags "-X main.gilVersion=$TAG" -o "$DIST/gil/servers/gil" .)
chmod +x "$DIST/gil/servers/gil"

python3 - "$DIST/gil/.claude-plugin/plugin.json" "$VERSION" <<'PY'
import json, sys
p, v = sys.argv[1], sys.argv[2]
m = json.load(open(p)); m["version"] = v
json.dump(m, open(p, "w"), ensure_ascii=False, indent=2); open(p, "a").write("\n")
PY

# ── 파일 하나로도 낸다 (.zip · .plugin) ─────────────────────────────────────────
#
# 실측(상현님, 2026-08-10): Desktop·Cowork 의 **Add marketplace 는 http(s) 만 받는다** —
# `file://` 도 로컬 경로도 안 받는다. 대신 **로컬 플러그인 등록** 창구가 따로 있고 거기는
# `.zip`·`.plugin` 만 받는다. 그러니 git 저장소만으로는 이 표면에 못 들어간다.
#
# 담는 것은 **마켓플레이스가 아니라 플러그인 하나**다. 규범: `.claude-plugin/` 이 압축 최상위에
# 있거나 **단일 최상위 폴더 안**에 있어야 하고, 그보다 깊으면 설치가 실패한다. 256 MiB 이하.
#
# `zip` CLI 를 쓴다 — python zipfile 은 실행 비트를 안 담는다. 그게 빠지면 설치는 되고
# 서버만 안 뜬다(오류 없이 조용히 — 이 저장소가 제일 싫어하는 모양).
mkdir -p "$DIST/dist"
printf 'dist/\n' > "$DIST/.gitignore"
ZIP="$DIST/dist/gil-$VERSION.zip"
rm -f "$ZIP" "$DIST/dist/gil-$VERSION.plugin"
(cd "$DIST" && zip -q -r "$ZIP" gil)
cp "$ZIP" "$DIST/dist/gil-$VERSION.plugin"
echo "→ 파일로도 냈다: $(basename "$ZIP") ($(wc -c < "$ZIP" | tr -d ' ') bytes) · 같은 것을 .plugin 으로도"
# 배포 저장소는 **그 자체가 마켓플레이스 원본**이라 커밋이 있어야 한다(file:// 로든 GitHub
# 으로든 git 이 읽어 간다). 커밋은 여기서 하고, **push 는 하지 않는다** — 바깥에 내보내는
# 것은 사람이 정한다.
if [ ! -d "$DIST/.git" ]; then
  git -C "$DIST" init -q -b main
fi
git -C "$DIST" add -A
if git -C "$DIST" diff --cached --quiet; then
  echo "→ 바뀐 것이 없다(커밋 안 함)"
else
  git -C "$DIST" commit -qm "gil $VERSION"
  echo "→ 커밋했다: gil $VERSION"
fi


echo
echo "이 저장소가 곧 마켓플레이스다: $DIST"
echo
echo "  Desktop · Cowork UI:  Customize → Plugins → + → 로컬 플러그인 등록 → 이 파일을 고른다"
echo "                        $ZIP"
echo "  Claude Code(터미널):  claude plugin marketplace add $DIST"
echo
echo "  (Add marketplace 는 http(s) 만 받는다 — 공개하기 전에는 위 zip 이 유일한 길이다.)"
