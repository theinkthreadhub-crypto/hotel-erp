"""Big hotel on the real Windows installer (JSON engine, the default): 300,000 bills.

    python tools/bench/win_counter_scale.py <new installer.exe> <old installer.exe> <work folder> <results.json>

A. The OLD installer (the published one): install, start the installed program on 300,000 synthetic bills, send one
   whole-data save as the screen does. Expected before the fix: refused (save over 200 MB).
B. The NEW installer over it (upgrade, same data): the same save, three times: accepted and in setu-db.json; daily copies:
   yesterday's plain copy compressed, an older plain copy (from before the upgrade) left as it is; memory, times, disk.
Synthetic data only, in <work folder>; never a real hotel's data folder. Publishes nothing.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
NEW, OLD, WORK, OUT = [os.path.abspath(a) for a in sys.argv[1:5]]
EXE = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'AghanyaDevanyaERP', 'Aghanya-Devanya-Hotel-ERP.exe')
PORT = 8812
U = f'http://127.0.0.1:{PORT}'
DATA = os.path.join(WORK, 'hotel')
TOKEN = 'win-scale-test-' + os.urandom(6).hex()
R = {'machine': {'cpus': os.cpu_count(), 'ramGB': round(psutil.virtual_memory().total / 2 ** 30, 1)}}
MB = 1048576


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def save():
    with open(OUT, 'w') as f:
        json.dump(R, f, indent=1)


def install(inst):
    subprocess.run(['taskkill', '/F', '/IM', 'Aghanya-Devanya-Hotel-ERP.exe'], capture_output=True)
    r = subprocess.run([inst, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/NOCANCEL'], timeout=900)
    for _ in range(60):
        if os.path.exists(EXE):
            break
        time.sleep(1)
    subprocess.run(['taskkill', '/F', '/IM', 'Aghanya-Devanya-Hotel-ERP.exe'], capture_output=True)
    time.sleep(2)
    return r.returncode


def start():
    with open(os.path.join(DATA, 'setu-devices.json'), 'w', encoding='utf-8') as f:
        json.dump({TOKEN: 'admin'}, f)
    env = dict(os.environ, SETU_CLOUD_URL='http://127.0.0.1:9', SETU_BACKUP='off')
    p = subprocess.Popen([EXE, '--server', '--port', str(PORT), '--data', DATA], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    while time.time() - t0 < 900:
        try:
            urllib.request.urlopen(U + '/api/ping', timeout=2).read()
            return p, round(time.time() - t0, 1)
        except Exception:
            if p.poll() is not None:
                raise RuntimeError(f'program exited with {p.returncode}')
            time.sleep(0.3)
    raise RuntimeError('program did not start')


def stop(p):
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)], capture_output=True)
    subprocess.run(['taskkill', '/F', '/IM', 'Aghanya-Devanya-Hotel-ERP.exe'], capture_output=True)
    time.sleep(2)


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
    req = urllib.request.Request(U + path, data=body, method=method, headers={'Content-Type': 'application/json', 'X-Setu-Token': TOKEN})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            raw = r.read()
            return r.status, raw, round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), round(time.time() - t0, 1)
    except Exception as e:                       # connection closed by the counter (refused before reading)
        return 'error: ' + type(e).__name__ + ': ' + str(e)[:120], b'', round(time.time() - t0, 1)


def one_save(tag):
    s, raw, t = http('GET', '/api/db')
    cur = json.loads(raw)
    data = cur['data']
    data.setdefault('settings', {})['scaleCheck'] = tag
    body = json.dumps({'baseVersion': cur['version'], 'force': False, 'removed': [], 'data': data}, ensure_ascii=False).encode('utf-8')
    before = os.path.getmtime(os.path.join(DATA, 'setu-db.json'))
    s2, raw2, t2 = http('POST', '/api/db', body)
    with open(os.path.join(DATA, 'setu-db.json'), encoding='utf-8') as f:
        on_disk = json.load(f)['data'].get('settings', {}).get('scaleCheck')
    return {'loadMB': round(len(raw) / MB, 1), 'loadS': t, 'saveMB': round(len(body) / MB, 1), 'saveStatus': s2, 'saveS': t2,
            'fileChanged': os.path.getmtime(os.path.join(DATA, 'setu-db.json')) != before, 'inFile': on_disk == tag}


def folder_mb(d):
    return round(sum(os.path.getsize(os.path.join(d, x)) for x in os.listdir(d)) / MB, 1) if os.path.isdir(d) else 0


def main():
    os.makedirs(WORK, exist_ok=True)
    shutil.rmtree(DATA, ignore_errors=True)
    t0 = time.time()
    out = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'db-benchmark', 'make_dataset.py'), DATA, '300000', '--per-day', '300',
                          '--end', date.today().isoformat()], capture_output=True, text=True, timeout=3600)
    R['dataset'] = {**json.loads(out.stdout.strip().splitlines()[-1]), 'seconds': round(time.time() - t0)}
    log('dataset', R['dataset'])
    save()

    # A. published installer
    R['A_old'] = {'installExit': install(OLD)}
    p, R['A_old']['startS'] = start()
    pk = Peak(p)
    R['A_old']['memIdleMB'] = round(rss(p))
    try:
        R['A_old']['save'] = one_save('old-1')
    except Exception as e:
        R['A_old']['save'] = {'error': repr(e)[:300]}
    pk.on = False
    R['A_old']['memPeakMB'] = round(pk.v)
    stop(p)
    log('A old', R['A_old'])
    save()

    # Daily copies as an older version leaves them: yesterday's and an 8-day-old plain copy
    bk = os.path.join(DATA, 'Backups')
    os.makedirs(bk, exist_ok=True)
    y = (date.today() - timedelta(days=1)).isoformat()
    o = (date.today() - timedelta(days=8)).isoformat()
    for d in (y, o):
        shutil.copy2(os.path.join(DATA, 'setu-db.json'), os.path.join(bk, f'setu-{d}.json'))
    R['backupsBeforeMB'] = folder_mb(bk)

    # B. new installer over it (upgrade), same data
    R['B_new'] = {'installExit': install(NEW)}
    p, R['B_new']['startS'] = start()
    pk = Peak(p)
    R['B_new']['memIdleMB'] = round(rss(p))
    R['B_new']['saves'] = []
    for i in range(3):
        R['B_new']['saves'].append(one_save(f'new-{i}'))
        log('B save', R['B_new']['saves'][-1])
        save()
    for _ in range(240):                       # the compression runs in the background after a save
        if os.path.exists(os.path.join(bk, f'setu-{y}.json.gz')) and not os.path.exists(os.path.join(bk, f'setu-{y}.json')):
            break
        time.sleep(1)
    pk.on = False
    R['B_new']['memPeakMB'] = round(pk.v)
    stop(p)
    R['backupsAfter'] = {x: round(os.path.getsize(os.path.join(bk, x)) / MB, 1) for x in sorted(os.listdir(bk))}
    R['backupsAfterMB'] = folder_mb(bk)
    R['dataFileMB'] = round(os.path.getsize(os.path.join(DATA, 'setu-db.json')) / MB, 1)

    a, b = R['A_old'].get('save', {}), R['B_new']['saves']
    R['checks'] = {
        'old installer refused the big save': a.get('saveStatus') != 200 and not a.get('inFile'),
        'new installer: 3 of 3 saves reached setu-db.json': all(s.get('saveStatus') == 200 and s.get('inFile') for s in b),
        "yesterday's copy compressed": f'setu-{y}.json.gz' in R['backupsAfter'] and f'setu-{y}.json' not in R['backupsAfter'],
        'older pre-upgrade copy left as it is': f'setu-{o}.json' in R['backupsAfter'],
        "today's copy plain": f'setu-{date.today().isoformat()}.json' in R['backupsAfter'],
    }
    save()
    log('RESULT', json.dumps(R, indent=1))
    bad = [k for k, v in R['checks'].items() if not v]
    print('WINDOWS COUNTER SCALE:', 'ALL PASS' if not bad else 'FAILED: ' + '; '.join(bad), flush=True)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
