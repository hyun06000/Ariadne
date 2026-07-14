#!/usr/bin/env python3
"""C043 변이 시험 — 판정기가 '구현'이 아니라 '행동'을 판정하는가.

각 변이는 예약 기능의 한 주장을 무력화한다. C041의 교훈(심층 방어가 변이를 가린다)을
설계에 반영해, 각 변이가 **다른 방어선이 침묵하는 입력**에서 격추되게 골랐다.

사용: python3 mutants.py <스크래치> <gil.py> <conformance.py>
"""
import os
import re
import shutil
import subprocess
import sys

MUTANTS = [
    ("m1-ignore-reserved", "OPEN-SKIPS-RESERVED", [
        # _next_number가 예약을 무시한다 (C037 이전의 행동 그대로) — 남의 예약 번호를 재발급한다
        ('        num = _next_number(records, [r["num"] for r in reservations])  # 남의 예약 번호는 건너뛴다',
         '        num = _next_number(records)  # MUT'),
    ]),
    ("m2-no-promotion", "OPEN-PROMOTES-OWNER", [
        # 예약자를 알아보지 못한다 — 승격이 사라지고 예약자도 재번호를 받는다
        ('    mine = [r for r in reservations if r["for"] == args.author]',
         '    mine = []  # MUT'),
    ]),
    ("m3-no-owner-required", "RESERVE-NEEDS-FOR", [
        # 예약이 주인을 지어낸다 (§3.2 P1 위반) — --for 없이도 예약이 선다
        ('    if not args.author:  # §3.2 P1/P2 — 도구는 예약의 주인을 지어내지 않는다 (이슈 #17)',
         '    if False:  # MUT'),
    ]),
    ("m4-keep-consumed", "OPEN-PROMOTES-OWNER", [
        # 승격은 하되 예약을 원장에서 지우지 않는다 — 소비되지 않은 예약이 번호를 영원히 막는다
        ('        res_path, _ = _save_reservations(chain_dir, [r for r in reservations if r is not consumed])',
         '        res_path, _ = _save_reservations(chain_dir, reservations)  # MUT'),
    ]),
    ("m5-silent-log", "RESERVE-IN-LOG", [
        # log가 예약을 보고하지 않는다 — 낡은 화면은 침묵보다 나쁘다 (C042)
        ('    reservations = _load_reservations(chain_dir)  # 예약은 사이클이 아니다 — 그래프 밖 별도 섹션 (loom/C043)',
         '    reservations = []  # MUT'),
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
            print(f"{'격추 ' if hit else '생존!'} {name:22} → {expect:20} "
                  f"{'실패(기대대로)' if hit else '통과해버렸다'}   [실패항목: {', '.join(failed) or '없음'}]")

    print(f"\n변이 격추: {killed}/{len(MUTANTS)}")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
