#!/usr/bin/env python3
"""C042 변이 시험 — 판정기가 '구현'이 아니라 '행동'을 판정하는가.

사용: python3 mutants.py <스크래치> <gil.py> <conformance.py>
"""
import os
import re
import shutil
import subprocess
import sys

MUTANTS = [
    ("m1-viewer-in-cycle-commit", "WEB-AUTO-PURE-COMMIT", [
        # 뷰어를 사이클 커밋에 섞는다 — 태그가 사이클 밖의 것을 봉인하게 된다 (§4 붕괴)
        ('        _git(repo, "commit", "-m", f"gil: web 갱신 — {label}", "--", *rels)',
         '        _git(repo, "commit", "--amend", "--no-edit", "--", *rels)'),
    ]),
    ("m2-create-viewer-anyway", "WEB-AUTO-NONE", [
        # 뷰어가 없어도 만들어낸다 — 도구가 사용자에게 파일을 강요한다
        ('        if not viewers:\n            return  # 뷰어를 쓰지 않는 사용자에게 파일을 강요하지 않는다',
         '        if not viewers:\n            _bake_viewer(chains_root, os.path.join(root, "chains.html"), _WEB_DEFAULT_TITLE, None)\n            return'),
    ]),
    ("m3-ignore-bake-title", "WEB-BAKE-META", [
        # 재굽기가 자기보고를 무시하고 기본 제목으로 덮어쓴다 — 갱신이 아니라 훼손이다
        ("            title, only = _bake_meta(text)",
         "            title, only = _WEB_DEFAULT_TITLE, None"),
    ]),
    ("m4-no-refresh", "WEB-AUTO-REFRESH", [
        # 갱신을 아예 하지 않는다 (v2.1의 행동 그대로) — 창이 낡는다
        ("    if no_web:\n        return", "    if True:\n        return"),
    ]),
]


def main():
    work, gil, suite = sys.argv[1], sys.argv[2], sys.argv[3]
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    src = open(gil, encoding="utf-8").read()
    killed = 0

    for name, expect, patches in MUTANTS:
        s = src
        for old, new in patches:
            if old not in s:
                print(f"하네스 오류  {name}: 치환 대상 없음 — {old[:60]!r}")
                break
            s = s.replace(old, new, 1)
        else:
            path = os.path.join(work, f"{name}.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(s)
            out = subprocess.run([sys.executable, suite, "--gil", f"{sys.executable} {path}"],
                                 capture_output=True, text=True).stdout
            failed = re.findall(r"^FAIL ([A-Z0-9-]+):", out, flags=re.M)
            hit = expect in failed
            killed += hit
            print(f"{'격추 ' if hit else '생존!'} {name:26} → {expect:22} "
                  f"{'실패(기대대로)' if hit else '통과해버렸다'}   [실패항목: {', '.join(failed) or '없음'}]")

    print(f"\n변이 격추: {killed}/{len(MUTANTS)}")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
