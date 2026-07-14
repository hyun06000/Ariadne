#!/usr/bin/env python3
"""C041 변이 시험 — 판정기가 '구현'이 아니라 '행동'을 판정하는가.

각 변이는 정정 계약의 **한 조항만** 부순다. 해당 판정 항목이 반드시 실패해야 한다(격추).
살아남은 변이는 판정기의 사각지대다.

사용: python3 mutants.py <스크래치디렉토리> <gil.py 경로> <conformance.py 경로>
"""
import os
import re
import shutil
import subprocess
import sys

# (변이명, 격추되어야 할 항목, [(찾을 것, 바꿀 것), …])
MUTANTS = [
    ("m1-no-evidence-check", "CORRECT-EVIDENCE-REQUIRED", [
        # 증거를 '기록'만 하고 대조하지 않는다 — 관측은 판정이 아니다 (C040)
        ("            if v not in haystack:", "            if False:"),
    ]),
    ("m2-no-field-limit", "CORRECT-FIELD-LIMIT", [
        # L1 붕괴: 저자의 주장(verdict)까지 정정 대상이 된다
        ('_PROVENANCE_FIELDS = ("author", "parent", "lineage")',
         '_PROVENANCE_FIELDS = ("author", "parent", "lineage", "verdict", "status", "title")'),
    ]),
    ("m3a-overwrite-record", "CORRECT-RECORD", [
        # 덧붙이지 않고 덮어쓴다 — 과거의 정정 기록이 사라진다
        ("    body = corr_before if corr_before else (", "    body = None or ("),
    ]),
    ("m3b-drop-from", "CORRECT-RECORD", [
        # L3 붕괴: 거짓값(from)을 기록하지 않는다 — 정정이 각주가 아니라 지우개가 된다.
        # (치환 대상은 '쓰는 쪽'이어야 한다 — _CORRECTION_KEYS(검사기)를 건드리면 행동이 안 변한다)
        ('                                                          ("field", "from", "to", "evidence",',
         '                                                          ("field", "to", "evidence",'),
    ]),
    ("m4-no-tag-move", "CORRECT-TAG-MOVE", [
        # 태그를 옮기지 않는다 — 정정한 자가 위조자가 된다.
        # (cmd_supersede에도 같은 모양의 호출이 있다 — f"[correct]" 줄까지 포함해 특정한다)
        ('    _git(repo, "tag", "-f", "-a", tag, "-m",\n'
         '         f"[correct] ',
         '    _skip = (repo, tag) and (\n'
         '         f"[correct] '),
    ]),
    ("m5-no-tamper-guard", "CORRECT-TAMPER-GUARD", [
        # C6 붕괴: 이미 변조된 사이클도 정정 허용 — 변조 세탁의 뒷문
        ("    if dirty:", "    if False:"),
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
                print(f"하네스 오류  {name}: 치환 대상을 찾지 못했다 — {old[:50]!r}")
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
            print(f"{'격추 ' if hit else '생존!'} {name:22} → {expect:28} "
                  f"{'실패(기대대로)' if hit else '통과해버렸다'}   [실패항목: {', '.join(failed) or '없음'}]")

    print(f"\n변이 격추: {killed}/{len(MUTANTS)}")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
