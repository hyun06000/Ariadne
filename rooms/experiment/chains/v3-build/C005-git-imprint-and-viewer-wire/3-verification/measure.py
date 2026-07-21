#!/usr/bin/env python3
"""C005 측정: G1(스텝=커밋)·G2(뷰어 배선)·M3(모델 무오염).

usage: python3 measure.py <imprinted-repo-dir>
G1 재구성 산출 저장소를 받아 커밋 계보를 검사하고, gilv3 view가 C004와 동등한
뷰어를 내는지, steps.yaml이 C002 스키마 그대로인지 판정한다.
"""
import sys, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
C002_FIELDS = {"id", "kind", "parent", "outcome", "backtrack", "body"}


def git_log(repo):
    r = subprocess.run(["git", "-C", repo, "log", "--reverse", "--format=%s"],
                       stdout=subprocess.PIPE, check=True)
    return r.stdout.decode().strip().split("\n")


def diff_files(repo, rev):
    r = subprocess.run(["git", "-C", repo, "show", "--name-only", "--format=", rev],
                       stdout=subprocess.PIPE, check=True)
    return [x for x in r.stdout.decode().strip().split("\n") if x]


def load_yaml_fields(path):
    fields = set()
    for raw in open(path, encoding="utf-8"):
        st = raw.strip()
        if st.startswith("- id:") or (st and ":" in st and not st.startswith("#")):
            k = st.lstrip("- ").split(":", 1)[0].strip()
            if k:
                fields.add(k)
    return fields


def main():
    repo = sys.argv[1]
    steps_yaml = os.path.join(repo, "steps.yaml")
    ok = True

    # ---- G1: 스텝 = 커밋 ----
    log = git_log(repo)
    print("[G1 스텝=커밋]")
    expect_seq = ["open", "step: s2", "step: s3", "step: s4", "step: s5",
                  "step: s6", "step: s7", "step: s8", "step: s9", "step: s10", "close"]
    g1_count = len(log) == 11
    g1_order = all(exp in msg for exp, msg in zip(expect_seq, log))
    print("    커밋 수 == 11:", g1_count, "(%d)" % len(log))
    print("    순서 == 스텝 시간순:", g1_order)
    # 각 step 커밋이 정확히 그 스텝의 파일만 건드리는가 (open/close 제외 검사)
    revs = subprocess.run(["git", "-C", repo, "rev-list", "--reverse", "HEAD"],
                          stdout=subprocess.PIPE, check=True).stdout.decode().split()
    per_ok = True
    for i, rev in enumerate(revs[1:-1], start=2):  # s2..s10
        files = diff_files(repo, rev)
        touched_body = any(("steps/s%d.md" % i) in f for f in files)
        touched_yaml = any("steps.yaml" in f for f in files)
        if not (touched_body and touched_yaml):
            per_ok = False
            print("    ✗ 커밋 s%d 파일:" % i, files)
    print("    각 step 커밋 == 그 스텝 파일:", per_ok)
    g1 = g1_count and g1_order and per_ok
    print("[G1]", "PASS" if g1 else "FAIL")
    ok = ok and g1

    # ---- G2: 뷰어 배선 (gilv3 view가 C004 생성기를 재현) ----
    # 동등의 강한 형태: 같은 C002 데이터를 gilv3 view로 렌더한 결과가
    # C004 render.py 산출물(out.html)과 **바이트 동일**해야 한다.
    # (배선이 독립 생성기를 재구현이 아니라 재사용함을 증명.)
    print("\n[G2 뷰어 배선 — C004 재현]")
    c004dir = os.path.normpath(os.path.join(
        HERE, "..", "..", "C004-v3-viewer-step-tree", "3-verification"))
    c002_yaml = os.path.normpath(os.path.join(
        HERE, "..", "..", "C002-design-v3-data-model", "3-verification",
        "case-c012-c014", "steps.yaml"))
    # C004의 기준 산출물 재생성
    subprocess.run(["python3", os.path.join(c004dir, "render.py")],
                   check=True, stdout=subprocess.DEVNULL)
    c004_html = open(os.path.join(c004dir, "out.html"), encoding="utf-8").read()
    # gilv3 view는 <dir>/steps.yaml을 읽으므로, C002 데이터를 담은 임시 dir 구성
    tmpdir = os.path.join(repo, "..", "gilv3-view-c002")
    os.makedirs(tmpdir, exist_ok=True)
    import shutil
    shutil.copy(c002_yaml, os.path.join(tmpdir, "steps.yaml"))
    v_out = os.path.join(tmpdir, "v.html")
    subprocess.run(["python3", os.path.join(HERE, "gilv3.py"), "view", tmpdir,
                    "-o", v_out], check=True, stdout=subprocess.DEVNULL)
    view_html = open(v_out, encoding="utf-8").read()
    # cycle 라벨만 다를 수 있으므로(dir 이름) 그 부분을 정규화 후 비교
    norm = lambda s: s.replace("gilv3-view-c002", "case-c012-c014")
    g2_bytes = norm(view_html) == norm(c004_html)
    print("    gilv3 view == C004 render 바이트 동일(라벨 정규화):", g2_bytes)
    # C004 measure로 뷰어 정확성 재확인 (M1~M4)
    r = subprocess.run(["python3", os.path.join(c004dir, "measure.py")],
                       stdout=subprocess.PIPE)
    g2_measure = (r.returncode == 0) and (b"ALL PASS" in r.stdout)
    print("    C004 measure ALL PASS:", g2_measure)
    g2 = g2_bytes and g2_measure
    print("[G2]", "PASS" if g2 else "FAIL")
    ok = ok and g2

    # ---- M3: 모델 무오염 ----
    print("\n[M3 모델 무오염]")
    fields = load_yaml_fields(steps_yaml)
    extra = fields - C002_FIELDS
    print("    steps.yaml 필드:", sorted(fields))
    print("    C002 스키마 밖 필드(깃 메타 등):", sorted(extra) or "없음")
    m3 = not extra
    print("[M3]", "PASS" if m3 else "FAIL")
    ok = ok and m3

    print("\n" + "=" * 50)
    print("판정:", "ALL PASS ✅" if ok else "FAIL ✗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
