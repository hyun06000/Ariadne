#!/usr/bin/env python3
"""cdp_probe (C025) — M4 드릴다운 실측: 실 Chrome raw-WebSocket CDP.

C007 interact.py의 stdlib CDP 구동을 통합 뷰어(DAG 노드 클릭 → 스텝 트리 패널 토글)에
적응. 브라우저 없이는 클릭→토글 실행을 관찰할 수 없으므로 실 Chrome headless로 실 DOM.

측정(run 반환 bool):
  M4a  DAG 노드 클릭 → 그 사이클 패널 hidden 해제, 노드 .active
  M4b  둘째 노드 클릭 → 둘째 패널 열림 AND 첫 패널 여전히 열림 (상태보존, C006 K2)
  M4c  첫 패널 닫기(✕) → 첫만 닫히고 둘째 유지 (닫기 국소성)
"""
import json, os, socket, struct, subprocess, sys, time, urllib.request
from base64 import b64encode

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9351


class WS:
    def __init__(self, url):
        hostport, _, path = url[5:].partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port)))
        key = b64encode(os.urandom(16)).decode()
        req = ("GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key))
        self.sock.sendall(req.encode())
        self._buf = b""
        while b"\r\n\r\n" not in self._buf:
            self._buf += self.sock.recv(4096)
        self._buf = self._buf.split(b"\r\n\r\n", 1)[1]
    def send(self, data):
        payload = data.encode(); n = len(payload)
        header = struct.pack("!B", 0x81); mask = os.urandom(4)
        if n < 126: header += struct.pack("!B", 0x80 | n)
        elif n < 65536: header += struct.pack("!B", 0x80 | 126) + struct.pack("!H", n)
        else: header += struct.pack("!B", 0x80 | 127) + struct.pack("!Q", n)
        header += mask
        self.sock.sendall(header + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
    def _read(self, n):
        while len(self._buf) < n:
            self._buf += self.sock.recv(65536)
        out, self._buf = self._buf[:n], self._buf[n:]
        return out
    def recv(self):
        b0, b1 = self._read(2); ln = b1 & 0x7F
        if ln == 126: ln = struct.unpack("!H", self._read(2))[0]
        elif ln == 127: ln = struct.unpack("!Q", self._read(8))[0]
        return self._read(ln).decode("utf-8", "replace")


class CDP:
    def __init__(self, ws_url):
        self.ws = WS(ws_url); self._id = 0
    def call(self, method, **params):
        self._id += 1; mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg: raise RuntimeError(msg["error"])
                return msg.get("result", {})
    def evaluate(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True)
        return r.get("result", {}).get("value")


def _js_esc(s): return s.replace("\\", "\\\\").replace('"', '\\"')


def run(out_html):
    if not os.path.exists(CHROME):
        print("M4 드릴다운: SKIP (Chrome 없음: %s)" % CHROME); return None
    here = os.path.dirname(os.path.abspath(out_html))
    profile = os.path.join(here, ".chrome-profile-m4")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT,
         "--user-data-dir=%s" % profile, "--no-first-run", "--no-default-browser-check",
         "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(50):
            try:
                data = urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT).read()
                for t in json.loads(data):
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        ws_url = t["webSocketDebuggerUrl"]; break
                if ws_url: break
            except Exception: pass
            time.sleep(0.2)
        if not ws_url:
            print("M4 드릴다운: FAIL (DevTools 엔드포인트 못 찾음)"); return False

        cdp = CDP(ws_url)
        cdp.call("Page.enable"); cdp.call("Runtime.enable")
        cdp.call("Page.navigate", url="file://" + os.path.abspath(out_html))
        for _ in range(50):
            time.sleep(0.15)
            if cdp.evaluate("document.readyState==='complete' && "
                            "!!document.querySelector('.dag-node')"):
                break

        # 두 사이클 키를 DOM에서 뽑는다 (원장 실제 노드).
        keys = cdp.evaluate(
            "Array.from(document.querySelectorAll('.dag-node'))"
            ".map(g=>g.getAttribute('data-key')).slice(0,2)")
        if not keys or len(keys) < 2:
            print("M4 드릴다운: FAIL (노드 2개 미만)"); return False
        k1, k2 = keys[0], keys[1]

        def hidden(k):
            return cdp.evaluate('document.getElementById("panel-%s").hidden' % _js_esc(k))
        def active(k):
            return cdp.evaluate(
                'Array.from(document.querySelectorAll(".dag-node"))'
                '.find(g=>g.getAttribute("data-key")==="%s").classList.contains("active")'
                % _js_esc(k))
        def click(k):
            cdp.evaluate(
                'Array.from(document.querySelectorAll(".dag-node"))'
                '.find(g=>g.getAttribute("data-key")==="%s")'
                '.dispatchEvent(new MouseEvent("click",{bubbles:true}))' % _js_esc(k))
        def close(k):
            cdp.evaluate(
                'document.querySelector(".panel-close[data-key=\\"%s\\"]")'
                '.dispatchEvent(new MouseEvent("click",{bubbles:true}))' % _js_esc(k))

        init_ok = hidden(k1) and hidden(k2)
        click(k1); time.sleep(0.1)
        a_ok = (not hidden(k1)) and active(k1)
        click(k2); time.sleep(0.1)
        b_ok = (not hidden(k2)) and (not hidden(k1)) and active(k1) and active(k2)
        close(k1); time.sleep(0.1)
        c_ok = hidden(k1) and (not hidden(k2)) and (not active(k1))

        print("M4 드릴다운 (실 Chrome CDP) — 노드 %s, %s" % (k1, k2))
        print("  M4a 클릭→패널펼침+.active: %s (초기 hidden=%s)" % ("PASS" if a_ok else "FAIL", init_ok))
        print("  M4b 상태보존(둘째 클릭에도 첫 패널 유지): %s" % ("PASS" if b_ok else "FAIL"))
        print("  M4c 닫기 국소성(첫만 닫힘): %s" % ("PASS" if c_ok else "FAIL"))
        return bool(init_ok and a_ok and b_ok and c_ok)
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "gilv3-web.html"
    r = run(out)
    sys.exit(0 if r else (1 if r is False else 0))
