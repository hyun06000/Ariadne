#!/usr/bin/env python3
"""CLI: case-c012-c014/steps.yaml → out.html (재현 가능한 생성).

usage: python3 render.py [steps.yaml] [out.html]
기본 입력은 C002 확정 데이터, 기본 출력은 out.html.
"""
import os
import sys
from steptree import html_from_yaml_text

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IN = os.path.normpath(os.path.join(
    HERE, "..", "..",
    "C002-design-v3-data-model", "3-verification",
    "case-c012-c014", "steps.yaml"))
DEFAULT_OUT = os.path.join(HERE, "out.html")


def main(argv):
    src = argv[1] if len(argv) > 1 else DEFAULT_IN
    dst = argv[2] if len(argv) > 2 else DEFAULT_OUT
    with open(src, encoding="utf-8") as f:
        text = f.read()
    doc = html_from_yaml_text(text)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"wrote {dst} ({len(doc)} bytes) from {src}")


if __name__ == "__main__":
    main(sys.argv)
