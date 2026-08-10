#!/usr/bin/env python3
"""fakehost — MCP Apps 호스트 흉내를 내서 **카드 껍데기를 실제로 밟는다.**

왜 있나. 표시모드·핸드셰이크·제스처 요청은 소스를 읽어서는 안 보인다 — 밟아야 보인다.
그런데 진짜 호스트(Claude Code·Desktop)는 ㄱ) 자기가 여는 모드를 우리가 못 고르고
ㄴ) 바이너리를 바꾸면 재시작해야 하고 ㄷ) 거절·무응답 같은 갈래를 일부러 만들 수 없다.
그래서 세 갈래(목록에 있다 / 목록에 없다 / 목록을 안 밝혔다)와 세 응답(승인·거절·무응답)을
**여기서 만들어 놓고 눌러 본다.** 2026-08-10 에 이 자리가 없어서, 한 번도 안 청해 본 것을
"호스트가 안 준다"로 결론지을 뻔했다.

쓰는 법:
    python3 devtools/fakehost.py <gil 저장소 경로> [포트]
    → http://127.0.0.1:<포트>/fakehost.html 을 브라우저로 연다.

이건 **제품 표면이 아니다** — 브라우저 뷰어는 2026-08-10 에 지웠고 이건 그것을 되살리는
것이 아니다. 개발자가 규범을 밟아 보는 시험대다.
"""
import http.server
import json
import os
import subprocess
import sys
import functools

HERE = os.path.dirname(os.path.abspath(__file__))
GIL = os.environ.get("GIL_BIN", os.path.join(HERE, "..", "go", "gil"))


def dump_shell(repo):
    """gil mcp serve 에 붙어 상태 카드 껍데기 HTML 을 그대로 받아 온다."""
    env = {**os.environ, "GIL_NO_VIEWER": "1", "GIL_NO_VERSION_CHECK": "1"}
    p = subprocess.Popen([GIL, "mcp", "serve"], cwd=repo, text=True, bufsize=1,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, env=env)

    def send(o):
        p.stdin.write(json.dumps(o) + "\n")
        p.stdin.flush()

    def pump(want):
        while True:
            ln = p.stdout.readline()
            if not ln:
                return None
            try:
                m = json.loads(ln.strip())
            except ValueError:
                continue
            if m.get("method"):
                if "id" in m:
                    send({"jsonrpc": "2.0", "id": m["id"],
                          "error": {"code": -32601, "message": "x"}})
                continue
            if m.get("id") == want:
                return m

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                     "clientInfo": {"name": "fakehost", "version": "0"}}})
    pump(1)
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "resources/read",
          "params": {"uri": "ui://gil/status"}})
    r = pump(2)
    p.terminate()
    if not r:
        sys.exit("껍데기를 못 받았다 — GIL_BIN 과 저장소 경로를 확인하라")
    return r["result"]["contents"][0]["text"]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    repo = os.path.abspath(sys.argv[1])
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8791
    with open(os.path.join(HERE, "shell.html"), "w") as f:
        f.write(dump_shell(repo))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=HERE)
    print(f"→ http://127.0.0.1:{port}/fakehost.html   (저장소: {repo})")
    http.server.HTTPServer(("127.0.0.1", port), handler).serve_forever()


if __name__ == "__main__":
    main()
