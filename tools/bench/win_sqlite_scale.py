"""Big hotel on the real Windows installer with SQLite storage: 300,000 bills.

    python tools/bench/win_sqlite_scale.py <installer.exe> <work folder> <results.json>

Installs the installer, makes 300,000 synthetic bills in the JSON format, starts the installed program with
SETU_STORAGE=sqlite (it migrates the data and verifies it), then bills like a busy counter: 300 bills one after the
other through /api/bill/settle (the screen's Settle), with timing, memory and the daily backup size.
Synthetic data only, in <work folder>; never a real hotel's data folder. Publishes nothing.
"""
import json
import os
import shutil
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date

import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
INST, WORK, OUT = [os.path.abspath(a) for a in sys.argv[1:4]]
EXE = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'AghanyaDevanyaERP', 'Aghanya-Devanya-Hotel-ERP.exe')
PORT = 8813
U = f'http://127.0.0.1:{PORT}'
DATA = os.path.join(WORK, 'hotel-sqlite')
TOKEN = 'win-sqlite-test-' + os.urandom(6).hex()
MB = 1048576
R = {'machine': {'cpus': os.cpu_count(), 'ramGB': round(psutil.virtual_memory().total / 2 ** 30, 1)}}


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def save():
    with open(OUT, 'w') as f:
        json.dump(R, f, indent=1)


def rss(p):
    try:
        pr = psutil.Process(p.pid)
        return sum(x.memory_info().rss for x in [pr] + pr.children(recursive=True)) / MB
    except Exception:
        return 0


class Peak:
    def __init__(self, p):
        self.p, self.v, self.on = p, 0, True
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while self.on:
            self.v = max(self.v, rss(self.p))
            time.sleep(0.25)


def http(method, path, body=None):
    req = urllib.request.Request(U + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={'Content-Type': 'application/json', 'X-Setu-Token': TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def main():
    os.makedirs(WORK, exist_ok=True)
    subprocess.run(['taskkill', '/F', '/IM', 'Aghanya-Devanya-Hotel-ERP.exe'], capture_output=True)
    R['installExit'] = subprocess.run([INST, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/NOCANCEL'], timeout=900).returncode
    time.sleep(3)
    subprocess.run(['taskkill', '/F', '/IM', 'Aghanya-Devanya-Hotel-ERP.exe'], capture_output=True)
    # A new install (empty data folder, no SETU_STORAGE): the installed program starts on SQLite by itself
    fresh = os.path.join(WORK, 'fresh')
    shutil.rmtree(fresh, ignore_errors=True)
    os.makedirs(fresh)
    with open(os.path.join(fresh, 'setu-devices.json'), 'w', encoding='utf-8') as f:
        json.dump({TOKEN: 'admin'}, f)
    env0 = {k: v for k, v in os.environ.items() if k not in ('SETU_STORAGE', 'SETU_NEW_ENGINE')}
    p0 = subprocess.Popen([EXE, '--server', '--port', str(PORT), '--data', fresh], env=dict(env0, SETU_CLOUD_URL='http://127.0.0.1:9', SETU_BACKUP='off'),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(300):
        try:
            urllib.request.urlopen(U + '/api/ping', timeout=2).read()
            break
        except Exception:
            time.sleep(0.5)
    R['newInstallEngine'] = http('GET', '/api/q/status')[1].get('engine') or 'json'
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(p0.pid)], capture_output=True)
    subprocess.run(['taskkill', '/F', '/IM', 'Aghanya-Devanya-Hotel-ERP.exe'], capture_output=True)
    time.sleep(2)
    log('new install engine', R['newInstallEngine'])
    shutil.rmtree(DATA, ignore_errors=True)
    out = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'db-benchmark', 'make_dataset.py'), DATA, '300000', '--per-day', '300',
                          '--end', date.today().isoformat()], capture_output=True, text=True, timeout=3600)
    R['dataset'] = json.loads(out.stdout.strip().splitlines()[-1])
    with open(os.path.join(DATA, 'setu-devices.json'), 'w', encoding='utf-8') as f:
        json.dump({TOKEN: 'admin'}, f)
    save()

    # First start: the program migrates JSON -> SQLite (verified) before it serves
    env = dict(os.environ, SETU_STORAGE='sqlite', SETU_CLOUD_URL='http://127.0.0.1:9', SETU_BACKUP='off')
    t0 = time.time()
    p = subprocess.Popen([EXE, '--server', '--port', str(PORT), '--data', DATA], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pk = Peak(p)
    while time.time() - t0 < 3000:
        try:
            urllib.request.urlopen(U + '/api/ping', timeout=2).read()
            break
        except Exception:
            if p.poll() is not None:
                raise RuntimeError(f'program exited with {p.returncode}')
            time.sleep(0.5)
    R['migrateAndStartS'] = round(time.time() - t0, 1)
    R['migrateMemPeakMB'] = round(pk.v)
    pk.on = False
    s, st = http('GET', '/api/q/status')
    R['engine'] = st.get('engine')
    R['dbMB'] = round((st.get('dbBytes') or 0) / MB, 1)
    R['memIdleMB'] = round(rss(p))
    save()
    log('migrated', R)

    # A busy counter: 300 bills, one after the other
    pk = Peak(p)
    times, errors = [], 0
    for i in range(300):
        b = {'id': f'win-sq-{i}', 'table': '', 'channel': 'Takeaway', 'mode': ['Cash', 'UPI', 'Card'][i % 3], 'date': date.today().isoformat(),
             'time': '13:00', 'items': [{'mid': 'mnu1', 'name': 'Dish 1', 'price': 120, 'qty': 1 + i % 3}], 'used': []}
        b['sub'] = 120 * b['items'][0]['qty']
        b['tax'] = round(b['sub'] * 0.05, 2)
        b['total'] = round(b['sub'] * 1.05)
        t = time.time()
        s, r = http('POST', '/api/bill/settle', {'idemKey': f'idem-win-sq-{i}', 'bill': b})
        times.append((time.time() - t) * 1000)
        if s != 200:
            errors += 1
    pk.on = False
    times.sort()
    R['settle'] = {'n': 300, 'errors': errors, 'p50ms': round(statistics.median(times), 1), 'p95ms': round(times[int(len(times) * 0.95) - 1], 1),
                   'maxms': round(times[-1], 1), 'memPeakMB': round(pk.v)}
    s, q = http('GET', '/api/q/bills?from=2000-01-01&to=2100-01-01&limit=1')
    R['billsAfter'] = q.get('total', None)
    time.sleep(20)                                     # the daily backup runs when the counter is quiet
    bk = os.path.join(DATA, 'Backups')
    R['backups'] = {x: round(os.path.getsize(os.path.join(bk, x)) / MB, 1) for x in sorted(os.listdir(bk))} if os.path.isdir(bk) else {}
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)], capture_output=True)
    subprocess.run(['taskkill', '/F', '/IM', 'Aghanya-Devanya-Hotel-ERP.exe'], capture_output=True)
    R['checks'] = {
        'a new install starts on SQLite': R.get('newInstallEngine') == 'sqlite',
        'migrated to SQLite': R['engine'] == 'sqlite',
        '300 bills, no error': errors == 0,
        'a bill in under 1 second (95%)': R['settle']['p95ms'] < 1000,
        'memory under 1 GB while billing': R['settle']['memPeakMB'] < 1024,
    }
    save()
    log('RESULT', json.dumps(R, indent=1))
    bad = [k for k, v in R['checks'].items() if not v]
    print('WINDOWS SQLITE SCALE:', 'ALL PASS' if not bad else 'FAILED: ' + '; '.join(bad), flush=True)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
