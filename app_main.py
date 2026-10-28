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
import ssl
import email.utils
import base64
import copy
import hashlib

APP_PORT = 8000
APP_VERSION = 'dev'   # stamped by installer/stamp-version.py when the EXE is built
# Setu Cloud the counter PC joins by itself (like Library ERP). SETU_CLOUD_URL overrides it.
DEFAULT_CLOUD_URL = os.environ.get('SETU_CLOUD_URL', 'https://setu-cloud.theinkthreadhub.workers.dev')
AUTO_LINK_EVERY = 30 * 60   # seconds between join attempts while offline / not licensed yet
MAX_BODY = 200 * 1024 * 1024   # 200 MB upper bound for one database upload
KEEP_BACKUPS = 60              # daily backup files kept
print_lock = threading.Lock()  # one print job at a time keeps receipts from interleaving


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
            return 'admin', auth.get('ownerName') or 'Manager'
        for s in d.get('staff') or []:
            if not s.get('left') and s.get('access') and str(s.get('pin') or '') == pin:
                return {'manager': 'admin'}.get(s['access'], s['access']), s.get('name') or 'Staff'
        if pin == str(st.get('cashierPin') or ''):
            return 'cashier', 'Cashier'
        return None


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
            headers={'X-Setu-Sync': key or self.cfg['key'], 'X-Setu-Hotel': hotel or self.cfg['hotel'],
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

        def role(self):
            if self.is_local():
                return 'local'
            return store.tokens.get(self.headers.get('X-Setu-Token', ''))

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
                return self.send_json(200, {'setu': True, 'version': store.version, 'local': self.is_local(),
                                            'grace': cloud.grace() if cloud else None})
            if path == '/api/cloud':
                if not self.is_local():
                    return self.send_json(403, {'error': 'main counter only'})
                return self.send_json(200, cloud.public() if cloud else {'configured': False})
            if path == '/api/info':
                return self.send_json(200, {'setu': True, 'port': port, 'ips': lan_ips(), 'local': self.is_local()})
            if path == '/api/update':
                if not self.is_local() or not updater:
                    return self.send_json(403, {'error': 'main counter only'})
                return self.send_json(200, updater.state)
            if path == '/api/log':
                # Error Log screen: the newest lines of setu-server.log (main counter only)
                if not self.is_local():
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
            if not self.role():
                return self.send_json(401, {'error': 'pin required'})
            if path == '/api/qr/state':
                return self.qr_proxy('GET', path)
            if path == '/api/clock':
                # Setu Doctor: how far this PC's clock is from the cloud's (wrong date breaks licence and SSL)
                try:
                    with _urlopen(urllib.request.Request(DEFAULT_CLOUD_URL + '/api/ping', headers={'User-Agent': 'Setu-Main-Counter/1.0'}), 15) as r:
                        server = email.utils.parsedate_to_datetime(r.headers.get('Date')).timestamp()
                    return self.send_json(200, {'offset': int((time.time() - server) * 1000)})
                except Exception as e:
                    return self.send_json(200, {'offset': None, 'error': _net_reason(e)[1]})
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
            if path == '/api/login':
                try:
                    pin = self.read_json().get('pin')
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                found = store.check_pin(pin)
                if not found:
                    time.sleep(1)   # slow down PIN guessing
                    return self.send_json(403, {'error': 'wrong pin'})
                role, name = found
                token = store.add_token(role)
                return self.send_json(200, {'token': token, 'role': role, 'name': name})
            if path == '/api/ai':
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
            if path.startswith('/api/qr/'):
                # Any staff device may accept orders; QR settings and table codes are for the manager
                if not self.role() or (path in ('/api/qr/settings', '/api/qr/table') and self.role() not in ('local', 'admin')):
                    return self.send_json(403, {'error': 'manager only'})
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
                if not self.is_local():
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
                if not self.is_local() or not cloud:
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
                if not self.is_local() or not cloud:
                    return self.send_json(403, {'error': 'main counter only'})
                try:
                    body = self.read_json()
                    cloud.set_config(body.get('url'), body.get('hotel'), body.get('key'), bool(body.get('enabled', True)))
                except ValueError as e:
                    return self.send_json(400, {'error': str(e)})
                except Exception:
                    return self.send_json(400, {'error': 'bad request'})
                return self.send_json(200, cloud.public())
            if path == '/api/update':
                # Check / download / install a new Setu (main counter PC only)
                if not self.is_local() or not updater:
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
                    try:
                        store.write(data)
                    except Exception as e:
                        store.log(f'SAVE FAILED v{store.version + 1}: {e!r}')
                        return self.send_json(500, {'error': 'save failed: ' + str(e)})
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
    cloud = CloudSync(store)
    store.on_write = cloud.wake.set
    store.log(f'Server start: port {port}, database version {store.version}')
    # Windows lets a second process bind a port with SO_REUSEADDR; two servers would split the data
    http.server.ThreadingHTTPServer.allow_reuse_address = os.name != 'nt'
    updater = Updater(store)
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

    try:
        open_window(base_dir, data_dir, url)
    except Exception as e:
        # No WebView2 runtime (old Windows 10 / 7) or a broken pywebview: the server is already
        # up, so run Setu in the normal browser instead of closing without a word.
        log_line(data_dir, f'Desktop window failed, opening browser: {e!r}')
        import webbrowser
        webbrowser.open(url)
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
