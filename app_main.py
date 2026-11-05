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
import urllib.error
import urllib.parse
import ssl
import email.utils
import base64
import copy
import hashlib
import atexit
import setu_security as SEC
import setu_media as MEDIA
import setu_sqlite as SQ
import re

APP_PORT = 8000
APP_VERSION = 'dev'   # stamped by installer/stamp-version.py when the EXE is built
# Setu Cloud the counter PC joins by itself (like Library ERP). SETU_CLOUD_URL overrides it.
DEFAULT_CLOUD_URL = os.environ.get('SETU_CLOUD_URL', 'https://setu-cloud.theinkthreadhub.workers.dev')

def http_cloud_post(path, obj, hotel=None, timeout=12):
    url = DEFAULT_CLOUD_URL
    headers = {'Content-Type': 'application/json', 'User-Agent': 'Setu-Main-Counter/1.0'}
    if hotel:
        headers['X-Setu-Hotel'] = hotel
    req = urllib.request.Request(url + path, data=json.dumps(obj).encode('utf-8'), method='POST', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8') or '{}')
        except Exception:
            return e.code, {'error': f'HTTP {e.code}'}
    except Exception as e:
        return None, {'error': str(e)}

AUTO_LINK_EVERY = 30 * 60   # seconds between join attempts while offline / not licensed yet
MAX_BODY = 200 * 1024 * 1024   # 200 MB upper bound for one database upload
KEEP_BACKUPS = 60              # daily backup files kept
print_lock = threading.Lock()  # one print job at a time keeps receipts from interleaving

# ---------------- Resend Email Service for Password & PIN Recovery ----------------
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', 're_VTatW35W_E1D5xCB7XBJ4shqzsVo7cagp')
RESEND_FROM_EMAIL = os.environ.get('RESEND_FROM_EMAIL', 'Aghanya Devanya Security <security@inkthreadhub.in>')
RESEND_REPLY_TO = os.environ.get('RESEND_REPLY_TO', 'theinkthreadhub@gmail.com')


def send_resend_email(to_email, subject, html, reply_to=None):
    if not RESEND_API_KEY:
        raise ValueError('Resend API Key is not configured')

    def _do_send(from_addr):
        url = 'https://api.resend.com/emails'
        payload = {
            'from': from_addr,
            'to': [to_email] if isinstance(to_email, str) else list(to_email),
            'subject': subject,
            'html': html
        }
        if reply_to or RESEND_REPLY_TO:
            payload['reply_to'] = reply_to or RESEND_REPLY_TO
        headers = {
            'Authorization': f'Bearer {RESEND_API_KEY}',
            'Content-Type': 'application/json',
            'User-Agent': 'AghanyaDevanya-HotelERP/2.0 (Windows NT 10.0; Win64; x64)'
        }
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers=headers, method='POST')
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
            res_data = resp.read().decode('utf-8')
            return json.loads(res_data) if res_data else {'ok': True}

    try:
        return _do_send(RESEND_FROM_EMAIL)
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8', errors='ignore')
        if e.code in (400, 403, 422) and 'domain' in err_msg.lower():
            try:
                return _do_send('Aghanya Devanya Security <onboarding@resend.dev>')
            except Exception:
                pass
        raise RuntimeError(f'Resend API error ({e.code}): {err_msg}')
    except Exception as e:
        raise RuntimeError(f'Email service error: {e}')


def render_forgot_password_email(hotel_name, hotel_id, otp):
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset Code - Aghanya Devanya ERP</title>
</head>
<body style="margin:0;padding:24px 12px;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1e293b;">
  <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:520px;background-color:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 10px 25px rgba(0,0,0,0.07);border:1px solid #e2e8f0;margin:0 auto;">
    <tr>
      <td style="padding:28px 24px 20px;background:linear-gradient(135deg, #0284c7 0%, #0369a1 100%);text-align:center;">
        <h1 style="margin:0;font-size:22px;font-weight:800;color:#ffffff;letter-spacing:0.5px;">Aghanya Devanya Enterprises</h1>
        <p style="margin:6px 0 0;font-size:13px;color:#e0f2fe;font-weight:500;">Restaurant & Hotel POS / ERP Security</p>
      </td>
    </tr>
    <tr>
      <td style="padding:28px 24px;">
        <h2 style="margin:0 0 12px;font-size:18px;font-weight:700;color:#0f172a;">Password & PIN Reset Request</h2>
        <p style="margin:0 0 16px;font-size:14px;line-height:1.6;color:#475569;">
          A password reset was requested for your restaurant POS system:
        </p>
        <div style="background-color:#f8fafc;border-left:4px solid #0284c7;padding:12px 16px;border-radius:6px;margin-bottom:20px;">
          <div style="font-size:13px;color:#64748b;margin-bottom:4px;">Hotel / Restaurant: <strong style="color:#0f172a;">{hotel_name}</strong></div>
          <div style="font-size:13px;color:#64748b;">Hotel ID: <strong style="color:#0f172a;">{hotel_id}</strong></div>
        </div>
        <p style="margin:0 0 10px;font-size:14px;color:#334155;font-weight:600;">Your 6-Digit Verification OTP:</p>
        <div style="text-align:center;padding:18px;background:linear-gradient(135deg, #f0fdf4 0%, #e0f2fe 100%);border:2px dashed #0284c7;border-radius:12px;margin-bottom:20px;">
          <span style="font-family:'Courier New',Courier,monospace;font-size:36px;font-weight:800;letter-spacing:10px;color:#0369a1;display:inline-block;padding-left:10px;">{otp}</span>
        </div>
        <p style="margin:0 0 12px;font-size:13px;color:#64748b;line-height:1.5;">
          ⏱️ This OTP is valid for <strong>15 minutes</strong>. Enter this code on your Hotel ERP screen to choose a new Master Password and Admin PIN.
        </p>
        <div style="margin-top:24px;padding-top:16px;border-top:1px solid #f1f5f9;font-size:12px;color:#94a3b8;line-height:1.5;">
          🔒 <strong>Security Warning:</strong> If you did not request this OTP, someone may be trying to access your ERP. Please ignore this email or contact support. Never share this code with anyone.
        </div>
      </td>
    </tr>
    <tr>
      <td style="padding:16px 24px;background-color:#f8fafc;border-top:1px solid #e2e8f0;text-align:center;font-size:11px;color:#94a3b8;">
        © 2026 Aghanya Devanya Enterprises. All rights reserved.<br>
        Setu Pro Restaurant & Hotel ERP
      </td>
    </tr>
  </table>
</body>
</html>"""



def get_base_dir():
    # If running as PyInstaller bundled executable
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        # The page built into the EXE always wins: an old hotel_erp.html lying next to a new
        # EXE used to bring the old version back. Testers can opt in with use-local-html.txt.
        if os.path.exists(os.path.join(exe_dir, 'use-local-html.txt')) and os.path.exists(os.path.join(exe_dir, 'hotel_erp.html')):
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


# ---------------- Direct (silent) printing to Windows printers ----------------
# Receipts arrive as ready ESC/POS bytes and go to the printer as a RAW job,
# so no print dialog appears. Works with thermal printers that have a Windows driver.
def _winspool():
    import ctypes
    from ctypes import wintypes
    ws = ctypes.WinDLL('winspool.drv')
    ws.EnumPrintersW.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    ws.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    ws.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p]
    ws.StartPagePrinter.argtypes = [wintypes.HANDLE]
    ws.WritePrinter.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    ws.EndPagePrinter.argtypes = [wintypes.HANDLE]
    ws.EndDocPrinter.argtypes = [wintypes.HANDLE]
    ws.ClosePrinter.argtypes = [wintypes.HANDLE]
    ws.GetDefaultPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    return ctypes, wintypes, ws


def list_printers():
    if os.name != 'nt':
        return [], ''
    ctypes, wintypes, ws = _winspool()

    class PRINTER_INFO_4(ctypes.Structure):
        _fields_ = [('pPrinterName', wintypes.LPWSTR), ('pServerName', wintypes.LPWSTR), ('Attributes', wintypes.DWORD)]

    flags = 2 | 4   # PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    needed, count = wintypes.DWORD(), wintypes.DWORD()
    ws.EnumPrintersW(flags, None, 4, None, 0, ctypes.byref(needed), ctypes.byref(count))
    names = []
    if needed.value:
        buf = ctypes.create_string_buffer(needed.value)
        if ws.EnumPrintersW(flags, None, 4, buf, needed, ctypes.byref(needed), ctypes.byref(count)):
            arr = ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_4))
            names = [arr[i].pPrinterName for i in range(count.value)]
    size = wintypes.DWORD(0)
    ws.GetDefaultPrinterW(None, ctypes.byref(size))
    default = ''
    if size.value:
        dbuf = ctypes.create_unicode_buffer(size.value)
        if ws.GetDefaultPrinterW(dbuf, ctypes.byref(size)):
            default = dbuf.value
    return names, default


def print_raw(printer, data):
    if os.name != 'nt':
        raise OSError('Direct printing is supported on Windows only')
    ctypes, wintypes, ws = _winspool()

    class DOC_INFO_1(ctypes.Structure):
        _fields_ = [('pDocName', wintypes.LPWSTR), ('pOutputFile', wintypes.LPWSTR), ('pDatatype', wintypes.LPWSTR)]

    h = wintypes.HANDLE()
    if not ws.OpenPrinterW(printer, ctypes.byref(h), None):
        raise OSError(f'Printer "{printer}" not found')
    try:
        doc = DOC_INFO_1('Setu Receipt', None, 'RAW')
        if not ws.StartDocPrinterW(h, 1, ctypes.byref(doc)):
            raise OSError('The printer did not accept the job')
        try:
            ws.StartPagePrinter(h)
            buf = ctypes.create_string_buffer(data, len(data))
            written = wintypes.DWORD(0)
            ok = ws.WritePrinter(h, buf, len(data), ctypes.byref(written))
            ws.EndPagePrinter(h)
            if not ok or written.value != len(data):
                raise OSError('Could not send data to the printer')
        finally:
            ws.EndDocPrinter(h)
    finally:
        ws.ClosePrinter(h)


# ---------------- Printer Health (read the Windows queue, remove stuck / repeated jobs) ----------------
# Separate from the printing code above: it only looks at the queue and deletes jobs on request.
PRINTER_FLAGS = {0x1: 'paused', 0x2: 'error', 0x8: 'jam', 0x10: 'paperout', 0x40: 'paper', 0x80: 'offline', 0x400: 'printing',
                 0x800: 'binfull', 0x1000: 'notavailable', 0x2000: 'waiting', 0x20000: 'tonerlow', 0x40000: 'notoner',
                 0x100000: 'intervention', 0x400000: 'dooropen', 0x1000000: 'powersave'}
JOB_FLAGS = {0x1: 'paused', 0x2: 'error', 0x4: 'deleting', 0x8: 'spooling', 0x10: 'printing', 0x20: 'offline', 0x40: 'paperout',
             0x80: 'printed', 0x200: 'blocked', 0x400: 'intervention', 0x800: 'restart'}
print_history = []   # newest last: Setu's own jobs on this counter, for Printer Health


def _flags(value, table):
    return [name for bit, name in table.items() if value & bit]


def _printer_handles():
    ctypes, wintypes, ws = _winspool()
    ws.GetPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    ws.EnumJobsW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                             ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    ws.SetJobW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    return ctypes, wintypes, ws


def _printer_jobs(ctypes, wintypes, ws, h):
    class SYSTEMTIME(ctypes.Structure):
        _fields_ = [(n, wintypes.WORD) for n in ('y', 'mo', 'dow', 'd', 'h', 'mi', 's', 'ms')]

    class JOB_INFO_1(ctypes.Structure):
        _fields_ = [('JobId', wintypes.DWORD), ('pPrinterName', wintypes.LPWSTR), ('pMachineName', wintypes.LPWSTR),
                    ('pUserName', wintypes.LPWSTR), ('pDocument', wintypes.LPWSTR), ('pDatatype', wintypes.LPWSTR),
                    ('pStatus', wintypes.LPWSTR), ('Status', wintypes.DWORD), ('Priority', wintypes.DWORD),
                    ('Position', wintypes.DWORD), ('TotalPages', wintypes.DWORD), ('PagesPrinted', wintypes.DWORD),
                    ('Submitted', SYSTEMTIME)]

    needed, count = wintypes.DWORD(), wintypes.DWORD()
    ws.EnumJobsW(h, 0, 500, 1, None, 0, ctypes.byref(needed), ctypes.byref(count))
    if not needed.value:
        return []
    buf = ctypes.create_string_buffer(needed.value)
    if not ws.EnumJobsW(h, 0, 500, 1, buf, needed, ctypes.byref(needed), ctypes.byref(count)):
        return []
    arr = ctypes.cast(buf, ctypes.POINTER(JOB_INFO_1))
    out = []
    for i in range(count.value):
        j, t = arr[i], arr[i].Submitted
        out.append({'id': j.JobId, 'doc': j.pDocument or '', 'user': j.pUserName or '', 'pc': j.pMachineName or '',
                    'state': _flags(j.Status, JOB_FLAGS), 'text': j.pStatus or '', 'pages': j.TotalPages,
                    'at': f'{t.y:04d}-{t.mo:02d}-{t.d:02d}T{t.h:02d}:{t.mi:02d}:{t.s:02d}Z'})
    return out


def printer_health():
    if os.name != 'nt':
        return {'supported': False, 'printers': [], 'default': '', 'history': print_history[-40:]}
    ctypes, wintypes, ws = _printer_handles()

    class PRINTER_INFO_2(ctypes.Structure):
        _fields_ = [(n, wintypes.LPWSTR) for n in ('pServerName', 'pPrinterName', 'pShareName', 'pPortName', 'pDriverName',
                                                   'pComment', 'pLocation')] + [('pDevMode', ctypes.c_void_p)] + \
                   [(n, wintypes.LPWSTR) for n in ('pSepFile', 'pPrintProcessor', 'pDatatype', 'pParameters')] + \
                   [('pSecurityDescriptor', ctypes.c_void_p)] + \
                   [(n, wintypes.DWORD) for n in ('Attributes', 'Priority', 'DefaultPriority', 'StartTime', 'UntilTime',
                                                  'Status', 'cJobs', 'AveragePPM')]

    names, default = list_printers()
    printers = []
    for name in names:
        p = {'name': name, 'default': name == default, 'state': [], 'jobs': [], 'port': '', 'driver': ''}
        h = wintypes.HANDLE()
        if not ws.OpenPrinterW(name, ctypes.byref(h), None):
            p['state'] = ['notavailable']
            printers.append(p)
            continue
        try:
            needed = wintypes.DWORD()
            ws.GetPrinterW(h, 2, None, 0, ctypes.byref(needed))
            if needed.value:
                buf = ctypes.create_string_buffer(needed.value)
                if ws.GetPrinterW(h, 2, buf, needed, ctypes.byref(needed)):
                    info = ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_2))[0]
                    p['state'] = _flags(info.Status, PRINTER_FLAGS) + (['workoffline'] if info.Attributes & 0x400 else [])
                    p['port'], p['driver'] = info.pPortName or '', info.pDriverName or ''
            p['jobs'] = _printer_jobs(ctypes, wintypes, ws, h)
        finally:
            ws.ClosePrinter(h)
        printers.append(p)
    return {'supported': True, 'printers': printers, 'default': default, 'history': print_history[-40:]}


def delete_print_jobs(printer, job_ids):
    # job_ids: list of job numbers, or None for every job in that printer's queue
    if os.name != 'nt':
        raise OSError('Windows only')
    ctypes, wintypes, ws = _printer_handles()
    h = wintypes.HANDLE()
    if not ws.OpenPrinterW(printer, ctypes.byref(h), None):
        raise OSError(f'Printer "{printer}" not found')
    try:
        ids = [j['id'] for j in _printer_jobs(ctypes, wintypes, ws, h)] if job_ids is None else [int(x) for x in job_ids]
        done, failed = 0, 0
        for jid in ids:
            if ws.SetJobW(h, jid, 0, None, 5):   # JOB_CONTROL_DELETE
                done += 1
            else:
                failed += 1
        return done, failed
    finally:
        ws.ClosePrinter(h)


class SetuStore:
    """Single shared database file with optimistic versioning."""

    def __init__(self, data_dir):
        self.dir = data_dir
        self.path = os.path.join(data_dir, 'setu-db.json')
        self.backup_dir = os.path.join(data_dir, 'Backups')
        os.makedirs(self.backup_dir, exist_ok=True)
        self.lock = threading.Lock()
        self.on_write = None        # set by CloudSync to push changes quickly
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
        self.elev = {}              # manager approvals: grant id -> {token, exp, by}
        self.reset_otps = {}        # email -> {otp, exp, attempts, sent_at}
        self.fails = {}             # PIN guessing: ip -> [wrong tries, first try time, tries being checked]
        self._guard_lock = threading.Lock()
        self._pub = (None, 'null')
        self._load()
        self._migrate_credentials()

    def public_raw(self):
        """JSON of the data without credentials (what every device gets); cached per saved version."""
        if self._pub[0] is not self.raw:
            try:
                self._pub = (self.raw, json.dumps(SEC.public_view(json.loads(self.raw)), ensure_ascii=False))
            except Exception:
                self._pub = (self.raw, 'null')
        return self._pub[1]

    def _migrate_credentials(self):
        """Plain PINs / owner password from older versions become salted hashes (once). The file as it was
        is kept in Backups\\ first, so the old program can be put back (see docs/P0-SECURITY.md)."""
        try:
            d = json.loads(self.raw)
        except Exception:
            return
        if not isinstance(d, dict) or not SEC.migrate_plaintext(d):
            return
        try:
            if os.path.exists(self.path):
                # Not named setu-*.json: the daily backup rotation must never delete it
                os.makedirs(self.backup_dir, exist_ok=True)
                shutil.copy2(self.path, os.path.join(self.backup_dir, 'before-credential-migration-' + time.strftime('%Y%m%d-%H%M%S') + '.json'))
            with self.lock:
                self.write(d)
            self.log('Credentials moved to salted hashes (plain PINs removed from the data)')
        except Exception as e:
            self.log(f'CREDENTIAL MIGRATION FAILED: {e!r}')

    def clean_expired_otps(self):
        now = time.time()
        for em in list(self.reset_otps):
            if self.reset_otps[em].get('exp', 0) < now:
                del self.reset_otps[em]

    def pin_guard(self, ip, ok=None):
        """5 wrong PINs from one address lock it for 5 minutes. Returns seconds left of a lock (0 = free).
        A check reserves a try at once, so many guesses sent at the same moment cannot get past the limit."""
        with self._guard_lock:
            now = time.time()
            n, first, busy = self.fails.get(ip, [0, now, 0])
            if now - first > 300:
                n, first = 0, now
            if ok is True:
                self.fails.pop(ip, None)
                return 0
            if ok is False:
                self.fails[ip] = [n + 1, first, max(0, busy - 1)]
                return 0
            if n + busy >= 5:
                return max(1, int(300 - (now - first)))
            self.fails[ip] = [n, first, busy + 1]
            return 0

    def hotel_id(self):
        """This counter's own hotel ID (tokens belong to it, never to an ID the device names)."""
        c = getattr(self, '_hid', (None, 'default'))
        if c[0] is not self.raw:
            try:
                d = self.data() or {}
            except Exception:
                d = {}
            c = (self.raw, str((d.get('settings') or {}).get('hotelId') or (d.get('auth') or {}).get('hotelId') or 'default').strip())
            self._hid = c
        return c[1]

    def add_token(self, role, hotel_id='default', name='Staff', expires_in_days=30):
        token = secrets.token_hex(16)
        self.tokens[token] = {
            'role': str(role).lower(),
            'hotelId': str(hotel_id or 'default').strip(),
            'name': str(name or role).strip(),
            'createdAt': int(time.time()),
            'expiresAt': int(time.time()) + (expires_in_days * 86400)
        }
        try:
            with open(self.tokens_path, 'w', encoding='utf-8') as f:
                json.dump(self.tokens, f, indent=2)
        except Exception:
            pass
        return token

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                doc = json.load(f)
            data_obj = doc.get('data')
            if isinstance(data_obj, dict):
                self.migrate_wa_history(data_obj)
            self.version = int(doc.get('version', 0))
            self.saved_at = doc.get('savedAt', 0)
            self.raw = json.dumps(data_obj, ensure_ascii=False)
        except Exception:
            # Never overwrite a file we could not read: keep it aside, then come back from the
            # newest readable daily backup (copied after every save, so it is the last good state)
            bad = self.path + '.corrupt-' + time.strftime('%Y%m%d-%H%M%S')
            try:
                shutil.copy2(self.path, bad)
            except Exception:
                pass
            self.version, self.raw = 0, 'null'
            try:
                files = sorted((x for x in os.listdir(self.backup_dir) if x.startswith('setu-') and x.endswith('.json')), reverse=True)
            except OSError:
                files = []
            for name in files:
                try:
                    with open(os.path.join(self.backup_dir, name), 'r', encoding='utf-8') as f:
                        doc = json.load(f)
                    if not isinstance(doc.get('data'), dict):
                        continue
                    self.version = int(doc.get('version', 0))
                    self.saved_at = doc.get('savedAt', 0)
                    self.raw = json.dumps(doc['data'], ensure_ascii=False)
                    self.log(f'setu-db.json was damaged (kept as {os.path.basename(bad)}); loaded backup {name}')
                    break
                except Exception:
                    continue

    def data(self):
        return json.loads(self.raw)

    def log(self, msg):
        try:
            with open(os.path.join(self.dir, 'setu-server.log'), 'a', encoding='utf-8') as f:
                f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')
        except Exception:
            pass

    def write(self, data_obj):
        # Nothing changes in memory until the file is safely on disk, so a failed
        # write can never leave the server "ahead" of what survives a restart.
        version = self.version + 1
        saved_at = int(time.time() * 1000)
        raw = json.dumps(data_obj, ensure_ascii=False)
        doc = '{"version": %d, "savedAt": %d, "data": %s}' % (version, saved_at, raw)
        tmp = self.path + '.tmp'
        os.makedirs(self.backup_dir, exist_ok=True)   # the data folder may have been deleted while Setu runs
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(doc)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(10):
            try:
                os.replace(tmp, self.path)   # atomic swap: a power cut leaves old or new, never half
                break
            except PermissionError:
                # Antivirus / indexer may hold the file for a moment on Windows
                if attempt == 9:
                    raise
                time.sleep(0.2)
        self.version, self.saved_at, self.raw = version, saved_at, raw
        if self.on_write:
            self.on_write()
        # One rolling backup per day (last write of the day wins); at most every 10 minutes so big databases stay fast
        try:
            if time.time() - getattr(self, '_last_copy', 0) < 600 and os.path.exists(os.path.join(self.backup_dir, 'setu-' + time.strftime('%Y-%m-%d') + '.json')):
                return
            self._last_copy = time.time()
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
        return SEC.check_pin(d, pin)

    def has_users_or_pins(self):
        """Returns True if any user, staff member, or PIN is configured in the database."""
        try:
            return SEC.has_credentials(self.data() or {})
        except Exception:
            return False

    def clean_and_validate_bills(self, data_obj, conflicts=None):
        """
        S01 Financial Invariant Enforcement:
        1. Validates that every Split mode bill satisfies sum(pays.amt) == total.
        2. Deduplicates bills by idemKey (prevents replay/duplicate financial posting).
        3. Backfills durable identity and explicit payment status.
        """
        bills = data_obj.get('bills')
        if not isinstance(bills, list):
            return
        
        seen_idem = {}
        deduped = []
        for b in bills:
            if not isinstance(b, dict):
                continue
            
            # 1. Split payment tender validation
            if b.get('mode') == 'Split':
                pays = b.get('pays')
                if not isinstance(pays, list) or len(pays) == 0:
                    raise ValueError(f"Bill #{b.get('no', '?')} has mode 'Split' but empty pays")
                tender_sum = round(sum(float(p.get('amt') or 0) for p in pays if isinstance(p, dict)), 2)
                bill_total = round(float(b.get('total') or 0), 2)
                if abs(tender_sum - bill_total) > 0.05:
                    raise ValueError(f"Bill #{b.get('no', '?')} split tender sum ({tender_sum}) does not match bill total ({bill_total})")
            
            # 2. Durable identity & idempotency key
            ik = b.get('idemKey')
            if not ik:
                # Backfill durable identity from id or table/no
                ik = f"idem_{b.get('id') or (str(b.get('table', '')) + '_' + str(b.get('no', '')))}"
                b['idemKey'] = ik
                
            if ik in seen_idem:
                # Same sale twice: an identical copy is a retry; different money is a conflict, reported, never silent
                f = seen_idem[ik]
                if any(not jeq(f.get(x, MISSING), b.get(x, MISSING)) for x in ('total', 'sub', 'disc', 'tax', 'mode', 'pays', 'items', 'cancelled')):
                    if conflicts is not None:
                        conflicts.append(('bills', b.get('id'), f'sale key {ik} twice with different amounts (bill #{f.get("no")} kept)', f, b))
                    else:
                        self.log(f'CONFLICT: sale key {ik} twice with different amounts; bill #{f.get("no")} kept, other copy: {json.dumps(b, ensure_ascii=False)[:2000]}')
                continue
            seen_idem[ik] = b
            
            # 3. Explicit payment status
            if not b.get('paymentStatus'):
                b['paymentStatus'] = 'recorded'
            if b.get('mode') == 'UPI' or any((p.get('mode') == 'UPI') for p in (b.get('pays') or []) if isinstance(p, dict)):
                if 'upiVerified' not in b:
                    b['upiVerified'] = False
                    
            deduped.append(b)
            
        data_obj['bills'] = deduped

    def settle_bill(self, payload):
        """
        S01 Atomic Bill Settlement with durable idempotency.
        Executes under self.lock to guarantee zero concurrent duplicate billing.
        """
        with self.lock:
            idem_key = payload.get('idemKey')
            bill = payload.get('bill')
            if not idem_key or not isinstance(bill, dict):
                return 400, {'error': 'idemKey and bill object are required'}
                
            d = self.data()
            bills = d.setdefault('bills', [])
            
            # Idempotency check: Return existing bill if identical request
            existing = next((b for b in bills if b.get('idemKey') == idem_key), None)
            if existing:
                is_same = (
                    existing.get('table') == bill.get('table') and
                    abs(float(existing.get('total') or 0) - float(bill.get('total') or 0)) < 0.01 and
                    existing.get('mode') == bill.get('mode')
                )
                if is_same:
                    return 200, {
                        'ok': True,
                        'alreadySettled': True,
                        'bill': existing,
                        'version': self.version
                    }
                return 409, {
                    'error': 'IDEMPOTENCY_PAYLOAD_MISMATCH',
                    'message': 'Idempotency key has already been used with a different bill payload'
                }
                
            # Table order session duplicate protection
            sess_id = bill.get('orderSessionId')
            tbl = bill.get('table')
            if tbl and sess_id:
                existing_sess = next((b for b in bills if not b.get('cancelled') and b.get('table') == tbl and b.get('orderSessionId') == sess_id), None)
                if existing_sess:
                    return 200, {
                        'ok': True,
                        'alreadySettled': True,
                        'bill': existing_sess,
                        'version': self.version
                    }
                    
            # Split payment verification
            if bill.get('mode') == 'Split':
                pays = bill.get('pays') or []
                if not pays:
                    return 400, {'error': 'SPLIT_TENDER_EMPTY', 'message': 'Split payment must have tender amounts'}
                tender_sum = round(sum(float(p.get('amt') or 0) for p in pays if isinstance(p, dict)), 2)
                bill_total = round(float(bill.get('total') or 0), 2)
                if abs(tender_sum - bill_total) > 0.05:
                    return 400, {
                        'error': 'SPLIT_TENDER_MISMATCH',
                        'message': f'Split payment tender sum ({tender_sum}) does not match bill total ({bill_total})'
                    }
                    
            # Assign sequential bill and kot numbers
            seq = d.setdefault('seq', {'bill': 0, 'kot': 0, 'token': 0})
            seq['bill'] = int(seq.get('bill') or 0) + 1
            bill['no'] = seq['bill']
            seq['kot'] = int(seq.get('kot') or 0) + 1
            bill['kot'] = seq['kot']
            bill['idemKey'] = idem_key
            
            # Status distinction
            bill['paymentStatus'] = 'recorded'
            if bill.get('mode') == 'UPI' or any((p.get('mode') == 'UPI') for p in (bill.get('pays') or []) if isinstance(p, dict)):
                bill['upiVerified'] = False
                
            # Deduct inventory safely
            used = bill.get('used') or []
            stock_list = d.setdefault('stock', [])
            for u in used:
                sid = u.get('sid')
                qty = float(u.get('qty') or 0)
                item = next((s for s in stock_list if s.get('id') == sid), None)
                if item:
                    item['qty'] = round(float(item.get('qty') or 0) - qty, 3)
                    
            # Clear running order from kaccha
            if tbl and 'kaccha' in d and tbl in d['kaccha']:
                del d['kaccha'][tbl]
                
            bills.append(bill)
            self.write(d)
            
            return 200, {
                'ok': True,
                'alreadySettled': False,
                'bill': bill,
                'version': self.version
            }

    # ---------------- WhatsApp Reports & Message Tracking ----------------
    STATUS_RANK = {
        'QUEUED': 1,
        'PROCESSING': 2,
        'SUBMITTED': 3,
        'SENT': 4,
        'DELIVERED': 5,
        'READ': 6,
        'FAILED': 0,
        'UNKNOWN': 0,
        'SKIPPED': 0,
        'CANCELLED': 0
    }

    @staticmethod
    def mask_phone(phone):
        p = re.sub(r'\D', '', str(phone or ''))
        if len(p) >= 10:
            core = p[-10:]
            return core[:2] + '****' + core[-4:]
        if len(p) >= 4:
            return p[:1] + '***' + p[-2:]
        return '****'

    def migrate_wa_history(self, d):
        """Safely backfills historical bill WhatsApp records without fabricating DELIVERED status."""
        msgs = d.setdefault('waMessages', [])
        existing_bill_ids = {m.get('billId') for m in msgs if m.get('billId')}
        for b in (d.get('bills') or []):
            if not isinstance(b, dict):
                continue
            bid = b.get('id')
            if not bid or bid in existing_bill_ids:
                continue
            wa_flag = b.get('wa')
            if wa_flag in ('sent', 'failed'):
                phone = str(b.get('phone') or '')
                now = int(time.time() * 1000)
                st = 'SUBMITTED' if wa_flag == 'sent' else 'FAILED'
                msgs.append({
                    'id': f'wa_hist_{bid}',
                    'hotelId': (d.get('settings') or {}).get('installId') or 'default',
                    'billId': bid,
                    'billNo': b.get('no'),
                    'customerName': b.get('customer') or 'Customer',
                    'phone': phone,
                    'maskedPhone': self.mask_phone(phone),
                    'msgType': 'receipt',
                    'provider': 'baileys',
                    'providerMsgId': '',
                    'templateName': 'setu_receipt_v1',
                    'status': st,
                    'consentRef': 'historical_record',
                    'requestedAt': now,
                    'submittedAt': now if st == 'SUBMITTED' else None,
                    'sentAt': None,
                    'deliveredAt': None,
                    'readAt': None,
                    'failedAt': now if st == 'FAILED' else None,
                    'errorCode': 'LEGACY_FAILURE' if st == 'FAILED' else '',
                    'errorReason': 'Legacy recorded failure' if st == 'FAILED' else '',
                    'idemKey': f'wa_hist_{bid}',
                    'attemptCount': 1,
                    'retryEligible': st == 'FAILED',
                    'staff': 'legacy',
                    'events': [{
                        'status': st,
                        'at': now,
                        'provider': 'baileys',
                        'providerMsgId': '',
                        'note': f'Historical import: marked {st} (delivery not fabricated)'
                    }],
                    'attempts': [{
                        'attemptNo': 1,
                        'requestedAt': now,
                        'provider': 'baileys',
                        'status': st,
                        'providerMsgId': '',
                        'error': ''
                    }]
                })
                existing_bill_ids.add(bid)

    def get_wa_messages(self, filters=None, role='admin', hotel_id=None):
        filters = filters or {}
        with self.lock:
            d = self.data() or {}
        msgs = list(d.get('waMessages') or [])
        
        # Tenant isolation
        if hotel_id:
            msgs = [m for m in msgs if m.get('hotelId') == hotel_id]
            
        # Date range filter
        date_range = filters.get('dateRange', 'all')
        now_ts = int(time.time() * 1000)
        DAY = 86400 * 1000
        start_ts = 0
        end_ts = now_ts + DAY
        
        if date_range == 'today':
            t = time.localtime(time.time())
            start_ts = int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)
        elif date_range == 'yesterday':
            t = time.localtime(time.time() - 86400)
            midnight = int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)
            start_ts = midnight
            end_ts = midnight + DAY
        elif date_range == '7days':
            start_ts = now_ts - 7 * DAY
        elif date_range == 'month':
            t = time.localtime(time.time())
            start_ts = int(time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, -1)) * 1000)
        elif date_range == 'custom':
            if filters.get('startDate'):
                try: start_ts = int(filters['startDate'])
                except Exception: pass
            if filters.get('endDate'):
                try: end_ts = int(filters['endDate'])
                except Exception: pass
                
        if start_ts > 0:
            msgs = [m for m in msgs if (m.get('requestedAt') or 0) >= start_ts]
        if end_ts < now_ts + DAY:
            msgs = [m for m in msgs if (m.get('requestedAt') or 0) <= end_ts]
            
        # Provider filter
        if filters.get('provider') and filters['provider'] != 'all':
            msgs = [m for m in msgs if m.get('provider') == filters['provider']]
            
        # Message Type filter
        if filters.get('msgType') and filters['msgType'] != 'all':
            msgs = [m for m in msgs if m.get('msgType') == filters['msgType']]
            
        # Staff filter
        if filters.get('staff') and filters['staff'] != 'all':
            msgs = [m for m in msgs if str(m.get('staff') or '').lower() == str(filters['staff']).lower()]
            
        # Status filter
        if filters.get('status') and filters['status'] != 'all':
            req_status = filters['status'].upper()
            if req_status == 'PENDING':
                msgs = [m for m in msgs if m.get('status') in ('QUEUED', 'PROCESSING')]
            else:
                msgs = [m for m in msgs if m.get('status') == req_status]
                
        # Search query (by id, billNo, customerName, phone, providerMsgId)
        q = str(filters.get('q') or '').strip().lower()
        if q:
            msgs = [m for m in msgs if (
                q in str(m.get('id', '')).lower() or
                q in str(m.get('billNo', '')).lower() or
                q in str(m.get('customerName', '')).lower() or
                q in str(m.get('phone', '')).lower() or
                q in str(m.get('providerMsgId', '')).lower()
            )]
            
        # Sort descending by requestedAt
        msgs.sort(key=lambda x: (x.get('requestedAt') or 0), reverse=True)
        total_count = len(msgs)
        
        # Pagination
        page = max(1, int(filters.get('page') or 1))
        limit = min(500, max(1, int(filters.get('limit') or 25)))
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        page_msgs = msgs[start_idx:end_idx]
        
        # Privacy masking: Cashier or unauthorized roles must NEVER see full customer mobile numbers
        is_privileged = role in ('local', 'admin', 'manager', 'owner', 'superadmin')
        res = []
        for m in page_msgs:
            item = copy.deepcopy(m)
            item['maskedPhone'] = item.get('maskedPhone') or self.mask_phone(item.get('phone'))
            if not is_privileged:
                item['phone'] = item['maskedPhone']
                item.pop('apiSecret', None)
                item.pop('authToken', None)
            res.append(item)
            
        return {
            'total': total_count,
            'page': page,
            'limit': limit,
            'totalPages': (total_count + limit - 1) // limit if limit > 0 else 1,
            'messages': res
        }

    def get_wa_stats(self, filters=None, hotel_id=None):
        filters = filters or {}
        with self.lock:
            d = self.data() or {}
        msgs = list(d.get('waMessages') or [])
        
        if hotel_id:
            msgs = [m for m in msgs if m.get('hotelId') == hotel_id]
            
        # Date range filter
        date_range = filters.get('dateRange', 'all')
        now_ts = int(time.time() * 1000)
        DAY = 86400 * 1000
        start_ts = 0
        end_ts = now_ts + DAY
        if date_range == 'today':
            t = time.localtime(time.time())
            start_ts = int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)
        elif date_range == 'yesterday':
            t = time.localtime(time.time() - 86400)
            midnight = int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)
            start_ts = midnight
            end_ts = midnight + DAY
        elif date_range == '7days':
            start_ts = now_ts - 7 * DAY
        elif date_range == 'month':
            t = time.localtime(time.time())
            start_ts = int(time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, -1)) * 1000)
        elif date_range == 'custom':
            if filters.get('startDate'):
                try: start_ts = int(filters['startDate'])
                except Exception: pass
            if filters.get('endDate'):
                try: end_ts = int(filters['endDate'])
                except Exception: pass
                
        if start_ts > 0:
            msgs = [m for m in msgs if (m.get('requestedAt') or 0) >= start_ts]
        if end_ts < now_ts + DAY:
            msgs = [m for m in msgs if (m.get('requestedAt') or 0) <= end_ts]
            
        if filters.get('provider') and filters['provider'] != 'all':
            msgs = [m for m in msgs if m.get('provider') == filters['provider']]
            
        total_requests = len(msgs)
        submitted = 0
        sent = 0
        delivered = 0
        read = 0
        failed = 0
        pending = 0
        unknown = 0
        skipped = 0
        cancelled = 0
        total_attempts = 0
        
        # Mutually exclusive counts based on last-known current status
        for m in msgs:
            st = (m.get('status') or 'UNKNOWN').upper()
            total_attempts += int(m.get('attemptCount') or 1)
            if st == 'SUBMITTED':
                submitted += 1
            elif st == 'SENT':
                sent += 1
            elif st == 'DELIVERED':
                delivered += 1
            elif st == 'READ':
                read += 1
            elif st == 'FAILED':
                failed += 1
            elif st in ('QUEUED', 'PROCESSING'):
                pending += 1
            elif st == 'UNKNOWN':
                unknown += 1
            elif st == 'SKIPPED':
                skipped += 1
            elif st == 'CANCELLED':
                cancelled += 1
            else:
                unknown += 1
                
        # Denominator excludes cancelled and skipped before dispatch
        effective_dispatched = total_requests - skipped - cancelled
        delivery_rate = round(((delivered + read) / effective_dispatched * 100), 1) if effective_dispatched > 0 else 0.0
        failure_rate = round((failed / effective_dispatched * 100), 1) if effective_dispatched > 0 else 0.0
        
        return {
            'totalRequests': total_requests,
            'submitted': submitted,
            'sent': sent,
            'delivered': delivered,
            'read': read,
            'confirmedDelivered': delivered + read,
            'failed': failed,
            'pending': pending,
            'unknown': unknown,
            'skipped': skipped,
            'cancelled': cancelled,
            'deliveryRate': delivery_rate,
            'failureRate': failure_rate,
            'totalAttempts': total_attempts
        }

    def record_wa_message(self, msg_dict):
        with self.lock:
            d = self.data() or {}
            msgs = d.setdefault('waMessages', [])
            
            VALID_STATUSES = {'QUEUED', 'PROCESSING', 'SUBMITTED', 'SENT', 'DELIVERED', 'READ', 'FAILED', 'UNKNOWN', 'SKIPPED', 'CANCELLED'}
            target = None
            msg_id = msg_dict.get('id')
            p_msg_id = msg_dict.get('providerMsgId')
            h_id = msg_dict.get('hotelId') or (d.get('settings') or {}).get('installId') or 'default'
            idem_key = msg_dict.get('idemKey') or (f"wa_bill_{h_id}_{msg_dict.get('billId')}" if msg_dict.get('billId') else None)
            
            for m in msgs:
                if msg_id and m.get('id') == msg_id:
                    target = m
                    break
                if p_msg_id and m.get('providerMsgId') == p_msg_id:
                    target = m
                    break
                if idem_key and m.get('idemKey') == idem_key:
                    target = m
                    break
                    
            now = int(time.time() * 1000)
            
            if not target:
                uid = msg_id or ('wa_' + str(now) + '_' + secrets.token_hex(4))
                phone = str(msg_dict.get('phone') or '')
                st_raw = (msg_dict.get('status') or 'QUEUED').upper()
                init_st = st_raw if st_raw in VALID_STATUSES else 'UNKNOWN'
                
                new_msg = {
                    'id': uid,
                    'hotelId': h_id,
                    'billId': msg_dict.get('billId'),
                    'billNo': msg_dict.get('billNo'),
                    'customerName': msg_dict.get('customerName') or 'Customer',
                    'phone': phone,
                    'maskedPhone': self.mask_phone(phone),
                    'msgType': msg_dict.get('msgType') or 'receipt',
                    'provider': msg_dict.get('provider') or 'meta',
                    'providerMsgId': p_msg_id or '',
                    'templateName': msg_dict.get('templateName') or 'setu_receipt_v1',
                    'status': init_st,
                    'consentRef': msg_dict.get('consentRef') or 'explicit_opt_in',
                    'requestedAt': msg_dict.get('requestedAt') or now,
                    'submittedAt': msg_dict.get('submittedAt') or (now if init_st == 'SUBMITTED' else None),
                    'sentAt': msg_dict.get('sentAt') or (now if init_st == 'SENT' else None),
                    'deliveredAt': msg_dict.get('deliveredAt') or (now if init_st == 'DELIVERED' else None),
                    'readAt': msg_dict.get('readAt') or (now if init_st == 'READ' else None),
                    'failedAt': msg_dict.get('failedAt') or (now if init_st == 'FAILED' else None),
                    'errorCode': msg_dict.get('errorCode') or '',
                    'errorReason': msg_dict.get('errorReason') or '',
                    'idemKey': idem_key or ('wa_' + str(uid) + '_' + str(now)),
                    'attemptCount': int(msg_dict.get('attemptCount') or 1),
                    'retryEligible': bool(msg_dict.get('retryEligible', init_st in ('FAILED', 'UNKNOWN'))),
                    'staff': msg_dict.get('staff') or 'system',
                    'events': list(msg_dict.get('events') or [{
                        'status': init_st,
                        'at': now,
                        'provider': msg_dict.get('provider') or 'meta',
                        'providerMsgId': p_msg_id or '',
                        'note': msg_dict.get('note') or 'Message queued for dispatch'
                    }]),
                    'attempts': list(msg_dict.get('attempts') or [{
                        'attemptNo': 1,
                        'requestedAt': now,
                        'provider': msg_dict.get('provider') or 'meta',
                        'status': init_st,
                        'providerMsgId': p_msg_id or '',
                        'error': msg_dict.get('errorReason') or ''
                    }])
                }
                msgs.append(new_msg)
                self.write(d)
                return new_msg
            else:
                cur_status = target.get('status', 'QUEUED').upper()
                new_st_raw = (msg_dict.get('status') or cur_status).upper()
                new_status = new_st_raw if new_st_raw in VALID_STATUSES else 'UNKNOWN'
                
                cur_rank = self.STATUS_RANK.get(cur_status, 0)
                new_rank = self.STATUS_RANK.get(new_status, 0)
                
                allow_status_change = False
                if new_status == cur_status:
                    allow_status_change = False
                elif new_rank > cur_rank:
                    allow_status_change = True
                elif new_status in ('FAILED', 'UNKNOWN', 'CANCELLED', 'SKIPPED'):
                    if cur_status not in ('DELIVERED', 'READ'):
                        allow_status_change = True
                
                if allow_status_change:
                    target['status'] = new_status
                    if new_status == 'SUBMITTED' and not target.get('submittedAt'):
                        target['submittedAt'] = msg_dict.get('submittedAt') or now
                    elif new_status == 'SENT' and not target.get('sentAt'):
                        target['sentAt'] = msg_dict.get('sentAt') or now
                    elif new_status == 'DELIVERED' and not target.get('deliveredAt'):
                        target['deliveredAt'] = msg_dict.get('deliveredAt') or now
                    elif new_status == 'READ' and not target.get('readAt'):
                        target['readAt'] = msg_dict.get('readAt') or now
                    elif new_status == 'FAILED':
                        target['failedAt'] = msg_dict.get('failedAt') or now
                        target['retryEligible'] = bool(msg_dict.get('retryEligible', True))
                
                if p_msg_id and not target.get('providerMsgId'):
                    target['providerMsgId'] = p_msg_id
                if msg_dict.get('errorCode'):
                    target['errorCode'] = msg_dict['errorCode']
                if msg_dict.get('errorReason'):
                    target['errorReason'] = msg_dict['errorReason']
                    
                events = target.setdefault('events', [])
                event_entry = {
                    'status': new_status,
                    'at': msg_dict.get('eventAt') or now,
                    'provider': msg_dict.get('provider') or target.get('provider'),
                    'providerMsgId': p_msg_id or target.get('providerMsgId', ''),
                    'note': msg_dict.get('note') or f'Status updated to {new_status}',
                    'code': msg_dict.get('errorCode') or '',
                    'error': msg_dict.get('errorReason') or ''
                }
                
                is_duplicate_event = (
                    events and
                    events[-1].get('status') == new_status and
                    not msg_dict.get('note') and
                    not msg_dict.get('errorCode') and
                    not allow_status_change
                )
                if not is_duplicate_event:
                    events.append(event_entry)
                
                self.write(d)
                return target

    def retry_wa_message(self, msg_id, role, provider=None):
        if role not in ('local', 'admin', 'manager', 'owner', 'superadmin'):
            return 403, {'error': 'PERMISSION_DENIED', 'message': 'Only Managers/Owners can retry messages'}
            
        with self.lock:
            d = self.data() or {}
            msgs = d.setdefault('waMessages', [])
            target = next((m for m in msgs if m.get('id') == msg_id), None)
            
            if not target:
                return 404, {'error': 'NOT_FOUND', 'message': 'Message not found'}
                
            cur_status = (target.get('status') or '').upper()
            if cur_status == 'PROCESSING':
                return 409, {'error': 'Message is currently processing', 'code': 'CONCURRENT_RETRY', 'message': 'Message is currently processing'}
            if cur_status not in ('FAILED', 'UNKNOWN'):
                return 400, {
                    'error': 'NOT_RETRY_ELIGIBLE',
                    'message': f'Cannot retry message in {cur_status} status. Only FAILED or UNKNOWN messages are eligible.'
                }
                
            raw_phone = re.sub(r'\D', '', str(target.get('phone') or ''))
            if len(raw_phone) < 10:
                return 400, {'error': 'INVALID_PHONE', 'message': 'Cannot retry message with invalid phone number'}
                
            now = int(time.time() * 1000)
            target['attemptCount'] = int(target.get('attemptCount') or 1) + 1
            attempt_no = target['attemptCount']
            
            if provider:
                target['provider'] = provider
            chosen_provider = target.get('provider') or 'meta'
            
            target['status'] = 'QUEUED'
            target['errorCode'] = ''
            target['errorReason'] = ''
            target['retryEligible'] = False
            
            attempts = target.setdefault('attempts', [])
            attempts.append({
                'attemptNo': attempt_no,
                'requestedAt': now,
                'provider': chosen_provider,
                'status': 'QUEUED',
                'providerMsgId': '',
                'error': ''
            })
            
            events = target.setdefault('events', [])
            events.append({
                'status': 'QUEUED',
                'at': now,
                'provider': chosen_provider,
                'providerMsgId': '',
                'note': f'Retry attempt #{attempt_no} initiated by {role}',
                'code': '',
                'error': ''
            })
            
            self.write(d)
            return 200, {'ok': True, 'message': target}

    def cleanup_wa_messages(self, retention_days, role):
        if role not in ('local', 'admin', 'manager', 'owner', 'superadmin'):
            return 403, {'error': 'PERMISSION_DENIED', 'message': 'Manager permission required for retention cleanup'}
            
        retention_days = max(7, int(retention_days or 90))
        cutoff_ts = int(time.time() * 1000) - (retention_days * 86400 * 1000)
        
        with self.lock:
            d = self.data() or {}
            msgs = d.get('waMessages') or []
            kept = [m for m in msgs if (m.get('requestedAt') or 0) >= cutoff_ts]
            pruned_count = len(msgs) - len(kept)
            d['waMessages'] = kept
            self.write(d)
            
        return 200, {
            'ok': True,
            'retentionDays': retention_days,
            'pruned': pruned_count,
            'remaining': len(kept)
        }



# ---------------- Cloud Sync (Setu Cloud on Cloudflare) ----------------
# This PC stays the master. A background thread mirrors the database to the hotel's
# Setu Cloud Worker (cloud/ folder) so the owner / captains can use Setu over the internet.
# Changes on both sides are joined with the same 3-way merge the app uses (merge3 in
# hotel_erp.html), ported below. Keep the two in step.
MISSING = object()


def _js(x):
    return json.dumps(x, ensure_ascii=False, separators=(',', ':'))


def jeq(a, b):
    if a is MISSING or b is MISSING:
        return a is b
    return a is b or _js(a) == _js(b)


def _scalar_key(x):
    return (type(x).__name__, x)


def merge_node(b, m, t, depth):
    if jeq(m, b):
        return t           # only the other side changed it
    if jeq(t, b):
        return m           # only this side changed it
    if jeq(m, t):
        return m
    if isinstance(m, list) and isinstance(t, list):
        both = m + t
        if all(isinstance(x, dict) and x.get('id') for x in both):
            return merge_by_id(b if isinstance(b, list) else [], m, t, depth)
        if all(x is not None and not isinstance(x, (dict, list)) for x in both):
            return list({_scalar_key(x): x for x in both}.values())   # e.g. usedKeys
        return m
    if isinstance(m, dict) and isinstance(t, dict) and depth < 6:
        bo = b if isinstance(b, dict) else {}
        out = {}
        for k in dict.fromkeys(list(m) + list(t) + list(bo)):
            in_m, in_t, in_b = k in m, k in t, k in bo
            if not in_m and not in_t:
                continue
            if not in_m:
                if in_b and jeq(t[k], bo[k]):
                    continue    # I deleted it
                out[k] = t[k]
                continue
            if not in_t:
                if in_b and jeq(m[k], bo[k]):
                    continue    # they deleted it
                out[k] = m[k]
                continue
            out[k] = merge_node(bo[k] if in_b else MISSING, m[k], t[k], depth + 1)
        return out
    return m               # both changed one value: "mine" wins


def merge_by_id(b, m, t, depth):
    def by_id(lst):
        return {x.get('id') if isinstance(x, dict) else None: x for x in lst}
    bm, mm, tm = by_id(b), by_id(m), by_id(t)
    out, seen = [], set()
    for x in t + m:
        if x['id'] in seen:
            continue
        seen.add(x['id'])
        bx, mx, tx = bm.get(x['id']), mm.get(x['id']), tm.get(x['id'])
        if mx is not None and tx is not None:
            v = merge_node(bx if bx is not None else MISSING, mx, tx, depth + 1)
        elif mx is not None:
            v = None if bx is not None and jeq(mx, bx) else mx   # they deleted it
        else:
            v = None if bx is not None and jeq(tx, bx) else tx   # I deleted it
        if v is not None:
            out.append(v)
    return out


def _num(x):
    # JavaScript "+x || 0"
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, (int, float)):
        return x if x == x else 0
    try:
        s = str(x).strip()
        v = float(s) if s else 0
        return int(v) if float(v).is_integer() else v
    except Exception:
        return 0


def merge3(base, mine, theirs):
    out = copy.deepcopy(merge_node(base if base is not None else {}, mine, theirs, 0))
    ms, ts = mine.get('seq') or {}, theirs.get('seq') or {}
    seq = {**ts, **ms}
    # Running numbers must never go backwards
    for k in ('bill', 'kot'):
        seq[k] = max(_num(ms.get(k)), _num(ts.get(k)))
    # Tokens restart daily, so the newer day wins before comparing numbers
    md, td = str(ms.get('tokenDate') or ''), str(ts.get('tokenDate') or '')
    seq['tokenDate'] = md if md > td else td
    if md == td:
        seq['token'] = max(_num(ms.get('token')), _num(ts.get('token')))
    else:
        seq['token'] = _num(ms.get('token')) if md > td else _num(ts.get('token'))
    out['seq'] = seq
    # S01 Idempotency deduplication: ensure no duplicate bill records share an idemKey
    theirs_bills = [x for x in (theirs.get('bills') or []) if isinstance(x, dict)]
    their_idem_map = {x.get('idemKey'): x for x in theirs_bills if x.get('idemKey')}
    deduped_bills = []
    seen_idem = set()
    for b in out.get('bills') or []:
        if not isinstance(b, dict):
            continue
        ik = b.get('idemKey')
        if ik:
            if ik in seen_idem:
                continue
            seen_idem.add(ik)
            # Only a true duplicate (the same sale under another id) takes their copy; the same bill keeps the
            # record-level merge, or a cancellation / edit would be undone by every conflict (same as the HTML)
            tb = their_idem_map.get(ik)
            if tb is not None and tb.get('id') != b.get('id'):
                b = tb
        deduped_bills.append(b)
    out['bills'] = deduped_bills

    # Both sides may have used the same bill / KOT number: new ones from "mine" get fresh numbers
    for lst, key in (('bills', 'bill'), ('kots', 'kot')):
        theirs_l = [x for x in theirs.get(lst) or [] if isinstance(x, dict)]
        base_l = [x for x in (base or {}).get(lst) or [] if isinstance(x, dict)]
        their_ids = {x.get('id') for x in theirs_l}
        base_ids = {x.get('id') for x in base_l}
        taken = {x.get('no') for x in theirs_l}
        for x in out.get(lst) or []:
            if not isinstance(x, dict):
                continue
            if x.get('id') not in their_ids and x.get('id') not in base_ids and x.get('no') in taken:
                seq[key] += 1
                x['no'] = seq[key]
            taken.add(x.get('no'))
    return out


def _urlopen(req, timeout):
    # Old or un-updated Windows may lack the root certificate the cloud uses: retry with the bundled certifi list
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        if not isinstance(getattr(e, 'reason', None), ssl.SSLError):
            raise
        try:
            import certifi
        except ImportError:
            raise e
        return urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context(cafile=certifi.where()))


def _net_reason(e):
    # Plain-language reason a cloud call failed, shown in Settings so the owner (or vendor) can fix it
    why = getattr(e, 'reason', e)
    text = str(why)
    if isinstance(why, ssl.SSLError) or 'CERTIFICATE' in text.upper():
        return ('ssl', 'The computer date / time is wrong or Windows is old (SSL). Correct the date-time, then press Connect Now.')
    if isinstance(why, socket.gaierror) or 'getaddrinfo' in text:
        return ('dns', 'Could not find the cloud address (DNS). The internet is off, or this internet / Wi-Fi is blocking the cloud. '
                       'Try a mobile hotspot.')
    if isinstance(why, (socket.timeout, TimeoutError)) or 'timed out' in text:
        return ('timeout', 'The cloud did not answer in time. The internet is slow or a firewall / antivirus is blocking it.')
    if isinstance(why, (ConnectionRefusedError, ConnectionResetError)) or 'refused' in text or 'reset' in text:
        return ('blocked', 'The connection was stopped. An antivirus / firewall / proxy is blocking Setu. Try a mobile hotspot.')
    return ('offline', f'No internet ({text[:120]})')


def _write_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _key_kind(key):
    # Byte 1 of a SETU key: 1 days, 2 minutes, 3 lifetime, 4 password reset (not a licence), 5 date set by the vendor,
    # 6 vendor Master Key (first install, any PC)
    B32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
    try:
        bits = ''.join(f'{B32.index(c):05b}' for c in key[4:8])
        return int(bits[8:16], 2)
    except ValueError:
        return 0


class CloudBusy(Exception):
    pass


HIST_KEYS = ('bills',)                 # read from the tables when needed, never kept in server memory
RECORD_KINDS = ('spec', 'extlist')     # lists saved record by record
MAP_KINDS = ('maptable', 'kvmap', 'att')
WHOLE_ONLY = ('staff', 'secure')
FIN_FIELDS = ('total', 'sub', 'disc', 'tax', 'mode', 'pays', 'items', 'cancelled', 'amount', 'qty', 'no')   # money / stock content       # staff PIN hashes are keyed by list position: always the whole list
MAX_OPS_RECORDS = 20000


def _seq_merge(mine, cur):
    """Running numbers never go back (the rule of merge3): bill / KOT / credit note = the larger, tokens by day."""
    mine = mine if isinstance(mine, dict) else {}
    cur = cur if isinstance(cur, dict) else {}
    seq = {**cur, **mine}
    for k in ('bill', 'kot', 'cn'):
        if k in mine or k in cur:
            seq[k] = max(_num(mine.get(k)), _num(cur.get(k)))
    md, td = str(mine.get('tokenDate') or ''), str(cur.get('tokenDate') or '')
    if 'tokenDate' in mine or 'tokenDate' in cur:
        seq['tokenDate'] = md if md > td else td
        seq['token'] = max(_num(mine.get('token')), _num(cur.get('token'))) if md == td else (_num(mine.get('token')) if md > td else _num(cur.get('token')))
    return seq


def _bill_part(b):
    """What one bill adds to the history totals (same rules as SqliteDoc.history_totals)."""
    if not isinstance(b, dict):
        return None
    tot = b.get('total')
    sale = SQ.MONEY(tot) if isinstance(tot, (int, float)) and not isinstance(tot, bool) and not b.get('cancelled') else (0 if not b.get('cancelled') else None)
    out = {'date': str(b.get('date') or ''), 'stock': {}, 'p': None, 'sale': sale}
    if b.get('mv'):
        for u in b.get('used') or []:
            if isinstance(u, dict):
                sid = str(u.get('sid')) if u.get('sid') is not None else ''
                q = float(u.get('qty') or 0)
                out['stock'][sid] = out['stock'].get(sid, 0) - q + (q if b.get('cancelled') else 0)
    if b.get('cancelled'):
        return out
    p = SQ.norm_ph(b.get('phone'))
    if len(p) != 10:
        return out
    pts = SQ.jsnum(b.get('ptsEarned')) - SQ.jsnum(b.get('ptsUsed'))
    agg = b.get('channel') in ('Zomato', 'Swiggy')
    fav = {}
    if not agg:
        for it in b.get('items') or []:
            if isinstance(it, dict) and it.get('name'):
                fav[it['name']] = fav.get(it['name'], 0) + (SQ.jsnum(it.get('qty')) or 1)
    out['p'] = {'phone': p, 'pa': pts, 'ws': SQ.jsnum(b.get('total')) if b.get('mode') == 'Wallet' else 0,
                'agg': agg, 'pts': 0 if agg else pts, 'spend': 0 if agg else SQ.jsnum(b.get('total')), 'name': b.get('cust') or '', 'fav': fav}
    return out


class SqliteSetuStore(SetuStore):
    """SetuStore on the local SQLite database (Phase 2b).

    * The server keeps in memory only the working data (settings, menu, stock, vouchers, KOTs, audit, maps, ...),
      never the bill history. Bills are read from the tables: a window of recent days for devices
      (GET /api/db), any older range on request (/api/q/bill-range), totals of older bills (/api/q/hist).
    * Devices save with POST /api/ops: only the records, map entries or small values that changed, in one
      transaction, through the same security rules as before (credentials, cashier limits, confirmed records,
      bill numbers). Other devices fetch only what changed (GET /api/changes).
    * The whole-document upload (POST /api/db) is accepted only for a restore and the first upload.
    Cloud full-document sync is switched off in this mode (sync_blocked) until Phase 3 incremental sync.
    """

    sync_blocked = 'Cloud sync is paused on this PC: the local SQLite database needs incremental cloud sync (Phase 3).'
    engine = 'sqlite'

    def __init__(self, data_dir):
        self.sdb = SQ.SqliteDoc(os.path.join(data_dir, SQ.DB_FILE))
        self._ws = None
        self._idx = {}
        self._raw_cache = (None, 'null')
        self._enc_lock = threading.RLock()
        self._hist = {}
        self._hist_rev = 0
        self._hist_lock = threading.Lock()
        self.stats = {'opsSaves': 0, 'opsRecords': 0, 'legacyFullSaves': 0, 'restores': 0, 'windowLoads': 0, 'fullExports': 0, 'changeFeeds': 0, 'changeReloads': 0}
        self.dispatcher = None
        self.phase3_sync_enabled = False
        super().__init__(data_dir)
        self.sdb.start_checkpointer()
        threading.Thread(target=self._warm_hist, daemon=True).start()

    # ---------- memory: the working data only ----------
    @property
    def raw(self):
        if self._ws is None:
            return 'null'
        with self._enc_lock:
            if self._raw_cache[0] != self.version:
                self._raw_cache = (self.version, json.dumps(self._ws, ensure_ascii=False))
            return self._raw_cache[1]

    @raw.setter
    def raw(self, value):
        pass

    def _load(self):
        self._ws = self.sdb.export_except(HIST_KEYS)
        self._idx = {}
        self.version = int(self.sdb.meta('doc_version') or 0)
        self.saved_at = int(self.sdb.meta('saved_at') or 0)
        self.migrate_wa_history(self._ws)

    def data(self):
        """The working data (no bill history). Server code that changes it saves with write(), key by key."""
        return json.loads(self.raw)

    def hotel_id(self):
        d = self._ws or {}
        return str((d.get('settings') or {}).get('hotelId') or (d.get('auth') or {}).get('hotelId') or 'default').strip()

    def check_pin(self, pin):
        return SEC.check_pin(self._ws or {}, pin)

    def has_users_or_pins(self):
        return SEC.has_credentials(self._ws or {})

    def public_raw(self):
        with self._enc_lock:
            if self._pub[0] != self.version:
                self._pub = (self.version, json.dumps(SEC.public_view(self._ws or {}), ensure_ascii=False))
            return self._pub[1]

    def _index(self, k):
        """id -> position in a working list; kept up to date by each save (rebuilt only if the list was replaced)."""
        lst = self._ws.get(k)
        ix = self._idx.get(k)
        if ix is None or ix[0] is not lst or len(ix[1]) > len(lst):
            ix = (lst, {x.get('id'): i for i, x in enumerate(lst) if isinstance(x, dict)})
            self._idx[k] = ix
        return ix[1]

    def _kot_numbers(self):
        """KOT number -> id of the KOTs kept in memory (cached until the KOTs change)."""
        if getattr(self, '_kotno', None) is None or self._kotno[0] is not self._ws.get('kots'):
            self._kotno = (self._ws.get('kots'), {x.get('no'): x.get('id') for x in self._ws.get('kots') or [] if isinstance(x, dict)})
        return dict(self._kotno[1])

    def _ws_record(self, k, rid):
        lst = self._ws.get(k)
        if not isinstance(lst, list):
            return None
        i = self._index(k).get(rid)
        return lst[i] if i is not None else None

    # ---------- history window and totals ----------
    def hist_days(self):
        try:
            return max(7, min(400, int((self._ws.get('settings') or {}).get('histDays') or 35)))
        except (TypeError, ValueError):
            return 35

    def window_from(self, days=None, today=None):
        """First day of the recent-bills window. `today` = the device's date (its screens use its own clock)."""
        days = days or self.hist_days()
        base = time.time()
        if today:
            try:
                base = time.mktime(time.strptime(today, '%Y-%m-%d')) + 43200
            except ValueError:
                pass
        return time.strftime('%Y-%m-%d', time.localtime(base - (days - 1) * 86400))

    def _warm_hist(self):
        try:
            self.hist(self.window_from())
        except Exception as e:
            self.log(f'history totals not prepared: {e!r}')

    def hist(self, frm):
        """Totals of the bills before `frm` (computed once per day, then kept up to date by every save)."""
        with self._hist_lock:
            h = self._hist.get(frm)
            if h is not None:
                return h
        for _ in range(3):
            v0 = self.version
            h = self.sdb.history_totals(frm)
            if self.version == v0:
                break
            # Saves during the count: if one touched an older bill, count again
            with self.sdb.reader() as c:
                ids = [r[0] for r in c.execute("SELECT DISTINCT rid FROM change_log WHERE k = 'bills' AND version > ?", (v0,))]
                old = any(r[0] < frm for r in c.execute(f'SELECT date FROM bills WHERE id IN ({",".join("?" * len(ids))})', ids)) if ids else False
            if not old:
                break
        with self._hist_lock:
            for k in sorted(x for x in self._hist if x != frm)[:-2]:
                self._hist.pop(k, None)   # at most 3 windows kept (the date moves once a day; devices' clocks differ)
            self._hist.setdefault(frm, h)
            return self._hist[frm]

    def _hist_update(self, old, new):
        """A saved bill older than a window changes the totals of that window: subtract its old part, add the new."""
        with self._hist_lock:
            if not self._hist:
                return
            for frm, h in self._hist.items():
                phones = set()
                for part, sign in ((_bill_part(old), -1), (_bill_part(new), 1)):
                    if not part or not part['date'] or part['date'] >= frm:
                        continue
                    for sid, q in part['stock'].items():
                        h['stock'][sid] = h['stock'].get(sid, 0) + sign * q
                    if part['sale'] is not None:
                        dd = h.setdefault('days', {}).setdefault(part['date'], [0, 0])
                        dd[0] += sign
                        dd[1] += sign * part['sale']
                        if dd[0] <= 0:
                            h['days'].pop(part['date'], None)
                    if part['p']:
                        phones.add(part['p']['phone'])
                was = bool(old) and str(old.get('date') or '') < frm
                now_in = bool(new) and str(new.get('date') or '') < frm
                h['bills'] += int(now_in) - int(was)
                if phones:
                    # First / last visit and the name cannot be undone by subtraction: count these customers again
                    fresh = self.sdb.cust_totals(frm, phones)
                    for p in phones:
                        if p in fresh:
                            h['cust'][p] = fresh[p]
                        else:
                            h['cust'].pop(p, None)
            self._hist_rev += 1

    # ---------- what a device loads ----------
    def db_payload(self, frm=None, full=False):
        """JSON for GET /api/db: the working data (public view) with the bills of the window, or every bill."""
        frm = frm or self.window_from()
        # The working data as JSON text made under the lock, with its version: a save that lands meanwhile can
        # never mix into this copy (the lists are changed in place after each commit)
        with self._enc_lock:
            pub_text = self.public_raw()
            version, saved_at = self.version, self.saved_at
        bills = self.sdb.export_window('0000-00-00' if full else frm)   # own read connection: billing is not paused
        body_bills = json.dumps(bills, ensure_ascii=False)
        bills = None
        pub_text = pub_text.strip()
        data_text = ('{"bills": ' + body_bills + '}') if pub_text in ('{}', 'null', '') else (pub_text[:-1] + ', "bills": ' + body_bills + '}')
        if full:
            self.stats['fullExports'] += 1
            return ('{"version": %d, "savedAt": %d, "data": %s}' % (version, saved_at, data_text)).encode('utf-8')
        self.stats['windowLoads'] += 1
        h = self.hist(frm)
        meta = {'engine': 'sqlite', 'win': {'from': frm, 'days': self.hist_days(), 'older': h['bills']}, 'histRev': self._hist_rev,
                'kinds': {k: v for k, v in self.sdb.kinds().items() if k != 'secure'}, 'hist': h}
        return ('{"version": %d, "savedAt": %d, "meta": %s, "data": %s}' % (version, saved_at, json.dumps(meta, ensure_ascii=False), data_text)).encode('utf-8')

    def bill_count(self):
        with self.sdb.reader() as c:
            return c.execute('SELECT COUNT(*) FROM bills').fetchone()[0]

    def write_full_json(self, f, public=False):
        """The whole data (every bill) as a backup file, written in parts: memory stays flat at any size.
        public=True: without credentials (what a device may download)."""
        with self._enc_lock:
            ws = copy.deepcopy(SEC.public_view(self._ws or {}) if public else self._ws or {})
            version = self.version
        keys = self.sdb.doc_keys()
        f.write('{"version": %d, "savedAt": %d, "data": {' % (version, int(time.time() * 1000)))
        first = True
        for k in keys + [k for k in ws if k not in keys]:
            if k not in ws and k not in HIST_KEYS:
                continue
            f.write(('' if first else ', ') + json.dumps(k) + ': ')
            first = False
            if k == 'bills':
                f.write('[')
                n = 0
                for part in self.sdb.iter_bills(5000):
                    for b in part:
                        f.write((', ' if n else '') + json.dumps(b, ensure_ascii=False))
                        n += 1
                f.write(']')
            else:
                f.write(json.dumps(ws[k], ensure_ascii=False))
        f.write('}}')

    # ---------- server-side writes (WhatsApp records, licence, restore, ...) ----------
    def write(self, data_obj, outbox=('doc', None)):
        """Save what differs from the working data, key by key. Keys not given are kept (never deleted here).
        A data object WITH bills is a whole replacement (restore / first upload)."""
        if 'bills' in data_obj:
            return self.replace_all(data_obj)
        version, saved_at = self.version + 1, int(time.time() * 1000)
        touched = []
        with self.sdb.tx() as c:
            for k, v in data_obj.items():
                if k in self._ws and jeq(self._ws[k], v):
                    continue
                kind = SQ.SqliteDoc.kind_of(k, v)
                self.sdb.set_value(c, k, kind, v, self._ws.get(k))
                self.sdb.log_change(c, version, k, '')
                touched.append(k)
            if not touched:
                return
            self.sdb.set_version(c, version, saved_at)
            hotel_id = self.sdb.meta('hotel_id') or (self._ws.get('settings') or {}).get('hotelCode') or 'UNKNOWN'
            changed_values = {k: data_obj[k] for k in touched}
            envelope = SQ.make_sync_envelope(
                op_id=outbox[1] or f"srv_{version}_{secrets.token_hex(6)}",
                hotel_id=hotel_id,
                device_id='counter_server',
                doc_version=version,
                timestamp=saved_at,
                event_type=outbox[0] or 'write',
                actor={'role': 'server', 'elevated': True},
                writes_whole=changed_values
            )
            SQ.SqliteDoc.append_outbox(c, outbox[0], outbox[1] or envelope['op_id'], version, envelope, saved_at)
        with self._enc_lock:
            for k in touched:
                self._ws[k] = data_obj[k]
            self.version, self.saved_at = version, saved_at
        self._after_write()

    def get_pending_outbox(self, limit=100, include_legacy=True):
        with self.sdb.rlock():
            return self.sdb.get_pending_outbox(self.sdb.con(), limit=limit, include_legacy=include_legacy)

    def ack_outbox(self, confirmed_keys, now=None):
        with self.sdb.tx() as c:
            return self.sdb.ack_outbox(c, confirmed_keys, now=now)

    def record_conflict(self, k, rid, reason, kept=None, other=None, device=None, now=None):
        with self.sdb.tx() as c:
            self.sdb.record_conflict(c, k, rid, reason, kept=kept, other=other, device=device, now=now)

    def _reload_after_inbound(self):
        """Refresh LAN-visible data after an inbound SQLite commit.

        Caller must hold self.lock (same lock ordering as apply_ops).
        Never append the inbound transaction to the outbound cloud queue:
        doing so would create a QR echo loop.
        """
        fresh = self.sdb.export_except(HIST_KEYS)
        version = int(self.sdb.meta('doc_version') or 0)
        saved_at = int(self.sdb.meta('saved_at') or 0)
        with self._enc_lock:
            self._ws = fresh
            self._idx = {}
            self._kotno = None
            self._raw_cache = (None, 'null')
            self._pub = (None, 'null')
            self.version = version
            self.saved_at = saved_at
        self._after_write(keep_maxno=True)

    def start_cloud_sync(self, url, hotel, key, enabled=False, batch_size=50, poll_interval=5.0):
        if getattr(self, 'dispatcher', None):
            self.dispatcher.stop()
        self.dispatcher = SQ.OutboxSyncDispatcher(
            store=self, url=url, hotel=hotel, key=key, enabled=enabled,
            batch_size=batch_size, poll_interval=poll_interval
        )
        self.dispatcher.start()
        return self.dispatcher

    def stop_cloud_sync(self, timeout=5.0):
        if getattr(self, 'dispatcher', None):
            self.dispatcher.stop(timeout=timeout)

    def _after_write(self, keep_maxno=False):
        super()._after_write(keep_maxno=keep_maxno)
        if getattr(self, 'dispatcher', None) and getattr(self.dispatcher, '_running', False):
            self.dispatcher.wake()

    def replace_all(self, doc):
        """Whole replacement in one transaction (restore from a backup, first upload): every key rewritten."""
        version, saved_at = self.version + 1, int(time.time() * 1000)
        with self.sdb.tx() as c:
            for k, kind in self.sdb.kinds().items():
                self.sdb._clear_key(c, k, kind)
            c.execute("DELETE FROM meta WHERE k IN ('doc_keys', 'doc_kinds')")
            self.sdb.commit_document(c, {}, doc, version, saved_at)
            self.sdb.log_change(c, version, '*', '')
            hotel_id = self.sdb.meta('hotel_id') or (doc.get('settings') or {}).get('hotelCode') or 'UNKNOWN'
            envelope = SQ.make_sync_envelope(
                op_id=f"restore_{version}_{secrets.token_hex(6)}",
                hotel_id=hotel_id,
                device_id='counter_server',
                doc_version=version,
                timestamp=saved_at,
                event_type='restore',
                actor={'role': 'manager', 'elevated': True},
                writes_whole={k: v for k, v in doc.items() if k not in HIST_KEYS}
            )
            SQ.SqliteDoc.append_outbox(c, 'restore', envelope['op_id'], version, envelope, saved_at)
        with self._enc_lock:
            self._ws = {k: v for k, v in doc.items() if k not in HIST_KEYS}
            self._idx = {}
            self.version, self.saved_at = version, saved_at
        with self._hist_lock:
            self._hist = {}
            self._hist_rev += 1
        self.stats['restores'] += 1
        self._after_write()

    def _after_write(self, keep_maxno=False):
        if not keep_maxno:
            self._maxno = None
        if self.on_write:
            self.on_write()
        self._backup_soon()

    BACKUP_IDLE = 45          # seconds without a save before the daily backup starts
    BACKUP_MAX_WAIT = 1800    # ... but never later than this after it became due

    def _backup_soon(self):
        """One verified online backup per day, at most every 10 minutes, taken when the counter is quiet.
        A backup reads the whole file in one snapshot (about 70 s at 365,000 bills); while it runs the write log
        cannot be folded back, and the checkpoint after it stalled saves for about a second (measured). So it waits
        for BACKUP_IDLE seconds without a save, at most BACKUP_MAX_WAIT, then shrinks the write log."""
        self._last_save = time.time()
        if os.environ.get('SETU_BACKUP') == 'off':
            return
        if getattr(self, '_backup_due', 0) or time.time() - getattr(self, '_last_copy', 0) < 600 or getattr(self, '_backing_up', False):
            return
        self._backup_due = time.time()
        if getattr(self, '_backup_thread', None) is None:
            self._backup_thread = threading.Thread(target=self._backup_loop, daemon=True)
            self._backup_thread.start()

    def _backup_loop(self):
        while True:
            time.sleep(5)
            due = getattr(self, '_backup_due', 0)
            if not due:
                continue
            now = time.time()
            if now - self._last_save < self.BACKUP_IDLE and now - due < self.BACKUP_MAX_WAIT:
                continue
            self._backup_due, self._backing_up, self._last_copy = 0, True, now
            try:
                os.makedirs(self.backup_dir, exist_ok=True)
                self.sdb.backup_to(os.path.join(self.backup_dir, 'setu-' + time.strftime('%Y-%m-%d') + '.sqlite.gz'), self.version, KEEP_BACKUPS)
                self.backup_stats = {'at': int(time.time() * 1000), 'waitedSeconds': round(now - due), 'tookSeconds': round(time.time() - now, 1)}
                with self.sdb.wlock:
                    self.sdb.con().execute('PRAGMA wal_checkpoint(TRUNCATE)')
            except Exception as e:
                self.log(f'SQLITE BACKUP FAILED: {e!r}')
            finally:
                self._backing_up = False

    # ---------- incremental saves from devices (POST /api/ops) ----------
    def _cur(self, c, k, kind, ids):
        """Stored records of a list by id: bills from the tables, the rest from memory."""
        if k in HIST_KEYS:
            return self.sdb.get_records(c, k, ids)
        out = {}
        for rid in ids:
            r = self._ws_record(k, rid)
            if r is not None:
                out[rid] = r
        return out

    def apply_ops(self, body, role, elev=False):
        """One device save: typed operations on records, map entries and small values, applied in ONE
        transaction after the same security rules as the whole-document save. Returns (status, answer).
        Caller holds self.lock."""
        ops = copy.deepcopy(body.get('ops'))   # never share objects with the caller (or with memory)
        opid = str(body.get('id') or '')[:120]
        try:
            bv = int(body.get('bv', -1))
        except (TypeError, ValueError):
            return 400, {'error': 'bad base version'}
        if not isinstance(ops, list) or not ops:
            return 400, {'error': 'ops required'}
        con = self.sdb.con()
        if opid:
            with self.sdb.rlock():
                done = con.execute("SELECT result FROM operation_idempotency WHERE key = ? AND op = 'ops'", (opid,)).fetchone()
            if done:
                out = json.loads(done[0] or '{}')
                out['repeat'] = True
                return 200, out
        kinds = self.sdb.kinds()
        rec, maps, whole = {}, {}, {}
        n_rec = 0
        conflicts = []     # (key, record id, reason, kept copy, other copy): stored, reported, never dropped silently
        for c_ in body.get('conflicts') or []:
            if isinstance(c_, dict) and isinstance(c_.get('k'), str):
                conflicts.append((c_['k'], str(c_.get('id') or ''), str(c_.get('reason') or 'differing copies on the device')[:200], c_.get('kept'), c_.get('other')))
        for op in ops:
            if not isinstance(op, dict) or not isinstance(op.get('k'), str) or not op['k'] or len(op['k']) > 60:
                return 400, {'error': 'bad op'}
            k = op['k']
            if k == 'secure':
                continue                      # credential hashes come only from the server
            if 'set' in op:
                if k in HIST_KEYS:
                    return 400, {'error': f'{k} are saved record by record'}
                whole[k] = (op['set'], op.get('prev', MISSING) if 'prev' in op else MISSING)
            elif 'up' in op or 'rm' in op:
                up, rm, prev = op.get('up') or [], op.get('rm') or [], op.get('prev') or {}
                if not isinstance(up, list) or not isinstance(rm, list) or not isinstance(prev, dict):
                    return 400, {'error': 'bad record op'}
                if k in WHOLE_ONLY:
                    return 400, {'error': f'{k} is saved as a whole'}
                if not all(isinstance(x, dict) and isinstance(x.get('id'), str) and x['id'] for x in up):
                    return 400, {'error': f'{k}: every record needs an id'}
                kind = kinds.get(k) or SQ.SqliteDoc.kind_of(k, up or [{'id': 'x'}])
                if kind not in RECORD_KINDS:
                    return 400, {'error': f'{k} is not a record list here ({kind})'}
                e = rec.setdefault(k, {'kind': kind, 'up': {}, 'rm': set(), 'prev': {}})
                for x in up:
                    first = e['up'].get(x['id'])
                    if first is not None:
                        # The same record twice in one save: identical = one copy; different = first kept, other recorded
                        if not jeq(first, x):
                            conflicts.append((k, x['id'], 'same id twice in one save, different content', first, x))
                        continue
                    e['up'][x['id']] = x
                    e['rm'].discard(x['id'])
                for i in rm:
                    e['rm'].add(str(i))
                    e['up'].pop(str(i), None)
                e['prev'].update({str(i): v for i, v in prev.items()})
                n_rec += len(up) + len(rm)
            elif 'mset' in op or 'mdel' in op:
                ms, md, mp = op.get('mset') or {}, op.get('mdel') or [], op.get('mprev') or {}
                if not isinstance(ms, dict) or not isinstance(md, list) or not isinstance(mp, dict):
                    return 400, {'error': 'bad map op'}
                kind = kinds.get(k) or SQ.SqliteDoc.kind_of(k, ms)
                if kind not in MAP_KINDS:
                    return 400, {'error': f'{k} is not a map here ({kind})'}
                e = maps.setdefault(k, {'kind': kind, 'set': {}, 'del': set(), 'prev': {}})
                for mk, v in ms.items():
                    e['set'][str(mk)] = v
                    e['del'].discard(str(mk))
                for mk in md:
                    e['del'].add(str(mk))
                    e['set'].pop(str(mk), None)
                e['prev'].update(mp)
            else:
                return 400, {'error': 'bad op'}
        orig_up = {k: copy.deepcopy(e['up']) for k, e in rec.items()}
        orig_touch = {k: list(e['up']) + sorted(e['rm']) for k, e in rec.items()}
        orig_map = {k: (copy.deepcopy(e['set']), set(e['del'])) for k, e in maps.items()}
        orig_whole = {k: copy.deepcopy(v[0]) for k, v in whole.items()}
        if n_rec > MAX_OPS_RECORDS:
            return 413, {'error': f'too many records in one save ({n_rec})'}
        admin = role in ('admin', 'local') or elev
        with self.sdb.rlock():
            last = lambda k, rid='': SQ.SqliteDoc.last_change(con, k, rid)   # noqa: E731
            # ---- 1. stored values, and three-way merge of what another device changed since this device's copy
            old_v, new_v, cur_rec = {}, {}, {}
            for k, e in rec.items():
                ids = list(e['up']) + list(e['rm'])
                cur = self._cur(con, k, e['kind'], ids)
                cur_rec[k] = cur
                old_v[k] = [copy.deepcopy(cur[i]) for i in ids if i in cur]
                lst = []
                for rid, mine in e['up'].items():
                    theirs = cur.get(rid)
                    if theirs is not None and rid in e['prev'] and last(k, rid) > bv:
                        mine = copy.deepcopy(merge_node(e['prev'][rid], mine, theirs, 1))
                    lst.append(mine)
                for rid in list(e['rm']):
                    theirs = cur.get(rid)
                    if theirs is not None and last(k, rid) > bv and not jeq(e['prev'].get(rid, MISSING), theirs):
                        e['rm'].discard(rid)          # another device changed it after this one read it: it stays
                        lst.append(copy.deepcopy(theirs))
                new_v[k] = lst
            cur_map = {}
            for k, e in maps.items():
                cm = self._ws.get(k) if isinstance(self._ws.get(k), dict) else {}
                cur_map[k] = cm
                for mk, mine in list(e['set'].items()):
                    if mk in cm and mk in e['prev'] and last(k, mk) > bv:
                        e['set'][mk] = copy.deepcopy(merge_node(e['prev'][mk], mine, cm[mk], 1))
                for mk in list(e['del']):
                    if mk in cm and last(k, mk) > bv and not jeq(e['prev'].get(mk, MISSING), cm[mk]):
                        e['del'].discard(mk)
            for k, (v, prev) in list(whole.items()):
                cur = self._ws.get(k, MISSING)
                if k == 'seq':
                    v = _seq_merge(v, cur if cur is not MISSING else {})
                elif cur is not MISSING and prev is not MISSING and last(k) > bv:
                    v = copy.deepcopy(merge_node(prev, v, cur, 0))
                whole[k] = (v, prev)
                if cur is not MISSING:
                    old_v[k] = copy.deepcopy(cur)
                new_v[k] = v
            seq_cur = copy.deepcopy(self._ws.get('seq') or {})
            old_v.setdefault('seq', copy.deepcopy(seq_cur))
            new_v.setdefault('seq', copy.deepcopy(seq_cur))
            # ---- 2. credentials: plain PINs become hashes (manager only); the stored hashes always stay
            cfg = {k: (new_v[k] if k in new_v else copy.deepcopy(self._ws[k])) for k in ('settings', 'auth', 'staff') if k in new_v or k in self._ws}
            SEC.absorb_secrets(cfg, {'secure': self._ws.get('secure')}, admin)
            for k in ('settings', 'auth', 'staff', 'secure'):
                if k in cfg and not jeq(cfg[k], self._ws.get(k, MISSING)):
                    new_v[k] = cfg[k]
                    old_v.setdefault(k, copy.deepcopy(self._ws.get(k)) if k in self._ws else None)
                    if old_v[k] is None:
                        del old_v[k]
            # ---- 3. cashier / captain / kitchen limits (settings, logins, licence, past records, numbers)
            given = set(new_v)
            if not admin and 'audit' in rec and len(self._ws.get('audit') or []) >= 19000:
                trimmed = rec['audit']['rm']
                old_v['audit'] = [x for x in old_v.get('audit', []) if x.get('id') not in trimmed]
            blocked = SEC.sanitize_write(role, old_v, new_v, elev)
            for k in list(new_v):
                if k not in given:
                    del new_v[k]                  # a key this save did not touch is never written
            if blocked:
                self.log(f'BLOCKED by role {role}: ' + ', '.join(blocked[:20]))
            # ---- 4. bills: split tenders, idempotency (also against bills already stored), numbers
            dup = {}
            if 'bills' in new_v:
                try:
                    self.clean_and_validate_bills(new_v, conflicts)
                except ValueError as ve:
                    return 400, {'error': str(ve)}
                keep = []
                for b in new_v['bills']:
                    if b.get('id') not in cur_rec['bills'] and b.get('idemKey'):
                        r = con.execute('SELECT id FROM bills WHERE idemKey = ? AND id <> ?', (b['idemKey'], b['id'])).fetchone()
                        if r:
                            stored = self.sdb.get_records(con, 'bills', [r[0]]).get(r[0])
                            dup[b['id']] = stored
                            # A retry of the same sale is fine; the same sale key with different money is a conflict
                            if stored and any(not jeq(stored.get(f, MISSING), b.get(f, MISSING)) for f in FIN_FIELDS if f != 'no'):
                                conflicts.append(('bills', b['id'], f'sale key {b["idemKey"]} already settled as bill #{stored.get("no")} with different amounts', stored, b))
                            continue
                    keep.append(b)
                new_v['bills'] = keep
            removed = {k: sorted(e['rm']) for k, e in rec.items()}
            kept = SEC.guard_records(old_v, new_v, removed, admin)
            if kept:
                self.log(f'Kept confirmed records from a {role} save: ' + '; '.join(kept[:15]))
            renum = {}
            if 'bills' in new_v:
                seq = new_v['seq'] if isinstance(new_v.get('seq'), dict) else {}
                top = max(_num(seq.get('bill')), _num(seq_cur.get('bill')), self._max_bill_no())   # cached: no scan per save
                batch = {}
                for b in new_v['bills']:
                    if b.get('id') in cur_rec['bills'] or b.get('imported'):
                        continue
                    no = _num(b.get('no'))
                    if not no:
                        continue
                    # Number stored as a number or as text: both use the bills(no) index (CAST would read every bill)
                    clash = batch.get(no) not in (None, b['id']) or con.execute(
                        'SELECT 1 FROM bills WHERE no IN (?, ?, ?) AND COALESCE(imported, 0) = 0 AND id <> ? LIMIT 1', (no, float(no), str(no), b['id'])).fetchone()
                    if clash:
                        top += 1
                        renum[b['id']] = top
                        b['no'] = no = top
                    batch[no] = b['id']
                    top = max(top, no)
                if top != _num(seq.get('bill')):
                    seq['bill'] = top
                    new_v['seq'] = seq
            if 'kots' in new_v:
                seq = new_v['seq'] if isinstance(new_v.get('seq'), dict) else {}
                taken = self._kot_numbers()
                for x in new_v['kots']:
                    if x.get('id') in cur_rec['kots'] or x.get('no') is None:
                        continue
                    if taken.get(x['no'], x['id']) != x['id']:
                        seq['kot'] = max(_num(seq.get('kot')), max([_num(v) for v in taken] + [0])) + 1
                        renum['kot:' + x['id']] = seq['kot']
                        x['no'] = seq['kot']
                        new_v['seq'] = seq
                    taken[x['no']] = x['id']
        # ---- 5. the final writes: only what differs from what is stored
        writes_rec, writes_map, writes_whole = {}, {}, {}
        for k, e in rec.items():
            final = {x['id']: x for x in new_v.get(k, []) if isinstance(x, dict) and x.get('id')}
            cur = cur_rec[k]
            ups = [x for rid, x in final.items() if rid not in cur or not jeq(cur[rid], x)]
            rms = [rid for rid in cur if rid not in final]
            if ups or rms:
                writes_rec[k] = (e['kind'], ups, rms)
        for k, e in maps.items():
            cm = cur_map[k]
            s_ = {mk: v for mk, v in e['set'].items() if mk not in cm or not jeq(cm[mk], v)}
            d_ = [mk for mk in e['del'] if mk in cm]
            if s_ or d_:
                writes_map[k] = (e['kind'], s_, d_)
        for k, v in new_v.items():
            if k in rec:
                continue
            if k not in self._ws or not jeq(self._ws[k], v):
                writes_whole[k] = v
        # What the device must correct in its own copy: every touched record / entry / value whose stored
        # result differs from what it sent (guards, merges, numbers, duplicates), plus values the server changed
        fix = []
        for k, e in rec.items():
            final = {x['id']: x for x in new_v.get(k, []) if isinstance(x, dict) and x.get('id')}
            for rid in [r for r in orig_touch[k] if r not in final and r in cur_rec[k] and r not in writes_rec.get(k, (0, 0, []))[2]]:
                final[rid] = cur_rec[k][rid]          # not removed after all (stays as stored)
            ups = [final[rid] for rid in orig_touch[k] if rid in final and not jeq(orig_up[k].get(rid, MISSING), final[rid])]
            rms = [rid for rid in orig_touch[k] if rid not in final and rid in orig_up[k]]
            if k == 'bills':
                ups += [b for b in dup.values() if b]
            if ups or rms:
                fix.append({'k': k, 'up': ups, 'rm': rms})
        for k, e in maps.items():
            cm, (oset, odel) = cur_map[k], orig_map[k]
            s_, d_ = writes_map.get(k, (None, {}, []))[1:]
            final = {mk: cm[mk] for mk in set(oset) | odel if mk in cm}
            final.update(s_)
            for mk in d_:
                final.pop(mk, None)
            ms = {mk: v for mk, v in final.items() if not jeq(oset.get(mk, MISSING), v)}
            md = [mk for mk in oset if mk not in final]
            if ms or md:
                fix.append({'k': k, 'mset': ms, 'mdel': md})
        for k in set(whole) | set(writes_whole):
            if k == 'secure' or k in rec:
                continue
            final = writes_whole[k] if k in writes_whole else self._ws.get(k, MISSING)
            if final is not MISSING and not jeq(orig_whole.get(k, MISSING), final):
                fix.append({'k': k, 'set': SEC.public_view({k: final}).get(k)})
        if conflicts:
            self._record_conflicts(conflicts, role)
        if not (writes_rec or writes_map or writes_whole):
            out = {'ok': True, 'version': self.version, 'savedAt': self.saved_at, 'unchanged': True}
            if conflicts:
                out['conflicts'] = [{'k': c_[0], 'id': c_[1], 'reason': c_[2]} for c_ in conflicts]
            if fix or dup:
                out.update(fix=fix, dup=dup, renumbered=renum, blocked=blocked)
            return 200, out
        # ---- 6. one transaction
        version, now = self.version + 1, int(time.time() * 1000)
        old_bills = {}
        with self.sdb.tx() as c:
            for k, (kind, ups, rms) in writes_rec.items():
                if k not in kinds:
                    self.sdb.register_key(c, k, kind)
                cur = cur_rec[k]
                for x in ups:
                    self.sdb.upsert(c, k, kind, x, cur.get(x['id']))
                    self.sdb.log_change(c, version, k, x['id'])
                for rid in rms:
                    self.sdb.remove(c, k, kind, rid, cur.get(rid))
                    self.sdb.log_change(c, version, k, rid)
                if k == 'bills':
                    old_bills = {x['id']: cur.get(x['id']) for x in ups}
                    old_bills.update({rid: cur.get(rid) for rid in rms})
            for k, (kind, s_, d_) in writes_map.items():
                if k not in kinds:
                    self.sdb.register_key(c, k, kind)
                for mk, v in s_.items():
                    self.sdb.map_set(c, k, kind, mk, v)
                    self.sdb.log_change(c, version, k, mk)
                for mk in d_:
                    self.sdb.map_del(c, k, kind, mk)
                    self.sdb.log_change(c, version, k, mk)
            for k, v in writes_whole.items():
                kind = SQ.SqliteDoc.kind_of(k, v)
                self.sdb.set_value(c, k, kind, v, self._ws.get(k))
                self.sdb.log_change(c, version, k, '')
            self.sdb.set_version(c, version, now)
            summary = {'keys': sorted(set(writes_rec) | set(writes_map) | set(writes_whole)), 'records': sum(len(u) + len(r) for _, u, r in writes_rec.values()), 'op': opid}
            hotel_id = self.sdb.meta('hotel_id') or (self._ws.get('settings') or {}).get('hotelCode') or 'UNKNOWN'
            dev_id = body.get('deviceId') or body.get('device') or ('counter_' + str(role))
            op_id_val = opid or f"op_{version}_{secrets.token_hex(6)}"
            envelope = SQ.make_sync_envelope(
                op_id=op_id_val,
                hotel_id=hotel_id,
                device_id=dev_id,
                doc_version=version,
                timestamp=now,
                event_type='settle' if opid and opid.startswith('settle:') else ('cancel' if opid and opid.startswith('cancel:') else 'ops'),
                actor={'role': role, 'elevated': bool(elev)},
                writes_rec=writes_rec,
                writes_map=writes_map,
                writes_whole=writes_whole,
                conflicts=conflicts
            )
            SQ.SqliteDoc.append_outbox(c, 'ops', op_id_val, version, envelope, now)
            if getattr(self, 'dispatcher', None) and getattr(self.dispatcher, '_running', False):
                self.dispatcher.wake()
            out = {'ok': True, 'version': version, 'savedAt': now}
            if conflicts:
                out['conflicts'] = [{'k': c_[0], 'id': c_[1], 'reason': c_[2]} for c_ in conflicts]
            if fix or dup or renum or blocked or kept:
                out.update(fix=fix, dup=dup, renumbered=renum, blocked=blocked, kept=len(kept))
            if opid:
                c.execute('INSERT OR REPLACE INTO operation_idempotency VALUES (?, ?, ?, ?, ?, ?, ?)', (opid, 'ops', None, None, role, now, json.dumps(out, ensure_ascii=False)))
            if version % 500 == 0:
                self.sdb.prune_change_log(c)
        # ---- 7. committed (WAL, synchronous=FULL): only now does memory move ahead
        with self._enc_lock:
            for k, (kind, ups, rms) in writes_rec.items():
                if k in HIST_KEYS:
                    continue
                lst = self._ws.get(k)
                if not isinstance(lst, list):
                    lst = self._ws[k] = []
                ix = self._index(k)
                for x in ups:
                    i = ix.get(x['id'])
                    if i is None:
                        lst.append(x)
                        ix[x['id']] = len(lst) - 1
                    else:
                        lst[i] = x
                if rms:
                    gone = set(rms)
                    lst[:] = [x for x in lst if not (isinstance(x, dict) and x.get('id') in gone)]
                    self._idx.pop(k, None)          # positions moved: rebuilt on next use
                if k == 'kots' and getattr(self, '_kotno', None):
                    if rms:
                        self._kotno = None
                    else:
                        for x in ups:
                            self._kotno[1][x.get('no')] = x.get('id')
            for k, (kind, s_, d_) in writes_map.items():
                m = self._ws.get(k)
                if not isinstance(m, dict):
                    m = self._ws[k] = {}
                m.update(s_)
                for mk in d_:
                    m.pop(mk, None)
            for k, v in writes_whole.items():
                self._ws[k] = v
            self.version, self.saved_at = version, now
        for bid, old in old_bills.items():
            new = next((x for x in writes_rec.get('bills', (None, [], []))[1] if x.get('id') == bid), None)
            self._hist_update(old, new)
        if getattr(self, '_maxno', None) is not None:
            nos = [int(_num(x.get('no'))) for x in writes_rec.get('bills', (None, [], []))[1] if not x.get('imported')]
            self._maxno = max([self._maxno] + nos)
            if writes_rec.get('bills', (None, [], []))[2]:
                self._maxno = None          # a bill was removed: count again when next needed
        self.stats['opsSaves'] += 1
        self.stats['opsRecords'] += summary['records']
        self._after_write(keep_maxno=True)
        return 200, out

    def _record_conflicts(self, conflicts, role):
        now = int(time.time() * 1000)
        with self.sdb.tx() as c:
            for k, rid, reason, kept, other in conflicts:
                c.execute('INSERT INTO sync_conflicts (at, k, rid, reason, kept, other, device) VALUES (?, ?, ?, ?, ?, ?, ?)',
                          (now, k, rid, reason, json.dumps(kept, ensure_ascii=False), json.dumps(other, ensure_ascii=False), role))
        self.stats['conflicts'] = self.stats.get('conflicts', 0) + len(conflicts)
        self.log(f'CONFLICT kept for review ({role}): ' + '; '.join(f'{k} {rid}: {reason}' for k, rid, reason, _, _ in conflicts[:10]))

    # ---------- what changed since a version (GET /api/changes) ----------
    def changes(self, since):
        with self._enc_lock:
            upto = self.version
        with self.sdb.rlock():
            con = self.sdb.con()
            rows = self.sdb.changed_since(con, since, upto) if since >= 0 else None
            if rows is None or len(rows) > 5000 or any(k == '*' for k, _, _ in rows):
                self.stats['changeReloads'] += 1
                return {'reload': True, 'version': self.version}
            kinds = self.sdb.kinds()
            groups = {}
            for k, rid, _ in rows:
                groups.setdefault(k, []).append(rid)
            out = []
            for k, rids in groups.items():
                kind = kinds.get(k)
                if '' in rids or kind not in RECORD_KINDS + MAP_KINDS:
                    if k in self._ws and k != 'secure':
                        out.append({'k': k, 'set': SEC.public_view({k: self._ws[k]}).get(k)})
                    continue
                if kind in RECORD_KINDS:
                    cur = self._cur(con, k, kind, rids)
                    out.append({'k': k, 'up': [cur[r] for r in rids if r in cur], 'rm': [r for r in rids if r not in cur]})
                else:
                    m = self._ws.get(k) if isinstance(self._ws.get(k), dict) else {}
                    out.append({'k': k, 'mset': {r: m[r] for r in rids if r in m}, 'mdel': [r for r in rids if r not in m]})
        self.stats['changeFeeds'] += 1
        return {'version': max(upto, since), 'savedAt': self.saved_at, 'histRev': self._hist_rev, 'ops': out}

    # ---------- native bill settle / cancel (one transaction each, through apply_ops) ----------
    def _native_ok(self, *keys):
        kinds = self.sdb.kinds()
        want = {'bills': 'spec', 'stock': 'spec', 'audit': 'spec', 'seq': 'seq'}
        # A key not stored yet (a new hotel's first bill) is fine: the first save registers it
        return all(kinds.get(k) in (want[k], None) for k in keys) and kinds.get('kaccha', 'maptable') == 'maptable'

    def settle_bill(self, payload):
        """Settle one bill: number, rows, stock, KOT number, running order cleared, idempotency, outbox."""
        key, bill = payload.get('idemKey'), payload.get('bill')
        if not key or not isinstance(bill, dict):
            return 400, {'error': 'idemKey and bill object are required'}
        if not self._native_ok('bills', 'stock', 'seq'):
            return 409, {'error': 'native settle not available for this data shape; save from the app'}
        with self.lock:
            con = self.sdb.con()
            with self.sdb.rlock():
                r = con.execute('SELECT id FROM bills WHERE idemKey = ?', (key,)).fetchone()
                ex = self.sdb.get_records(con, 'bills', [r[0]]).get(r[0]) if r else None
            if ex:
                same = ex.get('table') == bill.get('table') and abs(float(ex.get('total') or 0) - float(bill.get('total') or 0)) < 0.01 and ex.get('mode') == bill.get('mode')
                if same:
                    return 200, {'ok': True, 'alreadySettled': True, 'bill': ex, 'version': self.version}
                return 409, {'error': 'IDEMPOTENCY_PAYLOAD_MISMATCH', 'message': 'Idempotency key has already been used with a different bill payload'}
            if bill.get('mode') == 'Split':
                pays = bill.get('pays') or []
                if not pays:
                    return 400, {'error': 'SPLIT_TENDER_EMPTY', 'message': 'Split payment must have tender amounts'}
                tsum = round(sum(float(p.get('amt') or 0) for p in pays if isinstance(p, dict)), 2)
                if abs(tsum - round(float(bill.get('total') or 0), 2)) > 0.05:
                    return 400, {'error': 'SPLIT_TENDER_MISMATCH', 'message': f'Split payment tender sum ({tsum}) does not match bill total ({bill.get("total")})'}
            bill = copy.deepcopy(bill)
            seq = copy.deepcopy(self._ws.get('seq') or {})
            seq['bill'] = max(int(_num(seq.get('bill'))), self._max_bill_no()) + 1
            seq['kot'] = int(_num(seq.get('kot'))) + 1
            bill.update(no=seq['bill'], kot=seq['kot'], idemKey=key, paymentStatus='recorded')
            bill.setdefault('id', 'srv' + secrets.token_hex(8))
            bill.setdefault('date', time.strftime('%Y-%m-%d'))
            bill.setdefault('time', time.strftime('%H:%M'))
            if bill.get('mode') == 'UPI' or any(isinstance(p, dict) and p.get('mode') == 'UPI' for p in bill.get('pays') or []):
                bill['upiVerified'] = False
            ops = [{'k': 'bills', 'up': [bill]}, {'k': 'seq', 'set': seq}]
            if not bill.get('mv'):
                changed = {}
                for u in bill.get('used') or []:
                    it = self._ws_record('stock', u.get('sid'))
                    if it is not None:
                        it = copy.deepcopy(changed.get(it['id'], it))
                        it['qty'] = round(float(it.get('qty') or 0) - float(u.get('qty') or 0), 3)
                        changed[it['id']] = it
                if changed:
                    ops.append({'k': 'stock', 'up': list(changed.values())})
            tbl = bill.get('table')
            if tbl and tbl in (self._ws.get('kaccha') or {}):
                ops.append({'k': 'kaccha', 'mdel': [tbl]})
            code, res = self.apply_ops({'ops': ops, 'bv': self.version, 'id': 'settle:' + key}, 'local', True)
            if code != 200:
                return code, res
            with self.sdb.rlock():
                stored = self.sdb.get_records(con, 'bills', [bill['id']]).get(bill['id'], bill)
            self._maxno = max(self._maxno or 0, int(_num(stored.get('no'))))
            return 200, {'ok': True, 'alreadySettled': False, 'bill': stored, 'version': self.version}

    def _max_bill_no(self):
        # Highest finalized number ever stored (cached; any save resets it)
        if getattr(self, '_maxno', None) is None:
            with self.sdb.rlock():
                self._maxno = int(self.sdb.con().execute('SELECT MAX(CAST(no AS INTEGER)) FROM bills WHERE COALESCE(imported, 0) = 0').fetchone()[0] or 0)
        return self._maxno

    def cancel_bill(self, payload, by='Manager'):
        """Cancel a bill in one transaction: the record stays (cancelled), stock comes back once, audited."""
        bid, key = payload.get('billId'), payload.get('idemKey')
        if not bid or not key:
            return 400, {'error': 'billId and idemKey are required'}
        if not self._native_ok('bills', 'stock', 'audit'):
            return 409, {'error': 'native cancel not available for this data shape; cancel from the app'}
        with self.lock:
            con = self.sdb.con()
            with self.sdb.rlock():
                done = con.execute("SELECT 1 FROM operation_idempotency WHERE key = ?", ('cancel:' + key,)).fetchone()
                b = self.sdb.get_records(con, 'bills', [bid]).get(bid)
            if done:
                return 200, {'ok': True, 'alreadyDone': True, 'billId': bid, 'version': self.version}
            if b is None:
                return 404, {'error': 'bill not found'}
            if b.get('cancelled'):
                return 200, {'ok': True, 'alreadyCancelled': True, 'billId': bid, 'version': self.version}
            b = copy.deepcopy(b)
            b['cancelled'], b['cancelledBy'] = True, by
            ops = [{'k': 'bills', 'up': [b]}]
            if not b.get('mv'):
                changed = {}
                for u in b.get('used') or []:
                    it = self._ws_record('stock', u.get('sid'))
                    if it is not None:
                        it = copy.deepcopy(changed.get(it['id'], it))
                        it['qty'] = round(float(it.get('qty') or 0) + float(u.get('qty') or 0), 3)
                        changed[it['id']] = it
                if changed:
                    ops.append({'k': 'stock', 'up': list(changed.values())})
            now = int(time.time() * 1000)
            ops.append({'k': 'audit', 'up': [{'id': 'srv' + secrets.token_hex(6), 'at': now, 'date': time.strftime('%Y-%m-%d'), 'time': time.strftime('%H:%M'), 'user': by, 'role': 'manager',
                                              'action': 'Bill Cancel', 'detail': f'Bill #{b.get("no")} cancelled on the main counter', 'amount': b.get('total') or 0, 'ref': bid, 'approvedBy': by}]})
            code, res = self.apply_ops({'ops': ops, 'bv': self.version, 'id': 'cancel:' + key}, 'local', True)
            if code != 200:
                return code, res
            return 200, {'ok': True, 'billId': bid, 'version': self.version}

    # ---------- paginated reads (indexed SQL; nothing loads all history) ----------
    def query(self, name, q):
        if name == 'inbound-qr':
            # A bounded, local-first staff review queue; pending QR orders
            # remain separate from the billable running table cart.
            state = str(q.get('status') or 'pending').strip().lower()
            if state not in ('pending', 'accepted', 'rejected', 'all'):
                raise ValueError('status must be pending, accepted, rejected or all')
            limit = max(1, min(int(q.get('limit') or 50), 100))
            offset = max(0, int(q.get('offset') or 0))
            where = '' if state == 'all' else ' WHERE status = ?'
            args = () if state == 'all' else (state,)
            with self.sdb.rlock():
                c = self.sdb.con()
                count = c.execute(
                    'SELECT COUNT(*) FROM inbound_qr_orders' + where, args
                ).fetchone()[0]
                rows = c.execute(
                    'SELECT order_id,tbl,items_json,guest_name,note,status,kot_id,created_at,updated_at '
                    'FROM inbound_qr_orders' + where +
                    ' ORDER BY created_at DESC,order_id DESC LIMIT ? OFFSET ?',
                    args + (limit, offset)
                ).fetchall()
            native_qr = bool(getattr(getattr(getattr(self, 'dispatcher', None), 'inbound', None), '_running', False))
            return {
                'count': count, 'status': state, 'inboundQrNative': native_qr,
                'rows': [
                    {
                        'order_id': r[0], 'table': r[1],
                        'items': json.loads(r[2]), 'guest_name': r[3],
                        'note': r[4], 'status': r[5], 'kot_id': r[6],
                        'created_at': r[7], 'updated_at': r[8]
                    }
                    for r in rows
                ]
            }
        if name == 'bill-range':
            # Whole bill records of a date range (the app's own reports and screens run on them), by pages.
            # Own read connection: a long range never pauses billing.
            frm, to = q.get('from') or '0000-00-00', q.get('to') or '9999-99-99'
            lim = max(1, min(int(q.get('limit', 2000) or 2000), 5000))
            after = int(q.get('after', -1) or -1)
            n, rows, last = self.sdb.bill_page(frm, to, after, lim)
            return {'count': n, 'after': last, 'rows': rows, 'more': len(rows) == lim, 'ptsAt': self._pts_at(rows)}
        if name == 'hist':
            frm = q.get('from') or self.window_from()
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', frm):
                raise ValueError('from must be YYYY-MM-DD')
            return {'histRev': self._hist_rev, 'hist': self.hist(frm)}
        with self.sdb.rlock():
            return self._query(name, q)

    def _pts_at(self, rows):
        """Loyalty balance right after each bill (the app's ptsBalAt: same customer, not cancelled, number <= this one),
        for older bills a device loads (their earlier bills are not on the device)."""
        out, cache = {}, {}
        with self.sdb.reader() as c:
            for b in rows:
                if not (b.get('ptsEarned') or b.get('ptsUsed')):
                    continue
                p = SQ.norm_ph(b.get('phone'))
                if len(p) != 10:
                    continue
                if p not in cache:
                    lst = []
                    for no, extra, canc, ph in c.execute('SELECT no, extra, is_cancelled, phone FROM bills WHERE phone LIKE ?', ('%' + p,)):
                        if canc or SQ.norm_ph(ph) != p:
                            continue
                        ex = json.loads(extra) if extra and extra != '{}' else {}
                        lst.append((SQ.jsnum(no), SQ.jsnum(ex.get('ptsEarned')) - SQ.jsnum(ex.get('ptsUsed'))))
                    cache[p] = lst
                no = SQ.jsnum(b.get('no'))
                out[b['id']] = sum(v for n, v in cache[p] if n <= no)
        return out

    def _query(self, name, q):
        con = self.sdb.con()
        lim = max(1, min(int(q.get('limit', 100) or 100), 1000))
        off = max(0, int(q.get('offset', 0) or 0))
        frm, to = q.get('from') or '0000-00-00', q.get('to') or '9999-99-99'

        def rows(sql, args, cols):
            return [dict(zip(cols, r)) for r in con.execute(sql, args)]
        if name == 'bill':
            ids = [x for x in str(q.get('id') or '').split(',') if x][:200]
            rows_ = list(self.sdb.get_records(con, 'bills', ids).values())
            return {'rows': rows_, 'ptsAt': self._pts_at(rows_)}
        if name == 'bill-find':
            # Bill number, mobile or customer name, newest first (older bills not loaded on the device)
            s = str(q.get('q') or '').strip()
            if not s:
                return {'rows': []}
            if s.isdigit() and len(s) <= 7:
                sql, args = 'WHERE id IN (SELECT id FROM bills WHERE CAST(no AS INTEGER) = ? ORDER BY ord DESC LIMIT 50)', (int(s),)
            elif s.isdigit():
                sql, args = 'WHERE id IN (SELECT id FROM bills WHERE phone LIKE ? ORDER BY ord DESC LIMIT 50)', ('%' + s[-10:],)
            else:
                sql, args = 'WHERE id IN (SELECT id FROM bills WHERE cust LIKE ? ORDER BY ord DESC LIMIT 50)', ('%' + s.replace('%', '') + '%',)
            rows_ = self.sdb._export_rows(con, SQ.SPEC_BY_KEY['bills'], sql, args)
            return {'rows': rows_, 'ptsAt': self._pts_at(rows_)}
        if name == 'bills':
            cols = ['id', 'no', 'date', 'time', 'table', 'channel', 'mode', 'total', 'cancelled', 'phone']
            out = rows('SELECT id, no, date, time, "table", channel, mode, total, is_cancelled, phone FROM bills WHERE date BETWEEN ? AND ? ORDER BY date DESC, ord DESC LIMIT ? OFFSET ?', (frm, to, lim, off), cols)
            total = con.execute('SELECT COUNT(*), COALESCE(SUM(CASE WHEN is_cancelled = 0 THEN total_p END), 0) FROM bills WHERE date BETWEEN ? AND ?', (frm, to)).fetchone()
            return {'rows': out, 'count': total[0], 'sales_p': total[1]}
        if name == 'daybook':
            day = q.get('date') or time.strftime('%Y-%m-%d')
            sales = dict(con.execute("""SELECT CASE WHEN p.synthetic = 1 THEN COALESCE(b.mode, 'Cash') ELSE p.mode END, SUM(p.amount_p) FROM bill_payments p JOIN bills b ON b.id = p.bill_id
                                        WHERE b.date = ? AND b.is_cancelled = 0 AND (p.synthetic = 1 OR b.mode = 'Split') GROUP BY 1""", (day,)))
            vouchers = rows('SELECT type, head, COUNT(*), SUM(amount_p) FROM vouchers WHERE date = ? GROUP BY type, head', (day,), ['type', 'head', 'count', 'amount_p'])
            return {'date': day, 'sales_by_mode_p': sales, 'vouchers': vouchers}
        if name == 'stock-history':
            sid = q.get('sid', '')
            out = rows('SELECT id, source, ref, qty, type, date, time FROM stock_movements WHERE sid = ? AND date BETWEEN ? AND ? ORDER BY date DESC, time DESC LIMIT ? OFFSET ?', (sid, frm, to, lim, off), ['id', 'source', 'ref', 'qty', 'type', 'date', 'time'])
            bal = con.execute('SELECT qty FROM stock_balances WHERE sid = ?', (sid,)).fetchone()
            return {'rows': out, 'balance': bal[0] if bal else 0}
        if name == 'supplier-ledger':
            party = str(q.get('party', '')).strip().lower()
            out = rows("SELECT id, date, type, head, mode, amount, inv_id FROM vouchers WHERE LOWER(TRIM(COALESCE(party, ''))) = ? ORDER BY date DESC, ord DESC LIMIT ? OFFSET ?", (party, lim, off),
                       ['id', 'date', 'type', 'head', 'mode', 'amount', 'inv_id'])
            due = con.execute("""SELECT COALESCE(SUM(CASE WHEN (type = 'Purchase' OR (type = 'Expense' AND COALESCE(head, '') <> 'Supplier Payment')) AND mode = 'Credit' THEN amount_p
                                 WHEN type = 'Expense' AND head = 'Supplier Payment' THEN -amount_p ELSE 0 END), 0) FROM vouchers WHERE LOWER(TRIM(COALESCE(party, ''))) = ?""", (party,)).fetchone()[0]
            return {'rows': out, 'due_p': due}
        if name == 'audit':
            return {'rows': rows('SELECT id, at, date, action, user, amount, ref FROM audit_logs WHERE date BETWEEN ? AND ? ORDER BY ord DESC LIMIT ? OFFSET ?', (frm, to, lim, off), ['id', 'at', 'date', 'action', 'user', 'amount', 'ref'])}
        if name == 'customer':
            ph = q.get('phone', '')
            out = rows('SELECT id, no, date, total, is_cancelled FROM bills WHERE phone = ? ORDER BY date DESC LIMIT ? OFFSET ?', (ph, lim, off), ['id', 'no', 'date', 'total', 'cancelled'])
            agg = con.execute('SELECT COUNT(*), COALESCE(SUM(total_p), 0) FROM bills WHERE phone = ? AND is_cancelled = 0', (ph,)).fetchone()
            return {'rows': out, 'bills': agg[0], 'spent_p': agg[1]}
        if name == 'conflicts':
            return {'open': con.execute('SELECT COUNT(*) FROM sync_conflicts WHERE resolved = 0').fetchone()[0],
                    'rows': [dict(zip(('seq', 'at', 'k', 'id', 'reason', 'kept', 'other', 'device'), (r[0], r[1], r[2], r[3], r[4], json.loads(r[5] or 'null'), json.loads(r[6] or 'null'), r[7])))
                             for r in con.execute('SELECT seq, at, k, rid, reason, kept, other, device FROM sync_conflicts WHERE resolved = 0 ORDER BY seq DESC LIMIT ? OFFSET ?', (lim, off))]}
        if name == 'status':
            p = self.sdb.path
            size = lambda f: os.path.getsize(f) if os.path.exists(f) else 0   # noqa: E731
            return {'engine': 'sqlite', 'file': os.path.basename(p), 'dbBytes': size(p), 'walBytes': size(p + '-wal'), 'version': self.version,
                    'schema': self.sdb.meta('schema_version'), 'hotel': self.sdb.meta('hotel_id'), 'outboxPending': con.execute('SELECT COUNT(*) FROM sync_outbox WHERE sent_at IS NULL').fetchone()[0],
                    'window': {'from': self.window_from(), 'days': self.hist_days()}, 'stats': dict(self.stats), 'rssMB': rss_mb(),
                    'checkpoint': dict(getattr(self.sdb, 'ckpt_stats', None) or {'mode': 'inside commits (wal_autocheckpoint=1000)'}),
                    'lastBackup': getattr(self, 'backup_stats', None),
                    'conflictsOpen': con.execute('SELECT COUNT(*) FROM sync_conflicts WHERE resolved = 0').fetchone()[0],
                    'backups': rows('SELECT file, at, bytes, bills, verified, note FROM backup_manifest ORDER BY at DESC LIMIT 10', (), ['file', 'at', 'bytes', 'bills', 'verified', 'note']),
                    'cloudSync': self.sync_blocked}
        return None


def rss_mb():
    """Resident memory of this process in MB (Linux /proc, Windows GetProcessMemoryInfo); None if unknown."""
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD), ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                            ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t), ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                            ('QuotaNonPagedPoolUsage', ctypes.c_size_t), ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
            return round(pmc.WorkingSetSize / 1048576, 1)
        with open('/proc/self/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return round(int(line.split()[1]) / 1024, 1)
    except Exception:
        return None
    return None


class CloudSync:
    """Two-way sync between this PC's setu-db.json and the hotel's Setu Cloud Worker."""

    def __init__(self, store):
        self.store = store
        self.cfg_path = os.path.join(store.dir, 'setu-cloud.json')
        self.state_path = os.path.join(store.dir, 'setu-cloud-state.json')
        self.base_path = os.path.join(store.dir, 'setu-cloud-base.json')
        self.cfg = _read_json(self.cfg_path, {})
        self.state = _read_json(self.state_path, {})
        self.status = {'ok': None, 'at': 0, 'error': '', 'cloudVersion': self.state.get('cv', -1)}
        self.auto = {'state': '', 'code': '', 'at': 0}   # join-by-itself progress, shown in Settings
        self.link_lock = threading.Lock()                 # the loop and the "Connect Now" button must not both create a hotel
        self.wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def configured(self):
        return bool(self.cfg.get('url') and self.cfg.get('hotel') and self.cfg.get('key') and self.cfg.get('enabled', True))

    def public(self):
        # The sync key never leaves this PC
        lv = self.state.get('lv', -1)
        return {'configured': self.configured(), 'url': self.cfg.get('url', '') or DEFAULT_CLOUD_URL, 'hotel': self.cfg.get('hotel', ''),
                'enabled': self.cfg.get('enabled', True), 'hasKey': bool(self.cfg.get('key')), 'auto': self.auto, **self.status,
                # Edits on this PC that the cloud does not have yet, and the last time a sync fully succeeded
                'pending': self.configured() and (lv < 0 or self.store.version != lv), 'okAt': self.state.get('okAt', 0)}

    def grace(self):
        # Days since this PC last reached the cloud (or got a new licence key). Only for a hotel on the cloud;
        # an Offline hotel (set in Super Admin) and a PC that never synced after this update are left alone.
        ok_at = self.state.get('okAt', 0)
        if not self.configured() or not ok_at:
            return None
        with self.store.lock:
            d = self.store.data() if self.store.version else None
        if not isinstance(d, dict):
            return None
        saas = d.get('saas') or {}
        if not saas or saas.get('offline'):
            return None
        key_at = ((d.get('subscription') or {}).get('lastKeyAt') or 0) / 1000
        return round(max(0.0, (time.time() - max(ok_at / 1000, key_at)) / 86400), 2)

    def _license(self):
        # This PC's newest signed licence key (never the built-in AD-DEMO keys) + Install ID
        with self.store.lock:
            d = self.store.data() if self.store.version else None
        if not isinstance(d, dict):
            return None, None, {}
        st, sub = d.get('settings') or {}, d.get('subscription') or {}
        keys = self._licence_keys(d)
        return (keys[-1] if keys else None), st.get('installId'), d

    @staticmethod
    def _licence_keys(d):
        # Licence keys used on this PC, oldest first (never reset keys or the built-in AD-DEMO keys)
        sub = (d or {}).get('subscription') or {}
        return [k for k in (sub.get('usedKeys') or []) if isinstance(k, str) and k.startswith('SETU') and len(k) >= 128 and _key_kind(k) in (1, 2, 3, 5, 6)]

    def _post(self, url, path, obj, hotel=None):
        headers = {'Content-Type': 'application/json', 'User-Agent': 'Setu-Main-Counter/1.0'}
        if hotel:
            headers['X-Setu-Hotel'] = hotel
        req = urllib.request.Request(url + path, data=json.dumps(obj).encode('utf-8'), method='POST', headers=headers)
        try:
            with _urlopen(req, 30) as r:
                return r.status, json.loads(r.read().decode('utf-8') or '{}')
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode('utf-8') or '{}')
            except Exception:
                return e.code, {}

    def _save_link(self, url, hotel, key, restore=False):
        self.state = {'restore': True} if restore else {}
        try:
            os.remove(self.base_path)
        except OSError:
            pass
        _write_json(self.state_path, self.state)
        self.cfg = {'url': url, 'hotel': hotel, 'key': key, 'enabled': True}
        _write_json(self.cfg_path, self.cfg)
        self.status = {'ok': None, 'at': 0, 'error': '', 'cloudVersion': -1}
        self.wake.set()

    def auto_link(self):
        with self.link_lock:
            self._auto_link()

    def _auto_link(self):
        # Library ERP style: a licensed counter joins Setu Cloud by itself. Nothing to type.
        if self.configured():
            return
        key, iid, d = self._license()
        if not key or not iid:
            self.auto = {'state': 'nolicense', 'code': '', 'at': int(time.time() * 1000)}
            return
        # A fresh PC may be meant for "restore from cloud": join once it has data or has been signed up (hotel
        # name + owner login), so a new client shows in Super Admin right after the first activation
        auth0 = d.get('auth') or {}
        signed_up = bool(auth0.get('isRegistered') and (d.get('settings') or {}).get('name'))
        if not (d.get('menu') or d.get('bills') or signed_up):
            self.auto = {'state': 'waiting', 'code': '', 'at': int(time.time() * 1000)}
            return
        st, auth = d.get('settings') or {}, d.get('auth') or {}
        try:
            code, j = self._post(DEFAULT_CLOUD_URL, '/api/counter/link', {
                'installId': iid, 'key': key, 'name': st.get('name') or '', 'owner': auth.get('ownerName') or '',
                'phone': st.get('phone') or auth.get('phone') or ''})
        except Exception as e:
            kind, why = _net_reason(e)
            self.store.log(f'Hotel Setu Cloud: auto-join failed ({kind}): {e}')
            self.auto = {'state': 'offline', 'code': '', 'at': int(time.time() * 1000), 'kind': kind, 'error': why}
            return
        now = int(time.time() * 1000)
        if code == 200 and j.get('code') and j.get('syncKey'):
            self.store.log(f"Hotel Setu Cloud: joined by itself as {j['code']}")
            self.auto = {'state': 'joined', 'code': j['code'], 'at': now}
            self._save_link(DEFAULT_CLOUD_URL, j['code'], j['syncKey'])
        elif code == 409 and j.get('code'):
            self.auto = {'state': 'linked', 'code': j['code'], 'at': now}   # needs the owner password (restore)
        else:
            self.auto = {'state': 'error', 'code': '', 'at': now, 'error': j.get('error') or f'HTTP {code}'}

    def restore(self, hotel, password):
        with self.link_lock:
            self._restore(hotel, password)

    def _restore(self, hotel, password):
        hotel = ''.join(c for c in (hotel or '').upper() if c.isalnum())
        if not hotel or not password:
            raise ValueError('Enter both the Hotel Code and the owner password')
        _, iid, _ = self._license()
        try:
            code, j = self._post(DEFAULT_CLOUD_URL, '/api/counter/restore', {'password': password, 'installId': iid or ''}, hotel=hotel)
        except Exception as e:
            raise ValueError(_net_reason(e)[1])
        if code == 404:
            raise ValueError('This Hotel Code was not found on the cloud')
        if code != 200 or not j.get('syncKey'):
            raise ValueError(j.get('error') or f'Cloud HTTP {code}')
        self.store.log(f'Hotel Setu Cloud: restored from {hotel}')
        self.auto = {'state': 'joined', 'code': hotel, 'at': int(time.time() * 1000)}
        self._save_link(DEFAULT_CLOUD_URL, hotel, j['syncKey'], restore=True)

    def _push_license(self):
        # Every licence key used on this PC goes to the cloud once, in order, so the cloud period follows the
        # PC (the Worker checks each signature and applies the same rules: add days, set the date, lifetime)
        _, _, d = self._license()
        keys = self._licence_keys(d)
        sent = self.state.get('licSent')
        if sent is None:
            # First run (just joined / restored, or an older build that sent only the newest key): what the
            # cloud already counted is everything up to that key
            last = self.state.get('lic')
            sent = keys[:keys.index(last) + 1] if last in keys else list(keys)
            self.state['licSent'] = sent
            _write_json(self.state_path, self.state)
        for key in [k for k in keys if k not in sent]:
            code, _ = self._request('POST', '/api/counter/license', json.dumps({'key': key}))
            if code not in (200, 400):   # 400 = a key the cloud does not accept: do not resend it every few seconds
                return
            sent = self.state['licSent'] = (sent + [key])[-200:]
            _write_json(self.state_path, self.state)

    def set_config(self, url, hotel, key, enabled=True):
        url = (url or '').strip().rstrip('/')
        hotel = ''.join(c for c in (hotel or '').upper() if c.isalnum())
        if url.endswith('/hotel_erp.html'):
            url = url[:-len('/hotel_erp.html')]
        key = (key or '').strip() or self.cfg.get('key', '')
        if enabled:
            if not (url.startswith('https://') or url.startswith(('http://127.0.0.1:', 'http://localhost:'))):
                raise ValueError('The cloud URL must start with https://')
            if not hotel:
                raise ValueError('Please enter the Hotel Code')
            if not key:
                raise ValueError('Please enter the Cloud Sync Key')
            try:
                code, _ = self._request('GET', '/api/version', url=url, key=key, hotel=hotel)
            except Exception as e:
                raise ValueError('Could not connect to the cloud: ' + str(e))
            if code == 401:
                raise ValueError('Invalid Cloud Sync Key')
            if code == 404:
                raise ValueError('Hotel Code not found on the cloud')
            if code != 200:
                raise ValueError(f'Unexpected response from the cloud (HTTP {code})')
        if url != self.cfg.get('url') or hotel != self.cfg.get('hotel'):
            # A different cloud starts from scratch: nothing is "already synced" there
            self.state = {}
            try:
                os.remove(self.base_path)
            except OSError:
                pass
            _write_json(self.state_path, self.state)
        self.cfg = {'url': url, 'hotel': hotel, 'key': key, 'enabled': bool(enabled)}
        _write_json(self.cfg_path, self.cfg)
        self.status = {'ok': None, 'at': 0, 'error': '', 'cloudVersion': self.state.get('cv', -1)}
        self.wake.set()

    def _request(self, method, path, body=None, url=None, key=None, hotel=None):
        req = urllib.request.Request(
            (url or self.cfg['url']) + path,
            data=body.encode('utf-8') if body is not None else None,
            method=method,
            headers={'X-Setu-Sync': key or self.cfg['key'], 'X-Setu-Hotel': hotel or self.cfg['hotel'], 'X-Setu-Caps': 'secure1',
                     'Content-Type': 'application/json',
                     'User-Agent': 'Setu-Main-Counter/1.0'})
        try:
            with _urlopen(req, 60) as r:
                return r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')

    def _loop(self):
        last_try = 0
        while True:
            self.wake.wait(5 if self.status.get('ok') is not False else 20)
            woken = self.wake.is_set()
            self.wake.clear()
            if getattr(self.store, 'sync_blocked', None):
                # Whole-database cloud sync would undo the incremental storage: off until Phase 3
                self.status = {'ok': False, 'error': self.store.sync_blocked}
                continue
            if not self.configured():
                # Turned off by the owner ("enabled": false) = stay off
                # Every save wakes this loop: try at most once a minute then, else every 30 minutes
                gap = time.time() - last_try
                if getattr(self, 'relink_at', 0) > last_try:
                    gap = AUTO_LINK_EVERY + 1
                # Not licensed / no data yet is checked on this PC only, so a save may retry it at once
                # (a new client shows in Super Admin right after sign-up)
                local_wait = self.auto.get('state') in ('', 'nolicense', 'waiting')
                if self.cfg.get('enabled', True) and self.auto.get('state') != 'linked' and \
                        ((woken and (gap > 60 or local_wait)) or gap > AUTO_LINK_EVERY):
                    last_try = time.time()
                    try:
                        self.auto_link()
                    except Exception as e:
                        self.store.log('CLOUD AUTO-JOIN: ' + str(e))
                continue
            try:
                self._tick()
                now_ms = int(time.time() * 1000)
                self.status.update(ok=True, at=now_ms, error='')
                # Remember the last good sync on disk (for the 30-day check after a restart); every 10 min is enough
                if now_ms - self.state.get('okAt', 0) > 600000:
                    self.state['okAt'] = now_ms
                    _write_json(self.state_path, self.state)
                try:
                    self._push_license()
                except Exception:
                    pass
            except CloudBusy:
                self.wake.set()     # someone wrote in between: try again right away
            except Exception as e:
                msg = str(e) or e.__class__.__name__
                if self.status.get('error') != msg:
                    self.store.log('CLOUD SYNC: ' + msg)
                self.status.update(ok=False, at=int(time.time() * 1000), error=msg)

    def support(self, method, path, body=None):
        # Help & Support tickets go to the vendor through this PC's cloud link
        if not self.configured():
            raise ValueError('Help & Support needs this PC connected to Hotel Setu Cloud (Settings → Hotel Setu Cloud)')
        code, text = self._request(method, path, json.dumps(body) if body is not None else None)
        try:
            return code, json.loads(text or '{}')
        except ValueError:
            return code, {'error': f'Cloud HTTP {code}'}

    def _tick(self):
        code, text = self._request('GET', '/api/version')
        if code == 404:
            # Do NOT wipe self.cfg immediately! Transient 404s from edge/worker must not erase cloud link!
            consec = getattr(self, '_consec_404', 0) + 1
            self._consec_404 = consec
            if consec >= 30:  # Only after 30 consecutive failures across hours consider unlinking
                self.store.log(f"Hotel Setu Cloud: hotel {self.cfg.get('hotel')} not found on cloud after {consec} checks, resetting link")
                self.cfg = {'enabled': True}
                _write_json(self.cfg_path, self.cfg)
                self.state = {}
                _write_json(self.state_path, self.state)
                self.auto = {'state': '', 'code': '', 'at': 0}
                self.relink_at = time.time()
                self._consec_404 = 0
                raise OSError('Hotel not found on the cloud, reset link')
            raise OSError(f'Cloud HTTP 404 (check #{consec}), keeping connection settings and retrying...')
        self._consec_404 = 0
        if code != 200:
            raise OSError('Invalid Cloud Sync Key' if code == 401 else f'Cloud HTTP {code}')
        cv = json.loads(text)['version']
        st_cv, st_lv = self.state.get('cv', -1), self.state.get('lv', -1)
        if cv == st_cv and self.store.version == st_lv:
            return
        base = _read_json(self.base_path, None) if st_cv >= 0 else None
        if cv != st_cv or base is None:
            code, text = self._request('GET', '/api/db')
            if code != 200:
                raise OSError(f'Cloud HTTP {code}')
            doc = json.loads(text)
            cv, theirs = doc['version'], (doc['data'] if doc['version'] else None)
        else:
            theirs = copy.deepcopy(base)     # cloud unchanged since the last sync
        with self.store.lock:
            lv = self.store.version
            local = self.store.data() if lv else None
        if local is None and theirs is None:
            return
        if theirs is None:
            merged = local
        elif local is None:
            merged = theirs
        elif self.state.get('restore'):
            # New / formatted PC: the cloud copy wins, but this PC keeps its own Install ID and licence
            merged = copy.deepcopy(theirs)
            merged.setdefault('settings', {})['installId'] = (local.get('settings') or {}).get('installId') or merged['settings'].get('installId')
            if isinstance(local.get('subscription'), dict):
                merged['subscription'] = local['subscription']
        else:
            # Cloud as "mine" so bills already printed at this counter keep their numbers
            merged = merge3(base, theirs, local)
        if not isinstance(merged, dict) or 'settings' not in merged:
            raise OSError('Data looked wrong after merging, sync stopped')
        # The vendor's part (plan, message, warning / lock) always comes from the cloud
        if isinstance(theirs, dict) and 'saas' in theirs:
            merged['saas'] = theirs['saas']
        if theirs is None or not jeq(merged, theirs):
            body = '{"baseVersion": %d, "force": false, "data": %s}' % (cv, json.dumps(merged, ensure_ascii=False))
            code, text = self._request('POST', '/api/db', body)
            if code == 409:
                raise CloudBusy()
            if code == 402:
                # Suspended / expired: cloud saving stops, but the vendor's lock screen must still reach this PC
                with self.store.lock:
                    cur = self.store.data()
                    if isinstance(theirs, dict) and isinstance(cur, dict) and theirs.get('saas') != cur.get('saas'):
                        cur['saas'] = theirs.get('saas')
                        self.store.write(cur)
                if 'suspended' in text:
                    raise OSError('The vendor has suspended this Setu account. Please contact Aghanya Devanya Enterprises.')
                raise OSError('Hotel Setu Cloud subscription expired. Please renew online (billing continues on this PC).')
            if code != 200:
                raise OSError(f'Cloud save failed (HTTP {code})')
            cv = json.loads(text)['version']
        with self.store.lock:
            if self.store.version == lv:
                final = merged
                if local is None or not jeq(merged, local):
                    self.store.write(final)
            else:
                # The counter saved while we talked to the cloud: put its new edits on top
                final = merge3(local, merged, self.store.data())
                self.store.write(final)
            new_lv = self.store.version
        _write_json(self.base_path, merged)
        # lv = -1 tells the next round that this PC still has edits the cloud lacks
        self.state = {'cv': cv, 'lv': new_lv if jeq(final, merged) else -1, **{k: self.state[k] for k in ('lic', 'licSent', 'okAt') if k in self.state}}
        _write_json(self.state_path, self.state)
        self.status['cloudVersion'] = cv


def _ver(v):
    try:
        return tuple(int(x) for x in str(v).split('.'))
    except ValueError:
        return ()


class Updater:
    # Newest Setu installer from Hotel Setu Cloud: check every 6 hours, download only when the owner asks,
    # check its SHA-256, and install only when no print is running. Data, printers and licence are never touched:
    # they live in %LOCALAPPDATA%\AghanyaDevanyaERP\Data, outside the program folder.
    def __init__(self, store):
        self.store = store
        self.dir = os.path.join(os.path.dirname(store.dir), 'Updates')
        self.manifest = {}
        self.file = ''
        self.state = {'current': APP_VERSION, 'latest': '', 'available': False, 'hold': False, 'notes': '',
                      'step': '', 'error': '', 'progress': 0, 'checkedAt': 0}
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        time.sleep(90)
        while True:
            try:
                self.check()
            except Exception as e:
                self.state['error'] = _net_reason(e)
            time.sleep(6 * 3600)

    def check(self):
        req = urllib.request.Request(DEFAULT_CLOUD_URL + '/api/update', headers={'User-Agent': 'Setu-Main-Counter/1.0'})
        with _urlopen(req, 20) as r:
            m = json.loads(r.read().decode('utf-8') or '{}')
        self.manifest = m
        newer = APP_VERSION != 'dev' and bool(_ver(m.get('version'))) and _ver(m.get('version')) > _ver(APP_VERSION)
        self.state.update(latest=m.get('version', ''), hold=bool(m.get('hold')), notes=m.get('notes', ''),
                          available=newer and not m.get('hold'), checkedAt=int(time.time() * 1000), error='')
        return self.state

    def download(self):
        if self.state['step'] == 'downloading':
            return
        m = self.manifest
        if not self.state['available'] or not m.get('url') or not m.get('sha256'):
            raise ValueError('No update to download')
        self.state.update(step='downloading', progress=0, error='')
        threading.Thread(target=self._download, args=(dict(m),), daemon=True).start()

    def _download(self, m):
        try:
            os.makedirs(self.dir, exist_ok=True)
            path = os.path.join(self.dir, 'Setu-POS-Setup-%s.exe' % m['version'])
            part = path + '.part'
            h, got = hashlib.sha256(), 0
            req = urllib.request.Request(DEFAULT_CLOUD_URL + m['url'], headers={'User-Agent': 'Setu-Main-Counter/1.0'})
            with _urlopen(req, 60) as r, open(part, 'wb') as f:
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    if m.get('size'):
                        self.state['progress'] = min(99, int(got * 100 / m['size']))
            if h.hexdigest().lower() != str(m['sha256']).lower():
                os.remove(part)
                raise OSError('The downloaded file is damaged (check failed). Please try again.')
            os.replace(part, path)
            # Keep this one and the one before (to go back if needed)
            old = sorted((f for f in os.listdir(self.dir) if f.startswith('Setu-POS-Setup-') and f.endswith('.exe')),
                         key=lambda f: _ver(f[15:-4]))
            for f in old[:-2]:
                try:
                    os.remove(os.path.join(self.dir, f))
                except OSError:
                    pass
            self.file = path
            self.state.update(step='ready', progress=100)
            self.store.log('UPDATE: downloaded Setu ' + m['version'])
        except Exception as e:
            self.state.update(step='failed', error=_net_reason(e) if isinstance(e, urllib.error.URLError) else str(e))
            self.store.log('UPDATE FAILED: ' + str(e))

    def install(self):
        if self.state['step'] != 'ready' or not self.file or not os.path.exists(self.file):
            raise ValueError('Download the update first')
        last = print_history[-1]['at'] if print_history else 0
        if print_lock.locked() or time.time() * 1000 - last < 20000:
            raise ValueError('A print is running. Try again in a few seconds.')
        if os.name != 'nt':
            raise ValueError('Updates install only on Windows')
        import subprocess
        self.store.log('UPDATE: installing Setu ' + self.state['latest'])
        if getattr(self.store, 'wa', None):
            self.store.wa.kill()   # the WhatsApp helper's node.exe must not hold files the setup replaces
        # Silent install of the same per-user setup; it closes Setu, updates the program files and starts Setu again
        subprocess.Popen([self.file, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CLOSEAPPLICATIONS'],
                         close_fds=True, creationflags=0x00000008)   # DETACHED_PROCESS
        self.state['step'] = 'installing'
        threading.Timer(4, lambda: os._exit(0)).start()


def make_handler(base_dir, store, port, cloud=None, updater=None):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=base_dir, **kwargs)

        def log_message(self, format, *args):
            pass  # suppress log output

        # ---------- helpers ----------
        def is_local(self):
            return self.client_address[0] in ('127.0.0.1', '::1', '::ffff:127.0.0.1')

        def launch_ok(self):
            # Per-launch secret: only the Setu window started on this PC knows it (never a web page)
            got = self.headers.get('X-Setu-Launch', '')
            return bool(got) and bool(getattr(store, 'launch', '')) and secrets.compare_digest(got, store.launch)

        def counter_ok(self):
            """Main-counter-only actions: this PC's own Setu window, not any program or web page on it."""
            return self.is_local() and self.launch_ok()

        def elevated(self):
            # A manager typed their PIN on this device for one action (POST /api/auth/verify): valid 90 seconds
            gid = self.headers.get('X-Setu-Elev', '')
            g = store.elev.get(gid) if gid else None
            if not g or g['exp'] < time.time():
                return False
            return g['token'] == (self.headers.get('X-Setu-Token', '') or ('launch' if self.launch_ok() else ''))

        def request_refused(self, post):
            """Host / Origin / Content-Type checks for every /api/ request (CSRF and DNS rebinding)."""
            host = self.headers.get('Host', '')
            if not SEC.host_allowed(host):
                return 421, 'This address is not allowed. Open Setu by its IP address or localhost.'
            if not SEC.origin_allowed(self.headers.get('Origin'), host):
                return 403, 'Requests from another website are not allowed.'
            path = self.path.split('?')[0]
            if post and path not in ('/api/integrations/whatsapp/webhook', '/api/wa/callback'):
                ctype = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
                if ctype != 'application/json':
                    return 415, 'Send JSON (Content-Type: application/json).'
            return None

        def role(self):
            token = self.headers.get('X-Setu-Token', '')
            if token:
                tok = store.tokens.get(token)
                if isinstance(tok, dict):
                    # Check token session expiration
                    exp = tok.get('expiresAt')
                    if exp and time.time() > exp:
                        return None
                    # Tenant isolation: check against request hotel header if provided
                    req_hotel = (self.headers.get('X-Hotel-ID') or self.headers.get('X-Setu-Hotel') or '').strip()
                    tok_hotel = str(tok.get('hotelId') or '').strip()
                    if req_hotel and tok_hotel and tok_hotel not in ('default', 'all') and req_hotel != tok_hotel:
                        return None  # cross-hotel token rejected
                    own = store.hotel_id()
                    if req_hotel and own != 'default' and req_hotel != own:
                        return None  # this counter serves one hotel only
                    return tok.get('role', '').lower()
                elif isinstance(tok, str):
                    return tok.lower()
                else:
                    # A token this counter never issued (another hotel's, a deleted device's): refused, never ignored
                    # in favour of the main-counter fallback below (TENANT-01)
                    return None

            # Constrained bootstrap fallback:
            # Tokenless local access is allowed ONLY during bootstrap/setup (when database has no PINs or users configured),
            # and only for this PC's own Setu window (per-launch secret), never for a web page open on this PC.
            # Once any PIN or user exists, localhost requests MUST require authentication.
            if self.counter_ok():
                req_role = (self.headers.get('X-User-Role') or '').strip().lower()
                return req_role if req_role else 'local'
            return None

        def qr_proxy(self, method, path, body=None):
            # QR self-ordering lives on Hotel Setu Cloud; this PC forwards with its own sync key (never given to devices)
            if not cloud:
                return self.send_json(503, {'error': 'QR ordering needs Hotel Setu Cloud'})
            try:
                code, j = cloud.support(method, path, body)
            except ValueError as e:
                return self.send_json(400, {'error': str(e).replace('Help & Support', 'QR ordering')})
            except Exception:
                return self.send_json(502, {'error': 'Could not reach Hotel Setu Cloud. QR orders need the internet.'})
            return self.send_json(code, j)

        def guest_local_get(self, path):
            t = ''
            if '?' in self.path:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                t = (qs.get('t') or [''])[0].strip()
            with store.lock:
                try:
                    d = json.loads(store.raw)
                except Exception:
                    d = {}
            st = d.get('settings') or {}
            tbl = t or 'T-1'
            if path == '/api/guest/menu':
                items = [{
                    'id': m.get('id'),
                    'name': m.get('name'),
                    'cat': m.get('cat', 'Menu'),
                    'price': float(m.get('price', 0)),
                    'veg': m.get('veg'),
                    'desc': m.get('desc'),
                    'img': m.get('img') if re.match(r'^(https://|[a-zA-Z0-9_\-\./]+$)', str(m.get('img') or '')) and '..' not in str(m.get('img') or '') else None,
                    'photo': m.get('photo') if MEDIA.ID_RE.match(str(m.get('photo') or '')) else None,
                    'lib': m.get('lib') if re.match(r'^[a-z0-9-]{2,40}$', str(m.get('lib') or '')) else None,
                    'out': bool(m.get('out')) or None
                } for m in d.get('menu', []) if m and m.get('id') and m.get('name') and not m.get('qrOff') and m.get('active') is not False]
                return self.send_json(200, {
                    'hotel': st.get('name', 'Hotel Setu'),
                    'table': tbl,
                    'items': items,
                    'gst': float(st.get('gst', 0)),
                    'incl': bool(st.get('gstInclusive'))
                })
            if path == '/api/guest/status':
                return self.send_json(200, {'table': tbl, 'orders': [], 'calls': []})
            return self.send_json(404, {'error': 'not found'})

        def guest_local_post(self, path, body=None):
            b = body or {}
            if path == '/api/guest/order':
                tbl = (b.get('tbl') or b.get('t') or 'T-1').strip()
                items = b.get('items') or []
                with store.lock:
                    try:
                        d = json.loads(store.raw)
                    except Exception:
                        d = {}
                    kaccha = d.setdefault('kaccha', {})
                    k = kaccha.setdefault(tbl, {
                        'table': tbl, 'channel': 'Dine-In', 'cart': [], 'sent': {}, 'qr': [],
                        'createdAt': time.strftime('%I:%M %p'), 'note': 'QR Order'
                    })
                    k['qr'] = list(set(k.get('qr', []) + [b.get('id', str(int(time.time())))]))
                    menu = {str(m.get('id')): m for m in (d.get('menu') or []) if isinstance(m, dict)}
                    for it in items:
                        # Price and name come from the menu, never from the guest's phone
                        m = menu.get(str(it.get('mid')))
                        if not m or m.get('out') or m.get('qrOff'):
                            continue
                        try:
                            q = max(1, min(50, int(float(it.get('qty', 1)))))
                        except (TypeError, ValueError):
                            q = 1
                        it = {**it, 'name': m.get('name'), 'price': m.get('price', 0), 'qty': q}
                        c = next((x for x in k['cart'] if x.get('mid') == it.get('mid')), None)
                        if c:
                            c['qty'] = round(float(c.get('qty', 0)) + float(it.get('qty', 1)), 2)
                        else:
                            k['cart'].append({
                                'mid': it.get('mid'),
                                'name': it.get('name'),
                                'price': float(it.get('price', 0)),
                                'qty': float(it.get('qty', 1))
                            })
                    store.write(d)
                return self.send_json(200, {'id': b.get('id', 'g1'), 'status': 'accepted'})
            if path == '/api/guest/call':
                return self.send_json(200, {'id': 'c1'})
            return self.send_json(404, {'error': 'not found'})

        def send_json(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_media(self, got):
            body, ctype = got
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'public, max-age=31536000, immutable')   # the name is the content hash
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_full_db(self):
            # Written in parts straight to the connection: memory stays flat with any number of bills
            class _W:
                def __init__(self, w):
                    self.w, self.buf = w, []

                def write(self, t):
                    self.buf.append(t)
                    if sum(len(x) for x in self.buf) > 1 << 20:
                        self.flush()

                def flush(self):
                    if self.buf:
                        self.w.write(''.join(self.buf).encode('utf-8'))
                        self.buf = []
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            w = _W(self.wfile)
            store.write_full_json(w, public=True)   # no credential hashes for a device
            w.flush()
            self.close_connection = True

        def send_db(self):
            # Never the credentials: devices get the public view (cached per version)
            body = ('{"version": %d, "savedAt": %d, "data": %s}' % (store.version, store.saved_at, store.public_raw())).encode('utf-8')
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
        def static_allowed(self, path):
            # Only the app's own files: never app_main.py, keygen.py, keys, .dev.vars or test data next to it
            return path in PUBLIC_FILES or bool(FOOD_FILE_RE.match(path))

        def do_HEAD(self):
            if not self.static_allowed(self.path.split('?')[0]):
                return self.send_error(404)
            return super().do_HEAD()

        def do_GET(self):
            path = self.path.split('?')[0]
            if not path.startswith('/api/'):
                if not self.static_allowed(path):
                    return self.send_error(404)
                return super().do_GET()
            bad = self.request_refused(False)
            if bad:
                return self.send_json(bad[0], {'error': bad[1]})
            m = MEDIA_PATH_RE.match(path)
            if m:
                # A dish photo: public like any picture on the menu (the name is a hash; nothing else can be asked for)
                got = store.media.get(m.group(1), bool(m.group(2)))
                return self.send_media(got) if got else self.send_json(404, {'error': 'not found'})
            if path == '/api/media-export':
                # Photos backup, one page at a time (manager)
                if self.role() not in ('local', 'admin'):
                    return self.send_json(403, {'error': 'manager only'})
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                items, nxt = store.media.export((qs.get('after') or [''])[0])
                return self.send_json(200, {'v': 1, 'items': items, 'next': nxt})
            if path == '/api/ping':
                return self.send_json(200, {'setu': True, 'version': store.version, 'local': self.is_local(),
                                            'grace': cloud.grace() if cloud else None})
            if path == '/api/cloud':
                if not self.counter_ok():
                    return self.send_json(403, {'error': 'main counter only'})
                return self.send_json(200, cloud.public() if cloud else {'configured': False})
            if path == '/api/info':
                return self.send_json(200, {'setu': True, 'port': port, 'ips': lan_ips(), 'local': self.is_local()})
            if path == '/api/hotel/info':
                with store.lock:
                    d = store.data() or {}
                st = d.get('settings') or {}
                auth = d.get('auth') or {}
                h_id = str(st.get('hotelId') or auth.get('hotelId') or 'SETU001').strip()
                return self.send_json(200, {
                    'hotelId': h_id,
                    'name': st.get('name') or 'Setu Pro Hotel ERP',
                    'logo': st.get('logo') or '',
                    'active': bool(auth.get('isRegistered') or store.version > 0)
                })
            if path == '/api/update':
                if not self.counter_ok() or not updater:
                    return self.send_json(403, {'error': 'main counter only'})
                return self.send_json(200, updater.state)
            if path == '/api/autobackup':
                if self.role() not in ('local', 'admin'):
                    return self.send_json(403, {'error': 'manager only'})
                return self.send_json(200, store.autobackup.public())
            if path == '/api/integrations/whatsapp/webhook':
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                mode = params.get('hub.mode', [''])[0]
                token = params.get('hub.verify_token', [''])[0]
                challenge = params.get('hub.challenge', [''])[0]
                expected_token = os.environ.get('WHATSAPP_VERIFY_TOKEN') or 'setu_verify_token'
                if mode == 'subscribe' and (not expected_token or token == expected_token):
                    body = challenge.encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return self.send_json(403, {'error': 'Verification failed'})
            if path == '/api/wa/messages':
                role = self.role()
                if not role:
                    return self.send_json(401, {'error': 'pin required'})
                if role in ('waiter', 'kitchen'):
                    return self.send_json(403, {'error': 'staff unauthorized'})
                parsed = urllib.parse.urlparse(self.path)
                params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
                h_id = params.get('hotelId') or self.headers.get('X-Hotel-ID')
                res = store.get_wa_messages(filters=params, role=role, hotel_id=h_id)
                return self.send_json(200, res)
            if path == '/api/wa/stats':
                role = self.role()
                if not role:
                    return self.send_json(401, {'error': 'pin required'})
                if role in ('waiter', 'kitchen'):
                    return self.send_json(403, {'error': 'staff unauthorized'})
                parsed = urllib.parse.urlparse(self.path)
                params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
                h_id = params.get('hotelId') or self.headers.get('X-Hotel-ID')
                res = store.get_wa_stats(filters=params, hotel_id=h_id)
                return self.send_json(200, res)
            if path == '/api/wa/message':
                role = self.role()
                if not role:
                    return self.send_json(401, {'error': 'pin required'})
                if role in ('waiter', 'kitchen'):
                    return self.send_json(403, {'error': 'staff unauthorized'})
                parsed = urllib.parse.urlparse(self.path)
                params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
                msg_id = params.get('id')
                with store.lock:
                    d = store.data() or {}
                msgs = d.get('waMessages') or []
                msg = next((m for m in msgs if m.get('id') == msg_id or m.get('providerMsgId') == msg_id), None)
                if not msg:
                    return self.send_json(404, {'error': 'not found'})
                item = copy.deepcopy(msg)
                item['maskedPhone'] = item.get('maskedPhone') or store.mask_phone(item.get('phone'))
                if role not in ('local', 'admin', 'manager', 'owner', 'superadmin'):
                    item['phone'] = item['maskedPhone']
                    item.pop('apiSecret', None)
                    item.pop('authToken', None)
                return self.send_json(200, item)
            if path == '/api/wa/status':
                role = self.role()
                if not role:
                    return self.send_json(401, {'error': 'pin required'})
                st = store.wa.status()
                if role not in ('local', 'admin', 'manager', 'owner'):
                    st.pop('qr', None)   # only the manager/admin/owner sees the link QR
                return self.send_json(200, st)
            if path == '/api/log':
                # Error Log screen: the newest lines of setu-server.log (main counter only)
                if not self.counter_ok():
                    return self.send_json(403, {'error': 'main counter only'})
                try:
                    with open(os.path.join(store.dir, 'setu-server.log'), 'r', encoding='utf-8', errors='replace') as f:
                        lines = f.read().splitlines()[-300:]
                except OSError:
                    lines = []
                return self.send_json(200, {'lines': lines, 'cloud': cloud.public() if cloud else {}})
            if path == '/api/support/tickets':
                if self.role() not in ('local', 'admin') or not cloud:
                    return self.send_json(403, {'error': 'manager only'})
                try:
                    code, j = cloud.support('GET', path)
                except ValueError as e:
                    return self.send_json(400, {'error': str(e)})
                except Exception:
                    return self.send_json(502, {'error': 'Could not reach the cloud. Check the internet.'})
                return self.send_json(code, j)
            if path.startswith('/api/guest/'):
                if cloud:
                    return self.qr_proxy('GET', self.path)
                return self.guest_local_get(path)
            if not self.role():
                return self.send_json(401, {'error': 'pin required'})
            if path == '/api/aggregators/inbox':
                if self.role() not in ('local', 'admin', 'manager', 'cashier'):
                    return self.send_json(403, {'error': 'staff only'})
                return self.qr_proxy('GET', path)
            if path == '/api/qr/state':
                return self.qr_proxy('GET', path)
            if path == '/api/receipt/status':
                if self.role() not in ('local', 'admin', 'manager'):
                    return self.send_json(403, {'error': 'Staff receipt status permission required'})
                return self.qr_proxy('GET', self.path)
            if path == '/api/clock':
                # Setu Doctor: how far this PC's clock is from the cloud's (wrong date breaks licence and SSL)
                try:
                    with _urlopen(urllib.request.Request(DEFAULT_CLOUD_URL + '/api/ping', headers={'User-Agent': 'Setu-Main-Counter/1.0'}), 15) as r:
                        server = email.utils.parsedate_to_datetime(r.headers.get('Date')).timestamp()
                    return self.send_json(200, {'offset': int((time.time() - server) * 1000)})
                except Exception as e:
                    return self.send_json(200, {'offset': None, 'error': _net_reason(e)[1]})
            if path == '/api/ping':
                return self.send_json(200, {'ok': True, 'ping': 'pong'})
            if path == '/api/wa/balance':
                with store.lock:
                    d = store.data() or {}
                credits = int(d.get('settings', {}).get('waCredits', 500))
                total_sent = int(d.get('settings', {}).get('waTotalSent', 0))
                return self.send_json(200, {'ok': True, 'credits': credits, 'totalSent': total_sent})
            if path.startswith('/api/q/'):
                # Paginated, indexed reads (SQLite engine only): history without loading every bill
                if not hasattr(store, 'query'):
                    return self.send_json(404, {'error': 'available with the SQLite engine only'})
                qs = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
                if path[7:] in ('status', 'conflicts') and self.role() not in ('local', 'admin'):
                    return self.send_json(403, {'error': 'manager only'})
                if path[7:] == 'inbound-qr' and not self.role():
                    return self.send_json(401, {'error': 'staff login required'})
                try:
                    res = store.query(path[7:], qs)
                except (ValueError, TypeError) as e:
                    return self.send_json(400, {'error': str(e)})
                return self.send_json(200, res) if res is not None else self.send_json(404, {'error': 'unknown query'})
            if path == '/api/version':
                native_qr = bool(getattr(getattr(getattr(store, 'dispatcher', None), 'inbound', None), '_running', False))
                return self.send_json(200, {'version': store.version,
                                            **({'engine': 'sqlite', 'inboundQrNative': native_qr} if getattr(store, 'engine', '') == 'sqlite' else {})})
            if path == '/api/changes':
                # SQLite engine: only what changed since the device's version (never the whole data)
                if getattr(store, 'engine', '') != 'sqlite':
                    return self.send_json(404, {'error': 'available with the SQLite engine only'})
                if not self.role():
                    return self.send_json(401, {'error': 'pin required'})
                qs = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
                try:
                    since = int(qs.get('since', -1))
                except ValueError:
                    return self.send_json(400, {'error': 'since must be a number'})
                return self.send_json(200, store.changes(since))
            if path == '/api/db':
                if getattr(store, 'engine', '') == 'sqlite':
                    qs = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
                    if qs.get('full') == '1':
                        # The whole data with every bill (backup download): Manager / main counter only, streamed
                        if self.role() not in ('local', 'admin'):
                            return self.send_json(403, {'error': 'Manager only'})
                        return self.send_full_db()
                    frm = qs.get('from') or None
                    if frm and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', frm):
                        return self.send_json(400, {'error': 'from must be YYYY-MM-DD'})
                    if not frm and re.fullmatch(r'\d{4}-\d{2}-\d{2}', qs.get('today') or ''):
                        frm = store.window_from(today=qs['today'])
                    body = store.db_payload(frm)       # recent bills + totals of older ones; billing is not paused
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                with store.lock:
                    return self.send_db()
            if path == '/api/printer-health':
                try:
                    return self.send_json(200, printer_health())
                except Exception as e:
                    return self.send_json(500, {'error': str(e)})
            if path == '/api/printers':
                try:
                    names, default = list_printers()
                    return self.send_json(200, {'printers': names, 'default': default})
                except Exception as e:
                    return self.send_json(500, {'error': str(e)})
            return self.send_json(404, {'error': 'not found'})

        def do_POST(self):
            path = self.path.split('?')[0]
            bad = self.request_refused(True)
            if bad:
                return self.send_json(bad[0], {'error': bad[1]})
            if path == '/api/auth/verify':
                # Manager approval on a staff device: check a manager / owner PIN on the server, never on the device
                tok = self.headers.get('X-Setu-Token', '')
                if not self.role():
                    return self.send_json(401, {'error': 'pin required'})
                ip = self.client_address[0]
                wait = store.pin_guard(ip)
                if wait:
                    return self.send_json(429, {'error': f'Too many wrong PINs. Try again in {wait // 60 + 1} minutes.'})
                try:
                    pin = self.read_json().get('pin')
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                found = store.check_pin(pin)
                if not found or found[0] != 'admin':
                    store.pin_guard(ip, False)
                    time.sleep(1)
                    return self.send_json(403, {'ok': False, 'error': 'wrong pin'})
                store.pin_guard(ip, True)
                gid = secrets.token_hex(16)
                now = time.time()
                for k in [k for k, g in store.elev.items() if g['exp'] < now]:
                    del store.elev[k]
                store.elev[gid] = {'token': tok or ('launch' if self.launch_ok() else ''), 'exp': now + 90, 'by': found[1]}
                return self.send_json(200, {'ok': True, 'name': found[1], 'elev': gid, 'expiresIn': 90})
            if path == '/api/auth/forgot-password/send':
                ip = self.client_address[0]
                wait = store.pin_guard(ip)
                if wait:
                    return self.send_json(429, {'error': f'Too many attempts. Try again in {wait // 60 + 1} minutes.'})
                try:
                    b = self.read_json()
                    input_email = str(b.get('email') or '').strip()
                    h_id = str(b.get('hotelId') or '').strip()
                except Exception:
                    return self.send_json(400, {'error': 'Invalid request JSON'})

                if not input_email or '@' not in input_email or '.' not in input_email:
                    return self.send_json(400, {'error': 'Please enter a valid email address.'})

                store.clean_expired_otps()
                now = time.time()
                existing = store.reset_otps.get(input_email.lower())
                if existing and (now - existing.get('sent_at', 0)) < 60:
                    wait_sec = int(60 - (now - existing['sent_at']))
                    return self.send_json(429, {'error': f'Please wait {wait_sec}s before requesting a new OTP.'})

                with store.lock:
                    d = store.data() or {}
                st = d.get('settings') or {}
                auth = d.get('auth') or {}
                expected_hid = str(st.get('hotelId') or auth.get('hotelId') or 'SETU001').strip()
                reg_email = str(st.get('email') or auth.get('email') or '').strip()

                if h_id and h_id.upper() not in (expected_hid.upper(), 'SETU001', 'DEFAULT') and h_id != expected_hid:
                    return self.send_json(404, {'error': f'Hotel ID "{h_id}" not found on this system.'})

                # If a registered owner email exists in DB, ensure input matches it (prevent random recipient spam)
                if reg_email and '@' in reg_email:
                    if input_email.lower() != reg_email.lower():
                        eparts = reg_email.split('@')
                        ename = eparts[0]
                        edom = eparts[1] if len(eparts) > 1 else ''
                        masked_hint = (ename[0] + '***' + (ename[-1] if len(ename) > 1 else '')) + '@' + edom
                        return self.send_json(400, {'error': f'Email does not match registered owner email ({masked_hint}).'})
                    target_email = reg_email
                else:
                    target_email = input_email

                otp = f"{secrets.randbelow(900000) + 100000}"
                store.reset_otps[target_email.lower()] = {
                    'otp': otp,
                    'exp': now + 900,
                    'sent_at': now,
                    'attempts': 0
                }

                hotel_name = st.get('name') or 'Aghanya Devanya Hotel ERP'
                email_html = render_forgot_password_email(hotel_name, expected_hid, otp)
                try:
                    send_resend_email(target_email, f"Aghanya Devanya ERP - Password Reset OTP: {otp}", email_html)
                except Exception as e:
                    store.log(f'Resend email send error: {e}')
                    return self.send_json(500, {'error': f'Failed to send email via Resend: {e}'})

                eparts = target_email.split('@')
                ename = eparts[0]
                edom = eparts[1] if len(eparts) > 1 else ''
                masked_display = (ename[:2] + '***' + (ename[-1] if len(ename) > 2 else '')) + '@' + edom
                return self.send_json(200, {
                    'ok': True,
                    'maskedEmail': masked_display,
                    'message': f'6-digit reset OTP sent successfully to {masked_display}. Valid for 15 minutes.'
                })

            if path == '/api/auth/forgot-password/verify':
                ip = self.client_address[0]
                wait = store.pin_guard(ip)
                if wait:
                    return self.send_json(429, {'error': f'Too many attempts. Try again in {wait // 60 + 1} minutes.'})
                try:
                    b = self.read_json()
                    input_email = str(b.get('email') or '').strip().lower()
                    otp = str(b.get('otp') or '').strip()
                    new_pw = str(b.get('newPassword') or '').strip()
                except Exception:
                    return self.send_json(400, {'error': 'Invalid request JSON'})

                if not input_email or not otp or not new_pw:
                    return self.send_json(400, {'error': 'Email, OTP and new password are required.'})

                if len(new_pw) < 6:
                    return self.send_json(400, {'error': 'New password must be at least 6 characters.'})

                if SEC.is_weak(new_pw):
                    return self.send_json(400, {'error': 'The password is too simple. Please choose a stronger password.'})

                store.clean_expired_otps()
                rec = store.reset_otps.get(input_email)
                if not rec or time.time() > rec.get('exp', 0):
                    return self.send_json(400, {'error': 'OTP has expired or was not requested. Please request a new OTP.'})

                if rec.get('attempts', 0) >= 5:
                    store.reset_otps.pop(input_email, None)
                    return self.send_json(429, {'error': 'Too many wrong attempts. This OTP is cancelled. Request a new one.'})

                if rec['otp'] != otp:
                    rec['attempts'] = rec.get('attempts', 0) + 1
                    rem = 5 - rec['attempts']
                    return self.send_json(400, {'error': f'Invalid OTP code. {rem} tries remaining.'})

                store.reset_otps.pop(input_email, None)
                store.pin_guard(ip, True)

                with store.lock:
                    cur = copy.deepcopy(store.data() or {})
                    if not isinstance(cur.get('secure'), dict):
                        cur['secure'] = {}
                    new_hash = SEC.hash_secret(new_pw)
                    cur['secure']['owner'] = new_hash
                    cur['secure']['admin'] = new_hash
                    if not isinstance(cur.get('auth'), dict):
                        cur['auth'] = {}
                    cur['auth']['password'] = new_pw
                    if not isinstance(cur.get('settings'), dict):
                        cur['settings'] = {}
                    cur['settings']['adminPin'] = new_pw
                    cur['settings']['adminPinWeak'] = SEC.is_weak(new_pw)
                    if not cur['settings'].get('email'):
                        cur['settings']['email'] = input_email
                    SEC.absorb_secrets(cur, cur, True)
                    store.write(cur)

                store.log(f'Password & Admin PIN successfully reset via Resend OTP for {input_email}')
                return self.send_json(200, {
                    'ok': True,
                    'message': 'Password has been reset successfully! You can now login with your new password.'
                })

            if path == '/api/hotel/register':
                try:
                    b = self.read_json()
                except Exception:
                    return self.send_json(400, {'error': 'Invalid JSON request'})
                status, res = http_cloud_post('/api/hotel/register', b)
                if status is None:
                    return self.send_json(503, {'error': 'Hotel registration requires an active internet connection to allocate a Hotel ID.'})
                if status == 200 and res.get('ok'):
                    try:
                        d = store.data() or {}
                        st = d.setdefault('settings', {})
                        auth = d.setdefault('auth', {})
                        st['hotelId'] = res.get('hotelId')
                        st['name'] = res.get('hotelName')
                        auth['hotelId'] = res.get('hotelId')
                        auth['ownerName'] = res.get('owner')
                        auth['status'] = 'pending'
                        auth['isRegistered'] = True
                        store.save(d)
                    except Exception:
                        pass
                return self.send_json(status, res)

            if path == '/api/hotel/activate':
                try:
                    b = self.read_json()
                except Exception:
                    return self.send_json(400, {'error': 'Invalid JSON request'})
                status, res = http_cloud_post('/api/hotel/activate', b)
                if status is None:
                    return self.send_json(503, {'error': 'Activation Key validation requires an active internet connection.'})
                if status == 200 and res.get('ok'):
                    try:
                        d = store.data() or {}
                        auth = d.setdefault('auth', {})
                        auth['status'] = 'active'
                        auth['paidUntil'] = res.get('paidUntil')
                        store.save(d)
                        if cloud and res.get('syncKey'):
                            cloud.set_config(DEFAULT_CLOUD_URL, res['hotelId'], res['syncKey'], True)
                    except Exception:
                        pass
                return self.send_json(status, res)

            if path == '/api/hotel/login':
                try:
                    b = self.read_json()
                    hotel_id = str(b.get('hotelId') or '').strip().upper()
                    username = str(b.get('username') or 'owner').strip()
                    password = str(b.get('password') or '').strip()
                except Exception:
                    return self.send_json(400, {'error': 'Invalid JSON request'})

                if not hotel_id or not password:
                    return self.send_json(400, {'error': 'Hotel ID and Password are required.'})

                # Try cloud first
                status, cloud_res = http_cloud_post('/api/hotel/login', b)
                if status is not None:
                    if status == 200 and cloud_res.get('ok'):
                        try:
                            d = store.data() or {}
                            st = d.setdefault('settings', {})
                            auth = d.setdefault('auth', {})
                            sec = d.setdefault('secure', {})
                            st['hotelId'] = cloud_res.get('hotelId')
                            st['name'] = cloud_res.get('hotelName')
                            auth['hotelId'] = cloud_res.get('hotelId')
                            auth['ownerName'] = cloud_res.get('owner') or username
                            auth['status'] = 'active'
                            auth['isRegistered'] = True
                            sec['owner'] = SEC.hash_secret(password)
                            store.save(d)
                            if cloud and cloud_res.get('syncKey'):
                                cloud.set_config(DEFAULT_CLOUD_URL, cloud_res['hotelId'], cloud_res['syncKey'], True)
                                try:
                                    cloud.restore(cloud_res['hotelId'], password)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        token = store.add_token('admin', hotel_id=cloud_res['hotelId'], name=cloud_res.get('owner') or username)
                        cloud_res['token'] = token
                    return self.send_json(status, cloud_res)

                # Offline mode fallback
                d = store.data() or {}
                st = d.get('settings') or {}
                auth = d.get('auth') or {}
                local_hid = str(st.get('hotelId') or auth.get('hotelId') or '').upper()
                if not local_hid or (hotel_id and hotel_id != local_hid):
                    return self.send_json(503, {'error': 'Offline: Hotel ID not found locally. Initial login requires an active internet connection.'})

                found = store.check_pin(password)
                if not found:
                    return self.send_json(401, {'error': 'Invalid Hotel ID, Username, or Password (offline mode).'})

                role, name = found
                token = store.add_token(role, hotel_id=local_hid, name=name)
                return self.send_json(200, {
                    'ok': True,
                    'offline': True,
                    'hotelId': local_hid,
                    'hotelName': st.get('name') or 'Foodpiolet ERP',
                    'role': role,
                    'name': name,
                    'token': token,
                    'message': 'Logged in offline. Changes will sync when online.'
                })

            if path == '/api/hotel/auth':
                try:
                    b = self.read_json()
                    h_id = str(b.get('hotelId') or '').strip()
                    password = str(b.get('password') or '').strip()
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                with store.lock:
                    d = store.data() or {}
                st = d.get('settings') or {}
                auth = d.get('auth') or {}
                expected_hid = str(st.get('hotelId') or auth.get('hotelId') or 'SETU001').strip()
                has_pw = bool((d.get('secure') or {}).get('owner') or (d.get('secure') or {}).get('admin') or auth.get('password') or st.get('adminPin'))

                if store.version == 0 and not has_pw:
                    return self.send_json(200, {
                        'ok': True,
                        'bootstrap': True,
                        'hotelId': h_id or 'SETU001',
                        'name': 'Setu Pro Hotel ERP',
                        'status': 'unregistered'
                    })

                if not h_id or (h_id.upper() != expected_hid.upper() and h_id.upper() != 'SETU001' and h_id != expected_hid):
                    return self.send_json(404, {'error': 'Hotel ID not found', 'code': 'HOTEL_NOT_FOUND'})

                ip = self.client_address[0]
                wait = store.pin_guard(ip)
                if wait:
                    return self.send_json(429, {'error': f'Too many wrong tries. Try again in {wait // 60 + 1} minutes.'})
                if not password or not SEC.check_master(d, password):
                    store.pin_guard(ip, False)
                    time.sleep(1)
                    return self.send_json(403, {'error': 'Invalid Hotel Password', 'code': 'INVALID_PASSWORD'})
                store.pin_guard(ip, True)

                paid_until = int(d.get('paidUntil') or auth.get('paidUntil') or 0)
                if paid_until and paid_until < int(time.time() * 1000):
                    return self.send_json(402, {
                        'error': 'Hotel subscription expired',
                        'code': 'SUBSCRIPTION_EXPIRED',
                        'paidUntil': paid_until
                    })

                return self.send_json(200, {
                    'ok': True,
                    'hotelId': expected_hid,
                    'name': st.get('name') or 'Setu Pro Hotel ERP',
                    'logo': st.get('logo') or '',
                    'phone': st.get('phone') or '',
                    'status': 'active'
                })
            if path == '/api/login':
                try:
                    b = self.read_json()
                    pin = b.get('pin')
                    h_id = b.get('hotelId') or self.headers.get('X-Hotel-ID') or self.headers.get('X-Setu-Hotel') or 'default'
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                ip = self.client_address[0]
                wait = store.pin_guard(ip)
                if wait:
                    return self.send_json(429, {'error': f'Too many wrong PINs. Try again in {wait // 60 + 1} minutes.'})
                found = store.check_pin(pin)
                if not found:
                    store.pin_guard(ip, False)
                    time.sleep(1)   # slow down PIN guessing
                    return self.send_json(403, {'error': 'wrong pin'})
                own = store.hotel_id()
                if own != 'default' and str(h_id).strip() not in ('default', own):
                    return self.send_json(403, {'error': 'This PIN is for another hotel'})
                store.pin_guard(ip, True)
                role, name = found
                h_id = own if own != 'default' else h_id
                token = store.add_token(role, hotel_id=h_id, name=name)
                return self.send_json(200, {'token': token, 'role': role, 'name': name, 'hotelId': h_id})
            if path.startswith('/api/guest/'):
                if cloud:
                    return self.qr_proxy('POST', path, self.read_json())
                return self.guest_local_post(path, self.read_json())
            if path in ('/api/ai', '/api/ai/bill'):
                # Setu AI goes through this PC's cloud link (the Gemini key lives only on the cloud)
                if self.role() not in ('local', 'admin') or not cloud:
                    return self.send_json(403, {'error': 'Setu AI is for the owner / manager only'})
                try:
                    code, j = cloud.support('POST', path, self.read_json())
                except ValueError as e:
                    return self.send_json(400, {'error': str(e).replace('Help & Support', 'Setu AI')})
                except Exception:
                    return self.send_json(502, {'error': 'Could not reach the cloud. Check the internet.'})
                return self.send_json(code, j)
            if path == '/api/vendor/verify':
                # Bulk delete: the vendor's one-time code is checked on Hotel Setu Cloud (Manager / counter only)
                if self.role() not in ('local', 'admin'):
                    return self.send_json(403, {'error': 'manager only'})
                return self.qr_proxy('POST', path, self.read_json())
            if path == '/api/aggregators/ack':
                if self.role() not in ('local', 'admin'):
                    return self.send_json(403, {'error': 'Manager or main counter only'})
                return self.qr_proxy('POST', path, self.read_json())
            if path.startswith('/api/qr/'):
                # Any staff device may accept orders; QR settings and table codes are for the manager
                if not self.role() or (path in ('/api/qr/settings', '/api/qr/table') and self.role() not in ('local', 'admin')):
                    return self.send_json(403, {'error': 'manager only'})
                return self.qr_proxy('POST', path, self.read_json())
            if path == '/api/receipt/send':
                if self.role() not in ('local', 'admin'):
                    return self.send_json(403, {'error': 'Manager or Main Counter only'})
                return self.qr_proxy('POST', path, self.read_json())
            if path == '/api/support/ticket':
                if self.role() not in ('local', 'admin') or not cloud:
                    return self.send_json(403, {'error': 'manager only'})
                try:
                    code, j = cloud.support('POST', path, self.read_json())
                except ValueError as e:
                    return self.send_json(400, {'error': str(e)})
                except Exception:
                    return self.send_json(502, {'error': 'Could not reach the cloud. Check the internet.'})
                return self.send_json(code, j)
            if path == '/api/save-file':
                # The desktop window blocks downloads: backups / CSV / Tally files go to Downloads\Setu
                if not self.counter_ok():
                    return self.send_json(403, {'error': 'main counter only'})
                try:
                    body = self.read_json()
                    content = base64.b64decode(body['b64']) if body.get('b64') else str(body.get('text') or '')
                    saved = save_user_file(str(body.get('name') or ''), content)
                except Exception as e:
                    store.log(f'File save failed: {e}')
                    return self.send_json(500, {'error': str(e)})
                return self.send_json(200, {'path': saved})
            if path in ('/api/cloud/restore', '/api/cloud/join'):
                if not self.counter_ok() or not cloud:
                    return self.send_json(403, {'error': 'main counter only'})
                if getattr(store, 'sync_blocked', None):
                    # SQLite counter: whole-data cloud sync would undo incremental saves (Phase 3 dependency)
                    return self.send_json(409, {'error': store.sync_blocked})
                try:
                    body = self.read_json()
                    if path == '/api/cloud/restore':
                        cloud.restore(body.get('hotel'), str(body.get('password') or ''))
                    else:
                        if not cloud.cfg.get('enabled', True):
                            cloud.cfg = {**cloud.cfg, 'enabled': True}
                            _write_json(cloud.cfg_path, cloud.cfg)
                        cloud.auto_link()
                except ValueError as e:
                    return self.send_json(400, {'error': str(e)})
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                return self.send_json(200, cloud.public())
            if path == '/api/cloud':
                # Cloud URL + sync key are set only from the main counter PC itself
                if not self.counter_ok() or not cloud:
                    return self.send_json(403, {'error': 'main counter only'})
                try:
                    body = self.read_json()
                    cloud.set_config(body.get('url'), body.get('hotel'), body.get('key'), bool(body.get('enabled', True)))
                except ValueError as e:
                    return self.send_json(400, {'error': str(e)})
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                return self.send_json(200, cloud.public())
            if path == '/api/integrations/whatsapp/webhook':
                try:
                    b = self.read_json()
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                entries = b.get('entry') or []
                for entry in entries:
                    for change in entry.get('changes') or []:
                        val = change.get('value') or {}
                        statuses = val.get('statuses') or []
                        for st_item in statuses:
                            p_id = str(st_item.get('id') or '')
                            status_name = str(st_item.get('status') or '').lower()
                            ts = int(st_item.get('timestamp') or time.time()) * 1000
                            errors = st_item.get('errors') or []
                            err_code = ''
                            err_reason = ''
                            if errors:
                                err_code = str(errors[0].get('code') or '')
                                err_reason = str(errors[0].get('message') or errors[0].get('title') or '')
                            
                            mapped_status = {
                                'sent': 'SENT',
                                'delivered': 'DELIVERED',
                                'read': 'READ',
                                'failed': 'FAILED'
                            }.get(status_name, 'UNKNOWN')
                            
                            store.record_wa_message({
                                'providerMsgId': p_id,
                                'status': mapped_status,
                                'provider': 'meta',
                                'eventAt': ts,
                                'sentAt': ts if mapped_status == 'SENT' else None,
                                'deliveredAt': ts if mapped_status == 'DELIVERED' else None,
                                'readAt': ts if mapped_status == 'READ' else None,
                                'failedAt': ts if mapped_status == 'FAILED' else None,
                                'errorCode': err_code,
                                'errorReason': err_reason,
                                'note': f'Meta webhook callback: {status_name}' + (f' ({err_code}: {err_reason})' if err_code else '')
                            })
                return self.send_json(200, {'ok': True})
            if path == '/api/wa/callback':
                try:
                    b = self.read_json()
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                if not b.get('hotelId') and self.headers.get('X-Hotel-ID'):
                    b['hotelId'] = self.headers.get('X-Hotel-ID')
                res = store.record_wa_message(b)
                resp = {'ok': True, 'message': res}
                if isinstance(res, dict):
                    resp.update(res)
                return self.send_json(200, resp)
            if path == '/api/wa/retry':
                role = self.role()
                if not role:
                    return self.send_json(401, {'error': 'pin required'})
                try:
                    b = self.read_json()
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                msg_id = b.get('id')
                if not msg_id:
                    return self.send_json(400, {'error': 'MISSING_ID', 'message': 'Message id is required'})
                code, res = store.retry_wa_message(msg_id, role, provider=b.get('provider'))
                return self.send_json(code, res)
            if path == '/api/wa/cleanup':
                role = self.role()
                if not role:
                    return self.send_json(401, {'error': 'pin required'})
                try:
                    b = self.read_json()
                except Exception:
                    b = {}
                code, res = store.cleanup_wa_messages(b.get('retentionDays', 90), role)
                return self.send_json(code, res)
            if path == '/api/wa/pair':
                role = self.role()
                if not role or role not in ('local', 'admin', 'manager', 'owner'):
                    return self.send_json(403, {'error': 'manager or admin only'})
                try:
                    b = self.read_json()
                except Exception:
                    b = {}
                code, j = store.wa.call('/pair', b)
                return self.send_json(code, j)
            if path.startswith('/api/wa/') or path.startswith('/api/gupshup/'):
                # WhatsApp link: connect / disconnect = manager; send a bill = any logged-in device
                role = self.role()
                if not role or (path not in ('/api/wa/send', '/api/gupshup/send', '/api/gupshup/test', '/api/wa/recharge', '/api/wa/cloud-refresh') and role not in ('local', 'admin', 'manager', 'owner')):
                    return self.send_json(403, {'error': 'manager only'})
                try:
                    b = self.read_json() if int(self.headers.get('Content-Length') or 0) else {}
                    if path == '/api/wa/cloud-refresh':
                        if cloud and cloud.configured():
                            try:
                                code, res = cloud._request('GET', '/api/wa/balance')
                                if code == 200:
                                    j = json.loads(res)
                                    c_credits = j.get('credits')
                                    c_seq = j.get('seq', 0)
                                    if c_credits is not None:
                                        with store.lock:
                                            d = store.data() or {}
                                            st = d.setdefault('settings', {})
                                            last_seq = st.get('lastWaCreditSeq', 0)
                                            if c_seq > last_seq or st.get('waCredits') is None:
                                                st['waCredits'] = max(0, int(c_credits))
                                                st['lastWaCreditSeq'] = c_seq
                                                store.write(d)
                                        return self.send_json(200, {'ok': True, 'credits': int(c_credits), 'synced': True})
                            except Exception as e:
                                store.log(f'Cloud WA balance refresh exception: {e}')
                        with store.lock:
                            d = store.data() or {}
                        return self.send_json(200, {'ok': True, 'credits': int(d.get('settings', {}).get('waCredits', 0)), 'synced': False})
                    if path == '/api/wa/start':
                        store.wa.start()
                        return self.send_json(200, store.wa.status())
                    if path == '/api/wa/stop':
                        store.wa.stop()
                        return self.send_json(200, store.wa.status())
                    if path == '/api/wa/logout':
                        code, j = store.wa.call('/logout', {})
                        return self.send_json(code, j)
                    if path == '/api/wa/recharge':
                        if role not in ('local', 'admin', 'manager', 'owner'):
                            return self.send_json(403, {'error': 'manager or admin only'})
                        amt = int(b.get('amount') or 0)
                        if amt <= 0:
                            return self.send_json(400, {'ok': False, 'error': 'Invalid recharge amount: must be positive'})
                        code = str(b.get('code') or 'DIRECT_RECHARGE').strip()
                        note = str(b.get('note') or '').strip()
                        with store.lock:
                            d = store.data() or {}
                            st_dict = d.setdefault('settings', {})
                            cur_c = int(st_dict.get('waCredits', 500))
                            new_c = cur_c + amt
                            st_dict['waCredits'] = new_c
                            recharges = st_dict.setdefault('waRecharges', [])
                            recharges.insert(0, {
                                'id': f"rech_{int(time.time()*1000)}_{secrets.token_hex(3)}",
                                'amount': amt,
                                'prev': cur_c,
                                'balance': new_c,
                                'code': code,
                                'note': note,
                                'at': int(time.time() * 1000),
                                'by': role
                            })
                            st_dict['waRecharges'] = recharges[:50]
                            store.write(d)
                        return self.send_json(200, {'ok': True, 'credits': new_c, 'amount': amt})
                    if path in ('/api/gupshup/send', '/api/gupshup/test'):
                        with store.lock:
                            d_chk = store.data() or {}
                        st_settings = d_chk.get('settings', {})
                        cur_credits = int(st_settings.get('waCredits', 500))
                        is_test = (path == '/api/gupshup/test')

                        if not is_test and cur_credits <= 0:
                            return self.send_json(402, {
                                'ok': False,
                                'error': 'INSUFFICIENT_CREDITS',
                                'message': 'WhatsApp message balance is 0. Please recharge to continue sending messages.'
                            })

                        api_key = str(b.get('apiKey') or st_settings.get('gupshupApiKey') or '').strip()
                        app_name = str(b.get('appName') or st_settings.get('gupshupAppName') or '').strip()
                        src_num = str(b.get('source') or st_settings.get('gupshupSource') or '').strip()

                        if not api_key or not app_name or not src_num:
                            return self.send_json(400, {
                                'ok': False,
                                'error': 'GUPSHUP_NOT_CONFIGURED',
                                'message': 'Gupshup API credentials missing. Please set Gupshup API Key, App Name, and Source Number in Settings.'
                            })

                        raw_ph = re.sub(r'\D', '', str(b.get('phone') or ''))
                        if len(raw_ph) == 10:
                            raw_ph = '91' + raw_ph
                        elif len(raw_ph) < 10 or len(raw_ph) > 15:
                            return self.send_json(400, {'ok': False, 'error': 'Invalid phone number: must be 10 to 15 digits'})

                        raw_src = re.sub(r'\D', '', str(src_num))
                        if len(raw_src) == 10:
                            raw_src = '91' + raw_src

                        bill_id = b.get('billId')
                        force_resend = bool(b.get('forceResend'))
                        if bill_id and not is_test:
                            with store.lock:
                                d = store.data() or {}
                            msgs = d.get('waMessages') or []
                            prior = next((m for m in reversed(msgs) if m.get('billId') == bill_id and m.get('status') != 'CANCELLED'), None)
                            if prior:
                                cur_st = prior.get('status')
                                if cur_st == 'PROCESSING':
                                    return self.send_json(409, {
                                        'ok': False,
                                        'error': 'CONCURRENT_REQUEST',
                                        'message': 'Message is currently being dispatched',
                                        'id': prior.get('id')
                                    })
                                if cur_st in ('SUBMITTED', 'SENT', 'DELIVERED', 'READ') and not force_resend:
                                    return self.send_json(409, {
                                        'ok': False,
                                        'error': 'ALREADY_SUBMITTED',
                                        'message': 'Bill already submitted to WhatsApp',
                                        'existingMessage': prior
                                    })

                        token_data = store.tokens.get(self.headers.get('X-Setu-Token', ''))
                        tok_hotel = token_data.get('hotelId') if isinstance(token_data, dict) else None
                        h_id = str(b.get('hotelId') or self.headers.get('X-Hotel-ID') or self.headers.get('X-Setu-Hotel') or tok_hotel or 'default').strip()

                        req_id = b.get('id') or f'wa_req_{int(time.time()*1000)}_{secrets.token_hex(4)}'
                        idem_key = b.get('idemKey') or f'wa_bill_{h_id}_{bill_id or req_id}'
                        now_ts = int(time.time() * 1000)

                        if not is_test:
                            store.record_wa_message({
                                'id': req_id,
                                'hotelId': h_id,
                                'billId': bill_id,
                                'billNo': b.get('billNo'),
                                'phone': b.get('phone'),
                                'customerName': b.get('customerName') or 'Customer',
                                'provider': 'gupshup',
                                'idemKey': idem_key,
                                'status': 'PROCESSING',
                                'staff': role or 'staff',
                                'note': 'Gupshup dispatch initiated'
                            })

                        text_content = str(b.get('text') or '').strip()
                        msg_obj = json.dumps({'type': 'text', 'text': text_content}, ensure_ascii=False)
                        post_params = {
                            'channel': 'whatsapp',
                            'source': raw_src,
                            'destination': raw_ph,
                            'message': msg_obj,
                            'src.name': app_name
                        }
                        encoded_payload = urllib.parse.urlencode(post_params).encode('utf-8')
                        req = urllib.request.Request('https://api.gupshup.io/wa/api/v1/msg', data=encoded_payload, method='POST')
                        req.add_header('apikey', api_key)
                        req.add_header('Content-Type', 'application/x-www-form-urlencoded')

                        try:
                            with urllib.request.urlopen(req, timeout=15) as resp:
                                g_code = resp.getcode()
                                g_raw = resp.read().decode('utf-8')
                                g_json = json.loads(g_raw) if g_raw else {}
                        except urllib.error.HTTPError as he:
                            g_code = he.code
                            err_txt = he.read().decode('utf-8', errors='ignore')
                            try:
                                g_json = json.loads(err_txt)
                            except Exception:
                                g_json = {'error': err_txt or str(he)}
                        except Exception as e:
                            g_code = 503
                            g_json = {'error': str(e)}

                        now_ts = int(time.time() * 1000)
                        p_id = str(g_json.get('messageId') or '')
                        st = 'SUBMITTED' if (g_code in (200, 202) and (g_json.get('status') == 'submitted' or p_id)) else 'FAILED'
                        err_reason = str(g_json.get('message') or g_json.get('error') or '') if st == 'FAILED' else ''

                        if not is_test:
                            updated = store.record_wa_message({
                                'id': req_id,
                                'hotelId': h_id,
                                'billId': bill_id,
                                'providerMsgId': p_id,
                                'status': st,
                                'submittedAt': now_ts if st == 'SUBMITTED' else None,
                                'failedAt': now_ts if st == 'FAILED' else None,
                                'errorCode': str(g_code) if st == 'FAILED' else '',
                                'errorReason': err_reason,
                                'note': f'Gupshup API response: HTTP {g_code}'
                            })
                            if st == 'SUBMITTED':
                                with store.lock:
                                    d_up = store.data() or {}
                                    st_set = d_up.setdefault('settings', {})
                                    prev_c = int(st_set.get('waCredits', 500))
                                    st_set['waCredits'] = max(0, prev_c - 1)
                                    st_set['waTotalSent'] = int(st_set.get('waTotalSent', 0)) + 1
                                    store.write(d_up)
                        else:
                            updated = {'id': req_id, 'status': st}

                        return self.send_json(200 if st == 'SUBMITTED' else (g_code if g_code >= 400 else 400), {
                            'ok': st == 'SUBMITTED',
                            'id': req_id,
                            'status': st,
                            'providerMsgId': p_id,
                            'error': err_reason,
                            'message': updated
                        })

                    if path == '/api/wa/send':
                        with store.lock:
                            d_chk = store.data() or {}
                        cur_credits = int(d_chk.get('settings', {}).get('waCredits', 500))
                        if cur_credits <= 0:
                            return self.send_json(402, {
                                'ok': False,
                                'error': 'INSUFFICIENT_CREDITS',
                                'message': 'WhatsApp message balance is 0. Please recharge to continue sending messages.'
                            })

                        raw_ph = re.sub(r'\D', '', str(b.get('phone') or ''))
                        if len(raw_ph) < 10:
                            return self.send_json(400, {'ok': False, 'error': 'Invalid phone number: must be at least 10 digits'})

                        bill_id = b.get('billId')
                        force_resend = bool(b.get('forceResend'))
                        if bill_id:
                            with store.lock:
                                d = store.data() or {}
                            msgs = d.get('waMessages') or []
                            prior = next((m for m in reversed(msgs) if m.get('billId') == bill_id and m.get('status') != 'CANCELLED'), None)
                            if prior:
                                cur_st = prior.get('status')
                                if cur_st == 'PROCESSING':
                                    return self.send_json(409, {
                                        'ok': False,
                                        'error': 'CONCURRENT_REQUEST',
                                        'message': 'Message is currently being dispatched',
                                        'id': prior.get('id')
                                    })
                                if cur_st in ('SUBMITTED', 'SENT', 'DELIVERED', 'READ') and not force_resend:
                                    return self.send_json(409, {
                                        'ok': False,
                                        'error': 'ALREADY_SUBMITTED',
                                        'message': 'Bill already submitted to WhatsApp',
                                        'existingMessage': prior
                                    })
                                if force_resend and role not in ('local', 'admin', 'manager', 'owner'):
                                    return self.send_json(403, {
                                        'ok': False,
                                        'error': 'UNAUTHORIZED',
                                        'message': 'Manager authorization required to resend bill'
                                    })

                        token_data = store.tokens.get(self.headers.get('X-Setu-Token', ''))
                        tok_hotel = token_data.get('hotelId') if isinstance(token_data, dict) else None
                        h_id = str(b.get('hotelId') or self.headers.get('X-Hotel-ID') or self.headers.get('X-Setu-Hotel') or tok_hotel or 'default').strip()

                        req_id = b.get('id') or f"wa_req_{int(time.time()*1000)}_{secrets.token_hex(4)}"
                        idem_key = b.get('idemKey') or f"wa_bill_{h_id}_{bill_id or req_id}"
                        now_ts = int(time.time() * 1000)

                        # Persist PROCESSING outbox state before network dispatch
                        store.record_wa_message({
                            'id': req_id,
                            'hotelId': h_id,
                            'billId': bill_id,
                            'billNo': b.get('billNo'),
                            'phone': b.get('phone'),
                            'customerName': b.get('customerName') or 'Customer',
                            'provider': b.get('provider') or 'baileys',
                            'idemKey': idem_key,
                            'status': 'PROCESSING',
                            'staff': role or 'staff',
                            'note': 'Dispatch initiated'
                        })

                        try:
                            code, j = store.wa.call('/send', {k: b.get(k) for k in ('phone', 'text', 'pdf', 'image', 'fileName')}, timeout=15)
                            now_ts = int(time.time() * 1000)
                            st = 'SUBMITTED' if code == 200 and j.get('status') == 'submitted' else ('FAILED' if code != 200 else 'UNKNOWN')
                            p_id = str(j.get('id') or '')
                            err_reason = str(j.get('error') or '') if st == 'FAILED' else ''
                            updated = store.record_wa_message({
                                'id': req_id,
                                'hotelId': h_id,
                                'billId': bill_id,
                                'providerMsgId': p_id,
                                'status': st,
                                'submittedAt': now_ts if st == 'SUBMITTED' else None,
                                'failedAt': now_ts if st == 'FAILED' else None,
                                'errorCode': str(code) if st == 'FAILED' else '',
                                'errorReason': err_reason,
                                'note': f'Baileys gateway response: HTTP {code}'
                            })
                            if st == 'SUBMITTED':
                                with store.lock:
                                    d_up = store.data() or {}
                                    st_set = d_up.setdefault('settings', {})
                                    prev_c = int(st_set.get('waCredits', 500))
                                    st_set['waCredits'] = max(0, prev_c - 1)
                                    st_set['waTotalSent'] = int(st_set.get('waTotalSent', 0)) + 1
                                    store.write(d_up)
                            resp_payload = {'ok': code == 200, 'id': req_id, 'requestId': req_id, 'providerMsgId': p_id, 'message': updated}
                            if isinstance(j, dict):
                                j_copy = dict(j)
                                gw_id = j_copy.pop('id', None)
                                if gw_id and not p_id:
                                    p_id = str(gw_id)
                                    resp_payload['providerMsgId'] = p_id
                                resp_payload.update(j_copy)
                            resp_payload['id'] = req_id
                            resp_payload['requestId'] = req_id
                            resp_payload['status'] = st
                            return self.send_json(code, resp_payload)
                        except (socket.timeout, urllib.error.URLError) as e:
                            # Provider timeout or network disconnect -> mark as UNKNOWN, NEVER auto-fail
                            now_ts = int(time.time() * 1000)
                            store.record_wa_message({
                                'id': req_id,
                                'hotelId': h_id,
                                'billId': bill_id,
                                'status': 'UNKNOWN',
                                'errorReason': 'Gateway timeout / network disconnected: outcome unconfirmed',
                                'note': f'Network timeout: {e}'
                            })
                            return self.send_json(504, {
                                'ok': False,
                                'status': 'UNKNOWN',
                                'id': req_id,
                                'error': 'STATUS_UNKNOWN',
                                'message': 'Request timed out; message status unknown. Please check status before retrying.'
                            })
                        except Exception as e:
                            now_ts = int(time.time() * 1000)
                            store.record_wa_message({
                                'id': req_id,
                                'hotelId': h_id,
                                'billId': bill_id,
                                'status': 'FAILED',
                                'failedAt': now_ts,
                                'errorCode': 'GATEWAY_ERROR',
                                'errorReason': str(e)[:200],
                                'note': f'Gateway error: {e}'
                            })
                            return self.send_json(503, {
                                'ok': False,
                                'status': 'FAILED',
                                'id': req_id,
                                'error': str(e)[:200]
                            })
                except OSError as e:
                    return self.send_json(503, {'ok': False, 'error': str(e)[:200]})
                except ValueError:
                    return self.send_json(400, {'error': 'bad request'})
                return self.send_json(404, {'error': 'not found'})
            if path == '/api/autobackup':
                # Auto backup: change the folder / timing, back up now, pick a folder, restore (manager on the main counter)
                if self.role() not in ('local', 'admin'):
                    return self.send_json(403, {'error': 'manager only'})
                ab = store.autobackup
                try:
                    b = self.read_json()
                    act = b.get('action')
                    if act in ('set', 'restore') and not self.counter_ok():
                        return self.send_json(403, {'error': 'Change backups on the main counter PC (Setu window)'})
                    if act == 'set':
                        ab.set(b.get('folder'), b.get('every'), b.get('keep'), b.get('on'), allow_network=b.get('network') is True)
                    elif act == 'now':
                        ab.run('by hand')
                    elif act == 'pick':
                        if not self.counter_ok():
                            return self.send_json(403, {'error': 'choose the folder on the main counter PC'})
                        try:
                            import webview
                            res = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG, directory=ab.cfg['folder'])
                        except Exception:
                            return self.send_json(501, {'error': 'Folder window not available here: type the folder path'})
                        if res:
                            ab.set(res[0] if isinstance(res, (list, tuple)) else res, allow_network=b.get('network') is True)
                    elif act == 'restore':
                        ab.restore(b.get('name'))
                    else:
                        return self.send_json(400, {'error': 'unknown action'})
                except (OSError, ValueError) as e:
                    return self.send_json(400, {'error': str(e)[:200]})
                return self.send_json(200, ab.public())
            if path == '/api/update':
                # Check / download / install a new Setu (main counter PC only)
                if not self.counter_ok() or not updater:
                    return self.send_json(403, {'error': 'main counter only'})
                try:
                    act = self.read_json().get('action')
                    if act == 'check':
                        updater.check()
                    elif act == 'download':
                        updater.download()
                    elif act == 'install':
                        updater.install()
                    else:
                        return self.send_json(400, {'error': 'unknown action'})
                except ValueError as e:
                    return self.send_json(400, {'error': str(e)})
                except Exception as e:
                    return self.send_json(502, {'error': _net_reason(e) if isinstance(e, urllib.error.URLError) else str(e)})
                return self.send_json(200, updater.state)
            if path in ('/api/media', '/api/media-import'):
                # The restaurant's own dish photos (manager). Content is checked, named by its hash, kept out of the data
                if self.role() not in ('local', 'admin'):
                    return self.send_json(403, {'error': 'manager only'})
                try:
                    b = self.read_json()
                    items = b.get('items') if path == '/api/media-import' else [b]
                    if not isinstance(items, list) or not 0 < len(items) <= 50:
                        return self.send_json(400, {'error': 'bad request'})
                    ids = [store.media.put(it.get('full'), it.get('thumb'), it.get('id') or None) for it in items if isinstance(it, dict)]
                except ValueError as e:
                    return self.send_json(400, {'error': str(e)})
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                if cloud and cloud.configured():
                    # The QR menu and phones on the internet need the same photos: copy them to Setu Cloud (best effort)
                    def mirror(batch=items):
                        try:
                            cloud._request('POST', '/api/media-import', json.dumps({'items': batch}))
                        except Exception as e:
                            store.log(f'Photo copy to cloud failed: {e!r}')
                    threading.Thread(target=mirror, daemon=True).start()
                return self.send_json(200, {'ok': True, 'id': ids[0] if ids else '', 'ids': ids})
            if path == '/api/printer-jobs':
                # Printer Health: remove stuck or repeated jobs (main counter or a Manager device)
                if self.role() not in ('local', 'admin'):
                    return self.send_json(403, {'error': 'Only from a Manager device or the Main Counter PC'})
                try:
                    body = self.read_json()
                    printer = str(body.get('printer') or '')
                    ids = None if body.get('all') else [int(x) for x in body.get('ids') or []]
                    if not printer or (ids is not None and not ids):
                        return self.send_json(400, {'error': 'bad request'})
                    done, failed = delete_print_jobs(printer, ids)
                    store.log(f'Printer Health: removed {done} job(s) from {printer!r}' + (f', {failed} failed' if failed else ''))
                    return self.send_json(200, {'done': done, 'failed': failed})
                except Exception as e:
                    return self.send_json(500, {'error': str(e)})
            if path == '/api/print':
                if not self.role():
                    return self.send_json(401, {'error': 'pin required'})
                try:
                    body = self.read_json()
                    data = base64.b64decode(body.get('data') or '')
                    printer = str(body.get('printer') or '')
                    if not printer or not data or len(data) > 2 * 1024 * 1024:
                        return self.send_json(400, {'error': 'bad request'})
                    with print_lock:
                        print_raw(printer, data)
                    print_history.append({'at': int(time.time() * 1000), 'printer': printer, 'bytes': len(data), 'ok': True})
                    del print_history[:-100]
                    return self.send_json(200, {'ok': True})
                except Exception as e:
                    store.log(f'PRINT FAILED on {printer!r}: {e}')
                    print_history.append({'at': int(time.time() * 1000), 'printer': printer, 'ok': False, 'error': str(e)[:200]})
                    del print_history[:-100]
                    return self.send_json(500, {'error': str(e)})
            if path == '/api/bill/cancel':
                role = self.role()
                if role not in ('local', 'admin') and not self.elevated():
                    return self.send_json(403, {'error': 'Manager approval needed'})
                if not hasattr(store, 'cancel_bill'):
                    return self.send_json(404, {'error': 'available with the SQLite engine only'})
                try:
                    body = self.read_json()
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                code, resp = store.cancel_bill(body, by='Main Counter' if role == 'local' else 'Manager')
                return self.send_json(code, resp)
            if path == '/api/bill/settle':
                role = self.role()
                if not role:
                    return self.send_json(401, {'error': 'pin required'})
                try:
                    body = self.read_json()
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                status_code, resp = store.settle_bill(body)
                return self.send_json(status_code, resp)
            if path == '/api/backup/save':
                # SQLite engine, main counter: the whole data (every bill) as a JSON backup in Downloads\Setu, written in parts
                if not hasattr(store, 'write_full_json'):
                    return self.send_json(404, {'error': 'available with the SQLite engine only'})
                if not self.counter_ok() and self.role() != 'local':
                    return self.send_json(403, {'error': 'main counter only'})
                try:
                    body = self.read_json()
                except Exception:
                    body = {}
                name = str((body or {}).get('name') or 'setu-backup.json')
                try:
                    path = user_file_path(name if name.endswith('.json') else name + '.json')
                    with open(path + '.part', 'w', encoding='utf-8') as f:
                        store.write_full_json(f, public=True)
                    os.replace(path + '.part', path)
                    store.log(f'Full JSON backup saved to {path}')
                    return self.send_json(200, {'ok': True, 'path': path})
                except Exception as e:
                    store.log(f'FULL BACKUP FAILED: {e!r}')
                    return self.send_json(500, {'error': str(e)})
            if path == '/api/ops':
                # SQLite engine: a device saves only what changed (records, map entries, small values), one transaction
                if getattr(store, 'engine', '') != 'sqlite':
                    return self.send_json(404, {'error': 'available with the SQLite engine only'})
                role = self.role()
                if not role:
                    return self.send_json(401, {'error': 'pin required'})
                try:
                    body = self.read_json()
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                if not isinstance(body, dict):
                    return self.send_json(400, {'error': 'bad request'})
                elev = self.elevated()
                with store.lock:
                    try:
                        code, res = store.apply_ops(body, role, elev)
                    except SQ.StoreError as e:
                        return self.send_json(400, {'error': str(e)})
                    except Exception as e:
                        store.log(f'SAVE FAILED (ops) v{store.version + 1}: {e!r}')
                        return self.send_json(500, {'error': 'save failed: ' + str(e)})
                if code == 200 and elev and not res.get('repeat') and not res.get('unchanged'):
                    store.elev.pop(self.headers.get('X-Setu-Elev', ''), None)   # one approval = one save
                return self.send_json(code, res)
            if path == '/api/db':
                role = self.role()
                if not role:
                    return self.send_json(401, {'error': 'pin required'})
                try:
                    body = self.read_json()
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                if getattr(store, 'engine', '') == 'sqlite' and not body.get('force') and store.version:
                    # Normal saves on SQLite go through /api/ops; a whole upload here is an out-of-date page
                    store.stats['legacyFullSaves'] += 1
                    store.log(f'Whole-data save refused from a {role} device (out-of-date page); it must reload')
                    return self.send_json(426, {'error': 'This screen is out of date. Reload Setu (press F5) to keep saving.', 'upgrade': True})
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
                    if force and not (role == 'admin' or self.counter_ok()):
                        return self.send_json(403, {'error': 'Restore needs a manager login on the main counter'})
                    try:
                        old = json.loads(store.raw) if store.version else {}
                    except Exception:
                        old = {}
                    old = old if isinstance(old, dict) else {}
                    elev = self.elevated()
                    can_set = role in ('admin', 'local') or elev
                    # Credentials: plain PINs become hashes (manager only), the stored hashes always stay
                    changed = SEC.absorb_secrets(data, old, can_set)
                    # Cashier / captain / kitchen: settings, logins, licence, audit and past records stay as stored
                    blocked = [] if force else SEC.sanitize_write(role, old, data, elev)
                    if blocked:
                        store.log(f'BLOCKED by role {role}: ' + ', '.join(blocked[:20]))
                    try:
                        store.clean_and_validate_bills(data)
                    except ValueError as ve:
                        return self.send_json(400, {'error': str(ve)})
                    # Confirmed bills, vouchers and stock movements never vanish in a routine save
                    kept = []
                    if not force:
                        kept = SEC.guard_records(old, data, body.get('removed'), role in ('admin', 'local') or elev)
                        if kept:
                            store.log(f'Kept confirmed records from a {role} save: ' + '; '.join(kept[:15]) + (f' (+{len(kept) - 15} more)' if len(kept) > 15 else ''))
                    elif store.version:
                        # Forced restore: allowed above for the main counter / a Manager only; always recorded
                        before = len(old.get('bills') or []) if isinstance(old.get('bills'), list) else store.bill_count() if hasattr(store, 'bill_count') else 0
                        after = len(data.get('bills') or []) if isinstance(data.get('bills'), list) else 0
                        store.log(f'RESTORE by {role}{" (approved)" if elev else ""}: bills {before} -> {after}, version {store.version} replaced')
                        if not isinstance(data.get('audit'), list):
                            data['audit'] = []
                        now = time.time()
                        data['audit'].append({'id': 'restore-%d' % int(now * 1000), 'at': int(now * 1000), 'date': time.strftime('%Y-%m-%d'), 'time': time.strftime('%H:%M'),
                                                  'user': 'Main Counter' if role == 'local' else role, 'role': role, 'action': 'Data Restore',
                                                  'detail': f'Database replaced from a backup: bills {before} -> {after}', 'amount': 0, 'ref': '', 'approvedBy': 'approved' if elev else ''})
                    try:
                        store.write(data)
                    except Exception as e:
                        store.log(f'SAVE FAILED v{store.version + 1}: {e!r}')
                        return self.send_json(500, {'error': 'save failed: ' + str(e)})
                    if elev:
                        store.elev.pop(self.headers.get('X-Setu-Elev', ''), None)   # one approval = one save
                    out = {'version': store.version, 'savedAt': store.saved_at}
                    if changed or blocked or kept:
                        out['changed'] = True          # the device pulls the stored copy again
                    if blocked:
                        out['blocked'] = blocked
                    return self.send_json(200, out)
            return self.send_json(404, {'error': 'not found'})

        def send_db_conflict(self):
            body = ('{"conflict": true, "version": %d, "savedAt": %d, "data": %s}' % (store.version, store.saved_at, store.public_raw())).encode('utf-8')
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


class WhatsAppLink:
    """The hotel's own WhatsApp, linked by QR (like WhatsApp Web), sends bill receipts.
    Runs whatsapp/wa.js with the bundled node.exe on 127.0.0.1; only this server talks to it."""
    PORT = 47130

    def __init__(self, store):
        self.store = store
        self.cfg_path = os.path.join(store.dir, 'setu-whatsapp.json')
        self.cfg = _read_json(self.cfg_path, {}) or {}
        self.proc = None
        self.url = os.environ.get('SETU_WA_URL') or f'http://127.0.0.1:{self.PORT}'   # tests point this at a fake
        # Check multiple candidate locations for whatsapp helper directory
        candidates = [
            os.path.join(get_base_dir(), 'whatsapp'),
            os.path.join(os.path.dirname(sys.executable), 'whatsapp') if getattr(sys, 'frozen', False) else '',
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'whatsapp'),
        ]
        self.dir = next((d for d in candidates if d and os.path.exists(d)), candidates[0])
        if self.cfg.get('on'):
            threading.Thread(target=self.start, daemon=True).start()
        atexit.register(self.kill)

    def available(self):
        return bool(os.environ.get('SETU_WA_URL')) or os.path.exists(os.path.join(self.dir, 'wa.js'))

    def _node(self):
        exe = os.path.join(self.dir, 'node.exe')
        return exe if os.path.exists(exe) else shutil.which('node')

    def start(self):
        self.cfg['on'] = True
        _write_json(self.cfg_path, self.cfg)
        if os.environ.get('SETU_WA_URL') or (self.proc and self.proc.poll() is None):
            return
        node = self._node()
        if not node or not os.path.exists(os.path.join(self.dir, 'wa.js')):
            raise OSError('The WhatsApp part is not installed. Install the newest Setu.')
        import subprocess
        flags = 0x08000000 if os.name == 'nt' else 0   # CREATE_NO_WINDOW
        self.proc = subprocess.Popen([node, os.path.join(self.dir, 'wa.js'), str(self.PORT), os.path.join(self.store.dir, 'whatsapp-session')],
                                     cwd=self.dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        self.store.log('WhatsApp link started')

    def kill(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass

    def stop(self):
        self.cfg['on'] = False
        _write_json(self.cfg_path, self.cfg)
        self.kill()

    def call(self, path, body=None, timeout=10):
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode('utf-8') if body is not None else None,
                                     method='POST' if body is not None else 'GET', headers={'Content-Type': 'application/json'})
        try:
            # never through a proxy: the helper is on this PC
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode('utf-8') or '{}')
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode('utf-8') or '{}')
            except ValueError:
                return e.code, {'error': f'HTTP {e.code}'}

    def status(self):
        base = {'available': self.available(), 'on': bool(self.cfg.get('on'))}
        if not base['on']:
            return {**base, 'state': 'off'}
        if not os.environ.get('SETU_WA_URL') and (self.proc is None or self.proc.poll() is not None):
            try:
                self.start()   # the helper stopped: start it again
            except OSError as e:
                return {**base, 'state': 'error', 'lastError': str(e)}
        try:
            code, j = self.call('/status', timeout=3)
            return {**base, **j}
        except Exception:
            return {**base, 'state': 'starting'}


class AutoBackup:
    """Compressed copies of the database (and the archive) into a folder the owner chooses:
    another drive, a pen drive or a Google Drive / OneDrive folder. Every few hours and when Setu closes."""

    def __init__(self, store):
        self.store = store
        self.cfg_path = os.path.join(store.dir, 'setu-autobackup.json')
        self.cfg = _read_json(self.cfg_path, {}) or {}
        self.cfg.setdefault('folder', os.path.join(os.path.expanduser('~'), 'Documents', 'Setu Backups'))
        self.cfg.setdefault('every', 2)      # hours
        self.cfg.setdefault('keep', 60)      # newest files kept
        self.cfg.setdefault('on', True)
        self.lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def public(self):
        c = dict(self.cfg)
        try:
            files = self.files()
            c['files'] = [{'name': n, 'size': os.path.getsize(os.path.join(c['folder'], n)), 'at': int(os.path.getmtime(os.path.join(c['folder'], n)) * 1000)} for n in files[:15]]
            c['count'] = len(files)
            u = shutil.disk_usage(c['folder'])
            c['free'] = u.free
        except OSError:
            c['files'], c['count'] = [], 0
        c['drives'] = self.drives()
        c['dataDrive'] = os.path.splitdrive(os.path.abspath(self.store.dir))[0].upper()
        return c

    @staticmethod
    def drives():
        out = []
        if os.name == 'nt':
            import string
            for L in string.ascii_uppercase:
                root = L + ':\\'
                if os.path.exists(root):
                    try:
                        u = shutil.disk_usage(root)
                        out.append({'drive': L + ':', 'free': u.free, 'total': u.total})
                    except OSError:
                        pass
        return out

    def files(self):
        f = self.cfg['folder']
        return sorted((x for x in os.listdir(f) if x.startswith('Setu-Backup-') and x.endswith('.json.gz')), reverse=True) if os.path.isdir(f) else []

    def set(self, folder=None, every=None, keep=None, on=None, allow_network=False):
        with self.lock:
            if folder is not None:
                raw = str(folder).strip()
                # A network share would send the whole database (and its hashes) off this PC: only when the owner
                # ticks "network folder" in the Setu window on the main counter
                if SEC.is_network_path(raw) and not allow_network:
                    raise ValueError('Network / UNC folders (\\\\server\\share) are not allowed for backups. Choose a drive on this PC or a pen drive.')
                folder = os.path.abspath(os.path.expanduser(raw))
                os.makedirs(folder, exist_ok=True)
                test = os.path.join(folder, '.setu-write-test')
                with open(test, 'w') as f:      # fails here if the folder cannot be written (read-only / no pen drive)
                    f.write('ok')
                os.remove(test)
                self.cfg['folder'] = folder
            if every is not None:
                self.cfg['every'] = max(1, min(24, int(every)))
            if keep is not None:
                self.cfg['keep'] = max(3, min(500, int(keep)))
            if on is not None:
                self.cfg['on'] = bool(on)
            _write_json(self.cfg_path, self.cfg)

    def run(self, why='auto'):
        """One backup now. Returns the file name; raises when the folder cannot be written."""
        import gzip
        with self.lock:
            folder = self.cfg['folder']
            os.makedirs(folder, exist_ok=True)
            hotel = ''
            try:
                d = self.store.data() or {}
                hotel = ''.join(c for c in str((d.get('settings') or {}).get('name') or '') if c.isalnum())[:20]
            except Exception:
                pass
            name = 'Setu-Backup-' + time.strftime('%Y-%m-%d_%H%M') + ('-' + hotel if hotel else '') + '.json.gz'
            tmp = os.path.join(folder, name + '.tmp')
            try:
                full = getattr(self.store, 'write_full_json', None)
                if full:
                    # SQLite: every bill comes from the tables in parts (the server holds no bill history in memory)
                    with gzip.open(tmp, 'wt', encoding='utf-8', compresslevel=6) as f:
                        full(f)
                else:
                    with self.store.lock:
                        raw = self.store.raw
                        version = self.store.version
                    doc = '{"version": %d, "savedAt": %d, "data": %s}' % (version, int(time.time() * 1000), raw)
                    with gzip.open(tmp, 'wt', encoding='utf-8', compresslevel=6) as f:
                        f.write(doc)
                os.replace(tmp, os.path.join(folder, name))
                arch = getattr(self.store, 'archive', None)
                if arch:
                    arch.copy_to(os.path.join(folder, 'Setu-Archive.db'))
                media = getattr(self.store, 'media', None)
                if media:
                    media.copy_to(os.path.join(folder, 'Setu Media'))   # dish photos: only new ones are copied
                for old in self.files()[self.cfg['keep']:]:
                    os.remove(os.path.join(folder, old))
                self.cfg.update({'lastAt': int(time.time() * 1000), 'lastFile': name, 'lastError': '', 'lastWhy': why})
                _write_json(self.cfg_path, self.cfg)
                return name
            except Exception as e:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                self.cfg.update({'lastError': str(e)[:200], 'lastErrorAt': int(time.time() * 1000)})
                _write_json(self.cfg_path, self.cfg)
                self.store.log(f'AUTO BACKUP FAILED to {folder!r}: {e!r}')
                raise

    def restore(self, name):
        """Put a backup file back as the database (the current data is backed up first)."""
        import gzip
        name = os.path.basename(str(name))
        if not (name.startswith('Setu-Backup-') and name.endswith('.json.gz')):
            raise ValueError('not a Setu backup file')
        with gzip.open(os.path.join(self.cfg['folder'], name), 'rt', encoding='utf-8') as f:
            doc = json.load(f)
        data = doc.get('data')
        if not isinstance(data, dict) or 'settings' not in data:
            raise ValueError('this backup file is damaged')
        self.run('before restore')
        with self.store.lock:
            self.store.write(data)
        media = getattr(self.store, 'media', None)
        if media:
            media.restore_from(os.path.join(self.cfg['folder'], 'Setu Media'))
        self.store.log(f'Restored from auto backup {name}')

    def _loop(self):
        time.sleep(60)
        while True:
            try:
                due = (time.time() * 1000 - self.cfg.get('lastAt', 0)) >= self.cfg['every'] * 3600 * 1000
                if self.cfg.get('on', True) and due and self.store.version > 0:
                    self.run('auto')
            except Exception:
                pass
            time.sleep(600)


# Static files the local server may hand out (an allow-list; everything else is 404)
PUBLIC_FILES = {'/', '/index.html', '/hotel_erp.html', '/manifest.json', '/sw.js', '/icon-192.png', '/icon-512.png', '/logo.png', '/favicon.ico',
                '/food/food-match.js', '/food/manifest.json', '/food/Foodpiolet_Manifest.json',
                '/Foodpiolet_Real_Photo_Licenses_And_Status.csv', '/Foodpiolet_Missing_Images_Report.md', '/Foodpiolet_Real_Photos.zip'}
MEDIA_PATH_RE = re.compile(r'^/api/media/(m_[0-9a-f]{32})(\.t)?$')
FOOD_FILE_RE = re.compile(r'^/(food/)?(lib|thumb|Foodpiolet_Real_Food_Images)/[a-zA-Z0-9_\-\.]{2,80}\.(webp|jpg|jpeg|png)$')   # Smart Food Visuals & Foodpiolet real food photos
LAUNCH_FILE = 'setu-launch.key'


def read_launch_key(data_dir):
    try:
        with open(os.path.join(data_dir, LAUNCH_FILE), 'r', encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


def open_store(data_dir):
    """JSON file (default) or SQLite: setu-storage.json {"engine": "sqlite"} is written only by a verified migration
    (setu_migrate.py --cutover). SETU_STORAGE=sqlite (development / tests only) migrates a test folder first."""
    flag = SQ.read_flag(data_dir)
    if os.environ.get('SETU_STORAGE') == 'sqlite' and flag.get('engine') != 'sqlite' and os.path.exists(os.path.join(data_dir, 'setu-db.json')):
        import setu_migrate
        # Start once on the JSON file first, exactly like an installed counter (credential hashing etc.), then migrate
        SetuStore(data_dir)
        rep = setu_migrate.migrate(data_dir, cutover=True)
        flag = SQ.read_flag(data_dir)
        if rep.get('status') != 'MIGRATED':
            print('SQLite migration did not complete:', rep.get('message'))
    elif os.environ.get('SETU_STORAGE') == 'sqlite' and flag.get('engine') != 'sqlite' and not os.path.exists(os.path.join(data_dir, SQ.DB_FILE)):
        # Development / tests only: a new empty test folder starts directly on SQLite (version 0 = first upload)
        os.makedirs(data_dir, exist_ok=True)
        SQ.SqliteDoc(os.path.join(data_dir, SQ.DB_FILE), create=True).close()
        SQ.write_flag(data_dir, {'engine': 'sqlite', 'created': int(time.time() * 1000), 'note': 'empty test folder (SETU_STORAGE=sqlite)'})
        flag = SQ.read_flag(data_dir)
    if flag.get('engine') == 'sqlite':
        return SqliteSetuStore(data_dir)
    return SetuStore(data_dir)


def start_server(base_dir, data_dir, port):
    store = open_store(data_dir)
    # Per-launch secret: the Setu window gets it in its address (#launch=…); a web page on this PC cannot read it
    store.launch = secrets.token_urlsafe(32)
    try:
        kp = os.path.join(data_dir, LAUNCH_FILE)
        with open(kp, 'w', encoding='utf-8') as f:
            f.write(store.launch)
        try:
            os.chmod(kp, 0o600)
        except OSError:
            pass
    except OSError as e:
        store.log(f'Launch key not written: {e!r}')
    cloud = CloudSync(store)
    store.on_write = cloud.wake.set
    store.log(f'Server start: port {port}, database version {store.version}')
    # Windows lets a second process bind a port with SO_REUSEADDR; two servers would split the data
    http.server.ThreadingHTTPServer.allow_reuse_address = os.name != 'nt'
    http.server.ThreadingHTTPServer.request_queue_size = 128
    updater = Updater(store)
    store.media = MEDIA.MediaStore(data_dir)
    store.autobackup = AutoBackup(store)
    store.wa = WhatsAppLink(store)
    atexit.register(lambda: store.autobackup.run('Setu closed') if store.version > 0 else None)
    httpd = http.server.ThreadingHTTPServer(('0.0.0.0', port), make_handler(base_dir, store, port, cloud, updater))
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def keep_server(base_dir, data_dir, port):
    while True:
        time.sleep(3)
        if setu_running(port) or port_busy(port):
            continue
        try:
            start_server(base_dir, data_dir, port)
            log_line(data_dir, 'Server taken over: the other Setu window was closed')
            return
        except OSError:
            continue   # the old copy still holds the port for a moment


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
            msg = (f'Another program is using port {port}, so Setu could not start.\n'
                   f'Close that program and start Setu again.')
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

    # A second Setu window uses the first one's server. If that first copy is closed, take
    # the server over, so this window keeps saving (its unsaved edits are pushed on retry).
    if already and not server_only:
        threading.Thread(target=keep_server, args=(base_dir, data_dir, port), daemon=True).start()

    if server_only:
        if already:
            print(f'Setu is already running: {url}')
            return
        print('Setu LAN server is running.')
        print(f'  This PC:        {url}')
        for ip in lan_ips():
            print(f'  Phone/Tablet:   http://{ip}:{port}/hotel_erp.html')
        print('Press Ctrl+C to stop.')
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    key = read_launch_key(data_dir)
    win_url = url + ('#launch=' + key if key else '')
    try:
        open_window(base_dir, data_dir, win_url)
    except Exception as e:
        # No WebView2 runtime (old Windows 10 / 7) or a broken pywebview: the server is already
        # up, so run Setu in the normal browser instead of closing without a word.
        log_line(data_dir, f'Desktop window failed, opening browser: {e!r}')
        import webbrowser
        webbrowser.open(win_url)
        msg = ('The Setu window could not open, so Setu opened in your browser.\n\n'
               'For the window, install the Microsoft Edge WebView2 Runtime '
               '(go.microsoft.com/fwlink/p/?LinkId=2124703).\n\n'
               'Close this message to continue billing; Setu keeps running.')
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, 'Setu', 0x40)
        except Exception:
            print(msg)
        if already:
            return
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return


def user_file_path(name):
    """A free file name in Downloads\\Setu (never overwrites)."""
    name = ''.join(c for c in os.path.basename(name) if c.isalnum() or c in '._- ()').strip(' .') or 'setu-file.txt'
    home = os.path.expanduser('~')
    root = next((d for d in (os.path.join(home, 'Downloads'), os.path.join(home, 'Documents')) if os.path.isdir(d)), home)
    folder = os.path.join(root, 'Setu')
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(name)
    path, n = os.path.join(folder, name), 2
    while os.path.exists(path):
        path, n = os.path.join(folder, f'{stem} ({n}){ext}'), n + 1
    return path


def save_user_file(name, text):   # text: str, or bytes (PDF)
    """Write a file the user asked for into Downloads\\Setu (never overwrites) and show it in Explorer."""
    name = ''.join(c for c in os.path.basename(name) if c.isalnum() or c in '._- ()').strip(' .') or 'setu-file.txt'
    home = os.path.expanduser('~')
    root = next((d for d in (os.path.join(home, 'Downloads'), os.path.join(home, 'Documents')) if os.path.isdir(d)), home)
    folder = os.path.join(root, 'Setu')
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(name)
    path, n = os.path.join(folder, name), 2
    while os.path.exists(path):
        path, n = os.path.join(folder, f'{stem} ({n}){ext}'), n + 1
    if isinstance(text, bytes):
        with open(path, 'wb') as f:
            f.write(text)
    else:
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
    if os.name == 'nt':
        try:
            import subprocess
            subprocess.Popen(['explorer', '/select,', path])
        except Exception:
            pass
    return path


def log_line(data_dir, msg):
    try:
        with open(os.path.join(data_dir, 'setu-server.log'), 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')
    except Exception:
        pass


def open_window(base_dir, data_dir, url):
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

    # Drop the window's cached pages so an updated EXE never shows the previous version.
    # Logins and settings (Local Storage) and the database (setu-db.json) are not touched.
    for sub in ('Service Worker', 'Cache', 'Code Cache'):
        shutil.rmtree(os.path.join(data_dir, 'EBWebView', 'Default', sub), ignore_errors=True)

    # Ask for Edge WebView2 by name: without it pywebview drops to old IE (MSHTML), where the
    # page does not work. Asking by name makes it fail here, so main() opens the browser.
    webview.start(
        gui='edgechromium' if os.name == 'nt' else None,
        private_mode=False,
        storage_path=data_dir,
        icon=icon_path
    )

if __name__ == '__main__':
    main()
