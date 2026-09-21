#!/bin/sh
# **macOS 배포물을 짓는 하나의 진입점.** 사람과 CI 가 같은 것을 만든다.
#
# `make-app.sh` 와 섞지 않는다. 그쪽은 우리가 쓰는 개발용 bundle 이고, 서명도 공증도 없다.
# 여기는 **사용자에게 줄 수 있는 것**만 만든다 — 그래서 조용히 개발 빌드로 물러서지 않는다.
#
#   development              make-app.sh          사용자 배포 불가
#   release_unsigned         여기, credential 없음  packaging 확인용 · 배포 불가
#   release_signed_notarized 여기, credential 있음  배포 가능
#
# 산출물의 이름이 그 상태다. `release_unsigned/` 안의 DMG 를 배포 경로에 두지 않는다.
#
# # 비밀을 다루는 경계
#
# identity 도 credential 도 이 파일에 적지 않는다. 환경에서 받고, 값은 어디에도 찍지 않는다.
# 없으면 **없다고 말하고 그 단계를 건너뛴다** — 성공한 척하지 않는다.
#
#   APPLE_SIGNING_IDENTITY        "Developer ID Application: … (TEAMID)"
#   APPLE_API_KEY                 App Store Connect key id      ← 공증은 이쪽을 먼저 본다
#   APPLE_API_ISSUER              issuer uuid
#   APPLE_API_KEY_PATH            .p8 파일 경로 (저장소 밖)
#   APPLE_ID / APPLE_PASSWORD / APPLE_TEAM_ID                   ← API key 가 없을 때만
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
name="GIL Companion"
ident="dev.ariadne.gil.companion"
out="$root/target/release-macos"

say() { printf '%s\n' "$*"; }
die() { printf 'release-macos: %s\n' "$*" >&2; exit 1; }
# 비밀이 설정됐는지만 말한다. 값은 절대 찍지 않는다.
have() { [ -n "${1:-}" ]; }

# ── 0. 필요한 것이 없으면 **빠르고 구체적으로** 실패한다 ─────────────
[ "$(uname -s)" = "Darwin" ] || die "macOS 에서만 짓는다 (지금: $(uname -s))"
command -v cargo >/dev/null || die "cargo 가 없다"
command -v codesign >/dev/null || die "codesign 이 없다 — Xcode command line tools 를 설치한다"
command -v xcrun >/dev/null || die "xcrun 이 없다 — Xcode command line tools 를 설치한다"
if command -v cargo-tauri >/dev/null; then
  tauri="cargo-tauri tauri"
else
  die "cargo-tauri 가 없다. 공식 bundler 없이 손으로 .app 을 조립하지 않는다:
       cargo install tauri-cli --version '^2' --locked"
fi

# 판 번호는 **한 자리**에서 온다 — tauri.conf.json.
version=$(/usr/bin/python3 -c "import json;print(json.load(open('$root/companion/tauri.conf.json'))['version'])")
[ -n "$version" ] || die "tauri.conf.json 에서 version 을 읽지 못했다"

identity="${APPLE_SIGNING_IDENTITY:-}"
signing=no
have "$identity" && signing=yes

say "GIL Companion $version — macOS 배포물"
say "  서명 identity: $( [ "$signing" = yes ] && echo '환경에서 받음' || echo '없음' )"

# ── 1. Tauri 공식 bundler 로 app 과 DMG 를 짓는다 ────────────────────
say ""
say "1/6  release build 와 bundle"

# macOS bundler 는 `.icns` 를 요구한다. 1024px 원본 하나에서 **지을 때마다** 만든다 —
# 생성물을 역사에 넣지 않는다. 쓰는 도구는 OS 에 딸려 온 것뿐이다.
icons="$root/companion/icons"
[ -f "$icons/icon.png" ] || die "아이콘 원본이 없다: companion/icons/icon.png"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT   # DMG 를 열면 아래에서 다시 건다
mkdir -p "$work/icon.iconset"
for size in 16 32 64 128 256 512; do
  sips -z "$size" "$size" "$icons/icon.png" \
       --out "$work/icon.iconset/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$icons/icon.png" \
       --out "$work/icon.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$work/icon.iconset" -o "$icons/icon.icns" \
  || die "icns 를 만들지 못했다"

# **배포판에 실을 화면만 고른다.** `ui/` 는 제품과 시험 장치가 함께 사는 자리다 —
# selftest 와 fixture Host 는 개발 도구이지 사용자에게 줄 것이 아니다. 그대로 실으면
# 제품 안에 가짜 사실을 만들 수 있는 문이 함께 배포된다.
dist="$root/target/release-ui"
rm -rf "$dist"
mkdir -p "$dist"
for one in index.html companion.js companion.css layout.js; do
  [ -f "$root/ui/$one" ] || die "배포할 화면 조각이 없다: ui/$one"
  cp "$root/ui/$one" "$dist/"
done
say "     화면: $(ls "$dist" | tr '\n' ' ')"

# Tauri 는 설정 파일이 있는 자리에서 돈다. `frontendDist` 도 그 자리 기준이다.
cd "$root/companion"

# 의존성 source 경로가 panic 자리 정보로 binary 에 박힌다 — 거기에는 개발자의 home 이
# 들어 있다. 배포물에 사람의 계정 이름을 싣지 않는다.
RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=$HOME/.cargo=/cargo --remap-path-prefix=$root=/gil"
export RUSTFLAGS
# 그 flag 가 평소 build 와 다르므로, 같은 `target/` 을 쓰면 개발자가 `cargo test` 와 이
# script 를 오갈 때마다 의존성 전체가 다시 컴파일된다(실측 10분). **자기 자리**에서 짓는다.
CARGO_TARGET_DIR="$root/target/release-macos-build"
export CARGO_TARGET_DIR

# `--bundles dmg` 는 app 도 함께 만든다. 손으로 Info.plist 를 쓰지 않는다.
front='"build":{"frontendDist":"../target/release-ui"}'
if [ "$signing" = yes ]; then
  # identity 는 **인자로만** 넘긴다. 설정 파일에 남기지 않는다.
  APPLE_SIGNING_IDENTITY="$identity" \
    $tauri build --bundles dmg \
      --config "{$front,\"bundle\":{\"macOS\":{\"signingIdentity\":\"$identity\"}}}" \
    >/dev/null || die "tauri build 가 실패했다"
else
  $tauri build --bundles dmg --config "{$front}" >/dev/null || die "tauri build 가 실패했다"
fi

bundle="$root/target/release-macos-build/release/bundle"
dmg=$(find "$bundle/dmg" -name "*.dmg" -maxdepth 1 2>/dev/null | head -1)
# Tauri 는 DMG 를 만든 뒤 staging 한 `.app` 을 치운다. 그러니 **DMG 안의 것**을 본다 —
# 그것이 사람이 실제로 받는 것이고, 감사해야 할 것도 그쪽이다.
[ -n "$dmg" ] || die "DMG 가 만들어지지 않았다"

# ── 2. DMG 안의 app 을 연다 ─────────────────────────────────────────
say "2/6  DMG 안을 본다"
mount=$(mktemp -d)
hdiutil attach "$dmg" -readonly -nobrowse -mountpoint "$mount" >/dev/null \
  || die "DMG 를 열지 못했다"
# 열었으면 **무슨 일이 있어도** 닫는다.
trap 'hdiutil detach "$mount" -quiet >/dev/null 2>&1 || true; rm -rf "$work" "$mount"' EXIT
app="$mount/$name.app"
[ -d "$app" ] || die "DMG 안에 $name.app 이 없다"

# 표준 설치 UX: 앱 하나와 Applications 바로가기뿐이다.
inside=$(ls -A "$mount" | grep -v '^\.' | tr '\n' ' ')
say "     담긴 것: $inside"
[ -L "$mount/Applications" ] || die "DMG 에 Applications 바로가기가 없다"

exe="$app/Contents/MacOS/$name"
[ -x "$exe" ] || die "bundle 의 실행 파일 이름이 '$name' 이 아니다 — launcher 가 찾지 못한다"
arch=$(lipo -archs "$exe" 2>/dev/null || echo unknown)

notarized=no
if [ "$signing" = yes ]; then
  codesign --verify --deep --strict --verbose=2 "$app" 2>&1 | sed 's/^/     /' \
    || die "codesign --verify 가 실패했다 — 서명되지 않은 것을 배포물이라고 하지 않는다"
  codesign -d --entitlements - "$app" >/dev/null 2>&1 \
    || die "entitlements 를 읽지 못했다"
else
  say "     서명 확인 건너뜀 — APPLE_SIGNING_IDENTITY 가 없다"
fi

# ── 3. 공증 ────────────────────────────────────────────────────────
say "3/6  공증"
auth=""
if have "${APPLE_API_KEY:-}" && have "${APPLE_API_ISSUER:-}" && have "${APPLE_API_KEY_PATH:-}"; then
  # App Store Connect API key 를 **먼저** 쓴다 — 계정 비밀번호보다 좁은 권한이고,
  # 회수와 교체가 사람 계정과 무관하게 된다.
  auth="--key $APPLE_API_KEY_PATH --key-id $APPLE_API_KEY --issuer $APPLE_API_ISSUER"
  say "     App Store Connect API key 로 제출한다"
elif have "${APPLE_ID:-}" && have "${APPLE_PASSWORD:-}" && have "${APPLE_TEAM_ID:-}"; then
  auth="--apple-id $APPLE_ID --password $APPLE_PASSWORD --team-id $APPLE_TEAM_ID"
  say "     Apple ID 로 제출한다 (API key 가 없다)"
fi

if [ "$signing" = yes ] && [ -n "$auth" ]; then
  # shellcheck disable=SC2086
  xcrun notarytool submit "$dmg" $auth --wait \
    || die "공증이 실패했다 — 실패한 것을 배포 자리에 두지 않는다"
  xcrun stapler staple "$dmg" || die "stapler staple 이 실패했다"
  xcrun stapler validate "$dmg" || die "stapler validate 가 실패했다"
  notarized=yes
elif [ "$signing" != yes ]; then
  say "     건너뜀 — 서명되지 않은 것은 공증할 수 없다"
else
  say "     건너뜀 — 공증 credential 이 없다"
fi

# ── 4. Gatekeeper 평가 ──────────────────────────────────────────────
say "4/6  Gatekeeper 평가"
if [ "$notarized" = yes ]; then
  spctl -a -vvv -t install "$dmg" 2>&1 | sed 's/^/     /' \
    || die "spctl 이 이 DMG 를 거절했다"
else
  say "     건너뜀 — 공증되지 않은 것은 평가해도 통과하지 않는다"
fi

# ── 5. 상태에 맞는 자리에 놓는다 ────────────────────────────────────
say "5/6  산출물 배치"
if [ "$notarized" = yes ]; then
  state=release_signed_notarized
elif [ "$signing" = yes ]; then
  state=release_signed_unnotarized
else
  state=release_unsigned
fi
# **상태가 자리를 정한다.** 배포 가능한 것만 `release_signed_notarized/` 에 산다.
dest="$out/$state"
rm -rf "$dest"
mkdir -p "$dest"
cp "$dmg" "$dest/"
final="$dest/$(basename "$dmg")"

# ── 6. receipt ─────────────────────────────────────────────────────
say "6/6  receipt"
say ""
say "  상태      : $state"
say "  DMG       : ${final#"$root"/}"
say "  크기      : $(du -h "$final" | cut -f1 | tr -d ' ')"
say "  version   : $version"
say "  identifier: $ident"
say "  arch      : $arch"
say "  서명      : $( [ "$signing" = yes ] && echo '예' || echo '아니오' )"
say "  공증      : $( [ "$notarized" = yes ] && echo '예 · staple 확인' || echo '아니오' )"
if [ "$state" != release_signed_notarized ]; then
  say ""
  say "  이것은 **사용자에게 줄 수 있는 배포물이 아니다.** packaging 확인용이다."
fi
