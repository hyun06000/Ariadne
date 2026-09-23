#!/bin/sh
# **Plugin 을 설치 가능한 모양으로 싸는 하나의 자리.**
#
# 순서가 곧 규칙이다: Core 를 짓고 → 실린 것을 확인하고 → 그제서야 cachebuster 를 올리고
# 다시 설치한다. Core 가 없거나 이 기계의 것이 아니면 **여기서 멈춘다** — 확인되지 않은
# 설치본을 만들지 않는다.
#
# 이것은 **개발 packaging** 이다. 서명도 공증도 하지 않으며 공개 배포가 아니다.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
slot="darwin-arm64"
core="$here/core/$slot/gil"
scripts="$HOME/.codex/skills/.system/plugin-creator/scripts"
codex="/Applications/ChatGPT.app/Contents/Resources/codex"

say() { printf '%s\n' "$*"; }
die() { printf 'package: %s\n' "$*" >&2; exit 1; }

[ -d "$scripts" ] || die "plugin-creator 공식 script 를 찾지 못했다: $scripts"
[ -x "$codex" ] || die "codex CLI 를 찾지 못했다: $codex"

say "1/4  Core 를 짓고 확인한다"
"$here/make-core.sh" >/dev/null || die "Core 를 짓지 못했다 — 설치로 넘어가지 않는다"

# make-core.sh 가 이미 확인했지만, **싸는 순간에 다시 본다.** 그 사이에 지워졌을 수 있고,
# 확인되지 않은 binary 가 설치본에 실리는 것이 이 script 가 막으려는 바로 그 일이다.
[ -x "$core" ] || die "실린 Core 가 없다 — cachebuster 를 올리지 않는다"
[ "$(lipo -archs "$core" 2>/dev/null)" = "arm64" ] || die "실린 Core 가 arm64 가 아니다"
challenge="package_$(date +%Y%m%d%H%M%S)_check"
"$core" --gil-agent-probe "$challenge" 2>/dev/null | grep -q "$challenge" \
  || die "실린 Core 가 fresh challenge 에 답하지 않는다"
digest=$(shasum -a 256 "$core" | cut -d' ' -f1)

say "2/4  plugin 을 검증한다"
python3 "$scripts/validate_plugin.py" "$here" >/dev/null || die "plugin validation 이 실패했다"

say "3/4  cachebuster 를 올린다"
python3 "$scripts/update_plugin_cachebuster.py" "$here" | sed 's/^/     /'

say "4/4  다시 설치한다"
name=$(python3 "$scripts/read_marketplace_name.py")
"$codex" plugin add "gil-companion-prototype@$name" | sed 's/^/     /'

say ""
say "  Core digest : $(printf '%s' "$digest" | cut -c1-16)…"
say "  target      : $slot"
say "  marketplace : $name"
say ""
say "  개발 packaging 이다 — 서명·공증하지 않았고 공개 배포가 아니다."
say "  갱신된 skill 과 tool 은 **새 thread** 에서 붙는다."
