#!/usr/bin/env python3
"""loom/C006 검증 드라이버 — fixtures/expected-release.md 의 T1~T5를 실행한다.

T1의 정신: 문서가 곧 테스트다. QUICKSTART.md의 bash 블록을 추출해 신선한
임시 디렉토리(릴리스 패키지만 존재)에서 그대로 실행한다.
T6(태그·CHANGELOG)은 릴리스 커밋 이후 별도 런으로 확인한다.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(BASE, *[".."] * 6))
RELEASE = os.path.join(REPO, "rooms", "deployment", "ariadne-spec")
V5_ARI = os.path.join(REPO, "rooms", "experiment", "chains", "loom",
                      "C005-web-viewer", "3-verification", "ari", "ari.py")
TEMPLATE = os.path.join(REPO, "rooms", "experiment", "_template")
RESULTS = []


def check(tid, desc, cond, detail=""):
    RESULTS.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {tid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# T1: 신선한 환경에서 QUICKSTART의 bash 블록 실행
tmp = tempfile.mkdtemp(prefix="ari-c006-")
shutil.copytree(RELEASE, os.path.join(tmp, "ariadne-spec"))
qs = open(os.path.join(tmp, "ariadne-spec", "QUICKSTART.md"), encoding="utf-8").read()
blocks = re.findall(r"```bash\n(.*?)```", qs, re.S)
script = "set -e\n" + "\n".join(blocks)
r = subprocess.run(["bash"], input=script, cwd=tmp, capture_output=True, text=True)

proj = os.path.join(tmp, "myproject")
cyaml = os.path.join(proj, "rooms/experiment/chains/demo/C001-first-question/cycle.yaml")
closed = os.path.isfile(cyaml) and "status: closed" in open(cyaml, encoding="utf-8").read()
fsck = subprocess.run([sys.executable, "ari.py", "fsck"], cwd=proj, capture_output=True, text=True)
web_path = os.path.join(proj, "chains.html")
web_ok = False
if os.path.isfile(web_path):
    page = open(web_path, encoding="utf-8").read()
    m = re.search(r'id="ari-data">(.*?)</script>', page, re.S)
    web_ok = bool(m) and "demo" in json.loads(m.group(1))["chains"]
check("T1", "신선 환경에서 퀵스타트 전 블록 재현", r.returncode == 0 and closed
      and fsck.returncode == 0 and web_ok,
      (r.stderr or r.stdout).strip()[-200:])

# T2: ari.py 무드리프트
check("T2", "패키지 ari.py = C005 최종본 (sha256)", sha(os.path.join(RELEASE, "ari.py")) == sha(V5_ARI))

# T3: SPEC 완전성
spec = open(os.path.join(RELEASE, "SPEC.md"), encoding="utf-8").read()
missing = [t for t in [f"R{i}" for i in range(1, 9)] + ["log", "fsck", "open", "close", "verify", "web"]
           if t not in spec]
check("T3", "SPEC.md에 R1~R8 + 6명령 전부", missing == [], str(missing))

# T4: 배포 근거
rel = open(os.path.join(RELEASE, "RELEASE.md"), encoding="utf-8").read()
basis = ["C001-lineage-is-reconstructable", "C002-schema-v0-2", "C003-open-close-porcelain",
         "C004-git-binding", "C005-web-viewer"]
check("T4", "RELEASE.md에 근거 사이클 5개 명시", all(b in rel for b in basis),
      str([b for b in basis if b not in rel]))

# T5: 템플릿 무드리프트 (파일 집합 + 내용)
def tree(d):
    out = {}
    for root, _, files in os.walk(d):
        for name in files:
            p = os.path.join(root, name)
            out[os.path.relpath(p, d)] = sha(p)
    return out

check("T5", "패키지 template = _template (파일 단위 sha256)",
      tree(os.path.join(RELEASE, "template")) == tree(TEMPLATE))

shutil.rmtree(tmp, ignore_errors=True)
total, passed = len(RESULTS), sum(RESULTS)
print(f"\n결과: {passed}/{total} 통과")
sys.exit(0 if passed == total else 1)
