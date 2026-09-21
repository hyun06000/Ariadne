#!/bin/sh
# **개발용 `GIL Companion.app` 을 짓고 `~/Applications` 에 놓는다.**
#
# ## 이것은 배포물이 아니다
#
# 여기서 나온 bundle 은 **사용자에게 줄 수 없다.** 서명이 ad-hoc 이고 공증이 없어
# Gatekeeper 가 거절하며, 이 script 는 그것을 우회하려고 격리 표식을 손으로 뗀다.
# 그 우회가 바로 이 산출물이 배포물이 아니라는 증거다.
#
#   development               여기                  우리가 쓰는 dogfood
#   release_unsigned          release-macos.sh      packaging 확인용
#   release_signed_notarized  release-macos.sh      사용자에게 줄 수 있는 것
#
# 배포물은 `companion/release-macos.sh` 가 Tauri 공식 bundler 로 짓는다. 그쪽은 손으로
# `.app` 을 조립하지 않고, 산출물도 `target/release-macos/` 에 상태별로 따로 놓는다.
# 두 경로를 섞지 않는다.
#
# `cargo-tauri` 를 요구하지 않는다. macOS 의 `.app` 은 정해진 모양의 폴더일 뿐이고,
# 프런트엔드는 이미 실행 파일 안에 들어 있다(`generate_context!`). 아이콘 변환도 OS 에
# 딸려 오는 `sips`·`iconutil` 로 한다 — 따로 설치할 것이 없다.
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
name="GIL Companion"
ident="dev.ariadne.gil.companion"
version="0.1.0"
into="${1:-$HOME/Applications}"
app="$into/$name.app"

echo "1/4  실행 파일을 짓는다"
cargo build --release -p gil-companion --manifest-path "$root/Cargo.toml"
binary="$root/target/release/gil-companion"
[ -x "$binary" ] || { echo "실행 파일이 없다: $binary"; exit 1; }

echo "2/4  아이콘을 만든다"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
set -- 16 32 64 128 256 512
mkdir -p "$work/icon.iconset"
for size in "$@"; do
  sips -z "$size" "$size" "$root/companion/icons/icon.png" \
       --out "$work/icon.iconset/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$root/companion/icons/icon.png" \
       --out "$work/icon.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$work/icon.iconset" -o "$work/icon.icns"

echo "3/4  bundle 을 세운다"
# **있던 것을 먼저 치운다.** 덮어쓰면 옛 파일이 섞인 bundle 이 남는다.
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$binary" "$app/Contents/MacOS/$name"
cp "$work/icon.icns" "$app/Contents/Resources/icon.icns"
cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$name</string>
  <key>CFBundleDisplayName</key><string>$name</string>
  <key>CFBundleExecutable</key><string>$name</string>
  <key>CFBundleIdentifier</key><string>$ident</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$version</string>
  <key>CFBundleVersion</key><string>$version</string>
  <key>LSMinimumSystemVersion</key><string>10.15</string>
  <key>NSHighResolutionCapable</key><true/>
  <!-- 이 bundle 이 스스로 무엇인지 적는다. 배포물은 이 값이 release 다. -->
  <key>GILBuildChannel</key><string>development</string>
</dict>
</plist>
PLIST

echo "4/4  격리 표식을 뗀다"
# 우리가 지은 것이고 서명이 없다. 이것을 떼지 않으면 Gatekeeper 가 막는다.
xattr -dr com.apple.quarantine "$app" 2>/dev/null || true

echo
echo "놓았다: $app  (개발용 — 배포물이 아니다)"
echo "Finder 에서 두 번 누르거나:  open '$app'"
