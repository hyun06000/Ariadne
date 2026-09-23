#!/bin/sh
# **Plugin 안에 실을 GIL Core 를 짓는다.** 개발자가 명시적으로 돌리는 자리다.
#
# 이것은 **개발 artifact** 다. 서명도 공증도 하지 않으며 공개 배포판이 아니다. Companion 의
# `release-macos.sh` 와 혼동하지 않는다 — 그쪽은 사람이 볼 창을 짓고, 여기는 Agent 가 부를
# Core 를 짓는다. 두 산출물은 자리도 목적도 다르다.
#
# 지은 뒤 **반드시 확인한다.** 파일이 거기 있다는 사실은 아무것도 보장하지 않는다:
# 다른 architecture 일 수도, 실행이 안 될 수도, 다른 판일 수도 있다. 확인에 실패하면
# 실린 것을 지우고 멈춘다 — 낡은 binary 를 조용히 다시 쓰지 않는다.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
target="aarch64-apple-darwin"
slot="darwin-arm64"
dest="$here/core/$slot/gil"

say() { printf '%s\n' "$*"; }
die() { printf 'make-core: %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || die "이 자리는 macOS arm64 Core 를 짓는다 (지금: $(uname -s))"
[ "$(uname -m)" = "arm64" ] || die "이 자리는 arm64 에서만 짓는다 (지금: $(uname -m))"
command -v cargo >/dev/null || die "cargo 가 없다"
rustup target list --installed 2>/dev/null | grep -qx "$target" \
  || die "rust target 이 없다: rustup target add $target"

say "1/4  Core 를 짓는다 ($target)"
# 만든 사람의 home 이 panic 자리 정보로 binary 에 박힌다. 설치물에 계정 이름을 싣지 않는다.
RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=$HOME/.cargo=/cargo --remap-path-prefix=$root=/gil"
export RUSTFLAGS
# 평소 build 와 flag 가 다르므로 같은 `target/` 을 쓰면 개발자의 cache 가 매번 무효가 된다.
CARGO_TARGET_DIR="$root/target/plugin-core-build"
export CARGO_TARGET_DIR
cargo build --release -p gil --target "$target" --manifest-path "$root/Cargo.toml" >/dev/null \
  || die "cargo build 가 실패했다"
built="$CARGO_TARGET_DIR/$target/release/gil"
[ -x "$built" ] || die "지어진 실행 파일이 없다"

say "2/4  자리에 놓는다"
# **먼저 지운다.** 덮어쓰다 실패하면 낡은 것이 남고, 그것이 다음 설치에 실린다.
rm -rf "$here/core/$slot"
mkdir -p "$here/core/$slot"
cp "$built" "$dest"
chmod 755 "$dest"

say "3/4  실린 것을 확인한다"
[ -x "$dest" ] || die "실행 권한이 없다"
got_arch=$(lipo -archs "$dest" 2>/dev/null || echo unknown)
[ "$got_arch" = "arm64" ] || { rm -rf "$here/core/$slot"; die "architecture 가 arm64 가 아니다: $got_arch"; }

# 파일이 아니라 **실행이** 답해야 한다.
descriptor=$("$dest" --gil-agent-descriptor 2>/dev/null) \
  || { rm -rf "$here/core/$slot"; die "descriptor 에 답하지 않는다"; }
challenge="make_core_$(date +%Y%m%d%H%M%S)_check"
"$dest" --gil-agent-probe "$challenge" 2>/dev/null | grep -q "$challenge" \
  || { rm -rf "$here/core/$slot"; die "fresh challenge 에 답하지 않는다"; }

core_version=$(printf '%s' "$descriptor" | /usr/bin/python3 -c "import json,sys;print(json.load(sys.stdin)['core_version'])")
os=$(printf '%s' "$descriptor" | /usr/bin/python3 -c "import json,sys;print(json.load(sys.stdin)['os'])")
arch=$(printf '%s' "$descriptor" | /usr/bin/python3 -c "import json,sys;print(json.load(sys.stdin)['arch'])")
[ "$os" = "macos" ] && [ "$arch" = "aarch64" ] \
  || { rm -rf "$here/core/$slot"; die "descriptor 가 다른 기계를 말한다: $os/$arch"; }

say "4/4  receipt"
say ""
say "  core_version : $core_version"
say "  target       : $target  ($os/$arch)"
say "  digest       : $(shasum -a 256 "$dest" | cut -c1-16)…"
say "  크기         : $(du -h "$dest" | cut -f1 | tr -d ' ')"
say "  자리         : core/$slot/gil"
say ""
say "  개발 artifact 다 — 서명도 공증도 하지 않았다. 공개 배포판이 아니다."
say "  이제 cachebuster 를 올리고 Plugin 을 다시 설치한다."
