"""A small Chrome DevTools Protocol client on the standard library: launches headless Chrome
(or Edge), opens a websocket to its page, and sends commands. Enough for running tests and
reading Chrome's built-in coverage; no third-party packages."""
import base64
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request


class Chrome:
    def __init__(self, binary, width=1280, height=720, timeout=30):
        self.profile = tempfile.mkdtemp(prefix='sor-chrome-')
        self.proc = subprocess.Popen(
            [binary, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
             '--disable-extensions', '--remote-debugging-port=0', f'--user-data-dir={self.profile}',
             f'--window-size={width},{height}', 'about:blank'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = os.path.join(self.profile, 'DevToolsActivePort')
        deadline = time.time() + timeout
        while not (os.path.isfile(port_file) and open(port_file).read().strip()):
            if time.time() > deadline or self.proc.poll() is not None:
                self.close()
                raise RuntimeError('Chrome did not start its DevTools endpoint')
            time.sleep(0.05)
        port = open(port_file).read().split()[0]
        pages = []
        while not pages and time.time() < deadline:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=5) as r:
                pages = [p for p in json.load(r) if p.get('type') == 'page']
            time.sleep(0.05)
        if not pages:
            self.close()
            raise RuntimeError('Chrome opened no page')
        self.page = Socket(pages[0]['webSocketDebuggerUrl'], timeout)

    def close(self):
        try:
            self.page.close()
        except Exception:
            pass
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)
        shutil.rmtree(self.profile, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Socket:
    """One DevTools websocket: `call` sends a command and returns its result; events that arrive
    meanwhile are kept in `events`."""

    def __init__(self, url, timeout):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f'GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n'
                           'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                           f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        head = b''
        while b'\r\n\r\n' not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError('DevTools closed the connection')
            head += chunk
        if b' 101 ' not in head.split(b'\r\n', 1)[0]:
            raise ConnectionError('DevTools refused the websocket: ' + head.split(b'\r\n', 1)[0].decode())
        self.buf = head.split(b'\r\n\r\n', 1)[1]
        self.next_id = 0
        self.events = []

    def _exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise ConnectionError('DevTools closed the connection')
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _frame(self, opcode, data):
        head = bytearray([0x80 | opcode])
        n = len(data)
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += n.to_bytes(2, 'big')
        else:
            head.append(0x80 | 127)
            head += n.to_bytes(8, 'big')
        mask = os.urandom(4)
        masked = (int.from_bytes(data, 'big') ^ int.from_bytes((mask * (n // 4 + 1))[:n], 'big')).to_bytes(n, 'big') if n else b''
        self.sock.sendall(bytes(head) + mask + masked)

    def _message(self):
        parts = []
        while True:
            b1, b2 = self._exact(2)
            n = b2 & 0x7F
            if n == 126:
                n = int.from_bytes(self._exact(2), 'big')
            elif n == 127:
                n = int.from_bytes(self._exact(8), 'big')
            data = self._exact(n)
            opcode = b1 & 0x0F
            if opcode == 9:          # ping
                self._frame(10, data)
                continue
            if opcode == 8:          # close
                raise ConnectionError('DevTools closed the connection')
            parts.append(data)
            if b1 & 0x80:
                return b''.join(parts).decode('utf-8')

    def call(self, method, **params):
        self.next_id += 1
        self._frame(1, json.dumps({'id': self.next_id, 'method': method, 'params': params}).encode())
        while True:
            msg = json.loads(self._message())
            if msg.get('id') == self.next_id:
                if 'error' in msg:
                    raise RuntimeError(f'{method}: {msg["error"].get("message")}')
                return msg.get('result', {})
            self.events.append(msg)

    def close(self):
        try:
            self._frame(8, b'')
        finally:
            self.sock.close()
