"""Phase 2b benchmark on a migrated SQLite folder (synthetic data only; development tool).

    python3 tools/db-benchmark/p2b_bench.py <migratedFolder> <out.json> [--mode background|commit] [--runs 3] [--levels 1,20,50,100]
           [--today YYYY-MM-DD]

Measures, on the real counter server (app_main.py --server):
  * server start, server memory (RSS) at rest / after a device load / peak during saves and exports
  * device load (GET /api/db: recent bills + totals of older ones): bytes and time
  * device saves the way the app sends them (POST /api/ops: bill + KOT + running numbers, with stock use), at
    1 / 20 / 50 / 100 clients, each level repeated --runs times: P50 / P95 / P99, throughput, errors
  * the same through the native settle endpoint at 50 clients (the Phase 2 anomaly)
  * write-log (WAL) size sampled every 50 ms, checkpoint statistics from /api/q/status
  * change feed, older-bill pages, history totals, streamed full export (GET /api/db?full=1)
  * reconciliation after the run from the database file: every acknowledged bill present once, numbers unique,
    integrity_check ok
--exe <path>: run the built program (Windows EXE) instead of app_main.py.
--mode: background = checkpoints in a separate thread (Phase 2b default); commit = SQLite's own, inside commits.
"""
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
args = sys.argv[1:]
DIR, OUT = os.path.abspath(args[0]), args[1]
opt = lambda k, d: args[args.index(k) + 1] if k in args else d   # noqa: E731
MODE, RUNS = opt('--mode', 'background'), int(opt('--runs', '3'))
LEVELS = [int(x) for x in opt('--levels', '1,20,50,100').split(',')]
PORT = 8700 + (os.getpid() % 200)
U = f'http://127.0.0.1:{PORT}'
MGR_PIN = '739146'


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(len(xs) * p))], 1) if xs else None


def rss(pid):
    if not os.path.exists('/proc'):
        try:
            import psutil   # Windows: pip install psutil
            return round(psutil.Process(pid).memory_info().rss / 1048576, 1)
        except Exception:
            return None
    try:
        with open(f'/proc/{pid}/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        return None


class Sampler(threading.Thread):
    def __init__(self, pid):
        super().__init__(daemon=True)
        self.pid, self.stop, self.peak_rss, self.peak_wal, self.walls = pid, False, 0, 0, []

    def run(self):
        wal = os.path.join(DIR, 'setu.sqlite-wal')
        while not self.stop:
            r = rss(self.pid) or 0
            w = os.path.getsize(wal) if os.path.exists(wal) else 0
            self.peak_rss, self.peak_wal = max(self.peak_rss, r), max(self.peak_wal, w)
            self.walls.append(w)
            time.sleep(0.05)


def call(path, body=None, tok=None, raw=False, timeout=600):
    h = {'Content-Type': 'application/json', 'X-Setu-Launch': LAUNCH}
    if tok:
        h['X-Setu-Token'] = tok
    req = urllib.request.Request(U + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method='POST' if body is not None else 'GET')
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read()
            return r.status, (txt if raw else json.loads(txt)), (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}'), (time.perf_counter() - t0) * 1000
    except Exception as e:
        return 0, {'error': repr(e)}, (time.perf_counter() - t0) * 1000


if __name__ == '__main__':
    R = {'folder': os.path.basename(DIR), 'mode': MODE, 'runs': RUNS, 'machine': {'cpus': os.cpu_count(), 'sqlite': sqlite3.sqlite_version, 'python': sys.version.split()[0]}}
    con = sqlite3.connect(os.path.join(DIR, 'setu.sqlite'))
    R['billsBefore'] = con.execute('SELECT COUNT(*) FROM bills').fetchone()[0]
    TODAY = opt('--today', con.execute('SELECT MAX(date) FROM bills').fetchone()[0])
    con.close()
    R['dbMB'] = round(os.path.getsize(os.path.join(DIR, 'setu.sqlite')) / 1048576, 1)
    env = dict(os.environ, SETU_CHECKPOINT=MODE)
    t0 = time.time()
    EXE = opt('--exe', '')   # the built Windows program instead of app_main.py
    cmd = ([EXE] if EXE else [sys.executable, os.path.join(ROOT, 'app_main.py')]) + ['--server', '--port', str(PORT), '--data', DIR]
    R['program'] = os.path.basename(EXE) if EXE else 'app_main.py'
    srv = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(6000):
            try:
                urllib.request.urlopen(U + '/api/ping', timeout=1).read()
                break
            except Exception:
                time.sleep(0.1)
        R['serverStartSeconds'] = round(time.time() - t0, 1)
        LAUNCH = open(os.path.join(DIR, 'setu-launch.key')).read().strip()
        s, j, _ = call('/api/login', {'pin': MGR_PIN})
        TOK = j['token']
        time.sleep(2)
        R['rssAtRestMB'] = rss(srv.pid)
        # ---- device load (recent bills + totals of older bills) ----
        samp = Sampler(srv.pid)
        samp.start()
        loads = []
        for i in range(3):
            s, body, ms = call(f'/api/db?today={TODAY}', tok=TOK, raw=True)
            loads.append(ms)
        meta = json.loads(body)['meta']
        R['deviceLoad'] = {'status': s, 'bytes': len(body), 'MB': round(len(body) / 1048576, 1), 'billsSent': len(json.loads(body)['data']['bills']),
                           'olderBillsOnCounterOnly': meta['win']['older'], 'windowFrom': meta['win']['from'], 'firstMs': round(loads[0]), 'nextMs': [round(x) for x in loads[1:]]}
        R['rssAfterLoadMB'] = rss(srv.pid)
        s, db, _ = call(f'/api/db?today={TODAY}', tok=TOK)
        seq = db['data']['seq']
        stock = [x['id'] for x in db['data']['stock'][:3]]
        menu = db['data']['menu'][0]
        acked, lock = [], threading.Lock()
        counter = {'n': int(seq.get('bill') or 0) + 1, 'k': int(seq.get('kot') or 0) + 1}

        def device_save(tag):
            with lock:
                n, k = counter['n'], counter['k']
                counter['n'] += 1
                counter['k'] += 1
            bid = f'b2b-{tag}-{time.time_ns()}'
            bill = {'id': bid, 'idemKey': 'idem_' + bid, 'mv': 1, 'no': n, 'kot': k, 'date': TODAY, 'time': '13:00', 'channel': 'Takeaway', 'table': 'Takeaway', 'mode': 'Cash',
                    'items': [{'mid': menu['id'], 'name': menu['name'], 'price': 100, 'qty': 1}], 'sub': 100, 'disc': 0, 'tax': 5, 'taxable': 100, 'total': 105, 'round': 0,
                    'used': [{'sid': stock[0], 'qty': 0.25}], 'paymentStatus': 'recorded', 'by': 'Bench'}
            kot = {'id': 'k-' + bid, 'no': k, 'date': TODAY, 'time': '13:00', 'table': 'Takeaway', 'items': [{'mid': menu['id'], 'name': menu['name'], 'qty': 1}], 'status': 'new'}
            ops = [{'k': 'bills', 'up': [bill]}, {'k': 'kots', 'up': [kot]}, {'k': 'seq', 'set': {**seq, 'bill': n, 'kot': k}}]
            s, r, ms = call('/api/ops', {'bv': -1, 'id': 'op-' + bid, 'ops': ops}, tok=TOK)
            if s == 200:
                with lock:
                    acked.append(bid)
            return s, ms

        def level(c, total, fn):
            lat, st, lk = [], [], threading.Lock()
            per = max(1, total // c)

            def w(i):
                for j_ in range(per):
                    s_, ms_ = fn(f'{c}-{i}-{j_}')
                    with lk:
                        lat.append(ms_)
                        st.append(s_)
            t1 = time.time()
            ts = [threading.Thread(target=w, args=(i,)) for i in range(c)]
            [t.start() for t in ts]
            [t.join() for t in ts]
            el = time.time() - t1
            return {'clients': c, 'n': len(lat), 'p50': pct(lat, .5), 'p95': pct(lat, .95), 'p99': pct(lat, .99), 'max': round(max(lat), 1),
                    'perSecond': round(len(lat) / el, 1), 'errors': sum(1 for x in st if x != 200), 'seconds': round(el, 1)}
        R['opsSaves'] = {}
        for c in LEVELS:
            runs = []
            for r_ in range(RUNS):
                w0 = len(samp.walls)
                x = level(c, max(400, c * 4), device_save)
                walls = samp.walls[w0:]
                x['walMaxMB'] = round(max(walls or [0]) / 1048576, 1)
                s, stt, _ = call('/api/q/status', tok=TOK)
                x['checkpoint'] = (stt or {}).get('checkpoint')
                runs.append(x)
                print(f'[{MODE}] ops {c} clients run {r_ + 1}: {json.dumps(x)}', flush=True)
            R['opsSaves'][str(c)] = runs
        # ---- native settle at 50 clients (the Phase 2 anomaly level) ----
        def settle(tag):
            key = f'st-{tag}-{time.time_ns()}'
            s, r, ms = call('/api/bill/settle', {'idemKey': key, 'bill': {'id': 'n' + key, 'table': '', 'channel': 'Takeaway', 'mode': 'Cash', 'items': [{'mid': menu['id'], 'name': 'x', 'price': 100, 'qty': 1}],
                                                                           'total': 105, 'date': TODAY, 'time': '13:00', 'used': [{'sid': stock[1], 'qty': 0.25}], 'mv': 1}}, tok=TOK)
            if s == 200:
                with lock:
                    acked.append(r['bill']['id'])
            return s, ms
        R['settle50'] = []
        for r_ in range(RUNS):
            x = level(50, 400, settle)
            R['settle50'].append(x)
            print(f'[{MODE}] settle 50 clients run {r_ + 1}: {json.dumps(x)}', flush=True)
        # ---- reads ----
        s, v, _ = call('/api/version', tok=TOK)
        feed = [call(f'/api/changes?since={v["version"] - 20}', tok=TOK)[2] for _ in range(10)]
        R['changeFeedMs'] = {'p50': pct(feed, .5), 'p95': pct(feed, .95)}
        old = time.strftime('%Y-%m-%d', time.localtime(time.mktime(time.strptime(TODAY, '%Y-%m-%d')) - 200 * 86400))
        s, pg, ms = call(f'/api/q/bill-range?from={old}&to={old}&limit=2000', tok=TOK)
        R['olderDayLoad'] = {'date': old, 'bills': len(pg.get('rows', [])), 'ms': round(ms)}
        hs = [call(f'/api/q/hist?from={meta["win"]["from"]}', tok=TOK)[2] for _ in range(5)]
        R['histTotalsMs'] = {'p50': pct(hs, .5), 'max': round(max(hs))}
        rss0 = samp.peak_rss
        samp.peak_rss = 0
        s, body, ms = call('/api/db?full=1', tok=TOK, raw=True, timeout=3600)
        R['fullExport'] = {'status': s, 'MB': round(len(body) / 1048576, 1), 'seconds': round(ms / 1000, 1), 'peakRssMB': samp.peak_rss}
        body = None
        samp.peak_rss = max(rss0, samp.peak_rss)
        s, stt, _ = call('/api/q/status', tok=TOK)
        R['statusAtEnd'] = {k: stt.get(k) for k in ('rssMB', 'walBytes', 'dbBytes', 'stats', 'checkpoint')}
        R['peakRssMB'], R['peakWalMB'] = samp.peak_rss, round(samp.peak_wal / 1048576, 1)
        samp.stop = True
    finally:
        srv.terminate()
        srv.wait(60)
    # ---- reconciliation from the file ----
    con = sqlite3.connect(os.path.join(DIR, 'setu.sqlite'))
    have = {r[0] for r in con.execute('SELECT id FROM bills')}
    nos = [r[0] for r in con.execute('SELECT CAST(no AS INTEGER) FROM bills WHERE COALESCE(imported, 0) = 0')]
    R['reconciliation'] = {'acknowledgedBills': len(acked), 'acknowledgedLost': sum(1 for b in acked if b not in have), 'duplicateNumbers': len(nos) - len(set(nos)),
                           'duplicateIds': con.execute('SELECT COUNT(*) - COUNT(DISTINCT id) FROM bills').fetchone()[0], 'integrity': con.execute('PRAGMA integrity_check').fetchone()[0],
                           'billsAfter': len(have)}
    R['reconciliation']['pass'] = R['reconciliation']['acknowledgedLost'] == 0 and R['reconciliation']['duplicateNumbers'] == 0 and R['reconciliation']['integrity'] == 'ok'
    con.close()
    with open(OUT, 'w') as f:
        json.dump(R, f, indent=1)
    print(json.dumps({k: R[k] for k in ('serverStartSeconds', 'rssAtRestMB', 'rssAfterLoadMB', 'deviceLoad', 'peakRssMB', 'peakWalMB', 'reconciliation')}, indent=1))
