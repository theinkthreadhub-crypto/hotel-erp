"""Storage engine benchmark for the HoReCa One architecture decision (docs/architecture/ADR-0001).

Runs the SAME restaurant bill workload against
  * SQLite  (WAL, synchronous=FULL: every committed bill is on disk), in-process like setu_sqlite.py, and
  * PostgreSQL (fsync on, synchronous_commit on), a separate local server like an embedded install would run.

One bill transaction = next bill number + bill row + 4 item lines + 1-2 payments + 6 stock movements, idempotent on the
bill id (a retry never makes a second bill). Measured: cold start, history load, single-counter bill latency, concurrent
devices, a month report, memory (RSS/PSS of the processes that hold the data), disk, backup, crash (kill -9) recovery.

Synthetic data only. Needs PostgreSQL binaries (PG_BIN, default /usr/lib/postgresql/16/bin) and psycopg 3.
Results are written as JSON next to this file.  Example:

    python tools/bench/storage_engine_bench.py --history 100000 --bills 2000 --threads 8 --per-thread 500
"""
import argparse
import json
import os
import random
import shutil
import signal
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time

PG_BIN = os.environ.get('PG_BIN', '/usr/lib/postgresql/16/bin')
ITEMS = [('Paneer Tikka', 28000), ('Dal Makhani', 22000), ('Butter Naan', 6000), ('Jeera Rice', 16000),
         ('Masala Dosa', 12000), ('Cold Coffee', 15000), ('Veg Biryani', 24000), ('Gulab Jamun', 8000)]
SCHEMA = [
    "CREATE TABLE IF NOT EXISTS seq (name TEXT PRIMARY KEY, val BIGINT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS bills (id TEXT PRIMARY KEY, no BIGINT NOT NULL UNIQUE, day TEXT NOT NULL, "
    "total_p BIGINT NOT NULL, mode TEXT NOT NULL, doc TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS bill_items (bill_id TEXT NOT NULL, line INTEGER NOT NULL, item TEXT NOT NULL, "
    "qty INTEGER NOT NULL, price_p BIGINT NOT NULL, PRIMARY KEY (bill_id, line))",
    "CREATE TABLE IF NOT EXISTS payments (bill_id TEXT NOT NULL, k INTEGER NOT NULL, mode TEXT NOT NULL, "
    "amount_p BIGINT NOT NULL, PRIMARY KEY (bill_id, k))",
    "CREATE TABLE IF NOT EXISTS stock_moves (id TEXT PRIMARY KEY, sid TEXT NOT NULL, qty DOUBLE PRECISION NOT NULL, "
    "ref TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS bills_day ON bills(day)",
]


def make_bill(i, rnd, prefix='b'):
    lines = [(k, *ITEMS[rnd.randrange(len(ITEMS))], rnd.randint(1, 3)) for k in range(4)]
    total = sum(p * q for _, _, p, q in lines)
    mode = rnd.choice(['Cash', 'UPI', 'Card', 'Split'])
    pays = [('Cash', total // 2), ('UPI', total - total // 2)] if mode == 'Split' else [(mode, total)]
    day = '2026-%02d-%02d' % (1 + i % 12, 1 + i % 28)
    doc = json.dumps({'table': 'T-%d' % (i % 12 + 1), 'channel': 'Dine-In', 'gst': 5, 'items': len(lines)})
    moves = [('mv-%s%d-%d' % (prefix, i, k), 's%d' % rnd.randrange(40), -0.25 * (k + 1)) for k in range(6)]
    return {'id': '%s%d' % (prefix, i), 'day': day, 'total': total, 'mode': mode, 'doc': doc, 'lines': lines, 'pays': pays, 'moves': moves}


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(len(xs) * p / 100))], 3) if xs else None


def lat_summary(xs):
    return {'n': len(xs), 'p50_ms': pct(xs, 50), 'p95_ms': pct(xs, 95), 'p99_ms': pct(xs, 99), 'max_ms': round(max(xs), 3),
            'mean_ms': round(statistics.mean(xs), 3)}


def dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def proc_mem(pids):
    """Sum of RSS and PSS (MB) of the given processes (PSS counts shared pages once)."""
    rss = pss = 0
    for pid in pids:
        try:
            with open('/proc/%d/smaps_rollup' % pid) as f:
                for line in f:
                    if line.startswith('Rss:'):
                        rss += int(line.split()[1])
                    elif line.startswith('Pss:'):
                        pss += int(line.split()[1])
        except OSError:
            pass
    return {'rss_mb': round(rss / 1024, 1), 'pss_mb': round(pss / 1024, 1)}


# ------------------------------------------------------------------ SQLite
class SqliteEngine:
    name = 'sqlite'

    def __init__(self, folder):
        self.path = os.path.join(folder, 'bench.sqlite')
        self.local = threading.local()

    def con(self):
        c = getattr(self.local, 'c', None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('PRAGMA synchronous=FULL')
            c.execute('PRAGMA busy_timeout=30000')
            self.local.c = c
        return c

    def start(self):
        t = time.perf_counter()
        c = self.con()
        for s in SCHEMA:
            c.execute(s)
        c.execute("INSERT OR IGNORE INTO seq VALUES ('bill', 0)")
        return {'open_and_schema_ms': round((time.perf_counter() - t) * 1000, 1)}

    def settle(self, b):
        c = self.con()
        c.execute('BEGIN IMMEDIATE')
        try:
            if c.execute('SELECT 1 FROM bills WHERE id = ?', (b['id'],)).fetchone():
                c.execute('ROLLBACK')
                return None
            no = c.execute("UPDATE seq SET val = val + 1 WHERE name = 'bill' RETURNING val").fetchone()[0]
            c.execute('INSERT INTO bills VALUES (?,?,?,?,?,?)', (b['id'], no, b['day'], b['total'], b['mode'], b['doc']))
            c.executemany('INSERT INTO bill_items VALUES (?,?,?,?,?)', [(b['id'], k, n, q, p) for k, n, p, q in b['lines']])
            c.executemany('INSERT INTO payments VALUES (?,?,?,?)', [(b['id'], k, m, a) for k, (m, a) in enumerate(b['pays'])])
            c.executemany('INSERT INTO stock_moves VALUES (?,?,?,?)', [(i, s, q, b['id']) for i, s, q in b['moves']])
            c.execute('COMMIT')
            return no
        except Exception:
            c.execute('ROLLBACK')
            raise

    def bulk(self, bills):
        c = self.con()
        c.execute('BEGIN')
        no = c.execute("SELECT val FROM seq WHERE name='bill'").fetchone()[0]
        for b in bills:
            no += 1
            c.execute('INSERT INTO bills VALUES (?,?,?,?,?,?)', (b['id'], no, b['day'], b['total'], b['mode'], b['doc']))
            c.executemany('INSERT INTO bill_items VALUES (?,?,?,?,?)', [(b['id'], k, n, q, p) for k, n, p, q in b['lines']])
            c.executemany('INSERT INTO payments VALUES (?,?,?,?)', [(b['id'], k, m, a) for k, (m, a) in enumerate(b['pays'])])
            c.executemany('INSERT INTO stock_moves VALUES (?,?,?,?)', [(i, s, q, b['id']) for i, s, q in b['moves']])
        c.execute("UPDATE seq SET val = ? WHERE name='bill'", (no,))
        c.execute('COMMIT')

    def query(self, sql, args=()):
        return self.con().execute(sql.replace('%s', '?'), args).fetchall()

    def report(self):
        return self.query("SELECT p.mode, SUM(p.amount_p) FROM payments p JOIN bills b ON b.id = p.bill_id "
                          "WHERE b.day LIKE %s GROUP BY p.mode", ('2026-03-%',))

    def mem(self):
        return proc_mem([os.getpid()])

    def disk(self):
        return sum(os.path.getsize(self.path + s) for s in ('', '-wal', '-shm') if os.path.exists(self.path + s))

    def backup(self, out):
        t = time.perf_counter()
        dst = sqlite3.connect(out)
        self.con().backup(dst)
        dst.close()
        return {'ms': round((time.perf_counter() - t) * 1000, 1), 'bytes': os.path.getsize(out)}

    def integrity(self):
        return self.query('PRAGMA integrity_check')[0][0]

    def close(self):
        c = getattr(self.local, 'c', None)
        if c:
            c.close()
            self.local.c = None


# ------------------------------------------------------------------ PostgreSQL
class PostgresEngine:
    name = 'postgres'

    def __init__(self, folder, port):
        import psycopg  # noqa: F401
        self.folder, self.port = folder, port
        self.data = os.path.join(folder, 'pgdata')
        self.local = threading.local()
        self.dsn = 'host=127.0.0.1 port=%d dbname=bench user=bench' % port

    def _run(self, args, **kw):
        as_pg = ['runuser', '-u', 'postgres', '--'] if os.geteuid() == 0 else []
        return subprocess.run(as_pg + args, check=True, capture_output=True, text=True, **kw)

    def start(self, init=True):
        out = {}
        if init:
            os.makedirs(self.folder, exist_ok=True)
            if os.geteuid() == 0:
                shutil.chown(self.folder, 'postgres', 'postgres')
            pw = os.path.join(self.folder, 'pw')
            with open(pw, 'w') as f:
                f.write(os.urandom(16).hex())
            if os.geteuid() == 0:
                shutil.chown(pw, 'postgres', 'postgres')
            t = time.perf_counter()
            self._run([os.path.join(PG_BIN, 'initdb'), '-D', self.data, '-U', 'bench', '-A', 'scram-sha-256',
                       '--pwfile=' + pw, '-E', 'UTF8', '--locale=C'])
            out['initdb_ms'] = round((time.perf_counter() - t) * 1000, 1)
            self.password = open(pw).read().strip()
            os.remove(pw)
            out['data_dir_after_initdb_mb'] = round(dir_size(self.data) / 1e6, 1)
        t = time.perf_counter()
        self._run([os.path.join(PG_BIN, 'pg_ctl'), '-D', self.data, '-w', '-t', '60', '-l', os.path.join(self.folder, 'pg.log'),
                   '-o', '-p %d -c listen_addresses=127.0.0.1 -c unix_socket_directories=%s' % (self.port, self.folder), 'start'])
        out['pg_ctl_start_ms'] = round((time.perf_counter() - t) * 1000, 1)
        self.dsn = 'host=127.0.0.1 port=%d dbname=postgres user=bench password=%s' % (self.port, self.password)
        if init:
            import psycopg
            with psycopg.connect(self.dsn, autocommit=True) as c:
                c.execute('CREATE DATABASE bench')
        self.dsn = self.dsn.replace('dbname=postgres', 'dbname=bench')
        t = time.perf_counter()
        c = self.con()
        with c.transaction():
            for s in SCHEMA:
                c.execute(s)
            c.execute("INSERT INTO seq VALUES ('bill', 0) ON CONFLICT DO NOTHING")
        out['connect_and_schema_ms'] = round((time.perf_counter() - t) * 1000, 1)
        return out

    def con(self):
        import psycopg
        c = getattr(self.local, 'c', None)
        if c is None or c.closed:
            c = psycopg.connect(self.dsn, autocommit=True)
            self.local.c = c
        return c

    def settle(self, b):
        c = self.con()
        with c.transaction():
            if c.execute('SELECT 1 FROM bills WHERE id = %s', (b['id'],)).fetchone():
                return None
            no = c.execute("UPDATE seq SET val = val + 1 WHERE name = 'bill' RETURNING val").fetchone()[0]
            c.execute('INSERT INTO bills VALUES (%s,%s,%s,%s,%s,%s)', (b['id'], no, b['day'], b['total'], b['mode'], b['doc']))
            with c.cursor() as cur:
                cur.executemany('INSERT INTO bill_items VALUES (%s,%s,%s,%s,%s)', [(b['id'], k, n, q, p) for k, n, p, q in b['lines']])
                cur.executemany('INSERT INTO payments VALUES (%s,%s,%s,%s)', [(b['id'], k, m, a) for k, (m, a) in enumerate(b['pays'])])
                cur.executemany('INSERT INTO stock_moves VALUES (%s,%s,%s,%s)', [(i, s, q, b['id']) for i, s, q in b['moves']])
            return no

    def bulk(self, bills):
        c = self.con()
        with c.transaction():
            no = c.execute("SELECT val FROM seq WHERE name='bill'").fetchone()[0]
            with c.cursor() as cur:
                with cur.copy('COPY bills FROM STDIN') as cp:
                    for b in bills:
                        no += 1
                        b['_no'] = no
                        cp.write_row((b['id'], no, b['day'], b['total'], b['mode'], b['doc']))
                with cur.copy('COPY bill_items FROM STDIN') as cp:
                    for b in bills:
                        for k, n, p, q in b['lines']:
                            cp.write_row((b['id'], k, n, q, p))
                with cur.copy('COPY payments FROM STDIN') as cp:
                    for b in bills:
                        for k, (m, a) in enumerate(b['pays']):
                            cp.write_row((b['id'], k, m, a))
                with cur.copy('COPY stock_moves FROM STDIN') as cp:
                    for b in bills:
                        for i, s, q in b['moves']:
                            cp.write_row((i, s, q, b['id']))
            c.execute("UPDATE seq SET val = %s WHERE name='bill'", (no,))
        c.execute('ANALYZE')

    def query(self, sql, args=()):
        return self.con().execute(sql, args).fetchall()

    def report(self):
        return self.query("SELECT p.mode, SUM(p.amount_p) FROM payments p JOIN bills b ON b.id = p.bill_id "
                          "WHERE b.day LIKE %s GROUP BY p.mode", ('2026-03-%',))

    def pids(self):
        out = subprocess.run(['pgrep', '-u', 'postgres', '-f', 'postgres'], capture_output=True, text=True).stdout.split()
        return [int(p) for p in out]

    def mem(self):
        return proc_mem(self.pids())

    def disk(self):
        return dir_size(self.data)

    def backup(self, out):
        t = time.perf_counter()
        env = dict(os.environ, PGPASSWORD=self.password)
        subprocess.run([os.path.join(PG_BIN, 'pg_dump'), '-h', '127.0.0.1', '-p', str(self.port), '-U', 'bench', '-Fc', '-f', out, 'bench'],
                       check=True, env=env)
        return {'ms': round((time.perf_counter() - t) * 1000, 1), 'bytes': os.path.getsize(out)}

    def integrity(self):
        r = self.query("SELECT (SELECT COUNT(*) FROM bills), (SELECT MAX(no) FROM bills), (SELECT val FROM seq WHERE name='bill')")[0]
        return 'ok' if r[1] == r[2] else 'seq mismatch %s' % (r,)

    def postmaster_pid(self):
        with open(os.path.join(self.data, 'postmaster.pid')) as f:
            return int(f.readline())

    def close(self):
        c = getattr(self.local, 'c', None)
        if c and not c.closed:
            c.close()

    def stop(self):
        self.close()
        try:
            self._run([os.path.join(PG_BIN, 'pg_ctl'), '-D', self.data, '-m', 'fast', 'stop'])
        except subprocess.CalledProcessError:
            pass


# ------------------------------------------------------------------ scenario
def history(engine, n, rnd):
    t = time.perf_counter()
    for start in range(0, n, 5000):
        engine.bulk([make_bill(i, rnd, 'h') for i in range(start, min(n, start + 5000))])
    return round(time.perf_counter() - t, 1)


def single(engine, n, rnd):
    lat = []
    for i in range(n):
        b = make_bill(i, rnd, 's')
        t = time.perf_counter()
        engine.settle(b)
        lat.append((time.perf_counter() - t) * 1000)
    dup = engine.settle(make_bill(0, rnd, 's'))         # retry of an already-saved bill
    out = lat_summary(lat)
    out['retry_made_second_bill'] = dup is not None
    return out


def concurrent(engine, threads, per, rnd_seed):
    lat, errs, lock = [], [], threading.Lock()

    def worker(w):
        rnd = random.Random(rnd_seed + w)
        mine = []
        for i in range(per):
            b = make_bill(i, rnd, 'c%d-' % w)
            t = time.perf_counter()
            try:
                engine.settle(b)
            except Exception as e:                    # noqa: BLE001
                with lock:
                    errs.append(repr(e)[:120])
            mine.append((time.perf_counter() - t) * 1000)
        engine.close()
        with lock:
            lat.extend(mine)
    t = time.perf_counter()
    ts = [threading.Thread(target=worker, args=(w,)) for w in range(threads)]
    for x in ts:
        x.start()
    peak = {'rss_mb': 0, 'pss_mb': 0}
    while any(x.is_alive() for x in ts):
        m = engine.mem()
        peak = {k: max(peak[k], m[k]) for k in peak}
        time.sleep(0.2)
    for x in ts:
        x.join()
    wall = time.perf_counter() - t
    out = lat_summary(lat)
    out.update(threads=threads, bills=threads * per, wall_s=round(wall, 2), bills_per_s=round(threads * per / wall, 1),
               errors=len(errs), first_errors=errs[:3], peak_mem=peak)
    dup = engine.query('SELECT COUNT(*) - COUNT(DISTINCT no) FROM bills')[0][0]
    out['duplicate_bill_numbers'] = dup
    return out


CRASH_CHILD = r'''
import sys, json, random
sys.path.insert(0, sys.argv[1])
import storage_engine_bench as B
kind, folder, port = sys.argv[2], sys.argv[3], int(sys.argv[4])
if kind == 'sqlite':
    e = B.SqliteEngine(folder)
else:
    e = B.PostgresEngine(folder, port); e.password = sys.argv[5]
    e.dsn = 'host=127.0.0.1 port=%d dbname=bench user=bench password=%s' % (port, e.password)
rnd = random.Random(7)
i = 0
while True:
    b = B.make_bill(i, rnd, 'k')
    e.settle(b)
    print(b['id'], flush=True)                      # acknowledged = committed
    i += 1
'''


def crash(engine, kind, folder, port):
    """A writer acknowledges committed bills; we kill -9 (SQLite: the writer process; PostgreSQL: the server) mid-load."""
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(folder, 'crash_child.py')
    with open(script, 'w') as f:
        f.write(CRASH_CHILD)
    args = [sys.executable, script, here, kind, folder, str(port)] + ([engine.password] if kind == 'postgres' else [])
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    acked = []
    t = time.time()
    while time.time() - t < 3:
        line = p.stdout.readline()
        if line:
            acked.append(line.strip())
    if kind == 'sqlite':
        p.send_signal(signal.SIGKILL)
    else:
        pm = engine.postmaster_pid()                  # power cut: every database process dies at once
        kids = subprocess.run(['pgrep', '-P', str(pm)], capture_output=True, text=True).stdout.split()
        for pid in [pm] + [int(k) for k in kids]:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for _ in range(50):
            if not any(os.path.exists('/proc/%d' % int(x)) for x in [pm] + kids):
                break
            time.sleep(0.1)
        p.kill()
    for line in p.stdout:
        acked.append(line.strip())
    p.wait()
    t = time.perf_counter()
    if kind == 'postgres':
        engine.close()
        engine.start(init=False)                      # crash recovery replays the WAL
    else:
        engine.close()
    rec_ms = round((time.perf_counter() - t) * 1000, 1)
    present = {r[0] for r in engine.query("SELECT id FROM bills WHERE id LIKE %s", ('k%',))}
    lost = [a for a in acked if a not in present]
    return {'acknowledged': len(acked), 'present_after_restart': len(present), 'acknowledged_but_lost': len(lost),
            'restart_ms': rec_ms, 'integrity': engine.integrity()}


def run(kind, a):
    rnd = random.Random(42)
    folder = tempfile.mkdtemp(prefix='horeca-bench-%s-' % kind)
    os.chmod(folder, 0o755)                           # the postgres OS user must reach its data folder
    port = 55000 + random.randrange(900)
    eng = SqliteEngine(folder) if kind == 'sqlite' else PostgresEngine(os.path.join(folder, 'pg'), port)
    res = {'engine': kind}
    try:
        res['start'] = eng.start()
        res['idle_mem_empty'] = eng.mem()
        res['history_load_s'] = history(eng, a.history, rnd)
        res['disk_after_history_mb'] = round(eng.disk() / 1e6, 1)
        res['single_counter'] = single(eng, a.bills, rnd)
        res['concurrent'] = concurrent(eng, a.threads, a.per_thread, 99)
        t = time.perf_counter()
        for _ in range(5):
            eng.report()
        res['month_report_ms'] = round((time.perf_counter() - t) * 200, 1)
        res['idle_mem_loaded'] = eng.mem()
        res['backup'] = eng.backup(os.path.join(folder, 'backup.bin'))
        res['disk_final_mb'] = round(eng.disk() / 1e6, 1)
        res['crash'] = crash(eng, kind, folder if kind == 'sqlite' else eng.folder, port)
        if kind == 'postgres':
            t = time.perf_counter()
            eng.stop()
            res['clean_stop_ms'] = round((time.perf_counter() - t) * 1000, 1)
            res2 = eng.start(init=False)
            res['warm_restart'] = res2
            res['runtime_install_mb'] = round((dir_size('/usr/lib/postgresql/16') + dir_size('/usr/share/postgresql/16')) / 1e6, 1)
    finally:
        if kind == 'postgres':
            eng.stop()
        else:
            eng.close()
        shutil.rmtree(folder, ignore_errors=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--history', type=int, default=100000)
    ap.add_argument('--bills', type=int, default=2000)
    ap.add_argument('--threads', type=int, default=8)
    ap.add_argument('--per-thread', type=int, default=500)
    ap.add_argument('--engines', default='sqlite,postgres')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results.json'))
    a = ap.parse_args()
    env = {'python': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version, 'cpus': os.cpu_count(),
           'platform': sys.platform, 'kernel': os.uname().release}
    try:
        env['postgres'] = subprocess.run([os.path.join(PG_BIN, 'postgres'), '-V'], capture_output=True, text=True).stdout.strip()
    except OSError:
        pass
    results = {'env': env, 'args': vars(a), 'runs': [run(k, a) for k in a.engines.split(',')]}
    with open(a.out, 'w') as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
