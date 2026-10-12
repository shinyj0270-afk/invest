"""Authenticated HTTPS companion for the existing loopback dashboard.

Credentials and certificates stay in .local/mobile-access. No data is copied.
"""
import argparse
import base64
import getpass
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import queue
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
ITERATIONS = 600_000
MAX_RESPONSE = 128 * 1024 * 1024
LAN_NETWORKS = tuple(ipaddress.ip_network(x) for x in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
CLOUDFLARED_URL = 'https://github.com/cloudflare/cloudflared/releases/download/2026.10.0/cloudflared-windows-amd64.exe'
CLOUDFLARED_SHA256 = '86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c'


def lan_address(value):
    address = ipaddress.IPv4Address(value)
    if not any(address in network for network in LAN_NETWORKS):
        raise ValueError('집/회사 내부 IPv4 주소를 지정하세요.')
    return str(address)


def detect_address():
    if os.name == 'nt':
        command = ("$mobileIndexes = @(Get-NetAdapter -Physical | Where-Object Status -eq Up | "
                   "Select-Object -ExpandProperty ifIndex); "
                   "@(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceIndex -in $mobileIndexes } | "
                   "Select-Object -ExpandProperty IPAddress) | ConvertTo-Json -Compress")
        result = subprocess.run(['powershell.exe','-NoProfile','-Command',command],
                                check=True,capture_output=True,text=True)
        values = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(values,str): values=[values]
        addresses=[]
        for value in values:
            try: addresses.append(lan_address(value))
            except ValueError: pass
        if len(addresses)!=1:
            raise ValueError('물리 네트워크의 내부 주소가 확인되지 않았습니다. --address 또는 외부 HTTPS 연결을 설정하세요.')
        return addresses[0]
    # UDP connect selects the local interface without sending a packet.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.connect(('192.0.2.1', 9))
        return lan_address(connection.getsockname()[0])


def password_record(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('접속 비밀번호는 12~256자로 입력하세요.')
    salt = secrets.token_bytes(32)
    return dict(salt=salt.hex(), digest=hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS).hex())


def password_pair_error(password, confirmation):
    if not 12 <= len(password) <= 256:
        return '비밀번호는 12~256자로 입력하세요.'
    if password != confirmation:
        return '두 비밀번호가 일치하지 않습니다.'
    return ''


def request_password_window():
    """Masked local UI; the password never enters command arguments or logs."""
    import tkinter as tk
    from tkinter import ttk
    window=tk.Tk()
    window.title('INVESTMENT · 휴대폰 접속 비밀번호 설정')
    window.geometry('490x380')
    window.resizable(False,False)
    panel=ttk.Frame(window,padding=24);panel.pack(fill='both',expand=True)
    ttk.Label(panel,text='휴대폰 접속 비밀번호',font=('Malgun Gothic',15,'bold')).pack(anchor='w')
    ttk.Label(panel,text='12~256자로 입력하세요. 입력한 글자는 별표로 표시됩니다.').pack(anchor='w',pady=(8,16))
    ttk.Label(panel,text='비밀번호').pack(anchor='w')
    password=ttk.Entry(panel,show='*',width=48);password.pack(fill='x',pady=(3,8))
    ttk.Label(panel,text='비밀번호 확인').pack(anchor='w')
    confirmation=ttk.Entry(panel,show='*',width=48);confirmation.pack(fill='x',pady=(3,8))
    message=tk.StringVar()
    ttk.Label(panel,textvariable=message,foreground='#b3344f').pack(anchor='w')
    result=[]
    def confirm(event=None):
        value=password.get()
        error=password_pair_error(value,confirmation.get())
        if error:
            message.set(error)
            (password if not 12<=len(value)<=256 else confirmation).focus_set()
            return
        result.append(value)
        password.delete(0,'end');confirmation.delete(0,'end')
        window.destroy()
    actions=ttk.Frame(panel);actions.pack(fill='x',pady=(10,0))
    ttk.Button(actions,text='취소',command=window.destroy).pack(side='right')
    ttk.Button(actions,text='설정하고 접속 시작',command=confirm).pack(side='right',padx=8)
    window.update_idletasks()
    window.geometry(f'{max(490,window.winfo_reqwidth())}x{max(380,window.winfo_reqheight())}')
    window.bind('<Return>',confirm)
    window.bind('<Escape>',lambda event:window.destroy())
    window.after(100,lambda:(window.lift(),password.focus_force()))
    window.mainloop()
    if not result:
        raise KeyboardInterrupt()
    return result.pop()


class Access:
    def __init__(self, origin, record):
        parsed = urlsplit(origin)
        if parsed.scheme != 'https' or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('HTTPS 접속 주소만 허용합니다.')
        hostname=parsed.hostname or ''
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?',hostname) or '..' in hostname:
            raise ValueError('접속 호스트를 확인하세요.')
        if not 1 <= (parsed.port or 443) <= 65535:
            raise ValueError('접속 포트를 확인하세요.')
        self.origin, self.authority = origin, parsed.netloc
        self.salt, self.digest = bytes.fromhex(record['salt']), bytes.fromhex(record['digest'])
        if len(self.salt) != 32 or len(self.digest) != 32:
            raise ValueError('접속 인증 설정을 다시 만드세요.')
        self.lock = threading.Lock()
        self.failures = []

    def authenticate(self, value):
        # Global bounded backoff also covers attempts from changing source IPs.
        with self.lock:
            now = time.monotonic()
            self.failures = [x for x in self.failures if now - x < 60]
            if len(self.failures) >= 8:
                return 429
            try:
                if not value or not value.startswith('Basic ') or len(value) > 2048:
                    raise ValueError()
                username, password = base64.b64decode(value[6:], validate=True).decode('utf-8').split(':', 1)
                if username != 'investment' or not 12 <= len(password) <= 256:
                    raise ValueError()
                actual = hashlib.pbkdf2_hmac('sha256', password.encode(), self.salt, ITERATIONS)
                valid = hmac.compare_digest(actual, self.digest)
            except (ValueError, UnicodeError):
                valid = False
            if valid:
                return 200
            # Browser's initial challenge is not a failed password attempt.
            if value:
                self.failures.append(now)
            return 401


def handler_for(access, backend_port):
    class MobileHandler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def reply(self, status, content):
            body = content.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if status == 401:
                self.send_header('WWW-Authenticate', 'Basic realm="INVESTMENT mobile", charset="UTF-8"')
            if status == 429:
                self.send_header('Retry-After', '60')
            self.end_headers()
            self.wfile.write(body)

        def gate(self):
            if self.headers.get_all('Host') != [access.authority]:
                self.reply(403, '접속 주소를 확인하세요.'); return False
            if self.headers.get('Origin') not in (None, access.origin):
                self.reply(403, '다른 사이트의 요청은 허용하지 않습니다.'); return False
            if self.headers.get('Sec-Fetch-Site') == 'cross-site' and self.headers.get('Sec-Fetch-Mode') != 'navigate':
                self.reply(403, '대시보드 주소를 직접 열어 주세요.'); return False
            status = access.authenticate(self.headers.get('Authorization'))
            if status != 200:
                self.reply(status, '로그인이 필요합니다.' if status == 401 else '잠시 후 다시 로그인하세요.')
                return False
            return True

        def do_GET(self):
            if not self.gate(): return
            target = self.requestline.split(' ')[1]
            if not target.startswith('/') or target.startswith('//') or '\\' in target:
                self.reply(400, '접속 경로를 확인하세요.'); return
            # Reads are allowlisted; never proxy credentials or arbitrary targets.
            route = urlsplit(self.path).path
            if route not in ('/', '/dashboard', '/health', '/holdings-frame', '/holdings',
                             '/company-view', '/company-financials', '/financial-monitor',
                             '/market-refresh', '/quote-refresh', '/holding-market',
                             '/research-library', '/recommendations'):
                self.reply(404, '찾을 수 없습니다.'); return
            if route == '/holding-market' and 'refresh' in urlsplit(self.path).query:
                self.reply(403, '휴대폰에서는 저장된 자료를 조회합니다.'); return
            backend = http.client.HTTPConnection('127.0.0.1', backend_port, timeout=120)
            try:
                headers = {'Host': f'127.0.0.1:{backend_port}'}
                token = self.headers.get('X-Dashboard-Token')
                if token: headers['X-Dashboard-Token'] = token
                backend.request('GET', self.path, headers=headers)
                response = backend.getresponse()
                body = response.read(MAX_RESPONSE + 1)
                if len(body) > MAX_RESPONSE:
                    raise ValueError('response limit')
                content_type = response.getheader('Content-Type', 'application/octet-stream')
                if 'text/html' in content_type:
                    notice = ('<style>.mobile-readonly{position:fixed;bottom:8px;right:8px;z-index:9999;'
                              'padding:6px 12px;border-radius:16px;background:#293542;color:white;'
                              'font:12px sans-serif;pointer-events:none}'
                              '#refreshData,#pQuoteRefresh,#pSyncNow,#pEntry,#pImport,#pEntryPanel,'
                              '#pManagement,#pSyncConflict,[data-rec-month],[data-rec-exception]'
                              '{display:none!important}</style>'
                              '<div class="mobile-readonly" role="status">휴대폰 보기 · 읽기 전용</div>')
                    # Insert after doctype so document remains in standards mode.
                    text = body.decode('utf-8')
                    text = text.replace('</body>', notice + '</body>') if '</body>' in text else text + notice
                    body = text.encode('utf-8')
                self.send_response(response.status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('X-Frame-Options', 'SAMEORIGIN')
                self.end_headers()
                self.wfile.write(body)
            except (OSError, http.client.HTTPException, ValueError):
                self.reply(503, 'PC에서 INVESTMENT 대시보드를 실행한 뒤 다시 열어 주세요.')
            finally:
                backend.close()

        def do_POST(self):
            if self.gate(): self.reply(403, '휴대폰에서는 열람만 가능합니다. 입력·갱신은 PC에서 진행하세요.')

        def log_message(self, *args):
            pass  # No credentials, URLs, holdings, or request bodies in logs.

    return MobileHandler


class LimitedServer(ThreadingHTTPServer):
    """Bound simultaneous workers on both LAN and tunnel connections."""
    def __init__(self, address, handler):
        self.workers = threading.BoundedSemaphore(16)
        super().__init__(address, handler)

    def process_request(self, request, address):
        if not self.workers.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.workers.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.workers.release()


class TLSServer(LimitedServer):
    def __init__(self, address, handler, context):
        self.context=context
        super().__init__(address,handler)

    def get_request(self):
        connection,address=super().get_request()
        connection.settimeout(10)
        try:
            return self.context.wrap_socket(connection,server_side=True),address
        except OSError:
            connection.close()
            raise


def configure(folder, address, port, public_origin=None, internet=False, password_window=False):
    folder.mkdir(parents=True, exist_ok=True)
    config = folder / 'config.json'
    if config.exists():
        raise ValueError('기존 접속 설정이 있습니다. 기존 설정을 보존합니다.')
    if public_origin:
        Access(public_origin, password_record('synthetic-validation-only'))
    openssl = shutil.which('openssl')
    if not openssl and Path('C:/Program Files/Git/usr/bin/openssl.exe').exists():
        openssl = 'C:/Program Files/Git/usr/bin/openssl.exe'
    if not openssl and not public_origin:
        raise ValueError('HTTPS 인증서 생성에 OpenSSL이 필요합니다. Git for Windows 설치를 확인하세요.')
    if password_window:
        record=password_record(request_password_window())
    else:
        while True:
            password = getpass.getpass('휴대폰 접속 비밀번호 (12자 이상): ')
            if not 12 <= len(password) <= 256:
                print('비밀번호는 12~256자로 입력하세요. 다시 입력합니다.')
                continue
            if password != getpass.getpass('비밀번호 확인: '):
                print('두 비밀번호가 일치하지 않습니다. 다시 입력합니다.')
                continue
            record = password_record(password)
            break
    if not public_origin:
        cert, key = folder / 'cert.pem', folder / 'key.pem'
        if cert.exists() or key.exists():
            raise ValueError('기존 인증서가 있습니다. 파일을 보존합니다.')
        subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-sha256', '-nodes',
                        '-days', '365', '-subj', '/CN=INVESTMENT Mobile',
                        '-addext', 'subjectAltName=IP:' + address,
                        '-keyout', str(key), '-out', str(cert)],check=True,capture_output=True)
        os.chmod(key, 0o600)
    data = dict(origin=public_origin or f'https://{address}:{port}', password=record,
                mode='internet' if internet else 'proxy' if public_origin else 'lan', bind='127.0.0.1' if public_origin else address, port=port)
    with config.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2)
    os.chmod(config, 0o600)


def install_tunnel(folder):
    """Pinned official Windows binary, private to this project."""
    if os.name!='nt':
        raise ValueError('외부 주소 자동 실행은 Windows용입니다. 외부 HTTPS 연결 모드를 사용하세요.')
    binary=folder/'cloudflared.exe'
    if binary.exists():
        if hashlib.sha256(binary.read_bytes()).hexdigest()!=CLOUDFLARED_SHA256:
            raise ValueError('외부 접속 도구 해시가 다릅니다. 기존 파일을 보존합니다.')
        return binary
    print('외부 접속 도구를 준비하고 있습니다.')
    folder.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=folder,suffix='.download',delete=False) as stream:
        temporary=Path(stream.name)
        try:
            with urlopen(CLOUDFLARED_URL,timeout=60) as response:
                content=response.read(100*1024*1024+1)
            if hashlib.sha256(content).hexdigest()!=CLOUDFLARED_SHA256:
                raise ValueError('외부 접속 도구 검증 실패')
            stream.write(content)
        except Exception:
            stream.close();temporary.unlink(missing_ok=True)
            raise
    temporary.replace(binary)
    return binary


def start_tunnel(binary,port):
    process=subprocess.Popen([str(binary),'--no-autoupdate','tunnel','--url',f'http://127.0.0.1:{port}',
                              '--protocol','http2','--metrics','127.0.0.1:0'],
                             stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    addresses=queue.Queue(maxsize=1)
    def read():
        for line in process.stdout:
            found=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',line)
            if found and addresses.empty():
                try:addresses.put_nowait(found.group(0))
                except queue.Full:pass
    threading.Thread(target=read,daemon=True).start()
    try:
        origin=addresses.get(timeout=60)
        Access(origin,password_record('synthetic-validation-only'))
        return process,origin
    except Exception:
        stop_tunnel(process)
        raise ValueError('외부 HTTPS 주소를 준비하지 못했습니다. 네트워크 연결을 확인하세요.') from None


def stop_tunnel(process):
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    if process.stdout:process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description='휴대폰 HTTPS 대시보드 · 같은 Wi-Fi · 로그인 · 읽기 전용')
    parser.add_argument('--address', help='PC의 내부 IPv4 주소; 첫 실행에서 자동 탐지')
    parser.add_argument('--port', type=int)
    parser.add_argument('--backend-port', type=int, default=8767)
    parser.add_argument('--public-origin', help='외부 HTTPS 연결의 정확한 주소; 이 모드는 127.0.0.1에서만 수신')
    parser.add_argument('--internet', action='store_true', help='회사 PC 외부 접속 · 임시 HTTPS 주소 자동 연결')
    parser.add_argument('--password-window', action='store_true', help='첫 비밀번호를 별표 입력창에서 설정')
    args = parser.parse_args()
    args.port=args.port or (8771 if args.internet or args.public_origin else 8770)
    if not all(1 <= port <= 65535 for port in (args.port, args.backend_port)):
        parser.error('포트는 1~65535 범위여야 합니다.')
    if args.port==args.backend_port:
        parser.error('휴대폰 접속 포트는 PC 대시보드 포트와 달라야 합니다.')
    if args.internet and (args.address or args.public_origin):
        parser.error('--internet은 --address/--public-origin과 함께 지정하지 마세요.')
    folder = ROOT / '.local/mobile-access' / ('internet' if args.internet or args.public_origin else 'lan')
    config = folder / 'config.json'
    if not config.exists():
        if args.public_origin and args.address:
            parser.error('--public-origin과 --address를 함께 지정하지 마세요.')
        address = None if args.public_origin or args.internet else lan_address(args.address) if args.address else detect_address()
        configure(folder, address, args.port, args.public_origin or ('https://pending.trycloudflare.com' if args.internet else None),args.internet,args.password_window)
    data = json.loads(config.read_text(encoding='utf-8'))
    access = Access(data['origin'], data['password'])
    parsed = urlsplit(access.origin)
    mode = data.get('mode','lan')
    if mode not in ('lan','proxy','internet'):
        raise ValueError('접속 모드를 확인하세요.')
    if args.internet and mode!='internet':
        raise ValueError('기존 외부 주소 설정이 있습니다. docs/MOBILE_ACCESS.md를 확인하세요.')
    if args.public_origin and (mode!='proxy' or args.public_origin!=access.origin):
        raise ValueError('기존 외부 주소와 다릅니다.')
    if args.address and (mode!='lan' or lan_address(args.address) != parsed.hostname):
        raise ValueError('주소가 기존 인증서/설정과 다릅니다. docs/MOBILE_ACCESS.md를 확인하세요.')
    bind_port = data.get('port',parsed.port)
    if args.port != bind_port:
        raise ValueError('기존 접속 포트와 다릅니다.')
    if mode in ('proxy','internet'):
        if data.get('bind')!='127.0.0.1':
            raise ValueError('외부 HTTPS 연결 모드는 loopback에서만 수신합니다.')
        with LimitedServer(('127.0.0.1', bind_port), handler_for(access,args.backend_port)) as server:
            process=None
            try:
                if mode=='internet':
                    print('휴대폰 접속 주소를 준비하고 있습니다.')
                    process,origin=start_tunnel(install_tunnel(folder),bind_port)
                    access.origin=origin;access.authority=urlsplit(origin).netloc
                    print('휴대폰 외부 접속 주소:',origin)
                    print('로그인 사용자 이름: investment / 비밀번호: 직접 설정한 값')
                    print('주소는 실행할 때마다 바뀝니다. PC와 이 창을 켜 두세요. 종료: Ctrl+C')
                else:
                    print('외부 HTTPS 주소:',access.origin)
                    print('연결 대상: http://127.0.0.1:'+str(bind_port))
                    print('외부 HTTPS 연결을 실행해야 휴대폰에서 접속할 수 있습니다. 종료: Ctrl+C')
                server.serve_forever()
            finally:
                if process:stop_tunnel(process)
        return
    address=lan_address(parsed.hostname)
    if data.get('bind',address)!=address:
        raise ValueError('접속 주소와 수신 주소가 다릅니다.')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(folder/'cert.pem'), str(folder/'key.pem'))
    with TLSServer((address, bind_port), handler_for(access, args.backend_port), context) as server:
        certificate = ssl.PEM_cert_to_DER_cert((folder/'cert.pem').read_text(encoding='ascii'))
        print('휴대폰 접속 주소:', access.origin)
        print('로그인 사용자 이름: investment / 비밀번호: 첫 실행에서 직접 설정한 값')
        print('인증서 SHA256:', hashlib.sha256(certificate).hexdigest())
        print('같은 Wi-Fi에서 접속하세요. 종료: Ctrl+C')
        server.serve_forever()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, subprocess.SubprocessError):
        print('접속 서버를 열지 못했습니다. PC 주소·포트·인증서와 docs/MOBILE_ACCESS.md를 확인하세요.')
        raise SystemExit(1)
