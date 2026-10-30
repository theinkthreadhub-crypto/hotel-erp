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
import re

APP_PORT = 8000
APP_VERSION = 'dev'   # stamped by installer/stamp-version.py when the EXE is built
# Setu Cloud the counter PC joins by itself (like Library ERP). SETU_CLOUD_URL overrides it.
DEFAULT_CLOUD_URL = os.environ.get('SETU_CLOUD_URL', 'https://setu-cloud.theinkthreadhub.workers.dev')
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

    def clean_and_validate_bills(self, data_obj):
        """
        S01 Financial Invariant Enforcement:
        1. Validates that every Split mode bill satisfies sum(pays.amt) == total.
        2. Deduplicates bills by idemKey (prevents replay/duplicate financial posting).
        3. Backfills durable identity and explicit payment status.
        """
        bills = data_obj.get('bills')
        if not isinstance(bills, list):
            return
        
        seen_idem = set()
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
                # Discard duplicate financial posting
                continue
            seen_idem.add(ik)
            
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
            if ik in their_idem_map:
                b = their_idem_map[ik]
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
            # The vendor deleted this hotel on the cloud: forget the link, join again (unless blocked)
            self.store.log(f"Hotel Setu Cloud: hotel {self.cfg.get('hotel')} not found on the cloud, joining again")
            self.cfg = {'enabled': True}
            _write_json(self.cfg_path, self.cfg)
            self.state = {}
            _write_json(self.state_path, self.state)
            self.auto = {'state': '', 'code': '', 'at': 0}
            self.relink_at = time.time()   # join again soon, not after the usual 30 minutes
            raise OSError('Hotel not found on the cloud, reconnecting')
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
            if path == '/api/version':
                return self.send_json(200, {'version': store.version})
            if path == '/api/db':
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
            if path.startswith('/api/wa/'):
                # WhatsApp link: connect / disconnect = manager; send a bill = any logged-in device
                role = self.role()
                if not role or (path not in ('/api/wa/send', '/api/wa/recharge') and role not in ('local', 'admin', 'manager', 'owner')):
                    return self.send_json(403, {'error': 'manager only'})
                try:
                    b = self.read_json() if int(self.headers.get('Content-Length') or 0) else {}
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
                    try:
                        store.write(data)
                    except Exception as e:
                        store.log(f'SAVE FAILED v{store.version + 1}: {e!r}')
                        return self.send_json(500, {'error': 'save failed: ' + str(e)})
                    if elev:
                        store.elev.pop(self.headers.get('X-Setu-Elev', ''), None)   # one approval = one save
                    out = {'version': store.version, 'savedAt': store.saved_at}
                    if changed or blocked:
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


def start_server(base_dir, data_dir, port):
    store = SetuStore(data_dir)
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
