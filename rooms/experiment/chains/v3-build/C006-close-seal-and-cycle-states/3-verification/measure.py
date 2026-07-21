#!/usr/bin/env python3
"""C006 측정: M1(상태 분류)·M2(close 게이트+봉인)·M3(steps.yaml 무오염).

usage: python3 measure.py   (build-cases.sh를 먼저 실행해 cases/ 준비)
"""
import sys, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.join(HERE, "gilv3.py")
CASES = os.path.join(HERE, "cases")
C002_FIELDS = {"id", "kind", "parent", "outcome", "backtrack", "body"}


def status_state(d):
    r = subprocess.run(["python3", G, "status", d], stdout=subprocess.PIPE, check=True)
    for line in r.stdout.decode().split("\n"):
        if line.startswith("사이클 상태="):
            return line.split("=")[1].split(" ")[0]
    return "?"


def try_close(d, verdict):
    r = subprocess.run(["python3", G, "close", d, "--verdict", verdict, "--date", "2026-07-21"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.returncode, r.stdout.decode(), r.stderr.decode()


def yaml_fields(path):
    fs = set()
    for raw in open(path, encoding="utf-8"):
        st = raw.strip()
        if st and ":" in st and not st.startswith("#"):
            fs.add(st.lstrip("- ").split(":", 1)[0].strip())
    return fs


def main():
    ok = True

    # M1: 분류
    print("[M1 상태 분류]")
    expect = {"in-progress": "in_progress", "solved": "solved", "multi": "multi_solution"}
    m1 = True
    for k, exp in expect.items():
        got = status_state(os.path.join(CASES, k))
        good = got == exp
        m1 = m1 and good
        print("    %-12s → %-15s (기대 %s) %s" % (k, got, exp, "✓" if good else "✗"))
    print("[M1]", "PASS" if m1 else "FAIL"); ok = ok and m1

    # M2: 게이트 + 봉인
    print("\n[M2 close 게이트 + 봉인]")
    # in-progress: 거부 + cycle.yaml 미생성
    rc, out, err = try_close(os.path.join(CASES, "in-progress"), "rejected")
    ip_cy = os.path.join(CASES, "in-progress", "cycle.yaml")
    ip_ok = rc != 0 and not os.path.exists(ip_cy)
    print("    in-progress close 거부(rc≠0):", rc != 0, "| cycle.yaml 미생성:", not os.path.exists(ip_cy))
    # solved: 허용 + cycle.yaml state=solved
    rc, out, err = try_close(os.path.join(CASES, "solved"), "supported")
    sv_cy = os.path.join(CASES, "solved", "cycle.yaml")
    sv_txt = open(sv_cy).read() if os.path.exists(sv_cy) else ""
    sv_ok = rc == 0 and "state: solved" in sv_txt and "live_leaves: [s7]" in sv_txt and "verdict: supported" in sv_txt
    print("    solved close 허용(rc0):", rc == 0, "| cycle.yaml state=solved·live[s7]·verdict:", sv_ok)
    # multi: 허용 + 경고 + state=multi_solution
    rc, out, err = try_close(os.path.join(CASES, "multi"), "supported")
    mu_cy = os.path.join(CASES, "multi", "cycle.yaml")
    mu_txt = open(mu_cy).read() if os.path.exists(mu_cy) else ""
    mu_ok = rc == 0 and "state: multi_solution" in mu_txt and "경고" in err and "s4" in mu_txt and "s7" in mu_txt
    print("    multi close 허용+경고+state=multi_solution·live[s4,s7]:", mu_ok)
    m2 = ip_ok and sv_ok and mu_ok
    print("[M2]", "PASS" if m2 else "FAIL"); ok = ok and m2

    # M3: 무오염 — steps.yaml 필드는 봉인 후에도 6개
    print("\n[M3 steps.yaml 무오염]")
    m3 = True
    for k in ("solved", "multi"):
        fs = yaml_fields(os.path.join(CASES, k, "steps.yaml"))
        extra = fs - C002_FIELDS
        good = not extra
        m3 = m3 and good
        print("    %-8s steps.yaml 필드 == C002 6개, 밖=%s %s" % (k, sorted(extra) or "없음", "✓" if good else "✗"))
    # 봉인 메타는 cycle.yaml에만
    sep = os.path.exists(os.path.join(CASES, "solved", "cycle.yaml"))
    print("    봉인 메타는 cycle.yaml 별개 파일:", sep)
    m3 = m3 and sep
    print("[M3]", "PASS" if m3 else "FAIL"); ok = ok and m3

    print("\n" + "=" * 50)
    print("판정:", "ALL PASS ✅" if ok else "FAIL ✗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
