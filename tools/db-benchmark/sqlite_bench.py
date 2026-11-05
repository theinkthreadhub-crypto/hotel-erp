"""Phase 2 SQLite benchmark on synthetic data (isolated temp folder, local counter server only).

    python3 tools/db-benchmark/sqlite_bench.py <poolDataFolder> <bills> <outDir> [--days N]

<poolDataFolder> = a bench.cjs data folder (records made by the app's own code). Its bills are replicated to
<bills> bills at 1,000 a day (KOTs kept 7 days and audit capped at 20,000 like the app). Then:
migration (import + full verification), server start, native bill settle / cancel latency, 1-100 concurrent
clients, whole-document uploads (the path the current UI still uses for KOT, purchase, stock and expenses),
indexed queries, full download, backup + restore, file / WAL sizes, memory, and a final reconciliation.
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

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
import setu_sqlite as S      # noqa: E402
import setu_migrate as M     # noqa: E402
import setu_security as SEC  # noqa: E402

POOL, NBILLS, OUT = sys.argv[1], int(sys.argv[2]), sys.argv[3]
PER_DAY = 1000
PORT = 8700 + (NBILLS // 1000) % 90
U = f'http://127.0.0.1:{PORT}'
MGR = '739146'


def q(a, p):
    if not a:
        return None
    s = sorted(a)
    return round(s[min(len(s) - 1, int(p * len(s)))], 1)


def stat(a):
    return {'n': len(a), 'p50': q(a, 0.5), 'p95': q(a, 0.95), 'max': round(max(a), 1) if a else None}


def add_days(d, n):
    import datetime
    return (datetime.date.fromisoformat(d) + datetime.timedelta(days=n)).isoformat()


def build():
    pool = json.load(open(os.path.join(POOL, 'setu-db.json')))['data']
    bills = [b for b in pool['bills'] if not b.get('cancelled')]
    kots = pool.get('kots') or []
    tx_by, mv_by, au_by = {}, {}, {}
    for t in pool.get('txns') or []:
        tx_by.setdefault(t['date'], []).append(t)
    for m in pool.get('moves') or []:
        if m.get('type') != 'open':
            mv_by.setdefault(m['date'], []).append(m)
    for a in pool.get('audit') or []:
        au_by.setdefault(a.get('date'), []).append(a)
    pdays = sorted(tx_by)
    ndays = (NBILLS + PER_DAY - 1) // PER_DAY
    out = dict(pool)
    out.update(bills=[], kots=[], txns=[], moves=[m for m in pool.get('moves') or [] if m.get('type') == 'open'], audit=[], att={}, kaccha={})
    no = kno = bi = ki = 0
    att = next(iter((pool.get('att') or {}).values()), {})
    for d in range(ndays):
        date, sfx, pd = add_days('2025-01-06', d), '-' + format(d, 'x'), pdays[d % len(pdays)]
        for i in range(min(PER_DAY, NBILLS - no)):
            b = bills[bi % len(bills)]
            bi += 1
            no += 1
            kno += 1
            nb = dict(b, id=f'{b["id"]}{sfx}-{i}', date=date, no=no, kot=kno, idemKey=f'{b.get("idemKey", "idem")}{sfx}-{i}')
            if b.get('orderSessionId'):
                nb['orderSessionId'] = f'{b["orderSessionId"]}{sfx}-{i}'
            out['bills'].append(nb)
            if kots and d >= ndays - 8:
                k = kots[ki % len(kots)]
                ki += 1
                out['kots'].append(dict(k, id=f'{k.get("id", "k")}{sfx}-{i}', no=kno, date=date))
        for i, t in enumerate(tx_by.get(pd, [])):
            nt = dict(t, id=f'{t["id"]}{sfx}-{i}', date=date)
            if isinstance(t.get('inv'), dict):
                nt['inv'] = dict(t['inv'], id=t['inv']['id'] + sfx)
            out['txns'].append(nt)
        for i, m in enumerate(mv_by.get(pd, [])):
            out['moves'].append(dict(m, id=f'{m["id"]}{sfx}-{i}', date=date))
        for i, a in enumerate(au_by.get(pd, [])):
            out['audit'].append(dict(a, id=f'{a.get("id", "a")}{sfx}-{i}', date=date))
        out['att'][date] = att
    out['audit'] = out['audit'][-20000:]
    out['seq'] = dict(pool.get('seq') or {}, bill=no, kot=kno)
    # stock quantities consistent with the replicated movements (as the app's stockRecalc would leave them)
    exp = M.legacy_stock(out)
    out['stock'] = [dict(s, qty=exp.get(s['id'], s.get('qty'))) for s in pool['stock']]
    return out, ndays


def rss_mb(pid):
    try:
        for line in open(f'/proc/{pid}/status'):
            if line.startswith('VmHWM:'):
                return round(int(line.split()[1]) / 1024)
    except Exception:
        return None


class Api:
    def __init__(self):
        self.launch = open(os.path.join(DIR, 'setu-launch.key')).read().strip()
        self.tok = self.call('/api/login', {'pin': MGR}, auth=False)[1]['token']

    def call(self, path, body=None, auth=True, raw=False):
        h = {'Content-Type': 'application/json', 'X-Setu-Launch': self.launch}
        if auth:
            h['X-Setu-Token'] = self.tok
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        req = urllib.request.Request(U + path, data=data, headers=h, method='POST' if body is not None else 'GET')
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                txt = r.read()
                ms = (time.perf_counter() - t0) * 1000
                return r.status, (txt if raw else json.loads(txt)), ms
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}'), (time.perf_counter() - t0) * 1000


def bill(tag, total=105.0, mode='Cash'):
    return {'id': f'bb-{tag}', 'table': '', 'channel': 'Takeaway', 'mode': mode, 'items': [{'mid': 'mnu1', 'name': 'Dish 2', 'price': 100, 'qty': 1}],
            'sub': 100, 'tax': 5, 'total': total, 'date': LAST, 'time': '13:00', 'used': [{'sid': 'stk1', 'qty': 0.25}]}


if __name__ == '__main__':
    R = {'bills': NBILLS, 'perDay': PER_DAY, 'machine': {'cpus': os.cpu_count(), 'sqlite': S.sqlite3.sqlite_version, 'python': sys.version.split()[0]}}
    DIR = os.path.join(os.path.abspath(OUT), f'sqlite-{NBILLS}')
    REUSE = os.environ.get('REUSE') == '1' and S.read_flag(DIR).get('engine') == 'sqlite'
    if REUSE:
        # A folder this script already built and migrated (e.g. after an interruption): measure the server only
        ndays = (NBILLS + PER_DAY - 1) // PER_DAY
        LAST = add_days('2025-01-06', ndays - 1)
        R.update(days=ndays, reusedMigratedFolder=True, dbMB=round(os.path.getsize(os.path.join(DIR, S.DB_FILE)) / 1048576, 1),
                 jsonMB=round(os.path.getsize(os.path.join(DIR, 'setu-db.json')) / 1048576, 1))
        try:
            R['migration'] = json.load(open(os.path.join(DIR, 'migration', 'migration-report.json')))
            R['migration'] = {k: R['migration'].get(k) for k in ('status', 'message', 'import_seconds', 'verify_seconds')}
        except Exception:
            R['migration'] = {'status': 'MIGRATED'}
        BIG = NBILLS >= 300000
    else:
        shutil.rmtree(DIR, ignore_errors=True)
        os.makedirs(DIR)
    t0 = time.time()
    doc, ndays = build() if not REUSE else (None, ndays)
    if not REUSE:
        LAST = add_days('2025-01-06', ndays - 1)
        raw = json.dumps({'version': 1, 'savedAt': 1, 'data': doc}, ensure_ascii=False)
        with open(os.path.join(DIR, 'setu-db.json'), 'w', encoding='utf-8') as f:
            f.write(raw)
        R['days'] = ndays
        R['jsonMB'] = round(len(raw.encode()) / 1048576, 1)
        raw = None
        BIG = NBILLS >= 300000
        nb = len(doc['bills'])
        doc = None                      # free the dataset before the migration process builds its own
        import gc
        gc.collect()
        R['buildSeconds'] = round(time.time() - t0, 1)
        print(f'[{NBILLS}] dataset {R["jsonMB"]} MB JSON, {nb} bills, {ndays} days', flush=True)
        # ---- migration in its own process (measures its memory) ----
        t0 = time.time()
        p = subprocess.run([sys.executable, '-c', f'import sys,json,resource; sys.path.insert(0,{ROOT!r}); import setu_migrate as M; r=M.migrate({DIR!r}, cutover=True); '
                            'r["rss_mb"]=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024); print(json.dumps({k:r.get(k) for k in ("status","message","import_seconds","verify_seconds","rss_mb")})); '
                            'print(json.dumps([c for c in r["checks"] if not c["pass"]]))'], capture_output=True, text=True)
        lines = p.stdout.strip().splitlines()
        R['migration'] = json.loads(lines[0]) if lines else {'error': p.stderr[-500:]}
        R['migration']['notPassed'] = json.loads(lines[1]) if len(lines) > 1 else None
        R['migration']['wallSeconds'] = round(time.time() - t0, 1)
        dbp = os.path.join(DIR, S.DB_FILE)
        R['dbMB'] = round(os.path.getsize(dbp) / 1048576, 1) if os.path.exists(dbp) else None
        print(f'[{NBILLS}] migration', R['migration'], 'db', R['dbMB'], 'MB', flush=True)
        if R['migration'].get('status') != 'MIGRATED':
            json.dump(R, open(os.path.join(OUT, f'sqlite-bench-{NBILLS}.json'), 'w'), indent=1)
            sys.exit(1)
    dbp = os.path.join(DIR, S.DB_FILE)
    # ---- counter server on SQLite ----
    t0 = time.time()
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, 'app_main.py'), '--server', '--port', str(PORT), '--data', DIR], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(3000):
        try:
            urllib.request.urlopen(U + '/api/ping', timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    R['serverStartSeconds'] = round(time.time() - t0, 1)
    api = Api()
    try:
        # ---- native bill settle, one at a time ----
        lat = []
        for i in range(200):
            s, r, ms = api.call('/api/bill/settle', {'idemKey': f'seq-{i}', 'bill': bill(f'seq-{i}', mode='Split' if i % 10 == 0 else 'Cash') | ({'pays': [{'mode': 'Cash', 'amt': 50}, {'mode': 'UPI', 'amt': 55}]} if i % 10 == 0 else {})})
            assert s == 200, r
            lat.append(ms)
        R['settleMs'] = stat(lat)
        # ---- native cancel ----
        lat = []
        for i in range(0, 50):
            s, r, ms = api.call('/api/bill/cancel', {'billId': f'bb-seq-{i}', 'idemKey': f'cx-{i}'})
            assert s == 200, r
            lat.append(ms)
        R['cancelMs'] = stat(lat)
        # ---- repeated delivery ----
        rep = [api.call('/api/bill/settle', {'idemKey': 'seq-7', 'bill': bill('seq-7')})[1].get('alreadySettled') for _ in range(5)]
        R['repeatedSettleAllDeduplicated'] = all(rep)
        # ---- concurrency ----
        R['concurrency'] = {}
        acked = []
        for n in (1, 5, 20, 50, 100):
            lat, fails, lock = [], [], threading.Lock()
            per = max(2, 400 // n)

            def worker(w):
                for j in range(per):
                    key = f'cc{n}-{w}-{j}'
                    try:
                        s, r, ms = api.call('/api/bill/settle', {'idemKey': key, 'bill': bill(key)})
                        with lock:
                            (lat.append(ms), acked.append(key)) if s == 200 else fails.append(s)
                    except Exception as e:
                        with lock:
                            fails.append(repr(e)[:60])
            t1 = time.time()
            ts = [threading.Thread(target=worker, args=(w,)) for w in range(n)]
            [t.start() for t in ts]
            [t.join() for t in ts]
            wall = time.time() - t1
            R['concurrency'][n] = {**stat(lat), 'failures': len(fails), 'sample': fails[:2], 'billsPerSecond': round(len(lat) / wall, 1)}
            print(f'[{NBILLS}] {n} clients', R['concurrency'][n], flush=True)
        # ---- whole-document uploads (what the current UI sends for KOT / purchase / stock / expense) ----
        lat_get, lat_up = [], {}
        for kind in (() if BIG else ('kot', 'purchase', 'waste', 'expense')):
            lat_up[kind] = []
            for i in range(3 if NBILLS < 100000 else 1):
                s, db, ms = api.call('/api/db')
                lat_get.append(ms)
                d = db['data']
                if kind == 'kot':
                    d['kots'].append({'id': f'kk{i}', 'no': 10 ** 7 + i, 'date': LAST, 'items': [{'mid': 'mnu1', 'name': 'x', 'qty': 1}], 'status': 'new'})
                elif kind == 'purchase':
                    d['txns'].append({'id': f'pp{i}', 'type': 'Purchase', 'date': LAST, 'head': 'Ingredient 2', 'party': 'Supplier 1', 'amount': 500.5, 'mode': 'Credit', 'sid': 'stk1', 'qty': 10, 'mv': 1, 'inv': {'id': f'pinv{i}', 'total': 500.5, 'paid': 0, 'n': 1}})
                elif kind == 'waste':
                    d['moves'].append({'id': f'ww{i}', 'sid': 'stk2', 'qty': -1, 'type': 'waste', 'date': LAST})
                else:
                    d['txns'].append({'id': f'ee{i}', 'type': 'Expense', 'date': LAST, 'head': 'Gas', 'amount': 800, 'mode': 'Cash'})
                body = json.dumps({'baseVersion': db['version'], 'data': d}).encode()
                d = db = None
                s, r, ms = api.call('/api/db', body)
                assert s == 200, r
                lat_up[kind].append(ms)
        R['fullDownloadMs'] = stat(lat_get) if lat_get else 'not run at this size (memory; see 100k results)'
        R['fullUploadMs'] = {k: stat(v) for k, v in lat_up.items()} if lat_up else 'not run at this size (memory; see 100k results)'
        # ---- indexed queries ----
        qs = {'bills page': f'/api/q/bills?from={LAST}&to={LAST}&limit=50', 'bills month': f'/api/q/bills?from={LAST[:8]}01&to={LAST}&limit=50&offset=200',
              'day book': f'/api/q/daybook?date={LAST}', 'stock history': '/api/q/stock-history?sid=stk1&limit=50', 'supplier ledger': '/api/q/supplier-ledger?party=Supplier%201&limit=50',
              'audit': '/api/q/audit?limit=50', 'customer': '/api/q/customer?phone=9000000001'}
        R['queryMs'] = {}
        for name, path in qs.items():
            a = []
            for _ in range(20):
                s, r, ms = api.call(path)
                assert s == 200, (name, r)
                a.append(ms)
            R['queryMs'][name] = stat(a)
        # ---- backup + restore ----
        sdb = S.SqliteDoc(dbp)
        t1 = time.time()
        info = sdb.backup_to(os.path.join(DIR, 'Backups', 'setu-bench.sqlite.gz'), keep=0)
        R['backup'] = {**info, 'seconds': round(time.time() - t1, 1), 'MB': round(info['bytes'] / 1048576, 1)}
        t1 = time.time()
        rr = S.restore_backup(info['file'], os.path.join(DIR, 'restore-test.sqlite'))
        R['restore'] = {**rr, 'seconds': round(time.time() - t1, 1)}
        R['walMB'] = round(os.path.getsize(dbp + '-wal') / 1048576, 1) if os.path.exists(dbp + '-wal') else 0
        R['serverPeakRssMB'] = rss_mb(srv.pid)
        # ---- reconciliation after everything ----
        if BIG:
            # Reconcile from the database only (no second full copy in this process)
            srv.kill(); srv.wait()
            ex = sdb.export_document()
            d = SEC.public_view(ex)
        else:
            s, db, ms = api.call('/api/db')
            d = db['data']
            ex = sdb.export_document()
        have = {b.get('idemKey') for b in d['bills']}
        nos = [b['no'] for b in d['bills'] if not b.get('imported')]
        R['reconciliation'] = {
            'acknowledgedBillsLost': sum(1 for k in acked + [f'seq-{i}' for i in range(200)] if k not in have),
            'duplicateBillNumbers': len(nos) - len(set(nos)),
            'duplicateBillIds': len(d['bills']) - len({b['id'] for b in d['bills']}),
            'serverCopyEqualsDatabase': (S.canonical_hash(d) == S.canonical_hash(SEC.public_view(ex))) if not BIG else 'n/a (server stopped; reconciled from the database)',   # devices get the public view (no credential hashes)
            'moneyMatches': M.legacy_money(ex) == M.sql_money(sdb),
            'supplierBalancesMatch': M.legacy_supplier_dues(ex) == M.sql_supplier_dues(sdb, ex.get('supAlias')),
            'stockMismatches': sum(1 for k, v in M.legacy_stock(ex).items() if abs(v - M.sql_stock(sdb, ex).get(k, 0)) > 0.0015),
            'integrity': sdb.con().execute('PRAGMA integrity_check').fetchone()[0],
        }
        R['reconciliation']['pass'] = (R['reconciliation']['acknowledgedBillsLost'] == 0 and R['reconciliation']['duplicateBillNumbers'] == 0 and R['reconciliation']['duplicateBillIds'] == 0
                                       and R['reconciliation']['serverCopyEqualsDatabase'] is not False and R['reconciliation']['moneyMatches'] and R['reconciliation']['supplierBalancesMatch']
                                       and R['reconciliation']['stockMismatches'] == 0 and R['reconciliation']['integrity'] == 'ok')
        R['finalDbMB'] = round(os.path.getsize(dbp) / 1048576, 1)
    finally:
        srv.kill()
    json.dump(R, open(os.path.join(OUT, f'sqlite-bench-{NBILLS}.json'), 'w'), indent=1)
    print(json.dumps(R, indent=1))
    shutil.rmtree(DIR, ignore_errors=True)
