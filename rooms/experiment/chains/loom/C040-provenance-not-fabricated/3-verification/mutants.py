#!/usr/bin/env python3
"""C040 변이 주입 — 판정기가 '정말 보는가'를 시험한다.

통과는 증거가 아니다. 계약을 깨는 구현이 격추되는 것만이 증거다 (loom/C026).

각 변이는 참조 구현 사본을 한 곳만 고쳐 계약을 깬다. 판정기가 그 변이를
'지목한' 항목으로 격추하지 못하면 — 그 계약은 없는 계약이다 (Weft, loom/C036).

사용: python3 mutants.py <spec-dir> <work-dir>
"""
import os
import re
import shutil
import subprocess
import sys

SPEC, WORK = sys.argv[1], sys.argv[2]
SRC = open(os.path.join(SPEC, "gil.py"), encoding="utf-8").read()

MUTANTS = [
    # (이름, 설명, 치환 전, 치환 후, 격추되어야 할 항목)
    ("M1", "author 기본값 'clew' 부활 (이슈 #17의 결함 그 자체)",
     'p_open.add_argument("--author", help=',
     'p_open.add_argument("--author", default="clew", help=',
     "OPEN-AUTHOR-REQUIRED"),
    ("M2", "O2 부모 검사 삭제 (조용히 두 번째 루트를 만든다)",
     "if records and not args.parent and not args.new_root:",
     "if False:",
     "OPEN-PARENT-REQUIRED"),
    ("M3", "R12 삭제 (다중 루트를 다시 침묵시킨다)",
     "if len(roots) > 1:",
     "if False:",
     "FSCK-MULTI-ROOT"),
    # 과잉 작동 변이 — "이게 과하게 작동하면 어떤 참이 거짓이 되는가" (loom/C038)
    ("M4", "[과잉] 빈 체인에서도 부모를 요구 (정당한 루트를 불법화)",
     "if records and not args.parent and not args.new_root:",
     "if not args.parent and not args.new_root:",
     "OPEN-ROOT-EMPTY-CHAIN"),
]

os.makedirs(WORK, exist_ok=True)
ok = True
for name, desc, old, new, target in MUTANTS:
    if old not in SRC:
        print(f"✘ {name}: 치환 대상을 찾지 못했다 (스크립트가 낡았다) — {old!r}")
        ok = False
        continue
    d = os.path.join(WORK, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    with open(os.path.join(d, "gil.py"), "w", encoding="utf-8") as f:
        f.write(SRC.replace(old, new, 1))
    r = subprocess.run([sys.executable, os.path.join(SPEC, "conformance.py"),
                        "--gil", f"{sys.executable} {os.path.join(d, 'gil.py')}"],
                       capture_output=True, text=True)
    failed = set(re.findall(r"^FAIL (\S+):", r.stdout, re.M))
    hit = target in failed
    verdict = "격추" if hit else "생존 ✘"
    print(f"{name} [{verdict}] {desc}")
    print(f"     지목 항목: {target} → {'FAIL (판정기가 봤다)' if hit else 'PASS (판정기가 눈멀었다)'}")
    print(f"     동반 실패: {sorted(failed - {target}) or '없음'}")
    if not hit:
        ok = False

print("\n변이 검증:", "4/4 격추 — 판정기가 본다" if ok else "✘ 생존자 있음 — 계약이 눈멀었다")
sys.exit(0 if ok else 1)
