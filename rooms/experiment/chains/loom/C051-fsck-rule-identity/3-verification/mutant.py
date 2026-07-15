#!/usr/bin/env python3
# 변이 래퍼: fsck의 '위반 출력'만 변조하고 나머지는 참조 gil.py로 무손실 통과.
# 깨끗한 저장소(rc==0)는 손대지 않아 FSCK-CLEAN 등 다른 항목을 오염시키지 않는다.
# MUT=strip   : 규칙 토큰(Rk) 전부 제거 (T4 — 규칙 토큰 없는 구현)
# MUT=rewrite : 모든 규칙 토큰을 R1로 치환 (T5 — 잘못된 규칙 발화)
# MUT=render  : 문면만 변경(접미사 제거·None표기 교체), 토큰·id 보존 (T6 — 렌더는 자유)
import os, re, sys, subprocess
GIL = ["python3", "/Users/user/Desktop/code/personal/Ariadne/rooms/deployment/ariadne-spec/gil.py"]
mode = os.environ.get("MUT", "")
args = sys.argv[1:]
if not args or args[0] != "fsck":
    sys.exit(subprocess.run(GIL + args).returncode)
r = subprocess.run(GIL + args, capture_output=True, text=True)
out = r.stdout
if r.returncode != 0:  # 위반이 있을 때만 변조 (깨끗한 저장소는 보존)
    if mode == "strip":
        out = re.sub(r"\bR\d+\b", "", out)
    elif mode == "rewrite":
        out = re.sub(r"\bR\d+\b", "R1", out)
    elif mode == "render":
        out = out.replace(" (끊어진 참조)", "").replace("None", "").replace("≠", "!=")
sys.stdout.write(out)
sys.stderr.write(r.stderr)
sys.exit(r.returncode)
