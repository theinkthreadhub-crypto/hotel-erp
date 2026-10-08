# -*- coding: utf-8 -*-
"""
Setu - Restaurant & Hotel POS - Standalone Desktop Launcher + LAN Server
Powered by Aghanya Devanya Enterprises

The PC running this file is the "main counter". It:
  * serves hotel_erp.html to this PC and to phones/tablets on the same WiFi
  * keeps the single shared database on disk (setu-db.json) with daily backups
  * opens the desktop window (unless started with --server)

Usage:
  python app_main.py            -> desktop window + LAN server
  python app_main.py --server   -> LAN server only (no window)
  python app_main.py --server --port 8000 --data <folder>
"""
import os
import sys
import json
import time
import shutil
import socket
import secrets
import threading
import http.server
import urllib.request

APP_PORT = 8000
MAX_BODY = 200 * 1024 * 1024   # 200 MB upper bound for one database upload
KEEP_BACKUPS = 60              # daily backup files kept


def get_base_dir():
    # If running as PyInstaller bundled executable
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        # If user has hotel_erp.html placed right next to .exe, prioritize it
        if os.path.exists(os.path.join(exe_dir, 'hotel_erp.html')):
            return exe_dir
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))


def default_data_dir():
    # User data directory on Windows (%LOCALAPPDATA%\AghanyaDevanyaERP\Data)
    local_app_data = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    return os.path.join(local_app_data, 'AghanyaDevanyaERP', 'Data')


def lan_ips():
    ips = set()
    try:
        # UDP "connect" sends nothing; it only picks the outgoing interface
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))
            ips.add(s.getsockname()[0])
    except Exception:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            ips.add(ip)
    except Exception:
        pass
    return sorted(ip for ip in ips if not ip.startswith('127.'))


class SetuStore:
    """Single shared database file with optimistic versioning."""

    def __init__(self, data_dir):
        self.dir = data_dir
        self.path = os.path.join(data_dir, 'setu-db.json')
        self.backup_dir = os.path.join(data_dir, 'Backups')
        os.makedirs(self.backup_dir, exist_ok=True)
        self.lock = threading.Lock()
        self.version = 0
        self.saved_at = 0
        self.raw = 'null'           # JSON text of the data object
        self.tokens_path = os.path.join(data_dir, 'setu-devices.json')
        self.tokens = {}            # token -> role, for LAN devices (kept across restarts)
        try:
            with open(self.tokens_path, 'r', encoding='utf-8') as f:
                self.tokens = json.load(f)
        except Exception:
            pass
        self._load()

    def add_token(self, role):
        token = secrets.token_hex(16)
        self.tokens[token] = role
        try:
            with open(self.tokens_path, 'w', encoding='utf-8') as f:
                json.dump(self.tokens, f)
        except Exception:
            pass
        return token

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                doc = json.load(f)
            self.version = int(doc.get('version', 0))
            self.saved_at = doc.get('savedAt', 0)
            self.raw = json.dumps(doc.get('data'), ensure_ascii=False)
        except Exception:
            # Never overwrite a file we could not read: keep it aside and start empty
            bad = self.path + '.corrupt-' + time.strftime('%Y%m%d-%H%M%S')
            try:
                shutil.copy2(self.path, bad)
            except Exception:
                pass
            self.version, self.raw = 0, 'null'

    def data(self):
        return json.loads(self.raw)

    def write(self, data_obj):
        self.version += 1
        self.saved_at = int(time.time() * 1000)
        self.raw = json.dumps(data_obj, ensure_ascii=False)
        doc = '{"version": %d, "savedAt": %d, "data": %s}' % (self.version, self.saved_at, self.raw)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(doc)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)       # atomic swap: a power cut leaves old or new, never half
        # One rolling backup per day (last write of the day wins)
        try:
            shutil.copy2(self.path, os.path.join(self.backup_dir, 'setu-' + time.strftime('%Y-%m-%d') + '.json'))
            files = sorted(x for x in os.listdir(self.backup_dir) if x.startswith('setu-') and x.endswith('.json'))
            for old in files[:-KEEP_BACKUPS]:
                os.remove(os.path.join(self.backup_dir, old))
        except Exception:
            pass

    def check_pin(self, pin):
        try:
            d = self.data() or {}
        except Exception:
            return None
        st = d.get('settings') or {}
        auth = d.get('auth') or {}
        pin = str(pin or '')
        if not pin:
            return None
        if pin in (str(st.get('adminPin') or ''), str(auth.get('password') or '')):
            return 'admin'
        if pin == str(st.get('cashierPin') or ''):
            return 'cashier'
        return None


def make_handler(base_dir, store, port):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=base_dir, **kwargs)

        def log_message(self, format, *args):
            pass  # suppress log output

        # ---------- helpers ----------
        def is_local(self):
            return self.client_address[0] in ('127.0.0.1', '::1', '::ffff:127.0.0.1')

        def role(self):
            if self.is_local():
                return 'local'
            return store.tokens.get(self.headers.get('X-Setu-Token', ''))

        def send_json(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_db(self):
            # Data is already JSON text; avoid a parse/serialize round-trip on big databases
            body = ('{"version": %d, "savedAt": %d, "data": %s}' % (store.version, store.saved_at, store.raw)).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def read_json(self):
            n = int(self.headers.get('Content-Length') or 0)
            if n <= 0 or n > MAX_BODY:
                raise ValueError('bad length')
            return json.loads(self.rfile.read(n).decode('utf-8'))

        def end_headers(self):
            # The app page must never come from a stale cache on LAN devices
            if self.path.split('?')[0].endswith('.html'):
                self.send_header('Cache-Control', 'no-cache')
            super().end_headers()

        # ---------- routes ----------
        def do_GET(self):
            path = self.path.split('?')[0]
            if not path.startswith('/api/'):
                return super().do_GET()
            if path == '/api/ping':
                return self.send_json(200, {'setu': True, 'version': store.version, 'local': self.is_local()})
            if path == '/api/info':
                return self.send_json(200, {'setu': True, 'port': port, 'ips': lan_ips(), 'local': self.is_local()})
            if not self.role():
                return self.send_json(401, {'error': 'pin required'})
            if path == '/api/version':
                return self.send_json(200, {'version': store.version})
            if path == '/api/db':
                with store.lock:
                    return self.send_db()
            return self.send_json(404, {'error': 'not found'})

        def do_POST(self):
            path = self.path.split('?')[0]
            if path == '/api/login':
                try:
                    pin = self.read_json().get('pin')
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                role = store.check_pin(pin)
                if not role:
                    time.sleep(1)   # slow down PIN guessing
                    return self.send_json(403, {'error': 'wrong pin'})
                token = store.add_token(role)
                return self.send_json(200, {'token': token, 'role': role})
            if path == '/api/db':
                role = self.role()
                if not role:
                    return self.send_json(401, {'error': 'pin required'})
                try:
                    body = self.read_json()
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                data = body.get('data')
                if not isinstance(data, dict) or 'settings' not in data:
                    return self.send_json(400, {'error': 'invalid data'})
                force = bool(body.get('force'))
                with store.lock:
                    # First upload (migration from the browser) and forced restore are main-counter only
                    if (store.version == 0 or force) and role not in ('local', 'admin'):
                        return self.send_json(403, {'error': 'main counter only'})
                    if not force and int(body.get('baseVersion', -1)) != store.version:
                        return self.send_db_conflict()
                    store.write(data)
                    return self.send_json(200, {'version': store.version, 'savedAt': store.saved_at})
            return self.send_json(404, {'error': 'not found'})

        def send_db_conflict(self):
            body = ('{"conflict": true, "version": %d, "savedAt": %d, "data": %s}' % (store.version, store.saved_at, store.raw)).encode('utf-8')
            self.send_response(409)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def setu_running(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/ping', timeout=1.5) as r:
            return json.loads(r.read().decode('utf-8')).get('setu') is True
    except Exception:
        return False


def port_busy(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def start_server(base_dir, data_dir, port):
    store = SetuStore(data_dir)
    httpd = http.server.ThreadingHTTPServer(('0.0.0.0', port), make_handler(base_dir, store, port))
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def main():
    base_dir = get_base_dir()
    port = int(arg('--port', APP_PORT))
    data_dir = arg('--data', default_data_dir())
    os.makedirs(data_dir, exist_ok=True)
    server_only = '--server' in sys.argv

    # The port is fixed on purpose: the browser keeps login/session per address,
    # and a random port used to make all data look "lost".
    already = setu_running(port)
    if not already:
        if port_busy(port):
            msg = (f'Port {port} par koi doosra program chal raha hai, isliye Setu start nahi ho saka.\n'
                   f'Us program ko band karke Setu dobara kholein.')
            print(msg)
            if not server_only:
                try:
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(0, msg, 'Setu', 0x10)
                except Exception:
                    pass
            sys.exit(1)
        start_server(base_dir, data_dir, port)

    url = f"http://127.0.0.1:{port}/hotel_erp.html"

    if server_only:
        if already:
            print(f'Setu pehle se chal raha hai: {url}')
            return
        print('Setu LAN server chalu hai.')
        print(f'  Is PC par:      {url}')
        for ip in lan_ips():
            print(f'  Phone/Tablet:   http://{ip}:{port}/hotel_erp.html')
        print('Band karne ke liye Ctrl+C dabayein.')
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    import webview  # only needed for the desktop window

    icon_path = os.path.join(base_dir, 'favicon.ico')
    if not os.path.exists(icon_path):
        icon_path = None

    # Create native desktop window
    webview.create_window(
        title='Setu - Restaurant & Hotel POS',
        url=url,
        width=1340,
        height=860,
        min_size=(1020, 680),
        resizable=True,
        text_select=True,
        zoomable=True
    )

    webview.start(
        private_mode=False,
        storage_path=data_dir,
        icon=icon_path
    )


if __name__ == '__main__':
    main()
