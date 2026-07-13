#!/usr/bin/env python3
"""loom/C007 검증 드라이버 — fixtures/expected-wiring.md 의 T1~T4를 실행한다.

T1: 워크플로가 곧 테스트다 — .github/workflows/ariadne-pages.yml 의 run 블록을
추출해 신선한 클론(checkout 시뮬레이션) 안에서 그대로 실행한다.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(BASE, *[".."] * 6))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "ariadne-pages.yml")
RESULTS = []


def check(tid, desc, cond, detail=""):
    RESULTS.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {tid}: {desc}" + (f"  [{detail}]" if detail and not cond else ""))


def extract_runs(yml_text):
    """`run: |` 블록의 본문(더 깊이 들여쓰인 연속 줄)을 추출한다."""
    blocks = []
    lines = yml_text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)run:\s*\|\s*$", line)
        if not m:
            continue
        indent = len(m.group(1))
        body = []
        for nxt in lines[i + 1:]:
            if nxt.strip() == "" or (len(nxt) - len(nxt.lstrip())) > indent:
                body.append(nxt.strip())
            else:
                break
        blocks.append("\n".join(b for b in body if b))
    return blocks


yml = open(WORKFLOW, encoding="utf-8").read()
runs = extract_runs(yml)
script = "set -e\n" + "\n".join(runs)

# T1: 신선한 클론에서 빌드 스텝 실행 + JSON = 클론 스캔
tmp = tempfile.mkdtemp(prefix="ari-c007-")
clone = os.path.join(tmp, "clone")
subprocess.run(["git", "clone", "--quiet", REPO, clone], check=True, capture_output=True)
r = subprocess.run(["bash"], input=script, cwd=clone, capture_output=True, text=True)

site = os.path.join(clone, "_site", "index.html")
json_ok = scanned = rendered = None
if os.path.isfile(site):
    page = open(site, encoding="utf-8").read()
    m = re.search(r'id="ari-data">(.*?)</script>', page, re.S)
    data = json.loads(m.group(1)) if m else {"chains": {}}
    rendered = {f"{c}/{i}" for c, ch in data["chains"].items() for i in ch["cycles"]}
    croot = os.path.join(clone, "rooms", "experiment", "chains")
    scanned = set()
    for chain in os.listdir(croot):
        cdir = os.path.join(croot, chain)
        if os.path.isdir(cdir):
            for cyc in os.listdir(cdir):
                if os.path.isfile(os.path.join(cdir, cyc, "cycle.yaml")):
                    scanned.add(f"{chain}/{cyc}")
    json_ok = rendered == scanned and len(scanned) > 0
check("T1", "신선 클론에서 워크플로 빌드 스텝 재현 + JSON=스캔", r.returncode == 0 and bool(json_ok),
      f"rc={r.returncode}, rendered={rendered and len(rendered)}, scanned={scanned and len(scanned)}: "
      + (r.stderr or "").strip()[-150:])

# T2: 자기완결
page = open(site, encoding="utf-8").read() if os.path.isfile(site) else ""
external = re.findall(r'(?:src=|href=|url\(|@import)[^>\n]*https?://', page)
check("T2", "산출물 자기완결 (외부 참조 0)", os.path.isfile(site) and external == [], str(external))

# T3: 무설치 빌드
forbidden = [w for w in ("pip", "npm", "curl", "wget") if w in script]
check("T3", "빌드 스텝에 설치·네트워크 없음", forbidden == [], str(forbidden))

# T4: 워크플로 정합
needed = ["push", "branches: [main]", "pages: write", "id-token: write",
          "actions/checkout", "actions/upload-pages-artifact", "actions/deploy-pages"]
missing = [n for n in needed if n not in yml]
check("T4", "워크플로 구조(트리거·권한·액션) 완비", missing == [], str(missing))

import shutil
shutil.rmtree(tmp, ignore_errors=True)
total, passed = len(RESULTS), sum(RESULTS)
print(f"\n결과: {passed}/{total} 통과")
sys.exit(0 if passed == total else 1)
