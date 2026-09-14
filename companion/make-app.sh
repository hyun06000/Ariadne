#!/bin/sh
# **`GIL Companion.app` 을 짓고 `~/Applications` 에 놓는다.**
#
# `cargo-tauri` 를 요구하지 않는다. macOS 의 `.app` 은 정해진 모양의 폴더일 뿐이고,
# 프런트엔드는 이미 실행 파일 안에 들어 있다(`generate_context!`). 아이콘 변환도 OS 에
# 딸려 오는 `sips`·`iconutil` 로 한다 — 따로 설치할 것이 없다.
#
# 서명·공증·공개 배포는 이 판의 몫이 아니다. 우리가 쓰는 dogfood 다.
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
</dict>
</plist>
PLIST

echo "4/4  격리 표식을 뗀다"
# 우리가 지은 것이고 서명이 없다. 이것을 떼지 않으면 Gatekeeper 가 막는다.
xattr -dr com.apple.quarantine "$app" 2>/dev/null || true

echo
echo "놓았다: $app"
echo "Finder 에서 두 번 누르거나:  open '$app'"
