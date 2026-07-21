#!/usr/bin/env python3
"""Minimal Chrome DevTools Protocol client over raw WebSocket (stdlib only).
Usage: cdp.py <url> <script_file>
Evaluates the JS in script_file (which must produce a JSON-serializable result via
a global `__result__` after awaiting), returns JSON on stdout.
This driver:
  - launches headless chrome with remote debugging
  - opens the page url
  - runs a sequence of evaluate calls described by the caller
We keep it generic: it reads a JSON list of steps from script_file:
  [{"eval": "<js>"} , {"sleep_ms": 4000}, {"eval": "..."}]
Each eval result is collected. Objects returned must be JSON-serializable
(use JSON.stringify in the js and we JSON.parse).
"""
import http.client, json, socket, base64, hashlib, struct, os, sys, time, subprocess, urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def ws_connect(ws_url):
    # ws_url like ws://127.0.0.1:PORT/devtools/page/ID
    assert ws_url.startswith("ws://")
    hostport, path = ws_url[5:].split("/", 1)
    path = "/" + path
    host, port = hostport.split(":")
    s = socket.create_connection((host, int(port)))
    key = base64.b64encode(os.urandom(16)).decode()
    req = (f"GET {path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
           f"Sec-WebSocket-Version: 13\r\n\r\n")
    s.sendall(req.encode())
    # read handshake response
    buf = b""
    while b"\r\n\r\n" not in buf:
        buf += s.recv(4096)
    return s

def ws_send(s, data):
    payload = data.encode("utf-8")
    header = bytearray()
    header.append(0x81)  # FIN + text
    ln = len(payload)
    mask = os.urandom(4)
    if ln < 126:
        header.append(0x80 | ln)
    elif ln < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", ln)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", ln)
    header += mask
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    s.sendall(bytes(header) + masked)

def ws_recv(s):
    def readn(n):
        b = b""
        while len(b) < n:
            chunk = s.recv(n - len(b))
            if not chunk:
                raise IOError("closed")
            b += chunk
        return b
    b0, b1 = readn(2)
    ln = b1 & 0x7F
    if ln == 126:
        ln = struct.unpack(">H", readn(2))[0]
    elif ln == 127:
        ln = struct.unpack(">Q", readn(8))[0]
    data = readn(ln)
    return data.decode("utf-8", "replace")

def main():
    url = sys.argv[1]
    steps = json.load(open(sys.argv[2]))
    port = 9333
    import tempfile
    profile = tempfile.mkdtemp(prefix="cdp-profile-")  # 임시 프로필 — 산출물 디렉토리를 더럽히지 않는다
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}",
                             "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                             "--user-data-dir=" + profile,
                             url],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(50):
            time.sleep(0.2)
            try:
                r = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1)
                tabs = json.load(r)
                for t in tabs:
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        ws_url = t["webSocketDebuggerUrl"]; break
                if ws_url: break
            except Exception:
                continue
        if not ws_url:
            print(json.dumps({"error": "no ws url"})); return
        s = ws_connect(ws_url)
        mid = [0]
        def call(method, params=None):
            mid[0] += 1
            i = mid[0]
            ws_send(s, json.dumps({"id": i, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws_recv(s))
                if msg.get("id") == i:
                    return msg
        call("Runtime.enable")
        call("Page.enable")
        results = []
        for st in steps:
            if "sleep_ms" in st:
                time.sleep(st["sleep_ms"] / 1000.0)
                continue
            if "eval" in st:
                r = call("Runtime.evaluate", {"expression": st["eval"],
                                              "returnByValue": True, "awaitPromise": True})
                val = None
                if "result" in r and "result" in r["result"]:
                    val = r["result"]["result"].get("value")
                if "exceptionDetails" in r.get("result", {}):
                    val = {"__exception__": str(r["result"]["exceptionDetails"])}
                results.append(val)
        print(json.dumps(results, ensure_ascii=False))
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()

if __name__ == "__main__":
    main()
