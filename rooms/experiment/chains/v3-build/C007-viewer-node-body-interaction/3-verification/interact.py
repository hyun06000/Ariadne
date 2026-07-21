#!/usr/bin/env python3
"""M6 (C006): 상호작용·상태보존 헤드리스 실측 — stdlib raw-WebSocket CDP.

C010에서 짠 방식(순수 stdlib로 Chrome DevTools Protocol을 raw WebSocket으로 구동)을
정적 뷰어의 상호작용 검증에 적용한다. 브라우저 없이 정적 파서로는 클릭→토글의
실행을 관찰할 수 없으므로, 실 Chrome을 headless로 띄워 실제 DOM 상태를 읽는다.

측정:
  M6a  s1 노드 클릭 → #body-s1 이 보인다(hidden 제거), 노드에 .open 표시
  M6b  이어서 s10 노드 클릭 → #body-s10 도 보이고 **#body-s1 은 여전히 보인다**
       (상태보존: 다른 노드 조작이 이미 열린 본문을 안 지운다 — K4/C010·C014)
  M6c  s1 패널의 닫기(✕) → #body-s1 만 닫히고 #body-s10 은 그대로

의존: stdlib만. Chrome 실행 파일 경로는 아래 CHROME 상수.
"""
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request
from base64 import b64encode
from hashlib import sha1

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out.html")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9346


# --- 최소 WebSocket 클라이언트 (stdlib socket, C010 계보) -------------------------
class WS:
    def __init__(self, url):
        assert url.startswith("ws://")
        hostport, _, path = url[5:].partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port)))
        key = b64encode(os.urandom(16)).decode()
        req = (f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        self._buf = b""
        while b"\r\n\r\n" not in self._buf:
            self._buf += self.sock.recv(4096)
        self._buf = self._buf.split(b"\r\n\r\n", 1)[1]

    def send(self, data):
        payload = data.encode()
        header = struct.pack("!B", 0x81)
        n = len(payload)
        mask = os.urandom(4)
        if n < 126:
            header += struct.pack("!B", 0x80 | n)
        elif n < 65536:
            header += struct.pack("!B", 0x80 | 126) + struct.pack("!H", n)
        else:
            header += struct.pack("!B", 0x80 | 127) + struct.pack("!Q", n)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + masked)

    def _read(self, n):
        while len(self._buf) < n:
            self._buf += self.sock.recv(65536)
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def recv(self):
        b0, b1 = self._read(2)
        ln = b1 & 0x7F
        if ln == 126:
            ln = struct.unpack("!H", self._read(2))[0]
        elif ln == 127:
            ln = struct.unpack("!Q", self._read(8))[0]
        return self._read(ln).decode("utf-8", "replace")


class CDP:
    def __init__(self, ws_url):
        self.ws = WS(ws_url)
        self._id = 0

    def call(self, method, **params):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def evaluate(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True)
        return r.get("result", {}).get("value")


def main():
    if not os.path.exists(OUT):
        print("FAIL: out.html 없음 — render.py 먼저"); sys.exit(1)
    if not os.path.exists(CHROME):
        print("FAIL: Chrome 없음:", CHROME); sys.exit(1)

    profile = os.path.join(HERE, ".chrome-profile-m6")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
         f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # DevTools 엔드포인트 대기
        ws_url = None
        for _ in range(50):
            try:
                data = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read()
                targets = json.loads(data)
                for t in targets:
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        ws_url = t["webSocketDebuggerUrl"]; break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        if not ws_url:
            print("FAIL: DevTools 엔드포인트 못 찾음"); sys.exit(1)

        cdp = CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Page.navigate", url="file://" + OUT)
        # 로드·JS 마운트 대기 (리스너 부착까지)
        for _ in range(50):
            time.sleep(0.15)
            ready = cdp.evaluate(
                "document.readyState==='complete' && "
                "!!document.querySelector('.node.clickable[data-body=\"body-s1\"]')")
            if ready:
                break

        def hidden(body_id):
            return cdp.evaluate(
                f"document.getElementById('{body_id}').hasAttribute('hidden')")

        def click_node(nid):
            cdp.evaluate(
                f"document.querySelector('.node.clickable[data-body=\"body-{nid}\"]')"
                ".dispatchEvent(new MouseEvent('click',{bubbles:true}))")

        def node_open(nid):
            return cdp.evaluate(
                f"document.querySelector('.node.clickable[data-body=\"body-{nid}\"]')"
                ".classList.contains('open')")

        results = []

        # 초기 상태: 모두 hidden
        init_ok = hidden("body-s1") and hidden("body-s10")

        # M6a: s1 클릭 → 열림 + .open
        click_node("s1"); time.sleep(0.1)
        a_open = (not hidden("body-s1")) and node_open("s1")
        results.append(("M6a s1 클릭→본문 펼침+노드강조", init_ok and a_open,
            f"초기 모두 hidden={init_ok}; 클릭 후 body-s1 보임={not hidden('body-s1')}, "
            f"노드 .open={node_open('s1')}"))

        # M6b: s10 클릭 → s10 열림 AND s1 여전히 열림 (상태보존)
        click_node("s10"); time.sleep(0.1)
        s1_still = not hidden("body-s1")
        s10_open = not hidden("body-s10")
        b_ok = s10_open and s1_still and node_open("s1") and node_open("s10")
        results.append(("M6b 상태보존: 둘째 클릭에도 첫 본문 유지 (K4)", b_ok,
            f"body-s10 보임={s10_open}; **body-s1 여전히 보임={s1_still}**; "
            f"두 노드 다 .open={node_open('s1') and node_open('s10')}"))

        # M6c: s1 패널 닫기(✕) → s1만 닫히고 s10 유지
        cdp.evaluate(
            "document.querySelector('.sb-close[data-close=\"body-s1\"]')"
            ".dispatchEvent(new MouseEvent('click',{bubbles:true}))")
        time.sleep(0.1)
        c_ok = hidden("body-s1") and (not hidden("body-s10")) and (not node_open("s1"))
        results.append(("M6c 닫기 국소성: s1만 닫힘, s10 유지", c_ok,
            f"body-s1 닫힘={hidden('body-s1')}; body-s10 여전히 보임={not hidden('body-s10')}; "
            f"s1 노드 .open 해제={not node_open('s1')}"))

        print("=== M6 상호작용·상태보존 — 실 Chrome(headless) CDP 실측 ===\n")
        allpass = True
        for name, ok, detail in results:
            allpass = allpass and ok
            print(f"[{'PASS' if ok else 'FAIL'}] {name}")
            print(f"       {detail}\n")
        print("=" * 42)
        print("M6 ALL PASS ✓" if allpass else "M6 SOME FAIL ✗")
        sys.exit(0 if allpass else 1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
